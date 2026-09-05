using Voxam.Core.Glulx;
using Voxam.Core.Glulx.Glk;

namespace Voxam.Tests.Glulx.Glk;

/// <summary>
/// The save and restore opcodes, now that a Glk stream can be named
/// (Glulx: Game State). The format was whole from the serial era; what
/// arrives here is the stream to put it on.
/// </summary>
public sealed class SaveThroughGlkTests
{
    private const int Saved = 0x180;
    private const int Restored = 0x184;

    // The whole round trip, in the one story it has to be: a save onto a
    // stream in the first run, and the same bytes read back in the
    // second, which lands the machine back inside the save instruction
    // with -1 stored, exactly as the specification says.
    [Fact]
    public void AStateIsPutOnAStreamAndTakenBackOffIt()
    {
        var story = Program();

        // The first run saves onto stream one and finds nothing to
        // restore from stream two.
        var first = Booted(story, out var firstGlk);
        var written = new WordBuffer(4096);
        var empty = new WordBuffer(0);

        Register(first, firstGlk, new StreamOnMemory(written, GlkFileMode.ReadWrite));
        Register(first, firstGlk, new StreamOnMemory(empty, GlkFileMode.Read));

        first.Run();

        Assert.Equal(Serial.Succeeded, first.Memory.ReadWord(Saved));
        Assert.Equal(Serial.Failed, first.Memory.ReadWord(Restored));

        var bytes = written.Snapshot();

        Assert.Equal((uint)'F', bytes[0]);
        Assert.Equal((uint)'O', bytes[1]);
        Assert.Equal((uint)'R', bytes[2]);
        Assert.Equal((uint)'M', bytes[3]);

        // The second run cannot save, its stream being read-only, and
        // restores from the bytes the first one wrote.
        var second = Booted(story, out var secondGlk);

        Register(second, secondGlk, new StreamOnMemory(new WordBuffer(16), GlkFileMode.Read));
        Register(second, secondGlk, new StreamOnMemory(new WordBuffer(bytes), GlkFileMode.Read));

        second.Run();

        // The restore put the machine back inside the save, whose stub
        // stores the value that says so.
        Assert.Equal(0xFFFFFFFFu, second.Memory.ReadWord(Saved));

        // And the second pass over the restore found the stream spent.
        Assert.Equal(Serial.Failed, second.Memory.ReadWord(Restored));
    }

    // With no library there is no registry to name a stream in, so both
    // opcodes speak the failure a game learns to prompt again from.
    [Fact]
    public void WithNoLibraryThereIsNoStreamToName()
    {
        var machine = Program().Booted();

        machine.Run();

        Assert.Equal(Serial.Failed, machine.Memory.ReadWord(Saved));
        Assert.Equal(Serial.Failed, machine.Memory.ReadWord(Restored));
    }

    // An id that names no stream at all is the same failure, and so is
    // one that names a stream of the wrong class.
    [Fact]
    public void AnIdThatNamesNoStreamFailsToo()
    {
        var machine = Booted(Program(), out var glk);

        // The first two ids go to windows, so the stream ids the program
        // names resolve to nothing.
        glk.Windows.Add(new BlankWindow());
        machine.Bridge!.Registry.Register(glk.Windows[0], OpaqueClass.Window);
        machine.Bridge.Registry.Register(new BlankWindow(), OpaqueClass.Window);

        machine.Run();

        Assert.Equal(Serial.Failed, machine.Memory.ReadWord(Saved));
        Assert.Equal(Serial.Failed, machine.Memory.ReadWord(Restored));
    }

    // A save onto a stream that cannot be written, and a restore from
    // bytes that are no save file, both fail rather than faulting.
    [Fact]
    public void ARefusedStreamAndABadFileBothFail()
    {
        var machine = Booted(Program(), out var glk);

        Register(machine, glk, new StreamOnMemory(new WordBuffer(4), GlkFileMode.Read));
        Register(machine, glk, new StreamOnMemory(
            new WordBuffer([0x46, 0x4F, 0x52, 0x4D, 0, 0, 0, 4, 0x4E, 0x4F, 0x50, 0x45]),
            GlkFileMode.Read));

        machine.Run();

        Assert.Equal(Serial.Failed, machine.Memory.ReadWord(Saved));
        Assert.Equal(Serial.Failed, machine.Memory.ReadWord(Restored));
    }

    /// <summary>Put a stream on the live list and mint its id.</summary>
    private static void Register(Machine machine, Api glk, StreamObject stream)
    {
        glk.Streams.Add(stream);
        machine.Bridge!.Registry.Register(stream, OpaqueClass.Stream);
    }

    /// <summary>
    /// Save onto stream one, then restore from stream two. One story, so
    /// that what the first run writes the second can read.
    /// </summary>
    private static GlulxProgram Program()
    {
        var program = new GlulxProgram();

        program.Op(Op.Save, Modes.Constant(1), Modes.Memory(Saved));
        program.Op(Op.Restore, Modes.Constant(2), Modes.Memory(Restored));
        program.Op(Op.Quit);

        return program;
    }

    private static Machine Booted(GlulxProgram program, out Api glk)
    {
        glk = new Api();

        return program.Booted(library: glk);
    }
}
