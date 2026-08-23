"""The painted Glk displays' shared spine.

A painted display -- the blessed terminal, the pygame window --
keeps one shape: the window tree repaints whole on every flush,
grids from their cells and buffers from wrapped text with
scrollback and [MORE]; input is collected synchronously at a
keyboard that echoes nothing, the half-typed line drawn as part of
the layout; and a timer coming round or a sound ending interrupts
a wait by posting its event and answering None, so glk_select can
come back and deliver it. All of that is display-independent and
lives here. A display itself supplies only its geometry, its way
of placing a styled run of cells, and its raw keystroke read --
the four small methods at the bottom of this class.

Redraw is unconditional and whole-screen. A partial-update scheme
would save work, but a Glulx game emits a paragraph at a time to
displays that redraw in microseconds, and the simplicity is worth
more than the savings. Every window paints its own bounding box
padded to its full width, and the boxes partition the screen
between them, so painting over is all the erasing there is -- the
same philosophy as the Z-Machine painter, which never clears
either.

Sound arrives through the same Speaker the Z-Machine's painted
frontends own, and inherits its honest limit: one sampled sound
at a time. Glk allows a game many simultaneous channels; here the
newest play takes the speaker, and a displaced channel simply
falls silent -- no completion event, because its sound did not
finish, it was shouldered aside. Games that layer music under
effects lose the layering, never the session.
"""

from abc import abstractmethod
from time import monotonic
from typing import TYPE_CHECKING

from voxam.glulx.glk.frontend import Frontend
from voxam.glulx.glk.objects import (
    Event,
    EventType,
    FileMode,
    GraphicsWindow,
    KeyCode,
    PairWindow,
    SoundChannel,
    Style,
    TextBufferWindow,
    TextGridWindow,
    Window,
)
from voxam.glulx.glk.wrap import Wrapper, plain
from voxam.painter import FALLBACK_COLUMNS, IDLE_HEARTBEAT, MORE_PROMPT
from voxam.speaker import FULL_VOLUME as SPEAKER_FULL
from voxam.speaker import Speaker

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from voxam.glulx.glk.wrap import Segment

# Glk styles as the three attributes every painted display can
# dress a run in: bold, italic, and reverse. Anything absent
# renders plain; Preformatted deliberately so, since the painted
# displays are monospaced already.
ATTRIBUTES: dict[int, tuple[str, ...]] = {
    Style.EMPHASIZED: ("italic",),
    Style.HEADER: ("bold",),
    Style.SUBHEADER: ("bold",),
    Style.ALERT: ("bold", "reverse"),
    Style.NOTE: ("italic",),
    Style.BLOCK_QUOTE: ("italic",),
    Style.INPUT: ("bold",),
    Style.USER1: ("italic",),
    Style.USER2: ("reverse",),
}

# The stylehint numbers glk_style_measure asks in (Glk: Suggesting
# the Appearance of Styles).
HINT_INDENTATION = 0
HINT_PARA_INDENTATION = 1
HINT_JUSTIFICATION = 2
HINT_SIZE = 3
HINT_WEIGHT = 4
HINT_OBLIQUE = 5
HINT_PROPORTIONAL = 6

_PRINTABLE_FLOOR = 0x20
_CHARACTER_CEILING = 0x10FFFF

# Full volume as Glk measures it (Glk: Other Sound Channel
# Functions), and the repeat count that means "until stopped"
# (Glk: Playing Sounds) as it arrives through a 32-bit machine.
GLK_FULL_VOLUME = 0x10000
FOREVER = 0xFFFFFFFF


class Timer:
    """A repeating deadline, for a display that waits with one.

    Glk timers fire every so many milliseconds while the game is
    blocked in glk_select (Glk: Timer Events). A display that can
    wait on the keyboard with a timeout wants exactly this
    bookkeeping.
    """

    def __init__(self) -> None:
        """Start stopped."""

        self.interval = 0.0
        self.deadline: float | None = None

    def set(self, millisecs: int) -> None:
        """Start firing every millisecs; zero or less stops."""

        self.interval = millisecs / 1000
        self.deadline = None if millisecs <= 0 else monotonic() + self.interval

    def timeout(self) -> float | None:
        """How long a wait may block, or None for indefinitely."""

        if self.deadline is None:
            return None

        return max(0.0, self.deadline - monotonic())

    def due(self) -> bool:
        """Whether the timer has come round; rearms it if so."""

        if self.deadline is not None and monotonic() >= self.deadline:
            self.deadline = monotonic() + self.interval

            return True

        return False


class PaintedFrontend(Frontend):
    """Paints the Glk window tree across a whole display.

    Concrete displays override the four framing primitives --
    _begin, _place, _finish, and _translated -- and everything
    else about running a session is inherited: the tree walk, the
    wrappers, the pager, the line editor, the timer, the speaker.
    """

    # Every painted display reads a key with a timeout, so timers
    # can fire.
    timer_input = True

    def __init__(
        self,
        *,
        speaker: Speaker | None = None,
        on_line: "Callable[[str, int], None] | None" = None,
        on_key: "Callable[[int], None] | None" = None,
    ) -> None:
        """Start with an empty tree and a stopped timer.

        A speaker makes the sound claim true; without one the
        display claims no sound and Glk refuses the channels
        honestly (Glk: Testing for Sound Capabilities).

        The seams hear input the moment it is accepted: on_line
        every finished line with its terminator keycode (zero for
        Return), file-prompt answers included, and on_key every
        keystroke a character read delivered. A recording rides
        them; the display itself neither knows nor cares.
        """

        self._root: Window | None = None
        # Each buffer window's kept text, keyed by the window
        # itself rather than its id, so a window closed and another
        # opened cannot inherit the first one's text through a
        # reused address.
        self._buffers: dict[TextBufferWindow, Wrapper] = {}
        # The line being typed, and where it is being typed.
        self._typed = ""
        self._typing: Window | None = None
        self.timer = Timer()
        self._speaker = speaker
        self.sound = speaker is not None
        # The one channel the speaker is sounding for, if any.
        self._sounding: SoundChannel | None = None
        self._on_line = on_line
        self._on_key = on_key

    # -- display -------------------------------------------------------------

    def clear(self) -> None:
        """Paint every row blank, wiping what the shell left.

        Positions here and throughout the painting walk are in
        display units -- cells at a terminal, pixels at a window --
        with the metrics converting the character counts, so the
        one walk serves both.
        """

        width, height = self.size()
        cell = self.metrics
        columns = int(width / cell.width)
        self._begin()

        for row in range(int(height / cell.height)):
            self._place(0, int(row * cell.height), [(Style.NORMAL, " " * columns)])

        self._finish(None)

    def flush(self, root: Window | None) -> None:
        """Repaint the whole display from the window tree."""

        self._root = root

        if root is None:
            return

        self._begin()
        self._finish(self._paint(root))

    def _paint(self, window: Window) -> tuple[int, int] | None:
        """Draw a window and its children; say where the cursor goes."""

        if isinstance(window, PairWindow):
            first = self._paint(window.child1)
            second = self._paint(window.child2)

            return second or first

        if isinstance(window, TextGridWindow):
            return self._paint_grid(window)

        if isinstance(window, TextBufferWindow):
            return self._paint_buffer(window)

        if isinstance(window, GraphicsWindow):
            self._paint_graphics(window)

            return None

        # A blank window shows blankness (Glk: Blank Windows) --
        # and so does anything else without text to paint. The box
        # is measured directly: a sizeless window answers the game
        # zero, but its box is still real and still needs covering.
        left, top, right, bottom = window.bbox
        cell = window.metrics
        columns = int((right - left) / cell.width)

        for index in range(int((bottom - top) / cell.height)):
            self._place(
                left, int(top + index * cell.height), [(Style.NORMAL, " " * columns)]
            )

        return None

    def _paint_graphics(self, window: GraphicsWindow) -> None:
        """Honor a pending clear; otherwise leave the canvas alone.

        Painting over is all the erasing there is for text, but a
        graphics window's pixels are the game's own work: they
        persist on the display until the game draws again, so the
        repaint must not cover them. A pending clear erases the
        whole canvas to its background (Glk: Graphics Windows).
        """

        if window.pending_clear:
            self.erase_rect(window, 0, 0, window.width, window.height)
            window.pending_clear = False

    def _paint_grid(self, window: TextGridWindow) -> tuple[int, int] | None:
        left, top, _, _ = window.bbox
        cell = window.metrics

        # The grid's rows are already exactly its size: the model
        # resizes them with every rearrange.
        for index, cells in enumerate(window.lines):
            self._place(
                left,
                int(top + index * cell.height),
                _grouped(cells, window.styles[index]),
            )

        if self._typing is not window:
            return None

        # A grid window taking line input shows it at the cursor,
        # where the game left it -- there is nowhere else it could
        # sensibly go.
        column = min(window.cursor_x, max(0, window.width - 1))
        row = min(window.cursor_y, max(0, window.height - 1))
        text = self._typed[: max(0, window.width - column)]
        x = int(left + column * cell.width)
        y = int(top + row * cell.height)
        self._place(x, y, [(Style.INPUT, text)])

        return (int(x + len(text) * cell.width), y)

    def _paint_buffer(self, window: TextBufferWindow) -> tuple[int, int] | None:
        wrapper = self._wrapper(window)
        wrapper.add((run.style, run.text) for run in window.take_content())

        left, top, _, _ = window.bbox
        height = window.height

        if height <= 0:
            # A buffer squeezed flat by a split still keeps its
            # text; there is just nowhere to paint it.
            return None

        visible, _, more = wrapper.view(height)

        typing = self._typing is window and not more

        if typing:
            # The line being typed belongs at the end of the text,
            # but is not part of it until the game accepts it.
            visible = wrapper.preview([(Style.INPUT, self._typed)])[-height:]

        # The newest line sits at the bottom of the box, so the
        # display scrolls the way a terminal does rather than
        # filling downwards.
        offset = height - len(visible) - (1 if more else 0)
        cell = window.metrics
        bottom = int(top + (height - 1) * cell.height)

        for index in range(height):
            line = visible[index - offset] if 0 <= index - offset < len(visible) else []
            pad = " " * max(0, window.width - len(plain(line)))
            self._place(
                left, int(top + index * cell.height), [*line, (Style.NORMAL, pad)]
            )

        if more:
            pad = " " * max(0, window.width - len(MORE_PROMPT))
            self._place(
                left,
                bottom,
                [(Style.ALERT, MORE_PROMPT), (Style.NORMAL, pad)],
            )

            return (int(left + len(MORE_PROMPT) * cell.width), bottom)

        if not typing or not visible:
            return None

        return (int(left + len(plain(visible[-1])) * cell.width), bottom)

    def _wrapper(self, window: TextBufferWindow) -> Wrapper:
        """The kept text for a window, made current with its size."""

        wrapper = self._buffers.get(window)

        if wrapper is None:
            wrapper = Wrapper(window.width or FALLBACK_COLUMNS)
            self._buffers[window] = wrapper
        else:
            wrapper.resize(window.width or FALLBACK_COLUMNS)

        if window.pending_clear:
            wrapper.clear()
            window.pending_clear = False

        return wrapper

    def retire(self) -> None:
        """Leave the display ready for the shell's next prompt.

        A display drawing on the terminal parks the cursor under
        the story; a display in its own window has nothing to
        yield and inherits this quiet default.
        """

    # -- timers --------------------------------------------------------------

    def set_timer(self, millisecs: int) -> None:
        """Ask for timer events every so often; zero stops them."""

        self.timer.set(millisecs)

    # -- sound ---------------------------------------------------------------

    def play_sound(
        self, channel: SoundChannel, sound: int, repeats: int, notify: int
    ) -> bool:
        """Start a sound through the speaker; the newest play wins.

        The channel's own volume and notify request are already on
        the channel (Glk: Playing Sounds); what the speaker needs
        is the translation -- Glk's 0x10000 scale to the speaker's
        eight steps, and the until-stopped repeat count to the
        speaker's zero.
        """

        del notify

        if self._speaker is None:
            return False

        started = self._speaker.play(
            sound,
            _steps(channel.volume),
            0 if repeats == FOREVER else repeats,
        )

        if started:
            self._sounding = channel

        return started

    def stop_sound(self, channel: SoundChannel) -> None:
        """Silence a channel -- if it is the one being heard.

        A channel whose play was displaced by a newer one has
        nothing sounding to stop.
        """

        if channel is self._sounding and self._speaker is not None:
            self._speaker.stop()
            self._sounding = None

    def pause_sound(self, channel: SoundChannel, paused: bool) -> None:
        """Pause as silence; resume as starting over.

        The speaker owns no playback positions, so a paused sound
        cannot pick up mid-sample: unpausing plays the channel's
        sound again from its start. Neither edge is a natural
        ending, so neither raises a completion event.
        """

        if paused:
            self.stop_sound(channel)
        elif channel.sound:
            self.play_sound(channel, channel.sound, channel.repeats, channel.notify)

    def set_volume(self, channel: SoundChannel, volume: int, duration: int) -> None:
        """Take effect from the channel's next play.

        The speaker scales samples once, when a play starts, so a
        change of volume cannot reach a sound already sounding --
        and a fade duration even less. The channel remembers the
        volume (Glk: Other Sound Channel Functions), and the next
        play_sound reads it from there.
        """

        del channel, volume, duration

    def hush(self) -> None:
        """Stop the speaker outright, for the end of the session.

        A looping sound would otherwise play on past quit.
        """

        if self._speaker is not None:
            self._speaker.stop()
            self._sounding = None

    def _listen(self) -> bool:
        """Hear a sound ending naturally; did an event get posted?

        A natural ending clears the channel, and one that asked
        for notification posts the completion event (Glk: Playing
        Sounds) for the next select to deliver.
        """

        if self._speaker is None or not self._speaker.finished():
            return False

        channel, self._sounding = self._sounding, None

        if channel is None:
            return False

        ended, channel.sound = channel.sound, 0

        if not channel.notify:
            return False

        self.post(Event(EventType.SOUND_NOTIFY, None, ended, channel.notify))

        return True

    # -- input ---------------------------------------------------------------

    def read_line(self, window: Window, maxlen: int) -> tuple[str, int] | None:
        """Collect a line at the keyboard, drawn as it is typed."""

        request = window.line_request
        terminators = request.terminators if request is not None else ()
        self._typing = window
        # The flush that preceded this did not know where input was
        # going, so repaint once to put the cursor at the prompt.
        self._repaint()

        while True:
            code = self._key()

            if code is None:
                # A timer fired mid-line. The half-typed line stays
                # where it is and the request stays pending;
                # glk_select will be back for it once it has
                # delivered the timer event.
                return None

            if code == KeyCode.RETURN:
                return self._accept(maxlen, 0)

            if code in terminators:
                return self._accept(maxlen, code)

            self._edit(code, maxlen)
            self._repaint()

    def _accept(self, maxlen: int, terminator: int) -> tuple[str, int]:
        text = self._typed[:maxlen]
        self._typed = ""
        self._typing = None

        if self._on_line is not None:
            self._on_line(text, terminator)

        return text, terminator

    def _edit(self, code: int, maxlen: int) -> None:
        """Apply one keystroke to the line being typed."""

        if code == KeyCode.DELETE:
            self._typed = self._typed[:-1]
        elif code == KeyCode.ESCAPE:
            self._typed = ""
        elif (
            _PRINTABLE_FLOOR <= code <= _CHARACTER_CEILING and len(self._typed) < maxlen
        ):
            self._typed += chr(code)

    def read_char(self, window: Window) -> int | None:
        """One keystroke, as a Glk character code."""

        del window

        code = self._key()

        if code is not None and self._on_key is not None:
            self._on_key(code)

        return code

    def _key(self) -> int | None:
        """Wait for a keystroke; None if something else came up.

        A key pressed while text is waiting turns the page instead
        of reaching the game -- which is the whole point of the
        pause, and why every input path goes through here. The
        something else is a timer coming round or a sound ending
        with a notification owed: either posts its event and
        answers None, so glk_select can come back and deliver it.
        """

        while True:
            if self._listen():
                return None

            timeout = self.timer.timeout()

            if self._sounding is not None and (
                timeout is None or timeout > IDLE_HEARTBEAT
            ):
                # While a sound plays, the infinite wait is chopped
                # into heartbeats so its ending can be heard
                # between keystrokes, not just after one.
                timeout = IDLE_HEARTBEAT

            code = self._translated(timeout)

            if code is not None:
                if self._turn_page():
                    continue

                return code

            if self.timer.due():
                self.post(Event(EventType.TIMER))

                return None

    def _turn_page(self) -> bool:
        """Show the next page of every waiting window; did any wait?"""

        waiting = [
            (window, wrapper)
            for window, wrapper in self._buffers.items()
            if wrapper.view(window.height).more
        ]

        for window, wrapper in waiting:
            wrapper.advance(window.height)

        if waiting:
            self._repaint()

        return bool(waiting)

    def _catch_up(self) -> None:
        """Treat every window as read, so nothing is waiting."""

        for wrapper in self._buffers.values():
            wrapper.catch_up()

    def _repaint(self) -> None:
        """Redraw after a keystroke, so typing is visible."""

        if self._root is not None:
            self.flush(self._root)

    def prompt_file(self, usage: int, fmode: int) -> str | None:
        """Ask for a filename on the bottom line of the display."""

        del usage

        verb = "Load from" if fmode == FileMode.READ else "Save to"
        prompt = f"{verb} which file? "
        width, height = self.size()
        cell = self.metrics
        columns = int(width / cell.width)
        bottom = int((int(height / cell.height) - 1) * cell.height)
        # glkterm forces every window to the end before a prompt
        # like this one, so the player is answering a question
        # rather than fighting a pager for the keyboard.
        self._catch_up()
        saved, self._typed = self._typed, ""
        saved_window, self._typing = self._typing, None

        try:
            while True:
                text = self._typed[: max(0, columns - len(prompt) - 1)]
                line = (prompt + text).ljust(columns - 1)
                self._begin()
                self._place(0, bottom, [(Style.NORMAL, line)])
                self._finish((int((len(prompt) + len(text)) * cell.width), bottom))

                code = self._key()

                if code is None:
                    # A timer during a file prompt is not an event.
                    continue

                if code == KeyCode.RETURN:
                    return self._answered(self._typed.strip() or None)

                if code == KeyCode.ESCAPE:
                    return self._answered(None)

                self._edit(code, columns)
        finally:
            self._typed, self._typing = saved, saved_window
            self._repaint()

    def _answered(self, name: str | None) -> str | None:
        """Pass a file-prompt answer through the line seam.

        The seam hears what a replay must feed the prompt: the
        name, or the empty line that cancels.
        """

        if self._on_line is not None:
            self._on_line(name or "", 0)

        return name

    # -- styles --------------------------------------------------------------

    def style_distinguish(self, window: Window, first: int, second: int) -> bool:
        """Two styles differ here when their dress differs."""

        del window

        return ATTRIBUTES.get(first, ()) != ATTRIBUTES.get(second, ())

    def style_measure(self, window: Window, style: int, hint: int) -> int | None:
        """Measure a style hint. A character cell is the only unit."""

        del window

        attributes = ATTRIBUTES.get(style, ())

        if hint == HINT_SIZE:
            # Relative to the normal size, which is the only size.
            return 0

        if hint == HINT_WEIGHT:
            return 1 if "bold" in attributes else 0

        if hint == HINT_OBLIQUE:
            return 1 if "italic" in attributes else 0

        if hint == HINT_PROPORTIONAL:
            # The painted displays are monospaced throughout.
            return 0

        if hint in (HINT_INDENTATION, HINT_PARA_INDENTATION):
            return 0

        return None

    # -- what a concrete display supplies ------------------------------------

    @abstractmethod
    def _begin(self) -> None:
        """Start one frame of painting."""

    @abstractmethod
    def _place(self, x: int, y: int, line: "Iterable[Segment]") -> None:
        """Put a styled run of cells at a display position.

        The position is 0-based cells, x across and y down -- the
        same units the window tree's bounding boxes are measured
        in.
        """

    @abstractmethod
    def _finish(self, cursor: tuple[int, int] | None) -> None:
        """End the frame, with the cursor shown at a cell or not."""

    @abstractmethod
    def _translated(self, timeout: float | None) -> int | None:
        """One raw read as a Glk code; None for nothing usable.

        Nothing usable covers an expired timeout as well as any
        keystroke the display cannot spell as a Glk character
        code.
        """


def _grouped(row: list[str], styles: list[int]) -> "list[Segment]":
    """Collapse a grid row's per-cell styles into runs."""

    segments: list[tuple[int, str]] = []

    for index, character in enumerate(row):
        style = styles[index] if index < len(styles) else Style.NORMAL

        if segments and segments[-1][0] == style:
            segments[-1] = (style, segments[-1][1] + character)
        else:
            segments.append((style, character))

    return list(segments)


def _steps(volume: int) -> int:
    """Glk's 0x10000 volume scale as the speaker's eight steps.

    Rounded to the nearest step and clamped from above: Glk allows
    amplification past full volume, and the speaker's answer to
    louder-than-loud is loud (Glk: Other Sound Channel Functions).
    """

    scaled = (volume * SPEAKER_FULL + GLK_FULL_VOLUME // 2) // GLK_FULL_VOLUME

    return min(SPEAKER_FULL, scaled)
