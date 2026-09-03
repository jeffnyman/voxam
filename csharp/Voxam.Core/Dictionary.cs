namespace Voxam.Core;

/// <summary>A dictionary table and lexical analysis (§13).</summary>
public sealed class DictionaryTable
{
    private readonly Memory _m;
    private readonly int _entryLength;
    private readonly int _count;
    private readonly int _entries;
    private readonly int _textBytes;

    public HashSet<char> Separators { get; } = [];

    public DictionaryTable(Memory m, int? baseAddress = null)
    {
        _m = m;
        var address = baseAddress ?? m.ReadWord(Header.Dictionary);
        var separatorCount = m.ReadByte(address);

        for (var i = 0; i < separatorCount; i++)
        {
            var text = Zscii.ToChar(m, m.ReadByte(address + 1 + i));

            if (text.Length == 1)
            {
                Separators.Add(text[0]);
            }
        }

        _entryLength = m.ReadByte(address + 1 + separatorCount);
        var count = m.ReadWord(address + 2 + separatorCount);

        if ((count & 0x8000) != 0)
        {
            count = 0x10000 - count;
        }

        _count = count;
        _entries = address + 4 + separatorCount;
        _textBytes = m.Version <= 3 ? 4 : 6;
    }

    /// <summary>A typed word's entry address, or 0 (§13.6.2).</summary>
    public int Lookup(string word)
    {
        var target = Zscii.EncodeWord(_m, word);

        for (var index = 0; index < _count; index++)
        {
            var address = _entries + index * _entryLength;
            var matched = true;

            for (var offset = 0; offset < _textBytes; offset++)
            {
                if (_m.ReadByte(address + offset) != target[offset])
                {
                    matched = false;
                    break;
                }
            }

            if (matched)
            {
                return address;
            }
        }

        return 0;
    }

    /// <summary>Split typed text into words with their offsets (§13.6.1).</summary>
    public static List<(string Word, int Offset)> Tokenize(string text, HashSet<char> separators)
    {
        var words = new List<(string, int)>();
        var start = -1;

        for (var position = 0; position < text.Length; position++)
        {
            var c = text[position];

            if (c == ' ' || separators.Contains(c))
            {
                if (start >= 0)
                {
                    words.Add((text[start..position], start));
                    start = -1;
                }

                if (c != ' ')
                {
                    words.Add((c.ToString(), position));
                }
            }
            else if (start < 0)
            {
                start = position;
            }
        }

        if (start >= 0)
        {
            words.Add((text[start..], start));
        }

        return words;
    }
}
