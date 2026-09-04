using Voxam.Core.Tests.Support;

namespace Voxam.Core.Tests;

/// <summary>The seams a machine sends only to a stage, and what a character face hears instead (§8.8).</summary>
public class StageMachineTests
{
    private const int G0 = 0x10;
    private const int Units = 2;

    /// <summary>A glass that records the paints it is given and answers queued keys.</summary>
    private sealed class FakeScreen : IStageScreen
    {
        public int Columns => 10;

        public int Lines => 6;

        public int FontWidth => Units;

        public int FontHeight => Units;

        public Queue<string?> Keys { get; } = new();

        public List<Paint> Settled { get; } = [];

        public string? ReadKey(double? timeoutSeconds) => Keys.Count > 0 ? Keys.Dequeue() : null;

        public void Settle(IReadOnlyList<Paint> paints) => Settled.AddRange(paints);
    }

    // Assemble a Version 6 story around a main routine and run it on a
    // stage, which is the only face these opcodes reach.
    private static (StageFrontend Face, FakeScreen Screen) Play(Action<StoryBuilder> body, params string[] keys)
    {
        var b = new StoryBuilder(6);
        var main = b.Routine(0);
        body(b);
        b.Quit();
        b.InitialPc = main;
        var screen = new FakeScreen();

        foreach (var key in keys)
        {
            screen.Keys.Enqueue(key);
        }

        var face = new StageFrontend(screen);
        new Machine(b.Build(), face, () => null, 1, face.ReadKey, face.ReadLineUntil).Run();
        return (face, screen);
    }

    private static void MoveWindow(StoryBuilder b, int window, int line, int column) =>
        b.Ext(0x10, Arg.Small(window), Arg.Large(line), Arg.Large(column));

    private static void WindowSize(StoryBuilder b, int window, int height, int width) =>
        b.Ext(0x11, Arg.Small(window), Arg.Large(height), Arg.Large(width));

    // A window moved or resized in the ledger is placed on the stage,
    // so what is printed next lands where §8.8.3.4 put it.
    [Fact]
    public void MovingAndSizingAWindowPlacesItOnTheStage()
    {
        var (face, _) = Play(b =>
        {
            WindowSize(b, 2, 2 * Units, 4 * Units);
            MoveWindow(b, 2, 2 * Units + 1, Units + 1);
            b.OpVar(0x0B, Arg.Small(2));
            b.Print("here");
        });
        Assert.Equal(" here", face.Model.RowText(3));
    }

    // A cursor aimed at the selected window moves at once; one aimed at
    // another window waits for its selection and rides along then.
    [Fact]
    public void ACursorAimedAtAnUnselectedWindowWaitsForIt()
    {
        var (face, _) = Play(b =>
        {
            WindowSize(b, 1, 3 * Units, 10 * Units);
            MoveWindow(b, 1, 3 * Units + 1, 1);
            // Aimed at window 1 while window 0 is selected.
            b.OpVar(0x0F, Arg.Large(1 + Units), Arg.Large(1 + 3 * Units), Arg.Small(1));
            b.Print("zero");
            b.OpVar(0x0B, Arg.Small(1));
            b.Print("one");
            // Now selected, so this move lands at once.
            b.OpVar(0x0F, Arg.Large(1), Arg.Large(1), Arg.Small(1));
            b.Print("X");
        });
        Assert.Equal("zero", face.Model.RowText(1));
        Assert.Equal("   one", face.Model.RowText(5));
        Assert.Equal("X", face.Model.RowText(4));
    }

    // §15's scroll_window shifts a window's own rectangle, which only a
    // stage has the pixels to do.
    [Fact]
    public void ScrollWindowShiftsTheRectangle()
    {
        var (face, screen) = Play(b =>
        {
            WindowSize(b, 2, 3 * Units, 4 * Units);
            MoveWindow(b, 2, 1, 1);
            b.OpVar(0x0B, Arg.Small(2));
            b.Print("ab");
            b.Ext(0x14, Arg.Small(2), Arg.Large(Units));
        });
        Assert.Equal("", face.Model.RowText(1));
        Assert.Contains(screen.Settled, paint => paint is ShiftPaint { Rise: Units });
    }

    // A line count written through put_wind_prop paces the window's
    // [MORE], and -999 stops it pausing at all (§8.8.3.2.6).
    [Fact]
    public void ALineCountWrittenThroughThePropertyPacesThePause()
    {
        var (face, screen) = Play(b =>
        {
            b.Ext(0x19, Arg.Small(0), Arg.Small(WindowLedger.TextStyle), Arg.Small(2));
            b.Ext(0x19, Arg.Small(0), Arg.Small(WindowLedger.LineCount), Arg.Large(0xFC19));
            b.Print("a\nb\nc\nd\ne\nf\ng\nh");
        });
        Assert.DoesNotContain(screen.Settled.OfType<TextPaint>(), paint => paint.Cell.Style == ScreenModel.Reverse);
        Assert.Equal("h", face.Model.RowText(6));
    }

    // set_margins reaches the stage, which clips its wrapping text to
    // stay inside them (§8.8.3.2.1).
    [Fact]
    public void MarginsSetByTheOpcodeClipTheText()
    {
        var (face, _) = Play(b =>
        {
            b.Ext(0x08, Arg.Large(Units), Arg.Large(2 * Units), Arg.Small(0));
            b.Print("abcdefghij");
        });
        Assert.Equal(" abcdefg", face.Model.RowText(1));
        Assert.Equal(" hij", face.Model.RowText(2));
    }

    // erase_line's Version 6 form erases a width in units, one less
    // than the value it is given (§8.8.5.2).
    [Fact]
    public void EraseLineErasesAWidthInUnits()
    {
        var (face, _) = Play(b =>
        {
            b.Print("abcdef");
            b.OpVar(0x0F, Arg.Large(1), Arg.Large(1 + Units));
            b.OpVar(0x0E, Arg.Large(2 * Units + 1));
        });
        Assert.Equal("a  def", face.Model.RowText(1));
    }

    // A stage renders all eight windows, so erasing one above the two a
    // character face paints reaches it (§8.8.5.3).
    [Fact]
    public void ErasingAHigherWindowReachesTheStage()
    {
        var (face, _) = Play(b =>
        {
            WindowSize(b, 3, 2 * Units, 4 * Units);
            MoveWindow(b, 3, 1, 1);
            b.Print("abcdefghij");
            b.OpVar(0x0D, Arg.Large(3));
        });
        Assert.Equal("    efghij", face.Model.RowText(1));
    }

    // The same story on a character face leaves the transcript exactly
    // as it was: none of these seams is sent, and the sweep that
    // certifies the corpus is untouched by construction.
    [Fact]
    public void ACharacterFaceHearsNoneOfIt()
    {
        var b = new StoryBuilder(6);
        var main = b.Routine(0);
        WindowSize(b, 3, 2 * Units, 4 * Units);
        MoveWindow(b, 3, 1, 1);
        b.Ext(0x08, Arg.Large(Units), Arg.Large(2 * Units), Arg.Small(0));
        b.Ext(0x19, Arg.Small(0), Arg.Small(WindowLedger.LineCount), Arg.Large(0xFC19));
        b.Ext(0x14, Arg.Small(0), Arg.Large(Units));
        b.Print("plain");
        b.OpVar(0x0E, Arg.Large(2 * Units + 1));
        b.OpVar(0x0D, Arg.Large(3));
        b.Quit();
        b.InitialPc = main;
        Assert.Equal("plain", Session.Run(b).Output);
    }
}
