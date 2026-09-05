using System.Globalization;
using System.Text;

namespace Voxam.Core;

/// <summary>A running Z-Machine (§6.1): memory, call state, and the pc.</summary>
public sealed class Machine
{
    private const int TrueValue = 1;
    private const int FalseValue = 0;
    private const int NewlineCode = 13;
    private const int UndoDepth = 10;
    private const int DefaultForeground = 9;
    private const int DefaultBackground = 2;
    private const int TotalWidthAddress = 0x30;
    private const int RedirectionLimit = 16;

    private sealed class Frame
    {
        public int ReturnAddress;
        public int StoreVariable;
        public int[] Locals = [];
        public int StackBase;
        public int ArgCount;
    }

    private sealed record Redirection(int Table, StringBuilder Text, int? Limit);

    private readonly Memory _m;
    private readonly IFrontend _frontend;
    private readonly Func<string?> _input;
    private readonly Func<double?, string?>? _keySource;
    private readonly Func<double, string?>? _timedInputSource;
    private readonly Randomizer _rng;
    private readonly int _version;
    private readonly int _globals;
    private readonly ObjectTable _objects;
    private readonly List<int> _stack = [];
    private readonly List<Frame> _frames = [];
    private readonly Dictionary<int, Instruction> _cache = [];
    private readonly List<Redirection> _redirections = [];
    private readonly Queue<int> _pendingKeys = [];
    private readonly LinkedList<SavedState> _undo = [];
    private readonly ISaveSlot? _saves;
    private readonly HashSet<int> _passedReserved = [];
    private WindowLedger _windows;
    private readonly IStageFrontend? _stage;
    private readonly SortedSet<int> _aimed = [];
    private DictionaryTable? _words;
    private int _pc;
    private bool _running = true;
    private bool _screenSelected = true;
    private bool _storyWindow = true;
    private int _font = 1;
    private int _screenBuffering;

    // Story-window prints so far: a timed read's interrupt that
    // printed asks for the input line to be shown again.
    private int _prints;

    // The nimble half of the patient typist: the address of a timed
    // read_char an interrupt just terminated, whose retry finds the
    // keys ready rather than waiting a second interval.
    private int _typistReady = -1;

    /// <summary>Instructions executed across the whole session.</summary>
    public long Instructions { get; private set; }

    /// <summary>The working memory image, for instruments that read it.</summary>
    public Memory Memory => _m;

    /// <summary>
    /// Boot the machine. The input source answers whole lines; a key
    /// source, when a frontend can read the keyboard raw, answers one
    /// key per call and null when its timeout in seconds expires, and
    /// a timed input source waits a line read's own interval on the
    /// wall clock, answering null on expiry with the half-typed line
    /// kept composed. Without them, keystrokes are spent from lines
    /// and the patient typist keeps scripted sessions identical.
    /// </summary>
    public Machine(
        byte[] story,
        IFrontend frontend,
        Func<string?> input,
        int? seed,
        Func<double?, string?>? keySource = null,
        Func<double, string?>? timedInputSource = null,
        ISaveSlot? saves = null)
    {
        _m = new Memory(story);
        _frontend = frontend;
        _stage = frontend as IStageFrontend;
        _input = input;
        _keySource = keySource;
        _timedInputSource = timedInputSource;
        _saves = saves;
        _rng = new Randomizer(seed);
        _version = _m.Version;
        _globals = _m.ReadWord(Header.Globals);
        _objects = new ObjectTable(_m);
        _windows = FreshWindows();
        DeclareCapabilities();
        StartExecution();
    }

    public void Run()
    {
        while (_running)
        {
            Step();
            Instructions++;
        }
    }

    // Outside Version 6, execution begins at the header's initial
    // address, inside no routine (§5.5); Version 6 instead calls the
    // main routine (§5.4).
    private void StartExecution()
    {
        _stack.Clear();
        _frames.Clear();
        _frames.Add(new Frame { ReturnAddress = 0, StoreVariable = -1 });

        if (_version == 6)
        {
            Enter(RoutineAddress(_m.ReadWord(Header.InitialPc)), [], 0, -1);
        }
        else
        {
            _pc = _m.ReadWord(Header.InitialPc);
        }
    }

    /// <summary>Stamp the frontend's honest capabilities into the header (§11.1).</summary>
    private void DeclareCapabilities()
    {
        _m.WriteByte(Header.StandardMajor, 1);
        _m.WriteByte(Header.StandardMinor, 1);
        SetFlag2(0x80, _frontend.HasSounds);

        if (_version == 3)
        {
            SetFlag1(0x10, !_frontend.HasStatusLine);
            SetFlag1(0x20, _frontend.HasScreenSplitting);
            SetFlag1(0x08, false);
        }
        else if (_version >= 4)
        {
            _m.WriteByte(Header.Interpreter, 6);
            _m.WriteByte(Header.InterpreterVersion, 'V');
            _m.WriteByte(Header.ScreenLines, Math.Min(_frontend.ScreenLines, 255));
            _m.WriteByte(Header.ScreenColumns, Math.Min(_frontend.ScreenColumns, 255));
            SetFlag1(0x04, _frontend.HasBold);
            SetFlag1(0x08, _frontend.HasItalic);
            SetFlag1(0x10, _frontend.HasFixedPitch);
            SetFlag1(0x80, _frontend.HasTimedInput);

            if (_version >= 5)
            {
                var (fontWidth, fontHeight) = UnitMetrics();
                _m.WriteWord(Header.ScreenWidthUnits, Math.Min(_frontend.ScreenColumns * fontWidth, 0xFFFF));
                _m.WriteWord(Header.ScreenHeightUnits, Math.Min(_frontend.ScreenLines * fontHeight, 0xFFFF));
                // §11's table swaps the two font bytes in Version 6.
                _m.WriteByte(Header.FontWidth, _version == 6 ? fontHeight : fontWidth);
                _m.WriteByte(Header.FontHeight, _version == 6 ? fontWidth : fontHeight);
                SetFlag1(0x01, _frontend.HasColours);
                _m.WriteByte(Header.DefaultBackground, DefaultBackground);
                _m.WriteByte(Header.DefaultForeground, DefaultForeground);
                SetFlag2(0x20, false);

                if (_version == 6)
                {
                    SetFlag2(0x08, false);
                    SetFlag2(0x0100, false);
                    SetFlag1(0x02, _stage?.HasPictures ?? false);
                    SetFlag1(0x20, _frontend.HasSounds);
                }
                else
                {
                    SetFlag2(0x08, false);
                    SetFlag1(0x02, false);
                }
            }
        }
    }

    /// <summary>Re-stamp the §8.4 screen size after the frontend resized; only the size and unit fields move.</summary>
    public void RefreshScreenFields()
    {
        if (_version < 4)
        {
            return;
        }

        _m.WriteByte(Header.ScreenLines, Math.Min(_frontend.ScreenLines, 255));
        _m.WriteByte(Header.ScreenColumns, Math.Min(_frontend.ScreenColumns, 255));

        if (_version >= 5)
        {
            var (fontWidth, fontHeight) = UnitMetrics();
            _m.WriteWord(Header.ScreenWidthUnits, Math.Min(_frontend.ScreenColumns * fontWidth, 0xFFFF));
            _m.WriteWord(Header.ScreenHeightUnits, Math.Min(_frontend.ScreenLines * fontHeight, 0xFFFF));
        }
    }

    // What the status line shows (§8.2): the object the first global
    // names, then score and turns, or the clock in a time game.
    private Status StatusLine()
    {
        var location = ReadVariable(16);
        var text = Zscii.Decode(_m, _objects.ShortNameAddress(location)).Text;
        // Only Versions 1 to 3 have a status line at all, so the flag
        // is read without asking the version again (§8.2.3.2).
        var timeGame = (_m.ReadByte(Header.Flags1) & 0x02) != 0;
        return new Status(text, Signed(ReadVariable(17)), ReadVariable(18), timeGame);
    }

    private void SetFlag1(int mask, bool on)
    {
        var value = _m.ReadByte(Header.Flags1);
        _m.WriteByte(Header.Flags1, on ? value | mask : value & ~mask);
    }

    private void SetFlag2(int mask, bool on)
    {
        var value = _m.ReadWord(Header.Flags2);
        _m.WriteWord(Header.Flags2, on ? value | mask : value & ~mask);
    }

    // One character cell's width and height in units: Version 6 alone
    // measures its screen in real pixels (§8.8.1); every other version
    // keeps one unit per character (§8.4.2).
    private (int Width, int Height) UnitMetrics() =>
        _version == 6 ? (_frontend.FontWidth, _frontend.FontHeight) : (1, 1);

    // A boot-state §8.8 window ledger sized to this glass, built for
    // every version: it is inert outside Version 6.
    private WindowLedger FreshWindows()
    {
        var (fontWidth, fontHeight) = UnitMetrics();
        return new WindowLedger(
            _frontend.ScreenLines * fontHeight,
            _frontend.ScreenColumns * fontWidth,
            DefaultForeground,
            DefaultBackground,
            fontWidth,
            fontHeight);
    }

    private void Step()
    {
        if (!_cache.TryGetValue(_pc, out var instruction))
        {
            instruction = Instruction.Decode(_m, _pc);

            if (_pc >= _m.StaticBase)
            {
                _cache[_pc] = instruction;
            }
        }

        Execute(instruction);
    }

    // Arithmetic and addressing.

    private static int Signed(int word) => (word & 0x8000) != 0 ? word - 0x10000 : word;

    private static int Quotient(int left, int right)
    {
        var magnitude = Math.Abs(left) / Math.Abs(right);
        return (left < 0) == (right < 0) ? magnitude : -magnitude;
    }

    private int RoutineAddress(int packed)
    {
        var scale = _version switch { <= 3 => 2, <= 7 => 4, _ => 8 };
        var address = packed * scale;

        if (_version is 6 or 7)
        {
            address += 8 * _m.ReadWord(Header.RoutinesOffset);
        }

        return address;
    }

    private int StringAddress(int packed)
    {
        var scale = _version switch { <= 3 => 2, <= 7 => 4, _ => 8 };
        var address = packed * scale;

        if (_version is 6 or 7)
        {
            address += 8 * _m.ReadWord(Header.StringsOffset);
        }

        return address;
    }

    private static int TableAddress(int array, int index, int scale) => (array + scale * Signed(index)) & 0xFFFF;

    // Variables and the stack (§6.3).

    private Frame Top => _frames[^1];

    private void Push(int value) => _stack.Add(value & 0xFFFF);

    private int Pop()
    {
        if (_stack.Count <= Top.StackBase)
        {
            throw new ZMachineException("stack underflow: the routine's stack is empty (§6.3.2)");
        }

        var value = _stack[^1];
        _stack.RemoveAt(_stack.Count - 1);
        return value;
    }

    private int Peek()
    {
        if (_stack.Count <= Top.StackBase)
        {
            throw new ZMachineException("stack underflow: the routine's stack is empty (§6.3.2)");
        }

        return _stack[^1];
    }

    private void ReplaceTop(int value)
    {
        if (_stack.Count <= Top.StackBase)
        {
            throw new ZMachineException("stack underflow: the routine's stack is empty (§6.3.2)");
        }

        _stack[^1] = value & 0xFFFF;
    }

    private int ReadVariable(int variable)
    {
        if (variable == 0)
        {
            return Pop();
        }

        if (variable < 16)
        {
            var locals = Top.Locals;

            if (variable > locals.Length)
            {
                throw new ZMachineException($"local variable {variable} does not exist in a routine with {locals.Length} locals (§6.3.1)");
            }

            return locals[variable - 1];
        }

        return _m.ReadWord(_globals + 2 * (variable - 16));
    }

    private void WriteVariable(int variable, int value)
    {
        value &= 0xFFFF;

        if (variable == 0)
        {
            Push(value);
        }
        else if (variable < 16)
        {
            var locals = Top.Locals;

            if (variable > locals.Length)
            {
                throw new ZMachineException($"local variable {variable} does not exist in a routine with {locals.Length} locals (§6.3.1)");
            }

            locals[variable - 1] = value;
        }
        else
        {
            _m.WriteWord(_globals + 2 * (variable - 16), value);
        }
    }

    private int ReadInPlace(int variable) => variable == 0 ? Peek() : ReadVariable(variable);

    private void WriteInPlace(int variable, int value)
    {
        if (variable == 0)
        {
            ReplaceTop(value);
        }
        else
        {
            WriteVariable(variable, value);
        }
    }

    private int Value(Operand operand) =>
        operand.Kind == OperandKind.Variable ? ReadVariable(operand.Value) : operand.Value;

    private int[] Values(Instruction i)
    {
        var values = new int[i.Operands.Length];

        for (var k = 0; k < values.Length; k++)
        {
            values[k] = Value(i.Operands[k]);
        }

        return values;
    }

    private void Store(Instruction i, int value)
    {
        if (i.StoreVariable >= 0)
        {
            WriteVariable(i.StoreVariable, value);
        }
    }

    private void Next(Instruction i) => _pc = i.NextAddress;

    // The §6.6 user stacks: the first word counts the spare slots and
    // doubles as the index of the top value's slot.

    private int UserPull(int stack)
    {
        var spare = _m.ReadWord(stack) + 1;
        _m.WriteWord(stack, spare);
        return _m.ReadWord(stack + 2 * spare);
    }

    // Calls, returns, and branches (§6.4, §4.7).

    private void Call(Instruction i)
    {
        var values = Values(i);
        var packed = values[0];

        if (packed == 0)
        {
            Store(i, FalseValue);
            Next(i);
            return;
        }

        Enter(RoutineAddress(packed), values[1..], i.NextAddress, i.StoreVariable);
    }

    // Enter a routine at its header: locals from the header through
    // Version 4 and zeroed after, arguments laid over them, and a
    // frame remembering where to return and where the result goes.
    private void Enter(int address, int[] arguments, int returnAddress, int storeVariable)
    {
        var count = _m.FetchByte(address);

        if (count > 15)
        {
            throw new ZMachineException(
                $"the byte at ${address:x4} claims {count} locals, but a routine has at most 15 (§5.2); this is probably not a routine address");
        }

        var locals = new int[count];
        int first;

        if (_version <= 4)
        {
            for (var k = 0; k < count; k++)
            {
                locals[k] = _m.FetchWord(address + 1 + 2 * k);
            }

            first = address + 1 + 2 * count;
        }
        else
        {
            first = address + 1;
        }

        for (var k = 0; k < Math.Min(arguments.Length, count); k++)
        {
            locals[k] = arguments[k];
        }

        _frames.Add(new Frame
        {
            ReturnAddress = returnAddress,
            StoreVariable = storeVariable,
            Locals = locals,
            StackBase = _stack.Count,
            ArgCount = arguments.Length,
        });
        _pc = first;
    }

    private void Return(int value)
    {
        if (_frames.Count <= 1)
        {
            throw new ZMachineException("return from the main routine, which has no caller (§6.4.5)");
        }

        var frame = _frames[^1];
        _frames.RemoveAt(_frames.Count - 1);
        _stack.RemoveRange(frame.StackBase, _stack.Count - frame.StackBase);
        _pc = frame.ReturnAddress;

        if (frame.StoreVariable >= 0)
        {
            WriteVariable(frame.StoreVariable, value);
        }
    }

    // Only branching opcodes arrive here, so the rider is always present.
    private void DoBranch(Instruction i, bool condition)
    {
        var branch = i.Branch!.Value;

        if (condition != branch.OnTrue)
        {
            _pc = i.NextAddress;
        }
        else if (branch.ReturnsFalse)
        {
            Return(FalseValue);
        }
        else if (branch.ReturnsTrue)
        {
            Return(TrueValue);
        }
        else
        {
            _pc = branch.Target(i.NextAddress);
        }
    }

    // Output (§7).

    private void Print(string text)
    {
        if (_redirections.Count > 0)
        {
            _redirections[^1].Text.Append(text);
            return;
        }

        if (_storyWindow && (_m.ReadWord(Header.Flags2) & 0x01) != 0)
        {
            throw new ZMachineException($"output stream 2 at ${_pc:x4} is not yet ported");
        }

        if (_screenSelected)
        {
            if (_storyWindow)
            {
                _prints++;
            }

            _frontend.Write(text);
        }
    }

    // Open a stream 3 redirection (§7.1.2.1). In Version 6 a third
    // operand asks for print_form's line shape: zero or positive
    // names a window whose width is the limit, negative a box of that
    // many units, and the wrap counts characters, so the unit width
    // divides by the font width.
    private void RedirectInto(Instruction i, int[] values)
    {
        if (values.Length < 2)
        {
            throw new ZMachineException($"output_stream 3 at ${i.Address:x4} names no table to redirect into (§7.1.2.1)");
        }

        if (_redirections.Count >= RedirectionLimit)
        {
            throw new ZMachineException(
                $"output_stream 3 at ${i.Address:x4} would nest {RedirectionLimit + 1} deep; §7.1.2.1.1 allows {RedirectionLimit} at most");
        }

        int? limit = null;

        if (values.Length > 2 && _version == 6)
        {
            var width = Signed(values[2]);
            var (fontWidth, _) = UnitMetrics();
            limit = width < 0
                ? Math.Max(1, -width / fontWidth)
                : Math.Max(1, _windows.Property(width, WindowLedger.XSize) / fontWidth);
        }

        _redirections.Add(new Redirection(values[1], new StringBuilder(), limit));
    }

    // Close the newest stream 3 table, writing its count (§7.1.2.1),
    // or print_form's line shape when a width was asked for; in
    // Version 6 the widest line lands in the header word at $30.
    private void EndRedirection(Instruction i)
    {
        if (_redirections.Count == 0)
        {
            throw new ZMachineException($"output_stream -3 at ${i.Address:x4}, but stream 3 is not selected (§7.1.2)");
        }

        var (table, text, limit) = _redirections[^1];
        _redirections.RemoveAt(_redirections.Count - 1);
        var content = text.ToString();
        int widest;

        if (limit is null)
        {
            for (var k = 0; k < content.Length; k++)
            {
                _m.WriteByte(table + 2 + k, Zscii.FromChar(_m, content[k]));
            }

            _m.WriteWord(table, content.Length);
            widest = content.Split('\n').Max(part => part.Length);
        }
        else
        {
            widest = WriteFormatted(table, content, limit.Value);
        }

        if (_version == 6)
        {
            var (fontWidth, _) = UnitMetrics();
            _m.WriteWord(TotalWidthAddress, widest * fontWidth);
        }
    }

    // print_form's line shape: each line a word holding its count then
    // the characters, ending at a zero word. A blank line travels as a
    // single space, since the count doubles as the terminator.
    private int WriteFormatted(int table, string text, int limit)
    {
        var position = table;
        var widest = 0;

        foreach (var line in Wrapped(text, limit))
        {
            var carried = line.Length > 0 ? line : " ";
            widest = Math.Max(widest, carried.Length);
            _m.WriteWord(position, carried.Length);
            position += 2;

            foreach (var c in carried)
            {
                _m.WriteByte(position, Zscii.FromChar(_m, c));
                position++;
            }
        }

        _m.WriteWord(position, 0);
        return widest;
    }

    // Greedy word-wrap onto lines at most limit wide (§7.2). Forced
    // new-lines end their lines; a word longer than the whole limit
    // breaks at the limit.
    private static List<string> Wrapped(string text, int limit)
    {
        var lines = new List<string>();

        foreach (var paragraph in text.Split('\n'))
        {
            var current = "";

            foreach (var word in paragraph.Split(' '))
            {
                var candidate = current.Length > 0 ? $"{current} {word}" : word;

                if (candidate.Length <= limit)
                {
                    current = candidate;
                    continue;
                }

                if (current.Length > 0)
                {
                    lines.Add(current);
                }

                var remainder = word;

                while (remainder.Length > limit)
                {
                    lines.Add(remainder[..limit]);
                    remainder = remainder[limit..];
                }

                current = remainder;
            }

            lines.Add(current);
        }

        return lines;
    }

    // Input (§15 read).

    private DictionaryTable Words => _words ??= new DictionaryTable(_m);

    private string NextLine() => _input() ?? throw new EndOfInputException();

    private void Read(Instruction i)
    {
        var values = Values(i);

        if (_version <= 3 && _frontend.HasStatusLine)
        {
            _frontend.ShowStatus(StatusLine());
        }

        var textBuffer = values[0];
        var parseBuffer = values.Length > 1 ? values[1] : 0;
        var counted = _version >= 5;

        if (!counted && parseBuffer == 0)
        {
            throw new ZMachineException(
                $"read at ${i.Address:x4} names no parse buffer, but lexing is not optional before Version 5 (§15 read)");
        }

        var capacity = _m.ReadByte(textBuffer);

        if (capacity < (counted ? 1 : 2))
        {
            throw new ZMachineException(
                $"the text buffer at ${textBuffer:x4} claims a capacity of {capacity}: almost certainly overrun by a previous array (§15 read)");
        }

        _typistReady = -1;
        var (terminated, ticked) = LineOutcome(values);

        // An interrupt that ends the read erases all input (§15 read):
        // a counted buffer reports no letters, a terminated one an
        // empty string, and the lexing sees that emptiness.
        if (terminated)
        {
            if (counted)
            {
                _m.WriteByte(textBuffer + 1, 0);
            }
            else
            {
                WriteText(textBuffer + 1, "", terminate: true);
            }

            if (parseBuffer != 0 || !counted)
            {
                Parse(parseBuffer, "", counted ? 2 : 1, null, keepUnrecognized: false);
            }

            if (i.Info.Stores)
            {
                Store(i, 0);
            }

            Next(i);
            return;
        }

        var preloaded = 0;
        var held = "";

        if (counted)
        {
            preloaded = Math.Min(_m.ReadByte(textBuffer + 1), capacity);
            var kept = new StringBuilder();

            for (var k = 0; k < preloaded; k++)
            {
                kept.Append(Zscii.ToChar(_m, _m.ReadByte(textBuffer + 2 + k)));
            }

            held = kept.ToString();
        }

        var raw = ticked ?? NextLine();
        string line;

        if (counted)
        {
            var typed = raw.ToLowerInvariant();
            typed = typed[..Math.Min(typed.Length, capacity - preloaded)];
            line = held + typed;
            _m.WriteByte(textBuffer + 1, line.Length);
            WriteText(textBuffer + 2 + preloaded, typed, terminate: false);
        }
        else
        {
            line = raw.ToLowerInvariant();
            line = line[..Math.Min(line.Length, capacity - 1)];
            WriteText(textBuffer + 1, line, terminate: true);
        }

        if (parseBuffer != 0 || !counted)
        {
            Parse(parseBuffer, line, counted ? 2 : 1, null, keepUnrecognized: false);
        }

        if (i.Info.Stores)
        {
            Store(i, NewlineCode);
        }

        Next(i);
    }

    private void WriteText(int position, string line, bool terminate)
    {
        foreach (var c in line)
        {
            _m.WriteByte(position, Zscii.FromChar(_m, c));
            position++;
        }

        if (terminate)
        {
            _m.WriteByte(position, 0);
        }
    }

    private void Parse(int parseBuffer, string line, int firstLetter, DictionaryTable? dictionary, bool keepUnrecognized)
    {
        dictionary ??= Words;
        var limit = _m.ReadByte(parseBuffer);

        if (limit < 1)
        {
            throw new ZMachineException(
                $"the parse buffer at ${parseBuffer:x4} claims room for {limit} words: almost certainly overrun by a previous array (§15 read)");
        }

        var words = DictionaryTable.Tokenize(line, dictionary.Separators);

        if (words.Count > limit)
        {
            words = words.Take(limit).ToList();
        }

        _m.WriteByte(parseBuffer + 1, words.Count);
        var block = parseBuffer + 2;

        foreach (var (word, offset) in words)
        {
            var address = dictionary.Lookup(word);

            if (address != 0 || !keepUnrecognized)
            {
                _m.WriteWord(block, address);
                _m.WriteByte(block + 2, word.Length);
                _m.WriteByte(block + 3, offset + firstLetter);
            }

            block += 4;
        }
    }

    // One key from the queue, refilled a line at a time: an empty
    // line is the return key alone, and a longer line queues its
    // characters to be typed one read_char at a time. The queue never
    // invents a return, so a one-character line is exactly one key.
    private int NextKey()
    {
        if (_keySource is not null && _pendingKeys.Count == 0)
        {
            // A key ZSCII has no code for is a key the story cannot
            // hear (§3.8): the wait stands for the next one.
            while (true)
            {
                var key = _keySource(null);

                if (key is not null && Zscii.TryFromChar(_m, key[0], out var code))
                {
                    return code;
                }
            }
        }

        if (_pendingKeys.Count == 0)
        {
            var line = NextLine();

            if (line.Length == 0)
            {
                return NewlineCode;
            }

            foreach (var c in line)
            {
                _pendingKeys.Enqueue(Zscii.FromChar(_m, c));
            }
        }

        return _pendingKeys.Dequeue();
    }

    // The patient typist lets one interval of a timed read elapse
    // (§15 read): the interrupt routine fires once, and a true return
    // ends the read with no input consumed. Before Version 4, and
    // without both a time and a routine, nothing fires.
    private bool TimedOut(int[] values, int timeIndex, bool redisplay = false)
    {
        if (_version < 4)
        {
            return false;
        }

        var time = values.Length > timeIndex ? values[timeIndex] : 0;
        var routine = values.Length > timeIndex + 1 ? values[timeIndex + 1] : 0;

        if (time == 0 || routine == 0)
        {
            return false;
        }

        // §15's remark: an interrupt that printed and let input
        // continue asks for the input line to be shown again.
        if (redisplay)
        {
            _frontend.BeginInput();
        }

        var printed = _prints;
        var terminated = Interrupt(routine) != 0;

        if (redisplay && !terminated && _prints != printed)
        {
            _frontend.ResumeInput();
        }

        return terminated;
    }

    // How a line read's timing plays out before any typing lands: a
    // live session with a wall clock runs a timed read in real time,
    // and the completed line comes back with the verdict; scripted
    // sessions fall through to the patient typist.
    private (bool Terminated, string? Line) LineOutcome(int[] values)
    {
        if (_timedInputSource is not null && _version >= 4 && values.Length > 3 && values[2] != 0 && values[3] != 0)
        {
            var ticked = TickedLine(_timedInputSource, values[2], values[3]);
            return (ticked is null, ticked);
        }

        return (TimedOut(values, 2, redisplay: true), null);
    }

    // A live timed line read: the frontend waits the read's interval
    // at a stretch, each expiry runs the interrupt, and a true return
    // ends the read with the input erased from glass and buffers.
    private string? TickedLine(Func<double, string?> source, int time, int routine)
    {
        var seconds = time / 10.0;

        while (true)
        {
            var line = source(seconds);

            if (line is not null)
            {
                return line;
            }

            _frontend.BeginInput();
            var printed = _prints;

            if (Interrupt(routine) != 0)
            {
                _frontend.AbandonInput();
                return null;
            }

            if (_prints != printed)
            {
                _frontend.ResumeInput();
            }
        }
    }

    // A live timed keystroke read: each expired interval fires the
    // interrupt, a true return ends the read with null, and a key
    // that arrives first beats the clock.
    private int? TimedKeystroke(Func<double?, string?> source, int time, int routine)
    {
        var interval = time / 10.0;

        while (true)
        {
            var key = source(interval);

            if (key is null)
            {
                if (Interrupt(routine) != 0)
                {
                    return null;
                }

                continue;
            }

            if (Zscii.TryFromChar(_m, key[0], out var code))
            {
                return code;
            }
        }
    }

    // Run an interrupt routine to completion through the ordinary call
    // machinery, its result routed through the stack. A story that
    // quits mid-interrupt has certainly ended its input.
    private int Interrupt(int packed)
    {
        var floor = _frames.Count;
        Enter(RoutineAddress(packed), [], _pc, 0);

        while (_running && _frames.Count > floor)
        {
            Step();
        }

        return _running ? Pop() : TrueValue;
    }

    // Save, restore, restart, undo (§6.1).

    // The four §6.1 ingredients frozen: dynamic memory, the pc, and the
    // call chain with each frame's locals and its portion of the stack.
    private SavedState Capture(int pc)
    {
        var frames = new List<SavedFrame>();

        for (var k = 0; k < _frames.Count; k++)
        {
            var frame = _frames[k];
            var top = k + 1 < _frames.Count ? _frames[k + 1].StackBase : _stack.Count;
            frames.Add(new SavedFrame(frame.ReturnAddress, frame.StoreVariable, (int[])frame.Locals.Clone(), frame.ArgCount, _stack[frame.StackBase..top].ToArray()));
        }

        return new SavedState(_m.DynamicSnapshot(), pc, frames);
    }

    // Everything comes back except Flags 2, whose bits belong to the
    // player's session (§6.1.2), and the header is stamped again
    // (§6.1.2.2), since the capture may not be this interpreter's.
    private void Restore(SavedState state)
    {
        var flags2 = _m.ReadWord(Header.Flags2);
        _m.RestoreDynamic(state.Dynamic);
        _m.WriteWord(Header.Flags2, flags2);
        _stack.Clear();
        _frames.Clear();

        foreach (var frame in state.Frames)
        {
            _frames.Add(new Frame
            {
                ReturnAddress = frame.ReturnAddress,
                StoreVariable = frame.StoreVariable,
                Locals = (int[])frame.Locals.Clone(),
                StackBase = _stack.Count,
                ArgCount = frame.ArgumentCount,
            });
            _stack.AddRange(frame.Stack);
        }

        _pc = state.Pc;
        DeclareCapabilities();
    }

    // Pick up at the rider of the save that made us (Quetzal §5.8):
    // through Version 3 the branch data, taken as the successful save
    // it was; from Version 4 the store byte, answered with 2 so the
    // story knows it is being restored rather than saved (§15 save).
    private void ResumeFromSave(int pc)
    {
        if (_version <= 3)
        {
            var (branch, after) = Instruction.ReadBranch(_m, pc);

            if (branch.ReturnsFalse)
            {
                Return(FalseValue);
            }
            else if (branch.ReturnsTrue)
            {
                Return(TrueValue);
            }
            else
            {
                _pc = branch.Target(after);
            }
        }
        else
        {
            WriteVariable(_m.FetchByte(pc), 2);
            _pc = pc + 1;
        }
    }

    // Save answers the §15 way: a branch through Version 3, a stored
    // result from Version 4.
    private void SaveRider(Instruction i, bool success)
    {
        if (_version <= 3)
        {
            DoBranch(i, success);
        }
        else
        {
            Store(i, success ? 1 : 0);
            Next(i);
        }
    }

    // The state of play as a Quetzal file (§15 save, §6.1.1): the pc
    // captured is this instruction's own rider, so a restore resumes
    // there. With operands, a region of memory goes to a game-named
    // auxiliary file instead, storing 1 on success and 0 on failure.
    private void Save(Instruction i)
    {
        if (i.Operands.Length > 0)
        {
            var (table, count, name) = TableForm(i);
            var data = new byte[count];

            for (var k = 0; k < count; k++)
            {
                data[k] = (byte)_m.ReadByte(table + k);
            }

            Store(i, _saves is not null && _saves.WriteAux(AuxName(name), data) ? 1 : 0);
            Next(i);
            return;
        }

        var bytes = Quetzal.Write(Capture(i.OperandsEnd), _m.Pristine);
        SaveRider(i, _saves is not null && _saves.Write(bytes));
    }

    // On success the machine does not continue here: the restored
    // state resumes at the save's rider. Every failure, no bytes, bytes
    // that are not a save, a save of another game, answers as §15
    // says: no branch through Version 3, a stored 0 from Version 4.
    private void RestoreSaved(Instruction i)
    {
        if (i.Operands.Length > 0)
        {
            var (table, count, name) = TableForm(i);
            var found = _saves?.ReadAux(AuxName(name)) ?? [];
            var loaded = Math.Min(found.Length, count);

            for (var k = 0; k < loaded; k++)
            {
                _m.WriteByte(table + k, found[k]);
            }

            Store(i, loaded);
            Next(i);
            return;
        }

        SavedState? state = null;
        var data = _saves?.Read();

        if (data is not null)
        {
            try
            {
                state = Quetzal.Read(data, _m.Pristine);
            }
            catch (ZMachineException)
            {
                state = null;
            }
        }

        if (state is null)
        {
            if (_version > 3)
            {
                Store(i, FalseValue);
            }

            Next(i);
            return;
        }

        Restore(state);
        ResumeFromSave(state.Pc);
    }

    private (int Table, int Count, int Name) TableForm(Instruction i)
    {
        var values = Values(i);

        if (values.Length < 3)
        {
            throw new ZMachineException(
                $"{i.Info.Name} at ${i.Address:x4} has {values.Length} operand(s), but the table form takes a table, a length, and a name (§15 save)");
        }

        return (values[0], values[1], values[2]);
    }

    // A game-supplied filename: a count byte, then text (§15).
    private string AuxName(int address)
    {
        var length = _m.ReadByte(address);
        var name = new StringBuilder();

        for (var k = 0; k < length; k++)
        {
            name.Append(Zscii.ToChar(_m, _m.ReadByte(address + 1 + k)));
        }

        return name.ToString();
    }

    private void Restart()
    {
        var flags2 = _m.ReadWord(Header.Flags2);
        _m.RestoreDynamic(_m.Pristine.AsSpan(0, _m.StaticBase));
        _m.WriteWord(Header.Flags2, (_m.ReadWord(Header.Flags2) & ~0x03) | (flags2 & 0x03));
        DeclareCapabilities();
        _redirections.Clear();
        _screenSelected = true;
        _storyWindow = true;
        _windows = FreshWindows();
        _frontend.EraseWindow(-1);
        StartExecution();
    }

    private bool Verified()
    {
        var scale = _version switch { <= 3 => 2, <= 5 => 4, _ => 8 };
        var story = _m.Pristine;
        var length = ((story[Header.FileLength] << 8) | story[Header.FileLength + 1]) * scale;

        if (length == 0 || length > story.Length)
        {
            length = story.Length;
        }

        var sum = 0;

        for (var k = 0x40; k < length; k++)
        {
            sum = (sum + story[k]) & 0xFFFF;
        }

        return sum == ((story[Header.Checksum] << 8) | story[Header.Checksum + 1]);
    }

    private static ZMachineException Unported(Instruction i) =>
        new($"{i.Info.Name} at ${i.Address:x4} is not yet ported");

    // The Version 6 window opcodes (§8.8), which land in the ledger;
    // the character glass hears only about windows 0 and 1.

    private void SelectWindow(int window)
    {
        if (_version == 6)
        {
            var selected = _windows.Resolve(window);
            _windows.Selected = selected;
            _storyWindow = selected == 0;

            if (_stage is not null)
            {
                _stage.SetWindow(selected);

                if (_aimed.Remove(selected))
                {
                    _stage.SetCursor(
                        _windows.Property(selected, WindowLedger.YCursor),
                        _windows.Property(selected, WindowLedger.XCursor));
                }
            }
            else if (selected <= 1)
            {
                _frontend.SetWindow(selected);
            }
        }
        else
        {
            _storyWindow = window == 0;
            _frontend.SetWindow(window);
        }
    }

    // In Version 6 any of the eight windows may be named, -3 meaning
    // the current one; erasing a window the glass never painted is
    // already true (§8.8.3), so nothing is said about it.
    private void EraseWindow(Instruction i)
    {
        var window = Signed(Value(i.Operands[0]));

        if (_version == 6)
        {
            if (window >= 0 || window == WindowLedger.CurrentWindow)
            {
                var target = _windows.Resolve(window);

                if (target > 1 && _stage is null)
                {
                    Next(i);
                    return;
                }

                window = target;
            }

            if (window == -1)
            {
                _windows.Selected = 0;
            }
        }

        if (window == -1)
        {
            _storyWindow = true;
        }

        _frontend.EraseWindow(window);
        Next(i);
    }

    // The Version 6 split tiles ledger windows 1 and 0 vertically
    // (§8.8.4.1): window 1 takes the top at the given height in units
    // and window 0 the rest.
    private void TileSplit(int height)
    {
        var (_, fontHeight) = UnitMetrics();
        var screenHeight = _frontend.ScreenLines * fontHeight;
        _windows.WriteProperty(1, WindowLedger.YCoordinate, 1);
        _windows.WriteProperty(1, WindowLedger.YSize, height);
        _windows.WriteProperty(0, WindowLedger.YCoordinate, height + 1);
        _windows.WriteProperty(0, WindowLedger.YSize, Math.Max(screenHeight - height, 0));
    }

    // The Version 6 set_cursor forms (§15): a line of -1 turns the
    // blinking cursor off and -2 on, chrome a character glass has no
    // cursor to honour; an ordinary move may name any window,
    // defaulting to the current one, and lands in its properties.
    private void MoveCursor(int[] values)
    {
        var line = values[0];

        if (line is 0xFFFF or 0xFFFE)
        {
            return;
        }

        var column = values[1];
        var window = values.Length > 2 ? values[2] : WindowLedger.CurrentWindow;
        var target = _windows.Resolve(window);
        _windows.WriteProperty(target, WindowLedger.YCursor, line);
        _windows.WriteProperty(target, WindowLedger.XCursor, column);

        if (_stage is null)
        {
            return;
        }

        if (target == _windows.Selected)
        {
            _stage.SetCursor(line, column);
        }
        else
        {
            // Aimed at an unselected window: the move reaches the
            // stage when that window is next selected.
            _aimed.Add(target);
        }
    }

    // A draw or erase call resolved to a screen position. Without
    // pictures the call passes in the conforming quiet: Infocom's own
    // games draw without consulting the header, which the §11.1.4
    // remarks name Zork Zero's Macintosh release for, so a loud halt
    // would stop Arthur at its title card. With pictures, coordinates
    // of zero or omitted mean the current window's cursor, the given
    // ones are relative to the window's own origin (§8.8.3.5), and an
    // invalid picture number is the one thing §15 calls illegal.
    private (int Number, int Line, int Column)? PlacedPicture(Instruction i)
    {
        var values = Values(i);
        var number = values[0];

        if (_stage is null || !_stage.HasPictures)
        {
            return null;
        }

        if (_stage.PictureData(number) is null)
        {
            throw new ZMachineException($"picture {number} is not in the gallery, and §15 calls drawing an invalid picture number illegal");
        }

        var line = values.Length > 1 ? values[1] : 0;
        var column = values.Length > 2 ? values[2] : 0;

        if (line == 0)
        {
            line = _windows.Property(WindowLedger.CurrentWindow, WindowLedger.YCursor);
        }

        if (column == 0)
        {
            column = _windows.Property(WindowLedger.CurrentWindow, WindowLedger.XCursor);
        }

        line += _windows.Property(WindowLedger.CurrentWindow, WindowLedger.YCoordinate) - 1;
        column += _windows.Property(WindowLedger.CurrentWindow, WindowLedger.XCoordinate) - 1;
        return (number, line, column);
    }

    // A window's ledger geometry, sent to a stage that places all eight
    // where §8.8.3.4 says; the character faces keep their two-window
    // mimicry and hear nothing.
    private void PlaceStaged(int window)
    {
        if (_stage is null)
        {
            return;
        }

        var target = _windows.Resolve(window);
        _stage.PlaceWindow(
            target,
            _windows.Property(target, WindowLedger.YCoordinate),
            _windows.Property(target, WindowLedger.XCoordinate),
            _windows.Property(target, WindowLedger.YSize),
            _windows.Property(target, WindowLedger.XSize));
    }

    // The dispatch (§14, §15).

    private void Execute(Instruction i)
    {
        switch (i.Op)
        {
            case Op.Je:
                {
                    var values = Values(i);

                    if (values.Length < 2)
                    {
                        throw new ZMachineException($"je at ${i.Address:x4} has {values.Length} operand(s), but needs at least two (§15)");
                    }

                    var equal = false;

                    for (var k = 1; k < values.Length; k++)
                    {
                        equal |= values[k] == values[0];
                    }

                    DoBranch(i, equal);
                    break;
                }
            case Op.Jl:
                {
                    var left = Signed(Value(i.Operands[0]));
                    var right = Signed(Value(i.Operands[1]));
                    DoBranch(i, left < right);
                    break;
                }
            case Op.Jg:
                {
                    var left = Signed(Value(i.Operands[0]));
                    var right = Signed(Value(i.Operands[1]));
                    DoBranch(i, left > right);
                    break;
                }
            case Op.DecChk:
            case Op.IncChk:
                {
                    var delta = i.Op == Op.IncChk ? 1 : -1;
                    var reference = Value(i.Operands[0]);
                    var comparison = Signed(Value(i.Operands[1]));
                    var stepped = (Signed(ReadInPlace(reference)) + delta) & 0xFFFF;
                    WriteInPlace(reference, stepped);
                    DoBranch(i, delta > 0 ? Signed(stepped) > comparison : Signed(stepped) < comparison);
                    break;
                }
            case Op.Jin:
                {
                    var obj = Value(i.Operands[0]);
                    var parent = Value(i.Operands[1]);
                    DoBranch(i, (obj != 0 ? _objects.Parent(obj) : 0) == parent);
                    break;
                }
            case Op.Test:
                {
                    var bitmap = Value(i.Operands[0]);
                    var flags = Value(i.Operands[1]);
                    DoBranch(i, (bitmap & flags) == flags);
                    break;
                }
            case Op.Or:
                {
                    var left = Value(i.Operands[0]);
                    var right = Value(i.Operands[1]);
                    Store(i, left | right);
                    Next(i);
                    break;
                }
            case Op.And:
                {
                    var left = Value(i.Operands[0]);
                    var right = Value(i.Operands[1]);
                    Store(i, left & right);
                    Next(i);
                    break;
                }
            case Op.TestAttr:
                {
                    var obj = Value(i.Operands[0]);
                    var attribute = Value(i.Operands[1]);
                    DoBranch(i, obj != 0 && _objects.Attribute(obj, attribute));
                    break;
                }
            case Op.SetAttr:
            case Op.ClearAttr:
                {
                    var obj = Value(i.Operands[0]);
                    var attribute = Value(i.Operands[1]);

                    if (obj != 0 && _objects.AttributeExists(attribute))
                    {
                        _objects.SetAttribute(obj, attribute, i.Op == Op.SetAttr);
                    }

                    Next(i);
                    break;
                }
            case Op.Store:
                {
                    var reference = Value(i.Operands[0]);
                    var value = Value(i.Operands[1]);
                    WriteInPlace(reference, value);
                    Next(i);
                    break;
                }
            case Op.InsertObj:
                {
                    var obj = Value(i.Operands[0]);
                    var destination = Value(i.Operands[1]);

                    if (obj != 0 && destination != 0)
                    {
                        _objects.Insert(obj, destination);
                    }

                    Next(i);
                    break;
                }
            case Op.Loadw:
                {
                    var array = Value(i.Operands[0]);
                    var index = Value(i.Operands[1]);
                    Store(i, _m.ReadWord(TableAddress(array, index, 2)));
                    Next(i);
                    break;
                }
            case Op.Loadb:
                {
                    var array = Value(i.Operands[0]);
                    var index = Value(i.Operands[1]);
                    Store(i, _m.ReadByte(TableAddress(array, index, 1)));
                    Next(i);
                    break;
                }
            case Op.GetProp:
                {
                    var obj = Value(i.Operands[0]);
                    var number = Value(i.Operands[1]);
                    Store(i, obj != 0 ? _objects.PropertyValue(obj, number) : 0);
                    Next(i);
                    break;
                }
            case Op.GetPropAddr:
                {
                    var obj = Value(i.Operands[0]);
                    var number = Value(i.Operands[1]);
                    var found = obj != 0 ? _objects.FindProperty(obj, number) : null;
                    Store(i, found?.Data ?? 0);
                    Next(i);
                    break;
                }
            case Op.GetNextProp:
                {
                    var obj = Value(i.Operands[0]);
                    var number = Value(i.Operands[1]);
                    Store(i, obj != 0 ? _objects.NextProperty(obj, number) : 0);
                    Next(i);
                    break;
                }
            case Op.Add:
            case Op.Sub:
            case Op.Mul:
                {
                    var left = Signed(Value(i.Operands[0]));
                    var right = Signed(Value(i.Operands[1]));
                    var result = i.Op switch
                    {
                        Op.Add => left + right,
                        Op.Sub => left - right,
                        _ => left * right,
                    };
                    Store(i, result & 0xFFFF);
                    Next(i);
                    break;
                }
            case Op.Div:
            case Op.Mod:
                {
                    var left = Signed(Value(i.Operands[0]));
                    var right = Signed(Value(i.Operands[1]));

                    if (right == 0)
                    {
                        throw new ZMachineException($"division by zero at ${i.Address:x4} (§2.3.1)");
                    }

                    var quotient = Quotient(left, right);
                    var result = i.Op == Op.Div ? quotient : left - quotient * right;
                    Store(i, result & 0xFFFF);
                    Next(i);
                    break;
                }
            case Op.Call:
            case Op.Call1s:
            case Op.Call1n:
            case Op.Call2s:
            case Op.Call2n:
            case Op.CallVs2:
            case Op.CallVn:
            case Op.CallVn2:
                Call(i);
                break;
            case Op.SetColour:
                // The pair is only read where colours were claimed; a
                // frontend that declared none makes the request a
                // legitimate no-op, its operands untouched.
                if (_frontend.HasColours)
                {
                    var foreground = Signed(Value(i.Operands[0]));
                    var background = Signed(Value(i.Operands[1]));
                    _frontend.SetColour(foreground, background);
                }

                Next(i);
                break;
            case Op.SetTextStyle:
                _frontend.SetStyle(Value(i.Operands[0]));
                Next(i);
                break;
            case Op.BufferMode:
                _frontend.SetBuffering(Value(i.Operands[0]) != 0);
                Next(i);
                break;
            case Op.EraseLine:
                {
                    // Value 1 erases to the end of the line in every
                    // version with the opcode. Any other value does
                    // nothing before Version 6; there it erases that
                    // many units less one rightward (§8.8.5.2), which
                    // only a stage has the pixels to do.
                    var value = Value(i.Operands[0]);

                    if (value == 1)
                    {
                        _frontend.EraseLine();
                    }
                    else if (_stage is not null)
                    {
                        _stage.EraseLine(value - 1);
                    }

                    Next(i);
                    break;
                }
            case Op.ScrollWindow:
                {
                    // Unrelated, §15 notes, to the scrolling attribute:
                    // a stage shifts the window's own rectangle by the
                    // signed amount, and a character glass, whose lower
                    // window scrolls as text flows, has no pixels here
                    // and passes in the conforming quiet.
                    var values = Values(i);
                    _stage?.ScrollWindow(_windows.Resolve(Signed(values[0])), Signed(values[1]));
                    Next(i);
                    break;
                }
            case Op.DrawPicture:
            case Op.ErasePicture:
                {
                    var placed = PlacedPicture(i);

                    if (placed is { } where)
                    {
                        if (i.Op == Op.DrawPicture)
                        {
                            _stage!.DrawPicture(where.Number, where.Line, where.Column);
                        }
                        else
                        {
                            _stage!.ErasePicture(where.Number, where.Line, where.Column);
                        }
                    }

                    Next(i);
                    break;
                }

            case Op.SoundEffect:
                // Presentation a plain stream has nothing to show for:
                // the operands are read, and nothing changes.
                Values(i);
                Next(i);
                break;
            case Op.SetTrueColour:
            case Op.Nop:
            case Op.MouseWindow:
            case Op.PictureTable:
            case Op.ExtPrivate:
            case Op.DrawImage:
                // Passed in the conforming quiet, operands and all.
                Next(i);
                break;
            default:
                // §14.2.1: an opcode of a future Standard, which the
                // tables decode as reserved and nothing above names, is
                // ignored with a warning off-screen, once per number.
                if (_passedReserved.Add(i.Number))
                {
                    Console.Error.WriteLine($"voxam: EXT:{i.Number} is reserved for a future Standard; passed unclaimed (§14.2.1)");
                }

                Next(i);
                break;
            case Op.InputStream:
                {
                    var stream = Value(i.Operands[0]);

                    if (stream == 1)
                    {
                        throw Unported(i);
                    }

                    if (stream != 0)
                    {
                        throw new ZMachineException($"input_stream at ${i.Address:x4} names stream {stream}, but §10.2 defines only 0 and 1");
                    }

                    Next(i);
                    break;
                }
            case Op.Throw:
                {
                    var value = Value(i.Operands[0]);
                    var frame = Value(i.Operands[1]);

                    if (frame > _frames.Count || frame < 1)
                    {
                        throw new ZMachineException(
                            $"cannot throw to stack frame {frame}: the call stack is {_frames.Count} deep, so that catch has already returned (§15 throw)");
                    }

                    while (_frames.Count > frame)
                    {
                        var popped = _frames[^1];
                        _frames.RemoveAt(_frames.Count - 1);
                        _stack.RemoveRange(popped.StackBase, _stack.Count - popped.StackBase);
                    }

                    Return(value);
                    break;
                }
            case Op.Jz:
                DoBranch(i, Value(i.Operands[0]) == 0);
                break;
            case Op.GetSibling:
                {
                    var obj = Value(i.Operands[0]);
                    var sibling = obj != 0 ? _objects.Sibling(obj) : 0;
                    Store(i, sibling);
                    DoBranch(i, sibling != 0);
                    break;
                }
            case Op.GetChild:
                {
                    var obj = Value(i.Operands[0]);
                    var child = obj != 0 ? _objects.Child(obj) : 0;
                    Store(i, child);
                    DoBranch(i, child != 0);
                    break;
                }
            case Op.GetParent:
                {
                    var obj = Value(i.Operands[0]);
                    Store(i, obj != 0 ? _objects.Parent(obj) : 0);
                    Next(i);
                    break;
                }
            case Op.GetPropLen:
                {
                    var address = Value(i.Operands[0]);
                    Store(i, address == 0 ? 0 : _objects.PropertyLengthAt(address));
                    Next(i);
                    break;
                }
            case Op.Inc:
            case Op.Dec:
                {
                    var reference = Value(i.Operands[0]);
                    var value = Signed(ReadInPlace(reference));
                    WriteInPlace(reference, (value + (i.Op == Op.Inc ? 1 : -1)) & 0xFFFF);
                    Next(i);
                    break;
                }
            case Op.PrintAddr:
                {
                    var address = Value(i.Operands[0]);
                    Print(Zscii.Decode(_m, address).Text);
                    Next(i);
                    break;
                }
            case Op.RemoveObj:
                {
                    var obj = Value(i.Operands[0]);

                    if (obj != 0)
                    {
                        _objects.Remove(obj);
                    }

                    Next(i);
                    break;
                }
            case Op.PrintObj:
                {
                    var obj = Value(i.Operands[0]);
                    Print(Zscii.Decode(_m, _objects.ShortNameAddress(obj)).Text);
                    Next(i);
                    break;
                }
            case Op.Ret:
                Return(Value(i.Operands[0]));
                break;
            case Op.Jump:
                {
                    var offset = Signed(Value(i.Operands[0]));
                    _pc = i.NextAddress + offset - 2;
                    break;
                }
            case Op.PrintPaddr:
                {
                    var packed = Value(i.Operands[0]);
                    Print(Zscii.Decode(_m, StringAddress(packed)).Text);
                    Next(i);
                    break;
                }
            case Op.Load:
                {
                    var reference = Value(i.Operands[0]);
                    Store(i, ReadInPlace(reference));
                    Next(i);
                    break;
                }
            case Op.Not:
                Store(i, ~Value(i.Operands[0]) & 0xFFFF);
                Next(i);
                break;
            case Op.Rtrue:
                Return(TrueValue);
                break;
            case Op.Rfalse:
                Return(FalseValue);
                break;
            case Op.Print:
                Print(Zscii.Decode(_m, i.OperandsEnd).Text);
                Next(i);
                break;
            case Op.PrintRet:
                Print(Zscii.Decode(_m, i.OperandsEnd).Text + "\n");
                Return(TrueValue);
                break;
            case Op.Save:
                Save(i);
                break;
            case Op.Restore:
                RestoreSaved(i);
                break;
            case Op.Restart:
                Restart();
                break;
            case Op.RetPopped:
                Return(Pop());
                break;
            case Op.Pop:
                Pop();
                Next(i);
                break;
            case Op.Catch:
                Store(i, _frames.Count);
                Next(i);
                break;
            case Op.Quit:
                _running = false;
                break;
            case Op.NewLine:
                Print("\n");
                Next(i);
                break;
            case Op.ShowStatus:
                if (_frontend.HasStatusLine)
                {
                    _frontend.ShowStatus(StatusLine());
                }

                Next(i);
                break;
            case Op.Verify:
                DoBranch(i, Verified());
                break;
            case Op.Piracy:
                DoBranch(i, true);
                break;
            case Op.MakeMenu:
                // The Flags 2 menus request was cleared at boot; a menu
                // is never successfully built.
                DoBranch(i, false);
                break;
            case Op.Storew:
                {
                    var array = Value(i.Operands[0]);
                    var index = Value(i.Operands[1]);
                    var value = Value(i.Operands[2]);
                    _m.WriteWord(TableAddress(array, index, 2), value);
                    Next(i);
                    break;
                }
            case Op.Storeb:
                {
                    var array = Value(i.Operands[0]);
                    var index = Value(i.Operands[1]);
                    var value = Value(i.Operands[2]);
                    _m.WriteByte(TableAddress(array, index, 1), value & 0xFF);
                    Next(i);
                    break;
                }
            case Op.PutProp:
                {
                    var obj = Value(i.Operands[0]);
                    var number = Value(i.Operands[1]);
                    var value = Value(i.Operands[2]);
                    _objects.PutProperty(obj, number, value);
                    Next(i);
                    break;
                }
            case Op.Sread:
            case Op.Aread:
                Read(i);
                break;
            case Op.PrintChar:
                Print(Zscii.ToChar(_m, Value(i.Operands[0])));
                Next(i);
                break;
            case Op.PrintNum:
                Print(Signed(Value(i.Operands[0])).ToString(CultureInfo.InvariantCulture));
                Next(i);
                break;
            case Op.Random:
                {
                    var value = Signed(Value(i.Operands[0]));
                    int result;

                    if (value > 0)
                    {
                        result = _rng.Roll(value);
                    }
                    else if (value < 0)
                    {
                        _rng.Seed(-value);
                        result = 0;
                    }
                    else
                    {
                        _rng.Randomize();
                        result = 0;
                    }

                    Store(i, result);
                    Next(i);
                    break;
                }
            case Op.Push:
                Push(Value(i.Operands[0]));
                Next(i);
                break;
            case Op.Pull:
                {
                    // Version 6 turns the opcode around: it stores its
                    // result, and an operand names a §6.6 user stack.
                    if (i.Info.Stores)
                    {
                        Store(i, i.Operands.Length > 0 ? UserPull(Value(i.Operands[0])) : Pop());
                        Next(i);
                        break;
                    }

                    var reference = Value(i.Operands[0]);
                    var value = Pop();
                    WriteInPlace(reference, value);
                    Next(i);
                    break;
                }
            case Op.PushStack:
                {
                    var values = Values(i);
                    var stack = values[1];
                    var spare = _m.ReadWord(stack);

                    if (spare != 0)
                    {
                        _m.WriteWord(stack + 2 * spare, values[0]);
                        _m.WriteWord(stack, spare - 1);
                    }

                    DoBranch(i, spare != 0);
                    break;
                }
            case Op.PopStack:
                {
                    var values = Values(i);

                    if (values.Length > 1)
                    {
                        _m.WriteWord(values[1], _m.ReadWord(values[1]) + values[0]);
                    }
                    else
                    {
                        for (var k = 0; k < values[0]; k++)
                        {
                            Pop();
                        }
                    }

                    Next(i);
                    break;
                }
            case Op.SplitWindow:
                {
                    var height = Value(i.Operands[0]);

                    if (_version == 6)
                    {
                        TileSplit(height);
                    }

                    _frontend.SplitWindow(height);
                    Next(i);
                    break;
                }
            case Op.SetWindow:
                SelectWindow(Value(i.Operands[0]));
                Next(i);
                break;
            case Op.EraseWindow:
                EraseWindow(i);
                break;
            case Op.SetCursor:
                {
                    if (_version == 6)
                    {
                        MoveCursor(Values(i));
                    }
                    else
                    {
                        var line = Value(i.Operands[0]);
                        var column = Value(i.Operands[1]);
                        _frontend.SetCursor(line, column);
                    }

                    Next(i);
                    break;
                }
            case Op.GetCursor:
                {
                    // A stage's cursor is the printing truth: text flow
                    // moves it, which the ledger's copy never sees, and
                    // a game that saves the cursor before redrawing its
                    // status line reprints a whole line on a stale
                    // answer. A character glass reads the ledger, the
                    // same place its own set_cursor writes, so its
                    // round trip stays exact.
                    var array = Value(i.Operands[0]);
                    var (line, column) = _version == 6 && _stage is null
                        ? (_windows.Property(WindowLedger.CurrentWindow, WindowLedger.YCursor),
                            _windows.Property(WindowLedger.CurrentWindow, WindowLedger.XCursor))
                        : _frontend.CursorPosition();
                    _m.WriteWord(array, line);
                    _m.WriteWord(array + 2, column);
                    Next(i);
                    break;
                }
            case Op.MoveWindow:
                {
                    var values = Values(i);
                    _windows.Move(values[0], values[1], values[2]);
                    PlaceStaged(values[0]);
                    Next(i);
                    break;
                }
            case Op.WindowSize:
                {
                    var values = Values(i);
                    _windows.Resize(values[0], values[1], values[2]);
                    PlaceStaged(values[0]);
                    Next(i);
                    break;
                }
            case Op.WindowStyle:
                {
                    var values = Values(i);
                    _windows.Restyle(values[0], values[1], values.Length > 2 ? values[2] : 0);
                    Next(i);
                    break;
                }
            case Op.GetWindProp:
                {
                    // On a stage the selected window's cursor properties
                    // answer from the flowed cursor: printing moves it,
                    // and the ledger's copy cannot know (§8.8.3.5).
                    // Shogun centres each title line by reading property
                    // 4 back between prints, and against the stale copy
                    // every line lands on the first one's row.
                    var values = Values(i);
                    var value = _windows.Property(values[0], values[1]);

                    if (_stage is not null
                        && values[1] is WindowLedger.YCursor or WindowLedger.XCursor
                        && _windows.Resolve(values[0]) == _windows.Selected)
                    {
                        var (line, column) = _stage.CursorPosition();
                        value = values[1] == WindowLedger.YCursor ? line : column;
                    }

                    Store(i, value);
                    Next(i);
                    break;
                }
            case Op.PutWindProp:
                {
                    // A staged frontend hears line-count writes: games
                    // set them freely to pace [MORE] (§8.8.3.2.6).
                    var values = Values(i);
                    _windows.WriteProperty(values[0], values[1], values[2]);

                    if (_stage is not null && values[1] == WindowLedger.LineCount)
                    {
                        _stage.SetLineCount(_windows.Resolve(values[0]), Signed(values[2]));
                    }

                    Next(i);
                    break;
                }
            case Op.SetMargins:
                {
                    var values = Values(i);
                    var window = values.Length > 2 ? values[2] : WindowLedger.CurrentWindow;
                    _windows.SetMargins(window, values[0], values[1]);
                    _stage?.SetMargins(_windows.Resolve(window), values[0], values[1]);
                    Next(i);
                    break;
                }
            case Op.PictureData:
                {
                    // Number 0 asks the census: how many pictures hang
                    // and what release the art is. Any other number
                    // asks that picture's size, and a number nothing
                    // answers takes no branch. Without pictures every
                    // number is invalid and the census counts none, as
                    // the cleared header bit promised (§11.1.4).
                    var values = Values(i);

                    if (values[0] == 0)
                    {
                        var (count, release) = _stage?.PictureCensus() ?? (0, 0);
                        _m.WriteWord(values[1], count);
                        _m.WriteWord(values[1] + 2, release);
                        DoBranch(i, count > 0);
                        break;
                    }

                    if (_stage?.PictureData(values[0]) is not { } size)
                    {
                        DoBranch(i, false);
                        break;
                    }

                    _m.WriteWord(values[1], size.Height);
                    _m.WriteWord(values[1] + 2, size.Width);
                    DoBranch(i, true);
                    break;
                }
            case Op.ReadMouse:
                {
                    // A mouse the header declined reports zeros: parked
                    // at nowhere, no buttons down, no menu touched.
                    var array = Value(i.Operands[0]);

                    for (var word = 0; word < 4; word++)
                    {
                        _m.WriteWord(array + 2 * word, 0);
                    }

                    Next(i);
                    break;
                }
            case Op.BufferScreen:
                {
                    var mode = Signed(Value(i.Operands[0]));

                    if (mode is not (0 or 1 or -1))
                    {
                        throw new ZMachineException($"buffer_screen at ${i.Address:x4} asks for mode {mode}, but §8.8.7.1 defines only 0, 1, and -1");
                    }

                    var previous = _screenBuffering;

                    if (mode != -1)
                    {
                        _screenBuffering = mode;
                    }

                    Store(i, previous);
                    Next(i);
                    break;
                }
            case Op.PrintForm:
                {
                    // Each line a word holding its count then the
                    // characters, the sequence ending at a zero word;
                    // each prints followed by a new-line.
                    var position = Value(i.Operands[0]);

                    while (true)
                    {
                        var count = _m.ReadWord(position);

                        if (count == 0)
                        {
                            break;
                        }

                        position += 2;
                        var line = new StringBuilder();

                        for (var k = 0; k < count; k++)
                        {
                            line.Append(Zscii.ToChar(_m, _m.ReadByte(position + k)));
                        }

                        Print(line.Append('\n').ToString());
                        position += count;
                    }

                    Next(i);
                    break;
                }
            case Op.OutputStream:
                {
                    var values = Values(i);
                    var stream = Signed(values[0]);

                    switch (stream)
                    {
                        case 1:
                            _screenSelected = true;
                            break;
                        case -1:
                            _screenSelected = false;
                            break;
                        case 2:
                            throw Unported(i);
                        case -2:
                            SetFlag2(0x01, false);
                            break;
                        case 3:
                            RedirectInto(i, values);
                            break;
                        case -3:
                            EndRedirection(i);
                            break;
                        case 4 or -4 or 0:
                            // Stream 4 records commands to a file this
                            // session does not keep; selecting it changes
                            // nothing, as in the reference without a scribe.
                            break;
                        default:
                            throw new ZMachineException($"output_stream at ${i.Address:x4} names stream {stream}, but §7.1 defines only 1 to 4");
                    }

                    Next(i);
                    break;
                }
            case Op.ReadChar:
                {
                    var values = Values(i);

                    if (values.Length > 0 && values[0] != 1)
                    {
                        throw new ZMachineException(
                            $"read_char at ${i.Address:x4} asks for input device {values[0]}, but the keyboard, 1, is the only device there is (§15 read_char)");
                    }

                    if (_keySource is not null && values.Length > 2 && values[1] != 0 && values[2] != 0)
                    {
                        Store(i, TimedKeystroke(_keySource, values[1], values[2]) ?? 0);
                        Next(i);
                        break;
                    }

                    // Keys already under the fingers beat the clock, and so
                    // does the retry of a read an interrupt just terminated.
                    var ready = _pendingKeys.Count > 0 || _typistReady == i.Address;
                    _typistReady = -1;

                    if (!ready && TimedOut(values, 1))
                    {
                        _typistReady = i.Address;
                        Store(i, 0);
                        Next(i);
                        break;
                    }

                    Store(i, NextKey());
                    Next(i);
                    break;
                }
            case Op.ScanTable:
                {
                    var values = Values(i);
                    var target = values[0];
                    var address = values[1];
                    var count = values[2];
                    var form = values.Length > 3 ? values[3] : 0x82;
                    var width = form & 0x7F;
                    var words = (form & 0x80) != 0;
                    var found = 0;

                    for (var k = 0; k < count; k++)
                    {
                        var entry = words ? _m.ReadWord(address) : _m.ReadByte(address);

                        if (entry == target)
                        {
                            found = address;
                            break;
                        }

                        address += width;
                    }

                    Store(i, found);
                    DoBranch(i, found != 0);
                    break;
                }
            case Op.Tokenise:
                {
                    var values = Values(i);
                    var textBuffer = values[0];
                    var parseBuffer = values[1];
                    var dictionary = values.Length > 2 && values[2] != 0 ? new DictionaryTable(_m, values[2]) : null;
                    var keep = values.Length > 3 && values[3] != 0;
                    var length = _m.ReadByte(textBuffer + 1);
                    var line = new StringBuilder();

                    for (var k = 0; k < length; k++)
                    {
                        line.Append(Zscii.ToChar(_m, _m.ReadByte(textBuffer + 2 + k)));
                    }

                    Parse(parseBuffer, line.ToString(), 2, dictionary, keep);
                    Next(i);
                    break;
                }
            case Op.EncodeText:
                {
                    var values = Values(i);
                    var text = new StringBuilder();

                    for (var k = 0; k < values[1]; k++)
                    {
                        text.Append(Zscii.ToChar(_m, _m.ReadByte(values[0] + values[2] + k)));
                    }

                    var encoded = Zscii.EncodeWord(_m, text.ToString());

                    for (var k = 0; k < encoded.Length; k++)
                    {
                        _m.WriteByte(values[3] + k, encoded[k]);
                    }

                    Next(i);
                    break;
                }
            case Op.CopyTable:
                {
                    var values = Values(i);
                    var first = values[0];
                    var second = values[1];
                    var size = Signed(values[2]);

                    if (second == 0)
                    {
                        for (var k = 0; k < Math.Abs(size); k++)
                        {
                            _m.WriteByte(first + k, 0);
                        }
                    }
                    else if (size < 0 || first > second)
                    {
                        for (var k = 0; k < Math.Abs(size); k++)
                        {
                            _m.WriteByte(second + k, _m.ReadByte(first + k));
                        }
                    }
                    else
                    {
                        for (var k = size - 1; k >= 0; k--)
                        {
                            _m.WriteByte(second + k, _m.ReadByte(first + k));
                        }
                    }

                    Next(i);
                    break;
                }
            case Op.PrintTable:
                {
                    var values = Values(i);
                    var table = values[0];
                    var width = values[1];
                    var height = values.Length > 2 ? values[2] : 1;
                    var skip = values.Length > 3 ? values[3] : 0;
                    var rows = new List<string>();
                    var address = table;

                    for (var row = 0; row < height; row++)
                    {
                        var text = new StringBuilder();

                        for (var column = 0; column < width; column++)
                        {
                            text.Append(Zscii.ToChar(_m, _m.ReadByte(address + column)));
                        }

                        rows.Add(text.ToString());
                        address += width + skip;
                    }

                    if (_redirections.Count > 0 || !_screenSelected)
                    {
                        Print(string.Join("\n", rows));
                    }
                    else
                    {
                        _frontend.WriteRectangle(rows);
                    }

                    Next(i);
                    break;
                }
            case Op.CheckArgCount:
                DoBranch(i, Value(i.Operands[0]) <= Top.ArgCount);
                break;
            case Op.LogShift:
            case Op.ArtShift:
                {
                    var number = Value(i.Operands[0]);
                    var places = Signed(Value(i.Operands[1]));
                    int result;

                    if (places >= 0)
                    {
                        result = (number << places) & 0xFFFF;
                    }
                    else if (i.Op == Op.LogShift)
                    {
                        result = number >> -places;
                    }
                    else
                    {
                        result = (Signed(number) >> -places) & 0xFFFF;
                    }

                    Store(i, result);
                    Next(i);
                    break;
                }
            case Op.SetFont:
                {
                    var font = Value(i.Operands[0]);

                    if (font == 0)
                    {
                        Store(i, _font);
                    }
                    else if (font is 1 or 4 || (font == 3 && _frontend.HasCharacterGraphics))
                    {
                        Store(i, _font);
                        _font = font;
                        _frontend.SetFont(font);
                    }
                    else
                    {
                        Store(i, 0);
                    }

                    Next(i);
                    break;
                }
            case Op.SaveUndo:
                {
                    _undo.AddLast(Capture(i.OperandsEnd));

                    if (_undo.Count > UndoDepth)
                    {
                        _undo.RemoveFirst();
                    }

                    Store(i, 1);
                    Next(i);
                    break;
                }
            case Op.RestoreUndo:
                {
                    if (_undo.Count == 0)
                    {
                        Store(i, 0);
                        Next(i);
                        break;
                    }

                    // Resumes at the save_undo's own store byte, which
                    // then answers 2 (§15 save).
                    var held = _undo.Last!.Value;
                    _undo.RemoveLast();
                    Restore(held);
                    ResumeFromSave(held.Pc);
                    break;
                }
            case Op.PrintUnicode:
                Print(char.ConvertFromUtf32(Value(i.Operands[0])));
                Next(i);
                break;
            case Op.CheckUnicode:
                {
                    var code = Value(i.Operands[0]);
                    Store(i, code is >= 32 and < 0xD800 or > 0xDFFF and <= 0xFFFF ? 3 : 0);
                    Next(i);
                    break;
                }
        }
    }
}
