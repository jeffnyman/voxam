namespace Voxam.Core.Glulx;

/// <summary>Whether an operand is read from or written to.</summary>
public enum Form
{
    Load = 0,
    Store = 1,
}

/// <summary>
/// What an operand's value costs to produce, once its addressing
/// mode is known. A shape names one of these per operand, and only
/// the first needs nothing but the payload already in hand.
/// </summary>
public enum Fetch
{
    Fixed = 0,
    FromStack = 1,
    FromMemory = 2,
    FromLocal = 3,
}

/// <summary>
/// Where a store operand's value goes, once it is known: the same
/// vocabulary call stubs speak (Glulx: Call Stubs).
/// </summary>
public readonly record struct StoreTarget(DestType DestType, uint Addr);

/// <summary>
/// One operand as the instruction's own bytes describe it, before
/// anything has been read: what it costs to fetch, and either the
/// constant or address that fetch needs, or the destination a store
/// already knows.
/// </summary>
public readonly record struct Shaped(Fetch Kind, uint Payload, StoreTarget Target);

/// <summary>
/// A decoded operand: a load's value, or a store's destination. The
/// caller tells the two apart by the same signature it passed in.
/// </summary>
public readonly record struct Operand(uint Value, StoreTarget Target);

/// <summary>
/// An opcode's operand signature: each operand's direction, left to
/// right, and the width the indirect modes move, which is 4 for
/// almost every opcode; copyb and copys narrow it to 1 and 2 (Glulx:
/// Instruction Format).
/// </summary>
public sealed class OperandList
{
    /// <summary>Build a signature from a spelling like "LLS": one letter per operand, L loads and S stores.</summary>
    public OperandList(string spec, int argSize = 4)
    {
        Forms = [.. spec.Select(letter => letter == 'L' ? Form.Load : Form.Store)];
        ArgSize = argSize;
    }

    /// <summary>Each operand's direction, left to right.</summary>
    public Form[] Forms { get; }

    /// <summary>The width the indirect modes move.</summary>
    public int ArgSize { get; }

    /// <summary>How many operands the signature carries.</summary>
    public int Count => Forms.Length;
}

/// <summary>
/// Operand decoding: opcodes, addressing modes, and stores.
///
/// Everything here is (Glulx: Instruction Format): an opcode number
/// whose own top bits say whether it spans one, two or four bytes;
/// then the operands' addressing modes, packed two nibbles per byte;
/// then the operand data itself. Operands are evaluated strictly
/// left to right, which the specification calls out because several
/// modes pop the stack, and order is the difference between right
/// and wrong.
///
/// This is also where the 32-bit discipline is enforced. Loads
/// always yield unsigned values, the constant modes sign-extending
/// and then reducing to the equivalent unsigned value, and Store
/// masks on the way out.
///
/// The sixteen modes decode arithmetically rather than by table:
/// they fall into four groups of four, constant, memory, local and
/// RAM, so mode >> 2 selects the group and mode &amp; 3 the operand's
/// width.
/// </summary>
public static class Operands
{
    // The opcode number's own length rides in its top bits: below
    // 0x80 one byte, below 0xC0 two bytes less 0x8000, else four
    // bytes less 0xC0000000, so 01, 8001 and C0000001 all name
    // opcode 1 (Glulx: Instruction Format).
    private const int OneByteOpcodeLimit = 0x80;
    private const int TwoByteOpcodeLimit = 0xC0;
    private const int TwoByteOpcodeBase = 0x8000;
    private const uint FourByteOpcodeBase = 0xC000_0000;

    // A mode byte carries two operands' modes: the first in its low
    // nibble, the second in its high (Glulx: Instruction Format).
    private const int ModeMask = 0x0F;
    private const int HighNibbleShift = 4;

    // mode >> 2 is the group, and mode & 3 the width code: none,
    // byte, short, word.
    private const int GroupShift = 2;
    private const int SizeMask = 0b11;
    private const int ConstantGroup = 0;
    private const int MemoryGroup = 1;
    private const int LocalGroup = 2;
    private const int StackMode = 8;

    private const int ByteBits = 8;
    private const int ShortBits = 16;

    /// <summary>A store operand that throws its value away.</summary>
    public static readonly StoreTarget Discard = new(DestType.Discard, 0);

    /// <summary>A store operand that pushes its value.</summary>
    public static readonly StoreTarget Push = new(DestType.Stack, 0);

    /// <summary>Read the opcode number at the program counter.</summary>
    /// <exception cref="GlulxException">For an opcode running off the map.</exception>
    public static (int Number, int After) DecodeOpcode(Memory memory, int pc)
    {
        var first = memory.ReadByte(pc);

        if (first < OneByteOpcodeLimit)
        {
            return (first, pc + 1);
        }

        if (first < TwoByteOpcodeLimit)
        {
            return (memory.ReadShort(pc) - TwoByteOpcodeBase, pc + 2);
        }

        return ((int)(memory.ReadWord(pc) - FourByteOpcodeBase), pc + 4);
    }

    /// <summary>
    /// Decode one instruction's addressing modes, without reading
    /// anything they name.
    ///
    /// An operand's mode, its width, and the address or constant it
    /// names all live in the instruction itself, so they are fixed
    /// for as long as those bytes are. What is not fixed is the value
    /// a mode fetches: a stack pop, a local, a word of memory. So
    /// this reads the shape and stops there, naming each operand as
    /// either a value already known or one of the three fetches.
    ///
    /// Store operands are wholly known here: their destination is the
    /// mode and the address, and neither depends on anything that
    /// runs (Glulx: Call Stubs).
    /// </summary>
    /// <exception cref="GlulxException">
    /// For an addressing mode the specification does not define, a
    /// constant mode on a store operand, or operand data running off
    /// the map.
    /// </exception>
    public static (Shaped[] Items, int After) Shape(Memory memory, int pc, OperandList oplist)
    {
        var forms = oplist.Forms;
        var count = oplist.Count;
        var data = memory.Data;
        var endmem = memory.EndMem;
        var ramstart = (uint)memory.RamStart;

        // The mode nibbles come first, packed two per byte, then the
        // operand data; both are read in step, from two cursors.
        var modeaddr = pc;
        pc += (count + 1) / 2;

        var items = new Shaped[count];
        var modeval = 0;

        for (var index = 0; index < count; index++)
        {
            int mode;

            if ((index & 1) != 0)
            {
                mode = modeval >> HighNibbleShift;
                modeaddr++;
            }
            else
            {
                if ((uint)modeaddr >= (uint)endmem)
                {
                    throw new GlulxException(OffTheMap(modeaddr));
                }

                modeval = data[modeaddr];
                mode = modeval & ModeMask;
            }

            var group = mode >> GroupShift;
            var size = mode & SizeMask;

            if (forms[index] == Form.Load)
            {
                if (group == ConstantGroup)
                {
                    switch (size)
                    {
                        case 0:
                            items[index] = new Shaped(Fetch.Fixed, 0, default);
                            break;
                        case 1:
                            if ((uint)pc >= (uint)endmem)
                            {
                                throw new GlulxException(OffTheMap(pc));
                            }

                            items[index] = new Shaped(Fetch.Fixed, SignExtend(data[pc], ByteBits), default);
                            pc += 1;
                            break;
                        case 2:
                            items[index] = new Shaped(Fetch.Fixed, SignExtend((uint)memory.ReadShort(pc), ShortBits), default);
                            pc += 2;
                            break;
                        default:
                            items[index] = new Shaped(Fetch.Fixed, memory.ReadWord(pc), default);
                            pc += 4;
                            break;
                    }

                    continue;
                }

                if (size == 0)
                {
                    if (mode != StackMode)
                    {
                        throw new GlulxException(UnknownMode(mode, "load"));
                    }

                    items[index] = new Shaped(Fetch.FromStack, 0, default);

                    continue;
                }

                var loadAddr = Address(memory, data, endmem, size, ref pc);

                items[index] = group switch
                {
                    MemoryGroup => new Shaped(Fetch.FromMemory, loadAddr, default),
                    LocalGroup => new Shaped(Fetch.FromLocal, loadAddr, default),
                    // Address addition truncates to 32 bits, so a RAM
                    // offset near 0xFFFFFFFF wraps around below
                    // RAMSTART (Glulx: Instruction Format). RAMSTART
                    // never moves, so the sum is settled here.
                    _ => new Shaped(Fetch.FromMemory, loadAddr + ramstart, default),
                };

                continue;
            }

            if (size == 0)
            {
                items[index] = mode switch
                {
                    0 => new Shaped(Fetch.Fixed, 0, Discard),
                    StackMode => new Shaped(Fetch.Fixed, 0, Push),
                    _ => throw new GlulxException(UnknownMode(mode, "store")),
                };

                continue;
            }

            if (group == ConstantGroup)
            {
                throw new GlulxException("a constant addressing mode cannot serve a store operand (Glulx: Instruction Format)");
            }

            var storeAddr = Address(memory, data, endmem, size, ref pc);

            items[index] = group switch
            {
                MemoryGroup => new Shaped(Fetch.Fixed, 0, new StoreTarget(DestType.Memory, storeAddr)),
                // DestType 2 is relative to LocalsBase, not an
                // absolute stack position, so the offset stores as
                // decoded (Glulx: Call Stubs).
                LocalGroup => new Shaped(Fetch.Fixed, 0, new StoreTarget(DestType.Local, storeAddr)),
                _ => new Shaped(Fetch.Fixed, 0, new StoreTarget(DestType.Memory, storeAddr + ramstart)),
            };
        }

        return (items, pc);
    }

    /// <summary>
    /// Fetch what a shape's operands stand for, left to right. The
    /// order matters: a stack-mode operand pops as its turn comes,
    /// which is the order the shape was read in (Glulx: Instruction
    /// Format).
    /// </summary>
    /// <exception cref="GlulxException">
    /// For a stack mode popping an empty stack, or a locals mode
    /// outside the frame's segment.
    /// </exception>
    public static Operand[] Resolve(Memory memory, StackMemory stack, Shaped[] items, int width)
    {
        var args = new Operand[items.Length];

        for (var index = 0; index < items.Length; index++)
        {
            var item = items[index];

            args[index] = item.Kind switch
            {
                Fetch.Fixed => new Operand(item.Payload, item.Target),
                Fetch.FromMemory => new Operand(memory.Read((int)item.Payload, width), default),
                Fetch.FromLocal => new Operand(stack.GetLocal((int)item.Payload, width), default),
                _ => new Operand(stack.Pop(), default),
            };
        }

        return args;
    }

    /// <summary>
    /// Decode one instruction's operands, left to right.
    ///
    /// The shape and the fetch are separate passes because the shape
    /// cannot change while the code it was read from cannot: the
    /// machine caches it and calls Resolve alone. This
    /// whole-instruction path stays for code that may move under the
    /// machine, and for anyone decoding a single instruction on its
    /// own.
    /// </summary>
    /// <exception cref="GlulxException">
    /// For an addressing mode the specification does not define, a
    /// constant mode on a store operand, operand data running off the
    /// map, a stack mode popping an empty stack, or a locals mode
    /// outside the frame's segment.
    /// </exception>
    public static (Operand[] Args, int After) DecodeOperands(Memory memory, StackMemory stack, int pc, OperandList oplist)
    {
        var (items, after) = Shape(memory, pc, oplist);

        return (Resolve(memory, stack, items, oplist.ArgSize), after);
    }

    /// <summary>
    /// Write a value where the target says. Call-stub destinations
    /// arrive here too: the vocabulary is the same (Glulx: Call
    /// Stubs). The width narrows only for copyb and copys, and a
    /// narrowed value pushed to the stack still lands as a full
    /// four-byte word, exactly as the reference glulxe's
    /// store_operand_s does.
    /// </summary>
    /// <exception cref="GlulxException">
    /// For a destination type the specification does not define, a
    /// memory destination off the map or in ROM, a local destination
    /// outside the frame's segment, or a push overflowing the stack.
    /// </exception>
    public static void Store(Memory memory, StackMemory stack, StoreTarget target, uint value, int width = 4)
    {
        value &= width switch { 1 => 0xFFu, 2 => 0xFFFFu, _ => 0xFFFFFFFFu };

        switch (target.DestType)
        {
            case DestType.Discard:
                return;
            case DestType.Memory:
                memory.Write((int)target.Addr, width, value);
                break;
            case DestType.Local:
                stack.SetLocal((int)target.Addr, value, width);
                break;
            case DestType.Stack:
                stack.Push(value);
                break;
            default:
                throw new GlulxException($"a store reached destination type {(uint)target.DestType}, which the spec does not define (Glulx: Call Stubs)");
        }
    }

    /// <summary>
    /// The low bits of a value, sign-extended to unsigned 32 bits.
    /// The value truncates to its low bits first: the operand modes
    /// feed this already-narrow values, but sexb and sexs pass full
    /// words and rely on the truncation, which the reference glulxe
    /// spells out as an explicit mask.
    /// </summary>
    public static uint SignExtend(uint value, int bits)
    {
        var mask = (1u << bits) - 1;
        var sign = 1u << (bits - 1);

        return ((value & mask) ^ sign) - sign;
    }

    // An indirect mode's address, at the width its size code names.
    private static uint Address(Memory memory, byte[] data, int endmem, int size, ref int pc)
    {
        if (size == 1)
        {
            if ((uint)pc >= (uint)endmem)
            {
                throw new GlulxException(OffTheMap(pc));
            }

            var single = data[pc];
            pc += 1;

            return single;
        }

        if (size == 2)
        {
            var pair = (uint)memory.ReadShort(pc);
            pc += 2;

            return pair;
        }

        var word = memory.ReadWord(pc);
        pc += 4;

        return word;
    }

    // The message an operand read past the map carries.
    private static string OffTheMap(int address) =>
        $"the address ${address:x} is outside the memory map (Glulx: The Memory Map)";

    // The message an undefined addressing mode carries.
    private static string UnknownMode(int mode, string direction) =>
        $"addressing mode {mode} in a {direction} operand is not one the spec defines (Glulx: Instruction Format)";
}
