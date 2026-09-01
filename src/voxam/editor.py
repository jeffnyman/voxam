"""The interpreter's line editor for painted input (§15 read).

Line editing belongs to the interpreter, not the machine: §15 read
hands whole lines to the game, and how the player composes one --
moving the cursor within it, correcting the middle, recalling an
earlier command -- is interpreter courtesy, the same courtesy the
classic interpreters offered. The editor here is pure state: a
buffer, an insertion point, and a session history, with each
keystroke a small transition, so the whole vocabulary is testable
without a terminal. The painted frontends translate transitions
onto their glass; recordings and replays never meet the editor,
because only the submitted line reaches the machine.

The cursor keys do double duty on the Z-Machine: §3.8.4 defines
them as input characters so a game like Beyond Zork can hear them
in read_char menus. Single-keystroke reads still pass them through
whole -- the editor lives only inside line input, where today no
key can reach the game before the line is done. When §10.7
terminating characters arrive, a game that names the cursor keys
as terminators will take precedence over the editor's use of them.
"""

from collections.abc import Callable
from typing import Protocol

# The editing vocabulary, in §3.8 input characters: both classic
# delete bytes rub out, the cursor keys move and recall, and escape
# with the remaining §3.8.4 input-only codes means nothing to a
# line and is waited out.
RUB_OUT_KEYS = ("\x7f", "\x08")
CURSOR_UP = "\x81"
CURSOR_DOWN = "\x82"
CURSOR_LEFT = "\x83"
CURSOR_RIGHT = "\x84"
INPUT_ONLY_FIRST = "\x81"
INPUT_ONLY_LAST = "\x9a"
ESCAPE = "\x1b"
NEWLINE = "\n"
# A bare carriage return IS the return key -- ZSCII 13 (§3.8.2.5)
# -- on a terminal that hands it over without naming it.
CARRIAGE_RETURN = "\r"

# A session keeps this many submitted lines for recall.
HISTORY_LIMIT = 100

# A key source may answer this instead of a key to say a timed
# wait expired (§15 read): the loop hands back None with the
# composed line intact, so the read can resume after the game's
# interrupt has run. NUL can never arrive as real typing.
EXPIRED = "\x00"


class LineCanvas(Protocol):
    """What the editor needs from a screen model to echo edits."""

    def write(self, text: str) -> None:
        """Print text at the cursor."""

    def retreat(self, cells: int) -> int:
        """Move the cursor left without erasing; answer cells moved."""

        ...


class LineEditor:
    """A line being composed, with the session's history behind it.

    One editor lives per frontend, so the history spans the whole
    session: every submitted line joins it, and the cursor-up key
    walks back through it the way every shell since has. Recalling
    preserves the interrupted draft -- cursor-down past the newest
    history line restores it.
    """

    def __init__(self) -> None:
        """Start with an empty line and an empty session history."""

        self._history: list[str] = []
        self._buffer: list[str] = []
        self._cursor = 0
        self._recall: int | None = None
        self._draft = ""

    @property
    def text(self) -> str:
        """The line as composed so far."""

        return "".join(self._buffer)

    @property
    def cursor(self) -> int:
        """The insertion point, in characters from the line's start."""

        return self._cursor

    def begin(self) -> None:
        """Start composing a fresh, empty line."""

        self._buffer = []
        self._cursor = 0
        self._recall = None
        self._draft = ""

    def insert(self, character: str) -> None:
        """Type one character at the insertion point."""

        self._buffer.insert(self._cursor, character)
        self._cursor += 1

    def rub_out(self) -> bool:
        """Delete the character before the insertion point.

        Returns:
            Whether anything was deleted; at the line's start there
            is nothing left of the line to rub.
        """

        if self._cursor == 0:
            return False

        self._cursor -= 1
        del self._buffer[self._cursor]

        return True

    def left(self) -> bool:
        """Move the insertion point one character left."""

        if self._cursor == 0:
            return False

        self._cursor -= 1

        return True

    def right(self) -> bool:
        """Move the insertion point one character right."""

        if self._cursor == len(self._buffer):
            return False

        self._cursor += 1

        return True

    def earlier(self) -> bool:
        """Recall the previous history line, saving the draft first.

        Returns:
            Whether the line changed; with no history, or at the
            oldest line already, there is nothing earlier.
        """

        if self._recall is None:
            if not self._history:
                return False

            self._draft = self.text
            self._recall = len(self._history) - 1
        elif self._recall > 0:
            self._recall -= 1
        else:
            return False

        self._buffer = list(self._history[self._recall])
        self._cursor = len(self._buffer)

        return True

    def later(self) -> bool:
        """Walk forward through history, back to the saved draft.

        Returns:
            Whether the line changed; without a recall in progress
            there is nothing later to return to.
        """

        if self._recall is None:
            return False

        self._recall += 1

        if self._recall == len(self._history):
            self._recall = None
            self._buffer = list(self._draft)
        else:
            self._buffer = list(self._history[self._recall])

        self._cursor = len(self._buffer)

        return True

    def submit(self) -> str:
        """Finish the line: record it in history and reset.

        An empty line never joins the history, and a line matching
        the newest entry joins only once -- pressing cursor-up
        after repeating a command should not walk through the
        repetitions.

        Returns:
            The submitted line.
        """

        line = self.text

        if line and (not self._history or self._history[-1] != line):
            self._history.append(line)

            if len(self._history) > HISTORY_LIMIT:
                del self._history[0]

        self.begin()

        return line


# The editing keys, each naming its LineEditor transition. Every
# transition answers whether the line changed -- the loop redraws
# only when one did.
EDITS: dict[str, Callable[[LineEditor], bool]] = {
    RUB_OUT_KEYS[0]: LineEditor.rub_out,
    RUB_OUT_KEYS[1]: LineEditor.rub_out,
    CURSOR_UP: LineEditor.earlier,
    CURSOR_DOWN: LineEditor.later,
    CURSOR_LEFT: LineEditor.left,
    CURSOR_RIGHT: LineEditor.right,
}


def read_line_edited(
    editor: LineEditor,
    canvas: LineCanvas,
    key_source: Callable[[], str | None],
    repaint: Callable[[], None],
    *,
    fresh: bool = True,
) -> str | None:
    """Run one line read through the editor, echoing via the canvas.

    The shared loop behind both painted frontends: keys arrive raw
    from the frontend's own source, the editor transitions, and any
    visible change is redrawn through the canvas -- so nothing but
    the frontend ever writes to its glass. Appending at the line's
    end takes the fast path of a single write; every other edit
    repaints the line whole from its start. The canvas's retreat
    stops at the left edge, as its rub_out always has, so on the
    rare line that wrapped only the final row redraws -- the
    returned line is right regardless, because the buffer, not the
    glass, is what the game receives.

    A key source that answers EXPIRED ends the call with None: the
    composed line stays in the editor and on the glass, and a later
    call with fresh=False resumes it exactly where it stood -- how
    a timed read survives its interrupts (§15 read).
    """

    if fresh:
        editor.begin()
        painted = 0  # cells on the glass since the line began
        at = 0  # the canvas cursor, in cells from the line's start
    else:
        painted = len(editor.text)
        at = editor.cursor

    def redraw() -> None:
        nonlocal painted, at

        canvas.retreat(at)
        text = editor.text
        canvas.write(text)

        remnant = painted - len(text)

        if remnant > 0:
            canvas.write(" " * remnant)
            canvas.retreat(remnant)

        canvas.retreat(len(text) - editor.cursor)
        painted = len(text)
        at = editor.cursor
        repaint()

    while True:
        key = key_source()

        if key == EXPIRED:
            return None

        if key is None or key == ESCAPE:
            continue

        if key in (NEWLINE, CARRIAGE_RETURN):
            canvas.write(NEWLINE)
            repaint()

            return editor.submit()

        edit = EDITS.get(key)

        if edit is not None:
            if edit(editor):
                redraw()
        elif key < " " or (INPUT_ONLY_FIRST <= key <= INPUT_ONLY_LAST):
            # The §3.8.4 input-only codes beyond the editing keys,
            # and every raw control character -- the tab chief
            # among them -- mean nothing to a line: no ZSCII code
            # to submit (§3.8), no glyph to echo, so they are
            # waited out rather than inserted to crash at submit.
            continue
        else:
            appending = editor.cursor == len(editor.text)
            editor.insert(key)

            if appending:
                canvas.write(key)
                painted += 1
                at += 1
                repaint()
            else:
                redraw()
