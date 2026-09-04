namespace Voxam.Core.Glulx;

/// <summary>A decoded function header (Glulx: Functions).</summary>
public sealed class FunctionHeader(int funcType, LocalsFormat[] localsFormat, int codeAddr)
{
    /// <summary>StackArguments or LocalArguments.</summary>
    public int FuncType { get; } = funcType;

    /// <summary>The declared locals, in order.</summary>
    public LocalsFormat[] LocalsFormat { get; } = localsFormat;

    /// <summary>The first instruction, just past the header.</summary>
    public int CodeAddr { get; } = codeAddr;
}

/// <summary>
/// Function entry: headers read, frames built, arguments seated.
///
/// A function opens with a type byte, C0 for stack arguments and C1
/// for local arguments, and a locals-format list, and its code begins
/// just past that (Glulx: Functions). Entering one builds a call
/// frame and seats the arguments as the type directs: a C0 function
/// finds them pushed on its value stack, last argument first with the
/// count on top, while a C1 function finds them written into its
/// locals in order, extras dropped silently and unfilled locals left
/// zero (Glulx: Calling and Returning).
///
/// The call stub is deliberately not pushed here. Whether one is
/// needed, and what its DestType says, depends on the opcode, call
/// pushing one where tailcall pointedly does not, so the stub stays
/// the caller's business.
/// </summary>
public static class Funcs
{
    /// <summary>A function taking its arguments on the stack (Glulx: Functions).</summary>
    public const int StackArguments = 0xC0;

    /// <summary>A function taking its arguments in its locals (Glulx: Functions).</summary>
    public const int LocalArguments = 0xC1;

    // C2 through DF are reserved for function types yet to be defined
    // (Glulx: Functions). The specification distinguishes them from
    // plain non-functions, and so does the reference glulxe, because
    // the difference tells an author whether an address is wrong or
    // merely too new for the interpreter.
    private const int ReservedFirst = 0xC2;
    private const int ReservedLast = 0xDF;

    // The sign bit of an unsigned 32-bit argument count: a negative
    // count is a count gone wrong, not a big one.
    private const uint CountSignBit = 0x8000_0000;

    private const int WordWidth = 4;

    /// <summary>
    /// Read the type byte and locals-format list at an address.
    ///
    /// A header below RAMSTART cannot change, so a caller that offers
    /// somewhere to keep one gets the same header back on every later
    /// call to the same function (Glulx: The Memory Map). A header
    /// reaching into RAM is read afresh every time, since the story
    /// may have written over it.
    /// </summary>
    /// <exception cref="GlulxException">
    /// For a type byte that is no function, or one reserved for a
    /// future kind of function, named as such, or a local type the
    /// format bytes cannot mean, or a header running off the map.
    /// </exception>
    public static FunctionHeader ReadFunctionHeader(Memory memory, int addr, Dictionary<int, FunctionHeader>? headers = null)
    {
        if (headers is not null && headers.TryGetValue(addr, out var held))
        {
            return held;
        }

        var funcaddr = addr;
        var functype = memory.ReadByte(addr);

        if (functype is not (StackArguments or LocalArguments))
        {
            throw new GlulxException(functype >= ReservedFirst && functype <= ReservedLast
                ? $"the address ${addr:x} holds type ${functype:x}, a function of a kind reserved for the future (Glulx: Functions)"
                : $"the address ${addr:x} holds type ${functype:x}, which is not a function at all (Glulx: Functions)");
        }

        addr++;
        var entries = new List<LocalsFormat>();

        while (true)
        {
            var size = memory.ReadByte(addr);
            var count = memory.ReadByte(addr + 1);
            addr += 2;

            if (size == 0)
            {
                break;
            }

            if (size is not (1 or 2 or 4))
            {
                throw new GlulxException($"the function header at ${addr - 2:x} declares a local type of {size}, not 1, 2, or 4 (Glulx: Functions)");
            }

            entries.Add(new LocalsFormat(size, count));
        }

        var header = new FunctionHeader(functype, [.. entries], addr);

        // The header runs from funcaddr up to the code it names, so
        // that is the span which has to sit in memory the story
        // cannot write before it is worth keeping.
        if (headers is not null && addr <= memory.RamStart)
        {
            headers[funcaddr] = header;
        }

        return header;
    }

    /// <summary>
    /// Enter the function at an address; the new program counter comes
    /// back. The arguments arrive in call order and are seated as the
    /// function's type directs (Glulx: Calling and Returning).
    /// </summary>
    /// <exception cref="GlulxException">
    /// For an address that is no function, or a frame the stack cannot
    /// hold.
    /// </exception>
    public static int PushCallFrame(Memory memory, StackMemory stack, int funcaddr, IReadOnlyList<uint> args, Dictionary<int, FunctionHeader>? headers = null)
    {
        var header = ReadFunctionHeader(memory, funcaddr, headers);

        stack.PushFrame(header.LocalsFormat);

        if (header.FuncType == StackArguments)
        {
            PushStackArguments(stack, args);
        }
        else
        {
            WriteLocalArguments(stack, header.LocalsFormat, args);
        }

        return header.CodeAddr;
    }

    /// <summary>
    /// Collect a call's arguments, from the stack or from memory.
    ///
    /// With addr zero the arguments come off the stack, first argument
    /// topmost, which is how callf's kin leave them. Otherwise they
    /// read as a word array at addr, which is what the accelerated
    /// functions need, the address arithmetic wrapping at 32 bits like
    /// all address arithmetic.
    /// </summary>
    /// <exception cref="GlulxException">
    /// For a stack with fewer values than asked, or a count with its
    /// sign bit set, which is a count gone wrong rather than a big
    /// one.
    /// </exception>
    public static List<uint> PopArguments(StackMemory stack, uint count, Memory memory, uint addr = 0)
    {
        if ((count & CountSignBit) != 0)
        {
            throw new GlulxException($"an argument count of {count} has its sign bit set");
        }

        var args = new List<uint>();

        for (var index = 0u; index < count; index++)
        {
            args.Add(addr == 0
                ? stack.Pop()
                : memory.ReadWord((int)(addr + (WordWidth * index))));
        }

        return args;
    }

    // Seat a C0 function's arguments: backwards, then the count. The
    // last argument pushes first, so the first ends up topmost with
    // the count above it (Glulx: Functions).
    private static void PushStackArguments(StackMemory stack, IReadOnlyList<uint> args)
    {
        for (var index = args.Count - 1; index >= 0; index--)
        {
            stack.Push(args[index]);
        }

        stack.Push((uint)args.Count);
    }

    // Seat a C1 function's arguments into its locals, in order. Extra
    // arguments drop silently and unfilled locals stay zero, both per
    // (Glulx: Functions). A value written into an 8- or 16-bit local
    // truncates, a deprecated arrangement but still a legal one.
    private static void WriteLocalArguments(StackMemory stack, LocalsFormat[] localsFormat, IReadOnlyList<uint> args)
    {
        var index = 0;
        var offset = 0;

        foreach (var entry in localsFormat)
        {
            if (index >= args.Count)
            {
                return;
            }

            // Each run starts at its own natural alignment, exactly as
            // the frame laid it down.
            var remainder = offset % entry.Size;
            offset += remainder == 0 ? 0 : entry.Size - remainder;

            for (var seat = 0; seat < entry.Count; seat++)
            {
                if (index >= args.Count)
                {
                    return;
                }

                stack.SetLocal(offset, args[index], entry.Size);
                offset += entry.Size;
                index++;
            }
        }
    }
}
