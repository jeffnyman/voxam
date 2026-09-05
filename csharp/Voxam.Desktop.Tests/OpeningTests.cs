using Avalonia;

namespace Voxam.Desktop.Tests;

public class OpeningTests
{
    // The cap is a share of the screen, in the window's own units
    // rather than the screen's pixels, so a scaled display is not
    // mistaken for a larger one.
    [Fact]
    public void TheCapIsAShareOfTheScreenInTheWindowsOwnUnits()
    {
        var unscaled = Opening.Capped(new PixelSize(1920, 1080), 1);

        Assert.Equal(1920 * Opening.Fill, unscaled.Width);
        Assert.Equal(1080 * Opening.Fill, unscaled.Height);

        var scaled = Opening.Capped(new PixelSize(2560, 1440), 2);

        Assert.Equal(1280 * Opening.Fill, scaled.Width);
        Assert.Equal(720 * Opening.Fill, scaled.Height);
    }

    // A screen that reports nothing usable caps nothing: the opening
    // grid is a sane size on its own, and a measurement that cannot be
    // trusted is no reason to shrink a window to nothing.
    [Fact]
    public void AnUnusableScreenCapsNothing()
    {
        foreach (var (size, scaling) in new[]
        {
            (new PixelSize(0, 1080), 1.0),
            (new PixelSize(1920, 0), 1.0),
            (new PixelSize(1920, 1080), 0.0),
            (new PixelSize(1920, 1080), -1.0),
        })
        {
            var uncapped = Opening.Capped(size, scaling);

            Assert.Equal(double.PositiveInfinity, uncapped.Width);
            Assert.Equal(double.PositiveInfinity, uncapped.Height);
        }
    }

    // Centred in the working area rather than in the screen, so a
    // taskbar or a menu bar is not counted as room the window can have.
    [Fact]
    public void AWindowIsCentredInTheWorkingArea()
    {
        var working = new PixelRect(0, 40, 1920, 1040);

        Assert.Equal(
            new PixelPoint(460, 340),
            Opening.Centred(working, new PixelSize(1000, 440)));
    }

    // A second screen's working area starts where that screen does,
    // and the window is centred in it rather than on the desktop.
    [Fact]
    public void ASecondScreenCentresInItsOwnCorner()
    {
        var working = new PixelRect(1920, 0, 1280, 1024);

        Assert.Equal(
            new PixelPoint(2080, 262),
            Opening.Centred(working, new PixelSize(960, 500)));
    }

    // A window too large for the screen sits at the working area's own
    // corner: half of it showing from the top left beats half of it
    // showing from off the edge.
    [Fact]
    public void AWindowLargerThanItsScreenStartsAtTheCorner()
    {
        var working = new PixelRect(10, 20, 800, 600);

        Assert.Equal(
            new PixelPoint(10, 20),
            Opening.Centred(working, new PixelSize(1200, 900)));
    }
}
