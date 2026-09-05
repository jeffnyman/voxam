namespace Voxam.Core.Glulx.Glk;

/// <summary>
/// What a character is worth on the way out of the machine.
///
/// Glulx characters are arbitrary 32-bit values, so a game can print
/// something that is not a Unicode code point at all, and glulxercise
/// does exactly that.
/// </summary>
public static class Characters
{
    /// <summary>
    /// What a non-Unicode stream substitutes for a character it cannot
    /// hold: '?', the placeholder the specification names (Glk: Output).
    /// </summary>
    public const uint Unprintable = 0x3F;

    /// <summary>The last code point Unicode defines.</summary>
    public const uint MaxUnicode = 0x10FFFF;

    /// <summary>The line feed, which every window type reads as a break.</summary>
    public const uint Newline = 0x0A;

    /// <summary>One past the last character a byte stream can hold.</summary>
    internal const uint ByteLimit = 0x100;

    // The surrogate block: reserved for UTF-16 pairs, so the values are
    // not independently encodable characters.
    private const uint SurrogateFirst = 0xD800;
    private const uint SurrogateLast = 0xDFFF;

    /// <summary>
    /// Render a Glulx character value as text. Anything outside the
    /// Unicode range, and the surrogate block, which is not
    /// independently encodable, becomes '?' (Glk: Output).
    ///
    /// The answer is a string rather than a char because a code point
    /// above the basic plane takes two of C#'s UTF-16 units, and a
    /// window holds what it was told to show.
    /// </summary>
    public static string ToChar(uint value) =>
        value > MaxUnicode || (value >= SurrogateFirst && value <= SurrogateLast)
            ? char.ConvertFromUtf32((int)Unprintable)
            : char.ConvertFromUtf32((int)value);
}

/// <summary>
/// What a stream asks of a character array: sized and indexed.
///
/// The bridge era's live view onto VM memory satisfies this, and so
/// does a plain array, which is what the tests hand in.
/// </summary>
public interface IBuffer
{
    /// <summary>The array's capacity, in characters.</summary>
    int Length { get; }

    /// <summary>The character at an index.</summary>
    /// <param name="index">Where in the array to look.</param>
    uint this[int index] { get; set; }
}

/// <summary>
/// The window types (Glk: The Types of Windows).
///
/// All is not a type a window can have: it is the wildcard the gestalt
/// selectors accept when asking about every type at once.
/// </summary>
public static class WindowType
{
    /// <summary>The wildcard, for asking about every type at once.</summary>
    public const uint All = 0;

    /// <summary>An internal node: a split of two.</summary>
    public const uint Pair = 1;

    /// <summary>A window that shows nothing.</summary>
    public const uint Blank = 2;

    /// <summary>A scrolling window of styled text.</summary>
    public const uint TextBuffer = 3;

    /// <summary>A character grid with a cursor.</summary>
    public const uint TextGrid = 4;

    /// <summary>A grid of pixels.</summary>
    public const uint Graphics = 5;
}

/// <summary>
/// The split-method bits window_open takes.
///
/// Masked bitfields (Glk: Window Opening, Closing, and Constraints),
/// held as constants rather than an enum on purpose, because Border
/// shares the value zero with Left.
/// </summary>
public static class WindowMethod
{
    /// <summary>The new window takes the left side.</summary>
    public const uint Left = 0x00;

    /// <summary>The new window takes the right side.</summary>
    public const uint Right = 0x01;

    /// <summary>The new window takes the top.</summary>
    public const uint Above = 0x02;

    /// <summary>The new window takes the bottom.</summary>
    public const uint Below = 0x03;

    /// <summary>The bits naming which side the new window takes.</summary>
    public const uint DirMask = 0x0F;

    /// <summary>The split is a count in the key window's own units.</summary>
    public const uint Fixed = 0x10;

    /// <summary>The split is a percentage of the whole.</summary>
    public const uint Proportional = 0x20;

    /// <summary>The bits naming how the size is measured.</summary>
    public const uint DivisionMask = 0xF0;

    /// <summary>A visible border between the two, which is the default.</summary>
    public const uint Border = 0x000;

    /// <summary>No border between the two.</summary>
    public const uint NoBorder = 0x100;

    /// <summary>The bit naming whether a border is drawn.</summary>
    public const uint BorderMask = 0x100;
}

/// <summary>The event types glk_select can report (Glk: Events).</summary>
public static class EventType
{
    /// <summary>Nothing happened, which is what a poll usually finds.</summary>
    public const uint None = 0;

    /// <summary>A timer fired.</summary>
    public const uint Timer = 1;

    /// <summary>A single key arrived.</summary>
    public const uint CharInput = 2;

    /// <summary>A line of input arrived.</summary>
    public const uint LineInput = 3;

    /// <summary>The player clicked in a window that asked for it.</summary>
    public const uint MouseInput = 4;

    /// <summary>The window tree was resized.</summary>
    public const uint Arrange = 5;

    /// <summary>A window lost its contents and must be redrawn.</summary>
    public const uint Redraw = 6;

    /// <summary>A sound finished playing.</summary>
    public const uint SoundNotify = 7;

    /// <summary>The player followed a hyperlink.</summary>
    public const uint Hyperlink = 8;

    /// <summary>A volume change finished.</summary>
    public const uint VolumeNotify = 9;
}

/// <summary>
/// The eleven text styles (Glk: Styles).
///
/// The family is named for what its members are rather than the bare
/// word, because a window carries a Style property and the two cannot
/// share a name inside the same class.
/// </summary>
public static class TextStyle
{
    /// <summary>The style everything else is measured against.</summary>
    public const uint Normal = 0;

    /// <summary>Emphasized text, which most displays italicize.</summary>
    public const uint Emphasized = 1;

    /// <summary>Text whose spacing matters, which most displays set fixed.</summary>
    public const uint Preformatted = 2;

    /// <summary>A heading.</summary>
    public const uint Header = 3;

    /// <summary>A subheading.</summary>
    public const uint Subheader = 4;

    /// <summary>Text the player should not miss.</summary>
    public const uint Alert = 5;

    /// <summary>An aside.</summary>
    public const uint Note = 6;

    /// <summary>A quoted block.</summary>
    public const uint BlockQuote = 7;

    /// <summary>The player's own input, echoed.</summary>
    public const uint Input = 8;

    /// <summary>A style the game defines for itself.</summary>
    public const uint User1 = 9;

    /// <summary>A second style the game defines for itself.</summary>
    public const uint User2 = 10;

    /// <summary>How many styles there are, which glk.h counts here.</summary>
    public const uint NumStyles = 11;
}

/// <summary>Where a stream seek measures from (Glk: Stream Positions).</summary>
public static class SeekMode
{
    /// <summary>From the beginning.</summary>
    public const uint Start = 0;

    /// <summary>From the mark as it stands.</summary>
    public const uint Current = 1;

    /// <summary>From the end.</summary>
    public const uint End = 2;
}

/// <summary>
/// How a stream is opened (Glk: File Streams).
///
/// The name carries the Glk prefix its sibling families do not,
/// because the base class library owns the bare one and a file that
/// imports both would not know which was meant.
/// </summary>
public static class GlkFileMode
{
    /// <summary>Write only, truncating whatever was there.</summary>
    public const uint Write = 0x01;

    /// <summary>Read only.</summary>
    public const uint Read = 0x02;

    /// <summary>Both directions.</summary>
    public const uint ReadWrite = 0x03;

    /// <summary>Write only, starting at the end of what is there.</summary>
    public const uint WriteAppend = 0x05;
}

/// <summary>
/// What a file is for (Glk: The Types of File References).
///
/// Constants rather than an enum: the usage is a masked field, and
/// BinaryMode shares the value zero with Data.
/// </summary>
public static class FileUsage
{
    /// <summary>The game's own data, in whatever shape it likes.</summary>
    public const uint Data = 0x00;

    /// <summary>A saved game.</summary>
    public const uint SavedGame = 0x01;

    /// <summary>A transcript of play.</summary>
    public const uint Transcript = 0x02;

    /// <summary>A record of what the player typed.</summary>
    public const uint InputRecord = 0x03;

    /// <summary>The bits naming what the file is for.</summary>
    public const uint TypeMask = 0x0F;

    /// <summary>The file holds bytes, which is the default.</summary>
    public const uint BinaryMode = 0x000;

    /// <summary>The file holds text, and a display may line-end it its own way.</summary>
    public const uint TextMode = 0x100;
}

/// <summary>
/// The special keys of character input (Glk: Character Input).
///
/// The function keys are not contiguous with End: glk.h leaves
/// 0xFFFFFFF2 through 0xFFFFFFF0 unassigned. MaxVal is glk.h's own
/// bookkeeping, the last keycode being 0x100000000 less this.
/// </summary>
public static class KeyCode
{
    /// <summary>A key this display cannot name.</summary>
    public const uint Unknown = 0xFFFFFFFF;

    /// <summary>The left arrow.</summary>
    public const uint Left = 0xFFFFFFFE;

    /// <summary>The right arrow.</summary>
    public const uint Right = 0xFFFFFFFD;

    /// <summary>The up arrow.</summary>
    public const uint Up = 0xFFFFFFFC;

    /// <summary>The down arrow.</summary>
    public const uint Down = 0xFFFFFFFB;

    /// <summary>The return key.</summary>
    public const uint Return = 0xFFFFFFFA;

    /// <summary>The delete or backspace key.</summary>
    public const uint Delete = 0xFFFFFFF9;

    /// <summary>The escape key.</summary>
    public const uint Escape = 0xFFFFFFF8;

    /// <summary>The tab key.</summary>
    public const uint Tab = 0xFFFFFFF7;

    /// <summary>Page up.</summary>
    public const uint PageUp = 0xFFFFFFF6;

    /// <summary>Page down.</summary>
    public const uint PageDown = 0xFFFFFFF5;

    /// <summary>The home key.</summary>
    public const uint Home = 0xFFFFFFF4;

    /// <summary>The end key.</summary>
    public const uint End = 0xFFFFFFF3;

    /// <summary>Function key 1.</summary>
    public const uint Func1 = 0xFFFFFFEF;

    /// <summary>Function key 2.</summary>
    public const uint Func2 = 0xFFFFFFEE;

    /// <summary>Function key 3.</summary>
    public const uint Func3 = 0xFFFFFFED;

    /// <summary>Function key 4.</summary>
    public const uint Func4 = 0xFFFFFFEC;

    /// <summary>Function key 5.</summary>
    public const uint Func5 = 0xFFFFFFEB;

    /// <summary>Function key 6.</summary>
    public const uint Func6 = 0xFFFFFFEA;

    /// <summary>Function key 7.</summary>
    public const uint Func7 = 0xFFFFFFE9;

    /// <summary>Function key 8.</summary>
    public const uint Func8 = 0xFFFFFFE8;

    /// <summary>Function key 9.</summary>
    public const uint Func9 = 0xFFFFFFE7;

    /// <summary>Function key 10.</summary>
    public const uint Func10 = 0xFFFFFFE6;

    /// <summary>Function key 11.</summary>
    public const uint Func11 = 0xFFFFFFE5;

    /// <summary>Function key 12.</summary>
    public const uint Func12 = 0xFFFFFFE4;

    /// <summary>How many keycodes glk.h counts.</summary>
    public const uint MaxVal = 28;
}
