using Voxam.Core.Glulx;
using Voxam.Core.Glulx.Glk;
using GlulxException = Voxam.Core.GlulxException;

namespace Voxam.Tests.Glulx.Glk;

/// <summary>
/// A library that serves whatever a test asks it to, so the seam can be
/// exercised before there are real functions on the other side of it.
/// </summary>
internal sealed class TestLibrary : GlkLibrary
{
    public List<object?[]> Calls { get; } = [];

    public void Offer(int selector, Func<object?[], Held> handler) => Serve(selector, handler);

    public void Record(int selector, Held answer = default) =>
        Serve(selector, args =>
        {
            Calls.Add(args);

            return answer;
        });
}

/// <summary>
/// The VM and Glk seam: ids in both directions, references in memory
/// and on the stack, arrays as live views, and string objects read out
/// of memory (Glulx: Miscellaneous).
/// </summary>
public sealed class BridgeTests
{
    private const int Ram = 300;

    // Ids are minted in order and never reused, which is what makes a
    // session's transcript comparable against another interpreter's.
    [Fact]
    public void IdsAreMintedInOrderAndKept()
    {
        var registry = new Registry();
        var first = new BlankWindow();
        var second = new TextGridWindow();

        Assert.Equal(1u, registry.Register(first, OpaqueClass.Window));
        Assert.Equal(2u, registry.Register(second, OpaqueClass.Window));
        Assert.Equal(1u, registry.Register(first, OpaqueClass.Window));
        Assert.Same(first, registry.Lookup(OpaqueClass.Window, 1));
        Assert.Same(second, registry.Lookup(OpaqueClass.Window, 2));
    }

    // The null object is zero in both directions, and zero is nothing
    // at all rather than the first object.
    [Fact]
    public void TheNullObjectIsZero()
    {
        var registry = new Registry();

        Assert.Equal(0u, registry.Register(null, OpaqueClass.Window));
        Assert.Null(registry.Lookup(OpaqueClass.Window, 0));
    }

    // Ids are unique across classes but lookups are class-checked, so a
    // stream id where a window is expected reads as the null object
    // rather than as the wrong object.
    [Fact]
    public void LookupsAreCheckedAgainstTheirClass()
    {
        var registry = new Registry();
        var window = new BlankWindow();
        var stream = window.Stream;

        var windowId = registry.Register(window, OpaqueClass.Window);
        var streamId = registry.Register(stream, OpaqueClass.Stream);

        Assert.NotEqual(windowId, streamId);
        Assert.Null(registry.Lookup(OpaqueClass.Window, streamId));
        Assert.Null(registry.Lookup(OpaqueClass.Stream, windowId));
        Assert.Same(stream, registry.Lookup(OpaqueClass.Stream, streamId));
    }

    // A destroyed object's id stops resolving, and forgetting one that
    // was never registered is no error.
    [Fact]
    public void AForgottenObjectStopsResolving()
    {
        var registry = new Registry();
        var window = new BlankWindow();
        var ident = registry.Register(window, OpaqueClass.Window);

        registry.Forget(window);

        Assert.Null(registry.Lookup(OpaqueClass.Window, ident));

        registry.Forget(new BlankWindow());

        Assert.Throws<ArgumentNullException>(() => registry.Forget(null!));
    }

    // The library's disposal seat is wired into the registry when the
    // bridge is built, so a library that reports a closure has the id
    // dropped for it.
    [Fact]
    public void TheLibrarysDisposalReportsReachTheRegistry()
    {
        var (bridge, library) = Seam();
        var window = new BlankWindow();
        var ident = bridge.Registry.Register(window, OpaqueClass.Window);

        library.OnDispose!(window);

        Assert.Null(bridge.Registry.Lookup(OpaqueClass.Window, ident));
    }

    // A live view reads and writes straight through to memory, in the
    // element width its item declared.
    [Theory]
    [InlineData(1, 0x12u)]
    [InlineData(4, 0x12345678u)]
    public void AnArrayViewReachesMemoryInItsOwnWidth(int width, uint value)
    {
        var memory = Mapped();
        var array = new MemArray(memory, Ram, 3, width);

        Assert.Equal(3, array.Length);

        array[1] = value;

        Assert.Equal(value, array[1]);
        Assert.Equal(value, memory.Read(Ram + width, width));
    }

    // An index outside the array is refused rather than reaching some
    // other part of memory.
    [Theory]
    [InlineData(-1)]
    [InlineData(3)]
    public void AnIndexOutsideTheArrayIsRefused(int index)
    {
        var array = new MemArray(Mapped(), Ram, 3, 4);

        Assert.Equal(
            $"array index {index} is outside the 3 elements",
            Assert.Throws<GlulxException>(() => array[index]).Message);
        Assert.Throws<GlulxException>(() => array[index] = 1);
    }

    // A game asking for a selector this Glk lacks expects a library from
    // the future; that should be loud.
    [Fact]
    public void AnUnknownSelectorIsRefused()
    {
        var (bridge, _) = Seam();

        Assert.Equal(
            "the glk opcode asked for unknown function 0x0002",
            Assert.Throws<GlulxException>(() => bridge.Perform(0x0002, [])).Message);
    }

    // An argument count that contradicts the signature is refused by
    // name, with both counts said out loud.
    [Fact]
    public void AnArgumentCountThatContradictsTheSignatureIsRefused()
    {
        var (bridge, _) = Seam();

        Assert.Equal(
            "glk_window_open takes 5 argument words, but 2 arrived",
            Assert.Throws<GlulxException>(() => bridge.Perform(0x0023, [0, 0])).Message);
    }

    // A selector the dispatch table carries but nobody serves yet
    // refuses by name, the way an opcode not carried yet does.
    [Fact]
    public void ASelectorNobodyServesRefusesByName()
    {
        var (bridge, _) = Seam();

        Assert.Equal(
            "called glk_tick, a Glk function this library does not serve yet",
            Assert.Throws<GlulxException>(() => bridge.Perform(0x0003, [])).Message);
    }

    // A plain word passes through as itself, and the result stores.
    [Fact]
    public void PlainWordsPassThroughAndTheResultStores()
    {
        var (bridge, library) = Seam();

        library.Offer(0x0004, args => Held.OfWord(((Held)args[0]!).Word + ((Held)args[1]!).Word));

        Assert.Equal(7u, bridge.Perform(0x0004, [3, 4]));
    }

    // A void function stores zero (Glulx: Miscellaneous).
    [Fact]
    public void AVoidFunctionStoresZero()
    {
        var (bridge, library) = Seam();

        library.Record(0x0086, Held.OfWord(0xFFFF));

        Assert.Equal(0u, bridge.Perform(0x0086, [5]));
        Assert.Equal(Held.OfWord(5), (Held)library.Calls[0][0]!);
    }

    // An opaque argument arrives as the object its id names, and an id
    // that names nothing arrives as the null object.
    [Fact]
    public void OpaqueArgumentsArriveAsObjects()
    {
        var (bridge, library) = Seam();
        var window = new BlankWindow();
        var ident = bridge.Registry.Register(window, OpaqueClass.Window);

        library.Record(0x002A);

        bridge.Perform(0x002A, [ident]);
        bridge.Perform(0x002A, [999]);

        Assert.Same(window, ((Held)library.Calls[0][0]!).Opaque);
        Assert.Null(((Held)library.Calls[1][0]!).Opaque);
    }

    // An opaque result is minted into an id, and the same object always
    // answers with the same one.
    [Fact]
    public void AnOpaqueResultMintsAnId()
    {
        var (bridge, library) = Seam();
        var window = new BlankWindow();

        library.Offer(0x0022, _ => Held.OfOpaque(window));

        var ident = bridge.Perform(0x0022, []);

        Assert.Equal(ident, bridge.Perform(0x0022, []));
        Assert.Same(window, bridge.Registry.Lookup(OpaqueClass.Window, ident));
    }

    // A result of the null object is zero, which is what a game reads as
    // "there is no root window".
    [Fact]
    public void ANullOpaqueResultIsZero()
    {
        var (bridge, library) = Seam();

        library.Offer(0x0022, _ => Held.OfOpaque(null));

        Assert.Equal(0u, bridge.Perform(0x0022, []));
    }

    // An output reference is written back into memory after the call.
    [Fact]
    public void AnOutputReferenceLandsInMemoryAfterTheCall()
    {
        var (bridge, library) = Seam();

        library.Offer(0x0021, args =>
        {
            Assert.Null(args[0]);

            return Held.OfWord(0);
        });

        library.Offer(0x0025, args =>
        {
            ((Ref)args[1]!).Value = Held.OfWord(80);
            ((Ref)args[2]!).Value = Held.OfWord(24);

            return default;
        });

        bridge.Perform(0x0025, [0, Ram, Ram + 4]);

        Assert.Equal(80u, bridge.Memory.ReadWord(Ram));
        Assert.Equal(24u, bridge.Memory.ReadWord(Ram + 4));
    }

    // An input reference is read before the call and left alone after
    // it: the game wrote it, and Glk only reads.
    [Fact]
    public void AnInputReferenceIsReadAndNotWrittenBack()
    {
        var (bridge, library) = Seam();

        bridge.Memory.WriteWord(Ram, 11);
        bridge.Memory.WriteWord(Ram + 4, 22);
        bridge.Memory.WriteWord(Ram + 8, 33);

        library.Offer(0x016E, args =>
        {
            var date = (RefStruct)args[0]!;

            Assert.Equal(Held.OfWord(11), date[0]);
            Assert.Equal(Held.OfWord(22), date[1]);

            date[0] = Held.OfWord(999);

            return Held.OfWord(5);
        });

        Assert.Equal(5u, bridge.Perform(0x016E, [Ram, 0]));
        Assert.Equal(11u, bridge.Memory.ReadWord(Ram));
    }

    // A struct passes as one reference carrying its fields, and an
    // opaque field is encoded on the way back like any other.
    [Fact]
    public void AStructTravelsFieldByFieldAndMintsItsWindow()
    {
        var (bridge, library) = Seam();
        var window = new BlankWindow();

        library.Offer(0x00C0, args =>
        {
            ((RefStruct)args[0]!).SetAll(
                Held.OfWord(EventType.LineInput),
                Held.OfOpaque(window),
                Held.OfWord(7),
                Held.OfWord(0));

            return default;
        });

        bridge.Perform(0x00C0, [Ram]);

        Assert.Equal(EventType.LineInput, bridge.Memory.ReadWord(Ram));
        Assert.Equal(1u, bridge.Memory.ReadWord(Ram + 4));
        Assert.Equal(7u, bridge.Memory.ReadWord(Ram + 8));
        Assert.Equal(0u, bridge.Memory.ReadWord(Ram + 12));
        Assert.Same(window, bridge.Registry.Lookup(OpaqueClass.Window, 1));
    }

    // An output reference of -1 pushes onto the stack instead, after the
    // call and before the opcode's own store (Glulx: Miscellaneous).
    [Fact]
    public void AnOutputReferenceOfMinusOnePushesOntoTheStack()
    {
        var (bridge, library) = Seam();

        library.Offer(0x0025, args =>
        {
            ((Ref)args[1]!).Value = Held.OfWord(80);
            ((Ref)args[2]!).Value = Held.OfWord(24);

            return default;
        });

        bridge.Perform(0x0025, [0, Bridge.StackRef, Bridge.StackRef]);

        Assert.Equal(24u, bridge.Stack.Pop());
        Assert.Equal(80u, bridge.Stack.Pop());
    }

    // A struct pushed onto the stack leaves its last field on top,
    // because the fields push in order.
    [Fact]
    public void AStructPushesItsFieldsInOrder()
    {
        var (bridge, library) = Seam();

        library.Offer(0x00C0, args =>
        {
            ((RefStruct)args[0]!).SetAll(
                Held.OfWord(1), Held.OfOpaque(null), Held.OfWord(3), Held.OfWord(4));

            return default;
        });

        bridge.Perform(0x00C0, [Bridge.StackRef]);

        Assert.Equal(4u, bridge.Stack.Pop());
        Assert.Equal(3u, bridge.Stack.Pop());
        Assert.Equal(0u, bridge.Stack.Pop());
        Assert.Equal(1u, bridge.Stack.Pop());
    }

    // An input reference of -1 pops, first field topmost.
    [Fact]
    public void AnInputReferenceOfMinusOnePopsFirstFieldTopmost()
    {
        var (bridge, library) = Seam();

        bridge.Stack.Push(30);
        bridge.Stack.Push(20);
        bridge.Stack.Push(10);

        library.Offer(0x016E, args =>
        {
            var date = (RefStruct)args[0]!;

            Assert.Equal(Held.OfWord(10), date[0]);
            Assert.Equal(Held.OfWord(20), date[1]);
            Assert.Equal(Held.OfWord(30), date[2]);

            return Held.OfWord(0);
        });

        // glkdate_t has eight fields; the rest come off as whatever the
        // stack holds beneath.
        bridge.Stack.Push(0);
        bridge.Stack.Push(0);
        bridge.Stack.Push(0);
        bridge.Stack.Push(0);
        bridge.Stack.Push(0);
        bridge.Stack.Push(30);
        bridge.Stack.Push(20);
        bridge.Stack.Push(10);

        bridge.Perform(0x016E, [Bridge.StackRef, 0]);
    }

    // A scalar reference of -1 pops its value in and pushes it back.
    [Fact]
    public void AScalarReferenceOfMinusOneTravelsBothWays()
    {
        var (bridge, library) = Seam();

        bridge.Stack.Push(6);

        library.Offer(0x0005, args =>
        {
            var view = (MemArray?)args[2];

            Assert.Null(view);

            return Held.OfWord(1);
        });

        Assert.Equal(1u, bridge.Perform(0x0005, [4, 0, 0, 0]));
    }

    // A null address arrives as nothing at all where the signature
    // allows it, and is refused where it does not.
    [Fact]
    public void ANullAddressIsAllowedOnlyWhereTheSignatureSaysSo()
    {
        var (bridge, library) = Seam();

        library.Offer(0x00D1, args =>
        {
            Assert.Null(args[1]);

            return default;
        });

        bridge.Perform(0x00D1, [0, 0]);

        library.Record(0x00C0);

        Assert.Equal(
            "a null address arrived where the Glk call requires one",
            Assert.Throws<GlulxException>(() => bridge.Perform(0x00C0, [0])).Message);
    }

    // A null array is nothing at all too, where its signature allows it.
    [Fact]
    public void ANullArrayIsNothingAtAll()
    {
        var (bridge, library) = Seam();

        library.Offer(0x0151, args =>
        {
            Assert.Null(args[1]);

            return default;
        });

        bridge.Perform(0x0151, [0, 0, 0]);

        library.Record(0x0084);

        Assert.Throws<GlulxException>(() => bridge.Perform(0x0084, [0, 4]));
    }

    // An array arrives as a live view, so what the library writes is
    // already in memory when the call returns.
    [Fact]
    public void AnArrayArrivesAsALiveViewOntoMemory()
    {
        var (bridge, library) = Seam();

        bridge.Memory.WriteByte(Ram, 0x41);
        bridge.Memory.WriteByte(Ram + 1, 0x42);

        library.Offer(0x0091, args =>
        {
            var view = (MemArray)args[1]!;

            Assert.Equal(3, view.Length);
            Assert.Equal(0x41u, view[0]);

            view[2] = 0x5A;

            return Held.OfWord(2);
        });

        Assert.Equal(2u, bridge.Perform(0x0091, [0, Ram, 3]));
        Assert.Equal(0x5A, bridge.Memory.ReadByte(Ram + 2));
    }

    // An array of object ids arrives as the objects, since such an array
    // only ever passes in.
    [Fact]
    public void AnArrayOfIdsArrivesAsTheObjects()
    {
        var (bridge, library) = Seam();
        var first = new SoundChannel();
        var second = new SoundChannel();

        bridge.Memory.WriteWord(Ram, bridge.Registry.Register(first, OpaqueClass.SoundChannel));
        bridge.Memory.WriteWord(Ram + 4, bridge.Registry.Register(second, OpaqueClass.SoundChannel));
        bridge.Memory.WriteWord(Ram + 8, 0);

        library.Offer(0x00F7, args =>
        {
            var channels = (GlkObject?[])args[0]!;

            Assert.Equal(3, channels.Length);
            Assert.Same(first, channels[0]);
            Assert.Same(second, channels[1]);
            Assert.Null(channels[2]);

            return Held.OfWord(2);
        });

        Assert.Equal(2u, bridge.Perform(0x00F7, [Ram, 3, Ram + 32, 3, 0]));
    }

    // A string argument is the address of a string object, not of a bare
    // byte array: the type byte comes first and the text ends at a zero.
    [Fact]
    public void AStringArgumentIsAStringObject()
    {
        var (bridge, library) = Seam();

        bridge.Memory.WriteByte(Ram, 0xE0);
        bridge.Memory.WriteByte(Ram + 1, 0x68);
        bridge.Memory.WriteByte(Ram + 2, 0xE9);
        bridge.Memory.WriteByte(Ram + 3, 0);

        library.Record(0x0082);

        bridge.Perform(0x0082, [Ram]);

        Assert.Equal("hé", library.Calls[0][0]);
    }

    // An address that holds no string object at all is refused, saying
    // what it found there.
    [Fact]
    public void AnAddressThatIsNoStringObjectIsRefused()
    {
        var (bridge, library) = Seam();

        bridge.Memory.WriteByte(Ram, 0xE1);
        library.Record(0x0082);
        library.Record(0x0129);

        Assert.Equal(
            $"the Glk string argument at 0x{Ram:x} is not an E0 string object (found 0xe1)",
            Assert.Throws<GlulxException>(() => bridge.Perform(0x0082, [Ram])).Message);

        Assert.Equal(
            $"the Glk Unicode string argument at 0x{Ram:x} is not an E2 string object (found 0xe1)",
            Assert.Throws<GlulxException>(() => bridge.Perform(0x0129, [Ram])).Message);
    }

    // A Unicode string object is a type byte and three of padding, so
    // its characters start four bytes in. A word past the last code
    // point renders as the placeholder; a lone surrogate travels as
    // itself, which is the reference's own rule here.
    [Fact]
    public void AUnicodeStringObjectStartsFourBytesIn()
    {
        var (bridge, library) = Seam();

        bridge.Memory.WriteWord(Ram, 0xE2000000);
        bridge.Memory.WriteWord(Ram + 4, 0x41);
        bridge.Memory.WriteWord(Ram + 8, 0x1F600);
        bridge.Memory.WriteWord(Ram + 12, 0xD800);
        bridge.Memory.WriteWord(Ram + 16, 0x110000);
        bridge.Memory.WriteWord(Ram + 20, 0);

        library.Record(0x0129);

        bridge.Perform(0x0129, [Ram]);

        Assert.Equal("A\U0001F600\uD800?", library.Calls[0][0]);
    }

    private static Memory Mapped() => new(new Story(new GlulxBuilder().Build()));

    private static (Bridge Bridge, TestLibrary Library) Seam()
    {
        var library = new TestLibrary();
        var bridge = new Bridge(Mapped(), library, new StackMemory(1024));

        return (bridge, library);
    }
}
