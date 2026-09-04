using Voxam.Core.Glulx;
using GlulxException = Voxam.Core.GlulxException;

namespace Voxam.Tests.Glulx;

/// <summary>
/// The built-in search opcodes (Glulx: Searching). The table here
/// holds four eight-byte structures at 320, each opening with a
/// two-byte key: 10, 20, 30 and 40, in the ascending order a binary
/// search needs.
/// </summary>
public sealed class SearchTests
{
    private const uint Table = 320;
    private const uint Stride = 8;
    private const uint Count = 4;

    // ReturnIndex asks for the position; without it the answer is the
    // structure's own address.
    [Theory]
    [InlineData(10u, 0u, 0u, 320u)]
    [InlineData(30u, 0u, 2u, 336u)]
    [InlineData(40u, 0u, 3u, 344u)]
    [InlineData(25u, 0u, Search.NotFoundIndex, Search.NotFoundAddress)]
    public void ALinearSearchWalksTheTableInOrder(uint key, uint options, uint index, uint address)
    {
        var memory = Mapped();

        Assert.Equal(address, Search.Linear(memory, key, 2, Table, Stride, Count, 0, options));
        Assert.Equal(index, Search.Linear(memory, key, 2, Table, Stride, Count, 0, options | 4));
    }

    // A count of 0xFFFFFFFF means no upper limit, so something has to
    // stop the walk: an all-zero key does, and the test comes after
    // the match so a search for that key still finds it.
    [Fact]
    public void AnUnlimitedSearchStopsAtAnAllZeroKey()
    {
        var memory = Mapped();

        Assert.Equal(Search.NotFoundAddress, Search.Linear(memory, 99, 2, Table, Stride, 0xFFFFFFFF, 0, 2));
        Assert.Equal(352u, Search.Linear(memory, 0, 2, Table, Stride, 0xFFFFFFFF, 0, 2));
    }

    [Theory]
    [InlineData(10u, 0u, 320u)]
    [InlineData(20u, 1u, 328u)]
    [InlineData(30u, 2u, 336u)]
    [InlineData(40u, 3u, 344u)]
    public void ABinarySearchFindsEveryKeyInAnOrderedTable(uint key, uint index, uint address)
    {
        var memory = Mapped();

        Assert.Equal(address, Search.Binary(memory, key, 2, Table, Stride, Count, 0, 0));
        Assert.Equal(index, Search.Binary(memory, key, 2, Table, Stride, Count, 0, 4));
    }

    // A key below every entry, above every entry, and between two of
    // them: the three ways a binary search can run out of room.
    [Theory]
    [InlineData(5u)]
    [InlineData(25u)]
    [InlineData(99u)]
    public void ABinarySearchThatFindsNothingSaysSo(uint key)
    {
        var memory = Mapped();

        Assert.Equal(Search.NotFoundAddress, Search.Binary(memory, key, 2, Table, Stride, Count, 0, 0));
        Assert.Equal(Search.NotFoundIndex, Search.Binary(memory, key, 2, Table, Stride, Count, 0, 4));
    }

    // A linked list follows its own next field, and a zero there ends
    // it; a list has no indexes, so the answer is an address or zero.
    [Fact]
    public void ALinkedSearchFollowsItsOwnLinks()
    {
        var memory = Mapped();

        Assert.Equal(336u, Search.Linked(memory, 30, 2, Table, 0, 4, 0));
        Assert.Equal(Search.NotFoundAddress, Search.Linked(memory, 99, 2, Table, 0, 4, 0));
        // With ZeroKeyTerminates the walk stops at the fifth
        // structure, whose key is zero, rather than following on.
        Assert.Equal(Search.NotFoundAddress, Search.Linked(memory, 60, 2, Table, 0, 4, 2));
        Assert.Equal(352u, Search.Linked(memory, 0, 2, Table, 0, 4, 2));
    }

    // With KeyIndirect the operand is the key's address, and any size
    // is legal; without it the key sits in the operand's own low
    // bytes, big-endian.
    [Fact]
    public void AKeyArrivesEitherDirectlyOrByAddress()
    {
        var memory = Mapped();

        Assert.Equal(336u, Search.Linear(memory, 336, 2, Table, Stride, Count, 0, 1));
        Assert.Equal(320u, Search.Linear(memory, 0x000A, 2, Table, Stride, Count, 0, 0));
        // A one-byte key matches the structure's first byte, which
        // every key here shares.
        Assert.Equal(320u, Search.Linear(memory, 0, 1, Table, Stride, Count, 0, 0));
        // And a four-byte key takes in the two bytes after it.
        Assert.Equal(0x000A0000u, memory.ReadWord((int)Table));
        Assert.Equal(320u, Search.Linear(memory, 0x000A0000, 4, Table, Stride, Count, 0, 0));
    }

    [Fact]
    public void ADirectKeyOfASizeNoWordCanHoldIsRefused()
    {
        var memory = Mapped();

        Assert.Equal(
            "a direct search key must hold one, two, or four bytes, not 3 (Glulx: Searching)",
            Assert.Throws<GlulxException>(() => Search.Linear(memory, 1, 3, Table, Stride, Count, 0, 0)).Message);
    }

    // And the opcodes ask the same three searches.
    [Fact]
    public void TheOpcodesAskTheSameSearches()
    {
        var program = new GlulxProgram();
        program.Op(Op.Linearsearch, Modes.Constant(30), Modes.Constant(2), Modes.Constant(Table),
            Modes.Constant(Stride), Modes.Constant(Count), Modes.Constant(0), Modes.Constant(0), Modes.Memory(0x180));
        program.Op(Op.Binarysearch, Modes.Constant(30), Modes.Constant(2), Modes.Constant(Table),
            Modes.Constant(Stride), Modes.Constant(Count), Modes.Constant(0), Modes.Constant(4), Modes.Memory(0x184));
        program.Op(Op.Linkedsearch, Modes.Constant(30), Modes.Constant(2), Modes.Constant(Table),
            Modes.Constant(0), Modes.Constant(4), Modes.Constant(0), Modes.Memory(0x188));
        program.Op(Op.Quit);

        for (var index = 0u; index < 5; index++)
        {
            var at = (int)(Table + (index * Stride));
            var key = index < Count ? (index + 1) * 10 : 0;
            var next = index < Count ? Table + ((index + 1) * Stride) : 0;
            program.Lay(at, [(byte)(key >> 8), (byte)key, 0, 0, .. Word(next)]);
        }

        var machine = program.Booted();
        machine.Run();

        Assert.Equal(336u, machine.Memory.ReadWord(0x180));
        Assert.Equal(2u, machine.Memory.ReadWord(0x184));
        Assert.Equal(336u, machine.Memory.ReadWord(0x188));
    }

    // Four structures with ascending keys, each linking to the next,
    // and a fifth with an all-zero key to stop an unlimited walk.
    private static Memory Mapped()
    {
        var builder = new GlulxBuilder();

        for (var index = 0u; index < 5; index++)
        {
            var at = (int)(Table + (index * Stride));
            var key = index < Count ? (index + 1) * 10 : 0;
            var next = index < Count ? Table + ((index + 1) * Stride) : 0;
            builder.Lay(at, [(byte)(key >> 8), (byte)key, 0, 0, .. Word(next)]);
        }

        return new Memory(new Story(builder.Build()));
    }

    private static byte[] Word(uint value) => [(byte)(value >> 24), (byte)(value >> 16), (byte)(value >> 8), (byte)value];
}
