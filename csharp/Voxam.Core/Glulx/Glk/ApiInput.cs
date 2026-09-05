using System.Text;

namespace Voxam.Core.Glulx.Glk;

/// <summary>
/// The input half of the library: what a game asks for, and how the
/// answer finds its way back (Glk: Events).
///
/// Blocking by default, suspending on request. A display that can block
/// is simply asked for input and glk_select returns when it has some,
/// the cheapglk and glkterm arrangement. A display that cannot block
/// raises its suspends flag, and glk_select records the wait instead:
/// the machine returns to its host, and the host answers through the
/// delivery methods here.
/// </summary>
public sealed partial class Api
{
    // The events a poll may return. A poll must never return input, but
    // it may return the events a display raises by itself (Glk: Other
    // Events); those are exactly the ones sitting in the queue.
    private static readonly uint[] Pollable =
    [
        EventType.Timer,
        EventType.Arrange,
        EventType.Redraw,
        EventType.SoundNotify,
        EventType.VolumeNotify,
    ];

    /// <summary>
    /// The requested timer cadence in milliseconds, zero for none (Glk:
    /// Timer Events).
    /// </summary>
    public int TimerInterval { get; private set; }

    /// <summary>
    /// Complete a suspended select with the event a host collected.
    ///
    /// The struct fills and the bridge's deferred writes run, so the
    /// answer lands in VM memory exactly where the game will look when
    /// it steps on.
    /// </summary>
    /// <param name="arrived">What happened.</param>
    /// <exception cref="GlulxException">
    /// When nothing stands suspended. An event with no seat to land in
    /// is a driver's bug, and should be loud.
    /// </exception>
    public void DeliverEvent(GlkEvent arrived)
    {
        ArgumentNullException.ThrowIfNull(arrived);

        if (Suspended is not Waiting waiting)
        {
            throw new GlulxException(
                "an event arrived with no select suspended to receive it");
        }

        Fill(waiting.Record, arrived);

        foreach (var writeback in waiting.Writebacks)
        {
            writeback();
        }

        Suspended = null;
    }

    /// <summary>
    /// Complete a window's line request with text from anywhere.
    ///
    /// Split out from the display ask because a display need not be
    /// asked for the window it answers about: a protocol display gets
    /// told which window the player typed into, which may not be the one
    /// glk_select happened to ask after.
    /// </summary>
    /// <param name="window">The window that was waiting.</param>
    /// <param name="text">What the player typed.</param>
    /// <param name="terminator">The keycode that ended it, or zero.</param>
    /// <exception cref="GlulxException">
    /// When the window has no line request.
    /// </exception>
    public GlkEvent DeliverLine(Window window, string text, uint terminator = 0)
    {
        ArgumentNullException.ThrowIfNull(window);
        ArgumentNullException.ThrowIfNull(text);

        if (window.LineRequest is not { } request)
        {
            throw new GlulxException("line input delivered to a window not expecting it");
        }

        window.LineRequest = null;

        var length = Fill(request.Buffer, text.EnumerateRunes().Select(rune => (uint)rune.Value));

        if (request.Echo && !Display.EchoesInput && window is TextBufferWindow buffer)
        {
            // The line the player typed becomes part of the window's
            // text, in the Input style (Glk: Line Input Events).
            var previous = buffer.Style;

            buffer.Style = TextStyle.Input;
            buffer.Stream.PutString(Truncated(text, length) + "\n");
            buffer.Style = previous;
        }

        return new GlkEvent(EventType.LineInput, window, (uint)length, terminator);
    }

    /// <summary>Complete a window's character request.</summary>
    /// <param name="window">The window that was waiting.</param>
    /// <param name="value">The keystroke, as a Glk character code.</param>
    /// <exception cref="GlulxException">
    /// When the window has no character request.
    /// </exception>
    public static GlkEvent DeliverChar(Window window, uint value)
    {
        ArgumentNullException.ThrowIfNull(window);

        if (!window.CharRequest)
        {
            throw new GlulxException(
                "character input delivered to a window not expecting it");
        }

        window.CharRequest = false;

        return new GlkEvent(EventType.CharInput, window, value);
    }

    /// <summary>Complete a window's mouse request with a clicked position.</summary>
    /// <param name="window">The window that was waiting.</param>
    /// <param name="x">Where across the window the click landed.</param>
    /// <param name="y">Where down it.</param>
    /// <exception cref="GlulxException">
    /// When the window has no mouse request.
    /// </exception>
    public static GlkEvent DeliverMouse(Window window, int x, int y)
    {
        ArgumentNullException.ThrowIfNull(window);

        if (!window.MouseRequest)
        {
            throw new GlulxException("mouse input delivered to a window not expecting it");
        }

        window.MouseRequest = false;

        return new GlkEvent(EventType.MouseInput, window, (uint)x, (uint)y);
    }

    /// <summary>Complete a window's hyperlink request with a link value.</summary>
    /// <param name="window">The window that was waiting.</param>
    /// <param name="value">The link the player followed.</param>
    /// <exception cref="GlulxException">
    /// When the window has no hyperlink request.
    /// </exception>
    public static GlkEvent DeliverHyperlink(Window window, uint value)
    {
        ArgumentNullException.ThrowIfNull(window);

        if (!window.HyperlinkRequest)
        {
            throw new GlulxException(
                "hyperlink input delivered to a window not expecting it");
        }

        window.HyperlinkRequest = false;

        return new GlkEvent(EventType.Hyperlink, window, value);
    }

    /// <summary>
    /// Re-lay the windows after the display changed size.
    ///
    /// A display whose window can be resized calls this; the layout is
    /// redone and the game is told, so it can redraw anything it keeps
    /// track of itself (Glk: Window Arrangement Events).
    /// </summary>
    public void DisplayResized()
    {
        Rearrange();

        PostEvent(new GlkEvent(EventType.Arrange, Root));
    }

    private void ServeInput()
    {
        Serve(0x00C0, args =>
        {
            Select(Record(args[0])!);

            return default;
        });

        // Report a queued non-input event without waiting.
        Serve(0x00C1, args =>
        {
            Fill(Record(args[0])!, Polled());

            return default;
        });

        // Ask for a line of Latin-1 input (Glk: Line Input Events).
        Serve(0x00D0, args =>
        {
            RequestLine(Win(args[0]), Buf(args[1]), Signed(args[2]), false);

            return default;
        });

        // Withdraw a line request. The full behavior returns any partial
        // input; nothing here keeps a half-typed line, so the answer is
        // the no-event.
        Serve(0x00D1, args =>
        {
            var window = Win(args[0]);

            if (window is not null)
            {
                window.LineRequest = null;
            }

            if (Record(args[1]) is { } record)
            {
                Fill(record, new GlkEvent());
            }

            return default;
        });

        // Ask for one Latin-1 keystroke (Glk: Character Input Events).
        Serve(0x00D2, args =>
        {
            RequestChar(Win(args[0]), false);

            return default;
        });

        // Withdraw a character request.
        Serve(0x00D3, args =>
        {
            var window = Win(args[0]);

            if (window is not null)
            {
                window.CharRequest = false;
            }

            return default;
        });

        // Ask for a click in a grid or graphics window, and withdraw the
        // request (Glk: Mouse Input Events).
        Serve(0x00D4, args => Requested(Win(args[0]), mouse: true, wanted: true));
        Serve(0x00D5, args => Requested(Win(args[0]), mouse: true, wanted: false));

        // Ask for a timer every so often; zero stops them (Glk: Timer
        // Events).
        Serve(0x00D6, args =>
        {
            TimerInterval = Signed(args[0]);

            Display.SetTimer(TimerInterval);

            return default;
        });

        // Ask for a link selection, and withdraw the request (Glk:
        // Accepting Hyperlink Events).
        Serve(0x0102, args => Requested(Win(args[0]), mouse: false, wanted: true));
        Serve(0x0103, args => Requested(Win(args[0]), mouse: false, wanted: false));

        // The Unicode twins: the same requests over a buffer of words.
        Serve(0x0140, args =>
        {
            RequestChar(Win(args[0]), true);

            return default;
        });

        Serve(0x0141, args =>
        {
            RequestLine(Win(args[0]), Buf(args[1]), Signed(args[2]), true);

            return default;
        });

        // Choose whether the pending line echoes (Glk: Line Input
        // Events).
        Serve(0x0150, args =>
        {
            if (Win(args[0])?.LineRequest is { } request)
            {
                request.Echo = Word(args[1]) != 0;
            }

            return default;
        });

        // Choose the special keys that may end the pending line.
        Serve(0x0151, args =>
        {
            if (Win(args[0])?.LineRequest is { } request)
            {
                request.Terminators = Keycodes(Buf(args[1]));
            }

            return default;
        });
    }

    /// <summary>
    /// Wait until something happens, then report it.
    ///
    /// A blocking display is asked for input on the spot and the struct
    /// fills before this returns. A suspending display is never asked:
    /// whatever is already queued is delivered, and otherwise the wait
    /// is recorded for the host, who answers through DeliverEvent once
    /// the event arrives (Glk: Events).
    /// </summary>
    /// <exception cref="GlulxException">
    /// When no outstanding request could ever be satisfied: waiting
    /// longer would never end.
    /// </exception>
    private void Select(RefStruct record)
    {
        if (!Display.Suspends)
        {
            Fill(record, WaitForEvent());

            return;
        }

        Display.Flush(Root);

        if (PendingEvents.Count > 0)
        {
            Fill(record, Taken());

            return;
        }

        if (!Awaited())
        {
            throw new GlulxException(
                "glk_select with no input requested: the game would wait forever");
        }

        Suspended = new Waiting(record);
    }

    /// <summary>
    /// The first queued event a poll is allowed to return, or the
    /// no-event when the queue holds none.
    /// </summary>
    private GlkEvent Polled()
    {
        for (var at = 0; at < PendingEvents.Count; at++)
        {
            if (Array.IndexOf(Pollable, PendingEvents[at].Kind) >= 0)
            {
                var queued = PendingEvents[at];

                PendingEvents.RemoveAt(at);

                return queued;
            }
        }

        return new GlkEvent();
    }

    /// <summary>
    /// Whether any outstanding request can ever be answered.
    ///
    /// A request counts only where the display claims the matching
    /// capability, the same rule the blocking loop enforces one refusal
    /// at a time. A running timer counts too: a suspending display's
    /// host raises timer events itself, which is more than a blocking
    /// display can promise when no input is requested alongside.
    /// </summary>
    private bool Awaited()
    {
        if (Windows.Exists(held => held.LineRequest is not null || held.CharRequest))
        {
            return true;
        }

        if (Display.MouseInput && Windows.Exists(held => held.MouseRequest))
        {
            return true;
        }

        if (Display.HyperlinkInput && Windows.Exists(held => held.HyperlinkRequest))
        {
            return true;
        }

        return Display.TimerInput && TimerInterval != 0;
    }

    /// <summary>
    /// Block until something happens, then report it.
    ///
    /// The loop exists for interruptions: a display may answer nothing
    /// to an input call because a timer fired instead, in which case the
    /// input request stays pending and we come round again to pick the
    /// queued event up.
    /// </summary>
    /// <exception cref="GlulxException">
    /// When nothing is queued and no outstanding request can ever be
    /// satisfied: waiting longer would never end.
    /// </exception>
    private GlkEvent WaitForEvent()
    {
        while (true)
        {
            Display.Flush(Root);

            if (PendingEvents.Count > 0)
            {
                return Taken();
            }

            if (Windows.Find(held => held.LineRequest is not null) is { } typing)
            {
                if (CollectLine(typing) is { } typed)
                {
                    return typed;
                }

                continue;
            }

            if (Windows.Find(held => held.CharRequest) is { } keying)
            {
                if (Display.ReadChar(keying) is { } key)
                {
                    return DeliverChar(keying, key);
                }

                continue;
            }

            if (Windows.Find(held => held.MouseRequest) is { } clicking)
            {
                if (Display.ReadMouse(clicking) is { } position)
                {
                    return DeliverMouse(clicking, position.X, position.Y);
                }

                if (Display.MouseInput)
                {
                    // It can click, so this was an interruption, not a
                    // refusal: come round again. A display that cannot
                    // click falls through to the refusal below instead.
                    continue;
                }
            }

            if (Windows.Find(held => held.HyperlinkRequest) is { } following)
            {
                // Zero is no link, the same nothing the reference reads
                // out of a falsy answer.
                if (Display.ReadHyperlink(following) is { } link && link != 0)
                {
                    return DeliverHyperlink(following, link);
                }

                if (Display.HyperlinkInput)
                {
                    continue;
                }
            }

            throw new GlulxException(
                "glk_select with no input requested: the game would wait forever");
        }
    }

    /// <summary>Ask the display for the line a window is waiting on.</summary>
    private GlkEvent? CollectLine(Window window)
    {
        // The scan that found this window is what guarantees the
        // request, so the capacity asked for is the request's own.
        var answer = Display.ReadLine(window, window.LineRequest!.Capacity);

        return answer is { } typed ? DeliverLine(window, typed.Text, typed.Terminator) : null;
    }

    /// <summary>Take the event at the head of the queue.</summary>
    private GlkEvent Taken()
    {
        var first = PendingEvents[0];

        PendingEvents.RemoveAt(0);

        return first;
    }

    /// <summary>
    /// Open a line request on a window (Glk: Line Input Events).
    /// </summary>
    /// <exception cref="GlulxException">
    /// For the null window, or one already waiting on a line.
    /// </exception>
    private static void RequestLine(Window? window, IBuffer? buf, int initlen, bool unicode)
    {
        if (window is null)
        {
            throw new GlulxException("request_line_event: invalid window");
        }

        if (window.LineRequest is not null)
        {
            throw new GlulxException("request_line_event: input already requested");
        }

        window.LineRequest = new LineRequest(buf, initlen, unicode);
    }

    /// <summary>
    /// Open a character request on a window (Glk: Character Input
    /// Events).
    /// </summary>
    /// <exception cref="GlulxException">For the null window.</exception>
    private static void RequestChar(Window? window, bool unicode)
    {
        if (window is null)
        {
            throw new GlulxException("request_char_event: invalid window");
        }

        window.CharRequest = true;
        window.CharUnicode = unicode;
    }

    /// <summary>
    /// Turn a request for a click or a link on or off. The null window
    /// is simply nothing to ask about, which is what the reference does
    /// for all four of these.
    /// </summary>
    private static Held Requested(Window? window, bool mouse, bool wanted)
    {
        if (window is not null)
        {
            if (mouse)
            {
                window.MouseRequest = wanted;
            }
            else
            {
                window.HyperlinkRequest = wanted;
            }
        }

        return default;
    }

    /// <summary>Fill an event struct from an event.</summary>
    private static void Fill(RefStruct record, GlkEvent arrived)
    {
        var (kind, window, val1, val2) = arrived.AsFields();

        record.SetAll(
            Held.OfWord(kind), Held.OfOpaque(window), Held.OfWord(val1), Held.OfWord(val2));
    }

    /// <summary>The terminator keycodes a buffer names, copied out of it.</summary>
    private static uint[] Keycodes(IBuffer? keycodes)
    {
        if (keycodes is null)
        {
            return [];
        }

        var taken = new uint[keycodes.Length];

        for (var at = 0; at < taken.Length; at++)
        {
            taken[at] = keycodes[at];
        }

        return taken;
    }

    /// <summary>
    /// The first so many characters of a line, counted as Glk counts
    /// them. A character above the basic plane is one character to Glk
    /// and two units to the string holding it, so the cut is made by
    /// walking runes rather than by slicing.
    /// </summary>
    private static string Truncated(string text, int characters)
    {
        var kept = new StringBuilder();
        var counted = 0;

        foreach (var rune in text.EnumerateRunes())
        {
            if (counted >= characters)
            {
                break;
            }

            kept.Append(rune);
            counted++;
        }

        return kept.ToString();
    }
}
