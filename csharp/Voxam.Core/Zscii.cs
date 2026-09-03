using System.Text;

namespace Voxam.Core;

/// <summary>Text: Z-characters, ZSCII, alphabets and abbreviations (§3).</summary>
public static class Zscii
{
    private const string Alphabet0 = "abcdefghijklmnopqrstuvwxyz";
    private const string Alphabet1 = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";
    private const string Alphabet2 = " \n0123456789.,!?_#'\"/\\-:()";
    private const string Alphabet2V1 = " 0123456789.,!?_#'\"/\\<-:()";

    private const int Newline = 13;
    private const int ExtrasFirst = 155;
    private const int ExtrasLast = 251;

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

    // An abbreviation may not itself use an abbreviation (§3.3.1). A
    // table that breaks the rule can point at itself, and refusing it
    // is what keeps a broken story from recursing without end.
    private static (string Text, int End) Decode(Memory m, int address, bool abbreviated)
    {
        var version = m.Version;
        var text = new StringBuilder();
        var pos = address;
        var alphabet = 0;
        var shift = -1;
        var lockedFrom = 0;
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
                    continue;
                }

                if (abbreviation != 0)
                {
                    if (abbreviated)
                    {
                        throw new ZMachineException(
                            $"the abbreviation at ${address:x4} uses an abbreviation itself, which §3.3.1 forbids");
                    }

                    var table = m.ReadWord(Header.Abbreviations);
                    var entry = m.FetchWord(table + 2 * (32 * (abbreviation - 1) + z));
                    text.Append(Decode(m, entry * 2, abbreviated: true).Text);
                    abbreviation = 0;
                    continue;
                }

                switch (z)
                {
                    case 0:
                        text.Append(' ');
                        break;
                    case 1 when version >= 2:
                        abbreviation = 1;
                        break;
                    case 1:
                        text.Append('\n');
                        break;
                    case 2 or 3 when version >= 3:
                        abbreviation = z;
                        break;
                    case 2 or 3:
                        // Versions 1 and 2: a temporary shift up or down.
                        shift = (alphabet + (z == 2 ? 1 : 2)) % 3;
                        break;
                    case 4 or 5 when version >= 3:
                        shift = z - 3;
                        break;
                    case 4 or 5:
                        // Versions 1 and 2: a shift lock.
                        alphabet = (alphabet + (z == 4 ? 1 : 2)) % 3;
                        lockedFrom = alphabet;
                        break;
                    default:
                        {
                            var row = shift >= 0 ? shift : alphabet;
                            shift = -1;

                            if (row == 2 && z == 6)
                            {
                                tenBit = 1;
                            }
                            else if (row == 2 && z == 7 && version >= 2)
                            {
                                text.Append('\n');
                            }
                            else
                            {
                                text.Append(AlphabetChar(m, row, z - 6));
                            }

                            break;
                        }
                }

                if (z >= 6 && version < 3)
                {
                    alphabet = lockedFrom;
                }
            }

            if ((word & 0x8000) != 0)
            {
                return (text.ToString(), pos);
            }
        }
    }

    /// <summary>The character a ZSCII code prints as (§3.8).</summary>
    public static string ToChar(Memory m, int code)
    {
        return code switch
        {
            0 => "",
            9 => "\t",
            11 => " ",
            Newline => "\n",
            >= 32 and <= 126 => ((char)code).ToString(),
            >= ExtrasFirst and <= ExtrasLast => Extra(m, code),
            _ => throw new ZMachineException($"ZSCII {code} has no character to print (§3.8)"),
        };
    }

    /// <summary>The ZSCII code a typed character lands as (§3.8).</summary>
    public static int FromChar(Memory m, char c)
    {
        if (c == '\n')
        {
            return Newline;
        }

        if (c is >= (char)32 and <= (char)126)
        {
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
        var count = m.Version <= 3 ? 6 : 9;
        var codes = new List<int>();

        // Dictionary form is lower case, as the reference encodes it.
        foreach (var c in word.ToLowerInvariant())
        {
            if (codes.Count >= count)
            {
                break;
            }

            var row = -1;
            var index = -1;

            for (var r = 0; r < 3 && row < 0; r++)
            {
                for (var i = 0; i < 26; i++)
                {
                    if (r == 2 && i < 2)
                    {
                        continue;
                    }

                    if (AlphabetChar(m, r, i) == c.ToString())
                    {
                        row = r;
                        index = i;
                        break;
                    }
                }
            }

            if (row == 0)
            {
                codes.Add(index + 6);
            }
            else if (row > 0)
            {
                codes.Add(row + 3);
                codes.Add(index + 6);
            }
            else
            {
                var code = FromChar(m, c);
                codes.Add(5);
                codes.Add(6);
                codes.Add(code >> 5);
                codes.Add(code & 0x1F);
            }
        }

        while (codes.Count < count)
        {
            codes.Add(5);
        }

        var encoded = new byte[count / 3 * 2];

        for (var w = 0; w < count / 3; w++)
        {
            var value = (codes[3 * w] << 10) | (codes[3 * w + 1] << 5) | codes[3 * w + 2];

            if (w == count / 3 - 1)
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
