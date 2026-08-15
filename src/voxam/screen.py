"""The screen model: §8's two windows as a pure grid of cells.

This is the presentation half of the screen split into its testable
core: a two-dimensional grid of attributed characters obeying every
window, cursor, scrolling, and erasure rule of §8 -- and touching no
terminal whatsoever. A painter (the blessed frontend) diffs this
grid onto a real screen; tests read the grid directly and assert on
what a player would see. The model is deterministic by construction,
so a seeded replay draws the same grid, forever.

Rows and columns are 1-based, (1,1) at the top left, matching the
coordinates set_cursor speaks (§8.7.2.3.1). In Version 3 the top
row belongs to the interpreter's own status line and the upper
window hangs below it (§8.6.1.1); from Version 4 the upper window
starts at the top of the screen (§8.7.2.1).
"""

from collections.abc import Sequence
from dataclasses import dataclass

from voxam.errors import ZMachineScreenError
from voxam.frontend import NORMAL_FONT, Status

LOWER = 0
UPPER = 1

# The §8.7.1 text styles, as set_text_style speaks them (§15): a
# bitmask where 0 is Roman and clears the rest.
ROMAN = 0
REVERSE = 1
BOLD = 2
ITALIC = 4
FIXED_PITCH = 8

# The §8.3.1 colour codes: 0 means "no change" and 1 is the
# interpreter's default, which the model keeps symbolic -- mapping
# it to actual ink belongs to the painter.
CURRENT_COLOUR = 0
DEFAULT_COLOUR = 1

# The status line belongs to versions 1 to 3 (§8.2); the windowed
# model beneath it belongs to Version 3 alone (§8.6), and versions
# 1 and 2 are teletypes with no windows at all (§8.5.1). From
# Version 4 the lower window's cursor holds the bottom line and
# erasure homes it there (§8.7.2.2, §8.7.3.2.1); from Version 5 the
# cursor may sit on any line clear of the upper window and erasure
# homes to the top left (§8.7.3.3).
STATUS_LAST_VERSION = 3
WINDOWS_FIRST_VERSION = 3
BOTTOM_HOME_LAST_VERSION = 4

# Erase window's two whole-screen requests (§15 erase_window).
ERASE_UNSPLIT = -1
ERASE_KEEP_SPLIT = -2


@dataclass(frozen=True)
class Cell:
    """One character position on the screen with its dress (§8.7.1).

    Attributes:
        character: The character shown, a space when blank.
        style: The §8.7.1 style bitmask it was printed in.
        foreground: Its §8.3.1 foreground colour code.
        background: Its §8.3.1 background colour code.
        font: The §8.1.2 font it was printed in.
    """

    character: str = " "
    style: int = ROMAN
    foreground: int = DEFAULT_COLOUR
    background: int = DEFAULT_COLOUR
    font: int = NORMAL_FONT


BLANK = Cell()


class ScreenModel:
    """A pure §8 screen: two windows, one grid, no terminal.

    Every method mirrors a Frontend operation, so a grid-backed
    frontend can forward calls one-to-one. Inspection methods --
    row_text, rendered, cell -- flush pending buffered text first,
    so tests always see the screen a player would.
    """

    def __init__(self, columns: int = 80, lines: int = 24, version: int = 3) -> None:
        """Set the §8.7.3.3 start-of-game screen.

        Cleared, lower window selected, and the cursor at the bottom
        left through Version 4 (§8.6.3), the top left from Version 5.

        Args:
            columns: The screen width in characters (§8.4).
            lines: The screen height in lines (§8.4).
            version: The story version whose screen rules apply.
        """

        self._columns = columns
        self._lines = lines
        self._version = version
        self._grid: list[list[Cell]] = [[BLANK] * columns for _ in range(lines)]
        self._split = 0
        self._selected = LOWER
        self._style = ROMAN
        self._font = NORMAL_FONT
        self._foreground = DEFAULT_COLOUR
        self._background = DEFAULT_COLOUR
        self._buffered = True
        self._pending: list[Cell] = []
        self._scroll_due = False
        self._damage: set[int] = set()
        self._upper_cursor = (1, 1)
        self._lower_cursor = (
            (lines, 1)
            if version <= BOTTOM_HOME_LAST_VERSION
            else (self._lower_top(), 1)
        )

    @property
    def columns(self) -> int:
        """The screen width in characters (§8.4)."""

        return self._columns

    @property
    def lines(self) -> int:
        """The screen height in lines (§8.4)."""

        return self._lines

    @property
    def split(self) -> int:
        """The upper window's current height in lines (§8.7.2.1)."""

        return self._split

    @property
    def selected(self) -> int:
        """Which window takes the next printing (§8.7.2)."""

        return self._selected

    def _upper_top(self) -> int:
        """The screen row the upper window starts on.

        Below the Version 3 status line, at the very top from
        Version 4 (§8.6.1.1, §8.7.2.1).
        """

        return 2 if self._version <= STATUS_LAST_VERSION else 1

    def _lower_top(self) -> int:
        """The first screen row belonging to the lower window."""

        return self._upper_top() + self._split

    def _require_windows(self) -> None:
        """Refuse window operations on a teletype (§8.5.1)."""

        if self._version < WINDOWS_FIRST_VERSION:
            msg = (
                f"version {self._version} has no windows: its screen "
                f"can only be printed to (§8.5.1)"
            )

            raise ZMachineScreenError(msg)

    def write(self, text: str) -> None:
        """Print text to the selected window (§8.7.2).

        The upper window overlays whatever is there and never
        scrolls or buffers (§8.6.1.1.1, §8.7.2.5); the lower window
        word-wraps while buffering is on and scrolls at the bottom
        (§8.7.3.1).
        """

        for character in text:
            if self._selected == UPPER:
                self._write_upper(character)
            else:
                self._write_lower(character)

    def _write_upper(self, character: str) -> None:
        """Overlay one character at the upper cursor (§8.6.1.1.1).

        A newline moves to the start of the next window line,
        stopping at the window's bottom. Printing in the last
        column is legal and the cursor stays put, as §8.7.3.1's
        author suggests.
        """

        row, column = self._upper_cursor

        if character == "\n":
            self._upper_cursor = (min(row + 1, max(self._split, 1)), 1)

            return

        self._paint(self._upper_top() + row - 1, column, self._dressed(character))

        if column < self._columns:
            self._upper_cursor = (row, column + 1)

    def _write_lower(self, character: str) -> None:
        """Queue or emit one character for the lower window.

        While buffering is on, word characters gather in a pending
        buffer so a word that would overrun the margin wraps whole
        (§8.7.2.5 buffer_mode); spaces and newlines flush it.
        """

        if character == "\n":
            self._flush()
            self._line_feed()
        elif not self._buffered:
            self._emit(self._dressed(character))
        elif character == " ":
            self._flush()
            self._emit_space()
        else:
            self._pending.append(self._dressed(character))

    def _dressed(self, character: str) -> Cell:
        """One character wearing the current style, colours, and font."""

        return Cell(
            character, self._style, self._foreground, self._background, self._font
        )

    def _flush(self) -> None:
        """Emit the pending word, wrapping it whole if it fits a line.

        A word too long for any line simply character-wraps: there
        is no whole line it could have waited for.
        """

        if not self._pending:
            return

        word = self._pending
        self._pending = []
        _row, column = self._lower_cursor

        if len(word) > self._columns - column + 1 and len(word) <= self._columns:
            self._line_feed()

        for cell in word:
            self._emit(cell)

    def _emit_space(self) -> None:
        """Emit one space, or break the line instead at the margin.

        A space that would wrap becomes the line break itself: the
        next line never opens with the gap.
        """

        _row, column = self._lower_cursor

        if column > self._columns:
            self._line_feed()

            return

        self._emit(self._dressed(" "))

    def _emit(self, cell: Cell) -> None:
        """Place one cell at the lower cursor, wrapping at the margin.

        A scroll owed by an earlier line feed happens now, just as
        the text "reaches" the bottom (§8.7.3.1): deferring it keeps
        the last printed line visible at the foot of the screen
        instead of above a permanently blank one.
        """

        row, column = self._lower_cursor

        if column > self._columns:
            self._line_feed()
            row, column = self._lower_cursor

        if self._scroll_due:
            self._scroll()
            self._scroll_due = False

        self._paint(row, column, cell)
        self._lower_cursor = (row, column + 1)

    def _line_feed(self) -> None:
        """Move the lower cursor down, scrolling at the bottom (§8.7.3.1).

        At the bottom line the scroll is owed rather than paid: the
        next emission performs it. An already-owed scroll is paid
        first, so consecutive blank lines each earn their own.
        """

        if self._scroll_due:
            self._scroll()
            self._scroll_due = False

        row, _column = self._lower_cursor

        if row >= self._lines:
            self._scroll_due = True
            self._lower_cursor = (self._lines, 1)
        else:
            self._lower_cursor = (row + 1, 1)

    def _scroll(self) -> None:
        """Scroll the lower window up one line (§8.7.3.1).

        The upper window and the Version 3 status line never move
        (§8.6.2), and the fresh bottom line is blank in the current
        background without any reverse video.
        """

        top = self._lower_top()

        for row in range(top, self._lines):
            self._grid[row - 1] = self._grid[row]

        self._grid[self._lines - 1] = [self._blank_cell()] * self._columns
        self._damage.update(range(top, self._lines + 1))

    def _blank_cell(self) -> Cell:
        """A blank in the current background (§8.7.3.1, §8.7.3.2)."""

        return Cell(" ", ROMAN, DEFAULT_COLOUR, self._background)

    def _paint(self, row: int, column: int, cell: Cell) -> None:
        """Set one grid position, remembering the row as damaged."""

        self._grid[row - 1][column - 1] = cell
        self._damage.add(row)

    def split_window(self, height: int) -> None:
        """Resize the upper window to the given height (§8.7.2.1).

        Version 3 clears the freshly split upper window
        (§8.6.1.1.2); later versions leave the screen's appearance
        alone (§8.6.1). A split that would swallow the lower
        cursor pushes it to the line just below the new upper
        window (§8.7.2.2), and a split made while the upper window
        is selected keeps its cursor when still inside, moving it
        to the top left otherwise (§8.7.2.1.1).

        Raises:
            ZMachineScreenError: On a teletype version (§8.5.1), or
                for a split leaving no lower window at all.
        """

        self._require_windows()
        self._flush()

        # The upper window may take the whole screen -- Z-Tornado
        # plays its entire game in a full-height split -- but not
        # more than exists (§8.7.2.1).
        if height < 0 or height > self._lines - self._upper_top() + 1:
            msg = (
                f"an upper window {height} lines tall does not fit a "
                f"{self._lines}-line screen (§8.7.2.1)"
            )

            raise ZMachineScreenError(msg)

        self._split = height

        if self._version == STATUS_LAST_VERSION and height:
            top = self._upper_top()
            self._clear_rows(top, top + height - 1)

        row, _column = self._lower_cursor

        if row < self._lower_top():
            # The line just below the new upper window (§8.7.2.2) --
            # or the last line there is, when the split took all.
            self._lower_cursor = (min(self._lower_top(), self._lines), 1)

        upper_row, _upper_column = self._upper_cursor

        if self._selected == UPPER and upper_row > max(height, 1):
            self._upper_cursor = (1, 1)

    def set_window(self, window: int) -> None:
        """Select a window for printing (§8.7.2).

        Selecting the upper window homes its cursor to the top left
        every time (§8.6.1, §8.7.2); the lower window keeps its
        place.

        Raises:
            ZMachineScreenError: On a teletype version (§8.5.1), or
                for a window number the model does not have.
        """

        self._require_windows()
        self._flush()

        if window not in (LOWER, UPPER):
            msg = f"there is no window {window} before version 6 (§8.7.2)"

            raise ZMachineScreenError(msg)

        self._selected = window

        if window == UPPER:
            self._upper_cursor = (1, 1)

    def set_cursor(self, line: int, column: int) -> None:
        """Move the upper window's cursor (§8.7.2.3.1).

        The opcode has no effect when the lower window is selected,
        by the spec's own sentence -- a conforming quiet, not a
        shortcut.

        Raises:
            ZMachineScreenError: For a position outside the upper
                window's current size, which §8.7.2.3.1 makes
                illegal.
        """

        self._flush()

        if self._selected != UPPER:
            return

        if not (1 <= line <= self._split and 1 <= column <= self._columns):
            msg = (
                f"the cursor cannot move to ({line}, {column}) in an "
                f"upper window {self._split} lines by {self._columns} "
                f"(§8.7.2.3.1)"
            )

            raise ZMachineScreenError(msg)

        self._upper_cursor = (line, column)

    def get_cursor(self) -> tuple[int, int]:
        """The upper window's cursor, from either window (§8.7.2.3.2)."""

        self._flush()

        return self._upper_cursor

    def erase_window(self, window: int) -> None:
        """Erase a window to the background colour (§8.7.3.2).

        Window -1 unsplits the screen, clears the lot, selects the
        lower window, and homes its cursor -- bottom left in
        Version 4, top left from Version 5 (§8.7.3.3). Window -2
        clears the screen but keeps the split and the cursors (§15
        erase_window). Erasing a plain window homes its cursor to
        the top left from Version 5; in Version 4 the lower
        window's cursor homes to the bottom left (§8.7.3.2.1).

        Raises:
            ZMachineScreenError: For a window number the model does
                not have.
        """

        self._flush()

        if window == ERASE_UNSPLIT:
            self._clear_all()
            self._split = 0
            self._selected = LOWER
            self._home_lower()
        elif window == ERASE_KEEP_SPLIT:
            self._clear_all()
        elif window == LOWER:
            self._clear_rows(self._lower_top(), self._lines)
            self._home_lower()
        elif window == UPPER:
            top = self._upper_top()
            self._clear_rows(top, top + self._split - 1)
            self._upper_cursor = (1, 1)
        else:
            msg = f"there is no window {window} to erase (§15 erase_window)"

            raise ZMachineScreenError(msg)

    def _clear_all(self) -> None:
        """Blank every row, status line included."""

        self._clear_rows(1, self._lines)

    def _clear_rows(self, first: int, last: int) -> None:
        """Blank the rows to the background, never reversed (§8.7.3.2)."""

        for row in range(first, last + 1):
            self._grid[row - 1] = [self._blank_cell()] * self._columns

        self._damage.update(range(first, last + 1))

    def _home_lower(self) -> None:
        """Home the lower cursor per version (§8.7.3.2.1, §8.7.3.3)."""

        self._scroll_due = False

        if self._version <= BOTTOM_HOME_LAST_VERSION:
            self._lower_cursor = (self._lines, 1)
        else:
            self._lower_cursor = (min(self._lower_top(), self._lines), 1)

    def erase_line(self) -> None:
        """Erase from the cursor to the end of the line (§8.7.3.4)."""

        self._flush()

        if self._selected == UPPER:
            row, column = self._upper_cursor
            screen_row = self._upper_top() + row - 1
        else:
            screen_row, column = self._lower_cursor

        for position in range(column, self._columns + 1):
            self._grid[screen_row - 1][position - 1] = self._blank_cell()

        self._damage.add(screen_row)

    def set_style(self, style: int) -> None:
        """Change the text style for what follows (§8.7.1).

        Roman clears every style; the rest combine, which §15
        set_text_style permits and Standard 1.1 blesses outright.
        Changing style mid-word is legal (§8.7.1.2), so the pending
        buffer stays: its cells are already dressed.
        """

        if style == ROMAN:
            self._style = ROMAN
        else:
            self._style |= style

    def rub_out(self) -> None:
        """Erase the last typed character during line input (§15 read).

        Line editing belongs to the interpreter, and its rubout
        retreats the selected window's cursor one cell and blanks
        it. At the left edge there is nothing left of the line to
        rub, and the cursor stays put: the editor never chews into
        an earlier row.
        """

        self._flush()

        if self._selected == UPPER:
            row, column = self._upper_cursor

            if column > 1:
                self._paint(self._upper_top() + row - 1, column - 1, self._blank_cell())
                self._upper_cursor = (row, column - 1)
        else:
            row, column = self._lower_cursor

            if column > 1:
                self._paint(row, column - 1, self._blank_cell())
                self._lower_cursor = (row, column - 1)

    def write_rectangle(self, rows: Sequence[str]) -> None:
        """Print a §15 rectangle, right and down from the cursor.

        In the upper window each row after the first begins one
        line down from the last, at the column where the rectangle
        began -- how Beyond Zork stamps its map beside the story
        box without touching it. A rectangle taller than the
        window presses its last rows onto the bottom line, as an
        upper-window newline would. §15 leaves heights past 1
        undefined in the lower window; ordinary stacked lines,
        scrolling and all, are this model's settled answer.
        """

        self._flush()

        if self._selected != UPPER:
            for index, row_text in enumerate(rows):
                if index:
                    self.write("\n")

                self.write(row_text)

            return

        start_row, start_column = self._upper_cursor

        for index, row_text in enumerate(rows):
            if index:
                self._upper_cursor = (
                    min(start_row + index, max(self._split, 1)),
                    start_column,
                )

            for character in row_text:
                self._write_upper(character)

    def set_font(self, font: int) -> None:
        """Change the font for what follows (§8.1.2).

        The model records which font dressed each cell and leaves
        the drawing of §16's shapes to the painter. Changing font
        mid-word is legal (§8.1.3.1), so the pending buffer stays:
        its cells are already dressed.
        """

        self._font = font

    def set_buffering(self, buffered: bool) -> None:
        """Turn lower-window word-wrapping on or off (§15 buffer_mode).

        The upper window never buffers either way (§8.7.2.5).
        """

        self._flush()
        self._buffered = buffered

    def set_colour(self, foreground: int, background: int) -> None:
        """Change the printing colours (§8.3.1).

        A zero keeps that colour current; the codes stay symbolic,
        and mapping them to actual ink belongs to the painter.
        """

        if foreground != CURRENT_COLOUR:
            self._foreground = foreground

        if background != CURRENT_COLOUR:
            self._background = background

    def show_status(self, status: Status) -> None:
        """Draw the Version 1 to 3 status line on the top row (§8.2).

        The location sits on the left (§8.2.2), broken with an
        ellipsis when too long (§8.2.2.2); the right side shows
        score and turns, or an hours:minutes clock in a time game
        (§8.2.3). The whole row wears reverse video, the customary
        dress interpreters give it.

        Raises:
            ZMachineScreenError: From Version 4 on, where the
                interpreter no longer owns a status line (§8.2).
        """

        if self._version > STATUS_LAST_VERSION:
            msg = (
                f"version {self._version} draws its own status area; "
                f"the interpreter's line ends at version 3 (§8.2)"
            )

            raise ZMachineScreenError(msg)

        self._flush()

        if status.time_game:
            right = f"Time: {status.score}:{status.turns:02d}"
        else:
            right = f"Score: {status.score}  Moves: {status.turns}"

        room = status.location
        available = self._columns - len(right) - 3

        if len(room) > available:
            room = room[: max(available - 3, 0)].rstrip() + "..."

        line = f" {room}".ljust(self._columns - len(right) - 1) + right + " "
        self._grid[0] = [
            Cell(character, REVERSE) for character in line[: self._columns]
        ]
        self._damage.add(1)

    def sweep(self) -> list[int]:
        """The rows changed since the last sweep, in screen order.

        The painter's contract: repaint exactly these rows and the
        grid and glass agree again. Sweeping clears the slate.
        """

        self._flush()
        damaged = sorted(self._damage)
        self._damage.clear()

        return damaged

    def cell(self, row: int, column: int) -> Cell:
        """One grid position, pending text flushed first."""

        self._flush()

        return self._grid[row - 1][column - 1]

    def row_text(self, row: int) -> str:
        """One row's characters as a string, right side trimmed."""

        self._flush()

        return "".join(cell.character for cell in self._grid[row - 1]).rstrip()

    def rendered(self) -> str:
        """The whole screen as a text block, one line per row."""

        self._flush()

        return "\n".join(self.row_text(row) for row in range(1, self._lines + 1))

    @property
    def cursor(self) -> tuple[int, int]:
        """The selected window's cursor in screen coordinates."""

        self._flush()

        if self._selected == UPPER:
            row, column = self._upper_cursor

            return (self._upper_top() + row - 1, column)

        return self._lower_cursor
