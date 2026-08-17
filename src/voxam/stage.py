"""The Version 6 stage: §8.8's eight windows on one cell grid.

Version 6 games place their windows in pixels -- a status strip
here, a story box there, chrome around a picture -- and the plain
and painted frontends can only mimic that with flowing text. This
model is for a glass that measures: it keeps all eight §8.8.3
windows, each with a position and size in units, its own cursor,
dress, and attributes, and plots their text onto one shared grid
of cells. The grid interface is the screen model's own -- cell,
sweep, row_text -- so the graphics frontend blits a stage exactly
as it blits a screen.

Units arrive from the machine's ledger world and cells leave for
the glass: positions and sizes are §8.8's pixels, converted here
with the font metrics the stage was built with. Nothing printed
belongs to a window once plotted (§8.8.3): moving a window moves
only its bookkeeping, and text lands wherever the window was at
the moment of printing.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field

from voxam.errors import ZMachineScreenError
from voxam.frontend import NORMAL_FONT, Status
from voxam.screen import (
    CURRENT_COLOUR,
    DEFAULT_COLOUR,
    ERASE_KEEP_SPLIT,
    ERASE_UNSPLIT,
    ROMAN,
    Cell,
)

# §8.8.3's eight windows, and the §8.8.3.1 boot attributes: window
# 0 wraps and scrolls its running text; every other window overlays
# in place until told otherwise.
STAGE_WINDOWS = 8

# The rectangle a stage erasure touched: first row, first column,
# row count, and column count, in cells. The frontend uses it to
# forget its shadow of the region.
Rectangle = tuple[int, int, int, int]


@dataclass(frozen=True)
class TextPaint:
    """One dressed character placed at a unit position.

    Attributes:
        line: The character's top edge in units, 1-based -- the
            window's own y plus the cursor's rows, unrounded, so
            text lands exactly where §8.8 placed its window.
        column: The character's left edge in units.
        cell: The character and its dress.
    """

    line: int
    column: int
    cell: Cell


@dataclass(frozen=True)
class FillPaint:
    """A unit rectangle painted to a background colour (§8.8.5).

    Attributes:
        line: The rectangle's top edge in units, 1-based.
        column: Its left edge in units.
        height: Its height in units.
        width: Its width in units.
        background: The §8.3.1 background colour code to paint.
    """

    line: int
    column: int
    height: int
    width: int
    background: int


@dataclass(frozen=True)
class ShiftPaint:
    """A unit rectangle whose pixels slide vertically (§8.8.3.6).

    Attributes:
        line: The rectangle's top edge in units, 1-based.
        column: Its left edge in units.
        height: Its height in units.
        width: Its width in units.
        rise: How far the content slides in units -- positive up,
            negative down. The exposed strip arrives as its own
            FillPaint.
    """

    line: int
    column: int
    height: int
    width: int
    rise: int


Paint = TextPaint | FillPaint | ShiftPaint


@dataclass
class _Window:
    """One §8.8.3 window: geometry in units, a cursor in cells.

    The cursor is kept as 0-based cell offsets within the window's
    own box -- the wrap arithmetic's natural coordinates -- and
    converted to §8.8's 1-based units at the seam.
    """

    y: int = 1
    x: int = 1
    height: int = 0
    width: int = 0
    left: int = 0
    right: int = 0
    row: int = 0
    column: int = 0
    style: int = ROMAN
    foreground: int = DEFAULT_COLOUR
    background: int = DEFAULT_COLOUR
    font: int = NORMAL_FONT
    wrapping: bool = False
    scrolling: bool = False
    scroll_due: bool = False
    pending: list[Cell] = field(default_factory=list)


class StageModel:
    """A pure §8.8 screen: eight windows, one grid, no window system.

    Every method mirrors a Frontend operation the machine forwards,
    so the graphics frontend can hand calls straight through.
    Inspection methods flush pending buffered text first, so tests
    always see the stage a player would.
    """

    def __init__(
        self, columns: int, lines: int, font_width: int, font_height: int
    ) -> None:
        """Set the §8.8.3.3 boot stage: window 0 filling the screen.

        Args:
            columns: The screen width in cells.
            lines: The screen height in cells.
            font_width: One cell's width in units.
            font_height: One cell's height in units.
        """

        self._columns = columns
        self._lines = lines
        self._font_width = font_width
        self._font_height = font_height
        self._grid: list[list[Cell]] = [[Cell()] * columns for _ in range(lines)]
        self._damage: set[int] = set()
        self._paints: list[Paint] = []
        self._buffered = True
        self._split_seen = False
        self._selected = 0
        self._windows = [_Window() for _ in range(STAGE_WINDOWS)]
        self._windows[0].height = lines * font_height
        self._windows[0].width = columns * font_width
        self._windows[0].wrapping = True
        self._windows[0].scrolling = True
        # Window 1 boots screen-wide and flat: §8.8.4.1's split
        # tiles it against window 0 without touching widths, so a
        # width must already be there for the split to mean
        # anything.
        self._windows[1].width = columns * font_width

    @property
    def columns(self) -> int:
        """The screen width in cells."""

        return self._columns

    @property
    def lines(self) -> int:
        """The screen height in cells."""

        return self._lines

    @property
    def selected(self) -> int:
        """Which of the eight windows takes the next printing."""

        return self._selected

    @property
    def background(self) -> int:
        """The selected window's §8.3.1 background colour code."""

        return self._windows[self._selected].background

    # --- geometry, from units to the cell grid ---

    def _first_row(self, window: _Window) -> int:
        """The window's first screen cell row, 1-based."""

        return (window.y - 1) // self._font_height + 1

    def _first_column(self, window: _Window) -> int:
        """The window's first screen cell column, 1-based."""

        return (window.x - 1) // self._font_width + 1

    def _row_count(self, window: _Window) -> int:
        """How many whole cell rows fit the window's height."""

        return window.height // self._font_height

    def _column_count(self, window: _Window) -> int:
        """How many whole cell columns fit the window's width."""

        return window.width // self._font_width

    def _left_edge(self, window: _Window) -> int:
        """The first writable cell column offset: the left margin."""

        return window.left // self._font_width

    def _right_edge(self, window: _Window) -> int:
        """One past the last writable column offset: the right margin.

        Margins are §8.8.3.2.1's: sizes in units, 0 by default,
        and text is clipped to stay inside them.
        """

        return (window.width - window.right) // self._font_width

    def _box(self, window: _Window) -> Rectangle:
        """The window's cell rectangle, clipped to the screen."""

        first_row = max(self._first_row(window), 1)
        first_column = max(self._first_column(window), 1)
        last_row = min(
            self._first_row(window) + self._row_count(window) - 1, self._lines
        )
        last_column = min(
            self._first_column(window) + self._column_count(window) - 1, self._columns
        )

        return (
            first_row,
            first_column,
            max(last_row - first_row + 1, 0),
            max(last_column - first_column + 1, 0),
        )

    # --- the stage seam the machine drives ---

    def place_window(
        self, window: int, line: int, column: int, height: int, width: int
    ) -> None:
        """Place a window at (line, column) with a size, in units.

        Nothing on screen moves (§8.8.3): the geometry only decides
        where future text lands. The window's own cursor is
        relative to its origin and rides along unchanged
        (§8.8.3.5).
        """

        target = self._known(window)

        self._flush(self._windows[self._selected])

        target_window = self._windows[target]
        target_window.y = line
        target_window.x = column
        target_window.height = height
        target_window.width = width

    def set_window(self, window: int) -> None:
        """Select the window that takes the next printing (§8.8.3).

        Each window remembers its own cursor (§8.8.3.5), so
        selection homes nothing.
        """

        self._flush(self._windows[self._selected])
        self._selected = self._known(window)

    def set_cursor(self, line: int, column: int) -> None:
        """Move the selected window's cursor, in relative units."""

        current = self._windows[self._selected]

        self._flush(current)

        current.row = max((line - 1) // self._font_height, 0)
        current.column = max((column - 1) // self._font_width, 0)
        current.scroll_due = False

    def get_cursor(self) -> tuple[int, int]:
        """The selected window's cursor, in relative units."""

        current = self._windows[self._selected]

        self._flush(current)

        return (
            current.row * self._font_height + 1,
            current.column * self._font_width + 1,
        )

    def split_window(self, height: int) -> None:
        """Tile windows 1 and 0 vertically, the height in units.

        Window 1 takes the top of the screen at the given height
        and window 0 the rest (§8.8.4.1); x coordinates and widths
        stay put. Each cursor keeps its absolute screen position
        unless that now falls outside its window, in which case it
        homes (§15 split_window).
        """

        self._flush(self._windows[self._selected])

        self._split_seen = self._split_seen or height > 0
        screen_height = self._lines * self._font_height
        upper = self._windows[1]
        lower = self._windows[0]
        absolutes = [
            (window, self._first_row(window) + window.row) for window in (upper, lower)
        ]
        upper.y = 1
        upper.height = height
        lower.y = height + 1
        lower.height = max(screen_height - height, 0)

        for window, absolute in absolutes:
            window.row = absolute - self._first_row(window)

            if not 0 <= window.row < max(self._row_count(window), 1):
                window.row = 0
                window.column = 0

    def write(self, text: str) -> None:
        """Print to the selected window, by its §8.8.3.1 attributes.

        A wrapping window breaks lines at its own right edge --
        whole words while buffering is on -- and a scrolling one
        scrolls its own rectangle; a window with neither overlays
        until its right margin, where the cursor stays and further
        text is ignored (§8.8.3.1.1).
        """

        current = self._windows[self._selected]

        for character in text:
            if character == "\n":
                self._flush(current)
                self._feed(current)
            elif not self._buffered:
                self._emit(current, self._dressed(character))
            elif character == " ":
                self._flush(current)
                self._emit_space(current)
            else:
                current.pending.append(self._dressed(character))

    def erase_window(self, window: int) -> Rectangle:
        """Erase a window's rectangle to background (§8.8.5.3).

        Window -1 erases the whole screen to window 0's
        background, re-tiles windows 0 and 1 if a split had
        happened, and selects window 0 (§8.8.5.3.1, §8.8.4.2);
        window -2 erases the whole screen to the current
        background and changes nothing else (§8.8.5.3.2). A plain
        window erases its own rectangle and homes its cursor.

        Returns:
            The erased cell rectangle, for the glass to forget.

        Raises:
            ZMachineScreenError: For a window §8.8.3 does not
                name.
        """

        self._flush(self._windows[self._selected])

        if window == ERASE_UNSPLIT:
            self._blank_rows(1, self._lines, self._windows[0].background)
            self._paints.append(self._screen_fill(self._windows[0].background))

            if self._split_seen:
                self.split_window(0)

            self._selected = 0
            self._windows[0].row = 0
            self._windows[0].column = 0
            self._windows[0].scroll_due = False

            return (1, 1, self._lines, self._columns)

        if window == ERASE_KEEP_SPLIT:
            self._blank_rows(1, self._lines, self.background)
            self._paints.append(self._screen_fill(self.background))

            return (1, 1, self._lines, self._columns)

        target = self._windows[self._known(window)]
        first_row, first_column, row_count, column_count = self._box(target)

        for row in range(first_row, first_row + row_count):
            for column in range(first_column, first_column + column_count):
                self._paint(row, column, self._blank(target.background))

        # The glass erases the window's true unit rectangle -- not
        # the cell approximation -- as §8.8.5.3 measures it.
        self._paints.append(
            FillPaint(
                target.y, target.x, target.height, target.width, target.background
            )
        )

        target.row = 0
        target.column = 0
        target.scroll_due = False

        return (first_row, first_column, row_count, column_count)

    def _screen_fill(self, background: int) -> FillPaint:
        """The whole screen as one fill, in units."""

        return FillPaint(
            1,
            1,
            self._lines * self._font_height,
            self._columns * self._font_width,
            background,
        )

    def scroll_window(self, window: int, pixels: int) -> None:
        """Scroll a window's rectangle by a pixel amount (§8.8.3.6).

        Positive scrolls the text up, negative down, in whole cell
        rows -- the §15 opcode, unrelated to the scrolling
        attribute -- and the exposed rows blank to the window's
        background. Arthur scrolls its story window this way at
        every prompt.
        """

        self._flush(self._windows[self._selected])

        target = self._windows[self._known(window)]

        for _ in range(abs(pixels) // self._font_height):
            if pixels > 0:
                self._scroll(target)
            else:
                self._scroll_down(target)

    def set_margins(self, window: int, left: int, right: int) -> None:
        """Set a window's margins in units (§8.8.3.2.1).

        Wrapping text is clipped to stay inside them, and a cursor
        the new margins would strand moves to the left margin
        (§8.8.3.2.2.2).
        """

        self._flush(self._windows[self._selected])

        target = self._windows[self._known(window)]
        target.left = left
        target.right = right

        if not self._left_edge(target) <= target.column < self._right_edge(target):
            target.column = self._left_edge(target)

    def erase_line(self) -> None:
        """Erase from the cursor to the right margin (§8.8.5.2)."""

        current = self._windows[self._selected]

        self._flush(current)

        first_row, first_column, row_count, _column_count = self._box(current)

        if current.row >= row_count:
            return

        row = first_row + current.row

        for column in range(
            first_column + current.column, first_column + self._right_edge(current)
        ):
            self._paint(row, column, self._blank(current.background))

        width = (self._right_edge(current) - current.column) * self._font_width

        if width > 0:
            self._paints.append(
                FillPaint(
                    current.y + current.row * self._font_height,
                    current.x + current.column * self._font_width,
                    self._font_height,
                    width,
                    current.background,
                )
            )

    def rub_out(self) -> None:
        """Retreat the cursor one cell and blank it (§15 read)."""

        current = self._windows[self._selected]

        self._flush(current)

        if current.column > 0:
            current.column -= 1
            first_row, first_column, _rows, _columns = self._box(current)

            self._paint(
                first_row + current.row,
                first_column + current.column,
                self._blank(current.background),
            )
            self._paints.append(
                FillPaint(
                    current.y + current.row * self._font_height,
                    current.x + current.column * self._font_width,
                    self._font_height,
                    self._font_width,
                    current.background,
                )
            )

    def write_rectangle(self, rows: Sequence[str]) -> None:
        """Print a §15 rectangle, right and down from the cursor.

        Each row after the first begins one line down at the
        column where the rectangle began, overlaying without wrap
        -- the §15 print_table shape.
        """

        current = self._windows[self._selected]

        self._flush(current)

        start_row, start_column = current.row, current.column
        wrapping = current.wrapping
        current.wrapping = False

        for index, row_text in enumerate(rows):
            if index:
                bottom = max(self._row_count(current) - 1, 0)
                current.row = min(start_row + index, bottom)
                current.column = start_column

            for character in row_text:
                self._emit(current, self._dressed(character))

        current.wrapping = wrapping

    def set_style(self, style: int) -> None:
        """Change the selected window's style (§8.8.3.2.3)."""

        current = self._windows[self._selected]

        if style == ROMAN:
            current.style = ROMAN
        else:
            current.style |= style

    def set_colour(self, foreground: int, background: int) -> None:
        """Change the selected window's colours (§8.8.3.2.4)."""

        current = self._windows[self._selected]

        if foreground != CURRENT_COLOUR:
            current.foreground = foreground

        if background != CURRENT_COLOUR:
            current.background = background

    def set_font(self, font: int) -> None:
        """Change the selected window's font (§8.8.3.2.5)."""

        self._windows[self._selected].font = font

    def set_buffering(self, buffered: bool) -> None:
        """Turn buffered printing off or on (§8.8.3.1.2)."""

        self._flush(self._windows[self._selected])
        self._buffered = buffered

    def show_status(self, status: Status) -> None:
        """Refuse: a Version 6 game draws its own status (§8.2).

        Raises:
            ZMachineScreenError: Always -- the machine never sends
                one, and a stray call is a wiring fault worth
                hearing about.
        """

        del status

        msg = "version 6 draws its own status area; the stage has no line (§8.2)"

        raise ZMachineScreenError(msg)

    # --- the grid the glass blits ---

    def paints(self) -> list[Paint]:
        """The unit-positioned paints since the last drain, in order.

        The glass performs exactly these -- text at true §8.8
        positions, fills, and scrolls -- and its own persistent
        pixels are the retained screen, §8.8.3's rule made
        literal. Draining clears the slate; the cell grid remains
        the inspectable approximation the tests read.
        """

        self._flush(self._windows[self._selected])

        drained = self._paints
        self._paints = []

        return drained

    def sweep(self) -> list[int]:
        """The rows changed since the last sweep, in screen order."""

        self._flush(self._windows[self._selected])

        damaged = sorted(self._damage)
        self._damage.clear()

        return damaged

    def cell(self, row: int, column: int) -> Cell:
        """One grid position, pending text flushed first."""

        self._flush(self._windows[self._selected])

        return self._grid[row - 1][column - 1]

    def row_text(self, row: int) -> str:
        """One row's characters as a string, right side trimmed."""

        self._flush(self._windows[self._selected])

        return "".join(cell.character for cell in self._grid[row - 1]).rstrip()

    def rendered(self) -> str:
        """The whole stage as a text block, one line per row."""

        return "\n".join(self.row_text(row) for row in range(1, self._lines + 1))

    # --- the wrap machinery, one window at a time ---

    def _known(self, window: int) -> int:
        """Police a window number against §8.8.3's eight.

        Raises:
            ZMachineScreenError: For a number naming none of them.
        """

        if not 0 <= window < STAGE_WINDOWS:
            msg = f"window {window} is not one of the eight (§8.8.3)"

            raise ZMachineScreenError(msg)

        return window

    def _dressed(self, character: str) -> Cell:
        """One character wearing the selected window's dress."""

        current = self._windows[self._selected]

        return Cell(
            character,
            current.style,
            current.foreground,
            current.background,
            current.font,
        )

    def _blank(self, background: int) -> Cell:
        """A blank cell in a window's background, never reversed."""

        return Cell(" ", ROMAN, DEFAULT_COLOUR, background)

    def _flush(self, window: _Window) -> None:
        """Emit a pending word, wrapping it whole when that fits."""

        if not window.pending:
            return

        word = window.pending
        window.pending = []
        edge = self._right_edge(window)

        if (
            window.wrapping
            and len(word) > edge - window.column
            and len(word) <= edge - self._left_edge(window)
        ):
            self._feed(window)

        for cell in word:
            self._emit(window, cell)

    def _emit_space(self, window: _Window) -> None:
        """Emit one space, or let the line break swallow it."""

        if window.wrapping and window.column >= self._right_edge(window):
            self._feed(window)

            return

        self._emit(window, self._dressed(" "))

    def _emit(self, window: _Window, cell: Cell) -> None:
        """Place one cell at the window's cursor, edge rules and all.

        The edges are the §8.8.3.2.1 margins' -- the whole window
        when they are 0, their default.
        """

        edge = self._right_edge(window)

        if edge <= self._left_edge(window) or not self._row_count(window):
            return

        if window.column >= edge:
            if not window.wrapping:
                # §8.8.3.1.1: the cursor moves to the right margin
                # and stays there; further text is ignored.
                window.column = edge

                return

            self._feed(window)

        if window.scroll_due:
            self._scroll(window)

            window.scroll_due = False

        first_row, first_column, _rows, _columns = self._box(window)

        self._paint(first_row + window.row, first_column + window.column, cell)
        self._paints.append(
            TextPaint(
                window.y + window.row * self._font_height,
                window.x + window.column * self._font_width,
                cell,
            )
        )

        window.column += 1

    def _feed(self, window: _Window) -> None:
        """Move to the next line, scrolling or pinning at the bottom.

        The cursor returns to the left margin (§8.8.3.2.1) -- the
        window's own left edge when no margin is set.
        """

        if window.scroll_due:
            self._scroll(window)

            window.scroll_due = False

        bottom = max(self._row_count(window) - 1, 0)

        if window.row >= bottom:
            window.row = bottom

            if window.scrolling:
                # The scroll is owed, not paid: it happens when the
                # next text arrives, keeping the last line at the
                # window's foot instead of above a blank one.
                window.scroll_due = True
        else:
            window.row += 1

        window.column = self._left_edge(window)

    def _scroll(self, window: _Window) -> None:
        """Scroll the window's own rectangle up one cell row."""

        first_row, first_column, row_count, column_count = self._box(window)

        for row in range(first_row, first_row + row_count - 1):
            for column in range(first_column, first_column + column_count):
                self._paint(row, column, self._grid[row][column - 1])

        for column in range(first_column, first_column + column_count):
            self._paint(
                first_row + row_count - 1, column, self._blank(window.background)
            )

        self._paints.append(
            ShiftPaint(
                window.y,
                window.x,
                row_count * self._font_height,
                column_count * self._font_width,
                self._font_height,
            )
        )
        self._paints.append(
            FillPaint(
                window.y + (row_count - 1) * self._font_height,
                window.x,
                self._font_height,
                column_count * self._font_width,
                window.background,
            )
        )

    def _scroll_down(self, window: _Window) -> None:
        """Scroll the window's own rectangle down one cell row."""

        first_row, first_column, row_count, column_count = self._box(window)

        for row in range(first_row + row_count - 1, first_row, -1):
            for column in range(first_column, first_column + column_count):
                self._paint(row, column, self._grid[row - 2][column - 1])

        for column in range(first_column, first_column + column_count):
            self._paint(first_row, column, self._blank(window.background))

        self._paints.append(
            ShiftPaint(
                window.y,
                window.x,
                row_count * self._font_height,
                column_count * self._font_width,
                -self._font_height,
            )
        )
        self._paints.append(
            FillPaint(
                window.y,
                window.x,
                self._font_height,
                column_count * self._font_width,
                window.background,
            )
        )

    def _blank_rows(self, first: int, last: int, background: int) -> None:
        """Blank whole screen rows to a background colour."""

        for row in range(first, last + 1):
            self._grid[row - 1] = [self._blank(background)] * self._columns

        self._damage.update(range(first, last + 1))

    def _paint(self, row: int, column: int, cell: Cell) -> None:
        """Set one grid position, clipped to the screen, and damage it."""

        if 1 <= row <= self._lines and 1 <= column <= self._columns:
            self._grid[row - 1][column - 1] = cell
            self._damage.add(row)
