using Avalonia.Headless;
using Avalonia.Headless.XUnit;
using Avalonia.Media;
using Voxam.Core;
using Voxam.Core.Tests.Support;
using static Voxam.Desktop.Tests.Rig;

namespace Voxam.Desktop.Tests;

/// <summary>A Version 6 stage drawn on the glass, measured on the pixels of rendered frames (§8.8).</summary>
public sealed class StageGlassTests : IDisposable
{
    private static readonly Color Green = Color.FromRgb(0, 204, 0);
    private readonly DirectoryInfo _directory = Directory.CreateTempSubdirectory("voxam-stage");

    public void Dispose() => _directory.Delete(recursive: true);

    // A Version 6 story runs from a main routine rather than an
    // instruction address (§5.5).
    private string Story(string name, Action<StoryBuilder> body)
    {
        var b = new StoryBuilder(6);
        var main = b.Routine(0);
        body(b);
        b.Quit();
        b.InitialPc = main;
        var path = Path.Combine(_directory.FullName, name);
        File.WriteAllBytes(path, b.Build());
        return path;
    }

    private static void ReadKey(StoryBuilder b)
    {
        b.OpVar(0x16, Arg.Small(1));
        b.Store(0x10);
    }

    // Black on green, so a printed cell is a block of colour a frame
    // can be measured at rather than a glyph's own scattered pixels.
    private static void OnGreen(StoryBuilder b) => b.Op2(0x1B, Arg.Small(2), Arg.Small(4));

    // A Version 6 story gets the stage, and what it prints reaches the
    // glass in the window's own colours.
    [AvaloniaFact]
    public void AVersionSixStoryPlaysOnTheStage()
    {
        var path = Story("staged.z6", b =>
        {
            OnGreen(b);
            b.Print("A");
            ReadKey(b);
        });
        var window = Shown(path, Theme.Classic);
        Until(window, () => window.Glass.Waiting);
        Assert.Null(window.Session!.Face);
        Assert.Equal("A", window.Session.Stage!.Model.RowText(1));
        var frame = window.CaptureRenderedFrame()!;
        var corner = CellOrigin(window, 1, 1);
        Assert.Equal(Green, Pixel(frame, corner.X + 1, corner.Y + 1));
        Assert.Equal(Theme.Classic.Paper, Pixel(frame, corner.X + 1, corner.Y + window.Glass.CellSize.Height + 1));
    }

    // The stage places its windows in units, so a cell lands where the
    // game put it and not on a cell boundary (§8.8.3.4).
    [AvaloniaFact]
    public void AWindowPlacedInUnitsLandsThere()
    {
        var path = Story("placed.z6", b =>
        {
            b.Ext(0x11, Arg.Small(2), Arg.Large(40), Arg.Large(200));
            b.Ext(0x10, Arg.Small(2), Arg.Large(31), Arg.Large(21));
            b.OpVar(0x0B, Arg.Small(2));
            OnGreen(b);
            b.Print("M");
            ReadKey(b);
        });
        var window = Shown(path, Theme.Classic);
        Until(window, () => window.Glass.Waiting);
        Assert.Equal(2, window.Session!.Stage!.Model.Selected);
        var origin = CellOrigin(window, 1, 1);
        var frame = window.CaptureRenderedFrame()!;
        // The cell's own corner, at unit (31, 21) counted from one.
        Assert.Equal(Green, Pixel(frame, origin.X + 20 + 1, origin.Y + 30 + 1));
        Assert.Equal(Theme.Classic.Paper, Pixel(frame, origin.X + 20 + 1, origin.Y + 30 - 1));
        Assert.Equal(Theme.Classic.Paper, Pixel(frame, origin.X + 20 - 1, origin.Y + 30 + 1));
    }

    // §8.8.3.6's scroll slides the pixels a window already holds, and
    // the strip it exposes comes back in the window's background.
    [AvaloniaFact]
    public void ScrollingAWindowSlidesThePixelsItHolds()
    {
        var path = Story("scrolled.z6", b =>
        {
            b.Print("a\n");
            OnGreen(b);
            b.Print("X");
            ReadKey(b);
        });
        var window = Shown(path, Theme.Classic);
        Until(window, () => window.Glass.Waiting);
        Assert.Equal("X", window.Session!.Stage!.Model.RowText(2));
        var origin = CellOrigin(window, 1, 1);
        var height = window.Glass.CellSize.Height;
        var before = window.CaptureRenderedFrame()!;
        Assert.Equal(Green, Pixel(before, origin.X + 1, origin.Y + height + 1));
        Assert.Equal(Theme.Classic.Paper, Pixel(before, origin.X + 1, origin.Y + 1));

        // The story is parked, so the scroll is driven here, the way
        // the machine would drive it, and settles at once.
        window.Session.Stage.ScrollWindow(0, (int)Math.Round(height));
        Until(window, () => window.Session.Stage.Model.RowText(1) == "X");
        var after = window.CaptureRenderedFrame()!;
        Assert.Equal(Green, Pixel(after, origin.X + 1, origin.Y + 1));
        Assert.Equal(Theme.Classic.Paper, Pixel(after, origin.X + 1, origin.Y + height + 1));
    }

    // Opening another story strikes the stage's surface, so nothing of
    // the first shows through the second.
    [AvaloniaFact]
    public void OpeningAnotherStoryStrikesTheStage()
    {
        var first = Story("first.z6", b =>
        {
            OnGreen(b);
            b.Print("F");
            ReadKey(b);
        });
        var window = Shown(first, Theme.Classic);
        Until(window, () => window.Glass.Waiting);
        Assert.Equal("F", window.Session!.Stage!.Model.RowText(1));
        var origin = CellOrigin(window, 1, 1);
        Assert.Equal(Green, Pixel(window.CaptureRenderedFrame()!, origin.X + 1, origin.Y + 1));

        var b = new StoryBuilder(5);
        ReadKey(b);
        b.Quit();
        var second = Path.Combine(_directory.FullName, "second.z5");
        File.WriteAllBytes(second, b.Build());
        window.Open(second);
        Until(window, () => window.Session?.Face is not null && window.Glass.Waiting);
        Assert.Null(window.Session!.Stage);
        Assert.Equal(Theme.Classic.Paper, Pixel(window.CaptureRenderedFrame()!, origin.X + 1, origin.Y + 1));
    }

    // Font 3's shapes are drawn from their own pixels on the stage too,
    // the solid block filling its cell edge to edge (§16).
    [AvaloniaFact]
    public void TheStageDrawsFontThreeFromItsOwnPixels()
    {
        var path = Story("shapes.z6", b =>
        {
            b.Op2(0x1B, Arg.Small(9), Arg.Small(2));
            b.Ext(0x04, Arg.Small(3));
            b.Store(0x10);
            b.Print("6");
            b.Ext(0x04, Arg.Small(1));
            b.Store(0x10);
            ReadKey(b);
        });
        var window = Shown(path, Theme.Classic);
        Until(window, () => window.Glass.Waiting);
        Assert.Equal("6", window.Session!.Stage!.Model.RowText(1));
        var origin = CellOrigin(window, 1, 1);
        var cell = window.Glass.CellSize;
        var frame = window.CaptureRenderedFrame()!;
        Assert.Equal(Theme.Classic.Ink, Pixel(frame, origin.X + cell.Width / 2, origin.Y + cell.Height / 2));
        Assert.Equal(Theme.Classic.Ink, Pixel(frame, origin.X + 1, origin.Y + 1));
    }

    // The stage wears the styles a window sets, each in its own face
    // (§8.8.3.2.3), and font 3's part-lit shapes keep their dark pixels.
    [AvaloniaFact]
    public void TheStageWearsItsStylesAndPartLitShapes()
    {
        var path = Story("dressed.z6", b =>
        {
            b.OpVar(0x11, Arg.Small(2));
            b.Print("B");
            // The styles accumulate until Roman clears them (§8.8.3.2.3),
            // so italic alone needs the reset first.
            b.OpVar(0x11, Arg.Small(0));
            b.OpVar(0x11, Arg.Small(4));
            b.Print("I");
            b.OpVar(0x11, Arg.Small(6));
            b.Print("X");
            b.OpVar(0x11, Arg.Small(0));
            b.Op2(0x1B, Arg.Small(9), Arg.Small(2));
            b.Ext(0x04, Arg.Small(3));
            b.Store(0x10);
            b.Print("!");
            b.Ext(0x04, Arg.Small(1));
            b.Store(0x10);
            ReadKey(b);
        });
        var window = Shown(path, Theme.Classic);
        Until(window, () => window.Glass.Waiting);
        Assert.Equal("BIX!", window.Session!.Stage!.Model.RowText(1));
        var origin = CellOrigin(window, 1, 1);
        var cell = window.Glass.CellSize;
        var frame = window.CaptureRenderedFrame()!;
        // The left arrow at cell four is lit across its middle and dark
        // in its corner.
        Assert.Equal(Theme.Classic.Ink, Pixel(frame, origin.X + 3 * cell.Width + cell.Width / 2, origin.Y + cell.Height / 2));
        Assert.Equal(Theme.Classic.Paper, Pixel(frame, origin.X + 3 * cell.Width + 1, origin.Y + 1));
    }

    // A story longer than the stage holds waits behind [MORE] for a
    // player, and runs to its end once keys arrive, the last screenful
    // standing and the prompt leaving nothing behind (§8.8.3.2.6).
    [AvaloniaFact]
    public void AScreenfulPausesTheStageBehindMore()
    {
        var path = Story("paused.z6", b =>
        {
            for (var line = 0; line < 60; line++)
            {
                b.Print("line\n");
            }
        });
        var window = Shown(path, Theme.Classic);
        var glass = window.Glass;
        Until(window, () => window.Session?.Stage is not null);
        Assert.NotEqual("The story has ended.", Notice(window));

        // How many screenfuls sixty lines make is the platform's own,
        // so every pause is let go until the story reaches its end.
        Until(window, () =>
        {
            glass.Press(" ");
            return Notice(window) == "The story has ended.";
        });
        Assert.Equal("line", window.Session!.Stage!.Model.RowText(1));
        Assert.NotNull(window.CaptureRenderedFrame());
    }
}
