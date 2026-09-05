using System.Globalization;
using System.Text;

namespace Voxam.Core.Tests;

public class LineEditorTests
{
    /// <summary>A canvas that records writes and cursor retreats as the model would see them.</summary>
    private sealed class Canvas : ILineCanvas
    {
        public StringBuilder Log { get; } = new();

        public void Write(string text) => Log.Append(text);

        public int Retreat(int cells)
        {
            Log.Append(CultureInfo.InvariantCulture, $"<{cells}");
            return cells;
        }
    }

    private static string? Read(LineEditor editor, Canvas canvas, params string?[] keys)
    {
        var queue = new Queue<string?>(keys);
        return editor.ReadLine(canvas, () => queue.Count > 0 ? queue.Dequeue() : LineEditor.Expired, () => { });
    }

    [Fact]
    public void KeysComposeTheLineAndEnterSubmitsIt()
    {
        var editor = new LineEditor();
        var canvas = new Canvas();
        Assert.Equal("look", Read(editor, canvas, "l", "o", "o", "k", "\n"));
        Assert.Equal("look\n", canvas.Log.ToString());
        Assert.Equal("", editor.Text);
    }

    [Fact]
    public void EditsInTheMiddleRedrawTheWholeLine()
    {
        var editor = new LineEditor();
        var canvas = new Canvas();
        var line = Read(editor, canvas, "a", "c", LineEditor.CursorLeft, "b", LineEditor.CursorRight, "\u007f", "\b", "d", "\r");
        Assert.Equal("ad", line);
        // Appending writes the key; every other edit retreats to the
        // line's start, rewrites it, blanks any remnant, and retreats to
        // the cursor.
        Assert.Equal("ac<2ac<1<1abc<1<2abc<0<3ab <1<0<2a <1<0d\n", canvas.Log.ToString());
    }

    [Fact]
    public void HistoryWalksBackAndForwardAndKeepsTheDraft()
    {
        var editor = new LineEditor();
        var canvas = new Canvas();
        Read(editor, canvas, "n", "\n");
        Read(editor, canvas, "n", "\n");
        Read(editor, canvas, "e", "\n");
        Read(editor, canvas, "\n");
        Assert.Equal("n", Read(editor, canvas, "x", LineEditor.CursorUp, LineEditor.CursorUp, LineEditor.CursorUp, "\n"));
        Assert.Equal("x", Read(editor, canvas, "x", LineEditor.CursorUp, LineEditor.CursorDown, LineEditor.CursorDown, "\n"));
        Assert.Equal("x", Read(editor, canvas, LineEditor.CursorUp, LineEditor.CursorUp, LineEditor.CursorDown, "\n"));
        var fresh = new LineEditor();
        Assert.False(fresh.Earlier());
        Assert.False(fresh.Later());
        Assert.False(fresh.Left());
        Assert.False(fresh.Right());
        Assert.False(fresh.RubOut());
    }

    [Fact]
    public void TheHistoryKeepsAHundredLines()
    {
        var editor = new LineEditor();
        var canvas = new Canvas();

        for (var k = 0; k < 105; k++)
        {
            Read(editor, canvas, k.ToString(System.Globalization.CultureInfo.InvariantCulture), "\n");
        }

        foreach (var _ in Enumerable.Range(0, 120))
        {
            editor.Earlier();
        }

        Assert.Equal("5", editor.Text);
    }

    [Fact]
    public void ControlKeysNullsAndEscapesAreIgnored()
    {
        var editor = new LineEditor();
        var canvas = new Canvas();
        Assert.Equal("ok", Read(editor, canvas, null, LineEditor.Escape, "\u0001", "\u0090", "o", "k", "\n"));
    }

    [Fact]
    public void AnExpiredSourceLeavesTheLineComposedForNextTime()
    {
        var editor = new LineEditor();
        var canvas = new Canvas();
        Assert.Null(Read(editor, canvas, "w", "a"));
        Assert.Equal("wa", editor.Text);
        var queue = new Queue<string>(["i", "t", "\n"]);
        var line = editor.ReadLine(canvas, () => queue.Dequeue(), () => { }, fresh: false);
        Assert.Equal("wait", line);
    }
}
