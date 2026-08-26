"""The Z-Machine spoken over the GlkOte protocol, both ways.

The same Page the Glulx composer feeds, fed from the §8 screen
model: the upper window and the Version 1 to 3 status line travel
as the protocol's grid window, read out of the ScreenModel that
already knows every splitting and cursor rule, while the lower
window's text -- which GlkOte wraps and scrolls itself -- never
enters the model at all and accumulates as styled runs instead.

The reads ride the suspension seam: the machine stands down at a
read, the update carries the ask -- the counted buffer's preload
as the field's initial -- and the display's answer is delivered
straight to the machine, echoed here first, since the machine
never echoes and the display owes the typed line and its newline.
The saves stand down the same way: a §15 save or restore asks for
its file through the protocol's special input, and the answered
path -- or the cancel -- runs the parked rider.

The arc_image band hangs here too: a story whose sidecar carries
pictures plays them in a graphics window above the whole screen --
the picture inlined as a data: url, the grid and buffer re-based
below, the header's rows updated as the contract asks (arc_image:
the contract, part A).

Deliberately not carried, each refused honestly at the claims: the
Version 6 stage (the painted glasses keep it), colours, the Z
mouse, sound, and §13.7's terminating characters -- a line here
ends at Return.
"""

import json
from collections.abc import Sequence
from typing import TextIO

from voxam.errors import GlkOteError, VoxamError
from voxam.frontend import (
    ARC_MODES,
    ARC_PIXEL_ROWS,
    ARC_REFERENCE_WIDTH,
    PlainFrontend,
    Status,
)
from voxam.glkote import (
    Page,
    Stanza,
    measured,
    partials,
    read_stanza,
    write_stanza,
)
from voxam.glulx.glk.resources import Resources
from voxam.screen import BOLD, FIXED_PITCH, ITALIC, REVERSE, UPPER, ScreenModel
from voxam.zmachine.header import STATUS_FLAGS_VERSION
from voxam.zmachine.machine import Filing, Machine, Reading
from voxam.zmachine.story import Story

# The verdicts accept hands the serving loops: run the machine on,
# render the standing picture, or answer the pass stanza.
ADVANCE = "advance"
STAND = "stand"
PASS = "pass"  # noqa: S105 -- a verdict, not a secret

# The named keys of a char event, each as the §3.8 input character
# ZSCII spells it; a name outside this table is a key the story
# cannot hear.
ZSCII_KEYS = {
    "up": chr(129),
    "down": chr(130),
    "left": chr(131),
    "right": chr(132),
    "return": chr(13),
    "delete": chr(8),
    "escape": chr(27),
    "func1": chr(133),
    "func2": chr(134),
    "func3": chr(135),
    "func4": chr(136),
    "func5": chr(137),
    "func6": chr(138),
    "func7": chr(139),
    "func8": chr(140),
    "func9": chr(141),
    "func10": chr(142),
    "func11": chr(143),
    "func12": chr(144),
}

# The §10.5.2.1 terminating characters the wire can name: the
# twelve function keys alone -- a table's cursor, keypad, and
# click codes have no terminator names in the protocol's
# vocabulary, so those stay unoffered here (GlkOte: Input Events).
TERMINATOR_NAMES = {code: f"func{code - 132}" for code in range(133, 145)}

# The same keys read back: a line event's terminator name as the
# ZSCII code the read stores; any other name reads as a plain
# new-line ending.
TERMINATOR_CODES = {name: code for code, name in TERMINATOR_NAMES.items()}

# One §15 tenth of a second, in the protocol's milliseconds.
_TENTH_MS = 100


# The events that never carry the player's partial input (GlkOte:
# Partial Input).
_NO_PARTIAL = frozenset({"init", "specialresponse", "refresh", "debuginput"})

# The buffer window's protocol id; the grid's ids are minted
# fresh at every reopening, since the protocol forbids reuse.
_BUFFER = 1


class GlkOteFrontend(PlainFrontend):
    """The Z display at the far end of the protocol.

    Suspends like its Glk twin: never asked for input, its picture
    gathered whole at render. The upper half of the screen lives
    in a ScreenModel; the lower half is a stream of styled runs.
    """

    suspends = True
    has_status_line = True
    has_screen_splitting = True
    has_bold = True
    has_italic = True
    has_fixed_pitch = True

    def __init__(self, version: int, resources: Resources | None = None) -> None:
        """Open unmeasured, before any init; the model comes sized."""

        super().__init__(lambda _text: None)

        self.version = version
        self.page = Page()
        self.machine: Machine | None = None
        self._resources = resources
        self._model = ScreenModel(
            columns=self.screen_columns, lines=24, version=version
        )
        self._runs: list[tuple[str, int, str] | object] = []
        self._cleared = False
        self._style = 0
        self._size = (0, 0)
        self._cell = (1.0, 1.0)
        self._margins = (0.0, 0.0)
        self._grid_ident: int | None = None
        self._next_ident = _BUFFER + 1
        self._last_read: object = None
        # The arc_image band: the hanging (picture, mode), the
        # canvas id it wears -- minted fresh at every reopening --
        # and whether its drawing still owes the display.
        self._band: tuple[int, int] | None = None
        self._band_ident: int | None = None
        self._band_dirty = False

    # -- the conversation's opening ----------------------------------------

    def begin(self, stanza: Stanza) -> None:
        """Open the session on the init event's word.

        The screen's size in cells is settled here, before any
        machine is booted over this display -- the header reads it
        once at boot (§8.4).

        Raises:
            GlkOteError: When the metrics carry no size.
        """

        support = stanza.get("support", [])
        self.has_timed_input = "timer" in support

        # The band's claim is honest twice over: pictures must
        # actually hang behind the story, and the display must
        # speak graphics windows (arc_image: the contract).
        self.has_arc_images = (
            self._resources is not None
            and self._resources.blorb is not None
            and "graphicswin" in support
        )

        self._measure(stanza)

        self._model = ScreenModel(
            columns=self.screen_columns, lines=self.screen_lines, version=self.version
        )

    def _measure(self, stanza: Stanza) -> None:
        """Take the display's size and cells from its metrics.

        Raises:
            GlkOteError: When the metrics carry no size.
        """

        metrics = stanza.get("metrics", {})

        if "width" not in metrics or "height" not in metrics:
            msg = "the display's metrics carry no size (GlkOte: The Metrics Object)"

            raise GlkOteError(msg)

        width, height, margin_x, margin_y = measured(metrics, "grid")

        self._size = (int(metrics["width"]), int(metrics["height"]))
        self._cell = (width, height)
        self._margins = (margin_x, margin_y)
        self.screen_columns = max(1, int((self._size[0] - margin_x) // width))
        self.screen_lines = max(1, int((self._size[1] - margin_y) // height))

    # -- the screen ops, §8 through the model ------------------------------

    def write(self, text: str) -> None:
        """Story text: the upper window's goes into the model.

        The lower window's joins the stream of styled runs the
        display wraps for itself.
        """

        if self._model.selected == UPPER:
            self._model.write(text)
        else:
            self._runs.append((_named(self._style), 0, text))

    def write_rectangle(self, rows: Sequence[str]) -> None:
        """§15 print_table: stamped in the upper, stacked below."""

        if self._model.selected == UPPER:
            self._model.write_rectangle(rows)
        else:
            for row in rows:
                self._runs.append((_named(self._style), 0, row + "\n"))

    def show_status(self, status: Status) -> None:
        """The §8.2 status line, drawn onto the model's top row."""

        self._model.show_status(status)

    def set_style(self, style: int) -> None:
        """§8.7.1 combining: zero clears, anything else joins."""

        self._model.set_style(style)
        self._style = 0 if style == 0 else self._style | style

    def set_font(self, font: int) -> None:
        """Fonts route to the model; the dress keys on styles."""

        self._model.set_font(font)

    def erase_window(self, window: int) -> None:
        """An erasure of the lower half clears the buffer whole."""

        self._model.erase_window(window)

        if window != UPPER:
            self._runs.clear()
            self._cleared = True

    def erase_line(self, pixels: int | None = None) -> None:  # noqa: ARG002 -- v6's unit never reaches this display
        """To the end of the line -- meaningful in the grid alone."""

        if self._model.selected == UPPER:
            self._model.erase_line()

    def set_buffering(self, buffered: bool) -> None:
        """The display wraps for itself; the model need not."""

    def draw_arc_image(self, image: int, mode: int) -> None:
        """Hang, replace, or clear the arc_image band.

        Id 0 takes the band down; an id no picture answers, or a
        mode outside the two named, is ignored where it lands --
        presentation, never state (arc_image: the contract). A
        change re-bases the screen: the header's rows shrink to
        what stands below the band, or grow back at a clear.
        """

        if mode not in ARC_MODES:
            return

        if image == 0:
            hung = None
        elif self._resources is None or self._resources.image(image) is None:
            return
        else:
            hung = (image, mode)

        if hung == self._band:
            return

        self._band = hung
        self._band_dirty = True

        self._rebased()

    def _band_height(self) -> int:
        """The band's height in display pixels, aspect held true.

        The art is mode x 8 rows tall at the 320-pixel reference
        width; the display's band keeps that shape at its own
        width (arc_image: the contract).
        """

        if self._band is None:
            return 0

        width, _ = self._size
        _, mode = self._band

        return round(width * mode * ARC_PIXEL_ROWS / ARC_REFERENCE_WIDTH)

    def _rebased(self) -> None:
        """Tell the header how many rows stand below the band.

        The first draw re-bases the screen and a clear gives the
        rows back; the header's height field follows, exactly as
        for any screen change (arc_image: the contract).
        """

        if self.machine is None:
            return

        _, height = self._size
        _, cell_h = self._cell

        below = int((height - self._band_height() - self._margins[1]) // cell_h)

        # One byte of header, and 255 already means "infinite"
        # there (§8.4): the claim stays inside both bounds.
        self.machine.memory.header.declare_screen_size(
            lines=max(1, min(below, 255)), columns=self.screen_columns
        )

    def split_window(self, lines: int) -> None:
        """Resize the upper window (§8.7.2.1); the model rules."""

        self._model.split_window(lines)

    def set_window(self, window: int) -> None:
        """Select the window taking the next printing (§8.7.2)."""

        self._model.set_window(window)

    def set_cursor(self, line: int, column: int) -> None:
        """Place the upper window's cursor (§8.7.2.3)."""

        self._model.set_cursor(line, column)

    def cursor_position(self) -> tuple[int, int]:
        """What get_cursor reads back: the model's own ledger."""

        return self._model.get_cursor()

    # -- the two halves of the conversation --------------------------------

    def render(self, *, exit: bool = False) -> Stanza:  # noqa: A002 -- the field's name
        """Compose everything since the last update into a stanza.

        The grid is the status chrome plus the split; one that
        closes and reopens is a new window with a new id, the
        protocol forbidding reuse (GlkOte: The Windows Update
        Array).
        """

        machine = self._machine()
        width, height = self._size
        _, cell_h = self._cell
        rows = self._grid_rows()

        # The band hangs above everything: grid and buffer alike
        # re-base below it (arc_image: the contract, part A).
        band_h = self._banded(width)

        # A grid's box carries its rows plus the display's own
        # interior margins (GlkOte: The Metrics Object); a box of
        # bare rows clips its bottom and floats the buffer up
        # into the status line.
        brow = band_h + (int(rows * cell_h + self._margins[1]) if rows else 0)

        self.page.window(_BUFFER, "buffer", 0, (0, brow, width, height))

        if rows:
            if self._grid_ident is None:
                self._grid_ident = self._next_ident
                self._next_ident += 1

            self.page.window(
                self._grid_ident,
                "grid",
                0,
                (0, band_h, width, brow),
                gridsize=(self.screen_columns, rows),
            )
            self.page.grid(self._grid_ident, self._faced(rows))
        else:
            self._grid_ident = None

        if self._runs or self._cleared:
            self.page.buffer(_BUFFER, self._runs, clear=self._cleared)

            self._runs = []
            self._cleared = False

        waiting = machine.waiting

        if isinstance(waiting, Filing):
            # A save or restore asks for its file through the
            # protocol's special input; the display disables the
            # game until the answer comes back (GlkOte: Special
            # Input Requests).
            self.page.prompt("write" if waiting.purpose == "save" else "read", "save")
        elif isinstance(waiting, Reading):
            if waiting.wants == "line":
                self.page.line_input(
                    _BUFFER,
                    waiting.capacity,
                    initial=waiting.held,
                    terminators=tuple(
                        TERMINATOR_NAMES[code]
                        for code in sorted(waiting.terminators)
                        if code in TERMINATOR_NAMES
                    ),
                )
            else:
                self.page.char_input(_BUFFER)

        if isinstance(waiting, Reading) and waiting.time and waiting.routine:
            # A fresh timed read restarts the display's clock even
            # at the same cadence, as §15 restarts its own.
            self.page.timer(
                waiting.time * _TENTH_MS, restart=waiting is not self._last_read
            )
        else:
            self.page.timer(0)

        self._last_read = waiting

        return self.page.update(exit=exit)

    def _banded(self, width: int) -> int:
        """Declare the band's canvas and feed any owed drawing.

        Returns:
            The band's height in display pixels; zero without one.
        """

        if self._band is None:
            self._band_ident = None

            return 0

        band_h = self._band_height()

        if self._band_ident is None:
            self._band_ident = self._next_ident
            self._next_ident += 1

        self.page.window(
            self._band_ident,
            "graphics",
            0,
            (0, 0, width, band_h),
            graphsize=(width, band_h),
        )

        if self._band_dirty:
            self._band_dirty = False

            picture, _ = self._band
            url = (
                self._resources.pictured(picture)
                if self._resources is not None
                else None
            )

            self.page.draw(
                self._band_ident,
                [
                    {"special": "fill"},
                    {
                        "special": "image",
                        "image": picture,
                        "url": url,
                        "x": 0,
                        "y": 0,
                        "width": width,
                        "height": band_h,
                    },
                ],
            )

        return band_h

    def _grid_rows(self) -> int:
        """The grid's height: the §8.2 chrome plus the split."""

        chrome = 1 if self.version <= STATUS_FLAGS_VERSION else 0

        return chrome + self._model.split

    def _faced(self, rows: int) -> list[list[tuple[str, int, str]]]:
        """The grid's face, cells coalesced into named runs."""

        face: list[list[tuple[str, int, str]]] = []

        for row in range(1, rows + 1):
            spans: list[tuple[str, int, str]] = []

            for column in range(1, self.screen_columns + 1):
                held = self._model.cell(row, column)
                name = _named(held.style)

                if spans and spans[-1][0] == name:
                    spans[-1] = (name, 0, spans[-1][2] + held.character)
                else:
                    spans.append((name, 0, held.character))

            face.append(spans)

        return face

    def accept(self, stanza: Stanza) -> str:  # noqa: PLR0911 -- one verdict per event kind
        """Translate one inbound stanza into a serving verdict.

        ADVANCE means the machine can run on; STAND means the wait
        still stands but the picture may have changed -- a timer's
        interrupt printed -- and PASS means the stanza asked for
        nothing here.

        Raises:
            ZMachineInstructionError: For input no read stands to
                receive -- unreachable from a conforming display,
                whose generations shield every withdrawal.
        """

        kind = stanza.get("type")

        if kind not in _NO_PARTIAL:
            self.page.typed(partials(stanza.get("partial")))

        if stanza.get("gen") != self.page.gen:
            return PASS

        if kind == "line":
            line = str(stanza.get("value", ""))
            terminator = TERMINATOR_CODES.get(str(stanza.get("terminator")), 0)

            # The machine never echoes: the display owes the typed
            # line and its newline, in the input dress -- but only
            # a return-ended read prints its return (§15 read). A
            # terminator-ended line stays uncommitted, ready for
            # the preloaded re-read Beyond Zork answers one with.
            if not terminator:
                self._runs.append(("input", 0, line + "\n"))

            self._machine().deliver_line(line, terminator)

            return ADVANCE

        if kind == "char":
            return self._keyed(stanza)

        if kind == "timer":
            return self._ticked()

        if kind == "specialresponse":
            return self._answered(stanza)

        if kind in ("arrange", "redraw"):
            return self._reshaped(kind, stanza)

        return PASS

    def _answered(self, stanza: Stanza) -> str:
        """The player's file name, or not, to the suspended ask.

        A response to some other ask asks nothing here (GlkOte:
        Special Input Requests); a non-string value is a browser
        dialog's fileref object, and no dialog was invited: it
        reads as the cancel it is, which is always legitimate.
        """

        if stanza.get("response") != "fileref_prompt":
            return PASS

        value = stanza.get("value")

        self._machine().deliver_file(value if isinstance(value, str) else None)

        return ADVANCE

    def _reshaped(self, kind: str, stanza: Stanza) -> str:
        """An arrange or redraw: the picture re-shapes or re-paints.

        An arrange re-measures -- the next reload boots a machine
        at the new size (§8.4), while a hanging band re-shapes now
        and its rows-below claim follows. A redraw re-feeds the
        band whole (GlkOte: Redraw Events); without one there is
        nothing here to redraw.
        """

        if kind == "redraw":
            if self._band is None:
                return PASS

            self._band_dirty = True

            return STAND

        self._measure(stanza)

        if self._band is not None:
            self._band_dirty = True

            self._rebased()

        return STAND

    def _keyed(self, stanza: Stanza) -> str:
        """One keystroke to the machine, §3.8-spelled."""

        value = stanza.get("value", "")

        if isinstance(value, str) and len(value) == 1:
            key = value
        else:
            named = ZSCII_KEYS.get(str(value))

            if named is None:
                return PASS

            key = named

        return ADVANCE if self._machine().deliver_key(key) else PASS

    def _ticked(self) -> str:
        """A timer event: the §15 interrupt fires, or nothing does."""

        machine = self._machine()
        waiting = machine.waiting

        if waiting is None or not waiting.routine:
            return PASS

        machine.deliver_tick()

        return ADVANCE if machine.waiting is None else STAND

    def _machine(self) -> Machine:
        """The machine this display fronts.

        Raises:
            GlkOteError: Before any machine is booted over it.
        """

        if self.machine is None:
            msg = "the display fronts no machine yet"

            raise GlkOteError(msg)

        return self.machine


def serve(
    story: Story,
    frontend: GlkOteFrontend,
    reader: TextIO,
    writer: TextIO,
    *,
    seed: int | None = None,
) -> bool:
    """Drive one Z session over the protocol, stanza by stanza.

    The init comes first -- the machine boots only after it, since
    the header reads the screen's size at boot -- and thereafter
    the burst model: run to a suspension, the update out, the
    answer delivered. True is a session that ended cleanly; a
    broken conversation answers the protocol's own error stanza
    and is False.
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

        machine = Machine(story, frontend, seed=seed)
        frontend.machine = machine

        while True:
            machine.run()

            write_stanza(writer, frontend.render(exit=not machine.running))

            if not machine.running:
                return True

            while True:
                stanza = read_stanza(reader)

                if stanza is None:
                    return True

                verdict = frontend.accept(stanza)

                if verdict == ADVANCE:
                    break

                if verdict == STAND:
                    # The wait stands but the picture moved -- an
                    # interrupt printed, a resize arrived.
                    write_stanza(writer, frontend.render())

                    continue

                write_stanza(writer, {"type": "pass"})
    except json.JSONDecodeError as error:
        write_stanza(writer, {"type": "error", "message": f"voxam: not JSON: {error}"})

        return False
    except VoxamError as error:
        write_stanza(writer, {"type": "error", "message": f"voxam: {error}"})

        return False


def _named(style: int) -> str:
    """A §8.7 style bitmask as the protocol name it wears.

    Priority-ordered: reverse video first (the page's own CSS
    dresses user1 as inverse), then fixed pitch, then the weights.
    """

    if style & REVERSE:
        return "user1"

    if style & FIXED_PITCH:
        return "preformatted"

    if style & BOLD and style & ITALIC:
        return "alert"

    if style & BOLD:
        return "subheader"

    if style & ITALIC:
        return "emphasized"

    return "normal"
