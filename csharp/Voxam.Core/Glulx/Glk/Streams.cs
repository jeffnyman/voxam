using System.Text;

namespace Voxam.Core.Glulx.Glk;

/// <summary>
/// Base stream: a sink, a source, or both (Glk: Streams).
///
/// The four kinds cannot wear the specification's own names here. Every
/// type ending in the bare word is refused by the analyzers, and two of
/// the names the specification would have us use are among the best
/// known in the base class library, so a file wrapping a real handle
/// would have to qualify which one it meant on every line. The word
/// leads instead of trailing, and the kinds stay parallel.
/// </summary>
public abstract class StreamObject : GlkObject
{
    /// <summary>Open with the directions and width the subclass chose.</summary>
    /// <param name="rock">The value the game files the stream under.</param>
    /// <param name="readable">Whether characters can be read from it.</param>
    /// <param name="writable">Whether characters can be written to it.</param>
    /// <param name="unicode">Whether it holds full words rather than bytes.</param>
    protected StreamObject(
        uint rock = 0,
        bool readable = false,
        bool writable = false,
        bool unicode = false)
        : base(rock)
    {
        Readable = readable;
        Writable = writable;
        Unicode = unicode;
    }

    /// <inheritdoc/>
    public override int GlkClass => 1;

    /// <summary>Whether characters can be read from it.</summary>
    public bool Readable { get; }

    /// <summary>Whether characters can be written to it.</summary>
    public bool Writable { get; }

    /// <summary>
    /// Whether it holds full words; a byte stream substitutes '?' for
    /// anything above 0xFF (Glk: Output).
    /// </summary>
    public bool Unicode { get; }

    /// <summary>Characters read so far.</summary>
    public uint ReadCount { get; private set; }

    /// <summary>Characters written so far, discards included.</summary>
    public uint WriteCount { get; private set; }

    /// <summary>
    /// The link value written output belongs to; zero means "not a
    /// link" (Glk: Creating Hyperlinks).
    /// </summary>
    public uint Hyperlink { get; set; }

    /// <summary>
    /// Write one character, counting it even if it goes nowhere.
    ///
    /// The write count reported at close must include characters a
    /// stream discards, "it will count the number of characters written
    /// into the stream, not the number that fit" (Glk: Memory Streams),
    /// so it is incremented before any capacity check.
    /// </summary>
    /// <param name="character">The character value to write.</param>
    public void PutChar(uint character)
    {
        if (!Writable)
        {
            return;
        }

        if (!Unicode && character >= Characters.ByteLimit)
        {
            character = Characters.Unprintable;
        }

        WriteCount++;

        Emit(character);
    }

    /// <summary>Write a string, one code point at a time.</summary>
    /// <param name="text">The text to write.</param>
    public void PutString(string text)
    {
        ArgumentNullException.ThrowIfNull(text);

        foreach (var rune in text.EnumerateRunes())
        {
            PutChar((uint)rune.Value);
        }
    }

    /// <summary>Write a sequence of character values.</summary>
    /// <param name="values">The characters to write, in order.</param>
    public void PutBuffer(IEnumerable<uint> values)
    {
        ArgumentNullException.ThrowIfNull(values);

        foreach (var value in values)
        {
            PutChar(value);
        }
    }

    /// <summary>Read one character, or -1 at end of stream.</summary>
    public long GetChar()
    {
        if (!Readable)
        {
            return -1;
        }

        var value = Read();

        if (value >= 0)
        {
            ReadCount++;
        }

        return value;
    }

    /// <summary>
    /// Fill a buffer; answer how many characters were read. No terminal
    /// null is placed (Glk: How To Read).
    /// </summary>
    /// <param name="buf">The array the characters land in.</param>
    public int GetBuffer(IBuffer buf)
    {
        ArgumentNullException.ThrowIfNull(buf);

        var count = 0;

        for (var index = 0; index < buf.Length; index++)
        {
            var value = GetChar();

            if (value < 0)
            {
                break;
            }

            buf[index] = (uint)value;
            count = index + 1;
        }

        return count;
    }

    /// <summary>
    /// Read up to a newline, null-terminating; answer the length.
    ///
    /// At most one less than the buffer's capacity is stored, the
    /// newline is kept if one is read, and the result is always
    /// terminated, the terminal null not counted (Glk: How To Read).
    /// </summary>
    /// <param name="buf">The array the line lands in.</param>
    public int GetLine(IBuffer buf)
    {
        ArgumentNullException.ThrowIfNull(buf);

        var capacity = buf.Length;

        if (capacity == 0)
        {
            return 0;
        }

        var count = 0;

        while (count < capacity - 1)
        {
            var value = GetChar();

            if (value < 0)
            {
                break;
            }

            buf[count] = (uint)value;
            count++;

            if (value == Characters.Newline)
            {
                break;
            }
        }

        buf[count] = 0;

        return count;
    }

    /// <summary>The stream's mark; zero where seeking is meaningless.</summary>
    public virtual long GetPosition() => 0;

    /// <summary>
    /// Move the mark. Ignored where seeking is meaningless: window
    /// streams have no position at all (Glk: Stream Positions), which is
    /// why doing nothing is the base.
    /// </summary>
    /// <param name="position">Where to move to, in the mode's terms.</param>
    /// <param name="mode">What the position is measured from.</param>
    public virtual void SetPosition(long position, uint mode)
    {
        // A stream with no position has nowhere to move to.
    }

    /// <summary>
    /// Close, answering stream_result_t (Glk: Closing Streams).
    /// </summary>
    public virtual (uint Read, uint Write) Close()
    {
        Disposed = true;

        return (ReadCount, WriteCount);
    }

    /// <summary>Actually place the character. Each kind overrides.</summary>
    /// <param name="character">The character to place.</param>
    protected virtual void Emit(uint character)
    {
        // The base stream holds nothing, so the character goes nowhere.
    }

    /// <summary>Actually fetch a character. Each kind overrides.</summary>
    protected virtual long Read() => -1;
}

/// <summary>
/// A window's output stream, never readable (Glk: Window Streams).
///
/// Always Unicode: the byte-stream rule, substitute '?' above 0xFF, is
/// about how a stream stores characters, which for a memory or file
/// stream is a real constraint and for a window is not. A window shows
/// text, and what it can render is the display's affair. The reference
/// glkapi.js sets the same flag on the same object.
/// </summary>
public sealed class StreamOnWindow : StreamObject
{
    /// <summary>Bind to the window whose output this is.</summary>
    /// <param name="window">The window that holds what is written.</param>
    /// <param name="rock">The value the game files the stream under.</param>
    public StreamOnWindow(Window window, uint rock = 0)
        : base(rock, writable: true, unicode: true) => Window = window;

    /// <summary>The window whose output this is.</summary>
    public Window Window { get; }

    /// <inheritdoc/>
    protected override void Emit(uint character) => Window.PutChar(character);
}

/// <summary>
/// A stream over an array in the game's memory (Glk: Memory Streams).
///
/// The buffer is whatever the bridge hands over, a live view, so writes
/// land straight in VM memory. A null buffer is legal: the stream then
/// discards writes but still counts them, which is how a game measures
/// output length (Glk: Memory Streams).
/// </summary>
public sealed class StreamOnMemory : StreamObject
{
    /// <summary>Open over a buffer, in a file mode's directions.</summary>
    /// <param name="buf">The array to work over, or null to discard.</param>
    /// <param name="fmode">The mode naming which directions are open.</param>
    /// <param name="rock">The value the game files the stream under.</param>
    /// <param name="unicode">Whether the array holds words rather than bytes.</param>
    public StreamOnMemory(IBuffer? buf, uint fmode, uint rock = 0, bool unicode = false)
        : base(
            rock,
            readable: fmode is GlkFileMode.Read or GlkFileMode.ReadWrite,
            writable: fmode is GlkFileMode.Write or GlkFileMode.ReadWrite or GlkFileMode.WriteAppend,
            unicode: unicode) => Buffer = buf;

    /// <summary>The array being worked over, or null.</summary>
    public IBuffer? Buffer { get; }

    /// <summary>The buffer's length; zero for the null buffer.</summary>
    public int Capacity => Buffer?.Length ?? 0;

    /// <summary>The mark, in characters from the buffer's start.</summary>
    public int Position { get; private set; }

    /// <inheritdoc/>
    public override long GetPosition() => Position;

    /// <summary>
    /// Move the mark, clamped to the buffer (Glk: Stream Positions).
    /// </summary>
    /// <param name="position">Where to move to, in the mode's terms.</param>
    /// <param name="mode">What the position is measured from.</param>
    public override void SetPosition(long position, uint mode)
    {
        if (mode == SeekMode.Current)
        {
            position += Position;
        }
        else if (mode == SeekMode.End)
        {
            position += Capacity;
        }

        Position = (int)Math.Max(0, Math.Min(position, Capacity));
    }

    /// <summary>
    /// Store within the buffer; advance past its end regardless.
    ///
    /// The position advancing past the end is what lets a game discover
    /// how much output it would have produced.
    /// </summary>
    /// <param name="character">The character to store.</param>
    protected override void Emit(uint character)
    {
        if (Buffer is not null && Position < Buffer.Length)
        {
            Buffer[Position] = character;
        }

        Position++;
    }

    /// <inheritdoc/>
    protected override long Read()
    {
        if (Buffer is null || Position >= Buffer.Length)
        {
            return -1;
        }

        var value = Buffer[Position];
        Position++;

        return value;
    }
}

/// <summary>
/// A stream over a file (Glk: File Streams).
///
/// Four combinations, and they are all different: a byte stream holds
/// one Latin-1 byte per character in either mode; a Unicode stream
/// holds four-byte big-endian words in binary mode and UTF-8, with no
/// byte-order mark, in text mode (Glk: File Streams).
///
/// The UTF-8 case is what makes a text file written through
/// glk_stream_open_file_uni readable by anything else, and
/// byte-identical to one written through glk_stream_open_file when only
/// ASCII is involved, which the specification requires.
/// </summary>
public sealed class StreamOnFile : StreamObject, IDisposable
{
    // The UTF-8 lead-byte thresholds: below the first is ASCII, and each
    // of the others starts a sequence of that many bytes.
    private const int AsciiLimit = 0x80;
    private const int LeadTwo = 0xC0;
    private const int LeadThree = 0xE0;
    private const int LeadFour = 0xF0;

    private static readonly UTF8Encoding Strict = new(false, true);

    /// <summary>Wrap an open binary handle in a file mode's directions.</summary>
    /// <param name="handle">The open file.</param>
    /// <param name="fmode">The mode naming which directions are open.</param>
    /// <param name="rock">The value the game files the stream under.</param>
    /// <param name="unicode">Whether the stream holds full words.</param>
    /// <param name="textMode">Whether the file holds text rather than bytes.</param>
    public StreamOnFile(
        Stream handle,
        uint fmode,
        uint rock = 0,
        bool unicode = false,
        bool textMode = false)
        : base(
            rock,
            readable: fmode is GlkFileMode.Read or GlkFileMode.ReadWrite,
            writable: fmode is GlkFileMode.Write or GlkFileMode.ReadWrite or GlkFileMode.WriteAppend,
            unicode: unicode)
    {
        Handle = handle;
        Utf8 = unicode && textMode;
        Width = unicode && !textMode ? 4 : 1;
    }

    /// <summary>The open file this stream reads and writes.</summary>
    public Stream Handle { get; }

    /// <summary>Whether characters travel as UTF-8 sequences.</summary>
    public bool Utf8 { get; }

    /// <summary>How many bytes one character takes, outside UTF-8.</summary>
    public int Width { get; }

    /// <summary>The mark, straight from the handle.</summary>
    public override long GetPosition() => Handle.Position;

    /// <summary>
    /// Move the mark; an unknown mode measures from the start.
    /// </summary>
    /// <param name="position">Where to move to, in the mode's terms.</param>
    /// <param name="mode">What the position is measured from.</param>
    public override void SetPosition(long position, uint mode) =>
        Handle.Seek(
            position,
            mode switch
            {
                SeekMode.Current => SeekOrigin.Current,
                SeekMode.End => SeekOrigin.End,
                _ => SeekOrigin.Begin,
            });

    /// <summary>Close the file along with the stream.</summary>
    public override (uint Read, uint Write) Close()
    {
        var counts = base.Close();

        Handle.Dispose();

        return counts;
    }

    /// <summary>Let the handle go, whether or not the stream was closed.</summary>
    public void Dispose() => Handle.Dispose();

    /// <summary>Encode one character the way this stream's mode does.</summary>
    /// <param name="character">The character to encode.</param>
    protected override void Emit(uint character)
    {
        if (Utf8)
        {
            Handle.Write(Strict.GetBytes(Characters.ToChar(character)));

            return;
        }

        Span<byte> word = stackalloc byte[Width];

        for (var at = 0; at < Width; at++)
        {
            word[at] = (byte)(character >> (8 * (Width - 1 - at)));
        }

        Handle.Write(word);
    }

    /// <summary>Decode one character, or -1 at end of file.</summary>
    protected override long Read()
    {
        if (Utf8)
        {
            return ReadUtf8();
        }

        Span<byte> word = stackalloc byte[Width];

        if (Handle.ReadAtLeast(word, Width, throwOnEndOfStream: false) < Width)
        {
            return -1;
        }

        long value = 0;

        foreach (var piece in word)
        {
            value = (value << 8) | piece;
        }

        return value;
    }

    /// <summary>
    /// Decode one UTF-8 sequence, one byte at a time.
    ///
    /// The length is read off the leading byte rather than decoding the
    /// whole file, because a stream may be positioned anywhere and the
    /// caller wants exactly one character.
    /// </summary>
    private long ReadUtf8()
    {
        var first = Handle.ReadByte();

        if (first < 0)
        {
            return -1;
        }

        if (first < AsciiLimit)
        {
            return first;
        }

        int extra;

        if (first >= LeadFour)
        {
            extra = 3;
        }
        else if (first >= LeadThree)
        {
            extra = 2;
        }
        else if (first >= LeadTwo)
        {
            extra = 1;
        }
        else
        {
            // A stray continuation byte.
            return Characters.Unprintable;
        }

        var sequence = new byte[extra + 1];
        sequence[0] = (byte)first;

        if (Handle.ReadAtLeast(sequence.AsSpan(1), extra, throwOnEndOfStream: false) < extra)
        {
            return Characters.Unprintable;
        }

        try
        {
            return char.ConvertToUtf32(Strict.GetString(sequence), 0);
        }
        catch (DecoderFallbackException)
        {
            return Characters.Unprintable;
        }
    }
}
