"""A stdio display, in the manner of cheapglk.

Text buffer windows stream to the output as their contents
accumulate. Text grid windows are drawn as a block whenever they
change, which is what an Inform status line amounts to on a
terminal that cannot address the cursor. Input is a line off the
input stream.

No cursor control, no styles, no partial redraw: this is the
minimum viable Glk, the display glulxercise needs and a piped
session can drive. Everything richer belongs to the painted
displays, voxam.glulx.glk.terminal first among them.
"""

import shutil
import sys
from collections.abc import Callable
from typing import TextIO

from voxam.errors import GlulxSessionEnd
from voxam.glulx.glk.frontend import Frontend
from voxam.glulx.glk.objects import (
    FileMode,
    KeyCode,
    PairWindow,
    TextBufferWindow,
    TextGridWindow,
    Window,
)

DEFAULT_SIZE = (80, 24)

# The status-line divider never grows past a sensible width, even
# on a very wide terminal.
DIVIDER_LIMIT = 60


class StdioFrontend(Frontend):
    """A display over two text streams.

    The streams are injectable, so a test or a script drives this
    as easily as a terminal does.
    """

    echoes_input = True

    def __init__(
        self,
        output: TextIO | None = None,
        input_stream: TextIO | None = None,
        *,
        size: tuple[int, int] | None = None,
        input_source: Callable[[], str] | None = None,
        witness: Callable[[str], None] | None = None,
    ) -> None:
        """Stand over streams, stdout and stdin by default.

        An input source replaces the stream for reading -- the
        acceptance harness's replay callable slots in here, its
        EOFError meaning the script ran dry. A witness receives
        every run of buffer text as it renders, which is where the
        refusal watch listens.
        """

        self.output = output if output is not None else sys.stdout
        self.input = input_stream if input_stream is not None else sys.stdin
        self._source = input_source
        self._witness = witness
        self._size = size
        # Grids are redrawn only when they change, by window
        # identity.
        self._grids: dict[int, list[str]] = {}

    def size(self) -> tuple[int, int]:
        """The terminal's own measure, unless one was chosen."""

        if self._size is not None:
            return self._size

        columns, lines = shutil.get_terminal_size(DEFAULT_SIZE)

        return (columns, lines)

    def flush(self, root: Window | None) -> None:
        """Render what changed and push it out."""

        if root is not None:
            self._render(root)

        self.output.flush()

    def _render(self, window: Window) -> None:
        """Walk the tree in visual order, drawing what shows.

        Visual order rather than tree order, so a status line
        split off above its buffer prints above it.
        """

        if isinstance(window, PairWindow):
            for child in sorted(
                (window.child1, window.child2),
                key=lambda held: (held.bbox[1], held.bbox[0]),
            ):
                self._render(child)
        elif isinstance(window, TextGridWindow):
            self._render_grid(window)
        elif isinstance(window, TextBufferWindow):
            # take_text drains the window, so each run of output
            # prints exactly once however often we are flushed.
            text = window.take_text()

            if text:
                self.output.write(text)

                if self._witness is not None:
                    self._witness(text)

    def _render_grid(self, window: TextGridWindow) -> None:
        """Draw a grid as a block, only when its contents moved."""

        rows = [row.rstrip() for row in window.rows()]

        if not any(rows):
            return

        if self._grids.get(id(window)) == rows:
            return

        self._grids[id(window)] = rows

        for row in rows:
            self.output.write(row + "\n")

        self.output.write("-" * min(self.size()[0], DIVIDER_LIMIT) + "\n")

    def read_line(self, _window: Window, maxlen: int) -> tuple[str, int]:
        """A line off the input, cut to what the buffer holds."""

        line = self._readline()

        return line[:maxlen], 0

    def read_char(self, _window: Window) -> int:
        """One keystroke: the first character of a line.

        The input is line-buffered, so this is the same compromise
        cheapglk makes -- and a bare Return reads as the Return
        keycode, which is what "press any key" prompts expect.
        """

        line = self._readline()

        return ord(line[0]) if line else KeyCode.RETURN

    def prompt_file(self, _usage: int, fmode: int) -> str | None:
        """Ask for a filename in the stream; empty cancels."""

        verb = "Load from" if fmode == FileMode.READ else "Save to"

        self.output.write(f"{verb} which file? ")

        try:
            name = self._readline().strip()
        except GlulxSessionEnd:
            return None

        return name or None

    def _readline(self) -> str:
        """One line, flushed first; end of input ends the session.

        Raises:
            GlulxSessionEnd: At end of input -- the session is
                over, not broken.
        """

        self.output.flush()

        if self._source is not None:
            try:
                return self._source()
            except EOFError:
                raise GlulxSessionEnd from None

        line = self.input.readline()

        if line == "":
            raise GlulxSessionEnd

        return line.rstrip("\r\n")
