using Avalonia;
using Avalonia.Controls;
using Avalonia.Headless;
using Avalonia.Headless.XUnit;
using Avalonia.Media;
using Voxam.Core.Tests.Support;
using static Voxam.Desktop.Tests.Rig;

namespace Voxam.Desktop.Tests;

/// <summary>The glass's dress, measured on the pixels of rendered frames.</summary>
public sealed class GlassTests : IDisposable
{
    private readonly DirectoryInfo _directory = Directory.CreateTempSubdirectory("voxam-glass");

    public void Dispose() => _directory.Delete(recursive: true);

    private string Story(string name, Action<StoryBuilder> body) => Rig.Story(_directory, name, body);

    // The window opens to the classic eighty by twenty-four, whatever
    // the face measures.
    [AvaloniaFact]
    public void TheWindowOpensAtTheClassicGrid()
    {
        var window = Shown(null);
        Assert.Equal((Glass.OpeningColumns, Glass.OpeningLines), (window.Glass.Columns, window.Glass.Lines));
        Assert.True(window.Glass.CellSize.Width > 5 && window.Glass.CellSize.Height > 10);
    }

    // The theme paints the paper, a game's own white and black wear
    // the theme (§8.3.3), a named colour keeps its value, and reverse
    // swaps the pair.
    [AvaloniaFact]
    public void TheThemeDressesThePaperAndTheBookFollowsIt()
    {
        var path = Story("themed.z5", b =>
        {
            b.Print("A");
            b.Op2(0x1B, Arg.Small(9), Arg.Small(2));
            b.Print("B");
            b.Op2(0x1B, Arg.Small(3), Arg.Small(4));
            b.Print("C");
            b.Op2(0x1B, Arg.Small(1), Arg.Small(1));
            b.OpVar(0x11, Arg.Small(1));
            b.Print("D");
            b.OpVar(0x11, Arg.Small(0));
            ReadKey(b);
        });
        var window = Shown(path, Theme.Sepia);
        var glass = window.Glass;
        Until(window, () => glass.Waiting);
        var frame = window.CaptureRenderedFrame()!;
        var row = 1;
        var corner = CellOrigin(window, row, 1);
        Assert.Equal(Theme.Sepia.Paper, Pixel(frame, corner.X + 1, corner.Y + 1));
        var black = CellOrigin(window, row, 2);
        Assert.Equal(Theme.Sepia.Paper, Pixel(frame, black.X + 1, black.Y + 1));
        var green = CellOrigin(window, row, 3);
        Assert.Equal(Color.FromRgb(0, 204, 0), Pixel(frame, green.X + 1, green.Y + 1));
        var reversed = CellOrigin(window, row, 4);
        Assert.Equal(Theme.Sepia.Ink, Pixel(frame, reversed.X + 1, reversed.Y + 1));
        var far = CellOrigin(window, 1, glass.Columns);
        Assert.Equal(Theme.Sepia.Paper, Pixel(frame, far.X + 1, far.Y + 1));
    }

    // Font 3 cells are the §16 bitmaps stretched over the cell: the
    // solid block is ink throughout, the blank is paper, and a road
    // tip lights exactly its corner.
    [AvaloniaFact]
    public void FontThreeIsDrawnFromItsOwnPixels()
    {
        var path = Story("font3.z5", b =>
        {
            b.Ext(0x04, Arg.Small(3));
            b.Store(G0);
            b.Print("6 G");
            b.Ext(0x04, Arg.Small(1));
            b.Store(G0);
            ReadKey(b);
        });
        var window = Shown(path, Theme.Classic);
        var glass = window.Glass;
        Until(window, () => glass.Waiting);
        var frame = window.CaptureRenderedFrame()!;
        var cell = glass.CellSize;
        var row = 1;
        var solid = CellOrigin(window, row, 1);
        Assert.Equal(Theme.Classic.Ink, Pixel(frame, solid.X + cell.Width / 2, solid.Y + cell.Height / 2));
        Assert.Equal(Theme.Classic.Ink, Pixel(frame, solid.X + 1, solid.Y + 1));
        var blank = CellOrigin(window, row, 2);
        Assert.Equal(Theme.Classic.Paper, Pixel(frame, blank.X + cell.Width / 2, blank.Y + cell.Height / 2));
        var tip = CellOrigin(window, row, 3);
        Assert.Equal(Theme.Classic.Paper, Pixel(frame, tip.X + cell.Width / 2, tip.Y + cell.Height / 2));
        var lit = Math.Round(tip.X + cell.Width) - 1;
        Assert.Equal(Theme.Classic.Ink, Pixel(frame, lit, Math.Round(tip.Y)));
    }

    // The caret underlines the cursor's cell while the machine waits
    // for a key, and is gone once the story has moved on.
    [AvaloniaFact]
    public void TheCaretShowsOnlyWhileTheMachineWaits()
    {
        var path = Story("caret.z5", b =>
        {
            b.Print("A");
            ReadKey(b);
        });
        var window = Shown(path, Theme.Classic);
        var glass = window.Glass;
        Until(window, () => glass.Waiting);
        var cell = glass.CellSize;
        var under = CellOrigin(window, 1, 2);
        var frame = window.CaptureRenderedFrame()!;
        Assert.Equal(Theme.Classic.Ink, Pixel(frame, under.X + cell.Width / 2, under.Y + cell.Height - 1));
        glass.Press(" ");
        Until(window, () => Notice(window) == "The story has ended.");
        Assert.False(glass.Waiting);
        frame = window.CaptureRenderedFrame()!;
        Assert.Equal(Theme.Classic.Paper, Pixel(frame, under.X + cell.Width / 2, under.Y + cell.Height - 1));
    }

    [AvaloniaFact]
    public void TheCommandLineNamesAStoryAndATheme()
    {
        Assert.Equal(new Launch(null, null, null), Launch.Parse([]));
        Assert.Equal(new Launch("tale.z5", null, null), Launch.Parse(["tale.z5"]));
        Assert.Equal(new Launch("tale.z5", Theme.Sepia, null), Launch.Parse(["--theme", "sepia", "tale.z5"]));
        Assert.Equal(new Launch("tale.z5", Theme.Light, null), Launch.Parse(["tale.z5", "--theme", "paper"]));
        Assert.Equal("voxam: no theme named neon; the themes are dark, paper, sepia, classic", Launch.Parse(["--theme", "neon"]).Complaint);
        Assert.Equal("voxam: usage: Voxam [--theme NAME] [STORY]", Launch.Parse(["--bogus"]).Complaint);
        Assert.Equal("voxam: usage: Voxam [--theme NAME] [STORY]", Launch.Parse(["one.z5", "two.z5"]).Complaint);
        Assert.Equal("voxam: usage: Voxam [--theme NAME] [STORY]", Launch.Parse(["--theme"]).Complaint);
        Assert.Null(Launch.Parse(["--bogus"]).Game);
    }

    // A complaint takes the notice line and no story opens.
    [AvaloniaFact]
    public void AComplaintStandsInForTheStory()
    {
        var window = new MainWindow(Launch.Parse(["--theme", "neon"]));
        window.Show();
        Until(window, () => Notice(window).StartsWith("voxam: no theme named neon", StringComparison.Ordinal));
        Assert.Null(window.Session);
    }
}
