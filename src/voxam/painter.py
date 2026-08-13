"""The blessed frontend: the screen model painted onto a terminal.

The model in voxam.screen decides everything -- where each character
lands, what it wears, what scrolled -- and this painter's whole job
is to repaint the rows the model reports damaged, then park the
terminal cursor where the model says the game's cursor stands. The
division keeps the painter too thin to hide bugs: anything worth
testing lives in the model, and the golden-grid suite already holds
it to §8.

The terminal itself arrives through the `blessed` package, the
optional extra the frontend is named for. Only a sliver of it is
used -- geometry, cursor movement, and style sequences -- and that
sliver is a Protocol, so tests drive the painter with a stub and no
terminal at all.
"""

import sys
from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Protocol, cast

from voxam.frontend import Status
from voxam.screen import (
    BOLD,
    ITALIC,
    REVERSE,
    Cell,
    ScreenModel,
)

# Special keys arrive from blessed with names; §3.8.2.2 gives the
# input-only ZSCII characters they mean. Anything unnamed passes
# through as the character it already is.
KEY_CHARACTERS = {
    "KEY_ENTER": "\n",
    "KEY_BACKSPACE": "\x7f",
    "KEY_DELETE": "\x7f",
    "KEY_ESCAPE": "\x1b",
}

# The §8.3.1 colour codes the painter can mix, named as blessed
# knows them. Code 1 is the terminal's own default and needs no
# sequence at all.
COLOUR_NAMES = {
    2: "black",
    3: "red",
    4: "green",
    5: "yellow",
    6: "blue",
    7: "magenta",
    8: "cyan",
    9: "white",
}
DEFAULT_COLOUR = 1

# A screen without an answer for its size -- a pipe, a dumb TTY --
# paints as the classic 80 by 24 glass.
FALLBACK_COLUMNS = 80
FALLBACK_LINES = 24


class Terminal(Protocol):
    """The sliver of a blessed Terminal the painter uses.

    Attributes:
        width: The terminal's width in characters, 0 when unknown.
        height: The terminal's height in lines, 0 when unknown.
        normal: The sequence restoring default style and colour.
        reverse: The sequence starting reverse video.
        bold: The sequence starting bold type.
        italic: The sequence starting italic type.
    """

    width: int
    height: int
    normal: str
    reverse: str
    bold: str
    italic: str

    def move_xy(self, x: int, y: int) -> str:
        """The sequence moving the cursor to (x, y), zero-based."""

    def cbreak(self) -> AbstractContextManager[object]:
        """A context in which keystrokes arrive raw, one at a time."""

    def inkey(self) -> object:
        """One keystroke: a str-like, with a .name for special keys."""


class ScreenFrontend:
    """A frontend that keeps a screen model and paints it live.

    Every Frontend operation updates the model first; the damaged
    rows are then redrawn in place. The capability flags tell the
    header the truth this frontend makes true: a status line, a
    splittable screen, and the §8.7.1 styles.
    """

    has_status_line = True
    has_screen_splitting = True
    has_bold = True
    has_italic = True
    has_fixed_pitch = True
    has_timed_input = True
    has_sounds = False

    def __init__(
        self,
        version: int,
        terminal: Terminal | None = None,
        out: Callable[[str], None] | None = None,
        read: Callable[[], str] | None = None,
    ) -> None:
        """Wrap a terminal around a fresh screen model.

        Args:
            version: The story version whose §8 rules the model
                follows.
            terminal: The terminal to paint on; None builds a real
                blessed Terminal.
            out: Where escape sequences and text go; None writes to
                standard output.
            read: Where typed lines come from; None reads standard
                input.
        """

        if terminal is None:
            # Imported here so the module loads without the extra;
            # only building a real terminal needs blessed itself.
            import blessed  # noqa: PLC0415

            terminal = cast("Terminal", blessed.Terminal())

        self._terminal = terminal
        self._out = out if out is not None else _stdout_write
        self._read = read if read is not None else input
        self.screen_columns = terminal.width or FALLBACK_COLUMNS
        self.screen_lines = terminal.height or FALLBACK_LINES
        self._model = ScreenModel(
            columns=self.screen_columns, lines=self.screen_lines, version=version
        )

    @property
    def model(self) -> ScreenModel:
        """The screen model this painter keeps faithful."""

        return self._model

    def write(self, text: str) -> None:
        """Print story text through the model, then repaint."""

        self._model.write(text)
        self._repaint()

    def show_status(self, status: Status) -> None:
        """Draw the Version 3 status line (§8.2)."""

        self._model.show_status(status)
        self._repaint()

    def set_style(self, style: int) -> None:
        """Change the style for text that follows (§8.7.1)."""

        self._model.set_style(style)

    def set_colour(self, foreground: int, background: int) -> None:
        """Change the colours for text that follows (§8.3.1)."""

        self._model.set_colour(foreground, background)

    def erase_window(self, window: int) -> None:
        """Erase a window to background (§8.7.3.2)."""

        self._model.erase_window(window)
        self._repaint()

    def erase_line(self) -> None:
        """Erase from the cursor to the end of the line (§8.7.3.4)."""

        self._model.erase_line()
        self._repaint()

    def split_window(self, lines: int) -> None:
        """Resize the upper window (§8.7.2.1)."""

        self._model.split_window(lines)
        self._repaint()

    def set_window(self, window: int) -> None:
        """Select the window taking the next printing (§8.7.2)."""

        self._model.set_window(window)
        self._repaint()

    def set_cursor(self, line: int, column: int) -> None:
        """Move the upper window's cursor (§8.7.2.3.1)."""

        self._model.set_cursor(line, column)
        self._repaint()

    def set_buffering(self, buffered: bool) -> None:
        """Turn lower-window word wrapping on or off (§15 buffer_mode)."""

        self._model.set_buffering(buffered)

    def bleep(self, number: int) -> None:  # noqa: ARG002
        """Ring the terminal bell: one bell serves both bleeps (§9)."""

        self._out("\a")

    def read_key(self) -> str:
        """Read one raw keystroke at the model's cursor.

        Special keys translate to their §3.8.2.2 input characters;
        unnamed keys pass through as themselves. Keystrokes are not
        echoed -- §15 read_char leaves any echoing to the game --
        and empty reads simply wait for a real one.
        """

        self._park()

        while True:
            with self._terminal.cbreak():
                key = self._terminal.inkey()

            name = getattr(key, "name", None)

            if name in KEY_CHARACTERS:
                return KEY_CHARACTERS[name]

            character = str(key)

            # Multi-character escape sequences -- arrows and friends
            # with no §3.8.2.2 mapping yet -- are not keystrokes the
            # story can hear; wait for one it can.
            if len(character) == 1:
                return character

    def read_line(self) -> str:
        """Read one typed line at the model's cursor.

        The terminal's own echo shows the typing as it happens; the
        line is then written through the model so the grid agrees
        with the glass, newline included.
        """

        self._park()
        line = self._read()
        self._model.write(line + "\n")
        self._repaint()

        return line

    def _repaint(self) -> None:
        """Redraw every damaged row, then park the cursor."""

        for row in self._model.sweep():
            self._paint_row(row)

        self._park()

    def _paint_row(self, row: int) -> None:
        """Redraw one row from the model's cells."""

        pieces = [self._terminal.move_xy(0, row - 1)]
        dress = None

        for column in range(1, self._model.columns + 1):
            cell = self._model.cell(row, column)
            wanted = (cell.style, cell.foreground, cell.background)

            if wanted != dress:
                pieces.append(self._sequences(cell))
                dress = wanted

            pieces.append(cell.character)

        pieces.append(self._terminal.normal)
        self._out("".join(pieces))

    def _sequences(self, cell: Cell) -> str:
        """The style and colour sequences dressing one cell."""

        pieces = [self._terminal.normal]

        if cell.style & REVERSE:
            pieces.append(self._terminal.reverse)

        if cell.style & BOLD:
            pieces.append(self._terminal.bold)

        if cell.style & ITALIC:
            pieces.append(self._terminal.italic)

        if cell.foreground in COLOUR_NAMES:
            pieces.append(str(getattr(self._terminal, COLOUR_NAMES[cell.foreground])))

        if cell.background in COLOUR_NAMES:
            pieces.append(
                str(getattr(self._terminal, "on_" + COLOUR_NAMES[cell.background]))
            )

        return "".join(pieces)

    def _park(self) -> None:
        """Put the terminal cursor where the model's cursor stands."""

        row, column = self._model.cursor
        self._out(self._terminal.move_xy(column - 1, row - 1))


def _stdout_write(text: str) -> None:
    """Write straight through to the terminal, unbuffered."""

    sys.stdout.write(text)
    sys.stdout.flush()
