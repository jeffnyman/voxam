namespace Voxam.Core.Glulx.Glk;

/// <summary>
/// The display a Glk library renders into and reads from.
///
/// The reference calls this the frontend. The port cannot: one
/// namespace out there is already a Frontend, and a file that imports
/// both would not know which was meant.
///
/// The seat grows with the eras. What a display must answer for text to
/// come out and input to come in is here; drawing a picture and playing
/// a sound arrive with the rungs that need them, so that nothing
/// declares a promise it has no caller for.
///
/// Every capability defaults to "cannot": a display claims what it can
/// do by overriding a flag and the methods behind it, and the gestalt
/// answers follow the flags, so a game never asks for what the display
/// never promised.
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
    /// Whether input arrives from outside rather than from a read call.
    ///
    /// A blocking display is asked and answers on the spot. A suspending
    /// display is never asked: glk_select records the wait, the machine
    /// returns to its host, and the host delivers the event through the
    /// library.
    /// </summary>
    public virtual bool Suspends => false;

    /// <summary>
    /// Whether typed input is already visible without Glk reprinting it.
    ///
    /// A terminal echoes as the player types, so Glk echoing the line
    /// into the window as well would show it twice. A display that draws
    /// everything itself leaves this false and lets Glk echo.
    /// </summary>
    public virtual bool EchoesInput => false;

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
    /// What one character costs in the display's own layout unit. A
    /// terminal's unit is already the cell, so the default is one by one
    /// and every measurement is the same number either way.
    /// </summary>
    public virtual Metrics Metrics => Glk.Metrics.CharacterCell;

    /// <summary>
    /// The metrics for one window; by default, the same for all.
    ///
    /// A display may spend different amounts on different window types,
    /// so the tree asks per window rather than once. A display with one
    /// answer need not override this.
    /// </summary>
    /// <param name="window">The window being measured.</param>
    public virtual Metrics MetricsFor(Window window) => Metrics;

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

    /// <summary>
    /// Read a line, and the keycode that ended it. An ordinary Return
    /// ends a line with zero; a terminator key ends it with its own
    /// keycode (Glk: Line Input Events).
    ///
    /// Null means "nothing yet, but something else happened", a timer
    /// firing most likely. The request stays pending and glk_select
    /// looks again, which is what lets a timer arrive without cancelling
    /// line input.
    /// </summary>
    /// <param name="window">The window waiting on the line.</param>
    /// <param name="maxlen">How many characters its buffer holds.</param>
    public abstract (string Text, uint Terminator)? ReadLine(Window window, int maxlen);

    /// <summary>
    /// Read one keystroke as a Glk character code. Null means what it
    /// means for a line.
    /// </summary>
    /// <param name="window">The window waiting on the key.</param>
    public abstract uint? ReadChar(Window window);

    /// <summary>Ask for timer events every so often; zero stops them.</summary>
    /// <param name="millisecs">The cadence, or zero.</param>
    public virtual void SetTimer(int millisecs)
    {
        // A display with no clock has nothing to set.
    }

    /// <summary>
    /// Where the player clicked, or null where none can be (Glk: Mouse
    /// Input Events).
    /// </summary>
    /// <param name="window">The window waiting on a click.</param>
    public virtual (int X, int Y)? ReadMouse(Window window) => null;

    /// <summary>
    /// The link value the player followed, or null where none can be
    /// (Glk: Accepting Hyperlink Events).
    /// </summary>
    /// <param name="window">The window waiting on a link.</param>
    public virtual uint? ReadHyperlink(Window window) => null;

    /// <summary>
    /// Ask the player for a filename; null cancels. Cancelling is always
    /// a legitimate answer (Glk: File References), so a display with no
    /// way to ask can simply inherit this.
    /// </summary>
    /// <param name="usage">What the file is for.</param>
    /// <param name="fmode">How the game means to open it.</param>
    public virtual string? PromptFile(uint usage, uint fmode) => null;

    // The drawing contract is inert by default. A display that claims
    // graphics overrides these; one that does not is never asked,
    // because the Graphics gestalt reports zero and graphics windows
    // refuse to open.

    /// <summary>
    /// Draw a picture; answer whether it was drawn (Glk: Graphics).
    /// </summary>
    /// <param name="window">The window to draw in.</param>
    /// <param name="image">The picture, measured.</param>
    /// <param name="val1">Where across, or the alignment in a buffer.</param>
    /// <param name="val2">Where down, or the link value in a buffer.</param>
    /// <param name="width">How wide to draw it.</param>
    /// <param name="height">How tall.</param>
    public virtual bool DrawImage(
        Window window, ImageInfo image, int val1, int val2, uint width, uint height) => false;

    /// <summary>
    /// Erase a rectangle to the background (Glk: Graphics in Graphics
    /// Windows).
    /// </summary>
    /// <param name="window">The window to erase in.</param>
    /// <param name="left">The rectangle's left edge.</param>
    /// <param name="top">Its top edge.</param>
    /// <param name="width">Its width.</param>
    /// <param name="height">Its height.</param>
    public virtual void EraseRect(Window window, int left, int top, uint width, uint height)
    {
        // A display that cannot draw has nothing to erase.
    }

    /// <summary>Fill a rectangle with a color.</summary>
    /// <param name="window">The window to fill in.</param>
    /// <param name="color">The color to fill with.</param>
    /// <param name="left">The rectangle's left edge.</param>
    /// <param name="top">Its top edge.</param>
    /// <param name="width">Its width.</param>
    /// <param name="height">Its height.</param>
    public virtual void FillRect(
        Window window, uint color, int left, int top, uint width, uint height)
    {
        // Nor anything to fill.
    }

    /// <summary>Set the color future clears fill with.</summary>
    /// <param name="window">The window whose background it is.</param>
    /// <param name="color">The color to clear to.</param>
    public virtual void SetBackgroundColor(Window window, uint color)
    {
        // A background nothing is drawn on is nothing to choose.
    }

    /// <summary>
    /// Break text below margin images (Glk: Graphics in Text Buffer
    /// Windows).
    /// </summary>
    /// <param name="window">The buffer window to break in.</param>
    public virtual void FlowBreak(Window window)
    {
        // Text laid around no pictures needs no break.
    }

    // The sound contract, equally inert without the sound flag.

    /// <summary>
    /// Begin playing; answer whether it started.
    ///
    /// A display that supports notification posts a sound event through
    /// Post when the sound ends: a blocking display has no other way to
    /// raise one.
    /// </summary>
    /// <param name="channel">The channel to play on.</param>
    /// <param name="sound">The resource number to play.</param>
    /// <param name="repeats">How many times, or -1 for forever.</param>
    /// <param name="notify">The nonzero value a finished play reports with.</param>
    public virtual bool PlaySound(
        SoundChannel channel, uint sound, uint repeats, uint notify) => false;

    /// <summary>Stop whatever the channel is playing.</summary>
    /// <param name="channel">The channel to silence.</param>
    public virtual void StopSound(SoundChannel channel)
    {
        // Silence needs no stopping.
    }

    /// <summary>Pause or resume the channel.</summary>
    /// <param name="channel">The channel to hold or release.</param>
    /// <param name="paused">Whether it is held.</param>
    public virtual void PauseSound(SoundChannel channel, bool paused)
    {
        // Nor holding.
    }

    /// <summary>Change the channel's volume, over a duration if asked.</summary>
    /// <param name="channel">The channel to change.</param>
    /// <param name="volume">The volume, as a fraction of full volume.</param>
    /// <param name="duration">How long to take about it, in milliseconds.</param>
    public virtual void SetVolume(SoundChannel channel, uint volume, uint duration)
    {
        // Nor turning up.
    }

    /// <summary>
    /// Queue an event the display raised, for the next select.
    ///
    /// A blocking display has no other way to report something that is
    /// not the input it was asked for. It returns null from the input
    /// call as well, so that glk_select comes back round and finds what
    /// was queued here.
    /// </summary>
    /// <param name="arrived">What happened.</param>
    protected void Post(GlkEvent arrived)
    {
        if (Library is Api library)
        {
            library.PostEvent(arrived);
        }
    }
}

/// <summary>
/// A display that shows nothing, for a session with no face on it. The
/// library still works: streams still count, windows still lay out, and
/// what is written simply goes nowhere.
///
/// An input request ends the session, since a game waiting for input
/// that can never arrive would otherwise wait forever.
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

    /// <summary>End the session: no line can ever arrive.</summary>
    /// <param name="window">The window waiting on the line.</param>
    /// <param name="maxlen">How many characters its buffer holds.</param>
    /// <exception cref="SessionEndException">Always.</exception>
    public override (string Text, uint Terminator)? ReadLine(Window window, int maxlen) =>
        throw new SessionEndException();

    /// <summary>End the session: no keystroke can ever arrive.</summary>
    /// <param name="window">The window waiting on the key.</param>
    /// <exception cref="SessionEndException">Always.</exception>
    public override uint? ReadChar(Window window) => throw new SessionEndException();
}
