using Voxam.Core.Glulx;
using Voxam.Core.Glulx.Glk;
using GlulxException = Voxam.Core.GlulxException;

namespace Voxam.Tests.Glulx.Glk;

/// <summary>
/// The glk opcode itself: the last frontier in the roster, and what it
/// does now that a library can stand behind it (Glulx: Miscellaneous).
/// </summary>
public sealed class OpcodeTests
{
    // The roster is whole. Every opcode the specification defines has a
    // handler, which is the promise the decoder's refusal now leans on:
    // a number that misses the table is a number 3.1.3 does not define,
    // and there is no third case for it to mistake.
    [Fact]
    public void EveryOpcodeInTheRosterIsCarried()
    {
        var missing = Enum.GetValues<Op>()
            .Where(op => !Machine.Carries((int)op))
            .Select(op => Opcode.Name((int)op))
            .ToArray();

        Assert.Empty(missing);
    }

    // The opcode needs a library to call into, and says so plainly when
    // there is none rather than answering some default.
    [Fact]
    public void TheOpcodeNeedsALibraryAndSaysSoWithoutOne()
    {
        var program = new GlulxProgram();
        program.Op(Op.Glk, Modes.Constant(0x0003), Modes.Constant(0), Modes.Discard);

        var refusal = Assert.Throws<GlulxException>(() => program.Booted().Run());

        Assert.Equal("the glk opcode needs a Glk library, and none is installed", refusal.Message);
    }

    // With a library installed the opcode dispatches: the selector names
    // the function, the arguments come off the stack first argument
    // topmost, and the result stores.
    [Fact]
    public void TheOpcodeDispatchesAndStoresItsResult()
    {
        var library = new TestLibrary();
        library.Offer(0x0004, args =>
            Held.OfWord((((Held)args[0]!).Word * 10) + ((Held)args[1]!).Word));

        var program = new GlulxProgram();
        // Push the two arguments, first argument topmost, the way the
        // call opcodes leave them.
        program.Op(Op.Copy, Modes.Constant(4), Modes.Stack);
        program.Op(Op.Copy, Modes.Constant(3), Modes.Stack);
        program.Op(Op.Glk, Modes.Constant(0x0004), Modes.Constant(2), Modes.Memory(Slot));
        program.Op(Op.Quit);

        var machine = program.Booted(library: library);
        machine.Run();

        Assert.Equal(34u, machine.Memory.ReadWord(Slot));
    }

    // A selector the table carries but the library does not serve yet
    // refuses by name. That is the same discipline the opcode roster
    // kept while it was still filling: an absence speaks in the words of
    // the thing that is missing.
    [Fact]
    public void AnUnservedFunctionRefusesByName()
    {
        var program = new GlulxProgram();
        program.Op(Op.Glk, Modes.Constant(0x0003), Modes.Constant(0), Modes.Discard);

        var refusal = Assert.Throws<GlulxException>(
            () => program.Booted(library: new TestLibrary()).Run());

        Assert.Equal(
            "called glk_tick, a Glk function this library does not serve yet",
            refusal.Message);
    }

    // A stack output reference pushes before the opcode's own store, so
    // a store to the stack lands on top of what the call pushed (Glulx:
    // Miscellaneous).
    [Fact]
    public void AStackReferencePushesBeforeTheResultStores()
    {
        var library = new TestLibrary();
        library.Offer(0x0025, args =>
        {
            ((Ref)args[1]!).Value = Held.OfWord(80);
            ((Ref)args[2]!).Value = Held.OfWord(24);

            return default;
        });

        var program = new GlulxProgram();
        program.Op(Op.Copy, Modes.Constant(Voxam.Core.Glulx.Bridge.StackRef), Modes.Stack);
        program.Op(Op.Copy, Modes.Constant(Voxam.Core.Glulx.Bridge.StackRef), Modes.Stack);
        program.Op(Op.Copy, Modes.Constant(0), Modes.Stack);
        program.Op(Op.Glk, Modes.Constant(0x0025), Modes.Constant(3), Modes.Memory(Slot));
        program.Op(Op.Copy, Modes.Stack, Modes.Memory(Slot + 4));
        program.Op(Op.Copy, Modes.Stack, Modes.Memory(Slot + 8));
        program.Op(Op.Quit);

        var machine = program.Booted(library: library);
        machine.Run();

        // The call stored zero, being void, and the two pushed sizes sit
        // under it with the last one on top.
        Assert.Equal(0u, machine.Memory.ReadWord(Slot));
        Assert.Equal(24u, machine.Memory.ReadWord(Slot + 4));
        Assert.Equal(80u, machine.Memory.ReadWord(Slot + 8));
    }

    // A library is its own seat, kept apart from the output one until
    // the era that joins them.
    [Fact]
    public void TheLibraryAndTheBridgeStandOrFallTogether()
    {
        var program = new GlulxProgram();
        program.Op(Op.Quit);

        Assert.Null(program.Booted().Library);
        Assert.Null(program.Booted().Bridge);

        var library = new TestLibrary();
        var machine = program.Booted(library: library);

        Assert.Same(library, machine.Library);
        Assert.Same(library, machine.Bridge!.Library);
        Assert.Same(machine.Memory, machine.Bridge.Memory);
        Assert.Same(machine.Stack, machine.Bridge.Stack);
    }

    // A slot in RAM the tests read their answers out of, clear of the
    // program's own code.
    private const int Slot = 0x180;
}
