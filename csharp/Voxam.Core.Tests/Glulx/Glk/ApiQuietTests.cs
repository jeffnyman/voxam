using Voxam.Core.Glulx;
using Voxam.Core.Glulx.Glk;

namespace Voxam.Tests.Glulx.Glk;

/// <summary>
/// What the library does when it is asked to write to nothing, split
/// by a percentage, or told to end the session mid-instruction.
/// </summary>
public sealed class ApiQuietTests
{
    private const uint Buf = 0x500;
    private const uint Ref = 0x600;
    private const int Slot = 0x180;

    // Printing to no stream at all is quiet, whichever of the twelve
    // doors it arrives at.
    [Fact]
    public void PrintingToNothingIsQuiet()
    {
        var (bridge, glk) = Seam();

        Assert.Null(glk.CurrentStream);

        // The current stream is nothing, and the named stream is too.
        bridge.Perform(0x0080, [0x41]);
        bridge.Perform(0x0128, [0x41]);
        bridge.Perform(0x0082, [StringAt(bridge, "a")]);
        bridge.Perform(0x0129, [UniStringAt(bridge, "a")]);
        bridge.Perform(0x0084, [Buf, 1]);
        bridge.Perform(0x012A, [Buf, 1]);

        bridge.Perform(0x0081, [0, 0x41]);
        bridge.Perform(0x012B, [0, 0x41]);
        bridge.Perform(0x0083, [0, StringAt(bridge, "a")]);
        bridge.Perform(0x012C, [0, UniStringAt(bridge, "a")]);
        bridge.Perform(0x0085, [0, Buf, 1]);
        bridge.Perform(0x012D, [0, Buf, 1]);

        Assert.Empty(glk.Streams);
    }

    // A proportional split takes its percentage of the room, where a
    // fixed one counts in the key window's units.
    [Fact]
    public void AProportionalSplitTakesItsPercentage()
    {
        var (bridge, glk) = Seam();

        var first = bridge.Perform(0x0023, [0, 0, 0, WindowType.TextBuffer, 0]);

        bridge.Perform(
            0x0023,
            [first, WindowMethod.Above | WindowMethod.Proportional, 25, WindowType.TextGrid, 0]);

        var pair = (PairWindow)glk.Root!;

        Assert.Equal(new Box(0, 0, 80, 6), pair.Child2.BBox);
    }

    // Turning a split around without naming a key leaves the old key
    // where it was, and asking for the arrangement without wanting every
    // part of it is allowed.
    [Fact]
    public void ASplitKeepsItsKeyWhenNoneIsNamed()
    {
        var (bridge, glk) = Seam();

        var first = bridge.Perform(0x0023, [0, 0, 0, WindowType.TextBuffer, 0]);
        bridge.Perform(
            0x0023, [first, WindowMethod.Above | WindowMethod.Fixed, 3, WindowType.TextGrid, 0]);

        var pair = (PairWindow)glk.Root!;
        var ident = bridge.Registry.Register(pair, 0);
        var key = pair.Key;

        // Below is the same axis as Above, so this is a turn and not a
        // rotation: the children swap and the key stands.
        bridge.Perform(0x0026, [ident, WindowMethod.Below | WindowMethod.Fixed, 3, 0]);

        Assert.Same(key, pair.Key);
        Assert.False(pair.Backward);

        // And asking for none of the three parts is no error.
        bridge.Perform(0x0027, [ident, 0, 0, 0]);
        bridge.Perform(0x0025, [first, 0, 0]);

        // Setting the same direction again turns nothing around.
        bridge.Perform(0x0026, [ident, WindowMethod.Below | WindowMethod.Fixed, 4, 0]);

        Assert.Same(key, pair.Key);
        Assert.False(pair.Backward);
        Assert.Equal(4, pair.Size);
    }

    // The window on the other side of a pair, from both sides.
    [Fact]
    public void ASiblingIsFoundFromEitherSide()
    {
        var (bridge, glk) = Seam();

        var first = bridge.Perform(0x0023, [0, 0, 0, WindowType.TextBuffer, 0]);
        var second = bridge.Perform(
            0x0023, [first, WindowMethod.Above | WindowMethod.Fixed, 3, WindowType.TextGrid, 0]);

        Assert.Equal(first, bridge.Perform(0x0030, [second]));
        Assert.Equal(second, bridge.Perform(0x0030, [first]));

        Assert.NotNull(glk.Root);
    }

    // Closing the window on the far side of a pair promotes the near one.
    [Fact]
    public void ClosingTheFarChildPromotesTheNearOne()
    {
        var (bridge, glk) = Seam();

        var first = bridge.Perform(0x0023, [0, 0, 0, WindowType.TextBuffer, 1]);
        var second = bridge.Perform(
            0x0023, [first, WindowMethod.Above | WindowMethod.Fixed, 3, WindowType.TextGrid, 2]);

        bridge.Perform(0x0024, [first, 0]);

        Assert.Single(glk.Windows);
        Assert.Equal(second, bridge.Registry.Register(glk.Root!, 0));
    }

    // A display that cannot measure a style says nothing, which is what
    // the base seat answers for every display that has not been taught
    // to.
    [Fact]
    public void ADisplayThatCannotMeasureSaysNothing()
    {
        var (bridge, _) = Seam();

        var window = bridge.Perform(0x0023, [0, 0, 0, WindowType.TextBuffer, 0]);

        Assert.Equal(0u, bridge.Perform(0x00B3, [window, TextStyle.Normal, 0, Ref]));
        Assert.Equal(0u, bridge.Perform(0x00B2, [window, TextStyle.Normal, TextStyle.Header]));
    }

    // glk_exit ends the session from wherever it was called, however
    // deep inside a Glk call that was, and the machine stops there
    // (Glk: Your Program's Main Function).
    [Fact]
    public void ExitEndsTheSessionFromInsideAnInstruction()
    {
        var program = new GlulxProgram();
        program.Op(Op.Glk, Modes.Constant(0x0001), Modes.Constant(0), Modes.Memory(Slot));
        program.Op(Op.Copy, Modes.Constant(0x2A), Modes.Memory(Slot + 4));
        program.Op(Op.Quit);

        var machine = program.Booted(library: new Api());
        var steps = machine.Run();

        Assert.False(machine.Running);
        Assert.Equal(1, steps);
        // The instruction after the exit never ran.
        Assert.Equal(0u, machine.Memory.ReadWord(Slot + 4));
    }

    private static uint StringAt(Bridge bridge, string text)
    {
        const int At = 0x800;

        bridge.Memory.WriteByte(At, 0xE0);

        for (var index = 0; index < text.Length; index++)
        {
            bridge.Memory.WriteByte(At + 1 + index, text[index]);
        }

        bridge.Memory.WriteByte(At + 1 + text.Length, 0);

        return At;
    }

    private static uint UniStringAt(Bridge bridge, string text)
    {
        const int At = 0x900;

        bridge.Memory.WriteWord(At, 0xE2000000);

        for (var index = 0; index < text.Length; index++)
        {
            bridge.Memory.WriteWord(At + 4 + (index * 4), text[index]);
        }

        bridge.Memory.WriteWord(At + 4 + (text.Length * 4), 0);

        return At;
    }

    private static (Bridge Bridge, Api Glk) Seam()
    {
        var story = new Story(new GlulxBuilder
        {
            RamStart = 0x100,
            ExtStart = 0x200,
            EndMem = 0x2000,
            StackSize = 0x400,
        }.Build());

        var glk = new Api();

        return (new Bridge(new Memory(story), glk, new StackMemory(0x400)), glk);
    }
}
