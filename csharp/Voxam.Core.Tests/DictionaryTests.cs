using Voxam.Core.Tests.Support;

namespace Voxam.Core.Tests;

public class DictionaryTests
{
    private static (Memory Memory, DictionaryTable Dictionary) Words(int version = 3, int? declared = null, params string[] words)
    {
        var builder = new StoryBuilder(version);
        // A separator of ZSCII 0 prints as nothing and separates nothing.
        builder.Dictionary(".,\0", declared ?? words.Length, words);
        builder.Quit();
        var memory = new Memory(builder.Build());
        return (memory, new DictionaryTable(memory));
    }

    [Theory]
    [InlineData(3)]
    [InlineData(5)]
    public void LookupFindsAnEntryOrAnswersZero(int version)
    {
        var (memory, dictionary) = Words(version, null, "open", "mailbox", "lamp");
        // Three separator bytes precede the entry length and count.
        var entries = memory.ReadWord(Header.Dictionary) + 4 + 3;
        var entryLength = version <= 3 ? 7 : 9;
        Assert.Equal(entries, dictionary.Lookup("open"));
        Assert.Equal(entries + 2 * entryLength, dictionary.Lookup("lamp"));
        Assert.Equal(0, dictionary.Lookup("sword"));
        Assert.Equal(new HashSet<char> { '.', ',' }, dictionary.Separators);
    }

    [Fact]
    public void ANegativeCountMeansAnUnsortedTableOfThatSize()
    {
        var (_, dictionary) = Words(3, 0x10000 - 2, "open", "lamp");
        Assert.NotEqual(0, dictionary.Lookup("lamp"));
    }

    [Fact]
    public void AnotherTableCanBeReadByAddress()
    {
        var builder = new StoryBuilder();
        builder.Dictionary("", "open");
        var other = builder.Dictionary("", "close");
        builder.Quit();
        var memory = new Memory(builder.Build());
        var dictionary = new DictionaryTable(memory, other);
        Assert.NotEqual(0, dictionary.Lookup("close"));
        Assert.Equal(0, dictionary.Lookup("open"));
    }

    [Fact]
    public void TokenizingSplitsAtSpacesAndKeepsSeparators()
    {
        var separators = new HashSet<char> { '.', ',' };
        var words = DictionaryTable.Tokenize("  open the mailbox, then.read leaflet ", separators);
        Assert.Equal(
            [("open", 2), ("the", 7), ("mailbox", 11), (",", 18), ("then", 20), (".", 24), ("read", 25), ("leaflet", 30)],
            words);
        Assert.Empty(DictionaryTable.Tokenize("   ", separators));
        Assert.Equal([("x", 0)], DictionaryTable.Tokenize("x", separators));
    }
}
