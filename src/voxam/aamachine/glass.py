"""The Å-machine at the glass: the third machine gets a window.

The face is the terminal voice's twin with a pixel window where
the stream was, and it is a short file for a reason. StyledVoice
already does the dressing: the LOOK sheet's classes fold into one
outfit of bold, italic, reverse, ink, and paper, and _fitted is
the single seam a face fills. Here that seam pours everything
told so far before the outfit changes, so a span's dress lands on
its own characters and on nothing after them.

The window itself is the pygame one the other two machines paint
on, asked for through a narrower protocol than theirs: a text
machine paints cells, presents frames, names its window, and
waits for keys, so Pane asks for that and nothing else. A stub
drives the whole face in tests and no window ever opens in
continuous integration.

The paint call takes ink and paper as real RGB, which is why the
voice keeps its own grid rather than borrowing the Z-Machine's
screen model: that model stores §8.3.1 colour codes, and eleven
codes cannot spell the LOOK sheet's palette (orange, purple, and
brown have no code at all). A grid of dressed cells costs little,
and the whole of it repaints at each pour: a text machine speaks
a paragraph at a time, not a frame at a time.

What the window claims over the terminal is its height. A glass
knows how many lines it has, so VM_INFO's screen-height question
finally has a true answer, text that would scroll away pauses at
a [MORE] first, and CLEAR really clears (Aa-machine: VM_INFO).

A story's own pictures hang here too. The window has always been
able to draw them: the same glass draws Version 6 art and Glulx
canvases, and Voxam decodes PNG itself. What the face had to
learn is where a picture goes in a scrolling column of text, and
the answer is that it takes whole rows: a picture reserves the
lines it needs, the text carries on beneath it, and it rides the
scroll like everything else until it leaves at the top
(Aa-machine: EMBED_RES).

Status areas and links are still refused honestly, which is the
plain voice's own posture and the spec's own provision for a
display that cannot hold them: they are this face's named next
roads.
"""

from itertools import groupby
from typing import TYPE_CHECKING, Protocol, cast

from voxam.aamachine.machine import Machine
from voxam.aamachine.output import FiledVoice
from voxam.aamachine.story import Story
from voxam.editor import LineEditor, read_line_edited
from voxam.errors import PNGError
from voxam.glass import DEFAULT_THEME, GLASS_THEMES, layered, open_pygame_glass
from voxam.painter import MORE_PROMPT
from voxam.png import decode

if TYPE_CHECKING:
    from collections.abc import Sequence

    from voxam.aamachine.output import Outfit

# The bare outfit a blank cell wears: no attribute claimed, and
# both colours left to the window's own.
_PLAIN: "Outfit" = (False, False, False, None, None)

# The outfit the [MORE] prompt wears: the window's own colours,
# swapped, which is how every pager since has marked itself out.
_MARKED: "Outfit" = (False, False, True, None, None)

# The §3.8-translated characters the glass answers with, as the
# reserved keypress codes the Å-machine knows them by (Aa-machine:
# Text). It is one alphabet with the other two machines' key
# seams, so an arrow means the same press at every face Voxam
# paints.
KEY_CODES: dict[str, int] = {
    "\n": 0x0D,
    "\x7f": 0x08,
    "\x81": 0x10,
    "\x82": 0x11,
    "\x83": 0x12,
    "\x84": 0x13,
}


class Pane(Protocol):
    """The sliver of a window this voice drives.

    Narrower than voxam.glass's own Glass protocol, deliberately:
    a text machine paints cells, presents frames, names its
    window, and waits for keys. It samples no pixels and hangs no
    art, so it asks for neither, and a real Glass satisfies this
    without being told about it.

    Attributes:
        columns: The window's width in characters.
        lines: The window's height in characters.
        cell_width: One cell's width in real pixels, which is what
            a picture has to be measured against to know how many
            columns it covers.
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
        """Blit a run of same-dressed characters into their cells."""

    def present(self) -> None:
        """Put the painted frame on screen."""

    def entitle(self, title: str) -> None:
        """Name the window, for a title bar that knows its story."""

    def key(self, timeout: float | None) -> str | None:
        """One keypress, already §3.8-translated; None on expiry.

        The window's close button raises EOFError, which is how a
        shut window ends a session.
        """

    def draw(
        self,
        rows: "Sequence[Sequence[tuple[int, ...]]]",
        line: int,
        column: int,
        size: tuple[int, int],
    ) -> None:
        """Blit pixel rows with their top left at a pixel position."""

    def photograph(
        self, data: bytes
    ) -> "Sequence[Sequence[tuple[int, int, int]]] | None":
        """Decode photographic bytes -- a JPEG -- to pixel rows.

        The interpreter decodes PNG itself; JPEG it hands to the
        window, whose pygame carries the decoders it does not.
        """


# The window badge an Å-machine session wears: the packaged
# aamachine.ico, where a Z-Machine story wears its numbered z<n>
# and a Glulx one its own mark.
BADGE = "aamachine"

# One cell as the window holds it: the character standing there
# and the outfit it was told in.
Painted = tuple[str, "Outfit"]

# One picture hung in the column: the row its top sits on, the
# rows it covers, its pixels, and the size those are drawn at. The
# row falls as the text scrolls, and the picture leaves at the top
# with the lines it was set among.
Hung = tuple[int, int, "Sequence[Sequence[tuple[int, ...]]]", tuple[int, int]]


class GlassVoice(FiledVoice):
    """The Å-machine's voice at a pixel window.

    The voice owns a grid of dressed cells and a cursor into it.
    Everything the story says arrives through the telling, poured
    into that grid at each dress change and each wait; everything
    the player types arrives through the same grid, because the
    line editor's canvas seam is the two methods this class
    already needs (write and retreat).
    """

    has_styles = True
    has_color = True

    def __init__(
        self, story: Story, glass: Pane, *, theme: str = DEFAULT_THEME
    ) -> None:
        """Speak into a window, wearing a theme's ink and paper."""

        self._glass = glass
        self._story = story
        self._columns = glass.columns
        self._lines = glass.lines
        self._cell_width = glass.cell_width
        self._cell_height = glass.cell_height
        self._ink, self._paper = GLASS_THEMES[theme]
        # The ground the blank cells wear, the theme's until a
        # body class names its own.
        self._ground = self._paper
        self._outfit: Outfit = _PLAIN
        self._editor = LineEditor()
        self._rows: list[list[Painted]] = []
        self._hung: list[Hung] = []
        self._row = 0
        self._column = 0
        self._mark = 0
        # Rows scrolled away since the player last had the keys:
        # what a [MORE] holds back before it is a windowful.
        self._fresh = 0

        # The wrapper counts the window's own columns, and reset()
        # below blanks the grid, so the fields above stand first.
        super().__init__(story, self._columns, self._asking)

    # -- the telling ----------------------------------------------------

    def _fitted(self) -> None:
        """Pour what stands, then wear the dress that follows it.

        The pour is what makes the dress land on the right
        characters: everything told up to here belongs to the
        outfit that was worn when it was said.
        """

        self._poured()
        self._outfit = self._wardrobe.folded()

    def poured(self) -> None:
        """Land everything told since the last pour, and show it."""

        self._poured()
        self._repaint()

    def _poured(self) -> None:
        """Write the telling's new tail into the grid."""

        told = self.told()
        self.write(told[self._mark :])
        self._mark = len(told)

    def set_body(self, style: int) -> None:
        """Dress the body; the window's ground goes with it.

        A body class that names a background means the page and
        not only the characters standing on it, so the blank
        cells take the colour too (Aa-machine: LOOK).
        """

        super().set_body(style)

        paper = self._wardrobe.classed(style).paper
        self._ground = self._paper if paper is None else paper

    def can_embed_res(self, resource: int) -> bool:
        """Whether this story carries a picture this window can draw."""

        return self._pixels(resource) is not None

    def embed_res(self, resource: int) -> None:
        """Hang a picture where the telling has reached.

        A picture takes whole rows rather than a place on a line:
        the text told so far is poured first, the rows the picture
        needs are broken past -- pausing at a [MORE] and scrolling
        exactly as text does -- and the story carries on beneath
        it (Aa-machine: EMBED_RES).
        """

        found = self._pixels(resource)

        if found is None:
            return

        rows, (width, height) = found

        self._poured()

        if self._column:
            self._broken()

        tall = -(-height // self._cell_height)
        top = self._row

        for _ in range(tall):
            self._broken()

            # A scroll while the rows are being reserved carries
            # the top up with everything else.
            top = min(top, self._row - 1)

        self._hung.append((top, tall, rows, (width, height)))
        self.prompted()

    def _pixels(
        self, resource: int
    ) -> "tuple[Sequence[Sequence[tuple[int, ...]]], tuple[int, int]] | None":
        """One resource as pixel rows and the size to draw them at.

        PNG is decoded here, as everywhere else in Voxam; a JPEG
        goes to the window, whose pygame carries what the
        interpreter does not. A picture wider than the window is
        brought down to fit, keeping its proportions.
        """

        found = self._story.embedded(resource)

        if found is None:
            return None

        name, data = found

        if name.lower().endswith((".jpg", ".jpeg")):
            shot = self._glass.photograph(data)

            if not shot or not shot[0]:
                return None

            rows: Sequence[Sequence[tuple[int, ...]]] = tuple(
                tuple(tuple(pixel) for pixel in row) for row in shot
            )
            width, height = len(shot[0]), len(shot)
        else:
            try:
                picture = decode(data)
            except PNGError:
                return None

            rows = layered(picture)
            width, height = picture.width, picture.height

        room = self._columns * self._cell_width

        if width > room:
            height = max(1, height * room // width)
            width = room

        return rows, (width, height)

    def clear(self) -> None:
        """Wipe the window: a glass really can (Aa-machine: CLEAR)."""

        self._poured()
        self._wiped()
        # prompted() is the voice's own note that the cursor went
        # home with a line break standing, which is exactly the
        # state a cleared window is in.
        self.prompted()
        self._repaint()

    def clear_all(self) -> None:
        """Wipe the window; no status area stands to hide."""

        self.clear()

    def reset(self) -> None:
        """Forget everything: a restart opens on a blank window."""

        super().reset()
        self._wiped()

    def measured(self, dimension: int) -> int:
        """The window's size in characters (Aa-machine: VM_INFO).

        A window knows its height, which is the one question a
        stream has to answer with a shrug.
        """

        if dimension == 0:
            return self._columns

        if dimension == 1:
            return self._lines

        return 0

    # -- the grid -------------------------------------------------------

    def write(self, text: str) -> None:
        """Land text in the grid at the cursor: the canvas seam.

        Both the telling and the line editor's echo come through
        here, so one cursor serves the story and the player alike
        and neither has to know about the other.
        """

        for character in text:
            if character == "\n":
                self._broken()

                continue

            if self._column >= self._columns:
                self._broken()

            self._rows[self._row][self._column] = (character, self._outfit)
            self._column += 1

    def retreat(self, cells: int) -> int:
        """Move the cursor left, stopping at the row's own edge."""

        moved = min(cells, self._column)
        self._column -= moved

        return moved

    def _broken(self) -> None:
        """Start the next row, scrolling at the foot of the window."""

        if self._row + 1 < self._lines:
            self._row += 1
            self._column = 0

            return

        # The scroll is about to carry the top row away, so a
        # windowful of unread text stops for a reader first.
        if self._fresh >= self._lines - 1:
            self._paused()

        self._rows.pop(0)
        self._rows.append(self._blank())
        self._fresh += 1
        self._column = 0
        self._hung = [
            (top - 1, tall, rows, size)
            for top, tall, rows, size in self._hung
            if top - 1 + tall > 0
        ]

    def _wiped(self) -> None:
        """Blank every row and take the cursor home."""

        self._rows = [self._blank() for _ in range(self._lines)]
        self._hung = []
        self._row = 0
        self._column = 0
        self._fresh = 0

    def _blank(self) -> list[Painted]:
        """One row of undressed spaces."""

        return [(" ", _PLAIN) for _ in range(self._columns)]

    # -- the window -----------------------------------------------------

    def _repaint(self, *, more: bool = False, caret: bool = False) -> None:
        """Blit every row and present the frame.

        The whole grid redraws rather than a damaged part of it:
        a windowful is under two thousand cells, painted in
        same-dressed runs, and a text machine paints when it has
        something to say rather than on a clock.
        """

        for row, cells in enumerate(self._rows):
            column = 0

            for outfit, run in groupby(cells, key=lambda cell: cell[1]):
                characters = "".join(character for character, _ in run)
                self._blit(row, column, characters, outfit)
                column += len(characters)

        # After the cells, so a picture covers the blank rows it
        # reserved rather than being written over by them.
        for top, _tall, pixels, size in self._hung:
            self._glass.draw(pixels, top * self._cell_height + 1, 1, size)

        if more:
            self._blit(self._row, self._marked(), MORE_PROMPT, _MARKED)

        if caret:
            # A window has no hardware cursor to park, so the cell
            # the next character lands in wears its dress swapped.
            character, (bold, italic, reverse, ink, paper) = self._at()
            self._blit(
                self._row,
                self._column,
                character,
                (bold, italic, not reverse, ink, paper),
            )

        self._glass.present()

    def _blit(self, row: int, column: int, characters: str, outfit: "Outfit") -> None:
        """Paint one same-dressed run, its colours resolved."""

        bold, italic, reverse, ink, paper = outfit
        foreground = self._ink if ink is None else ink
        background = self._ground if paper is None else paper

        if reverse:
            foreground, background = background, foreground

        self._glass.paint(
            row + 1,
            column + 1,
            characters,
            foreground,
            background,
            bold=bold,
            italic=italic,
            graphics=False,
        )

    def _at(self) -> Painted:
        """The cell the cursor stands on, the right edge included."""

        column = min(self._column, self._columns - 1)

        return self._rows[self._row][column]

    def _marked(self) -> int:
        """Where the [MORE] prompt fits on the row it interrupts."""

        return max(0, min(self._column, self._columns - len(MORE_PROMPT)))

    # -- the player -----------------------------------------------------

    def read_line(self) -> str:
        """One typed line, edited and echoed in the window.

        The editor is the painted faces' own: backspace rubs out,
        the arrows move within the line, and up and down walk the
        session's history. Every visible change comes back through
        this voice's own canvas seam.
        """

        line = read_line_edited(
            self._editor,
            self,
            self._key,
            lambda: self._repaint(caret=True),
        )
        self._fresh = 0
        self._repaint()

        # The key source never expires, so the line is always real.
        return cast("str", line)

    def read_key(self) -> int:
        """One keypress as the machine's own code (Aa-machine: Text)."""

        character = self._key()
        self._fresh = 0
        code = KEY_CODES.get(character)

        return ord(character) if code is None else code

    def _key(self) -> str:
        """One keypress; a window with none left has closed.

        A real window blocks until a key arrives and raises
        EOFError when the player closes it, so None can only come
        from a scripted glass whose keys have run out: the same
        end of input an exhausted stream gives the terminal face.
        """

        key = self._glass.key(None)

        if key is None:
            raise EOFError

        return key

    def _paused(self) -> None:
        """Hold the scroll behind a [MORE] until a key arrives.

        The key is spent on the pause and never reaches the story,
        which is what every pager has always done with it.
        """

        self._repaint(more=True)
        self._key()
        self._fresh = 0
        self._repaint()

    def _asking(self, prompt: str) -> str:
        """Ask for a filename in the window itself.

        The filed voice has already broken the line and poured
        what stood, so the prompt lands on a fresh row and the
        editor picks up right after it.
        """

        self.write(prompt)
        self._repaint()

        return self.read_line()


def played(
    story: Story,
    *,
    seed: int | None = None,
    glass: Pane | None = None,
    theme: str = DEFAULT_THEME,
    zoom: float | None = None,
) -> None:
    """Play one story at the glass, opening to quit.

    The glass is the seam the tests drive: a stub answers with
    scripted keys and collects the paints, and live play opens a
    real window instead. A closed window ends the session the way
    an exhausted stream ends the terminal's.

    Raises:
        ImportError: When a real window is asked for and the
            pygame extra is not installed.
    """

    if glass is None:
        glass = open_pygame_glass(None, BADGE, zoom)

    caption = story.meta.get("title")

    if caption:
        glass.entitle(caption)

    voice = GlassVoice(story, glass, theme=theme)
    machine = Machine(story, voice, seed=seed)

    try:
        _driven(machine, voice)
        voice.line()
        voice.poured()
    except EOFError:
        # The player shut the window, or a scripted glass ran dry:
        # there is nothing left to pour the closing line onto.
        pass


def _driven(machine: Machine, voice: GlassVoice) -> None:
    """Turn the machine over until it quits or the window shuts."""

    waiting = machine.run()

    while waiting != "quit":
        voice.poured()

        if waiting == "line":
            line = voice.read_line()
            voice.prompted()
            waiting = machine.deliver_line(line)
        else:
            waiting = machine.deliver_key(voice.read_key())
