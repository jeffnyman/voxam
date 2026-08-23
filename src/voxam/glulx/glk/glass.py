"""A pygame-windowed display for Glk: the glass speaks Glulx.

The painted spine -- tree walk, wrappers, pager, line editor,
timer, speaker -- lives in voxam.glulx.glk.painted; this display
supplies the window specifics. It rides the same Glass sliver the
Z-Machine's graphics frontend drives -- the protocol from
voxam.glass -- so a test drives the whole display with a stub and
no window ever opens in continuous integration.

The display's unit is the real pixel: the window tree is arranged
over the glass's pixel grid, the metrics carry the font cell so a
text window still answers its size in characters, and a graphics
window's size is honestly its box (Glk: Graphics Windows). The
graphics claim is true here -- canvases open, fill and erase in
their own pixels, and persist between repaints, because their
pixels are the game's work and painting over is only text's way
of erasing. And the mouse is claimed: a click lands in whichever
armed grid or canvas it hit, translated to that window's own
units and posted as the event glk_select delivers -- while a
click nothing asked for is still swallowed, as every interpreter
swallows it.

The window echoes nothing on its own: Glk does the echoing into
the window once a line is accepted, and until then the half-typed
line is drawn by the spine, with a block caret painted where the
next character will land -- a window has no hardware cursor to
park the way a terminal does.
"""

from typing import TYPE_CHECKING, cast

from voxam.errors import GlulxSessionEnd, PNGError
from voxam.glass import INK_DEFAULT, PAPER_DEFAULT, layered, open_pygame_glass
from voxam.glulx.glk.objects import (
    Event,
    EventType,
    GraphicsWindow,
    KeyCode,
    Metrics,
    TextBufferWindow,
    TextGridWindow,
    Window,
)
from voxam.glulx.glk.painted import ATTRIBUTES, PaintedFrontend
from voxam.png import decode
from voxam.speaker import Speaker

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from voxam.glass import Glass
    from voxam.glulx.glk.resources import ImageInfo
    from voxam.glulx.glk.wrap import Segment
    from voxam.png import Picture

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

# The characters a click travels as in §10.3's eyes, single and
# double alike -- Glk knows only clicks, so a fast pair at the
# window is simply two mouse events (Glk: Mouse Input Events).
# The position itself waits on the glass's click() until asked.
_CLICKS = frozenset({"\xfe", "\xfd"})

# A fresh canvas's background, until the game chooses another:
# "The initial background color of each window is white" (Glk:
# Graphics in Graphics Windows).
_WHITE = (255, 255, 255)

# The ink a hyperlink wears: the blue every reader already knows
# means "click here". The Terminal protocol carries no underline,
# so color alone is the dress.
LINK_INK = (0, 102, 204)


def _rgb(color: int) -> tuple[int, int, int]:
    """A Glk 0x00RRGGBB color as an RGB triple (Glk: Graphics)."""

    return ((color >> 16) & 0xFF, (color >> 8) & 0xFF, color & 0xFF)


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

    # A real window draws in real pixels, so the graphics claim is
    # true here and canvases open (Glk: Graphics Windows).
    graphics = True
    # A real window has a real pointer, so grids and canvases can
    # carry a click (Glk: Mouse Input Events).
    mouse_input = True
    # And the pointer selects links: a click on a linked run in an
    # armed text window delivers its value (Glk: Accepting
    # Hyperlink Events).
    hyperlink_input = True

    def __init__(  # noqa: PLR0913 -- one seat per session concern
        self,
        glass: "Glass | None" = None,
        *,
        standard: tuple[int, int] | None = None,
        zoom: float | None = None,
        speaker: Speaker | None = None,
        on_line: "Callable[[str, int], None] | None" = None,
        on_key: "Callable[[int], None] | None" = None,
        on_click: "Callable[[int, int], None] | None" = None,
        on_link: "Callable[[int], None] | None" = None,
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
            on_click: The click seam, hearing each delivered
                click as the window-relative coordinates the game
                itself was told.
            on_link: The hyperlink seam, hearing each delivered
                selection as the link value the game itself was
                told.
        """

        if glass is None:
            glass = open_pygame_glass(standard, BADGE, zoom)

        self._glass = glass
        # The font cell in real pixels: what lets a text window
        # answer its size in characters while the tree is arranged
        # over the pixel grid.
        self.metrics = Metrics(glass.cell_width, glass.cell_height)
        # Each canvas's background color, once a game chooses one
        # (Glk: Graphics in Graphics Windows).
        self._backgrounds: dict[Window, tuple[int, int, int]] = {}
        # Each Pict's decoded pixels, once per number -- including
        # the refusals, so a JPEG costs one attempt, not one per
        # draw.
        self._pictures: dict[int, Picture | None] = {}
        self._on_click = on_click
        self._on_link = on_link
        # Where each linked run stands on the glass this frame:
        # (left, top, right, bottom, value) in 0-based pixels,
        # rebuilt with every repaint -- what turns a click into a
        # selection.
        self._links: list[tuple[int, int, int, int, int]] = []

        super().__init__(speaker=speaker, on_line=on_line, on_key=on_key)

    def size(self) -> tuple[int, int]:
        """The whole glass, measured in its real pixels."""

        return (
            self._glass.columns * self._glass.cell_width,
            self._glass.lines * self._glass.cell_height,
        )

    def _begin(self) -> None:
        """Start a frame: the link map is repainted with the text."""

        self._links = []

    def _place(self, x: int, y: int, line: "Iterable[Segment]") -> None:
        column = x

        for key, text in line:
            if not text:
                continue

            style, link = cast("tuple[int, int]", key)
            names = ATTRIBUTES.get(style, ())

            if "reverse" in names:
                ink, paper = PAPER_DEFAULT, INK_DEFAULT
            elif link:
                ink, paper = LINK_INK, PAPER_DEFAULT
            else:
                ink, paper = INK_DEFAULT, PAPER_DEFAULT

            self._glass.text(
                y + 1,
                column + 1,
                text,
                ink,
                paper,
                bold="bold" in names,
                italic="italic" in names,
                graphics=False,
            )

            width = len(text) * self._glass.cell_width

            if link:
                self._links.append(
                    (column, y, column + width, y + self._glass.cell_height, link)
                )

            column += width

    def _finish(self, cursor: tuple[int, int] | None) -> None:
        if cursor is not None and cursor[0] < self.size()[0]:
            # The block caret: one filled cell where the next
            # character will land, since a window has no hardware
            # cursor of its own to park there.
            self._glass.fill(
                cursor[1] + 1,
                cursor[0] + 1,
                self._glass.cell_height,
                self._glass.cell_width,
                INK_DEFAULT,
            )

        self._glass.present()

    # -- graphics (Glk: Graphics in Graphics Windows) --------------------------

    def set_background_color(self, window: Window, color: int) -> None:
        """Remember the color; only future clears and erases wear it."""

        self._backgrounds[window] = _rgb(color)

    def erase_rect(
        self, window: Window, left: int, top: int, width: int, height: int
    ) -> None:
        """Erase a rectangle to the canvas's background color."""

        self._fill(window, left, top, width, height, self._background(window))

    def fill_rect(  # noqa: PLR0913, PLR0917 -- the rectangle, colored
        self, window: Window, color: int, left: int, top: int, width: int, height: int
    ) -> None:
        """Fill a rectangle with a color of the game's own."""

        self._settled(window)
        self._fill(window, left, top, width, height, _rgb(color))

    def draw_image(  # noqa: PLR0913, PLR0917 -- the six values of image_draw_scaled
        self,
        window: Window,
        image: "ImageInfo",
        val1: int,
        val2: int,
        width: int,
        height: int,
    ) -> bool:
        """Draw a Pict onto a canvas, scaled and clipped.

        Only graphics windows draw here, as the gestalt already
        told the game (Glk: Testing for Graphics Capabilities),
        and only PNG resources: no JPEG decoder is aboard, so a
        JPEG Pict is refused whole rather than half-drawn. val1
        and val2 are the upper-left corner in window pixels,
        signed, and "it is legitimate for part of the image to
        fall outside the window; the excess is not drawn" (Glk:
        Graphics in Graphics Windows).
        """

        if not isinstance(window, GraphicsWindow):
            return False

        picture = self._picture(image)

        if picture is None:
            return False

        self._settled(window)

        if width <= 0 or height <= 0:
            # Scaled to nothing is drawn as nothing.
            return True

        box_left, box_top, box_right, box_bottom = window.bbox
        left = box_left + val1
        top = box_top + val2
        x0 = max(left, box_left)
        y0 = max(top, box_top)
        x1 = min(left + width, box_right)
        y1 = min(top + height, box_bottom)

        if x1 <= x0 or y1 <= y0:
            # Fully off the canvas: legitimate, and nothing shows.
            return True

        rows = layered(picture)

        if (x0, y0, x1, y1) != (left, top, left + width, top + height):
            # The overhang is cut away by sampling only the
            # visible pixels, each destination pixel reading its
            # nearest-neighbour source; the glass then blits the
            # slice one-to-one instead of scaling.
            rows = tuple(
                tuple(
                    rows[(y - top) * picture.height // height][
                        (x - left) * picture.width // width
                    ]
                    for x in range(x0, x1)
                )
                for y in range(y0, y1)
            )

        self._glass.draw(rows, y0 + 1, x0 + 1, (x1 - x0, y1 - y0))

        return True

    def _picture(self, image: "ImageInfo") -> "Picture | None":
        """The decoded pixels, once per Pict number.

        Whatever cannot decode -- a JPEG, a corrupt PNG -- is
        remembered as nothing, so a refusal costs one attempt.
        """

        if image.number not in self._pictures:
            try:
                self._pictures[image.number] = decode(image.data)
            except PNGError:
                self._pictures[image.number] = None

        return self._pictures[image.number]

    def _settled(self, window: Window) -> None:
        """Consume a pending clear before new paint lands.

        glk_window_clear only raises the flag, and a repaint
        honors it later -- but paint arriving in between must land
        on the cleared canvas, not be erased under it, so the
        clear happens now. An erase needs no such care: it paints
        the same background the clear would.
        """

        if window.pending_clear:
            window.pending_clear = False
            self.erase_rect(window, 0, 0, window.width, window.height)

    def _background(self, window: Window) -> tuple[int, int, int]:
        """The canvas's background: white until the game says else."""

        return self._backgrounds.get(window, _WHITE)

    def _fill(  # noqa: PLR0913, PLR0917 -- the rectangle, colored
        self,
        window: Window,
        left: int,
        top: int,
        width: int,
        height: int,
        colour: tuple[int, int, int],
    ) -> None:
        """Paint a window-relative rectangle, clipped to its box.

        "It is legitimate for part of the rectangle to fall
        outside the window" (Glk: Graphics in Graphics Windows),
        so whatever falls outside simply is not drawn -- and the
        arguments are signed, so the overhang may be on any edge.
        """

        box_left, box_top, box_right, box_bottom = window.bbox
        x0 = max(box_left + left, box_left)
        y0 = max(box_top + top, box_top)
        x1 = min(box_left + left + width, box_right)
        y1 = min(box_top + top + height, box_bottom)

        if x1 <= x0 or y1 <= y0:
            return

        self._glass.fill(y0 + 1, x0 + 1, y1 - y0, x1 - x0, colour)

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

        if character in _CLICKS:
            self._clicked()

            return None

        if character is None:
            return None

        code = KEY_CODES.get(character)

        if code is not None:
            return code

        return ord(character)

    def _clicked(self) -> None:
        """Deliver the glass's click to whichever armed window it hit.

        A click on a linked run in a text window with a hyperlink
        request delivers the link's value (Glk: Accepting
        Hyperlink Events); otherwise a grid or a canvas with a
        mouse request hears the click in its own coordinates --
        cells in a grid, pixels on a canvas (Glk: Mouse Input
        Events). A click nothing asked for is swallowed, as every
        interpreter swallows it. Between two armed windows the
        position decides; the grammar cannot spell which window a
        recorded input chose, so a replay leans on the request
        that is standing when it arrives.
        """

        position = self._glass.click()

        if position is None:
            return

        # The glass counts its pixels 1-based; the boxes are 0-based.
        x, y = position[0] - 1, position[1] - 1
        windows = self.glk.windows if self.glk is not None else []

        for window in windows:
            if not window.hyperlink_request or not isinstance(
                window, TextBufferWindow | TextGridWindow
            ):
                continue

            left, top, right, bottom = window.bbox

            if not (left <= x < right and top <= y < bottom):
                continue

            value = self._link_at(x, y)

            if not value:
                continue

            window.hyperlink_request = False
            self.post(Event(EventType.HYPERLINK, window, value, 0))

            if self._on_link is not None:
                self._on_link(value)

            return

        for window in windows:
            if not window.mouse_request or not isinstance(
                window, TextGridWindow | GraphicsWindow
            ):
                continue

            left, top, right, bottom = window.bbox

            if not (left <= x < right and top <= y < bottom):
                continue

            if isinstance(window, TextGridWindow):
                cell = window.metrics
                val1 = int((x - left) / cell.width)
                val2 = int((y - top) / cell.height)
            else:
                val1, val2 = x - left, y - top

            window.mouse_request = False
            self.post(Event(EventType.MOUSE_INPUT, window, val1, val2))

            if self._on_click is not None:
                self._on_click(val1, val2)

            return

    def _link_at(self, x: int, y: int) -> int:
        """The link value painted at a pixel, or zero for none."""

        for left, top, right, bottom, value in self._links:
            if left <= x < right and top <= y < bottom:
                return value

        return 0

    def read_mouse(self, window: Window) -> tuple[int, int] | None:
        """Wait at the glass; the click itself travels as an event.

        _clicked posts the click with its window and coordinates
        already resolved, so this wait only blocks until something
        happens: a posted click or timer answers None, and
        glk_select comes back round to find the event. A keystroke
        while only the mouse is wanted means nothing, and the wait
        resumes.
        """

        del window

        self._await()

        return None

    def read_hyperlink(self, window: Window) -> int | None:
        """Wait at the glass; the selection travels as an event.

        The same wait as read_mouse: _clicked posts the hyperlink
        event with its value already resolved off the painted link
        map, and this only blocks until something happens.
        """

        del window

        self._await()

        return None

    def _await(self) -> None:
        """Wait out keystrokes until an interruption ends the wait."""

        while self._key() is not None:
            pass
