using Voxam.Core.Glulx;
using GlulxException = Voxam.Core.GlulxException;

namespace Voxam.Tests.Glulx;

/// <summary>
/// Operand decoding: an opcode number whose own top bits say how
/// long it is, then addressing modes packed two nibbles per byte,
/// then the operand data (Glulx: Instruction Format). The map here
/// has ROM to 256, the stored image ending at 512, and the map
/// ending at 1024, with instructions laid in ROM at 64.
/// </summary>
public sealed class OperandTests
{
    private const int Code = 64;
    private const int RamStart = 256;
    private const int EndMem = 1024;

    // The opcode number's length rides in its own top bits, so 01,
    // 8001 and C0000001 all name opcode 1.
    [Theory]
    [InlineData(new byte[] { 0x10 }, 0x10, 1)]
    [InlineData(new byte[] { 0x81, 0x30 }, 0x130, 2)]
    [InlineData(new byte[] { 0xC0, 0x00, 0x01, 0x60 }, 0x160, 4)]
    public void AnOpcodeNumberSaysItsOwnLength(byte[] code, int number, int length)
    {
        var memory = Mapped(code);
        var (decoded, after) = Operands.DecodeOpcode(memory, Code);

        Assert.Equal(number, decoded);
        Assert.Equal(Code + length, after);
    }

    // An opcode number's name comes from the number itself, and a
    // number the specification does not define says its hex instead.
    [Fact]
    public void AnOpcodeSaysItsOwnName()
    {
        Assert.Equal("add", Opcode.Name(0x10));
        Assert.Equal("sshiftr", Opcode.Name(0x1D));
        Assert.Equal("callfiii", Opcode.Name(0x163));
        Assert.Equal("jdisinf", Opcode.Name(0x239));
        Assert.Equal("$99", Opcode.Name(0x99));
    }

    // The four constant modes: nothing at all, then a byte, a short
    // and a word, the narrow two sign-extended into their unsigned
    // equivalent.
    [Fact]
    public void TheConstantModesCarryTheirOwnValues()
    {
        // Modes 0 and 1 in the first byte, 2 and 3 in the second.
        var memory = Mapped([0x10, 0x32, 0xFF, 0xFF, 0x00, 0x12, 0x34, 0x56, 0x78]);
        var (items, after) = Operands.Shape(memory, Code, new OperandList("LLLL"));

        Assert.Equal(
            [
                new Shaped(Fetch.Fixed, 0, default),
                new Shaped(Fetch.Fixed, 0xFFFFFFFF, default),
                new Shaped(Fetch.Fixed, 0xFFFFFF00, default),
                new Shaped(Fetch.Fixed, 0x12345678, default),
            ],
            items);
        Assert.Equal(Code + 9, after);
    }

    // The indirect load modes name where to fetch from rather than
    // fetching: memory, a local, the stack, and a RAM offset that
    // RAMSTART is added to here, since RAMSTART never moves.
    [Fact]
    public void TheIndirectLoadModesNameWhereToFetchFrom()
    {
        // Modes 5 and 9 in the first byte, 13 and 8 in the second.
        var memory = Mapped([0x95, 0x8D, 0x40, 0x00, 0x10]);
        var (items, after) = Operands.Shape(memory, Code, new OperandList("LLLL"));

        Assert.Equal(
            [
                new Shaped(Fetch.FromMemory, 0x40, default),
                new Shaped(Fetch.FromLocal, 0, default),
                new Shaped(Fetch.FromMemory, 0x10 + RamStart, default),
                new Shaped(Fetch.FromStack, 0, default),
            ],
            items);
        Assert.Equal(Code + 5, after);
    }

    // An indirect mode's address comes in a byte, a short or a word.
    [Fact]
    public void AnIndirectAddressComesAtEveryWidth()
    {
        // Modes 6 and 7 in the first byte, 10 and 15 in the second.
        var memory = Mapped([0x76, 0xFA, 0x01, 0x00, 0x00, 0x00, 0x02, 0x00, 0x00, 0x04, 0xFF, 0xFF, 0xFF, 0xF0]);
        var (items, after) = Operands.Shape(memory, Code, new OperandList("LLLL"));

        Assert.Equal(
            [
                new Shaped(Fetch.FromMemory, 0x0100, default),
                new Shaped(Fetch.FromMemory, 0x0200, default),
                new Shaped(Fetch.FromLocal, 0x0004, default),
                // The addition truncates to 32 bits, so a RAM offset
                // near the top wraps around below RAMSTART.
                new Shaped(Fetch.FromMemory, 0xF0, default),
            ],
            items);
        Assert.Equal(Code + 14, after);
    }

    // A store operand's destination is wholly known from the
    // instruction: it depends on nothing that runs.
    [Fact]
    public void TheStoreModesNameWhereTheValueGoes()
    {
        // Modes 0 and 8 in the first byte, 5 and 9 in the second,
        // then 13 in the third.
        var memory = Mapped([0x80, 0x95, 0x0D, 0x40, 0x00, 0x10]);
        var (items, after) = Operands.Shape(memory, Code, new OperandList("SSSSS"));

        Assert.Equal(
            [
                new Shaped(Fetch.Fixed, 0, Operands.Discard),
                new Shaped(Fetch.Fixed, 0, Operands.Push),
                new Shaped(Fetch.Fixed, 0, new StoreTarget(DestType.Memory, 0x40)),
                new Shaped(Fetch.Fixed, 0, new StoreTarget(DestType.Local, 0)),
                new Shaped(Fetch.Fixed, 0, new StoreTarget(DestType.Memory, 0x10 + RamStart)),
            ],
            items);
        Assert.Equal(Code + 6, after);
    }

    // An opcode with no operands reads no mode bytes at all.
    [Fact]
    public void AnOpcodeWithNoOperandsReadsNothing()
    {
        var (items, after) = Operands.Shape(Mapped([]), Code, new OperandList(""));

        Assert.Empty(items);
        Assert.Equal(Code, after);
    }

    // Modes 4 and 12 have no width and are not the stack, so they
    // name nothing the specification defines.
    [Theory]
    [InlineData(0x04, "load", "L")]
    [InlineData(0x0C, "load", "L")]
    [InlineData(0x04, "store", "S")]
    [InlineData(0x0C, "store", "S")]
    public void AnUndefinedAddressingModeIsRefused(byte mode, string direction, string spec)
    {
        var memory = Mapped([mode]);

        Assert.Equal(
            $"addressing mode {mode} in a {direction} operand is not one the spec defines (Glulx: Instruction Format)",
            Refusal(() => Operands.Shape(memory, Code, new OperandList(spec))));
    }

    [Fact]
    public void AConstantModeCannotServeAStoreOperand()
    {
        var memory = Mapped([0x01, 0x00]);

        Assert.Equal(
            "a constant addressing mode cannot serve a store operand (Glulx: Instruction Format)",
            Refusal(() => Operands.Shape(memory, Code, new OperandList("S"))));
    }

    // The mode nibbles and the operand data are read from two cursors
    // that each have to stay on the map.
    [Fact]
    public void OperandDataRunningOffTheMapIsRefused()
    {
        var memory = Mapped([]);

        Assert.Equal(
            "the address $400 is outside the memory map (Glulx: The Memory Map)",
            Refusal(() => Operands.Shape(memory, EndMem, new OperandList("L"))));
        Assert.Equal(
            "the address $ffffffff is outside the memory map (Glulx: The Memory Map)",
            Refusal(() => Operands.Shape(memory, -1, new OperandList("L"))));

        // A one-byte constant whose mode byte is the map's last.
        memory.WriteByte(EndMem - 1, 0x01);
        Assert.Equal(
            "the address $400 is outside the memory map (Glulx: The Memory Map)",
            Refusal(() => Operands.Shape(memory, EndMem - 1, new OperandList("L"))));

        // And an indirect address in the same seat.
        memory.WriteByte(EndMem - 1, 0x05);
        Assert.Equal(
            "the address $400 is outside the memory map (Glulx: The Memory Map)",
            Refusal(() => Operands.Shape(memory, EndMem - 1, new OperandList("L"))));
    }

    // What a mode fetches is read only when the shape is resolved,
    // and strictly left to right, because a stack mode pops as its
    // turn comes.
    [Fact]
    public void ResolvingFetchesWhatTheModesName()
    {
        // Modes 6, 9, 8 and 1.
        var memory = Mapped([0x96, 0x18, 0x01, 0x40, 0x00, 0x07]);
        memory.WriteWord(0x140, 0xAABBCCDD);
        var stack = new StackMemory(1024);
        stack.PushFrame([new LocalsFormat(4, 1)]);
        stack.SetLocal(0, 0x11223344);
        stack.Push(0x55667788);

        var (args, after) = Operands.DecodeOperands(memory, stack, Code, new OperandList("LLLL"));

        Assert.Equal(Code + 6, after);
        Assert.Equal([0xAABBCCDDu, 0x11223344u, 0x55667788u, 7u], args.Select(arg => arg.Value));
    }

    // The memory mode reads at the operand list's own width, which
    // copyb and copys narrow.
    [Fact]
    public void AResolvedMemoryModeReadsAtTheListsWidth()
    {
        var memory = Mapped([0x06, 0x01, 0x40]);
        memory.WriteWord(0x140, 0xAABBCCDD);
        var stack = new StackMemory(1024);

        Assert.Equal(0xAAu, Operands.DecodeOperands(memory, stack, Code, new OperandList("L", 1)).Args[0].Value);
        Assert.Equal(0xAABBu, Operands.DecodeOperands(memory, stack, Code, new OperandList("L", 2)).Args[0].Value);
    }

    // A store writes where the target says, at the width it was
    // given, and a narrowed value pushed to the stack still lands as
    // a full four-byte word.
    [Fact]
    public void AStoreWritesWhereItsTargetSays()
    {
        var memory = Mapped([]);
        var stack = new StackMemory(1024);
        stack.PushFrame([new LocalsFormat(4, 1)]);

        Operands.Store(memory, stack, Operands.Discard, 0xFF);
        Operands.Store(memory, stack, new StoreTarget(DestType.Memory, 0x140), 0xAABBCCDD);
        Operands.Store(memory, stack, new StoreTarget(DestType.Memory, 0x150), 0xAABBCCDD, 1);
        Operands.Store(memory, stack, new StoreTarget(DestType.Memory, 0x160), 0xAABBCCDD, 2);
        Operands.Store(memory, stack, new StoreTarget(DestType.Local, 0), 0x11223344);
        Operands.Store(memory, stack, Operands.Push, 0xAABBCCDD, 1);

        Assert.Equal(0xAABBCCDDu, memory.ReadWord(0x140));
        Assert.Equal(0xDD, memory.ReadByte(0x150));
        Assert.Equal(0xCCDD, memory.ReadShort(0x160));
        Assert.Equal(0x11223344u, stack.GetLocal(0));
        Assert.Equal(0xDDu, stack.Pop());
    }

    [Fact]
    public void AStoreToADestinationTheSpecDoesNotDefineIsRefused()
    {
        var memory = Mapped([]);
        var stack = new StackMemory(1024);

        Assert.Equal(
            "a store reached destination type 7, which the spec does not define (Glulx: Call Stubs)",
            Refusal(() => Operands.Store(memory, stack, new StoreTarget((DestType)7, 0), 1)));
    }

    // The value truncates to its low bits first: the operand modes
    // feed narrow values, but sexb and sexs pass full words and rely
    // on that truncation.
    [Theory]
    [InlineData(0x7Fu, 8, 0x7Fu)]
    [InlineData(0xFFu, 8, 0xFFFFFFFFu)]
    [InlineData(0x12345678u, 8, 0x78u)]
    [InlineData(0x1234u, 16, 0x1234u)]
    [InlineData(0x8000u, 16, 0xFFFF8000u)]
    [InlineData(0x12348765u, 16, 0xFFFF8765u)]
    public void ASignExtensionTruncatesThenSpreadsTheSignBit(uint value, int bits, uint extended)
    {
        Assert.Equal(extended, Operands.SignExtend(value, bits));
    }

    // The one place the Glulx map is named, the Z-machine having a
    // Memory of its own.
    private static Memory Mapped(byte[] code) =>
        new(new Story(new GlulxBuilder().Lay(Code, code).Build()));

    private static string Refusal(Action work) => Assert.Throws<GlulxException>(work).Message;
}
