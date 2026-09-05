using System.Text;
using Voxam.Core.Glulx.Glk;

namespace Voxam.Tests.Glulx.Glk;

/// <summary>
/// The four kinds of stream: what they count, what they substitute, and
/// where their marks sit (Glk: Streams).
/// </summary>
public sealed class StreamsTests
{
    // The base holds the counting rules and nothing else: what is
    // written goes nowhere and what is read is the end of the stream.
    [Fact]
    public void TheBaseStreamCountsWithoutHoldingAnything()
    {
        var stream = new BareStream();

        stream.PutChar('A');
        stream.PutChar('B');

        Assert.Equal(2u, stream.WriteCount);
        Assert.Equal(-1, stream.GetChar());
        Assert.Equal(0u, stream.ReadCount);
        Assert.Equal(0, stream.GetPosition());

        // A stream with no position has nowhere to move to.
        stream.SetPosition(4, SeekMode.Start);

        Assert.Equal(0, stream.GetPosition());

        var (read, written) = stream.Close();

        Assert.Equal(0u, read);
        Assert.Equal(2u, written);
        Assert.True(stream.Disposed);
    }

    // A stream that cannot be written discards without even counting:
    // the count is of characters written into the stream, and nothing
    // was.
    [Fact]
    public void AStreamThatCannotBeWrittenCountsNothing()
    {
        var stream = new BareStream(writable: false);

        stream.PutChar('A');

        Assert.Equal(0u, stream.WriteCount);
    }

    // A stream that cannot be read answers the end of stream without
    // counting a read.
    [Fact]
    public void AStreamThatCannotBeReadIsAlreadyAtItsEnd()
    {
        var stream = new BareStream(readable: false);

        Assert.Equal(-1, stream.GetChar());
        Assert.Equal(0u, stream.ReadCount);
    }

    // A byte stream substitutes '?' for anything above 0xFF; a Unicode
    // stream holds the word itself (Glk: Output). The limit is the byte
    // and not ASCII, so an accented letter passes through a byte stream
    // as the Latin-1 value it already is.
    [Fact]
    public void AByteStreamSubstitutesOnlyWhatWillNotFitInAByte()
    {
        var narrow = new WordBuffer(2);
        var wide = new WordBuffer(2);

        new StreamOnMemory(narrow, GlkFileMode.Write).PutString("é€");
        new StreamOnMemory(wide, GlkFileMode.Write, unicode: true).PutString("é€");

        Assert.Equal([0x00E9u, Characters.Unprintable], narrow.Snapshot());
        Assert.Equal([0x00E9u, 0x20ACu], wide.Snapshot());
    }

    // The count reported at close includes characters that did not fit,
    // "the number of characters written into the stream, not the number
    // that fit" (Glk: Memory Streams), which is how a game measures the
    // length of output it never means to keep.
    [Fact]
    public void TheWriteCountIncludesWhatDidNotFit()
    {
        var stream = new StreamOnMemory(new WordBuffer(2), GlkFileMode.Write);

        stream.PutString("abcde");

        Assert.Equal(5u, stream.WriteCount);
        Assert.Equal(5, stream.GetPosition());
    }

    // A string is written a code point at a time, so a character above
    // the basic plane is one write and not the two units C# spends on
    // holding it.
    [Fact]
    public void AStringIsWrittenACodePointAtATime()
    {
        var stream = new StreamOnMemory(new WordBuffer(4), GlkFileMode.Write, unicode: true);

        stream.PutString("a😀b");

        Assert.Equal(3u, stream.WriteCount);
        Assert.Equal([0x61u, 0x1F600u, 0x62u, 0u], ((WordBuffer)stream.Buffer!).Snapshot());
    }

    // A buffer of values goes out in order.
    [Fact]
    public void ABufferOfValuesGoesOutInOrder()
    {
        var held = new WordBuffer(3);

        new StreamOnMemory(held, GlkFileMode.Write).PutBuffer([1u, 2u, 3u]);

        Assert.Equal([1u, 2u, 3u], held.Snapshot());
    }

    // Nothing at all is not something to write or read into.
    [Fact]
    public void NothingAtAllIsNotSomethingToReadOrWrite()
    {
        var stream = new BareStream();

        Assert.Throws<ArgumentNullException>(() => stream.PutString(null!));
        Assert.Throws<ArgumentNullException>(() => stream.PutBuffer(null!));
        Assert.Throws<ArgumentNullException>(() => stream.GetBuffer(null!));
        Assert.Throws<ArgumentNullException>(() => stream.GetLine(null!));
    }

    // A buffer read stops at the end of the stream and answers how far
    // it got, with no terminal null placed (Glk: How To Read).
    [Fact]
    public void ABufferReadStopsAtTheEndOfTheStream()
    {
        var source = new StreamOnMemory(new WordBuffer(0x41u, 0x42u), GlkFileMode.Read);
        var into = new WordBuffer(4);

        Assert.Equal(2, source.GetBuffer(into));
        Assert.Equal([0x41u, 0x42u, 0u, 0u], into.Snapshot());
        Assert.Equal(2u, source.ReadCount);
    }

    // A buffer read that fills its array stops there.
    [Fact]
    public void ABufferReadStopsWhenTheArrayIsFull()
    {
        var source = new StreamOnMemory(
            new WordBuffer(0x41u, 0x42u, 0x43u), GlkFileMode.Read);
        var into = new WordBuffer(2);

        Assert.Equal(2, source.GetBuffer(into));
        Assert.Equal([0x41u, 0x42u], into.Snapshot());
    }

    // A line read keeps the newline and terminates what it stored, the
    // terminal null not counted (Glk: How To Read).
    [Fact]
    public void ALineReadKeepsTheNewlineAndTerminates()
    {
        var source = new StreamOnMemory(
            new WordBuffer(0x41u, Characters.Newline, 0x42u), GlkFileMode.Read);
        var into = new WordBuffer(8);

        Assert.Equal(2, source.GetLine(into));
        Assert.Equal([0x41u, Characters.Newline, 0u, 0u, 0u, 0u, 0u, 0u], into.Snapshot());
    }

    // A line read that meets the end of the stream terminates what it
    // has.
    [Fact]
    public void ALineReadTerminatesAtTheEndOfTheStream()
    {
        var source = new StreamOnMemory(new WordBuffer(0x41u), GlkFileMode.Read);
        var into = new WordBuffer(4);

        Assert.Equal(1, source.GetLine(into));
        Assert.Equal([0x41u, 0u, 0u, 0u], into.Snapshot());
    }

    // At most one less than the capacity is stored, so the terminator
    // always has somewhere to go.
    [Fact]
    public void ALineReadLeavesRoomForItsTerminator()
    {
        var source = new StreamOnMemory(
            new WordBuffer(0x41u, 0x42u, 0x43u), GlkFileMode.Read);
        var into = new WordBuffer(3);

        Assert.Equal(2, source.GetLine(into));
        Assert.Equal([0x41u, 0x42u, 0u], into.Snapshot());
    }

    // A line read into no room at all reads nothing, because there is
    // nowhere to put even the terminator.
    [Fact]
    public void ALineReadIntoNoRoomReadsNothing()
    {
        var source = new StreamOnMemory(new WordBuffer(0x41u), GlkFileMode.Read);

        Assert.Equal(0, source.GetLine(new WordBuffer(0)));
        Assert.Equal(0u, source.ReadCount);
    }

    // The mode word opens the directions, and a mode naming none opens
    // neither.
    [Theory]
    [InlineData(GlkFileMode.Read, true, false)]
    [InlineData(GlkFileMode.Write, false, true)]
    [InlineData(GlkFileMode.ReadWrite, true, true)]
    [InlineData(GlkFileMode.WriteAppend, false, true)]
    [InlineData(0u, false, false)]
    public void TheModeWordOpensTheDirections(uint fmode, bool readable, bool writable)
    {
        var stream = new StreamOnMemory(new WordBuffer(1), fmode);

        Assert.Equal(readable, stream.Readable);
        Assert.Equal(writable, stream.Writable);
    }

    // A null buffer is legal: the stream discards writes but still
    // counts them, which is how a game measures output length (Glk:
    // Memory Streams).
    [Fact]
    public void ANullBufferDiscardsButStillCounts()
    {
        var stream = new StreamOnMemory(null, GlkFileMode.ReadWrite);

        stream.PutString("abc");

        Assert.Equal(0, stream.Capacity);
        Assert.Equal(3u, stream.WriteCount);
        Assert.Equal(3, stream.GetPosition());
        Assert.Equal(-1, stream.GetChar());
    }

    // Reading walks the buffer and then reports the end.
    [Fact]
    public void AMemoryReadWalksTheBufferThenReportsTheEnd()
    {
        var stream = new StreamOnMemory(new WordBuffer(0x41u, 0x42u), GlkFileMode.Read);

        Assert.Equal(0x41, stream.GetChar());
        Assert.Equal(0x42, stream.GetChar());
        Assert.Equal(-1, stream.GetChar());
        Assert.Equal(2u, stream.ReadCount);
    }

    // The mark moves from wherever the mode names, and is clamped to
    // the buffer at both ends (Glk: Stream Positions).
    [Fact]
    public void TheMemoryMarkMovesAndIsClamped()
    {
        var stream = new StreamOnMemory(new WordBuffer(4), GlkFileMode.ReadWrite);

        stream.SetPosition(2, SeekMode.Start);
        Assert.Equal(2, stream.GetPosition());

        stream.SetPosition(1, SeekMode.Current);
        Assert.Equal(3, stream.GetPosition());

        stream.SetPosition(-1, SeekMode.End);
        Assert.Equal(3, stream.GetPosition());

        stream.SetPosition(-100, SeekMode.Start);
        Assert.Equal(0, stream.GetPosition());

        stream.SetPosition(100, SeekMode.Start);
        Assert.Equal(4, stream.GetPosition());
    }

    // A window's stream is write-only and always Unicode, and what it
    // takes reaches the window itself.
    [Fact]
    public void AWindowStreamCarriesToItsWindow()
    {
        var window = new TextBufferWindow();
        var stream = window.Stream;

        Assert.True(stream.Writable);
        Assert.False(stream.Readable);
        Assert.True(stream.Unicode);
        Assert.Same(window, stream.Window);

        stream.PutString("hi");

        Assert.Equal("hi", window.Text());
    }

    // A window has no position at all (Glk: Stream Positions), so a
    // seek on its stream is nothing.
    [Fact]
    public void AWindowStreamHasNoPosition()
    {
        var stream = new TextBufferWindow().Stream;

        stream.SetPosition(9, SeekMode.Start);

        Assert.Equal(0, stream.GetPosition());
    }

    // A byte file holds one Latin-1 byte per character, in either mode.
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void AByteFileHoldsOneBytePerCharacter(bool textMode)
    {
        var handle = new MemoryStream();
        var stream = new StreamOnFile(handle, GlkFileMode.ReadWrite, textMode: textMode);

        Assert.Equal(1, stream.Width);
        Assert.False(stream.Utf8);

        stream.PutString("AB");
        stream.SetPosition(0, SeekMode.Start);

        Assert.Equal(0x41, stream.GetChar());
        Assert.Equal(0x42, stream.GetChar());
        Assert.Equal(-1, stream.GetChar());
        Assert.Equal([0x41, 0x42], handle.ToArray());
    }

    // A Unicode file in binary mode holds four-byte big-endian words
    // (Glk: File Streams).
    [Fact]
    public void AUnicodeBinaryFileHoldsBigEndianWords()
    {
        var handle = new MemoryStream();
        var stream = new StreamOnFile(handle, GlkFileMode.ReadWrite, unicode: true);

        Assert.Equal(4, stream.Width);
        Assert.False(stream.Utf8);

        stream.PutChar(0x1F600);
        stream.PutChar(0xFFFFFFFF);

        Assert.Equal([0x00, 0x01, 0xF6, 0x00, 0xFF, 0xFF, 0xFF, 0xFF], handle.ToArray());

        stream.SetPosition(0, SeekMode.Start);

        Assert.Equal(0x1F600, stream.GetChar());
        Assert.Equal(0xFFFFFFFF, stream.GetChar());
        Assert.Equal(-1, stream.GetChar());
    }

    // A word cut short by the end of the file is not a character.
    [Fact]
    public void AWordCutShortIsNotACharacter()
    {
        var handle = new MemoryStream([0x00, 0x01]);
        var stream = new StreamOnFile(handle, GlkFileMode.Read, unicode: true);

        Assert.Equal(-1, stream.GetChar());
    }

    // A Unicode file in text mode holds UTF-8 with no byte-order mark,
    // which is what makes it readable by anything else, and identical
    // to a byte file wherever only ASCII is involved.
    [Fact]
    public void AUnicodeTextFileHoldsPlainUtf8()
    {
        var handle = new MemoryStream();
        var stream = new StreamOnFile(
            handle, GlkFileMode.ReadWrite, unicode: true, textMode: true);

        Assert.True(stream.Utf8);

        stream.PutString("A😀");

        Assert.Equal(Encoding.UTF8.GetBytes("A😀"), handle.ToArray());
    }

    // Every UTF-8 length decodes to the one character it stands for.
    [Theory]
    [InlineData("A", 0x41L)]
    [InlineData("é", 0xE9L)]
    [InlineData("€", 0x20ACL)]
    [InlineData("😀", 0x1F600L)]
    public void EveryUtf8LengthDecodesToItsCharacter(string text, long expected)
    {
        var stream = Utf8Over(Encoding.UTF8.GetBytes(text));

        Assert.Equal(expected, stream.GetChar());
        Assert.Equal(-1, stream.GetChar());
    }

    // Bytes that are not a sequence at all become the placeholder
    // rather than derailing the read: a stray continuation byte, a
    // sequence the file ends in the middle of, and an overlong form.
    [Theory]
    [InlineData(new byte[] { 0x80 })]
    [InlineData(new byte[] { 0xE2, 0x82 })]
    [InlineData(new byte[] { 0xC0, 0x80 })]
    public void BytesThatAreNotASequenceBecomeThePlaceholder(byte[] bytes) =>
        Assert.Equal(Characters.Unprintable, (uint)Utf8Over(bytes).GetChar());

    // The mark of a file stream is the handle's own, and an unknown
    // mode measures from the start.
    [Fact]
    public void TheFileMarkIsTheHandlesOwn()
    {
        var handle = new MemoryStream([0x41, 0x42, 0x43, 0x44]);
        var stream = new StreamOnFile(handle, GlkFileMode.Read);

        stream.SetPosition(1, SeekMode.Start);
        Assert.Equal(1, stream.GetPosition());

        stream.SetPosition(1, SeekMode.Current);
        Assert.Equal(2, stream.GetPosition());

        stream.SetPosition(-1, SeekMode.End);
        Assert.Equal(3, stream.GetPosition());

        stream.SetPosition(0, 99);
        Assert.Equal(0, stream.GetPosition());
    }

    // Closing a file stream closes the file along with it, and still
    // answers the counts the game asked for.
    [Fact]
    public void ClosingAFileStreamClosesTheFile()
    {
        var handle = new MemoryStream();
        var stream = new StreamOnFile(handle, GlkFileMode.Write);

        stream.PutString("hi");

        var (read, written) = stream.Close();

        Assert.Equal(0u, read);
        Assert.Equal(2u, written);
        Assert.True(stream.Disposed);
        Assert.Throws<ObjectDisposedException>(() => handle.Position);
    }

    // The handle can be let go without a close, for the caller that
    // holds one and never opened a session with it.
    [Fact]
    public void TheHandleCanBeLetGoOnItsOwn()
    {
        var handle = new MemoryStream();

        using (var stream = new StreamOnFile(handle, GlkFileMode.Write))
        {
            stream.PutChar('x');
        }

        Assert.Throws<ObjectDisposedException>(() => handle.Position);
    }

    private static StreamOnFile Utf8Over(byte[] bytes) =>
        new(new MemoryStream(bytes), GlkFileMode.Read, unicode: true, textMode: true);
}
