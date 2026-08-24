"""The Glk library read out as GlkOte updates.

The Page in voxam.glkote speaks the protocol; the composer here
walks the library the way a painted display walks it -- the same
tree, the same boxes -- and feeds the Page plain facts. What
belongs to Glk stays here: style numbers become names, terminator
keycodes become key names, and the line a request pre-filled is
read back out of its buffer.

The composer also holds the one identity the protocol demands:
GlkOte window ids are minted here, sequentially and never reused
(GlkOte: The Windows Update Array), because the windows themselves
carry no dispatch-layer identity at all.
"""

from typing import cast

from voxam.glkote import STYLES, Page
from voxam.glulx.glk.api import Glk
from voxam.glulx.glk.objects import (
    BlankWindow,
    KeyCode,
    LineRequest,
    PairWindow,
    TextBufferWindow,
    TextGridWindow,
    Window,
    to_char,
)
from voxam.glulx.glk.painted import grouped
from voxam.glulx.glk.wrap import Segment

# The terminator keys the protocol can name; Glk's other specials
# are dropped from the request, which a library may do (Glk: Line
# Input Events; GlkOte: The Input Update Array).
TERMINATOR_NAMES = {
    KeyCode.ESCAPE: "escape",
    KeyCode.FUNC1: "func1",
    KeyCode.FUNC2: "func2",
    KeyCode.FUNC3: "func3",
    KeyCode.FUNC4: "func4",
    KeyCode.FUNC5: "func5",
    KeyCode.FUNC6: "func6",
    KeyCode.FUNC7: "func7",
    KeyCode.FUNC8: "func8",
    KeyCode.FUNC9: "func9",
    KeyCode.FUNC10: "func10",
    KeyCode.FUNC11: "func11",
    KeyCode.FUNC12: "func12",
}


class Composer:
    """Reads a Glk library into a Page, one cycle per flush.

    The buffer drain makes the composer the display's sole reader:
    take_content empties what it reports, so no painted display
    can share the same library.
    """

    def __init__(self) -> None:
        """Open with no windows known and the first id unminted."""

        self._idents: dict[Window, int] = {}
        self._next = 1

    def compose(self, glk: Glk, page: Page) -> None:
        """Feed the library's whole face to the Page, one cycle.

        Pairs and blanks stay home -- the protocol's window list
        is flat and knows only the three drawn kinds (GlkOte: The
        Windows Update Array) -- and a window gone from the tree
        goes undeclared, which is how the Page learns it closed.
        """

        for window in _visible(glk.root):
            ident = self._ident(window)

            if isinstance(window, TextGridWindow):
                self._grid(page, ident, window)
            elif isinstance(window, TextBufferWindow):
                self._buffer(page, ident, window)
            else:
                self._graphics(page, ident, window)

            self._asked(page, ident, window)

        page.timer(glk.timer_interval)

        # A closed window's memo goes with it; the counter never
        # rewinds, so its id stays retired.
        self._idents = {
            held: ident for held, ident in self._idents.items() if held in glk.windows
        }

    def _ident(self, window: Window) -> int:
        """The window's GlkOte id, minted on first sight."""

        ident = self._idents.get(window)

        if ident is None:
            ident = self._next
            self._next += 1
            self._idents[window] = ident

        return ident

    def _grid(self, page: Page, ident: int, window: TextGridWindow) -> None:
        """Declare a grid and feed its whole face; the Page diffs."""

        page.window(
            ident,
            "grid",
            window.rock,
            window.bbox,
            gridsize=(window.width, window.height),
        )

        page.grid(
            ident,
            [
                _dressed(
                    grouped(
                        window.lines[index], window.styles[index], window.links[index]
                    )
                )
                for index in range(len(window.lines))
            ],
        )

    def _buffer(self, page: Page, ident: int, window: TextBufferWindow) -> None:
        """Declare a buffer and drain its new text into the Page."""

        page.window(ident, "buffer", window.rock, window.bbox)

        clear = window.pending_clear
        window.pending_clear = False
        runs = window.take_content()

        if runs or clear:
            page.buffer(
                ident,
                [(_styled(run.style), run.hyperlink, run.text) for run in runs],
                clear=clear,
            )

    def _graphics(self, page: Page, ident: int, window: Window) -> None:
        """Declare a graphics window by its drawable size.

        The canvas's own pending clear stays untouched: a clear is
        a fill with the background color, and that color lives
        with the display that draws, not with the model.
        """

        cell = window.metrics
        page.window(
            ident,
            "graphics",
            window.rock,
            window.bbox,
            graphsize=(
                max(0, int(window.width - cell.margin_x)),
                max(0, int(window.height - cell.margin_y)),
            ),
        )

    def _asked(self, page: Page, ident: int, window: Window) -> None:
        """Translate a window's outstanding requests, if any.

        Clicks are suppressed for buffers -- "buffer windows do
        not support mouse-click input" (GlkOte: The Input Update
        Array) -- and grid input carries the cursor, clamped into
        the grid the way the painted displays clamp it.
        """

        linked = window.hyperlink_request
        clicked = window.mouse_request and not isinstance(window, TextBufferWindow)
        cursor = _caret(window)

        if window.line_request is not None:
            page.line_input(
                ident,
                window.line_request.capacity,
                initial=_initial(window.line_request),
                terminators=_named_terminators(window.line_request.terminators),
                cursor=cursor,
                hyperlink=linked,
                mouse=clicked,
            )
        elif window.char_request:
            page.char_input(ident, cursor=cursor, hyperlink=linked, mouse=clicked)
        else:
            page.passive_input(ident, hyperlink=linked, mouse=clicked)


def _visible(window: Window | None) -> "list[Window]":
    """The drawn windows of a tree, in tree order."""

    if window is None or isinstance(window, BlankWindow):
        return []

    if isinstance(window, PairWindow):
        return [*_visible(window.child1), *_visible(window.child2)]

    return [window]


def _dressed(segments: "list[Segment]") -> "list[tuple[str, int, str]]":
    """Painted segments as protocol runs: the key opened, the style named."""

    runs: list[tuple[str, int, str]] = []

    for key, text in segments:
        style, link = cast("tuple[int, int]", key)

        runs.append((_styled(style), link, text))

    return runs


def _styled(style: int) -> str:
    """A Glk style number as its protocol name.

    A number beyond the eleven renders normal, exactly as the
    painted displays render it plain (Glk: Styles).
    """

    return STYLES[style] if 0 <= style < len(STYLES) else "normal"


def _caret(window: Window) -> "tuple[int, int] | None":
    """A grid's input position, clamped inside it; None elsewhere."""

    if not isinstance(window, TextGridWindow):
        return None

    return (
        min(window.cursor_x, max(0, window.width - 1)),
        min(window.cursor_y, max(0, window.height - 1)),
    )


def _initial(request: LineRequest) -> str:
    """The text a line request arrived pre-filled with."""

    buf = request.buf

    if buf is None:
        return ""

    return "".join(
        to_char(buf[index]) for index in range(min(request.initlen, len(buf)))
    )


def _named_terminators(terminators: "tuple[int, ...]") -> "tuple[str, ...]":
    """Glk terminator keycodes as protocol key names, the rest dropped."""

    return tuple(
        TERMINATOR_NAMES[keycode]
        for keycode in terminators
        if keycode in TERMINATOR_NAMES
    )
