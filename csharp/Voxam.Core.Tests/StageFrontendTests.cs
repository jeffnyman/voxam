using Voxam.Core.Tests.Support;

namespace Voxam.Core.Tests;

/// <summary>The Version 6 face: a stage kept faithful, and its paints handed to a glass (§8.8).</summary>
public class StageFrontendTests
{
    private const int G0 = 0x10;
    private const int Units = 2;

    /// <summary>A glass that records every paint it is asked to carry out and answers queued keys.</summary>
    private sealed class FakeScreen : IStageScreen
    {
        public int Columns { get; set; } = 10;

        public int Lines { get; set; } = 4;

        public int FontWidth => Units;

        public int FontHeight => Units;

        public Queue<string?> Keys { get; } = new();

        public List<Paint> Settled { get; } = [];

        public string? ReadKey(double? timeoutSeconds) => Keys.Count > 0 ? Keys.Dequeue() : null;

        public void Settle(IReadOnlyList<Paint> paints) => Settled.AddRange(paints);
    }

    private static (StageFrontend Face, FakeScreen Screen) Staged()
    {
        var screen = new FakeScreen();
        return (new StageFrontend(screen), screen);
    }

    [Fact]
    public void TheFaceClaimsWhatAStageHas()
    {
        var (face, _) = Staged();
        Assert.False(face.HasStatusLine);
        Assert.True(face.HasScreenSplitting);
        Assert.False(face.HasSounds);
        Assert.True(face.HasBold);
        Assert.True(face.HasItalic);
        Assert.True(face.HasFixedPitch);
        Assert.True(face.HasTimedInput);
        Assert.True(face.HasColours);
        Assert.True(face.HasCharacterGraphics);
        Assert.Equal((10, 4), (face.ScreenColumns, face.ScreenLines));
        Assert.Equal((Units, Units), (face.FontWidth, face.FontHeight));
    }

    // A Version 6 game draws its own status area (§8.2), so a status
    // line arriving here is a wiring fault worth hearing about.
    [Fact]
    public void AStatusLineIsRefused()
    {
        var (face, _) = Staged();
        Assert.Equal(
            "version 6 draws its own status area; the stage has no line (§8.2)",
            Assert.Throws<ZMachineException>(() => face.ShowStatus(new Status("here", 0, 0, false))).Message);
    }

    // Every operation settles what it drew, in units, on the glass.
    [Fact]
    public void WhatTheStageDrawsIsSettledOnTheGlass()
    {
        var (face, screen) = Staged();
        face.Write("hi");
        Assert.Equal(
            [
                new TextPaint(1, 1, new Cell("h", ScreenModel.Roman, ScreenModel.DefaultColour, ScreenModel.DefaultColour, 1)),
                new TextPaint(1, 1 + Units, new Cell("i", ScreenModel.Roman, ScreenModel.DefaultColour, ScreenModel.DefaultColour, 1)),
            ],
            screen.Settled);
        screen.Settled.Clear();
        face.EraseWindow(-1);
        Assert.Equal([new FillPaint(1, 1, 4 * Units, 10 * Units, ScreenModel.DefaultColour)], screen.Settled);
    }

    // The window seams the machine drives reach the stage: placing,
    // margins, scrolling, the pixel erase, and the line count.
    [Fact]
    public void TheStageSeamsReachTheModel()
    {
        var (face, screen) = Staged();
        face.PlaceWindow(2, 1 + Units, 1, 2 * Units, 4 * Units);
        face.SetWindow(2);
        Assert.Equal(2, face.Model.Selected);
        face.SetMargins(2, Units, 0);
        face.Write("abc");
        Assert.Equal(" abc", face.Model.RowText(2));
        face.SetCursor(1, 1 + Units);
        Assert.Equal((1, 1 + Units), face.CursorPosition());
        face.EraseLine(Units);
        Assert.Equal("  bc", face.Model.RowText(2));
        screen.Settled.Clear();
        face.ScrollWindow(2, Units);
        Assert.Contains(screen.Settled, paint => paint is ShiftPaint);
        face.SetLineCount(2, StageModel.NeverMore);
        face.SplitWindow(Units);
        face.SetStyle(ScreenModel.Bold);
        face.SetFont(3);
        face.SetColour(3, 4);
        face.SetBuffering(false);
        face.SetWindow(0);
        face.Write("z");
        Assert.Equal(new Cell("z", ScreenModel.Roman, ScreenModel.DefaultColour, ScreenModel.DefaultColour, 1), face.Model.CellAt(2, 1));
        face.EraseLine();
        face.WriteRectangle(["pq"]);
        Assert.Equal("zpq", face.Model.RowText(2));
    }

    // A driven session has nobody to press the key, so its stage
    // prints straight past what would otherwise pause.
    [Fact]
    public void ADrivenStageNeverPauses()
    {
        var screen = new FakeScreen();
        var face = new StageFrontend(screen, driven: true);
        face.Write("a\nb\nc\nd\ne\nf");
        Assert.Empty(screen.Keys);
        Assert.DoesNotContain(screen.Settled.OfType<TextPaint>(), paint => paint.Cell.Style == ScreenModel.Reverse);
        Assert.Equal("f", face.Model.RowText(4));
    }

    // A glass with no art behind it answers no picture, and the calls
    // that would draw one settle nothing.
    [Fact]
    public void WithoutArtNoPictureIsDrawn()
    {
        var (face, screen) = Staged();
        Assert.False(face.HasPictures);
        Assert.Null(face.PictureData(1));
        Assert.Equal((0, 0), face.PictureCensus());
        face.DrawPicture(1, 1, 1);
        face.ErasePicture(1, 1, 1);
        Assert.Empty(screen.Settled);
    }

    // A picture is settled as its pixels stretched to the size
    // picture_data reported; a placard has a size and no pixels, so
    // drawing it shows nothing, which is the conforming answer.
    [Fact]
    public void APictureIsSettledAtTheSizeItWasMeasured()
    {
        var png = new List<byte> { 0x89, (byte)'P', (byte)'N', (byte)'G', 0x0D, 0x0A, 0x1A, 0x0A, 0, 0, 0, 13 };
        png.AddRange("IHDR"u8.ToArray());
        png.AddRange([0, 0, 0, 8, 0, 0, 0, 6]);
        var pixels = png.ToArray();
        var art = new Dictionary<int, object> { [1] = pixels, [2] = new Placard(4, 2) };
        var scalings = new Dictionary<int, Scaling> { [1] = new(new Ratio(2, 1), null, null) };
        var screen = new FakeScreen();
        var face = new StageFrontend(screen, gallery: new Gallery(art, 3, new Resolution(10 * Units, 4 * Units, scalings)));
        Assert.True(face.HasPictures);
        Assert.Equal((2, 3), face.PictureCensus());

        // The screen is the standard window, so the room is one and
        // the picture wears its own doubling.
        Assert.Equal((12, 16), face.PictureData(1));
        face.DrawPicture(1, 5, 7);
        Assert.Equal([new PicturePaint(5, 7, 12, 16, pixels)], screen.Settled);

        // A placard takes its room and shows nothing.
        screen.Settled.Clear();
        face.DrawPicture(2, 1, 1);
        face.DrawPicture(9, 1, 1);
        Assert.Empty(screen.Settled);
    }

    // Erasing a picture paints its room in the selected window's own
    // background (§15 erase_picture).
    [Fact]
    public void ErasingAPicturePaintsItsRoom()
    {
        var art = new Dictionary<int, object> { [1] = new Placard(4, 2) };
        var screen = new FakeScreen();
        var face = new StageFrontend(screen, gallery: new Gallery(art, 0, null));
        face.SetColour(ScreenModel.CurrentColour, 4);
        face.ErasePicture(1, 3, 5);
        Assert.Equal([new FillPaint(3, 5, 2, 4, 4)], screen.Settled);
        screen.Settled.Clear();
        face.ErasePicture(9, 1, 1);
        Assert.Empty(screen.Settled);
    }

    [Fact]
    public void KeysAreReadRawWithOrWithoutATimeout()
    {
        var (face, screen) = Staged();
        screen.Keys.Enqueue(null);
        screen.Keys.Enqueue("x");
        Assert.Equal("x", face.ReadKey(null));
        Assert.Null(face.ReadKey(0.5));
    }

    [Fact]
    public void LinesAreEditedAndEchoedThroughTheStage()
    {
        var (face, screen) = Staged();
        face.Write(">");

        foreach (var key in new[] { "l", "o", "\u007f", "o", "\n" })
        {
            screen.Keys.Enqueue(key);
        }

        Assert.Equal("lo", face.ReadLine());
        Assert.Equal(">lo", face.Model.RowText(1));
    }

    // A timed read keeps its half-typed line when the clock runs out,
    // shows the prompt again after a printing interrupt, and can be
    // abandoned outright (§15 read remarks).
    [Fact]
    public void ATimedLineReadSurvivesItsInterruptsOrIsAbandoned()
    {
        var (face, screen) = Staged();
        face.Write(">");
        face.BeginInput();
        screen.Keys.Enqueue("w");
        screen.Keys.Enqueue(LineEditor.Expired);
        Assert.Null(face.ReadLineUntil(5));
        Assert.Equal(">w", face.Model.RowText(1));
        face.Write("\nrumble\n");
        face.ResumeInput();
        Assert.Equal(">", face.Model.RowText(3));
        screen.Keys.Enqueue("a");
        screen.Keys.Enqueue("\n");
        Assert.Equal("wa", face.ReadLineUntil(5));

        screen.Keys.Enqueue("z");
        screen.Keys.Enqueue(LineEditor.Expired);
        Assert.Null(face.ReadLineUntil(5));
        face.AbandonInput();
        Assert.Equal("", face.Model.RowText(4).Trim());
        face.AbandonInput();
        screen.Keys.Enqueue("\n");
        Assert.Equal("", face.ReadLineUntil(5));
    }

    [Fact]
    public void ATimedLineReadRunsOutItsOwnClock()
    {
        var (face, _) = Staged();
        Assert.Null(face.ReadLineUntil(0));
    }

    // A screenful behind [MORE]: the prompt is laid over the pause
    // position in the window's colours reversed, the key that answers
    // is spent, and the patch is rebuilt from the stage's own grid so
    // freshly flowed text is not burned over (§8.8.3.2.6).
    [Fact]
    public void AScreenfulPausesBehindMoreAndRepairsWhatItCovered()
    {
        var (face, screen) = Staged();
        screen.Keys.Enqueue(null);
        screen.Keys.Enqueue(" ");
        face.SetColour(3, 4);
        face.Write("ab\ncd\nef\ngh");
        var prompt = screen.Settled.OfType<TextPaint>().Where(paint => paint.Cell.Style == ScreenModel.Reverse).ToList();
        Assert.Equal("[MORE]", string.Concat(prompt.Select(paint => paint.Cell.Character)));
        Assert.Equal(1 + 3 * Units, prompt[0].Line);
        Assert.Equal((3, 4), (prompt[0].Cell.Foreground, prompt[0].Cell.Background));
        Assert.Empty(screen.Keys);
        var repair = screen.Settled.IndexOf(new FillPaint(1 + 3 * Units, 1, Units, 6 * Units, 4));
        Assert.True(repair > 0);
        // The prompt covered "gh", which comes back as itself.
        Assert.Equal("gh", string.Concat(screen.Settled.Skip(repair).OfType<TextPaint>().Select(paint => paint.Cell.Character)));
    }

    // A pause landing on text puts that text back, character by
    // character, rather than burning a blank box over it.
    [Fact]
    public void APauseRebuildsTheTextItCovered()
    {
        var (face, screen) = Staged();
        screen.Keys.Enqueue(" ");
        face.SetCursor(1 + 3 * Units, 1);
        face.Write("XXXXXXXX");
        face.SetCursor(1, 1);
        screen.Settled.Clear();
        face.Write("a\nb\nc\n");
        var fill = screen.Settled.FindIndex(paint => paint is FillPaint { Line: 1 + 3 * Units });
        Assert.True(fill > 0);
        var repaired = screen.Settled.Skip(fill).OfType<TextPaint>().Where(paint => paint.Cell.Style == ScreenModel.Roman).ToList();
        Assert.Equal("XXXXXX", string.Concat(repaired.Select(paint => paint.Cell.Character)));
    }

    // A pause landing where the prompt would run off the screen repairs
    // only the cells the stage actually holds.
    [Fact]
    public void APauseRepairsOnlyTheCellsTheStageHolds()
    {
        var screen = new FakeScreen { Columns = 4, Lines = 3 };
        var face = new StageFrontend(screen);
        screen.Keys.Enqueue(" ");
        face.Write("wxyz\nabcd\nefgh");
        Assert.Empty(screen.Keys);
        Assert.Equal(4, face.Model.Columns);
    }

    // The whole face driven by a machine: a Version 6 story places a
    // window, prints into it, and the stage holds what it drew.
    [Fact]
    public void AVersionSixStoryPlaysOnTheStage()
    {
        var b = new StoryBuilder(6);
        var main = b.Routine(0);
        b.OpVar(0x0A, Arg.Small(2 * Units));
        b.OpVar(0x0B, Arg.Small(1));
        b.Print("top");
        b.OpVar(0x0B, Arg.Small(0));
        b.Print("story");
        b.OpVar(0x16, Arg.Small(1));
        b.Store(G0);
        b.Quit();
        b.InitialPc = main;
        var screen = new FakeScreen();
        var face = new StageFrontend(screen);
        screen.Keys.Enqueue(" ");
        new Machine(b.Build(), face, () => null, 1, face.ReadKey, face.ReadLineUntil).Run();
        Assert.Equal("top", face.Model.RowText(1));
        Assert.Equal("story", face.Model.RowText(3));
        Assert.NotEmpty(screen.Settled);
    }
}
