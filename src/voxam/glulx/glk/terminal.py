"""A full-screen terminal display, in the manner of glkterm.

The window tree keeps its own contents -- grids their cells,
buffers their styled runs -- and this display's whole job is to
paint that tree across the terminal on every flush, then wait at
the keyboard. It rides the same blessed sliver the Z-Machine's
painter does: the Terminal protocol from voxam.painter, so a test
drives the whole display with a stub and no terminal at all.

Redraw is unconditional and whole-screen. A partial-update scheme
would save output bytes, but a Glulx game emits a paragraph at a
time to a terminal that redraws in microseconds, and the
simplicity is worth more than the bytes. Every window paints its
own bounding box padded to its full width, and the boxes partition
the screen between them, so painting over is all the erasing there
is -- the same philosophy as the Z-Machine painter, which never
clears either.

The terminal is in cbreak mode while reading, so it echoes
nothing: Glk does the echoing into the window once a line is
accepted, and until then the half-typed line is drawn here, as
part of the layout but not yet part of the window.
"""

import sys
from time import monotonic
from typing import TYPE_CHECKING, cast

from voxam.glulx.glk.frontend import Frontend
from voxam.glulx.glk.objects import (
    Event,
    EventType,
    FileMode,
    KeyCode,
    PairWindow,
    Style,
    TextBufferWindow,
    TextGridWindow,
    Window,
)
from voxam.glulx.glk.wrap import Segment, Wrapper, plain
from voxam.painter import FALLBACK_COLUMNS, FALLBACK_LINES, MORE_PROMPT, Terminal

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

# Glk styles as terminal attributes, drawn from the sequences the
# Terminal protocol already carries for the Z-Machine's §8.7.1
# styles. Anything absent renders plain; Preformatted deliberately
# so, since a terminal is monospaced already.
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

# blessed key names for the keys Glk has codes of its own for
# (Glk: Character Input).
KEYNAMES = {
    "KEY_LEFT": KeyCode.LEFT,
    "KEY_RIGHT": KeyCode.RIGHT,
    "KEY_UP": KeyCode.UP,
    "KEY_DOWN": KeyCode.DOWN,
    "KEY_ENTER": KeyCode.RETURN,
    "KEY_BACKSPACE": KeyCode.DELETE,
    "KEY_DELETE": KeyCode.DELETE,
    "KEY_ESCAPE": KeyCode.ESCAPE,
    "KEY_TAB": KeyCode.TAB,
    "KEY_PGUP": KeyCode.PAGE_UP,
    "KEY_PGDOWN": KeyCode.PAGE_DOWN,
    "KEY_HOME": KeyCode.HOME,
    "KEY_END": KeyCode.END,
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

# The single characters a raw keystroke may arrive as for keys
# that have Glk codes of their own.
_CONTROL_KEYS = {
    0x08: KeyCode.DELETE,
    0x7F: KeyCode.DELETE,
    0x1B: KeyCode.ESCAPE,
    0x09: KeyCode.TAB,
    0x0A: KeyCode.RETURN,
    0x0D: KeyCode.RETURN,
}

_PRINTABLE_FLOOR = 0x20
_CHARACTER_CEILING = 0x10FFFF


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


class TerminalFrontend(Frontend):
    """Paints the Glk window tree across the whole terminal.

    The terminal and the output seam are injectable, the same
    arrangement the Z-Machine painter tests by: a stub terminal
    answers geometry and keystrokes, and the escape sequences land
    in a list instead of a live glass.
    """

    # blessed reads a key with a timeout, so timers can fire.
    timer_input = True

    def __init__(
        self,
        terminal: Terminal | None = None,
        out: "Callable[[str], None] | None" = None,
        *,
        size: tuple[int, int] | None = None,
    ) -> None:
        """Stand over a terminal, a real blessed one by default."""

        if terminal is None:
            # Imported here because the blessed extra is optional:
            # the stdio display must keep working without it.
            import blessed  # noqa: PLC0415

            terminal = cast("Terminal", blessed.Terminal())

        self._terminal = terminal
        self._out = out if out is not None else _stdout_write
        self._size = size
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

    # -- display -------------------------------------------------------------

    def size(self) -> tuple[int, int]:
        """The terminal's own measure, unless one was chosen."""

        if self._size is not None:
            return self._size

        return (
            self._terminal.width or FALLBACK_COLUMNS,
            self._terminal.height or FALLBACK_LINES,
        )

    def clear(self) -> None:
        """Paint every row blank, wiping what the shell left."""

        width, height = self.size()
        blank = " " * width
        pieces = [self._terminal.move_xy(0, row) + blank for row in range(height)]

        self._out("".join(pieces) + self._terminal.move_xy(0, 0))

    def flush(self, root: Window | None) -> None:
        """Repaint the whole screen from the window tree."""

        self._root = root

        if root is None:
            return

        out: list[str] = []
        cursor = self._paint(root, out)
        # Park the cursor where input is going, or out of the way
        # at the bottom if none is.
        out.append(self._terminal.move_xy(*(cursor or (0, self.size()[1] - 1))))
        self._out("".join(out))

    def _paint(self, window: Window, out: list[str]) -> tuple[int, int] | None:
        """Draw a window and its children; say where the cursor goes."""

        if isinstance(window, PairWindow):
            first = self._paint(window.child1, out)
            second = self._paint(window.child2, out)

            return second or first

        if isinstance(window, TextGridWindow):
            return self._paint_grid(window, out)

        if isinstance(window, TextBufferWindow):
            return self._paint_buffer(window, out)

        # A blank window shows blankness (Glk: Blank Windows) --
        # and so does anything else without text to paint. The box
        # is measured directly: a sizeless window answers the game
        # zero, but its box is still real and still needs covering.
        left, top, right, bottom = window.bbox

        for index in range(bottom - top):
            out.append(self._terminal.move_xy(left, top + index))
            out.append(" " * (right - left))

        return None

    def _paint_grid(
        self, window: TextGridWindow, out: list[str]
    ) -> tuple[int, int] | None:
        left, top, _, _ = window.bbox

        # The grid's rows are already exactly its size: the model
        # resizes them with every rearrange.
        for index, cells in enumerate(window.lines):
            out.append(self._terminal.move_xy(left, top + index))
            out.append(self._render(_grouped(cells, window.styles[index])))

        if self._typing is not window:
            return None

        # A grid window taking line input shows it at the cursor,
        # where the game left it -- there is nowhere else it could
        # sensibly go.
        column = min(window.cursor_x, max(0, window.width - 1))
        row = min(window.cursor_y, max(0, window.height - 1))
        text = self._typed[: max(0, window.width - column)]
        out.append(self._terminal.move_xy(left + column, top + row))
        out.append(self._render([(Style.INPUT, text)]))

        return (left + column + len(text), top + row)

    def _paint_buffer(
        self, window: TextBufferWindow, out: list[str]
    ) -> tuple[int, int] | None:
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

        for index in range(height):
            out.append(self._terminal.move_xy(left, top + index))
            line = visible[index - offset] if 0 <= index - offset < len(visible) else []
            out.append(self._render(line))
            out.append(" " * max(0, window.width - len(plain(line))))

        if more:
            out.append(self._terminal.move_xy(left, top + height - 1))
            out.append(self._dressed(MORE_PROMPT, Style.ALERT))
            out.append(" " * max(0, window.width - len(MORE_PROMPT)))

            return (left + len(MORE_PROMPT), top + height - 1)

        if not typing or not visible:
            return None

        return (left + len(plain(visible[-1])), top + height - 1)

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

    def _render(self, line: "Iterable[Segment]") -> str:
        """Turn styled segments into a string of dressed text.

        The wrapper keys segments by whatever it was given; this
        display only ever gives it style numbers, so the key comes
        back as the int it went in as.
        """

        return "".join(self._dressed(text, cast("int", style)) for style, text in line)

    def _dressed(self, text: str, style: int) -> str:
        """One run of text wearing its style's sequences."""

        names = ATTRIBUTES.get(style, ())

        if not names:
            return text

        dress = "".join(getattr(self._terminal, name) for name in names)

        return dress + text + self._terminal.normal

    def retire(self) -> None:
        """Leave the cursor under the story, for the shell's prompt.

        The session's last words stay on the glass; whatever the
        caller prints next lands on a fresh line below them instead
        of somewhere mid-screen.
        """

        self._out(self._terminal.move_xy(0, self.size()[1] - 1) + "\n")

    # -- timers --------------------------------------------------------------

    def set_timer(self, millisecs: int) -> None:
        """Ask for timer events every so often; zero stops them."""

        self.timer.set(millisecs)

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

        return self._key()

    def _key(self) -> int | None:
        """Wait for a keystroke; None if a timer fired first.

        A key pressed while text is waiting turns the page instead
        of reaching the game -- which is the whole point of the
        pause, and why every input path goes through here.
        """

        while True:
            code = self._translated(self.timer.timeout())

            if code is not None:
                if self._turn_page():
                    continue

                return code

            if self.timer.due():
                self.post(Event(EventType.TIMER))

                return None

    def _translated(self, timeout: float | None) -> int | None:
        """One terminal read as a Glk code; None for nothing usable.

        Named special keys become their Glk keycodes; unnamed
        single characters become themselves, control characters
        translated. An expired timeout and an unmapped escape
        sequence are both nothing usable.
        """

        with self._terminal.cbreak():
            key = self._terminal.inkey(timeout)

        name = getattr(key, "name", None)

        if name in KEYNAMES:
            return KEYNAMES[name]

        character = str(key)

        if len(character) != 1:
            return None

        code = ord(character)

        return _CONTROL_KEYS.get(code, code)

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
        """Ask for a filename on the bottom line of the screen."""

        del usage

        verb = "Load from" if fmode == FileMode.READ else "Save to"
        prompt = f"{verb} which file? "
        width, height = self.size()
        # glkterm forces every window to the end before a prompt
        # like this one, so the player is answering a question
        # rather than fighting a pager for the keyboard.
        self._catch_up()
        saved, self._typed = self._typed, ""
        saved_window, self._typing = self._typing, None

        try:
            while True:
                text = self._typed[: max(0, width - len(prompt) - 1)]
                line = (prompt + text).ljust(width - 1)
                self._out(self._terminal.move_xy(0, height - 1) + line)
                self._out(self._terminal.move_xy(len(prompt) + len(text), height - 1))

                code = self._key()

                if code is None:
                    # A timer during a file prompt is not an event.
                    continue

                if code == KeyCode.RETURN:
                    return self._typed.strip() or None

                if code == KeyCode.ESCAPE:
                    return None

                self._edit(code, width)
        finally:
            self._typed, self._typing = saved, saved_window
            self._repaint()

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
            # A terminal is monospaced throughout.
            return 0

        if hint in (HINT_INDENTATION, HINT_PARA_INDENTATION):
            return 0

        return None


def _grouped(row: list[str], styles: list[int]) -> list[Segment]:
    """Collapse a grid row's per-cell styles into runs."""

    segments: list[tuple[int, str]] = []

    for index, character in enumerate(row):
        style = styles[index] if index < len(styles) else Style.NORMAL

        if segments and segments[-1][0] == style:
            segments[-1] = (style, segments[-1][1] + character)
        else:
            segments.append((style, character))

    return list(segments)


def _stdout_write(text: str) -> None:
    """Write straight through to the terminal, unbuffered."""

    sys.stdout.write(text)
    sys.stdout.flush()
