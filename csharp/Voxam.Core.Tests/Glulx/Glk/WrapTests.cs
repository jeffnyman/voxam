using Voxam.Core.Glulx.Glk;

namespace Voxam.Tests.Glulx.Glk;

/// <summary>
/// Word wrapping for text buffer windows: where the lines break, how
/// styled runs are cut to match, and what a pager holds back.
/// </summary>
public sealed class WrapTests
{
    // Text arrives in pieces, and a piece may stop mid-word: the
    // wrapper folds the next one into the paragraph still open.
    [Fact]
    public void PiecesFoldIntoTheParagraphStillOpen()
    {
        var wrapper = new Wrapper(20);

        wrapper.Add([Run("the quick br")]);
        wrapper.Add([Run("own fox")]);

        Assert.Equal(["the quick brown fox"], Flat(wrapper.Lines));
    }

    // Runs of the same dress merge; a change of dress starts a new run,
    // and an empty piece is nothing at all.
    [Fact]
    public void RunsOfOneDressMergeAndEmptyPiecesAreNothing()
    {
        var wrapper = new Wrapper(40);

        wrapper.Add([Run("one "), Run(""), Run("two "), Run("three", TextStyle.Header)]);

        var line = Assert.Single(wrapper.Lines);

        Assert.Equal(2, line.Count);
        Assert.Equal("one two ", line[0].Text);
        Assert.Equal(TextStyle.Header, line[1].Key.Style);
    }

    // A newline ends a paragraph wherever it falls, including at the
    // head and tail of a piece.
    [Fact]
    public void ANewlineEndsAParagraphWhereverItFalls()
    {
        var wrapper = new Wrapper(20);

        wrapper.Add([Run("one\ntwo\n")]);
        wrapper.Add([Run("\nthree")]);

        Assert.Equal(["one", "two", "", "three"], Flat(wrapper.Lines));
    }

    // Breaking a line cuts the segments that make it up, so the
    // emphasis does not move.
    [Fact]
    public void BreakingCutsTheSegmentsAndNotJustTheText()
    {
        var lines = Wrapper.WrapSegments(
            [Run("hello "), Run("brave new", TextStyle.Emphasized), Run(" world")], 11);

        Assert.Equal(["hello brave", "new world"], Flat(lines));

        // The emphasized run is cut at the break, and both halves keep
        // the dress they were written in.
        Assert.Equal(TextStyle.Emphasized, lines[0][1].Key.Style);
        Assert.Equal("brave", lines[0][1].Text);
        Assert.Equal(TextStyle.Emphasized, lines[1][0].Key.Style);
        Assert.Equal("new", lines[1][0].Text);
        Assert.Equal(TextStyle.Normal, lines[1][1].Key.Style);
    }

    // A word wider than the line is cut rather than left to overflow,
    // and the space at a break is dropped.
    [Fact]
    public void AWordWiderThanTheLineIsCut()
    {
        var wrapper = new Wrapper(5);

        wrapper.Add([Run("antidisestablishment")]);

        Assert.Equal(["antid", "isest", "ablis", "hment"], Flat(wrapper.Lines));

        var spaced = new Wrapper(6);

        spaced.Add([Run("ab cd ef gh")]);

        Assert.Equal(["ab cd", "ef gh"], Flat(spaced.Lines));
    }

    // A character above the basic plane counts once toward a line's
    // width, however many units hold it.
    [Fact]
    public void AnAstralCharacterCountsOnce()
    {
        var wrapper = new Wrapper(3);

        wrapper.Add([Run("\U0001F600\U0001F600\U0001F600\U0001F600")]);

        Assert.Equal(
            ["\U0001F600\U0001F600\U0001F600", "\U0001F600"], Flat(wrapper.Lines));
    }

    // An empty paragraph is still a line, and no segments at all is one
    // empty line rather than none.
    [Fact]
    public void AnEmptyParagraphIsStillALine()
    {
        Assert.Equal([[]], Wrapper.WrapSegments([], 10));
        Assert.Equal([""], Flat(new Wrapper(10).Lines));
    }

    // The line being typed is drawn as part of the layout without
    // becoming part of the window's contents.
    [Fact]
    public void TheTypedLineIsPreviewedWithoutBeingKept()
    {
        var wrapper = new Wrapper(20);

        wrapper.Add([Run("you are here. ")]);

        Assert.Equal(
            ["you are here. north"],
            Flat(wrapper.Preview([Run("north", TextStyle.Input)])));
        Assert.Equal(["you are here. "], Flat(wrapper.Lines));

        // Previewing nothing is the text as it stands.
        Assert.Equal(["you are here. "], Flat(wrapper.Preview([])));
    }

    // A resize re-wraps from the paragraphs, not from lines that
    // already lost their spaces at the break points.
    [Fact]
    public void AResizeReWrapsFromTheParagraphs()
    {
        var wrapper = new Wrapper(10);

        wrapper.Add([Run("the quick brown fox\n")]);

        // The newline closed a paragraph and opened an empty one, which
        // is a line of its own until something is written into it.
        Assert.Equal(["the quick", "brown fox", ""], Flat(wrapper.Lines));

        wrapper.Resize(19);

        Assert.Equal(["the quick brown fox", ""], Flat(wrapper.Lines));

        // Resizing to the width it already has changes nothing.
        wrapper.Resize(19);

        Assert.Equal(19, wrapper.Width);

        // And a width below one is still one.
        wrapper.Resize(0);

        Assert.Equal(1, wrapper.Width);
        Assert.Equal(1, new Wrapper(-4).Width);
    }

    // Everything unseen that fits is shown, and the player has then had
    // the lot: asking again is the same answer.
    [Fact]
    public void AWindowfulThatFitsIsShownAndCountsAsRead()
    {
        var wrapper = new Wrapper(10);

        wrapper.Add([Run("one\ntwo\nthree\n")]);

        var shown = wrapper.Show(5);

        Assert.Equal(["one", "two", "three", ""], Flat(shown.Lines));
        Assert.False(shown.More);
        Assert.Equal(0, shown.Start);
        Assert.Equal(4, wrapper.Seen);
        Assert.Equal(4, wrapper.Seen);
    }

    // A window with no room shows nothing and holds nothing back.
    [Fact]
    public void AWindowWithNoRoomShowsNothing()
    {
        var wrapper = new Wrapper(10);

        wrapper.Add([Run("one\ntwo\n")]);

        var shown = wrapper.Show(0);

        Assert.Empty(shown.Lines);
        Assert.False(shown.More);
        Assert.Equal(0, wrapper.Seen);
    }

    // More text than a windowful holds the view where it is until the
    // player turns the page, one line of overlap each time.
    [Fact]
    public void MoreThanAWindowfulWaitsToBeRead()
    {
        var wrapper = new Wrapper(10);

        wrapper.Add([Run("a\nb\nc\nd\ne\nf\ng\n")]);

        var first = wrapper.Show(3);

        Assert.True(first.More);
        Assert.Equal(["a", "b"], Flat(first.Lines));
        Assert.Equal(0, first.Start);

        // The view stays put until the page is turned.
        Assert.Equal(["a", "b"], Flat(wrapper.Show(3).Lines));

        wrapper.Advance(3);

        var second = wrapper.Show(3);

        Assert.Equal(["b", "c"], Flat(second.Lines));
        Assert.Equal(1, second.Start);

        while (wrapper.Show(3).More)
        {
            wrapper.Advance(3);
        }

        Assert.Equal(8, wrapper.Seen);
    }

    // In a window one line tall the page and the overlap are both a
    // single line, and the pager still moves.
    [Fact]
    public void EvenAOneLineWindowTurnsItsPages()
    {
        var wrapper = new Wrapper(10);

        wrapper.Add([Run("a\nb\nc\n")]);

        var turns = 0;

        while (wrapper.Show(1).More && turns < 10)
        {
            wrapper.Advance(1);
            turns++;
        }

        Assert.Equal(3, turns);
        Assert.Equal(4, wrapper.Seen);
    }

    // Catching up treats everything as read, for the moments when
    // pausing would be wrong.
    [Fact]
    public void CatchingUpTreatsEverythingAsRead()
    {
        var wrapper = new Wrapper(10);

        wrapper.Add([Run("a\nb\nc\nd\ne\nf\n")]);

        Assert.True(wrapper.Show(2).More);

        wrapper.CatchUp();

        Assert.False(wrapper.Show(2).More);
    }

    // A cleared window has forgotten everything, its pager included.
    [Fact]
    public void ClearingForgetsEverything()
    {
        var wrapper = new Wrapper(10);

        wrapper.Add([Run("a\nb\nc\n")]);
        wrapper.Show(2);
        wrapper.Clear();

        Assert.Equal([""], Flat(wrapper.Lines));
        Assert.Equal(0, wrapper.Seen);
    }

    // Past the scrollback the oldest paragraphs are dropped, in
    // batches, so a long game does not accumulate its whole transcript.
    [Fact]
    public void TheOldestParagraphsAreDroppedInBatches()
    {
        var wrapper = new Wrapper(10);

        for (var at = 0; at < 2200; at++)
        {
            wrapper.Add([Run("line\n")]);
        }

        // Not yet: the trim waits until the scrollback and a whole
        // batch beyond it have accumulated.
        Assert.Equal(2201, wrapper.Lines.Count);

        for (var at = 0; at < 100; at++)
        {
            wrapper.Add([Run("line\n")]);
        }

        // Now it has fired, and dropped the oldest batch entire.
        Assert.Equal(2101, wrapper.Lines.Count);
    }

    // The text of a line, without its styling, is what a display pads
    // and measures by.
    [Fact]
    public void ALinesPlainTextIsItsCharacters()
    {
        Assert.Equal(
            "one two", Wrapper.Plain([Run("one "), Run("two", TextStyle.Alert)]));
        Assert.Equal("", Wrapper.Plain([]));
    }

    // Breaking segments is a function in its own right, and a newline
    // inside one ends a line there. The wrapper splits them out before
    // it ever gets here, so this is the contract rather than the path
    // its own text takes.
    [Fact]
    public void ANewlineInsideSegmentsEndsALineThere()
    {
        Assert.Equal(
            ["one", "two", "three"],
            Flat(Wrapper.WrapSegments([Run("one" + "\n" + "two" + "\n" + "three")], 20)));
    }

    private static Segment Run(string text, uint style = TextStyle.Normal, uint link = 0) =>
        new(new Dress(style, link), text);

    private static List<string> Flat(IEnumerable<IReadOnlyList<Segment>> lines) =>
        [.. lines.Select(Wrapper.Plain)];
}
