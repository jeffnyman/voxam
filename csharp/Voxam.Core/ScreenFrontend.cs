using System.Diagnostics;

namespace Voxam.Core;

/// <summary>
/// The sliver of a display a screen frontend needs: its size in
/// cells, raw keys, and three ways to show the model. A row is
/// painted as it now stands, the cursor is parked at a cell, and a
/// prompt is laid over a row until that row is painted again.
/// </summary>
public interface IScreen
{
    /// <summary>The width in cells, 0 when unknown.</summary>
    int Width { get; }

    /// <summary>The height in rows, 0 when unknown.</summary>
    int Height { get; }

    /// <summary>
    /// One keystroke, translated: "\n" for enter, U+007F for
    /// backspace, U+001B for escape, the §3.8.4 cursor codes, or a
    /// single character. With a timeout in seconds, null when it
    /// expires; null also for an unusable key.
    /// </summary>
    string? ReadKey(double? timeoutSeconds);

    /// <summary>Show one row of the model as it stands, erasing any prompt laid over it.</summary>
    void Paint(ScreenModel model, int row);

    /// <summary>Put the cursor at a cell.</summary>
    void Park(int row, int column);

    /// <summary>Lay a prompt over a row, from a column, until the row is painted again.</summary>
    void Overlay(int row, int column, string prompt);
}

/// <summary>
/// A frontend that keeps a screen model and shows it live on a
/// screen, ported from the reference's painter: every operation
/// updates the model first, then the damaged rows are painted in
/// place, and the capability flags tell the header what this makes
/// true. The terminal and the window are two screens under it.
/// </summary>
public class ScreenFrontend : IFrontend, ILineCanvas
{
    private const int FallbackColumns = 80;
    private const int FallbackLines = 24;
    private const string MorePrompt = "[MORE]";

    private readonly IScreen _screen;
    private readonly ScreenModel _model;
    private readonly LineEditor _editor = new();
    private bool _composing;
    private string _prompt = "";

    public ScreenFrontend(int version, IScreen screen)
    {
        _screen = screen;
        ScreenColumns = screen.Width > 0 ? screen.Width : FallbackColumns;
        ScreenLines = screen.Height > 0 ? screen.Height : FallbackLines;
        _model = new ScreenModel(ScreenColumns, ScreenLines, version) { More = Pause };
    }

    /// <summary>The screen model this painter keeps faithful.</summary>
    public ScreenModel Model => _model;

    /// <summary>Told when the screen's size changed, so the header's §8.4 fields can follow.</summary>
    public Action? OnResize { get; set; }

    public bool HasStatusLine => true;
    public bool HasScreenSplitting => true;
    public bool HasSounds => false;
    public bool HasBold => true;
    public bool HasItalic => true;
    public bool HasFixedPitch => true;
    public bool HasTimedInput => true;
    public bool HasColours => true;
    public bool HasCharacterGraphics => true;
    public int ScreenLines { get; private set; }
    public int ScreenColumns { get; private set; }
    public int FontWidth => 1;
    public int FontHeight => 1;

    public void Write(string text)
    {
        _model.Write(text);
        Repaint();
    }

    public void WriteRectangle(IReadOnlyList<string> rows)
    {
        _model.WriteRectangle(rows);
        Repaint();
    }

    public void ShowStatus(Status status)
    {
        _model.ShowStatus(status);
        Repaint();
    }

    public void SetStyle(int style) => _model.SetStyle(style);

    public void SetFont(int font) => _model.SetFont(font);

    public void SetColour(int foreground, int background) => _model.SetColour(foreground, background);

    public void SetBuffering(bool buffered) => _model.SetBuffering(buffered);

    public void EraseWindow(int window)
    {
        _model.EraseWindow(window);
        Repaint();
    }

    public void EraseLine()
    {
        _model.EraseLine();
        Repaint();
    }

    public void SplitWindow(int lines)
    {
        _model.SplitWindow(lines);
        Repaint();
    }

    public void SetWindow(int window)
    {
        _model.SetWindow(window);
        Repaint();
    }

    public void SetCursor(int line, int column)
    {
        _model.SetCursor(line, column);
        Repaint();
    }

    public (int Line, int Column) CursorPosition() => _model.GetCursor();

    /// <summary>Remember the prompt: the line's text left of the cursor.</summary>
    public void BeginInput()
    {
        var (row, column) = _model.Cursor;
        var text = _model.RowText(row);
        _prompt = text[..Math.Min(column - 1, text.Length)];
    }

    /// <summary>Show the prompt again after a printing interrupt (§15 read remarks).</summary>
    public void ResumeInput()
    {
        _model.Write(_prompt);
        Repaint();
    }

    /// <summary>Erase the half-typed line a terminated timed read leaves.</summary>
    public void AbandonInput()
    {
        if (!_composing)
        {
            return;
        }

        var pending = _editor.Text.Length;
        _model.Retreat(_editor.Cursor);
        _model.Write(new string(' ', pending));
        _model.Retreat(pending);
        _editor.Begin();
        _composing = false;
        Repaint();
    }

    int ILineCanvas.Retreat(int cells) => _model.Retreat(cells);

    /// <summary>Read one raw keystroke at the model's cursor, never echoed.</summary>
    public string? ReadKey(double? timeoutSeconds)
    {
        _model.Rest();
        Park();

        while (true)
        {
            var key = _screen.ReadKey(timeoutSeconds);

            if (key is not null)
            {
                return key;
            }

            if (timeoutSeconds is not null)
            {
                return null;
            }
        }
    }

    /// <summary>Read one line, edited and echoed through the model.</summary>
    public string ReadLine()
    {
        _model.Rest();
        Park();
        var fresh = !_composing;
        _composing = false;
        return _editor.ReadLine(this, () => _screen.ReadKey(null), Repaint, fresh)!;
    }

    /// <summary>Read a line on the clock, or null when the wait expires with the line kept composed.</summary>
    public string? ReadLineUntil(double seconds)
    {
        _model.Rest();
        Park();
        var started = Stopwatch.StartNew();

        string? TickingKey()
        {
            var remaining = seconds - started.Elapsed.TotalSeconds;
            return remaining <= 0 ? LineEditor.Expired : _screen.ReadKey(remaining);
        }

        var fresh = !_composing;
        var line = _editor.ReadLine(this, TickingKey, Repaint, fresh);
        _composing = line is null;
        return line;
    }

    /// <summary>Paint the model's every row over the screen.</summary>
    public void Clear()
    {
        SyncScreenSize();

        for (var row = 1; row <= _model.Lines; row++)
        {
            _screen.Paint(_model, row);
        }
    }

    private bool SyncScreenSize()
    {
        var columns = _screen.Width > 0 ? _screen.Width : ScreenColumns;
        var lines = _screen.Height > 0 ? _screen.Height : ScreenLines;

        if (columns == ScreenColumns && lines == ScreenLines)
        {
            return false;
        }

        ScreenColumns = columns;
        ScreenLines = lines;
        _model.Resize(columns, lines);
        OnResize?.Invoke();
        return true;
    }

    private void Repaint()
    {
        SyncScreenSize();

        foreach (var row in _model.Sweep())
        {
            _screen.Paint(_model, row);
        }

        Park();
    }

    private void Park()
    {
        var (row, column) = _model.Cursor;
        _screen.Park(row, column);
    }

    // Hold a screenful behind [MORE] until any key arrives: the damage
    // paints first, the prompt overlays the cursor, and painting the
    // row from the model again erases it without a trace.
    private void Pause()
    {
        foreach (var damaged in _model.Sweep())
        {
            _screen.Paint(_model, damaged);
        }

        var (row, column) = _model.Cursor;
        column = Math.Min(column, Math.Max(_model.Columns - MorePrompt.Length + 1, 1));
        _screen.Overlay(row, column, MorePrompt);

        while (_screen.ReadKey(null) is null)
        {
        }

        _screen.Paint(_model, row);
        Park();
    }
}
