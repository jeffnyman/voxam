using System.Diagnostics.CodeAnalysis;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Platform;

namespace Voxam.Desktop;

/// <summary>
/// The room a window asks for when it opens, and where it opens.
///
/// The size is counted in cells rather than pixels, so a reader who
/// chose larger type gets a larger window rather than fewer words
/// across it. The screen has the last word: a window that opens off
/// the edge of a small display is worse than a cramped one. Both are
/// opening manners only, and neither binds the window afterwards.
/// </summary>
public static class Opening
{
    /// <summary>The grid a window opens at, in cells.</summary>
    /// <remarks>
    /// Roomier than the 80 by 24 the reference's own glass opens at.
    /// That is the classic terminal, and a terminal is what a story
    /// was written for; a window is not a terminal, and a desktop that
    /// can afford the room should give it.
    /// </remarks>
    public const int Columns = 100;

    /// <summary>The grid's height, in cells.</summary>
    public const int Lines = 30;

    /// <summary>The share of a screen a window may fill when it opens.</summary>
    public const double Fill = 0.85;

    /// <summary>
    /// The largest a window may open on a screen this size, in the
    /// window's own units rather than the screen's pixels.
    ///
    /// A screen that reports nothing usable leaves the window
    /// uncapped: the grid above is a sane size on its own, and a
    /// measurement that cannot be trusted is no reason to shrink a
    /// window to nothing.
    /// </summary>
    public static Size Capped(PixelSize working, double scaling)
    {
        if (working.Width <= 0 || working.Height <= 0 || scaling <= 0)
        {
            return new Size(double.PositiveInfinity, double.PositiveInfinity);
        }

        return new Size(working.Width / scaling * Fill, working.Height / scaling * Fill);
    }

    /// <summary>
    /// Where a window of this size sits centred in this screen's
    /// working area, which is the screen less whatever the platform
    /// keeps for itself.
    ///
    /// A window larger than the screen is placed at the working area's
    /// own corner rather than at a negative one: half of it showing
    /// from the top left beats half of it showing from nowhere.
    /// </summary>
    public static PixelPoint Centred(PixelRect working, PixelSize frame) =>
        new(
            working.X + Math.Max((working.Width - frame.Width) / 2, 0),
            working.Y + Math.Max((working.Height - frame.Height) / 2, 0));

    /// <summary>
    /// The cap for whichever screen the platform calls primary, or no
    /// cap at all where it names none.
    /// </summary>
    [ExcludeFromCodeCoverage]
    public static Size Capped(Screens screens) =>
        screens.Primary is { } screen
            ? Capped(screen.WorkingArea.Size, screen.Scaling)
            : new Size(double.PositiveInfinity, double.PositiveInfinity);
}
