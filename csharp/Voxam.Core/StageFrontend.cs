using System.Diagnostics;

namespace Voxam.Core;

/// <summary>
/// The sliver of a glass a stage needs: its size in cells, the units
/// one cell measures, raw keys, and somewhere to carry out paints. A
/// stage keeps no shadow of what it drew, because the glass's own
/// pixels are the retained screen (§8.8.3).
/// </summary>
public interface IStageScreen
{
    /// <summary>The width in cells.</summary>
    int Columns { get; }

    /// <summary>The height in cells.</summary>
    int Lines { get; }

    /// <summary>One cell's width in units.</summary>
    int FontWidth { get; }

    /// <summary>One cell's height in units.</summary>
    int FontHeight { get; }

    /// <summary>
    /// One keystroke, translated as the character faces translate
    /// theirs, or null when a timeout expires or the key is unusable.
    /// </summary>
    string? ReadKey(double? timeoutSeconds);

    /// <summary>Carry out paints, in order, on the retained surface.</summary>
    void Settle(IReadOnlyList<Paint> paints);
}

/// <summary>
/// A frontend with a Version 6 stage behind it, which the machine
/// drives through seams the character faces have no use for. The
/// machine asks whether its frontend is one of these before sending
/// any of them, so a plain stream or a painted terminal goes on
/// mimicking §8.8 with its two windows exactly as before.
/// </summary>
public interface IStageFrontend : IFrontend
{
    /// <summary>Place one of the eight windows, in units (§8.8.3.4).</summary>
    void PlaceWindow(int window, int line, int column, int height, int width);

    /// <summary>Set a window's §8.8.3.2.6 line count, which paces its [MORE].</summary>
    void SetLineCount(int window, int count);

    /// <summary>Set a window's margins, in units (§8.8.3.2.1).</summary>
    void SetMargins(int window, int left, int right);

    /// <summary>Scroll a window's own rectangle by a unit amount (§8.8.3.6).</summary>
    void ScrollWindow(int window, int pixels);

    /// <summary>Erase rightward from the cursor across a width in units (§8.8.5.2).</summary>
    void EraseLine(int pixels);
}

/// <summary>
/// The Version 6 face: a stage model kept faithful, and its paints
/// carried out on a glass. Every operation updates the model first,
/// then whatever it drew is settled on the surface, which is how §8.8's
/// retained screen behaves. The glass draws no caret: a Version 6 game
/// places its own.
/// </summary>
public sealed class StageFrontend : IStageFrontend, ILineCanvas
{
    private const string MorePrompt = "[MORE]";

    private readonly IStageScreen _screen;
    private readonly StageModel _model;
    private readonly LineEditor _editor = new();
    private bool _composing;
    private string _prompt = "";

    /// <summary>
    /// Wrap a stage around a glass. A driven session never pauses at
    /// [MORE]: a script is typing, there is nobody to press the key,
    /// and the walk's own pacing is the walk itself.
    /// </summary>
    public StageFrontend(IStageScreen screen, bool driven = false)
    {
        _screen = screen;
        _model = new StageModel(screen.Columns, screen.Lines, screen.FontWidth, screen.FontHeight);

        if (!driven)
        {
            _model.More = Pause;
        }
    }

    /// <summary>The stage this face keeps faithful.</summary>
    public StageModel Model => _model;

    public bool HasStatusLine => false;
    public bool HasScreenSplitting => true;
    public bool HasSounds => false;
    public bool HasBold => true;
    public bool HasItalic => true;
    public bool HasFixedPitch => true;
    public bool HasTimedInput => true;
    public bool HasColours => true;
    public bool HasCharacterGraphics => true;
    public int ScreenLines => _screen.Lines;
    public int ScreenColumns => _screen.Columns;
    public int FontWidth => _screen.FontWidth;
    public int FontHeight => _screen.FontHeight;

    public void Write(string text)
    {
        _model.Write(text);
        Settle();
    }

    public void WriteRectangle(IReadOnlyList<string> rows)
    {
        _model.WriteRectangle(rows);
        Settle();
    }

    /// <summary>
    /// Refuse: a Version 6 game draws its own status area (§8.2), so
    /// the machine never sends one and a stray call is a wiring fault
    /// worth hearing about.
    /// </summary>
    public void ShowStatus(Status status) =>
        throw new ZMachineException("version 6 draws its own status area; the stage has no line (§8.2)");

    public void SetStyle(int style) => _model.SetStyle(style);

    public void SetFont(int font) => _model.SetFont(font);

    public void SetColour(int foreground, int background) => _model.SetColour(foreground, background);

    public void SetBuffering(bool buffered) => _model.SetBuffering(buffered);

    public void SplitWindow(int lines)
    {
        _model.SplitWindow(lines);
        Settle();
    }

    public void SetWindow(int window)
    {
        _model.SetWindow(window);
        Settle();
    }

    public void EraseWindow(int window)
    {
        _model.EraseWindow(window);
        Settle();
    }

    public void EraseLine()
    {
        _model.EraseLine();
        Settle();
    }

    /// <summary>Erase rightward across a width in units (§8.8.5.2).</summary>
    public void EraseLine(int pixels)
    {
        _model.EraseLine(pixels);
        Settle();
    }

    public void SetCursor(int line, int column)
    {
        _model.SetCursor(line, column);
        Settle();
    }

    public (int Line, int Column) CursorPosition() => _model.GetCursor();

    public void PlaceWindow(int window, int line, int column, int height, int width)
    {
        _model.PlaceWindow(window, line, column, height, width);
        Settle();
    }

    public void SetLineCount(int window, int count) => _model.SetLineCount(window, count);

    public void SetMargins(int window, int left, int right)
    {
        _model.SetMargins(window, left, right);
        Settle();
    }

    public void ScrollWindow(int window, int pixels)
    {
        _model.ScrollWindow(window, pixels);
        Settle();
    }

    /// <summary>Remember the prompt: the text left of the cursor on its row.</summary>
    public void BeginInput()
    {
        var (row, column) = CursorCell();
        var text = _model.RowText(row);
        _prompt = text[..Math.Min(column - 1, text.Length)];
    }

    /// <summary>Show the prompt again after a printing interrupt (§15 read remarks).</summary>
    public void ResumeInput()
    {
        _model.Write(_prompt);
        Settle();
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
        Settle();
    }

    int ILineCanvas.Retreat(int cells) => _model.Retreat(cells);

    /// <summary>Read one raw keystroke, never echoed.</summary>
    public string? ReadKey(double? timeoutSeconds)
    {
        _model.Rest();
        Settle();

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

    /// <summary>Read one line, edited and echoed through the stage.</summary>
    public string ReadLine()
    {
        _model.Rest();
        Settle();
        var fresh = !_composing;
        _composing = false;
        return _editor.ReadLine(this, () => _screen.ReadKey(null), Settle, fresh)!;
    }

    /// <summary>Read a line on the clock, or null when the wait expires with the line kept composed.</summary>
    public string? ReadLineUntil(double seconds)
    {
        _model.Rest();
        Settle();
        var started = Stopwatch.StartNew();

        string? TickingKey()
        {
            var remaining = seconds - started.Elapsed.TotalSeconds;
            return remaining <= 0 ? LineEditor.Expired : _screen.ReadKey(remaining);
        }

        var fresh = !_composing;
        var line = _editor.ReadLine(this, TickingKey, Settle, fresh);
        _composing = line is null;
        return line;
    }

    private void Settle()
    {
        var paints = _model.Paints();

        if (paints.Count > 0)
        {
            _screen.Settle(paints);
        }

        _model.Sweep();
    }

    // The selected cursor as a screen cell, for reading back the row a
    // prompt was typed on.
    private (int Row, int Column) CursorCell()
    {
        var (line, column) = _model.ScreenCursor();
        return ((line - 1) / _screen.FontHeight + 1, (column - 1) / _screen.FontWidth + 1);
    }

    // Hold the scroll behind [MORE] until a key arrives. Everything
    // painted so far settles first, then the prompt appears at the
    // pause position wearing the window's own colours reversed. The key
    // that answers is spent, never passed to the story (§8.8.3.2.6),
    // and the prompt's patch is rebuilt from the stage's own grid,
    // because the pause can land on freshly flowed text and a blind
    // erase would burn a box over it.
    private void Pause(int line, int column, int foreground, int background)
    {
        Settle();
        var prompt = new List<Paint>();

        for (var offset = 0; offset < MorePrompt.Length; offset++)
        {
            var dress = new Cell(MorePrompt[offset].ToString(), ScreenModel.Reverse, foreground, background, 1);
            prompt.Add(new TextPaint(line, column + offset * _screen.FontWidth, dress));
        }

        _screen.Settle(prompt);

        while (_screen.ReadKey(null) is null)
        {
        }

        var repair = new List<Paint>
        {
            new FillPaint(line, column, _screen.FontHeight, MorePrompt.Length * _screen.FontWidth, background),
        };
        var row = (line - 1) / _screen.FontHeight + 1;
        var first = (column - 1) / _screen.FontWidth + 1;

        for (var offset = 0; offset < MorePrompt.Length && first + offset <= _model.Columns; offset++)
        {
            var covered = _model.CellAt(row, first + offset);

            if (covered.Character != " ")
            {
                repair.Add(new TextPaint(line, column + offset * _screen.FontWidth, covered));
            }
        }

        _screen.Settle(repair);
    }
}
