namespace Voxam.Core;

/// <summary>Where text and status go, and what the display claims (§11.1).</summary>
public interface IFrontend
{
    bool HasStatusLine { get; }
    bool HasScreenSplitting { get; }
    bool HasSounds { get; }
    bool HasBold { get; }
    bool HasItalic { get; }
    bool HasFixedPitch { get; }
    bool HasTimedInput { get; }
    bool HasColours { get; }

    /// <summary>Whether §16's character graphics font can be drawn.</summary>
    bool HasCharacterGraphics { get; }

    int ScreenLines { get; }
    int ScreenColumns { get; }

    /// <summary>One character cell's width in units, which Version 6 reads as pixels (§8.8.1).</summary>
    int FontWidth { get; }

    /// <summary>One character cell's height in units.</summary>
    int FontHeight { get; }

    void Write(string text);
    void WriteRectangle(IReadOnlyList<string> rows);
    void ShowStatus(Status status);
    void SetStyle(int style);
    void SetFont(int font);
    void SetColour(int foreground, int background);
    void SetBuffering(bool buffered);
    void SplitWindow(int lines);
    void SetWindow(int window);
    void EraseWindow(int window);
    void EraseLine();
    void SetCursor(int line, int column);
    (int Line, int Column) CursorPosition();

    /// <summary>A timed line read begins: remember the prompt (§15 read remarks).</summary>
    void BeginInput();

    /// <summary>A printing interrupt let input continue: show the prompt again.</summary>
    void ResumeInput();

    /// <summary>An interrupt ended the read: erase the half-typed line.</summary>
    void AbandonInput();
}

/// <summary>
/// A dumb-terminal presentation: one unadorned stream of text, ported
/// from the Python PlainFrontend with its upper-window muting rules.
/// </summary>
public sealed class PlainFrontend(Action<string> write) : IFrontend
{
    private const int LowerWindow = 0;
    private const int UpperWindow = 1;
    private const int UnsplitAndClear = -1;
    private const int StatusChromeLines = 2;

    private int _window = LowerWindow;
    private int _split;
    private int _upperRow = 1;
    private int _upperColumn = 1;

    public bool HasStatusLine => false;
    public bool HasScreenSplitting => false;
    public bool HasSounds => false;
    public bool HasBold => false;
    public bool HasItalic => false;
    public bool HasFixedPitch => true;
    public bool HasTimedInput => true;
    public bool HasColours => false;
    public bool HasCharacterGraphics => false;
    public int ScreenLines => 255;
    public int ScreenColumns => 80;

    // A stream measures in characters: one unit is one character.
    public int FontWidth => 1;
    public int FontHeight => 1;

    private bool UpperHoldsContent => _split > StatusChromeLines;

    public void Write(string text)
    {
        if (_window == LowerWindow)
        {
            write(text);
        }
        else if (UpperHoldsContent)
        {
            write(text);
            _upperColumn += text.Length;
        }
    }

    public void WriteRectangle(IReadOnlyList<string> rows)
    {
        for (var index = 0; index < rows.Count; index++)
        {
            if (index > 0)
            {
                Write("\n");
            }

            Write(rows[index]);
        }
    }

    public void SplitWindow(int lines) => _split = lines;

    public void SetWindow(int window)
    {
        if (window == LowerWindow && _window == UpperWindow && UpperHoldsContent)
        {
            write("\n");
        }

        _window = window;
        _upperRow = 1;
        _upperColumn = 1;
    }

    public void EraseWindow(int window)
    {
        if (window == UnsplitAndClear)
        {
            _window = LowerWindow;
            _split = 0;
        }
    }

    public void SetCursor(int line, int column)
    {
        if (_window != UpperWindow || !UpperHoldsContent)
        {
            return;
        }

        if (line != _upperRow)
        {
            write("\n");
            _upperRow = line;
            _upperColumn = 1;
        }

        if (column > _upperColumn)
        {
            write(new string(' ', column - _upperColumn));
            _upperColumn = column;
        }
    }

    public (int Line, int Column) CursorPosition() => (_upperRow, _upperColumn);

    // A transcript has no status line, no styles, no colours, no
    // cursor to erase from, and no input line to redisplay: each
    // request is the conforming quiet of a frontend that said so.
    public void ShowStatus(Status status)
    {
    }

    public void SetStyle(int style)
    {
    }

    public void SetFont(int font)
    {
    }

    public void SetColour(int foreground, int background)
    {
    }

    public void SetBuffering(bool buffered)
    {
    }

    public void EraseLine()
    {
    }

    public void BeginInput()
    {
    }

    public void ResumeInput()
    {
    }

    public void AbandonInput()
    {
    }
}
