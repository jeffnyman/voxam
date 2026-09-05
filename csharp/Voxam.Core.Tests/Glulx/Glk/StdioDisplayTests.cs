using System.Text;
using Voxam.Core.Glulx.Glk;
using SessionEndException = Voxam.Core.SessionEndException;

namespace Voxam.Tests.Glulx.Glk;

/// <summary>
/// The plain-stream face: what a piped session and the acceptance
/// harness drive, and the minimum a Glk display can be.
/// </summary>
public sealed class StdioDisplayTests
{
    // A buffer window streams its text out as it accumulates, and the
    // witness hears every run of it. The window is drained by the
    // render, so a second flush with nothing new says nothing.
    [Fact]
    public void ABufferStreamsItsTextOutOnce()
    {
        var heard = new List<string>();
        var (shown, glk) = Seam(witness: heard.Add);
        var window = Open(glk, WindowType.TextBuffer);

        Call(glk, 0x002F, Held.OfOpaque(window));
        Call(glk, 0x0080, Held.OfWord('h'));
        Call(glk, 0x0080, Held.OfWord('i'));

        glk.Display.Flush(glk.Root);
        glk.Display.Flush(glk.Root);

        Assert.Equal("hi", shown.ToString());
        Assert.Equal(["hi"], heard);
    }

    // Nothing to render is nothing said: an empty tree, and a window
    // with no text in it, both leave the stream alone.
    [Fact]
    public void NothingToRenderSaysNothing()
    {
        var (shown, glk) = Seam();

        glk.Display.Flush(null);
        Open(glk, WindowType.TextBuffer);
        glk.Display.Flush(glk.Root);

        Assert.Equal("", shown.ToString());
    }

    // A blank window shows nothing, which is the whole of what it is
    // for (Glk: Blank Windows).
    [Fact]
    public void ABlankWindowShowsNothing()
    {
        var (shown, glk) = Seam();

        Open(glk, WindowType.Blank);
        glk.Display.Flush(glk.Root);

        Assert.Equal("", shown.ToString());
    }

    // A grid is drawn as a block whenever its contents move, with a
    // divider under it: an Inform status line, on a terminal that
    // cannot address the cursor. An unchanged grid is not redrawn.
    [Fact]
    public void AGridIsDrawnAsABlockOnlyWhenItMoves()
    {
        var (shown, glk) = Seam(size: (20, 24));
        var buffer = Open(glk, WindowType.TextBuffer);
        var grid = Split(glk, buffer, WindowMethod.Above | WindowMethod.Fixed, 1,
            WindowType.TextGrid);

        // An empty grid is not a status line, and is not drawn.
        glk.Display.Flush(glk.Root);

        Assert.Equal("", shown.ToString());

        Call(glk, 0x002F, Held.OfOpaque(grid));
        Call(glk, 0x0082, "West of House");

        glk.Display.Flush(glk.Root);

        Assert.Equal("West of House\n" + new string('-', 20) + "\n", shown.ToString());

        shown.Clear();
        glk.Display.Flush(glk.Root);

        Assert.Equal("", shown.ToString());
    }

    // The divider never grows past a sensible width, however wide the
    // room is.
    [Fact]
    public void TheDividerStopsAtASensibleWidth()
    {
        var (shown, glk) = Seam(size: (200, 24));
        var buffer = Open(glk, WindowType.TextBuffer);
        var grid = Split(glk, buffer, WindowMethod.Above | WindowMethod.Fixed, 1,
            WindowType.TextGrid);

        Call(glk, 0x002F, Held.OfOpaque(grid));
        Call(glk, 0x0080, Held.OfWord('X'));

        glk.Display.Flush(glk.Root);

        Assert.Contains("\n" + new string('-', 60) + "\n", shown.ToString(), StringComparison.Ordinal);
    }

    // The tree is walked in visual order rather than tree order, so a
    // status line split off above its buffer prints above it, and two
    // windows side by side print left to right.
    [Fact]
    public void TheTreeIsWalkedInVisualOrder()
    {
        var (shown, glk) = Seam(size: (40, 10));
        var lower = Open(glk, WindowType.TextBuffer);
        var upper = Split(glk, lower, WindowMethod.Above | WindowMethod.Fixed, 1,
            WindowType.TextGrid);

        Call(glk, 0x002F, Held.OfOpaque(lower));
        Call(glk, 0x0082, "below");
        Call(glk, 0x002F, Held.OfOpaque(upper));
        Call(glk, 0x0080, Held.OfWord('A'));

        glk.Display.Flush(glk.Root);

        Assert.StartsWith("A\n", shown.ToString(), StringComparison.Ordinal);
        Assert.EndsWith("below", shown.ToString(), StringComparison.Ordinal);

        // Side by side, the left one first: the new window takes the
        // left half and its sibling keeps the right.
        var (beside, side) = Seam(size: (40, 10));
        var right = Open(side, WindowType.TextBuffer);
        var left = Split(side, right, WindowMethod.Left | WindowMethod.Proportional, 50,
            WindowType.TextBuffer);

        Call(side, 0x002F, Held.OfOpaque(right));
        Call(side, 0x0082, "right");
        Call(side, 0x002F, Held.OfOpaque(left));
        Call(side, 0x0082, "left");

        side.Display.Flush(side.Root);

        Assert.Equal("leftright", beside.ToString());
    }

    // A line is cut to what the game's buffer holds, and a shorter one
    // arrives whole.
    [Fact]
    public void ALineIsCutToWhatTheBufferHolds()
    {
        var (_, glk, face) = Wired("northwest", "go");

        Assert.Equal(("north", 0u), face.ReadLine(Any(glk), 5)!.Value);
        Assert.Equal(("go", 0u), face.ReadLine(Any(glk), 5)!.Value);
    }

    // A keystroke is the first character of a line, a bare Return is
    // the Return keycode, and a replayed key token presses the key it
    // means.
    [Fact]
    public void AKeystrokeIsTheFirstCharacterOfALine()
    {
        var (_, glk, face) = Wired("x", "", "\u0081", "\u001B");
        var window = Any(glk);

        Assert.Equal((uint)'x', face.ReadChar(window));
        Assert.Equal(KeyCode.Return, face.ReadChar(window));
        Assert.Equal(KeyCode.Up, face.ReadChar(window));
        Assert.Equal(KeyCode.Escape, face.ReadChar(window));
    }

    // With no script aboard there is no pointer: the base answer, which
    // sends glk_select to its own loud refusal.
    [Fact]
    public void WithNoScriptThereIsNoPointer()
    {
        var (_, glk, face) = Wired();

        Assert.False(face.MouseInput);
        Assert.False(face.HyperlinkInput);
        Assert.Null(face.ReadMouse(Any(glk)));
        Assert.Null(face.ReadHyperlink(Any(glk)));
    }

    // A scripted click is spent as the script says click: the command
    // stream and the positions travel in step.
    [Fact]
    public void AScriptedClickIsSpentWhereTheScriptSaysClick()
    {
        var positions = new Queue<(int X, int Y)>([(4, 9)]);
        var (shown, glk, face) = Wired(
            ["\u00FE"], clicks: () => positions.Count > 0 ? positions.Dequeue() : null);

        Assert.True(face.MouseInput);
        Assert.Equal((4, 9), face.ReadMouse(Any(glk)));
        Assert.Equal("", shown.ToString());
    }

    // A script that speaks anything else where its game waits for a
    // click has diverged, and the session ends loudly rather than
    // replaying wrong. An empty line, a different command, and a
    // spent supply of clicks are all the same divergence.
    [Fact]
    public void AScriptThatDoesNotSpellTheClickEndsTheSession()
    {
        foreach (var typed in new[] { "", "north", "\u00FE" })
        {
            var (shown, glk, face) = Wired([typed], clicks: () => null);

            Assert.Throws<SessionEndException>(() => face.ReadMouse(Any(glk)));
            Assert.Equal(
                "\nvoxam: the game waits for a click the script does not spell\n",
                shown.ToString());
        }
    }

    // A scripted link keeps the same discipline, marker and all.
    [Fact]
    public void AScriptedLinkKeepsTheSameDiscipline()
    {
        var values = new Queue<int>([77]);
        var (_, glk, face) = Wired(
            ["\u00FC"], links: () => values.Count > 0 ? values.Dequeue() : null);

        Assert.True(face.HyperlinkInput);
        Assert.Equal(77u, face.ReadHyperlink(Any(glk)));
    }

    // And the same divergence, spoken in the link's own words.
    [Fact]
    public void AScriptThatDoesNotSpellTheLinkEndsTheSession()
    {
        foreach (var typed in new[] { "", "north", "\u00FC" })
        {
            var (shown, glk, face) = Wired([typed], links: () => null);

            Assert.Throws<SessionEndException>(() => face.ReadHyperlink(Any(glk)));
            Assert.Equal(
                "\nvoxam: the game waits for a link the script does not spell\n",
                shown.ToString());
        }
    }

    // The file prompt asks in the stream, naming which way the file is
    // going. An empty answer cancels, and so does an input that ran dry
    // mid-prompt.
    [Fact]
    public void TheFilePromptAsksInTheStream()
    {
        var (shown, _, face) = Wired("bronze", "  ");

        Assert.Equal("bronze", face.PromptFile(FileUsage.SavedGame, GlkFileMode.Write));
        Assert.Equal("Save to which file? ", shown.ToString());

        shown.Clear();

        Assert.Null(face.PromptFile(FileUsage.SavedGame, GlkFileMode.Read));
        Assert.Equal("Load from which file? ", shown.ToString());

        Assert.Null(face.PromptFile(FileUsage.SavedGame, GlkFileMode.Read));
    }

    // The end of the input ends the session: it is over, not broken.
    [Fact]
    public void TheEndOfTheInputEndsTheSession()
    {
        var (_, glk, face) = Wired();

        Assert.Throws<SessionEndException>(() => face.ReadLine(Any(glk), 8));
        Assert.Throws<SessionEndException>(() => face.ReadChar(Any(glk)));
    }

    // Without a room chosen, the windows lay out over the conventional
    // terminal, which is what the reference falls back to when it
    // cannot ask.
    [Fact]
    public void TheRoomIsAConventionalTerminalUnlessOneIsChosen()
    {
        var (_, _, face) = Wired();

        Assert.Equal((80, 24), face.Size());
        Assert.True(face.EchoesInput);
        Assert.Equal((20, 24), Seam(size: (20, 24)).Glk.Display.Size());
    }

    /// <summary>Any window, so a read has one to be asked about.</summary>
    private static Window Any(Api glk) => glk.Windows.Count > 0 ? glk.Windows[0] : Open(glk, WindowType.Blank);

    /// <summary>Open a window of a type as the root of the tree.</summary>
    private static Window Open(Api glk, uint wtype) => (Window)Call(
        glk, 0x0023, Held.OfOpaque(null), Held.OfWord(0), Held.OfWord(0),
        Held.OfWord(wtype), Held.OfWord(0)).Opaque!;

    /// <summary>Split an existing window, and hand back the new one.</summary>
    private static Window Split(Api glk, Window window, uint method, int size, uint wtype) =>
        (Window)Call(
            glk, 0x0023, Held.OfOpaque(window), Held.OfWord(method), Held.OfWord((uint)size),
            Held.OfWord(wtype), Held.OfWord(0)).Opaque!;

    /// <summary>Reach one function the way the bridge would.</summary>
    private static Held Call(Api glk, int selector, params object?[] args) =>
        glk.Call(Signatures.Lookup(selector)!, args);

    private static (StringBuilder Shown, Api Glk) Seam(
        (int Width, int Height)? size = null, Action<string>? witness = null)
    {
        var shown = new StringBuilder();
        var face = new StdioDisplay(
            text => shown.Append(text), () => null, size, witness);

        return (shown, new Api(face));
    }

    private static (StringBuilder Shown, Api Glk, StdioDisplay Face) Wired(
        params string[] typed) =>
        Wired(typed, null, null);

    private static (StringBuilder Shown, Api Glk, StdioDisplay Face) Wired(
        string[] typed,
        Func<(int X, int Y)?>? clicks = null,
        Func<int?>? links = null)
    {
        var shown = new StringBuilder();
        var lines = new Queue<string>(typed);
        var face = new StdioDisplay(
            text => shown.Append(text),
            () => lines.Count > 0 ? lines.Dequeue() : null,
            null,
            null,
            clicks,
            links);

        return (shown, new Api(face), face);
    }
}
