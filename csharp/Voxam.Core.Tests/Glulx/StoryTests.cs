using Voxam.Core.Glulx;
using GlulxException = Voxam.Core.GlulxException;

namespace Voxam.Tests.Glulx;

/// <summary>
/// Loading a Glulx story file: the header is nine words in ROM, so
/// the moment of loading is the moment to hold the file to every
/// promise they make (Glulx: The Header).
/// </summary>
public sealed class StoryTests
{
    // A file with no room for a header cannot have made any of the
    // header's promises.
    [Fact]
    public void AFileTooShortForAHeaderIsRefused()
    {
        var error = Assert.Throws<GlulxException>(() => new Story("Glul"u8.ToArray()));
        Assert.Equal("a Glulx story opens with a 36-byte header, but only 4 bytes are present (Glulx: The Header)", error.Message);
    }

    [Fact]
    public void AFileWithoutTheMagicWordIsRefused()
    {
        var error = Assert.Throws<GlulxException>(() => new Story(new byte[36]));
        Assert.Equal("the file does not open with the magic number 'Glul' (Glulx: The Header)", error.Message);
    }

    // An interpreter written to specification 3.1.3 accepts 2.0.0
    // through 3.1.* and nothing on either side of that window.
    [Theory]
    [InlineData(0x00010000u, "1.0.0")]
    [InlineData(0x00030200u, "3.2.0")]
    public void AVersionOutsideTheWindowIsRefused(uint version, string dotted)
    {
        var error = Assert.Throws<GlulxException>(() => new Story(new GlulxBuilder { Version = version }.Build()));
        Assert.Equal($"the story declares Glulx version {dotted}, but an interpreter written to 3.1.3 accepts 2.0.0 through 3.1.* (Glulx: The Header)", error.Message);
    }

    // Every boundary the header names sits on a 256-byte seat, the
    // stack size included.
    [Theory]
    [InlineData("RAMSTART")]
    [InlineData("EXTSTART")]
    [InlineData("ENDMEM")]
    [InlineData("the stack size")]
    public void AMisalignedBoundaryIsRefused(string name)
    {
        var error = Assert.Throws<GlulxException>(() => new Story(Declaring(name, 260).Build()));
        Assert.Equal($"{name} is 260, which is not a multiple of 256 (Glulx: The Header)", error.Message);
    }

    // The spec sets no ceiling, addresses being 32 bits; a machine
    // that cannot lay out that much memory says so rather than
    // failing to allocate.
    [Fact]
    public void AMapLargerThanTheMachineCanHoldIsRefused()
    {
        var error = Assert.Throws<GlulxException>(() => new Story(Declaring("ENDMEM", 0x80000000).Build()));
        Assert.Equal("ENDMEM is 2147483648, larger than this machine can map (Glulx: The Header)", error.Message);
    }

    // ROM holds the header, so RAMSTART is at least 256, and the
    // three boundaries climb in order.
    [Theory]
    [InlineData(0u, 512u, 1024u)]
    [InlineData(768u, 512u, 1024u)]
    [InlineData(256u, 2048u, 1024u)]
    public void AMemoryMapOutOfOrderIsRefused(uint ramStart, uint extStart, uint endMem)
    {
        var builder = new GlulxBuilder { RamStart = ramStart, ExtStart = extStart, EndMem = endMem };
        var error = Assert.Throws<GlulxException>(() => new Story(builder.Build()));
        Assert.Equal(
            $"the memory map is out of order: ROM holds the header so RAMSTART is at least 256, and RAMSTART ({ramStart}) precedes EXTSTART ({extStart}) precedes ENDMEM ({endMem}) (Glulx: The Header)",
            error.Message);
    }

    // EXTSTART is the length of the stored initial memory, which is
    // to say the length of the file itself.
    [Fact]
    public void AFileThatIsNotTheLengthItDeclaresIsRefused()
    {
        var error = Assert.Throws<GlulxException>(() => new Story(new GlulxBuilder { Length = 768 }.Build()));
        Assert.Equal("the file is 768 bytes, but its header declares EXTSTART 512, the length of the stored initial memory (Glulx: The Header)", error.Message);
    }

    [Fact]
    public void AHeaderReadsBackTheNumbersItDeclares()
    {
        var story = new Story(new GlulxBuilder
        {
            Version = 0x00020000,
            RamStart = 512,
            ExtStart = 1024,
            EndMem = 2048,
            StackSize = 4096,
            StartFunction = 600,
            DecodingTable = 700,
        }.Build());

        Assert.Equal("2.0.0", story.Version);
        Assert.Equal(512, story.RamStart);
        Assert.Equal(1024, story.ExtStart);
        Assert.Equal(2048, story.EndMem);
        Assert.Equal(4096, story.StackSize);
        Assert.Equal(600, story.StartFunction);
        Assert.Equal(700, story.DecodingTable);
        Assert.Equal(1024, story.Data.Length);
    }

    // The checksum sums the whole initial image as words, counting
    // its own seat as zero, which is why a story can be summed after
    // the checksum is written into it.
    [Fact]
    public void AStoryVerifiesAgainstTheChecksumItCarries()
    {
        var story = new Story(new GlulxBuilder().Lay(400, 1, 2, 3, 4).Build());

        Assert.True(story.Verify());
        Assert.Equal(story.ComputedChecksum, story.StoredChecksum);
    }

    // A byte changed anywhere above the header moves the sum without
    // moving the word the compiler stored.
    [Fact]
    public void AChangedByteBreaksTheChecksum()
    {
        var image = new GlulxBuilder().Build();
        image[40] ^= 1;

        Assert.False(new Story(image).Verify());
    }

    [Fact]
    public void OnlyTheMagicWordSaysAFileIsGlulx()
    {
        Assert.True(Story.IsGlulx(new GlulxBuilder().Build()));
        Assert.False(Story.IsGlulx(new byte[36]));
        Assert.False(Story.IsGlulx("Glu"u8.ToArray()));
    }

    // A builder with one boundary moved off its seat, by the name the
    // refusal will use for it.
    private static GlulxBuilder Declaring(string name, uint value)
    {
        var builder = new GlulxBuilder();

        switch (name)
        {
            case "RAMSTART":
                builder.RamStart = value;
                break;
            case "EXTSTART":
                builder.ExtStart = value;
                break;
            case "ENDMEM":
                builder.EndMem = value;
                break;
            default:
                builder.StackSize = value;
                break;
        }

        return builder;
    }
}
