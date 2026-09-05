namespace Voxam.Core;

/// <summary>A cell rectangle a stage operation touched: first row, first column, and the counts.</summary>
public readonly record struct Rectangle(int Row, int Column, int Rows, int Columns);

/// <summary>Something a glass must carry out, positioned in §8.8's units.</summary>
public abstract record Paint;

/// <summary>One dressed character at a unit position, its top left corner 1-based.</summary>
public sealed record TextPaint(int Line, int Column, Cell Cell) : Paint;

/// <summary>A unit rectangle painted to a §8.3.1 background colour (§8.8.5).</summary>
public sealed record FillPaint(int Line, int Column, int Height, int Width, int Background) : Paint;

/// <summary>
/// A unit rectangle whose pixels slide vertically (§8.8.3.6), the rise
/// positive upward. The strip it exposes arrives as its own fill.
/// </summary>
public sealed record ShiftPaint(int Line, int Column, int Height, int Width, int Rise) : Paint;

/// <summary>
/// A run of text at a unit position, its top left corner 1-based,
/// dressed in true colour. Glk names its colours outright rather than
/// through a table of eight, so this is what a Glk display paints with
/// where the Z-Machine's stage paints cells.
/// </summary>
public sealed record RunPaint(
    int Line, int Column, string Text, uint Ink, uint Paper, bool Bold, bool Italic) : Paint;

/// <summary>A unit rectangle painted in a true colour, for the same reason.</summary>
public sealed record ColourPaint(
    int Line, int Column, int Height, int Width, uint Colour) : Paint;

/// <summary>
/// A picture drawn into a unit rectangle, showing only the part of
/// itself named in its own pixels.
///
/// Glk lets a picture hang off the edge of its window, and "the excess
/// is not drawn" (Glk: Graphics in Graphics Windows). The overhang is
/// cut away by naming the source rectangle rather than by clipping the
/// destination, which is the same answer and one fewer thing for a
/// glass to keep track of.
/// </summary>
public sealed record ClipPaint(
    int Line,
    int Column,
    int Height,
    int Width,
    int SourceLeft,
    int SourceTop,
    int SourceWidth,
    int SourceHeight,
    byte[] Bytes) : Paint;

/// <summary>
/// A picture stretched into a unit rectangle (§15 draw_picture). The
/// size is the one picture_data reported, so what a game measured is
/// what it gets, and clear pixels stay see-through, which is how
/// Arthur's banner frames the scene art beneath it.
/// </summary>
public sealed record PicturePaint(int Line, int Column, int Height, int Width, byte[] Pixels) : Paint;

/// <summary>
/// The Version 6 stage: §8.8's eight windows on one cell grid.
///
/// Version 6 games place their windows in units, a status strip here,
/// a story box there, chrome around a picture, and the plain and
/// painted faces can only mimic that with flowing text. This model is
/// for a glass that measures: it keeps all eight §8.8.3 windows, each
/// with a position and size in units, its own cursor, dress and
/// attributes, and plots their text onto one shared grid of cells. The
/// grid it offers is the screen model's own, so a glass reads either
/// the same way, while the paints it hands out carry the true unit
/// positions no cell grid can hold.
///
/// Nothing printed belongs to a window once plotted (§8.8.3): moving a
/// window moves only its bookkeeping, and text lands wherever the
/// window was at the moment of printing.
/// </summary>
public sealed class StageModel
{
    /// <summary>§8.8.3's eight windows.</summary>
    public const int WindowCount = 8;

    /// <summary>A line count meaning never print [MORE] (§8.8.3.2.6).</summary>
    public const int NeverMore = -999;

    private const int EraseUnsplit = -1;
    private const int EraseKeepSplit = -2;

    // One §8.8.3 window: geometry in units, a cursor in cells. The
    // cursor is kept as 0-based cell offsets inside the window's own
    // box, the wrap arithmetic's natural coordinates, and converted to
    // §8.8's 1-based units at the seam.
    private sealed class Window
    {
        public int Y = 1;
        public int X = 1;
        public int Height;
        public int Width;
        public int Left;
        public int Right;
        public int Row;
        public int Column;
        public int Fed;
        public int Style = ScreenModel.Roman;
        public int Foreground = ScreenModel.DefaultColour;
        public int Background = ScreenModel.DefaultColour;
        public int Font = 1;
        public bool Wrapping;
        public bool Scrolling;
        public bool ScrollDue;
        public List<Cell> Pending = [];
    }

    private static readonly Cell Blank = new(" ", ScreenModel.Roman, ScreenModel.DefaultColour, ScreenModel.DefaultColour, 1);

    private readonly int _fontWidth;
    private readonly int _fontHeight;
    private readonly Cell[][] _grid;
    private readonly SortedSet<int> _damage = [];
    private readonly Window[] _windows = new Window[WindowCount];
    private List<Paint> _paints = [];
    private bool _buffered = true;
    private bool _splitSeen;
    private int _selected;

    /// <summary>The §8.8.3.3 boot stage: window 0 filling the screen.</summary>
    public StageModel(int columns, int lines, int fontWidth, int fontHeight)
    {
        Columns = columns;
        Lines = lines;
        _fontWidth = fontWidth;
        _fontHeight = fontHeight;
        _grid = new Cell[lines][];

        for (var row = 0; row < lines; row++)
        {
            _grid[row] = Enumerable.Repeat(Blank, columns).ToArray();
        }

        for (var number = 0; number < WindowCount; number++)
        {
            _windows[number] = new Window();
        }

        _windows[0].Height = lines * fontHeight;
        _windows[0].Width = columns * fontWidth;
        _windows[0].Wrapping = true;
        _windows[0].Scrolling = true;
        // Window 1 boots screen-wide and flat: §8.8.4.1's split tiles
        // it against window 0 without touching widths, so a width must
        // already be there for the split to mean anything.
        _windows[1].Width = columns * fontWidth;
    }

    /// <summary>The screen width in cells.</summary>
    public int Columns { get; }

    /// <summary>The screen height in cells.</summary>
    public int Lines { get; }

    /// <summary>Which of the eight windows takes the next printing.</summary>
    public int Selected => _selected;

    /// <summary>The selected window's §8.3.1 background colour code.</summary>
    public int Background => _windows[_selected].Background;

    /// <summary>The selected window's §8.3.1 foreground colour code.</summary>
    public int Foreground => _windows[_selected].Foreground;

    /// <summary>
    /// The [MORE] seam: the frontend hangs a callback here, and the
    /// stage calls it with the pause's unit position and the window's
    /// colour codes when a scrolling window has fed a screenful since
    /// the player last rested (§8.8.3.2.6).
    /// </summary>
    public Action<int, int, int, int>? More { get; set; }

    // --- geometry, from units to the cell grid ---

    private int FirstRow(Window window) => (window.Y - 1) / _fontHeight + 1;

    private int FirstColumn(Window window) => (window.X - 1) / _fontWidth + 1;

    private int RowCount(Window window) => window.Height / _fontHeight;

    private int ColumnCount(Window window) => window.Width / _fontWidth;

    private int LeftEdge(Window window) => window.Left / _fontWidth;

    // Margins are §8.8.3.2.1's: sizes in units, 0 by default, and text
    // is clipped to stay inside them.
    private int RightEdge(Window window) => (window.Width - window.Right) / _fontWidth;

    private Rectangle Box(Window window)
    {
        var firstRow = Math.Max(FirstRow(window), 1);
        var firstColumn = Math.Max(FirstColumn(window), 1);
        var lastRow = Math.Min(FirstRow(window) + RowCount(window) - 1, Lines);
        var lastColumn = Math.Min(FirstColumn(window) + ColumnCount(window) - 1, Columns);
        return new Rectangle(firstRow, firstColumn, Math.Max(lastRow - firstRow + 1, 0), Math.Max(lastColumn - firstColumn + 1, 0));
    }

    // --- the stage seam the machine drives ---

    /// <summary>
    /// Place a window at a position with a size, in units. Nothing on
    /// screen moves (§8.8.3): the geometry only decides where future
    /// text lands, and the window's own cursor rides along unchanged
    /// (§8.8.3.5).
    /// </summary>
    public void PlaceWindow(int window, int line, int column, int height, int width)
    {
        var target = _windows[Known(window)];
        Flush(_windows[_selected]);
        target.Y = line;
        target.X = column;
        target.Height = height;
        target.Width = width;
    }

    /// <summary>Select the window that takes the next printing; each remembers its own cursor (§8.8.3.5).</summary>
    public void SetWindow(int window)
    {
        Flush(_windows[_selected]);
        _selected = Known(window);
    }

    /// <summary>Move the selected window's cursor, in relative units.</summary>
    public void SetCursor(int line, int column)
    {
        var current = _windows[_selected];
        Flush(current);
        current.Row = Math.Max((line - 1) / _fontHeight, 0);
        current.Column = Math.Max((column - 1) / _fontWidth, 0);
        current.ScrollDue = false;
    }

    /// <summary>The selected window's cursor, in relative units.</summary>
    public (int Line, int Column) GetCursor()
    {
        var current = _windows[_selected];
        Flush(current);
        return (current.Row * _fontHeight + 1, current.Column * _fontWidth + 1);
    }

    /// <summary>
    /// The selected window's cursor as absolute screen units, where
    /// GetCursor answers in the window's own coordinates (§8.7.2.3.2).
    /// </summary>
    public (int Line, int Column) ScreenCursor()
    {
        var current = _windows[_selected];
        Flush(current);
        return (current.Y + current.Row * _fontHeight, current.X + current.Column * _fontWidth);
    }

    /// <summary>
    /// Tile windows 1 and 0 vertically, the height in units. Window 1
    /// takes the top at that height and window 0 the rest (§8.8.4.1);
    /// x coordinates and widths stay put. Each cursor keeps its
    /// absolute screen position unless that now falls outside its
    /// window, in which case it homes (§15 split_window).
    /// </summary>
    public void SplitWindow(int height)
    {
        Flush(_windows[_selected]);
        _splitSeen = _splitSeen || height > 0;
        var screenHeight = Lines * _fontHeight;
        var upper = _windows[1];
        var lower = _windows[0];
        var absolutes = new[] { (Window: upper, At: FirstRow(upper) + upper.Row), (Window: lower, At: FirstRow(lower) + lower.Row) };
        upper.Y = 1;
        upper.Height = height;
        lower.Y = height + 1;
        lower.Height = Math.Max(screenHeight - height, 0);

        foreach (var (window, at) in absolutes)
        {
            window.Row = at - FirstRow(window);

            if (window.Row < 0 || window.Row >= Math.Max(RowCount(window), 1))
            {
                window.Row = 0;
                window.Column = 0;
            }
        }
    }

    /// <summary>
    /// Print to the selected window, by its §8.8.3.1 attributes. A
    /// wrapping window breaks lines at its own right edge, whole words
    /// while buffering is on, and a scrolling one scrolls its own
    /// rectangle; a window with neither overlays until its right
    /// margin, where the cursor stays and further text is ignored
    /// (§8.8.3.1.1).
    /// </summary>
    public void Write(string text)
    {
        var current = _windows[_selected];

        foreach (var character in text)
        {
            if (character == '\n')
            {
                Flush(current);
                Feed(current);
            }
            else if (!_buffered)
            {
                Emit(current, Dressed(character));
            }
            else if (character == ' ')
            {
                Flush(current);
                EmitSpace(current);
            }
            else
            {
                current.Pending.Add(Dressed(character));
            }
        }
    }

    /// <summary>
    /// Erase a window's rectangle to background (§8.8.5.3). Window -1
    /// erases the whole screen to window 0's background, re-tiles
    /// windows 0 and 1 if a split had happened, and selects window 0
    /// (§8.8.5.3.1, §8.8.4.2); window -2 erases the whole screen to the
    /// current background and changes nothing else (§8.8.5.3.2). A
    /// plain window erases its own rectangle and homes its cursor.
    /// </summary>
    public Rectangle EraseWindow(int window)
    {
        Flush(_windows[_selected]);

        if (window == EraseUnsplit)
        {
            BlankRows(1, Lines, _windows[0].Background);
            _paints.Add(ScreenFill(_windows[0].Background));

            if (_splitSeen)
            {
                SplitWindow(0);
            }

            _selected = 0;
            _windows[0].Row = 0;
            _windows[0].Column = 0;
            _windows[0].ScrollDue = false;
            // Erased text cannot be unread: the whole screen is gone,
            // so every [MORE] budget refills (§8.8.3.2.6).
            Rest();
            return new Rectangle(1, 1, Lines, Columns);
        }

        if (window == EraseKeepSplit)
        {
            BlankRows(1, Lines, Background);
            _paints.Add(ScreenFill(Background));
            Rest();
            return new Rectangle(1, 1, Lines, Columns);
        }

        var target = _windows[Known(window)];
        var box = Box(target);

        for (var row = box.Row; row < box.Row + box.Rows; row++)
        {
            for (var column = box.Column; column < box.Column + box.Columns; column++)
            {
                PaintCell(row, column, BlankIn(target.Background));
            }
        }

        // The glass erases the window's true unit rectangle, not the
        // cell approximation, as §8.8.5.3 measures it.
        _paints.Add(new FillPaint(target.Y, target.X, target.Height, target.Width, target.Background));
        target.Row = 0;
        target.Column = 0;
        target.ScrollDue = false;

        // Erased text cannot be unread: this window's [MORE] budget
        // refills. Shogun erases window 0 before printing its title
        // menu into a freshly shrunken box, and a stale count would
        // pause the menu mid-print (§8.8.3.2.6). An explicit
        // never-pause stays in force.
        if (target.Fed != NeverMore)
        {
            target.Fed = 0;
        }

        return box;
    }

    private FillPaint ScreenFill(int background) =>
        new(1, 1, Lines * _fontHeight, Columns * _fontWidth, background);

    /// <summary>
    /// Scroll a window's rectangle by a unit amount (§8.8.3.6).
    /// Positive scrolls the text up, negative down, in whole cell rows,
    /// the §15 opcode unrelated to the scrolling attribute, and the
    /// exposed rows blank to the window's background. Arthur scrolls
    /// its story window this way at every prompt.
    /// </summary>
    public void ScrollWindow(int window, int pixels)
    {
        Flush(_windows[_selected]);
        var target = _windows[Known(window)];

        for (var step = 0; step < Math.Abs(pixels) / _fontHeight; step++)
        {
            if (pixels > 0)
            {
                Scroll(target);
            }
            else
            {
                ScrollDown(target);
            }
        }
    }

    /// <summary>
    /// The player is at an input: every [MORE] budget refills, since
    /// keyboard attention is the §8.8.3.2.6 clock.
    /// </summary>
    public void Rest()
    {
        foreach (var window in _windows)
        {
            if (window.Fed != NeverMore)
            {
                window.Fed = 0;
            }
        }
    }

    /// <summary>
    /// Set a window's §8.8.3.2.6 line count directly. Version 6 games
    /// set line counts to manipulate when [MORE] is printed; -999 means
    /// never print it at all.
    /// </summary>
    public void SetLineCount(int window, int count) => _windows[Known(window)].Fed = count;

    /// <summary>
    /// Set a window's margins in units (§8.8.3.2.1). Wrapping text is
    /// clipped to stay inside them, and a cursor the new margins would
    /// strand moves to the left margin (§8.8.3.2.2.2).
    /// </summary>
    public void SetMargins(int window, int left, int right)
    {
        Flush(_windows[_selected]);
        var target = _windows[Known(window)];
        target.Left = left;
        target.Right = right;

        if (target.Column < LeftEdge(target) || target.Column >= RightEdge(target))
        {
            target.Column = LeftEdge(target);
        }
    }

    /// <summary>
    /// Erase rightward from the cursor (§8.8.5.2), to the right margin
    /// by default or across a given width in units, clipped to stay
    /// inside the margin. The grid blanks only the cells the span fully
    /// covers; the fill is the pixel truth.
    /// </summary>
    public void EraseLine(int? pixels = null)
    {
        var current = _windows[_selected];
        Flush(current);
        var box = Box(current);

        if (current.Row >= box.Rows)
        {
            return;
        }

        var width = (RightEdge(current) - current.Column) * _fontWidth;

        if (pixels is not null)
        {
            width = Math.Min(pixels.Value, width);
        }

        var row = box.Row + current.Row;

        for (var column = box.Column + current.Column; column < box.Column + current.Column + width / _fontWidth; column++)
        {
            PaintCell(row, column, BlankIn(current.Background));
        }

        if (width > 0)
        {
            _paints.Add(new FillPaint(
                current.Y + current.Row * _fontHeight,
                current.X + current.Column * _fontWidth,
                _fontHeight,
                width,
                current.Background));
        }
    }

    /// <summary>Retreat the cursor one cell and blank it (§15 read).</summary>
    public void RubOut()
    {
        var current = _windows[_selected];
        Flush(current);

        if (current.Column <= 0)
        {
            return;
        }

        current.Column--;
        var box = Box(current);
        PaintCell(box.Row + current.Row, box.Column + current.Column, BlankIn(current.Background));
        _paints.Add(new FillPaint(
            current.Y + current.Row * _fontHeight,
            current.X + current.Column * _fontWidth,
            _fontHeight,
            _fontWidth,
            current.Background));
    }

    /// <summary>
    /// Move the cursor left without erasing (§15 line editing), stopped
    /// at the window's left edge, answering the cells actually moved.
    /// </summary>
    public int Retreat(int cells)
    {
        var current = _windows[_selected];
        Flush(current);
        var moved = Math.Min(cells, current.Column);
        current.Column -= moved;
        return moved;
    }

    /// <summary>
    /// Print a §15 rectangle, right and down from the cursor. Each row
    /// after the first begins one line down at the column where the
    /// rectangle began, overlaying without wrap.
    /// </summary>
    public void WriteRectangle(IReadOnlyList<string> rows)
    {
        var current = _windows[_selected];
        Flush(current);
        var (startRow, startColumn) = (current.Row, current.Column);
        var wrapping = current.Wrapping;
        current.Wrapping = false;

        for (var index = 0; index < rows.Count; index++)
        {
            if (index > 0)
            {
                var bottom = Math.Max(RowCount(current) - 1, 0);
                current.Row = Math.Min(startRow + index, bottom);
                current.Column = startColumn;
            }

            foreach (var character in rows[index])
            {
                Emit(current, Dressed(character));
            }
        }

        current.Wrapping = wrapping;
    }

    /// <summary>Change the selected window's style (§8.8.3.2.3).</summary>
    public void SetStyle(int style)
    {
        var current = _windows[_selected];
        current.Style = style == ScreenModel.Roman ? ScreenModel.Roman : current.Style | style;
    }

    /// <summary>Change the selected window's colours (§8.8.3.2.4).</summary>
    public void SetColour(int foreground, int background)
    {
        var current = _windows[_selected];

        if (foreground != ScreenModel.CurrentColour)
        {
            current.Foreground = foreground;
        }

        if (background != ScreenModel.CurrentColour)
        {
            current.Background = background;
        }
    }

    /// <summary>Change the selected window's font (§8.8.3.2.5).</summary>
    public void SetFont(int font) => _windows[_selected].Font = font;

    /// <summary>Turn buffered printing off or on (§8.8.3.1.2).</summary>
    public void SetBuffering(bool buffered)
    {
        Flush(_windows[_selected]);
        _buffered = buffered;
    }

    // --- the grid the glass blits ---

    /// <summary>
    /// The unit-positioned paints since the last drain, in order. The
    /// glass performs exactly these, and its own persistent pixels are
    /// the retained screen, §8.8.3's rule made literal.
    /// </summary>
    public IReadOnlyList<Paint> Paints()
    {
        Flush(_windows[_selected]);
        var drained = _paints;
        _paints = [];
        return drained;
    }

    /// <summary>The rows changed since the last sweep, in screen order.</summary>
    public List<int> Sweep()
    {
        Flush(_windows[_selected]);
        var damaged = _damage.ToList();
        _damage.Clear();
        return damaged;
    }

    /// <summary>One grid position, pending text flushed first.</summary>
    public Cell CellAt(int row, int column)
    {
        Flush(_windows[_selected]);
        return _grid[row - 1][column - 1];
    }

    /// <summary>One row's characters as a string, right side trimmed.</summary>
    public string RowText(int row)
    {
        Flush(_windows[_selected]);
        return string.Concat(_grid[row - 1].Select(cell => cell.Character)).TrimEnd();
    }

    /// <summary>The whole stage as a text block, one line per row.</summary>
    public string Rendered() => string.Join("\n", Enumerable.Range(1, Lines).Select(RowText));

    // --- the wrap machinery, one window at a time ---

    private static int Known(int window) => window is >= 0 and < WindowCount
        ? window
        : throw new ZMachineException($"window {window} is not one of the eight (§8.8.3)");

    private Cell Dressed(char character)
    {
        var current = _windows[_selected];
        return new Cell(character.ToString(), current.Style, current.Foreground, current.Background, current.Font);
    }

    private static Cell BlankIn(int background) => new(" ", ScreenModel.Roman, ScreenModel.DefaultColour, background, 1);

    // Emit a pending word, wrapping it whole when that fits.
    private void Flush(Window window)
    {
        if (window.Pending.Count == 0)
        {
            return;
        }

        var word = window.Pending;
        window.Pending = [];
        var edge = RightEdge(window);

        if (window.Wrapping && word.Count > edge - window.Column && word.Count <= edge - LeftEdge(window))
        {
            Feed(window);
        }

        foreach (var cell in word)
        {
            Emit(window, cell);
        }
    }

    // Emit one space, or let the line break swallow it.
    private void EmitSpace(Window window)
    {
        if (window.Wrapping && window.Column >= RightEdge(window))
        {
            Feed(window);
            return;
        }

        Emit(window, Dressed(' '));
    }

    // Place one cell at the window's cursor, edge rules and all. The
    // edges are the §8.8.3.2.1 margins', the whole window when they are
    // 0, their default.
    private void Emit(Window window, Cell cell)
    {
        var edge = RightEdge(window);

        if (edge <= LeftEdge(window) || RowCount(window) == 0)
        {
            return;
        }

        if (window.Column >= edge)
        {
            if (!window.Wrapping)
            {
                // §8.8.3.1.1: the cursor moves to the right margin and
                // stays there; further text is ignored.
                window.Column = edge;
                return;
            }

            Feed(window);
        }

        if (window.ScrollDue)
        {
            Scroll(window);
            window.ScrollDue = false;
        }

        var box = Box(window);
        PaintCell(box.Row + window.Row, box.Column + window.Column, cell);
        _paints.Add(new TextPaint(
            window.Y + window.Row * _fontHeight,
            window.X + window.Column * _fontWidth,
            cell));
        window.Column++;
    }

    // Move to the next line, scrolling or pinning at the bottom. The
    // cursor returns to the left margin (§8.8.3.2.1). A scrolling
    // window counts its new lines, and a screenful of them since the
    // player's last rest earns the [MORE] pause (§8.8.3.2.6).
    private void Feed(Window window)
    {
        if (window.ScrollDue)
        {
            Scroll(window);
            window.ScrollDue = false;
        }

        var bottom = Math.Max(RowCount(window) - 1, 0);

        if (window.Scrolling && window.Fed != NeverMore)
        {
            window.Fed++;

            if (window.Fed >= Math.Max(bottom, 1) && More is not null)
            {
                More(window.Y + bottom * _fontHeight, window.X + window.Left, window.Foreground, window.Background);
                window.Fed = 0;
            }
        }

        if (window.Row >= bottom)
        {
            window.Row = bottom;

            if (window.Scrolling)
            {
                // The scroll is owed, not paid: it happens when the
                // next text arrives, keeping the last line at the
                // window's foot instead of above a blank one.
                window.ScrollDue = true;
            }
        }
        else
        {
            window.Row++;
        }

        window.Column = LeftEdge(window);
    }

    // Scroll the window's own rectangle up one cell row.
    private void Scroll(Window window)
    {
        var box = Box(window);

        for (var row = box.Row; row < box.Row + box.Rows - 1; row++)
        {
            for (var column = box.Column; column < box.Column + box.Columns; column++)
            {
                PaintCell(row, column, _grid[row][column - 1]);
            }
        }

        for (var column = box.Column; column < box.Column + box.Columns; column++)
        {
            PaintCell(box.Row + box.Rows - 1, column, BlankIn(window.Background));
        }

        // Only the flowed region between the margins scrolls: the
        // margins keep their art. Shogun anchors its ship in a right
        // margin while the text beside it scrolls fifty times, which is
        // only possible if the reference interpreters left the margins
        // unswept (§8.8.3.2.1).
        var flowed = FlowedWidth(window, box.Columns * _fontWidth);
        _paints.Add(new ShiftPaint(window.Y, window.X + window.Left, box.Rows * _fontHeight, flowed, _fontHeight));
        _paints.Add(new FillPaint(
            window.Y + (box.Rows - 1) * _fontHeight,
            window.X + window.Left,
            _fontHeight,
            flowed,
            window.Background));
    }

    // Scroll the window's own rectangle down one cell row.
    private void ScrollDown(Window window)
    {
        var box = Box(window);

        for (var row = box.Row + box.Rows - 1; row > box.Row; row--)
        {
            for (var column = box.Column; column < box.Column + box.Columns; column++)
            {
                PaintCell(row, column, _grid[row - 2][column - 1]);
            }
        }

        for (var column = box.Column; column < box.Column + box.Columns; column++)
        {
            PaintCell(box.Row, column, BlankIn(window.Background));
        }

        // The downward twin keeps its margins too (§8.8.3.2.1).
        var flowed = FlowedWidth(window, box.Columns * _fontWidth);
        _paints.Add(new ShiftPaint(window.Y, window.X + window.Left, box.Rows * _fontHeight, flowed, -_fontHeight));
        _paints.Add(new FillPaint(window.Y, window.X + window.Left, _fontHeight, flowed, window.Background));
    }

    // The scrolled region's width: between the margins, clipped. A
    // window without margins scrolls its whole painted width; one with
    // margins scrolls only where text flows (§8.8.3.2.1).
    private static int FlowedWidth(Window window, int painted) =>
        Math.Max(Math.Min(window.Width - window.Left - window.Right, painted), 0);

    private void BlankRows(int first, int last, int background)
    {
        for (var row = first; row <= last; row++)
        {
            _grid[row - 1] = Enumerable.Repeat(BlankIn(background), Columns).ToArray();
            _damage.Add(row);
        }
    }

    // The box every caller paints through is clamped into the screen
    // and no window's cursor is ever negative, so a position can only
    // run off the far edges, never the near ones.
    private void PaintCell(int row, int column, Cell cell)
    {
        if (row <= Lines && column <= Columns)
        {
            _grid[row - 1][column - 1] = cell;
            _damage.Add(row);
        }
    }
}
