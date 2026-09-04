using System.Buffers.Binary;

namespace Voxam.Core.Glulx;

/// <summary>
/// Where a call stub's result lands (Glulx: Call Stubs).
///
/// The specification prints the string-resume values as "10"
/// through "14" with no radix marker, in a document that writes hex
/// bare everywhere else. Both reference implementations read them as
/// hexadecimal, glulxe's pop_callstub switching on 0x10 through 0x14
/// and quixe doing the same, so they are 16 through 20, not 10
/// through 14.
/// </summary>
public enum DestType : uint
{
    Discard = 0,
    Memory = 1,
    Local = 2,
    Stack = 3,

    /// <summary>Resuming an E1 compressed string; DestAddr holds the bit number within the byte.</summary>
    ResumeCompressed = 0x10,

    /// <summary>Resuming function code after a string finishes.</summary>
    ResumeFunction = 0x11,

    /// <summary>Resuming a signed decimal print; Pc holds the number itself.</summary>
    ResumeNumber = 0x12,

    /// <summary>Resuming an E0 C-string.</summary>
    ResumeCString = 0x13,

    /// <summary>Resuming an E2 Unicode string.</summary>
    ResumeUnicode = 0x14,
}

/// <summary>The four words a call, catch, or string print leaves behind (Glulx: Call Stubs).</summary>
public readonly record struct CallStub(DestType DestType, uint DestAddr, uint Pc, uint FramePtr);

/// <summary>
/// One LocalType/LocalCount pair from a locals-format list: a width
/// of 1, 2 or 4 bytes, and how many locals wear it (Glulx: The Call
/// Frame).
/// </summary>
public readonly record struct LocalsFormat(int Size, int Count);

/// <summary>
/// The Glulx stack: call frames, locals, and call stubs.
///
/// Byte-addressed and growing upward from zero (Glulx: The Stack),
/// the stack is where every function call builds its frame, a
/// header, a locals-format list, the zeroed locals themselves, and
/// where every call leaves a four-word stub saying how to come home
/// (Glulx: The Call Frame, Glulx: Call Stubs). Unlike main memory,
/// stack access is strictly aligned: shorts at even offsets, words
/// at multiples of four. A program that breaks that has undefined
/// behavior, and undefined behavior gets caught here rather than
/// tolerated.
///
/// Two settled rulings ride along from the Python. The byte order is
/// big-endian even though the specification leaves it to the
/// interpreter and the reference glulxe uses native order: the save
/// format stores the stack big-endian (Glulx: Contents of the
/// Stack), so storing it that way in the first place makes saving a
/// straight copy. And local references are bounds-checked: the
/// specification is explicit that a local reference must not point
/// outside the range of the current function's locals segment, a
/// check glulxe skips with a note that a strict interpreter probably
/// should make. Voxam is that strict interpreter.
/// </summary>
public sealed class StackMemory
{
    /// <summary>A call stub is four 32-bit words (Glulx: Call Stubs).</summary>
    public const int StubSize = 16;

    /// <summary>A frame opens with FrameLen and LocalsPos, four bytes each (Glulx: The Call Frame).</summary>
    public const int FrameHeaderSize = 8;

    // A locals-format entry is a LocalType byte and a LocalCount
    // byte; the legal types are 1, 2 and 4 (Glulx: The Call Frame).
    private const int FormatEntrySize = 2;
    private const int LocalCountLimit = 255;
    private const int ByteWidth = 1;
    private const int ShortWidth = 2;
    private const int WordWidth = 4;
    private const int Boundary = 256;
    private const int ShortAlignMask = 0b1;
    private const int WordAlignMask = 0b11;

    private readonly int _size;
    private byte[] _data;

    /// <summary>
    /// Raise an empty stack of the header's declared size, a multiple
    /// of 256 at least 256 tall (Glulx: The Stack).
    /// </summary>
    /// <exception cref="GlulxException">For a size below or off that convenience.</exception>
    public StackMemory(int size)
    {
        if (size < Boundary || size % Boundary != 0)
        {
            throw new GlulxException($"a stack of {size} bytes is not a multiple of {Boundary} at least {Boundary} tall (Glulx: The Stack)");
        }

        _size = size;
        _data = new byte[size];
    }

    /// <summary>The stack's full height in bytes.</summary>
    public int Size => _size;

    /// <summary>The stack pointer, counting bytes from zero.</summary>
    public int Sp { get; private set; }

    /// <summary>Where the current call frame begins.</summary>
    public int FramePtr { get; private set; }

    /// <summary>Where its locals segment begins: what the locals addressing modes and DestType 2 offset from.</summary>
    public int LocalsBase { get; private set; }

    /// <summary>Where its value stack begins: the floor pops may not pass.</summary>
    public int ValStackBase { get; private set; }

    /// <summary>Words above the current frame: stkcount's answer.</summary>
    public int Count => (Sp - ValStackBase) / WordWidth;

    /// <summary>Clear the stack whole: restart's share of the work.</summary>
    public void Reset()
    {
        Array.Clear(_data);
        Sp = 0;
        FramePtr = 0;
        LocalsBase = 0;
        ValStackBase = 0;
    }

    /// <summary>
    /// The live bytes, ready for a save file's stack chunk. A
    /// straight copy: the save format wants big-endian values (Glulx:
    /// Contents of the Stack) and that is already how the stack
    /// stores them.
    /// </summary>
    public byte[] Snapshot() => _data[..Sp];

    /// <summary>
    /// Replace the stack from a snapshot. The frame registers stay
    /// zeroed: a restore is completed by popping the call stub the
    /// saver pushed, and until then the bases mean nothing.
    /// </summary>
    /// <exception cref="GlulxException">
    /// For a snapshot taller than this stack or not a whole number of
    /// words long.
    /// </exception>
    public void Restore(byte[] data)
    {
        if (data.Length > _size)
        {
            throw new GlulxException($"a saved stack of {data.Length} bytes cannot fit this interpreter's {_size}-byte stack (Glulx: Contents of the Stack)");
        }

        if (data.Length % WordWidth != 0)
        {
            throw new GlulxException($"a saved stack of {data.Length} bytes is not a whole number of words (Glulx: Contents of the Stack)");
        }

        _data = new byte[_size];
        data.CopyTo(_data, 0);
        Sp = data.Length;
        FramePtr = 0;
        LocalsBase = 0;
        ValStackBase = 0;
    }

    /// <summary>Read one byte of the stack.</summary>
    /// <exception cref="GlulxException">For a position off the stack.</exception>
    public uint ReadByte(int position)
    {
        if (position < 0 || position >= _size)
        {
            throw new GlulxException(Refused(position, ByteWidth, _size));
        }

        return _data[position];
    }

    /// <summary>Read a big-endian short at an even position.</summary>
    /// <exception cref="GlulxException">For a position off the stack or off its natural alignment.</exception>
    public uint ReadShort(int position)
    {
        if (position < 0 || position > _size - ShortWidth || (position & ShortAlignMask) != 0)
        {
            throw new GlulxException(Refused(position, ShortWidth, _size));
        }

        return BinaryPrimitives.ReadUInt16BigEndian(_data.AsSpan(position));
    }

    /// <summary>Read a big-endian word at a multiple of four.</summary>
    /// <exception cref="GlulxException">For a position off the stack or off its natural alignment.</exception>
    public uint ReadWord(int position)
    {
        if (position < 0 || position > _size - WordWidth || (position & WordAlignMask) != 0)
        {
            throw new GlulxException(Refused(position, WordWidth, _size));
        }

        return BinaryPrimitives.ReadUInt32BigEndian(_data.AsSpan(position));
    }

    /// <summary>Read at a local's width: 1, 2 or 4 bytes.</summary>
    /// <exception cref="GlulxException">For a position off the stack or off the width's alignment.</exception>
    public uint Read(int position, int width) => width switch
    {
        WordWidth => ReadWord(position),
        ByteWidth => ReadByte(position),
        _ => ReadShort(position),
    };

    /// <summary>Write one byte of the stack, masked to 8 bits.</summary>
    /// <exception cref="GlulxException">For a position off the stack.</exception>
    public void WriteByte(int position, uint value)
    {
        if (position < 0 || position >= _size)
        {
            throw new GlulxException(Refused(position, ByteWidth, _size));
        }

        _data[position] = (byte)value;
    }

    /// <summary>Write a big-endian short at an even position, masked to 16 bits.</summary>
    /// <exception cref="GlulxException">For a position off the stack or off its natural alignment.</exception>
    public void WriteShort(int position, uint value)
    {
        if (position < 0 || position > _size - ShortWidth || (position & ShortAlignMask) != 0)
        {
            throw new GlulxException(Refused(position, ShortWidth, _size));
        }

        BinaryPrimitives.WriteUInt16BigEndian(_data.AsSpan(position), (ushort)value);
    }

    /// <summary>Write a big-endian word at a multiple of four, masked to 32 bits.</summary>
    /// <exception cref="GlulxException">For a position off the stack or off its natural alignment.</exception>
    public void WriteWord(int position, uint value)
    {
        if (position < 0 || position > _size - WordWidth || (position & WordAlignMask) != 0)
        {
            throw new GlulxException(Refused(position, WordWidth, _size));
        }

        BinaryPrimitives.WriteUInt32BigEndian(_data.AsSpan(position), value);
    }

    /// <summary>Write at a local's width: 1, 2 or 4 bytes.</summary>
    /// <exception cref="GlulxException">For a position off the stack or off the width's alignment.</exception>
    public void Write(int position, int width, uint value)
    {
        if (width == WordWidth)
        {
            WriteWord(position, value);
        }
        else if (width == ByteWidth)
        {
            WriteByte(position, value);
        }
        else
        {
            WriteShort(position, value);
        }
    }

    /// <summary>Push one word, masked to 32 bits.</summary>
    /// <exception cref="GlulxException">On overflow (Glulx: The Stack).</exception>
    public void Push(uint value)
    {
        if (Sp + WordWidth > _size)
        {
            throw new GlulxException($"the {_size}-byte stack overflowed (Glulx: The Stack)");
        }

        BinaryPrimitives.WriteUInt32BigEndian(_data.AsSpan(Sp), value);
        Sp += WordWidth;
    }

    /// <summary>Pop one word.</summary>
    /// <exception cref="GlulxException">
    /// On popping past the frame's value stack into the call frame
    /// itself (Glulx: The Call Frame).
    /// </exception>
    public uint Pop()
    {
        if (Sp < ValStackBase + WordWidth)
        {
            throw new GlulxException("the stack underflowed: popping past the value stack would eat the call frame (Glulx: The Call Frame)");
        }

        Sp -= WordWidth;

        return BinaryPrimitives.ReadUInt32BigEndian(_data.AsSpan(Sp));
    }

    /// <summary>Read a value without popping; depth 0 is the topmost.</summary>
    /// <exception cref="GlulxException">
    /// For a depth reaching past the frame's value stack: stkpeek's
    /// own error case.
    /// </exception>
    public uint Peek(int depth = 0)
    {
        var position = Sp - (WordWidth * (depth + 1));

        if (position < ValStackBase)
        {
            throw new GlulxException($"a peek {depth} deep reaches past the value stack (Glulx: The Call Frame)");
        }

        return BinaryPrimitives.ReadUInt32BigEndian(_data.AsSpan(position));
    }

    /// <summary>Push DestType, DestAddr, PC and FramePtr (Glulx: Call Stubs).</summary>
    /// <exception cref="GlulxException">On overflow.</exception>
    public void PushStub(DestType desttype, uint destaddr, uint pc)
    {
        if (Sp + StubSize > _size)
        {
            throw new GlulxException($"the {_size}-byte stack overflowed pushing a call stub (Glulx: Call Stubs)");
        }

        WriteWord(Sp, (uint)desttype);
        WriteWord(Sp + 4, destaddr);
        WriteWord(Sp + 8, pc);
        WriteWord(Sp + 12, (uint)FramePtr);
        Sp += StubSize;
    }

    /// <summary>
    /// Pop a call stub, restoring FramePtr and the derived bases. The
    /// program counter and the storing of any result stay the
    /// caller's business: what those mean depends on the DestType
    /// (Glulx: Call Stubs).
    /// </summary>
    /// <exception cref="GlulxException">On underflow.</exception>
    public CallStub PopStub()
    {
        if (Sp < StubSize)
        {
            throw new GlulxException("the stack underflowed popping a call stub (Glulx: Call Stubs)");
        }

        Sp -= StubSize;
        var stub = new CallStub(
            (DestType)ReadWord(Sp),
            ReadWord(Sp + 4),
            ReadWord(Sp + 8),
            ReadWord(Sp + 12));

        FramePtr = (int)stub.FramePtr;
        ValStackBase = FramePtr + (int)ReadWord(FramePtr);
        LocalsBase = FramePtr + (int)ReadWord(FramePtr + 4);

        return stub;
    }

    /// <summary>
    /// Build a call frame at the stack pointer and make it current.
    ///
    /// The locals arrive zeroed; placing arguments is the caller's
    /// business, since that depends on whether the function is the
    /// stack-argument or local-argument kind. Each run of locals pads
    /// up to its own natural alignment before it starts, the segment
    /// pads to a word, and the written format list ends with a zero
    /// pair, twice where that is what keeps it word-aligned (Glulx:
    /// The Call Frame).
    /// </summary>
    /// <exception cref="GlulxException">
    /// For a local type other than 1, 2 or 4, a count outside a byte,
    /// or a frame that would overflow the stack.
    /// </exception>
    public void PushFrame(IReadOnlyList<LocalsFormat> localsFormat)
    {
        foreach (var entry in localsFormat)
        {
            if (entry.Size is not (ByteWidth or ShortWidth or WordWidth))
            {
                throw new GlulxException($"a locals-format list may hold types 1, 2, and 4, not {entry.Size} (Glulx: The Call Frame)");
            }

            if (entry.Count < 0 || entry.Count > LocalCountLimit)
            {
                throw new GlulxException($"a locals-format count of {entry.Count} does not fit its byte (Glulx: The Call Frame)");
            }
        }

        var localsLength = 0;

        foreach (var entry in localsFormat)
        {
            localsLength = Aligned(localsLength, entry.Size) + (entry.Size * entry.Count);
        }

        localsLength = Aligned(localsLength, WordWidth);

        var written = new List<LocalsFormat>(localsFormat) { new(0, 0) };

        if (written.Count % 2 != 0)
        {
            written.Add(new LocalsFormat(0, 0));
        }

        var formatLength = FormatEntrySize * written.Count;
        var frameptr = Sp;
        var localsbase = frameptr + FrameHeaderSize + formatLength;
        var valstackbase = localsbase + localsLength;

        if (valstackbase >= _size)
        {
            throw new GlulxException($"the {_size}-byte stack overflowed building a call frame (Glulx: The Call Frame)");
        }

        FramePtr = frameptr;
        LocalsBase = localsbase;
        ValStackBase = valstackbase;

        WriteWord(frameptr, (uint)(FrameHeaderSize + formatLength + localsLength));
        WriteWord(frameptr + 4, (uint)(FrameHeaderSize + formatLength));

        var position = frameptr + FrameHeaderSize;

        foreach (var entry in written)
        {
            _data[position] = (byte)entry.Size;
            _data[position + 1] = (byte)entry.Count;
            position += FormatEntrySize;
        }

        Array.Clear(_data, localsbase, localsLength);
        Sp = valstackbase;
    }

    /// <summary>Discard the current frame and everything pushed above it.</summary>
    public void LeaveFrame() => Sp = FramePtr;

    /// <summary>
    /// Unwind to a catch token: throw's work (Glulx: Continuations).
    /// Whether the token is a place on this stack is the machine's to
    /// say, since only it knows what a token may be; what follows is
    /// the call stub that token stands above.
    /// </summary>
    public void Unwind(int position) => Sp = position;

    /// <summary>The current frame's whole length, off its own header.</summary>
    public uint FrameLen => ReadWord(FramePtr);

    /// <summary>Where the locals sit within the frame, off its header.</summary>
    public uint LocalsPos => ReadWord(FramePtr + 4);

    /// <summary>The locals segment's length in bytes, padding included.</summary>
    public int LocalsLength => ValStackBase - LocalsBase;

    /// <summary>Read the current frame's format list back off the stack.</summary>
    public IReadOnlyList<LocalsFormat> ReadLocalsFormat()
    {
        var entries = new List<LocalsFormat>();
        var position = FramePtr + FrameHeaderSize;

        while (position + FormatEntrySize <= LocalsBase)
        {
            int size = _data[position];

            if (size == 0)
            {
                break;
            }

            entries.Add(new LocalsFormat(size, _data[position + 1]));
            position += FormatEntrySize;
        }

        return entries;
    }

    /// <summary>
    /// Read a local by its offset from LocalsBase: what the locals
    /// addressing modes and a call stub's DestType 2 both carry.
    /// </summary>
    /// <exception cref="GlulxException">
    /// For a reference outside the locals segment, the specification's
    /// "must not point outside" made a real check, or off its
    /// alignment.
    /// </exception>
    public uint GetLocal(int offset, int width = WordWidth)
    {
        if (offset < 0 || offset > ValStackBase - LocalsBase - width)
        {
            throw new GlulxException(RefusedLocal(offset));
        }

        return Read(LocalsBase + offset, width);
    }

    /// <summary>Write a local by its offset from LocalsBase, masked to its width.</summary>
    /// <exception cref="GlulxException">
    /// For a reference outside the locals segment or off its
    /// alignment.
    /// </exception>
    public void SetLocal(int offset, uint value, int width = WordWidth)
    {
        if (offset < 0 || offset > ValStackBase - LocalsBase - width)
        {
            throw new GlulxException(RefusedLocal(offset));
        }

        Write(LocalsBase + offset, width, value);
    }

    // The value rounded up to its width's natural alignment.
    private static int Aligned(int value, int alignment)
    {
        var remainder = value % alignment;

        return remainder == 0 ? value : value + alignment - remainder;
    }

    // Why a stack access was refused: off the stack, or unaligned.
    private static string Refused(int position, int width, int size) => position < 0 || position > size - width
        ? $"a {width}-byte access at {position} is off the {size}-byte stack (Glulx: The Stack)"
        : $"a {width}-byte stack access at {position} is off its natural alignment (Glulx: The Call Frame)";

    // The reference glulxe skips this check, noting that a strict
    // mode interpreter probably should make it; an unchecked
    // reference reads the frame header or a neighboring frame, which
    // is silent corruption instead of a diagnosable fault.
    private static string RefusedLocal(int offset) =>
        $"a local reference at offset {offset} points outside the current function's locals segment (Glulx: The Call Frame)";
}
