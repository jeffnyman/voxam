using System.Text;
using Voxam.Core.Tests.Support;

namespace Voxam.Core.Tests;

public class QuetzalTests
{
    private static byte[] Story()
    {
        var b = new StoryBuilder(5);
        b.Alloc(600);
        b.Quit();
        return b.Build();
    }

    private static SavedState State(byte[] story)
    {
        var staticBase = (story[Header.StaticBase] << 8) | story[Header.StaticBase + 1];
        var dynamic = story[..staticBase];
        dynamic[0x100] = 7;
        dynamic[0x101] = 9;
        dynamic[0x3FF] ^= 1;
        return new SavedState(
            dynamic,
            0x1234,
            [
                new SavedFrame(0, -1, [], 0, [1, 2]),
                new SavedFrame(0x1000, 5, [10, 20, 30], 2, []),
                new SavedFrame(0x2000, -1, [], 0, [0xFFFF]),
            ]);
    }

    private static byte[] Chunk(string id, byte[] payload)
    {
        var framed = new List<byte>(Encoding.ASCII.GetBytes(id));
        framed.AddRange([(byte)(payload.Length >> 24), (byte)(payload.Length >> 16), (byte)(payload.Length >> 8), (byte)payload.Length]);
        framed.AddRange(payload);

        if (payload.Length % 2 != 0)
        {
            framed.Add(0);
        }

        return [.. framed];
    }

    private static byte[] Form(string type, params byte[][] chunks)
    {
        var body = new List<byte>(Encoding.ASCII.GetBytes(type));

        foreach (var chunk in chunks)
        {
            body.AddRange(chunk);
        }

        return Chunk("FORM", [.. body]);
    }

    private static byte[] Ifhd(byte[] story, int pc = 0x1234) => [.. Quetzal.Identity(story), (byte)(pc >> 16), (byte)(pc >> 8), (byte)pc];

    private static readonly byte[] Dummy = [0, 0, 0, 0, 0, 0, 0, 0];

    [Fact]
    public void AStateRoundTripsThroughACompressedSave()
    {
        var story = Story();
        var state = State(story);
        var bytes = Quetzal.Write(state, story);
        Assert.Equal("FORM", Encoding.ASCII.GetString(bytes, 0, 4));
        Assert.Equal("IFZS", Encoding.ASCII.GetString(bytes, 8, 4));
        Assert.Equal("IFhd", Encoding.ASCII.GetString(bytes, 12, 4));
        var read = Quetzal.Read(bytes, story);
        Assert.Equal(state.Dynamic, read.Dynamic);
        Assert.Equal(0x1234, read.Pc);
        Assert.Equal(3, read.Frames.Count);
        Assert.Equal([1, 2], read.Frames[0].Stack);
        Assert.Equal(-1, read.Frames[0].StoreVariable);
        Assert.Equal(0x1000, read.Frames[1].ReturnAddress);
        Assert.Equal(5, read.Frames[1].StoreVariable);
        Assert.Equal([10, 20, 30], read.Frames[1].Locals);
        Assert.Equal(2, read.Frames[1].ArgumentCount);
        Assert.Equal(-1, read.Frames[2].StoreVariable);
        Assert.Equal([0xFFFF], read.Frames[2].Stack);
    }

    [Fact]
    public void LongZeroRunsAndUnchangedTailsCompressAway()
    {
        var story = Story();
        var staticBase = (story[Header.StaticBase] << 8) | story[Header.StaticBase + 1];
        var dynamic = story[..staticBase];
        dynamic[0x40] ^= 1;
        dynamic[0x40 + 700] ^= 1;
        var bytes = Quetzal.Write(new SavedState(dynamic, 0, [new SavedFrame(0, -1, [], 0, [])]), story);
        // The 64 unchanged header bytes are one run; between the two
        // changes lie 699 zeros, a full run of 256, another, then 187;
        // the unchanged tail is dropped whole.
        var at = Encoding.Latin1.GetString(bytes).IndexOf("CMem", StringComparison.Ordinal);
        var length = (bytes[at + 4] << 24) | (bytes[at + 5] << 16) | (bytes[at + 6] << 8) | bytes[at + 7];
        Assert.Equal([0, 63, 1, 0, 255, 0, 255, 0, 186, 1], bytes[(at + 8)..(at + 8 + length)]);
        Assert.Equal(dynamic, Quetzal.Read(bytes, story).Dynamic);
    }

    [Fact]
    public void AnUnchangedMemoryCompressesToNothing()
    {
        var story = Story();
        var staticBase = (story[Header.StaticBase] << 8) | story[Header.StaticBase + 1];
        var dynamic = story[..staticBase];
        var bytes = Quetzal.Write(new SavedState(dynamic, 0, [new SavedFrame(0, -1, [], 0, [])]), story);
        var at = Encoding.Latin1.GetString(bytes).IndexOf("CMem", StringComparison.Ordinal);
        Assert.Equal(0, (bytes[at + 4] << 24) | (bytes[at + 5] << 16) | (bytes[at + 6] << 8) | bytes[at + 7]);
        Assert.Equal(dynamic, Quetzal.Read(bytes, story).Dynamic);
    }

    [Fact]
    public void AnUncompressedDumpIsReadToo()
    {
        var story = Story();
        var state = State(story);
        var bytes = Form("IFZS", Chunk("IFhd", Ifhd(story)), Chunk("UMem", state.Dynamic), Chunk("Stks", Dummy));
        Assert.Equal(state.Dynamic, Quetzal.Read(bytes, story).Dynamic);
        var wrong = Form("IFZS", Chunk("IFhd", Ifhd(story)), Chunk("UMem", [1, 2, 3]), Chunk("Stks", Dummy));
        Assert.Contains("must be exactly dynamic memory", Assert.Throws<ZMachineException>(() => Quetzal.Read(wrong, story)).Message, StringComparison.Ordinal);
    }

    // The declared length scales by version (§11.1.6), so the sum
    // walks the same bytes the builder summed for each.
    [Theory]
    [InlineData(3)]
    [InlineData(5)]
    [InlineData(8)]
    public void AStoryWithoutAChecksumIsNamedByAComputedOne(int version)
    {
        var b = new StoryBuilder(version);
        b.Alloc(600);
        b.Quit();
        var story = b.Build();
        var identity = Quetzal.Identity(story);
        StoryBuilder.Word(story, Header.Checksum, 0);
        Assert.Equal(identity, Quetzal.Identity(story));
    }

    [Theory]
    [InlineData("", "no FORM chunk")]
    [InlineData("RIFF", "no FORM chunk")]
    [InlineData("short", "claims")]
    [InlineData("type", "not the IFZS")]
    [InlineData("noifhd", "IFhd chunk is missing")]
    [InlineData("nostks", "Stks chunk is missing")]
    [InlineData("nomem", "CMem or UMem chunk is missing")]
    [InlineData("bothmem", "one or the other")]
    [InlineData("doubled", "appears twice")]
    [InlineData("late", "arrives before IFhd")]
    [InlineData("cut", "cut short mid-header")]
    [InlineData("overrun", "FORM ends before them")]
    [InlineData("shortifhd", "fewer than the 13")]
    [InlineData("other", "names a different game")]
    [InlineData("cmemtail", "no run length")]
    [InlineData("cmemlong", "decodes to")]
    [InlineData("framecut", "cut short mid-header")]
    [InlineData("framewords", "cut short mid-words")]
    [InlineData("reserved", "uses reserved bits")]
    [InlineData("gaps", "has gaps")]
    [InlineData("notdummy", "must be the dummy")]
    [InlineData("notdummyflags", "must be the dummy")]
    [InlineData("notdummystore", "must be the dummy")]
    [InlineData("notdummymask", "must be the dummy")]
    [InlineData("nostacks", "Stks chunk is empty")]
    public void MalformedSavesAreRefusedByRule(string shape, string message)
    {
        var story = Story();
        var ifhd = Chunk("IFhd", Ifhd(story));
        var stks = Chunk("Stks", Dummy);
        var cmem = Chunk("CMem", []);
        byte[] bytes = shape switch
        {
            "" => [],
            "RIFF" => [.. Encoding.ASCII.GetBytes("RIFF"), 0, 0, 0, 4, .. Encoding.ASCII.GetBytes("IFZS")],
            "short" => [.. Encoding.ASCII.GetBytes("FORM"), 0, 0, 0, 99, .. Encoding.ASCII.GetBytes("IFZS")],
            "type" => Form("IFRS", ifhd),
            "noifhd" => Form("IFZS", Chunk("Blah", [1])),
            "nostks" => Form("IFZS", ifhd, cmem),
            "nomem" => Form("IFZS", ifhd, stks),
            "bothmem" => Form("IFZS", ifhd, cmem, Chunk("UMem", []), stks),
            "doubled" => Form("IFZS", ifhd, ifhd, stks),
            "late" => Form("IFZS", stks, ifhd),
            "cut" => Form("IFZS", ifhd, [0, 0, 0]),
            "overrun" => Form("IFZS", ifhd, [.. Encoding.ASCII.GetBytes("Stks"), 0, 0, 0, 9, 1]),
            "shortifhd" => Form("IFZS", Chunk("IFhd", [1, 2, 3]), cmem, stks),
            "other" => Form("IFZS", Chunk("IFhd", [.. Ifhd(story)[..9], 0x77, 0, 0, 0]), cmem, stks),
            "cmemtail" => Form("IFZS", ifhd, Chunk("CMem", [1, 0]), stks),
            "cmemlong" => Form("IFZS", ifhd, Chunk("CMem", [0, 255, 0, 255, 0, 255, 0, 255, 0, 255, 0, 255, 0, 255, 0, 255, 0, 255, 0, 255, 0, 255, 0, 255, 0, 255, 0, 255, 0, 255, 0, 255, 0, 255]), stks),
            "framecut" => Form("IFZS", ifhd, cmem, Chunk("Stks", [.. Dummy, 0, 0, 0])),
            "framewords" => Form("IFZS", ifhd, cmem, Chunk("Stks", [.. Dummy, 0, 0x10, 0, 2, 0, 0, 0, 5, 1])),
            "reserved" => Form("IFZS", ifhd, cmem, Chunk("Stks", [.. Dummy, 0, 0x10, 0, 0x20, 0, 0, 0, 0])),
            "gaps" => Form("IFZS", ifhd, cmem, Chunk("Stks", [.. Dummy, 0, 0x10, 0, 0, 0, 5, 0, 0])),
            "notdummy" => Form("IFZS", ifhd, cmem, Chunk("Stks", [0, 0, 1, 0, 0, 0, 0, 0])),
            "notdummyflags" => Form("IFZS", ifhd, cmem, Chunk("Stks", [0, 0, 0, 1, 0, 0, 0, 0, 0, 0])),
            "notdummystore" => Form("IFZS", ifhd, cmem, Chunk("Stks", [0, 0, 0, 0, 1, 0, 0, 0])),
            "notdummymask" => Form("IFZS", ifhd, cmem, Chunk("Stks", [0, 0, 0, 0, 0, 1, 0, 0])),
            _ => Form("IFZS", ifhd, cmem, Chunk("Stks", [])),
        };
        var error = Assert.Throws<ZMachineException>(() => Quetzal.Read(bytes, story));
        Assert.Contains(message, error.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void UnknownChunksAndOddPaddingArePassedOver()
    {
        var story = Story();
        var bytes = Form("IFZS", Chunk("IFhd", Ifhd(story)), Chunk("AUTH", [1, 2, 3]), Chunk("CMem", [1]), Chunk("Stks", [.. Dummy, 0, 0, 0, 0x11, 0, 0x7F, 0, 1, 0, 9, 0, 3]));
        var state = Quetzal.Read(bytes, story);
        Assert.Equal(1, state.Dynamic[0] ^ story[0]);
        Assert.Equal(2, state.Frames.Count);
        Assert.Equal(7, state.Frames[1].ArgumentCount);
        Assert.Equal(-1, state.Frames[1].StoreVariable);
        Assert.Equal([9], state.Frames[1].Locals);
        Assert.Equal([3], state.Frames[1].Stack);
    }

    [Fact]
    public void WhatTheFormatCannotCarryIsRefusedOnWriting()
    {
        var story = Story();
        var frames = new[] { new SavedFrame(0, -1, [], 0, []) };
        Assert.Contains("belongs to a different game", Assert.Throws<ZMachineException>(() => Quetzal.Write(new SavedState([1, 2], 0, frames), story)).Message, StringComparison.Ordinal);
        var dynamic = State(story).Dynamic;
        Assert.Contains("does not fit in the three bytes", Assert.Throws<ZMachineException>(() => Quetzal.Write(new SavedState(dynamic, 0x1000000, frames), story)).Message, StringComparison.Ordinal);
        var many = new SavedState(dynamic, 0, [frames[0], new SavedFrame(0, 0, [], 8, [])]);
        Assert.Contains("seven argument bits", Assert.Throws<ZMachineException>(() => Quetzal.Write(many, story)).Message, StringComparison.Ordinal);
    }
}
