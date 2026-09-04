using Voxam.Core.Glulx;

namespace Voxam.Tests.Glulx;

/// <summary>
/// What this interpreter says it can do (Glulx: Gestalt). Every
/// answer here is a statement about which eras the port has built,
/// so a false is a road rather than a decision.
/// </summary>
public sealed class GestaltTests
{
    [Theory]
    [InlineData(0u, 0u, 0x00030103u)]
    [InlineData(2u, 0u, 1u)]
    [InlineData(3u, 0u, 0u)]
    [InlineData(5u, 0u, 1u)]
    [InlineData(6u, 0u, 1u)]
    [InlineData(7u, 0u, 1u)]
    [InlineData(8u, 0u, 0u)]
    [InlineData(9u, 0u, 1u)]
    [InlineData(11u, 0u, 0u)]
    [InlineData(12u, 0u, 0u)]
    [InlineData(13u, 0u, 0u)]
    [InlineData(99u, 0u, 0u)]
    public void EachSelectorAnswersForItsOwnEra(uint selector, uint argument, uint answer)
    {
        Assert.Equal(answer, Gestalt.Answer(Booted(), selector, argument));
    }

    // The interpreter's own version, packed the way the header packs
    // one, off the assembly so it cannot drift from what the port
    // versions at.
    [Fact]
    public void TheInterpreterNamesItsOwnVersion()
    {
        var version = typeof(Machine).Assembly.GetName().Version!;
        var packed = ((uint)version.Major << 16) | ((uint)version.Minor << 8) | (uint)version.Build;

        Assert.Equal(packed, Gestalt.Answer(Booted(), 1, 0));
        Assert.NotEqual(0u, Gestalt.TerpVersion);
    }

    // The null and filter systems always work; Glk is its own era's
    // promise, and installing a library is what keeps it.
    [Theory]
    [InlineData(0u, 1u, 1u)]
    [InlineData(1u, 1u, 1u)]
    [InlineData(2u, 0u, 1u)]
    [InlineData(9u, 0u, 0u)]
    public void TheOutputSystemsAnswerForThemselves(uint system, uint bare, uint installed)
    {
        Assert.Equal(bare, Gestalt.Answer(Booted(), 4, system));
        Assert.Equal(installed, Gestalt.Answer(Booted(new Silence()), 4, system));
    }

    // Per function: which numbers this interpreter can replace.
    [Theory]
    [InlineData(0u, 0u)]
    [InlineData(1u, 1u)]
    [InlineData(13u, 1u)]
    [InlineData(14u, 0u)]
    public void TheAcceleratedFunctionsAnswerOneAtATime(uint number, uint answer)
    {
        Assert.Equal(answer, Gestalt.Answer(Booted(), 10, number));
    }

    // The heap's start address, or zero with no blocks extant.
    [Fact]
    public void TheHeapAnswersWithItsOwnStart()
    {
        var machine = Booted();

        Assert.Equal(0u, Gestalt.Answer(machine, 8, 0));

        var block = machine.Heap.Alloc(16);

        Assert.Equal(block, Gestalt.Answer(machine, 8, 0));
    }

    // And the opcode itself asks the same questions.
    [Fact]
    public void TheOpcodeAsksTheSameQuestions()
    {
        var program = new GlulxProgram();
        program.Op(Op.Gestalt, Modes.Constant(0), Modes.Constant(0), Modes.Memory(0x140));
        program.Op(Op.Gestalt, Modes.Constant(11), Modes.Constant(0), Modes.Memory(0x144));
        program.Op(Op.Quit);
        var machine = program.Booted();
        machine.Run();

        Assert.Equal(0x00030103u, machine.Memory.ReadWord(0x140));
        Assert.Equal(0u, machine.Memory.ReadWord(0x144));
    }

    private static Machine Booted(IGlkOutput? glk = null) =>
        new(new Story(new GlulxProgram().Build()), 7, glk);

    // A Glk library that swallows everything, which is enough to make
    // the machine say the system is there.
    private sealed class Silence : IGlkOutput
    {
        public void PutChar(uint character) => _ = character;

        public void PutCharUni(uint character) => _ = character;
    }
}
