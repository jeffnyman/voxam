using Voxam.Core.Tests.Support;

namespace Voxam.Core.Tests;

public class ZsciiTests
{
    private static Memory Story(int version = 3, Action<StoryBuilder>? shape = null)
    {
        var builder = new StoryBuilder(version);
        shape?.Invoke(builder);
        builder.Quit();
        return new Memory(builder.Build());
    }

    private static string Decoded(string text, int version = 3)
    {
        var builder = new StoryBuilder(version);
        var address = builder.Bytes(StoryBuilder.ZString(text));
        builder.Quit();
        return Zscii.Decode(new Memory(builder.Build()), address).Text;
    }

    [Theory]
    [InlineData("hello world")]
    [InlineData("Hello, World!")]
    [InlineData("a1-b: (x) \"q\" #_/\\'?")]
    [InlineData("line one\nline two")]
    [InlineData("")]
    public void TextRoundTripsThroughTheStandardAlphabets(string text)
    {
        Assert.Equal(text, Decoded(text));
    }

    [Fact]
    public void TenBitEscapesCarryAnyZsciiCode()
    {
        Assert.Equal("~", Decoded("~"));
        // Z-characters 5 6 4 27 spell ZSCII 155, the first extra character.
        var builder = new StoryBuilder();
        var address = builder.Bytes(0x14, 0xC4, 0xEC, 0xA5);
        builder.Quit();
        Assert.Equal("ä", Zscii.Decode(new Memory(builder.Build()), address).Text);
    }

    [Fact]
    public void DecodeReportsTheAddressPastTheString()
    {
        var builder = new StoryBuilder();
        var address = builder.Bytes(StoryBuilder.ZString("abcdef"));
        builder.Quit();
        var memory = new Memory(builder.Build());
        Assert.Equal(address + 4, Zscii.Decode(memory, address).End);
    }

    [Fact]
    public void AbbreviationsExpandFromTheTable()
    {
        var builder = new StoryBuilder();
        builder.SetAbbreviation(0, "the ");
        builder.SetAbbreviation(32, "West ");
        builder.SetAbbreviation(64, "of ");
        // Z-characters 1, 2 and 3 name the three abbreviation rows:
        // 2 0, 3 0, 1 0, then 'h' 'o' and padding.
        var address = builder.Bytes(0x08, 0x03, 0x00, 0x20, 0xB6, 0x85);
        builder.Quit();
        var memory = new Memory(builder.Build());
        Assert.Equal("West of the ho", Zscii.Decode(memory, address).Text);
    }

    // An abbreviation using an abbreviation is forbidden (§3.3.1), and
    // a table whose entries are all zero would otherwise decode the
    // header as an abbreviation forever.
    [Fact]
    public void AnAbbreviationInsideAnAbbreviationIsRefused()
    {
        var builder = new StoryBuilder();
        builder.SetAbbreviation(0, "x");
        var address = builder.Bytes(0x04, 0x00, 0x80, 0x00);
        builder.Quit();
        var story = builder.Build();
        // Point abbreviation 0 at a string that itself uses abbreviation 0.
        var slot = (story[Header.Abbreviations] << 8) | story[Header.Abbreviations + 1];
        StoryBuilder.Word(story, slot, address / 2);
        var error = Assert.Throws<ZMachineException>(() => Zscii.Decode(new Memory(story), address));
        Assert.Contains("uses an abbreviation itself", error.Message, StringComparison.Ordinal);
    }

    // In Version 1, Z-character 1 is a new-line, 4 and 5 lock the
    // alphabet up and down, 2 and 3 shift the next character only,
    // and the third alphabet has '<' where later versions put the
    // new-line. The Z-characters here are 4 6 6, 5 6 1, 2 6 6, 5 27 5,
    // 3 8 5: the last shifts down from the locked first alphabet.
    [Fact]
    public void VersionOneUsesShiftLocksAndItsOwnAlphabet()
    {
        var builder = new StoryBuilder(1);
        var address = builder.Bytes(0x10, 0xC6, 0x14, 0xC1, 0x08, 0xC6, 0x17, 0x65, 0x8D, 0x05);
        builder.Quit();
        var memory = new Memory(builder.Build());
        Assert.Equal("AAa\nAa<c", Zscii.Decode(memory, address).Text);
    }

    [Fact]
    public void ACustomAlphabetTableIsHonored()
    {
        var builder = new StoryBuilder(5);
        var rows = new byte[78];

        for (var k = 0; k < 26; k++)
        {
            rows[k] = (byte)('z' - k);
            rows[26 + k] = (byte)('Z' - k);
            rows[52 + k] = (byte)('0' + k % 10);
        }

        builder.AlphabetTable = builder.Bytes(rows);
        var address = builder.Bytes(StoryBuilder.ZString("abc\nA"));
        builder.Quit();
        var memory = new Memory(builder.Build());
        Assert.Equal("zyx\nZ", Zscii.Decode(memory, address).Text);
    }

    [Fact]
    public void ZsciiCodesPrintAsTheStandardSays()
    {
        var memory = Story();
        Assert.Equal("", Zscii.ToChar(memory, 0));
        Assert.Throws<ZMachineException>(() => Zscii.ToChar(memory, 9));
        Assert.Throws<ZMachineException>(() => Zscii.ToChar(memory, 11));
        var typography = Story(6);
        Assert.Equal("   ", Zscii.ToChar(typography, 9));
        Assert.Equal("  ", Zscii.ToChar(typography, 11));
        Assert.Equal("\n", Zscii.ToChar(memory, 13));
        Assert.Equal("A", Zscii.ToChar(memory, 65));
        Assert.Equal("ä", Zscii.ToChar(memory, 155));
        Assert.Equal("¿", Zscii.ToChar(memory, 223));
        Assert.Equal("Œ", Zscii.ToChar(memory, 221));
        var beyond = Assert.Throws<ZMachineException>(() => Zscii.ToChar(memory, 224));
        Assert.Contains("beyond the extra characters", beyond.Message, StringComparison.Ordinal);
        var none = Assert.Throws<ZMachineException>(() => Zscii.ToChar(memory, 23));
        Assert.Contains("no character to print", none.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void CharactersLandAsZsciiCodes()
    {
        var memory = Story();
        Assert.Equal(13, Zscii.FromChar(memory, '\n'));
        Assert.Equal(97, Zscii.FromChar(memory, 'a'));
        Assert.Equal(155, Zscii.FromChar(memory, 'ä'));
        var none = Assert.Throws<ZMachineException>(() => Zscii.FromChar(memory, '↑'));
        Assert.Contains("no ZSCII code", none.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void ACustomUnicodeTableReplacesTheExtras()
    {
        var memory = Story(5, builder =>
        {
            var table = builder.Bytes(2, 0x21, 0x91, 0x03, 0xA9);
            builder.ExtensionTable = builder.Words(3, 0, 0, table);
        });
        Assert.Equal("↑", Zscii.ToChar(memory, 155));
        Assert.Equal("Ω", Zscii.ToChar(memory, 156));
        Assert.Equal(156, Zscii.FromChar(memory, 'Ω'));
        Assert.Throws<ZMachineException>(() => Zscii.ToChar(memory, 157));
    }

    [Fact]
    public void AnExtensionWithoutAUnicodeTableKeepsTheDefaults()
    {
        var short3 = Story(5, builder => builder.ExtensionTable = builder.Words(2, 0, 0));
        Assert.Equal("ä", Zscii.ToChar(short3, 155));
        var zero = Story(5, builder => builder.ExtensionTable = builder.Words(3, 0, 0, 0));
        Assert.Equal("ä", Zscii.ToChar(zero, 155));
    }

    // Versions 1 and 2 shift relative to the current alphabet and lock
    // for a run of two: these bytes come from the reference's
    // encode_word over the Version 1 and 2 releases of Zork I.
    [Theory]
    [InlineData(1, "n", "4ca594a5")]
    [InlineData(1, "mailbox", "48cec4f4")]
    [InlineData(1, ".", "0e2594a5")]
    [InlineData(1, "a1", "186894a5")]
    [InlineData(1, "12", "150994a5")]
    [InlineData(1, "x-y", "747cf8a5")]
    [InlineData(1, "ab12cd", "18e5a124")]
    [InlineData(1, "0", "0ce594a5")]
    [InlineData(1, "<", "0f6594a5")]
    [InlineData(1, "12a1", "150988c8")]
    [InlineData(2, ".", "0e4594a5")]
    [InlineData(2, "12a1", "152a88c9")]
    [InlineData(2, "a1", "186994a5")]
    [InlineData(2, "12", "152a94a5")]
    [InlineData(2, "ab12cd", "18e5a544")]
    [InlineData(2, "0", "0d0594a5")]
    [InlineData(2, "<", "0cc1f0a5")]
    public void EarlyDictionaryEncodingMatchesTheReference(int version, string word, string hex)
    {
        Assert.Equal(hex, Convert.ToHexStringLower(Zscii.EncodeWord(Story(version), word)));
    }

    // In Version 2, Z-character 1 opens the one abbreviation bank, 2
    // shifts up for one character relative to the alphabet in force,
    // a space ends a pending shift, and 4 and 5 rotate the lock. The
    // Z-characters here are 2 6 0, 2 0 6, 4 6 1, 0 5 5.
    [Fact]
    public void VersionTwoAbbreviatesAndShiftsRelatively()
    {
        var builder = new StoryBuilder(2);
        builder.SetAbbreviation(0, "the");
        var address = builder.Bytes(0x08, 0xC0, 0x08, 0x06, 0x10, 0xC1, 0x80, 0xA5);
        builder.Quit();
        Assert.Equal("A  aAthe", Zscii.Decode(new Memory(builder.Build()), address).Text);
    }

    [Fact]
    public void ArrowsAndInputKeysHaveCharacters()
    {
        var memory = Story();
        Assert.Equal("↑↓→←", string.Concat(Enumerable.Range(24, 4).Select(code => Zscii.ToChar(memory, code))));
        Assert.Equal(8, Zscii.FromChar(memory, '\b'));
        Assert.Equal(8, Zscii.FromChar(memory, '\x7f'));
        Assert.Equal(27, Zscii.FromChar(memory, '\x1b'));
        Assert.Equal(129, Zscii.FromChar(memory, '\u0081'));
        Assert.Equal(154, Zscii.FromChar(memory, '\u009a'));
    }

    // These bytes are what the Python reference's encode_word yields
    // for the same words, read off Zork I (Version 3) and Curses
    // (Version 5).
    [Theory]
    [InlineData(3, "mailbox", "48cec4f4")]
    [InlineData(3, "open", "52aacca5")]
    [InlineData(3, "x", "74a594a5")]
    [InlineData(3, "Zork", "7e97c0a5")]
    [InlineData(3, "a1-b", "18a99787")]
    [InlineData(3, "lanterns", "44d3e557")]
    [InlineData(3, "thirteenthing", "65aedf2a")]
    [InlineData(5, "mailbox", "48ce44f4f4a5")]
    [InlineData(5, "open", "52aa4ca594a5")]
    [InlineData(5, "x", "74a514a594a5")]
    [InlineData(5, "Zork", "7e9740a594a5")]
    [InlineData(5, "a1-b", "18a9178794a5")]
    [InlineData(5, "lanterns", "44d36557cf05")]
    [InlineData(5, "thirteenthing", "65ae5f2aaa79")]
    public void DictionaryEncodingMatchesTheReference(int version, string word, string hex)
    {
        var memory = Story(version);
        Assert.Equal(hex, Convert.ToHexStringLower(Zscii.EncodeWord(memory, word)));
        Assert.Equal(hex, Convert.ToHexStringLower(StoryBuilder.EncodeWord(version, word)));
    }

    [Fact]
    public void EncodingEscapesWhatNoAlphabetHolds()
    {
        var memory = Story();
        var encoded = Zscii.EncodeWord(memory, "ä");
        // 5, 6, then 155 as two five-bit halves: 4 and 27, then padding.
        Assert.Equal("14c4eca5", Convert.ToHexStringLower(encoded));
    }
}
