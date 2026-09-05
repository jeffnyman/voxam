namespace Voxam.Core.Glulx.Glk;

/// <summary>
/// A window Glk can paint on, measured in its real pixels.
///
/// The seam is the Version 6 stage's own, widened by the three things
/// Glk needs and the stage does not: the true colours a game names, the
/// ink and paper the window is dressed in, and where the player
/// clicked. The glass on the other side is the same one the Z-Machine
/// plays on, so a test drives the whole display with a stub and no
/// window ever opens.
/// </summary>
public interface IGlkGlass : IStageScreen
{
    /// <summary>The window's own ink, as 0x00RRGGBB.</summary>
    uint Ink { get; }

    /// <summary>And its paper.</summary>
    uint Paper { get; }

    /// <summary>
    /// Where the player last clicked, in zero-based pixels, or null
    /// where nothing is waiting. Reading it spends it.
    /// </summary>
    (int X, int Y)? Click();
}

/// <summary>
/// A windowed display for Glk: the glass speaks Glulx.
///
/// The painted spine, the tree walk and the wrappers and the pager and
/// the line editor and the timer, lives above; this display supplies
/// the window specifics. Its unit is the real pixel: the window tree is
/// arranged over the glass's pixel grid, the metrics carry the font
/// cell so a text window still answers its size in characters, and a
/// graphics window's size is honestly its box (Glk: Graphics Windows).
///
/// The graphics claim is true here. Canvases open, fill and erase in
/// their own pixels, and persist between repaints, because their pixels
/// are the game's work and painting over is only text's way of erasing.
/// And the mouse is claimed: a click lands in whichever armed grid or
/// canvas it hit, translated to that window's own units and posted as
/// the event glk_select delivers, while a click nothing asked for is
/// swallowed, as every interpreter swallows it.
///
/// The window echoes nothing on its own: Glk does the echoing into the
/// window once a line is accepted, and until then the half-typed line
/// is drawn by the spine, with a block caret painted where the next
/// character will land, a window having no hardware cursor to park the
/// way a terminal does.
/// </summary>
public sealed class GlassDisplay : PaintedDisplay
{
    /// <summary>
    /// The ink a hyperlink wears: the blue every reader already knows
    /// means "click here". The glass carries no underline, so color
    /// alone is the dress.
    /// </summary>
    public const uint LinkInk = 0x0066CC;

    // A fresh canvas's background, until the game chooses another: "The
    // initial background color of each window is white" (Glk: Graphics
    // in Graphics Windows).
    private const uint White = 0xFFFFFF;

    // The characters a click travels as in the Z-Machine's own eyes,
    // single and double alike. Glk knows only clicks, so a fast pair at
    // the window is simply two mouse events (Glk: Mouse Input Events).
    private const char Clicked = '\u00FE';
    private const char DoubleClicked = '\u00FD';

    // The keys the glass spells for itself, as the Glk keycodes they
    // mean (Glk: Character Input): one alphabet shared with the
    // Z-Machine's key seam, so one recorded press means the same on
    // either machine.
    private static readonly Dictionary<char, uint> Keycodes = new()
    {
        ['\n'] = KeyCode.Return,
        ['\u007F'] = KeyCode.Delete,
        ['\u001B'] = KeyCode.Escape,
        ['\u0081'] = KeyCode.Up,
        ['\u0082'] = KeyCode.Down,
        ['\u0083'] = KeyCode.Left,
        ['\u0084'] = KeyCode.Right,
        ['\u0085'] = KeyCode.Func1,
        ['\u0086'] = KeyCode.Func2,
        ['\u0087'] = KeyCode.Func3,
        ['\u0088'] = KeyCode.Func4,
        ['\u0089'] = KeyCode.Func5,
        ['\u008A'] = KeyCode.Func6,
        ['\u008B'] = KeyCode.Func7,
        ['\u008C'] = KeyCode.Func8,
        ['\u008D'] = KeyCode.Func9,
        ['\u008E'] = KeyCode.Func10,
        ['\u008F'] = KeyCode.Func11,
        ['\u0090'] = KeyCode.Func12,
    };

    private readonly IGlkGlass _glass;

    // Each canvas's background color, once a game chooses one (Glk:
    // Graphics in Graphics Windows).
    private readonly Dictionary<Window, uint> _backgrounds = [];

    // Where each linked run stands on the glass this frame, in
    // zero-based pixels, rebuilt with every repaint: what turns a click
    // into a selection.
    private readonly List<(int Left, int Top, int Right, int Bottom, uint Value)> _links = [];

    private readonly List<Paint> _pending = [];
    private readonly Action<int, int>? _onClick;
    private readonly Action<uint>? _onLink;

    private bool _framing;

    /// <summary>Stand over a glass.</summary>
    /// <param name="glass">The window to paint on.</param>
    /// <param name="onLine">Told every finished line and its terminator.</param>
    /// <param name="onKey">Told every keystroke a character read delivered.</param>
    /// <param name="onClick">
    /// Told each delivered click as the window-relative coordinates the
    /// game itself was told.
    /// </param>
    /// <param name="onLink">
    /// Told each delivered selection as the link value the game itself
    /// was told.
    /// </param>
    public GlassDisplay(
        IGlkGlass glass,
        Action<string, uint>? onLine = null,
        Action<uint>? onKey = null,
        Action<int, int>? onClick = null,
        Action<uint>? onLink = null)
        : base(onLine, onKey)
    {
        _glass = glass;
        _onClick = onClick;
        _onLink = onLink;
    }

    /// <summary>
    /// A real window draws in real pixels, so canvases open (Glk:
    /// Graphics Windows).
    /// </summary>
    public override bool Graphics => true;

    /// <summary>
    /// A real window has a real pointer, so grids and canvases can carry
    /// a click (Glk: Mouse Input Events).
    /// </summary>
    public override bool MouseInput => true;

    /// <summary>
    /// And the pointer selects links: a click on a linked run in an
    /// armed text window delivers its value (Glk: Accepting Hyperlink
    /// Events).
    /// </summary>
    public override bool HyperlinkInput => true;

    /// <summary>
    /// The font cell in real pixels: what lets a text window answer its
    /// size in characters while the tree is arranged over the pixel
    /// grid.
    /// </summary>
    public override Metrics Metrics => new(_glass.FontWidth, _glass.FontHeight);

    /// <summary>The whole glass, measured in its real pixels.</summary>
    public override (int Width, int Height) Size() =>
        (_glass.Columns * _glass.FontWidth, _glass.Lines * _glass.FontHeight);

    /// <summary>Remember the color; only future clears and erases wear it.</summary>
    /// <param name="window">The window whose background it is.</param>
    /// <param name="color">The color to clear to.</param>
    public override void SetBackgroundColor(Window window, uint color) =>
        _backgrounds[window] = color;

    /// <summary>Erase a rectangle to the canvas's background color.</summary>
    /// <param name="window">The window to erase in.</param>
    /// <param name="left">The rectangle's left edge.</param>
    /// <param name="top">Its top edge.</param>
    /// <param name="width">Its width.</param>
    /// <param name="height">Its height.</param>
    public override void EraseRect(Window window, int left, int top, uint width, uint height) =>
        Fill(window, left, top, (int)width, (int)height, Background(window));

    /// <summary>Fill a rectangle with a color of the game's own.</summary>
    /// <param name="window">The window to fill in.</param>
    /// <param name="color">The color to fill with.</param>
    /// <param name="left">The rectangle's left edge.</param>
    /// <param name="top">Its top edge.</param>
    /// <param name="width">Its width.</param>
    /// <param name="height">Its height.</param>
    public override void FillRect(
        Window window, uint color, int left, int top, uint width, uint height)
    {
        Settled(window);
        Fill(window, left, top, (int)width, (int)height, color);
    }

    /// <summary>
    /// Draw a picture onto a canvas, scaled and clipped.
    ///
    /// Only graphics windows draw here, as the gestalt already told the
    /// game (Glk: Testing for Graphics Capabilities). The bytes are the
    /// Blorb's own and the glass decodes them, which is one decoder for
    /// both kinds rather than two. The corner is in window pixels and
    /// signed, and "it is legitimate for part of the image to fall
    /// outside the window; the excess is not drawn" (Glk: Graphics in
    /// Graphics Windows).
    /// </summary>
    /// <param name="window">The window to draw in.</param>
    /// <param name="image">The picture, measured.</param>
    /// <param name="val1">Where across the window.</param>
    /// <param name="val2">Where down it.</param>
    /// <param name="width">How wide to draw it.</param>
    /// <param name="height">How tall.</param>
    public override bool DrawImage(
        Window window, ImageInfo image, int val1, int val2, uint width, uint height)
    {
        ArgumentNullException.ThrowIfNull(window);
        ArgumentNullException.ThrowIfNull(image);

        if (window is not GraphicsWindow canvas)
        {
            return false;
        }

        Settled(canvas);

        if (width == 0 || height == 0)
        {
            // Scaled to nothing is drawn as nothing.
            return true;
        }

        var (boxLeft, boxTop, boxRight, boxBottom) = canvas.BBox;
        var left = boxLeft + val1;
        var top = boxTop + val2;
        var x0 = Math.Max(left, boxLeft);
        var y0 = Math.Max(top, boxTop);
        var x1 = Math.Min(left + (int)width, boxRight);
        var y1 = Math.Min(top + (int)height, boxBottom);

        if (x1 <= x0 || y1 <= y0)
        {
            // Fully off the canvas: legitimate, and nothing shows.
            return true;
        }

        // The overhang is cut away by naming the part of the picture
        // that lands inside the box, in the picture's own pixels, and
        // drawing only that.
        Lay(new ClipPaint(
            y0 + 1,
            x0 + 1,
            y1 - y0,
            x1 - x0,
            (x0 - left) * image.Width / (int)width,
            (y0 - top) * image.Height / (int)height,
            Math.Max(1, (x1 - x0) * image.Width / (int)width),
            Math.Max(1, (y1 - y0) * image.Height / (int)height),
            image.Data));

        return true;
    }

    /// <summary>
    /// Wait at the glass; the click itself travels as an event.
    ///
    /// The click is posted with its window and coordinates already
    /// resolved, so this wait only blocks until something happens: a
    /// posted click or a timer answers nothing, and glk_select comes
    /// back round to find the event. A keystroke while only the mouse is
    /// wanted means nothing, and the wait resumes.
    /// </summary>
    /// <param name="window">The window waiting on a click.</param>
    public override (int X, int Y)? ReadMouse(Window window)
    {
        Await();

        return null;
    }

    /// <summary>
    /// Wait at the glass; the selection travels as an event, resolved
    /// off the painted link map exactly as a click is.
    /// </summary>
    /// <param name="window">The window waiting on a link.</param>
    public override uint? ReadHyperlink(Window window)
    {
        Await();

        return null;
    }

    /// <summary>Start a frame: the link map is repainted with the text.</summary>
    protected override void Begin()
    {
        _framing = true;

        _pending.Clear();
        _links.Clear();
    }

    /// <inheritdoc/>
    protected override void Place(int x, int y, IReadOnlyList<Segment> line)
    {
        ArgumentNullException.ThrowIfNull(line);

        var column = x;

        foreach (var (key, text) in line)
        {
            if (text.Length == 0)
            {
                continue;
            }

            var dress = Dressing(key.Style);
            var (ink, paper) = dress.Reverse
                ? (_glass.Paper, _glass.Ink)
                : (key.Link != 0 ? LinkInk : _glass.Ink, _glass.Paper);

            _pending.Add(new RunPaint(
                y + 1, column + 1, text, ink, paper, dress.Bold, dress.Italic));

            var width = Measured(text) * _glass.FontWidth;

            if (key.Link != 0)
            {
                _links.Add((column, y, column + width, y + _glass.FontHeight, key.Link));
            }

            column += width;
        }
    }

    /// <inheritdoc/>
    protected override void Finish((int X, int Y)? cursor)
    {
        if (cursor is { } at && at.X < Size().Width)
        {
            // The block caret: one filled cell where the next character
            // will land, since a window has no hardware cursor of its
            // own to park there.
            _pending.Add(new ColourPaint(
                at.Y + 1, at.X + 1, _glass.FontHeight, _glass.FontWidth, _glass.Ink));
        }

        _framing = false;

        _glass.Settle([.. _pending]);
        _pending.Clear();
    }

    /// <summary>
    /// One glass read as a Glk code; null for nothing usable.
    ///
    /// The glass answers in the Z-Machine's alphabet already: named keys
    /// as their code characters, ordinary typing as itself. A click is
    /// not a key at all, and is delivered to whichever armed window it
    /// hit before the wait comes back round.
    /// </summary>
    /// <param name="timeout">How long to wait, or null for as long as it takes.</param>
    protected override uint? Translated(double? timeout)
    {
        var key = _glass.ReadKey(timeout);

        if (key is null)
        {
            // The wait expired with nothing pressed.
            return null;
        }

        if (key.Length != 1)
        {
            // A press the glass cannot spell as one character.
            return null;
        }

        if (key[0] is Clicked or DoubleClicked)
        {
            Deliver();

            return null;
        }

        return Keycodes.TryGetValue(key[0], out var code) ? code : key[0];
    }

    /// <summary>How many characters a run holds, as Glk counts them.</summary>
    private static int Measured(string text)
    {
        var counted = 0;

        foreach (var _ in text.EnumerateRunes())
        {
            counted++;
        }

        return counted;
    }

    /// <summary>Whether a point lands inside a window's box.</summary>
    private static bool Inside(Window window, int x, int y)
    {
        var (left, top, right, bottom) = window.BBox;

        return x >= left && x < right && y >= top && y < bottom;
    }

    /// <summary>The canvas's background: white until the game says else.</summary>
    private uint Background(Window window) =>
        _backgrounds.TryGetValue(window, out var chosen) ? chosen : White;

    /// <summary>
    /// Consume a pending clear before new paint lands.
    ///
    /// glk_window_clear only raises the flag, and a repaint honors it
    /// later, but paint arriving in between must land on the cleared
    /// canvas rather than be erased under it, so the clear happens now.
    /// An erase needs no such care: it paints the same background the
    /// clear would.
    /// </summary>
    private void Settled(Window window)
    {
        if (!window.PendingClear)
        {
            return;
        }

        window.PendingClear = false;

        EraseRect(window, 0, 0, (uint)window.Width, (uint)window.Height);
    }

    /// <summary>
    /// Paint a window-relative rectangle, clipped to its box. "It is
    /// legitimate for part of the rectangle to fall outside the window"
    /// (Glk: Graphics in Graphics Windows), so whatever falls outside
    /// simply is not drawn, and the arguments are signed, so the
    /// overhang may be on any edge.
    /// </summary>
    private void Fill(Window window, int left, int top, int width, int height, uint colour)
    {
        var (boxLeft, boxTop, boxRight, boxBottom) = window.BBox;
        var x0 = Math.Max(boxLeft + left, boxLeft);
        var y0 = Math.Max(boxTop + top, boxTop);
        var x1 = Math.Min(boxLeft + left + width, boxRight);
        var y1 = Math.Min(boxTop + top + height, boxBottom);

        if (x1 <= x0 || y1 <= y0)
        {
            return;
        }

        Lay(new ColourPaint(y0 + 1, x0 + 1, y1 - y0, x1 - x0, colour));
    }

    /// <summary>
    /// Put a paint in the frame being gathered, or on the glass at once
    /// where no frame is open: a game's drawing arrives between
    /// repaints, and should show without waiting for one.
    /// </summary>
    private void Lay(Paint paint)
    {
        if (_framing)
        {
            _pending.Add(paint);

            return;
        }

        _glass.Settle([paint]);
    }

    /// <summary>
    /// Wait out keystrokes until an interruption ends the wait.
    ///
    /// The spine's own wait, so the pager and the timer keep working
    /// while only the pointer is wanted: a delivered click posts its
    /// event, and the very next look finds one queued and stops.
    /// </summary>
    private void Await()
    {
        while (Key() is not null)
        {
            // A key while only the pointer is wanted means nothing.
        }
    }

    /// <summary>
    /// Deliver the glass's click to whichever armed window it hit.
    ///
    /// A click on a linked run in a text window with a hyperlink request
    /// delivers the link's value (Glk: Accepting Hyperlink Events);
    /// otherwise a grid or a canvas with a mouse request hears the click
    /// in its own coordinates, cells in a grid and pixels on a canvas
    /// (Glk: Mouse Input Events). A click nothing asked for is
    /// swallowed, as every interpreter swallows it.
    /// </summary>
    private void Deliver()
    {
        if (_glass.Click() is not { } position || Library is not Api library)
        {
            return;
        }

        var (x, y) = position;

        foreach (var window in library.Windows)
        {
            if (!window.HyperlinkRequest
                || window is not (TextBufferWindow or TextGridWindow)
                || !Inside(window, x, y))
            {
                continue;
            }

            var value = LinkAt(x, y);

            if (value == 0)
            {
                continue;
            }

            window.HyperlinkRequest = false;

            Post(new GlkEvent(EventType.Hyperlink, window, value));
            _onLink?.Invoke(value);

            return;
        }

        foreach (var window in library.Windows)
        {
            if (!window.MouseRequest
                || window is not (TextGridWindow or GraphicsWindow)
                || !Inside(window, x, y))
            {
                continue;
            }

            var (left, top, _, _) = window.BBox;
            var cell = window.Metrics;
            var val1 = window is TextGridWindow ? (int)((x - left) / cell.Width) : x - left;
            var val2 = window is TextGridWindow ? (int)((y - top) / cell.Height) : y - top;

            window.MouseRequest = false;

            Post(new GlkEvent(EventType.MouseInput, window, (uint)val1, (uint)val2));
            _onClick?.Invoke(val1, val2);

            return;
        }
    }

    /// <summary>The link value painted at a pixel, or zero for none.</summary>
    private uint LinkAt(int x, int y)
    {
        foreach (var (left, top, right, bottom, value) in _links)
        {
            if (x >= left && x < right && y >= top && y < bottom)
            {
                return value;
            }
        }

        return 0;
    }
}
