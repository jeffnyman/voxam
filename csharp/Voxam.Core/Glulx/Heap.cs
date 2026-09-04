namespace Voxam.Core.Glulx;

/// <summary>One span of the heap, allocated or free.</summary>
public sealed class Block(int address, long length, bool free)
{
    /// <summary>Where the span begins.</summary>
    public int Address { get; } = address;

    /// <summary>How many bytes it covers.</summary>
    public long Length { get; set; } = length;

    /// <summary>Whether the span is unclaimed.</summary>
    public bool Free { get; set; } = free;
}

/// <summary>
/// The dynamic allocation heap (Glulx: Memory Allocation Heap).
///
/// Allocated blocks live above ENDMEM. The first malloc activates the
/// heap: the current end of memory becomes the heap's start address,
/// and the map grows from there. Freeing the last block deactivates
/// it and shrinks memory back to where it began, at which point
/// setmemsize becomes legal again.
///
/// The block list covers the heap completely and in address order:
/// the first block starts at the heap's start, each one ends where
/// the next begins, and the last ends at ENDMEM. Free blocks are part
/// of that list rather than a separate free list, which is why
/// coalescing is something the allocator does as it searches.
///
/// The bookkeeping lives here, not in the memory map, so a game
/// writing outside its blocks cannot corrupt it: the specification
/// says the interpreter may keep it in a private data structure, and
/// this does exactly that. Writing anywhere in the heap range stays
/// legal.
/// </summary>
public sealed class Heap(Memory memory)
{
    // Memory grows in 256-byte units, like every Glulx boundary.
    private const long Boundary = 0x100;

    private readonly Memory _memory = memory;
    private readonly List<Block> _blocks = [];

    /// <summary>The heap's start address; zero means inactive.</summary>
    public int Start { get; private set; }

    /// <summary>How many blocks are currently allocated.</summary>
    public int AllocCount { get; private set; }

    /// <summary>Whether any block is extant, which is to say the heap owns the map.</summary>
    public bool Active => Start != 0;

    /// <summary>Every span, allocated and free, in address order.</summary>
    public IReadOnlyList<Block> Blocks => _blocks;

    /// <summary>
    /// Deactivate the heap and give its memory back. Freeing the last
    /// block lands here, and so does a restart: the heap does not
    /// survive one (Glulx: Memory Allocation Heap).
    /// </summary>
    public void Clear()
    {
        _blocks.Clear();

        if (Start != 0)
        {
            _memory.SetSize(Start);
        }

        Start = 0;
        AllocCount = 0;
    }

    /// <summary>
    /// Claim a span; the address comes back, or zero on failure.
    /// Allocation is never guaranteed: a refusal is an answer, not an
    /// error (Glulx: Memory Allocation Heap).
    /// </summary>
    /// <exception cref="GlulxException">
    /// For a zero-length request, which no answer could name.
    /// </exception>
    public uint Alloc(long length)
    {
        if (length == 0)
        {
            throw new GlulxException("a heap allocation must ask for at least one byte");
        }

        var index = FindFree(length) ?? Extend(length);

        if (index is not { } at)
        {
            return 0;
        }

        var block = _blocks[at];

        if (block.Length > length)
        {
            // Split, leaving the remainder free and the list still in
            // address order.
            _blocks.Insert(at + 1, new Block(block.Address + (int)length, block.Length - length, true));
            block.Length = length;
        }

        block.Free = false;
        AllocCount++;

        return (uint)block.Address;
    }

    /// <summary>
    /// Release the block at an address, which must be extant. Freeing
    /// the last block deactivates the heap and hands the memory back
    /// (Glulx: Memory Allocation Heap).
    /// </summary>
    /// <exception cref="GlulxException">
    /// For an address that names no allocated block.
    /// </exception>
    public void Free(uint address)
    {
        var block = _blocks.Find(span => span.Address == address && !span.Free)
            ?? throw new GlulxException($"no allocated heap block begins at 0x{address:x}");

        block.Free = true;
        AllocCount--;

        if (AllocCount <= 0)
        {
            Clear();
        }
    }

    /// <summary>
    /// The heap as the save format's MAll words: start, count, then
    /// the address and length of each extant block (Glulx: Memory
    /// Allocation Heap). An inactive heap summarizes as nothing at
    /// all, and its chunk is omitted.
    /// </summary>
    public IReadOnlyList<uint> Summary()
    {
        if (!Active)
        {
            return [];
        }

        var values = new List<uint> { (uint)Start, (uint)AllocCount };

        foreach (var block in _blocks)
        {
            if (!block.Free)
            {
                values.Add((uint)block.Address);
                values.Add((uint)block.Length);
            }
        }

        return values;
    }

    /// <summary>
    /// Rebuild the heap from a summary's words.
    ///
    /// Memory must already be the size it was when the summary was
    /// taken, restoring the map being the caller's job, and the free
    /// blocks are reconstructed from the gaps between extant ones, out
    /// to ENDMEM.
    /// </summary>
    /// <exception cref="GlulxException">
    /// When the heap is already active, the summary's pairs are cut
    /// short, or its blocks are out of address order.
    /// </exception>
    public void ApplySummary(IReadOnlyList<uint> values)
    {
        if (Active)
        {
            throw new GlulxException("a heap summary cannot land on an active heap");
        }

        // Fewer than two words says nothing, and two zeroes say the
        // heap was inactive when the summary was taken.
        if (values.Count < 2 || (values[0] == 0 && values[1] == 0))
        {
            return;
        }

        var extant = values.Skip(2).ToList();

        if (extant.Count % 2 != 0)
        {
            throw new GlulxException("the save file's heap summary is cut short mid-block");
        }

        for (var at = 0; at + 2 < extant.Count; at += 2)
        {
            if (extant[at] >= extant[at + 2])
            {
                throw new GlulxException("the save file's heap blocks are out of address order");
            }
        }

        Start = (int)values[0];
        AllocCount = (int)values[1];
        _blocks.Clear();

        var position = 0;
        var cursor = Start;
        var endmem = _memory.EndMem;

        while (position < extant.Count || cursor < endmem)
        {
            if (position >= extant.Count)
            {
                // Trailing free space, out to the end of the map.
                _blocks.Add(new Block(cursor, endmem - cursor, true));

                break;
            }

            var address = (int)extant[position];

            if (cursor < address)
            {
                // A gap before the next extant block is free space.
                _blocks.Add(new Block(cursor, address - cursor, true));
                cursor = address;

                continue;
            }

            _blocks.Add(new Block(address, extant[position + 1], false));
            position += 2;
            cursor = address + (int)extant[position - 1];
        }
    }

    // First-fit search, coalescing free neighbors on the way. Merging
    // happens during the search rather than eagerly, as the reference
    // glulxe has it: a run of free blocks is only joined up when
    // something actually needs the space.
    private int? FindFree(long length)
    {
        var index = 0;

        while (index < _blocks.Count)
        {
            var block = _blocks[index];

            if (block.Free && block.Length >= length)
            {
                return index;
            }

            if (!block.Free)
            {
                index++;

                continue;
            }

            var following = index + 1 < _blocks.Count ? _blocks[index + 1] : null;

            if (following is null || !following.Free)
            {
                index++;

                continue;
            }

            // Free, too small, and followed by free space: merge and
            // retry at the same position rather than advancing.
            block.Length += following.Length;
            _blocks.RemoveAt(index + 1);
        }

        return null;
    }

    // Grow the map; the new free block's index comes back. The heap
    // doubles, or grows by the requested length, or by one boundary,
    // whichever is largest, rounded up to the 256-byte grain.
    private int? Extend(long length)
    {
        long oldEndMem = _memory.EndMem;
        var extension = Start != 0 ? oldEndMem - Start : 0;
        extension = Math.Max(Math.Max(extension, length), Boundary);
        extension = (extension + Boundary - 1) & ~(Boundary - 1);

        try
        {
            _memory.SetSize(oldEndMem + extension);
        }
        catch (Exception error) when (error is GlulxException or OutOfMemoryException)
        {
            // Allocation is never guaranteed (Glulx: Memory
            // Allocation Heap).
            return null;
        }

        if (Start == 0)
        {
            Start = (int)oldEndMem;
        }

        if (_blocks.Count > 0 && _blocks[^1].Free)
        {
            _blocks[^1].Length += extension;
        }
        else
        {
            _blocks.Add(new Block((int)oldEndMem, extension, true));
        }

        return _blocks.Count - 1;
    }
}
