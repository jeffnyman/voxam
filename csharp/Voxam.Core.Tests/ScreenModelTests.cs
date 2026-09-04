namespace Voxam.Core.Tests;

public class ScreenModelTests
{
    private static ScreenModel Small(int version = 3, int columns = 10, int lines = 5) => new(columns, lines, version);

    [Theory]
    [InlineData(3, 5)]
    [InlineData(4, 5)]
    [InlineData(5, 1)]
    public void TheLowerCursorHomesPerVersion(int version, int row)
    {
        var model = Small(version);
        Assert.Equal((row, 1), model.Cursor);
        Assert.Equal(0, model.Split);
        Assert.Equal(ScreenModel.Lower, model.Selected);
        Assert.Equal(10, model.Columns);
        Assert.Equal(5, model.Lines);
    }

    [Fact]
    public void WordsWrapWholeAndSpacesNeverOpenALine()
    {
        var model = Small(5);
        model.Write("one two three four");
        Assert.Equal("one two\nthree four", model.Rendered().TrimEnd());
        Assert.Equal((2, 11), model.Cursor);
        model.Write(" five");
        Assert.Equal("one two\nthree four\nfive", model.Rendered().TrimEnd());
        Assert.Equal([1, 2, 3], model.Sweep());
        Assert.Empty(model.Sweep());
    }

    [Fact]
    public void ALongWordCharacterWrapsAndUnbufferedTextWrapsAnywhere()
    {
        var model = Small(5);
        model.Write("abcdefghijklm");
        Assert.Equal("abcdefghij\nklm", model.Rendered().TrimEnd());
        model.SetBuffering(false);
        model.Write("nopqrstuvwxyz");
        Assert.Equal("abcdefghij\nklmnopqrst\nuvwxyz", model.Rendered().TrimEnd());
    }

    [Fact]
    public void TheBottomLineScrollsOnlyWhenTheNextTextArrives()
    {
        var model = Small(5, 10, 3);
        model.Write("a\nb\nc");
        Assert.Equal("a\nb\nc", model.Rendered());
        model.Write("\n");
        // The scroll is owed, not paid: the last line stays visible.
        Assert.Equal("a\nb\nc", model.Rendered());
        model.Write("d");
        Assert.Equal("b\nc\nd", model.Rendered());
        model.Write("\n\ne");
        Assert.Equal("d\n\ne", model.Rendered());
    }

    [Fact]
    public void AScreenfulPausesForMore()
    {
        var model = Small(5, 10, 4);
        var pauses = 0;
        model.More = () => pauses++;
        model.Write("a\nb\nc\nd\ne\nf\ng");
        Assert.Equal(2, pauses);
        model.Rest();
        model.Write("\n\n");
        Assert.Equal(2, pauses);
        model.Write("\n");
        Assert.Equal(3, pauses);
    }

    [Fact]
    public void TheUpperWindowOverlaysAndNeverScrolls()
    {
        var model = Small(5);
        model.SplitWindow(2);
        model.SetWindow(ScreenModel.Upper);
        model.Write("abcdefghijk\nsecond\nthird");
        Assert.Equal("abcdefghik\nthirdd", model.Rendered().TrimEnd());
        Assert.Equal((2, 6), model.Cursor);
        model.SetCursor(1, 3);
        model.Write("X");
        Assert.Equal("abXdefghik", model.RowText(1));
        Assert.Equal((1, 4), model.GetCursor());
        model.SetWindow(ScreenModel.Lower);
        Assert.Equal((1, 4), model.GetCursor());
        model.SetCursor(9, 9);
        Assert.Equal((1, 4), model.GetCursor());
    }

    [Fact]
    public void VersionThreeHangsTheUpperWindowBelowTheStatusLine()
    {
        var model = Small(3);
        model.SplitWindow(1);
        model.SetWindow(ScreenModel.Upper);
        model.Write("up");
        Assert.Equal("\nup", model.Rendered().TrimEnd());
        Assert.Equal((2, 3), model.Cursor);
    }

    [Fact]
    public void SplittingPolicesItsHeightAndPushesTheLowerCursor()
    {
        var model = Small(5);
        model.Write("x");
        model.SplitWindow(2);
        Assert.Equal((3, 1), model.Cursor);
        model.SetWindow(ScreenModel.Upper);
        model.SetCursor(2, 2);
        model.SplitWindow(3);
        Assert.Equal((2, 2), model.GetCursor());
        model.Write("\n\n");
        model.SplitWindow(1);
        Assert.Equal((1, 1), model.GetCursor());
        Assert.Contains("does not fit", Assert.Throws<ZMachineException>(() => model.SplitWindow(6)).Message, StringComparison.Ordinal);
        Assert.Contains("does not fit", Assert.Throws<ZMachineException>(() => model.SplitWindow(-1)).Message, StringComparison.Ordinal);
        var three = Small(3);
        three.SplitWindow(4);
        Assert.Equal(4, three.Split);
        three.SplitWindow(0);
        Assert.Equal(0, three.Split);
    }

    [Fact]
    public void ATeletypeHasNoWindows()
    {
        var model = Small(1);
        Assert.Contains("has no windows", Assert.Throws<ZMachineException>(() => model.SplitWindow(1)).Message, StringComparison.Ordinal);
        Assert.Contains("has no windows", Assert.Throws<ZMachineException>(() => model.SetWindow(1)).Message, StringComparison.Ordinal);
        Assert.Contains("no window 2 before version 6", Assert.Throws<ZMachineException>(() => Small(5).SetWindow(2)).Message, StringComparison.Ordinal);
    }

    [Fact]
    public void CursorMovesOutsideTheScreenAreRefused()
    {
        var model = Small(5);
        model.SplitWindow(1);
        model.SetWindow(ScreenModel.Upper);
        model.SetCursor(5, 10);
        Assert.Contains("cannot move to (6, 1)", Assert.Throws<ZMachineException>(() => model.SetCursor(6, 1)).Message, StringComparison.Ordinal);
        Assert.Throws<ZMachineException>(() => model.SetCursor(1, 11));
        Assert.Throws<ZMachineException>(() => model.SetCursor(1, 0));
        Assert.Throws<ZMachineException>(() => model.SetCursor(0, 1));
    }

    [Fact]
    public void ErasingWindowsClearsHomesAndUnsplits()
    {
        var model = Small(4);
        model.SplitWindow(1);
        model.SetWindow(ScreenModel.Upper);
        model.Write("top");
        model.SetWindow(ScreenModel.Lower);
        model.Write("story");
        model.EraseWindow(ScreenModel.Upper);
        Assert.Equal("\n\n\n\nstory", model.Rendered());
        model.EraseWindow(ScreenModel.Lower);
        Assert.Equal("", model.Rendered().Trim());
        Assert.Equal((5, 1), model.Cursor);
        model.SetWindow(ScreenModel.Upper);
        model.Write("again");
        model.EraseWindow(-2);
        Assert.Equal(1, model.Split);
        Assert.Equal(ScreenModel.Upper, model.Selected);
        model.EraseWindow(-1);
        Assert.Equal(0, model.Split);
        Assert.Equal(ScreenModel.Lower, model.Selected);
        Assert.Equal((5, 1), model.Cursor);
        var five = Small(5);
        five.Write("a\nb");
        five.EraseWindow(-1);
        Assert.Equal((1, 1), five.Cursor);
        Assert.Contains("no window 3 to erase", Assert.Throws<ZMachineException>(() => five.EraseWindow(3)).Message, StringComparison.Ordinal);
    }

    [Fact]
    public void EraseLineRubOutAndRetreatWorkInBothWindows()
    {
        var model = Small(5, 20);
        model.Write("hello world");
        model.Retreat(3);
        model.EraseLine();
        Assert.Equal("hello wo", model.RowText(1));
        model.Write("ab");
        model.RubOut();
        Assert.Equal("hello woa", model.RowText(1));
        model.RubOut();
        model.RubOut();
        Assert.Equal((1, 8), model.Cursor);
        Assert.Equal(7, model.Retreat(10));
        Assert.Equal(0, model.Retreat(4));
        model.RubOut();
        Assert.Equal((1, 1), model.Cursor);
        model.EraseWindow(-1);
        model.SplitWindow(2);
        model.SetWindow(ScreenModel.Upper);
        model.Write("upper");
        model.RubOut();
        Assert.Equal("uppe", model.RowText(1));
        Assert.Equal(2, model.Retreat(2));
        model.EraseLine();
        Assert.Equal("up", model.RowText(1));
        model.SetCursor(1, 1);
        model.RubOut();
        Assert.Equal("up", model.RowText(1));
    }

    [Fact]
    public void StylesColoursAndFontsDressTheCells()
    {
        var model = Small(5);
        model.SetStyle(ScreenModel.Bold);
        model.SetStyle(ScreenModel.Italic);
        model.SetColour(3, 0);
        model.SetColour(0, 6);
        model.SetFont(3);
        model.Write("x");
        var cell = model.CellAt(1, 1);
        Assert.Equal(new Cell("x", ScreenModel.Bold | ScreenModel.Italic, 3, 6, 3), cell);
        Assert.Equal(6, model.Background);
        model.SetStyle(ScreenModel.Roman);
        model.Write("y");
        Assert.Equal(ScreenModel.Roman, model.CellAt(1, 2).Style);
        // A scrolled-in line wears the current background.
        var scroller = Small(5, 4, 2);
        scroller.SetColour(0, 4);
        scroller.Write("a\nb\nc");
        Assert.Equal(4, scroller.CellAt(2, 4).Background);
    }

    [Fact]
    public void RectanglesStampRightAndDown()
    {
        var model = Small(5);
        model.SplitWindow(3);
        model.SetWindow(ScreenModel.Upper);
        model.SetCursor(1, 3);
        model.WriteRectangle(["ab", "cd", "ef", "gh"]);
        Assert.Equal("  ab\n  cd\n  gh", model.Rendered().TrimEnd());
        model.SetWindow(ScreenModel.Lower);
        model.WriteRectangle(["x", "y"]);
        Assert.Equal("  ab\n  cd\n  gh\nx\ny", model.Rendered().TrimEnd());
    }

    [Fact]
    public void TheStatusLineShowsScoreOrTimeInReverseVideo()
    {
        var model = new ScreenModel(40, 3, 3);
        model.ShowStatus(new Status("West of House", 10, 3, false));
        Assert.Equal(" West of House      Score: 10  Moves: 3", model.RowText(1));
        Assert.Equal(ScreenModel.Reverse, model.CellAt(1, 1).Style);
        model.ShowStatus(new Status("A very long location name indeed", 9, 5, true));
        Assert.Equal(" A very long location nam... Time: 9:05", model.RowText(1));
        Assert.Contains("draws its own status area", Assert.Throws<ZMachineException>(() => Small(4).ShowStatus(new Status("x", 0, 0, false))).Message, StringComparison.Ordinal);
    }

    [Fact]
    public void ResizingKeepsTheOverlapAndRedrawsTheStatus()
    {
        var model = new ScreenModel(20, 4, 3);
        model.ShowStatus(new Status("Room", 1, 2, false));
        model.SplitWindow(2);
        model.SetWindow(ScreenModel.Upper);
        model.SetCursor(2, 5);
        model.SetWindow(ScreenModel.Lower);
        model.Write("story text here");
        model.Sweep();
        model.Resize(20, 4);
        Assert.Empty(model.Sweep());
        model.Resize(8, 2);
        Assert.Equal([1, 2], model.Sweep());
        // Too narrow for the score: the room gives way to an ellipsis.
        Assert.Equal(" ...Scor", model.RowText(1));
        Assert.Equal(1, model.Split);
        Assert.Equal((1, 5), model.GetCursor());
        Assert.Equal((2, 8), model.Cursor);
        model.Resize(0, 0);
        Assert.Equal(1, model.Columns);
        Assert.Equal(1, model.Lines);
        var five = Small(5, 4, 2);
        five.Write("abcdefgh");
        five.Resize(6, 3);
        Assert.Equal("abcd", five.RowText(1));
        Assert.Equal("efgh", five.RowText(2));
        Assert.Equal((2, 5), five.Cursor);
    }

    [Fact]
    public void ASurrogatePairIsOneCell()
    {
        var model = Small(5);
        model.Write("a\U0001F600b");
        Assert.Equal("\U0001F600", model.CellAt(1, 2).Character);
        Assert.Equal((1, 4), model.Cursor);
    }
}
