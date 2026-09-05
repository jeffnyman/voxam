namespace Voxam.Core.Glulx.Glk;

/// <summary>
/// Base for the four opaque classes (Glk: Opaque Objects).
///
/// The disposed flag exists because Glulx can hold an id for an object
/// the game has already closed. The registry is told to forget it, but
/// a stale reference reaching a method should fault loudly rather than
/// operate on a corpse.
///
/// Objects carry no dispatch-layer identity. The 32-bit ids Glulx sees
/// are the bridge era's business, so nothing here knows a VM exists.
/// </summary>
public abstract class GlkObject
{
    /// <summary>Take the rock the game supplied, reduced to 32 bits.</summary>
    /// <param name="rock">The value the game files the object under.</param>
    protected GlkObject(uint rock = 0) => Rock = rock;

    /// <summary>
    /// Which of the four opaque classes this is, as the dispatch layer
    /// numbers them. The base answers with a number no class uses.
    /// </summary>
    public virtual int GlkClass => -1;

    /// <summary>
    /// The 32-bit value the game filed the object under (Glk: Rocks).
    /// </summary>
    public uint Rock { get; }

    /// <summary>Whether the object has been destroyed.</summary>
    public bool Disposed { get; protected internal set; }
}

/// <summary>A reference to a file (Glk: File References).</summary>
public sealed class FileRef : GlkObject
{
    /// <summary>Record what the file is and how it is meant to open.</summary>
    /// <param name="filename">The path the reference names.</param>
    /// <param name="usage">What the file is for, and its mode bit.</param>
    /// <param name="rock">The value the game files it under.</param>
    /// <param name="temporary">Whether the file dies with the reference.</param>
    public FileRef(string filename, uint usage, uint rock = 0, bool temporary = false)
        : base(rock)
    {
        Filename = filename;
        Usage = usage & FileUsage.TypeMask;
        TextMode = (usage & FileUsage.TextMode) != 0;
        Temporary = temporary;
    }

    /// <inheritdoc/>
    public override int GlkClass => 2;

    /// <summary>The path the reference names.</summary>
    public string Filename { get; }

    /// <summary>What the file is for, masked to the type bits.</summary>
    public uint Usage { get; }

    /// <summary>Whether the file opens in text mode.</summary>
    public bool TextMode { get; }

    /// <summary>Whether the file dies with the reference.</summary>
    public bool Temporary { get; }
}

/// <summary>A sound channel (Glk: Sound).</summary>
public sealed class SoundChannel : GlkObject
{
    /// <summary>Full volume, as a fraction of itself.</summary>
    public const uint FullVolume = 0x10000;

    /// <summary>Open silent, at the volume asked for.</summary>
    /// <param name="volume">The channel's volume.</param>
    /// <param name="rock">The value the game files it under.</param>
    public SoundChannel(uint volume = FullVolume, uint rock = 0)
        : base(rock) => Volume = volume;

    /// <inheritdoc/>
    public override int GlkClass => 3;

    /// <summary>
    /// The volume, as a fraction of full volume (Glk: Other Sound
    /// Channel Functions).
    /// </summary>
    public uint Volume { get; set; }

    /// <summary>The resource number playing, or zero for silence.</summary>
    public uint Sound { get; set; }

    /// <summary>How many plays were asked for.</summary>
    public uint Repeats { get; set; }

    /// <summary>The nonzero value a finished play reports with.</summary>
    public uint Notify { get; set; }

    /// <summary>Whether the channel is paused.</summary>
    public bool Paused { get; set; }
}

/// <summary>
/// One Glk event: the four fields of event_t (Glk: Events).
///
/// The name carries the Glk prefix because a type named for the bare
/// word is a reserved keyword in other languages the runtime serves.
/// </summary>
public sealed class GlkEvent
{
    /// <summary>Build an event, defaulting to nothing having happened.</summary>
    /// <param name="kind">The event type.</param>
    /// <param name="window">The window the event belongs to, if any.</param>
    /// <param name="val1">The first value.</param>
    /// <param name="val2">The second value.</param>
    public GlkEvent(uint kind = EventType.None, Window? window = null, uint val1 = 0, uint val2 = 0)
    {
        Kind = kind;
        Window = window;
        Val1 = val1;
        Val2 = val2;
    }

    /// <summary>
    /// The event type. The struct calls this field "type", which reads
    /// better here as something that is not a keyword.
    /// </summary>
    public uint Kind { get; }

    /// <summary>The window the event belongs to, or null.</summary>
    public Window? Window { get; }

    /// <summary>The first value; its meaning depends on the type.</summary>
    public uint Val1 { get; }

    /// <summary>The second value.</summary>
    public uint Val2 { get; }

    /// <summary>The four fields in event_t order.</summary>
    public (uint Kind, Window? Window, uint Val1, uint Val2) AsFields() =>
        (Kind, Window, Val1, Val2);
}
