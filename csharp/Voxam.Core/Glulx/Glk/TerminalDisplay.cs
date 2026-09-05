using System.Globalization;
using System.Text;

namespace Voxam.Core.Glulx.Glk;

/// <summary>
/// A full-screen terminal display, in the manner of glkterm.
///
/// The painted spine, the tree walk and the wrappers and the pager and
/// the line editor and the timer, lives in the class above; this
/// display supplies the terminal specifics. It rides the same seam the
/// Z-Machine's painter does, so a test drives the whole display with a
/// stub and no terminal at all.
///
/// The terminal echoes nothing while reading: Glk does the echoing into
/// the window once a line is accepted, and until then the half-typed
/// line is drawn by the spine, as part of the layout but not yet part
/// of the window.
/// </summary>
public sealed class TerminalDisplay : PaintedDisplay
{
    private const string Normal = "\u001B[0m";
    private const string ReverseVideo = "\u001B[7m";
    private const string BoldType = "\u001B[1m";
    private const string ItalicType = "\u001B[3m";

    // The keys the terminal seam spells for itself, in the alphabet the
    // Z-Machine's own reader answers in: the cursor codes, and the
    // control characters every terminal sends.
    private static readonly Dictionary<char, uint> Keycodes = new()
    {
        ['\u0081'] = KeyCode.Up,
        ['\u0082'] = KeyCode.Down,
        ['\u0083'] = KeyCode.Left,
        ['\u0084'] = KeyCode.Right,
        ['\u0008'] = KeyCode.Delete,
        ['\u007F'] = KeyCode.Delete,
        ['\u001B'] = KeyCode.Escape,
        ['\u0009'] = KeyCode.Tab,
        ['\n'] = KeyCode.Return,
        ['\r'] = KeyCode.Return,
    };

    private readonly ITerminal _terminal;
    private readonly (int Width, int Height)? _size;
    private readonly StringBuilder _frame = new();

    /// <summary>Stand over a terminal.</summary>
    /// <param name="terminal">The terminal to paint on and read from.</param>
    /// <param name="size">The room to lay out in, or null to ask the terminal.</param>
    /// <param name="onLine">Told every finished line and its terminator.</param>
    /// <param name="onKey">Told every keystroke a character read delivered.</param>
    public TerminalDisplay(
        ITerminal terminal,
        (int Width, int Height)? size = null,
        Action<string, uint>? onLine = null,
        Action<uint>? onKey = null)
        : base(onLine, onKey)
    {
        _terminal = terminal;
        _size = size;
    }

    /// <summary>The terminal's own measure, unless one was chosen.</summary>
    public override (int Width, int Height) Size()
    {
        if (_size is { } chosen)
        {
            return chosen;
        }

        var width = _terminal.Width;
        var height = _terminal.Height;

        return (width == 0 ? FallbackColumns : width, height == 0 ? FallbackLines : height);
    }

    /// <summary>
    /// Leave the cursor under the story, for the shell's prompt. The
    /// session's last words stay on the glass; whatever the caller
    /// prints next lands on a fresh line below them instead of somewhere
    /// mid-screen.
    /// </summary>
    public override void Retire() => _terminal.Write(MoveTo(0, Size().Height - 1) + "\n");

    /// <inheritdoc/>
    protected override void Begin() => _frame.Clear();

    /// <inheritdoc/>
    protected override void Place(int x, int y, IReadOnlyList<Segment> line)
    {
        ArgumentNullException.ThrowIfNull(line);

        _frame.Append(MoveTo(x, y));

        foreach (var (key, text) in line)
        {
            _frame.Append(Dressed(text, key));
        }
    }

    /// <inheritdoc/>
    protected override void Finish((int X, int Y)? cursor)
    {
        // Park the cursor where input is going, or out of the way at the
        // bottom if none is.
        var (x, y) = cursor ?? (0, Size().Height - 1);

        _frame.Append(MoveTo(x, y));
        _terminal.Write(_frame.ToString());
    }

    /// <summary>
    /// One terminal read as a Glk code; null for nothing usable.
    ///
    /// The seam already names the special keys it can, in the alphabet
    /// the Z-Machine reads in; those become their Glk keycodes, and
    /// anything else becomes itself. An expired timeout and a key the
    /// terminal cannot spell are both nothing usable.
    /// </summary>
    /// <param name="timeout">How long to wait, or null for as long as it takes.</param>
    protected override uint? Translated(double? timeout)
    {
        if (_terminal.ReadKey(timeout) is not { Length: 1 } key)
        {
            return null;
        }

        return Keycodes.TryGetValue(key[0], out var code) ? code : key[0];
    }

    private static string MoveTo(int x, int y) =>
        string.Create(CultureInfo.InvariantCulture, $"\u001B[{y + 1};{x + 1}H");

    /// <summary>
    /// One run of text wearing its style's sequences.
    ///
    /// A link dresses as its style alone: the terminal seam carries no
    /// underline, and the terminal claims no link selection anyway.
    /// Writing links is legal everywhere; showing them off is the
    /// window's claim (Glk: Hyperlinks).
    /// </summary>
    private static string Dressed(string text, Dress key)
    {
        var dress = Dressing(key.Style);

        if (dress == default)
        {
            return text;
        }

        var pieces = new StringBuilder();

        if (dress.Bold)
        {
            pieces.Append(BoldType);
        }

        if (dress.Italic)
        {
            pieces.Append(ItalicType);
        }

        if (dress.Reverse)
        {
            pieces.Append(ReverseVideo);
        }

        return pieces.Append(text).Append(Normal).ToString();
    }
}
