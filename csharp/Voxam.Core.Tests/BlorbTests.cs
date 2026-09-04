using System.Text;
using Voxam.Core.Tests.Support;

namespace Voxam.Core.Tests;

public class BlorbTests
{
    private static byte[] Chunk(string id, byte[] payload)
    {
        var bytes = new List<byte>(Encoding.ASCII.GetBytes(id));
        bytes.AddRange([(byte)(payload.Length >> 24), (byte)(payload.Length >> 16), (byte)(payload.Length >> 8), (byte)payload.Length]);
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

    private static byte[] Index(params string[] usages)
    {
        var bytes = new List<byte> { 0, 0, 0, (byte)usages.Length };

        foreach (var usage in usages)
        {
            bytes.AddRange(Encoding.ASCII.GetBytes(usage));
            bytes.AddRange(new byte[8]);
        }

        return Chunk("RIdx", [.. bytes]);
    }

    [Fact]
    public void TheCensusCountsPicturesSoundsAndAStory()
    {
        var blorb = Blorb.Load(Form(Index("Pict", "Pict", "Snd ", "Exec", "Data")));
        Assert.Equal(2, blorb.Pictures);
        Assert.Equal(1, blorb.Sounds);
        Assert.True(blorb.HasStory);
        Assert.Equal("2 pictures, 1 sound, a packaged story", blorb.Described());
        Assert.Equal("1 picture", Blorb.Load(Form(Index("Pict"))).Described());
        Assert.Equal("2 sounds", Blorb.Load(Form(Index("Snd ", "Snd "))).Described());
        Assert.Equal("no resources", Blorb.Load(Form(Index())).Described());
    }

    [Fact]
    public void AnythingElseIsNotABlorb()
    {
        Assert.Throws<ZMachineException>(() => Blorb.Load(new byte[4]));
        Assert.Throws<ZMachineException>(() => Blorb.Load(Chunk("FORM", Encoding.ASCII.GetBytes("AIFF"))));
        Assert.Throws<ZMachineException>(() => Blorb.Load(Chunk("RIFF", Encoding.ASCII.GetBytes("IFRS"))));
    }

    [Fact]
    public void TheIdentifierChunkNamesAStory()
    {
        var builder = new StoryBuilder();
        builder.Quit();
        var story = builder.Build();
        var identity = new byte[13];
        Array.Copy(story, Header.Release, identity, 0, 2);
        Array.Copy(story, Header.Serial, identity, 2, 6);
        Array.Copy(story, Header.Checksum, identity, 8, 2);
        Assert.True(Blorb.Load(Form(Index(), Chunk("IFhd", identity))).Matches(story));
        Assert.True(Blorb.Load(Form(Index())).Matches(story));
        Assert.True(Blorb.Load(Form(Index(), Chunk("IFhd", new byte[4]))).Matches(story));

        var wrongRelease = (byte[])identity.Clone();
        wrongRelease[1] ^= 1;
        Assert.False(Blorb.Load(Form(Index(), Chunk("IFhd", wrongRelease))).Matches(story));
        var wrongSerial = (byte[])identity.Clone();
        wrongSerial[5] = (byte)'x';
        Assert.False(Blorb.Load(Form(Index(), Chunk("IFhd", wrongSerial))).Matches(story));
        var wrongChecksum = (byte[])identity.Clone();
        wrongChecksum[9] ^= 1;
        Assert.False(Blorb.Load(Form(Index(), Chunk("IFhd", wrongChecksum))).Matches(story));
        var wrongChecksumHigh = (byte[])identity.Clone();
        wrongChecksumHigh[8] ^= 1;
        Assert.False(Blorb.Load(Form(Index(), Chunk("IFhd", wrongChecksumHigh))).Matches(story));
    }

    private static byte[] Png(int width, int height)
    {
        var bytes = new List<byte> { 0x89, (byte)'P', (byte)'N', (byte)'G', 0x0D, 0x0A, 0x1A, 0x0A };
        bytes.AddRange([0, 0, 0, 13]);
        bytes.AddRange(Encoding.ASCII.GetBytes("IHDR"));
        bytes.AddRange([(byte)(width >> 24), (byte)(width >> 16), (byte)(width >> 8), (byte)width]);
        bytes.AddRange([(byte)(height >> 24), (byte)(height >> 16), (byte)(height >> 8), (byte)height]);
        return [.. bytes];
    }

    // A resource index naming pictures, each entry pointing at the
    // chunk that follows the index.
    private static byte[] Hung(params (string Usage, int Number, byte[] Chunk)[] pieces)
    {
        var index = new List<byte> { 0, 0, 0, (byte)pieces.Length };
        var offset = 12 + 8 + 4 + 12 * pieces.Length;
        var body = new List<byte>();

        foreach (var (usage, number, chunk) in pieces)
        {
            index.AddRange(Encoding.ASCII.GetBytes(usage));
            index.AddRange([0, 0, 0, (byte)number]);
            index.AddRange([(byte)(offset >> 24), (byte)(offset >> 16), (byte)(offset >> 8), (byte)offset]);
            offset += chunk.Length;
            body.AddRange(chunk);
        }

        return Form(Chunk("RIdx", [.. index]), [.. body]);
    }

    // The art a Blorb hangs: a PNG keeps its bytes, a Rect is a size
    // with no pixels, and a format this machine cannot draw is left
    // out of the census, because a picture it cannot draw is not
    // available in picture_data's sense (§15).
    [Fact]
    public void ThePictureResourcesBecomeAGallery()
    {
        var blorb = Blorb.Load(Hung(
            ("Pict", 1, Chunk("PNG ", Png(320, 200))),
            ("Pict", 2, Chunk("Rect", [0, 0, 0, 40, 0, 0, 0, 20])),
            ("Pict", 3, Chunk("JPEG", [1, 2, 3, 4]))));
        Assert.Equal(3, blorb.Pictures);
        Assert.Equal(2, blorb.Gallery.Count);
        Assert.Equal((200, 320), blorb.Gallery.Size(1));
        Assert.Equal((20, 40), blorb.Gallery.Size(2));
        Assert.Null(blorb.Gallery.Size(3));
    }

    [Fact]
    public void TheReleaseAndTheResolutionAreRead()
    {
        var reso = new List<byte>();
        reso.AddRange([0, 0, 1, 64, 0, 0, 0, 200]);
        reso.AddRange(new byte[16]);
        reso.AddRange([0, 0, 0, 1]);
        reso.AddRange([0, 0, 0, 1, 0, 0, 0, 2]);
        reso.AddRange([0, 0, 0, 1, 0, 0, 0, 4]);
        reso.AddRange([0, 0, 0, 0, 0, 0, 0, 0]);
        var blorb = Blorb.Load(Form(Index(), Chunk("RelN", [0, 9]), Chunk("Reso", [.. reso])));
        Assert.Equal(9, blorb.Gallery.Release);
        // The standard ratio is a half, clamped up by the quarter
        // minimum only when the room shrinks below it.
        Assert.Equal(new Ratio(1, 2), blorb.Gallery.Scale(1, 320, 200));
        Assert.Equal(new Ratio(1, 4), blorb.Gallery.Scale(1, 160, 100));
    }

    [Theory]
    [InlineData("release", "a two-byte release")]
    [InlineData("rect", "a Rect is a width and a height")]
    [InlineData("reso", "a 24-byte header and 28-byte entries")]
    [InlineData("window", "px and py must be non-zero")]
    [InlineData("standard", "standard ratio divides by zero")]
    [InlineData("half", "half-zero limiting ratio")]
    [InlineData("halfother", "half-zero limiting ratio")]
    [InlineData("offset", "where no chunk begins")]
    [InlineData("long", "the PNG  chunk claims")]
    public void MalformedArtIsRefusedByRule(string shape, string message)
    {
        var header = new List<byte> { 0, 0, 1, 64, 0, 0, 0, 200 };
        header.AddRange(new byte[16]);

        byte[] bytes;

        switch (shape)
        {
            case "release":
                bytes = Form(Index(), Chunk("RelN", [1, 2, 3]));
                break;
            case "rect":
                bytes = Hung(("Pict", 1, Chunk("Rect", [0, 0, 0, 40])));
                break;
            case "reso":
                bytes = Form(Index(), Chunk("Reso", [1, 2, 3]));
                break;
            case "window":
                bytes = Form(Index(), Chunk("Reso", [.. new byte[24]]));
                break;
            case "standard":
                {
                    var body = new List<byte>(header);
                    body.AddRange([0, 0, 0, 1]);
                    body.AddRange(new byte[24]);
                    bytes = Form(Index(), Chunk("Reso", [.. body]));
                    break;
                }

            case "half":
                {
                    var body = new List<byte>(header);
                    body.AddRange([0, 0, 0, 1]);
                    body.AddRange([0, 0, 0, 1, 0, 0, 0, 1]);
                    body.AddRange([0, 0, 0, 1, 0, 0, 0, 0]);
                    body.AddRange(new byte[8]);
                    bytes = Form(Index(), Chunk("Reso", [.. body]));
                    break;
                }

            case "halfother":
                {
                    var body = new List<byte>(header);
                    body.AddRange([0, 0, 0, 1]);
                    body.AddRange([0, 0, 0, 1, 0, 0, 0, 1]);
                    body.AddRange([0, 0, 0, 0, 0, 0, 0, 1]);
                    body.AddRange(new byte[8]);
                    bytes = Form(Index(), Chunk("Reso", [.. body]));
                    break;
                }

            case "offset":
                {
                    var index = new List<byte> { 0, 0, 0, 1 };
                    index.AddRange(Encoding.ASCII.GetBytes("Pict"));
                    index.AddRange([0, 0, 0, 1, 0xFF, 0xFF, 0xFF, 0xFF]);
                    bytes = Form(Chunk("RIdx", [.. index]));
                    break;
                }

            default:
                {
                    var index = new List<byte> { 0, 0, 0, 1 };
                    index.AddRange(Encoding.ASCII.GetBytes("Pict"));
                    index.AddRange([0, 0, 0, 1, 0, 0, 0, 36]);
                    bytes = Form(Chunk("RIdx", [.. index]), [.. Encoding.ASCII.GetBytes("PNG "), 0, 0, 0, 99, 1]);
                    break;
                }
        }

        var error = Assert.Throws<ZMachineException>(() => Blorb.Load(bytes));
        Assert.Contains(message, error.Message, StringComparison.Ordinal);
    }

    // A chunk that runs past the file, and an index that cannot hold
    // what it counts, are refused by name rather than read off the end.
    [Theory]
    [InlineData("long", "the AUTH chunk claims 9 bytes, but the file ends before them")]
    [InlineData("count", "too short to hold its own count")]
    [InlineData("entries", "the RIdx count of 2 needs 28 bytes, but the chunk holds 4")]
    public void ATruncatedBlorbIsRefusedByName(string shape, string message)
    {
        byte[] bytes = shape switch
        {
            "long" => Form(Index(), [.. Encoding.ASCII.GetBytes("AUTH"), 0, 0, 0, 9, 1]),
            "count" => Form(Chunk("RIdx", [0, 0])),
            _ => Form(Chunk("RIdx", [0, 0, 0, 2])),
        };
        var error = Assert.Throws<ZMachineException>(() => Blorb.Load(bytes));
        Assert.Contains(message, error.Message, StringComparison.Ordinal);
    }

    // An Exec entry numbered 0 names the packaged story by the offset
    // of its chunk; only ZCOD belongs to this machine.
    [Fact]
    public void ThePackagedStoryIsTheZcodChunkAnExecEntryPointsAt()
    {
        var story = new byte[] { 3, 0, 1, 2, 3 };
        var index = new List<byte> { 0, 0, 0, 1 };
        index.AddRange(Encoding.ASCII.GetBytes("Exec"));
        index.AddRange([0, 0, 0, 0]);
        // The chunk follows the index: FORM header 12, RIdx header 8, index 16.
        index.AddRange([0, 0, 0, 36]);
        var packaged = Blorb.Load(Form(Chunk("RIdx", [.. index]), Chunk("ZCOD", story)));
        Assert.Equal(story, packaged.Story);
        Assert.True(packaged.HasStory);

        var glulx = Blorb.Load(Form(Chunk("RIdx", [.. index]), Chunk("GLUL", story)));
        Assert.Null(glulx.Story);
        Assert.True(glulx.HasStory);

        // An Exec entry pointing past the file, or at a place no file
        // could reach, packages nothing.
        var beyond = new List<byte>(index);
        beyond[12] = 0x7F;
        beyond[13] = 0xFF;
        Assert.Null(Blorb.Load(Form(Chunk("RIdx", [.. beyond]), Chunk("ZCOD", story))).Story);

        var astray = new List<byte>(index);
        astray[12] = 0xFF;
        astray[13] = 0xFF;
        astray[14] = 0xFF;
        astray[15] = 0xFF;
        Assert.Null(Blorb.Load(Form(Chunk("RIdx", [.. astray]), Chunk("ZCOD", story))).Story);

        var numbered = new List<byte>(index);
        numbered[11] = 1;
        Assert.Null(Blorb.Load(Form(Chunk("RIdx", [.. numbered]), Chunk("ZCOD", story))).Story);

        var dangling = new List<byte>(index);
        dangling[15] = 200;
        Assert.Null(Blorb.Load(Form(Chunk("RIdx", [.. dangling]))).Story);
        Assert.Null(Blorb.Load(Form(Index())).Story);
    }

    [Fact]
    public void OtherChunksArePassedOverWithTheirPadding()
    {
        var blorb = Blorb.Load(Form(Chunk("Fspc", [0, 0, 0, 1, 9]), Index("Pict")));
        Assert.Equal(1, blorb.Pictures);
    }
}
