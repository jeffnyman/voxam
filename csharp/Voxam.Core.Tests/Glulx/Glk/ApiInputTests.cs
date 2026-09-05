using Voxam.Core.Glulx.Glk;
using GlulxException = Voxam.Core.GlulxException;
using SessionEndException = Voxam.Core.SessionEndException;

namespace Voxam.Tests.Glulx.Glk;

/// <summary>
/// What a game asks for, and what a display that can block answers
/// (Glk: Events). The suspending arrangement is its own file, because
/// it is a different shape of answer.
/// </summary>
public sealed class ApiInputTests
{
    // A line request records the buffer, the pre-filled length and the
    // width, and the display is asked for exactly the buffer's worth.
    [Fact]
    public void ALineRequestIsRememberedUntilItIsAnswered()
    {
        var (glk, display) = Seam();
        var window = Open(glk, WindowType.TextBuffer);
        var buffer = new WordBuffer(16);

        Call(glk, 0x00D0, Held.OfOpaque(window), buffer, Held.OfWord(3));

        Assert.NotNull(window.LineRequest);
        Assert.Same(buffer, window.LineRequest.Buffer);
        Assert.Equal(3, window.LineRequest.InitLen);
        Assert.False(window.LineRequest.Unicode);

        display.Lines.Enqueue(("hi", 0));

        var arrived = Select(glk);

        Assert.Equal(16, display.Asked);
        Assert.Equal(EventType.LineInput, arrived[0].Word);
        Assert.Same(window, arrived[1].Opaque);
        Assert.Equal(2u, arrived[2].Word);
        Assert.Equal(0u, arrived[3].Word);
        Assert.Equal((uint)'h', buffer[0]);
        Assert.Equal((uint)'i', buffer[1]);
        Assert.Null(window.LineRequest);
    }

    // The Unicode twin asks for the same thing over a buffer of words,
    // and says so.
    [Fact]
    public void TheUnicodeTwinsRequestTheSameThings()
    {
        var (glk, _) = Seam();
        var window = Open(glk, WindowType.TextBuffer);

        Call(glk, 0x0141, Held.OfOpaque(window), new WordBuffer(4), Held.OfWord(0));

        Assert.True(window.LineRequest!.Unicode);

        Call(glk, 0x0140, Held.OfOpaque(window));

        Assert.True(window.CharRequest);
        Assert.True(window.CharUnicode);
    }

    // A character request is one keystroke, and the byte-wide twin says
    // it wants no more than that.
    [Fact]
    public void ACharacterRequestIsOneKeystroke()
    {
        var (glk, display) = Seam();
        var window = Open(glk, WindowType.TextGrid);

        Call(glk, 0x00D2, Held.OfOpaque(window));

        Assert.True(window.CharRequest);
        Assert.False(window.CharUnicode);

        display.Chars.Enqueue(KeyCode.Return);

        var arrived = Select(glk);

        Assert.Equal(EventType.CharInput, arrived[0].Word);
        Assert.Equal(KeyCode.Return, arrived[2].Word);
        Assert.False(window.CharRequest);
    }

    // Neither request will open on the null window: a game asking for
    // input into nothing is asking for input that can never arrive.
    [Fact]
    public void TheNullWindowCanBeAskedForNothing()
    {
        var (glk, _) = Seam();

        Assert.Equal(
            "request_line_event: invalid window",
            Assert.Throws<GlulxException>(
                () => Call(glk, 0x00D0, Held.OfOpaque(null), new WordBuffer(4), Held.OfWord(0)))
                .Message);

        Assert.Equal(
            "request_char_event: invalid window",
            Assert.Throws<GlulxException>(() => Call(glk, 0x00D2, Held.OfOpaque(null))).Message);
    }

    // One line at a time: a second request on a window already waiting
    // is refused rather than quietly replacing the first.
    [Fact]
    public void AWindowWaitsOnOneLineAtATime()
    {
        var (glk, _) = Seam();
        var window = Open(glk, WindowType.TextBuffer);

        Call(glk, 0x00D0, Held.OfOpaque(window), new WordBuffer(4), Held.OfWord(0));

        var refusal = Assert.Throws<GlulxException>(
            () => Call(glk, 0x00D0, Held.OfOpaque(window), new WordBuffer(4), Held.OfWord(0)));

        Assert.Equal("request_line_event: input already requested", refusal.Message);
    }

    // Cancelling withdraws the request and answers the no-event, since
    // nothing here keeps a half-typed line. The null window and the
    // absent struct are both simply nothing to do.
    [Fact]
    public void CancellingWithdrawsAndAnswersNothing()
    {
        var (glk, _) = Seam();
        var window = Open(glk, WindowType.TextBuffer);
        var record = new RefStruct(4);

        Call(glk, 0x00D0, Held.OfOpaque(window), new WordBuffer(4), Held.OfWord(0));
        Call(glk, 0x00D1, Held.OfOpaque(window), record);

        Assert.Null(window.LineRequest);
        Assert.Equal(EventType.None, record[0].Word);
        Assert.Null(record[1].Opaque);

        Call(glk, 0x00D2, Held.OfOpaque(window));
        Call(glk, 0x00D3, Held.OfOpaque(window));

        Assert.False(window.CharRequest);

        // Neither cancel has anything to say about nothing.
        Call(glk, 0x00D1, Held.OfOpaque(null), null);
        Call(glk, 0x00D3, Held.OfOpaque(null));
    }

    // Clicks and links are asked for and withdrawn the same way, and
    // the null window is nothing to ask about for either.
    [Fact]
    public void ClicksAndLinksAreAskedForAndWithdrawn()
    {
        var (glk, _) = Seam();
        var window = Open(glk, WindowType.TextGrid);

        Call(glk, 0x00D4, Held.OfOpaque(window));
        Call(glk, 0x0102, Held.OfOpaque(window));

        Assert.True(window.MouseRequest);
        Assert.True(window.HyperlinkRequest);

        Call(glk, 0x00D5, Held.OfOpaque(window));
        Call(glk, 0x0103, Held.OfOpaque(window));

        Assert.False(window.MouseRequest);
        Assert.False(window.HyperlinkRequest);

        Call(glk, 0x00D4, Held.OfOpaque(null));
        Call(glk, 0x0102, Held.OfOpaque(null));
    }

    // The timer cadence is remembered and the display is told, so a
    // face with its own clock can start and stop one.
    [Fact]
    public void TheTimerCadenceReachesTheDisplay()
    {
        var (glk, display) = Seam();

        Call(glk, 0x00D6, Held.OfWord(500));

        Assert.Equal(500, glk.TimerInterval);

        Call(glk, 0x00D6, Held.OfWord(0));

        Assert.Equal(0, glk.TimerInterval);
        Assert.Equal([500, 0], display.Timers);
    }

    // The echo and the terminators belong to the pending request, so
    // setting either without one standing is simply nothing at all.
    [Fact]
    public void TheEchoAndTheTerminatorsBelongToThePendingLine()
    {
        var (glk, _) = Seam();
        var window = Open(glk, WindowType.TextBuffer);

        // Nothing pending, and nothing happens.
        Call(glk, 0x0150, Held.OfOpaque(window), Held.OfWord(0));
        Call(glk, 0x0151, Held.OfOpaque(window), new WordBuffer(KeyCode.Escape));
        Call(glk, 0x0150, Held.OfOpaque(null), Held.OfWord(0));
        Call(glk, 0x0151, Held.OfOpaque(null), null);

        Call(glk, 0x00D0, Held.OfOpaque(window), new WordBuffer(4), Held.OfWord(0));

        Assert.True(window.LineRequest!.Echo);
        Assert.Empty(window.LineRequest.Terminators);

        Call(glk, 0x0150, Held.OfOpaque(window), Held.OfWord(0));
        Call(glk, 0x0151, Held.OfOpaque(window), new WordBuffer(KeyCode.Escape, KeyCode.Func1));

        Assert.False(window.LineRequest.Echo);
        Assert.Equal([KeyCode.Escape, KeyCode.Func1], window.LineRequest.Terminators);

        // And a null buffer of terminators names none.
        Call(glk, 0x0151, Held.OfOpaque(window), null);

        Assert.Empty(window.LineRequest.Terminators);
    }

    // A finished line is echoed into a buffer window in the Input
    // style, and the style the window was wearing comes back after.
    [Fact]
    public void AFinishedLineIsEchoedInTheInputStyle()
    {
        var (glk, display) = Seam();
        var window = (TextBufferWindow)Open(glk, WindowType.TextBuffer);

        window.Style = TextStyle.Header;

        Call(glk, 0x00D0, Held.OfOpaque(window), new WordBuffer(16), Held.OfWord(0));

        display.Lines.Enqueue(("north", 0));
        Select(glk);

        Assert.Equal("north\n", window.Text());
        Assert.Equal(TextStyle.Header, window.Style);
    }

    // The echo is the library's courtesy, not a rule: a display that
    // already shows what the player typed is not asked to show it
    // twice, and a request with the echo turned off shows nothing.
    [Fact]
    public void ThereAreThreeReasonsNotToEchoALine()
    {
        foreach (var echoing in new[] { false, true })
        {
            var (glk, display) = Seam();
            var window = (TextBufferWindow)Open(glk, WindowType.TextBuffer);

            display.Echoes = echoing;

            Call(glk, 0x00D0, Held.OfOpaque(window), new WordBuffer(16), Held.OfWord(0));

            if (!echoing)
            {
                Call(glk, 0x0150, Held.OfOpaque(window), Held.OfWord(0));
            }

            display.Lines.Enqueue(("north", 0));
            Select(glk);

            Assert.Equal("", window.Text());
        }

        // And a grid window has no flow to echo into.
        var (bare, face) = Seam();
        var grid = Open(bare, WindowType.TextGrid);

        Call(bare, 0x00D0, Held.OfOpaque(grid), new WordBuffer(16), Held.OfWord(0));

        face.Lines.Enqueue(("north", 0));

        Assert.Equal(EventType.LineInput, Select(bare)[0].Word);
    }

    // A line longer than the buffer fills it and reports what fit, and
    // the echo shows only as much as the game will read.
    [Fact]
    public void ALineLongerThanItsBufferIsCutToWhatFits()
    {
        var (glk, display) = Seam();
        var window = (TextBufferWindow)Open(glk, WindowType.TextBuffer);
        var buffer = new WordBuffer(3);

        Call(glk, 0x00D0, Held.OfOpaque(window), buffer, Held.OfWord(0));

        display.Lines.Enqueue(("northwest", 0));

        Assert.Equal(3u, Select(glk)[2].Word);
        Assert.Equal("nor\n", window.Text());
    }

    // A character above the basic plane is one character to Glk, so a
    // cut counts it once however many units hold it.
    [Fact]
    public void AnAstralCharacterCountsOnceInALine()
    {
        var (glk, display) = Seam();
        var window = (TextBufferWindow)Open(glk, WindowType.TextBuffer);
        var buffer = new WordBuffer(2);

        Call(glk, 0x00D0, Held.OfOpaque(window), buffer, Held.OfWord(0));

        display.Lines.Enqueue(("\U0001F600ab", 0));

        Assert.Equal(2u, Select(glk)[2].Word);
        Assert.Equal(0x1F600u, buffer[0]);
        Assert.Equal((uint)'a', buffer[1]);
        Assert.Equal("\U0001F600a\n", window.Text());
    }

    // A request with no buffer at all reads nothing and says so, which
    // is what a host that wired the request itself would see.
    [Fact]
    public void ARequestWithNoBufferReadsNothing()
    {
        var (glk, _) = Seam();
        var window = Open(glk, WindowType.TextGrid);

        window.LineRequest = new LineRequest(null);

        Assert.Equal(0u, glk.DeliverLine(window, "north").Val1);
    }

    // The terminator the display reports travels through into the
    // event's second value (Glk: Line Input Events).
    [Fact]
    public void TheTerminatorTravelsIntoTheEvent()
    {
        var (glk, display) = Seam();
        var window = Open(glk, WindowType.TextBuffer);

        Call(glk, 0x00D0, Held.OfOpaque(window), new WordBuffer(8), Held.OfWord(0));

        display.Lines.Enqueue(("go", KeyCode.Escape));

        Assert.Equal(KeyCode.Escape, Select(glk)[3].Word);
    }

    // Input delivered to a window that never asked for it is a driver's
    // bug, and each of the four says so in its own words.
    [Fact]
    public void InputNobodyAskedForIsRefusedByName()
    {
        var (glk, _) = Seam();
        var window = Open(glk, WindowType.TextGrid);

        Assert.Equal(
            "line input delivered to a window not expecting it",
            Assert.Throws<GlulxException>(() => glk.DeliverLine(window, "north")).Message);

        Assert.Equal(
            "character input delivered to a window not expecting it",
            Assert.Throws<GlulxException>(() => Api.DeliverChar(window, 0x41)).Message);

        Assert.Equal(
            "mouse input delivered to a window not expecting it",
            Assert.Throws<GlulxException>(() => Api.DeliverMouse(window, 1, 2)).Message);

        Assert.Equal(
            "hyperlink input delivered to a window not expecting it",
            Assert.Throws<GlulxException>(() => Api.DeliverHyperlink(window, 7)).Message);
    }

    // A click reaches the game as a position; a link as its value.
    [Fact]
    public void AClickAndALinkArriveWithTheirValues()
    {
        var (glk, display) = Seam();
        var window = Open(glk, WindowType.TextGrid);

        display.Clicks = true;
        display.Follows = true;

        Call(glk, 0x00D4, Held.OfOpaque(window));

        display.Mice.Enqueue((4, 9));

        var clicked = Select(glk);

        Assert.Equal(EventType.MouseInput, clicked[0].Word);
        Assert.Equal(4u, clicked[2].Word);
        Assert.Equal(9u, clicked[3].Word);
        Assert.False(window.MouseRequest);

        Call(glk, 0x0102, Held.OfOpaque(window));

        display.Links.Enqueue(77);

        var followed = Select(glk);

        Assert.Equal(EventType.Hyperlink, followed[0].Word);
        Assert.Equal(77u, followed[2].Word);
        Assert.False(window.HyperlinkRequest);
    }

    // Answering nothing means "not yet, but something else happened":
    // the request stays pending and the loop comes round, which is what
    // lets a timer arrive without cancelling the input beneath it.
    [Fact]
    public void AnInterruptionLeavesTheRequestStanding()
    {
        foreach (var selector in new[] { 0x00D0, 0x00D2, 0x00D4, 0x0102 })
        {
            var (glk, display) = Seam();
            var window = Open(glk, WindowType.TextGrid);

            display.Clicks = true;
            display.Follows = true;
            display.Interruption = new GlkEvent(EventType.Timer);

            Request(glk, selector, window);

            display.Lines.Enqueue(null);
            display.Chars.Enqueue(null);
            display.Mice.Enqueue(null);
            display.Links.Enqueue(null);

            // The read raised the timer instead of answering, so the
            // loop comes round and finds it queued.
            Assert.Equal(EventType.Timer, Select(glk)[0].Word);
            Assert.Equal(2, display.Flushes);
        }
    }

    // A link value of zero is no link at all: the same nothing a
    // display with none to report answers, and the request stands.
    [Fact]
    public void AZeroLinkIsNoLinkAtAll()
    {
        var (glk, display) = Seam();
        var window = Open(glk, WindowType.TextGrid);

        display.Follows = true;
        display.Interruption = new GlkEvent(EventType.Timer);

        Call(glk, 0x0102, Held.OfOpaque(window));
        display.Links.Enqueue(0);

        Assert.Equal(EventType.Timer, Select(glk)[0].Word);
        Assert.True(window.HyperlinkRequest);
    }

    // A display that cannot click, asked about a window waiting on a
    // click, is not being interrupted: it can never answer, and a game
    // that waits on it would wait forever.
    [Fact]
    public void ARequestTheDisplayCannotAnswerIsRefused()
    {
        foreach (var selector in new[] { 0x00D4, 0x0102 })
        {
            var (glk, display) = Seam();
            var window = Open(glk, WindowType.TextGrid);

            Request(glk, selector, window);

            display.Mice.Enqueue(null);
            display.Links.Enqueue(null);

            var refusal = Assert.Throws<GlulxException>(() => Select(glk));

            Assert.Equal(
                "glk_select with no input requested: the game would wait forever",
                refusal.Message);
        }
    }

    // A select with nothing requested at all is the same refusal, and
    // it is loud rather than a hang.
    [Fact]
    public void ASelectWithNothingRequestedIsRefused()
    {
        var (glk, _) = Seam();

        Open(glk, WindowType.TextBuffer);

        var refusal = Assert.Throws<GlulxException>(() => Select(glk));

        Assert.Equal(
            "glk_select with no input requested: the game would wait forever",
            refusal.Message);
    }

    // A queued event is delivered before any input is asked for, so a
    // face's own news never waits behind a keystroke.
    [Fact]
    public void AQueuedEventArrivesBeforeAnythingIsAsked()
    {
        var (glk, display) = Seam();
        var window = Open(glk, WindowType.TextBuffer);

        Call(glk, 0x00D2, Held.OfOpaque(window));
        display.Raise(new GlkEvent(EventType.Redraw, window));

        Assert.Equal(EventType.Redraw, Select(glk)[0].Word);
        Assert.True(window.CharRequest);
    }

    // A poll never returns input, only the events a display raises by
    // itself, and it takes the first of those wherever it sits.
    [Fact]
    public void APollTakesTheFirstEventADisplayRaisedItself()
    {
        var (glk, display) = Seam();
        var window = Open(glk, WindowType.TextBuffer);

        display.Raise(new GlkEvent(EventType.LineInput, window, 4));
        display.Raise(new GlkEvent(EventType.Timer));

        var polled = new RefStruct(4);

        Call(glk, 0x00C1, polled);

        Assert.Equal(EventType.Timer, polled[0].Word);
        Assert.Single(glk.PendingEvents);

        // The line event is still queued, and a poll will not take it.
        Call(glk, 0x00C1, polled);

        Assert.Equal(EventType.None, polled[0].Word);
        Assert.Single(glk.PendingEvents);
    }

    // A poll over an empty queue is the no-event.
    [Fact]
    public void APollOverNothingIsTheNoEvent()
    {
        var (glk, _) = Seam();
        var polled = new RefStruct(4);

        Call(glk, 0x00C1, polled);

        Assert.Equal(EventType.None, polled[0].Word);
        Assert.Null(polled[1].Opaque);
    }

    // A resize re-lays the tree and tells the game, so it can redraw
    // whatever it keeps track of itself.
    [Fact]
    public void AResizeRelaysTheTreeAndSaysSo()
    {
        var (glk, display) = Seam();
        var window = Open(glk, WindowType.TextBuffer);

        glk.DisplayResized();

        var arrived = Assert.Single(glk.PendingEvents);

        Assert.Equal(EventType.Arrange, arrived.Kind);
        Assert.Same(window, arrived.Window);
        Assert.Equal(display.Size().Width, window.Width);
    }

    // A display with no library behind it has nowhere to put an event,
    // and putting one there is simply nothing.
    [Fact]
    public void ADisplayWithNoLibraryHasNowhereToPutAnEvent()
    {
        var loose = new ScriptedDisplay();

        loose.Raise(new GlkEvent(EventType.Timer));

        Assert.Null(loose.Attached);
    }

    // The face that shows nothing can be asked for nothing: a game
    // waiting on input that can never arrive ends the session instead.
    [Fact]
    public void TheNullFaceEndsTheSessionRatherThanWaitOnIt()
    {
        var glk = new Api();
        var window = Open(glk, WindowType.TextBuffer);

        Call(glk, 0x00D0, Held.OfOpaque(window), new WordBuffer(8), Held.OfWord(0));

        Assert.Throws<SessionEndException>(() => Select(glk));

        Call(glk, 0x00D1, Held.OfOpaque(window), null);
        Call(glk, 0x00D2, Held.OfOpaque(window));

        Assert.Throws<SessionEndException>(() => Select(glk));
    }

    // A display claims what it can do, and everything it does not claim
    // has an answer waiting for it. The plain face overrides none of
    // these, so what a game asks of it is what the seat itself says: no
    // clock to set, no click, no link, no picker, and no echoing of its
    // own to spare the library the trouble.
    [Fact]
    public void ThePlainFaceAnswersForEverythingItNeverClaimed()
    {
        var glk = new Api();
        var window = (TextBufferWindow)Open(glk, WindowType.TextBuffer);

        // A cadence nobody rings is set all the same, and refused by
        // nobody.
        Call(glk, 0x00D6, Held.OfWord(500));

        Assert.Equal(500, glk.TimerInterval);

        // No picker means the prompt is cancelled, which is always a
        // legitimate answer.
        Assert.Null(Call(glk, 0x0062,
            Held.OfWord(FileUsage.SavedGame), Held.OfWord(0x02), Held.OfWord(0)).Opaque);

        // The library echoes, because the face does not.
        window.LineRequest = new LineRequest(new WordBuffer(8));

        glk.DeliverLine(window, "north");

        Assert.Equal("north\n", window.Text());

        // And a click or a link it can never report is a wait that would
        // never end, not an interruption.
        foreach (var selector in new[] { 0x00D4, 0x0102 })
        {
            var waiting = new Api();
            var grid = Open(waiting, WindowType.TextGrid);

            Call(waiting, selector, Held.OfOpaque(grid));

            var refusal = Assert.Throws<GlulxException>(() => Select(waiting));

            Assert.Equal(
                "glk_select with no input requested: the game would wait forever",
                refusal.Message);
        }
    }

    /// <summary>Open one of the four requests on a window.</summary>
    private static void Request(Api glk, int selector, Window window)
    {
        if (selector == 0x00D0)
        {
            Call(glk, selector, Held.OfOpaque(window), new WordBuffer(8), Held.OfWord(0));

            return;
        }

        Call(glk, selector, Held.OfOpaque(window));
    }

    /// <summary>Run a select and hand back the struct it filled.</summary>
    private static RefStruct Select(Api glk)
    {
        var record = new RefStruct(4);

        Call(glk, 0x00C0, record);

        return record;
    }

    /// <summary>Open a window of a type as the root of the tree.</summary>
    private static Window Open(Api glk, uint wtype)
    {
        Call(glk, 0x0023, Held.OfOpaque(null), Held.OfWord(0), Held.OfWord(0),
            Held.OfWord(wtype), Held.OfWord(0));

        return glk.Root!;
    }

    /// <summary>Reach one function the way the bridge would.</summary>
    private static Held Call(Api glk, int selector, params object?[] args) =>
        glk.Call(Signatures.Lookup(selector)!, args);

    private static (Api Glk, ScriptedDisplay Display) Seam()
    {
        var display = new ScriptedDisplay();

        return (new Api(display), display);
    }
}
