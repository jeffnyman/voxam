"""A full-screen terminal display, in the manner of glkterm.

The painted spine -- tree walk, wrappers, pager, line editor,
timer, speaker -- lives in voxam.glulx.glk.painted; this display
supplies the terminal specifics. It rides the same blessed sliver
the Z-Machine's painter does: the Terminal protocol from
voxam.painter, so a test drives the whole display with a stub and
no terminal at all.

The terminal is in cbreak mode while reading, so it echoes
nothing: Glk does the echoing into the window once a line is
accepted, and until then the half-typed line is drawn by the
spine, as part of the layout but not yet part of the window.
"""

import sys
from typing import TYPE_CHECKING, cast

from voxam.frontend import keystroke, widened
from voxam.glulx.glk.objects import KeyCode
from voxam.glulx.glk.painted import ATTRIBUTES, PaintedFrontend
from voxam.painter import FALLBACK_COLUMNS, FALLBACK_LINES, Terminal
from voxam.speaker import Speaker

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from voxam.glulx.glk.wrap import Segment

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


class TerminalFrontend(PaintedFrontend):
    """Paints the Glk window tree across the whole terminal.

    The terminal and the output seam are injectable, the same
    arrangement the Z-Machine painter tests by: a stub terminal
    answers geometry and keystrokes, and the escape sequences land
    in a list instead of a live glass.
    """

    def __init__(  # noqa: PLR0913 -- one seam per session concern
        self,
        terminal: Terminal | None = None,
        out: "Callable[[str], None] | None" = None,
        *,
        size: tuple[int, int] | None = None,
        speaker: Speaker | None = None,
        on_line: "Callable[[str, int], None] | None" = None,
        on_key: "Callable[[int], None] | None" = None,
    ) -> None:
        """Stand over a terminal, a real blessed one by default."""

        if terminal is None:
            # Imported here because the blessed extra is optional:
            # the stdio display must keep working without it.
            import blessed  # noqa: PLC0415

            terminal = cast("Terminal", widened(blessed.Terminal()))

        self._terminal = terminal
        self._out = out if out is not None else _stdout_write
        self._size = size
        # The frame being gathered: pieces accumulate here and
        # write to the terminal as one, so a repaint never shows
        # half-done.
        self._frame: list[str] = []

        super().__init__(speaker=speaker, on_line=on_line, on_key=on_key)

    def size(self) -> tuple[int, int]:
        """The terminal's own measure, unless one was chosen."""

        if self._size is not None:
            return self._size

        return (
            self._terminal.width or FALLBACK_COLUMNS,
            self._terminal.height or FALLBACK_LINES,
        )

    def _begin(self) -> None:
        self._frame = []

    def _place(self, x: int, y: int, line: "Iterable[Segment]") -> None:
        self._frame.append(self._terminal.move_xy(x, y))
        self._frame.append(self._render(line))

    def _finish(self, cursor: tuple[int, int] | None) -> None:
        # Park the cursor where input is going, or out of the way
        # at the bottom if none is.
        self._frame.append(self._terminal.move_xy(*(cursor or (0, self.size()[1] - 1))))
        self._out("".join(self._frame))

    def _render(self, line: "Iterable[Segment]") -> str:
        """Turn styled segments into a string of dressed text.

        The wrapper keys segments by whatever it was given; the
        spine only ever gives it (style, link) pairs, so the key
        comes back as the pair it went in as.
        """

        return "".join(
            self._dressed(text, cast("tuple[int, int]", key)) for key, text in line
        )

    def _dressed(self, text: str, key: tuple[int, int]) -> str:
        """One run of text wearing its style's sequences.

        A link dresses as its style alone: the Terminal protocol
        carries no underline, and the terminal claims no link
        selection anyway -- writing links is legal everywhere,
        showing them off is the window's claim (Glk: Hyperlinks).
        """

        style, _ = key
        names = ATTRIBUTES.get(style, ())

        if not names:
            return text

        dress = "".join(getattr(self._terminal, name) for name in names)

        return dress + text + self._terminal.normal

    def _translated(self, timeout: float | None) -> int | None:
        """One terminal read as a Glk code; None for nothing usable.

        Named special keys become their Glk keycodes; unnamed
        single characters become themselves, control characters
        translated. An expired timeout and an unmapped escape
        sequence are both nothing usable.
        """

        with self._terminal.cbreak():
            key = keystroke(self._terminal, timeout)

        name = getattr(key, "name", None)

        if name in KEYNAMES:
            return KEYNAMES[name]

        character = str(key)

        if len(character) != 1:
            return None

        code = ord(character)

        return _CONTROL_KEYS.get(code, code)

    def retire(self) -> None:
        """Leave the cursor under the story, for the shell's prompt.

        The session's last words stay on the glass; whatever the
        caller prints next lands on a fresh line below them instead
        of somewhere mid-screen.
        """

        self._out(self._terminal.move_xy(0, self.size()[1] - 1) + "\n")


def _stdout_write(text: str) -> None:
    """Write straight through to the terminal, unbuffered."""

    sys.stdout.write(text)
    sys.stdout.flush()
