using Voxam.Core.Glulx;
using Voxam.Core.Glulx.Glk;
using GlulxException = Voxam.Core.GlulxException;

namespace Voxam.Tests.Glulx.Glk;

/// <summary>
/// File references, the streams opened over them, and the functions
/// that work on text and on time.
/// </summary>
public sealed class ApiTextTests : IDisposable
{
    private const uint Buf = 0x500;
    private const uint Ref = 0x600;
    private const uint Date = 0x700;
    private const uint Time = 0x780;

    private readonly string _saveDir =
        Path.Combine(Path.GetTempPath(), "voxam-glk-test-" + Path.GetRandomFileName());

    public ApiTextTests() => Directory.CreateDirectory(_saveDir);

    public void Dispose() => Directory.Delete(_saveDir, true);

    // A name the game supplies is stripped of everything that could
    // reach outside the save directory, truncated at its first period,
    // and given the suffix its usage asks for.
    [Theory]
    [InlineData("notes", FileUsage.Data, "notes.glkdata")]
    [InlineData("notes.txt", FileUsage.Data, "notes.glkdata")]
    [InlineData("save", FileUsage.SavedGame, "save.glksave")]
    [InlineData("log", FileUsage.Transcript, "log.txt")]
    [InlineData("keys", FileUsage.InputRecord, "keys.txt")]
    [InlineData("../../etc/passwd", FileUsage.Data, "null.glkdata")]
    [InlineData("a/b<c>d:e|f?g*h", FileUsage.Data, "abcdefgh.glkdata")]
    [InlineData("", FileUsage.Data, "null.glkdata")]
    public void AGameSuppliedNameCannotReachOutsideTheSaveDirectory(
        string name, uint usage, string expected)
    {
        var (bridge, glk) = Seam();

        bridge.Perform(0x0061, [usage, StringAt(bridge, name), 0]);

        var fileref = Assert.Single(glk.FileRefs);

        Assert.Equal(expected, Path.GetFileName(fileref.Filename));
        Assert.Equal(_saveDir, Path.GetDirectoryName(fileref.Filename));
    }

    // A reference records what the file is for, and a second reference
    // to the same file can be made for a different usage.
    [Fact]
    public void AReferenceCanBeRemadeForAnotherUsage()
    {
        var (bridge, glk) = Seam();

        var first = bridge.Perform(
            0x0061, [FileUsage.Data | FileUsage.TextMode, StringAt(bridge, "notes"), 9]);

        Assert.Equal(9u, bridge.Perform(0x0065, [first]));
        Assert.Equal(0u, bridge.Perform(0x0065, [0]));
        Assert.True(glk.FileRefs[0].TextMode);

        bridge.Perform(0x0068, [FileUsage.SavedGame, first, 10]);

        Assert.Equal(2, glk.FileRefs.Count);
        Assert.Equal(glk.FileRefs[1].Filename, glk.FileRefs[0].Filename);
        Assert.Equal(FileUsage.SavedGame, glk.FileRefs[0].Usage);

        Assert.Equal(
            "fileref_create_from_fileref: invalid fileref",
            Assert.Throws<GlulxException>(
                () => bridge.Perform(0x0068, [FileUsage.Data, 0, 0])).Message);
    }

    // A temporary file exists the moment it is named and dies with the
    // reference to it.
    [Fact]
    public void ATemporaryFileDiesWithItsReference()
    {
        var (bridge, glk) = Seam();

        var ident = bridge.Perform(0x0060, [FileUsage.Data, 0]);
        var path = glk.FileRefs[0].Filename;

        Assert.True(glk.FileRefs[0].Temporary);
        Assert.Equal(1u, bridge.Perform(0x0067, [ident]));

        bridge.Perform(0x0063, [ident]);

        Assert.Empty(glk.FileRefs);
        Assert.False(File.Exists(path));

        // Destroying nothing is nothing.
        bridge.Perform(0x0063, [0]);
    }

    // A reference the game named itself is not temporary, so dropping it
    // leaves the file exactly where it is.
    [Fact]
    public void DroppingANamedReferenceLeavesTheFile()
    {
        var (bridge, glk) = Seam();

        var ident = bridge.Perform(0x0061, [FileUsage.Data, StringAt(bridge, "keep"), 0]);
        var path = glk.FileRefs[0].Filename;

        File.WriteAllText(path, "x");

        Assert.False(glk.FileRefs[0].Temporary);

        bridge.Perform(0x0063, [ident]);

        Assert.Empty(glk.FileRefs);
        Assert.True(File.Exists(path));
    }

    // Writing a file, reading it back, and deleting it.
    [Fact]
    public void AFileIsWrittenAndReadAndDeleted()
    {
        var (bridge, _) = Seam();

        var fileref = bridge.Perform(0x0061, [FileUsage.Data, StringAt(bridge, "notes"), 0]);

        Assert.Equal(0u, bridge.Perform(0x0067, [fileref]));
        Assert.Equal(0u, bridge.Perform(0x0067, [0]));

        var writing = bridge.Perform(0x0042, [fileref, GlkFileMode.Write, 3]);

        bridge.Perform(0x0083, [writing, StringAt(bridge, "hello")]);
        bridge.Perform(0x0044, [writing, Ref]);

        Assert.Equal(5u, Word(bridge, Ref + 4));
        Assert.Equal(1u, bridge.Perform(0x0067, [fileref]));

        var reading = bridge.Perform(0x0042, [fileref, GlkFileMode.Read, 4]);

        Assert.Equal(5u, bridge.Perform(0x0091, [reading, Ref, 8]));
        Assert.Equal(0x68, bridge.Memory.ReadByte((int)Ref));

        bridge.Perform(0x0044, [reading, 0]);
        bridge.Perform(0x0066, [fileref]);

        Assert.Equal(0u, bridge.Perform(0x0067, [fileref]));

        // Deleting nothing, and deleting what is already gone, are both
        // quiet.
        bridge.Perform(0x0066, [fileref]);
        bridge.Perform(0x0066, [0]);
    }

    // A file stream can be opened wide, and appending starts the mark at
    // the end without forcing later writes there.
    [Fact]
    public void AnAppendingStreamStartsAtTheEndAndStillSeeks()
    {
        var (bridge, _) = Seam();

        var fileref = bridge.Perform(0x0061, [FileUsage.Data, StringAt(bridge, "notes"), 0]);
        var first = bridge.Perform(0x0042, [fileref, GlkFileMode.Write, 0]);

        bridge.Perform(0x0083, [first, StringAt(bridge, "abc")]);
        bridge.Perform(0x0044, [first, 0]);

        var appending = bridge.Perform(0x0042, [fileref, GlkFileMode.WriteAppend, 0]);

        Assert.Equal(3u, bridge.Perform(0x0046, [appending]));

        bridge.Perform(0x0045, [appending, 0, SeekMode.Start]);
        bridge.Perform(0x0081, [appending, 0x5A]);
        bridge.Perform(0x0044, [appending, 0]);

        var reading = bridge.Perform(0x0042, [fileref, GlkFileMode.ReadWrite, 0]);

        Assert.Equal(0x5Au, bridge.Perform(0x0090, [reading]));

        bridge.Perform(0x0044, [reading, 0]);
    }

    // A Unicode file stream holds words, and the reference's text mode
    // decides whether they travel as UTF-8.
    [Fact]
    public void AUnicodeFileStreamFollowsItsReferencesMode()
    {
        var (bridge, glk) = Seam();

        var fileref = bridge.Perform(
            0x0061, [FileUsage.Data | FileUsage.TextMode, StringAt(bridge, "wide"), 0]);
        var stream = bridge.Perform(0x0138, [fileref, GlkFileMode.Write, 0]);

        Assert.True(((StreamOnFile)glk.Streams[0]).Utf8);

        bridge.Perform(0x012B, [stream, 0x1F600]);
        bridge.Perform(0x0044, [stream, 0]);

        Assert.Equal(4, new FileInfo(glk.FileRefs[0].Filename).Length);
    }

    // The null reference cannot be opened, and a mode that is not one of
    // the four is refused.
    [Fact]
    public void OpeningAFileIsRefusedWhereItCannotWork()
    {
        var (bridge, _) = Seam();

        Assert.Equal(
            "stream_open_file: invalid fileref",
            Assert.Throws<GlulxException>(
                () => bridge.Perform(0x0042, [0, GlkFileMode.Read, 0])).Message);

        var fileref = bridge.Perform(0x0061, [FileUsage.Data, StringAt(bridge, "notes"), 0]);

        Assert.Equal(
            "stream_open_file: illegal filemode",
            Assert.Throws<GlulxException>(() => bridge.Perform(0x0042, [fileref, 9, 0])).Message);

        // A file that is not there cannot be read, and that answers the
        // null stream rather than faulting (Glk: File Streams).
        Assert.Equal(0u, bridge.Perform(0x0042, [fileref, GlkFileMode.Read, 0]));
    }

    // Walking the live references, newest first.
    [Fact]
    public void ReferencesWalkNewestFirst()
    {
        var (bridge, _) = Seam();

        var first = bridge.Perform(0x0061, [FileUsage.Data, StringAt(bridge, "one"), 1]);
        var second = bridge.Perform(0x0061, [FileUsage.Data, StringAt(bridge, "two"), 2]);

        Assert.Equal(second, bridge.Perform(0x0064, [0, Ref]));
        Assert.Equal(2u, Word(bridge, Ref));
        Assert.Equal(first, bridge.Perform(0x0064, [second, Ref]));
        Assert.Equal(0u, bridge.Perform(0x0064, [first, Ref]));
    }

    // A character's case, where one character can hold it. The runtime
    // maps one to one, so a character whose uppercase needs more than
    // one character stays itself, which is what the specification asks
    // for here anyway (Glk: Upper and Lower Case).
    [Theory]
    [InlineData(0x61u, 0x61u, 0x41u)]
    [InlineData(0xE9u, 0xE9u, 0xC9u)]
    [InlineData(0x1C5u, 0x1C6u, 0x1C4u)]
    [InlineData(0xDFu, 0xDFu, 0xDFu)]
    [InlineData(0xFB04u, 0xFB04u, 0xFB04u)]
    [InlineData(0x110000u, 0x110000u, 0x110000u)]
    [InlineData(0x41u, 0x61u, 0x41u)]
    public void ACharactersCaseIsWhatOneCharacterCanHold(uint value, uint lower, uint upper)
    {
        var (bridge, _) = Seam();

        Assert.Equal(lower, bridge.Perform(0x00A0, [value]));
        Assert.Equal(upper, bridge.Perform(0x00A1, [value]));
    }

    // What the case functions promise, whatever tables the machine
    // underneath them carries.
    //
    // The mapping is one to one: every character answers exactly one
    // character back, which is the whole of what glk_char_to_upper can
    // express. That is a promise about the shape of the answer, so it
    // holds on any machine. Which characters map where is not: the
    // reference carries Python's Unicode tables and this carries the
    // platform's, and 55 code points differ between them, almost all
    // letters added to Unicode since one or the other last looked.
    // Those live in the prose, not in an assertion, because an
    // assertion about another machine's tables is a thing that breaks
    // on a machine you cannot see.
    [Theory]
    [InlineData(0x41u)]
    [InlineData(0x7Au)]
    [InlineData(0xDFu)]
    [InlineData(0xE9u)]
    [InlineData(0x131u)]
    [InlineData(0x17Fu)]
    [InlineData(0x1C4u)]
    [InlineData(0xFB04u)]
    [InlineData(0x3A3u)]
    [InlineData(0x1F600u)]
    public void TheCaseFunctionsAlwaysAnswerOneCharacter(uint value)
    {
        var (bridge, _) = Seam();

        var upper = bridge.Perform(0x00A1, [value]);
        var lower = bridge.Perform(0x00A0, [value]);

        // Whatever comes back is a character in its own right, and
        // mapping it again cannot wander further.
        Assert.Equal(upper, bridge.Perform(0x00A1, [upper]));
        Assert.Equal(lower, bridge.Perform(0x00A0, [lower]));
        Assert.True(upper <= Characters.MaxUnicode);
        Assert.True(lower <= Characters.MaxUnicode);
    }

    // A buffer is case-mapped one character at a time, not as a joined
    // string: a whole-string mapping applies context-sensitive rules
    // where the specification asks for every character mapped to its
    // equivalent.
    [Fact]
    public void ABufferIsMappedOneCharacterAtATime()
    {
        var (bridge, _) = Seam();

        // Greek final sigma: joined, the last one would lowercase
        // differently from the rest.
        Lay(bridge, [0x3A3, 0x3A3]);

        Assert.Equal(2u, bridge.Perform(0x0120, [Buf, 8, 2]));
        Assert.Equal(0x3C3u, Word(bridge, Buf));
        Assert.Equal(0x3C3u, Word(bridge, Buf + 4));

        Lay(bridge, [0x61, 0xE9]);

        Assert.Equal(2u, bridge.Perform(0x0121, [Buf, 8, 2]));
        Assert.Equal(0x41u, Word(bridge, Buf));
        Assert.Equal(0xC9u, Word(bridge, Buf + 4));
    }

    // A buffer whose mapping would grow is where the reference and this
    // runtime differ again: the reference expands 103 code points, and
    // this one maps each to itself. What is pinned here is what the port
    // answers, so the boundary is visible rather than assumed.
    [Fact]
    public void AMappingThatWouldGrowLeavesTheCharacterAlone()
    {
        var (bridge, _) = Seam();

        Lay(bridge, [0x41, 0xDF]);

        Assert.Equal(2u, bridge.Perform(0x0121, [Buf, 8, 2]));
        Assert.Equal(0x41u, Word(bridge, Buf));
        Assert.Equal(0xDFu, Word(bridge, Buf + 4));
    }

    // Title case is a third case, not a synonym for uppercase, and the
    // rest of the buffer follows or does not as the game asks.
    [Fact]
    public void TitleCaseIsItsOwnCase()
    {
        var (bridge, _) = Seam();

        Lay(bridge, [0x1C4, 0x42, 0x43]);

        Assert.Equal(3u, bridge.Perform(0x0122, [Buf, 8, 3, 1]));
        Assert.Equal(0x1C5u, Word(bridge, Buf));
        Assert.Equal(0x62u, Word(bridge, Buf + 4));

        Lay(bridge, [0x1C4, 0x42, 0x43]);

        Assert.Equal(3u, bridge.Perform(0x0122, [Buf, 8, 3, 0]));
        Assert.Equal(0x1C5u, Word(bridge, Buf));
        Assert.Equal(0x42u, Word(bridge, Buf + 4));

        // Nothing to title-case is nothing.
        Assert.Equal(0u, bridge.Perform(0x0122, [Buf, 8, 0, 1]));
    }

    // Normalization really normalizes: decomposing pulls an accent off
    // its letter, and composing puts it back (Glk: Unicode String
    // Normalization).
    [Fact]
    public void NormalizationDecomposesAndComposes()
    {
        var (bridge, _) = Seam();

        Lay(bridge, [0xE9, 0x41]);

        Assert.Equal(3u, bridge.Perform(0x0123, [Buf, 8, 2]));
        Assert.Equal(0x65u, Word(bridge, Buf));
        Assert.Equal(0x301u, Word(bridge, Buf + 4));
        Assert.Equal(0x41u, Word(bridge, Buf + 8));

        Lay(bridge, [0x65, 0x301]);

        Assert.Equal(1u, bridge.Perform(0x0124, [Buf, 8, 2]));
        Assert.Equal(0xE9u, Word(bridge, Buf));
    }

    // The true converted length is answered even where it will not fit,
    // the buffer past that point being undefined.
    [Fact]
    public void TheLengthIsAnsweredEvenWhereItWillNotFit()
    {
        var (bridge, _) = Seam();

        Lay(bridge, [0xE9, 0xE9, 0xE9]);

        // Three letters decompose into six characters, into a buffer
        // with room for four.
        Assert.Equal(6u, bridge.Perform(0x0123, [Buf, 4, 3]));
        Assert.Equal(0x65u, Word(bridge, Buf));
        Assert.Equal(0x301u, Word(bridge, Buf + 4));

        // And a count of nothing maps nothing at all.
        Assert.Equal(0u, bridge.Perform(0x0120, [Buf, 4, 0]));
        Assert.Equal(0u, bridge.Perform(0x0120, [Buf, 4, unchecked((uint)-1)]));
    }

    // The clock answers the moment it is pinned to, as a signed
    // sixty-four bit second count in two words (Glk: The System Clock).
    [Fact]
    public void TheClockAnswersItsMomentInTwoWords()
    {
        var (bridge, glk) = Seam();

        glk.Now = () => DateTimeOffset.FromUnixTimeSeconds(1614834367);

        bridge.Perform(0x0160, [Time]);

        Assert.Equal(0u, Word(bridge, Time));
        Assert.Equal(1614834367u, Word(bridge, Time + 4));

        Assert.Equal(26913906u, bridge.Perform(0x0161, [60]));
        Assert.Equal(unchecked((uint)-1), bridge.Perform(0x0161, [0]));
    }

    // A timestamp explodes into a date, and back again.
    [Fact]
    public void ATimestampExplodesIntoADateAndBack()
    {
        var (bridge, _) = Seam();

        Lay(bridge, Time, [0, 1614834367, 500000]);

        bridge.Perform(0x0168, [Time, Date]);

        Assert.Equal(2021u, Word(bridge, Date));
        Assert.Equal(3u, Word(bridge, Date + 4));
        Assert.Equal(4u, Word(bridge, Date + 8));
        // Glk counts weekdays from Sunday; 2021-03-04 was a Thursday.
        Assert.Equal(4u, Word(bridge, Date + 12));
        Assert.Equal(5u, Word(bridge, Date + 16));
        Assert.Equal(6u, Word(bridge, Date + 20));
        Assert.Equal(7u, Word(bridge, Date + 24));
        Assert.Equal(500000u, Word(bridge, Date + 28));

        bridge.Perform(0x016C, [Date, Time]);

        Assert.Equal(0u, Word(bridge, Time));
        Assert.Equal(1614834367u, Word(bridge, Time + 4));
        Assert.Equal(500000u, Word(bridge, Time + 8));

        Assert.Equal(26913906u, bridge.Perform(0x016E, [Date, 60]));
        Assert.Equal(unchecked((uint)-1), bridge.Perform(0x016E, [Date, 0]));
    }

    // A time before the epoch is a negative second count, which the two
    // words carry as one signed number.
    [Fact]
    public void ATimeBeforeTheEpochIsNegative()
    {
        var (bridge, _) = Seam();

        Lay(bridge, Time, [0xFFFFFFFF, 0xFFFFFFFF, 0]);

        bridge.Perform(0x0168, [Time, Date]);

        Assert.Equal(1969u, Word(bridge, Date));
        Assert.Equal(12u, Word(bridge, Date + 4));
        Assert.Equal(31u, Word(bridge, Date + 8));
        Assert.Equal(23u, Word(bridge, Date + 16));
        Assert.Equal(59u, Word(bridge, Date + 24));

        bridge.Perform(0x016C, [Date, Time]);

        Assert.Equal(0xFFFFFFFFu, Word(bridge, Time));
        Assert.Equal(0xFFFFFFFFu, Word(bridge, Time + 4));
    }

    // The fields need not be in their normal ranges: they are normalized
    // (Glk: Time and Date Conversions).
    [Fact]
    public void DateFieldsNeedNotBeInRange()
    {
        var (bridge, _) = Seam();

        // The fifteenth month of 2021 is March of 2022, and the fortieth
        // day of it is the ninth of April.
        Lay(bridge, Date, [2021, 15, 40, 0, 0, 0, 0, 0]);
        bridge.Perform(0x016C, [Date, Time]);
        bridge.Perform(0x0168, [Time, Date]);

        Assert.Equal(2022u, Word(bridge, Date));
        Assert.Equal(4u, Word(bridge, Date + 4));
        Assert.Equal(9u, Word(bridge, Date + 8));

        // And a month before the year's start walks back into the one
        // before it.
        Lay(bridge, Date, [2021, 0, 1, 0, 0, 0, 0, 0]);
        bridge.Perform(0x016C, [Date, Time]);
        bridge.Perform(0x0168, [Time, Date]);

        Assert.Equal(2020u, Word(bridge, Date));
        Assert.Equal(12u, Word(bridge, Date + 4));
    }

    // A date the calendar cannot hold answers the failure both words
    // carry (Glk: Time and Date Conversions).
    [Fact]
    public void ADateTheCalendarCannotHoldFails()
    {
        var (bridge, _) = Seam();

        Lay(bridge, Date, [99999, 1, 1, 0, 0, 0, 0, 0]);

        bridge.Perform(0x016C, [Date, Time]);

        Assert.Equal(0xFFFFFFFFu, Word(bridge, Time));
        Assert.Equal(0xFFFFFFFFu, Word(bridge, Time + 4));
        Assert.Equal(0u, Word(bridge, Time + 8));
        Assert.Equal(unchecked((uint)-1), bridge.Perform(0x016E, [Date, 60]));
        Assert.Equal(unchecked((uint)-1), bridge.Perform(0x016F, [Date, 60]));
    }

    // Every date and time reference is declared nonnull, so a call that
    // names none of them is refused before the library sees it.
    [Fact]
    public void ADateOrTimeReferenceCannotBeNothing()
    {
        var (bridge, _) = Seam();

        Assert.Throws<GlulxException>(() => bridge.Perform(0x0168, [Time, 0]));
        Assert.Throws<GlulxException>(() => bridge.Perform(0x0168, [0, Date]));
        Assert.Throws<GlulxException>(() => bridge.Perform(0x016C, [Date, 0]));
        Assert.Throws<GlulxException>(() => bridge.Perform(0x016C, [0, Time]));
        Assert.Throws<GlulxException>(() => bridge.Perform(0x016A, [0, 60, 0]));
        Assert.Throws<GlulxException>(() => bridge.Perform(0x016E, [0, 60]));
        Assert.Throws<GlulxException>(() => bridge.Perform(0x0160, [0]));
    }

    // A divided-down time explodes the same way, at whole-second
    // resolution.
    [Fact]
    public void ADividedTimeExplodesAtWholeSeconds()
    {
        var (bridge, _) = Seam();

        bridge.Perform(0x016A, [26913906, 60, Date]);

        Assert.Equal(2021u, Word(bridge, Date));
        Assert.Equal(3u, Word(bridge, Date + 4));
        Assert.Equal(0u, Word(bridge, Date + 28));

        bridge.Perform(0x016B, [26913906, 60, Date]);

        Assert.Equal(2021u, Word(bridge, Date));
    }

    // The local conversions answer the same instant read in this
    // machine's own zone, and round-trip through it.
    [Fact]
    public void TheLocalConversionsRoundTrip()
    {
        var (bridge, _) = Seam();

        Lay(bridge, Time, [0, 1614834367, 0]);
        bridge.Perform(0x0169, [Time, Date]);
        bridge.Perform(0x016D, [Date, Time]);

        Assert.Equal(1614834367u, Word(bridge, Time + 4));
        Assert.Equal(26913906u, bridge.Perform(0x016F, [Date, 60]));
    }

    private static uint Word(Bridge bridge, uint at) => bridge.Memory.ReadWord((int)at);

    private static void Lay(Bridge bridge, uint[] values) => Lay(bridge, Buf, values);

    private static void Lay(Bridge bridge, uint at, uint[] values)
    {
        for (var index = 0; index < 8; index++)
        {
            bridge.Memory.WriteWord((int)at + (index * 4), index < values.Length ? values[index] : 0);
        }
    }

    private static uint StringAt(Bridge bridge, string text)
    {
        const int At = 0x800;

        bridge.Memory.WriteByte(At, 0xE0);

        for (var index = 0; index < text.Length; index++)
        {
            bridge.Memory.WriteByte(At + 1 + index, text[index]);
        }

        bridge.Memory.WriteByte(At + 1 + text.Length, 0);

        return At;
    }

    private (Bridge Bridge, Api Glk) Seam()
    {
        var story = new Story(new GlulxBuilder
        {
            RamStart = 0x100,
            ExtStart = 0x200,
            EndMem = 0x2000,
            StackSize = 0x400,
        }.Build());

        var glk = new Api(saveDir: _saveDir);

        return (new Bridge(new Memory(story), glk, new StackMemory(0x400)), glk);
    }
}
