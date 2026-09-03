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
    int ScreenLines { get; }
    int ScreenColumns { get; }

    void Write(string text);
    void WriteRectangle(IReadOnlyList<string> rows);
    void SplitWindow(int lines);
    void SetWindow(int window);
    void EraseWindow(int window);
    void SetCursor(int line, int column);
    (int Line, int Column) CursorPosition();
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
    public int ScreenLines => 255;
    public int ScreenColumns => 80;

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
}
