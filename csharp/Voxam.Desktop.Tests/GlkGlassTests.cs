using Avalonia;
using Avalonia.Headless;
using Avalonia.Headless.XUnit;
using Avalonia.Input;
using Avalonia.Media;
using Voxam.Core;
using Voxam.Core.Glulx.Glk;
using static Voxam.Desktop.Tests.Rig;

namespace Voxam.Desktop.Tests;

/// <summary>
/// The glass wearing its Glk face: the true-colour paints a Glk display
/// draws with, and the pointer only it asks for.
/// </summary>
public sealed class GlkGlassTests
{
    private static readonly Color Red = Color.FromRgb(255, 0, 0);
    private static readonly Color Blue = Color.FromRgb(0, 102, 204);

    // A Glk display names its colours outright, and a filled rectangle
    // lands in the one it named.
    [AvaloniaFact]
    public void AFilledRectangleWearsTheColourItWasGiven()
    {
        var window = Shown(null, Theme.Classic);
        var glass = window.Glass;

        glass.Pin(glass.Columns, glass.Lines);
        glass.Settle([new ColourPaint(1, 1, 8, 8, 0xFF0000)]);

        var origin = StageOrigin(window, 1, 1);

        Assert.Equal(
            Red, Pixel(window.CaptureRenderedFrame()!, origin.X + 4, origin.Y + 4));
    }

    // A run of text is drawn whole, in its own ink on its own paper,
    // which is what a link's blue rides on.
    [AvaloniaFact]
    public void ARunOfTextIsDrawnInItsOwnInkAndPaper()
    {
        var window = Shown(null, Theme.Classic);
        var glass = window.Glass;
        var cell = glass.CellSize;

        glass.Pin(glass.Columns, glass.Lines);
        glass.Settle([
            new RunPaint(2, 1, "M", 0x0066CC, 0xFF0000, true, false),
            new RunPaint(3, 1, "M", 0x0066CC, 0xFF0000, false, true),
            new RunPaint(4, 1, "M", 0x0066CC, 0xFF0000, false, false),
            new RunPaint(1, 1, "MM", 0x0066CC, 0xFF0000, true, true),
        ]);

        var frame = window.CaptureRenderedFrame()!;
        var origin = StageOrigin(window, 1, 1);

        // The paper fills the run's whole box, and the ink is somewhere
        // inside the glyphs standing on it.
        Assert.Equal(
            Red,
            Pixel(frame, origin.X + (cell.Width * 2) - 1, origin.Y + cell.Height - 1));
        Assert.Contains(
            Blue,
            Pixels(frame, [.. Enumerable.Range(0, (int)cell.Height)
                .Select(row => new Point(origin.X + (cell.Width / 2), origin.Y + row))]));
    }

    // A picture is drawn from the part of itself the display named, so
    // what hangs off the edge of a window is not drawn.
    [AvaloniaFact]
    public void APictureIsDrawnFromThePartThatShows()
    {
        var window = Shown(null, Theme.Classic);
        var glass = window.Glass;

        glass.Pin(glass.Columns, glass.Lines);
        glass.Settle([new ClipPaint(1, 1, 4, 4, 0, 0, 2, 2, Art())]);

        var origin = StageOrigin(window, 1, 1);

        Assert.Equal(
            Red, Pixel(window.CaptureRenderedFrame()!, origin.X + 1, origin.Y + 1));

        // Bytes that decode as no picture at all draw nothing, rather
        // than half of something.
        glass.Settle([new ClipPaint(1, 1, 4, 4, 0, 0, 2, 2, [1, 2, 3])]);

        Assert.Equal(
            Red, Pixel(window.CaptureRenderedFrame()!, origin.X + 1, origin.Y + 1));
    }

    // The pointer reaches the story only where a display asked for it.
    // Glk does; the Z-Machine's faces read keys alone, and a marker
    // they never expected would be a keystroke to them.
    [AvaloniaFact]
    public void ThePointerReachesOnlyADisplayThatAskedForIt()
    {
        var window = Shown(null, Theme.Classic);
        var glass = window.Glass;

        var pressed = new Point(60, 90);
        var expected = window.TranslatePoint(pressed, glass)!.Value;

        Assert.False(glass.Clicks);
        Assert.Null(glass.Click());

        Clicked(window, pressed);

        Assert.Null(glass.Click());
        Assert.Null(glass.ReadKey(0.01));

        glass.Clicks = true;
        Clicked(window, pressed);

        Assert.Equal("\u00FE", glass.ReadKey(0.01));
        Assert.Equal(((int)expected.X, (int)expected.Y), glass.Click());

        // And reading it spends it.
        Assert.Null(glass.Click());
    }

    /// <summary>Press the pointer at a point in the window.</summary>
    private static void Clicked(MainWindow window, Point at) =>
        window.Glass.RaiseEvent(new PointerPressedEventArgs(
            window.Glass,
            new Pointer(0, PointerType.Mouse, true),
            window,
            at,
            0,
            new PointerPointProperties(RawInputModifiers.None, PointerUpdateKind.LeftButtonPressed),
            KeyModifiers.None));

    /// <summary>A two-by-two red PNG, small enough to write out by hand.</summary>
    private static byte[] Art()
    {
        var pixels = new byte[]
        {
            0x00, 0xFF, 0x00, 0x00, 0xFF, 0x00, 0x00,
            0x00, 0xFF, 0x00, 0x00, 0xFF, 0x00, 0x00,
        };

        return [.. Signature(), .. Header(2, 2), .. Data(pixels), .. End()];
    }

    private static byte[] Signature() => [0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A];

    private static byte[] Header(int width, int height)
    {
        var body = new List<byte>(Ascii("IHDR"));

        body.AddRange(Word(width));
        body.AddRange(Word(height));
        body.AddRange([8, 2, 0, 0, 0]);

        return Chunk([.. body]);
    }

    private static byte[] Data(byte[] pixels)
    {
        var body = new List<byte>(Ascii("IDAT"));

        body.AddRange(Deflated(pixels));

        return Chunk([.. body]);
    }

    private static byte[] End() => Chunk(Ascii("IEND"));

    // A stored deflate stream: the bytes as they are, in one final
    // block, wrapped in the zlib header and Adler checksum.
    private static byte[] Deflated(byte[] pixels)
    {
        var stream = new List<byte> { 0x78, 0x01, 0x01 };

        stream.AddRange([(byte)pixels.Length, (byte)(pixels.Length >> 8)]);
        stream.AddRange([(byte)~pixels.Length, (byte)(~pixels.Length >> 8)]);
        stream.AddRange(pixels);

        uint a = 1, b = 0;

        foreach (var value in pixels)
        {
            a = (a + value) % 65521;
            b = (b + a) % 65521;
        }

        stream.AddRange(Word((int)((b << 16) | a)));

        return [.. stream];
    }

    private static byte[] Chunk(byte[] body)
    {
        var whole = new List<byte>(Word(body.Length - 4));

        whole.AddRange(body);
        whole.AddRange(Word((int)Crc(body)));

        return [.. whole];
    }

    private static uint Crc(byte[] body)
    {
        var crc = 0xFFFFFFFFu;

        foreach (var value in body)
        {
            crc ^= value;

            for (var bit = 0; bit < 8; bit++)
            {
                crc = (crc >> 1) ^ (0xEDB88320u & (uint)-(crc & 1));
            }
        }

        return ~crc;
    }

    private static byte[] Ascii(string name) => [.. name.Select(letter => (byte)letter)];

    private static byte[] Word(int value) =>
        [(byte)(value >> 24), (byte)(value >> 16), (byte)(value >> 8), (byte)value];
}
