namespace Voxam.Core.Glulx.Glk;

/// <summary>A rectangle in the display's own layout units.</summary>
/// <param name="Left">The left edge.</param>
/// <param name="Top">The top edge.</param>
/// <param name="Right">One past the right edge.</param>
/// <param name="Bottom">One past the bottom edge.</param>
public readonly record struct Box(int Left, int Top, int Right, int Bottom);

/// <summary>One item in a text buffer's flow.</summary>
public abstract class Content
{
    /// <summary>Only the three kinds below are ever built.</summary>
    protected Content()
    {
    }
}

/// <summary>A span of window text sharing one style and link value.</summary>
public sealed class Run : Content
{
    /// <summary>Open a run of text in one dress.</summary>
    /// <param name="style">The style the span is written in.</param>
    /// <param name="hyperlink">The link value it belongs to, or zero.</param>
    /// <param name="text">The characters themselves.</param>
    public Run(uint style, uint hyperlink, string text)
    {
        Style = style;
        Hyperlink = hyperlink;
        Text = text;
    }

    /// <summary>The style the span is written in.</summary>
    public uint Style { get; }

    /// <summary>The link value it belongs to, or zero.</summary>
    public uint Hyperlink { get; }

    /// <summary>The characters themselves.</summary>
    public string Text { get; }
}

/// <summary>
/// One picture set into a buffer's text flow.
///
/// What a display that lays text around pictures needs to lay this one:
/// the Pict's number, the picture whole as a data url, the size the
/// draw asked for, the imagealign value naming how the text meets it,
/// and the link value it was drawn under (Glk: Graphics in Text Buffer
/// Windows).
/// </summary>
public sealed class Placed : Content
{
    /// <summary>Set a picture into the flow.</summary>
    /// <param name="image">The picture's resource number.</param>
    /// <param name="url">The picture whole, as a data url.</param>
    /// <param name="width">The width the draw asked for.</param>
    /// <param name="height">The height the draw asked for.</param>
    /// <param name="alignment">How the text meets the picture.</param>
    /// <param name="hyperlink">The link value it was drawn under.</param>
    public Placed(
        uint image,
        string url,
        int width,
        int height,
        uint alignment,
        uint hyperlink)
    {
        Image = image;
        Url = url;
        Width = width;
        Height = height;
        Alignment = alignment;
        Hyperlink = hyperlink;
    }

    /// <summary>The picture's resource number.</summary>
    public uint Image { get; }

    /// <summary>The picture whole, as a data url.</summary>
    public string Url { get; }

    /// <summary>The width the draw asked for.</summary>
    public int Width { get; }

    /// <summary>The height the draw asked for.</summary>
    public int Height { get; }

    /// <summary>How the text meets the picture.</summary>
    public uint Alignment { get; }

    /// <summary>The link value it was drawn under.</summary>
    public uint Hyperlink { get; }
}

/// <summary>
/// A flow break in a buffer's text flow. Text past the break starts
/// below any margin images standing at the point of the break (Glk:
/// Graphics in Text Buffer Windows).
/// </summary>
public sealed class FlowBreak : Content;

/// <summary>A pending line request on a window (Glk: Line Input Events).</summary>
public sealed class LineRequest
{
    /// <summary>Record what the request asked for.</summary>
    /// <param name="buf">The buffer the line lands in, or null.</param>
    /// <param name="initlen">How many characters of it are pre-filled.</param>
    /// <param name="unicode">Whether the buffer holds words rather than bytes.</param>
    /// <param name="echo">Whether the finished line is echoed to the window.</param>
    public LineRequest(IBuffer? buf, int initlen = 0, bool unicode = false, bool echo = true)
    {
        Buffer = buf;
        InitLen = initlen;
        Unicode = unicode;
        Echo = echo;
    }

    /// <summary>The buffer the line lands in, or null.</summary>
    public IBuffer? Buffer { get; }

    /// <summary>How many characters of it are pre-filled.</summary>
    public int InitLen { get; }

    /// <summary>Whether the buffer holds words rather than bytes.</summary>
    public bool Unicode { get; }

    /// <summary>
    /// Whether the finished line is echoed to the window (Glk: Line
    /// Input Events, by way of set_echo_line_event).
    /// </summary>
    public bool Echo { get; set; }

    /// <summary>The special keys that may end the line.</summary>
    public IReadOnlyList<uint> Terminators { get; set; } = [];

    /// <summary>The buffer's length; zero for the null buffer.</summary>
    public int Capacity => Buffer?.Length ?? 0;
}

/// <summary>
/// What a text window costs in the display's own layout unit.
///
/// The window tree is arranged in display units. A terminal's unit is
/// the character cell, so its metrics are one by one and every
/// measurement is the same number either way. A graphical display lays
/// out in pixels and gives the size of its font's cell here, which is
/// what lets a text window report its size in characters while a
/// graphics window reports the pixels the specification says it must
/// (Glk: Graphics Windows).
///
/// The cell is a real number because a display may measure one. GlkOte
/// says so outright, "we can wind up with a non-integer charwidth
/// value", and rounding it either way is wrong in one direction or the
/// other: too small and a window claims more columns than fit, too
/// large and it wastes them. The counts that come out of it are whole
/// numbers; the cell itself need not be.
///
/// The margins are what a window spends on padding and borders, over
/// and above its characters. They are nothing on a terminal, which is
/// why they default so.
/// </summary>
/// <param name="Width">The width of one character cell.</param>
/// <param name="Height">The height of one character cell.</param>
/// <param name="MarginX">What the window spends horizontally.</param>
/// <param name="MarginY">What the window spends vertically.</param>
public readonly record struct Metrics(
    double Width = 1,
    double Height = 1,
    double MarginX = 0,
    double MarginY = 0)
{
    /// <summary>
    /// The metrics of a display whose unit is already the character.
    /// </summary>
    public static Metrics CharacterCell => new(1, 1);

    /// <summary>
    /// How many characters fit an extent, margin taken out. Rounded
    /// down, for the same reason the other direction rounds up: a
    /// window claiming a column it does not have room for spills over
    /// its own edge.
    /// </summary>
    /// <param name="extent">The room available, in display units.</param>
    /// <param name="cell">The size of one character.</param>
    /// <param name="margin">What the window spends around them.</param>
    internal static int Cells(int extent, double cell, double margin) =>
        cell > 0 ? Math.Max(0, (int)((extent - margin) / cell)) : 0;
}

/// <summary>
/// Base window. Subclasses differ in how they hold contents.
/// </summary>
public abstract class Window : GlkObject
{
    /// <summary>Open unattached, with nothing requested.</summary>
    /// <param name="rock">The value the game files the window under.</param>
    protected Window(uint rock = 0)
        : base(rock) => Stream = new StreamOnWindow(this);

    /// <inheritdoc/>
    public override int GlkClass => 0;

    /// <summary>Which type of window this is (Glk: The Types of Windows).</summary>
    public virtual uint WinType => WindowType.Blank;

    /// <summary>The pair window this hangs under, or null at the root.</summary>
    public PairWindow? Parent { get; set; }

    /// <summary>The window's own output stream.</summary>
    public StreamOnWindow Stream { get; }

    /// <summary>
    /// A stream that receives a copy of the window's output, or null
    /// (Glk: Echo Streams).
    /// </summary>
    public StreamObject? EchoStream { get; set; }

    /// <summary>The style new output is written in.</summary>
    public uint Style { get; set; } = TextStyle.Normal;

    /// <summary>The pending line request, or null.</summary>
    public LineRequest? LineRequest { get; set; }

    /// <summary>Whether character input is requested.</summary>
    public bool CharRequest { get; set; }

    /// <summary>Whether the character request wants full words.</summary>
    public bool CharUnicode { get; set; }

    /// <summary>Whether a hyperlink click is requested.</summary>
    public bool HyperlinkRequest { get; set; }

    /// <summary>Whether a mouse click is requested.</summary>
    public bool MouseRequest { get; set; }

    /// <summary>The display's cell measurements for this window.</summary>
    public Metrics Metrics { get; set; } = Glk.Metrics.CharacterCell;

    /// <summary>
    /// Set by clear, cleared by a display once it redraws. A window that
    /// keeps its own contents, a grid, erases them itself; one whose
    /// contents live in the display, a buffer's scrollback or a graphics
    /// window's pixels, can only ask.
    /// </summary>
    public bool PendingClear { get; set; }

    /// <summary>The window's box, in display units.</summary>
    public Box BBox { get; private set; }

    /// <summary>The window's width in its own units; here, display units.</summary>
    public virtual int Width => Math.Max(0, BBox.Right - BBox.Left);

    /// <summary>The window's height in its own units.</summary>
    public virtual int Height => Math.Max(0, BBox.Bottom - BBox.Top);

    /// <summary>
    /// Display units needed for a size in this window's units.
    ///
    /// A fixed split is expressed in the key window's measurement system
    /// (Glk: Window Opening, Closing, and Constraints), which for a
    /// graphics window means pixels and for a text window means
    /// characters plus whatever the display spends around them. The
    /// conversion lives here so that rule stays in one place.
    /// </summary>
    /// <param name="size">The size in this window's own units.</param>
    /// <param name="vertical">Whether the split divides left from right.</param>
    public virtual int Extent(int size, bool vertical) => size;

    /// <summary>
    /// Hold a character from this window's stream.
    ///
    /// The base discards, a blank window supports no output, but the
    /// copy to any echo stream happens for every type (Glk: Echo
    /// Streams).
    /// </summary>
    /// <param name="character">The character written.</param>
    public virtual void PutChar(uint character) => EchoStream?.PutChar(character);

    /// <summary>
    /// Erase the window's contents.
    ///
    /// A graphics window is filled with its background color, a blank
    /// window has nothing to erase (Glk: Graphics Windows). Both are the
    /// display's to do, so the base does no more than raise the flag.
    /// </summary>
    public virtual void Clear() => PendingClear = true;

    /// <summary>Take a new bounding box from the layout.</summary>
    /// <param name="box">The room the layout gave this window.</param>
    public virtual void Rearrange(Box box) => BBox = box;
}

/// <summary>
/// A window with no measurement system, and so no size.
///
/// glk_window_get_size "returns the actual size of the window, in its
/// measurement system" (Glk: Changing Window Constraints), and a blank
/// window has nothing in it, while a pair window is a split rather than
/// a place. The specification answers zero by zero for blank windows
/// outright (Glk: Blank Windows); glkapi.js reaches the same answer for
/// pairs by only assigning a size to the three types that have one.
///
/// The bounding box is still there and still correct; it is what a
/// display draws borders from. This is only what the game is told.
/// </summary>
public abstract class SizelessWindow : Window
{
    /// <summary>Open unattached, with nothing requested.</summary>
    /// <param name="rock">The value the game files the window under.</param>
    protected SizelessWindow(uint rock = 0)
        : base(rock)
    {
    }

    /// <summary>Always zero: no measurement system to answer in.</summary>
    public override int Width => 0;

    /// <summary>Always zero, as the width is.</summary>
    public override int Height => 0;
}

/// <summary>A window that is always blank (Glk: Blank Windows).</summary>
public sealed class BlankWindow : SizelessWindow
{
    /// <summary>Open blank.</summary>
    /// <param name="rock">The value the game files the window under.</param>
    public BlankWindow(uint rock = 0)
        : base(rock)
    {
    }
}

/// <summary>
/// A grid of pixels (Glk: Graphics Windows).
///
/// The pixels themselves live in the display; the model holds the box
/// and the requests, and its size is the box, because a graphics window
/// measures in pixels.
/// </summary>
public sealed class GraphicsWindow : Window
{
    /// <summary>
    /// Open asking to be cleared: a fresh canvas is background.
    ///
    /// The background color is initially white (Glk: Graphics Windows),
    /// and whatever the display holds where the canvas now hangs is
    /// someone else's leavings.
    /// </summary>
    /// <param name="rock">The value the game files the window under.</param>
    public GraphicsWindow(uint rock = 0)
        : base(rock) => PendingClear = true;

    /// <inheritdoc/>
    public override uint WinType => WindowType.Graphics;

    /// <summary>
    /// Raised by a rearrange that changed a real box. The display's
    /// pixels are absolute and do not travel with the box, so the canvas
    /// is cleared and the game is owed a redraw event for it (Glk:
    /// Window Events).
    /// </summary>
    public bool Moved { get; set; }

    /// <summary>
    /// Take a new box; a changed one loses the canvas.
    ///
    /// The specification allows a resized window's contents to be thrown
    /// away so long as the game hears a redraw event, "the window in
    /// question has been cleared to its background color, and must be
    /// redrawn" (Glk: Window Events). A fresh window whose old box was
    /// empty owes no such event: it opens as background and the game
    /// knows it.
    /// </summary>
    /// <param name="box">The room the layout gave this window.</param>
    public override void Rearrange(Box box)
    {
        if (box != BBox)
        {
            PendingClear = true;
            Moved = Moved || (Width > 0 && Height > 0);
        }

        base.Rearrange(box);
    }
}

/// <summary>
/// Shared by the two text window types: measured in characters.
///
/// A graphical display arranges in pixels, so a text window's own size
/// is that extent divided by the font's cell, which is the number the
/// game gets from glk_window_get_size and the number it lays its text
/// out against.
/// </summary>
public abstract class TextWindow : Window
{
    /// <summary>Open unattached, with nothing requested.</summary>
    /// <param name="rock">The value the game files the window under.</param>
    protected TextWindow(uint rock = 0)
        : base(rock)
    {
    }

    /// <summary>The width in characters, by way of the metrics.</summary>
    public override int Width =>
        Glk.Metrics.Cells(BBox.Right - BBox.Left, Metrics.Width, Metrics.MarginX);

    /// <summary>The height in characters, by way of the metrics.</summary>
    public override int Height =>
        Glk.Metrics.Cells(BBox.Bottom - BBox.Top, Metrics.Height, Metrics.MarginY);

    /// <summary>
    /// Room for a count of characters, margin included. Rounded up: a
    /// window a fraction of a pixel short would have its last line
    /// pushed out past its own border.
    /// </summary>
    /// <param name="size">The size in characters.</param>
    /// <param name="vertical">Whether the split divides left from right.</param>
    public override int Extent(int size, bool vertical)
    {
        var cell = vertical ? Metrics.Width : Metrics.Height;
        var margin = vertical ? Metrics.MarginX : Metrics.MarginY;

        return (int)Math.Ceiling((size * cell) + margin);
    }
}

/// <summary>
/// A scrolling text window (Glk: Text Buffer Windows).
///
/// Contents accumulate as runs of text sharing a style and a link
/// value, oldest first, with any pictures and flow breaks a claiming
/// display placed among them, in flow order, until a display drains
/// them.
/// </summary>
public sealed class TextBufferWindow : TextWindow
{
    private readonly List<Content> _content = [];

    /// <summary>Open empty.</summary>
    /// <param name="rock">The value the game files the window under.</param>
    public TextBufferWindow(uint rock = 0)
        : base(rock)
    {
    }

    /// <inheritdoc/>
    public override uint WinType => WindowType.TextBuffer;

    /// <summary>What has been written since the last drain, in flow order.</summary>
    public IReadOnlyList<Content> Content => _content;

    /// <summary>
    /// Append to the last run, or start a new one.
    ///
    /// A run continues only while both the style and the link value
    /// hold, and only across text: a placed picture or a flow break ends
    /// the run it follows.
    /// </summary>
    /// <param name="character">The character written.</param>
    public override void PutChar(uint character)
    {
        base.PutChar(character);

        var text = Characters.ToChar(character);
        var link = Stream.Hyperlink;

        if (_content.Count > 0
            && _content[^1] is Run last
            && last.Style == Style
            && last.Hyperlink == link)
        {
            _content[^1] = new Run(last.Style, last.Hyperlink, last.Text + text);
        }
        else
        {
            _content.Add(new Run(Style, link, text));
        }
    }

    /// <summary>
    /// Set a picture into the flow, after everything written so far.
    /// </summary>
    /// <param name="placed">The picture and how it is to sit.</param>
    public void PutPlaced(Placed placed) => _content.Add(placed);

    /// <summary>
    /// Set a flow break into the flow (Glk: Graphics in Text Buffer
    /// Windows).
    /// </summary>
    public void PutBreak() => _content.Add(new FlowBreak());

    /// <summary>The accumulated text, styles and pictures flattened away.</summary>
    public string Text() =>
        string.Concat(_content.OfType<Run>().Select(run => run.Text));

    /// <summary>Answer accumulated text and reset, for a display to render.</summary>
    public string TakeText()
    {
        var text = Text();

        _content.Clear();

        return text;
    }

    /// <summary>
    /// Answer accumulated flow and reset, keeping their styles. The same
    /// drain as TakeText, for a display that renders styles, and lays
    /// pictures, rather than flattening them.
    /// </summary>
    public IReadOnlyList<Content> TakeContent()
    {
        var taken = _content.ToArray();

        _content.Clear();

        return taken;
    }

    /// <summary>Erase the held runs along with raising the flag.</summary>
    public override void Clear()
    {
        base.Clear();

        _content.Clear();
    }
}

/// <summary>
/// A character grid with a cursor (Glk: Text Grid Windows).
///
/// The characters, their styles, and their link values are held as
/// parallel row lists, resized whenever the layout hands over a new box.
/// </summary>
public sealed class TextGridWindow : TextWindow
{
    private string[][] _lines = [];
    private uint[][] _styles = [];
    private uint[][] _links = [];

    /// <summary>Open with no rows; the first rearrange sizes the grid.</summary>
    /// <param name="rock">The value the game files the window under.</param>
    public TextGridWindow(uint rock = 0)
        : base(rock)
    {
    }

    /// <inheritdoc/>
    public override uint WinType => WindowType.TextGrid;

    /// <summary>The characters, one list per row.</summary>
    public IReadOnlyList<IReadOnlyList<string>> Lines => _lines;

    /// <summary>The styles, one list per row.</summary>
    public IReadOnlyList<IReadOnlyList<uint>> Styles => _styles;

    /// <summary>The link values, one list per row.</summary>
    public IReadOnlyList<IReadOnlyList<uint>> Links => _links;

    /// <summary>Where the next character lands, across.</summary>
    public int CursorX { get; private set; }

    /// <summary>Where the next character lands, down.</summary>
    public int CursorY { get; private set; }

    /// <summary>Take a new box and resize the grid to fit it.</summary>
    /// <param name="box">The room the layout gave this window.</param>
    public override void Rearrange(Box box)
    {
        base.Rearrange(box);

        Resize(Width, Height);
    }

    /// <summary>
    /// Put the cursor where the game asks. Past-the-edge positions are
    /// legal: output there falls into the void until the cursor comes
    /// back inside.
    /// </summary>
    /// <param name="x">Where to put it across.</param>
    /// <param name="y">Where to put it down.</param>
    public void MoveCursor(int x, int y)
    {
        CursorX = x;
        CursorY = y;
    }

    /// <summary>
    /// Write at the cursor and advance (Glk: Text Grid Windows).
    ///
    /// A newline moves to the start of the next row and prints nothing;
    /// the right edge wraps; anything landing outside the grid is
    /// dropped.
    /// </summary>
    /// <param name="character">The character written.</param>
    public override void PutChar(uint character)
    {
        base.PutChar(character);

        int width = Width, height = Height;

        if (character == Characters.Newline)
        {
            CursorX = 0;
            CursorY++;

            return;
        }

        if (CursorX >= width)
        {
            CursorX = 0;
            CursorY++;
        }

        if (CursorY >= 0 && CursorY < height && CursorX >= 0 && CursorX < width)
        {
            _lines[CursorY][CursorX] = Characters.ToChar(character);
            _styles[CursorY][CursorX] = Style;
            _links[CursorY][CursorX] = Stream.Hyperlink;
        }

        CursorX++;
    }

    /// <summary>Fill the grid with blanks and home the cursor.</summary>
    public override void Clear()
    {
        Resize(Width, Height);

        foreach (var row in _lines)
        {
            Array.Fill(row, " ");
        }

        CursorX = 0;
        CursorY = 0;
    }

    /// <summary>The grid as one string per row.</summary>
    public IReadOnlyList<string> Rows() =>
        Array.ConvertAll(_lines, row => string.Concat(row));

    /// <summary>Grow or trim the rows, keeping what still fits.</summary>
    private void Resize(int width, int height)
    {
        _lines = Reshaped(_lines, width, height, " ");
        _styles = Reshaped(_styles, width, height, TextStyle.Normal);
        _links = Reshaped(_links, width, height, 0u);

        CursorX = Math.Min(CursorX, Math.Max(0, width));
        CursorY = Math.Min(CursorY, Math.Max(0, height));
    }

    /// <summary>One parallel grid, reshaped, the overlap kept.</summary>
    private static T[][] Reshaped<T>(T[][] old, int width, int height, T blank)
    {
        var grown = new T[height][];

        for (var row = 0; row < height; row++)
        {
            var line = new T[width];

            for (var column = 0; column < width; column++)
            {
                line[column] = row < old.Length && column < old[row].Length
                    ? old[row][column]
                    : blank;
            }

            grown[row] = line;
        }

        return grown;
    }
}

/// <summary>An internal node: a split of two (Glk: Window Arrangement).</summary>
public sealed class PairWindow : SizelessWindow
{
    /// <summary>Join two windows under a split method.</summary>
    /// <param name="child1">The window on the unconstrained side.</param>
    /// <param name="child2">The window on the side the direction names.</param>
    /// <param name="key">The window the split is measured against.</param>
    /// <param name="method">The split method, as a packed word.</param>
    /// <param name="size">The split's size, in the key window's units.</param>
    public PairWindow(Window child1, Window child2, Window key, uint method, int size)
    {
        Child1 = child1;
        Child2 = child2;
        Key = key;
        Size = size;
        SetMethod(method);
    }

    /// <inheritdoc/>
    public override uint WinType => WindowType.Pair;

    /// <summary>
    /// The window on the split's unconstrained side: the original
    /// window, until a re-arrangement flips the direction and swaps the
    /// children.
    /// </summary>
    public Window Child1 { get; set; }

    /// <summary>
    /// The window on the side the direction names, which carries the
    /// size constraint: the split-off window, at first.
    /// </summary>
    public Window Child2 { get; set; }

    /// <summary>
    /// The window the split's size is measured against. Only the
    /// measurement: the constraint sits on Child2's side wherever the
    /// key lives, and the specification's own worked example puts them
    /// apart on purpose (Glk: Changing Window Constraints).
    /// </summary>
    public Window Key { get; set; }

    /// <summary>
    /// The split's size, in the key window's units, or as a percentage
    /// for a proportional split.
    /// </summary>
    public int Size { get; set; }

    /// <summary>Which side the constrained window takes.</summary>
    public uint Direction { get; private set; }

    /// <summary>Whether the size is fixed or proportional.</summary>
    public uint Division { get; private set; }

    /// <summary>Whether a border is drawn between the two.</summary>
    public bool HasBorder { get; private set; }

    /// <summary>Whether the split divides left from right.</summary>
    public bool Vertical { get; private set; }

    /// <summary>Whether the constrained window comes first.</summary>
    public bool Backward { get; private set; }

    /// <summary>
    /// The box the constrained side received, kept for displays that
    /// draw borders.
    /// </summary>
    public Box SizedBox { get; private set; }

    /// <summary>The split's parts recomposed into a method word.</summary>
    public uint Method =>
        Direction | Division | (HasBorder ? WindowMethod.Border : WindowMethod.NoBorder);

    /// <summary>Unpack a method word into the split's parts.</summary>
    /// <param name="method">The split method, as a packed word.</param>
    public void SetMethod(uint method)
    {
        Direction = method & WindowMethod.DirMask;
        Division = method & WindowMethod.DivisionMask;
        HasBorder = (method & WindowMethod.BorderMask) == WindowMethod.Border;
        Vertical = Direction is WindowMethod.Left or WindowMethod.Right;
        Backward = Direction is WindowMethod.Left or WindowMethod.Above;
    }

    /// <summary>
    /// Split the box between the two children.
    ///
    /// The box is in display units. A proportional split is a percentage
    /// and needs no conversion; a fixed one is expressed in the key
    /// window's measurement system (Glk: Window Opening, Closing, and
    /// Constraints), so characters for a text window and pixels for a
    /// graphics window. Window.Extent supplies the conversion, which is
    /// nothing on a terminal.
    /// </summary>
    /// <param name="box">The room the layout gave this split.</param>
    public override void Rearrange(Box box)
    {
        base.Rearrange(box);

        var (left, top, right, bottom) = box;
        var extent = Vertical ? right - left : bottom - top;

        var split = Division == WindowMethod.Proportional
            ? extent * Size / 100
            : Key.Extent(Size, Vertical);

        split = Math.Max(0, Math.Min(split, extent));

        // How much of the extent the first box gets; the second box
        // takes the rest.
        var first = Backward ? split : extent - split;

        Box box1, box2;

        if (Vertical)
        {
            var middle = left + first;
            box1 = new Box(left, top, middle, bottom);
            box2 = new Box(middle, top, right, bottom);
        }
        else
        {
            var middle = top + first;
            box1 = new Box(left, top, right, middle);
            box2 = new Box(left, middle, right, bottom);
        }

        // The direction decides the sides outright: Child2 sits on the
        // named side and takes the split's size, however deep the key
        // window has since been buried. "The key window for the original
        // split is still the key window ... even though it's now a
        // grandchild" (Glk: Window Opening, Closing, and Constraints).
        Box other;

        if (Backward)
        {
            SizedBox = box1;
            other = box2;
        }
        else
        {
            SizedBox = box2;
            other = box1;
        }

        Child2.Rearrange(SizedBox);
        Child1.Rearrange(other);
    }
}
