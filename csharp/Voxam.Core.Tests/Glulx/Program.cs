using Voxam.Core.Glulx;

namespace Voxam.Tests.Glulx;

/// <summary>
/// One operand as a test spells it: its addressing mode, the value or
/// address that mode carries, and how many bytes that takes (Glulx:
/// Instruction Format).
/// </summary>
public readonly record struct Slot(int Mode, uint Value, int Bytes);

/// <summary>The addressing modes by name, each choosing its own narrowest width.</summary>
public static class Modes
{
    /// <summary>Pop a load's value, or push a store's.</summary>
    public static readonly Slot Stack = new(8, 0, 0);

    /// <summary>Throw a store's value away.</summary>
    public static readonly Slot Discard = new(0, 0, 0);

    /// <summary>A constant, which the narrow widths sign-extend.</summary>
    public static Slot Constant(uint value) => value switch
    {
        0 => new Slot(0, 0, 0),
        _ when (int)value is >= -128 and <= 127 => new Slot(1, value & 0xFF, 1),
        _ when (int)value is >= -32768 and <= 32767 => new Slot(2, value & 0xFFFF, 2),
        _ => new Slot(3, value, 4),
    };

    /// <summary>
    /// A constant in a full four bytes whatever its size, so a test
    /// that has to compute a branch offset knows the width first.
    /// </summary>
    public static Slot Word(uint value) => new(3, value, 4);

    /// <summary>Read from, or write to, an address in main memory.</summary>
    public static Slot Memory(uint addr) => Indirect(1, addr);

    /// <summary>Read from, or write to, a local at an offset.</summary>
    public static Slot Local(uint offset) => Indirect(2, offset);

    /// <summary>Read from, or write to, an address counted from RAMSTART.</summary>
    public static Slot Ram(uint offset) => Indirect(3, offset);

    private static Slot Indirect(int group, uint value) => value switch
    {
        <= 0xFF => new Slot((group * 4) + 1, value, 1),
        <= 0xFFFF => new Slot((group * 4) + 2, value, 2),
        _ => new Slot((group * 4) + 3, value, 4),
    };
}

/// <summary>
/// A tiny Glulx story assembled around one function: a header at the
/// start address, the instructions a test writes, and the header
/// numbers a machine boots from.
///
/// The function is the C1 kind by default, taking its arguments in
/// its locals, because that leaves the value stack empty for a test to
/// reason about; a C0 function pushes its argument count before the
/// first instruction runs.
/// </summary>
public sealed class GlulxProgram
{
    private readonly List<byte> _code = [];
    private readonly List<(int At, byte[] Data)> _laid = [];
    private readonly byte[] _header;

    /// <summary>Assemble at an address, with a count of word locals.</summary>
    public GlulxProgram(int at = 64, int locals = 0, int funcType = Funcs.LocalArguments)
    {
        Start = at;
        _header = locals == 0 ? [(byte)funcType, 0, 0] : [(byte)funcType, 4, (byte)locals, 0, 0];
    }

    /// <summary>Where the function begins, which is where the machine starts.</summary>
    public int Start { get; }

    /// <summary>How tall a stack the header asks for.</summary>
    public int StackSize { get; set; } = 1024;

    /// <summary>Where the memory map ends.</summary>
    public uint EndMem { get; set; } = 1024;

    /// <summary>The address the next instruction will be assembled at.</summary>
    public int Here => Start + _header.Length + _code.Count;

    /// <summary>Assemble one instruction (Glulx: Instruction Format).</summary>
    public GlulxProgram Op(Op opcode, params Slot[] args)
    {
        var number = (int)opcode;

        if (number < 0x80)
        {
            _code.Add((byte)number);
        }
        else
        {
            _code.Add((byte)(0x80 | (number >> 8)));
            _code.Add((byte)number);
        }

        for (var index = 0; index < args.Length; index += 2)
        {
            var high = index + 1 < args.Length ? args[index + 1].Mode : 0;
            _code.Add((byte)(args[index].Mode | (high << 4)));
        }

        foreach (var arg in args)
        {
            for (var shift = arg.Bytes - 1; shift >= 0; shift--)
            {
                _code.Add((byte)(arg.Value >> (8 * shift)));
            }
        }

        return this;
    }

    /// <summary>
    /// Overwrite a four-byte operand already assembled, which is how a
    /// branch learns the address of something written after it.
    /// </summary>
    public GlulxProgram Patch(int at, uint value)
    {
        var index = at - Start - _header.Length;

        for (var shift = 0; shift < 4; shift++)
        {
            _code[index + shift] = (byte)(value >> (8 * (3 - shift)));
        }

        return this;
    }

    /// <summary>Lay bytes somewhere in the stored image: a table, or a second function.</summary>
    public GlulxProgram Lay(int at, params byte[] data)
    {
        _laid.Add((at, data));

        return this;
    }

    /// <summary>
    /// The function's own bytes, header and code together, for laying
    /// into another program as a second function.
    /// </summary>
    public byte[] Assembled => [.. _header, .. _code];

    /// <summary>The story image, ready for a machine to boot.</summary>
    public byte[] Build()
    {
        var builder = new GlulxBuilder
        {
            StartFunction = (uint)Start,
            StackSize = (uint)StackSize,
            EndMem = EndMem,
        };

        builder.Lay(Start, [.. _header, .. _code]);

        foreach (var (at, data) in _laid)
        {
            builder.Lay(at, data);
        }

        return builder.Build();
    }

    /// <summary>A machine booted on this program, its dice seeded for repeatability.</summary>
    public Machine Booted(int? seed = 7) => new(new Story(Build()), seed);
}
