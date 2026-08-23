"""A pygame-windowed display for Glk: the glass speaks Glulx.

The painted spine -- tree walk, wrappers, pager, line editor,
timer, speaker -- lives in voxam.glulx.glk.painted; this display
supplies the window specifics. It rides the same Glass sliver the
Z-Machine's graphics frontend drives -- the protocol from
voxam.glass -- so a test drives the whole display with a stub and
no window ever opens in continuous integration.

The glass is cell-addressed, and for now every Glk measure stays
in character cells: the default 1x1 metrics make each size
conversion a no-op, exactly as at the terminal. Pixel metrics
arrive with graphics windows, which is the next road stop -- along
with the mouse, whose clicks the glass already hears but this
display does not yet claim, so a stray click is swallowed rather
than delivered to a game that never asked.

The window echoes nothing on its own: Glk does the echoing into
the window once a line is accepted, and until then the half-typed
line is drawn by the spine, with a block caret painted where the
next character will land -- a window has no hardware cursor to
park the way a terminal does.
"""

from typing import TYPE_CHECKING, cast

from voxam.errors import GlulxSessionEnd
from voxam.glass import INK_DEFAULT, PAPER_DEFAULT, open_pygame_glass
from voxam.glulx.glk.objects import KeyCode
from voxam.glulx.glk.painted import ATTRIBUTES, PaintedFrontend
from voxam.speaker import Speaker

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from voxam.glass import Glass
    from voxam.glulx.glk.wrap import Segment

# The §3.8-translated characters the glass's key() answers with, as
# the Glk keycodes they mean (Glk: Character Input) -- one alphabet
# shared with the Z-Machine's key seam, so one recorded <up>
# presses up on either machine.
KEY_CODES: dict[str, int] = {
    "\n": KeyCode.RETURN,
    "\x7f": KeyCode.DELETE,
    "\x1b": KeyCode.ESCAPE,
    "\x81": KeyCode.UP,
    "\x82": KeyCode.DOWN,
    "\x83": KeyCode.LEFT,
    "\x84": KeyCode.RIGHT,
    # The function keys, \x85 through \x90 in §3.8's numbering.
    **{
        chr(0x84 + number): getattr(KeyCode, f"FUNC{number}") for number in range(1, 13)
    },
}

# The character a click travels as in §10.3's eyes. This display
# does not claim the mouse yet, so a click is nothing usable -- it
# waits for the graphics road stop.
_CLICK = "\xfe"

# The window badge a Glulx session wears: the packaged glulx.ico,
# where a Z-Machine story wears its numbered z<version>.ico.
BADGE = "glulx"


class GlassFrontend(PaintedFrontend):
    """Paints the Glk window tree across a pygame window.

    The glass is injectable, the same arrangement the Z-Machine's
    graphics frontend tests by: a stub answers geometry and
    keystrokes, and the painted runs land in a list instead of a
    live window.
    """

    def __init__(  # noqa: PLR0913 -- one seat per session concern
        self,
        glass: "Glass | None" = None,
        *,
        standard: tuple[int, int] | None = None,
        zoom: float | None = None,
        speaker: Speaker | None = None,
        on_line: "Callable[[str, int], None] | None" = None,
        on_key: "Callable[[int], None] | None" = None,
    ) -> None:
        """Stand over a glass, a real pygame window by default.

        Args:
            glass: The window to paint on; None opens a real
                pygame one, which is where a missing graphics
                extra raises its ImportError.
            standard: The Blorb's Reso standard window size, so
                the opened window keeps the art's proportions
                (Blorb: The Resolution Chunk).
            zoom: The desktop fraction the opened window fills;
                None keeps the classic 80 by 24.
            speaker: The audio device; None claims no sound,
                honestly.
            on_line: The line seam a recording rides.
            on_key: The keystroke seam a recording rides.
        """

        if glass is None:
            glass = open_pygame_glass(standard, BADGE, zoom)

        self._glass = glass

        super().__init__(speaker=speaker, on_line=on_line, on_key=on_key)

    def size(self) -> tuple[int, int]:
        """The glass's grid, measured in cells."""

        return (self._glass.columns, self._glass.lines)

    def _begin(self) -> None:
        """Nothing to gather: runs paint straight onto the surface."""

    def _place(self, x: int, y: int, line: "Iterable[Segment]") -> None:
        column = x

        for style, text in line:
            if not text:
                continue

            names = ATTRIBUTES.get(cast("int", style), ())
            ink, paper = (
                (PAPER_DEFAULT, INK_DEFAULT)
                if "reverse" in names
                else (INK_DEFAULT, PAPER_DEFAULT)
            )

            self._glass.paint(
                y + 1,
                column + 1,
                text,
                ink,
                paper,
                bold="bold" in names,
                italic="italic" in names,
                graphics=False,
            )

            column += len(text)

    def _finish(self, cursor: tuple[int, int] | None) -> None:
        if cursor is not None and cursor[0] < self._glass.columns:
            # The block caret: a reversed space where the next
            # character will land, since a window has no hardware
            # cursor of its own to park there.
            self._glass.paint(
                cursor[1] + 1,
                cursor[0] + 1,
                " ",
                PAPER_DEFAULT,
                INK_DEFAULT,
                bold=False,
                italic=False,
                graphics=False,
            )

        self._glass.present()

    def _translated(self, timeout: float | None) -> int | None:
        """One glass read as a Glk code; None for nothing usable.

        The glass answers in §3.8's alphabet already: named keys as
        their code characters, ordinary typing as itself. The close
        button ends the session the way an exhausted input stream
        does.

        Raises:
            GlulxSessionEnd: When the window is closed.
        """

        try:
            character = self._glass.key(timeout)
        except EOFError:
            raise GlulxSessionEnd from None

        if character is None or character == _CLICK:
            return None

        code = KEY_CODES.get(character)

        if code is not None:
            return code

        return ord(character)
