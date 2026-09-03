using System.Text;

namespace Voxam.Core.Tests.Support;

/// <summary>An operand as a test spells it: a large or small constant, or a variable.</summary>
public readonly record struct Arg(OperandKind Kind, int Value)
{
    public static Arg Small(int value) => new(OperandKind.Small, value);
    public static Arg Large(int value) => new(OperandKind.Large, value);
    public static Arg Var(int variable) => new(OperandKind.Variable, variable);
    public static readonly Arg Stack = Var(0);
}

/// <summary>One object for the builder's object table.</summary>
public sealed record ObjectSpec(
    string Name,
    int Parent = 0,
    int Sibling = 0,
    int Child = 0,
    int[]? Attributes = null,
    (int Number, byte[] Data)[]? Properties = null);

/// <summary>
/// Assembles a tiny story file from parts: a header, a dynamic
/// region holding globals, abbreviations, an object table and a
/// dictionary, and a code region at a fixed static base. Tests
/// write programs as opcode bytes through the emitters below.
/// </summary>
public sealed class StoryBuilder
{
    public const int CodeStart = 0x1000;
    private const string Alphabet2 = " \n0123456789.,!?_#'\"/\\-:()";

    private readonly List<byte> _dynamic = [];
    private readonly List<byte> _code = [];

    public int Version { get; }
    public int Globals { get; }
    public int Abbreviations { get; }
    public int ObjectTable { get; private set; }
    public int DictionaryAddress { get; private set; }
    public int AlphabetTable { get; set; }
    public int ExtensionTable { get; set; }
    public int RoutinesOffset { get; set; }
    public int StringsOffset { get; set; }

    /// <summary>Where execution begins: the code start unless a test emits routines first.</summary>
    public int InitialPc { get; set; } = CodeStart;

    public StoryBuilder(int version = 3)
    {
        Version = version;
        Globals = Alloc(480);
        Abbreviations = Alloc(192);
    }

    /// <summary>The address the next code byte lands at.</summary>
    public int Here => CodeStart + _code.Count;

    public int Scale => Version switch { <= 3 => 2, <= 7 => 4, _ => 8 };

    public int Packed(int address) => (address - (Version is 6 or 7 ? 8 * RoutinesOffset : 0)) / Scale;

    public int PackedString(int address) => (address - (Version is 6 or 7 ? 8 * StringsOffset : 0)) / Scale;

    /// <summary>Pad the code to the version's scale, so what follows has a packed address.</summary>
    public void AlignCode()
    {
        while (Here % Scale != 0)
        {
            _code.Add(0);
        }
    }

    /// <summary>The first address at or past one that a packed address can name.</summary>
    public int Align(int address) => (address + Scale - 1) / Scale * Scale;

    // The dynamic region.

    public int Alloc(int count)
    {
        var address = Header.Size + _dynamic.Count;
        _dynamic.AddRange(new byte[count]);
        return address;
    }

    public int Bytes(params byte[] bytes)
    {
        var address = Header.Size + _dynamic.Count;
        _dynamic.AddRange(bytes);
        return address;
    }

    public int Words(params int[] words)
    {
        var address = Header.Size + _dynamic.Count;

        foreach (var word in words)
        {
            _dynamic.Add((byte)(word >> 8));
            _dynamic.Add((byte)word);
        }

        return address;
    }

    public void SetAbbreviation(int index, string text)
    {
        var address = Header.Size + _dynamic.Count;

        if (address % 2 != 0)
        {
            Alloc(1);
            address++;
        }

        _dynamic.AddRange(ZString(text));
        var slot = Abbreviations + 2 * index - Header.Size;
        _dynamic[slot] = (byte)((address / 2) >> 8);
        _dynamic[slot + 1] = (byte)(address / 2);
    }

    public int Objects(params ObjectSpec[] objects)
    {
        var small = Version <= 3;
        var maxProperties = small ? 31 : 63;
        var entrySize = small ? 9 : 14;
        ObjectTable = Header.Size + _dynamic.Count;
        _dynamic.AddRange(new byte[2 * maxProperties]);
        var entries = Header.Size + _dynamic.Count;
        _dynamic.AddRange(new byte[entrySize * objects.Length]);
        var propertyAddresses = new int[objects.Length];

        for (var index = 0; index < objects.Length; index++)
        {
            propertyAddresses[index] = Header.Size + _dynamic.Count;
            var spec = objects[index];
            var name = ZString(spec.Name);
            _dynamic.Add((byte)(name.Length / 2));
            _dynamic.AddRange(name);

            foreach (var (number, data) in (spec.Properties ?? []).OrderByDescending(p => p.Number))
            {
                if (small)
                {
                    _dynamic.Add((byte)(((data.Length - 1) << 5) | number));
                }
                else if (data.Length <= 2)
                {
                    _dynamic.Add((byte)((data.Length == 2 ? 0x40 : 0) | number));
                }
                else
                {
                    _dynamic.Add((byte)(0x80 | number));
                    _dynamic.Add((byte)(0x80 | (data.Length & 0x3F)));
                }

                _dynamic.AddRange(data);
            }

            _dynamic.Add(0);
        }

        for (var index = 0; index < objects.Length; index++)
        {
            var spec = objects[index];
            var at = entries + index * entrySize - Header.Size;

            foreach (var attribute in spec.Attributes ?? [])
            {
                _dynamic[at + attribute / 8] |= (byte)(0x80 >> (attribute % 8));
            }

            if (small)
            {
                _dynamic[at + 4] = (byte)spec.Parent;
                _dynamic[at + 5] = (byte)spec.Sibling;
                _dynamic[at + 6] = (byte)spec.Child;
                _dynamic[at + 7] = (byte)(propertyAddresses[index] >> 8);
                _dynamic[at + 8] = (byte)propertyAddresses[index];
            }
            else
            {
                _dynamic[at + 6] = (byte)(spec.Parent >> 8);
                _dynamic[at + 7] = (byte)spec.Parent;
                _dynamic[at + 8] = (byte)(spec.Sibling >> 8);
                _dynamic[at + 9] = (byte)spec.Sibling;
                _dynamic[at + 10] = (byte)(spec.Child >> 8);
                _dynamic[at + 11] = (byte)spec.Child;
                _dynamic[at + 12] = (byte)(propertyAddresses[index] >> 8);
                _dynamic[at + 13] = (byte)propertyAddresses[index];
            }
        }

        return ObjectTable;
    }

    public void PropertyDefault(int number, int value)
    {
        var slot = ObjectTable + 2 * (number - 1) - Header.Size;
        _dynamic[slot] = (byte)(value >> 8);
        _dynamic[slot + 1] = (byte)value;
    }

    public int Dictionary(string separators, params string[] words) => Dictionary(separators, words.Length, words);

    public int Dictionary(string separators, int declaredCount, params string[] words)
    {
        DictionaryAddress = Header.Size + _dynamic.Count;
        _dynamic.Add((byte)separators.Length);
        _dynamic.AddRange(Encoding.ASCII.GetBytes(separators));
        var textBytes = Version <= 3 ? 4 : 6;
        _dynamic.Add((byte)(textBytes + 3));
        _dynamic.Add((byte)(declaredCount >> 8));
        _dynamic.Add((byte)declaredCount);

        foreach (var word in words)
        {
            _dynamic.AddRange(EncodeWord(Version, word));
            _dynamic.AddRange(new byte[3]);
        }

        return DictionaryAddress;
    }

    // The code region.

    public int Routine(int locals, params int[] initial)
    {
        // Routines live at packed addresses, so the header is aligned
        // to the version's scale.
        AlignCode();
        var address = Here;
        _code.Add((byte)locals);

        if (Version <= 4)
        {
            for (var k = 0; k < locals; k++)
            {
                var value = k < initial.Length ? initial[k] : 0;
                _code.Add((byte)(value >> 8));
                _code.Add((byte)value);
            }
        }

        return address;
    }

    public void Raw(params byte[] bytes) => _code.AddRange(bytes);

    public void Op0(int opcode) => _code.Add((byte)(0xB0 | opcode));

    public void Op1(int opcode, Arg operand)
    {
        _code.Add((byte)(0x80 | ((int)operand.Kind << 4) | opcode));
        Operand(operand);
    }

    public void Op2(int opcode, Arg first, Arg second)
    {
        if (first.Kind == OperandKind.Large || second.Kind == OperandKind.Large)
        {
            Op2Var(opcode, first, second);
            return;
        }

        var firstBit = first.Kind == OperandKind.Variable ? 0x40 : 0;
        var secondBit = second.Kind == OperandKind.Variable ? 0x20 : 0;
        _code.Add((byte)(firstBit | secondBit | opcode));
        Operand(first);
        Operand(second);
    }

    public void Op2Var(int opcode, params Arg[] operands)
    {
        _code.Add((byte)(0xC0 | opcode));
        Types(operands, 4);
        Operands(operands);
    }

    public void OpVar(int opcode, params Arg[] operands)
    {
        _code.Add((byte)(0xE0 | opcode));
        Types(operands, opcode is 0x0C or 0x1A ? 8 : 4);
        Operands(operands);
    }

    public void Ext(int opcode, params Arg[] operands)
    {
        _code.Add(0xBE);
        _code.Add((byte)opcode);
        Types(operands, 4);
        Operands(operands);
    }

    public void Store(int variable) => _code.Add((byte)variable);

    public void Branch(bool onTrue, int offset)
    {
        var sense = onTrue ? 0x80 : 0;

        if (offset is >= 0 and < 64)
        {
            _code.Add((byte)(sense | 0x40 | offset));
            return;
        }

        var value = offset & 0x3FFF;
        _code.Add((byte)(sense | (value >> 8)));
        _code.Add((byte)value);
    }

    public void Text(string text) => _code.AddRange(ZString(text));

    public void Print(string text)
    {
        Op0(0x2);
        Text(text);
    }

    public void PrintRet(string text)
    {
        Op0(0x3);
        Text(text);
    }

    public void NewLine() => Op0(0xB);

    public void Quit() => Op0(0xA);

    public void Call(int routine, int store, params Arg[] arguments)
    {
        OpVar(0x00, [Arg.Large(Packed(routine)), .. arguments]);
        Store(store);
    }

    private void Types(Arg[] operands, int slots)
    {
        var bytes = slots / 4;
        var kinds = new int[slots];

        for (var k = 0; k < slots; k++)
        {
            kinds[k] = k < operands.Length ? (int)operands[k].Kind : 3;
        }

        for (var b = 0; b < bytes; b++)
        {
            var value = 0;

            for (var k = 0; k < 4; k++)
            {
                value |= kinds[b * 4 + k] << (6 - 2 * k);
            }

            _code.Add((byte)value);
        }
    }

    private void Operands(Arg[] operands)
    {
        foreach (var operand in operands)
        {
            Operand(operand);
        }
    }

    private void Operand(Arg operand)
    {
        if (operand.Kind == OperandKind.Large)
        {
            _code.Add((byte)(operand.Value >> 8));
        }

        _code.Add((byte)operand.Value);
    }

    // Assembly.

    public byte[] Build()
    {
        if (ObjectTable == 0)
        {
            Objects();
        }

        if (DictionaryAddress == 0)
        {
            Dictionary("");
        }

        var dynamicEnd = Header.Size + _dynamic.Count;

        if (dynamicEnd > CodeStart)
        {
            throw new InvalidOperationException($"the dynamic region runs to ${dynamicEnd:x4}, past the code at ${CodeStart:x4}");
        }

        // Padded to a multiple of eight, so the declared length covers
        // every byte whatever the version's scale.
        var length = CodeStart + _code.Count;
        var story = new byte[(length + 7) / 8 * 8];
        _dynamic.CopyTo(story, Header.Size);
        _code.CopyTo(story, CodeStart);

        story[Header.Version] = (byte)Version;
        Word(story, Header.Release, 1);
        Word(story, Header.HighBase, CodeStart);
        Word(story, Header.InitialPc, InitialPc);
        Word(story, Header.Dictionary, DictionaryAddress);
        Word(story, Header.ObjectTable, ObjectTable);
        Word(story, Header.Globals, Globals);
        Word(story, Header.StaticBase, CodeStart);
        Encoding.ASCII.GetBytes("TESTSR").CopyTo(story, Header.Serial);
        Word(story, Header.Abbreviations, Abbreviations);
        Word(story, Header.FileLength, story.Length / (Version <= 3 ? 2 : Version <= 5 ? 4 : 8));
        Word(story, Header.AlphabetTable, AlphabetTable);
        Word(story, Header.RoutinesOffset, RoutinesOffset);
        Word(story, Header.StringsOffset, StringsOffset);
        Word(story, Header.Extension, ExtensionTable);

        var sum = 0;

        for (var k = Header.Size; k < story.Length; k++)
        {
            sum = (sum + story[k]) & 0xFFFF;
        }

        Word(story, Header.Checksum, sum);
        return story;
    }

    public static void Word(byte[] story, int address, int value)
    {
        story[address] = (byte)(value >> 8);
        story[address + 1] = (byte)value;
    }

    /// <summary>Encode text as a Z-string in the standard alphabets, top bit on the last word.</summary>
    public static byte[] ZString(string text)
    {
        var codes = new List<int>();

        foreach (var c in text)
        {
            if (c == ' ')
            {
                codes.Add(0);
            }
            else if (c is >= 'a' and <= 'z')
            {
                codes.Add(6 + (c - 'a'));
            }
            else if (c is >= 'A' and <= 'Z')
            {
                codes.Add(4);
                codes.Add(6 + (c - 'A'));
            }
            else if (Alphabet2.IndexOf(c, StringComparison.Ordinal) is var index and >= 1)
            {
                codes.Add(5);
                codes.Add(6 + index);
            }
            else
            {
                codes.Add(5);
                codes.Add(6);
                codes.Add(c >> 5);
                codes.Add(c & 0x1F);
            }
        }

        while (codes.Count == 0 || codes.Count % 3 != 0)
        {
            codes.Add(5);
        }

        return Pack(codes);
    }

    /// <summary>Encode a dictionary word: six Z-characters through Version 3, nine after.</summary>
    public static byte[] EncodeWord(int version, string word)
    {
        var count = version <= 3 ? 6 : 9;
        var codes = new List<int>();

        foreach (var c in word.ToLowerInvariant())
        {
            if (codes.Count >= count)
            {
                break;
            }

            if (c is >= 'a' and <= 'z')
            {
                codes.Add(6 + (c - 'a'));
            }
            else if (c is >= 'A' and <= 'Z')
            {
                codes.Add(4);
                codes.Add(6 + (c - 'A'));
            }
            else if (Alphabet2.IndexOf(c, StringComparison.Ordinal) is var index and >= 2)
            {
                codes.Add(5);
                codes.Add(6 + index);
            }
            else
            {
                codes.Add(5);
                codes.Add(6);
                codes.Add(c >> 5);
                codes.Add(c & 0x1F);
            }
        }

        while (codes.Count < count)
        {
            codes.Add(5);
        }

        return Pack(codes.Take(count).ToList());
    }

    private static byte[] Pack(List<int> codes)
    {
        var words = codes.Count / 3;
        var bytes = new byte[2 * words];

        for (var w = 0; w < words; w++)
        {
            var value = (codes[3 * w] << 10) | (codes[3 * w + 1] << 5) | codes[3 * w + 2];

            if (w == words - 1)
            {
                value |= 0x8000;
            }

            bytes[2 * w] = (byte)(value >> 8);
            bytes[2 * w + 1] = (byte)value;
        }

        return bytes;
    }
}

/// <summary>Runs a built story to completion under a plain frontend, keeping what it printed.</summary>
public static class Session
{
    public static (string Output, Machine Machine) Run(StoryBuilder builder, IEnumerable<string>? input = null, int? seed = null)
    {
        var output = new StringBuilder();
        var lines = (input ?? []).GetEnumerator();
        var machine = new Machine(builder.Build(), new PlainFrontend(text => output.Append(text)), () => lines.MoveNext() ? lines.Current : null, seed);
        machine.Run();
        return (output.ToString(), machine);
    }

    public static T Fails<T>(StoryBuilder builder, IEnumerable<string>? input = null) where T : Exception
    {
        var lines = (input ?? []).GetEnumerator();
        var machine = new Machine(builder.Build(), new PlainFrontend(_ => { }), () => lines.MoveNext() ? lines.Current : null, 1);
        return Assert.Throws<T>(machine.Run);
    }
}
