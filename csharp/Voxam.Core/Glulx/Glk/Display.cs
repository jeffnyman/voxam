namespace Voxam.Core.Glulx.Glk;

/// <summary>
/// The display a Glk library renders into and reads from.
///
/// The reference calls this the frontend. The port cannot: one
/// namespace out there is already a Frontend, and a file that imports
/// both would not know which was meant.
///
/// The seat grows with the eras. What a display must answer for text to
/// come out is here; reading a line, drawing a picture and playing a
/// sound arrive with the rungs that need them, so that nothing declares
/// a promise it has no caller for.
/// </summary>
public abstract class GlkDisplay
{
    /// <summary>The library rendering into this display, once attached.</summary>
    protected GlkLibrary? Library { get; private set; }

    /// <summary>Whether the display can carry a graphics window.</summary>
    public virtual bool Graphics => false;

    /// <summary>Whether it lays text around pictures in a buffer window.</summary>
    public virtual bool BufferImages => false;

    /// <summary>Whether it can play sound.</summary>
    public virtual bool Sound => false;

    /// <summary>Whether it can report where the player clicked.</summary>
    public virtual bool MouseInput => false;

    /// <summary>Whether it can wake the game on a timer.</summary>
    public virtual bool TimerInput => false;

    /// <summary>Whether a link in its text can be followed.</summary>
    public virtual bool HyperlinkInput => false;

    /// <summary>
    /// The whole display's size, in whatever unit it lays out in.
    /// </summary>
    public abstract (int Width, int Height) Size();

    /// <summary>
    /// Show everything written since the last flush. The root window is
    /// handed over so a display can walk the tree it is drawing.
    /// </summary>
    /// <param name="root">The root of the window tree, or null.</param>
    public abstract void Flush(Window? root);

    /// <summary>Take note of the library this display serves.</summary>
    /// <param name="library">The library rendering into it.</param>
    public virtual void Attach(GlkLibrary library) => Library = library;

    /// <summary>
    /// What one window's characters cost in the display's own layout
    /// unit. A terminal's unit is already the cell, so the default is
    /// one by one and every measurement is the same number either way.
    /// </summary>
    /// <param name="window">The window being measured.</param>
    public virtual Metrics MetricsFor(Window window) => Metrics.CharacterCell;

    /// <summary>
    /// Whether two styles look different in a window. Only the display
    /// knows; one that cannot say answers no, which is what the
    /// specification asks of the unsure (Glk: Testing the Appearance of
    /// Styles).
    /// </summary>
    /// <param name="window">The window the styles would appear in.</param>
    /// <param name="first">One style.</param>
    /// <param name="second">The other.</param>
    public virtual bool StyleDistinguish(Window window, uint first, uint second) => false;

    /// <summary>
    /// One attribute of a style as a number, or null where the display
    /// cannot measure it.
    /// </summary>
    /// <param name="window">The window the style would appear in.</param>
    /// <param name="style">Which style to measure.</param>
    /// <param name="hint">Which attribute of it.</param>
    public virtual uint? StyleMeasure(Window window, uint style, uint hint) => null;
}

/// <summary>
/// A display that shows nothing, for a session with no face on it. The
/// library still works: streams still count, windows still lay out, and
/// what is written simply goes nowhere.
/// </summary>
public sealed class NullDisplay : GlkDisplay
{
    private const int Columns = 80;
    private const int Lines = 24;

    /// <summary>A conventional terminal's worth of room.</summary>
    public override (int Width, int Height) Size() => (Columns, Lines);

    /// <summary>There is nothing to show.</summary>
    /// <param name="root">The root of the window tree, or null.</param>
    public override void Flush(Window? root)
    {
        // A display with no face has nothing to put a face on.
    }
}
