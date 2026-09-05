namespace Voxam.Core.Glulx.Glk;

/// <summary>
/// The Glk gestalt selectors (Glk: The Gestalt System).
///
/// These are Glk's own capability questions, asked through glk_gestalt,
/// not the Glulx machine's, which live beside the VM and answer for it.
/// </summary>
public static class GlkGestalt
{
    /// <summary>Which Glk this is.</summary>
    public const uint Version = 0;

    /// <summary>Whether a key can be read.</summary>
    public const uint CharInput = 1;

    /// <summary>Whether a character can appear in a line of input.</summary>
    public const uint LineInput = 2;

    /// <summary>Whether a character can be printed.</summary>
    public const uint CharOutput = 3;

    /// <summary>Whether a click can be reported.</summary>
    public const uint MouseInput = 4;

    /// <summary>Whether a timer can wake the game.</summary>
    public const uint Timer = 5;

    /// <summary>Whether a graphics window can open.</summary>
    public const uint Graphics = 6;

    /// <summary>Whether a picture can be drawn in a window type.</summary>
    public const uint DrawImage = 7;

    /// <summary>Whether sound can play.</summary>
    public const uint Sound = 8;

    /// <summary>Whether a channel's volume can be set.</summary>
    public const uint SoundVolume = 9;

    /// <summary>Whether a finished sound can report itself.</summary>
    public const uint SoundNotify = 10;

    /// <summary>Whether link markup is accepted.</summary>
    public const uint Hyperlinks = 11;

    /// <summary>Whether a link can be followed.</summary>
    public const uint HyperlinkInput = 12;

    /// <summary>Whether song files can play.</summary>
    public const uint SoundMusic = 13;

    /// <summary>Whether a translucent picture blends.</summary>
    public const uint GraphicsTransparency = 14;

    /// <summary>Whether the Unicode functions are there.</summary>
    public const uint Unicode = 15;

    /// <summary>Whether the normalization functions are there.</summary>
    public const uint UnicodeNorm = 16;

    /// <summary>Whether a line's echo can be turned off.</summary>
    public const uint LineInputEcho = 17;

    /// <summary>Whether a line can be given terminator keys.</summary>
    public const uint LineTerminators = 18;

    /// <summary>Whether one key can terminate a line.</summary>
    public const uint LineTerminatorKey = 19;

    /// <summary>Whether the clock is there.</summary>
    public const uint DateTime = 20;

    /// <summary>The second generation of the sound functions.</summary>
    public const uint Sound2 = 21;

    /// <summary>Whether a Blorb resource can be opened as a stream.</summary>
    public const uint ResourceStream = 22;

    /// <summary>Whether a graphics window takes keystrokes.</summary>
    public const uint GraphicsCharInput = 23;

    /// <summary>Whether a picture can be drawn scaled.</summary>
    public const uint DrawImageScale = 24;
}

/// <summary>
/// A Glk library instance: the functions themselves, standing on the
/// object model and reaching a display.
///
/// The class is split across files the way the reference's one module
/// is split by section, because it is one library and its state is
/// shared: the window tree, the live object lists, and the current
/// stream are the same few fields everything here reads.
///
/// Not every function is served yet. Pictures and sound wait for the
/// resources they would draw and play; the events, and everything that
/// asks the player for something, wait for the era that can suspend a
/// machine. What is missing refuses by name through the seat above.
/// </summary>
public sealed partial class Api : GlkLibrary, IGlkOutput
{
    /// <summary>Which Glk this library answers as (Glk: The Gestalt System).</summary>
    public const uint GlkVersion = 0x00000706;

    // The CharOutput selector's answers (Glk: Output).
    private const uint CannotPrint = 0;
    private const uint ExactPrint = 2;

    private const uint LatinOneLimit = 0x100;

    // The lowest special keycode; glk.h defines the range this way.
    private const uint SpecialKeys = unchecked((uint)(0x100000000 - KeyCode.MaxVal));

    /// <summary>Open with no windows, over a display or over nothing.</summary>
    /// <param name="display">The display to render into, or null.</param>
    /// <param name="saveDir">Where game-named files live.</param>
    public Api(GlkDisplay? display = null, string? saveDir = null)
    {
        Display = display ?? new NullDisplay();
        SaveDir = saveDir ?? Directory.GetCurrentDirectory();

        ServeMain();
        ServeWindows();
        ServeStreams();
        ServeFiles();
        ServeOutput();
        ServeText();

        Display.Attach(this);
    }

    /// <summary>The display rendered into and read from.</summary>
    public GlkDisplay Display { get; }

    /// <summary>
    /// Where game-named files live; every sanitized filename resolves
    /// inside it.
    /// </summary>
    public string SaveDir { get; }

    /// <summary>
    /// The root of the window tree, or null before the first window
    /// opens.
    /// </summary>
    public Window? Root { get; private set; }

    /// <summary>
    /// Where the printing functions send output, or null (Glk: Streams).
    /// </summary>
    public StreamObject? CurrentStream { get; private set; }

    /// <summary>
    /// Every live window, newest first: the order the reference walks,
    /// by prepending.
    /// </summary>
    public List<Window> Windows { get; } = [];

    /// <summary>Every live stream, newest first.</summary>
    public List<StreamObject> Streams { get; } = [];

    /// <summary>Every live file reference, newest first.</summary>
    public List<FileRef> FileRefs { get; } = [];

    /// <summary>The hints set by stylehint_set, for a display that honors them.</summary>
    public Dictionary<(uint WinType, uint Style, uint Hint), int> StyleHints { get; } = [];

    /// <summary>
    /// Events a display has posted, waiting for the next select. The era
    /// that reads them is the one that can suspend a machine.
    /// </summary>
    public List<GlkEvent> PendingEvents { get; } = [];

    /// <summary>Put an event by for the next select to find.</summary>
    /// <param name="arrived">What happened.</param>
    public void PostEvent(GlkEvent arrived) => PendingEvents.Add(arrived);

    /// <summary>Mark an object dead and tell the bridge to forget it.</summary>
    private void Dispose(GlkObject held)
    {
        held.Disposed = true;

        OnDispose?.Invoke(held);
    }

    /// <summary>
    /// Lay the window tree out over the display again.
    ///
    /// Metrics are refreshed here rather than at window creation, so a
    /// display that changes its font mid-game only has to re-arrange.
    /// </summary>
    private void Rearrange()
    {
        if (Root is null)
        {
            return;
        }

        foreach (var window in Windows)
        {
            window.Metrics = Display.MetricsFor(window);
        }

        var (width, height) = Display.Size();

        Root.Rearrange(new Box(0, 0, width, height));

        foreach (var window in Windows)
        {
            if (window is GraphicsWindow canvas && canvas.Moved)
            {
                // The move cleared the canvas to background; the game
                // owes it a redraw and is told so (Glk: Window Events).
                canvas.Moved = false;
                PostEvent(new GlkEvent(EventType.Redraw, canvas));
            }
        }
    }

    private void ServeMain()
    {
        // End the session, showing whatever is pending first.
        Serve(0x0001, _ =>
        {
            Display.Flush(Root);

            throw new SessionEndException();
        });

        // Yield time to the display; here, nothing (Glk: The Tick Thing).
        Serve(0x0003, _ => default);

        Serve(0x0004, args => Held.OfWord(Gestalt(Word(args[0]), Word(args[1]), null)));
        Serve(0x0005, args =>
            Held.OfWord(Gestalt(Word(args[0]), Word(args[1]), (IBuffer?)args[2])));
    }

    /// <summary>Ask a capability question with room for extra answers.</summary>
    private uint Gestalt(uint selector, uint value, IBuffer? array)
    {
        switch (selector)
        {
            case GlkGestalt.Version:
                return GlkVersion;

            // Any Latin-1 printable, plus the special keycodes. Unknown
            // is not a key a game can ask to receive: it is what a
            // display reports when it cannot name one (Glk: Character
            // Input).
            case GlkGestalt.CharInput:
                return Printable(value) || (value >= SpecialKeys && value < KeyCode.Unknown)
                    ? 1u
                    : 0u;

            // A line is made of printable characters; the special keys
            // can only end one, which is the LineTerminators selector's
            // business (Glk: Line Input).
            case GlkGestalt.LineInput:
                return Printable(value) && value != Characters.Newline ? 1u : 0u;

            case GlkGestalt.CharOutput:
                {
                    var printable = Printable(value);

                    if (array is not null && array.Length > 0)
                    {
                        array[0] = printable ? 1u : 0u;
                    }

                    return printable ? ExactPrint : CannotPrint;
                }

            case GlkGestalt.Graphics:
            // Alpha travels the whole way at a drawing display, and
            // character input is window-blind at every display here, so
            // both answer wherever a canvas can exist at all (Glk:
            // Testing for Graphics Capabilities).
            case GlkGestalt.GraphicsTransparency:
            case GlkGestalt.GraphicsCharInput:
                return Display.Graphics ? 1u : 0u;

            // The argument is a window type: "libraries may implement
            // both, neither, or only one" (Glk: Testing for Graphics
            // Capabilities). Canvases answer for the drawing displays;
            // text buffers answer only where the display lays text
            // around pictures.
            case GlkGestalt.DrawImage:
            case GlkGestalt.DrawImageScale:
                return (Display.Graphics && value == WindowType.Graphics)
                    || (Display.BufferImages && value == WindowType.TextBuffer)
                    ? 1u
                    : 0u;

            case GlkGestalt.Sound:
            case GlkGestalt.Sound2:
            case GlkGestalt.SoundVolume:
            case GlkGestalt.SoundNotify:
                return Display.Sound ? 1u : 0u;

            // Music means MOD and song files (Glk: Testing for Sound
            // Capabilities); nothing here decodes one, so the claim
            // stays honestly zero whatever else a display can play.
            case GlkGestalt.SoundMusic:
                return 0;

            // The argument is a window type, and only grids and graphics
            // windows can carry a mouse position (Glk: Mouse Input
            // Events).
            case GlkGestalt.MouseInput:
                return Display.MouseInput
                    && value is WindowType.TextGrid or WindowType.Graphics
                    ? 1u
                    : 0u;

            case GlkGestalt.Timer:
                return Display.TimerInput ? 1u : 0u;

            // Link markup is accepted on any stream; whether a link can
            // be selected is the separate question below.
            case GlkGestalt.Hyperlinks:
                return 1;

            case GlkGestalt.HyperlinkInput:
                return Display.HyperlinkInput ? 1u : 0u;

            case GlkGestalt.Unicode:
            case GlkGestalt.UnicodeNorm:
            case GlkGestalt.LineInputEcho:
            case GlkGestalt.LineTerminators:
            case GlkGestalt.LineTerminatorKey:
            case GlkGestalt.DateTime:
            case GlkGestalt.ResourceStream:
                return 1;

            // Every selector from a Glk yet to be written: zero is the
            // honest answer for the unsupported and the unknown alike.
            default:
                return 0;
        }
    }

    /// <summary>Latin-1 printable, plus newline (Glk: Output).</summary>
    private static bool Printable(uint character) =>
        character == Characters.Newline
        || (character >= 0x20 && character < 0x7F)
        || (character >= 0xA0 && character < LatinOneLimit);

    /// <summary>
    /// One step of an object walk (Glk: Iterating Through Opaque
    /// Objects). The null object starts the walk; the object after the
    /// last, and an object no longer on the list at all, ends it.
    /// </summary>
    private static T? Iterate<T>(List<T> objects, T? current, Ref? rockref)
        where T : GlkObject
    {
        T? found;

        if (current is null)
        {
            found = objects.Count > 0 ? objects[0] : null;
        }
        else
        {
            var index = objects.IndexOf(current);

            found = index >= 0 && index + 1 < objects.Count ? objects[index + 1] : null;
        }

        if (rockref is not null)
        {
            rockref.Value = Held.OfWord(found?.Rock ?? 0);
        }

        return found;
    }

    /// <summary>A window and all its descendants.</summary>
    private static List<Window> Subtree(Window window)
    {
        var found = new List<Window> { window };

        if (window is PairWindow pair)
        {
            found.AddRange(Subtree(pair.Child1));
            found.AddRange(Subtree(pair.Child2));
        }

        return found;
    }

    /// <summary>
    /// Write values into a buffer from the start; answer how many fit.
    /// Stopping at the buffer's end is what the input functions want:
    /// they fill as much as fits and report that.
    /// </summary>
    private static int Fill(IBuffer? buf, IEnumerable<uint> values)
    {
        var written = 0;

        foreach (var value in values)
        {
            if (written >= buf!.Length)
            {
                break;
            }

            buf[written] = value;
            written++;
        }

        return written;
    }

    // The shapes an argument arrives in, unpacked. The bridge hands
    // over holds, holders, live views and strings; these say which.
    private static uint Word(object? arg) => ((Held)arg!).Word;

    private static int Signed(object? arg) => (int)((Held)arg!).Word;

    private static Window? Win(object? arg) => ((Held)arg!).Opaque as Window;

    private static StreamObject? Str(object? arg) => ((Held)arg!).Opaque as StreamObject;

    private static FileRef? File(object? arg) => ((Held)arg!).Opaque as FileRef;

    private static Ref? Holder(object? arg) => (Ref?)arg;

    private static RefStruct? Record(object? arg) => (RefStruct?)arg;

    private static IBuffer? Buf(object? arg) => (IBuffer?)arg;

    private static string Text(object? arg) => (string)arg!;
}
