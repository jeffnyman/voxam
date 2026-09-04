namespace Voxam.Core.Tests;

/// <summary>The Version 6 stage as pure state: eight windows, one grid, and the paints a glass carries out (§8.8).</summary>
public class StageModelTests
{
    private const int Units = 2;

    // A stage measuring two units to the cell each way, so a unit
    // position is never mistaken for a cell one.
    private static StageModel Stage(int columns = 10, int lines = 5) => new(columns, lines, Units, Units);

    private static List<Paint> Drained(StageModel stage) => [.. stage.Paints()];

    [Fact]
    public void TheBootStageIsWindowZeroFillingTheScreen()
    {
        var stage = Stage();
        Assert.Equal((10, 5), (stage.Columns, stage.Lines));
        Assert.Equal(0, stage.Selected);
        Assert.Equal(ScreenModel.DefaultColour, stage.Foreground);
        Assert.Equal(ScreenModel.DefaultColour, stage.Background);
        stage.Write("hello");
        Assert.Equal("hello", stage.RowText(1));
        Assert.Equal("hello\n\n\n\n", stage.Rendered());
    }

    // Window 0 wraps at its right edge and carries whole words over
    // while buffering is on (§8.8.3.1).
    [Fact]
    public void AWrappingWindowBreaksWholeWordsAtItsEdge()
    {
        var stage = Stage();
        stage.Write("alpha beta gamma");
        Assert.Equal("alpha beta", stage.RowText(1));
        Assert.Equal("gamma", stage.RowText(2));
    }

    // A word that will not fit the rest of the line, but would fit a
    // line of its own, is carried over whole; one too long for any line
    // is broken where it falls.
    [Fact]
    public void AWordTooLongForAnyLineIsBrokenWhereItFalls()
    {
        var carried = Stage();
        carried.Write("abcde fghij");
        Assert.Equal("abcde", carried.RowText(1));
        Assert.Equal("fghij", carried.RowText(2));

        var broken = Stage();
        broken.Write("ab cdefghijklmn");
        Assert.Equal("ab cdefghi", broken.RowText(1));
        Assert.Equal("jklmn", broken.RowText(2));
    }

    // Unbuffered, every character lands where it falls and a word is
    // broken across the edge (§8.8.3.1.2).
    [Fact]
    public void UnbufferedPrintingBreaksMidWord()
    {
        var stage = Stage();
        stage.SetBuffering(false);
        stage.Write("alphabetagamma");
        Assert.Equal("alphabetag", stage.RowText(1));
        Assert.Equal("amma", stage.RowText(2));
        stage.SetBuffering(true);
        stage.Write("!");
        Assert.Equal("amma!", stage.RowText(2));
    }

    // A window with neither attribute overlays until its right margin,
    // where the cursor stays and further text is ignored (§8.8.3.1.1).
    [Fact]
    public void AnOverlayingWindowStopsAtItsRightMargin()
    {
        var stage = Stage();
        stage.PlaceWindow(2, 1, 1, 2 * Units, 4 * Units);
        stage.SetWindow(2);
        stage.Write("abcdefg");
        Assert.Equal("abcd", stage.RowText(1));
        Assert.Equal((1, 4 * Units + 1), stage.GetCursor());
        stage.Write("h");
        Assert.Equal("abcd", stage.RowText(1));
    }

    // Text lands where the window was when it was printed: moving the
    // window afterwards moves only its bookkeeping (§8.8.3).
    [Fact]
    public void MovingAWindowLeavesItsPrintingBehind()
    {
        var stage = Stage();
        stage.PlaceWindow(3, 3 * Units + 1, 2 * Units + 1, 2 * Units, 4 * Units);
        stage.SetWindow(3);
        stage.Write("xy");
        Assert.Equal("  xy", stage.RowText(4));
        stage.PlaceWindow(3, 1, 1, 2 * Units, 4 * Units);
        stage.Write("z");
        Assert.Equal("  xy", stage.RowText(4));
        Assert.Equal("  z", stage.RowText(1));
    }

    // Each window keeps its own cursor, so selection homes nothing
    // (§8.8.3.5), and a cursor is read back in the window's own units.
    [Fact]
    public void EachWindowRemembersItsOwnCursor()
    {
        var stage = Stage();
        stage.PlaceWindow(1, 1, 1, 2 * Units, 10 * Units);
        stage.Write("ab");
        stage.SetWindow(1);
        Assert.Equal((1, 1), stage.GetCursor());
        stage.Write("Z");
        stage.SetWindow(0);
        Assert.Equal((1, 2 * Units + 1), stage.GetCursor());
        stage.SetCursor(1 + Units, 1 + 3 * Units);
        Assert.Equal((1 + Units, 1 + 3 * Units), stage.GetCursor());
        Assert.Equal((1 + Units, 1 + 3 * Units), stage.ScreenCursor());
    }

    // A cursor set outside its window's origin still reads absolutely
    // from the screen's own corner (§8.7.2.3.2).
    [Fact]
    public void TheScreenCursorFoldsInTheWindowsOrigin()
    {
        var stage = Stage();
        stage.PlaceWindow(4, 2 * Units + 1, 3 * Units + 1, 2 * Units, 4 * Units);
        stage.SetWindow(4);
        stage.SetCursor(1 + Units, 1);
        Assert.Equal((1 + Units, 1), stage.GetCursor());
        Assert.Equal((3 * Units + 1, 3 * Units + 1), stage.ScreenCursor());
    }

    // §8.8.4.1's split tiles windows 1 and 0 vertically without
    // touching widths, and a cursor stranded outside homes.
    [Fact]
    public void TheSplitTilesTheTwoWindowsAndKeepsAbsoluteCursors()
    {
        var stage = Stage();
        stage.Write("one\ntwo");
        stage.SplitWindow(2 * Units);
        stage.Write("!");
        Assert.Equal("two", stage.RowText(2));
        Assert.Equal("!", stage.RowText(3));
        stage.SetWindow(1);
        stage.Write("top");
        Assert.Equal("top", stage.RowText(1));
        stage.SetWindow(0);
        stage.SplitWindow(4 * Units);
        stage.Write("?");
        Assert.Equal("?", stage.RowText(5));
    }

    [Fact]
    public void WindowMinusOneErasesTheScreenAndUnsplits()
    {
        var stage = Stage();
        stage.SplitWindow(2 * Units);
        stage.SetWindow(1);
        stage.Write("top");
        stage.SetWindow(0);
        stage.Write("bottom");
        Drained(stage);
        var erased = stage.EraseWindow(-1);
        Assert.Equal(new Rectangle(1, 1, 5, 10), erased);
        Assert.Equal("\n\n\n\n", stage.Rendered());
        Assert.Equal(0, stage.Selected);
        Assert.Equal([new FillPaint(1, 1, 5 * Units, 10 * Units, ScreenModel.DefaultColour)], Drained(stage));
        stage.Write("fresh");
        Assert.Equal("fresh", stage.RowText(1));
    }

    // Window -2 erases the screen to the current background and leaves
    // the split alone (§8.8.5.3.2).
    [Fact]
    public void WindowMinusTwoErasesTheScreenAndKeepsTheSplit()
    {
        var stage = Stage();
        stage.SplitWindow(2 * Units);
        stage.SetColour(3, 4);
        stage.Write("text");
        var erased = stage.EraseWindow(-2);
        Assert.Equal(new Rectangle(1, 1, 5, 10), erased);
        Assert.Equal(4, stage.CellAt(1, 1).Background);
        stage.Write("!");
        Assert.Equal("    !", stage.RowText(3));
    }

    // A plain window erases its own rectangle in units, homes its
    // cursor, and refills its [MORE] budget (§8.8.5.3).
    [Fact]
    public void APlainWindowErasesItsOwnRectangle()
    {
        var stage = Stage();
        stage.PlaceWindow(2, 2 * Units + 1, 1, 2 * Units, 4 * Units);
        stage.Write("aaaaaaaaaa\nbbbbbbbbbb\ncccccccccc");
        stage.SetWindow(2);
        Drained(stage);
        var erased = stage.EraseWindow(2);
        Assert.Equal(new Rectangle(3, 1, 2, 4), erased);
        Assert.Equal("    cccccc", stage.RowText(3));
        Assert.Contains(new FillPaint(2 * Units + 1, 1, 2 * Units, 4 * Units, ScreenModel.DefaultColour), Drained(stage));
        stage.Write("z");
        Assert.Equal("z", stage.RowText(3)[..1]);
        // A window told never to pause keeps that through an erasure.
        stage.SetLineCount(2, StageModel.NeverMore);
        stage.EraseWindow(2);
        var pauses = 0;
        stage.More = (_, _, _, _) => pauses++;
        stage.Write("1\n2\n3\n4");
        Assert.Equal(0, pauses);
    }

    [Fact]
    public void AWindowOutsideTheEightIsRefused()
    {
        var stage = Stage();
        Assert.Equal("window 8 is not one of the eight (§8.8.3)", Assert.Throws<ZMachineException>(() => stage.SetWindow(8)).Message);
        Assert.Throws<ZMachineException>(() => stage.EraseWindow(9));
        Assert.Throws<ZMachineException>(() => stage.PlaceWindow(-4, 1, 1, 1, 1));
        Assert.Throws<ZMachineException>(() => stage.SetLineCount(8, 0));
        Assert.Throws<ZMachineException>(() => stage.SetMargins(8, 0, 0));
        Assert.Throws<ZMachineException>(() => stage.ScrollWindow(8, 0));
    }

    // A scrolling window scrolls its own rectangle, and the scroll is
    // owed until the next text arrives so the last line stays at the
    // window's foot.
    [Fact]
    public void AScrollingWindowScrollsItsOwnRectangleWhenTextArrives()
    {
        var stage = Stage(columns: 4, lines: 3);
        stage.Write("a\nb\nc");
        Assert.Equal("a\nb\nc", stage.Rendered());
        stage.Write("\n");
        Assert.Equal("a\nb\nc", stage.Rendered());
        stage.Write("d");
        Assert.Equal("b\nc\nd", stage.Rendered());
        // A second feed at the foot pays the owed scroll on its way.
        stage.Write("\n\ne");
        Assert.Equal("d\n\ne", stage.Rendered());
    }

    // §15's scroll_window is unrelated to the scrolling attribute: it
    // shifts a window's rectangle by whole cell rows, up or down.
    [Fact]
    public void ScrollWindowShiftsARectangleEitherWay()
    {
        var stage = Stage(columns: 4, lines: 4);
        stage.PlaceWindow(2, 1, 1, 3 * Units, 4 * Units);
        stage.SetWindow(2);
        stage.SetCursor(1, 1);
        stage.Write("aa");
        stage.SetCursor(1 + Units, 1);
        stage.Write("bb");
        Drained(stage);
        stage.ScrollWindow(2, Units);
        Assert.Equal("bb\n\n\n", stage.Rendered());
        var paints = Drained(stage);
        Assert.Contains(new ShiftPaint(1, 1, 3 * Units, 4 * Units, Units), paints);
        Assert.Contains(new FillPaint(1 + 2 * Units, 1, Units, 4 * Units, ScreenModel.DefaultColour), paints);
        stage.ScrollWindow(2, -Units);
        Assert.Equal("\nbb\n\n", stage.Rendered());
        Assert.Contains(new ShiftPaint(1, 1, 3 * Units, 4 * Units, -Units), Drained(stage));
    }

    // Only the flowed region between the margins scrolls: Shogun
    // anchors art in a margin while the text beside it scrolls
    // (§8.8.3.2.1).
    [Fact]
    public void AScrollLeavesTheMarginsUnswept()
    {
        var stage = Stage(columns: 6, lines: 3);
        stage.SetMargins(0, Units, Units);
        stage.Write("aa\nbb");
        Drained(stage);
        stage.ScrollWindow(0, Units);
        var shift = Assert.IsType<ShiftPaint>(Drained(stage)[0]);
        Assert.Equal(1 + Units, shift.Column);
        Assert.Equal(4 * Units, shift.Width);
    }

    // The margins clip wrapping text, and a cursor they would strand
    // moves to the left margin (§8.8.3.2.2.2).
    [Fact]
    public void MarginsClipTheTextAndRehomeAStrandedCursor()
    {
        var stage = Stage(columns: 8, lines: 3);
        stage.SetCursor(1, 7 * Units + 1);
        stage.SetMargins(0, Units, 2 * Units);
        Assert.Equal((1, Units + 1), stage.GetCursor());
        stage.Write("abcdefgh");
        Assert.Equal(" abcde", stage.RowText(1));
        Assert.Equal(" fgh", stage.RowText(2));
    }

    // A window whose margins leave no room, or which has no rows at
    // all, swallows its text.
    [Fact]
    public void AWindowWithNoRoomPrintsNothing()
    {
        var stage = Stage();
        stage.PlaceWindow(5, 1, 1, 2 * Units, 4 * Units);
        stage.SetWindow(5);
        stage.SetMargins(5, 2 * Units, 2 * Units);
        stage.Write("nope");
        Assert.Equal("", stage.Rendered().Trim());
        stage.PlaceWindow(5, 1, 1, 0, 4 * Units);
        stage.SetMargins(5, 0, 0);
        stage.Write("nope");
        Assert.Equal("", stage.Rendered().Trim());
    }

    // The [MORE] seam fires when a scrolling window has fed a screenful
    // since the player last rested, and -999 never pauses (§8.8.3.2.6).
    [Fact]
    public void AScreenfulEarnsThePauseUntilTheLineCountForbidsIt()
    {
        var stage = Stage(columns: 4, lines: 3);
        var pauses = new List<(int Line, int Column, int Foreground, int Background)>();
        stage.More = (line, column, foreground, background) => pauses.Add((line, column, foreground, background));
        stage.Write("a\nb\nc\nd\ne\nf");
        Assert.Equal(2, pauses.Count);
        Assert.Equal((1 + 2 * Units, 1, ScreenModel.DefaultColour, ScreenModel.DefaultColour), pauses[0]);
        stage.Rest();
        stage.SetLineCount(0, StageModel.NeverMore);
        stage.Write("g\nh\ni\nj\nk\nl");
        Assert.Equal(2, pauses.Count);
        stage.Rest();
        stage.Write("m\n");
        Assert.Equal(2, pauses.Count);
    }

    // A window that never scrolls never pauses, whatever it prints.
    [Fact]
    public void AnOverlayingWindowNeverPauses()
    {
        var stage = Stage(columns: 4, lines: 3);
        var pauses = 0;
        stage.More = (_, _, _, _) => pauses++;
        stage.PlaceWindow(1, 1, 1, 2 * Units, 4 * Units);
        stage.SetWindow(1);
        stage.Write("a\nb\nc\nd\ne");
        Assert.Equal(0, pauses);
    }

    [Fact]
    public void EraseLineClearsToTheMarginOrAcrossAWidth()
    {
        var stage = Stage(columns: 6, lines: 2);
        stage.Write("abcdef");
        stage.SetCursor(1, 2 * Units + 1);
        Drained(stage);
        stage.EraseLine();
        Assert.Equal("ab", stage.RowText(1));
        Assert.Equal([new FillPaint(1, 2 * Units + 1, Units, 4 * Units, ScreenModel.DefaultColour)], Drained(stage));
        stage.SetCursor(1, 1);
        stage.Write("abcdef");
        stage.SetCursor(1, Units + 1);
        stage.EraseLine(2 * Units);
        Assert.Equal("a  def", stage.RowText(1));
        stage.EraseLine(0);
        Assert.Equal("a  def", stage.RowText(1));
    }

    // An erase below the window's own rows has nothing to clear.
    [Fact]
    public void EraseLineOutsideTheWindowDoesNothing()
    {
        var stage = Stage(columns: 6, lines: 3);
        stage.PlaceWindow(2, 1, 1, Units, 4 * Units);
        stage.SetWindow(2);
        stage.SetCursor(1 + 2 * Units, 1);
        stage.EraseLine();
        Assert.Empty(Drained(stage));
    }

    [Fact]
    public void RubbingOutRetreatsAndBlanksTheCell()
    {
        var stage = Stage();
        stage.Write("ab");
        Drained(stage);
        stage.RubOut();
        Assert.Equal("a", stage.RowText(1));
        Assert.Equal([new FillPaint(1, Units + 1, Units, Units, ScreenModel.DefaultColour)], Drained(stage));
        stage.RubOut();
        Assert.Equal("", stage.RowText(1));
        Drained(stage);
        stage.RubOut();
        Assert.Empty(Drained(stage));
    }

    [Fact]
    public void RetreatingMovesTheCursorWithoutErasing()
    {
        var stage = Stage();
        stage.Write("abc");
        Assert.Equal(2, stage.Retreat(2));
        Assert.Equal("abc", stage.RowText(1));
        Assert.Equal(1, stage.Retreat(5));
        Assert.Equal((1, 1), stage.GetCursor());
    }

    // A rectangle prints right and down from the cursor, overlaying
    // without wrap, and stops at the window's last row.
    [Fact]
    public void ARectanglePrintsWithoutWrapping()
    {
        var stage = Stage(columns: 6, lines: 3);
        stage.SetCursor(1, Units + 1);
        stage.WriteRectangle(["ab", "cd", "ef", "gh"]);
        Assert.Equal(" ab", stage.RowText(1));
        Assert.Equal(" cd", stage.RowText(2));
        Assert.Equal(" gh", stage.RowText(3));
        stage.Write("!");
        Assert.Equal(" gh!", stage.RowText(3));
    }

    // The dress a cell wears is the selected window's, and each window
    // dresses independently (§8.8.3.2).
    [Fact]
    public void EveryWindowWearsItsOwnDress()
    {
        var stage = Stage();
        stage.SetStyle(ScreenModel.Bold);
        stage.SetStyle(ScreenModel.Italic);
        stage.SetColour(3, 4);
        stage.SetFont(3);
        stage.Write("a");
        var cell = stage.CellAt(1, 1);
        Assert.Equal(new Cell("a", ScreenModel.Bold | ScreenModel.Italic, 3, 4, 3), cell);
        stage.PlaceWindow(1, 1 + Units, 1, Units, 4 * Units);
        stage.SetWindow(1);
        stage.Write("b");
        Assert.Equal(new Cell("b", ScreenModel.Roman, ScreenModel.DefaultColour, ScreenModel.DefaultColour, 1), stage.CellAt(2, 1));
        stage.SetWindow(0);
        stage.SetStyle(ScreenModel.Roman);
        stage.SetColour(ScreenModel.CurrentColour, ScreenModel.CurrentColour);
        stage.Write("c");
        Assert.Equal(new Cell("c", ScreenModel.Roman, 3, 4, 3), stage.CellAt(1, 2));
    }

    // The paints are the truth a glass carries out: text at true unit
    // positions, whatever the cell grid rounds them to.
    [Fact]
    public void ThePaintsCarryTrueUnitPositions()
    {
        var stage = Stage();
        stage.PlaceWindow(2, 2, 3, 2 * Units, 4 * Units);
        stage.SetWindow(2);
        stage.Write("hi");
        Assert.Equal(
            [
                new TextPaint(2, 3, new Cell("h", ScreenModel.Roman, ScreenModel.DefaultColour, ScreenModel.DefaultColour, 1)),
                new TextPaint(2, 3 + Units, new Cell("i", ScreenModel.Roman, ScreenModel.DefaultColour, ScreenModel.DefaultColour, 1)),
            ],
            Drained(stage));
        Assert.Empty(Drained(stage));
    }

    // The sweep reports the rows the grid changed on, once each.
    [Fact]
    public void TheSweepNamesTheChangedRows()
    {
        var stage = Stage();
        stage.Write("a\nb");
        Assert.Equal([1, 2], stage.Sweep());
        Assert.Empty(stage.Sweep());
        stage.EraseWindow(-1);
        Assert.Equal([1, 2, 3, 4, 5], stage.Sweep());
    }

    // Printing outside the screen's own bounds is clipped away.
    [Fact]
    public void PrintingBeyondTheScreenIsClipped()
    {
        var stage = Stage(columns: 4, lines: 2);
        stage.PlaceWindow(3, 1 + 4 * Units, 1, 2 * Units, 4 * Units);
        stage.SetWindow(3);
        stage.Write("off");
        Assert.Equal("\n", stage.Rendered());
        Assert.Equal(3, Drained(stage).Count);
        // Off the right edge as well: the paints still carry the true
        // positions, which is what a glass wider than the grid draws.
        stage.PlaceWindow(3, 1, 1 + 6 * Units, 2 * Units, 4 * Units);
        stage.SetCursor(1, 1);
        stage.Write("edge");
        Assert.Equal("", stage.RowText(1));
        Assert.Equal(4, Drained(stage).Count);
    }
}
