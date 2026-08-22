"""Word wrapping for text buffer windows.

Buffer windows wrap: the game emits a stream of styled characters
and the display decides where the lines break (Glk: Text Buffer
Windows). Only a display knows its width, so wrapping belongs on
the display side -- but every painted display needs the same
thing, so it lives here rather than being written twice.

Two things make this more than a call to textwrap.wrap. Text
arrives in pieces: a window hands over whatever accumulated since
the last flush, which may stop mid-word, so the wrapper keeps the
unfinished paragraph and folds the next piece into it. And text is
styled: breaking a line has to cut the *segments* that make it up,
not a flat string, or the emphasis moves -- so the breaks are
found in the plain text and the segments sliced to match.

The wrapper also keeps the paragraphs it has been given, which is
what makes a resize exact: display lines are recomputed from the
original text rather than re-broken from lines that already lost
their spaces at the break points.
"""

from collections.abc import Iterable, Sequence
from typing import NamedTuple

Segment = tuple[object, str]
"""A run of text sharing one appearance: (key, text).

The key is whatever the display wants to distinguish runs by, and
is only ever compared for equality here -- a Glk style number for
a terminal, something richer for a display that knows links.
"""


class View(NamedTuple):
    """What a window should be showing at this moment.

    Attributes:
        lines: The display lines to show, oldest first.
        start: The index in the wrapper's lines that these begin
            at, for anything anchored to a line number.
        more: Whether text is waiting that this view could not
            fit -- what a pause prompt announces.
    """

    lines: list[list[Segment]]
    start: int
    more: bool


# How many completed paragraphs to remember. Past this the oldest
# are dropped -- a terminal cannot scroll back to them anyway, and
# a long game would otherwise accumulate its entire transcript.
SCROLLBACK = 2000
_TRIM = 200


def _spans(text: str, width: int) -> list[tuple[int, int]]:
    """Index ranges of text, one per display line.

    Newlines are consumed, as is the space at each break. A word
    wider than the line is cut rather than left to overflow.
    """

    width = max(width, 1)
    spans: list[tuple[int, int]] = []
    position = 0
    length = len(text)

    while True:
        newline = text.find("\n", position)
        end = length if newline < 0 else newline
        start = position

        while end - start > width:
            limit = start + width
            # The break may fall on the character just past the
            # line, since a space there costs nothing to drop.
            point = text.rfind(" ", start, limit + 1)

            if point <= start:
                spans.append((start, limit))
                start = limit
            else:
                spans.append((start, point))
                start = point + 1

        spans.append((start, end))

        if newline < 0:
            return spans

        position = newline + 1


def wrap(text: str, width: int) -> list[str]:
    """Break text into lines of at most width characters."""

    return [text[start:end] for start, end in _spans(text, width)]


def wrap_segments(segments: Sequence[Segment], width: int) -> list[list[Segment]]:
    """Break one styled paragraph into styled display lines."""

    if not segments:
        return [[]]

    text = "".join(chunk for _, chunk in segments)
    starts: list[int] = []
    position = 0

    for _, chunk in segments:
        starts.append(position)
        position += len(chunk)

    lines: list[list[Segment]] = []

    for begin, finish in _spans(text, width):
        line: list[Segment] = []

        for index, (key, chunk) in enumerate(segments):
            at = starts[index]
            to = at + len(chunk)

            if to <= begin or at >= finish:
                continue

            piece = chunk[max(begin, at) - at : min(finish, to) - at]

            if piece:
                line.append((key, piece))

        lines.append(line)

    return lines


def plain(line: Iterable[Segment]) -> str:
    """The text of a display line, without its styling."""

    return "".join(chunk for _, chunk in line)


class Wrapper:
    """Accumulates one window's styled output and wraps it to a width.

    Keeps every paragraph, because a full-screen display repaints
    from scratch and cannot re-ask the window for text it has
    already drained.

    Attributes:
        width: The width lines are currently wrapped to.
        seen: How many display lines the player has been shown.
            Everything before this has had its turn on screen;
            text past it that will not fit in one windowful is
            what a pause prompt is for -- see view.
    """

    def __init__(self, width: int = 80) -> None:
        """Start empty, wrapping to the given width."""

        self.width = max(1, width)
        # Completed paragraphs, and the one still being written.
        self._history: list[list[Segment]] = []
        self._current: list[Segment] = []
        # Wrapped forms of each, recomputed only when they change.
        self._done: list[list[Segment]] | None = []
        self._tail: list[list[Segment]] | None = None
        self.seen = 0

    def add(self, runs: Iterable[Segment]) -> None:
        """Fold more styled output in, continuing the open paragraph."""

        for key, text in runs:
            if not text:
                continue

            pieces = text.split("\n")
            self._extend(key, pieces[0])

            for piece in pieces[1:]:
                self._break_paragraph()
                self._extend(key, piece)

        self._tail = None

    def _extend(self, key: object, text: str) -> None:
        if not text:
            return

        if self._current and self._current[-1][0] == key:
            self._current[-1] = (key, self._current[-1][1] + text)
        else:
            self._current.append((key, text))

    def _break_paragraph(self) -> None:
        self._history.append(self._current)

        if self._done is not None:
            self._done.extend(wrap_segments(self._current, self.width))

        self._current = []

        if len(self._history) > SCROLLBACK + _TRIM:
            # Trimmed in batches, so this is not paid on every line.
            del self._history[:_TRIM]
            self._done = None

    @property
    def lines(self) -> list[list[Segment]]:
        """Every display line, oldest first."""

        if self._done is None:
            self._done = [
                line
                for paragraph in self._history
                for line in wrap_segments(paragraph, self.width)
            ]

        if self._tail is None:
            self._tail = wrap_segments(self._current, self.width)

        return self._done + self._tail

    def preview(self, runs: Sequence[Segment]) -> list[list[Segment]]:
        """The display lines as if runs had been added, without adding.

        A display draws the line the player is typing this way: it
        is part of the layout, but it is not part of the window's
        contents until the game accepts it.
        """

        if not runs:
            return self.lines

        lines = self.lines

        return lines[: len(lines) - len(self._tail or [[]])] + wrap_segments(
            [*self._current, *runs], self.width
        )

    # A window shows a windowful. If the game prints more than that
    # between two chances for the player to read, the excess would
    # scroll past unread, so the display stops and waits. The model
    # is glkterm's lastseenline: seen is the high-water mark of what
    # has been shown, and text beyond it that will not fit is what
    # holds things up.

    def view(self, height: int) -> View:
        """What to show now, where it starts, and whether more waits.

        Calling this *is* the display showing them, so it advances
        seen -- but only when there is nothing left waiting. While
        there is, the view stays put until advance is called, which
        is what makes the pause a pause.
        """

        lines = self.lines

        if height <= 0:
            return View([], 0, False)

        if len(lines) - self.seen <= height:
            # Everything unseen fits: show the newest windowful,
            # and the player has now had the lot. Idempotent, which
            # matters -- a repaint happens on every keystroke.
            self.seen = len(lines)
            start = max(0, len(lines) - height)

            return View(lines[start:], start, False)

        start = self._page_start()

        return View(lines[start : start + self._page(height)], start, True)

    def advance(self, height: int) -> None:
        """The player has read a page; move on to the next.

        Always at least one line further on. In a window one or two
        lines tall the page and the overlap are both a single line,
        and without this the pair cancel out and the prompt never
        clears.
        """

        page = self._page_start() + self._page(height)
        self.seen = min(len(self.lines), max(self.seen + 1, page))

    def catch_up(self) -> None:
        """Treat everything as read, however much of it there is.

        For the moments when pausing would be wrong: a file prompt,
        or a window the game has just cleared.
        """

        self.seen = len(self.lines)

    def _page(self, height: int) -> int:
        """Lines of text per page: the window, less the prompt's line."""

        return max(1, height - 1)

    def _page_start(self) -> int:
        # One line of overlap, so the page break does not read as a
        # gap.
        return max(0, self.seen - 1)

    def resize(self, width: int) -> None:
        """Re-wrap everything for a new width."""

        width = max(1, width)

        if width == self.width:
            return

        self.width = width
        self._done = None
        self._tail = None

    def clear(self) -> None:
        """Forget everything, as a cleared window has."""

        self._history = []
        self._current = []
        self._done = []
        self._tail = None
        self.seen = 0
