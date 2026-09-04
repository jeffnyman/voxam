using System.Text;

namespace Voxam.Core;

/// <summary>Text: Z-characters, ZSCII, alphabets and abbreviations (§3).</summary>
public static class Zscii
{
    private const string Alphabet0 = "abcdefghijklmnopqrstuvwxyz";
    private const string Alphabet1 = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";
    private const string Alphabet2 = " \n0123456789.,!?_#'\"/\\-:()";
    private const string Alphabet2V1 = " 0123456789.,!?_#'\"/\\<-:()";

    private const int Space = 0;
    private const int Escape = 6;
    private const int A2Newline = 7;
    private const int FirstAlphabetChar = 6;
    private const int LastShiftLockVersion = 2;

    private const int Delete = 8;
    private const int Newline = 13;
    private const int EscapeKey = 27;
    private const int InputKeysFirst = 129;
    private const int InputKeysLast = 154;
    private const int ExtrasFirst = 155;
    private const int ExtrasLast = 251;

    // The IBM PC's arrow glyphs at ZSCII 24 to 27, which Beyond Zork
    // prints for its compass rose; the reference draws them so.
    private static readonly string[] Arrows = ["↑", "↓", "→", "←"];

    // The default extra characters, ZSCII 155 to 223 (§3.8.5.3).
    private static readonly int[] DefaultExtras =
    [
        0xE4, 0xF6, 0xFC, 0xC4, 0xD6, 0xDC, 0xDF, 0xBB, 0xAB, 0xEB, 0xEF, 0xFF, 0xCB, 0xCF,
        0xE1, 0xE9, 0xED, 0xF3, 0xFA, 0xFD, 0xC1, 0xC9, 0xCD, 0xD3, 0xDA, 0xDD, 0xE0, 0xE8,
        0xEC, 0xF2, 0xF9, 0xC0, 0xC8, 0xCC, 0xD2, 0xD9, 0xE2, 0xEA, 0xEE, 0xF4, 0xFB, 0xC2,
        0xCA, 0xCE, 0xD4, 0xDB, 0xE5, 0xC5, 0xF8, 0xD8, 0xE3, 0xF1, 0xF5, 0xC3, 0xD1, 0xD5,
        0xE6, 0xC6, 0xE7, 0xC7, 0xFE, 0xF0, 0xDE, 0xD0, 0xA3, 0x153, 0x152, 0xA1, 0xBF,
    ];

    /// <summary>The character at an alphabet row and index, 0 to 25 (§3.5).</summary>
    public static string AlphabetChar(Memory m, int row, int index)
    {
        if (m.Version >= 5)
        {
            var table = m.ReadWord(Header.AlphabetTable);

            // Row 2's second entry is always the new-line, which the
            // decoder answers before ever asking here.
            if (table != 0)
            {
                return ToChar(m, m.ReadByte(table + row * 26 + index));
            }
        }

        var alphabet = row switch
        {
            0 => Alphabet0,
            1 => Alphabet1,
            _ => m.Version == 1 ? Alphabet2V1 : Alphabet2,
        };

        return alphabet[index].ToString();
    }

    /// <summary>Decode the string at an address: its text and the address past it.</summary>
    public static (string Text, int End) Decode(Memory m, int address) => Decode(m, address, abbreviated: false);

    // Z-characters are read under the version's rules (§3.2, §3.5).
    // "Current" is the alphabet for the next character and "locked"
    // the one it falls back to: from Version 3 a shift is absolute
    // and lasts one character; in Versions 1 and 2 the shifts rotate
    // relative to the current alphabet, and 4 and 5 rotate the lock.
    // An abbreviation may not itself use an abbreviation (§3.3.1),
    // and a table that breaks the rule can point at itself, so that
    // is refused rather than recursed into.
    private static (string Text, int End) Decode(Memory m, int address, bool abbreviated)
    {
        var version = m.Version;
        var text = new StringBuilder();
        var pos = address;
        var locked = 0;
        var current = 0;
        var tenBit = 0;
        var high = 0;
        var abbreviation = 0;

        while (true)
        {
            var word = m.FetchWord(pos);
            pos += 2;

            for (var slot = 2; slot >= 0; slot--)
            {
                var z = (word >> (5 * slot)) & 0x1F;

                if (tenBit == 1)
                {
                    high = z;
                    tenBit = 2;
                    continue;
                }

                if (tenBit == 2)
                {
                    text.Append(ToChar(m, (high << 5) | z));
                    tenBit = 0;
                    current = locked;
                    continue;
                }

                if (abbreviation != 0)
                {
                    var table = m.ReadWord(Header.Abbreviations);
                    var entry = m.FetchWord(table + 2 * (32 * (abbreviation - 1) + z));
                    text.Append(Decode(m, entry * 2, abbreviated: true).Text);
                    abbreviation = 0;
                    current = locked;
                    continue;
                }

                if (z == Space)
                {
                    text.Append(' ');
                    current = locked;
                }
                else if (version == 1 && z == 1)
                {
                    text.Append('\n');
                    current = locked;
                }
                else if (IsAbbreviation(version, z))
                {
                    if (abbreviated)
                    {
                        throw new ZMachineException(
                            $"the abbreviation at ${address:x4} uses an abbreviation itself, which §3.3.1 forbids");
                    }

                    abbreviation = z;
                }
                else if (z < FirstAlphabetChar)
                {
                    (current, locked) = Shift(version, current, locked, z);
                }
                else if (current == 2 && z == Escape)
                {
                    tenBit = 1;
                }
                else if (current == 2 && version > 1 && z == A2Newline)
                {
                    text.Append('\n');
                    current = locked;
                }
                else
                {
                    text.Append(AlphabetChar(m, current, z - FirstAlphabetChar));
                    current = locked;
                }
            }

            if ((word & 0x8000) != 0)
            {
                return (text.ToString(), pos);
            }
        }
    }

    private static bool IsAbbreviation(int version, int z) =>
        version >= 3 ? z is 1 or 2 or 3 : version == 2 && z == 1;

    private static (int Current, int Locked) Shift(int version, int current, int locked, int z)
    {
        if (version > LastShiftLockVersion)
        {
            return (z - 3, locked);
        }

        var rotated = (current + (z % 2 == 0 ? 1 : 2)) % 3;
        return z is 4 or 5 ? (rotated, rotated) : (rotated, locked);
    }

    /// <summary>The character a ZSCII code prints as (§3.8).</summary>
    public static string ToChar(Memory m, int code)
    {
        // The Version 6 typography codes render as runs of spaces
        // (§3.8.2.3); elsewhere they are not printable at all.
        return code switch
        {
            0 => "",
            9 when m.Version == 6 => "   ",
            11 when m.Version == 6 => "  ",
            Newline => "\n",
            >= 24 and <= 27 => Arrows[code - 24],
            >= 32 and <= 126 => ((char)code).ToString(),
            >= ExtrasFirst and <= ExtrasLast => Extra(m, code),
            _ => throw new ZMachineException($"ZSCII {code} has no character to print (§3.8)"),
        };
    }

    /// <summary>Whether a typed character has a ZSCII code, and which (§3.8).</summary>
    public static bool TryFromChar(Memory m, char c, out int code)
    {
        try
        {
            code = FromChar(m, c);
            return true;
        }
        catch (ZMachineException)
        {
            code = 0;
            return false;
        }
    }

    /// <summary>The ZSCII code a typed character lands as (§3.8).</summary>
    public static int FromChar(Memory m, char c)
    {
        switch (c)
        {
            case '\n':
                return Newline;
            case '\b' or '\x7f':
                return Delete;
            case '\x1b':
                return EscapeKey;
            case >= (char)32 and <= (char)126:
            case >= (char)InputKeysFirst and <= (char)InputKeysLast:
                return c;
        }

        var extras = ExtrasTable(m);

        for (var i = 0; i < extras.Length; i++)
        {
            if (extras[i] == c)
            {
                return ExtrasFirst + i;
            }
        }

        throw new ZMachineException($"the character U+{(int)c:X4} has no ZSCII code (§3.8)");
    }

    /// <summary>Encode a word to dictionary form: 4 bytes through Version 3, 6 after (§3.7).</summary>
    public static byte[] EncodeWord(Memory m, string word)
    {
        var version = m.Version;
        var count = version <= 3 ? 6 : 9;
        var targets = new List<(int Alphabet, int[] Chars)>();
        // Version 1's third alphabet has no new-line entry, so its
        // search starts one place earlier.
        var searchFrom = version == 1 ? 1 : 2;

        // Dictionary form is lower case, as the reference encodes it.
        foreach (var c in word.ToLowerInvariant())
        {
            var text = c.ToString();
            var found = false;

            for (var row = 0; row < 3 && !found; row++)
            {
                for (var index = row == 2 ? searchFrom : 0; index < 26; index++)
                {
                    if (AlphabetChar(m, row, index) == text)
                    {
                        targets.Add((row, [index + FirstAlphabetChar]));
                        found = true;
                        break;
                    }
                }
            }

            if (!found)
            {
                var code = FromChar(m, c);
                targets.Add((2, [Escape, (code >> 5) & 0x1F, code & 0x1F]));
            }
        }

        var codes = version > LastShiftLockVersion ? SingleShifted(targets) : ShiftLocked(targets);

        while (codes.Count < count)
        {
            codes.Add(5);
        }

        return Pack(codes.Take(count).ToList());
    }

    // From Version 3, each character outside the first alphabet takes
    // its own single shift (§3.7).
    private static List<int> SingleShifted(List<(int Alphabet, int[] Chars)> targets)
    {
        var codes = new List<int>();

        foreach (var (alphabet, chars) in targets)
        {
            if (alphabet != 0)
            {
                codes.Add(3 + alphabet);
            }

            codes.AddRange(chars);
        }

        return codes;
    }

    // Versions 1 and 2 shift relative to the current alphabet, and
    // lock instead when the next character shares the alphabet
    // (§3.2.2, §3.7.1).
    private static List<int> ShiftLocked(List<(int Alphabet, int[] Chars)> targets)
    {
        var codes = new List<int>();
        var locked = 0;

        for (var index = 0; index < targets.Count; index++)
        {
            var (alphabet, chars) = targets[index];

            if (alphabet != locked)
            {
                var run = index + 1 < targets.Count && targets[index + 1].Alphabet == alphabet;
                var upward = ((alphabet - locked) % 3 + 3) % 3 == 1;

                if (run)
                {
                    codes.Add(upward ? 4 : 5);
                    locked = alphabet;
                }
                else
                {
                    codes.Add(upward ? 2 : 3);
                }
            }

            codes.AddRange(chars);
        }

        return codes;
    }

    private static byte[] Pack(List<int> codes)
    {
        var words = codes.Count / 3;
        var encoded = new byte[2 * words];

        for (var w = 0; w < words; w++)
        {
            var value = (codes[3 * w] << 10) | (codes[3 * w + 1] << 5) | codes[3 * w + 2];

            if (w == words - 1)
            {
                value |= 0x8000;
            }

            encoded[2 * w] = (byte)(value >> 8);
            encoded[2 * w + 1] = (byte)value;
        }

        return encoded;
    }

    private static string Extra(Memory m, int code)
    {
        var extras = ExtrasTable(m);
        var index = code - ExtrasFirst;

        if (index >= extras.Length)
        {
            throw new ZMachineException($"ZSCII {code} is beyond the extra characters in force (§3.8.5)");
        }

        return char.ConvertFromUtf32(extras[index]);
    }

    private static int[] ExtrasTable(Memory m)
    {
        if (m.Version >= 5)
        {
            var extension = m.ReadWord(Header.Extension);

            if (extension != 0 && m.ReadWord(extension) >= 3)
            {
                var table = m.ReadWord(extension + 6);

                if (table != 0)
                {
                    var count = m.ReadByte(table);
                    var custom = new int[count];

                    for (var i = 0; i < count; i++)
                    {
                        custom[i] = m.ReadWord(table + 1 + 2 * i);
                    }

                    return custom;
                }
            }
        }

        return DefaultExtras;
    }
}
