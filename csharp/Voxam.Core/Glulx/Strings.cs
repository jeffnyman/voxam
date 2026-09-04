using System.Globalization;

namespace Voxam.Core.Glulx;

/// <summary>
/// Where a character goes when the Glk output system is current
/// (Glulx: Output).
///
/// Two calls rather than one, because a byte stream would flatten
/// anything above 0xFF to a question mark, and the wide characters
/// have their own Glk call for exactly that reason (Glk: Output). The
/// library that answers these arrives with the Glk era; until then
/// only the machine's own callers can supply one.
/// </summary>
public interface IGlkOutput
{
    /// <summary>A character that fits a byte.</summary>
    void PutChar(uint character);

    /// <summary>A character too wide for a byte stream to carry whole.</summary>
    void PutCharUni(uint character);
}

/// <summary>
/// String decoding and the output opcodes (Glulx: Strings).
///
/// Three string types share one entry point: E0, plain bytes; E2,
/// 32-bit characters; and E1, Huffman-compressed against the
/// string-decoding table (Glulx: The String-Decoding Table). Only E1
/// is interesting: its tree can hold nodes that print other strings
/// or call functions, so decoding is not a loop that runs to
/// completion but a coroutine that may suspend into the machine and
/// resume later (Glulx: Calling and Returning Within Strings).
///
/// In filter mode every character is a function call, and a
/// compressed string may call a function at any node. Either way the
/// decoder stops, records where it was as a call stub, the resume
/// types the stack module names, and lets the machine run; Resume is
/// the other half, called when one of those stubs comes back off the
/// stack. Glk mode never suspends, since output there is a direct
/// call: that is the path real games take, and it stays a plain loop.
/// The null mode decodes and discards.
/// </summary>
public static class Strings
{
    // The three string types; E3 through FF are reserved for future
    // kinds of string (Glulx: Strings).
    private const int CString = 0xE0;
    private const int Compressed = 0xE1;
    private const int UnicodeString = 0xE2;
    private const int StringFirst = 0xE0;
    private const int StringLast = 0xFF;

    private const int FunctionFirst = 0xC0;
    private const int FunctionLast = 0xDF;

    // The node types a decoding table may hold (Glulx: The
    // String-Decoding Table).
    private const int NodeBranch = 0x00;
    private const int NodeTerminator = 0x01;
    private const int NodeChar = 0x02;
    private const int NodeCStr = 0x03;
    private const int NodeUniChar = 0x04;
    private const int NodeUniStr = 0x05;
    private const int NodeIndirect = 0x08;
    private const int NodeDoubleIndirect = 0x09;
    private const int NodeIndirectArgs = 0x0A;
    private const int NodeDoubleIndirectArgs = 0x0B;

    // The root node's address sits at the table's ninth byte, after
    // the length and node-count words (Glulx: The String-Decoding
    // Table).
    private const int RootAt = 8;
    private const int LastBit = 7;

    // One past the last character a byte-sized Glk put can carry
    // whole (Glk: Output).
    private const uint GlkByteLimit = 0x100;

    /// <summary>
    /// The engine of streamchar and streamunichar. In filter mode this
    /// enters the filter function and returns; the machine carries on
    /// from there, and the ordinary function-return path brings it
    /// back, the stub discarding the filter's result exactly as the
    /// reference glulxe arranges it.
    /// </summary>
    public static void PutChar(Machine machine, uint character)
    {
        var mode = machine.IoSys.Mode;

        if (mode == (uint)IoMode.Null)
        {
            return;
        }

        if (mode == (uint)IoMode.Filter)
        {
            machine.Stack.PushStub(DestType.Discard, 0, (uint)machine.Pc);
            machine.EnterFunction(machine.IoSys.Rock, [character]);

            return;
        }

        PutGlk(machine, character);
    }

    /// <summary>
    /// The engine of streamnum: print a signed decimal. The character
    /// count is nonzero only when resuming a filter-mode print, and
    /// the resume stub's own program-counter field carries the number,
    /// so resuming needs it stored nowhere else (Glulx: Calling and
    /// Returning Within Strings).
    /// </summary>
    public static void StreamNum(Machine machine, uint value, bool inMiddle = false, int charnum = 0)
    {
        var text = ((int)value).ToString(CultureInfo.InvariantCulture);
        var mode = machine.IoSys.Mode;

        if (mode == (uint)IoMode.Glk)
        {
            for (var at = charnum; at < text.Length; at++)
            {
                PutGlk(machine, text[at]);
            }
        }
        else if (mode == (uint)IoMode.Filter)
        {
            if (!inMiddle)
            {
                machine.Stack.PushStub(DestType.ResumeFunction, 0, (uint)machine.Pc);
                inMiddle = true;
            }

            if (charnum < text.Length)
            {
                machine.Stack.PushStub(DestType.ResumeNumber, (uint)(charnum + 1), value);
                machine.EnterFunction(machine.IoSys.Rock, [text[charnum]]);

                return;
            }
        }

        if (!inMiddle)
        {
            return;
        }

        var stub = machine.Stack.PopStub();
        machine.Pc = (int)stub.Pc;

        if (stub.DestType != DestType.ResumeFunction)
        {
            throw new GlulxException("a string-on-string call stub arrived while printing a number (Glulx: Calling and Returning Within Strings)");
        }
    }

    /// <summary>The engine of streamstr, and the landing for resumed strings.</summary>
    /// <exception cref="GlulxException">
    /// For a null address, a type byte that is no string, or a table
    /// the walk cannot follow.
    /// </exception>
    public static void StreamString(Machine machine, uint addr, int inMiddle = 0, int bitnum = 0)
    {
        if (addr == 0)
        {
            throw new GlulxException("streamstr with a null address (Glulx: Output)");
        }

        new Printer(machine, (int)addr, inMiddle, bitnum).Run();
    }

    /// <summary>
    /// Continue a suspended print from its popped stub. The machine's
    /// stub-popping filtered the types already, so the four resume
    /// kinds are exhaustive here (Glulx: Calling and Returning Within
    /// Strings).
    /// </summary>
    public static void Resume(Machine machine, CallStub stub)
    {
        machine.Pc = (int)stub.Pc;

        switch (stub.DestType)
        {
            case DestType.ResumeCompressed:
                StreamString(machine, stub.Pc, Compressed, (int)stub.DestAddr);
                break;
            case DestType.ResumeCString:
                StreamString(machine, stub.Pc, CString);
                break;
            case DestType.ResumeUnicode:
                StreamString(machine, stub.Pc, UnicodeString);
                break;
            default:
                StreamNum(machine, stub.Pc, inMiddle: true, charnum: (int)stub.DestAddr);
                break;
        }
    }

    // Emit one character through the machine's Glk library. Only
    // forcing the output system can arrange for this with no library
    // installed, since setiosys falls back to the null system.
    private static void PutGlk(Machine machine, uint character)
    {
        if (machine.Glk is null)
        {
            throw new GlulxException("Glk output selected, but no Glk library is installed");
        }

        if (character < GlkByteLimit)
        {
            machine.Glk.PutChar(character);
        }
        else
        {
            machine.Glk.PutCharUni(character);
        }
    }

    /// <summary>
    /// One streamstr in progress: the mutable state the reference
    /// glulxe keeps in the locals of a three-hundred-line function.
    /// Where the walk stands, which bit, whether the terminator stub
    /// is down yet, and whether control was handed back to the
    /// machine.
    /// </summary>
    private sealed class Printer(Machine machine, int addr, int inMiddle, int bitnum)
    {
        private readonly Machine _machine = machine;
        private int _addr = addr;
        private int _inMiddle = inMiddle;
        private int _bitnum = bitnum;

        // Entering mid-string means the terminator stub is already on
        // the stack.
        private bool _substring = inMiddle != 0;
        private bool _suspended;

        /// <summary>Print until the string ends or the machine must run.</summary>
        public void Run()
        {
            var memory = _machine.Memory;

            while (true)
            {
                int kind;

                if (_inMiddle == 0)
                {
                    kind = memory.ReadByte(_addr);
                    // E2 strings pad to a four-byte boundary; the
                    // others start right after their type byte.
                    _addr += kind == UnicodeString ? 4 : 1;
                    _bitnum = 0;
                }
                else
                {
                    kind = _inMiddle;
                    _inMiddle = 0;
                }

                var restart = kind switch
                {
                    Compressed => Walk(),
                    CString => PlainString(),
                    UnicodeString => WideString(),
                    >= StringFirst and <= StringLast =>
                        throw new GlulxException($"the type byte ${kind:x} names a kind of string reserved for the future (Glulx: Strings)"),
                    _ => throw new GlulxException($"the type byte ${kind:x} is not a string at all (Glulx: Strings)"),
                };

                if (_suspended)
                {
                    return;
                }

                if (restart)
                {
                    continue;
                }

                if (!_substring || !PopStringStub())
                {
                    return;
                }

                _inMiddle = Compressed;
            }
        }

        // An E0 string: bytes to a zero terminator.
        private bool PlainString()
        {
            var memory = _machine.Memory;
            var mode = _machine.IoSys.Mode;

            if (mode == (uint)IoMode.Filter)
            {
                BeginSubstring();

                var first = (uint)memory.ReadByte(_addr);
                _addr += 1;

                if (first != 0)
                {
                    CallFilter(first, DestType.ResumeCString, 0, _addr);
                }

                return false;
            }

            while (true)
            {
                var character = (uint)memory.ReadByte(_addr);
                _addr += 1;

                if (character == 0)
                {
                    return false;
                }

                if (mode == (uint)IoMode.Glk)
                {
                    PutGlk(_machine, character);
                }
            }
        }

        // An E2 string: 32-bit characters to a zero terminator.
        private bool WideString()
        {
            var memory = _machine.Memory;
            var mode = _machine.IoSys.Mode;

            if (mode == (uint)IoMode.Filter)
            {
                BeginSubstring();

                var first = memory.ReadWord(_addr);
                _addr += 4;

                if (first != 0)
                {
                    CallFilter(first, DestType.ResumeUnicode, 0, _addr);
                }

                return false;
            }

            while (true)
            {
                var character = memory.ReadWord(_addr);
                _addr += 4;

                if (character == 0)
                {
                    return false;
                }

                if (mode == (uint)IoMode.Glk)
                {
                    PutGlk(_machine, character);
                }
            }
        }

        /// <summary>
        /// Walk the Huffman tree until the string ends or the print
        /// suspends; true means a sub-object was set up and the outer
        /// loop should start again on it.
        ///
        /// The reference glulxe keeps a multi-bit cache of the tree;
        /// this is the plain walk it falls back on, one memory read
        /// per bit. The cache is a worthwhile optimization later, but
        /// it has to cope with a table in RAM the game can rewrite, so
        /// correctness first.
        /// </summary>
        private bool Walk()
        {
            var memory = _machine.Memory;
            var table = (int)_machine.StringTable;

            if (table == 0)
            {
                throw new GlulxException("a compressed string cannot print with no decoding table set (Glulx: The String-Decoding Table)");
            }

            var root = (int)memory.ReadWord(table + RootAt);
            var bits = memory.ReadByte(_addr);

            if (_bitnum != 0)
            {
                bits >>= _bitnum;
            }

            var node = root;

            while (true)
            {
                var nodetype = memory.ReadByte(node);
                node++;

                switch (nodetype)
                {
                    case NodeBranch:
                        // Bits read low bit first (Glulx: Strings).
                        node = (int)memory.ReadWord((bits & 1) != 0 ? node + 4 : node);

                        if (_bitnum == LastBit)
                        {
                            _bitnum = 0;
                            _addr += 1;
                            bits = memory.ReadByte(_addr);
                        }
                        else
                        {
                            _bitnum++;
                            bits >>= 1;
                        }

                        break;
                    case NodeTerminator:
                        return false;
                    case NodeChar:
                        if (!Emit((uint)memory.ReadByte(node)))
                        {
                            return false;
                        }

                        node = root;
                        break;
                    case NodeUniChar:
                        if (!Emit(memory.ReadWord(node)))
                        {
                            return false;
                        }

                        node = root;
                        break;
                    case NodeCStr:
                        if (EmitSubstring(node, CString))
                        {
                            return true;
                        }

                        node = root;
                        break;
                    case NodeUniStr:
                        if (EmitSubstring(node, UnicodeString))
                        {
                            return true;
                        }

                        node = root;
                        break;
                    case NodeIndirect:
                    case NodeDoubleIndirect:
                    case NodeIndirectArgs:
                    case NodeDoubleIndirectArgs:
                        // Either restarts on a referenced string or
                        // suspends into a referenced function; both
                        // end this walk.
                        return Indirect(nodetype, node);
                    default:
                        throw new GlulxException($"node type ${nodetype:x} is not one the decoding table may hold (Glulx: The String-Decoding Table)");
                }
            }
        }

        // Print one character; false means the print suspended into a
        // filter.
        private bool Emit(uint character)
        {
            var mode = _machine.IoSys.Mode;

            if (mode == (uint)IoMode.Glk)
            {
                PutGlk(_machine, character);

                return true;
            }

            if (mode == (uint)IoMode.Filter)
            {
                BeginSubstring();
                CallFilter(character, DestType.ResumeCompressed, (uint)_bitnum, _addr);

                return false;
            }

            // The null mode: decoded and discarded.
            return true;
        }

        // A node holding a whole string; true restarts on it.
        private bool EmitSubstring(int node, int kind)
        {
            var memory = _machine.Memory;
            var mode = _machine.IoSys.Mode;

            if (mode == (uint)IoMode.Filter)
            {
                // Hand the sub-string to the top-level loop, with a
                // stub remembering where the compressed stream picks
                // back up.
                BeginSubstring();
                _machine.Pc = _addr;
                _machine.Stack.PushStub(DestType.ResumeCompressed, (uint)_bitnum, (uint)_addr);
                _inMiddle = kind;
                _addr = node;

                return true;
            }

            if (mode == (uint)IoMode.Glk)
            {
                if (kind == CString)
                {
                    uint character;

                    while ((character = (uint)memory.ReadByte(node)) != 0)
                    {
                        PutGlk(_machine, character);
                        node += 1;
                    }
                }
                else
                {
                    uint character;

                    while ((character = memory.ReadWord(node)) != 0)
                    {
                        PutGlk(_machine, character);
                        node += 4;
                    }
                }
            }

            return false;
        }

        // Follow an indirect reference to a string or a function. True
        // restarts the outer loop on a referenced string; a referenced
        // function suspends instead.
        private bool Indirect(int nodetype, int node)
        {
            var memory = _machine.Memory;
            var target = (int)memory.ReadWord(node);

            if (nodetype is NodeDoubleIndirect or NodeDoubleIndirectArgs)
            {
                target = (int)memory.ReadWord(target);
            }

            var targetType = memory.ReadByte(target);

            BeginSubstring();

            if (targetType is >= StringFirst and <= StringLast)
            {
                _machine.Pc = _addr;
                _machine.Stack.PushStub(DestType.ResumeCompressed, (uint)_bitnum, (uint)_addr);
                _inMiddle = 0;
                _addr = target;

                return true;
            }

            if (targetType is >= FunctionFirst and <= FunctionLast)
            {
                var args = nodetype is NodeIndirectArgs or NodeDoubleIndirectArgs
                    ? Funcs.PopArguments(_machine.Stack, memory.ReadWord(node + 4), memory, (uint)(node + 8))
                    : [];

                _machine.Stack.PushStub(DestType.ResumeCompressed, (uint)_bitnum, (uint)_addr);
                _machine.EnterFunction((uint)target, args);
                _suspended = true;

                return false;
            }

            throw new GlulxException($"an indirect node reaches ${target:x}, which holds neither a string nor a function (Glulx: The String-Decoding Table)");
        }

        // Lay the terminator stub that marks where this print began.
        private void BeginSubstring()
        {
            if (!_substring)
            {
                _machine.Stack.PushStub(DestType.ResumeFunction, 0, (uint)_machine.Pc);
                _substring = true;
            }
        }

        // Suspend into the filter function with one character.
        private void CallFilter(uint character, DestType desttype, uint destaddr, int pc)
        {
            _machine.Stack.PushStub(desttype, destaddr, (uint)pc);
            _machine.EnterFunction(_machine.IoSys.Rock, [character]);
            _suspended = true;
        }

        // Pop a resume or terminator stub; false ends the print.
        private bool PopStringStub()
        {
            var stub = _machine.Stack.PopStub();
            _machine.Pc = (int)stub.Pc;

            if (stub.DestType == DestType.ResumeFunction)
            {
                return false;
            }

            if (stub.DestType == DestType.ResumeCompressed)
            {
                _addr = (int)stub.Pc;
                _bitnum = (int)stub.DestAddr;

                return true;
            }

            throw new GlulxException("a function-terminator call stub arrived at the end of a string (Glulx: Calling and Returning Within Strings)");
        }
    }
}
