"""A windowed frontend, built on pygame-ce: the third glass.

The screen model in voxam.screen still decides everything; this
frontend, like the terminal painter, only repaints the rows the
model reports damaged -- blitting glyphs into fixed cells instead
of emitting escape sequences. The window itself arrives through
the `pygame-ce` package, the `graphics` optional extra, and only
through the sliver the Glass protocol names, so every piece of the
machinery is driven by a stub in tests and no window ever opens in
continuous integration.

Several decisions here are inherited scars from prior art (a
pygame-ce Glk frontend of Jeff's): pygame prints its greeting
banner to stdout unless told not to *before* import -- and stdout
is where a piped transcript goes; a bold or italic face may only
be used if every glyph steps by exactly the regular face's cell,
or columns creep into one another (macOS fakes Menlo's bold one
pixel wide); and the event pump sleeps between polls so a wait is
not a spin.
"""

import os
from collections.abc import Callable, Sequence
from itertools import groupby
from typing import Any, Protocol, cast

from voxam.font3 import FONT_3_BITMAPS, PIXELS, ROWS
from voxam.frontend import GRAPHICS_FONT, Status
from voxam.painter import (
    IDLE_HEARTBEAT,
    INPUT_ONLY_FIRST,
    INPUT_ONLY_LAST,
    RUB_OUT_KEYS,
)
from voxam.png import Picture
from voxam.screen import BOLD, ITALIC, REVERSE, Cell, ScreenModel
from voxam.speaker import Speaker

# The classic glass: 80 by 24 cells, the size every recording and
# header claim already assumes.
GLASS_COLUMNS = 80
GLASS_LINES = 24

# The §8.3.1 colour codes as RGB, code 1 being the interpreter's
# default ink and paper: white on black, the machine's home look.
INK_DEFAULT = (255, 255, 255)
PAPER_DEFAULT = (0, 0, 0)
COLOUR_VALUES = {
    2: (0, 0, 0),
    3: (204, 0, 0),
    4: (0, 204, 0),
    5: (204, 204, 0),
    6: (0, 0, 204),
    7: (204, 0, 204),
    8: (0, 204, 204),
    9: (255, 255, 255),
}


class Glass(Protocol):
    """The sliver of a pygame window the frontend drives.

    Attributes:
        columns: The glass's width in cells.
        lines: The glass's height in cells.
        cell_width: One cell's width in real pixels -- the font
            metric a Version 6 story hears as its unit (§8.4.2).
        cell_height: One cell's height in real pixels.
    """

    columns: int
    lines: int
    cell_width: int
    cell_height: int

    def paint(  # noqa: PLR0913 -- a run carries its whole dress
        self,
        row: int,
        column: int,
        text: str,
        ink: tuple[int, int, int],
        paper: tuple[int, int, int],
        *,
        bold: bool,
        italic: bool,
        graphics: bool,
    ) -> None:
        """Blit a run of same-dressed characters into their cells.

        A graphics run is in the §16 character graphics font: the
        glass draws the spec's own 8x8 bitmaps instead of glyphs
        from a face.
        """

    def present(self) -> None:
        """Put the painted frame on screen."""

    def key(self, timeout: float | None) -> str | None:
        """One keypress, already §3.8-translated; None on expiry.

        The window's close button raises EOFError -- ending the
        session the same way an exhausted input stream does.
        """

    def picture(self, rows: Sequence[Sequence[tuple[int, int, int]]]) -> None:
        """Show a cover picture centred until present() paints over."""


class GraphicsFrontend:
    """A frontend that keeps a screen model and blits it to a window.

    The same shape as the terminal painter: every operation updates
    the model first, then the damaged rows redraw. The capability
    claims are the window's truth -- real styles, real colours, the
    §16 font as the spec's own pixels.
    """

    has_status_line = True
    has_screen_splitting = True
    has_bold = True
    has_italic = True
    has_fixed_pitch = True
    has_timed_input = True
    has_character_graphics = True
    has_colours = True

    def __init__(
        self,
        version: int,
        glass: Glass | None = None,
        speaker: Speaker | None = None,
    ) -> None:
        """Wrap a window around a fresh screen model.

        Args:
            version: The story version whose §8 rules the model
                follows.
            glass: The window to blit on; None opens a real pygame
                one.
            speaker: The audio device for the sound seam; None
                claims no sound, honestly.
        """

        if glass is None:
            glass = open_pygame_glass()

        self._glass = glass
        self._speaker = speaker
        self.has_sounds = speaker is not None
        self.idle: Callable[[], None] | None = None
        self.screen_columns = glass.columns
        self.screen_lines = glass.lines
        # The glass measures its cells in real pixels, and those
        # metrics are the units a Version 6 story does its §8.8
        # arithmetic in -- the first frontend that can retire the
        # character glasses' 1-by-1 font (§8.4.2).
        self.font_width = glass.cell_width
        self.font_height = glass.cell_height
        self._model = ScreenModel(
            columns=glass.columns, lines=glass.lines, version=version
        )

    @property
    def model(self) -> ScreenModel:
        """The screen model this window keeps faithful."""

        return self._model

    def write(self, text: str) -> None:
        """Print story text through the model, then repaint."""

        self._model.write(text)
        self._repaint()

    def write_rectangle(self, rows: Sequence[str]) -> None:
        """Stamp a §15 print_table rectangle through the model."""

        self._model.write_rectangle(rows)
        self._repaint()

    def show_status(self, status: Status) -> None:
        """Draw the §8.2 status line through the model."""

        self._model.show_status(status)
        self._repaint()

    def set_style(self, style: int) -> None:
        """Change the §8.7.1 style for text that follows."""

        self._model.set_style(style)

    def set_font(self, font: int) -> None:
        """Change the §8.1.2 font for text that follows."""

        self._model.set_font(font)

    def set_colour(self, foreground: int, background: int) -> None:
        """Change the §8.3.1 colours for text that follows."""

        self._model.set_colour(foreground, background)

    def erase_window(self, window: int) -> None:
        """Erase a window to its background, repainting (§8.7)."""

        self._model.erase_window(window)
        self._repaint()

    def erase_line(self) -> None:
        """Erase from the cursor to the end of the line (§8.7.3.4)."""

        self._model.erase_line()
        self._repaint()

    def set_buffering(self, buffered: bool) -> None:
        """Flow the §7.2 buffering flag into the model."""

        self._model.set_buffering(buffered)

    def split_window(self, lines: int) -> None:
        """Resize the upper window (§8.7.2)."""

        self._model.split_window(lines)
        self._repaint()

    def set_window(self, window: int) -> None:
        """Select the window that receives text (§8.7.2)."""

        self._model.set_window(window)

    def set_cursor(self, line: int, column: int) -> None:
        """Move the upper window's cursor (§8.7.2.3.1)."""

        self._model.set_cursor(line, column)

    def cursor_position(self) -> tuple[int, int]:
        """The model's own answer for get_cursor (§8.7.2.3.2)."""

        return self._model.get_cursor()

    def bleep(self, number: int) -> None:
        """Drop the bleep: a window has no bell to ring (§9).

        The speaker seam is where this frontend's real sound
        lives; a bleep synthesizer can join it someday.
        """

    def play_sound(self, number: int, volume: int, repeats: int | None) -> bool:
        """Hand a sampled sound to the speaker (§9.4)."""

        return self._speaker is not None and self._speaker.play(number, volume, repeats)

    def stop_sound(self, number: int | None) -> None:
        """Stop a sound, or all of them when None (§9.4)."""

        if self._speaker is not None:
            self._speaker.stop(number)

    def sound_playing(self) -> bool:
        """Whether the speaker is still sounding (§9 remarks)."""

        return self._speaker is not None and self._speaker.playing()

    def sound_finished(self) -> bool:
        """Whether a sound just ended naturally (§9.4.4)."""

        return self._speaker is not None and self._speaker.finished()

    def wait_for_sound(self) -> None:
        """Let the playing sound finish a cycle (§9 remarks)."""

        if self._speaker is not None:
            self._speaker.wait()

    def read_key(self, timeout: float | None = None) -> str | None:
        """Read one raw keystroke (§15 read_char).

        Without a timeout the wait is infinite but attentive --
        the idle heartbeat fires exactly as it does at the
        terminal; with one, an expired wait answers None for the
        machine's wall-clock interrupts.
        """

        while True:
            key = self._waited_key() if timeout is None else self._glass.key(timeout)

            if key is not None:
                return key

            if timeout is not None:
                return None

    def read_line(self) -> str:
        """Read one line of raw typing, echoed through the model.

        The same line editor the terminal painter runs: backspace
        rubs out, escape and the §3.8.4 codes are waited out, and
        every visible change to the window is the model's doing.
        """

        typed: list[str] = []

        while True:
            key = self._waited_key()

            if key is None or key == "\x1b" or self._input_only(key):
                continue

            if key == "\n":
                self._model.write("\n")
                self._repaint()

                return "".join(typed)

            if key in RUB_OUT_KEYS:
                if typed:
                    typed.pop()
                    self._model.rub_out()
                    self._repaint()

                continue

            typed.append(key)
            self._model.write(key)
            self._repaint()

    def clear(self) -> None:
        """Blit the model's every row, blank or not."""

        for row in range(1, self._model.lines + 1):
            self._paint_row(row)

        self._glass.present()

    def show_frontispiece(self, picture: Picture, *, pixels: bool = False) -> None:
        """Show a cover picture until a key is pressed, then clear.

        A window draws the real bitmap -- the pixels flag is the
        terminal's sixel question, and every window already has
        pixels. Infocom's own interpreters opened this way: the
        art, a keypress, the story.
        """

        del pixels

        self._glass.picture(picture.rows)
        self.read_key()
        self.clear()

    def _waited_key(self) -> str | None:
        """One read of an infinite wait, attentive while it lasts."""

        if self.idle is None:
            return self._glass.key(None)

        key = self._glass.key(IDLE_HEARTBEAT)

        if key is None:
            self.idle()

        return key

    @staticmethod
    def _input_only(key: str) -> bool:
        """Whether a key is one of the §3.8.4 input-only codes."""

        return INPUT_ONLY_FIRST <= key <= INPUT_ONLY_LAST

    def _repaint(self) -> None:
        """Blit every damaged row, then put the frame on screen."""

        rows = list(self._model.sweep())

        for row in rows:
            self._paint_row(row)

        if rows:
            self._glass.present()

    def _paint_row(self, row: int) -> None:
        """Blit one row from the model's cells, in same-dress runs."""

        cells = [
            _appearance(self._model.cell(row, column))
            for column in range(1, self._model.columns + 1)
        ]
        column = 1

        for dress, grouped in groupby(cells, key=lambda pair: pair[1]):
            text = "".join(character for character, _ in grouped)
            ink, paper, bold, italic, graphics = dress

            self._glass.paint(
                row,
                column,
                text,
                ink,
                paper,
                bold=bold,
                italic=italic,
                graphics=graphics,
            )

            column += len(text)


def _appearance(
    cell: Cell,
) -> tuple[str, tuple[tuple[int, int, int], tuple[int, int, int], bool, bool, bool]]:
    """One cell's character and dress, reverse video pre-swapped.

    Cells in the §16 character graphics font keep their raw
    character and mark the dress graphics: the glass draws the
    spec's own bitmaps for them, so no Unicode stand-in is asked
    to approximate a pixel, and the reverse twins at 123 to 126
    arrive as the inverted bitmaps the spec drew for them.
    """

    style = cell.style
    ink = COLOUR_VALUES.get(cell.foreground, INK_DEFAULT)
    paper = COLOUR_VALUES.get(cell.background, PAPER_DEFAULT)

    if style & REVERSE:
        ink, paper = paper, ink

    return cell.character, (
        ink,
        paper,
        bool(style & BOLD),
        bool(style & ITALIC),
        cell.font == GRAPHICS_FONT,
    )


def open_pygame_glass() -> Glass:
    """Open a real pygame window, the graphics extra permitting.

    The pygame import happens here, not at module top -- and the
    banner-hiding variable is set before it, because pygame greets
    on stdout, where a piped transcript goes.
    """

    os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

    import pygame  # noqa: PLC0415

    return cast("Glass", _PygameGlass(pygame))


class _PygameGlass:
    """The real window: fixed cells, cached glyphs, a patient pump.

    Faces beyond regular are kept only when every probe glyph
    steps by exactly the regular face's cell -- a face that steps
    wider creeps out of its columns, which is the macOS fake-bold
    defect the prior art measured. A misfit face falls back to
    the regular one; reverse video and colour still distinguish
    what needed distinguishing.
    """

    def __init__(self, pygame: object) -> None:
        module: Any = pygame

        self._pygame: Any = module
        self.columns = GLASS_COLUMNS
        self.lines = GLASS_LINES

        module.init()

        self._fonts = _fitted_faces(module)
        regular: Any = self._fonts[(False, False)]
        self.cell_width = int(regular.metrics("M")[0][4])
        self.cell_height = int(regular.get_linesize())
        self._screen: Any = module.display.set_mode(
            (self.columns * self.cell_width, self.lines * self.cell_height)
        )

        module.display.set_caption("Voxam")

        self._keys = _key_characters(module)
        self._tiles: dict[
            tuple[str, tuple[int, int, int], tuple[int, int, int]], Any
        ] = {}

    def paint(  # noqa: PLR0913 -- a run carries its whole dress
        self,
        row: int,
        column: int,
        text: str,
        ink: tuple[int, int, int],
        paper: tuple[int, int, int],
        *,
        bold: bool,
        italic: bool,
        graphics: bool,
    ) -> None:
        font: Any = self._fonts.get((bold, italic), self._fonts[(False, False)])
        x = (column - 1) * self.cell_width
        y = (row - 1) * self.cell_height
        width = len(text) * self.cell_width

        self._screen.fill(paper, (x, y, width, self.cell_height))

        for offset, character in enumerate(text):
            if character == " ":
                continue

            if graphics and ord(character) in FONT_3_BITMAPS:
                glyph = self._tile(character, ink, paper)
            else:
                glyph = font.render(character, True, ink)

            self._screen.blit(glyph, (x + offset * self.cell_width, y))

    def _tile(
        self, character: str, ink: tuple[int, int, int], paper: tuple[int, int, int]
    ) -> object:
        """One §16 bitmap stretched to the cell, cached by dress.

        The stretch is deliberately edge-to-edge: font 3's shapes
        are built to tile, so a map corridor drawn in one cell
        must meet its neighbour with no seam. Pygame's scale is
        nearest-neighbour, which keeps the pixels square-shouldered
        the way a 1988 monitor drew them.
        """

        cached = self._tiles.get((character, ink, paper))

        if cached is None:
            module = self._pygame
            tile: Any = module.Surface((PIXELS, ROWS))

            for y, bits in enumerate(FONT_3_BITMAPS[ord(character)]):
                for x in range(PIXELS):
                    lit = bits & (0x80 >> x)

                    tile.set_at((x, y), ink if lit else paper)

            cached = module.transform.scale(tile, (self.cell_width, self.cell_height))
            self._tiles[(character, ink, paper)] = cached

        return cached

    def present(self) -> None:
        self._pygame.display.flip()

    def key(self, timeout: float | None) -> str | None:
        module = self._pygame
        clock_start = module.time.get_ticks()

        while True:
            for event in module.event.get():
                if event.type == module.QUIT:
                    raise EOFError

                if event.type == module.KEYDOWN:
                    named = self._keys.get(event.key)

                    if named is not None:
                        return named

                    typed = str(event.unicode)

                    if typed and typed.isprintable():
                        return typed

            if timeout is not None:
                elapsed = module.time.get_ticks() - clock_start

                if elapsed >= timeout * 1000:
                    return None

            module.time.wait(10)

    def picture(self, rows: Sequence[Sequence[tuple[int, int, int]]]) -> None:
        module = self._pygame
        height = len(rows)
        width = len(rows[0]) if height else 0

        if not width:
            return

        surface = module.Surface((width, height))

        for y, row in enumerate(rows):
            for x, colour in enumerate(row):
                surface.set_at((x, y), colour)

        screen = self._screen
        bounds = screen.get_size()
        scale = max(1, min(bounds[0] // width, bounds[1] // height))
        scaled = module.transform.scale(surface, (width * scale, height * scale))

        screen.fill(PAPER_DEFAULT)
        screen.blit(
            scaled,
            (
                (bounds[0] - width * scale) // 2,
                (bounds[1] - height * scale) // 2,
            ),
        )
        self.present()


# The monospace families tried when no bundled font exists yet, in
# the prior art's order of preference.
FONT_FAMILIES = "menlo,dejavusansmono,consolas,couriernew,liberationmono,monospace"
FONT_SIZE = 18

# Glyphs whose advance every kept face must match exactly.
FIT_PROBE = "Mi1"


def _fitted_faces(module: object) -> dict[tuple[bool, bool], object]:
    """The faces whose glyphs step exactly one cell; misfits dropped."""

    pygame: Any = module
    sysfont = pygame.font.SysFont
    regular = sysfont(FONT_FAMILIES, FONT_SIZE)
    cell = regular.metrics("M")[0][4]
    faces: dict[tuple[bool, bool], object] = {(False, False): regular}

    for bold in (False, True):
        for italic in (False, True):
            if not bold and not italic:
                continue

            face = sysfont(FONT_FAMILIES, FONT_SIZE, bold=bold, italic=italic)

            if all(face.metrics(probe)[0][4] == cell for probe in FIT_PROBE):
                faces[(bold, italic)] = face

    return faces


def _key_characters(module: object) -> dict[int, str]:
    """Pygame's key constants as the §3.8 characters they mean."""

    pygame: Any = module

    keys = {
        "K_RETURN": "\n",
        "K_KP_ENTER": "\n",
        "K_BACKSPACE": "\x7f",
        "K_DELETE": "\x7f",
        "K_ESCAPE": "\x1b",
        "K_UP": "\x81",
        "K_DOWN": "\x82",
        "K_LEFT": "\x83",
        "K_RIGHT": "\x84",
    }
    functions = {f"K_F{number}": chr(0x84 + number) for number in range(1, 13)}

    return {
        int(getattr(pygame, name)): character
        for name, character in {**keys, **functions}.items()
    }
