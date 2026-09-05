using System.Globalization;
using Voxam.Core;
using Voxam.Core.Glulx.Glk;

namespace Voxam.Tests.Glulx.Glk;

/// <summary>
/// A glass that answers from a script and keeps what it was asked to
/// paint, so a whole windowed session runs with no window at all.
/// </summary>
internal sealed class PaperGlass : IGlkGlass
{
    public List<string> Painted { get; } = [];

    public Queue<string?> Keys { get; } = [];

    public Queue<(int X, int Y)?> Clicks { get; } = [];

    public int Columns { get; set; } = 10;

    public int Lines { get; set; } = 5;

    public int FontWidth { get; set; } = 2;

    public int FontHeight { get; set; } = 4;

    public uint Ink => 0xD6D6D6;

    public uint Paper => 0x1C1C1C;

    public string Taken()
    {
        var shown = string.Join(" ", Painted);

        Painted.Clear();

        return shown;
    }

    public string? ReadKey(double? timeoutSeconds) => Keys.Count > 0 ? Keys.Dequeue() : null;

    public (int X, int Y)? Click() => Clicks.Count > 0 ? Clicks.Dequeue() : null;

    public void Settle(IReadOnlyList<Paint> paints)
    {
        Painted.Add("|");

        foreach (var paint in paints)
        {
            Painted.Add(paint switch
            {
                RunPaint run => string.Create(
                    CultureInfo.InvariantCulture,
                    $"run {run.Column},{run.Line} '{run.Text}' {run.Ink:x6}/{run.Paper:x6}"
                    + $" b{(run.Bold ? 1 : 0)}i{(run.Italic ? 1 : 0)}"),
                ColourPaint fill => string.Create(
                    CultureInfo.InvariantCulture,
                    $"fill {fill.Column},{fill.Line} {fill.Width}x{fill.Height} {fill.Colour:x6}"),
                ClipPaint clip => string.Create(
                    CultureInfo.InvariantCulture,
                    $"art {clip.Column},{clip.Line} {clip.Width}x{clip.Height} of "
                    + $"{clip.SourceLeft},{clip.SourceTop} {clip.SourceWidth}x{clip.SourceHeight}"),
                _ => paint.ToString()!,
            });
        }
    }
}

/// <summary>
/// The windowed display: where its runs land in real pixels, what it
/// draws on a canvas, and how a click becomes the event a game asked
/// for.
/// </summary>
public sealed class GlassDisplayTests
{
    // The glass measures in real pixels, and the font cell is what lets
    // a text window still answer its size in characters.
    [Fact]
    public void TheGlassMeasuresInPixelsAndCells()
    {
        var (face, _, glass) = Seam();

        Assert.Equal((20, 20), face.Size());
        Assert.Equal(new Metrics(2, 4), face.Metrics);
        Assert.True(face.Graphics);
        Assert.True(face.MouseInput);
        Assert.True(face.HyperlinkInput);
        Assert.False(face.BufferImages);
        Assert.Equal(0xD6D6D6u, glass.Ink);
    }

    // Every run lands at its own pixel, dressed in the window's ink and
    // paper; reverse swaps them, and a link wears the blue that says
    // click here.
    [Fact]
    public void EveryRunLandsDressedAtItsOwnPixel()
    {
        var (face, glk, glass) = Seam();
        var window = Open(glk, WindowType.TextGrid);

        Print(glk, window, "ab");
        face.Flush(glk.Root);

        // A grid row is painted to its full width, the padding with it.
        Assert.Contains(
            "run 1,1 'ab        ' d6d6d6/1c1c1c b0i0",
            glass.Taken(),
            StringComparison.Ordinal);

        // Alert reverses; a linked run is blue.
        Call(glk, 0x0086, Held.OfWord(TextStyle.Alert));
        Call(glk, 0x0080, Held.OfWord('c'));
        Call(glk, 0x0086, Held.OfWord(TextStyle.Normal));
        Call(glk, 0x0100, Held.OfWord(7));
        Call(glk, 0x0080, Held.OfWord('d'));
        face.Flush(glk.Root);

        var shown = glass.Taken();

        Assert.Contains("'c' 1c1c1c/d6d6d6", shown, StringComparison.Ordinal);
        Assert.Contains("'d' 0066cc/1c1c1c", shown, StringComparison.Ordinal);
    }

    // The caret is a filled cell where the next character will land,
    // since a window has no hardware cursor to park; a cursor off the
    // right edge of the glass is nowhere to draw one.
    [Fact]
    public void TheCaretIsAFilledCell()
    {
        var (face, glk, glass) = Seam();
        var window = Open(glk, WindowType.TextGrid);

        face.Flush(glk.Root);
        glass.Taken();
        glass.Keys.Enqueue("h");
        glass.Keys.Enqueue("\n");

        Call(glk, 0x00D0, Held.OfOpaque(window), new WordBuffer(4), Held.OfWord(0));

        Assert.Equal(("h", 0u), face.ReadLine(window, 4));
        Assert.Contains("fill 1,1 2x4 d6d6d6", glass.Taken(), StringComparison.Ordinal);
    }

    // A canvas is white until the game says otherwise, and an erase
    // wears whatever the game last chose.
    [Fact]
    public void ACanvasIsWhiteUntilTheGameSaysOtherwise()
    {
        var (face, glk, glass) = Seam();
        var canvas = Open(glk, WindowType.Graphics);

        face.EraseRect(canvas, 0, 0, 4, 4);

        Assert.Equal("| fill 1,1 4x4 ffffff", glass.Taken());

        face.SetBackgroundColor(canvas, 0x102030);
        face.EraseRect(canvas, 0, 0, 4, 4);

        Assert.Equal("| fill 1,1 4x4 102030", glass.Taken());
    }

    // A rectangle may hang off any edge of its window, and what falls
    // outside simply is not drawn; one wholly outside draws nothing.
    [Fact]
    public void ARectangleIsClippedToItsWindow()
    {
        var (face, glk, glass) = Seam();
        var canvas = Open(glk, WindowType.Graphics);

        // The fresh canvas owes itself a clear; that is its own claim,
        // and this one is about where a rectangle lands.
        face.Flush(glk.Root);
        glass.Taken();

        face.FillRect(canvas, 0xFF0000, -4, -4, 8, 8);

        Assert.Equal("| fill 1,1 4x4 ff0000", glass.Taken());

        face.FillRect(canvas, 0xFF0000, 100, 100, 4, 4);

        Assert.Equal("", glass.Taken());
    }

    // A pending clear is honored before new paint lands, so the paint
    // is not erased out from under itself.
    [Fact]
    public void APendingClearIsHonoredBeforeNewPaintLands()
    {
        var (face, glk, glass) = Seam();
        var canvas = (GraphicsWindow)Open(glk, WindowType.Graphics);

        Assert.True(canvas.PendingClear);

        face.FillRect(canvas, 0xFF0000, 0, 0, 4, 4);

        Assert.False(canvas.PendingClear);
        Assert.Equal(
            "| fill 1,1 20x20 ffffff | fill 1,1 4x4 ff0000", glass.Taken());
    }

    // A picture is drawn at the corner the game named, and the part of
    // it that hangs off the window is not drawn.
    [Fact]
    public void APictureIsDrawnAndClippedToItsCanvas()
    {
        var (face, glk, glass) = Seam();
        var canvas = Open(glk, WindowType.Graphics);
        var picture = new ImageInfo(1, "PNG ", [1, 2, 3], 40, 40);

        face.Flush(glk.Root);
        glass.Taken();

        Assert.True(face.DrawImage(canvas, picture, 0, 0, 20, 20));
        Assert.Equal("| art 1,1 20x20 of 0,0 40x40", glass.Taken());

        // Half off the left edge: only the right half is drawn, and only
        // the right half of the picture is read.
        Assert.True(face.DrawImage(canvas, picture, -10, 0, 20, 20));
        Assert.Equal("| art 1,1 10x20 of 20,0 20x40", glass.Taken());
    }

    // A picture scaled to nothing, one wholly off the canvas, and one
    // aimed at a window that cannot draw are all simply not drawn.
    [Fact]
    public void ThereAreThreeWaysAPictureIsNotDrawn()
    {
        var (face, glk, glass) = Seam();
        var canvas = Open(glk, WindowType.Graphics);
        var picture = new ImageInfo(1, "PNG ", [1, 2, 3], 40, 40);

        face.Flush(glk.Root);
        glass.Taken();

        Assert.True(face.DrawImage(canvas, picture, 0, 0, 0, 20));
        Assert.True(face.DrawImage(canvas, picture, 100, 100, 20, 20));
        Assert.Equal("", glass.Taken());

        var (other, elsewhere, quiet) = Seam();
        var text = Open(elsewhere, WindowType.TextBuffer);

        Assert.False(other.DrawImage(text, picture, 0, 0, 20, 20));
    }

    // The keys the glass spells for itself become the Glk codes they
    // mean; anything else is the character it is, and a key of more
    // than one character is nothing usable.
    [Fact]
    public void TheGlassKeysBecomeGlkCodes()
    {
        var (face, glk, glass) = Seam();
        var window = Open(glk, WindowType.TextGrid);

        foreach (var (typed, expected) in new (string, uint)[]
        {
            ("\n", KeyCode.Return),
            ("\u007F", KeyCode.Delete),
            ("\u001B", KeyCode.Escape),
            ("\u0081", KeyCode.Up),
            ("\u0090", KeyCode.Func12),
            ("q", 'q'),
        })
        {
            glass.Keys.Enqueue(typed);

            Assert.Equal(expected, face.ReadChar(window));
        }

        // Nothing usable sends the read back round, and a timer is what
        // lets it ever answer.
        glass.Keys.Enqueue("\u001B[A");
        face.SetTimer(1);
        Thread.Sleep(20);

        Assert.Null(face.ReadChar(window));

        // And so does a wait that expired with nothing pressed at all.
        Thread.Sleep(20);

        Assert.Null(face.ReadChar(window));
    }

    // A click in an armed grid arrives in cells; one on a canvas
    // arrives in pixels. Either way the request is spent.
    [Fact]
    public void AClickArrivesInTheWindowsOwnUnits()
    {
        var (face, glk, glass) = Seam();
        var canvas = Open(glk, WindowType.Graphics);
        var grid = Split(glk, canvas, WindowMethod.Above | WindowMethod.Fixed, 2,
            WindowType.TextGrid);

        // The split moved the canvas, which owes itself a redraw
        // (Glk: Window Events); the click is what comes after.
        glk.PendingEvents.Clear();

        Call(glk, 0x00D4, Held.OfOpaque(grid));
        Clicked(glass, (6, 4));

        Assert.Null(face.ReadMouse(grid));

        var arrived = Assert.Single(glk.PendingEvents);

        Assert.Equal(EventType.MouseInput, arrived.Kind);
        Assert.Same(grid, arrived.Window);
        Assert.Equal(3u, arrived.Val1);
        Assert.Equal(1u, arrived.Val2);
        Assert.False(grid.MouseRequest);

        glk.PendingEvents.Clear();
        Call(glk, 0x00D4, Held.OfOpaque(canvas));
        Clicked(glass, (5, 12));

        Assert.Null(face.ReadMouse(canvas));

        var onCanvas = Assert.Single(glk.PendingEvents);

        Assert.Equal(EventType.MouseInput, onCanvas.Kind);
        Assert.Equal(5u, onCanvas.Val1);
        Assert.Equal(4u, onCanvas.Val2);
    }

    // A click on a linked run in an armed text window delivers the
    // link's value, which is read off the map the paint left behind.
    [Fact]
    public void AClickOnALinkedRunDeliversItsValue()
    {
        var (face, glk, glass) = Seam();
        var window = Open(glk, WindowType.TextGrid);

        Print(glk, window, "ab");
        Call(glk, 0x0100, Held.OfWord(9));
        Call(glk, 0x0080, Held.OfWord('c'));
        face.Flush(glk.Root);

        Call(glk, 0x0102, Held.OfOpaque(window));
        Clicked(glass, (5, 1));

        Assert.Null(face.ReadHyperlink(window));

        var arrived = Assert.Single(glk.PendingEvents);

        Assert.Equal(EventType.Hyperlink, arrived.Kind);
        Assert.Equal(9u, arrived.Val1);
        Assert.False(window.HyperlinkRequest);
    }

    // A click nothing asked for is swallowed, as every interpreter
    // swallows it: outside every armed window, on plain text where a
    // link was wanted, and with nothing armed at all.
    [Fact]
    public void AClickNobodyAskedForIsSwallowed()
    {
        foreach (var arm in new[] { 0, 0x00D4, 0x0102 })
        {
            var (face, glk, glass) = Seam();
            var window = Open(glk, WindowType.TextGrid);

            Print(glk, window, "ab");
            face.Flush(glk.Root);

            if (arm != 0)
            {
                Call(glk, arm, Held.OfOpaque(window));
            }

            // Outside every window, and then on plain unlinked text.
            Clicked(glass, (100, 100));
            Clicked(glass, (1, 1));
            face.SetTimer(1);
            Thread.Sleep(20);

            Assert.Null(face.ReadChar(window));
            Assert.Equal(EventType.Timer, Assert.Single(glk.PendingEvents).Kind);
        }
    }

    // A click inside an armed text window that landed on no link at
    // all selects nothing: the map says where the links are, and
    // everywhere else is plain text.
    [Fact]
    public void AClickOnPlainTextSelectsNothing()
    {
        var (face, glk, glass) = Seam();
        var window = Open(glk, WindowType.TextGrid);

        Print(glk, window, "ab");
        face.Flush(glk.Root);

        Call(glk, 0x0102, Held.OfOpaque(window));
        Clicked(glass, (1, 1));
        face.SetTimer(1);
        Thread.Sleep(20);

        Assert.Null(face.ReadChar(window));
        Assert.Equal(EventType.Timer, Assert.Single(glk.PendingEvents).Kind);
        Assert.True(window.HyperlinkRequest);
    }

    // A request on a window that cannot carry it is no request at all:
    // a canvas has no links to select, and a buffer has no cells to
    // click in.
    [Fact]
    public void ARequestOnAWindowThatCannotCarryItIsSkipped()
    {
        var (face, glk, glass) = Seam();
        var canvas = Open(glk, WindowType.Graphics);
        var buffer = Split(glk, canvas, WindowMethod.Above | WindowMethod.Fixed, 2,
            WindowType.TextBuffer);

        face.Flush(glk.Root);
        glk.PendingEvents.Clear();

        // The canvas is armed for links, which it can never carry, and
        // the buffer for clicks, which it can never report.
        canvas.HyperlinkRequest = true;
        buffer.MouseRequest = true;

        Clicked(glass, (2, 12));
        Clicked(glass, (2, 2));
        face.SetTimer(1);
        Thread.Sleep(20);

        Assert.Null(face.ReadChar(canvas));
        Assert.Null(face.ReadChar(canvas));
        Assert.True(canvas.HyperlinkRequest);
        Assert.True(buffer.MouseRequest);
    }

    // A cursor at the right edge of the glass is nowhere to draw a
    // caret, so none is drawn.
    [Fact]
    public void ACaretPastTheEdgeIsNotDrawn()
    {
        var (face, glk, glass) = Seam();
        var window = Open(glk, WindowType.TextBuffer);

        face.Flush(glk.Root);
        glass.Taken();

        // Ten characters at two pixels each fills the glass exactly, so
        // the caret would land one cell past its right edge.
        foreach (var key in "abcdefghij")
        {
            glass.Keys.Enqueue(key.ToString());
        }

        glass.Keys.Enqueue("\n");

        Call(glk, 0x00D0, Held.OfOpaque(window), new WordBuffer(16), Held.OfWord(0));

        Assert.Equal(("abcdefghij", 0u), face.ReadLine(window, 16));
        Assert.DoesNotContain("fill 21,", glass.Taken(), StringComparison.Ordinal);
    }

    // A click with no position behind it, and one at a library-less
    // display, are both nothing to deliver.
    [Fact]
    public void AClickWithNothingBehindItIsNothingToDeliver()
    {
        var (face, glk, glass) = Seam();
        var window = Open(glk, WindowType.TextGrid);

        Call(glk, 0x00D4, Held.OfOpaque(window));

        // The marker arrives but the glass has no position to give.
        glass.Keys.Enqueue("\u00FE");
        face.SetTimer(1);
        Thread.Sleep(20);

        Assert.Null(face.ReadChar(window));
        Assert.Equal(EventType.Timer, Assert.Single(glk.PendingEvents).Kind);

        var elsewhere = new PaperGlass();
        var loose = new GlassDisplay(elsewhere);

        Clicked(elsewhere, (1, 1));
        loose.SetTimer(1);
        Thread.Sleep(20);

        Assert.Null(loose.ReadHyperlink(new BlankWindow()));
    }

    // A double click is two clicks: Glk knows only clicks, so a fast
    // pair at the window is simply two mouse events.
    [Fact]
    public void ADoubleClickIsJustAClick()
    {
        var (face, glk, glass) = Seam();
        var window = Open(glk, WindowType.TextGrid);

        Call(glk, 0x00D4, Held.OfOpaque(window));
        glass.Clicks.Enqueue((2, 2));
        glass.Keys.Enqueue("\u00FD");

        Assert.Null(face.ReadMouse(window));
        Assert.Equal(EventType.MouseInput, Assert.Single(glk.PendingEvents).Kind);
    }

    // The seams hear each delivered click and each selection, as the
    // very values the game itself was told, which is what a recording
    // rides.
    [Fact]
    public void TheSeamsHearWhatTheGameWasTold()
    {
        var glass = new PaperGlass();
        var heard = new List<string>();
        var face = new GlassDisplay(
            glass,
            onClick: (x, y) => heard.Add($"click {x},{y}"),
            onLink: value => heard.Add($"link {value}"));
        var glk = new Api(face);
        var window = Open(glk, WindowType.TextGrid);

        Call(glk, 0x002F, Held.OfOpaque(window));
        Call(glk, 0x0100, Held.OfWord(4));
        Call(glk, 0x0082, "ab");
        face.Flush(glk.Root);

        Call(glk, 0x0102, Held.OfOpaque(window));
        Clicked(glass, (1, 1));
        face.ReadHyperlink(window);

        Call(glk, 0x00D4, Held.OfOpaque(window));
        Clicked(glass, (4, 4));
        face.ReadMouse(window);

        Assert.Equal(["link 4", "click 2,1"], heard);
    }

    /// <summary>Queue a click and the position it landed at.</summary>
    private static void Clicked(PaperGlass glass, (int X, int Y) at)
    {
        glass.Clicks.Enqueue(at);
        glass.Keys.Enqueue("\u00FE");
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

    private static (GlassDisplay Face, Api Glk, PaperGlass Glass) Seam()
    {
        var glass = new PaperGlass();
        var face = new GlassDisplay(glass);

        return (face, new Api(face), glass);
    }
}
