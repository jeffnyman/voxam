using System.Text;

namespace Voxam.Core;

/// <summary>Enough of a Blorb to take the session banner's census and check identity.</summary>
public sealed class Blorb
{
    private const int RectSize = 8;
    private const int ResolutionHeader = 24;
    private const int ResolutionEntry = 28;

    public int Pictures { get; private init; }
    public int Sounds { get; private init; }
    public bool HasStory { get; private init; }
    private byte[]? _identity;

    /// <summary>
    /// The packaged Z-code story, or null: an Exec resource is
    /// numbered 0, and only the ZCOD executable format belongs to
    /// this machine.
    /// </summary>
    public byte[]? Story { get; private init; }

    /// <summary>
    /// The Version 6 art as a gallery: sizes eager, pixels lazy. PNG
    /// pictures and Rect placeholders make the census; a JPEG, which
    /// no Infocom Version 6 set carries, is left out, because a
    /// picture this machine cannot draw is not available in
    /// picture_data's sense (§15).
    /// </summary>
    public Gallery Gallery { get; private init; } = Gallery.Empty;

    public static Blorb Load(byte[] data)
    {
        if (data.Length < 12 || Ascii(data, 0) != "FORM" || Ascii(data, 8) != "IFRS")
        {
            throw new ZMachineException("the resource file is not a Blorb: no FORM IFRS header");
        }

        var pictures = 0;
        var sounds = 0;
        var story = false;
        byte[]? packaged = null;
        byte[]? identity = null;
        var art = new Dictionary<int, object>();
        var release = 0;
        Resolution? resolution = null;
        var pos = 12;

        while (pos + 8 <= data.Length)
        {
            var id = Ascii(data, pos);
            var length = Word32(data, pos + 4);
            var payload = pos + 8;

            if (payload + length > data.Length)
            {
                throw new ZMachineException($"the {id} chunk claims {length} bytes, but the file ends before them (Blorb: IFF)");
            }

            if (id == "RIdx")
            {
                if (length < 4)
                {
                    throw new ZMachineException("the RIdx chunk is too short to hold its own count");
                }

                var count = Word32(data, payload);

                if (length != 4 + 12 * count)
                {
                    throw new ZMachineException($"the RIdx count of {count} needs {4 + 12 * count} bytes, but the chunk holds {length} (Blorb: Resource Index Chunk)");
                }

                for (var k = 0; k < count; k++)
                {
                    var entry = payload + 4 + 12 * k;
                    var usage = Ascii(data, entry);

                    if (usage == "Pict")
                    {
                        pictures++;
                        Hang(data, art, Word32(data, entry + 4), Word32(data, entry + 8));
                    }
                    else if (usage == "Snd ")
                    {
                        sounds++;
                    }
                    else if (usage == "Exec")
                    {
                        story = true;

                        if (Word32(data, entry + 4) == 0)
                        {
                            packaged = Executable(data, Word32(data, entry + 8));
                        }
                    }
                }
            }
            else if (id == "IFhd")
            {
                identity = data[payload..(payload + length)];
            }
            else if (id == "RelN")
            {
                if (length != 2)
                {
                    throw new ZMachineException($"a RelN chunk is a two-byte release, but this one holds {length} bytes (Blorb: Release Number Chunk)");
                }

                release = (data[payload] << 8) | data[payload + 1];
            }
            else if (id == "Reso")
            {
                resolution = Resolved(data, payload, length);
            }

            pos = payload + length + (length & 1);
        }

        return new Blorb
        {
            Pictures = pictures,
            Sounds = sounds,
            HasStory = story,
            Story = packaged,
            Gallery = new Gallery(art, release, resolution),
            _identity = identity,
        };
    }

    // One Pict entry's art, when this machine can draw it: a PNG
    // keeps its bytes, and a Rect is a size with no pixels at all
    // (Blorb: Picture Resource Chunks).
    private static void Hang(byte[] data, Dictionary<int, object> art, int number, int offset)
    {
        if (offset < 0 || offset + 8 > data.Length)
        {
            throw new ZMachineException($"picture {number} points at offset {offset}, where no chunk begins (Blorb: Resource Index Chunk)");
        }

        var id = Ascii(data, offset);
        var length = Word32(data, offset + 4);

        if (offset + 8 + length > data.Length)
        {
            throw new ZMachineException($"the {id} chunk claims {length} bytes, but the file ends before them (Blorb: IFF)");
        }

        if (id == "PNG ")
        {
            art[number] = data[(offset + 8)..(offset + 8 + length)];
        }
        else if (id == "Rect")
        {
            if (length != RectSize)
            {
                throw new ZMachineException($"picture {number} is a Rect of {length} bytes, but a Rect is a width and a height (Blorb: Picture Resource Chunks)");
            }

            art[number] = new Placard(Word32(data, offset + 8), Word32(data, offset + 12));
        }
    }

    // The Reso chunk: six words of standard, minimum and maximum
    // window sizes, then 28-byte entries of a picture number and its
    // three scaling ratios (Blorb: The Resolution Chunk).
    private static Resolution Resolved(byte[] data, int payload, int length)
    {
        if (length < ResolutionHeader || (length - ResolutionHeader) % ResolutionEntry != 0)
        {
            throw new ZMachineException($"a Reso chunk is a 24-byte header and 28-byte entries, but this one holds {length} bytes (Blorb: The Resolution Chunk)");
        }

        var width = Word32(data, payload);
        var height = Word32(data, payload + 4);

        if (width == 0 || height == 0)
        {
            throw new ZMachineException($"the Reso standard window is {width} by {height}, but px and py must be non-zero (Blorb: The Resolution Chunk)");
        }

        var scalings = new Dictionary<int, Scaling>();

        for (var start = payload + ResolutionHeader; start < payload + length; start += ResolutionEntry)
        {
            var words = new int[7];

            for (var k = 0; k < words.Length; k++)
            {
                words[k] = Word32(data, start + 4 * k);
            }

            scalings[words[0]] = new Scaling(
                Standard(words[0], words[1], words[2]),
                Limit(words[0], words[3], words[4]),
                Limit(words[0], words[5], words[6]));
        }

        return new Resolution(width, height, scalings);
    }

    // A picture's standard ratio, which has no zero form.
    private static Ratio Standard(int number, int numerator, int denominator) =>
        denominator == 0
            ? throw new ZMachineException($"picture {number}'s standard ratio divides by zero (Blorb: The Resolution Chunk)")
            : new Ratio(numerator, denominator);

    // A minimum or maximum ratio; zero over zero means no limit at all,
    // and only whole (Blorb: The Resolution Chunk).
    private static Ratio? Limit(int number, int numerator, int denominator)
    {
        if (numerator == 0 && denominator == 0)
        {
            return null;
        }

        if (numerator == 0 || denominator == 0)
        {
            throw new ZMachineException($"picture {number} has a half-zero limiting ratio, which is neither a limit nor none (Blorb: The Resolution Chunk)");
        }

        return new Ratio(numerator, denominator);
    }

    // The chunk an Exec entry points at, when it is Z-code.
    private static byte[]? Executable(byte[] data, int offset)
    {
        if (offset < 0 || offset + 8 > data.Length || Ascii(data, offset) != "ZCOD")
        {
            return null;
        }

        var length = Word32(data, offset + 4);
        return data[(offset + 8)..(offset + 8 + length)];
    }

    private static int Word32(byte[] data, int at) => (data[at] << 24) | (data[at + 1] << 16) | (data[at + 2] << 8) | data[at + 3];

    /// <summary>A one-line census for the session banner.</summary>
    public string Described()
    {
        var parts = new List<string>();

        if (Pictures > 0) parts.Add($"{Pictures} picture{(Pictures != 1 ? "s" : "")}");
        if (Sounds > 0) parts.Add($"{Sounds} sound{(Sounds != 1 ? "s" : "")}");
        if (HasStory) parts.Add("a packaged story");

        return parts.Count > 0 ? string.Join(", ", parts) : "no resources";
    }

    /// <summary>Whether the identifier chunk names this story; absence matches anything.</summary>
    public bool Matches(byte[] story)
    {
        if (_identity is null || _identity.Length < 10)
        {
            return true;
        }

        for (var k = 0; k < 2; k++)
        {
            if (_identity[k] != story[Header.Release + k]) return false;
        }

        for (var k = 0; k < 6; k++)
        {
            if (_identity[2 + k] != story[Header.Serial + k]) return false;
        }

        return _identity[8] == story[Header.Checksum] && _identity[9] == story[Header.Checksum + 1];
    }

    private static string Ascii(byte[] data, int at) => Encoding.ASCII.GetString(data, at, 4);
}
