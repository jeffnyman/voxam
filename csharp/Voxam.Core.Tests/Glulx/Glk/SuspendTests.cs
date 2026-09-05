using Voxam.Core.Glulx;
using Voxam.Core.Glulx.Glk;
using GlulxException = Voxam.Core.GlulxException;

namespace Voxam.Tests.Glulx.Glk;

/// <summary>
/// The other arrangement: a display that cannot block, and the machine
/// that stands down for it.
///
/// A select records what it waits for and unwinds; the host collects
/// the answer and delivers it; running again continues from the same
/// instruction. A file prompt goes further and parks the call itself,
/// because its result is the player's answer and no value can be stored
/// until the name arrives (Glk: Events, File References).
/// </summary>
public sealed class SuspendTests : IDisposable
{
    private const uint Slot = 0x180;
    private const uint Record = 0x200;

    private readonly string _saveDir =
        Path.Combine(Path.GetTempPath(), "voxam-glk-wait-" + Path.GetRandomFileName());

    public SuspendTests() => Directory.CreateDirectory(_saveDir);

    public void Dispose() => Directory.Delete(_saveDir, true);

    // A suspending display is never asked for input. The select records
    // the seat the event will land in and returns, leaving the game's
    // struct untouched until there is something to put in it.
    [Fact]
    public void ASelectWithNothingToReportRecordsTheWait()
    {
        var (glk, display) = Seam();
        var window = Waiting(glk);
        var record = new RefStruct(4);

        Call(glk, 0x00C0, record);

        var waiting = Assert.IsType<Waiting>(glk.Suspended);

        Assert.Same(record, waiting.Record);
        Assert.Equal(EventType.None, record[0].Word);
        Assert.Equal(1, display.Flushes);
        Assert.True(window.CharRequest);
    }

    // What is already queued is delivered on the spot: a host's own
    // news never waits on a round trip it does not need.
    [Fact]
    public void AQueuedEventNeedsNoRoundTrip()
    {
        var (glk, display) = Seam();

        Waiting(glk);
        display.Raise(new GlkEvent(EventType.Timer, null, 4));

        var record = new RefStruct(4);

        Call(glk, 0x00C0, record);

        Assert.Null(glk.Suspended);
        Assert.Equal(EventType.Timer, record[0].Word);
        Assert.Equal(4u, record[2].Word);
    }

    // A select with nothing outstanding is refused rather than recorded:
    // a wait nothing could ever answer is a hang with extra steps.
    [Fact]
    public void AWaitNothingCouldAnswerIsRefused()
    {
        var (glk, _) = Seam();

        glk.Windows.Add(new BlankWindow());

        var refusal = Assert.Throws<GlulxException>(
            () => Call(glk, 0x00C0, new RefStruct(4)));

        Assert.Equal(
            "glk_select with no input requested: the game would wait forever",
            refusal.Message);
        Assert.Null(glk.Suspended);
    }

    // Only a request the display could actually answer counts as
    // something to wait for. A click nobody can make, a link nobody can
    // follow and a timer nobody can ring are all still hangs.
    [Fact]
    public void OnlyARequestTheDisplayCanAnswerCounts()
    {
        foreach (var claimed in new[] { false, true })
        {
            var (mouse, mouseFace) = Seam();
            var clicking = new BlankWindow { MouseRequest = true };

            mouseFace.Clicks = claimed;
            mouse.Windows.Add(clicking);

            Assert.Equal(claimed, Recorded(mouse));

            var (link, linkFace) = Seam();
            var following = new BlankWindow { HyperlinkRequest = true };

            linkFace.Follows = claimed;
            link.Windows.Add(following);

            Assert.Equal(claimed, Recorded(link));

            var (timed, timedFace) = Seam();

            timedFace.Ticks = claimed;
            Call(timed, 0x00D6, Held.OfWord(500));

            Assert.Equal(claimed, Recorded(timed));
        }

        // And a timer the display can ring but the game never asked for
        // is nothing to wait on either.
        var (idle, idleFace) = Seam();

        idleFace.Ticks = true;

        Assert.False(Recorded(idle));
    }

    // A line request is enough on its own, whatever the display claims:
    // typing is the one thing every face can do.
    [Fact]
    public void ALineRequestIsAlwaysSomethingToWaitFor()
    {
        var (glk, _) = Seam();
        var window = new BlankWindow { LineRequest = new LineRequest(new WordBuffer(8)) };

        glk.Windows.Add(window);

        Assert.True(Recorded(glk));
    }

    // The event a host collects lands in the seat the select left, and
    // the machine's memory is written from it.
    [Fact]
    public void TheDeliveredEventLandsInTheSeatTheSelectLeft()
    {
        var (bridge, glk, display) = Wired();
        var window = Waiting(glk);

        bridge.Perform(0x00C0, [Record]);

        Assert.IsType<Waiting>(glk.Suspended);
        Assert.Equal(0u, bridge.Memory.ReadWord((int)Record));

        glk.DeliverEvent(Api.DeliverChar(window, 0x41));

        Assert.Null(glk.Suspended);
        Assert.Equal(EventType.CharInput, bridge.Memory.ReadWord((int)Record));
        Assert.NotEqual(0u, bridge.Memory.ReadWord((int)Record + 4));
        Assert.Equal(0x41u, bridge.Memory.ReadWord((int)Record + 8));
        Assert.Equal(1, display.Flushes);
    }

    // An event with no seat to land in is a driver's bug, and a loud
    // one: a file prompt standing is no seat for an event either.
    [Fact]
    public void AnEventWithNoSeatIsRefused()
    {
        var (glk, _) = Seam();

        Assert.Equal(
            "an event arrived with no select suspended to receive it",
            Assert.Throws<GlulxException>(() => glk.DeliverEvent(new GlkEvent())).Message);

        Call(glk, 0x0062, Held.OfWord(FileUsage.SavedGame), Held.OfWord(0x02), Held.OfWord(0));

        Assert.IsType<Prompting>(glk.Suspended);
        Assert.Throws<GlulxException>(() => glk.DeliverEvent(new GlkEvent()));
    }

    // A suspended machine executes nothing. A call arriving anyway
    // means a host ran on past the suspension, and it is refused before
    // a single argument pops, so the stack stays whole.
    [Fact]
    public void NothingElseMayBeCalledWhileTheMachineStandsSuspended()
    {
        var (bridge, glk, _) = Wired();

        Waiting(glk);
        bridge.Perform(0x00C0, [Record]);

        var refusal = Assert.Throws<GlulxException>(() => bridge.Perform(0x0003, []));

        Assert.Equal("glk_tick called while the machine stands suspended", refusal.Message);
    }

    // The machine stands down where it is: the select's own instruction
    // is whole, the machine is still running, and delivering the event
    // lets it step on.
    [Fact]
    public void TheMachineStandsDownAndPicksUpAgain()
    {
        var glk = new Api(new QuietDisplay());
        var program = new GlulxProgram();

        program.Op(Op.Copy, Modes.Word(Record), Modes.Stack);
        program.Op(Op.Glk, Modes.Constant(0x00C0), Modes.Constant(1), Modes.Memory(Slot));
        program.Op(Op.Copy, Modes.Constant(99), Modes.Memory(Slot + 4));
        program.Op(Op.Quit);

        var machine = program.Booted(library: glk);
        var window = Waiting(glk);

        machine.Run();

        // The opcode completed: void, so it stored zero. What follows it
        // has not run.
        Assert.True(machine.Running);
        Assert.Equal(0u, machine.Memory.ReadWord((int)Slot));
        Assert.Equal(0u, machine.Memory.ReadWord((int)Slot + 4));

        glk.DeliverEvent(Api.DeliverChar(window, 0x42));
        machine.Run();

        Assert.False(machine.Running);
        Assert.Equal(0x42u, machine.Memory.ReadWord((int)Record + 8));
        Assert.Equal(99u, machine.Memory.ReadWord((int)Slot + 4));
    }

    // A blocking display is asked for a filename on the spot, and a
    // cancelled prompt is the null reference, which is always a
    // legitimate answer.
    [Fact]
    public void ABlockingDisplayIsAskedForTheNameOnTheSpot()
    {
        var display = new ScriptedDisplay();
        var glk = new Api(display, _saveDir);

        display.Names.Enqueue("bronze");

        var chosen = Call(glk, 0x0062,
            Held.OfWord(FileUsage.SavedGame), Held.OfWord(0x02), Held.OfWord(7));
        var fileref = Assert.IsType<FileRef>(chosen.Opaque);

        Assert.Equal(Path.Combine(_saveDir, "bronze.glksave"), fileref.Filename);
        Assert.Equal(7u, fileref.Rock);
        Assert.Null(glk.Suspended);

        display.Names.Enqueue(null);

        Assert.Null(Call(glk, 0x0062,
            Held.OfWord(FileUsage.SavedGame), Held.OfWord(0x02), Held.OfWord(0)).Opaque);
    }

    // A suspending display is never asked, so the call itself stands
    // mid-flight: nothing is stored until the name arrives.
    [Fact]
    public void AFilePromptParksTheWholeCall()
    {
        var (bridge, glk, _) = Wired();

        var stored = bridge.Perform(0x0062, [FileUsage.Transcript, 0x05, 3]);
        var prompting = Assert.IsType<Prompting>(glk.Suspended);

        Assert.Equal(FileUsage.Transcript, prompting.Usage);
        Assert.Equal(0x05u, prompting.FMode);
        Assert.Equal(3u, prompting.Rock);
        Assert.NotNull(prompting.Encode);
        Assert.Equal(0u, stored);

        // The machine's own store is what the opcode parks; a bridge
        // reached on its own has none to offer.
        Assert.Equal(
            "the file prompt stands outside any glk call, with no store owed",
            Assert.Throws<GlulxException>(() => glk.DeliverFile("notes")).Message);
    }

    // A name arriving with no prompt standing is the same driver's bug
    // the stray event is. So is a name for a prompt that never came
    // through a glk opcode: neither half of its tail is parked, and
    // there is nowhere for the reference to go.
    [Fact]
    public void ANameWithNoPromptIsRefused()
    {
        var (glk, _) = Seam();

        Assert.Equal(
            "a file name arrived with no prompt suspended to receive it",
            Assert.Throws<GlulxException>(() => glk.DeliverFile("notes")).Message);

        Call(glk, 0x0062, Held.OfWord(FileUsage.Data), Held.OfWord(0x02), Held.OfWord(0));

        Assert.Equal(
            "the file prompt stands outside any glk call, with no store owed",
            Assert.Throws<GlulxException>(() => glk.DeliverFile("notes")).Message);
    }

    // The whole round trip through the machine: the opcode parks its
    // store, the name arrives, and the id lands where the game will
    // look for it.
    [Fact]
    public void TheParkedStoreRunsWhenTheNameArrives()
    {
        var machine = Prompted(out var glk);

        machine.Run();

        Assert.True(machine.Running);
        Assert.IsType<Prompting>(glk.Suspended);
        Assert.Equal(0u, machine.Memory.ReadWord((int)Slot));

        glk.DeliverFile("bronze");

        var ident = machine.Memory.ReadWord((int)Slot);
        var fileref = Assert.IsType<FileRef>(
            machine.Bridge!.Registry.Lookup(OpaqueClass.FileRef, ident));

        Assert.Equal(Path.Combine(_saveDir, "bronze.glksave"), fileref.Filename);
        Assert.Null(glk.Suspended);

        machine.Run();

        Assert.False(machine.Running);
        Assert.Equal(99u, machine.Memory.ReadWord((int)Slot + 4));
    }

    // A cancelled prompt stores the null reference, and the game reads
    // it as the zero it is.
    [Fact]
    public void ACancelledPromptStoresNothing()
    {
        var machine = Prompted(out var glk);

        machine.Run();
        glk.DeliverFile(null);

        Assert.Equal(0u, machine.Memory.ReadWord((int)Slot));
        Assert.Empty(glk.FileRefs);
    }

    // The name is the player's own, not the game's: an absolute path is
    // honored as given, a relative one lands in the save directory, and
    // a name that already has a suffix keeps it.
    [Fact]
    public void ThePlayersNameIsHonoredAsGiven()
    {
        var whole = Path.Combine(_saveDir, "sub", "story.dat");

        Assert.Equal(whole, Named(whole).Filename);
        Assert.Equal(Path.Combine(_saveDir, "notes.txt"), Named("notes.txt").Filename);
        Assert.Equal(Path.Combine(_saveDir, "notes.glksave"), Named("notes").Filename);
    }

    /// <summary>Run one prompt to a name, and hand back the reference.</summary>
    private FileRef Named(string name)
    {
        var machine = Prompted(out var glk);

        machine.Run();
        glk.DeliverFile(name);

        return Assert.IsType<FileRef>(
            machine.Bridge!.Registry.Lookup(
                OpaqueClass.FileRef, machine.Memory.ReadWord((int)Slot)));
    }

    /// <summary>
    /// A machine that prompts for a saved game and then goes on, so a
    /// test can watch the parked store run.
    /// </summary>
    private Machine Prompted(out Api glk)
    {
        glk = new Api(new QuietDisplay(), _saveDir);

        var program = new GlulxProgram();

        program.Op(Op.Copy, Modes.Constant(0), Modes.Stack);
        program.Op(Op.Copy, Modes.Constant(0x02), Modes.Stack);
        program.Op(Op.Copy, Modes.Constant(FileUsage.SavedGame), Modes.Stack);
        program.Op(Op.Glk, Modes.Constant(0x0062), Modes.Constant(3), Modes.Memory(Slot));
        program.Op(Op.Copy, Modes.Constant(99), Modes.Memory(Slot + 4));
        program.Op(Op.Quit);

        return program.Booted(library: glk);
    }

    /// <summary>Whether a select records a wait rather than refusing.</summary>
    private static bool Recorded(Api glk)
    {
        try
        {
            Call(glk, 0x00C0, new RefStruct(4));
        }
        catch (GlulxException)
        {
            return false;
        }

        return glk.Suspended is Waiting;
    }

    /// <summary>A window with a keystroke outstanding, on the live list.</summary>
    private static BlankWindow Waiting(Api glk)
    {
        var window = new BlankWindow { CharRequest = true };

        glk.Windows.Add(window);

        return window;
    }

    /// <summary>Reach one function the way the bridge would.</summary>
    private static Held Call(Api glk, int selector, params object?[] args) =>
        glk.Call(Signatures.Lookup(selector)!, args);

    private static (Api Glk, QuietDisplay Display) Seam()
    {
        var display = new QuietDisplay();

        return (new Api(display), display);
    }

    private (Bridge Bridge, Api Glk, QuietDisplay Display) Wired()
    {
        var story = new Story(new GlulxBuilder
        {
            RamStart = 0x100,
            ExtStart = 0x200,
            EndMem = 0x2000,
            StackSize = 0x400,
        }.Build());

        var display = new QuietDisplay();
        var glk = new Api(display, _saveDir);

        return (new Bridge(new Memory(story), glk, new StackMemory(0x400)), glk, display);
    }
}
