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
/// the frontend's reads expect.
/// </summary>
public sealed class Glass : Control, IScreen
{
    private const double FontSize = 16;
    private const string FontNames = "Cascadia Mono, Consolas, Menlo, DejaVu Sans Mono, monospace";
    private const string Backspace = "\u007f";
    private const string Escape = "\u001b";

    private static readonly FontFamily Family = new(FontNames);
    private static readonly Typeface Roman = new(Family);
    private static readonly Typeface Bold = new(Family, FontStyle.Normal, FontWeight.Bold);
    private static readonly Typeface Italic = new(Family, FontStyle.Italic);
    private static readonly Typeface BoldItalic = new(Family, FontStyle.Italic, FontWeight.Bold);
    private static readonly Color Ink = Color.FromRgb(0xE6, 0xE6, 0xE6);
    private static readonly Cell Blank = new(" ", ScreenModel.Roman, ScreenModel.DefaultColour, ScreenModel.DefaultColour, 1);
    private static readonly Color Paper = Colors.Black;

    // The §8.3.1 colours, in the reference's palette.
    private static readonly Dictionary<int, Color> Palette = new()
    {
        [2] = Color.FromRgb(0, 0, 0),
        [3] = Color.FromRgb(204, 0, 0),
        [4] = Color.FromRgb(0, 204, 0),
        [5] = Color.FromRgb(204, 204, 0),
        [6] = Color.FromRgb(0, 0, 204),
        [7] = Color.FromRgb(204, 0, 204),
        [8] = Color.FromRgb(0, 204, 204),
        [9] = Color.FromRgb(255, 255, 255),
        [10] = Color.FromRgb(181, 181, 181),
        [11] = Color.FromRgb(139, 139, 139),
        [12] = Color.FromRgb(90, 90, 90),
    };

    private static readonly Dictionary<Key, string> Keys = new()
    {
        [Key.Enter] = "\n",
        [Key.Back] = Backspace,
        [Key.Escape] = Escape,
        [Key.Up] = LineEditor.CursorUp,
        [Key.Down] = LineEditor.CursorDown,
        [Key.Left] = LineEditor.CursorLeft,
        [Key.Right] = LineEditor.CursorRight,
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

    public Glass()
    {
        Focusable = true;
        Cursor = new Cursor(StandardCursorType.Ibeam);
    }

    /// <summary>The width in cells the control's bounds allow.</summary>
    public int Columns => _columns;

    /// <summary>The height in rows the control's bounds allow.</summary>
    public int Lines => _lines;

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

    // The machine's thread waits here for the keyboard. A retired
    // glass wakes it with a cancellation instead of a key.
    public string? ReadKey(double? timeoutSeconds)
    {
        lock (_typed)
        {
            var generation = _generation;
            var clock = Stopwatch.StartNew();

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

        var cell = CellSize();
        context.FillRectangle(new SolidColorBrush(Paper), new Rect(Bounds.Size));

        for (var row = 0; row < rows.Length; row++)
        {
            DrawRow(context, rows[row], row, cell);
        }

        // The cursor sits in reverse on its cell; parked past a row's
        // end, as the model allows, it shows on the last cell.
        if (cursor.Row <= rows.Length)
        {
            var line = rows[cursor.Row - 1];
            var column = Math.Min(cursor.Column, line.Length);
            var under = line[column - 1];
            var (character, style) = Glyphs.Appearance(under);
            var (ink, paper) = Colours(under, style ^ ScreenModel.Reverse);
            DrawRun(context, character, column - 1, cursor.Row - 1, cell, ink, paper, style);
        }

        if (overlay is { } laid)
        {
            DrawRun(context, laid.Prompt, laid.Column - 1, laid.Row - 1, cell, Paper, Ink, ScreenModel.Roman);
        }
    }

    protected override void OnSizeChanged(SizeChangedEventArgs e)
    {
        base.OnSizeChanged(e);
        var cell = CellSize();
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

    private Size CellSize()
    {
        if (_cell is null)
        {
            var probe = Formatted("M", Roman, Ink);
            _cell = new Size(probe.Width, probe.Height);
        }

        return _cell.Value;
    }

    // A row paints as runs of cells dressed alike: one background
    // rectangle and one text run each.
    private static void DrawRow(DrawingContext context, Cell[] cells, int row, Size cell)
    {
        var column = 0;

        while (column < cells.Length)
        {
            var (character, style) = Glyphs.Appearance(cells[column]);
            var (ink, paper) = Colours(cells[column], style);
            var run = new StringBuilder(character);
            var start = column;
            column++;

            while (column < cells.Length)
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

    // The colours a cell shows: its own §8.3.1 codes, the defaults
    // where it names none, swapped when the style is reverse.
    private static (Color Ink, Color Paper) Colours(Cell cell, int style)
    {
        var ink = Palette.TryGetValue(cell.Foreground, out var foreground) ? foreground : Ink;
        var paper = Palette.TryGetValue(cell.Background, out var background) ? background : Paper;
        return (style & ScreenModel.Reverse) != 0 ? (paper, ink) : (ink, paper);
    }

    private static FormattedText Formatted(string text, Typeface face, Color ink) =>
        new(text, CultureInfo.InvariantCulture, FlowDirection.LeftToRight, face, FontSize, new SolidColorBrush(ink));
}
