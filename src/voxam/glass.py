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

import io
import os
from collections.abc import Callable, Sequence
from fractions import Fraction
from importlib import resources
from itertools import groupby
from time import monotonic
from typing import Any, Protocol, cast

from voxam.editor import EXPIRED, LineEditor, read_line_edited
from voxam.font3 import FONT_3_BITMAPS, PIXELS, ROWS
from voxam.frontend import GRAPHICS_FONT, Status
from voxam.gallery import Gallery
from voxam.painter import IDLE_HEARTBEAT, MORE_PROMPT
from voxam.png import OPAQUE, Picture
from voxam.screen import (
    BOLD,
    ERASE_KEEP_SPLIT,
    ERASE_UNSPLIT,
    ITALIC,
    REVERSE,
    Cell,
    ScreenModel,
)
from voxam.speaker import Speaker
from voxam.stage import FillPaint, Paint, StageModel, TextPaint

# The classic glass: 80 by 24 cells, the size every recording and
# header claim already assumes.
GLASS_COLUMNS = 80
GLASS_LINES = 24

# Version 6 alone gets the §8.8 stage; every other version keeps
# the two-window screen model.
STAGE_VERSION = 6

# Every story version has its own window badge in the package's
# icons directory, z1.ico through z8.ico.
BADGED_VERSIONS = range(1, 9)


# One cell as the glass paints it: its character and its dress of
# ink, paper, bold, italic, and the graphics-font flag.
Appearance = tuple[
    str, tuple[tuple[int, int, int], tuple[int, int, int], bool, bool, bool]
]

# The §8.3.1 colour codes as RGB, code 1 being the interpreter's
# default ink and paper: white on black, the machine's home look.
# The greys at 10-12 are the Version 6 additions, their values
# scaled from the spec's own true-colour equivalents.
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
    10: (181, 181, 181),
    11: (139, 139, 139),
    12: (90, 90, 90),
}

# §8.3.1's colour code -1: the colour of the pixel under the
# cursor, Version 6 only. A sampled colour is not one of the
# standard set, so it lives in the book under a dynamic code of 16
# or higher -- the range §8.3.5.2 reserves for exactly this.
UNDER_CURSOR = -1
FIRST_SAMPLED = 16

# What makes two clicks one double: the second lands within this
# many milliseconds and this many pixels of the first. The
# Standard names the input code (§10.3.3) but not the timing, so
# the timing is the desktop convention.
DOUBLE_CLICK_MILLIS = 500
DOUBLE_CLICK_REACH = 4


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

    def text(  # noqa: PLR0913 -- a run carries its whole dress
        self,
        line: int,
        column: int,
        characters: str,
        ink: tuple[int, int, int],
        paper: tuple[int, int, int],
        *,
        bold: bool,
        italic: bool,
        graphics: bool,
    ) -> None:
        """Blit characters with their top left at a pixel position.

        The position is 1-based screen pixels -- §8.8's own units
        on a measuring glass -- so Version 6 text lands exactly
        where its window was placed, not on the nearest cell.
        Each character paints its own exact background rectangle.
        """

    def fill(
        self,
        line: int,
        column: int,
        height: int,
        width: int,
        colour: tuple[int, int, int],
    ) -> None:
        """Paint a pixel rectangle a solid colour (§8.8.5)."""

    def shift(
        self,
        line: int,
        column: int,
        height: int,
        width: int,
        rise: int,
    ) -> None:
        """Slide a pixel rectangle's contents vertically (§8.8.3.6).

        Positive rise moves the pixels up, negative down; the
        exposed strip is the caller's to fill.
        """

    def sample(self, line: int, column: int) -> tuple[int, int, int]:
        """The colour of one pixel, at a 1-based pixel position.

        This is how §8.3.1's colour -1 reads the glass: the pixel
        under the cursor, as it stands painted.
        """

    def present(self) -> None:
        """Put the painted frame on screen."""

    def key(self, timeout: float | None) -> str | None:
        """One keypress, already §3.8-translated; None on expiry.

        The window's close button raises EOFError -- ending the
        session the same way an exhausted input stream does. A
        mouse click arrives as the character for its §10.3 input
        code, with the position kept for click().
        """

    def click(self) -> tuple[int, int] | None:
        """The last click's (x, y), in 1-based window pixels."""

    def picture(self, rows: Sequence[Sequence[tuple[int, int, int]]]) -> None:
        """Show a cover picture centred until present() paints over."""

    def photograph(
        self, data: bytes
    ) -> Sequence[Sequence[tuple[int, int, int]]] | None:
        """Decode photographic bytes -- a JPEG -- to pixel rows.

        The interpreter decodes PNG itself; JPEG it hands to the
        window, whose pygame carries the decoders the interpreter
        does not. Bytes nothing aboard can decode answer None, and
        the picture is refused honestly.
        """

    def draw(
        self,
        rows: Sequence[Sequence[tuple[int, ...]]],
        line: int,
        column: int,
        size: tuple[int, int],
    ) -> None:
        """Blit pixel rows with their top left at (line, column).

        The position is 1-based screen pixels, §8.8.1's own
        origin; size is the on-screen (width, height) the rows
        stretch to -- the Reso scaling, already decided. A pixel
        may carry a fourth value: its alpha, 0 fully transparent
        through 255 opaque, blended over whatever is already
        drawn -- how Version 6 chrome layers over its scene art
        with holes, and how a translucent Glulx picture settles
        onto its canvas. The pixels stay until text or another
        picture is painted over them, which is exactly the §8.8.3
        rule that nothing belongs to a window once plotted.
        """


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
    # A window has a real pointer: clicks arrive as §10.3's input
    # codes, so the mouse request bit stays set.
    has_mouse = True

    def __init__(  # noqa: PLR0913 -- one seat per optional collaborator
        self,
        version: int,
        glass: Glass | None = None,
        speaker: Speaker | None = None,
        gallery: Gallery | None = None,
        standard: tuple[int, int] | None = None,
        *,
        zoom: float | None = None,
    ) -> None:
        """Wrap a window around a fresh screen model.

        Args:
            version: The story version whose §8 rules the model
                follows.
            glass: The window to blit on; None opens a real pygame
                one.
            speaker: The audio device for the sound seam; None
                claims no sound, honestly.
            gallery: The Blorb's art for the picture seam; None
                claims no pictures, honestly. An empty gallery
                stands in behind the scenes so no picture method
                ever has to ask whether one hangs.
            standard: The Reso chunk's standard window size, the
                shape the game's art was laid out for. The spec
                offers it as a hint for choosing a window size
                (Blorb: The Resolution Chunk), and it matters:
                Arthur aligns its rails under its banner's ends,
                which only nest inside the side regions when the
                screen keeps the standard proportions.
            zoom: The fraction of the desktop the window should
                fill, satisfied by growing the grid -- more rows
                and columns of the same type; None keeps the
                classic 80 by 24.
        """

        if glass is None:
            glass = open_pygame_glass(standard, version, zoom)

        self._glass = glass
        self._speaker = speaker
        self._gallery = gallery if gallery is not None else Gallery({}, 0)
        self.has_sounds = speaker is not None
        self.has_pictures = gallery is not None
        self.idle: Callable[[], None] | None = None
        self.screen_columns = glass.columns
        self.screen_lines = glass.lines
        # The glass measures its cells in real pixels, and those
        # metrics are the units a Version 6 story does its §8.8
        # arithmetic in -- the first frontend that can retire the
        # character glasses' 1-by-1 font (§8.4.2).
        self.font_width = glass.cell_width
        self.font_height = glass.cell_height
        # A Version 6 session plays on the §8.8 stage -- eight
        # placeable windows on one grid -- and the has_stage claim
        # tells the machine to forward window geometry here.
        self.has_stage = version == STAGE_VERSION
        self._stage = (
            StageModel(glass.columns, glass.lines, glass.cell_width, glass.cell_height)
            if self.has_stage
            else None
        )
        self._model: ScreenModel | StageModel = (
            self._stage
            if self._stage is not None
            else ScreenModel(columns=glass.columns, lines=glass.lines, version=version)
        )
        self._shadow: dict[int, list[Appearance | None]] = {}
        self._chrome: dict[int, tuple[int, int]] = {}
        self._editor = LineEditor()
        # Whether a timed read left a half-typed line composed: the
        # next line read resumes it instead of starting fresh.
        self._composing = False
        # The input caret: where the underline was last drawn, and
        # whether a read is currently showing one. The v6 stage
        # draws no caret of its own -- its games place and paint
        # their own cursors.
        self._caret: tuple[int, int] | None = None
        self._typing = False
        self._prompt = ""
        # The frontend's colour book: the §8.3.1 codes, joined by
        # a dynamic code (16 and up, §8.3.5.2) for every colour
        # ever sampled off the glass by colour -1.
        self._colours: dict[int, tuple[int, int, int]] = dict(COLOUR_VALUES)
        self._sampled: dict[tuple[int, int, int], int] = {}

        if self._stage is not None:
            self._stage.more = self._pause
        else:
            cast("ScreenModel", self._model).more = self._pause_cells

    @property
    def model(self) -> "ScreenModel | StageModel":
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
        """Change the §8.3.1 colours for text that follows.

        On the stage, colour -1 means the colour of the pixel
        under the cursor (§8.3.1, Version 6 only): the glass is
        brought current and read at the cursor's own position, and
        the sampled colour joins the book under a dynamic code.
        """

        if self._stage is not None:
            foreground = self._resolved(self._stage, foreground)
            background = self._resolved(self._stage, background)

        self._model.set_colour(foreground, background)

    def _resolved(self, stage: StageModel, code: int) -> int:
        """A paintable colour code: sampling stands in for -1."""

        if code != UNDER_CURSOR:
            return code

        # The cursor position first -- asking flushes buffered
        # text into paints -- then the pending paints onto the
        # glass, so the sample reads the screen a player sees.
        line, column = stage.screen_cursor()

        self._settle(stage)

        colour = self._glass.sample(line, column)

        if colour not in self._sampled:
            self._sampled[colour] = FIRST_SAMPLED + len(self._sampled)
            self._colours[self._sampled[colour]] = colour

        return self._sampled[colour]

    def erase_window(self, window: int) -> None:
        """Erase a window to its background, repainting (§8.7, §8.8.5.3).

        On the stage the erased rectangle is also forgotten from
        the shadow: an erasure legitimately paints over any
        picture in its region, and cells whose text did not change
        would otherwise skip repainting and leave ghosts of the
        art behind.
        """

        if window in (ERASE_UNSPLIT, ERASE_KEEP_SPLIT):
            # A whole-screen erasure takes the drawn chrome with
            # it; nothing remains to re-dress.
            self._chrome.clear()

        self._model.erase_window(window)
        self._repaint()

    def place_window(
        self, window: int, line: int, column: int, height: int, width: int
    ) -> None:
        """Place a §8.8 window on the stage, in units (§15).

        Only a Version 6 session has a stage -- the has_stage
        claim says so, and the machine sends geometry nowhere
        else.
        """

        if self._stage is not None:
            self._stage.place_window(window, line, column, height, width)

    def scroll_window(self, window: int, pixels: int) -> None:
        """Scroll a stage window's own rectangle (§8.8.3.6)."""

        if self._stage is not None:
            self._stage.scroll_window(window, pixels)
            self._repaint()

    def set_margins(self, window: int, left: int, right: int) -> None:
        """Set a stage window's margins, in units (§8.8.3.2.1)."""

        if self._stage is not None:
            self._stage.set_margins(window, left, right)

    def set_line_count(self, window: int, count: int) -> None:
        """Set a stage window's [MORE] line count (§8.8.3.2.6)."""

        if self._stage is not None:
            self._stage.set_line_count(window, count)

    def _pause(self, line: int, column: int, foreground: int, background: int) -> None:
        """Hold the scroll behind a [MORE] until a key arrives.

        Everything painted so far goes to the glass first, then
        the prompt appears at the pause position wearing the
        window's own colours in reverse. The key that answers is
        spent, never passed to the story (§8.8.3.2.6) -- and the
        prompt's patch is rebuilt from the stage's grid, because
        the pause can land on freshly flowed text, and a blind
        erase would burn a box over it: Zork Zero's death question
        kept losing its first word that way.
        """

        stage = cast("StageModel", self._stage)
        ink = self._colours.get(foreground, INK_DEFAULT)
        paper = self._colours.get(background, PAPER_DEFAULT)

        self._repaint()
        self._glass.text(
            line,
            column,
            MORE_PROMPT,
            paper,
            ink,
            bold=False,
            italic=False,
            graphics=False,
        )
        self._glass.present()

        while self._waited_key() is None:
            pass

        self._glass.fill(
            line,
            column,
            self.font_height,
            len(MORE_PROMPT) * self.font_width,
            paper,
        )

        row = (line - 1) // self.font_height + 1
        first = (column - 1) // self.font_width + 1

        for offset in range(len(MORE_PROMPT)):
            if first + offset > self.screen_columns:
                break

            covered = stage.cell(row, first + offset)

            if covered.character != " ":
                (
                    character,
                    (
                        cell_ink,
                        cell_paper,
                        bold,
                        italic,
                        graphics,
                    ),
                ) = _appearance(covered, self._colours)

                self._glass.text(
                    line,
                    column + offset * self.font_width,
                    character,
                    cell_ink,
                    cell_paper,
                    bold=bold,
                    italic=italic,
                    graphics=graphics,
                )

        self._glass.present()

    def erase_line(self, pixels: int | None = None) -> None:
        """Erase rightward from the cursor, repainting (§8.8.5.2).

        The pixel width only means anything on the stage; the cell
        model always erases to the end of the line (§8.7.3.4).
        """

        if self._stage is not None:
            self._stage.erase_line(pixels)
        else:
            self._model.erase_line()

        self._repaint()

    def begin_input(self) -> None:
        """Remember the prompt: the line's text left of the cursor.

        On the stage the cursor speaks units, not cells, so the
        prompt snapshot stays empty there until a Version 6 game
        earns the arithmetic.
        """

        if self._stage is not None:
            self._prompt = ""

            return

        model = cast("ScreenModel", self._model)
        row, column = model.cursor
        self._prompt = model.row_text(row)[: column - 1]

    def resume_input(self) -> None:
        """Show the prompt again after a printing interrupt (§15).

        Jigsaw's chapter epigraphs print from a timed read's
        interrupt: without this, the "> " strands above the
        quotation and the player types into a promptless line.
        """

        if self._prompt:
            self.write(self._prompt)

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

    def picture_data(self, number: int) -> tuple[int, int] | None:
        """A picture's height and width in pixels (§15 picture_data).

        The size is Reso-scaled: the Blorb decides how its art
        grows on a roomier screen than its standard window, and
        the answer here must be the drawn truth, because games
        lay out their whole stage from these words (Blorb: The
        Resolution Chunk).
        """

        size = self._gallery.size(number)

        if size is None:
            return None

        height, width = size
        factor = self._factor(number)

        return int(height * factor), int(width * factor)

    def _factor(self, number: int) -> Fraction:
        """One picture's Reso ratio on this glass's screen."""

        return self._gallery.scale(
            number,
            self.screen_columns * self.font_width,
            self.screen_lines * self.font_height,
        )

    def picture_census(self) -> tuple[int, int]:
        """How many pictures hang, and the art's release (§15)."""

        return self._gallery.count, self._gallery.release

    def draw_picture(self, number: int, line: int, column: int) -> None:
        """Blit a picture at a screen pixel position (§15 draw_picture).

        The glass stretches the pixels to their Reso-scaled size
        -- the same size picture_data reported -- and any clear
        pixels stay see-through, so chrome like Arthur's banner
        frames the scene art beneath instead of blotting it out.
        A Rect placard has a size and no pixels: games measure
        and position by it, and drawing it shows nothing -- the
        conforming answer, not a shortfall.

        Adaptive chrome is remembered where it lands; a plot that
        changes the Current Palette re-dresses it in place, the
        way Infocom's interpreters recoloured the screen through
        the hardware palette without replotting (Blorb: The
        Adaptive Palette Chunk).
        """

        serial = self._gallery.serial
        picture = self._gallery.picture(number)

        if picture is None:
            return

        self._blit_picture(number, picture, line, column)

        if number in self._gallery.adaptive:
            self._chrome[number] = (line, column)
        elif self._gallery.serial != serial:
            self._redress()

    def _blit_picture(
        self, number: int, picture: Picture, line: int, column: int
    ) -> None:
        """One picture onto the glass, Reso-scaled and layered."""

        factor = self._factor(number)
        size = (int(picture.width * factor), int(picture.height * factor))

        self._glass.draw(layered(picture), line, column, size)

    def _redress(self) -> None:
        """Re-blit the on-screen chrome in the new Current Palette.

        In its original order, so the layering survives -- and the
        chrome's clear pixels keep the freshly plotted scene
        visible beneath it.
        """

        for number, (line, column) in self._chrome.items():
            # Recorded chrome was drawable when it was recorded,
            # so the gallery always answers.
            picture = cast("Picture", self._gallery.picture(number))

            self._blit_picture(number, picture, line, column)

    def erase_picture(self, number: int, line: int, column: int) -> None:
        """Paint a picture's region to the background (§15 erase_picture).

        The region is the Reso-scaled size picture_data reported,
        painted by stretching a single pixel of the model's
        current background colour -- the nearest truth this glass
        has to "the background colour for the given window" until
        all eight windows render.
        """

        size = self.picture_data(number)

        if size is None:
            return

        height, width = size
        paper = self._colours.get(self._model.background, PAPER_DEFAULT)

        self._glass.draw(((paper,),), line, column, (width, height))

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
        machine's wall-clock interrupts. While the read waits, the
        caret marks where input is going -- which is how a player
        follows Bureaucracy's form as its cursor hops fields.
        """

        self._model.rest()
        self._typing = True
        self._show_caret()

        try:
            while True:
                key = (
                    self._waited_key() if timeout is None else self._glass.key(timeout)
                )

                if key is not None:
                    return key

                if timeout is not None:
                    return None
        finally:
            self._typing = False
            self._hide_caret()

    def click_position(self) -> tuple[int, int] | None:
        """The last mouse click, in the story's own units (§10.3.2).

        A Version 6 story hears window pixels -- its §8.8 units --
        while every earlier version hears character cells, both
        1-based from the top left.
        """

        pixels = self._glass.click()

        if pixels is None:
            return None

        x, y = pixels

        if self._stage is not None:
            return x, y

        return (x - 1) // self.font_width + 1, (y - 1) // self.font_height + 1

    def read_line(self) -> str:
        """Read one line of raw typing, edited and echoed via the model.

        The same line editor the terminal painter runs: backspace
        rubs out, the left and right cursor keys move within the
        line, up and down walk the session's command history, and
        every visible change to the window is the model's doing --
        with the caret showing where the next character lands.
        """

        self._model.rest()
        self._typing = True
        self._show_caret()

        fresh = not self._composing
        self._composing = False

        try:
            line = read_line_edited(
                self._editor, self._model, self._waited_key, self._repaint, fresh=fresh
            )
        finally:
            self._typing = False
            self._hide_caret()

        # The untimed key source never expires, so the line is real.
        return cast("str", line)

    def read_line_until(self, seconds: float) -> str | None:
        """Read a line on the clock, or None when the wait expires.

        The live half of a §15 timed read, twin to the painter's:
        the half-typed line survives between calls, composed in the
        editor and standing in the window, with the caret marking
        where it left off.
        """

        self._model.rest()
        self._typing = True
        self._show_caret()

        deadline = monotonic() + seconds

        def ticking_key() -> str | None:
            remaining = deadline - monotonic()

            if remaining <= 0:
                return EXPIRED

            wait = (
                min(remaining, IDLE_HEARTBEAT) if self.idle is not None else remaining
            )
            key = self._glass.key(wait)

            if key is None and self.idle is not None:
                self.idle()

            return key

        fresh = not self._composing

        try:
            line = read_line_edited(
                self._editor, self._model, ticking_key, self._repaint, fresh=fresh
            )
        finally:
            self._typing = False
            self._hide_caret()

        self._composing = line is None

        return line

    def abandon_input(self) -> None:
        """Erase the half-typed line a terminated timed read leaves."""

        if not self._composing:
            return

        pending = len(self._editor.text)
        self._model.retreat(self._editor.cursor)
        self._model.write(" " * pending)
        self._model.retreat(pending)
        self._editor.begin()
        self._composing = False
        self._repaint()

    def clear(self) -> None:
        """Return the glass to a blank screen after a frontispiece.

        On the stage the pixels themselves are the retained
        screen, so a fill is the whole of it; the cell path blits
        every row afresh, its shadow emptied first, because the
        cover left pixels no cell accounts for.
        """

        if self._stage is not None:
            self._stage.paints()
            self._glass.fill(
                1,
                1,
                self.screen_lines * self.font_height,
                self.screen_columns * self.font_width,
                PAPER_DEFAULT,
            )
            self._glass.present()

            return

        self._shadow.clear()

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

    def _repaint(self) -> None:
        """Carry the model's changes to the glass, then present.

        The stage hands over unit-positioned paints -- text at
        true §8.8 positions, fills, scrolls -- and the glass's
        persistent pixels are the retained screen. The cell model
        instead reports damaged rows, blitted through the shadow
        diff.
        """

        if self._stage is not None:
            if self._settle(self._stage):
                self._glass.present()

            return

        rows = list(self._model.sweep())

        for row in rows:
            self._paint_row(row)

        if rows:
            self._glass.present()

        if self._typing:
            # A repainted row overwrote any caret it held; forget
            # the old drawing so the caret comes back at the
            # cursor's (possibly new) cell.
            if self._caret is not None and self._caret[0] in rows:
                self._caret = None

            self._show_caret()

    def _show_caret(self) -> None:
        """Underline the model's cursor cell so typing has a home.

        The caret is an overlay, not a cell: it draws straight onto
        the glass and marks its cell dirty in the shadow, so the
        next honest repaint of that row wipes it without a trace. A
        standing caret stays where it is -- a timed interrupt
        printing an upper-window clock mid-read must not drag it
        along -- and it re-homes to the cursor exactly when its own
        row repaints, which is what typing does. The v6 stage draws
        no caret -- its games place their own.
        """

        if self._stage is not None or self._caret is not None:
            return

        model = cast("ScreenModel", self._model)
        row, column = model.cursor
        column = min(column, model.columns)

        _character, (ink, _paper, _bold, _italic, _graphics) = _appearance(
            model.cell(row, column), self._colours
        )

        self._glass.fill(
            (row - 1) * self.font_height + self.font_height - 1,
            (column - 1) * self.font_width + 1,
            2,
            self.font_width,
            ink,
        )
        self._glass.present()
        self._shadow.setdefault(row, [None] * model.columns)[column - 1] = None
        self._caret = (row, column)

    def _hide_caret(self) -> None:
        """Take the caret back off the glass, restoring its cell."""

        if self._caret is None:
            return

        row, _column = self._caret
        self._caret = None
        self._paint_row(row)
        self._glass.present()

    def _pause_cells(self) -> None:
        """Hold a screenful behind [MORE] until any key arrives.

        The cell-model twin of the stage's pause: the model calls
        mid-write, so its piled-up damage paints first; the prompt
        overlays the cursor's cell in the window's own colours
        reversed, its cells marked dirty in the shadow; and the
        keypress is spent on the pause, with an honest row repaint
        erasing the prompt.
        """

        model = cast("ScreenModel", self._model)

        for damaged in model.sweep():
            self._paint_row(damaged)

        row, column = model.cursor
        column = min(column, max(model.columns - len(MORE_PROMPT) + 1, 1))
        _character, (ink, paper, _bold, _italic, _graphics) = _appearance(
            model.cell(row, column), self._colours
        )

        self._glass.paint(
            row,
            column,
            MORE_PROMPT,
            paper,
            ink,
            bold=False,
            italic=False,
            graphics=False,
        )
        self._glass.present()

        shadow = self._shadow.setdefault(row, [None] * model.columns)

        for offset in range(len(MORE_PROMPT)):
            shadow[column - 1 + offset] = None

        # A heartbeat expiry answers None so background work can
        # run; only a real key ends the pause.
        while self._waited_key() is None:
            pass

        self._paint_row(row)
        self._glass.present()

    def _settle(self, stage: StageModel) -> bool:
        """Carry the stage's pending paints onto the glass.

        Returns:
            Whether anything was painted.
        """

        paints = stage.paints()

        for paint in paints:
            self._perform(paint)

        stage.sweep()

        return bool(paints)

    def _perform(self, paint: Paint) -> None:
        """Execute one stage paint on the glass, in real pixels."""

        if isinstance(paint, TextPaint):
            character, (ink, paper, bold, italic, graphics) = _appearance(
                paint.cell, self._colours
            )

            self._glass.text(
                paint.line,
                paint.column,
                character,
                ink,
                paper,
                bold=bold,
                italic=italic,
                graphics=graphics,
            )
        elif isinstance(paint, FillPaint):
            self._glass.fill(
                paint.line,
                paint.column,
                paint.height,
                paint.width,
                self._colours.get(paint.background, PAPER_DEFAULT),
            )
        else:
            self._glass.shift(
                paint.line, paint.column, paint.height, paint.width, paint.rise
            )

    def _paint_row(self, row: int) -> None:
        """Blit one row's changed cells, in same-dress runs.

        The shadow is the glass's memory of what every cell last
        showed: only cells that differ repaint. That is what lets
        a drawn picture survive beneath rows of unchanged cells --
        §8.8.3's rule that pixels stay until something is actually
        painted over them.
        """

        cells: list[Appearance] = [
            _appearance(self._model.cell(row, column), self._colours)
            for column in range(1, self._model.columns + 1)
        ]
        shadow = self._shadow.get(row, [None] * self._model.columns)
        column = 1

        for changed, grouped in groupby(
            zip(cells, shadow, strict=True), key=lambda pair: pair[0] != pair[1]
        ):
            block = [appearance for appearance, _ in grouped]

            if changed:
                offset = 0

                for dress, run in groupby(block, key=lambda appearance: appearance[1]):
                    text = "".join(character for character, _ in run)
                    ink, paper, bold, italic, graphics = dress

                    self._glass.paint(
                        row,
                        column + offset,
                        text,
                        ink,
                        paper,
                        bold=bold,
                        italic=italic,
                        graphics=graphics,
                    )

                    offset += len(text)

            column += len(block)

        remembered: list[Appearance | None] = list(cells)
        self._shadow[row] = remembered


def _appearance(
    cell: Cell,
    colours: dict[int, tuple[int, int, int]],
) -> tuple[str, tuple[tuple[int, int, int], tuple[int, int, int], bool, bool, bool]]:
    """One cell's character and dress, reverse video pre-swapped.

    Cells in the §16 character graphics font keep their raw
    character and mark the dress graphics: the glass draws the
    spec's own bitmaps for them, so no Unicode stand-in is asked
    to approximate a pixel, and the reverse twins at 123 to 126
    arrive as the inverted bitmaps the spec drew for them.
    """

    style = cell.style
    ink = colours.get(cell.foreground, INK_DEFAULT)
    paper = colours.get(cell.background, PAPER_DEFAULT)

    if style & REVERSE:
        ink, paper = paper, ink

    return cell.character, (
        ink,
        paper,
        bool(style & BOLD),
        bool(style & ITALIC),
        cell.font == GRAPHICS_FONT,
    )


def layered(picture: Picture) -> Sequence[Sequence[tuple[int, ...]]]:
    """A picture's rows dressed for the glass's own blending.

    A partially see-through picture travels as (red, green, blue,
    alpha) straight colors, blended on blit; one with only holes
    marks each clear pixel (red, green, blue, 0); one with no
    transparency passes its rows unchanged (Blorb: Picture
    Resource Chunks).
    """

    if picture.alpha is not None:
        return tuple(
            tuple(
                pixel if value == OPAQUE else (*pixel, value)
                for pixel, value in zip(row, alpha_row, strict=True)
            )
            for row, alpha_row in zip(picture.rows, picture.alpha, strict=True)
        )

    if picture.clear is None:
        return picture.rows

    return tuple(
        tuple(
            (*pixel, 0) if hole else pixel
            for pixel, hole in zip(row, clear_row, strict=True)
        )
        for row, clear_row in zip(picture.rows, picture.clear, strict=True)
    )


def open_pygame_glass(
    standard: tuple[int, int] | None = None,
    version: int | str = 0,
    zoom: float | None = None,
) -> Glass:
    """Open a real pygame window, the graphics extra permitting.

    The pygame import happens here, not at module top -- and the
    banner-hiding variable is set before it, because pygame greets
    on stdout, where a piped transcript goes.

    Args:
        standard: The art's standard window size, when a Blorb
            declared one; the glass keeps its proportions (Blorb:
            The Resolution Chunk).
        version: The story version, whose numbered badge becomes
            the window's icon -- or a badge named outright, the
            way a Glulx session asks for its own; 0 leaves the
            icon alone.
        zoom: The fraction of the desktop the window should fill,
            satisfied by growing the grid -- more rows and columns
            of the same modest type, a genuinely roomier screen
            whose Elbow Room the Reso arithmetic then fills with
            proportionally grown art (Blorb: The Resolution
            Chunk). None keeps the classic 80 by 24.
    """

    os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

    import pygame  # noqa: PLC0415

    return cast("Glass", _PygameGlass(pygame, standard, version, zoom))


class _PygameGlass:
    """The real window: fixed cells, cached glyphs, a patient pump.

    Faces beyond regular are kept only when every probe glyph
    steps by exactly the regular face's cell -- a face that steps
    wider creeps out of its columns, which is the macOS fake-bold
    defect the prior art measured. A misfit face falls back to
    the regular one; reverse video and colour still distinguish
    what needed distinguishing.
    """

    def __init__(
        self,
        pygame: object,
        standard: tuple[int, int] | None = None,
        version: int | str = 0,
        zoom: float | None = None,
    ) -> None:
        module: Any = pygame

        self._pygame: Any = module

        module.init()
        _badge(module, version)

        self._fonts = _fitted_faces(module)
        regular: Any = self._fonts[(False, False)]
        self.cell_width = int(regular.metrics("M")[0][4])
        self.cell_height = int(regular.get_linesize())

        if zoom is None:
            self.lines = GLASS_LINES
            self.columns = _columns_for(standard, self.cell_width, self.cell_height)
        else:
            self.columns, self.lines = _roomy_grid(module, standard, zoom)

        self._screen: Any = module.display.set_mode(
            (self.columns * self.cell_width, self.lines * self.cell_height)
        )

        module.display.set_caption("Voxam")

        self._keys = _key_characters(module)
        # The window events that mean "the OS blanked me; paint
        # again" -- looked up defensively, since the set has grown
        # across pygame releases.
        self._exposures = {
            getattr(module, name)
            for name in (
                "WINDOWEXPOSED",
                "WINDOWRESTORED",
                "WINDOWSHOWN",
                "VIDEOEXPOSE",
            )
            if hasattr(module, name)
        }
        # A diagnostic witness: with VOXAM_SNAPSHOT set to a file
        # path, every present also saves the surface there -- what
        # the window was GIVEN, captured from inside a live
        # session, for comparing against what it SHOWS.
        self._snapshot = os.environ.get("VOXAM_SNAPSHOT")
        self._click: tuple[int, int] | None = None
        # The last single click, as (ticks, x, y), for hearing the
        # second that makes a double (§10.3.3).
        self._last_click: tuple[int, int, int] | None = None
        self._pasted: list[str] = []
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
        self.text(
            (row - 1) * self.cell_height + 1,
            (column - 1) * self.cell_width + 1,
            text,
            ink,
            paper,
            bold=bold,
            italic=italic,
            graphics=graphics,
        )

    def text(  # noqa: PLR0913 -- a run carries its whole dress
        self,
        line: int,
        column: int,
        characters: str,
        ink: tuple[int, int, int],
        paper: tuple[int, int, int],
        *,
        bold: bool,
        italic: bool,
        graphics: bool,
    ) -> None:
        font: Any = self._fonts.get((bold, italic), self._fonts[(False, False)])
        x = column - 1
        y = line - 1
        width = len(characters) * self.cell_width

        self._screen.fill(paper, (x, y, width, self.cell_height))

        for offset, character in enumerate(characters):
            if character == " ":
                continue

            if graphics and ord(character) in FONT_3_BITMAPS:
                glyph = self._tile(character, ink, paper)
            else:
                glyph = font.render(character, True, ink)

            self._screen.blit(glyph, (x + offset * self.cell_width, y))

    def fill(
        self,
        line: int,
        column: int,
        height: int,
        width: int,
        colour: tuple[int, int, int],
    ) -> None:
        self._screen.fill(colour, (column - 1, line - 1, width, height))

    def shift(
        self,
        line: int,
        column: int,
        height: int,
        width: int,
        rise: int,
    ) -> None:
        region = self._screen.get_rect().clip((column - 1, line - 1, width, height))

        if not region.width or not region.height:
            return

        moved: Any = self._screen.subsurface(region).copy()

        if rise > 0:
            self._screen.blit(
                moved, (region.x, region.y), (0, rise, region.width, region.height)
            )
        else:
            self._screen.blit(
                moved,
                (region.x, region.y - rise),
                (0, 0, region.width, region.height + rise),
            )

    def sample(self, line: int, column: int) -> tuple[int, int, int]:
        colour = self._screen.get_at((column - 1, line - 1))

        return (colour[0], colour[1], colour[2])

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

        if self._snapshot:
            self._pygame.image.save(self._screen, self._snapshot)

    def key(self, timeout: float | None) -> str | None:
        module = self._pygame
        clock_start = module.time.get_ticks()

        while True:
            if self._pasted:
                # Pasted text drains one character per call, so the
                # editor, timed reads, and the recorder all hear it
                # as ordinary typing.
                return self._pasted.pop(0)

            for event in module.event.get():
                if event.type == module.QUIT:
                    raise EOFError

                if event.type in self._exposures:
                    # The OS invalidated the window -- covered,
                    # restored, un-minimized -- and asks for a
                    # repaint. The surface still holds everything
                    # drawn; presenting it again is the whole
                    # repair. Without this, a session waiting at a
                    # prompt shows black after an alt-tab.
                    self.present()

                    continue

                if event.type == module.MOUSEBUTTONDOWN and event.button == 1:
                    # A click is a keypress in §10.3's eyes: 254
                    # travels as its character for a single, 253
                    # for a second click landing fast and close
                    # enough to double (§10.3.3), and the position
                    # waits for click() -- 1-based, as the screen's
                    # pixels are counted (§8.8.1). The first of a
                    # pair always delivers as a single, the way
                    # every desktop counts; a double resets the
                    # run, so a third fast click begins anew.
                    now = module.time.get_ticks()
                    x, y = event.pos[0] + 1, event.pos[1] + 1
                    doubled = self._last_click is not None and (
                        now - self._last_click[0] <= DOUBLE_CLICK_MILLIS
                        and abs(x - self._last_click[1]) <= DOUBLE_CLICK_REACH
                        and abs(y - self._last_click[2]) <= DOUBLE_CLICK_REACH
                    )
                    self._click = (x, y)
                    self._last_click = None if doubled else (now, x, y)

                    return "\xfd" if doubled else "\xfe"

                if event.type == module.KEYDOWN:
                    # The paste chords a desktop expects: Ctrl+V --
                    # Cmd+V through KMOD_META on a Mac -- and the
                    # traditional Shift+Insert.
                    pasting = (
                        event.key == module.K_v
                        and event.mod & (module.KMOD_CTRL | module.KMOD_META)
                    ) or (
                        event.key == module.K_INSERT and event.mod & module.KMOD_SHIFT
                    )

                    if pasting:
                        self._pasted.extend(_pasteable(module))

                        continue

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

    def click(self) -> tuple[int, int] | None:
        return self._click

    def photograph(
        self, data: bytes
    ) -> Sequence[Sequence[tuple[int, int, int]]] | None:
        module = self._pygame

        try:
            surface: Any = module.image.load(io.BytesIO(data))
        except module.error:
            return None

        width, height = surface.get_size()

        def pixel(x: int, y: int) -> tuple[int, int, int]:
            colour = surface.get_at((x, y))

            return (colour[0], colour[1], colour[2])

        return tuple(tuple(pixel(x, y) for x in range(width)) for y in range(height))

    def picture(self, rows: Sequence[Sequence[tuple[int, int, int]]]) -> None:
        surface = self._surface(rows)

        if surface is None:
            return

        module = self._pygame
        height = len(rows)
        width = len(rows[0])
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

    def draw(
        self,
        rows: Sequence[Sequence[tuple[int, ...]]],
        line: int,
        column: int,
        size: tuple[int, int],
    ) -> None:
        surface = self._surface(rows)

        if surface is None:
            return

        scaled = self._pygame.transform.scale(surface, size)

        self._screen.blit(scaled, (column - 1, line - 1))
        self.present()

    def _surface(self, rows: Sequence[Sequence[tuple[int, ...]]]) -> object:
        """Pixel rows as a surface, or None for an empty picture.

        The surface carries per-pixel alpha, so a fourth value
        survives the scale and blends on the blit -- a clear
        pixel letting the screen beneath show through whole, a
        translucent one settling over it.
        """

        height = len(rows)
        width = len(rows[0]) if height else 0

        if not width:
            return None

        module = self._pygame
        surface: Any = module.Surface((width, height), module.SRCALPHA)

        for y, row in enumerate(rows):
            for x, colour in enumerate(row):
                surface.set_at((x, y), colour)

        return surface


def _badge(module: object, version: int | str) -> None:
    """Give the window the story's own icon.

    Each Z-Machine version ships a numbered badge in the package's
    icons directory, and the window wears the one for the story it
    is playing; a badge named outright -- glulx -- is worn as it
    is. Set before the display opens, as pygame prefers.
    """

    if isinstance(version, str):
        name = f"{version}.ico"
    elif version in BADGED_VERSIONS:
        name = f"z{version}.ico"
    else:
        return

    pygame: Any = module

    with resources.as_file(resources.files("voxam") / "icons" / name) as path:
        pygame.display.set_icon(pygame.image.load(str(path)))


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


# The header stores lines and columns in single bytes ($20, $21),
# so no grid dimension may pass 255 whatever the desktop offers.
GRID_CAP = 255


def _columns_for(
    standard: tuple[int, int] | None,
    cell_width: int,
    cell_height: int,
    lines: int = GLASS_LINES,
) -> int:
    """How many columns a grid of this many lines opens with.

    Without a declared standard, the classic 80. With one, the
    window keeps the art's proportions (Blorb: The Resolution
    Chunk): the width follows the standard aspect at the given
    height, so a game's own layout arithmetic -- built for that
    shape -- nests the way its artists drew it.
    """

    if standard is None:
        return GLASS_COLUMNS

    width, height = standard

    return max(round(lines * cell_height * width / (height * cell_width)), 1)


def _roomy_grid(
    module: object, standard: tuple[int, int] | None, zoom: float
) -> tuple[int, int]:
    """The largest grid of classic cells filling the desktop's share.

    Room means more rows and columns of the same modest type --
    the way Infocom's own interpreters used a big monitor -- never
    bigger letters. Version 6 games read the screen's true pixel
    size and lay out accordingly, so every cell added is real room
    for their windows. With a declared standard the grid keeps the
    art's aspect, walking the height down until the width fits;
    the classic 80 by 24 is the floor either way, even on a
    desktop too small for its share to hold it.

    Returns:
        The grid as (columns, lines).
    """

    pygame: Any = module
    desktop_width, desktop_height = pygame.display.get_desktop_sizes()[0]
    face: Any = pygame.font.SysFont(FONT_FAMILIES, FONT_SIZE)
    cell_width = int(face.metrics("M")[0][4])
    cell_height = int(face.get_linesize())
    target_width = desktop_width * zoom
    target_height = desktop_height * zoom

    lines = min(int(target_height // cell_height), GRID_CAP)

    if standard is None:
        columns = min(int(target_width // cell_width), GRID_CAP)

        return (max(columns, GLASS_COLUMNS), max(lines, GLASS_LINES))

    while lines > GLASS_LINES:
        columns = _columns_for(standard, cell_width, cell_height, lines)

        if columns <= GRID_CAP and columns * cell_width <= target_width:
            return (columns, lines)

        lines -= 1

    return (_columns_for(standard, cell_width, cell_height), GLASS_LINES)


def _pasteable(module: object) -> list[str]:
    """The clipboard as keystrokes: printable text, returns kept.

    A Windows clipboard ends its lines with a carriage-return
    pair, so both forms collapse to the one newline the reader
    takes as a return key -- a multi-line paste submits line by
    line, exactly as it does at a terminal. Everything else
    unprintable is dross no keyboard could type and is dropped
    rather than arriving at §3.8 as a crash.
    """

    pygame: Any = module
    text = pygame.scrap.get_text().replace("\r\n", "\n").replace("\r", "\n")

    return [
        character for character in text if character == "\n" or character.isprintable()
    ]


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
