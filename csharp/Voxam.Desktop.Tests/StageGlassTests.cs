using Avalonia;
using Avalonia.Headless;
using Avalonia.Headless.XUnit;
using Avalonia.Media;
using Avalonia.Media.Imaging;
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
        var corner = StageOrigin(window, 1, 1);
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
        var origin = StageOrigin(window, 1, 1);
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
        var origin = StageOrigin(window, 1, 1);
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
        var origin = StageOrigin(window, 1, 1);
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
        var origin = StageOrigin(window, 1, 1);
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
        var origin = StageOrigin(window, 1, 1);
        var cell = window.Glass.CellSize;
        var frame = window.CaptureRenderedFrame()!;
        // The left arrow at cell four is lit across its middle and dark
        // in its corner.
        Assert.Equal(Theme.Classic.Ink, Pixel(frame, origin.X + 3 * cell.Width + cell.Width / 2, origin.Y + cell.Height / 2));
        Assert.Equal(Theme.Classic.Paper, Pixel(frame, origin.X + 3 * cell.Width + 1, origin.Y + 1));
    }

    // A Blorb beside the story hangs its art behind the stage, so the
    // game lays its windows out for the room its pictures take, even
    // while the drawing of them is still a road.
    [AvaloniaFact]
    public void ArtBesideAStoryIsHungBehindTheStage()
    {
        var bare = Story("bare.z6", ReadKey);
        var window = Shown(bare, Theme.Classic);
        Until(window, () => window.Glass.Waiting);
        Assert.False(window.Session!.Stage!.HasPictures);

        var withArt = Story("withart.z6", ReadKey);
        File.WriteAllBytes(Path.ChangeExtension(withArt, ".blb"), Packaged());
        window.Open(withArt);
        Until(window, () => window.Glass.Waiting);
        Assert.True(window.Session!.Stage!.HasPictures);
        Assert.Equal((20, 40), window.Session.Stage.PictureData(1));
    }

    // A solid square of colour, encoded as a real PNG the glass can
    // decode, so what is drawn can be measured on the frame.
    private static byte[] SolidPng(int width, int height, Color colour)
    {
        using var bitmap = new RenderTargetBitmap(new PixelSize(width, height));

        using (var context = bitmap.CreateDrawingContext(false))
        {
            context.FillRectangle(new SolidColorBrush(colour), new Rect(0, 0, width, height));
        }

        using var stream = new MemoryStream();
        bitmap.Save(stream, new PngBitmapEncoderOptions());
        return stream.ToArray();
    }

    // A Blorb of one PNG picture: an index whose only entry points at
    // the chunk that follows it.
    // Art with a signature and a header but no pixels: the size is
    // readable, and no glass can decode it.
    private static byte[] Headless() =>
        [0x89, (byte)'P', (byte)'N', (byte)'G', 0x0D, 0x0A, 0x1A, 0x0A, 0, 0, 0, 13, .. "IHDR"u8.ToArray(), 0, 0, 0, 40, 0, 0, 0, 20];

    private static byte[] Packaged(params byte[][] pictures)
    {
        var art = pictures.Length > 0 ? pictures : [Headless()];
        var index = new List<byte> { 0, 0, 0, (byte)art.Length };
        var body = new List<byte>();
        var offset = 12 + 8 + 4 + 12 * art.Length;

        for (var number = 0; number < art.Length; number++)
        {
            var picture = Chunk("PNG ", art[number]);
            index.AddRange("Pict"u8.ToArray());
            index.AddRange([0, 0, 0, (byte)(number + 1)]);
            index.AddRange([(byte)(offset >> 24), (byte)(offset >> 16), (byte)(offset >> 8), (byte)offset]);
            offset += picture.Length;
            body.AddRange(picture);
        }

        var whole = new List<byte>("IFRS"u8.ToArray());
        whole.AddRange(Chunk("RIdx", [.. index]));
        whole.AddRange(body);
        return Chunk("FORM", [.. whole]);
    }

    private static byte[] Chunk(string id, byte[] payload)
    {
        var framed = new List<byte>(System.Text.Encoding.ASCII.GetBytes(id));
        framed.AddRange([(byte)(payload.Length >> 24), (byte)(payload.Length >> 16), (byte)(payload.Length >> 8), (byte)payload.Length]);
        framed.AddRange(payload);

        if (payload.Length % 2 != 0)
        {
            framed.Add(0);
        }

        return [.. framed];
    }

    // Every row the model holds is the row the surface shows, through
    // as many scrolls as it takes to fill the screen twice. Each line
    // is printed on its own background, so a row's colour names the
    // line standing there.
    [AvaloniaFact]
    public void TheSurfaceHoldsWhatTheModelHoldsThroughAScroll()
    {
        var path = Story("scrolling.z6", b =>
        {
            b.Ext(0x19, Arg.Small(0), Arg.Small(WindowLedger.LineCount), Arg.Large(0xFC19));

            for (var line = 0; line < 40; line++)
            {
                b.Op2(0x1B, Arg.Small(2), Arg.Small(3 + (line % 6)));
                b.Print(" ");
                b.NewLine();
            }

            ReadKey(b);
        });
        var window = Shown(path, Theme.Classic);
        Until(window, () => window.Glass.Waiting);
        var model = window.Session!.Stage!.Model;
        var frame = window.CaptureRenderedFrame()!;

        // Only the rows the frame actually holds: the window's own
        // chrome takes room from the bottom of the glass.
        var rows = Enumerable.Range(1, model.Lines)
            .Where(row => StageOrigin(window, row, 1).Y + 1 < frame.PixelSize.Height)
            .ToList();
        var shown = Pixels(frame, [.. rows.Select(row => StageOrigin(window, row, 1) + new Avalonia.Vector(1, 1))]);
        var expected = string.Join(" ", rows.Select(row => $"{row}:{Painted(model.CellAt(row, 1).Background)}"));
        var actual = string.Join(" ", rows.Select((row, at) => $"{row}:{shown[at]}"));
        Assert.True(rows.Count > model.Lines / 2, $"only {rows.Count} rows of {model.Lines} are on the frame");
        Assert.Equal(expected, actual);
    }

    // The §8.3.1 colour a cell names, as the glass paints it.
    private static Color Painted(int code) => code switch
    {
        3 => Color.FromRgb(204, 0, 0),
        4 => Color.FromRgb(0, 204, 0),
        5 => Color.FromRgb(204, 204, 0),
        6 => Color.FromRgb(0, 0, 204),
        7 => Color.FromRgb(204, 0, 204),
        8 => Color.FromRgb(0, 204, 204),
        _ => Theme.Classic.Paper,
    };

    // A drawn picture lands where the game placed it, stretched to
    // the size picture_data reported, and erasing it paints its room
    // in the window's own background (§15).
    [AvaloniaFact]
    public void ADrawnPictureLandsWhereItWasPlaced()
    {
        var path = Story("drawn.z6", b =>
        {
            b.Ext(0x05, Arg.Small(1), Arg.Large(41), Arg.Large(21));
            ReadKey(b);
            b.Op2(0x1B, Arg.Small(2), Arg.Small(4));
            b.Ext(0x07, Arg.Small(1), Arg.Large(41), Arg.Large(21));
        });
        File.WriteAllBytes(Path.ChangeExtension(path, ".blb"), Packaged(SolidPng(8, 6, Colors.Red)));
        var window = Shown(path, Theme.Classic);
        var glass = window.Glass;
        Until(window, () => glass.Waiting);
        Assert.Equal((6, 8), window.Session!.Stage!.PictureData(1));

        var origin = StageOrigin(window, 1, 1);
        var inside = new Point(origin.X + 20 + 4, origin.Y + 40 + 3);
        var outside = new Point(origin.X + 20 + 4, origin.Y + 40 - 2);
        Assert.Equal(Colors.Red, Pixel(window.CaptureRenderedFrame()!, inside.X, inside.Y));
        Assert.Equal(Theme.Classic.Paper, Pixel(window.CaptureRenderedFrame()!, outside.X, outside.Y));

        // Erased, its room wears the window's background.
        glass.Press(" ");
        Until(window, () => Notice(window) == "The story has ended.");
        Assert.Equal(Green, Pixel(window.CaptureRenderedFrame()!, inside.X, inside.Y));
    }

    // Art is decoded once and remembered, because a game redraws its
    // chrome every turn; art nothing can decode is ignored where it
    // lands, which is presentation and never state. Opening another
    // story lets both the surface and the decoded art go.
    [AvaloniaFact]
    public void DecodedArtIsRememberedAndUndecodableArtIsIgnored()
    {
        var path = Story("twice.z6", b =>
        {
            b.Ext(0x05, Arg.Small(1), Arg.Large(1), Arg.Large(1));
            b.Ext(0x05, Arg.Small(1), Arg.Large(41), Arg.Large(1));
            b.Ext(0x05, Arg.Small(2), Arg.Large(1), Arg.Large(41));
            ReadKey(b);
        });
        File.WriteAllBytes(Path.ChangeExtension(path, ".blb"), Packaged(SolidPng(8, 6, Colors.Red), Headless()));
        var window = Shown(path, Theme.Classic);
        Until(window, () => window.Glass.Waiting);
        var origin = StageOrigin(window, 1, 1);
        var frame = window.CaptureRenderedFrame()!;
        // Both copies of the first picture, the second forty units
        // down, and nothing where the other could not be decoded.
        var probes = new[]
        {
            new Point(origin.X + 2, origin.Y + 2),
            new Point(origin.X + 2, origin.Y + 42),
            new Point(origin.X + 42, origin.Y + 2),
        };
        Assert.Equal([Colors.Red, Colors.Red, Theme.Classic.Paper], Pixels(frame, probes));

        var plain = new StoryBuilder(5);
        ReadKey(plain);
        plain.Quit();
        var after = Path.Combine(_directory.FullName, "after.z5");
        File.WriteAllBytes(after, plain.Build());
        window.Open(after);
        Until(window, () => window.Session?.Face is not null && window.Glass.Waiting);
        Assert.Equal(Theme.Classic.Paper, Pixel(window.CaptureRenderedFrame()!, origin.X + 2, origin.Y + 2));
    }

    // A glass nothing has pinned mints its surface at whatever it
    // measures, which is what settling on it outside a session does.
    [AvaloniaFact]
    public void AnUnpinnedGlassSizesItsOwnSurface()
    {
        var window = Shown(null);
        ((Voxam.Core.IStageScreen)window.Glass).Settle([new Voxam.Core.FillPaint(1, 1, 8, 8, 4)]);
        Until(window, () => true);
        var origin = StageOrigin(window, 1, 1);
        Assert.Equal(Green, Pixel(window.CaptureRenderedFrame()!, origin.X + 1, origin.Y + 1));
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
