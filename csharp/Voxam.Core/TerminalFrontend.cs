using System.Globalization;
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

/// <summary>How a cell looks on a screen that has no font 3 of its own (§16).</summary>
public static class Glyphs
{
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

    /// <summary>
    /// The character and style one cell paints as: font 3 cells
    /// translate to their stand-ins, and a blank never paints bold.
    /// </summary>
    public static (string Character, int Style) Appearance(Cell cell)
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
}

/// <summary>A terminal as a screen: rows painted as ANSI sequences, the cursor moved by escape.</summary>
public sealed class AnsiScreen(ITerminal terminal) : IScreen
{
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

    public int Width => terminal.Width;

    public int Height => terminal.Height;

    public string? ReadKey(double? timeoutSeconds) => terminal.ReadKey(timeoutSeconds);

    public void Paint(ScreenModel model, int row)
    {
        var pieces = new StringBuilder(MoveTo(row, 1));
        (int Style, int Foreground, int Background)? dress = null;

        for (var column = 1; column <= model.Columns; column++)
        {
            var cell = model.CellAt(row, column);
            var (character, style) = Glyphs.Appearance(cell);
            var wanted = (style, cell.Foreground, cell.Background);

            if (wanted != dress)
            {
                pieces.Append(Sequences(style, cell));
                dress = wanted;
            }

            pieces.Append(character);
        }

        pieces.Append(Normal);
        terminal.Write(pieces.ToString());
    }

    public void Park(int row, int column) => terminal.Write(MoveTo(row, column));

    public void Overlay(int row, int column, string prompt) =>
        terminal.Write(MoveTo(row, column) + Normal + ReverseVideo + prompt + Normal);

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
            pieces.Append(CultureInfo.InvariantCulture, $"\u001b[{30 + foreground}m");
        }

        if (AnsiColours.TryGetValue(cell.Background, out var background))
        {
            pieces.Append(CultureInfo.InvariantCulture, $"\u001b[{40 + background}m");
        }

        return pieces.ToString();
    }

    private static string MoveTo(int row, int column) => $"\u001b[{row};{column}H";
}

/// <summary>The painted terminal: the screen frontend over an ANSI terminal.</summary>
public sealed class TerminalFrontend(int version, ITerminal terminal) : ScreenFrontend(version, new AnsiScreen(terminal))
{
}
