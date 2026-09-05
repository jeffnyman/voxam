using Voxam.Core.Glulx.Glk;
using SessionEndException = Voxam.Core.SessionEndException;

namespace Voxam.Tests.Glulx.Glk;

/// <summary>
/// A character array standing in for the live view onto VM memory the
/// bridge era will hand the library.
/// </summary>
internal sealed class WordBuffer : IBuffer
{
    private readonly uint[] _values;

    public WordBuffer(int length) => _values = new uint[length];

    public WordBuffer(params uint[] values) => _values = values;

    public int Length => _values.Length;

    public uint this[int index]
    {
        get => _values[index];
        set => _values[index] = value;
    }

    public uint[] Snapshot() => [.. _values];
}

/// <summary>
/// A stream that overrides nothing, so the base's own placing and
/// fetching are what answer. Glk has no such stream; the base exists to
/// hold the counting rules the four real kinds share, and this is how
/// those rules are reached on their own.
/// </summary>
internal sealed class BareStream : StreamObject
{
    public BareStream(bool readable = true, bool writable = true, bool unicode = true)
        : base(0, readable, writable, unicode)
    {
    }
}

/// <summary>
/// An opaque object of no particular class, for the base's own answers.
/// </summary>
internal sealed class NamelessObject : GlkObject
{
    public NamelessObject(uint rock = 0)
        : base(rock)
    {
    }

    public void Bury() => Disposed = true;
}

/// <summary>
/// A display that is asked for input and answers from a script. Every
/// queue may hold nulls, which is how a display says "nothing yet, but
/// something else happened" and sends the select loop round again.
/// </summary>
internal class ScriptedDisplay : GlkDisplay
{
    public Queue<(string Text, uint Terminator)?> Lines { get; } = [];

    public Queue<uint?> Chars { get; } = [];

    public Queue<(int X, int Y)?> Mice { get; } = [];

    public Queue<uint?> Links { get; } = [];

    public Queue<string?> Names { get; } = [];

    public List<int> Timers { get; } = [];

    public int Flushes { get; private set; }

    public int Asked { get; private set; }

    public bool Clicks { get; set; }

    public bool Follows { get; set; }

    public bool Ticks { get; set; }

    public bool Echoes { get; set; }

    public GlkLibrary? Attached => Library;

    /// <summary>
    /// An event the display raises the first time it is asked for
    /// input, the way a timer coming round interrupts a read.
    /// </summary>
    public GlkEvent? Interruption { get; set; }

    public override bool MouseInput => Clicks;

    public override bool HyperlinkInput => Follows;

    public override bool TimerInput => Ticks;

    public override bool EchoesInput => Echoes;

    public override (int Width, int Height) Size() => (80, 24);

    public override void Flush(Window? root) => Flushes++;

    public override void SetTimer(int millisecs) => Timers.Add(millisecs);

    public override (string Text, uint Terminator)? ReadLine(Window window, int maxlen)
    {
        Asked = maxlen;

        Interrupt();

        return Next(Lines);
    }

    public override uint? ReadChar(Window window)
    {
        Interrupt();

        return Next(Chars);
    }

    public override (int X, int Y)? ReadMouse(Window window)
    {
        Interrupt();

        return Next(Mice);
    }

    public override uint? ReadHyperlink(Window window)
    {
        Interrupt();

        return Next(Links);
    }

    public override string? PromptFile(uint usage, uint fmode) => Next(Names);

    /// <summary>Raise an event of the display's own, as a timer would.</summary>
    public void Raise(GlkEvent arrived) => Post(arrived);

    /// <summary>
    /// The next scripted answer. A queue run dry ends the session rather
    /// than looping forever, which is what a test that forgot to script
    /// far enough should look like.
    /// </summary>
    private static T Next<T>(Queue<T> queue) =>
        queue.Count > 0 ? queue.Dequeue() : throw new SessionEndException();

    /// <summary>Raise the interruption, once, on the first read.</summary>
    private void Interrupt()
    {
        if (Interruption is { } arrived)
        {
            Interruption = null;

            Post(arrived);
        }
    }
}

/// <summary>
/// A display that cannot block: it is never asked for input, and every
/// select records a wait for the host to answer.
/// </summary>
internal sealed class QuietDisplay : ScriptedDisplay
{
    public override bool Suspends => true;
}
