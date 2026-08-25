"""The Glk library spoken over the GlkOte protocol, both ways.

The Page in voxam.glkote builds the updates; the composer here
walks the library the way a painted display walks it -- the same
tree, the same boxes -- and feeds the Page plain facts. What
belongs to Glk stays here: style numbers become names, terminator
keycodes become key names, and the line a request pre-filled is
read back out of its buffer.

The composer also holds the one identity the protocol demands:
GlkOte window ids are minted here, sequentially and never reused
(GlkOte: The Windows Update Array), because the windows themselves
carry no dispatch-layer identity at all.

The display itself is the GlkOteFrontend: the first display that
suspends rather than blocks. It is never asked for input; serve
runs the machine until a select stands waiting, sends the update,
and delivers whatever event the far side answers with -- JSON, one
stanza to a line, each way (GlkOte: The Application's Life Story).

The file prompt is carried: a game's ask for a file suspends the
call itself, travels as the protocol's special input, and the
player's answer -- a name, or the ever-legitimate cancel --
completes the parked call (GlkOte: Special Input Requests). So is
the player's half-typed line: every event carries it, and a field
that must be made anew takes it as its initial, so an
interruption never eats a command in progress (GlkOte: Partial
Input).

Deliberately not carried yet, each a named road: the refresh
event (this transport loses nothing); the metrics' outspacing and
inspacing (the window arrangement leaves no gaps for them); and
flow breaks, which mean nothing until buffer windows claim
images.
"""

import json
from typing import TextIO, cast

from voxam.errors import GlkOteError, GlulxGlkError, VoxamError
from voxam.glkote import (
    STYLES,
    Page,
    Stanza,
    measured,
    partials,
    read_stanza,
    write_stanza,
)
from voxam.glulx.glk.api import Glk, Prompting
from voxam.glulx.glk.frontend import Frontend
from voxam.glulx.glk.objects import (
    CHARACTER_CELL,
    BlankWindow,
    Event,
    EventType,
    FileMode,
    FileUsage,
    GraphicsWindow,
    KeyCode,
    LineRequest,
    Metrics,
    PairWindow,
    TextBufferWindow,
    TextGridWindow,
    Window,
    to_char,
)
from voxam.glulx.glk.painted import grouped
from voxam.glulx.glk.resources import ImageInfo, pictured
from voxam.glulx.glk.wrap import Segment
from voxam.glulx.machine import Machine

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

# The same keys read back: the names a line event's terminator
# wears; an unnamed ending is an ordinary Return (GlkOte: Input:
# Accepting User Events).
TERMINATOR_CODES = {name: code for code, name in TERMINATOR_NAMES.items()}

# The named keys of a char event, each to its Glk keycode; a name
# from some newer display reads as unknown (GlkOte: Input:
# Accepting User Events; Glk: Character Input).
KEY_CODES = {
    "left": KeyCode.LEFT,
    "right": KeyCode.RIGHT,
    "up": KeyCode.UP,
    "down": KeyCode.DOWN,
    "return": KeyCode.RETURN,
    "delete": KeyCode.DELETE,
    "escape": KeyCode.ESCAPE,
    "tab": KeyCode.TAB,
    "pageup": KeyCode.PAGE_UP,
    "pagedown": KeyCode.PAGE_DOWN,
    "home": KeyCode.HOME,
    "end": KeyCode.END,
    "func1": KeyCode.FUNC1,
    "func2": KeyCode.FUNC2,
    "func3": KeyCode.FUNC3,
    "func4": KeyCode.FUNC4,
    "func5": KeyCode.FUNC5,
    "func6": KeyCode.FUNC6,
    "func7": KeyCode.FUNC7,
    "func8": KeyCode.FUNC8,
    "func9": KeyCode.FUNC9,
    "func10": KeyCode.FUNC10,
    "func11": KeyCode.FUNC11,
    "func12": KeyCode.FUNC12,
}

# The highest character a Latin-1 char request can carry (Glk:
# Character Input).
_LATIN_1_TOP = 0xFF

# The events that never carry the player's partial input: the
# init by definition, and the kinds the display suppresses it on
# -- their absence of a partial means nothing (GlkOte: Partial
# Input).
_NO_PARTIAL = frozenset({"init", "specialresponse", "refresh", "debuginput"})

# A file prompt's dress in the protocol's names: Glk's file modes
# and usages, spelled the way specialinput spells them (GlkOte:
# Special Input Requests). A mode outside the four is refused the
# way the file streams refuse it.
_FILE_MODES = {
    FileMode.READ: "read",
    FileMode.WRITE: "write",
    FileMode.READ_WRITE: "readwrite",
    FileMode.WRITE_APPEND: "writeappend",
}
_FILE_KINDS = {
    FileUsage.DATA: "data",
    FileUsage.SAVED_GAME: "save",
    FileUsage.TRANSCRIPT: "transcript",
    FileUsage.INPUT_RECORD: "command",
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
            ident = self.ident(window)

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

    def ident(self, window: Window) -> int:
        """The window's GlkOte id, minted on first sight.

        Public because the display's other half needs it too: a
        drawing operation names its window before the cycle that
        declares it.
        """

        ident = self._idents.get(window)

        if ident is None:
            ident = self._next
            self._next += 1
            self._idents[window] = ident

        return ident

    def window_for(self, ident: int) -> Window | None:
        """The window an id names, while it lives; None after."""

        for held, number in self._idents.items():
            if number == ident:
                return held

        return None

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


class GlkOteFrontend(Frontend):
    """The display at the far end of the protocol.

    The first display that suspends rather than blocks: it is
    never asked for input, and its flush is a deliberate no-op --
    a select can flush more than once between updates, so nothing
    composes until render gathers the whole cycle at once. Its
    capabilities are not its own to claim: the init event's
    support list says what the far side can show, and the claims
    follow it (GlkOte: Input: Accepting User Events).
    """

    suspends = True
    # Clicks have no support token: they are core GlkOte.
    mouse_input = True

    def __init__(self) -> None:
        """Open unattached and unmeasured, before any init."""

        self.page = Page()
        self.composer = Composer()
        self._size: tuple[int, int] | None = None
        self._grid_cell = CHARACTER_CELL
        self._buffer_cell = CHARACTER_CELL
        self._graphics_cell = CHARACTER_CELL
        self._ops: dict[Window, list[Stanza]] = {}
        self._restarted = False

    def begin(self, stanza: Stanza) -> None:
        """Open the session on the init event's word.

        The support list grants the capabilities: graphicswin for
        canvases -- bare graphics means buffer-window images,
        which stay unclaimed -- timer for timers, hyperlinks for
        links (GlkOte: Input: Accepting User Events).

        Raises:
            GlkOteError: When the metrics carry no size.
        """

        support = stanza.get("support", [])
        self.timer_input = "timer" in support
        self.graphics = "graphicswin" in support
        self.hyperlink_input = "hyperlinks" in support

        self._measure(stanza)

    def _measure(self, stanza: Stanza) -> None:
        """Take the display's size and cells from its metrics.

        Every arrange carries a complete metrics object, so this
        replaces rather than amends (GlkOte: The Metrics Object).

        Raises:
            GlkOteError: When the metrics carry no size.
        """

        metrics = stanza.get("metrics", {})

        if "width" not in metrics or "height" not in metrics:
            msg = "the display's metrics carry no size (GlkOte: The Metrics Object)"

            raise GlkOteError(msg)

        self._size = (int(metrics["width"]), int(metrics["height"]))
        self._grid_cell = _cell(metrics, "grid")
        self._buffer_cell = _cell(metrics, "buffer")

        # A canvas's unit is the pixel itself; only the margins
        # come from the metrics.
        edged = _cell(metrics, "graphics")
        self._graphics_cell = Metrics(1, 1, edged.margin_x, edged.margin_y)

    def size(self) -> tuple[int, int]:
        """The display in pixels, as its init declared.

        Raises:
            GlkOteError: Before any init has been accepted.
        """

        if self._size is None:
            msg = "the display has not spoken its init yet"

            raise GlkOteError(msg)

        return self._size

    def metrics_for(self, window: Window) -> Metrics:
        """The cell for a window's kind, from the init's metrics.

        Pairs and blanks are asked too, when the tree re-lays;
        their spans are pixels pure and simple.
        """

        if isinstance(window, TextGridWindow):
            return self._grid_cell

        if isinstance(window, TextBufferWindow):
            return self._buffer_cell

        if isinstance(window, GraphicsWindow):
            return self._graphics_cell

        return CHARACTER_CELL

    def flush(self, root: Window | None) -> None:
        """Deliberately nothing: render gathers the whole cycle."""

    def read_line(self, window: Window, maxlen: int) -> tuple[str, int] | None:
        """Never called: a suspending display is never asked.

        Raises:
            GlulxGlkError: Always -- reaching here is a driver's
                bug.
        """

        del window, maxlen

        msg = "a suspending display is never asked for a line"

        raise GlulxGlkError(msg)

    def read_char(self, window: Window) -> int | None:
        """Never called: a suspending display is never asked.

        Raises:
            GlulxGlkError: Always -- reaching here is a driver's
                bug.
        """

        del window

        msg = "a suspending display is never asked for a keystroke"

        raise GlulxGlkError(msg)

    def set_timer(self, millisecs: int) -> None:
        """Note that the cadence was set anew.

        Even the same interval restarts the clock when re-asked
        (Glk: Timer Events), which polled state cannot show;
        render carries the restart through.
        """

        del millisecs

        self._restarted = True

    # -- the drawing ops, buffered until render ----------------------------

    def _settled(self, window: Window) -> None:
        """Emit a canvas's pending clear ahead of anything else.

        A clear is a whole-window fill in the background color the
        window had at the time -- which is the colorless fill,
        since the display's default fill color is exactly that
        background (GlkOte: Graphics Window Updates). It must land
        before later draws, and before any change of background.
        """

        if window.pending_clear:
            window.pending_clear = False
            self._ops.setdefault(window, []).append({"special": "fill"})

    def set_background_color(self, window: Window, color: int) -> None:
        """Set the color future clears and plain fills wear."""

        self._settled(window)
        self._ops.setdefault(window, []).append(
            {"special": "setcolor", "color": _css(color)}
        )

    def fill_rect(  # noqa: PLR0913, PLR0917 -- the six values of fill_rect
        self, window: Window, color: int, left: int, top: int, width: int, height: int
    ) -> None:
        """Fill a rectangle with a color."""

        self._settled(window)
        self._ops.setdefault(window, []).append(
            {
                "special": "fill",
                "color": _css(color),
                "x": left,
                "y": top,
                "width": width,
                "height": height,
            }
        )

    def erase_rect(
        self, window: Window, left: int, top: int, width: int, height: int
    ) -> None:
        """Erase a rectangle to the background.

        A fill with no color named fills with the display's
        default fill color -- the background, exactly (GlkOte:
        Graphics Window Updates).
        """

        self._settled(window)
        self._ops.setdefault(window, []).append(
            {"special": "fill", "x": left, "y": top, "width": width, "height": height}
        )

    def draw_image(  # noqa: PLR0913, PLR0917 -- the six values of image_draw_scaled
        self,
        window: Window,
        image: ImageInfo,
        val1: int,
        val2: int,
        width: int,
        height: int,
    ) -> bool:
        """Draw a picture on a canvas; only canvases draw here.

        The operation names the Pict by number and carries the
        picture whole as a data: url beside it (GlkOte: Graphics
        Window Updates): a host with a Blorb of its own may keep
        resolving numbers the way GiLoad does, and a host with
        none -- the desktop shell's webview -- draws from the
        update alone.
        """

        if not isinstance(window, GraphicsWindow):
            return False

        self._settled(window)
        self._ops.setdefault(window, []).append(
            {
                "special": "image",
                "image": image.number,
                "url": pictured(image),
                "x": val1,
                "y": val2,
                "width": width,
                "height": height,
            }
        )

        return True

    # -- the two halves of the conversation --------------------------------

    def render(self, *, exit: bool = False) -> Stanza:  # noqa: A002 -- the field's name
        """Compose everything since the last update into a stanza.

        The buffered drawing goes first -- dropped outright for a
        window that closed before its draws could show, which is
        also why the ops never touch the Page mid-run -- then the
        composer reads the tree, then a timer restart is re-fed,
        since the composer's own polled feeding cannot carry one.
        """

        glk = self._library()

        for window in list(self._ops):
            if window not in glk.windows:
                del self._ops[window]

        # A canvas cleared and then left alone still owes the
        # display its fill.
        for window in glk.windows:
            if isinstance(window, GraphicsWindow):
                self._settled(window)

        # The composer walks first, so ids mint in tree order; the
        # Page takes the ops in any order before the update.
        self.composer.compose(glk, self.page)

        for window, ops in self._ops.items():
            self.page.draw(self.composer.ident(window), ops)

        self._ops = {}

        if self._restarted:
            self.page.timer(glk.timer_interval, restart=True)

            self._restarted = False

        if isinstance(glk.waiting, Prompting):
            self.page.prompt(
                self._filemode(glk.waiting.fmode),
                _FILE_KINDS[glk.waiting.usage & FileUsage.TYPE_MASK],
            )

        return self.page.update(exit=exit)

    def _filemode(self, fmode: int) -> str:
        """A Glk file mode as the protocol's name for it.

        Raises:
            GlulxGlkError: For a mode that is not one of the four,
                the rule the file streams enforce (Glk: File
                Streams).
        """

        named = _FILE_MODES.get(fmode)

        if named is None:
            msg = f"a file cannot be prompted for in mode {fmode}"

            raise GlulxGlkError(msg)

        return named

    def accept(  # noqa: PLR0911 -- one return per event kind
        self, stanza: Stanza
    ) -> Event | None:
        """Translate one inbound stanza into the event it means.

        None means the stanza asks for nothing here: a stale
        generation the protocol says to ignore (GlkOte: The
        Generation Number), or a kind this face does not carry --
        refresh, external, debuginput.

        Raises:
            GlkOteError: For a window this session never showed.
            GlulxGlkError: For input no request stands to receive
                -- unreachable from a conforming display, whose
                generations shield every withdrawal.
        """

        kind = stanza.get("type")

        if kind not in _NO_PARTIAL:
            # The player's half-typed lines ride every event that
            # can carry them, a stale one included -- the typing
            # is current even when the event is not.
            self.page.typed(partials(stanza.get("partial")))

        if stanza.get("gen") != self.page.gen:
            return None

        if kind == "line":
            terminator = TERMINATOR_CODES.get(str(stanza.get("terminator")), 0)

            return self._library().deliver_line(
                self._window(stanza), str(stanza.get("value", "")), terminator
            )

        if kind == "char":
            return self._library().deliver_char(*self._keyed(stanza))

        if kind == "mouse":
            return self._library().deliver_mouse(
                self._window(stanza), int(stanza.get("x", 0)), int(stanza.get("y", 0))
            )

        if kind == "hyperlink":
            return self._library().deliver_hyperlink(
                self._window(stanza), int(stanza.get("value", 0))
            )

        if kind == "timer":
            return Event(EventType.TIMER)

        if kind == "redraw":
            # An unnamed window means every canvas, which Glk
            # spells as the null window (Glk: Window Events).
            named = self._window(stanza) if "window" in stanza else None

            return Event(EventType.REDRAW, named)

        if kind == "arrange":
            return self._rearranged(stanza)

        if kind == "specialresponse":
            self._answered(stanza)

        return None

    def _answered(self, stanza: Stanza) -> None:
        """Take a special response: the player's file name, or not.

        Completing the parked call clears the wait, which is the
        signal the serving loop reads -- there is no event to
        deliver, the call itself was the destination. A response
        to some other ask leaves the wait standing (GlkOte:
        Special Input Requests).
        """

        if stanza.get("response") != "fileref_prompt":
            return

        value = stanza.get("value")

        # A non-string value would be a browser dialog's fileref
        # object, and no dialog was invited: it reads as a cancel,
        # which is always legitimate.
        self._library().deliver_file(value if isinstance(value, str) else None)

    def _rearranged(self, stanza: Stanza) -> Event:
        """Take an arrange event: new metrics, then the re-lay.

        The re-lay may queue redraws for moved canvases before the
        arrange event lands last in the queue -- so the arrange is
        taken from the end, and the redraws drain through the next
        selects in their natural order.
        """

        self._measure(stanza)

        glk = self._library()

        glk.display_resized()

        return glk.pending_events.pop()

    def _window(self, stanza: Stanza) -> Window:
        """The window an event names.

        Raises:
            GlkOteError: For an id this session never showed.
        """

        ident = stanza.get("window")
        window = self.composer.window_for(ident) if isinstance(ident, int) else None

        if window is None:
            msg = f"no window is numbered {ident}"

            raise GlkOteError(msg)

        return window

    def _keyed(self, stanza: Stanza) -> tuple[Window, int]:
        """A char event's window and Glk character code.

        A literal character beyond Latin-1 lands as the unknown
        key when the request was not a Unicode one -- the request
        cannot carry it (Glk: Character Input).
        """

        window = self._window(stanza)
        value = stanza.get("value", "")

        if isinstance(value, str) and len(value) == 1:
            code = ord(value)

            if code > _LATIN_1_TOP and not window.char_unicode:
                code = KeyCode.UNKNOWN

            return window, code

        return window, KEY_CODES.get(str(value), KeyCode.UNKNOWN)

    def _library(self) -> Glk:
        """The attached library.

        Raises:
            GlkOteError: When no library has attached yet.
        """

        if self.glk is None:
            msg = "the display is not attached to a library"

            raise GlkOteError(msg)

        return self.glk


def serve(
    machine: Machine,
    glk: Glk,
    frontend: GlkOteFrontend,
    reader: TextIO,
    writer: TextIO,
) -> bool:
    """Drive one session over the protocol, stanza by stanza.

    JSON lines both ways: the conversation opens with the
    display's init, and thereafter the machine runs to a
    suspension, the update goes out, and the display's answer
    comes back and is delivered -- the intermittent burst model
    (GlkOte: The Application's Life Story). Every inbound stanza
    is owed a response, so one that asks for nothing is answered
    with the pass stanza rather than silence, which would starve a
    lockstep display (GlkOte: Output: Updating the Display).

    True is a session that ended cleanly -- the story quit, or the
    display hung up. A broken conversation answers the protocol's
    own error stanza and is False.
    """

    try:
        opening = read_stanza(reader)

        if opening is None or opening.get("type") != "init":
            msg = (
                "the conversation opens with an init event "
                "(GlkOte: The Application's Life Story)"
            )

            raise GlkOteError(msg)

        frontend.begin(opening)

        while True:
            machine.run()

            write_stanza(writer, frontend.render(exit=not machine.running))

            if not machine.running:
                return True

            while True:
                stanza = read_stanza(reader)

                if stanza is None:
                    # The display hung up: the session ends the
                    # way a closed window ends it.
                    return True

                event = frontend.accept(stanza)

                if event is not None:
                    glk.deliver_event(event)

                    break

                if glk.waiting is None:
                    # The stanza itself completed the wait: a file
                    # answer stores through the parked call, and
                    # the machine can simply step on.
                    break

                write_stanza(writer, {"type": "pass"})
    except json.JSONDecodeError as error:
        write_stanza(writer, {"type": "error", "message": f"voxam: not JSON: {error}"})

        return False
    except VoxamError as error:
        write_stanza(writer, {"type": "error", "message": f"voxam: {error}"})

        return False


def _css(color: int) -> str:
    """A Glk color word as the CSS string the protocol draws with.

    Masked to its low three bytes: a color is 0x00RRGGBB (Glk:
    Suggesting Colors of Styles).
    """

    return f"#{color & 0xFFFFFF:06X}"


def _cell(metrics: Stanza, prefix: str) -> Metrics:
    """One window kind's cell, the shared measure worn as Metrics."""

    return Metrics(*measured(metrics, prefix))


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
