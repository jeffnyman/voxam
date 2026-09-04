using System.Diagnostics;
using System.Globalization;
using System.Text;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Input;
using Avalonia.Media;
using Avalonia.Threading;
using Voxam.Core;

namespace Voxam.Desktop;

/// <summary>
/// The glass: a character grid drawn straight onto the control from
/// a snapshot of the screen model, and the screen a machine thread
/// paints on. The machine thread hands over rows, the cursor and the
/// [MORE] overlay under a lock and asks for one redraw; the UI thread
/// draws whatever the snapshot holds and turns keys into the strings
/// the frontend's reads expect. Font 3 is drawn from its own §16
/// bitmaps, edge to edge, so a map corridor meets its neighbour with
/// no seam.
/// </summary>
public sealed class Glass : Control, IScreen
{
    /// <summary>The classic grid the window opens at.</summary>
    public const int OpeningColumns = 80;

    /// <summary>The classic grid's height, the reference's GLASS_LINES.</summary>
    public const int OpeningLines = 24;

    private const double FontSize = 18;
    private const int GraphicsFont = 3;
    private const int WhiteCode = 9;
    private const int BlackCode = 2;
    private const string Backspace = "\u007f";
    private const string Escape = "\u001b";

    // The bundled face: Go Mono, the same the browser tab wears as
    // Voxam Mono, so a frame is the same frame on every desktop.
    private static readonly FontFamily Family = new("avares://Voxam/Assets/Fonts#Go Mono");
    private static readonly Typeface Roman = new(Family);
    private static readonly Typeface Bold = new(Family, FontStyle.Normal, FontWeight.Bold);
    private static readonly Typeface Italic = new(Family, FontStyle.Italic);
    private static readonly Typeface BoldItalic = new(Family, FontStyle.Italic, FontWeight.Bold);
    private static readonly Cell Blank = new(" ", ScreenModel.Roman, ScreenModel.DefaultColour, ScreenModel.DefaultColour, 1);

    // The §8.3.1 colours the theme leaves alone, in the reference's
    // palette; 2 and 9, black and white, follow the theme (§8.3.3).
    private static readonly Dictionary<int, Color> Palette = new()
    {
        [3] = Color.FromRgb(204, 0, 0),
        [4] = Color.FromRgb(0, 204, 0),
        [5] = Color.FromRgb(204, 204, 0),
        [6] = Color.FromRgb(0, 0, 204),
        [7] = Color.FromRgb(204, 0, 204),
        [8] = Color.FromRgb(0, 204, 204),
        [10] = Color.FromRgb(181, 181, 181),
        [11] = Color.FromRgb(139, 139, 139),
        [12] = Color.FromRgb(90, 90, 90),
    };

    // The keys with a §3.8 character of their own; the function
    // keys are 133 to 144 in order.
    private static readonly Dictionary<Key, string> Keys = new()
    {
        [Key.Enter] = "\n",
        [Key.Back] = Backspace,
        [Key.Delete] = Backspace,
        [Key.Escape] = Escape,
        [Key.Up] = LineEditor.CursorUp,
        [Key.Down] = LineEditor.CursorDown,
        [Key.Left] = LineEditor.CursorLeft,
        [Key.Right] = LineEditor.CursorRight,
        [Key.F1] = "\u0085",
        [Key.F2] = "\u0086",
        [Key.F3] = "\u0087",
        [Key.F4] = "\u0088",
        [Key.F5] = "\u0089",
        [Key.F6] = "\u008a",
        [Key.F7] = "\u008b",
        [Key.F8] = "\u008c",
        [Key.F9] = "\u008d",
        [Key.F10] = "\u008e",
        [Key.F11] = "\u008f",
        [Key.F12] = "\u0090",
    };

    private readonly Lock _lock = new();
    private readonly Queue<string> _typed = new();
    private int _generation;
    private Cell[][] _rows = [];
    private (int Row, int Column) _cursor = (1, 1);
    private (int Row, int Column, string Prompt)? _overlay;
    private Size? _cell;
    private int _dirty;
    private volatile int _columns;
    private volatile int _lines;
    private volatile bool _waiting;

    public Glass()
    {
        Focusable = true;
        Cursor = new Cursor(StandardCursorType.Ibeam);
    }

    /// <summary>The ink and paper the glass wears where a game names none.</summary>
    public Theme Look { get; set; } = Voxam.Desktop.Theme.Dark;

    /// <summary>The width in cells the control's bounds allow.</summary>
    public int Columns => _columns;

    /// <summary>The height in rows the control's bounds allow.</summary>
    public int Lines => _lines;

    /// <summary>One cell's size in the control's own units.</summary>
    public Size CellSize
    {
        get
        {
            if (_cell is null)
            {
                var probe = Formatted("M", Roman, Look.Ink);
                _cell = new Size(probe.Width, probe.Height);
            }

            return _cell.Value;
        }
    }

    /// <summary>Whether the machine is parked in a read, which is when the caret shows.</summary>
    public bool Waiting => _waiting;

    int IScreen.Width => _columns;

    int IScreen.Height => _lines;

    /// <summary>The snapshot as text, rows joined by newlines, for anyone reading over the player's shoulder.</summary>
    public string Text
    {
        get
        {
            lock (_lock)
            {
                var rows = new StringBuilder();

                foreach (var row in _rows)
                {
                    rows.Append(string.Concat(row.Select(cell => cell.Character)).TrimEnd()).Append('\n');
                }

                return rows.ToString();
            }
        }
    }

    /// <summary>The prompt laid over the glass, [MORE] while a screenful waits, or null.</summary>
    public string? Prompt
    {
        get
        {
            lock (_lock)
            {
                return _overlay?.Prompt;
            }
        }
    }

    /// <summary>Send one translated key, as the keyboard would.</summary>
    public void Press(string key)
    {
        lock (_typed)
        {
            _typed.Enqueue(key);
            Monitor.Pulse(_typed);
        }
    }

    /// <summary>End every read in flight: the thread waiting on this glass is finished with it.</summary>
    public void Retire()
    {
        lock (_typed)
        {
            _generation++;
            _typed.Clear();
            Monitor.PulseAll(_typed);
        }
    }

    // The machine's thread waits here for the keyboard, with the
    // caret showing while it does. A retired glass wakes it with a
    // cancellation instead of a key.
    public string? ReadKey(double? timeoutSeconds)
    {
        lock (_typed)
        {
            var generation = _generation;
            var clock = Stopwatch.StartNew();
            _waiting = true;
            Invalidate();

            try
            {
                while (_typed.Count == 0)
                {
                    if (_generation != generation)
                    {
                        throw new OperationCanceledException("the glass was retired");
                    }

                    if (timeoutSeconds is null)
                    {
                        Monitor.Wait(_typed);
                        continue;
                    }

                    var remaining = TimeSpan.FromSeconds(timeoutSeconds.Value) - clock.Elapsed;

                    if (remaining <= TimeSpan.Zero)
                    {
                        return null;
                    }

                    Monitor.Wait(_typed, remaining);
                }

                return _typed.Dequeue();
            }
            finally
            {
                _waiting = false;
                Invalidate();
            }
        }
    }

    public void Paint(ScreenModel model, int row)
    {
        var cells = new Cell[model.Columns];

        for (var column = 1; column <= model.Columns; column++)
        {
            cells[column - 1] = model.CellAt(row, column);
        }

        lock (_lock)
        {
            if (_rows.Length != model.Lines)
            {
                var rows = new Cell[model.Lines][];

                for (var k = 0; k < rows.Length; k++)
                {
                    rows[k] = k < _rows.Length ? _rows[k] : Enumerable.Repeat(Blank, model.Columns).ToArray();
                }

                _rows = rows;
            }

            _rows[row - 1] = cells;

            if (_overlay is { } overlay && overlay.Row == row)
            {
                _overlay = null;
            }
        }

        Invalidate();
    }

    public void Park(int row, int column)
    {
        lock (_lock)
        {
            _cursor = (row, column);
        }

        Invalidate();
    }

    public void Overlay(int row, int column, string prompt)
    {
        lock (_lock)
        {
            _overlay = (row, column, prompt);
        }

        Invalidate();
    }

    public override void Render(DrawingContext context)
    {
        _dirty = 0;
        Cell[][] rows;
        (int Row, int Column) cursor;
        (int Row, int Column, string Prompt)? overlay;

        lock (_lock)
        {
            rows = _rows;
            cursor = _cursor;
            overlay = _overlay;
        }

        var cell = CellSize;
        context.FillRectangle(new SolidColorBrush(Look.Paper), new Rect(Bounds.Size));

        for (var row = 0; row < rows.Length; row++)
        {
            DrawRow(context, rows[row], row, cell);
        }

        // The caret underlines the cursor's cell in its own ink while
        // the machine waits for typing; the wait only begins once
        // Clear has painted every row, so the cursor always has one,
        // and parked past a row's end it shows on the last cell.
        if (_waiting)
        {
            var line = rows[Math.Min(cursor.Row, rows.Length) - 1];
            var column = Math.Min(cursor.Column, line.Length);
            var (ink, _) = Colours(line[column - 1], line[column - 1].Style);
            var origin = new Point((column - 1) * cell.Width, cursor.Row * cell.Height - 2);
            context.FillRectangle(new SolidColorBrush(ink), new Rect(origin, new Size(cell.Width, 2)));
        }

        if (overlay is { } laid)
        {
            DrawRun(context, laid.Prompt, laid.Column - 1, laid.Row - 1, cell, Look.Paper, Look.Ink, ScreenModel.Roman);
        }
    }

    /// <summary>The classic grid, as what the control asks for: the window opens to fit it.</summary>
    protected override Size MeasureOverride(Size availableSize) =>
        new(OpeningColumns * CellSize.Width, OpeningLines * CellSize.Height);

    protected override void OnSizeChanged(SizeChangedEventArgs e)
    {
        base.OnSizeChanged(e);
        var cell = CellSize;
        _columns = (int)(e.NewSize.Width / cell.Width);
        _lines = (int)(e.NewSize.Height / cell.Height);
    }

    protected override void OnKeyDown(KeyEventArgs e)
    {
        if (Keys.TryGetValue(e.Key, out var key))
        {
            Press(key);
            e.Handled = true;
        }

        base.OnKeyDown(e);
    }

    // Typed text arrives here, one or more characters at a time;
    // controls have their own keys above and never come through as text.
    protected override void OnTextInput(TextInputEventArgs e)
    {
        foreach (var rune in e.Text.AsSpan().EnumerateRunes())
        {
            if (rune.Value >= ' ')
            {
                Press(rune.ToString());
            }
        }

        e.Handled = true;
        base.OnTextInput(e);
    }

    protected override void OnPointerPressed(PointerPressedEventArgs e)
    {
        Focus();
        base.OnPointerPressed(e);
    }

    // One redraw per burst of paints: the first paint after a frame
    // asks for it, the rest ride along.
    private void Invalidate()
    {
        if (Interlocked.Exchange(ref _dirty, 1) == 0)
        {
            Dispatcher.UIThread.Post(InvalidateVisual);
        }
    }

    // A row paints as runs of cells dressed alike, one background
    // rectangle and one text run each; a font 3 cell is its own tile.
    private void DrawRow(DrawingContext context, Cell[] cells, int row, Size cell)
    {
        var column = 0;

        while (column < cells.Length)
        {
            if (cells[column].Font == GraphicsFont && Font3.Bitmap(cells[column].Character) is { } bitmap)
            {
                var (tileInk, tilePaper) = Colours(cells[column], cells[column].Style);
                DrawTile(context, bitmap, column, row, cell, tileInk, tilePaper);
                column++;
                continue;
            }

            var (character, style) = Glyphs.Appearance(cells[column]);
            var (ink, paper) = Colours(cells[column], style);
            var run = new StringBuilder(character);
            var start = column;
            column++;

            while (column < cells.Length && cells[column].Font != GraphicsFont)
            {
                var (next, nextStyle) = Glyphs.Appearance(cells[column]);

                if (nextStyle != style || Colours(cells[column], nextStyle) != (ink, paper))
                {
                    break;
                }

                run.Append(next);
                column++;
            }

            DrawRun(context, run.ToString(), start, row, cell, ink, paper, style);
        }
    }

    private static void DrawRun(DrawingContext context, string text, int column, int row, Size cell, Color ink, Color paper, int style)
    {
        var origin = new Point(column * cell.Width, row * cell.Height);
        context.FillRectangle(new SolidColorBrush(paper), new Rect(origin, new Size(text.Length * cell.Width, cell.Height)));
        var face = (style & ScreenModel.Bold, style & ScreenModel.Italic) switch
        {
            (0, 0) => Roman,
            (_, 0) => Bold,
            (0, _) => Italic,
            _ => BoldItalic,
        };
        context.DrawText(Formatted(text, face, ink), origin);
    }

    // One §16 bitmap stretched to the cell, each pixel snapped to
    // whole device pixels so neighbours meet without a seam.
    private static void DrawTile(DrawingContext context, byte[] bitmap, int column, int row, Size cell, Color ink, Color paper)
    {
        var left = column * cell.Width;
        var top = row * cell.Height;
        context.FillRectangle(new SolidColorBrush(paper), new Rect(new Point(left, top), cell));
        var brush = new SolidColorBrush(ink);

        for (var y = 0; y < Font3.Rows; y++)
        {
            var y0 = Math.Round(top + y * cell.Height / Font3.Rows);
            var y1 = Math.Round(top + (y + 1) * cell.Height / Font3.Rows);

            for (var x = 0; x < Font3.Pixels; x++)
            {
                if (Font3.Lit(bitmap, x, y))
                {
                    var x0 = Math.Round(left + x * cell.Width / Font3.Pixels);
                    var x1 = Math.Round(left + (x + 1) * cell.Width / Font3.Pixels);
                    context.FillRectangle(brush, new Rect(x0, y0, x1 - x0, y1 - y0));
                }
            }
        }
    }

    // The colours a cell shows: its own §8.3.1 codes where the book
    // holds them, the theme's ink and paper for 0, 1, black, white
    // and anything else, swapped when the style is reverse.
    private (Color Ink, Color Paper) Colours(Cell cell, int style)
    {
        var ink = Resolve(cell.Foreground, Look.Ink);
        var paper = Resolve(cell.Background, Look.Paper);
        return (style & ScreenModel.Reverse) != 0 ? (paper, ink) : (ink, paper);
    }

    private Color Resolve(int code, Color fallback) => code switch
    {
        WhiteCode => Look.Ink,
        BlackCode => Look.Paper,
        _ => Palette.TryGetValue(code, out var named) ? named : fallback,
    };

    private static FormattedText Formatted(string text, Typeface face, Color ink) =>
        new(text, CultureInfo.InvariantCulture, FlowDirection.LeftToRight, face, FontSize, new SolidColorBrush(ink));
}
