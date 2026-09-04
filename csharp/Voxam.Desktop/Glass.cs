using System.Diagnostics;
using System.Globalization;
using System.Text;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Input;
using Avalonia.Media;
using Avalonia.Media.Imaging;
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
public sealed class Glass : Control, IScreen, IStageScreen, IDisposable
{
    /// <summary>The classic grid the window opens at.</summary>
    public const int OpeningColumns = 80;

    /// <summary>The classic grid's height, the reference's GLASS_LINES.</summary>
    public const int OpeningLines = 24;

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
    private double _size = Preferences.Default.Size;
    private int _dirty;
    private volatile int _columns;
    private volatile int _lines;
    private volatile bool _waiting;
    private (int Columns, int Lines, int Width, int Height)? _pinned;
    private RenderTargetBitmap? _surface;
    private RenderTargetBitmap? _scratch;
    private readonly Dictionary<byte[], Bitmap> _decoded = new(ReferenceEqualityComparer.Instance);

    public Glass()
    {
        Focusable = true;
        Cursor = new Cursor(StandardCursorType.Ibeam);
    }

    /// <summary>The ink and paper the glass wears where a game names none.</summary>
    public Theme Look { get; set; } = Voxam.Desktop.Theme.Dark;

    /// <summary>
    /// The type's size in points. Changing it re-measures the cell, so
    /// the grid grows or shrinks; a Version 6 stage keeps the metrics
    /// it was born with until the next story, because its own surface
    /// is drawn in those units.
    /// </summary>
    public double Size
    {
        get => _size;

        set
        {
            _size = value;
            _cell = null;
            InvalidateMeasure();
            InvalidateVisual();
        }
    }

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
                var probe = Formatted("M", Roman, Look.Ink, _size);
                _cell = new Size(probe.Width, probe.Height);
            }

            return _cell.Value;
        }
    }

    /// <summary>Whether the machine is parked in a read, which is when the caret shows.</summary>
    public bool Waiting => _waiting;

    int IScreen.Width => _columns;

    int IScreen.Height => _lines;

    int IStageScreen.Columns => _columns;

    int IStageScreen.Lines => _lines;

    int IStageScreen.FontWidth => UnitWidth;

    int IStageScreen.FontHeight => UnitHeight;

    private int UnitWidth => _pinned?.Width ?? Math.Max((int)Math.Round(CellSize.Width), 1);

    private int UnitHeight => _pinned?.Height ?? Math.Max((int)Math.Round(CellSize.Height), 1);

    private Size UnitCell => new(UnitWidth, UnitHeight);

    /// <summary>
    /// Carry out a Version 6 stage's paints on the retained surface,
    /// which is §8.8.3's screen made literal: what is drawn stays drawn
    /// until something else is drawn over it.
    /// </summary>
    public void Settle(IReadOnlyList<Paint> paints)
    {
        var cell = UnitCell;
        var surface = Surface();
        var pending = 0;

        while (pending < paints.Count)
        {
            // A shift slides pixels the surface already holds, so it
            // reads through a scratch copy rather than itself; the runs
            // between shifts share one drawing context.
            var run = pending;

            while (run < paints.Count && paints[run] is not ShiftPaint)
            {
                run++;
            }

            if (run > pending)
            {
                using var context = surface.CreateDrawingContext(false);

                for (var at = pending; at < run; at++)
                {
                    Perform(context, paints[at], cell);
                }
            }

            if (run < paints.Count)
            {
                Slide(surface, (ShiftPaint)paints[run]);
                run++;
            }

            pending = run;
        }

        Invalidate();
    }

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

        if (_surface is { } stage)
        {
            context.DrawImage(stage, new Rect(stage.Size));
            return;
        }

        for (var row = 0; row < rows.Length; row++)
        {
            DrawRow(context, rows[row], row, cell);
        }

        // The caret underlines the cursor's cell in its own ink while
        // the machine waits for typing. Only the cell face reaches
        // here, and it paints every row before its first wait, so the
        // cursor always has one; parked past a row's end, as the model
        // allows, it shows on the last cell. A Version 6 stage draws
        // no caret: its games place their own.
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

    /// <summary>
    /// The classic grid, as what the control asks for, measured in the
    /// same whole units the grid is counted in so the two agree.
    /// </summary>
    protected override Size MeasureOverride(Size availableSize) =>
        new(OpeningColumns * UnitWidth, OpeningLines * UnitHeight);

    // The grid counts in whole units, the same units a stage measures
    // its windows in, so a surface of that many never overruns the
    // control it is drawn on.
    protected override void OnSizeChanged(SizeChangedEventArgs e)
    {
        base.OnSizeChanged(e);
        _columns = (int)(e.NewSize.Width / UnitWidth);
        _lines = (int)(e.NewSize.Height / UnitHeight);
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

    private void DrawRun(DrawingContext context, string text, int column, int row, Size cell, Color ink, Color paper, int style) =>
        DrawRun(context, text, column, row, cell, ink, paper, style, _size);

    private static void DrawRun(DrawingContext context, string text, int column, int row, Size cell, Color ink, Color paper, int style, double size)
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
        context.DrawText(Formatted(text, face, ink, size), origin);
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

    // The retained surface, minted at the size the stage was built for
    // and kept for the story's whole life.
    private RenderTargetBitmap Surface()
    {
        if (_surface is null)
        {
            // A stage pins the grid it was built for; anything else
            // settling here takes the glass as it stands.
            var (columns, lines) = _pinned is { } pinned ? (pinned.Columns, pinned.Lines) : (_columns, _lines);
            var size = new PixelSize(Math.Max(columns * UnitWidth, 1), Math.Max(lines * UnitHeight, 1));
            _surface = new RenderTargetBitmap(size);
            _scratch = new RenderTargetBitmap(size);

            using var context = _surface.CreateDrawingContext(false);
            context.FillRectangle(new SolidColorBrush(Look.Paper), new Rect(0, 0, size.Width, size.Height));
        }

        return _surface;
    }

    /// <summary>Let go of the surfaces a stage drew on.</summary>
    public void Dispose() => Strike();

    /// <summary>
    /// Hold the grid at the size a stage was built for. A stage cannot
    /// follow a window that changes size, so its surface is minted at
    /// its own geometry and the two can never disagree; a window grown
    /// afterwards shows the stage at its own size, as a fixed window
    /// always did.
    /// </summary>
    public void Pin(int columns, int lines)
    {
        _pinned = (columns, lines, UnitWidth, UnitHeight);
        // The surface is minted here rather than at the first paint,
        // so a stage always has one to show: what follows the early
        // return in Render is the cell face's own, where every row has
        // been painted before the first wait.
        Surface();
    }

    /// <summary>Let go of a stage's surface, so the next story starts on a clean one.</summary>
    public void Strike()
    {
        _pinned = null;
        _cell = null;
        _surface?.Dispose();
        _scratch?.Dispose();
        _surface = null;
        _scratch = null;

        foreach (var art in _decoded.Values)
        {
            art.Dispose();
        }

        _decoded.Clear();
        Invalidate();
    }

    private void Perform(DrawingContext context, Paint paint, Size cell)
    {
        switch (paint)
        {
            case PicturePaint picture:
                {
                    // The pixels stretch to the size picture_data
                    // reported, kept square-shouldered the way a 1988
                    // monitor drew them, and whatever is clear in them
                    // stays see-through.
                    if (Decoded(picture.Pixels) is not { } art)
                    {
                        return;
                    }

                    var room = new Rect(picture.Column - 1, picture.Line - 1, picture.Width, picture.Height);
                    using var square = context.PushRenderOptions(new RenderOptions { BitmapInterpolationMode = BitmapInterpolationMode.None });
                    context.DrawImage(art, new Rect(art.Size), room);
                    return;
                }

            case TextPaint text:
                {
                    var (character, style) = Glyphs.Appearance(text.Cell);
                    var (ink, paper) = Colours(text.Cell, style);
                    var origin = new Point(text.Column - 1, text.Line - 1);
                    context.FillRectangle(new SolidColorBrush(paper), new Rect(origin, cell));

                    if (text.Cell.Font == GraphicsFont && Font3.Bitmap(text.Cell.Character) is { } bitmap)
                    {
                        Tile(context, bitmap, origin, cell, ink);
                        return;
                    }

                    var face = (style & ScreenModel.Bold, style & ScreenModel.Italic) switch
                    {
                        (0, 0) => Roman,
                        (_, 0) => Bold,
                        (0, _) => Italic,
                        _ => BoldItalic,
                    };
                    context.DrawText(Formatted(character, face, ink, _size), origin);
                    return;
                }

            default:
                {
                    var fill = (FillPaint)paint;
                    var brush = new SolidColorBrush(Resolve(fill.Background, Look.Paper));
                    context.FillRectangle(brush, new Rect(fill.Column - 1, fill.Line - 1, fill.Width, fill.Height));
                    return;
                }
        }
    }

    // A shift reads the pixels the surface already holds, through a
    // scratch copy, and lays them back down risen (§8.8.3.6).
    private void Slide(RenderTargetBitmap surface, ShiftPaint shift)
    {
        var scratch = _scratch!;

        using (var copy = scratch.CreateDrawingContext(false))
        {
            copy.DrawImage(surface, new Rect(surface.Size));
        }

        var source = new Rect(shift.Column - 1, shift.Line - 1, shift.Width, shift.Height);
        var landing = source.WithY(source.Y - shift.Rise);
        // The surface keeps everything else it holds: only the band the
        // shift names is laid down again, risen.
        using var context = surface.CreateDrawingContext(false);
        using var clip = context.PushClip(source);
        context.DrawImage(scratch, source, landing);
    }

    // A picture's pixels, decoded once and remembered. Art this glass
    // cannot decode is ignored where it lands: presentation, never
    // state.
    private Bitmap? Decoded(byte[] pixels)
    {
        if (_decoded.TryGetValue(pixels, out var art))
        {
            return art;
        }

        try
        {
            art = new Bitmap(new MemoryStream(pixels));
        }
        catch (Exception error) when (error is ArgumentException or NotSupportedException)
        {
            return null;
        }

        _decoded[pixels] = art;
        return art;
    }

    private static void Tile(DrawingContext context, byte[] bitmap, Point origin, Size cell, Color ink)
    {
        var brush = new SolidColorBrush(ink);

        for (var y = 0; y < Font3.Rows; y++)
        {
            var y0 = Math.Round(origin.Y + y * cell.Height / Font3.Rows);
            var y1 = Math.Round(origin.Y + (y + 1) * cell.Height / Font3.Rows);

            for (var x = 0; x < Font3.Pixels; x++)
            {
                if (Font3.Lit(bitmap, x, y))
                {
                    var x0 = Math.Round(origin.X + x * cell.Width / Font3.Pixels);
                    var x1 = Math.Round(origin.X + (x + 1) * cell.Width / Font3.Pixels);
                    context.FillRectangle(brush, new Rect(x0, y0, x1 - x0, y1 - y0));
                }
            }
        }
    }

    private static FormattedText Formatted(string text, Typeface face, Color ink, double size) =>
        new(text, CultureInfo.InvariantCulture, FlowDirection.LeftToRight, face, size, new SolidColorBrush(ink));
}
