namespace Voxam.Core.Glulx;

/// <summary>
/// Glulx main memory: the ROM/RAM map (Glulx: The Memory Map).
///
/// Addresses 0 to RAMSTART are ROM, the header included, and writing
/// there is illegal; RAM runs from RAMSTART to ENDMEM. The game file
/// stores only the bytes up to EXTSTART, and everything above starts
/// zeroed; once execution begins there is no difference between the
/// memory below and above that line. Unlike the stack, memory has no
/// alignment rule: a four-byte read at an odd address is legal
/// Glulx.
/// </summary>
public sealed class Memory
{
    // The operand widths a read or write may come in: the spec's
    // bytes, shorts and 32-bit words (Glulx: The Memory Map).
    private const int ByteWidth = 1;
    private const int ShortWidth = 2;
    private const int WordWidth = 4;
    private const int Boundary = 256;

    private readonly byte[] _image;
    private readonly int _bootEndMem;
    private byte[] _data;
    private int _endMem;
    private int _protectStart;
    private int _protectEnd;

    /// <summary>
    /// Lay the stored image into a map grown to ENDMEM.
    ///
    /// The story already held the header to its promises, the
    /// boundaries aligned, ordered, and ROM big enough for the
    /// header, so none of that is re-litigated here.
    /// </summary>
    public Memory(Story story)
    {
        _image = story.Data;
        _bootEndMem = story.EndMem;
        _data = [];
        RamStart = story.RamStart;

        Reset();
    }

    /// <summary>The first writable address (Glulx: The Memory Map).</summary>
    public int RamStart { get; }

    /// <summary>
    /// The current end of the memory map. Kept as its own number
    /// rather than read off the backing store: every bounds check
    /// consults it.
    /// </summary>
    public int EndMem => _endMem;

    /// <summary>
    /// The raw backing store, for the instruction decoder only.
    /// Everything else goes through the accessors. The decoder reads
    /// several bytes per instruction from an ever-advancing program
    /// counter, and per-call overhead there is the machine's single
    /// largest cost; it does its own bounds test inline instead. The
    /// array is replaced whole when the map is resized, so nothing
    /// may hold on to it across a setmemsize.
    /// </summary>
    public byte[] Data => _data;

    /// <summary>Read one byte anywhere in the map.</summary>
    /// <exception cref="GlulxException">For an address outside the map.</exception>
    public int ReadByte(int address)
    {
        if (address < 0 || address >= _endMem)
        {
            throw new GlulxException(OutOfRange(address));
        }

        return _data[address];
    }

    /// <summary>Read a big-endian 16-bit short, any alignment.</summary>
    /// <exception cref="GlulxException">For a short running outside the map.</exception>
    public int ReadShort(int address)
    {
        if (address < 0 || address > _endMem - ShortWidth)
        {
            throw new GlulxException(OutOfRange(address));
        }

        return (_data[address] << 8) | _data[address + 1];
    }

    /// <summary>Read a big-endian 32-bit word, any alignment.</summary>
    /// <exception cref="GlulxException">For a word running outside the map.</exception>
    public uint ReadWord(int address)
    {
        if (address < 0 || address > _endMem - WordWidth)
        {
            throw new GlulxException(OutOfRange(address));
        }

        return ((uint)_data[address] << 24) | ((uint)_data[address + 1] << 16) | ((uint)_data[address + 2] << 8) | _data[address + 3];
    }

    /// <summary>Read at an operand's width: 1, 2 or 4 bytes.</summary>
    /// <exception cref="GlulxException">For an access outside the map.</exception>
    public uint Read(int address, int width) => width switch
    {
        WordWidth => ReadWord(address),
        ByteWidth => (uint)ReadByte(address),
        _ => (uint)ReadShort(address),
    };

    /// <summary>Read a run of bytes; an empty run needs no address at all.</summary>
    /// <exception cref="GlulxException">For a run leaving the map.</exception>
    public byte[] ReadRun(int address, long count)
    {
        if (count == 0)
        {
            return [];
        }

        RequireReadable(address, count);

        return _data[address..(int)(address + count)];
    }

    /// <summary>Write one byte into RAM, the value masked to 8 bits.</summary>
    /// <exception cref="GlulxException">For a write into ROM or outside the map.</exception>
    public void WriteByte(int address, uint value)
    {
        if (address < RamStart || address >= _endMem)
        {
            throw new GlulxException(RefusedWrite(address, RamStart));
        }

        _data[address] = (byte)value;
    }

    /// <summary>Write a big-endian short into RAM, masked to 16 bits.</summary>
    /// <exception cref="GlulxException">For a write into ROM or outside the map.</exception>
    public void WriteShort(int address, uint value)
    {
        if (address < RamStart || address > _endMem - ShortWidth)
        {
            throw new GlulxException(RefusedWrite(address, RamStart));
        }

        _data[address] = (byte)(value >> 8);
        _data[address + 1] = (byte)value;
    }

    /// <summary>Write a big-endian word into RAM, masked to 32 bits.</summary>
    /// <exception cref="GlulxException">For a write into ROM or outside the map.</exception>
    public void WriteWord(int address, uint value)
    {
        if (address < RamStart || address > _endMem - WordWidth)
        {
            throw new GlulxException(RefusedWrite(address, RamStart));
        }

        _data[address] = (byte)(value >> 24);
        _data[address + 1] = (byte)(value >> 16);
        _data[address + 2] = (byte)(value >> 8);
        _data[address + 3] = (byte)value;
    }

    /// <summary>Write at an operand's width: 1, 2 or 4 bytes.</summary>
    /// <exception cref="GlulxException">For a write into ROM or outside the map.</exception>
    public void Write(int address, int width, uint value)
    {
        if (width == WordWidth)
        {
            WriteWord(address, value);
        }
        else if (width == ByteWidth)
        {
            WriteByte(address, value);
        }
        else
        {
            WriteShort(address, value);
        }
    }

    /// <summary>Write a run of bytes into RAM; an empty run writes nowhere.</summary>
    /// <exception cref="GlulxException">For a run touching ROM or leaving the map.</exception>
    public void WriteRun(int address, byte[] data)
    {
        if (data.Length == 0)
        {
            return;
        }

        RequireWritable(address, data.Length);
        data.CopyTo(_data, address);
    }

    /// <summary>Set a run of RAM bytes to one value: mzero's work.</summary>
    /// <exception cref="GlulxException">For a run touching ROM or leaving the map.</exception>
    public void Fill(int address, long count, uint value = 0)
    {
        if (count == 0)
        {
            return;
        }

        RequireWritable(address, count);
        Array.Fill(_data, (byte)value, address, (int)count);
    }

    /// <summary>
    /// Copy a run within memory: mcopy's work. Overlap comes out
    /// right, the source being read whole before a byte lands.
    /// </summary>
    /// <exception cref="GlulxException">
    /// For a source leaving the map, or a destination touching ROM or
    /// leaving it.
    /// </exception>
    public void Copy(int destination, int source, long count)
    {
        if (count == 0)
        {
            return;
        }

        RequireReadable(source, count);
        RequireWritable(destination, count);
        Array.Copy(_data, source, _data, destination, (int)count);
    }

    /// <summary>
    /// Resize the memory map: setmemsize's work.
    ///
    /// Growth is zero-filled and shrinkage discards, but the map
    /// never shrinks below its boot ENDMEM, and every size sits on
    /// the 256-byte boundary the header's numbers do (Glulx: Game
    /// State). Refusing this while the allocation heap is active is
    /// the caller's duty when the heap era arrives: memory has no
    /// business knowing about the heap.
    /// </summary>
    /// <exception cref="GlulxException">
    /// For a size off its boundary or below the boot ENDMEM.
    /// </exception>
    public void SetSize(long size)
    {
        if (size % Boundary != 0)
        {
            throw new GlulxException($"a memory size of {size} is not a multiple of {Boundary} (Glulx: Game State)");
        }

        if (size < _bootEndMem)
        {
            throw new GlulxException($"memory cannot shrink to {size}, below the {_bootEndMem} it booted with (Glulx: Game State)");
        }

        // The same ceiling the header is held to, and for the same
        // reason: a map this machine cannot lay out is refused in
        // words rather than by failing to allocate.
        if (size > Story.Ceiling)
        {
            throw new GlulxException($"a memory size of {size} is larger than this machine can map (Glulx: Game State)");
        }

        Array.Resize(ref _data, (int)size);
        _endMem = (int)size;
    }

    /// <summary>
    /// Mark the range restart and restore leave alone: protect's
    /// work. One range exists at a time, a zero length turns
    /// protection off, and the range itself is deliberately not part
    /// of saved state (Glulx: Game State).
    /// </summary>
    public void SetProtection(int start, int length)
    {
        if (length == 0)
        {
            _protectStart = 0;
            _protectEnd = 0;
        }
        else
        {
            _protectStart = start;
            _protectEnd = start + length;
        }
    }

    /// <summary>
    /// What the game file held over a span; zeroes past its end.
    ///
    /// The compressed save format XORs live RAM against the original
    /// image, as if the game file were extended with as many zeroes
    /// as necessary above EXTSTART (Glulx: The Save-Game Format).
    /// Whole spans rather than single bytes, because everything that
    /// asks XORs the answer, and Inform calls saveundo every turn.
    /// </summary>
    public byte[] OriginalRun(int address, int count)
    {
        var run = new byte[count];
        var stored = Math.Clamp(_image.Length - address, 0, count);

        if (stored > 0)
        {
            Array.Copy(_image, address, run, 0, stored);
        }

        return run;
    }

    /// <summary>
    /// Lay restored RAM in from RAMSTART, sparing protection.
    ///
    /// The protected range is silently unaffected by a restore
    /// (Glulx: Game State). Skipping the writes is the right model
    /// rather than saving and replacing the bytes, because the
    /// restore may have resized memory underneath the range: a range
    /// beyond the new end must come back zeroed by the resize, not
    /// repopulated from the file.
    /// </summary>
    public void OverwriteRam(byte[] contents)
    {
        var start = RamStart;
        var end = start + contents.Length;
        var low = Math.Max(_protectStart, start);
        var high = Math.Min(_protectEnd, end);

        if (high <= low)
        {
            contents.CopyTo(_data, start);

            return;
        }

        if (low > start)
        {
            Array.Copy(contents, 0, _data, start, low - start);
        }

        if (high < end)
        {
            Array.Copy(contents, high - start, _data, high, end - high);
        }
    }

    /// <summary>
    /// Restore the boot image whole: restart's work.
    ///
    /// The protected range is silently unaffected (Glulx: Game
    /// State), with no qualification about where it lies, so it
    /// survives even above EXTSTART, where the reference glulxe loses
    /// it by zero-filling without consulting the range; quixe keeps
    /// it, and the spec's words side with quixe. The map also returns
    /// to its boot size: a setmemsize grown map does not survive a
    /// restart.
    /// </summary>
    public void Reset()
    {
        var saved = ProtectedCopy();
        _data = new byte[_bootEndMem];
        _endMem = _bootEndMem;
        _image.CopyTo(_data, 0);

        PasteProtected(saved);
    }

    // The protected range's live bytes, null when none is set.
    private (int Start, byte[] Data)? ProtectedCopy()
    {
        var start = _protectStart;
        var end = Math.Min(_protectEnd, _endMem);

        return end <= start ? null : (start, _data[start..end]);
    }

    // Lay the protected bytes back, clipped to the new map.
    private void PasteProtected((int Start, byte[] Data)? saved)
    {
        if (saved is not { } range)
        {
            return;
        }

        var end = Math.Min(range.Start + range.Data.Length, _endMem);

        if (end > range.Start)
        {
            Array.Copy(range.Data, 0, _data, range.Start, end - range.Start);
        }
    }

    // Hold a run to the map (Glulx: The Memory Map). Element counts
    // arrive as exact integers, so the overflow gymnastics glulxe
    // needs when a count times a size wraps its 32-bit arithmetic
    // cannot happen here: the naive check is the correct one.
    private void RequireReadable(int address, long count)
    {
        if (address < 0 || address > _endMem - count)
        {
            throw new GlulxException(OutOfRange(address));
        }
    }

    // Hold a run to RAM (Glulx: The Memory Map).
    private void RequireWritable(int address, long count)
    {
        if (address < RamStart || address > _endMem - count)
        {
            throw new GlulxException(RefusedWrite(address, RamStart));
        }
    }

    // The one message every out-of-map access carries.
    private static string OutOfRange(int address) => $"the address ${address:x} is outside the memory map (Glulx: The Memory Map)";

    // Why a write was refused: ROM below RAMSTART, or off the map.
    private static string RefusedWrite(int address, int ramStart) => address < ramStart
        ? $"the address ${address:x} is in ROM, which ends at ${ramStart:x}: it is illegal to write there (Glulx: The Memory Map)"
        : OutOfRange(address);
}
