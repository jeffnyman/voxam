namespace Voxam.Core.Glulx.Glk;

/// <summary>
/// One picture resource, measured.
/// </summary>
/// <param name="Number">The number the game asks for it by.</param>
/// <param name="Kind">
/// The Blorb chunk type: PNG followed by a space, or JPEG (Blorb:
/// Picture Resource Chunks).
/// </param>
/// <param name="Data">The picture bytes, ready for a display to decode.</param>
/// <param name="Width">The width in pixels.</param>
/// <param name="Height">The height in pixels.</param>
public sealed record ImageInfo(int Number, string Kind, byte[] Data, int Width, int Height);

/// <summary>
/// Glk's view of the Blorb resources: pictures, sounds, data files.
///
/// The Blorb reader reads the container; this decides what its contents
/// mean to Glk: the pictures glk_image_draw names (Glk: Graphics), the
/// sounds a channel plays (Glk: Sound Resources), and the data chunks a
/// resource stream opens over (Glk: Resource Streams). The split matters
/// because the interpreter needs the same container to find the
/// executable chunk before any of this exists.
///
/// Image sizes are read out of the picture bytes here rather than asked
/// of the display, because glk_image_get_info must answer even when
/// nothing can be drawn: a game may lay out a window from the
/// dimensions and then discover it has no graphics (Glk: Testing for
/// Graphics Capabilities).
///
/// The reference also hands pictures and sounds out as data URLs, for
/// the display that speaks a wire protocol to a browser. That display
/// is the reference's alone, so those two are not here; what a drawing
/// display wants is the bytes, which it gets.
/// </summary>
public sealed class GlkResources
{
    // The usages a game asks about, as the index spells them (Blorb:
    // Resource Index Chunk).
    private const string Picture = "Pict";
    private const string Sound = "Snd ";
    private const string Datum = "Data";

    // A nested IFF file, which is what an AIFF sound and a data
    // container both arrive as.
    private const string Form = "FORM";

    // The Blorb chunk type marking a data resource as text rather than
    // bytes (Blorb: Data Resource Chunks).
    private const string Text = "TEXT";

    private static readonly byte[] PngSignature = [0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A];

    // PNG requires the IHDR chunk to come first, so the dimensions sit
    // at fixed offsets.
    private const int PngHeaderEnd = 24;
    private const int IhdrWidthAt = 16;
    private const int IhdrHeightAt = 20;

    private const byte Marker = 0xFF;
    private const byte StartOfImage = 0xD8;
    private const byte Temporary = 0x01;
    private const byte StandaloneLow = 0xD0;
    private const byte StandaloneHigh = 0xD7;
    private const int SofNeed = 9;
    private const int SofHeightAt = 5;
    private const int SofWidthAt = 7;

    private readonly Dictionary<int, ImageInfo?> _images = [];

    /// <summary>Stand in front of a container, or of nothing.</summary>
    /// <param name="blorb">The container, or null without one.</param>
    public GlkResources(Blorb? blorb = null) => Blorb = blorb;

    /// <summary>The container, or null without one.</summary>
    public Blorb? Blorb { get; }

    /// <summary>
    /// Look up a picture, measuring it on first use.
    ///
    /// A picture whose dimensions cannot be read answers null: a size
    /// glk_image_get_info cannot report is a picture the game cannot lay
    /// out (Glk: Graphics).
    /// </summary>
    /// <param name="number">The number the game asks for it by.</param>
    public ImageInfo? Image(int number)
    {
        if (_images.TryGetValue(number, out var known))
        {
            return known;
        }

        ImageInfo? info = null;
        var found = Blorb?.Resource(Picture, number);

        if (found is not null && ImageSize(found.Payload) is var (width, height))
        {
            info = new ImageInfo(number, found.Id, found.Payload, width, height);
        }

        _images[number] = info;

        return info;
    }

    /// <summary>
    /// A sound resource's bytes, or null if absent.
    ///
    /// AIFF sounds are stored as FORM chunks, and an AIFF file is that
    /// FORM, header included (Blorb: Sound Resource Chunks). Handing an
    /// audio decoder the body alone would give it a file starting at
    /// "AIFF" with no container.
    /// </summary>
    /// <param name="number">The number the game asks for it by.</param>
    public byte[]? Audio(int number)
    {
        var found = Blorb?.Resource(Sound, number);

        return found is null ? null : Contents(found);
    }

    /// <summary>
    /// A data resource as its bytes and whether it is text.
    ///
    /// Blorb marks a data chunk TEXT or BINA (Blorb: Data Resource
    /// Chunks); the distinction only matters when the resource is opened
    /// as a Unicode stream, where text means UTF-8 and binary means
    /// four-byte words (Glk: Resource Streams).
    /// </summary>
    /// <param name="number">The number the game asks for it by.</param>
    public (byte[] Bytes, bool IsText)? Datafile(int number)
    {
        var found = Blorb?.Resource(Datum, number);

        if (found is null)
        {
            return null;
        }

        return found.Id == Form
            ? (Contents(found), false)
            : (found.Payload, found.Id == Text);
    }

    /// <summary>
    /// The pixel dimensions of a PNG or a JPEG, or null for anything
    /// else. A JPEG hides them in a start-of-frame segment that has to
    /// be walked to.
    /// </summary>
    /// <param name="data">The picture bytes.</param>
    public static (int Width, int Height)? ImageSize(byte[] data)
    {
        ArgumentNullException.ThrowIfNull(data);

        if (data.AsSpan().StartsWith(PngSignature) && data.Length >= PngHeaderEnd)
        {
            return (Word32(data, IhdrWidthAt), Word32(data, IhdrHeightAt));
        }

        return data.Length >= 2 && data[0] == Marker && data[1] == StartOfImage
            ? JpegSize(data)
            : null;
    }

    /// <summary>Walk JPEG segments until a start-of-frame marker turns up.</summary>
    private static (int Width, int Height)? JpegSize(byte[] data)
    {
        var position = 2;

        while (position + 4 <= data.Length)
        {
            if (data[position] != Marker)
            {
                return null;
            }

            var marker = data[position + 1];

            if (marker is StartOfImage or Temporary
                || (marker >= StandaloneLow && marker <= StandaloneHigh))
            {
                // Standalone markers carry no length word.
                position += 2;

                continue;
            }

            if (IsStartOfFrame(marker))
            {
                return position + SofNeed > data.Length
                    ? null
                    : (Word16(data, position + SofWidthAt), Word16(data, position + SofHeightAt));
            }

            position += 2 + Word16(data, position + 2);
        }

        return null;
    }

    /// <summary>
    /// Whether a marker carries the image dimensions. C4, C8 and CC sit
    /// in the start-of-frame numbering but are not frames: they are the
    /// Huffman table, the JPEG extension, and arithmetic coding.
    /// </summary>
    private static bool IsStartOfFrame(byte marker) =>
        marker >= 0xC0 && marker < 0xD0 && marker is not (0xC4 or 0xC8 or 0xCC);

    /// <summary>
    /// A resource's bytes: the whole chunk for a FORM, the body else.
    ///
    /// A FORM resource is a complete nested IFF file, an AIFF sound or a
    /// data container, so its header belongs to the contents. Everything
    /// else (PNG, JPEG, TEXT, BINA) is raw payload.
    /// </summary>
    private static byte[] Contents(Resource found)
    {
        if (found.Id != Form)
        {
            return found.Payload;
        }

        var whole = new byte[8 + found.Payload.Length];

        System.Text.Encoding.ASCII.GetBytes(found.Id).CopyTo(whole, 0);

        whole[4] = (byte)(found.Payload.Length >> 24);
        whole[5] = (byte)(found.Payload.Length >> 16);
        whole[6] = (byte)(found.Payload.Length >> 8);
        whole[7] = (byte)found.Payload.Length;

        found.Payload.CopyTo(whole, 8);

        return whole;
    }

    private static int Word32(byte[] data, int at) =>
        (data[at] << 24) | (data[at + 1] << 16) | (data[at + 2] << 8) | data[at + 3];

    private static int Word16(byte[] data, int at) => (data[at] << 8) | data[at + 1];
}
