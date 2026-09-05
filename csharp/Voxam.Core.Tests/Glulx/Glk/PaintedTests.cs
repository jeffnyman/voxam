using System.Globalization;
using Voxam.Core.Glulx.Glk;
using SessionEndException = Voxam.Core.SessionEndException;

namespace Voxam.Tests.Glulx.Glk;

/// <summary>Where a painted display's input and echoes are heard.</summary>
internal sealed class Heard
{
    public List<string> Said { get; } = [];

    public void Line(string text, uint terminator) =>
        Said.Add($"line '{text}' term {terminator}");

    public void Key(uint code) => Said.Add($"key {code}");
}

/// <summary>
/// The painted spine over a stub that records placements rather than
/// drawing them, which is the level the layout can be read at.
/// </summary>
internal sealed class PaperDisplay(Heard heard) : PaintedDisplay(heard.Line, heard.Key)
{
    public List<string> Paints { get; } = [];

    public Queue<uint?> Keys { get; } = [];

    public (int Width, int Height) Room { get; set; } = (20, 6);

    public Metrics Cell { get; set; } = Metrics.CharacterCell;

    public override bool Graphics => true;

    public bool Dry { get; private set; }

    public override Metrics Metrics => Cell;

    public override (int Width, int Height) Size() => Room;

    /// <summary>Everything placed since the last look, as one string.</summary>
    public string Taken()
    {
        var shown = string.Join(" ", Paints);

        Paints.Clear();

        return shown;
    }

    protected override void Begin() => Paints.Add("|");

    protected override void Place(int x, int y, IReadOnlyList<Segment> line)
    {
        var runs = string.Join("", line.Select(segment => segment.Text));

        Paints.Add(string.Create(CultureInfo.InvariantCulture, $"{x},{y}[{runs}]"));
    }

    protected override void Finish((int X, int Y)? cursor) =>
        Paints.Add(cursor is { } at
            ? string.Create(CultureInfo.InvariantCulture, $"^{at.X},{at.Y}")
            : "^-");

    protected override uint? Translated(double? timeout)
    {
        if (Keys.Count == 0)
        {
            Dry = true;

            throw new SessionEndException();
        }

        return Keys.Dequeue();
    }
}

/// <summary>
/// The painted spine: the tree walk, the wrappers, the pager, the line
/// editor and the timer, over a display that records rather than draws.
/// </summary>
public sealed class PaintedTests
{
    private const uint Buf = 0x500;

    // Clearing paints every row blank, wiping whatever the shell left
    // on the glass, and parks the cursor nowhere in particular.
    [Fact]
    public void ClearingWipesEveryRow()
    {
        var (face, _, _) = Seam();

        face.Clear();

        Assert.Equal(
            "| 0,0[    ] 0,1[    ] 0,2[    ] ^-", Over(face, (4, 3)));
    }

    // A display measuring in something larger than the cell lays its
    // rows out at the metrics it names.
    [Fact]
    public void ARowLandsWhereTheMetricsPutIt()
    {
        var (face, _, _) = Seam();

        face.Cell = new Metrics(2, 3);
        face.Room = (8, 9);
        face.Clear();

        Assert.Equal("| 0,0[    ] 0,3[    ] 0,6[    ] ^-", face.Taken());
    }

    // An empty tree is nothing to paint at all.
    [Fact]
    public void AnEmptyTreeIsNothingToPaint()
    {
        var (face, _, _) = Seam();

        face.Flush(null);

        Assert.Equal("", face.Taken());
    }

    // A buffer window's text is wrapped to its width and sits at the
    // bottom of its box, the way a terminal scrolls.
    [Fact]
    public void ABuffersTextSitsAtTheBottomOfItsBox()
    {
        var (face, glk, _) = Seam();
        var window = Open(glk, WindowType.TextBuffer);

        Print(glk, window, "the quick brown fox");
        face.Flush(glk.Root);

        Assert.Equal(
            "| 0,0[                    ] 0,1[                    ] "
            + "0,2[                    ] 0,3[                    ] "
            + "0,4[                    ] 0,5[the quick brown fox ] ^-",
            face.Taken());
    }

    // A blank window shows blankness, and so does a window squeezed to
    // nothing: the box is still real and still needs covering.
    [Fact]
    public void ABlankWindowShowsBlankness()
    {
        var (face, glk, _) = Seam();

        Open(glk, WindowType.Blank);
        face.Flush(glk.Root);

        Assert.Equal(
            "| 0,0[                    ] 0,1[                    ] "
            + "0,2[                    ] 0,3[                    ] "
            + "0,4[                    ] 0,5[                    ] ^-",
            face.Taken());
    }

    // A grid is painted from its cells, row by row.
    [Fact]
    public void AGridIsPaintedFromItsCells()
    {
        var (face, glk, _) = Seam();
        var buffer = Open(glk, WindowType.TextBuffer);
        var grid = Split(glk, buffer, WindowMethod.Above | WindowMethod.Fixed, 1,
            WindowType.TextGrid);

        Print(glk, grid, "West of House");
        face.Flush(glk.Root);

        Assert.StartsWith("| 0,1[", face.Taken(), StringComparison.Ordinal);
    }

    // A graphics window's pixels are the game's own work and survive a
    // repaint; a pending clear erases the canvas once and is spent.
    [Fact]
    public void ACanvasIsLeftAloneUnlessAClearIsPending()
    {
        var (face, glk, _) = Seam();
        var canvas = (GraphicsWindow)Open(glk, WindowType.Graphics);

        Assert.True(canvas.PendingClear);

        face.Flush(glk.Root);

        Assert.False(canvas.PendingClear);
        Assert.Equal("| ^-", face.Taken());
    }

    // A line is typed one keystroke at a time and drawn as part of the
    // layout; backspace takes one back, and escape wipes the lot.
    [Fact]
    public void ALineIsEditedAsItIsTyped()
    {
        var (face, glk, heard) = Seam();
        var window = Open(glk, WindowType.TextBuffer);

        Type(face, 'g', 'o', KeyCode.Delete, 'o', KeyCode.Escape, 'n', KeyCode.Return);

        Assert.Equal(("n", 0u), Read(glk, window, face));
        Assert.Equal(["line 'n' term 0"], heard.Said);
    }

    // The line is cut to what the game's buffer holds, and a
    // terminator ends it with its own keycode.
    [Fact]
    public void ALineIsCutToItsBufferAndMayEndOnATerminator()
    {
        var (face, glk, heard) = Seam();
        var window = Open(glk, WindowType.TextBuffer);

        Call(glk, 0x00D0, Held.OfOpaque(window), new WordBuffer(3), Held.OfWord(0));
        Call(glk, 0x0151, Held.OfOpaque(window), new WordBuffer([KeyCode.Tab]));

        Type(face, 'n', 'o', 'r', 't', 'h', KeyCode.Tab);

        Assert.Equal(("nor", KeyCode.Tab), face.ReadLine(window, 3));
        Assert.Equal(["line 'nor' term 4294967287"], heard.Said);
    }

    // A character above the basic plane is one character to the editor,
    // however many units hold it, and a full line takes no more.
    [Fact]
    public void TheEditorCountsCharactersAndNotUnits()
    {
        var (face, glk, _) = Seam();
        var window = Open(glk, WindowType.TextBuffer);

        Type(face, 0x1F600, 0x1F600, 0x1F600, KeyCode.Return);

        Assert.Equal(("\U0001F600\U0001F600", 0u), face.ReadLine(window, 2));

        // And a backspace on an empty line has nothing to take.
        Type(face, KeyCode.Delete, KeyCode.Return);

        Assert.Equal(("", 0u), face.ReadLine(window, 4));
    }

    // A keystroke read hands the code straight over and tells the seam.
    [Fact]
    public void AKeystrokeIsHeardAsItIsRead()
    {
        var (face, glk, heard) = Seam();
        var window = Open(glk, WindowType.TextBuffer);

        Type(face, 'z');

        Assert.Equal((uint)'z', face.ReadChar(window));
        Assert.Equal(["key 122"], heard.Said);
    }

    // A timer coming round cuts a wait short: the display answers
    // nothing, the event is posted, and the request stays standing.
    [Fact]
    public void ATimerCutsAWaitShort()
    {
        var (face, glk, _) = Seam();
        var window = Open(glk, WindowType.TextBuffer);

        face.SetTimer(1);
        face.Keys.Enqueue(null);
        Thread.Sleep(20);

        Assert.Null(face.ReadChar(window));
        Assert.Equal(EventType.Timer, Assert.Single(glk.PendingEvents).Kind);
        Assert.True(face.TimerInput);
    }

    // An event the display posted itself brings the wait back round
    // just as a timer does, so glk_select can deliver it.
    [Fact]
    public void APostedEventBringsTheWaitBackRound()
    {
        var (face, glk, _) = Seam();
        var window = Open(glk, WindowType.TextBuffer);

        glk.PostEvent(new GlkEvent(EventType.Redraw));
        face.Keys.Enqueue(null);

        Assert.Null(face.ReadChar(window));
    }

    // More text than a windowful holds, and a keystroke turns the page
    // rather than reaching the game.
    [Fact]
    public void AKeyTurnsThePageBeforeItReachesTheGame()
    {
        var (face, glk, _) = Seam();
        var window = Open(glk, WindowType.TextBuffer);

        for (var line = 0; line < 12; line++)
        {
            Print(glk, window, "line\n");
        }

        face.Flush(glk.Root);

        Assert.Contains(PaintedDisplay.MorePrompt, face.Taken(), StringComparison.Ordinal);

        // One key at a time, so the pager's own appetite is measured
        // rather than guessed at: a key it eats leaves the read asking
        // for another, and the queue runs dry.
        var turns = 0;
        uint? reached = null;

        while (reached is null && turns < 10)
        {
            face.Keys.Enqueue(' ');

            try
            {
                reached = face.ReadChar(window);
            }
            catch (SessionEndException)
            {
                turns++;
            }
        }

        Assert.True(turns > 0);
        Assert.Equal((uint)' ', reached);

        // And with the text all read, the prompt is gone. The repaints
        // the page turns made are discarded first: they are the frames
        // that still carried it.
        face.Taken();
        face.Flush(glk.Root);

        Assert.DoesNotContain(
            PaintedDisplay.MorePrompt, face.Taken(), StringComparison.Ordinal);
    }

    // A file prompt takes the bottom line, and both ways of answering
    // it are heard at the line seam.
    [Fact]
    public void AFilePromptTakesTheBottomLine()
    {
        var (face, glk, heard) = Seam();

        Open(glk, WindowType.TextBuffer);
        Type(face, 'a', 'b', KeyCode.Return);

        Assert.Equal("ab", face.PromptFile(FileUsage.SavedGame, GlkFileMode.Write));
        Assert.Equal(["line 'ab' term 0"], heard.Said);

        heard.Said.Clear();
        Type(face, 'c', KeyCode.Escape);

        Assert.Null(face.PromptFile(FileUsage.SavedGame, GlkFileMode.Read));
        Assert.Equal(["line '' term 0"], heard.Said);

        // A line with nothing but space in it is a cancel too.
        heard.Said.Clear();
        Type(face, ' ', KeyCode.Return);

        Assert.Null(face.PromptFile(FileUsage.SavedGame, GlkFileMode.Read));
    }

    // A file prompt forces every window to the end first, so the player
    // is answering a question rather than fighting the pager for the
    // keyboard.
    [Fact]
    public void AFilePromptForcesEveryWindowToTheEnd()
    {
        var (face, glk, _) = Seam();
        var window = Open(glk, WindowType.TextBuffer);

        for (var line = 0; line < 12; line++)
        {
            Print(glk, window, "line\n");
        }

        face.Flush(glk.Root);

        Assert.Contains(PaintedDisplay.MorePrompt, face.Taken(), StringComparison.Ordinal);

        Type(face, 'a', KeyCode.Return);

        Assert.Equal("a", face.PromptFile(FileUsage.SavedGame, GlkFileMode.Write));

        // The prompt caught the window up on its way in, so nothing is
        // waiting behind it any more.
        face.Taken();
        face.Flush(glk.Root);

        Assert.DoesNotContain(
            PaintedDisplay.MorePrompt, face.Taken(), StringComparison.Ordinal);
    }

    // A timer during a file prompt is not an event: the prompt simply
    // asks again.
    [Fact]
    public void ATimerDuringAFilePromptIsNotAnEvent()
    {
        var (face, glk, _) = Seam();

        Open(glk, WindowType.TextBuffer);
        face.SetTimer(1);
        Thread.Sleep(20);
        Type(face, null, 'q', KeyCode.Return);

        // The event is posted, as it is anywhere else; what it does not
        // do is answer the question.
        Assert.Equal("q", face.PromptFile(FileUsage.SavedGame, GlkFileMode.Write));
        Assert.Equal(EventType.Timer, Assert.Single(glk.PendingEvents).Kind);
    }

    // Two styles differ here when their dress differs, and the hints
    // are measured in the one unit a painted display has.
    [Fact]
    public void StylesAreToldApartByTheirDress()
    {
        var (face, glk, _) = Seam();
        var window = Open(glk, WindowType.TextBuffer);

        Assert.True(face.StyleDistinguish(window, TextStyle.Normal, TextStyle.Header));
        Assert.False(face.StyleDistinguish(window, TextStyle.Header, TextStyle.Subheader));
        Assert.False(face.StyleDistinguish(window, TextStyle.Normal, TextStyle.Preformatted));

        Assert.Equal(0u, face.StyleMeasure(window, TextStyle.Header, 3));
        Assert.Equal(1u, face.StyleMeasure(window, TextStyle.Header, 4));
        Assert.Equal(0u, face.StyleMeasure(window, TextStyle.Normal, 4));
        Assert.Equal(1u, face.StyleMeasure(window, TextStyle.Emphasized, 5));
        Assert.Equal(0u, face.StyleMeasure(window, TextStyle.Normal, 5));
        Assert.Equal(0u, face.StyleMeasure(window, TextStyle.Normal, 6));
        Assert.Equal(0u, face.StyleMeasure(window, TextStyle.Normal, 0));
        Assert.Equal(0u, face.StyleMeasure(window, TextStyle.Normal, 1));
        Assert.Null(face.StyleMeasure(window, TextStyle.Normal, 2));

        // Alert is the one style wearing two attributes at once.
        Assert.Equal(new Attributes(true, false, true), PaintedDisplay.Dressing(TextStyle.Alert));
    }

    // A grid row's per-cell dress collapses into runs, and a row longer
    // than its dress wears the plain one.
    [Fact]
    public void AGridRowCollapsesIntoRuns()
    {
        var grouped = PaintedDisplay.Grouped(
            ["a", "b", "c", "d"], [1, 1, 2], [0, 0, 0]);

        Assert.Equal(3, grouped.Count);
        Assert.Equal("ab", grouped[0].Text);
        Assert.Equal("c", grouped[1].Text);
        Assert.Equal("d", grouped[2].Text);
        Assert.Equal(TextStyle.Normal, grouped[2].Key.Style);
    }

    // The line being typed is drawn into the window it is going to, as
    // part of the layout and not yet part of the text.
    [Fact]
    public void TheTypedLineIsDrawnWhereItIsGoing()
    {
        var (face, glk, _) = Seam();
        var window = Open(glk, WindowType.TextBuffer);

        Print(glk, window, "you are here. ");
        face.Flush(glk.Root);
        face.Taken();

        Type(face, 'n', 'o', KeyCode.Return);

        Assert.Equal(("no", 0u), Read(glk, window, face));

        var frames = face.Taken();

        // The half-typed line shows, and the cursor sits after it.
        Assert.Contains("you are here. n ", frames, StringComparison.Ordinal);
        Assert.Contains("^16,5", frames, StringComparison.Ordinal);

        // And the window's own text still ends where the game left it,
        // until Glk echoes the accepted line into it.
        Assert.Contains("you are here.       ", face.Taken() + frames, StringComparison.Ordinal);
    }

    // A grid taking line input shows it at the cursor, where the game
    // left it: there is nowhere else it could sensibly go.
    [Fact]
    public void AGridShowsTheTypedLineAtItsCursor()
    {
        var (face, glk, _) = Seam();
        var buffer = Open(glk, WindowType.TextBuffer);
        var grid = Split(glk, buffer, WindowMethod.Above | WindowMethod.Fixed, 2,
            WindowType.TextGrid);

        Call(glk, 0x002B, Held.OfOpaque(grid), Held.OfWord(2), Held.OfWord(1));
        face.Flush(glk.Root);
        face.Taken();

        Type(face, 'h', 'i', KeyCode.Return);

        Assert.Equal(("hi", 0u), Read(glk, grid, face));

        var frames = face.Taken();

        Assert.Contains("2,1[h]", frames, StringComparison.Ordinal);
        Assert.Contains("^3,1", frames, StringComparison.Ordinal);
    }

    // A buffer squeezed flat by a split still keeps its text; there is
    // just nowhere to paint it.
    [Fact]
    public void ABufferSqueezedFlatKeepsItsTextAnyway()
    {
        var (face, glk, _) = Seam();
        var buffer = Open(glk, WindowType.TextBuffer);

        Print(glk, buffer, "still here");
        Split(glk, buffer, WindowMethod.Above | WindowMethod.Fixed, 6, WindowType.TextGrid);
        face.Flush(glk.Root);

        Assert.Equal(0, buffer.Height);
        Assert.DoesNotContain("still here", face.Taken(), StringComparison.Ordinal);
    }

    // A canvas is erased once and then left alone: its pixels are the
    // game's own work and survive every later repaint.
    [Fact]
    public void ACanvasIsErasedOnceAndThenLeftAlone()
    {
        var (face, glk, _) = Seam();

        Open(glk, WindowType.Graphics);
        face.Flush(glk.Root);
        face.Taken();
        face.Flush(glk.Root);

        Assert.Equal("| ^-", face.Taken());
    }

    // A timer coming round mid-line leaves the half-typed line where it
    // is and the request standing.
    [Fact]
    public void ATimerMidLineLeavesTheLineStanding()
    {
        var (face, glk, _) = Seam();
        var window = Open(glk, WindowType.TextBuffer);

        Call(glk, 0x00D0, Held.OfOpaque(window), new WordBuffer(8), Held.OfWord(0));
        face.SetTimer(1);
        Type(face, 'n', null);
        Thread.Sleep(20);

        Assert.Null(face.ReadLine(window, 8));
        Assert.NotNull(window.LineRequest);
        Assert.Equal(EventType.Timer, Assert.Single(glk.PendingEvents).Kind);
    }

    // A timer that has not come round yet is not a timer coming round:
    // the read simply waits for the next key.
    [Fact]
    public void ATimerNotYetDueDoesNotInterrupt()
    {
        var (face, glk, _) = Seam();
        var window = Open(glk, WindowType.TextBuffer);

        face.SetTimer(100000);
        Type(face, null, 'x');

        Assert.Equal((uint)'x', face.ReadChar(window));
        Assert.Empty(glk.PendingEvents);
    }

    // A timer set to nothing is a timer stopped, and a read with none
    // running simply waits for the next key.
    [Fact]
    public void ATimerSetToNothingIsATimerStopped()
    {
        var (face, glk, _) = Seam();
        var window = Open(glk, WindowType.TextBuffer);

        face.SetTimer(10);
        face.SetTimer(0);
        Thread.Sleep(20);
        Type(face, null, 'x');

        Assert.Equal((uint)'x', face.ReadChar(window));
        Assert.Empty(glk.PendingEvents);
    }

    // A window with no width of its own is wrapped to a conventional
    // one, since text has to be broken somewhere.
    [Fact]
    public void AWindowWithNoWidthIsWrappedToAConventionalOne()
    {
        var (face, glk, _) = Seam();

        face.Room = (0, 6);

        var window = Open(glk, WindowType.TextBuffer);

        Print(glk, window, "text");
        face.Flush(glk.Root);

        // Twice, so the wrapper is met once new and once already made.
        Print(glk, window, " more");
        face.Flush(glk.Root);

        Assert.Equal(0, window.Width);
    }

    // A code outside the printable range is not a character to type:
    // neither a control code below it, nor a special key above every
    // character there is, which is where the keycodes live.
    [Fact]
    public void ACodeOutsideThePrintableRangeTypesNothing()
    {
        var (face, glk, _) = Seam();
        var window = Open(glk, WindowType.TextBuffer);

        Type(face, 1, KeyCode.Up, 'a', KeyCode.PageDown, KeyCode.Return);

        Assert.Equal(("a", 0u), Read(glk, window, face));
    }

    // A display of one's own has nothing to leave behind on retiring.
    [Fact]
    public void AWindowOfOnesOwnRetiresQuietly()
    {
        var (face, _, _) = Seam();

        face.Retire();

        Assert.Equal("", face.Taken());
    }

    /// <summary>Everything placed since the last look, at a chosen size.</summary>
    private static string Over(PaperDisplay face, (int Width, int Height) room)
    {
        face.Paints.Clear();
        face.Room = room;
        face.Clear();

        return face.Taken();
    }

    /// <summary>Queue keystrokes, characters or keycodes alike.</summary>
    private static void Type(PaperDisplay face, params object?[] keys)
    {
        foreach (var key in keys)
        {
            face.Keys.Enqueue(key switch
            {
                null => null,
                char character => character,
                int code => (uint)code,
                _ => (uint)key,
            });
        }
    }

    /// <summary>Open a line request and read it.</summary>
    private static (string Text, uint Terminator)? Read(
        Api glk, Window window, PaperDisplay face)
    {
        Call(glk, 0x00D0, Held.OfOpaque(window), new WordBuffer(16), Held.OfWord(0));

        return face.ReadLine(window, 16);
    }

    /// <summary>Print into a window, through the library.</summary>
    private static void Print(Api glk, Window window, string text)
    {
        Call(glk, 0x002F, Held.OfOpaque(window));
        Call(glk, 0x0082, text);
    }

    private static Window Open(Api glk, uint wtype) => (Window)Call(
        glk, 0x0023, Held.OfOpaque(null), Held.OfWord(0), Held.OfWord(0),
        Held.OfWord(wtype), Held.OfWord(0)).Opaque!;

    private static Window Split(Api glk, Window window, uint method, int size, uint wtype) =>
        (Window)Call(
            glk, 0x0023, Held.OfOpaque(window), Held.OfWord(method), Held.OfWord((uint)size),
            Held.OfWord(wtype), Held.OfWord(0)).Opaque!;

    private static Held Call(Api glk, int selector, params object?[] args) =>
        glk.Call(Signatures.Lookup(selector)!, args);

    private static (PaperDisplay Face, Api Glk, Heard Heard) Seam()
    {
        var heard = new Heard();
        var face = new PaperDisplay(heard);

        return (face, new Api(face), heard);
    }
}
