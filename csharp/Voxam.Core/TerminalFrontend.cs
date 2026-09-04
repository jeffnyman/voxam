using System.Diagnostics;
using System.Text;

namespace Voxam.Core;

/// <summary>The sliver of a terminal the painter needs: its size, a place to write, and raw keys.</summary>
public interface ITerminal
{
    /// <summary>The width in characters, 0 when unknown.</summary>
    int Width { get; }

    /// <summary>The height in lines, 0 when unknown.</summary>
    int Height { get; }

    void Write(string text);

    /// <summary>
    /// One keystroke, translated: "\n" for enter, U+007F for
    /// backspace, U+001B for escape, the §3.8.4 cursor codes, or a
    /// single character. With a timeout in seconds, null when it
    /// expires; null also for an unusable key.
    /// </summary>
    string? ReadKey(double? timeoutSeconds);
}

/// <summary>
/// A frontend that keeps a screen model and paints it live on a
/// terminal, ported from the reference's painter: every operation
/// updates the model first, then the damaged rows are redrawn in
/// place, and the capability flags tell the header what this makes
/// true.
/// </summary>
public sealed class TerminalFrontend : IFrontend, ILineCanvas
{
    private const int FallbackColumns = 80;
    private const int FallbackLines = 24;
    private const string MorePrompt = "[MORE]";
    private const string Normal = "\u001b[0m";
    private const string ReverseVideo = "\u001b[7m";
    private const string BoldType = "\u001b[1m";
    private const string ItalicType = "\u001b[3m";

    // The §8.3.1 colour codes with a terminal name: 2 to 9 are the
    // eight ANSI colours, in the Standard's order.
    private static readonly Dictionary<int, int> AnsiColours = new()
    {
        [2] = 0,
        [3] = 1,
        [4] = 2,
        [5] = 3,
        [6] = 4,
        [7] = 5,
        [8] = 6,
        [9] = 7,
    };

    // Font 3's shapes as Unicode stand-ins (§16); four reverse-video
    // shapes flip reverse instead of carrying it in the glyph.
    private static readonly Dictionary<string, string> Font3 = new()
    {
        [" "] = " ",
        ["!"] = "←",
        ["\""] = "→",
        ["#"] = "╱",
        ["$"] = "╲",
        ["%"] = " ",
        ["&"] = "─",
        ["'"] = "─",
        ["("] = "│",
        [")"] = "│",
        ["*"] = "┴",
        ["+"] = "┬",
        [","] = "├",
        ["-"] = "┤",
        ["."] = "└",
        ["/"] = "┌",
        ["0"] = "┐",
        ["1"] = "┘",
        ["2"] = "└",
        ["3"] = "┌",
        ["4"] = "┐",
        ["5"] = "┘",
        ["6"] = "█",
        ["7"] = "▀",
        ["8"] = "▄",
        ["9"] = "▌",
        [":"] = "▐",
        [";"] = "▄",
        ["<"] = "▀",
        ["="] = "▌",
        [">"] = "▐",
        ["?"] = "▝",
        ["@"] = "▗",
        ["A"] = "▖",
        ["B"] = "▘",
        ["C"] = "▝",
        ["D"] = "▗",
        ["E"] = "▖",
        ["F"] = "▘",
        ["G"] = "╱",
        ["H"] = "╲",
        ["I"] = "╱",
        ["J"] = "╲",
        ["K"] = "▔",
        ["L"] = "▁",
        ["M"] = "▏",
        ["N"] = "▕",
        ["O"] = "═",
        ["P"] = "▏",
        ["Q"] = "▎",
        ["R"] = "▍",
        ["S"] = "▌",
        ["T"] = "▋",
        ["U"] = "▊",
        ["V"] = "▉",
        ["W"] = "█",
        ["X"] = "▕",
        ["Y"] = "▏",
        ["Z"] = "╳",
        ["["] = "┼",
        ["\\"] = "↑",
        ["]"] = "↓",
        ["^"] = "↕",
        ["_"] = "□",
        ["`"] = "?",
        ["a"] = "ᚪ",
        ["b"] = "ᛒ",
        ["c"] = "ᛇ",
        ["d"] = "ᛞ",
        ["e"] = "ᛖ",
        ["f"] = "ᚠ",
        ["g"] = "ᚷ",
        ["h"] = "ᚻ",
        ["i"] = "ᛁ",
        ["j"] = "ᛄ",
        ["k"] = "ᛣ",
        ["l"] = "ᛚ",
        ["m"] = "ᛗ",
        ["n"] = "ᚾ",
        ["o"] = "ᚩ",
        ["p"] = "ᛈ",
        ["q"] = "ᚳ",
        ["r"] = "ᚱ",
        ["s"] = "ᛋ",
        ["t"] = "ᛏ",
        ["u"] = "ᚢ",
        ["v"] = "ᛠ",
        ["w"] = "ᚹ",
        ["x"] = "ᛉ",
        ["y"] = "ᚣ",
        ["z"] = "ᛟ",
    };

    private static readonly Dictionary<string, string> Font3Reversed = new()
    {
        ["{"] = "↑",
        ["|"] = "↓",
        ["}"] = "↕",
        ["~"] = "?",
    };

    private readonly ITerminal _terminal;
    private readonly ScreenModel _model;
    private readonly LineEditor _editor = new();
    private bool _composing;
    private string _prompt = "";

    public TerminalFrontend(int version, ITerminal terminal)
    {
        _terminal = terminal;
        ScreenColumns = terminal.Width > 0 ? terminal.Width : FallbackColumns;
        ScreenLines = terminal.Height > 0 ? terminal.Height : FallbackLines;
        _model = new ScreenModel(ScreenColumns, ScreenLines, version) { More = Pause };
    }

    /// <summary>The screen model this painter keeps faithful.</summary>
    public ScreenModel Model => _model;

    /// <summary>Told when the terminal's size changed, so the header's §8.4 fields can follow.</summary>
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
            var key = _terminal.ReadKey(timeoutSeconds);

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
        return _editor.ReadLine(this, () => _terminal.ReadKey(null), Repaint, fresh)!;
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
            return remaining <= 0 ? LineEditor.Expired : _terminal.ReadKey(remaining);
        }

        var fresh = !_composing;
        var line = _editor.ReadLine(this, TickingKey, Repaint, fresh);
        _composing = line is null;
        return line;
    }

    /// <summary>Paint the model's every row over the glass.</summary>
    public void Clear()
    {
        SyncTerminalSize();

        for (var row = 1; row <= _model.Lines; row++)
        {
            PaintRow(row);
        }
    }

    private bool SyncTerminalSize()
    {
        var columns = _terminal.Width > 0 ? _terminal.Width : ScreenColumns;
        var lines = _terminal.Height > 0 ? _terminal.Height : ScreenLines;

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
        SyncTerminalSize();

        foreach (var row in _model.Sweep())
        {
            PaintRow(row);
        }

        Park();
    }

    private void PaintRow(int row)
    {
        var pieces = new StringBuilder(MoveTo(row, 1));
        (int Style, int Foreground, int Background)? dress = null;

        for (var column = 1; column <= _model.Columns; column++)
        {
            var cell = _model.CellAt(row, column);
            var (character, style) = Appearance(cell);
            var wanted = (style, cell.Foreground, cell.Background);

            if (wanted != dress)
            {
                pieces.Append(Sequences(style, cell));
                dress = wanted;
            }

            pieces.Append(character);
        }

        pieces.Append(Normal);
        _terminal.Write(pieces.ToString());
    }

    // The character and style one cell paints as (§16): font 3 cells
    // translate to their stand-ins, and a blank never paints bold.
    private static (string Character, int Style) Appearance(Cell cell)
    {
        if (cell.Font != 3)
        {
            var style = cell.Style;

            if (cell.Character == " ")
            {
                style &= ~ScreenModel.Bold;
            }

            return (cell.Character, style);
        }

        if (Font3Reversed.TryGetValue(cell.Character, out var reversed))
        {
            return (reversed, cell.Style ^ ScreenModel.Reverse);
        }

        return (Font3.TryGetValue(cell.Character, out var shape) ? shape : cell.Character, cell.Style);
    }

    private static string Sequences(int style, Cell cell)
    {
        var pieces = new StringBuilder(Normal);

        if ((style & ScreenModel.Reverse) != 0)
        {
            pieces.Append(ReverseVideo);
        }

        if ((style & ScreenModel.Bold) != 0)
        {
            pieces.Append(BoldType);
        }

        if ((style & ScreenModel.Italic) != 0)
        {
            pieces.Append(ItalicType);
        }

        if (AnsiColours.TryGetValue(cell.Foreground, out var foreground))
        {
            pieces.Append($"\u001b[{30 + foreground}m");
        }

        if (AnsiColours.TryGetValue(cell.Background, out var background))
        {
            pieces.Append($"\u001b[{40 + background}m");
        }

        return pieces.ToString();
    }

    private static string MoveTo(int row, int column) => $"\u001b[{row};{column}H";

    private void Park()
    {
        var (row, column) = _model.Cursor;
        _terminal.Write(MoveTo(row, column));
    }

    // Hold a screenful behind [MORE] until any key arrives: the damage
    // paints first, the prompt overlays the cursor in reverse video,
    // and repainting the row from the model erases it without a trace.
    private void Pause()
    {
        foreach (var damaged in _model.Sweep())
        {
            PaintRow(damaged);
        }

        var (row, column) = _model.Cursor;
        column = Math.Min(column, Math.Max(_model.Columns - MorePrompt.Length + 1, 1));
        _terminal.Write(MoveTo(row, column) + Normal + ReverseVideo + MorePrompt + Normal);

        while (_terminal.ReadKey(null) is null)
        {
        }

        PaintRow(row);
        Park();
    }
}
