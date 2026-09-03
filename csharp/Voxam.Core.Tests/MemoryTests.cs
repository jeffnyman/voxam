using Voxam.Core.Tests.Support;

namespace Voxam.Core.Tests;

public class MemoryTests
{
    private static byte[] Story()
    {
        var builder = new StoryBuilder();
        builder.Quit();
        return builder.Build();
    }

    [Fact]
    public void AStoryShorterThanAHeaderIsRefused()
    {
        var error = Assert.Throws<ZMachineException>(() => new Memory(new byte[10]));
        Assert.Contains("header alone requires 64", error.Message, StringComparison.Ordinal);
    }

    [Theory]
    [InlineData(0)]
    [InlineData(9)]
    public void AVersionOutsideOneToEightIsRefused(int version)
    {
        var story = Story();
        story[0] = (byte)version;
        var error = Assert.Throws<ZMachineException>(() => new Memory(story));
        Assert.Contains($"declares version {version}", error.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void AnOversizedStoryIsRefused()
    {
        var story = new byte[128 * 1024 + 1];
        Story().CopyTo(story, 0);
        var error = Assert.Throws<ZMachineException>(() => new Memory(story));
        Assert.Contains("allows at most 131072", error.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void AStaticBaseInsideTheHeaderIsRefused()
    {
        var story = Story();
        StoryBuilder.Word(story, Header.StaticBase, 0x20);
        var error = Assert.Throws<ZMachineException>(() => new Memory(story));
        Assert.Contains("smaller than the 64-byte header", error.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void AStaticBaseBeyondTheFileIsRefused()
    {
        var story = Story();
        StoryBuilder.Word(story, Header.StaticBase, 0xFFFF);
        var error = Assert.Throws<ZMachineException>(() => new Memory(story));
        Assert.Contains("beyond the end", error.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void AHighBaseInsideDynamicMemoryIsRefused()
    {
        var story = Story();
        StoryBuilder.Word(story, Header.HighBase, 0x100);
        var error = Assert.Throws<ZMachineException>(() => new Memory(story));
        Assert.Contains("inside dynamic memory", error.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void ReadsAndWritesKeepTheirBounds()
    {
        var memory = new Memory(Story());
        memory.WriteWord(0x100, 0xABCD);
        Assert.Equal(0xABCD, memory.ReadWord(0x100));
        Assert.Equal(0xAB, memory.ReadByte(0x100));
        memory.WriteByte(0x101, 0x12);
        Assert.Equal(0xAB12, memory.FetchWord(0x100));
        Assert.Equal(0x12, memory.FetchByte(0x101));

        Assert.Contains("only dynamic memory", Assert.Throws<ZMachineException>(() => memory.WriteByte(memory.StaticBase, 0)).Message, StringComparison.Ordinal);
        Assert.Contains("only dynamic memory", Assert.Throws<ZMachineException>(() => memory.WriteWord(memory.StaticBase - 1, 0)).Message, StringComparison.Ordinal);
        Assert.Contains("does not fit in a byte", Assert.Throws<ZMachineException>(() => memory.WriteByte(0x100, 256)).Message, StringComparison.Ordinal);
        Assert.Contains("does not fit in a byte", Assert.Throws<ZMachineException>(() => memory.WriteByte(0x100, -1)).Message, StringComparison.Ordinal);
        Assert.Contains("does not fit in a word", Assert.Throws<ZMachineException>(() => memory.WriteWord(0x100, -1)).Message, StringComparison.Ordinal);
        Assert.Contains("only dynamic memory", Assert.Throws<ZMachineException>(() => memory.WriteByte(-1, 0)).Message, StringComparison.Ordinal);
        Assert.Contains("cannot fetch", Assert.Throws<ZMachineException>(() => memory.FetchByte(-1)).Message, StringComparison.Ordinal);
        Assert.Contains("does not fit in a word", Assert.Throws<ZMachineException>(() => memory.WriteWord(0x100, 0x10000)).Message, StringComparison.Ordinal);
        Assert.Contains("cannot read", Assert.Throws<ZMachineException>(() => memory.ReadByte(memory.Length)).Message, StringComparison.Ordinal);
        Assert.Contains("cannot read", Assert.Throws<ZMachineException>(() => memory.ReadWord(-1)).Message, StringComparison.Ordinal);
        Assert.Contains("cannot fetch", Assert.Throws<ZMachineException>(() => memory.FetchByte(memory.Length)).Message, StringComparison.Ordinal);
        Assert.Contains("cannot fetch", Assert.Throws<ZMachineException>(() => memory.FetchWord(memory.Length - 1)).Message, StringComparison.Ordinal);
    }

    [Fact]
    public void ADynamicSnapshotRestoresWholeAndRefusesAnotherShape()
    {
        var memory = new Memory(Story());
        var before = memory.DynamicSnapshot();
        Assert.Equal(memory.StaticBase, before.Length);
        memory.WriteWord(0x100, 0x1234);
        memory.RestoreDynamic(before);
        Assert.Equal(0, memory.ReadWord(0x100));
        var error = Assert.Throws<ZMachineException>(() => memory.RestoreDynamic(new byte[3]));
        Assert.Contains("captured from a different game", error.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void ThePristineStoryIsKeptApart()
    {
        var story = Story();
        var memory = new Memory(story);
        memory.WriteByte(0x100, 7);
        Assert.Equal(0, memory.Pristine[0x100]);
        Assert.Same(story, memory.Pristine);
        Assert.Equal(3, memory.Version);
    }
}
