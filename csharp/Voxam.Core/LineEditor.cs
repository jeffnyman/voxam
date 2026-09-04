namespace Voxam.Core;

/// <summary>What the editor needs from a screen model to echo edits.</summary>
public interface ILineCanvas
{
    void Write(string text);

    /// <summary>Move the cursor left without erasing; answer the cells moved.</summary>
    int Retreat(int cells);
}

/// <summary>
/// The interpreter's line editor for painted input (§15 read), as
/// pure state: a buffer, an insertion point, and a session history,
/// each keystroke a small transition. Only the submitted line reaches
/// the machine.
/// </summary>
public sealed class LineEditor
{
    public const string CursorUp = "\u0081";
    public const string CursorDown = "\u0082";
    public const string CursorLeft = "\u0083";
    public const string CursorRight = "\u0084";
    public const string Escape = "\u001b";

    /// <summary>What a key source answers when a timed read's interval expires.</summary>
    public const string Expired = "\0";

    private const int HistoryLimit = 100;
    private static readonly string[] RubOutKeys = ["\u007f", "\b"];

    private readonly List<string> _history = [];
    private List<string> _buffer = [];
    private int _recall = -1;
    private string _draft = "";

    /// <summary>The line as composed so far.</summary>
    public string Text => string.Concat(_buffer);

    /// <summary>The insertion point, in characters from the line's start.</summary>
    public int Cursor { get; private set; }

    /// <summary>Start composing a fresh, empty line.</summary>
    public void Begin()
    {
        _buffer = [];
        Cursor = 0;
        _recall = -1;
        _draft = "";
    }

    public void Insert(string character)
    {
        _buffer.Insert(Cursor, character);
        Cursor++;
    }

    public bool RubOut()
    {
        if (Cursor == 0)
        {
            return false;
        }

        Cursor--;
        _buffer.RemoveAt(Cursor);
        return true;
    }

    public bool Left()
    {
        if (Cursor == 0)
        {
            return false;
        }

        Cursor--;
        return true;
    }

    public bool Right()
    {
        if (Cursor == _buffer.Count)
        {
            return false;
        }

        Cursor++;
        return true;
    }

    /// <summary>Recall the previous history line, saving the draft first.</summary>
    public bool Earlier()
    {
        if (_recall < 0)
        {
            if (_history.Count == 0)
            {
                return false;
            }

            _draft = Text;
            _recall = _history.Count - 1;
        }
        else if (_recall > 0)
        {
            _recall--;
        }
        else
        {
            return false;
        }

        _buffer = [.. Characters(_history[_recall])];
        Cursor = _buffer.Count;
        return true;
    }

    /// <summary>Walk forward through history, back to the saved draft.</summary>
    public bool Later()
    {
        if (_recall < 0)
        {
            return false;
        }

        _recall++;

        if (_recall == _history.Count)
        {
            _recall = -1;
            _buffer = [.. Characters(_draft)];
        }
        else
        {
            _buffer = [.. Characters(_history[_recall])];
        }

        Cursor = _buffer.Count;
        return true;
    }

    /// <summary>Finish the line: record it in history (once, and never empty) and reset.</summary>
    public string Submit()
    {
        var line = Text;

        if (line.Length > 0 && (_history.Count == 0 || _history[^1] != line))
        {
            _history.Add(line);

            if (_history.Count > HistoryLimit)
            {
                _history.RemoveAt(0);
            }
        }

        Begin();
        return line;
    }

    private static IEnumerable<string> Characters(string text)
    {
        var enumerator = System.Globalization.StringInfo.GetTextElementEnumerator(text);

        while (enumerator.MoveNext())
        {
            yield return enumerator.GetTextElement();
        }
    }

    /// <summary>
    /// Run one line read through the editor, echoing via the canvas.
    /// Keys arrive raw from the key source; a source answering
    /// Expired ends the call with null, the composed line standing,
    /// and a later call with fresh false resumes it where it stood.
    /// </summary>
    public string? ReadLine(ILineCanvas canvas, Func<string?> keySource, Action repaint, bool fresh = true)
    {
        int painted;
        int at;

        if (fresh)
        {
            Begin();
            painted = 0;
            at = 0;
        }
        else
        {
            painted = Text.Length;
            at = Cursor;
        }

        void Redraw()
        {
            canvas.Retreat(at);
            var text = Text;
            canvas.Write(text);
            var remnant = painted - text.Length;

            if (remnant > 0)
            {
                canvas.Write(new string(' ', remnant));
                canvas.Retreat(remnant);
            }

            canvas.Retreat(text.Length - Cursor);
            painted = text.Length;
            at = Cursor;
            repaint();
        }

        while (true)
        {
            var key = keySource();

            if (key == Expired)
            {
                return null;
            }

            if (key is null || key == Escape)
            {
                continue;
            }

            if (key is "\n" or "\r")
            {
                canvas.Write("\n");
                repaint();
                return Submit();
            }

            var edit = Edit(key);

            if (edit is not null)
            {
                if (edit())
                {
                    Redraw();
                }
            }
            else if (key[0] < ' ' || key[0] is >= '\u0081' and <= '\u009a')
            {
                continue;
            }
            else
            {
                var appending = Cursor == Text.Length;
                Insert(key);

                if (appending)
                {
                    canvas.Write(key);
                    painted++;
                    at++;
                    repaint();
                }
                else
                {
                    Redraw();
                }
            }
        }
    }

    private Func<bool>? Edit(string key)
    {
        if (RubOutKeys.Contains(key))
        {
            return RubOut;
        }

        return key switch
        {
            CursorUp => Earlier,
            CursorDown => Later,
            CursorLeft => Left,
            CursorRight => Right,
            _ => null,
        };
    }
}
