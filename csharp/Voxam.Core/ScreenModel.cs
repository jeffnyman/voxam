using System.Text;

namespace Voxam.Core;

/// <summary>What the Version 1 to 3 status line shows (§8.2).</summary>
public readonly record struct Status(string Location, int Score, int Turns, bool TimeGame);

/// <summary>One character position on the screen with its dress (§8.7.1).</summary>
public readonly record struct Cell(
    string Character = " ",
    int Style = ScreenModel.Roman,
    int Foreground = ScreenModel.DefaultColour,
    int Background = ScreenModel.DefaultColour,
    int Font = 1);

/// <summary>
/// A pure §8 screen: two windows, one grid, no terminal, ported from
/// the reference's screen model. Rows and columns are 1-based with
/// (1,1) at the top left. In Version 3 the top row belongs to the
/// interpreter's status line and the upper window hangs below it;
/// from Version 4 the upper window starts at the top.
/// </summary>
public sealed class ScreenModel
{
    public const int Lower = 0;
    public const int Upper = 1;
    public const int Roman = 0;
    public const int Reverse = 1;
    public const int Bold = 2;
    public const int Italic = 4;
    public const int FixedPitch = 8;
    public const int CurrentColour = 0;
    public const int DefaultColour = 1;
    private const int StatusLastVersion = 3;
    private const int WindowsFirstVersion = 3;
    private const int BottomHomeLastVersion = 4;
    private const int EraseUnsplit = -1;
    private const int EraseKeepSplit = -2;

    // Spelled out: a struct's new() is its zero value, whose character
    // would be null rather than a space.
    private static readonly Cell Blank = new(" ", Roman, DefaultColour, DefaultColour, 1);

    private readonly int _version;
    private Cell[][] _grid;
    private int _split;
    private int _selected = Lower;
    private int _style = Roman;
    private int _font = 1;
    private int _foreground = DefaultColour;
    private int _background = DefaultColour;
    private bool _buffered = true;
    private readonly List<Cell> _pending = [];
    private bool _scrollDue;
    private readonly SortedSet<int> _damage = [];
    private Status? _status;
    private int _fed;
    private (int Row, int Column) _upperCursor = (1, 1);
    private (int Row, int Column) _lowerCursor;

    /// <summary>Called when a screenful has been fed: the painter's [MORE] pause.</summary>
    public Action? More { get; set; }

    public ScreenModel(int columns = 80, int lines = 24, int version = 3)
    {
        Columns = columns;
        Lines = lines;
        _version = version;
        _grid = Fresh(lines, columns, Blank);
        _lowerCursor = version <= BottomHomeLastVersion ? (lines, 1) : (LowerTop, 1);
    }

    public int Columns { get; private set; }

    public int Lines { get; private set; }

    /// <summary>The upper window's current height in lines (§8.7.2.1).</summary>
    public int Split => _split;

    /// <summary>Which window takes the next printing (§8.7.2).</summary>
    public int Selected => _selected;

    /// <summary>The current §8.3.1 background colour code.</summary>
    public int Background => _background;

    private int UpperTop => _version <= StatusLastVersion ? 2 : 1;

    private int LowerTop => UpperTop + _split;

    private static Cell[][] Fresh(int lines, int columns, Cell blank)
    {
        var grid = new Cell[lines][];

        for (var row = 0; row < lines; row++)
        {
            grid[row] = new Cell[columns];
            Array.Fill(grid[row], blank);
        }

        return grid;
    }

    private void RequireWindows()
    {
        if (_version < WindowsFirstVersion)
        {
            throw new ZMachineException($"version {_version} has no windows: its screen can only be printed to (§8.5.1)");
        }
    }

    /// <summary>Print text to the selected window (§8.7.2).</summary>
    public void Write(string text)
    {
        foreach (var character in Characters(text))
        {
            if (_selected == Upper)
            {
                WriteUpper(character);
            }
            else
            {
                WriteLower(character);
            }
        }
    }

    // Text as printable units: a surrogate pair is one character.
    private static IEnumerable<string> Characters(string text)
    {
        var enumerator = System.Globalization.StringInfo.GetTextElementEnumerator(text);

        while (enumerator.MoveNext())
        {
            yield return enumerator.GetTextElement();
        }
    }

    // Overlay one character at the upper cursor (§8.6.1.1.1): a newline
    // moves to the start of the next window line, stopping at the
    // window's bottom; printing in the last column leaves the cursor put.
    private void WriteUpper(string character)
    {
        var (row, column) = _upperCursor;

        if (character == "\n")
        {
            _upperCursor = (Math.Min(row + 1, Math.Max(_split, 1)), 1);
            return;
        }

        Paint(UpperTop + row - 1, column, Dressed(character));

        if (column < Columns)
        {
            _upperCursor = (row, column + 1);
        }
    }

    // Queue or emit one character for the lower window: while buffering
    // is on, word characters gather so a word that would overrun the
    // margin wraps whole; spaces and newlines flush it.
    private void WriteLower(string character)
    {
        if (character == "\n")
        {
            Flush();
            LineFeed();
        }
        else if (!_buffered)
        {
            Emit(Dressed(character));
        }
        else if (character == " ")
        {
            Flush();
            EmitSpace();
        }
        else
        {
            _pending.Add(Dressed(character));
        }
    }

    private Cell Dressed(string character) => new(character, _style, _foreground, _background, _font);

    // Emit the pending word, wrapping it whole if it fits a line; a word
    // too long for any line simply character-wraps.
    private void Flush()
    {
        if (_pending.Count == 0)
        {
            return;
        }

        var word = _pending.ToArray();
        _pending.Clear();
        var column = _lowerCursor.Column;

        if (word.Length > Columns - column + 1 && word.Length <= Columns)
        {
            LineFeed();
        }

        foreach (var cell in word)
        {
            Emit(cell);
        }
    }

    // A space that would wrap becomes the line break itself.
    private void EmitSpace()
    {
        if (_lowerCursor.Column > Columns)
        {
            LineFeed();
            return;
        }

        Emit(Dressed(" "));
    }

    // Place one cell at the lower cursor, wrapping at the margin; a
    // scroll owed by an earlier line feed happens now (§8.7.3.1).
    private void Emit(Cell cell)
    {
        if (_lowerCursor.Column > Columns)
        {
            LineFeed();
        }

        if (_scrollDue)
        {
            Scroll();
            _scrollDue = false;
        }

        var (row, column) = _lowerCursor;
        Paint(row, column, cell);
        _lowerCursor = (row, column + 1);
    }

    // Move the lower cursor down, owing a scroll at the bottom.
    private void LineFeed()
    {
        if (_scrollDue)
        {
            Scroll();
            _scrollDue = false;
        }

        if (_lowerCursor.Row >= Lines)
        {
            _scrollDue = true;
            _lowerCursor = (Lines, 1);
        }
        else
        {
            _lowerCursor = (_lowerCursor.Row + 1, 1);
        }

        FeedPage();
    }

    // Count one fed line toward a [MORE] pause: a screenful is the lower
    // window's height less the line the prompt stands on.
    private void FeedPage()
    {
        if (More is null)
        {
            return;
        }

        _fed++;

        if (_fed >= Math.Max(Lines - _split - 1, 1))
        {
            _fed = 0;
            More();
        }
    }

    /// <summary>Reset the [MORE] budget: input means everything was read.</summary>
    public void Rest() => _fed = 0;

    // Scroll the lower window up one line; the upper window and the
    // status line never move, and the fresh bottom line is blank.
    private void Scroll()
    {
        var top = LowerTop;

        for (var row = top; row < Lines; row++)
        {
            _grid[row - 1] = _grid[row];
        }

        _grid[Lines - 1] = new Cell[Columns];
        Array.Fill(_grid[Lines - 1], BlankCell());

        for (var row = top; row <= Lines; row++)
        {
            _damage.Add(row);
        }
    }

    private Cell BlankCell() => new(" ", Roman, DefaultColour, _background);

    private void Paint(int row, int column, Cell cell)
    {
        _grid[row - 1][column - 1] = cell;
        _damage.Add(row);
    }

    /// <summary>
    /// Reshape the grid to a new screen size (§8.4), keeping the old
    /// grid's overlap top left aligned, drawing the split and cursors
    /// inside the new bounds, and leaving every row damaged.
    /// </summary>
    public void Resize(int columns, int lines)
    {
        columns = Math.Max(1, columns);
        lines = Math.Max(1, lines);

        if (columns == Columns && lines == Lines)
        {
            return;
        }

        Flush();
        var old = _grid;
        var blank = BlankCell();
        var grid = new Cell[lines][];

        for (var row = 0; row < lines; row++)
        {
            grid[row] = new Cell[columns];

            for (var column = 0; column < columns; column++)
            {
                grid[row][column] = row < old.Length && column < old[row].Length ? old[row][column] : blank;
            }
        }

        _grid = grid;
        Columns = columns;
        Lines = lines;
        _split = Math.Max(0, Math.Min(_split, lines - UpperTop + 1));
        var reach = Math.Max(1, lines - UpperTop + 1);
        _upperCursor = (Math.Min(Math.Max(_upperCursor.Row, 1), reach), Math.Min(Math.Max(_upperCursor.Column, 1), columns));
        var floor = Math.Min(LowerTop, lines);
        _lowerCursor = (Math.Min(Math.Max(_lowerCursor.Row, floor), lines), Math.Min(Math.Max(_lowerCursor.Column, 1), columns));
        _scrollDue = false;
        _fed = 0;
        _damage.Clear();

        for (var row = 1; row <= lines; row++)
        {
            _damage.Add(row);
        }

        if (_status is { } status)
        {
            ShowStatus(status);
        }
    }

    /// <summary>Resize the upper window (§8.7.2.1); Version 3 clears the fresh split.</summary>
    public void SplitWindow(int height)
    {
        RequireWindows();
        Flush();

        if (height < 0 || height > Lines - UpperTop + 1)
        {
            throw new ZMachineException($"an upper window {height} lines tall does not fit a {Lines}-line screen (§8.7.2.1)");
        }

        _split = height;

        if (_version == StatusLastVersion && height > 0)
        {
            ClearRows(UpperTop, UpperTop + height - 1);
        }

        if (_lowerCursor.Row < LowerTop)
        {
            _lowerCursor = (Math.Min(LowerTop, Lines), 1);
        }

        if (_selected == Upper && _upperCursor.Row > Math.Max(height, 1))
        {
            _upperCursor = (1, 1);
        }
    }

    /// <summary>Select a window for printing (§8.7.2); the upper window's cursor homes.</summary>
    public void SetWindow(int window)
    {
        RequireWindows();
        Flush();

        if (window is not (Lower or Upper))
        {
            throw new ZMachineException($"there is no window {window} before version 6 (§8.7.2)");
        }

        _selected = window;

        if (window == Upper)
        {
            _upperCursor = (1, 1);
        }
    }

    /// <summary>Move the upper window's cursor (§8.7.2.3.1); nothing happens in the lower window.</summary>
    public void SetCursor(int line, int column)
    {
        Flush();

        if (_selected != Upper)
        {
            return;
        }

        var reach = Lines - UpperTop + 1;

        if (line < 1 || line > reach || column < 1 || column > Columns)
        {
            throw new ZMachineException(
                $"the cursor cannot move to ({line}, {column}): even §8.7.2.3.1's tolerated overreach past the upper window's {_split} lines ends at the screen, {reach} lines by {Columns}");
        }

        _upperCursor = (line, column);
    }

    /// <summary>The upper window's cursor, from either window (§8.7.2.3.2).</summary>
    public (int Line, int Column) GetCursor()
    {
        Flush();
        return _upperCursor;
    }

    /// <summary>Erase a window to the background colour (§8.7.3.2).</summary>
    public void EraseWindow(int window)
    {
        Flush();

        if (window != Upper)
        {
            _fed = 0;
        }

        switch (window)
        {
            case EraseUnsplit:
                ClearRows(1, Lines);
                _split = 0;
                _selected = Lower;
                HomeLower();
                break;
            case EraseKeepSplit:
                ClearRows(1, Lines);
                break;
            case Lower:
                ClearRows(LowerTop, Lines);
                HomeLower();
                break;
            case Upper:
                ClearRows(UpperTop, UpperTop + _split - 1);
                _upperCursor = (1, 1);
                break;
            default:
                throw new ZMachineException($"there is no window {window} to erase (§15 erase_window)");
        }
    }

    private void ClearRows(int first, int last)
    {
        for (var row = first; row <= last; row++)
        {
            _grid[row - 1] = new Cell[Columns];
            Array.Fill(_grid[row - 1], BlankCell());
            _damage.Add(row);
        }
    }

    private void HomeLower()
    {
        _scrollDue = false;
        _lowerCursor = _version <= BottomHomeLastVersion ? (Lines, 1) : (Math.Min(LowerTop, Lines), 1);
    }

    /// <summary>Erase from the cursor to the end of the line (§8.7.3.4).</summary>
    public void EraseLine()
    {
        Flush();
        int screenRow, column;

        if (_selected == Upper)
        {
            screenRow = UpperTop + _upperCursor.Row - 1;
            column = _upperCursor.Column;
        }
        else
        {
            (screenRow, column) = _lowerCursor;
        }

        for (var position = column; position <= Columns; position++)
        {
            _grid[screenRow - 1][position - 1] = BlankCell();
        }

        _damage.Add(screenRow);
    }

    /// <summary>Change the text style for what follows (§8.7.1): roman clears, the rest combine.</summary>
    public void SetStyle(int style) => _style = style == Roman ? Roman : _style | style;

    /// <summary>Erase the last typed character during line input, never past the left edge.</summary>
    public void RubOut()
    {
        Flush();

        if (_selected == Upper)
        {
            var (row, column) = _upperCursor;

            if (column > 1)
            {
                Paint(UpperTop + row - 1, column - 1, BlankCell());
                _upperCursor = (row, column - 1);
            }
        }
        else
        {
            var (row, column) = _lowerCursor;

            if (column > 1)
            {
                Paint(row, column - 1, BlankCell());
                _lowerCursor = (row, column - 1);
            }
        }
    }

    /// <summary>Move the selected window's cursor left without erasing; answers the cells moved.</summary>
    public int Retreat(int cells)
    {
        Flush();

        if (_selected == Upper)
        {
            var moved = Math.Min(cells, _upperCursor.Column - 1);
            _upperCursor = (_upperCursor.Row, _upperCursor.Column - moved);
            return moved;
        }
        else
        {
            var moved = Math.Min(cells, _lowerCursor.Column - 1);
            _lowerCursor = (_lowerCursor.Row, _lowerCursor.Column - moved);
            return moved;
        }
    }

    /// <summary>Print a §15 rectangle, right and down from the cursor.</summary>
    public void WriteRectangle(IReadOnlyList<string> rows)
    {
        Flush();

        if (_selected != Upper)
        {
            for (var index = 0; index < rows.Count; index++)
            {
                if (index > 0)
                {
                    Write("\n");
                }

                Write(rows[index]);
            }

            return;
        }

        var (startRow, startColumn) = _upperCursor;

        for (var index = 0; index < rows.Count; index++)
        {
            if (index > 0)
            {
                _upperCursor = (Math.Min(startRow + index, Math.Max(_split, 1)), startColumn);
            }

            foreach (var character in Characters(rows[index]))
            {
                WriteUpper(character);
            }
        }
    }

    /// <summary>Change the font for what follows (§8.1.2).</summary>
    public void SetFont(int font) => _font = font;

    /// <summary>Turn lower-window word-wrapping on or off (§15 buffer_mode).</summary>
    public void SetBuffering(bool buffered)
    {
        Flush();
        _buffered = buffered;
    }

    /// <summary>Change the printing colours (§8.3.1); zero keeps a colour current.</summary>
    public void SetColour(int foreground, int background)
    {
        if (foreground != CurrentColour)
        {
            _foreground = foreground;
        }

        if (background != CurrentColour)
        {
            _background = background;
        }
    }

    /// <summary>Draw the Version 1 to 3 status line on the top row, in reverse video (§8.2).</summary>
    public void ShowStatus(Status status)
    {
        if (_version > StatusLastVersion)
        {
            throw new ZMachineException($"version {_version} draws its own status area; the interpreter's line ends at version 3 (§8.2)");
        }

        Flush();
        var right = status.TimeGame
            ? $"Time: {status.Score}:{status.Turns:00}"
            : $"Score: {status.Score}  Moves: {status.Turns}";
        var room = status.Location;
        var available = Columns - right.Length - 3;

        if (room.Length > available)
        {
            room = room[..Math.Max(available - 3, 0)].TrimEnd() + "...";
        }

        var line = $" {room}".PadRight(Math.Max(Columns - right.Length - 1, 0)) + right + " ";
        // The line is padded to the width, or longer and cut: never short.
        var row = new Cell[Columns];

        for (var column = 0; column < Columns; column++)
        {
            row[column] = new Cell(line[column].ToString(), Reverse);
        }

        _grid[0] = row;
        _damage.Add(1);
        _status = status;
    }

    /// <summary>The rows changed since the last sweep, in screen order; sweeping clears the slate.</summary>
    public List<int> Sweep()
    {
        Flush();
        var damaged = _damage.ToList();
        _damage.Clear();
        return damaged;
    }

    /// <summary>One grid position, pending text flushed first.</summary>
    public Cell CellAt(int row, int column)
    {
        Flush();
        return _grid[row - 1][column - 1];
    }

    /// <summary>One row's characters as a string, right side trimmed.</summary>
    public string RowText(int row)
    {
        Flush();
        var text = new StringBuilder();

        foreach (var cell in _grid[row - 1])
        {
            text.Append(cell.Character);
        }

        return text.ToString().TrimEnd();
    }

    /// <summary>The whole screen as a text block, one line per row.</summary>
    public string Rendered()
    {
        Flush();
        return string.Join("\n", Enumerable.Range(1, Lines).Select(RowText));
    }

    /// <summary>The selected window's cursor in screen coordinates.</summary>
    public (int Row, int Column) Cursor
    {
        get
        {
            Flush();
            return _selected == Upper ? (UpperTop + _upperCursor.Row - 1, _upperCursor.Column) : _lowerCursor;
        }
    }
}
