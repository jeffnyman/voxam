using System.Text;
using Voxam.Core;
using Voxam.Core.Glulx.Glk;

namespace Voxam.Tests.Glulx.Glk;

/// <summary>
/// Glk's view of a Blorb: the pictures it measures, the sounds it hands
/// out whole, and the data files a resource stream opens over.
/// </summary>
public sealed class ResourcesTests
{
    // A picture is measured from its own bytes, so a size can be
    // reported where nothing can be drawn, and the measurement is kept
    // rather than made again.
    [Fact]
    public void APictureIsMeasuredFromItsOwnBytesAndRemembered()
    {
        var resources = Over(Blorb.Load(Packaged(("Pict", 1, Png(640, 400)))));
        var image = resources.Image(1);

        Assert.NotNull(image);
        Assert.Equal(1, image.Number);
        Assert.Equal("PNG ", image.Kind);
        Assert.Equal(640, image.Width);
        Assert.Equal(400, image.Height);
        Assert.Same(image, resources.Image(1));
    }

    // A number no picture answers is nothing, whether the Blorb lacks
    // it, the container is missing altogether, or the bytes are of a
    // kind nothing can measure.
    [Fact]
    public void APictureNothingCanMeasureIsNothing()
    {
        Assert.Null(new GlkResources().Image(1));
        Assert.Null(Over(Blorb.Load(Packaged(("Pict", 1, Png(4, 4))))).Image(2));

        // A Rect is a size with no pixels: a picture, but not one whose
        // bytes carry dimensions.
        var flat = Over(Blorb.Load(Packaged(("Pict", 1, ("Rect", new byte[8])))));

        Assert.Null(flat.Image(1));
    }

    // A sound arrives whole. An AIFF is a FORM, and a FORM resource is
    // a complete nested file, so its header comes back with it.
    [Fact]
    public void ASoundArrivesWholeHeaderAndAll()
    {
        var resources = Over(Blorb.Load(Packaged(
            ("Snd ", 3, ("FORM", Encoding.ASCII.GetBytes("AIFFbody"))),
            ("Snd ", 4, ("OGGV", Encoding.ASCII.GetBytes("ogg"))))));

        Assert.Equal(
            Encoding.ASCII.GetBytes("FORM\0\0\0\bAIFFbody"), resources.Audio(3));

        // Everything else is the payload as it stands.
        Assert.Equal(Encoding.ASCII.GetBytes("ogg"), resources.Audio(4));
        Assert.Null(resources.Audio(9));
        Assert.Null(new GlkResources().Audio(3));
    }

    // A data resource says whether it is text, since that is what
    // decides how a Unicode stream reads it (Glk: Resource Streams).
    [Fact]
    public void ADataResourceSaysWhetherItIsText()
    {
        var resources = Over(Blorb.Load(Packaged(
            ("Data", 1, ("TEXT", Encoding.ASCII.GetBytes("hello"))),
            ("Data", 2, ("BINA", new byte[] { 1, 2, 3, 4 })),
            ("Data", 3, ("FORM", Encoding.ASCII.GetBytes("XXXXbody"))))));

        Assert.Equal((Encoding.ASCII.GetBytes("hello"), true), resources.Datafile(1));
        Assert.Equal((new byte[] { 1, 2, 3, 4 }, false), resources.Datafile(2));

        // A FORM data container is a whole nested file, like a sound.
        var (bytes, isText) = resources.Datafile(3)!.Value;

        Assert.Equal(Encoding.ASCII.GetBytes("FORM\0\0\0\bXXXXbody"), bytes);
        Assert.False(isText);

        Assert.Null(resources.Datafile(9));
        Assert.Null(new GlkResources().Datafile(1));
    }

    // The index answers by usage and by number together: a picture
    // three is not a sound three.
    [Fact]
    public void TheIndexAnswersByUsageAndNumberTogether()
    {
        var blorb = Blorb.Load(Packaged(
            ("Pict", 3, Png(2, 2)),
            ("Snd ", 3, ("OGGV", Encoding.ASCII.GetBytes("ogg")))));

        Assert.Equal("PNG ", blorb.Resource("Pict", 3)!.Id);
        Assert.Equal("OGGV", blorb.Resource("Snd ", 3)!.Id);
        Assert.Null(blorb.Resource("Data", 3));
        Assert.Null(blorb.Resource("Pict", 4));
    }

    // An index entry pointing where no chunk begins is the file lying
    // about itself, and is refused.
    [Fact]
    public void AnEntryPointingNowhereIsRefused()
    {
        var beyond = Assert.Throws<ZMachineException>(
            () => Blorb.Load(Astray("Snd ", 1, 0x7FFF0000)));

        Assert.Equal(
            "Snd  resource 1 points at offset 2147418112, where no chunk begins (Blorb: Resource Index Chunk)",
            beyond.Message);

        // And a chunk whose own length runs past the file is the same
        // lie, told one level down.
        var truncated = Packaged(("Data", 1, ("BINA", new byte[] { 1, 2, 3, 4 })));
        var at = Offset(truncated, "BINA");

        truncated[at + 4] = 0x7F;

        Assert.Throws<ZMachineException>(() => Blorb.Load(truncated));
    }

    // A JPEG hides its size in a start-of-frame segment, which has to
    // be walked to: past standalone markers that carry no length, and
    // past the tables that sit in the frame numbering without being
    // frames.
    [Fact]
    public void AJpegIsWalkedToItsStartOfFrame()
    {
        Assert.Equal(
            (800, 600),
            GlkResources.ImageSize([
                0xFF, 0xD8,
                0xFF, 0x01,                           // a standalone marker
                0xFF, 0xD3,                           // a restart marker
                0xFF, 0xD8,                           // and another start of image
                0xFF, 0xA0, 0x00, 0x04, 0x01, 0x02,   // a segment below the frames
                0xFF, 0xE0, 0x00, 0x04, 0x01, 0x02,   // an application segment
                0xFF, 0xC4, 0x00, 0x04, 0x01, 0x02,   // a Huffman table, not a frame
                0xFF, 0xC8, 0x00, 0x04, 0x01, 0x02,   // the JPEG extension, nor is it
                0xFF, 0xCC, 0x00, 0x04, 0x01, 0x02,   // nor arithmetic conditioning
                0xFF, 0xC0, 0x00, 0x11, 0x08,
                0x02, 0x58,                           // height
                0x03, 0x20,                           // width
            ]));
    }

    // A JPEG that is not one, that ends before its frame, or that runs
    // out mid-frame, has no size to report.
    [Fact]
    public void AJpegThatCannotBeWalkedHasNoSize()
    {
        // A segment that does not begin with a marker.
        Assert.Null(GlkResources.ImageSize([0xFF, 0xD8, 0x00, 0x01, 0x02, 0x03]));

        // Segments that simply run out.
        Assert.Null(GlkResources.ImageSize([0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x04, 0x01, 0x02]));

        // A frame the file ends inside.
        Assert.Null(GlkResources.ImageSize([0xFF, 0xD8, 0xFF, 0xC0, 0x00, 0x11, 0x08, 0x02]));
    }

    // Anything that is neither a PNG nor a JPEG has no size, and so
    // does a PNG too short to hold its own header.
    [Fact]
    public void OnlyTheTwoKindsAreMeasured()
    {
        Assert.Null(GlkResources.ImageSize([]));
        Assert.Null(GlkResources.ImageSize(Encoding.ASCII.GetBytes("GIF89a")));
        Assert.Null(GlkResources.ImageSize([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A]));

        // A marker byte that begins something other than an image.
        Assert.Null(GlkResources.ImageSize([0xFF, 0x00, 0x01, 0x02]));
    }

    /// <summary>A minimal PNG: the signature, then an IHDR carrying a size.</summary>
    private static (string Id, byte[] Payload) Png(int width, int height)
    {
        var bytes = new List<byte> { 0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A };

        bytes.AddRange([0, 0, 0, 13]);
        bytes.AddRange(Encoding.ASCII.GetBytes("IHDR"));
        bytes.AddRange(Word(width));
        bytes.AddRange(Word(height));

        return ("PNG ", [.. bytes]);
    }

    /// <summary>A Blorb carrying the named resources, in order.</summary>
    private static byte[] Packaged(params (string Usage, int Number, (string Id, byte[] Payload) Chunk)[] pieces)
    {
        var index = new List<byte>(Word(pieces.Length));
        var body = new List<byte>();

        // The RIdx chunk comes first, so every offset is counted from
        // the end of it: the FORM header is 12 bytes, and the index is
        // its own 8-byte header plus four bytes of count plus twelve
        // per entry.
        var at = 12 + 8 + 4 + (12 * pieces.Length);

        foreach (var (usage, number, chunk) in pieces)
        {
            index.AddRange(Encoding.ASCII.GetBytes(usage));
            index.AddRange(Word(number));
            index.AddRange(Word(at));

            var bytes = Chunk(chunk.Id, chunk.Payload);

            body.AddRange(bytes);
            at += bytes.Length;
        }

        return Form([Chunk("RIdx", [.. index]), .. Split(body)]);
    }

    /// <summary>A Blorb whose one entry points at an offset nothing is at.</summary>
    private static byte[] Astray(string usage, int number, int offset)
    {
        var index = new List<byte>(Word(1));

        index.AddRange(Encoding.ASCII.GetBytes(usage));
        index.AddRange(Word(number));
        index.AddRange(Word(offset));

        return Form(Chunk("RIdx", [.. index]));
    }

    /// <summary>Where a chunk of a kind begins inside an assembled file.</summary>
    private static int Offset(byte[] data, string id)
    {
        var wanted = Encoding.ASCII.GetBytes(id);

        for (var at = 0; at + 4 <= data.Length; at++)
        {
            if (data.AsSpan(at, 4).SequenceEqual(wanted))
            {
                return at;
            }
        }

        throw new InvalidOperationException(id);
    }

    private static GlkResources Over(Blorb blorb) => new(blorb);

    private static byte[][] Split(List<byte> body) => [[.. body]];

    private static byte[] Word(int value) =>
        [(byte)(value >> 24), (byte)(value >> 16), (byte)(value >> 8), (byte)value];

    private static byte[] Chunk(string id, byte[] payload)
    {
        var bytes = new List<byte>(Encoding.ASCII.GetBytes(id));

        bytes.AddRange(Word(payload.Length));
        bytes.AddRange(payload);

        if (payload.Length % 2 != 0)
        {
            bytes.Add(0);
        }

        return [.. bytes];
    }

    private static byte[] Form(params byte[][] chunks)
    {
        var body = new List<byte>(Encoding.ASCII.GetBytes("IFRS"));

        foreach (var chunk in chunks)
        {
            body.AddRange(chunk);
        }

        return Chunk("FORM", [.. body]);
    }
}
