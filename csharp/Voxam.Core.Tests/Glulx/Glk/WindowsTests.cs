using Voxam.Core.Glulx.Glk;

namespace Voxam.Tests.Glulx.Glk;

/// <summary>
/// The window types: what they hold, how they measure themselves, and
/// how a split divides the room between two of them.
/// </summary>
public sealed class WindowsTests
{
    // A window opens unattached, with its own stream bound to it and
    // nothing requested.
    [Fact]
    public void AWindowOpensUnattachedWithItsOwnStream()
    {
        var window = new BlankWindow(rock: 5);

        Assert.Equal(5u, window.Rock);
        Assert.Equal(0, window.GlkClass);
        Assert.Equal(WindowType.Blank, window.WinType);
        Assert.Same(window, window.Stream.Window);
        Assert.Null(window.Parent);
        Assert.Null(window.EchoStream);
        Assert.Null(window.LineRequest);
        Assert.False(window.CharRequest);
        Assert.False(window.CharUnicode);
        Assert.False(window.HyperlinkRequest);
        Assert.False(window.MouseRequest);
        Assert.False(window.PendingClear);
        Assert.Equal(TextStyle.Normal, window.Style);
        Assert.Equal(Metrics.CharacterCell, window.Metrics);
        Assert.Equal(default, window.BBox);
    }

    // A blank window supports no output, but the copy to an echo stream
    // happens for every type (Glk: Echo Streams).
    [Fact]
    public void OutputToABlankWindowGoesOnlyToItsEcho()
    {
        var window = new BlankWindow();

        window.PutChar('x');

        var echo = new StreamOnMemory(new WordBuffer(4), GlkFileMode.Write);
        window.EchoStream = echo;
        window.PutChar('y');

        Assert.Equal(1u, echo.WriteCount);
        Assert.Equal([0x79u, 0u, 0u, 0u], ((WordBuffer)echo.Buffer!).Snapshot());
    }

    // A blank window and a pair window have no measurement system, so
    // the size the game is told is zero either way, however real the
    // box a display draws borders from (Glk: Blank Windows).
    [Fact]
    public void AWindowWithNoMeasurementSystemHasNoSize()
    {
        var window = new BlankWindow();

        window.Rearrange(new Box(0, 0, 80, 24));

        Assert.Equal(new Box(0, 0, 80, 24), window.BBox);
        Assert.Equal(0, window.Width);
        Assert.Equal(0, window.Height);
    }

    // Clearing a window whose contents live in the display can only
    // raise the flag.
    [Fact]
    public void ClearingAWindowRaisesTheFlagForTheDisplay()
    {
        var window = new BlankWindow();

        window.Clear();

        Assert.True(window.PendingClear);
    }

    // A window with no conversion to make answers the size it was
    // given, whichever axis the split divides.
    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public void AWindowWithNoConversionAnswersTheSizeItWasGiven(bool vertical) =>
        Assert.Equal(7, new GraphicsWindow().Extent(7, vertical));

    // A graphics window opens asking to be cleared, because whatever
    // the display holds where the canvas now hangs is someone else's
    // leavings, and it measures in the pixels of its own box.
    [Fact]
    public void AGraphicsWindowOpensAsBackgroundAndMeasuresInPixels()
    {
        var window = new GraphicsWindow();

        Assert.Equal(WindowType.Graphics, window.WinType);
        Assert.True(window.PendingClear);
        Assert.False(window.Moved);

        window.Rearrange(new Box(10, 20, 110, 70));

        Assert.Equal(100, window.Width);
        Assert.Equal(50, window.Height);
    }

    // A box that did not change is not a move, so nothing is owed.
    [Fact]
    public void AGraphicsBoxThatDidNotChangeOwesNothing()
    {
        var window = new GraphicsWindow();

        window.Rearrange(new Box(0, 0, 40, 40));
        window.PendingClear = false;
        window.Rearrange(new Box(0, 0, 40, 40));

        Assert.False(window.PendingClear);
        Assert.False(window.Moved);
    }

    // A fresh window whose old box was empty owes no redraw: it opens
    // as background and the game knows it. A window that had a real box
    // is owed one, because the display's pixels do not travel (Glk:
    // Window Events).
    [Fact]
    public void OnlyAWindowThatHadPixelsIsOwedARedraw()
    {
        var window = new GraphicsWindow();

        window.Rearrange(new Box(0, 0, 40, 40));

        Assert.False(window.Moved);

        window.Rearrange(new Box(0, 0, 60, 40));

        Assert.True(window.Moved);
        Assert.True(window.PendingClear);

        // Once owed, still owed: a further move does not unsay it.
        window.Rearrange(new Box(0, 0, 80, 40));

        Assert.True(window.Moved);
    }

    // A box with an extent of zero holds no pixels, so leaving it is
    // not a move either.
    [Fact]
    public void ABoxWithNoHeightHoldsNoPixels()
    {
        var window = new GraphicsWindow();

        window.Rearrange(new Box(0, 0, 40, 0));
        window.Rearrange(new Box(0, 0, 40, 30));

        Assert.False(window.Moved);
    }

    // A text window on a terminal measures in the cell it is already
    // laid out in, so every number is the same either way.
    [Fact]
    public void ATextWindowOnATerminalMeasuresInItsOwnUnits()
    {
        var window = new TextGridWindow();

        window.Rearrange(new Box(0, 0, 80, 24));

        Assert.Equal(80, window.Width);
        Assert.Equal(24, window.Height);
        Assert.Equal(5, window.Extent(5, vertical: true));
    }

    // On a graphical display the size is the extent divided by the
    // font's cell, margin taken out, rounded down: a window claiming a
    // column it has no room for spills over its own edge.
    [Fact]
    public void ATextWindowOnAGlassDividesByItsCell()
    {
        var window = new TextGridWindow
        {
            Metrics = new Metrics(8, 16, 4, 6),
        };

        window.Rearrange(new Box(0, 0, 84, 38));

        Assert.Equal(10, window.Width);
        Assert.Equal(2, window.Height);

        // And the other direction rounds up, so a window a fraction of
        // a pixel short does not push its last line past its border.
        Assert.Equal(84, window.Extent(10, vertical: true));
        Assert.Equal(38, window.Extent(2, vertical: false));
    }

    // A display that reports no cell at all cannot be divided by, and a
    // window measured against it holds nothing.
    [Fact]
    public void ADisplayWithNoCellLeavesAWindowEmpty()
    {
        var window = new TextGridWindow
        {
            Metrics = new Metrics(0, 0),
        };

        window.Rearrange(new Box(0, 0, 80, 24));

        Assert.Equal(0, window.Width);
        Assert.Equal(0, window.Height);
    }

    // Text accumulates as runs, and a run continues only while both the
    // style and the link value hold.
    [Fact]
    public void BufferTextGathersIntoRunsThatShareTheirDress()
    {
        var window = new TextBufferWindow();

        window.Stream.PutString("ab");
        window.Style = TextStyle.Emphasized;
        window.Stream.PutString("cd");
        window.Stream.Hyperlink = 7;
        window.Stream.PutString("ef");

        var content = window.Content;

        Assert.Equal(3, content.Count);
        Assert.Equal("ab", ((Run)content[0]).Text);
        Assert.Equal(TextStyle.Normal, ((Run)content[0]).Style);
        Assert.Equal("cd", ((Run)content[1]).Text);
        Assert.Equal(TextStyle.Emphasized, ((Run)content[1]).Style);
        Assert.Equal("ef", ((Run)content[2]).Text);
        Assert.Equal(7u, ((Run)content[2]).Hyperlink);
        Assert.Equal("abcdef", window.Text());
    }

    // A picture and a flow break sit in the flow where they were put,
    // and each ends the run it follows.
    [Fact]
    public void APictureAndABreakEndTheRunTheyFollow()
    {
        var window = new TextBufferWindow();

        window.Stream.PutString("a");
        window.PutPlaced(new Placed(3, "data:image/png;base64,AA", 16, 16, 1, 0));
        window.Stream.PutString("b");
        window.PutBreak();
        window.Stream.PutString("c");

        var content = window.Content;

        Assert.Equal(5, content.Count);
        Assert.Equal("a", ((Run)content[0]).Text);

        var placed = Assert.IsType<Placed>(content[1]);

        Assert.Equal(3u, placed.Image);
        Assert.Equal("data:image/png;base64,AA", placed.Url);
        Assert.Equal(16, placed.Width);
        Assert.Equal(16, placed.Height);
        Assert.Equal(1u, placed.Alignment);
        Assert.Equal(0u, placed.Hyperlink);

        Assert.Equal("b", ((Run)content[2]).Text);
        Assert.IsType<FlowBreak>(content[3]);
        Assert.Equal("c", ((Run)content[4]).Text);
        Assert.Equal("abc", window.Text());
    }

    // A display drains what has gathered, flattened or dressed, and
    // what it took is gone.
    [Fact]
    public void ADisplayDrainsWhatHasGathered()
    {
        var window = new TextBufferWindow();

        window.Stream.PutString("hello");

        Assert.Equal("hello", window.TakeText());
        Assert.Empty(window.Content);

        window.Stream.PutString("again");

        var taken = window.TakeContent();

        Assert.Single(taken);
        Assert.Equal("again", ((Run)taken[0]).Text);
        Assert.Empty(window.Content);
    }

    // A buffer keeps its own contents, so clearing erases them here as
    // well as asking the display to.
    [Fact]
    public void ClearingABufferErasesWhatItHeld()
    {
        var window = new TextBufferWindow();

        window.Stream.PutString("gone");
        window.Clear();

        Assert.True(window.PendingClear);
        Assert.Empty(window.Content);
        Assert.Equal(WindowType.TextBuffer, window.WinType);
    }

    // A grid opens with no rows at all; the first rearrange is what
    // sizes it.
    [Fact]
    public void AGridOpensWithNoRows()
    {
        var window = new TextGridWindow();

        Assert.Equal(WindowType.TextGrid, window.WinType);
        Assert.Empty(window.Lines);
        Assert.Empty(window.Rows());

        window.Rearrange(new Box(0, 0, 3, 2));

        Assert.Equal(["   ", "   "], window.Rows());
        Assert.Equal(2, window.Styles.Count);
        Assert.Equal(3, window.Links[0].Count);
    }

    // Writing lands at the cursor and advances it, carrying the style
    // and link value the stream is wearing.
    [Fact]
    public void GridWritingLandsAtTheCursorAndCarriesItsDress()
    {
        var window = Grid(4, 2);

        window.Style = TextStyle.Header;
        window.Stream.Hyperlink = 12;
        window.Stream.PutString("ab");

        Assert.Equal(["ab  ", "    "], window.Rows());
        Assert.Equal(TextStyle.Header, window.Styles[0][0]);
        Assert.Equal(12u, window.Links[0][1]);
        Assert.Equal(TextStyle.Normal, window.Styles[0][2]);
        Assert.Equal(2, window.CursorX);
        Assert.Equal(0, window.CursorY);
    }

    // A newline moves to the start of the next row and prints nothing.
    [Fact]
    public void ANewlineMovesToTheNextRowAndPrintsNothing()
    {
        var window = Grid(4, 2);

        window.Stream.PutString("a\nb");

        Assert.Equal(["a   ", "b   "], window.Rows());
        Assert.Equal(1, window.CursorX);
        Assert.Equal(1, window.CursorY);
    }

    // The right edge wraps.
    [Fact]
    public void TheRightEdgeWraps()
    {
        var window = Grid(2, 2);

        window.Stream.PutString("abc");

        Assert.Equal(["ab", "c "], window.Rows());
    }

    // Past-the-edge positions are legal: output there falls into the
    // void until the cursor comes back inside.
    [Theory]
    [InlineData(0, 9)]
    [InlineData(-1, 0)]
    [InlineData(0, -1)]
    public void OutputOutsideTheGridFallsIntoTheVoid(int x, int y)
    {
        var window = Grid(3, 2);

        window.MoveCursor(x, y);
        window.Stream.PutChar('z');

        Assert.Equal(["   ", "   "], window.Rows());
    }

    // A grid the layout left no room for still takes writing, and drops
    // every character of it: the wrap moves the cursor down a row that
    // has no columns to land in.
    [Fact]
    public void AGridWithNoRoomDropsWhatIsWritten()
    {
        var window = Grid(0, 2);

        window.Stream.PutString("ab");

        Assert.Equal(["", ""], window.Rows());
        Assert.Equal(2, window.CursorY);
    }

    // Clearing fills the grid with blanks and brings the cursor home.
    // A grid keeps its own contents, so it erases them itself and has
    // nothing to ask the display for: the flag a buffer raises stays
    // down here.
    [Fact]
    public void ClearingAGridBlanksItAndHomesTheCursor()
    {
        var window = Grid(3, 2);

        window.Stream.PutString("abc");
        window.Clear();

        Assert.Equal(["   ", "   "], window.Rows());
        Assert.Equal(0, window.CursorX);
        Assert.Equal(0, window.CursorY);
        Assert.False(window.PendingClear);
    }

    // A resize keeps the overlap, top left aligned, and blanks whatever
    // room is new. The cursor is drawn back inside.
    [Fact]
    public void AResizeKeepsTheOverlapAndBlanksTheRest()
    {
        var window = Grid(4, 2);

        window.Stream.PutString("abcd");
        window.MoveCursor(3, 1);

        window.Rearrange(new Box(0, 0, 2, 1));

        Assert.Equal(["ab"], window.Rows());
        Assert.Equal(2, window.CursorX);
        Assert.Equal(1, window.CursorY);

        window.Rearrange(new Box(0, 0, 4, 2));

        Assert.Equal(["ab  ", "    "], window.Rows());
    }

    // The split's parts unpack from a method word and pack back into
    // one.
    [Theory]
    [InlineData(WindowMethod.Left | WindowMethod.Fixed, true, true, true)]
    [InlineData(WindowMethod.Right | WindowMethod.Proportional, true, false, true)]
    [InlineData(WindowMethod.Above | WindowMethod.Fixed | WindowMethod.NoBorder, false, true, false)]
    [InlineData(WindowMethod.Below | WindowMethod.Proportional, false, false, true)]
    public void AMethodWordUnpacksAndPacksBack(
        uint method, bool vertical, bool backward, bool border)
    {
        var pair = Pair(method, 1);

        Assert.Equal(vertical, pair.Vertical);
        Assert.Equal(backward, pair.Backward);
        Assert.Equal(border, pair.HasBorder);
        Assert.Equal(method, pair.Method);
        Assert.Equal(WindowType.Pair, pair.WinType);
        Assert.Equal(0, pair.Width);
        Assert.Equal(0, pair.Height);
    }

    // A proportional split is a percentage of the room and needs no
    // conversion.
    [Fact]
    public void AProportionalSplitTakesItsPercentage()
    {
        var pair = Pair(WindowMethod.Right | WindowMethod.Proportional, 25);

        pair.Rearrange(new Box(0, 0, 80, 24));

        Assert.Equal(new Box(60, 0, 80, 24), pair.SizedBox);
        Assert.Equal(new Box(60, 0, 80, 24), pair.Child2.BBox);
        Assert.Equal(new Box(0, 0, 60, 24), pair.Child1.BBox);
    }

    // A fixed split is expressed in the key window's own measurement
    // system, so a text key means characters and the display's cell is
    // what turns them into room.
    [Fact]
    public void AFixedSplitMeasuresInTheKeyWindowsUnits()
    {
        var child1 = new TextBufferWindow();
        var key = new TextGridWindow { Metrics = new Metrics(8, 16) };
        var pair = new PairWindow(child1, key, key, WindowMethod.Above | WindowMethod.Fixed, 3);

        pair.Rearrange(new Box(0, 0, 640, 480));

        Assert.Equal(new Box(0, 0, 640, 48), pair.SizedBox);
        Assert.Equal(new Box(0, 48, 640, 480), child1.BBox);
        Assert.Equal(3, key.Height);
    }

    // The direction decides the sides outright, so a split that names
    // the far side puts the constrained window there.
    [Fact]
    public void TheDirectionDecidesWhichSideIsConstrained()
    {
        var pair = Pair(WindowMethod.Below | WindowMethod.Fixed, 4);

        pair.Rearrange(new Box(0, 0, 20, 10));

        Assert.Equal(new Box(0, 6, 20, 10), pair.SizedBox);
        Assert.Equal(new Box(0, 0, 20, 6), pair.Child1.BBox);
    }

    // A split larger than the room, or smaller than none, is drawn back
    // inside it.
    [Theory]
    [InlineData(500, 20, 0)]
    [InlineData(-5, 0, 20)]
    public void ASplitIsDrawnBackInsideTheRoom(int size, int firstWidth, int secondWidth)
    {
        var pair = Pair(WindowMethod.Left | WindowMethod.Fixed, size);

        pair.Rearrange(new Box(0, 0, 20, 10));

        Assert.Equal(firstWidth, pair.Child2.BBox.Right - pair.Child2.BBox.Left);
        Assert.Equal(secondWidth, pair.Child1.BBox.Right - pair.Child1.BBox.Left);
    }

    // A re-arrangement can flip the split, and the children and key are
    // the api era's to move.
    [Fact]
    public void ASplitCanBeReshapedAfterItIsMade()
    {
        var pair = Pair(WindowMethod.Left | WindowMethod.Fixed, 5);
        var other = new TextGridWindow();

        pair.SetMethod(WindowMethod.Below | WindowMethod.Proportional | WindowMethod.NoBorder);
        pair.Size = 50;
        pair.Key = other;
        pair.Child1 = other;

        Assert.False(pair.Vertical);
        Assert.False(pair.Backward);
        Assert.False(pair.HasBorder);
        Assert.Same(other, pair.Key);
        Assert.Same(other, pair.Child1);
        Assert.Equal(50, pair.Size);
    }

    // A line request records what it asked for, and answers the room it
    // was given.
    [Fact]
    public void ALineRequestRecordsWhatItAskedFor()
    {
        var buffer = new WordBuffer(16);
        var request = new LineRequest(buffer, initlen: 4, unicode: true)
        {
            Terminators = [KeyCode.Escape, KeyCode.Func1],
        };

        Assert.Same(buffer, request.Buffer);
        Assert.Equal(4, request.InitLen);
        Assert.True(request.Unicode);
        Assert.True(request.Echo);
        Assert.Equal(16, request.Capacity);
        Assert.Equal([KeyCode.Escape, KeyCode.Func1], request.Terminators);

        request.Echo = false;

        Assert.False(request.Echo);
    }

    // A request with nowhere to put the line still stands; the null
    // buffer simply has no room in it.
    [Fact]
    public void ALineRequestWithNoBufferHasNoRoom()
    {
        var request = new LineRequest(null);

        Assert.Null(request.Buffer);
        Assert.Equal(0, request.Capacity);
        Assert.Empty(request.Terminators);
    }

    // The cell a display reports is its own; two that measure alike are
    // the same measurement.
    [Fact]
    public void CellsCompareByWhatTheyMeasure()
    {
        Assert.Equal(new Metrics(1, 1), Metrics.CharacterCell);
        Assert.NotEqual(new Metrics(8, 16), Metrics.CharacterCell);
        Assert.Equal(new Metrics(8, 16, 2, 3), new Metrics(8, 16, 2, 3));
    }

    private static TextGridWindow Grid(int width, int height)
    {
        var window = new TextGridWindow();

        window.Rearrange(new Box(0, 0, width, height));

        return window;
    }

    private static PairWindow Pair(uint method, int size)
    {
        var child1 = new TextBufferWindow();
        var child2 = new TextGridWindow();

        return new PairWindow(child1, child2, child2, method, size);
    }
}
