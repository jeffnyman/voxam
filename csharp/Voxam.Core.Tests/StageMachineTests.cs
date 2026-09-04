using Voxam.Core.Tests.Support;

namespace Voxam.Core.Tests;

/// <summary>The seams a machine sends only to a stage, and what a character face hears instead (§8.8).</summary>
public class StageMachineTests
{
    private const int G0 = 0x10;
    private const int Units = 2;

    /// <summary>A glass that records the paints it is given and answers queued keys.</summary>
    private sealed class FakeScreen : IStageScreen
    {
        public int Columns { get; set; } = 10;

        public int Lines => 6;

        public int FontWidth => Units;

        public int FontHeight => Units;

        public Queue<string?> Keys { get; } = new();

        public List<Paint> Settled { get; } = [];

        public string? ReadKey(double? timeoutSeconds) => Keys.Count > 0 ? Keys.Dequeue() : null;

        public void Settle(IReadOnlyList<Paint> paints) => Settled.AddRange(paints);
    }

    /// <summary>A stage that writes down every picture it is asked to draw or erase.</summary>
    private sealed class Watching(StageFrontend inner, List<(int Number, int Line, int Column)> drawn) : IStageFrontend
    {
        public bool HasStatusLine => inner.HasStatusLine;

        public bool HasScreenSplitting => inner.HasScreenSplitting;

        public bool HasSounds => inner.HasSounds;

        public bool HasBold => inner.HasBold;

        public bool HasItalic => inner.HasItalic;

        public bool HasFixedPitch => inner.HasFixedPitch;

        public bool HasTimedInput => inner.HasTimedInput;

        public bool HasColours => inner.HasColours;

        public bool HasCharacterGraphics => inner.HasCharacterGraphics;

        public bool HasPictures => inner.HasPictures;

        public int ScreenLines => inner.ScreenLines;

        public int ScreenColumns => inner.ScreenColumns;

        public int FontWidth => inner.FontWidth;

        public int FontHeight => inner.FontHeight;

        public void Write(string text) => inner.Write(text);

        public void WriteRectangle(IReadOnlyList<string> rows) => inner.WriteRectangle(rows);

        public void ShowStatus(Status status) => inner.ShowStatus(status);

        public void SetStyle(int style) => inner.SetStyle(style);

        public void SetFont(int font) => inner.SetFont(font);

        public void SetColour(int foreground, int background) => inner.SetColour(foreground, background);

        public void SetBuffering(bool buffered) => inner.SetBuffering(buffered);

        public void SplitWindow(int lines) => inner.SplitWindow(lines);

        public void SetWindow(int window) => inner.SetWindow(window);

        public void EraseWindow(int window) => inner.EraseWindow(window);

        public void EraseLine() => inner.EraseLine();

        public void EraseLine(int pixels) => inner.EraseLine(pixels);

        public void SetCursor(int line, int column) => inner.SetCursor(line, column);

        public (int Line, int Column) CursorPosition() => inner.CursorPosition();

        public void PlaceWindow(int window, int line, int column, int height, int width) =>
            inner.PlaceWindow(window, line, column, height, width);

        public void SetLineCount(int window, int count) => inner.SetLineCount(window, count);

        public void SetMargins(int window, int left, int right) => inner.SetMargins(window, left, right);

        public void ScrollWindow(int window, int pixels) => inner.ScrollWindow(window, pixels);

        public (int Height, int Width)? PictureData(int number) => inner.PictureData(number);

        public (int Count, int Release) PictureCensus() => inner.PictureCensus();

        public void DrawPicture(int number, int line, int column) => drawn.Add((number, line, column));

        public void ErasePicture(int number, int line, int column) => drawn.Add((number, line, column));

        public void BeginInput() => inner.BeginInput();

        public void ResumeInput() => inner.ResumeInput();

        public void AbandonInput() => inner.AbandonInput();
    }

    // Assemble a Version 6 story around a main routine and run it on a
    // stage, which is the only face these opcodes reach.
    private static (StageFrontend Face, FakeScreen Screen) Play(Action<StoryBuilder> body, params string[] keys)
    {
        var b = new StoryBuilder(6);
        var main = b.Routine(0);
        body(b);
        b.Quit();
        b.InitialPc = main;
        var screen = new FakeScreen();

        foreach (var key in keys)
        {
            screen.Keys.Enqueue(key);
        }

        var face = new StageFrontend(screen);
        new Machine(b.Build(), face, () => null, 1, face.ReadKey, face.ReadLineUntil).Run();
        return (face, screen);
    }

    private static void MoveWindow(StoryBuilder b, int window, int line, int column) =>
        b.Ext(0x10, Arg.Small(window), Arg.Large(line), Arg.Large(column));

    private static void WindowSize(StoryBuilder b, int window, int height, int width) =>
        b.Ext(0x11, Arg.Small(window), Arg.Large(height), Arg.Large(width));

    // A window moved or resized in the ledger is placed on the stage,
    // so what is printed next lands where §8.8.3.4 put it.
    [Fact]
    public void MovingAndSizingAWindowPlacesItOnTheStage()
    {
        var (face, _) = Play(b =>
        {
            WindowSize(b, 2, 2 * Units, 4 * Units);
            MoveWindow(b, 2, 2 * Units + 1, Units + 1);
            b.OpVar(0x0B, Arg.Small(2));
            b.Print("here");
        });
        Assert.Equal(" here", face.Model.RowText(3));
    }

    // A cursor aimed at the selected window moves at once; one aimed at
    // another window waits for its selection and rides along then.
    [Fact]
    public void ACursorAimedAtAnUnselectedWindowWaitsForIt()
    {
        var (face, _) = Play(b =>
        {
            WindowSize(b, 1, 3 * Units, 10 * Units);
            MoveWindow(b, 1, 3 * Units + 1, 1);
            // Aimed at window 1 while window 0 is selected.
            b.OpVar(0x0F, Arg.Large(1 + Units), Arg.Large(1 + 3 * Units), Arg.Small(1));
            b.Print("zero");
            b.OpVar(0x0B, Arg.Small(1));
            b.Print("one");
            // Now selected, so this move lands at once.
            b.OpVar(0x0F, Arg.Large(1), Arg.Large(1), Arg.Small(1));
            b.Print("X");
        });
        Assert.Equal("zero", face.Model.RowText(1));
        Assert.Equal("   one", face.Model.RowText(5));
        Assert.Equal("X", face.Model.RowText(4));
    }

    // §15's scroll_window shifts a window's own rectangle, which only a
    // stage has the pixels to do.
    [Fact]
    public void ScrollWindowShiftsTheRectangle()
    {
        var (face, screen) = Play(b =>
        {
            WindowSize(b, 2, 3 * Units, 4 * Units);
            MoveWindow(b, 2, 1, 1);
            b.OpVar(0x0B, Arg.Small(2));
            b.Print("ab");
            b.Ext(0x14, Arg.Small(2), Arg.Large(Units));
        });
        Assert.Equal("", face.Model.RowText(1));
        Assert.Contains(screen.Settled, paint => paint is ShiftPaint { Rise: Units });
    }

    // A line count written through put_wind_prop paces the window's
    // [MORE], and -999 stops it pausing at all (§8.8.3.2.6).
    [Fact]
    public void ALineCountWrittenThroughThePropertyPacesThePause()
    {
        var (face, screen) = Play(b =>
        {
            b.Ext(0x19, Arg.Small(0), Arg.Small(WindowLedger.TextStyle), Arg.Small(2));
            b.Ext(0x19, Arg.Small(0), Arg.Small(WindowLedger.LineCount), Arg.Large(0xFC19));
            b.Print("a\nb\nc\nd\ne\nf\ng\nh");
        });
        Assert.DoesNotContain(screen.Settled.OfType<TextPaint>(), paint => paint.Cell.Style == ScreenModel.Reverse);
        Assert.Equal("h", face.Model.RowText(6));
    }

    // set_margins reaches the stage, which clips its wrapping text to
    // stay inside them (§8.8.3.2.1).
    [Fact]
    public void MarginsSetByTheOpcodeClipTheText()
    {
        var (face, _) = Play(b =>
        {
            b.Ext(0x08, Arg.Large(Units), Arg.Large(2 * Units), Arg.Small(0));
            b.Print("abcdefghij");
        });
        Assert.Equal(" abcdefg", face.Model.RowText(1));
        Assert.Equal(" hij", face.Model.RowText(2));
    }

    // erase_line's Version 6 form erases a width in units, one less
    // than the value it is given (§8.8.5.2).
    [Fact]
    public void EraseLineErasesAWidthInUnits()
    {
        var (face, _) = Play(b =>
        {
            b.Print("abcdef");
            b.OpVar(0x0F, Arg.Large(1), Arg.Large(1 + Units));
            b.OpVar(0x0E, Arg.Large(2 * Units + 1));
        });
        Assert.Equal("a  def", face.Model.RowText(1));
    }

    // A stage renders all eight windows, so erasing one above the two a
    // character face paints reaches it (§8.8.5.3).
    [Fact]
    public void ErasingAHigherWindowReachesTheStage()
    {
        var (face, _) = Play(b =>
        {
            WindowSize(b, 3, 2 * Units, 4 * Units);
            MoveWindow(b, 3, 1, 1);
            b.Print("abcdefghij");
            b.OpVar(0x0D, Arg.Large(3));
        });
        Assert.Equal("    efghij", face.Model.RowText(1));
    }

    // A stage's cursor is the printing truth: text flow moves it, and
    // the ledger's copy cannot know (§8.8.3.5). Shogun centres each
    // title line by reading property 4 back between prints, and against
    // a stale copy every line lands on the first one's row.
    [Fact]
    public void TheCursorPropertiesAnswerFromTheStagesOwnCursor()
    {
        var (face, _) = Play(b =>
        {
            b.Print("ab\n");
            b.Ext(0x13, Arg.Small(0), Arg.Small(WindowLedger.YCursor));
            b.Store(G0);
            b.Ext(0x13, Arg.Small(0), Arg.Small(WindowLedger.XCursor));
            b.Store(G0 + 1);
            b.OpVar(0x06, Arg.Var(G0));
            b.Print(" ");
            b.OpVar(0x06, Arg.Var(G0 + 1));
            // A window that is not the selected one keeps answering
            // from the ledger, where its own set_cursor wrote.
            b.OpVar(0x0F, Arg.Large(1 + 3 * Units), Arg.Large(1 + 4 * Units), Arg.Small(1));
            b.Ext(0x13, Arg.Small(1), Arg.Small(WindowLedger.YCursor));
            b.Store(G0);
            b.Print(" ");
            b.OpVar(0x06, Arg.Var(G0));
            // A property that is not a cursor answers from the ledger
            // whatever face is listening.
            b.Ext(0x13, Arg.Small(1), Arg.Small(WindowLedger.XSize));
            b.Store(G0);
            b.Print(" ");
            b.OpVar(0x06, Arg.Var(G0));
        });
        Assert.Equal($"{1 + Units} 1 {1 + 3 * Units} {10 * Units}", face.Model.RowText(2));
    }

    // get_cursor answers from the stage as well, for the same reason.
    [Fact]
    public void GetCursorAnswersFromTheStageToo()
    {
        var (face, _) = Play(b =>
        {
            var array = b.Alloc(4);
            b.Print("abc\n");
            b.OpVar(0x10, Arg.Large(array));
            b.Op2(0x0F, Arg.Large(array), Arg.Small(0));
            b.Store(G0);
            b.OpVar(0x06, Arg.Var(G0));
        });
        Assert.Equal($"{1 + Units}", face.Model.RowText(2));
    }

    // A gallery of one PNG and one placard, with the second scalable
    // to half its size on the standard window.
    private static Gallery Hung()
    {
        var png = new List<byte> { 0x89, (byte)'P', (byte)'N', (byte)'G', 0x0D, 0x0A, 0x1A, 0x0A, 0, 0, 0, 13 };
        png.AddRange(System.Text.Encoding.ASCII.GetBytes("IHDR"));
        png.AddRange([0, 0, 0, 40, 0, 0, 0, 20]);
        var art = new Dictionary<int, object> { [1] = png.ToArray(), [2] = new Placard(8, 4) };
        var scalings = new Dictionary<int, Scaling> { [2] = new(new Ratio(1, 2), null, null) };
        return new Gallery(art, 9, new Resolution(10 * Units, 6 * Units, scalings));
    }

    private static (StageFrontend Face, FakeScreen Screen) Showing(Action<StoryBuilder> body, Gallery? gallery, int columns = 10)
    {
        var b = new StoryBuilder(6);
        var main = b.Routine(0);
        body(b);
        b.Quit();
        b.InitialPc = main;
        var screen = new FakeScreen { Columns = columns };
        var face = new StageFrontend(screen, driven: true, gallery: gallery);
        new Machine(b.Build(), face, () => null, 1).Run();
        return (face, screen);
    }

    // picture_data's number 0 asks the census, and any other number
    // asks that picture's size, Reso-scaled, because a game lays its
    // whole stage out from these words (§15 picture_data).
    [Fact]
    public void PictureDataAnswersTheCensusAndTheScaledSizes()
    {
        // A branch of 2 carries on either way, so the words the call
        // wrote (or left alone) are what is read back.
        void Ask(StoryBuilder b, int number, int array)
        {
            b.Ext(0x06, Arg.Small(number), Arg.Large(array));
            b.Branch(true, 2);
            b.Op2(0x0F, Arg.Large(array), Arg.Small(0));
            b.Store(G0);
            b.OpVar(0x06, Arg.Var(G0));
            b.Print(" ");
            b.Op2(0x0F, Arg.Large(array), Arg.Small(1));
            b.Store(G0);
            b.OpVar(0x06, Arg.Var(G0));
            b.Print(" ");
        }

        var (face, _) = Showing(b =>
        {
            var array = b.Alloc(4);
            Ask(b, 0, array);
            Ask(b, 1, array);
            Ask(b, 2, array);
            Ask(b, 3, array);
        }, Hung(), columns: 40);
        // Two pictures and release 9; the PNG at its own size; the
        // placard at the room the screen earns it; then a number
        // nothing answers, which writes nothing and leaves the words
        // where they stood.
        Assert.Equal("2 9 20 40 2 4 2 4", face.Model.RowText(1));
    }

    // Without art the census counts none and every number is invalid,
    // as the cleared header bit promised (§11.1.4).
    [Fact]
    public void WithoutArtEveryPictureNumberIsInvalid()
    {
        var (face, _) = Showing(b =>
        {
            var array = b.Alloc(4);
            b.Ext(0x06, Arg.Small(0), Arg.Large(array));
            b.Branch(true, 2);
            b.Op2(0x0F, Arg.Large(array), Arg.Small(0));
            b.Store(G0);
            b.OpVar(0x06, Arg.Var(G0));
            b.Print(" ");
            b.Op2(0x0F, Arg.Large(array), Arg.Small(1));
            b.Store(G0);
            b.OpVar(0x06, Arg.Var(G0));
        }, null);
        Assert.Equal("0 0", face.Model.RowText(1));
    }

    // The header declares the art the stage actually hangs (§11.1.4).
    [Fact]
    public void TheHeaderDeclaresWhatHangs()
    {
        void Flag(StoryBuilder b)
        {
            b.Op2(0x10, Arg.Small(0), Arg.Small(1));
            b.Store(G0);
            b.Op2(0x09, Arg.Var(G0), Arg.Small(2));
            b.Store(G0);
            b.OpVar(0x06, Arg.Var(G0));
        }

        Assert.Equal("2", Showing(Flag, Hung()).Face.Model.RowText(1));
        Assert.Equal("0", Showing(Flag, null).Face.Model.RowText(1));
    }

    // A draw or erase places the picture relative to the current
    // window, with zero meaning the cursor (§8.8.3.5, §15).
    [Fact]
    public void DrawingPlacesAPictureAgainstItsWindow()
    {
        var drawn = new List<(int Number, int Line, int Column)>();
        var b = new StoryBuilder(6);
        var main = b.Routine(0);
        b.Ext(0x11, Arg.Small(2), Arg.Large(3 * Units), Arg.Large(4 * Units));
        b.Ext(0x10, Arg.Small(2), Arg.Large(1 + Units), Arg.Large(1 + Units));
        b.OpVar(0x0B, Arg.Small(2));
        b.OpVar(0x0F, Arg.Large(1 + Units), Arg.Large(1 + 2 * Units));
        b.Ext(0x05, Arg.Small(1), Arg.Large(1), Arg.Large(1));
        b.Ext(0x05, Arg.Small(1));
        b.Ext(0x07, Arg.Small(2), Arg.Large(1), Arg.Large(1));
        b.Quit();
        b.InitialPc = main;
        var face = new Watching(new StageFrontend(new FakeScreen(), driven: true, gallery: Hung()), drawn);
        new Machine(b.Build(), face, () => null, 1).Run();
        Assert.Equal(
            [
                (1, 1 + Units, 1 + Units),
                (1, 1 + 2 * Units, 1 + 3 * Units),
                (2, 1 + Units, 1 + Units),
            ],
            drawn);
    }

    // A picture number nothing answers is the one thing §15 calls
    // illegal, and without art the call passes in the conforming
    // quiet, because Infocom's own games draw without asking.
    [Fact]
    public void AnInvalidPictureNumberIsRefusedOnlyWhenArtHangs()
    {
        void Draw(StoryBuilder b) => b.Ext(0x05, Arg.Small(9), Arg.Large(1), Arg.Large(1));

        Assert.Equal("", Showing(Draw, null).Face.Model.RowText(1));
        var b = new StoryBuilder(6);
        var main = b.Routine(0);
        Draw(b);
        b.Quit();
        b.InitialPc = main;
        var face = new StageFrontend(new FakeScreen(), driven: true, gallery: Hung());
        var error = Assert.Throws<ZMachineException>(() => new Machine(b.Build(), face, () => null, 1).Run());
        Assert.Contains("picture 9 is not in the gallery", error.Message, StringComparison.Ordinal);
    }

    // The same story on a character face leaves the transcript exactly
    // as it was: none of these seams is sent, and the sweep that
    // certifies the corpus is untouched by construction.
    [Fact]
    public void ACharacterFaceHearsNoneOfIt()
    {
        var b = new StoryBuilder(6);
        var main = b.Routine(0);
        WindowSize(b, 3, 2 * Units, 4 * Units);
        MoveWindow(b, 3, 1, 1);
        b.Ext(0x08, Arg.Large(Units), Arg.Large(2 * Units), Arg.Small(0));
        b.Ext(0x19, Arg.Small(0), Arg.Small(WindowLedger.LineCount), Arg.Large(0xFC19));
        b.Ext(0x14, Arg.Small(0), Arg.Large(Units));
        b.Print("plain");
        b.OpVar(0x0E, Arg.Large(2 * Units + 1));
        b.OpVar(0x0D, Arg.Large(3));
        b.Quit();
        b.InitialPc = main;
        Assert.Equal("plain", Session.Run(b).Output);
    }
}
