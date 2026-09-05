using Voxam.Core;
using Voxam.Core.Glulx.Glk;

namespace Voxam.Tests.Glulx.Glk;

/// <summary>A terminal that answers from a script and keeps what it was written.</summary>
internal sealed class PaperTerminal : ITerminal
{
    public List<string> Written { get; } = [];

    public Queue<string?> Keys { get; } = [];

    public int Width { get; set; }

    public int Height { get; set; }

    public string Taken()
    {
        var shown = string.Join("", Written);

        Written.Clear();

        return shown;
    }

    public void Write(string text) => Written.Add(text);

    public string? ReadKey(double? timeoutSeconds) =>
        Keys.Count > 0 ? Keys.Dequeue() : null;
}

/// <summary>
/// The terminal specifics: where the escape sequences land, how a style
/// is dressed, and how the seam's own key alphabet becomes Glk's.
/// </summary>
public sealed class TerminalDisplayTests
{
    // A placement moves the cursor and writes the run, and the frame
    // reaches the terminal in one piece at the end of it.
    [Fact]
    public void AFrameReachesTheTerminalWhole()
    {
        var (face, terminal) = Seam();

        face.Clear();

        Assert.Equal(
            "\u001B[1;1H   \u001B[2;1H   \u001B[2;1H", terminal.Taken());
    }

    // Every style wears the sequences its dress calls for, and a style
    // with no dress of its own is written plain.
    [Fact]
    public void EveryStyleWearsItsOwnDress()
    {
        var (face, terminal) = Seam();
        var glk = new Api(face);
        var window = Open(glk, WindowType.TextBuffer);

        Call(glk, 0x002F, Held.OfOpaque(window));

        foreach (var (style, expected) in new (uint, string)[]
        {
            (TextStyle.Normal, "x"),
            (TextStyle.Preformatted, "x"),
            (TextStyle.Emphasized, "\u001B[3mx\u001B[0m"),
            (TextStyle.Header, "\u001B[1mx\u001B[0m"),
            (TextStyle.User2, "\u001B[7mx\u001B[0m"),
            (TextStyle.Alert, "\u001B[1m\u001B[7mx\u001B[0m"),
        })
        {
            Call(glk, 0x0086, Held.OfWord(style));
            Call(glk, 0x0080, Held.OfWord('x'));

            terminal.Taken();
            face.Flush(glk.Root);

            Assert.Contains(expected, terminal.Taken(), StringComparison.Ordinal);
            Call(glk, 0x002A, Held.OfOpaque(glk.Root));
        }
    }

    // The room is the terminal's own measure, unless one was chosen, and
    // a terminal that cannot say falls back to a conventional one.
    [Fact]
    public void TheRoomIsTheTerminalsUnlessOneWasChosen()
    {
        var terminal = new PaperTerminal();

        Assert.Equal((80, 24), new TerminalDisplay(terminal).Size());

        terminal.Width = 100;
        terminal.Height = 40;

        Assert.Equal((100, 40), new TerminalDisplay(terminal).Size());
        Assert.Equal((30, 8), new TerminalDisplay(terminal, (30, 8)).Size());
    }

    // The keys the seam spells for itself become the Glk codes they
    // mean; anything else is the character it is.
    [Fact]
    public void TheSeamsKeysBecomeGlkCodes()
    {
        var (face, terminal) = Seam();
        var glk = new Api(face);
        var window = Open(glk, WindowType.TextBuffer);

        foreach (var (typed, expected) in new (string, uint)[]
        {
            ("\u0081", KeyCode.Up),
            ("\u0082", KeyCode.Down),
            ("\u0083", KeyCode.Left),
            ("\u0084", KeyCode.Right),
            ("\u0008", KeyCode.Delete),
            ("\u007F", KeyCode.Delete),
            ("\u001B", KeyCode.Escape),
            ("\u0009", KeyCode.Tab),
            ("\n", KeyCode.Return),
            ("\r", KeyCode.Return),
            ("q", 'q'),
        })
        {
            terminal.Keys.Enqueue(typed);

            Assert.Equal(expected, face.ReadChar(window));
        }
    }

    // A wait that expired and a key of more than one character are both
    // nothing usable, and the read simply comes back round for another.
    // A timer is what lets it ever answer: without one it waits, which
    // is what a keyboard read is for.
    [Fact]
    public void NothingUsableSendsTheReadBackRound()
    {
        foreach (var typed in new[] { null, "\u001B[A" })
        {
            var (face, terminal) = Seam();
            var glk = new Api(face);
            var window = Open(glk, WindowType.TextBuffer);

            if (typed is not null)
            {
                terminal.Keys.Enqueue(typed);
            }

            face.SetTimer(1);
            Thread.Sleep(20);

            Assert.Null(face.ReadChar(window));
            Assert.Equal(EventType.Timer, Assert.Single(glk.PendingEvents).Kind);
        }
    }

    // A display with nobody listening at its seams still accepts a line
    // and still answers a file prompt: the seams are for a recording,
    // and a session without one is the ordinary case.
    [Fact]
    public void ADisplayWithNobodyListeningStillReads()
    {
        var (face, terminal) = Seam();
        var glk = new Api(face);
        var window = Open(glk, WindowType.TextBuffer);

        face.Flush(glk.Root);
        terminal.Taken();

        Call(glk, 0x00D0, Held.OfOpaque(window), new WordBuffer(8), Held.OfWord(0));

        foreach (var key in new[] { "h", "i", "\n" })
        {
            terminal.Keys.Enqueue(key);
        }

        Assert.Equal(("hi", 0u), face.ReadLine(window, 8));

        // The cursor was parked after the line as it was typed.
        Assert.Contains("\u001B[2;3H", terminal.Taken(), StringComparison.Ordinal);

        foreach (var key in new[] { "a", "\n" })
        {
            terminal.Keys.Enqueue(key);
        }

        Assert.Equal("a", face.PromptFile(FileUsage.SavedGame, GlkFileMode.Write));
    }

    // Retiring parks the cursor under the story, so the shell's next
    // prompt lands on a fresh line below it.
    [Fact]
    public void RetiringParksTheCursorUnderTheStory()
    {
        var (face, terminal) = Seam();

        terminal.Taken();
        face.Retire();

        Assert.Equal("\u001B[2;1H\n", terminal.Taken());
    }

    private static Window Open(Api glk, uint wtype) => (Window)Call(
        glk, 0x0023, Held.OfOpaque(null), Held.OfWord(0), Held.OfWord(0),
        Held.OfWord(wtype), Held.OfWord(0)).Opaque!;

    private static Held Call(Api glk, int selector, params object?[] args) =>
        glk.Call(Signatures.Lookup(selector)!, args);

    private static (TerminalDisplay Face, PaperTerminal Terminal) Seam()
    {
        var terminal = new PaperTerminal();

        return (new TerminalDisplay(terminal, (3, 2)), terminal);
    }
}
