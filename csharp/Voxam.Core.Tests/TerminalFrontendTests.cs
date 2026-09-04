using System.Text;

namespace Voxam.Core.Tests;

public class TerminalFrontendTests
{
    private const string Esc = "\u001b";

    /// <summary>A terminal that records what is written and answers queued keys.</summary>
    private sealed class FakeTerminal : ITerminal
    {
        public int Width { get; set; } = 20;

        public int Height { get; set; } = 4;

        public StringBuilder Written { get; } = new();

        public Queue<string?> Keys { get; } = new();

        public List<double?> Timeouts { get; } = [];

        public void Write(string text) => Written.Append(text);

        public string? ReadKey(double? timeoutSeconds)
        {
            Timeouts.Add(timeoutSeconds);
            return Keys.Count > 0 ? Keys.Dequeue() : null;
        }
    }

    private static (TerminalFrontend Face, FakeTerminal Terminal) Painted(int version = 3)
    {
        var terminal = new FakeTerminal();
        return (new TerminalFrontend(version, terminal), terminal);
    }

    [Fact]
    public void TheFaceClaimsWhatAPaintedTerminalHas()
    {
        var (face, _) = Painted();
        Assert.True(face.HasStatusLine);
        Assert.True(face.HasScreenSplitting);
        Assert.False(face.HasSounds);
        Assert.True(face.HasBold);
        Assert.True(face.HasItalic);
        Assert.True(face.HasFixedPitch);
        Assert.True(face.HasTimedInput);
        Assert.True(face.HasColours);
        Assert.True(face.HasCharacterGraphics);
        Assert.Equal(20, face.ScreenColumns);
        Assert.Equal(4, face.ScreenLines);
        Assert.Equal(1, face.FontWidth);
        Assert.Equal(1, face.FontHeight);
        var unknown = new TerminalFrontend(3, new FakeTerminal { Width = 0, Height = 0 });
        Assert.Equal(80, unknown.ScreenColumns);
        Assert.Equal(24, unknown.ScreenLines);
    }

    [Fact]
    public void WritingPaintsTheDamagedRowAndParksTheCursor()
    {
        var (face, terminal) = Painted();
        face.Write("hi");
        var written = terminal.Written.ToString();
        Assert.Contains($"{Esc}[4;1H{Esc}[0mhi", written, StringComparison.Ordinal);
        Assert.EndsWith($"{Esc}[4;3H", written, StringComparison.Ordinal);
        Assert.Equal("hi", face.Model.RowText(4));
    }

    [Fact]
    public void DressIsSpelledInSequencesAndABlankIsNeverBold()
    {
        var terminal = new FakeTerminal { Width = 40 };
        var face = new TerminalFrontend(3, terminal);
        face.SetStyle(ScreenModel.Bold);
        face.SetStyle(ScreenModel.Italic);
        face.SetColour(3, 6);
        face.Write(" a");
        var written = terminal.Written.ToString();
        Assert.Contains($"{Esc}[0m{Esc}[3m{Esc}[31m{Esc}[44m {Esc}[0m{Esc}[1m{Esc}[3m{Esc}[31m{Esc}[44ma", written, StringComparison.Ordinal);
        face.ShowStatus(new Status("Room", 0, 0, false));
        Assert.Contains($"{Esc}[1;1H{Esc}[0m{Esc}[7m Room", terminal.Written.ToString(), StringComparison.Ordinal);
    }

    [Fact]
    public void FontThreePaintsItsStandIns()
    {
        var (face, terminal) = Painted();
        face.SetFont(3);
        face.Write("!{é");
        var written = terminal.Written.ToString();
        Assert.Contains("←", written, StringComparison.Ordinal);
        Assert.Contains($"{Esc}[7m↑", written, StringComparison.Ordinal);
        // A character font 3 has no shape for paints as itself.
        Assert.Contains("é", written, StringComparison.Ordinal);
        face.SetFont(1);
        face.Write("{");
        Assert.EndsWith($"{Esc}[0m{Esc}[4;5H", terminal.Written.ToString(), StringComparison.Ordinal);
    }

    [Fact]
    public void ClearPaintsEveryRowAndResizeFollowsTheTerminal()
    {
        var (face, terminal) = Painted();
        face.Clear();
        // Each row opens with a normal dress and closes with one.
        Assert.Equal(8, terminal.Written.ToString().Split($"{Esc}[0m").Length - 1);
        // A resize with nobody listening still reshapes the model.
        terminal.Width = 25;
        face.Write("w");
        Assert.Equal(25, face.ScreenColumns);
        var resized = 0;
        face.OnResize = () => resized++;
        terminal.Width = 30;
        terminal.Height = 6;
        face.Write("x");
        Assert.Equal(1, resized);
        Assert.Equal(30, face.ScreenColumns);
        Assert.Equal(6, face.Model.Lines);
        face.Write("y");
        Assert.Equal(1, resized);
        // A terminal that stops answering keeps the size it last gave.
        terminal.Width = 0;
        terminal.Height = 0;
        face.Write("z");
        Assert.Equal(1, resized);
        Assert.Equal(30, face.ScreenColumns);
    }

    [Fact]
    public void KeysAreReadRawWithOrWithoutATimeout()
    {
        var (face, terminal) = Painted();
        terminal.Keys.Enqueue(null);
        terminal.Keys.Enqueue("x");
        Assert.Equal("x", face.ReadKey(null));
        Assert.Equal([null, null], terminal.Timeouts);
        Assert.Null(face.ReadKey(0.5));
        Assert.Equal(0.5, terminal.Timeouts[^1]);
    }

    [Fact]
    public void LinesAreEditedAndEchoedThroughTheModel()
    {
        var (face, terminal) = Painted();
        face.Write(">");

        foreach (var key in new[] { "l", "o", "\u007f", "o", "\n" })
        {
            terminal.Keys.Enqueue(key);
        }

        Assert.Equal("lo", face.ReadLine());
        Assert.Equal(">lo", face.Model.RowText(4));
    }

    [Fact]
    public void ATimedLineReadSurvivesItsInterruptsOrIsAbandoned()
    {
        var (face, terminal) = Painted();
        face.Write(">");
        face.BeginInput();
        terminal.Keys.Enqueue("w");
        Assert.Null(face.ReadLineUntil(0.05));
        Assert.Equal(">w", face.Model.RowText(4));
        face.Write("\nrumble\n");
        face.ResumeInput();
        Assert.Equal(">", face.Model.RowText(4));
        terminal.Keys.Enqueue("a");
        terminal.Keys.Enqueue("\n");
        Assert.Equal("wa", face.ReadLineUntil(5));

        terminal.Keys.Enqueue("z");
        Assert.Null(face.ReadLineUntil(0.05));
        face.AbandonInput();
        Assert.Equal("", face.Model.RowText(4).Trim());
        face.AbandonInput();
        terminal.Keys.Enqueue("\n");
        Assert.Equal("", face.ReadLineUntil(5));
    }

    [Fact]
    public void AScreenfulPausesBehindMoreUntilAKeyArrives()
    {
        var (face, terminal) = Painted(5);
        terminal.Keys.Enqueue(null);
        terminal.Keys.Enqueue(" ");
        face.Write("a\nb\nc\n");
        Assert.Contains($"{Esc}[7m[MORE]{Esc}[0m", terminal.Written.ToString(), StringComparison.Ordinal);
        Assert.Empty(terminal.Keys);
    }

    [Fact]
    public void WindowOperationsReachTheModel()
    {
        var (face, _) = Painted(5);
        face.SplitWindow(2);
        face.SetWindow(ScreenModel.Upper);
        face.SetCursor(2, 3);
        Assert.Equal((2, 3), face.CursorPosition());
        face.Write("abc");
        face.EraseLine();
        face.SetBuffering(false);
        face.WriteRectangle(["xy"]);
        face.EraseWindow(ScreenModel.Upper);
        Assert.Equal("", face.Model.RowText(2).Trim());
        face.SetWindow(ScreenModel.Lower);
        Assert.Equal((1, 1), face.CursorPosition());
    }
}
