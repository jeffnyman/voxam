using Voxam.Core.Glulx;
using Voxam.Core.Glulx.Glk;
using GlulxException = Voxam.Core.GlulxException;
using SessionEndException = Voxam.Core.SessionEndException;

namespace Voxam.Tests.Glulx.Glk;

/// <summary>A display that claims everything and measures oddly.</summary>
internal sealed class LoudDisplay : GlkDisplay
{
    public int Width { get; set; } = 80;

    public int Height { get; set; } = 24;

    public Metrics Cell { get; set; } = Metrics.CharacterCell;

    public uint? Measured { get; set; }

    public bool Distinct { get; set; }

    public GlkLibrary? Attached => Library;

    public override bool Graphics => true;

    public override bool BufferImages => true;

    public override bool Sound => true;

    public override bool MouseInput => true;

    public override bool TimerInput => true;

    public override bool HyperlinkInput => true;

    public int Flushes { get; private set; }

    public override (int Width, int Height) Size() => (Width, Height);

    public override void Flush(Window? root) => Flushes++;

    public override Metrics MetricsFor(Window window) => Cell;

    public override bool StyleDistinguish(Window window, uint first, uint second) => Distinct;

    public override uint? StyleMeasure(Window window, uint style, uint hint) => Measured;
}

/// <summary>
/// The library itself: what it opens, what it prints, and what it
/// answers about the display it stands on.
/// </summary>
public sealed class ApiTests
{
    private const uint Buf = 0x500;
    private const uint Ref = 0x600;

    // A library with no display still works: windows lay out over a
    // conventional terminal's worth of room and what is written goes
    // nowhere in particular.
    [Fact]
    public void ALibraryWithNoDisplayStillWorks()
    {
        var glk = new Api();

        Assert.IsType<NullDisplay>(glk.Display);
        Assert.Equal((80, 24), glk.Display.Size());
        Assert.Null(glk.Root);
        Assert.Null(glk.CurrentStream);
        Assert.Empty(glk.Windows);
        Assert.Empty(glk.Streams);
        Assert.Empty(glk.FileRefs);
        Assert.Empty(glk.PendingEvents);
        Assert.Empty(glk.StyleHints);

        glk.Display.Flush(null);
    }

    // The display is told which library it serves, so it can reach back
    // into the window tree when it draws.
    [Fact]
    public void TheDisplayIsToldWhichLibraryItServes()
    {
        var display = new LoudDisplay();
        var glk = new Api(display);

        Assert.Same(glk, display.Attached);
        Assert.Same(display, glk.Display);
    }

    // The version answers what this Glk is, and an unknown selector
    // answers zero: the honest answer for the unsupported and the
    // unheard-of alike.
    [Fact]
    public void TheGestaltAnswersItsVersionAndNothingForTheUnknown()
    {
        var (bridge, _) = Seam();

        Assert.Equal(Api.GlkVersion, bridge.Perform(0x0004, [GlkGestalt.Version, 0]));
        Assert.Equal(0u, bridge.Perform(0x0004, [999, 0]));
    }

    // A display that can do nothing says so, and one that can do
    // everything says that instead.
    [Theory]
    [InlineData(GlkGestalt.Graphics, 0u, 0u, 1u)]
    [InlineData(GlkGestalt.GraphicsTransparency, 0u, 0u, 1u)]
    [InlineData(GlkGestalt.GraphicsCharInput, 0u, 0u, 1u)]
    [InlineData(GlkGestalt.Sound, 0u, 0u, 1u)]
    [InlineData(GlkGestalt.Sound2, 0u, 0u, 1u)]
    [InlineData(GlkGestalt.SoundVolume, 0u, 0u, 1u)]
    [InlineData(GlkGestalt.SoundNotify, 0u, 0u, 1u)]
    [InlineData(GlkGestalt.Timer, 0u, 0u, 1u)]
    [InlineData(GlkGestalt.HyperlinkInput, 0u, 0u, 1u)]
    [InlineData(GlkGestalt.DrawImage, WindowType.Graphics, 0u, 1u)]
    [InlineData(GlkGestalt.DrawImageScale, WindowType.TextBuffer, 0u, 1u)]
    [InlineData(GlkGestalt.DrawImage, WindowType.TextGrid, 0u, 0u)]
    [InlineData(GlkGestalt.MouseInput, WindowType.TextGrid, 0u, 1u)]
    [InlineData(GlkGestalt.MouseInput, WindowType.Graphics, 0u, 1u)]
    [InlineData(GlkGestalt.MouseInput, WindowType.TextBuffer, 0u, 0u)]
    public void CapabilityAnswersFollowTheDisplay(
        uint selector, uint value, uint quiet, uint loud)
    {
        Assert.Equal(quiet, Seam().Bridge.Perform(0x0004, [selector, value]));
        Assert.Equal(loud, Seam(new LoudDisplay()).Bridge.Perform(0x0004, [selector, value]));
    }

    // Music means song files, and nothing here decodes one, so the claim
    // stays honestly zero however loud the display is.
    [Fact]
    public void MusicIsRefusedByEveryDisplay()
    {
        Assert.Equal(0u, Seam().Bridge.Perform(0x0004, [GlkGestalt.SoundMusic, 0]));
        Assert.Equal(0u, Seam(new LoudDisplay()).Bridge.Perform(0x0004, [GlkGestalt.SoundMusic, 0]));
    }

    // The answers that do not depend on a display at all.
    [Theory]
    [InlineData(GlkGestalt.Unicode)]
    [InlineData(GlkGestalt.UnicodeNorm)]
    [InlineData(GlkGestalt.LineInputEcho)]
    [InlineData(GlkGestalt.LineTerminators)]
    [InlineData(GlkGestalt.LineTerminatorKey)]
    [InlineData(GlkGestalt.DateTime)]
    [InlineData(GlkGestalt.ResourceStream)]
    [InlineData(GlkGestalt.Hyperlinks)]
    public void SomeCapabilitiesAreTheLibrarysOwn(uint selector) =>
        Assert.Equal(1u, Seam().Bridge.Perform(0x0004, [selector, 0]));

    // A character can be typed if it is printable or one of the special
    // keys; Unknown is not a key a game can ask to receive.
    [Theory]
    [InlineData(0x41u, 1u)]
    [InlineData(0x0Au, 1u)]
    [InlineData(0xE9u, 1u)]
    [InlineData(0x1Fu, 0u)]
    [InlineData(0x7Fu, 0u)]
    [InlineData(KeyCode.Return, 1u)]
    [InlineData(KeyCode.Func12, 1u)]
    [InlineData(KeyCode.Unknown, 0u)]
    public void CharacterInputAnswersForPrintablesAndSpecialKeys(uint value, uint expected) =>
        Assert.Equal(expected, Seam().Bridge.Perform(0x0004, [GlkGestalt.CharInput, value]));

    // A line is made of printable characters, and the newline that ends
    // one is not among them.
    [Theory]
    [InlineData(0x41u, 1u)]
    [InlineData(0x0Au, 0u)]
    [InlineData(0x01u, 0u)]
    public void LineInputRefusesTheNewlineThatEndsIt(uint value, uint expected) =>
        Assert.Equal(expected, Seam().Bridge.Perform(0x0004, [GlkGestalt.LineInput, value]));

    // Character output says whether a character prints exactly, and the
    // extended form writes the same answer into the array it was given.
    [Fact]
    public void CharacterOutputAnswersAndFillsItsArray()
    {
        var (bridge, _) = Seam();

        Assert.Equal(2u, bridge.Perform(0x0004, [GlkGestalt.CharOutput, 0x41]));
        Assert.Equal(0u, bridge.Perform(0x0004, [GlkGestalt.CharOutput, 0x07]));

        Assert.Equal(2u, bridge.Perform(0x0005, [GlkGestalt.CharOutput, 0x41, Buf, 1]));
        Assert.Equal(1u, Word(bridge, Buf));

        Assert.Equal(0u, bridge.Perform(0x0005, [GlkGestalt.CharOutput, 0x07, Buf, 1]));
        Assert.Equal(0u, Word(bridge, Buf));

        // An array with no room in it is simply not written to.
        Assert.Equal(2u, bridge.Perform(0x0005, [GlkGestalt.CharOutput, 0x41, Buf, 0]));
    }

    // The first window is the root, and it opens with a stream of its
    // own already on the live list.
    [Fact]
    public void TheFirstWindowIsTheRoot()
    {
        var (bridge, glk) = Seam();

        var ident = bridge.Perform(0x0023, [0, 0, 0, WindowType.TextBuffer, 7]);

        Assert.NotEqual(0u, ident);
        Assert.Same(glk.Root, glk.Windows[0]);
        Assert.Equal(7u, glk.Root!.Rock);
        Assert.Single(glk.Windows);
        Assert.Single(glk.Streams);
        Assert.Equal(new Box(0, 0, 80, 24), glk.Root.BBox);
    }

    // A split makes a pair above the two, and the tree still reaches
    // every window from the root.
    [Fact]
    public void ASplitMakesAPairAboveBoth()
    {
        var (bridge, glk) = Seam();

        var first = bridge.Perform(0x0023, [0, 0, 0, WindowType.TextBuffer, 1]);
        var second = bridge.Perform(
            0x0023, [first, WindowMethod.Above | WindowMethod.Fixed, 3, WindowType.TextGrid, 2]);

        var pair = Assert.IsType<PairWindow>(glk.Root);

        Assert.Equal(3, glk.Windows.Count);
        Assert.Equal(WindowType.Pair, bridge.Perform(0x0028, [bridge.Registry.Register(pair, 0)]));
        Assert.Same(pair, glk.Windows.OfType<Window>().First(each => each is PairWindow));
        Assert.Equal(new Box(0, 0, 80, 3), pair.Child2.BBox);
        Assert.Equal(second, bridge.Registry.Register(pair.Child2, 0));
    }

    // The first window may not be a split, and a later one must be.
    [Fact]
    public void ASplitMustMatchTheTree()
    {
        var (bridge, _) = Seam();

        // An id naming nothing decodes to the null window, so the split
        // has to name a real one for the tree to object to it.
        var stranger = bridge.Registry.Register(new TextGridWindow(), 0);

        Assert.Equal(
            "window_open: splitwin must be null for the first window",
            Assert.Throws<GlulxException>(
                () => bridge.Perform(0x0023, [stranger, 0, 0, WindowType.TextBuffer, 0])).Message);

        var first = bridge.Perform(0x0023, [0, 0, 0, WindowType.TextBuffer, 0]);

        Assert.Equal(
            "window_open: splitwin must not be null",
            Assert.Throws<GlulxException>(
                () => bridge.Perform(0x0023, [0, 0x12, 3, WindowType.TextGrid, 0])).Message);

        Assert.Equal(
            "window_open: the method is neither fixed nor proportional",
            Assert.Throws<GlulxException>(
                () => bridge.Perform(0x0023, [first, 0x02, 3, WindowType.TextGrid, 0])).Message);

        Assert.Equal(
            "window_open: the method names no direction",
            Assert.Throws<GlulxException>(
                () => bridge.Perform(0x0023, [first, 0x14, 3, WindowType.TextGrid, 0])).Message);
    }

    // A pair window is only ever made by splitting, and a type this Glk
    // does not carry answers nothing rather than faulting, so a game can
    // probe by trying.
    [Fact]
    public void SomeWindowTypesCannotBeOpened()
    {
        var (bridge, _) = Seam();

        Assert.Equal(
            "window_open: cannot open a pair window directly",
            Assert.Throws<GlulxException>(
                () => bridge.Perform(0x0023, [0, 0, 0, WindowType.Pair, 0])).Message);

        Assert.Equal(0u, bridge.Perform(0x0023, [0, 0, 0, WindowType.Graphics, 0]));
        Assert.Equal(0u, bridge.Perform(0x0023, [0, 0, 0, 99, 0]));

        // A display that carries canvases opens one.
        Assert.NotEqual(0u, Seam(new LoudDisplay()).Bridge
            .Perform(0x0023, [0, 0, 0, WindowType.Graphics, 0]));
    }

    // Closing a window takes its subtree with it and promotes the
    // sibling into the parent pair's place.
    [Fact]
    public void ClosingAWindowPromotesItsSibling()
    {
        var (bridge, glk) = Seam();

        var first = bridge.Perform(0x0023, [0, 0, 0, WindowType.TextBuffer, 1]);
        var second = bridge.Perform(
            0x0023, [first, WindowMethod.Above | WindowMethod.Fixed, 3, WindowType.TextGrid, 2]);

        bridge.Perform(0x0024, [second, Ref]);

        Assert.Single(glk.Windows);
        Assert.Same(glk.Root, glk.Windows[0]);
        Assert.Equal(first, bridge.Registry.Register(glk.Root!, 0));
        Assert.Equal(new Box(0, 0, 80, 24), glk.Root!.BBox);

        bridge.Perform(0x0024, [first, 0]);

        Assert.Null(glk.Root);
        Assert.Empty(glk.Windows);
        Assert.Empty(glk.Streams);
    }

    // The null window cannot be closed, and closing one reports what its
    // stream carried.
    [Fact]
    public void ClosingReportsTheStreamsCountsAndRefusesTheNullWindow()
    {
        var (bridge, glk) = Seam();

        Assert.Equal(
            "window_close: invalid window",
            Assert.Throws<GlulxException>(() => bridge.Perform(0x0024, [0, Ref])).Message);

        var ident = bridge.Perform(0x0023, [0, 0, 0, WindowType.TextBuffer, 0]);
        bridge.Perform(0x002F, [ident]);
        bridge.Perform(0x0082, [StringAt(bridge, "hi")]);
        bridge.Perform(0x0024, [ident, Ref]);

        Assert.Equal(0u, Word(bridge, Ref));
        Assert.Equal(2u, Word(bridge, Ref + 4));
        Assert.Null(glk.CurrentStream);
    }

    // Only a pair window has an arrangement, and its axis cannot change.
    [Fact]
    public void OnlyAPairHasAnArrangementAndItsAxisIsFixed()
    {
        var (bridge, glk) = Seam();

        var first = bridge.Perform(0x0023, [0, 0, 0, WindowType.TextBuffer, 1]);
        bridge.Perform(0x0023, [first, WindowMethod.Above | WindowMethod.Fixed, 3, WindowType.TextGrid, 2]);

        var pair = bridge.Registry.Register(glk.Root!, 0);
        var grid = bridge.Registry.Register(((PairWindow)glk.Root!).Child2, 0);

        Assert.Equal(
            "window_set_arrangement: not a pair window",
            Assert.Throws<GlulxException>(
                () => bridge.Perform(0x0026, [first, 0x12, 3, 0])).Message);

        Assert.Equal(
            "window_get_arrangement: not a pair window",
            Assert.Throws<GlulxException>(
                () => bridge.Perform(0x0027, [first, Ref, Ref + 4, Ref + 8])).Message);

        Assert.Equal(
            "window_set_arrangement: a split cannot change its axis",
            Assert.Throws<GlulxException>(
                () => bridge.Perform(0x0026, [pair, WindowMethod.Left | WindowMethod.Fixed, 3, 0])).Message);

        Assert.Equal(
            "window_set_arrangement: the key cannot be a pair window",
            Assert.Throws<GlulxException>(
                () => bridge.Perform(0x0026, [pair, 0x12, 3, pair])).Message);

        // A window outside this pair's subtree cannot be its key.
        var stranger = new TextGridWindow();

        Assert.Equal(
            "window_set_arrangement: the key must live under the pair",
            Assert.Throws<GlulxException>(() => bridge.Perform(
                0x0026, [pair, 0x12, 3, bridge.Registry.Register(stranger, 0)])).Message);

        // Turning the split around swaps the children while the glass
        // stays where it is.
        bridge.Perform(0x0026, [pair, WindowMethod.Below | WindowMethod.Fixed, 5, grid]);
        bridge.Perform(0x0027, [pair, Ref, Ref + 4, Ref + 8]);

        Assert.Equal(WindowMethod.Below | WindowMethod.Fixed, Word(bridge, Ref));
        Assert.Equal(5u, Word(bridge, Ref + 4));
        Assert.Equal(grid, Word(bridge, Ref + 8));
    }

    // Everything a game can ask about one window.
    [Fact]
    public void AWindowAnswersForItself()
    {
        var (bridge, glk) = Seam();

        var first = bridge.Perform(0x0023, [0, 0, 0, WindowType.TextBuffer, 11]);
        var second = bridge.Perform(
            0x0023, [first, WindowMethod.Above | WindowMethod.Fixed, 3, WindowType.TextGrid, 12]);
        var pair = bridge.Registry.Register(glk.Root!, 0);

        Assert.Equal(11u, bridge.Perform(0x0021, [first]));
        Assert.Equal(0u, bridge.Perform(0x0021, [0]));
        Assert.Equal(pair, bridge.Perform(0x0022, []));
        Assert.Equal(WindowType.TextGrid, bridge.Perform(0x0028, [second]));
        Assert.Equal(0u, bridge.Perform(0x0028, [0]));
        Assert.Equal(pair, bridge.Perform(0x0029, [second]));
        Assert.Equal(0u, bridge.Perform(0x0029, [0]));
        Assert.Equal(first, bridge.Perform(0x0030, [second]));
        Assert.Equal(0u, bridge.Perform(0x0030, [0]));
        Assert.Equal(0u, bridge.Perform(0x0030, [pair]));

        bridge.Perform(0x0025, [second, Ref, Ref + 4]);

        Assert.Equal(80u, Word(bridge, Ref));
        Assert.Equal(3u, Word(bridge, Ref + 4));

        // The null window has no size at all.
        bridge.Perform(0x0025, [0, Ref, Ref + 4]);

        Assert.Equal(0u, Word(bridge, Ref));
    }

    // A cursor belongs to a grid, and nothing else has one.
    [Fact]
    public void OnlyAGridHasACursor()
    {
        var (bridge, glk) = Seam();

        var buffer = bridge.Perform(0x0023, [0, 0, 0, WindowType.TextBuffer, 0]);

        Assert.Equal(
            "window_move_cursor: not a text grid window",
            Assert.Throws<GlulxException>(() => bridge.Perform(0x002B, [buffer, 1, 1])).Message);

        var grid = bridge.Perform(
            0x0023, [buffer, WindowMethod.Above | WindowMethod.Fixed, 3, WindowType.TextGrid, 0]);

        bridge.Perform(0x002B, [grid, 2, 1]);
        bridge.Perform(0x0081, [bridge.Perform(0x002C, [grid]), 0x58]);

        var window = (TextGridWindow)glk.Windows.First(each => each is TextGridWindow);

        Assert.Equal("  X" + new string(' ', 77), window.Rows()[1]);
    }

    // A window's own stream, its echo, and the clearing of it.
    [Fact]
    public void AWindowCarriesItsStreamsAndCanBeCleared()
    {
        var (bridge, glk) = Seam();

        var ident = bridge.Perform(0x0023, [0, 0, 0, WindowType.TextBuffer, 0]);
        var stream = bridge.Perform(0x002C, [ident]);

        Assert.Equal(0u, bridge.Perform(0x002C, [0]));
        Assert.Equal(0u, bridge.Perform(0x002E, [ident]));
        Assert.Equal(0u, bridge.Perform(0x002E, [0]));

        var echo = bridge.Perform(0x0043, [Buf, 8, GlkFileMode.Write, 0]);

        bridge.Perform(0x002D, [ident, echo]);

        Assert.Equal(echo, bridge.Perform(0x002E, [ident]));

        // The null window takes no echo and answers none.
        bridge.Perform(0x002D, [0, echo]);

        bridge.Perform(0x0081, [stream, 0x41]);

        Assert.Equal(0x41, Byte(bridge, Buf));

        bridge.Perform(0x002A, [ident]);
        bridge.Perform(0x002A, [0]);

        Assert.Empty(((TextBufferWindow)glk.Windows[0]).Content);
    }

    // The printing functions follow the current stream, which a window
    // or a stream can claim.
    [Fact]
    public void PrintingFollowsTheCurrentStream()
    {
        var (bridge, glk) = Seam();

        var window = bridge.Perform(0x0023, [0, 0, 0, WindowType.TextBuffer, 0]);

        Assert.Equal(0u, bridge.Perform(0x0048, []));

        bridge.Perform(0x002F, [window]);

        Assert.Equal(bridge.Perform(0x002C, [window]), bridge.Perform(0x0048, []));

        bridge.Perform(0x0080, [0x41]);
        bridge.Perform(0x0128, [0x1F600]);
        bridge.Perform(0x0082, [StringAt(bridge, "bc")]);

        Assert.Equal("A\U0001F600bc", ((TextBufferWindow)glk.Windows[0]).Text());

        // Sent nowhere, printing simply goes nowhere.
        bridge.Perform(0x002F, [0]);

        Assert.Null(glk.CurrentStream);

        bridge.Perform(0x0080, [0x5A]);
        bridge.Perform(0x0082, [StringAt(bridge, "z")]);
        bridge.Perform(0x0084, [Buf, 2]);
        bridge.Perform(0x0086, [TextStyle.Header]);
        bridge.Perform(0x0100, [3]);

        Assert.Equal("A\U0001F600bc", ((TextBufferWindow)glk.Windows[0]).Text());
    }

    // Style and link mark the stream they are set on, and only a window
    // stream shows a style at all.
    [Fact]
    public void StyleAndLinkMarkTheStreamTheyAreSetOn()
    {
        var (bridge, glk) = Seam();

        var window = bridge.Perform(0x0023, [0, 0, 0, WindowType.TextBuffer, 0]);
        var stream = bridge.Perform(0x002C, [window]);

        bridge.Perform(0x0087, [stream, TextStyle.Alert]);
        bridge.Perform(0x0101, [stream, 42]);

        Assert.Equal(TextStyle.Alert, glk.Windows[0].Style);
        Assert.Equal(42u, glk.Windows[0].Stream.Hyperlink);

        // A memory stream takes a link but has no style to show.
        var memory = bridge.Perform(0x0043, [Buf, 4, GlkFileMode.Write, 0]);

        bridge.Perform(0x0087, [memory, TextStyle.Header]);
        bridge.Perform(0x0101, [memory, 9]);

        Assert.Equal(9u, glk.Streams[0].Hyperlink);

        // And the null stream takes neither.
        bridge.Perform(0x0087, [0, TextStyle.Header]);
        bridge.Perform(0x0101, [0, 9]);
    }

    // A memory stream carries what is written and reads it back, and the
    // mode that a memory stream cannot take is refused.
    [Fact]
    public void AMemoryStreamCarriesAndReadsBack()
    {
        var (bridge, glk) = Seam();

        Assert.Equal(
            "stream_open_memory: illegal filemode",
            Assert.Throws<GlulxException>(
                () => bridge.Perform(0x0043, [Buf, 4, GlkFileMode.WriteAppend, 0])).Message);

        var ident = bridge.Perform(0x0043, [Buf, 8, GlkFileMode.ReadWrite, 33]);

        Assert.Equal(33u, bridge.Perform(0x0041, [ident]));
        Assert.Equal(0u, bridge.Perform(0x0041, [0]));

        bridge.Perform(0x0085, [ident, StringAt(bridge, "abc") + 1, 3]);

        Assert.Equal(3u, bridge.Perform(0x0046, [ident]));
        Assert.Equal(0u, bridge.Perform(0x0046, [0]));

        bridge.Perform(0x0045, [ident, 0, SeekMode.Start]);
        bridge.Perform(0x0045, [0, 0, SeekMode.Start]);

        Assert.Equal(0x61u, bridge.Perform(0x0090, [ident]));
        Assert.Equal(unchecked((uint)-1), bridge.Perform(0x0090, [0]));

        Assert.Equal(2u, bridge.Perform(0x0092, [ident, Ref, 2]));
        Assert.Equal(0u, bridge.Perform(0x0092, [0, Ref, 2]));

        bridge.Perform(0x0044, [ident, Ref]);

        Assert.Equal(3u, Word(bridge, Ref));
        Assert.Equal(3u, Word(bridge, Ref + 4));
        Assert.Empty(glk.Streams);
    }

    // A word-wide memory stream reads a line the same way, and the null
    // stream cannot be closed.
    [Fact]
    public void AWordStreamReadsALineAndTheNullStreamCannotClose()
    {
        var (bridge, _) = Seam();

        Poke(bridge, Buf, 0x41);
        Poke(bridge, Buf + 4, Characters.Newline);
        Poke(bridge, Buf + 8, 0x42);

        var ident = bridge.Perform(0x0139, [Buf, 3, GlkFileMode.Read, 0]);

        Assert.Equal(2u, bridge.Perform(0x0132, [ident, Ref, 4]));
        Assert.Equal(0u, bridge.Perform(0x0132, [0, Ref, 4]));
        Assert.Equal(0x41u, Word(bridge, Ref));

        Assert.Equal(
            "stream_close: invalid stream",
            Assert.Throws<GlulxException>(() => bridge.Perform(0x0044, [0, Ref])).Message);
    }

    // The current stream stops being current when it closes.
    [Fact]
    public void ClosingTheCurrentStreamLeavesNoneCurrent()
    {
        var (bridge, glk) = Seam();

        var ident = bridge.Perform(0x0043, [Buf, 4, GlkFileMode.Write, 0]);

        bridge.Perform(0x0047, [ident]);

        Assert.NotNull(glk.CurrentStream);

        bridge.Perform(0x0044, [ident, 0]);

        Assert.Null(glk.CurrentStream);
    }

    // Walking the live objects: the null object starts the walk, and the
    // one after the last ends it. An object no longer on the list ends
    // it too.
    [Fact]
    public void WalksStartAtNothingAndEndAtNothing()
    {
        var (bridge, glk) = Seam();

        var first = bridge.Perform(0x0023, [0, 0, 0, WindowType.TextBuffer, 5]);

        Assert.Equal(first, bridge.Perform(0x0020, [0, Ref]));
        Assert.Equal(5u, Word(bridge, Ref));

        Assert.Equal(0u, bridge.Perform(0x0020, [first, Ref]));
        Assert.Equal(0u, Word(bridge, Ref));

        var stranger = bridge.Registry.Register(new TextGridWindow(), 0);

        Assert.Equal(0u, bridge.Perform(0x0020, [stranger, 0]));

        // Streams walk the same way, newest first.
        var stream = bridge.Perform(0x0043, [Buf, 4, GlkFileMode.Write, 6]);

        Assert.Equal(stream, bridge.Perform(0x0040, [0, Ref]));
        Assert.Equal(6u, Word(bridge, Ref));
        Assert.NotEqual(0u, bridge.Perform(0x0040, [stream, 0]));
    }

    // A styling hint is recorded for a display to honor, and withdrawn
    // when the game says so.
    [Fact]
    public void StyleHintsAreRecordedAndWithdrawn()
    {
        var (bridge, glk) = Seam();

        bridge.Perform(0x00B0, [WindowType.TextBuffer, TextStyle.Header, 4, unchecked((uint)-3)]);

        Assert.Equal(-3, glk.StyleHints[(WindowType.TextBuffer, TextStyle.Header, 4)]);

        bridge.Perform(0x00B1, [WindowType.TextBuffer, TextStyle.Header, 4]);
        bridge.Perform(0x00B1, [WindowType.TextBuffer, TextStyle.Header, 9]);

        Assert.Empty(glk.StyleHints);
    }

    // Only the display knows whether two styles look different, and one
    // that cannot say answers no. The same style is never distinct from
    // itself, whatever the display thinks.
    [Fact]
    public void OnlyTheDisplayKnowsWhetherStylesDiffer()
    {
        var (quiet, _) = Seam();
        var display = new LoudDisplay { Distinct = true };
        var (loud, _) = Seam(display);

        var first = quiet.Perform(0x0023, [0, 0, 0, WindowType.TextBuffer, 0]);
        var second = loud.Perform(0x0023, [0, 0, 0, WindowType.TextBuffer, 0]);

        Assert.Equal(0u, quiet.Perform(0x00B2, [first, TextStyle.Normal, TextStyle.Header]));
        Assert.Equal(1u, loud.Perform(0x00B2, [second, TextStyle.Normal, TextStyle.Header]));
        Assert.Equal(0u, loud.Perform(0x00B2, [second, TextStyle.Header, TextStyle.Header]));
        Assert.Equal(0u, loud.Perform(0x00B2, [0, TextStyle.Normal, TextStyle.Header]));
    }

    // A style can be measured only where the display can measure it.
    [Fact]
    public void AStyleIsMeasuredOnlyWhereTheDisplayCan()
    {
        var display = new LoudDisplay { Measured = 12 };
        var (bridge, _) = Seam(display);

        var window = bridge.Perform(0x0023, [0, 0, 0, WindowType.TextBuffer, 0]);

        Assert.Equal(1u, bridge.Perform(0x00B3, [window, TextStyle.Normal, 0, Ref]));
        Assert.Equal(12u, Word(bridge, Ref));
        Assert.Equal(1u, bridge.Perform(0x00B3, [window, TextStyle.Normal, 0, 0]));
        Assert.Equal(0u, bridge.Perform(0x00B3, [0, TextStyle.Normal, 0, Ref]));

        display.Measured = null;

        Assert.Equal(0u, bridge.Perform(0x00B3, [window, TextStyle.Normal, 0, Ref]));
    }

    // A display that lays out in pixels gives its cell, and the windows
    // measure themselves against it when the tree is arranged.
    [Fact]
    public void TheDisplaysCellDecidesWhatAWindowMeasures()
    {
        var display = new LoudDisplay { Width = 640, Height = 480, Cell = new Metrics(8, 16) };
        var (bridge, _) = Seam(display);

        var window = bridge.Perform(0x0023, [0, 0, 0, WindowType.TextBuffer, 0]);

        bridge.Perform(0x0025, [window, Ref, Ref + 4]);

        Assert.Equal(80u, Word(bridge, Ref));
        Assert.Equal(30u, Word(bridge, Ref + 4));
    }

    // A canvas that moves is owed a redraw, and the event waits for the
    // era that reads it.
    [Fact]
    public void AMovedCanvasIsOwedARedraw()
    {
        var display = new LoudDisplay();
        var (bridge, glk) = Seam(display);

        var canvas = bridge.Perform(0x0023, [0, 0, 0, WindowType.Graphics, 0]);

        Assert.Empty(glk.PendingEvents);

        display.Width = 100;
        bridge.Perform(0x0023, [canvas, WindowMethod.Above | WindowMethod.Fixed, 3, WindowType.TextGrid, 0]);

        var owed = Assert.Single(glk.PendingEvents);

        Assert.Equal(EventType.Redraw, owed.Kind);
        Assert.Same(glk.Windows.First(each => each is GraphicsWindow), owed.Window);
    }

    // Ending the session shows whatever is pending and stops the machine
    // wherever it stood (Glk: Your Program's Main Function).
    [Fact]
    public void ExitFlushesAndEndsTheSession()
    {
        var display = new LoudDisplay();
        var (bridge, _) = Seam(display);

        Assert.Throws<SessionEndException>(() => bridge.Perform(0x0001, []));
        Assert.Equal(1, display.Flushes);
    }

    // A tick yields time to the display, which here is nothing at all
    // (Glk: The Tick Thing).
    [Fact]
    public void ATickIsNothing() => Assert.Equal(0u, Seam().Bridge.Perform(0x0003, []));

    /// <summary>A word of memory, at an address the calls also use.</summary>
    private static uint Word(Bridge bridge, uint at) => bridge.Memory.ReadWord((int)at);

    /// <summary>A byte of memory, likewise.</summary>
    private static int Byte(Bridge bridge, uint at) => bridge.Memory.ReadByte((int)at);

    /// <summary>Lay a word where a call will find it.</summary>
    private static void Poke(Bridge bridge, uint at, uint value) =>
        bridge.Memory.WriteWord((int)at, value);

    /// <summary>Lay an E0 string object in memory and answer its address.</summary>
    private static uint StringAt(Bridge bridge, string text)
    {
        const int At = 0x700;

        bridge.Memory.WriteByte(At, 0xE0);

        for (var index = 0; index < text.Length; index++)
        {
            bridge.Memory.WriteByte(At + 1 + index, text[index]);
        }

        bridge.Memory.WriteByte(At + 1 + text.Length, 0);

        return (uint)At;
    }

    private static (Bridge Bridge, Api Glk) Seam(GlkDisplay? display = null)
    {
        var story = new Story(new GlulxBuilder
        {
            RamStart = 0x100,
            ExtStart = 0x200,
            EndMem = 0x2000,
            StackSize = 0x400,
        }.Build());

        var glk = new Api(display);
        var bridge = new Bridge(new Memory(story), glk, new StackMemory(0x400));

        return (bridge, glk);
    }
}
