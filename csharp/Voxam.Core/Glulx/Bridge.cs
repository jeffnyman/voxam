using System.Text;
using Voxam.Core.Glulx.Glk;

namespace Voxam.Core.Glulx;

/// <summary>
/// Two-way mapping between Glk objects and the ids Glulx sees.
///
/// The reference glkop.c keeps a hash table per class and seeds each
/// with a randomized offset, so that games cannot come to depend on
/// particular id values. Voxam assigns ids sequentially instead:
/// reproducible ids make transcript-diffing against a reference
/// interpreter possible, which is the best correctness test available,
/// and nothing in the specification requires randomness.
///
/// Ids are unique across classes and never reused, but lookups are
/// still class-checked, so passing a stream id where a window is
/// expected reads as the null object rather than as the wrong object.
/// </summary>
public sealed class Registry
{
    private const int ClassCount = 4;

    private readonly Dictionary<uint, GlkObject>[] _byId =
        [.. Enumerable.Range(0, ClassCount).Select(_ => new Dictionary<uint, GlkObject>())];

    private readonly Dictionary<GlkObject, uint> _byObject = [];

    private uint _next = 1;

    /// <summary>
    /// The object's id, minted if it is new; the null object is zero.
    /// </summary>
    /// <param name="held">The object to name, or null.</param>
    /// <param name="glkClass">Which of the four classes it belongs to.</param>
    public uint Register(GlkObject? held, int glkClass)
    {
        if (held is null)
        {
            return 0;
        }

        if (_byObject.TryGetValue(held, out var existing))
        {
            return existing;
        }

        var ident = _next;
        _next++;
        _byObject[held] = ident;
        _byId[glkClass][ident] = held;

        return ident;
    }

    /// <summary>The object an id names within a class, or null.</summary>
    /// <param name="glkClass">Which of the four classes to look in.</param>
    /// <param name="ident">The id the game passed.</param>
    public GlkObject? Lookup(int glkClass, uint ident) =>
        ident != 0 && _byId[glkClass].TryGetValue(ident, out var found) ? found : null;

    /// <summary>
    /// Drop a destroyed object, so its id stops resolving. The library
    /// reports every disposal through its own seat.
    /// </summary>
    /// <param name="held">The object that has been destroyed.</param>
    public void Forget(GlkObject held)
    {
        ArgumentNullException.ThrowIfNull(held);

        if (_byObject.Remove(held, out var ident))
        {
            _byId[held.GlkClass].Remove(ident);
        }
    }
}

/// <summary>
/// A live view onto an array in VM memory.
///
/// Deliberately not a copy. Holding coordinates and indexing lazily
/// means a retained array, one Glk keeps after the call returns such as
/// a pending line request's buffer, stays valid across a setmemsize
/// that would invalidate a snapshot. It also handles four-byte
/// elements, which a byte-oriented view does not.
///
/// Satisfies the object model's buffer contract, which is the whole
/// point: the library reads and writes it without knowing a VM exists.
///
/// The reference carries a signed flag here as well. Nothing can reach
/// it: no array in the dispatch table holds a signed type, and a buffer
/// delivers the same thirty-two bits either way, so the flag would
/// decorate rather than decide. It is left out.
/// </summary>
public sealed class MemArray : IBuffer
{
    private readonly Memory _memory;
    private readonly uint _address;
    private readonly int _size;

    /// <summary>Frame a span of memory as elements of a size.</summary>
    /// <param name="memory">The VM memory the array lives in.</param>
    /// <param name="address">Where the first element sits.</param>
    /// <param name="count">How many elements the call named.</param>
    /// <param name="elementSize">Bytes per element.</param>
    public MemArray(Memory memory, uint address, int count, int elementSize = 1)
    {
        _memory = memory;
        _address = address;
        _size = elementSize;
        Length = count;
    }

    /// <summary>The element count the call named.</summary>
    public int Length { get; }

    /// <summary>One element, read or written straight through to memory.</summary>
    /// <param name="index">Which element to reach.</param>
    public uint this[int index]
    {
        get => _memory.Read(Offset(index), _size);
        set => _memory.Write(Offset(index), _size, value);
    }

    /// <summary>The address of one element, bounds enforced.</summary>
    private int Offset(int index) => index >= 0 && index < Length
        ? (int)(_address + (uint)(index * _size))
        : throw new GlulxException($"array index {index} is outside the {Length} elements");
}

/// <summary>
/// The VM and Glk seam: argument marshalling and the object registry.
///
/// This is the only place that reads both sides. Glulx sees opaque Glk
/// objects as 32-bit ids and passes references as addresses, while the
/// library sees objects and writes into holders. The glk opcode hands
/// over a selector and a list of raw words; everything here is about
/// turning those into a call and writing the answers back into VM
/// memory or onto the stack, by the rules the specification spells out
/// under the glk opcode (Glulx: Miscellaneous).
///
/// One thing the reference does here is not done yet: a call that
/// suspends, which is glk_select and the file prompts, parks its
/// write-backs on the suspension instead of running them. Nothing can
/// suspend until the library has functions in it, so the branch waits
/// for the era that creates one, and until then every write-back runs
/// as the call returns.
/// </summary>
public sealed class Bridge
{
    /// <summary>
    /// A reference argument of -1 means "read from or write to the
    /// stack", a feature of the Glk invocation mechanism alone and not
    /// of Glulx addressing (Glulx: Miscellaneous).
    /// </summary>
    public const uint StackRef = 0xFFFFFFFF;

    private const int Word = 4;

    // The type bytes of the string objects a Glk call may name: the
    // unencoded forms, and only those (Glulx: Miscellaneous).
    private const int Unencoded = 0xE0;
    private const int UnencodedUnicode = 0xE2;

    /// <summary>Join a machine's memory and stack to a library.</summary>
    /// <param name="memory">The VM memory reference arguments live in.</param>
    /// <param name="library">The Glk library the calls land on.</param>
    /// <param name="stack">The VM stack the -1 references reach.</param>
    public Bridge(Memory memory, GlkLibrary library, StackMemory stack)
    {
        ArgumentNullException.ThrowIfNull(library);

        Memory = memory;
        Stack = stack;
        Library = library;
        Registry = new Registry();

        // The library's disposal reports go straight into the registry,
        // so a closed object's id stops resolving.
        library.OnDispose = Registry.Forget;
    }

    /// <summary>The VM memory reference arguments live in.</summary>
    public Memory Memory { get; }

    /// <summary>The VM stack the -1 references reach.</summary>
    public StackMemory Stack { get; }

    /// <summary>The Glk library the calls land on.</summary>
    public GlkLibrary Library { get; }

    /// <summary>The id mapping for the opaque classes.</summary>
    public Registry Registry { get; }

    /// <summary>
    /// Run one Glk call; answer the value the opcode stores.
    ///
    /// Stack output references push here, after the call but before the
    /// opcode's own store, the order the specification fixes (Glulx:
    /// Miscellaneous).
    /// </summary>
    /// <param name="selector">Which Glk function the opcode named.</param>
    /// <param name="args">The raw argument words, in order.</param>
    /// <exception cref="GlulxException">
    /// For a selector the dispatch table does not carry, or an argument
    /// count that contradicts its signature.
    /// </exception>
    public uint Perform(int selector, IReadOnlyList<uint> args)
    {
        ArgumentNullException.ThrowIfNull(args);

        var signature = Signatures.Lookup(selector)
            ?? throw new GlulxException(
                $"the glk opcode asked for unknown function 0x{selector:x4}");

        if (args.Count != signature.WordCount)
        {
            throw new GlulxException(
                $"{signature.GlkName} takes {signature.WordCount} argument words, "
                + $"but {args.Count} arrived");
        }

        var (callArgs, writebacks) = Unmarshal(signature, args);
        var result = Library.Call(signature, callArgs);

        foreach (var writeback in writebacks)
        {
            writeback();
        }

        return EncodeResult(signature.Result, result);
    }

    /// <summary>Turn raw words into call arguments, left to right.</summary>
    private (object?[] Args, List<Action> Writebacks) Unmarshal(
        Signature signature, IReadOnlyList<uint> args)
    {
        var callArgs = new object?[signature.Args.Count];
        var writebacks = new List<Action>();
        var position = 0;

        for (var at = 0; at < signature.Args.Count; at++)
        {
            var (value, writeback, moved) = UnmarshalItem(signature.Args[at], args, position);

            callArgs[at] = value;
            position = moved;

            if (writeback is not null)
            {
                writebacks.Add(writeback);
            }
        }

        return (callArgs, writebacks);
    }

    /// <summary>One prototype item into one call argument.</summary>
    private (object? Value, Action? Writeback, int Position) UnmarshalItem(
        Item item, IReadOnlyList<uint> args, int position)
    {
        if (item.IsArray)
        {
            var address = args[position];
            var count = args[position + 1];
            position += 2;

            if (address == 0)
            {
                RequireNullable(item);

                return (null, null, position);
            }

            if (item.IsOpaque)
            {
                // An array of object ids, only ever passed in, so a
                // snapshot is equivalent to a live view.
                var found = new GlkObject?[count];

                for (var index = 0; index < count; index++)
                {
                    found[index] = Registry.Lookup(
                        item.ClassNumber ?? 0,
                        Memory.ReadWord((int)(address + ((uint)index * Word))));
                }

                return (found, null, position);
            }

            // Writes through a live view land straight in memory, so
            // even an out-array needs no write-back step.
            return (new MemArray(Memory, address, (int)count, item.ElementSize), null, position);
        }

        if (item.IsReference)
        {
            var address = args[position];
            position += 1;

            if (address == 0)
            {
                RequireNullable(item);

                return (null, null, position);
            }

            var (value, writeback) = address == StackRef
                ? StackReference(item)
                : MemoryReference(item, address);

            return (value, writeback, position);
        }

        var raw = args[position];
        position += 1;

        return (Decode(item, raw), null, position);
    }

    /// <summary>Refuse a null address the signature marked nonnull.</summary>
    private static void RequireNullable(Item item)
    {
        if (item.NonNull)
        {
            throw new GlulxException("a null address arrived where the Glk call requires one");
        }
    }

    /// <summary>
    /// A reference argument held in main memory. The value need not be
    /// aligned, but is big-endian, which the memory layer's word
    /// accessors already are (Glulx: Miscellaneous).
    /// </summary>
    private (object Value, Action? Writeback) MemoryReference(Item item, uint address)
    {
        if (item.IsStruct)
        {
            var record = new RefStruct(item.Fields.Count);

            if (item.PassesIn)
            {
                for (var index = 0; index < item.Fields.Count; index++)
                {
                    record[index] = DecodeValue(
                        item.Fields[index],
                        Memory.ReadWord((int)(address + ((uint)index * Word))));
                }
            }

            if (!item.PassesOut)
            {
                return (record, null);
            }

            return (record, () =>
            {
                for (var index = 0; index < item.Fields.Count; index++)
                {
                    Memory.WriteWord(
                        (int)(address + ((uint)index * Word)),
                        Encode(item.Fields[index], record[index]));
                }
            }
            );
        }

        // Every scalar reference in Glk 0.7.6 is an out-reference:
        // nothing passes a bare word in by address, and only structs
        // travel inward. So a scalar opens empty and always writes back.
        // A test holds the whole table to that, so a later Glk that
        // breaks it fails there rather than quietly here.
        var reference = new Ref();

        return (reference, () => Memory.WriteWord((int)address, Encode(item, reference.Value)));
    }

    /// <summary>
    /// A reference argument of -1: the value lives on the stack.
    ///
    /// The specification spells out the ordering: an input reference is
    /// popped first-topmost, so a struct's first field is the topmost
    /// value, and an output reference is pushed last-topmost, so pushing
    /// the fields in order leaves the last one on top (Glulx:
    /// Miscellaneous). The pops happen here, after the Glk argument list
    /// has already come off the stack, which is also the order the
    /// specification requires.
    /// </summary>
    private (object Value, Action? Writeback) StackReference(Item item)
    {
        if (item.IsStruct)
        {
            var record = new RefStruct(item.Fields.Count);

            if (item.PassesIn)
            {
                for (var index = 0; index < item.Fields.Count; index++)
                {
                    record[index] = DecodeValue(item.Fields[index], Stack.Pop());
                }
            }

            if (!item.PassesOut)
            {
                return (record, null);
            }

            return (record, () =>
            {
                for (var index = 0; index < item.Fields.Count; index++)
                {
                    Stack.Push(Encode(item.Fields[index], record[index]));
                }
            }
            );
        }

        // As above: a scalar reference only ever travels outward.
        var scalar = new Ref();

        return (scalar, () => Stack.Push(Encode(item, scalar.Value)));
    }

    /// <summary>A plain argument word into what Glk should receive.</summary>
    private object Decode(Item item, uint raw) => item.IsString
        ? (item.Code == "U" ? ReadUnicodeString(raw) : ReadString(raw))
        : DecodeValue(item, raw);

    /// <summary>
    /// A word into an object, or into itself.
    ///
    /// The reference turns a signed item's word into a negative number
    /// here. A hold carries thirty-two bits and no sign, so the reading
    /// happens where the value is used instead: the signature already
    /// says which arguments are signed, and the function that receives
    /// one knows it.
    /// </summary>
    private Held DecodeValue(Item item, uint raw) => item.IsOpaque
        ? Held.OfOpaque(Registry.Lookup(item.ClassNumber ?? 0, raw))
        : Held.OfWord(raw);

    /// <summary>A held value back into a 32-bit word.</summary>
    private uint Encode(Item item, Held value) => item.IsOpaque
        ? Registry.Register(value.Opaque, item.ClassNumber ?? 0)
        : value.Word;

    /// <summary>
    /// The result as a word; a void call stores zero (Glulx:
    /// Miscellaneous).
    /// </summary>
    private uint EncodeResult(Item? item, Held value) =>
        item is null ? 0 : Encode(item, value);

    /// <summary>
    /// Read an unencoded (E0) string object.
    ///
    /// A string argument is the address of a string object, not of a
    /// bare byte array: the type byte comes first and the text ends at a
    /// zero byte (Glulx: Miscellaneous).
    /// </summary>
    private string ReadString(uint address)
    {
        var kind = Memory.ReadByte((int)address);

        if (kind != Unencoded)
        {
            throw new GlulxException(
                $"the Glk string argument at 0x{address:x} is not an E0 string object "
                + $"(found 0x{kind:x2})");
        }

        var at = address + 1;
        var built = new List<byte>();

        while (true)
        {
            var character = Memory.ReadByte((int)at);

            if (character == 0)
            {
                return Encoding.Latin1.GetString([.. built]);
            }

            built.Add((byte)character);
            at++;
        }
    }

    /// <summary>
    /// Read an unencoded Unicode (E2) string object. An E2 object is a
    /// type byte and three padding bytes, so the characters start four
    /// bytes in (Glulx: String Encoding).
    /// </summary>
    private string ReadUnicodeString(uint address)
    {
        var kind = Memory.ReadByte((int)address);

        if (kind != UnencodedUnicode)
        {
            throw new GlulxException(
                $"the Glk Unicode string argument at 0x{address:x} is not an E2 string object "
                + $"(found 0x{kind:x2})");
        }

        var at = address + Word;
        var built = new StringBuilder();

        while (true)
        {
            var character = Memory.ReadWord((int)at);

            if (character == 0)
            {
                return built.ToString();
            }

            // A Glulx string may hold values that are not code points at
            // all; they render as the placeholder. The rule here is the
            // reference's own and not the object model's: only what is
            // past the last code point is refused, so a lone surrogate
            // travels as itself rather than becoming a placeholder.
            built.Append(character <= Characters.MaxUnicode
                ? Rendered(character)
                : Characters.ToChar(Characters.Unprintable));

            at += Word;
        }
    }

    /// <summary>
    /// One code point as text, the surrogate block included. Anything
    /// inside the Unicode range is what it says it is here.
    /// </summary>
    private static string Rendered(uint character) => character <= char.MaxValue
        ? ((char)character).ToString()
        : char.ConvertFromUtf32((int)character);
}
