using System.Diagnostics;
using System.Text;

namespace Voxam.Core.Glulx.Glk;

/// <summary>
/// How a painted display dresses a run: the three attributes every one
/// of them can manage.
/// </summary>
/// <param name="Bold">Whether the run is heavy.</param>
/// <param name="Italic">Whether it slants.</param>
/// <param name="Reverse">Whether ink and paper swap.</param>
public readonly record struct Attributes(bool Bold, bool Italic, bool Reverse);

/// <summary>
/// A repeating deadline, for a display that waits with one.
///
/// Glk timers fire every so many milliseconds while the game is blocked
/// in glk_select (Glk: Timer Events). A display that can wait on the
/// keyboard with a timeout wants exactly this bookkeeping.
/// </summary>
public sealed class Deadline
{
    private readonly Stopwatch _clock = Stopwatch.StartNew();

    private double _interval;
    private double? _due;

    /// <summary>Start firing every so many milliseconds; zero stops.</summary>
    /// <param name="millisecs">The cadence, or zero to stop.</param>
    public void Set(int millisecs)
    {
        _interval = millisecs / 1000.0;
        _due = millisecs <= 0 ? null : Now + _interval;
    }

    /// <summary>How long a wait may block, or null for indefinitely.</summary>
    public double? Timeout() => _due is { } due ? Math.Max(0, due - Now) : null;

    /// <summary>Whether the timer has come round; rearms it if so.</summary>
    public bool Due()
    {
        if (_due is not { } due || Now < due)
        {
            return false;
        }

        _due = Now + _interval;

        return true;
    }

    private double Now => _clock.Elapsed.TotalSeconds;
}

/// <summary>
/// Paints the Glk window tree across a whole display.
///
/// A painted display, the blessed terminal or a window of its own,
/// keeps one shape: the window tree repaints whole on every flush,
/// grids from their cells and buffers from wrapped text with scrollback
/// and a pause prompt; input is collected synchronously at a keyboard
/// that echoes nothing, the half-typed line drawn as part of the
/// layout; and a timer coming round interrupts a wait by posting its
/// event and answering nothing, so glk_select can come back and deliver
/// it. All of that is display-independent and lives here. A display
/// itself supplies only its geometry, its way of placing a styled run
/// of cells, and its raw keystroke read: the four small methods at the
/// bottom of this class.
///
/// Redraw is unconditional and whole-screen. A partial-update scheme
/// would save work, but a Glulx game emits a paragraph at a time to
/// displays that redraw in microseconds, and the simplicity is worth
/// more than the savings. Every window paints its own bounding box
/// padded to its full width, and the boxes partition the screen between
/// them, so painting over is all the erasing there is.
///
/// Sound is not here. The reference plays it through the same speaker
/// its Z-Machine painted displays own, and this port has no speaker
/// yet, so a painted display claims no sound and Glk refuses the
/// channels honestly (Glk: Testing for Sound Capabilities).
/// </summary>
public abstract class PaintedDisplay : GlkDisplay
{
    /// <summary>What a windowful of unread text is announced with.</summary>
    public const string MorePrompt = "[MORE]";

    /// <summary>The room a display falls back to when it cannot measure.</summary>
    public const int FallbackColumns = 80;

    /// <summary>And the lines of it.</summary>
    public const int FallbackLines = 24;

    // Glk styles as the three attributes every painted display can
    // dress a run in. Anything absent renders plain; Preformatted
    // deliberately so, since the painted displays are monospaced
    // already.
    private static readonly Dictionary<uint, Attributes> Dressings = new()
    {
        [TextStyle.Emphasized] = new Attributes(false, true, false),
        [TextStyle.Header] = new Attributes(true, false, false),
        [TextStyle.Subheader] = new Attributes(true, false, false),
        [TextStyle.Alert] = new Attributes(true, false, true),
        [TextStyle.Note] = new Attributes(false, true, false),
        [TextStyle.BlockQuote] = new Attributes(false, true, false),
        [TextStyle.Input] = new Attributes(true, false, false),
        [TextStyle.User1] = new Attributes(false, true, false),
        [TextStyle.User2] = new Attributes(false, false, true),
    };

    // The stylehint numbers glk_style_measure asks in (Glk: Suggesting
    // the Appearance of Styles).
    private const uint HintIndentation = 0;
    private const uint HintParaIndentation = 1;
    private const uint HintSize = 3;
    private const uint HintWeight = 4;
    private const uint HintOblique = 5;
    private const uint HintProportional = 6;

    private const uint PrintableFloor = 0x20;
    private const uint CharacterCeiling = 0x10FFFF;

    // Each buffer window's kept text, keyed by the window itself rather
    // than its id, so a window closed and another opened cannot inherit
    // the first one's text through a reused address.
    private readonly Dictionary<TextBufferWindow, Wrapper> _buffers = [];

    private readonly Action<string, uint>? _onLine;
    private readonly Action<uint>? _onKey;

    private Window? _root;

    // The line being typed, and where it is being typed.
    private string _typed = "";
    private Window? _typing;

    /// <summary>Start with an empty tree and a stopped timer.</summary>
    /// <param name="onLine">
    /// Told every finished line with its terminator keycode, zero for
    /// Return, file-prompt answers included. A recording rides this
    /// seam; the display itself neither knows nor cares.
    /// </param>
    /// <param name="onKey">Told every keystroke a character read delivered.</param>
    protected PaintedDisplay(
        Action<string, uint>? onLine = null, Action<uint>? onKey = null)
    {
        _onLine = onLine;
        _onKey = onKey;
    }

    /// <summary>
    /// Every painted display reads a key with a timeout, so timers can
    /// fire.
    /// </summary>
    public override bool TimerInput => true;

    /// <summary>The repeating deadline a wait is cut short by.</summary>
    public Deadline Timer { get; } = new();

    /// <summary>How a style is dressed here, or plain for one that is not.</summary>
    /// <param name="style">The Glk style number.</param>
    public static Attributes Dressing(uint style) =>
        Dressings.TryGetValue(style, out var found) ? found : default;

    /// <summary>
    /// Collapse a grid row's per-cell dress into runs.
    ///
    /// The key carries the style and the link value together, so a
    /// linked run stays distinct from its plain neighbours all the way
    /// to the display (Glk: Hyperlinks).
    /// </summary>
    /// <param name="row">The row's characters.</param>
    /// <param name="styles">The style of each cell.</param>
    /// <param name="links">The link value of each cell.</param>
    public static List<Segment> Grouped(
        IReadOnlyList<string> row, IReadOnlyList<uint> styles, IReadOnlyList<uint> links)
    {
        ArgumentNullException.ThrowIfNull(row);
        ArgumentNullException.ThrowIfNull(styles);
        ArgumentNullException.ThrowIfNull(links);

        var segments = new List<Segment>();

        for (var at = 0; at < row.Count; at++)
        {
            var key = new Dress(
                at < styles.Count ? styles[at] : TextStyle.Normal,
                at < links.Count ? links[at] : 0);

            if (segments.Count > 0 && segments[^1].Key == key)
            {
                segments[^1] = new Segment(key, segments[^1].Text + row[at]);
            }
            else
            {
                segments.Add(new Segment(key, row[at]));
            }
        }

        return segments;
    }

    /// <summary>
    /// Paint every row blank, wiping what the shell left.
    ///
    /// Positions here and throughout the painting walk are in display
    /// units, cells at a terminal and pixels at a window, with the
    /// metrics converting the character counts, so the one walk serves
    /// both.
    /// </summary>
    public void Clear()
    {
        var (width, height) = Size();
        var cell = Metrics;
        var columns = (int)(width / cell.Width);
        var rows = (int)(height / cell.Height);

        Begin();

        for (var row = 0; row < rows; row++)
        {
            Place(0, (int)(row * cell.Height), [Blank(columns)]);
        }

        Finish(null);
    }

    /// <summary>Repaint the whole display from the window tree.</summary>
    /// <param name="root">The root of the window tree, or null.</param>
    public override void Flush(Window? root)
    {
        _root = root;

        if (root is null)
        {
            return;
        }

        Begin();
        Finish(Paint(root));
    }

    /// <summary>
    /// Leave the display ready for the shell's next prompt. A display
    /// drawing on the terminal parks the cursor under the story; a
    /// display in its own window has nothing to yield and inherits this
    /// quiet default.
    /// </summary>
    public virtual void Retire()
    {
        // A window of one's own leaves nothing behind.
    }

    /// <summary>Ask for timer events every so often; zero stops them.</summary>
    /// <param name="millisecs">The cadence, or zero.</param>
    public override void SetTimer(int millisecs) => Timer.Set(millisecs);

    /// <summary>Collect a line at the keyboard, drawn as it is typed.</summary>
    /// <param name="window">The window waiting on the line.</param>
    /// <param name="maxlen">How many characters its buffer holds.</param>
    public override (string Text, uint Terminator)? ReadLine(Window window, int maxlen)
    {
        ArgumentNullException.ThrowIfNull(window);

        var terminators = window.LineRequest?.Terminators ?? [];

        _typing = window;

        // The flush that preceded this did not know where input was
        // going, so repaint once to put the cursor at the prompt.
        Repaint();

        while (true)
        {
            if (Key() is not { } code)
            {
                // A timer fired mid-line. The half-typed line stays
                // where it is and the request stays pending; glk_select
                // will be back for it once it has delivered the event.
                return null;
            }

            if (code == KeyCode.Return)
            {
                return Accept(maxlen, 0);
            }

            if (terminators.Contains(code))
            {
                return Accept(maxlen, code);
            }

            Edit(code, maxlen);
            Repaint();
        }
    }

    /// <summary>One keystroke, as a Glk character code.</summary>
    /// <param name="window">The window waiting on the key.</param>
    public override uint? ReadChar(Window window)
    {
        var code = Key();

        if (code is { } pressed)
        {
            _onKey?.Invoke(pressed);
        }

        return code;
    }

    /// <summary>Ask for a filename on the bottom line of the display.</summary>
    /// <param name="usage">What the file is for, which the ask ignores.</param>
    /// <param name="fmode">How the game means to open it.</param>
    public override string? PromptFile(uint usage, uint fmode)
    {
        var prompt = (fmode == GlkFileMode.Read ? "Load from" : "Save to") + " which file? ";
        var (width, height) = Size();
        var cell = Metrics;
        var columns = (int)(width / cell.Width);
        var bottom = (int)(((int)(height / cell.Height) - 1) * cell.Height);

        // glkterm forces every window to the end before a prompt like
        // this one, so the player is answering a question rather than
        // fighting a pager for the keyboard.
        CatchUp();

        var saved = _typed;
        var savedWindow = _typing;

        _typed = "";
        _typing = null;

        try
        {
            while (true)
            {
                var text = Cut(_typed, Math.Max(0, columns - prompt.Length - 1));
                var line = (prompt + text).PadRight(columns - 1);

                Begin();
                Place(0, bottom, [new Segment(new Dress(TextStyle.Normal, 0), line)]);
                Finish(((int)((prompt.Length + text.Length) * cell.Width), bottom));

                if (Key() is not { } code)
                {
                    // A timer during a file prompt is not an event.
                    continue;
                }

                if (code == KeyCode.Return)
                {
                    var name = _typed.Trim();

                    return Answered(name.Length == 0 ? null : name);
                }

                if (code == KeyCode.Escape)
                {
                    return Answered(null);
                }

                Edit(code, columns);
            }
        }
        finally
        {
            _typed = saved;
            _typing = savedWindow;

            Repaint();
        }
    }

    /// <summary>Two styles differ here when their dress differs.</summary>
    /// <param name="window">The window the styles would appear in.</param>
    /// <param name="first">One style.</param>
    /// <param name="second">The other.</param>
    public override bool StyleDistinguish(Window window, uint first, uint second) =>
        Dressing(first) != Dressing(second);

    /// <summary>
    /// Measure a style hint. A character cell is the only unit.
    /// </summary>
    /// <param name="window">The window the style would appear in.</param>
    /// <param name="style">Which style to measure.</param>
    /// <param name="hint">Which attribute of it.</param>
    public override uint? StyleMeasure(Window window, uint style, uint hint)
    {
        var dress = Dressing(style);

        return hint switch
        {
            // Relative to the normal size, which is the only size.
            HintSize => 0,
            HintWeight => dress.Bold ? 1u : 0,
            HintOblique => dress.Italic ? 1u : 0,
            // The painted displays are monospaced throughout.
            HintProportional => 0,
            HintIndentation or HintParaIndentation => 0,
            _ => null,
        };
    }

    /// <summary>Start one frame of painting.</summary>
    protected abstract void Begin();

    /// <summary>
    /// Put a styled run of cells at a display position. The position is
    /// zero-based display units, x across and y down: the same units the
    /// window tree's bounding boxes are measured in.
    /// </summary>
    /// <param name="x">Where across the display.</param>
    /// <param name="y">Where down it.</param>
    /// <param name="line">The styled run to place.</param>
    protected abstract void Place(int x, int y, IReadOnlyList<Segment> line);

    /// <summary>End the frame, with the cursor shown at a cell or not.</summary>
    /// <param name="cursor">Where the cursor belongs, or null for nowhere.</param>
    protected abstract void Finish((int X, int Y)? cursor);

    /// <summary>
    /// One raw read as a Glk code; null for nothing usable. Nothing
    /// usable covers an expired timeout as well as any keystroke the
    /// display cannot spell as a Glk character code.
    /// </summary>
    /// <param name="timeout">How long to wait, or null for as long as it takes.</param>
    protected abstract uint? Translated(double? timeout);

    /// <summary>A run of blanks, in the plain dress.</summary>
    private static Segment Blank(int columns) =>
        new(new Dress(TextStyle.Normal, 0), new string(' ', Math.Max(0, columns)));

    /// <summary>The first so many characters of a line, counted as Glk counts them.</summary>
    private static string Cut(string text, int characters)
    {
        var kept = new StringBuilder();
        var counted = 0;

        foreach (var rune in text.EnumerateRunes())
        {
            if (counted >= characters)
            {
                break;
            }

            kept.Append(rune);
            counted++;
        }

        return kept.ToString();
    }

    /// <summary>How many characters a line holds, as Glk counts them.</summary>
    private static int Measured(string text)
    {
        var counted = 0;

        foreach (var _ in text.EnumerateRunes())
        {
            counted++;
        }

        return counted;
    }

    /// <summary>Draw a window and its children; say where the cursor goes.</summary>
    private (int X, int Y)? Paint(Window window)
    {
        switch (window)
        {
            case PairWindow pair:
                {
                    var first = Paint(pair.Child1);

                    return Paint(pair.Child2) ?? first;
                }

            case TextGridWindow grid:
                return PaintGrid(grid);

            case TextBufferWindow buffer:
                return PaintBuffer(buffer);

            case GraphicsWindow canvas:
                PaintGraphics(canvas);

                return null;

            default:
                {
                    // A blank window shows blankness (Glk: Blank
                    // Windows), and so does anything else without text
                    // to paint. The box is measured directly: a sizeless
                    // window answers the game zero, but its box is still
                    // real and still needs covering.
                    var (left, top, right, bottom) = window.BBox;
                    var cell = window.Metrics;
                    var columns = (int)((right - left) / cell.Width);
                    var rows = (int)((bottom - top) / cell.Height);

                    for (var index = 0; index < rows; index++)
                    {
                        Place(left, (int)(top + (index * cell.Height)), [Blank(columns)]);
                    }

                    return null;
                }
        }
    }

    /// <summary>
    /// Honor a pending clear; otherwise leave the canvas alone.
    ///
    /// Painting over is all the erasing there is for text, but a
    /// graphics window's pixels are the game's own work: they persist on
    /// the display until the game draws again, so the repaint must not
    /// cover them. A pending clear erases the whole canvas to its
    /// background (Glk: Graphics Windows).
    /// </summary>
    private void PaintGraphics(GraphicsWindow window)
    {
        if (!window.PendingClear)
        {
            return;
        }

        EraseRect(window, 0, 0, (uint)window.Width, (uint)window.Height);

        window.PendingClear = false;
    }

    private (int X, int Y)? PaintGrid(TextGridWindow window)
    {
        var (left, top, _, _) = window.BBox;
        var cell = window.Metrics;

        // The grid's rows are already exactly its size: the model
        // resizes them with every rearrange.
        for (var index = 0; index < window.Lines.Count; index++)
        {
            Place(
                left,
                (int)(top + (index * cell.Height)),
                Grouped(window.Lines[index], window.Styles[index], window.Links[index]));
        }

        if (!ReferenceEquals(_typing, window))
        {
            return null;
        }

        // A grid window taking line input shows it at the cursor, where
        // the game left it: there is nowhere else it could sensibly go.
        var column = Math.Min(window.CursorX, Math.Max(0, window.Width - 1));
        var row = Math.Min(window.CursorY, Math.Max(0, window.Height - 1));
        var text = Cut(_typed, Math.Max(0, window.Width - column));
        var x = (int)(left + (column * cell.Width));
        var y = (int)(top + (row * cell.Height));

        Place(x, y, [new Segment(new Dress(TextStyle.Input, 0), text)]);

        return ((int)(x + (Measured(text) * cell.Width)), y);
    }

    private (int X, int Y)? PaintBuffer(TextBufferWindow window)
    {
        var wrapper = WrapperFor(window);

        // The wrapper keys runs by style and link together, so a linked
        // run survives wrapping distinct from its plain neighbours. Text
        // alone: a display that claims no buffer images never has a
        // placed picture to meet here.
        wrapper.Add(window.TakeContent().OfType<Run>()
            .Select(run => new Segment(new Dress(run.Style, run.Hyperlink), run.Text)));

        var (left, top, _, _) = window.BBox;
        var height = window.Height;

        if (height <= 0)
        {
            // A buffer squeezed flat by a split still keeps its text;
            // there is just nowhere to paint it.
            return null;
        }

        var shown = wrapper.Show(height);
        var visible = shown.Lines;
        var typing = ReferenceEquals(_typing, window) && !shown.More;

        if (typing)
        {
            // The line being typed belongs at the end of the text, but
            // is not part of it until the game accepts it.
            var previewed = wrapper.Preview(
                [new Segment(new Dress(TextStyle.Input, 0), _typed)]);

            visible = previewed.Skip(Math.Max(0, previewed.Count - height)).ToList();
        }

        // The newest line sits at the bottom of the box, so the display
        // scrolls the way a terminal does rather than filling downwards.
        var offset = height - visible.Count - (shown.More ? 1 : 0);
        var cell = window.Metrics;
        var bottom = (int)(top + ((height - 1) * cell.Height));

        for (var index = 0; index < height; index++)
        {
            var at = index - offset;
            var line = at >= 0 && at < visible.Count ? visible[at] : [];
            var pad = Math.Max(0, window.Width - Measured(Wrapper.Plain(line)));

            Place(left, (int)(top + (index * cell.Height)), [.. line, Blank(pad)]);
        }

        if (shown.More)
        {
            Place(
                left,
                bottom,
                [
                    new Segment(new Dress(TextStyle.Alert, 0), MorePrompt),
                    Blank(window.Width - MorePrompt.Length),
                ]);

            return ((int)(left + (MorePrompt.Length * cell.Width)), bottom);
        }

        if (!typing || visible.Count == 0)
        {
            return null;
        }

        return ((int)(left + (Measured(Wrapper.Plain(visible[^1])) * cell.Width)), bottom);
    }

    /// <summary>The kept text for a window, made current with its size.</summary>
    private Wrapper WrapperFor(TextBufferWindow window)
    {
        if (_buffers.TryGetValue(window, out var wrapper))
        {
            wrapper.Resize(window.Width == 0 ? FallbackColumns : window.Width);
        }
        else
        {
            wrapper = new Wrapper(window.Width == 0 ? FallbackColumns : window.Width);
            _buffers[window] = wrapper;
        }

        if (window.PendingClear)
        {
            wrapper.Clear();
            window.PendingClear = false;
        }

        return wrapper;
    }

    private (string Text, uint Terminator) Accept(int maxlen, uint terminator)
    {
        var text = Cut(_typed, maxlen);

        _typed = "";
        _typing = null;

        _onLine?.Invoke(text, terminator);

        return (text, terminator);
    }

    /// <summary>Apply one keystroke to the line being typed.</summary>
    private void Edit(uint code, int maxlen)
    {
        if (code == KeyCode.Delete)
        {
            _typed = _typed.Length == 0
                ? _typed
                : Cut(_typed, Math.Max(0, Measured(_typed) - 1));
        }
        else if (code == KeyCode.Escape)
        {
            _typed = "";
        }
        else if (code >= PrintableFloor && code <= CharacterCeiling
            && Measured(_typed) < maxlen)
        {
            _typed += new Rune(code).ToString();
        }
    }

    /// <summary>
    /// Wait for a keystroke; null if something else came up.
    ///
    /// A key pressed while text is waiting turns the page instead of
    /// reaching the game, which is the whole point of the pause, and why
    /// every input path goes through here. The something else is a timer
    /// coming round, which posts its event and answers nothing so that
    /// glk_select can come back and deliver it.
    /// </summary>
    private uint? Key()
    {
        while (true)
        {
            if (Translated(Timer.Timeout()) is { } code)
            {
                if (TurnPage())
                {
                    continue;
                }

                return code;
            }

            if (Library is Api library && library.PendingEvents.Count > 0)
            {
                // The wait heard something that was not a keystroke, a
                // click the display posted, say, and glk_select must
                // come back round to deliver it, exactly as it does for
                // a timer.
                return null;
            }

            if (Timer.Due())
            {
                Post(new GlkEvent(EventType.Timer));

                return null;
            }
        }
    }

    /// <summary>Show the next page of every waiting window; did any wait?</summary>
    private bool TurnPage()
    {
        var waiting = _buffers
            .Where(each => each.Value.Show(each.Key.Height).More)
            .ToList();

        foreach (var (window, wrapper) in waiting)
        {
            wrapper.Advance(window.Height);
        }

        if (waiting.Count > 0)
        {
            Repaint();
        }

        return waiting.Count > 0;
    }

    /// <summary>Treat every window as read, so nothing is waiting.</summary>
    private void CatchUp()
    {
        foreach (var wrapper in _buffers.Values)
        {
            wrapper.CatchUp();
        }
    }

    /// <summary>Redraw after a keystroke, so typing is visible.</summary>
    private void Repaint()
    {
        if (_root is not null)
        {
            Flush(_root);
        }
    }

    /// <summary>
    /// Pass a file-prompt answer through the line seam, which hears what
    /// a replay must feed the prompt: the name, or the empty line that
    /// cancels.
    /// </summary>
    private string? Answered(string? name)
    {
        _onLine?.Invoke(name ?? "", 0);

        return name;
    }
}
