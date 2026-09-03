using System.Text;

namespace Voxam.Core;

/// <summary>A running Z-Machine (§6.1): memory, call state, and the pc.</summary>
public sealed class Machine
{
    private const int TrueValue = 1;
    private const int FalseValue = 0;
    private const int NewlineCode = 13;
    private const int UndoDepth = 10;

    private sealed class Frame
    {
        public int ReturnAddress;
        public int StoreVariable;
        public int[] Locals = [];
        public int StackBase;
        public int ArgCount;
    }

    private sealed record Snapshot(byte[] Dynamic, int[] Stack, Frame[] Frames, int Pc, int StoreVariable);

    private readonly Memory _m;
    private readonly IFrontend _frontend;
    private readonly Func<string?> _input;
    private readonly Randomizer _rng;
    private readonly int _version;
    private readonly int _globals;
    private readonly ObjectTable _objects;
    private readonly List<int> _stack = [];
    private readonly List<Frame> _frames = [];
    private readonly Dictionary<int, Instruction> _cache = [];
    private readonly List<(int Table, StringBuilder Text)> _redirections = [];
    private readonly Queue<int> _pendingKeys = [];
    private readonly LinkedList<Snapshot> _undo = [];
    private DictionaryTable? _words;
    private int _pc;
    private bool _running = true;
    private bool _screenSelected = true;
    private bool _storyWindow = true;
    private int _font = 1;

    /// <summary>Instructions executed across the whole session.</summary>
    public long Instructions { get; private set; }

    /// <summary>The working memory image, for instruments that read it.</summary>
    public Memory Memory => _m;

    public Machine(byte[] story, IFrontend frontend, Func<string?> input, int? seed)
    {
        _m = new Memory(story);
        _frontend = frontend;
        _input = input;
        _rng = new Randomizer(seed);
        _version = _m.Version;
        _globals = _m.ReadWord(Header.Globals);
        _objects = new ObjectTable(_m);
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

    private void StartExecution()
    {
        _stack.Clear();
        _frames.Clear();
        _frames.Add(new Frame { ReturnAddress = 0, StoreVariable = -1 });

        if (_version == 6)
        {
            throw new ZMachineException("Version 6 is not yet ported");
        }

        _pc = _m.ReadWord(Header.InitialPc);
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
            _m.WriteByte(Header.ScreenLines, _frontend.ScreenLines);
            _m.WriteByte(Header.ScreenColumns, _frontend.ScreenColumns);
            SetFlag1(0x04, _frontend.HasBold);
            SetFlag1(0x08, _frontend.HasItalic);
            SetFlag1(0x10, _frontend.HasFixedPitch);
            SetFlag1(0x80, _frontend.HasTimedInput);

            if (_version >= 5)
            {
                _m.WriteWord(Header.ScreenWidthUnits, _frontend.ScreenColumns);
                _m.WriteWord(Header.ScreenHeightUnits, _frontend.ScreenLines);
                _m.WriteByte(Header.FontWidth, 1);
                _m.WriteByte(Header.FontHeight, 1);
                SetFlag1(0x01, _frontend.HasColours);
                SetFlag2(0x08, false);
                SetFlag2(0x20, false);
                SetFlag2(0x40, false);
            }
        }
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

        var address = RoutineAddress(packed);
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

        var argCount = values.Length - 1;

        for (var k = 0; k < Math.Min(argCount, count); k++)
        {
            locals[k] = values[k + 1];
        }

        _frames.Add(new Frame
        {
            ReturnAddress = i.NextAddress,
            StoreVariable = i.StoreVariable,
            Locals = locals,
            StackBase = _stack.Count,
            ArgCount = argCount,
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
            _frontend.Write(text);
        }
    }

    private void EndRedirection()
    {
        var (table, text) = _redirections[^1];
        _redirections.RemoveAt(_redirections.Count - 1);
        var content = text.ToString();
        _m.WriteWord(table, content.Length);

        for (var k = 0; k < content.Length; k++)
        {
            _m.WriteByte(table + 2 + k, Zscii.FromChar(_m, content[k]));
        }
    }

    // Input (§15 read).

    private DictionaryTable Words => _words ??= new DictionaryTable(_m);

    private string NextLine() => _input() ?? throw new EndOfInputException();

    private void Read(Instruction i)
    {
        var values = Values(i);
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

        var raw = NextLine();
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

    private int NextKey()
    {
        if (_pendingKeys.Count == 0)
        {
            var line = NextLine();

            foreach (var c in line)
            {
                _pendingKeys.Enqueue(Zscii.FromChar(_m, c));
            }

            _pendingKeys.Enqueue(NewlineCode);
        }

        return _pendingKeys.Dequeue();
    }

    // Save, restore, restart, undo (§6.1).

    private Snapshot TakeSnapshot(int storeVariable, int pc) =>
        new(
            _m.DynamicSnapshot(),
            [.. _stack],
            _frames.Select(f => new Frame
            {
                ReturnAddress = f.ReturnAddress,
                StoreVariable = f.StoreVariable,
                Locals = (int[])f.Locals.Clone(),
                StackBase = f.StackBase,
                ArgCount = f.ArgCount,
            }).ToArray(),
            pc,
            storeVariable);

    private void RestoreSnapshot(Snapshot snapshot)
    {
        var flags2 = _m.ReadWord(Header.Flags2);
        _m.RestoreDynamic(snapshot.Dynamic);
        _m.WriteWord(Header.Flags2, (_m.ReadWord(Header.Flags2) & ~0x03) | (flags2 & 0x03));
        DeclareCapabilities();
        _stack.Clear();
        _stack.AddRange(snapshot.Stack);
        _frames.Clear();

        foreach (var f in snapshot.Frames)
        {
            _frames.Add(new Frame
            {
                ReturnAddress = f.ReturnAddress,
                StoreVariable = f.StoreVariable,
                Locals = (int[])f.Locals.Clone(),
                StackBase = f.StackBase,
                ArgCount = f.ArgCount,
            });
        }

        _pc = snapshot.Pc;
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
            case Op.SetTrueColour:
            case Op.SetTextStyle:
            case Op.BufferMode:
            case Op.EraseLine:
            case Op.InputStream:
            case Op.SoundEffect:
            case Op.Nop:
                Values(i);
                Next(i);
                break;
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
            case Op.Restore:
                throw Unported(i);
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
                Next(i);
                break;
            case Op.Verify:
                DoBranch(i, Verified());
                break;
            case Op.Piracy:
                DoBranch(i, true);
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
                Print(Signed(Value(i.Operands[0])).ToString());
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
                    // Version 6's storing form never arrives: the machine
                    // refuses Version 6 stories at the door for now.
                    var reference = Value(i.Operands[0]);
                    var value = Pop();
                    WriteInPlace(reference, value);
                    Next(i);
                    break;
                }
            case Op.SplitWindow:
                _frontend.SplitWindow(Value(i.Operands[0]));
                Next(i);
                break;
            case Op.SetWindow:
                {
                    var window = Value(i.Operands[0]);
                    _frontend.SetWindow(window);
                    _storyWindow = window == 0;
                    Next(i);
                    break;
                }
            case Op.EraseWindow:
                {
                    var window = Signed(Value(i.Operands[0]));
                    _frontend.EraseWindow(window);

                    if (window == -1)
                    {
                        _storyWindow = true;
                    }

                    Next(i);
                    break;
                }
            case Op.SetCursor:
                {
                    var line = Value(i.Operands[0]);
                    var column = Value(i.Operands[1]);
                    _frontend.SetCursor(line, column);
                    Next(i);
                    break;
                }
            case Op.GetCursor:
                {
                    var array = Value(i.Operands[0]);
                    var (line, column) = _frontend.CursorPosition();
                    _m.WriteWord(array, line);
                    _m.WriteWord(array + 2, column);
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
                            if (_redirections.Count >= 16)
                            {
                                throw new ZMachineException("output stream 3 nested more than 16 deep (§7.1.2.1.1)");
                            }

                            _redirections.Add((values[1], new StringBuilder()));
                            break;
                        case -3:
                            if (_redirections.Count > 0)
                            {
                                EndRedirection();
                            }

                            break;
                        case 4 or -4 or 0:
                            // Stream 4 records commands to a file this
                            // session does not keep; selecting it changes
                            // nothing, as in the reference without a scribe.
                            break;
                        default:
                            throw new ZMachineException($"output stream {stream} does not exist (§7.1)");
                    }

                    Next(i);
                    break;
                }
            case Op.ReadChar:
                {
                    Values(i);
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
                    else if (font is 1 or 4)
                    {
                        Store(i, _font);
                        _font = font;
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
                    _undo.AddLast(TakeSnapshot(i.StoreVariable, i.NextAddress));

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

                    var snapshot = _undo.Last!.Value;
                    _undo.RemoveLast();
                    RestoreSnapshot(snapshot);
                    // The save_undo that took this snapshot now answers 2.
                    WriteVariable(snapshot.StoreVariable, 2);
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
            default:
                throw Unported(i);
        }
    }
}
