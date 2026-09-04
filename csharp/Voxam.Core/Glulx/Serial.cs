using System.Text;

namespace Voxam.Core.Glulx;

/// <summary>
/// Saving and restoring the machine state.
///
/// The format is Quetzal with Glulx's own chunks (Glulx: The
/// Save-Game Format): IFhd identifies the story as the first 128
/// bytes of memory, CMem holds dynamic memory XOR-compressed against
/// the game file, MAll the allocation heap, and Stks the stack whole.
///
/// What is not saved matters as much (Glulx: State Not Saved): Glk
/// state, the protected range, the random number generator, the I/O
/// system, and the string-decoding table address all survive a
/// restore untouched.
///
/// The stack chunk is a straight copy. The specification requires
/// stack values written big-endian, and the reference glulxe has to
/// walk each frame's locals format to byte-swap them, but this stack
/// chose big-endian storage in its own era for exactly this moment,
/// so saving is a snapshot and restoring is the reverse, the locals
/// format never consulted.
///
/// The IFF walking below is this module's own. The Python shares one
/// reader between the Z-machine and Glulx; the port has the
/// Z-machine's inside its own Quetzal, entangled with that machine's
/// refusals, and a shared reader is a road rather than this branch's
/// business.
/// </summary>
public static class Serial
{
    /// <summary>Success, as the opcodes speak it (Glulx: Game State).</summary>
    public const uint Succeeded = 0;

    /// <summary>Failure, as the opcodes speak it (Glulx: Game State).</summary>
    public const uint Failed = 1;

    // IFhd is the first 128 bytes of memory, always in ROM, since
    // RAMSTART is at least 256 (Glulx: Associated Story File).
    private const int IdentityLength = 128;

    // How many undo states to keep; the reference glulxe keeps the
    // same number.
    private const int MaxUndoLevels = 8;

    private const int HeaderSize = 8;
    private const int TypeSize = 4;
    private const int LengthSize = 4;
    private const int LongestRun = 0x100;

    /// <summary>
    /// A complete save file for the current state.
    ///
    /// The caller must already have pushed the four-value call stub
    /// the specification requires, since it forms part of the stack
    /// chunk (Glulx: Contents of the Stack). An MAll chunk is written
    /// only while the heap is active; an inactive heap's chunk may be
    /// omitted (Glulx: Memory Allocation Heap).
    /// </summary>
    public static byte[] Serialize(Machine machine)
    {
        var body = new List<byte>();
        body.AddRange(Chunk("IFhd", machine.Memory.ReadRun(0, IdentityLength)));
        body.AddRange(Chunk("CMem", EncodeMemory(machine)));

        var summary = machine.Heap.Summary();

        if (summary.Count > 0)
        {
            body.AddRange(Chunk("MAll", [.. summary.SelectMany(Word)]));
        }

        body.AddRange(Chunk("Stks", machine.Stack.Snapshot()));

        return [.. Ascii("FORM"), .. Word((uint)(TypeSize + body.Count)), .. Ascii("IFZS"), .. body];
    }

    /// <summary>
    /// Restore the state a save file holds.
    ///
    /// Order matters: the live heap is dropped first, since it does
    /// not survive into the restored state and its shrink must land
    /// before the memory chunk sets the size, then memory, then the
    /// heap summary above it, then the stack.
    /// </summary>
    /// <exception cref="GlulxException">
    /// For bytes that are not an IFZS container, a story that is not
    /// this one, a missing chunk, or a heap summary that contradicts
    /// itself.
    /// </exception>
    public static void Deserialize(Machine machine, byte[] data)
    {
        var chunks = Walk(data);

        if (!chunks.TryGetValue("IFhd", out var identity))
        {
            throw new GlulxException("the save file has no IFhd chunk to name its story");
        }

        if (!identity.AsSpan().SequenceEqual(machine.Memory.ReadRun(0, IdentityLength)))
        {
            throw new GlulxException("the save file belongs to a different story");
        }

        machine.Heap.Clear();

        if (chunks.TryGetValue("CMem", out var compressed))
        {
            DecodeMemory(machine, compressed);
        }
        else if (chunks.TryGetValue("UMem", out var plain))
        {
            DecodePlainMemory(machine, plain);
        }
        else
        {
            throw new GlulxException("the save file has no memory chunk");
        }

        var heap = chunks.GetValueOrDefault("MAll", []);
        machine.Heap.ApplySummary([.. Enumerable.Range(0, heap.Length / 4).Select(at => Word32(heap, at * 4))]);

        if (!chunks.TryGetValue("Stks", out var stack))
        {
            throw new GlulxException("the save file has no Stks chunk");
        }

        machine.Stack.Restore(stack);
    }

    /// <summary>
    /// The saveundo opcode's work: the state into the undo chain. The
    /// chain keeps the newest handful of states; saving past the limit
    /// lets the oldest go, the way the reference does.
    /// </summary>
    public static uint SaveUndo(Machine machine)
    {
        machine.UndoChain.Add(Serialize(machine));

        if (machine.UndoChain.Count > MaxUndoLevels)
        {
            machine.UndoChain.RemoveRange(0, machine.UndoChain.Count - MaxUndoLevels);
        }

        return Succeeded;
    }

    /// <summary>
    /// The restoreundo opcode's work: the newest undo state back. An
    /// empty chain fails with 1; a successful restore consumes the
    /// state it restored.
    /// </summary>
    public static uint RestoreUndo(Machine machine)
    {
        if (machine.UndoChain.Count == 0)
        {
            return Failed;
        }

        var state = machine.UndoChain[^1];
        machine.UndoChain.RemoveAt(machine.UndoChain.Count - 1);
        Deserialize(machine, state);

        return Succeeded;
    }

    /// <summary>
    /// The hasundo opcode's answer: 0 with a state waiting, 1 bare. A
    /// zero here is a promise that restoreundo will succeed (Glulx:
    /// Game State).
    /// </summary>
    public static uint HasUndo(Machine machine) => machine.UndoChain.Count > 0 ? Succeeded : Failed;

    /// <summary>The discardundo opcode's work: let the newest state go.</summary>
    public static void DiscardUndo(Machine machine)
    {
        if (machine.UndoChain.Count > 0)
        {
            machine.UndoChain.RemoveAt(machine.UndoChain.Count - 1);
        }
    }

    // RAM as a CMem body: XOR'd against the original, then packed. A
    // run of zeroes is written as a zero byte followed by the run
    // length less one, so one pair encodes up to 256; a trailing run
    // is dropped entirely, because the decoder treats anything past
    // the chunk's end as unchanged (Glulx: Contents of Dynamic
    // Memory).
    private static byte[] EncodeMemory(Machine machine)
    {
        var memory = machine.Memory;
        var length = memory.EndMem - memory.RamStart;
        var difference = Different(memory, length);
        var body = new List<byte>(Word((uint)memory.EndMem));
        var index = 0;

        while (index < length)
        {
            if (difference[index] != 0)
            {
                body.Add(difference[index]);
                index++;

                continue;
            }

            var run = 0;

            while (index + run < length && difference[index + run] == 0)
            {
                run++;
            }

            if (index + run == length)
            {
                break;
            }

            while (run > 0)
            {
                var step = Math.Min(run, LongestRun);
                body.Add(0);
                body.Add((byte)(step - 1));
                run -= step;
                index += step;
            }
        }

        return [.. body];
    }

    // Undo the CMem encoding into the live memory map.
    private static void DecodeMemory(Machine machine, byte[] body)
    {
        var memory = machine.Memory;
        memory.SetSize(MemorySize(body));

        var length = memory.EndMem - memory.RamStart;
        var difference = new List<byte>();
        var cursor = LengthSize;

        // The loop runs over the compressed data, which is mostly
        // runs, not over every byte of RAM.
        while (cursor < body.Length && difference.Count < length)
        {
            var value = body[cursor];
            cursor++;

            if (value != 0)
            {
                difference.Add(value);

                continue;
            }

            if (cursor >= body.Length)
            {
                throw new GlulxException("a zero byte ends the memory chunk with no run length");
            }

            difference.AddRange(new byte[body[cursor] + 1]);
            cursor++;
        }

        var contents = new byte[length];
        var original = memory.OriginalRun(memory.RamStart, length);

        for (var at = 0; at < length; at++)
        {
            contents[at] = (byte)((at < difference.Count ? difference[at] : 0) ^ original[at]);
        }

        memory.OverwriteRam(contents);
    }

    // A UMem chunk: the new size, then raw RAM.
    private static void DecodePlainMemory(Machine machine, byte[] body)
    {
        var memory = machine.Memory;
        memory.SetSize(MemorySize(body));

        var length = Math.Min(memory.EndMem - memory.RamStart, body.Length - LengthSize);

        memory.OverwriteRam(body[LengthSize..(LengthSize + length)]);
    }

    // The XOR of live RAM against what the game file held there.
    private static byte[] Different(Memory memory, int length)
    {
        var current = memory.ReadRun(memory.RamStart, length);
        var original = memory.OriginalRun(memory.RamStart, length);
        var difference = new byte[length];

        for (var at = 0; at < length; at++)
        {
            difference[at] = (byte)(current[at] ^ original[at]);
        }

        return difference;
    }

    // The four-byte size a memory chunk opens with.
    private static uint MemorySize(byte[] body) => body.Length < LengthSize
        ? throw new GlulxException("the save file's memory chunk cannot hold its own size")
        : Word32(body, 0);

    // The chunks of an IFZS FORM, by name.
    private static Dictionary<string, byte[]> Walk(byte[] data)
    {
        if (data.Length < HeaderSize + TypeSize || Ascii(data, 0) != "FORM")
        {
            throw new GlulxException("the save file is not an IFF container: no FORM chunk to open it (Quetzal 8.5)");
        }

        var length = (int)Word32(data, 4);

        if (HeaderSize + length > data.Length)
        {
            throw new GlulxException($"the FORM chunk claims {length} bytes, but the file has only {data.Length - HeaderSize} after its header (Quetzal 8.3.5)");
        }

        var kind = Ascii(data, 8);

        if (kind != "IFZS")
        {
            throw new GlulxException($"the save file is a {kind} FORM, not Quetzal's IFZS");
        }

        var found = new Dictionary<string, byte[]>(StringComparer.Ordinal);
        var position = HeaderSize + TypeSize;
        var end = HeaderSize + length;

        while (position < end)
        {
            if (position + HeaderSize > end)
            {
                throw new GlulxException("a chunk is cut short mid-header (Quetzal 8.3.1)");
            }

            var id = Ascii(data, position);
            var size = (int)Word32(data, position + 4);
            position += HeaderSize;

            if (position + size > end)
            {
                throw new GlulxException($"the {id} chunk claims {size} bytes, but the FORM ends before them (Quetzal 8.4)");
            }

            found[id] = data[position..(position + size)];
            position += size + (size % 2);
        }

        return found;
    }

    // One IFF chunk: its name, its length, its payload, and the pad
    // byte an odd length takes.
    private static byte[] Chunk(string id, byte[] payload) => payload.Length % 2 == 0
        ? [.. Ascii(id), .. Word((uint)payload.Length), .. payload]
        : [.. Ascii(id), .. Word((uint)payload.Length), .. payload, 0];

    private static byte[] Word(uint value) => [(byte)(value >> 24), (byte)(value >> 16), (byte)(value >> 8), (byte)value];

    private static uint Word32(byte[] data, int at) =>
        ((uint)data[at] << 24) | ((uint)data[at + 1] << 16) | ((uint)data[at + 2] << 8) | data[at + 3];

    private static byte[] Ascii(string text) => Encoding.ASCII.GetBytes(text);

    private static string Ascii(byte[] data, int at) => Encoding.ASCII.GetString(data, at, 4);
}
