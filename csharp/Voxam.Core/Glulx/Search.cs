namespace Voxam.Core.Glulx;

/// <summary>
/// The built-in search opcodes (Glulx: Searching).
///
/// All three look through fixed-size structures in memory for one
/// whose key matches. They exist for speed: Inform's property and
/// dictionary lookups dominate its running time, and the
/// specification notes Advent runs 15 to 20% faster with
/// binary-search property lookup than with the equivalent Inform
/// code.
///
/// Keys are compared as byte strings. The reference glulxe carries
/// two comparison paths, short keys copied into a stack buffer and
/// long keys re-read from memory on every comparison, because
/// buffering would mean allocating. Here the key is fetched once and
/// every comparison is a span compare. The equivalence holds because
/// a search never writes memory, and a span of bytes orders
/// lexicographically over unsigned bytes, which is exactly the
/// big-endian unsigned ordering the sorted form requires.
/// </summary>
public static class Search
{
    /// <summary>The index form's failure answer (Glulx: Searching).</summary>
    public const uint NotFoundIndex = 0xFFFFFFFF;

    /// <summary>The address form's failure answer (Glulx: Searching).</summary>
    public const uint NotFoundAddress = 0;

    // The Options flags. Not every flag applies to every search:
    // ReturnIndex means nothing to linkedsearch, and
    // ZeroKeyTerminates nothing to binarysearch.
    private const uint KeyIndirect = 0x01;
    private const uint ZeroKeyTerminates = 0x02;
    private const uint ReturnIndex = 0x04;

    /// <summary>
    /// Search an array of structures in order (Glulx: Searching). A
    /// count of 0xFFFFFFFF means no upper limit: the search then runs
    /// until it matches or, with ZeroKeyTerminates, until it meets an
    /// all-zero key.
    /// </summary>
    public static uint Linear(Memory memory, uint key, uint keysize, uint start, uint structsize, uint numstructs, uint keyoffset, uint options)
    {
        var wanted = Key(memory, key, keysize, options);
        var index = (options & ReturnIndex) != 0;
        var stops = (options & ZeroKeyTerminates) != 0;
        var zeros = new byte[keysize];
        var address = start;

        for (var count = 0u; count < numstructs; count++)
        {
            var entry = memory.ReadRun((int)(address + keyoffset), keysize);

            if (entry.AsSpan().SequenceEqual(wanted))
            {
                return index ? count : address;
            }

            // Checked after the match, so a search for the all-zero
            // key still finds it rather than stopping short.
            if (stops && entry.AsSpan().SequenceEqual(zeros))
            {
                break;
            }

            address += structsize;
        }

        return index ? NotFoundIndex : NotFoundAddress;
    }

    /// <summary>
    /// Search a key-ordered array of structures (Glulx: Searching).
    /// The structures must sit in ascending key order with no
    /// duplicates, and the count must be exact: the unlimited
    /// 0xFFFFFFFF is not legal here, and ZeroKeyTerminates does not
    /// apply.
    /// </summary>
    public static uint Binary(Memory memory, uint key, uint keysize, uint start, uint structsize, uint numstructs, uint keyoffset, uint options)
    {
        var wanted = Key(memory, key, keysize, options);
        var index = (options & ReturnIndex) != 0;
        var low = 0u;
        var high = numstructs;

        while (low < high)
        {
            var middle = low + ((high - low) / 2);
            var address = start + (middle * structsize);
            var entry = memory.ReadRun((int)(address + keyoffset), keysize);
            var order = entry.AsSpan().SequenceCompareTo(wanted);

            if (order == 0)
            {
                return index ? middle : address;
            }

            if (order < 0)
            {
                low = middle + 1;
            }
            else
            {
                high = middle;
            }
        }

        return index ? NotFoundIndex : NotFoundAddress;
    }

    /// <summary>
    /// Follow a linked list of structures (Glulx: Searching). A zero
    /// in the link field ends the list. ReturnIndex does not apply,
    /// a list having no indexes, so the answer is an address or zero.
    /// </summary>
    public static uint Linked(Memory memory, uint key, uint keysize, uint start, uint keyoffset, uint nextoffset, uint options)
    {
        var wanted = Key(memory, key, keysize, options);
        var stops = (options & ZeroKeyTerminates) != 0;
        var zeros = new byte[keysize];
        var address = start;

        while (address != 0)
        {
            var entry = memory.ReadRun((int)(address + keyoffset), keysize);

            if (entry.AsSpan().SequenceEqual(wanted))
            {
                return address;
            }

            if (stops && entry.AsSpan().SequenceEqual(zeros))
            {
                break;
            }

            address = memory.ReadWord((int)(address + nextoffset));
        }

        return NotFoundAddress;
    }

    // The key operand as the bytes every entry compares against. With
    // KeyIndirect the operand is the key's address and any size is
    // legal; without it the operand is the key itself, sitting in the
    // low bytes big-endian, and must fit a word (Glulx: Searching).
    private static byte[] Key(Memory memory, uint key, uint keysize, uint options)
    {
        if ((options & KeyIndirect) != 0)
        {
            return memory.ReadRun((int)key, keysize);
        }

        if (keysize is not (1 or 2 or 4))
        {
            throw new GlulxException($"a direct search key must hold one, two, or four bytes, not {keysize} (Glulx: Searching)");
        }

        var bytes = new byte[keysize];

        for (var at = 0; at < keysize; at++)
        {
            bytes[keysize - 1 - at] = (byte)(key >> (8 * at));
        }

        return bytes;
    }
}
