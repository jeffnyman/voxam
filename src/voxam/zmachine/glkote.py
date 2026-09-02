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

The rest of the eras' claims live here too, each under the
display's own grant: the §10.5.2.1 terminating characters the
wire can name, §10.3's clicks on the grid, §9's sounds in the
dialect's channel ops, and §8.3's colours as per-span ink with
the window's own paper.

The Version 6 stage joins at last, as its own face: the
StageFrontend hosts the same StageModel the pygame glass paints
from, and its unit-positioned paints become the stage dialect's
draw ops on one scaled canvas -- placed text, fills, sliding
rectangles -- in the art's own coordinate space, the display
magnifying it to fit. A display that never learned the dialect
is refused loudly at the door.
"""

import json
from base64 import b64encode
from collections.abc import Callable, Mapping, Sequence
from typing import Final, TextIO

from voxam.errors import GlkOteError, VoxamError
from voxam.frontend import (
    ARC_MODES,
    ARC_PIXEL_ROWS,
    ARC_REFERENCE_WIDTH,
    COLOUR_VALUES,
    PlainFrontend,
    Status,
)
from voxam.gallery import Gallery
from voxam.glkote import (
    Ink,
    Page,
    Stanza,
    TextRun,
    measured,
    partials,
    read_stanza,
    write_stanza,
)
from voxam.glulx.glk.resources import Resources, pictured
from voxam.png import encoded
from voxam.screen import (
    BOLD,
    CURRENT_COLOUR,
    DEFAULT_COLOUR,
    FIXED_PITCH,
    ITALIC,
    REVERSE,
    UPPER,
    ScreenModel,
)
from voxam.stage import FillPaint, Paint, StageModel, TextPaint
from voxam.zmachine.header import STATUS_FLAGS_VERSION
from voxam.zmachine.machine import (
    FULL_VOLUME,
    SINGLE_CLICK,
    Filing,
    Machine,
    Reading,
)
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
    # Return spells as the newline ZSCII knows, not a raw carriage
    # return -- chr(13) falls through every char_to_zscii branch
    # and is refused, leaving Enter silently dead at the machine.
    "return": "\n",
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

# A text run wearing the colour dialect's ink is one member
# longer than a colourless one.
_INKED_RUN: Final = 4

# One §15 tenth of a second, in the protocol's milliseconds.
_TENTH_MS = 100


# The events that never carry the player's partial input (GlkOte:
# Partial Input).
_NO_PARTIAL = frozenset({"init", "specialresponse", "refresh", "debuginput"})

# The buffer window's protocol id; the grid's ids are minted
# fresh at every reopening, since the protocol forbids reuse.
_BUFFER = 1

# The screen model that plays on the §8.8 stage.
STAGE_VERSION: Final = 6

# The stage without a Reso chunk: MCGA's 320 by 200, the screen
# Infocom's Version 6 art was drawn for -- and the Blorb rule for
# art without a Reso is one image pixel per screen pixel, so the
# art's own space is the only default that draws it true (Blorb:
# The Resolution Chunk).
STANDARD_STAGE: Final = (320, 200)

# One stage cell in units: the 8-by-8 character of the MCGA
# presentation (§8.8.1).
_CELL: Final = 8

# §8.3.1's "the colour of the pixel under the cursor", passed
# through signed by the machine.
_PIXEL_COLOUR: Final = -1

# Where the stage's minted colour codes begin: past every §8.3.1
# code the spec names, exactly as the pygame glass mints its
# sampled colours.
_FIRST_SAMPLED: Final = 16

# The stage's own §8.3.1 code-1 defaults: white ink on black
# paper, the machine's home look, matching the pygame glass.
_INK_DEFAULT: Final = "#ffffff"
_PAPER_DEFAULT: Final = "#000000"


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
    # Clicks have no support token: they are core GlkOte, so the
    # header's §10.3.1.1 request answers honestly on the wire.
    has_mouse = True

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
        # An arrange re-measures the display mid-session -- the
        # shell's Display menu changing the font size is one, with
        # the same box holding fewer or more cells -- and the model
        # follows it. Set by the machine, which re-stamps the §8.4
        # header fields through it; None leaves the header be.
        self.on_resize: Callable[[], None] | None = None
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
        # The sound seam: the cycle's queued channel ops, the
        # number sounding on the wire's one channel, and the
        # once-only flag a natural ending raises for poll_sound.
        self._sound_ops: list[Stanza] = []
        self._sounding: int | None = None
        self._sound_done = False
        self._speaks_sound = False
        # The current §8.3.1 pair, inking the lower window's runs;
        # the model keeps the grid's cells dressed on its own.
        self._ink: tuple[int, int] = (DEFAULT_COLOUR, DEFAULT_COLOUR)
        # The turn's tallest split: what keeps a quote box on the
        # screen after its shrink (see split_window).
        self._peak_split = 0
        # A display that lost its picture asked for it whole; the
        # next render answers with everything.
        self._refresh_owed = False
        # The sidecar seam: granted by the display's "voxam"
        # token, carrying the last line this face delivered (DESIGN:
        # What the sidecar carries).
        self._speaks_voxam = False
        self._last_command: str | None = None

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
        self._speaks_voxam = "voxam" in support

        # The band's claim is honest twice over: pictures must
        # actually hang behind the story, and the display must
        # speak graphics windows (arc_image: the contract).
        self.has_arc_images = (
            self._resources is not None
            and self._resources.blorb is not None
            and "graphicswin" in support
        )

        # Colours are the dialect's word too: a display that says
        # it renders the ink the spans carry, and one that never
        # learned it leaves the header's §8.3 offer honestly
        # unclaimed.
        self.has_colours = "colors" in support

        # The sound claim is honest twice over as well: the
        # display must say the dialect's word, and a Blorb must
        # actually hang sounds behind the story (§9, §11.1). The
        # interpreter's own bleeps need only the display.
        self._speaks_sound = "sound" in support
        self.has_sounds = (
            self._speaks_sound
            and self._resources is not None
            and self._resources.blorb is not None
        )

        # The doorway courtesy, over the wire: the Blorb's cover
        # stands at the top of the story's text, when there is one
        # and the display grants bare graphics -- pictures laid in
        # text (Blorb: Frontispiece Chunk). Art is a courtesy,
        # never a gate: no cover, no grant, or an unmeasurable
        # picture simply plays on.
        if "graphics" in support and self._resources is not None:
            cover = _fronted(self._resources)

            if cover is not None:
                self._runs.extend([cover, ("normal", 0, "\n")])

        # The record's card no longer joins the cover at the door.
        # It was told as the page's opening text, which put a
        # publisher's blurb in the middle of the story's own words
        # where no reader asked for it; WinFrotz shows the same
        # bibliography in a little window of its own, and so does
        # the browser face now, behind a button (Babel: The
        # iFiction format).

        self._measure(stanza)

        self._model = ScreenModel(
            columns=self.screen_columns, lines=self.screen_lines, version=self.version
        )

    def _sized(self, stanza: Stanza) -> Stanza:
        """Take the display's box from its metrics, which it must carry.

        Raises:
            GlkOteError: When the metrics carry no size.
        """

        metrics: Stanza = stanza.get("metrics", {})

        if "width" not in metrics or "height" not in metrics:
            msg = "the display's metrics carry no size (GlkOte: The Metrics Object)"

            raise GlkOteError(msg)

        self._size = (int(metrics["width"]), int(metrics["height"]))

        return metrics

    def _measure(self, stanza: Stanza) -> None:
        """Take the display's size and cells from its metrics.

        Raises:
            GlkOteError: When the metrics carry no size.
        """

        metrics = self._sized(stanza)
        width, height, margin_x, margin_y = measured(metrics, "grid")

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
            self._runs.append(self._run(text))

    def _run(self, text: str) -> TextRun:
        """One lower-window run in the current dress and ink."""

        name = _named(self._style)
        ink = _inked(self._ink, reverse=bool(self._style & REVERSE))

        return (name, 0, text) if ink is None else (name, 0, text, ink)

    def write_rectangle(self, rows: Sequence[str]) -> None:
        """§15 print_table: stamped in the upper, stacked below."""

        if self._model.selected == UPPER:
            self._model.write_rectangle(rows)
        else:
            for row in rows:
                self._runs.append(self._run(row + "\n"))

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

    def set_colour(self, foreground: int, background: int) -> None:
        """Change the printing colours (§8.3.1).

        The model keeps the grid's cells dressed; the pair kept
        here inks the lower window's runs -- zero keeps a colour
        current, exactly as the model reads it. Only a claiming
        face hears the call at all (§8.3).
        """

        self._model.set_colour(foreground, background)

        fg, bg = self._ink
        self._ink = (
            foreground if foreground != CURRENT_COLOUR else fg,
            background if background != CURRENT_COLOUR else bg,
        )

    def erase_window(self, window: int) -> None:
        """An erasure of the lower half clears the buffer whole.

        The whole-screen forms are a deliberate teardown, not a
        quote box: the high water recedes with the split
        (§8.7.3.3).
        """

        self._model.erase_window(window)

        if window < 0:
            self._peak_split = self._model.split

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

    # -- the §9 sounds, in the wire's own dialect ---------------------------

    def bleep(self, number: int) -> None:
        """Sound a bleep over the wire: 1 is high, 2 is low (§9.2).

        The op carries no sample: the display's own oscillator
        answers, the way a terminal's bell would. Only a display
        that said the dialect's word hears it -- no Blorb needed,
        since the bleeps are the interpreter's own.
        """

        if self._speaks_sound:
            self._sound_ops.append({"op": "bleep", "bleep": number})

    def play_sound(self, number: int, volume: int, repeats: int | None) -> bool:
        """Start a sampled sound on the wire's one channel (§9.4).

        The newest play winning is §9.4.2's own rule, and the
        display's channel does exactly that. The §9.3 volume maps
        to eighths of unit gain, and a sound the wire cannot
        carry starts nothing -- so its end-of-sound routine is
        never kept.
        """

        if self._resources is None:
            return False

        url = self._resources.audible(number)

        if url is None:
            return False

        self._sound_ops.append(
            {
                "channel": 1,
                "op": "play",
                "sound": number,
                "url": url,
                "repeats": self._repeated(number, repeats),
                "notify": 0,
                "volume": volume / FULL_VOLUME,
            }
        )
        self._sounding = number
        self._sound_done = False

        return True

    def _repeated(self, number: int, repeats: int | None) -> int:
        """The §9.4.3 play count in the dialect's own spelling.

        Zero repeats until stopped, spelled -1 on the wire; None
        is Version 3's silence on the matter, answered by the
        Blorb's Loop chunk -- how The Lurking Horror's rats hum
        until the valve stops them (Blorb: The Looping Chunk).
        """

        if repeats is None:
            blorb = self._resources.blorb if self._resources is not None else None

            return -1 if blorb is not None and number in blorb.loops else 1

        return -1 if repeats == 0 else repeats

    def stop_sound(self, number: int | None) -> None:
        """Stop the sounding sample, when the ask names it (§9.4).

        One sound plays at a time (§9.4.2), so a stop for some
        other number stops nothing -- and None, the stop-them-all
        form, always lands on whatever sounds.
        """

        if self._sounding is None or (number is not None and number != self._sounding):
            return

        self._sounding = None
        self._sound_done = False
        self._sound_ops.append({"channel": 1, "op": "stop"})

    def sound_finished(self) -> bool:
        """Whether the wire reported a natural ending, once (§9.4.4)."""

        done, self._sound_done = self._sound_done, False

        return done

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
        """Resize the upper window (§8.7.2.1); the model rules.

        The turn's tallest split is remembered: an Inform quote
        box splits tall, writes, and shrinks back at once,
        trusting §8.6.1.2's rule that splitting clears nothing
        from Version 4 -- on a real §8 screen the box lingers in
        the unsplit region, so the grid here stands at the turn's
        high water until the next input arrives, the same
        courtesy garglk and Parchment extend the same box.
        """

        self._model.split_window(lines)

        if self.version > STATUS_FLAGS_VERSION:
            self._peak_split = max(self._peak_split, lines)

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

        # The window's paper is the model's own background,
        # travelling only when a claiming display can show it and
        # a game has coloured it -- Photopia's scenes bleed to the
        # window's edge, not just under its letters (§8.3).
        paper = _css(self._model.background) if self.has_colours else None

        self.page.window(_BUFFER, "buffer", 0, (0, brow, width, height), bg=paper)

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
                bg=paper,
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
                # The field carries no §15 preload: "the game must
                # do this" -- the held text is already printed by
                # the story's own hand, so what the field sends
                # back is the typed part alone, which is exactly
                # what the machine appends after the preload it
                # holds (§15 read).
                self.page.line_input(
                    _BUFFER,
                    waiting.capacity,
                    terminators=tuple(
                        TERMINATOR_NAMES[code]
                        for code in sorted(waiting.terminators)
                        if code in TERMINATOR_NAMES
                    ),
                )
            else:
                self.page.char_input(_BUFFER)

            if self._grid_ident is not None and (
                waiting.wants == "key" or SINGLE_CLICK in waiting.terminators
            ):
                # A keystroke read hears a click the way it hears
                # any key; a line read only when its table names
                # the click code (§10.3.3). The grid is the whole
                # clickable surface: "buffer windows do not
                # support mouse-click input" (GlkOte: The Input
                # Update Array).
                self.page.passive_input(self._grid_ident, mouse=True)

        self._timed(waiting)
        self._sung()

        refresh, self._refresh_owed = self._refresh_owed, False

        return self.page.update(
            exit=exit,
            refresh=refresh,
            voxam=self._sidecar() if self._speaks_voxam else None,
        )

    def _timed(self, waiting: Filing | Reading | None) -> None:
        """The timer field for the cycle, from the standing wait.

        A fresh timed read restarts the display's clock even at
        the same cadence, as §15 restarts its own.
        """

        if isinstance(waiting, Reading) and waiting.time and waiting.routine:
            self.page.timer(
                waiting.time * _TENTH_MS, restart=waiting is not self._last_read
            )
        else:
            self.page.timer(0)

        self._last_read = waiting

    def _sung(self) -> None:
        """The cycle's queued channel ops onto the page, once."""

        if self._sound_ops:
            self.page.sounds(self._sound_ops)
            self._sound_ops = []

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
        """The grid's height: the §8.2 chrome plus the split.

        The split is the turn's high water, not the moment's --
        the quote-box courtesy split_window explains.
        """

        chrome = 1 if self.version <= STATUS_FLAGS_VERSION else 0

        return chrome + max(self._model.split, self._peak_split)

    def _faced(self, rows: int) -> list[list[TextRun]]:
        """The grid's face, cells coalesced into named, inked runs."""

        face: list[list[TextRun]] = []

        for row in range(1, rows + 1):
            spans: list[TextRun] = []

            for column in range(1, self.screen_columns + 1):
                held = self._model.cell(row, column)
                name = _named(held.style)
                ink = _inked(
                    (held.foreground, held.background),
                    reverse=bool(held.style & REVERSE),
                )

                if spans and spans[-1][0] == name and _ink_of(spans[-1]) == ink:
                    text = spans[-1][2] + held.character
                    spans[-1] = (name, 0, text) if ink is None else (name, 0, text, ink)
                else:
                    spans.append(
                        (name, 0, held.character)
                        if ink is None
                        else (name, 0, held.character, ink)
                    )

            face.append(spans)

        return face

    def accept(self, stanza: Stanza) -> str:
        """Translate one inbound stanza into a serving verdict.

        ADVANCE means the machine can run on; STAND means the wait
        still stands but the picture may have changed -- a timer's
        interrupt printed -- and PASS means the stanza asked for
        nothing here. Delivered input begins the next turn, so a
        quote box's high water recedes to the real split there.

        Raises:
            ZMachineInstructionError: For input no read stands to
                receive -- unreachable from a conforming display,
                whose generations shield every withdrawal.
        """

        verdict = self._accepted(stanza)

        if verdict == ADVANCE:
            self._peak_split = self._model.split

        return verdict

    def _accepted(self, stanza: Stanza) -> str:  # noqa: PLR0911 -- one verdict per event kind
        """The verdict itself, one return per event kind."""

        kind = stanza.get("type")

        if kind not in _NO_PARTIAL:
            self.page.typed(partials(stanza.get("partial")))

        if kind == "refresh":
            # The display lost its picture and asks for it whole
            # -- ahead of the generation gate, since a refreshing
            # display is out of sync by definition (GlkOte: the
            # refresh input event). The band owes its drawing
            # again too.
            self._refresh_owed = True

            if self._band is not None:
                self._band_dirty = True

            return STAND

        if stanza.get("gen") != self.page.gen:
            return PASS

        if kind == "line":
            return self._lined(stanza)

        if kind == "char":
            return self._keyed(stanza)

        if kind == "mouse":
            return self._pointed(stanza)

        if kind == "timer":
            return self._ticked()

        if kind == "sound":
            return self._sound_over(stanza)

        if kind == "specialresponse":
            return self._answered(stanza)

        if kind in ("arrange", "redraw"):
            return self._reshaped(kind, stanza)

        return PASS

    def _echoed(self, line: str) -> None:
        """The typed line and its newline, in the input dress."""

        self._runs.append(("input", 0, line + "\n"))

    def _lined(self, stanza: Stanza) -> str:
        """A typed line to the machine, echoed first.

        A line with no line read standing passes: a display can
        misaim one event across the roster's swap -- a keystroke
        landing in a field already replaced -- and a misaimed
        delivery is the blocking loop's shrug, never a
        session-fatal wiring fault.
        """

        if self._reading("line") is None:
            return PASS

        line = str(stanza.get("value", ""))
        terminator = TERMINATOR_CODES.get(str(stanza.get("terminator")), 0)

        # The machine never echoes: the display owes the typed
        # line and its newline -- but only a return-ended read
        # prints its return (§15 read). A terminator-ended line
        # stays uncommitted, ready for the preloaded re-read
        # Beyond Zork answers one with.
        if not terminator:
            self._echoed(line)

        self._machine().deliver_line(line, terminator)
        self._last_command = line

        return ADVANCE

    def _reading(self, wants: str) -> Reading | None:
        """The standing read of this kind, or None.

        The guard that keeps a misaimed delivery from reaching
        the machine's loud wiring-fault refusals.
        """

        waiting = self._machine().waiting

        if isinstance(waiting, Reading) and waiting.wants == wants:
            return waiting

        return None

    def _answered(self, stanza: Stanza) -> str:
        """The player's file name, or not, to the suspended ask.

        A response to some other ask asks nothing here (GlkOte:
        Special Input Requests); a non-string value is a browser
        dialog's fileref object, and no dialog was invited: it
        reads as the cancel it is, which is always legitimate.
        """

        if stanza.get("response") != "fileref_prompt":
            return PASS

        if not isinstance(self._machine().waiting, Filing):
            # No file ask stands: the misaimed-event shrug.
            return PASS

        value = stanza.get("value")

        self._machine().deliver_file(value if isinstance(value, str) else None)

        return ADVANCE

    def _reshaped(self, kind: str, stanza: Stanza) -> str:
        """An arrange or redraw: the picture re-shapes or re-paints.

        An arrange re-measures, and the screen model follows it to
        the new size: the display's own font size can move mid-
        session, and a model left at the size it booted against
        composes the §8.2 status line for a screen that is no
        longer there -- the score stranded off the right edge of a
        narrowed grid, and a widened one reaching past the row it
        has. The §8.4 header fields follow too, through the
        machine's own callback. A hanging band re-shapes now and
        its rows-below claim follows. A redraw re-feeds the band
        whole (GlkOte: Redraw Events); without one there is
        nothing here to redraw.
        """

        if kind == "redraw":
            if self._band is None:
                return PASS

            self._band_dirty = True

            return STAND

        self._measure(stanza)
        self._model.resize(self.screen_columns, self.screen_lines)

        if self.on_resize is not None:
            self.on_resize()

        if self._band is not None:
            self._band_dirty = True

            self._rebased()

        return STAND

    def _pointed(self, stanza: Stanza) -> str:
        """A click in the grid to the machine, §10.3-spelled.

        The event's cell coordinates count from the grid's own
        zero; the header extension counts the screen from (1,1),
        and the grid sits at the screen's top, so one step moves
        between them (§10.3.2). A click that ends a line read
        takes the typed text riding the event as the line
        composed so far; a click nothing can hear passes with
        the wait standing.
        """

        if self._grid_ident is None or stanza.get("window") != self._grid_ident:
            return PASS

        if not isinstance(self._machine().waiting, Reading):
            # No read stands to hear a click: the misaimed-event
            # shrug -- deliver_click's own False covers a standing
            # read that cannot hear one.
            return PASS

        typed = partials(stanza.get("partial")).get(_BUFFER, "")
        heard = self._machine().deliver_click(
            int(stanza.get("x", 0)) + 1, int(stanza.get("y", 0)) + 1, typed
        )

        return ADVANCE if heard else PASS

    def _keyed(self, stanza: Stanza) -> str:
        """One keystroke to the machine, §3.8-spelled.

        A keystroke with no key read standing passes -- the
        misaimed-event shrug the line branch explains.
        """

        if self._reading("key") is None:
            return PASS

        value = stanza.get("value", "")

        if isinstance(value, str) and len(value) == 1:
            key = value
        else:
            named = ZSCII_KEYS.get(str(value))

            if named is None:
                return PASS

            key = named

        return ADVANCE if self._machine().deliver_key(key) else PASS

    def _sound_over(self, stanza: Stanza) -> str:
        """A sampled sound finished naturally on the display.

        The ending is noted once and §9.4.4's end-of-sound
        routine fires through the machine's own re-entrant loop,
        its prints rendered while any read stands. A report for a
        sound since stopped or replaced means nothing -- §9.4.4's
        own rule -- and passes with the picture unchanged.
        """

        if self._sounding is None or stanza.get("sound") != self._sounding:
            return PASS

        self._sounding = None
        self._sound_done = True

        self._machine().poll_sound()

        return STAND

    def _ticked(self) -> str:
        """A timer event: the §15 interrupt fires, or nothing does."""

        machine = self._machine()
        waiting = machine.waiting

        if waiting is None or not waiting.routine:
            return PASS

        machine.deliver_tick()

        return ADVANCE if machine.waiting is None else STAND

    def _sidecar(self) -> Stanza:
        """The voxam block: the deluxe features' dumb factual feed.

        Location, score, and turns come from the machine's honest
        bearings; the command is the last line this face delivered
        -- the wire knows what it handed over -- and the
        discontinuity bit reports an undo, restore, or restart
        since the last update, read once and rested (DESIGN: What
        the sidecar carries).
        """

        machine = self._machine()
        bearings = machine.bearings()
        block: Stanza = {}

        if bearings.location is not None:
            number, name = bearings.location
            block["location"] = {"object": number, "name": name}

        if bearings.score is not None:
            block["score"] = bearings.score

        if bearings.turns is not None:
            block["turns"] = bearings.turns

        if self._last_command is not None:
            block["command"] = self._last_command

        if machine.discontinuity:
            machine.discontinuity = False
            block["discontinuity"] = True

        return block

    def _machine(self) -> Machine:
        """The machine this display fronts.

        Raises:
            GlkOteError: Before any machine is booted over it.
        """

        if self.machine is None:
            msg = "the display fronts no machine yet"

            raise GlkOteError(msg)

        return self.machine


class StageFrontend(GlkOteFrontend):
    """The Version 6 stage at the far end of the protocol.

    One scaled canvas in the stage dialect's words: the same
    StageModel the pygame glass paints from reduces the
    eight-window screen to unit-positioned paints, and each
    becomes a draw op here -- placed text, fills, sliding
    rectangles -- in the art's own logical space, the display
    magnifying it to fit (§8.8). The stage is pinned to the
    Blorb's Reso standard window, or MCGA's 320 by 200 without
    one, so layouts land exactly where the artists put them and
    the Reso arithmetic collapses to each picture's own standard
    ratio.

    The doorway courtesies stay off the stage -- a Version 6 game
    paints its own opening -- and the [MORE] budget stays unarmed:
    a suspending face cannot hold a scroll mid-print, so long
    passages flow uninterrupted, the scrollback road not yet
    taken.
    """

    has_stage = True
    # The stage paints its own ink into the ops, so the §8.3
    # claim needs no display grant.
    has_colours = True
    font_width = _CELL
    font_height = _CELL

    def __init__(self, version: int, resources: Resources | None = None) -> None:
        """Open at the art's own size, before any init."""

        super().__init__(version, resources)

        blorb = resources.blorb if resources is not None else None
        width, height = STANDARD_STAGE

        if blorb is not None and blorb.resolution is not None:
            width, height = blorb.resolution.width, blorb.resolution.height

        self.screen_columns = max(1, width // self.font_width)
        self.screen_lines = max(1, height // self.font_height)
        # The gallery rules the picture claims exactly as it does
        # at the glass: placards measured, Reso understood, and a
        # count of zero leaving the header's offer unclaimed.
        self._gallery: Gallery | None = blorb.gallery() if blorb is not None else None
        self.has_pictures = self._gallery is not None and self._gallery.count > 0
        self._stage = StageModel(
            self.screen_columns, self.screen_lines, self.font_width, self.font_height
        )
        self._canvas_ident: int | None = None
        # The cycle's draw ops, and the journal a repaint replays:
        # everything since the last whole-stage fill, since
        # nothing before one can ever show again.
        self._ops: list[Stanza] = []
        self._journal: list[Stanza] = []
        self._repaint_owed = False
        # The adaptive-palette seam: each picture's encoding
        # remembered per palette era, the standing chrome's
        # positions, and the last Current Palette serial seen --
        # a change re-dresses the chrome (Blorb: The Adaptive
        # Palette Chunk).
        self._urls: dict[int, tuple[int, str]] = {}
        self._chrome: dict[int, tuple[int, int]] = {}
        self._palette_serial = 0
        # The minted colours: §8.3.1's under-cursor samples, each
        # distinct CSS colour given a code past the named ones --
        # the wire's twin of the glass's sampled palette.
        self._minted: dict[int, str] = {}
        self._codes: dict[str, int] = {}
        self._next_code = _FIRST_SAMPLED

        # The opening curtain: the stage's own paper before any
        # game paints, the setcolor keeping a rescaled canvas's
        # clear the same colour.
        self._ops.append({"special": "setcolor", "color": _PAPER_DEFAULT})
        self._ops.append(self._whole(_PAPER_DEFAULT))

    def _logical(self) -> tuple[int, int]:
        """The stage's size in its own units."""

        return (
            self.screen_columns * self.font_width,
            self.screen_lines * self.font_height,
        )

    def _whole(self, color: str) -> Stanza:
        """A fill covering the whole stage."""

        width, height = self._logical()

        return {
            "special": "fill",
            "x": 0,
            "y": 0,
            "width": width,
            "height": height,
            "color": color,
        }

    def begin(self, stanza: Stanza) -> None:
        """Open the session; the stage needs the dialect spoken.

        The screen's size never comes from the metrics here: the
        stage is pinned to the art's own space and the display
        scales it. Only the box is taken.

        Raises:
            GlkOteError: When the display never learned the stage
                dialect, or the metrics carry no size.
        """

        support = stanza.get("support", [])

        if "stage" not in support:
            msg = (
                "the display never learned the stage; the Version 6 "
                "screen needs the dialect's own word"
            )

            raise GlkOteError(msg)

        self.has_timed_input = "timer" in support
        self._speaks_voxam = "voxam" in support
        self._speaks_sound = "sound" in support
        self.has_sounds = (
            self._speaks_sound
            and self._resources is not None
            and self._resources.blorb is not None
        )

        self._sized(stanza)

    # -- the §8.8 screen, straight onto the stage ---------------------------

    def write(self, text: str) -> None:
        """Story text onto the stage, §8.8-flowed."""

        self._stage.write(text)

    def write_rectangle(self, rows: Sequence[str]) -> None:
        """§15 print_table: right-and-down from the cursor."""

        self._stage.write_rectangle(rows)

    def show_status(self, status: Status) -> None:
        """§8.2 has no line on a stage; the model says so loudly."""

        self._stage.show_status(status)

    def set_style(self, style: int) -> None:
        """§8.7.1: the stage keeps every window's own dress."""

        self._stage.set_style(style)

    def set_font(self, font: int) -> None:
        """§8.1.2 fonts, the stage's own ledger."""

        self._stage.set_font(font)

    def set_buffering(self, buffered: bool) -> None:
        """§7.2.2: the stage wraps for itself, so buffering is real."""

        self._stage.set_buffering(buffered)

    def set_colour(self, foreground: int, background: int) -> None:
        """§8.3.1, the under-cursor sample resolved to a cell truth."""

        self._stage.set_colour(self._sampled(foreground), self._sampled(background))

    def _sampled(self, code: int) -> int:
        """§8.3.1's -1 as the colour showing under the cursor.

        The painted stage itself answers, as the glass's real
        pixel does: the drawn ops walked newest-first, an image's
        own pixel or a fill's colour, and the found colour minted
        as a code past the named ones -- how Zork Zero's status
        text sits on its ribbons without a seam.
        """

        if code != _PIXEL_COLOUR:
            return code

        self._flowed()

        line, column = self._stage.screen_cursor()
        css = _plotted(
            [*self._journal, *self._ops], column - 1, line - 1, self._gallery
        )

        return self._minted_code(css)

    def _minted_code(self, css: str) -> int:
        """The code a sampled colour wears, minted once per colour."""

        held = self._codes.get(css)

        if held is None:
            held = self._next_code
            self._next_code += 1
            self._codes[css] = held
            self._minted[held] = css

        return held

    def erase_window(self, window: int) -> None:
        """§8.7.3: the stage fills; its paint carries the erasure.

        A whole-screen erasure takes the drawn chrome with it, as
        the glass's does -- nothing is left to re-dress.
        """

        self._stage.erase_window(window)

        if window < 0:
            self._chrome.clear()

    def erase_line(self, pixels: int | None = None) -> None:
        """§8.7.3.2, the pixel-width form included."""

        self._stage.erase_line(pixels)

    def split_window(self, lines: int) -> None:
        """§8.8.4.1's tiling, the stage's own arithmetic.

        Splitting clears nothing on a stage, so a quote box's
        pixels stand without any high-water courtesy.
        """

        self._stage.split_window(lines)

    def set_window(self, window: int) -> None:
        """Select among all eight (§8.8.3)."""

        self._stage.set_window(window)

    def set_cursor(self, line: int, column: int) -> None:
        """The selected window's cursor, in its own units."""

        self._stage.set_cursor(line, column)

    def cursor_position(self) -> tuple[int, int]:
        """What get_cursor reads back: the stage's own ledger."""

        return self._stage.get_cursor()

    def place_window(
        self, window: int, line: int, column: int, height: int, width: int
    ) -> None:
        """§8.8 geometry, forwarded whole."""

        self._stage.place_window(window, line, column, height, width)

    def scroll_window(self, window: int, pixels: int) -> None:
        """§15 scroll_window, in units."""

        self._stage.scroll_window(window, pixels)

    def set_margins(self, window: int, left: int, right: int) -> None:
        """§8.8.3.2.1 margins, in units."""

        self._stage.set_margins(window, left, right)

    def set_line_count(self, window: int, count: int) -> None:
        """§8.8.3.2.6's budget, the game's own hand on it."""

        self._stage.set_line_count(window, count)

    # -- the §11 pictures, Reso-scaled onto the canvas ----------------------

    def picture_data(self, number: int) -> tuple[int, int] | None:
        """A picture's drawn height and width (§15 picture_data).

        The Reso arithmetic is the gallery's, exactly as at the
        glass -- though on a stage pinned to the standard window
        the Elbow Room Factor is one, and only each picture's own
        standard ratio remains (Blorb: The Resolution Chunk).
        """

        gallery = self._gallery

        if gallery is None:
            return None

        size = gallery.size(number)

        if size is None:
            return None

        height, width = size
        logical_w, logical_h = self._logical()
        factor = gallery.scale(number, logical_w, logical_h)

        return int(height * factor), int(width * factor)

    def picture_census(self) -> tuple[int, int]:
        """The count of drawable pictures and the art's release."""

        if self._gallery is None:
            return (0, 0)

        return (self._gallery.count, self._gallery.release)

    def draw_picture(self, number: int, line: int, column: int) -> None:
        """§15 draw_picture as an image op at its unit position.

        A Rect placard has no bytes to send and draws nothing --
        invisible by design, its size still spoken for layout.
        The plotting runs through the gallery's adaptive-palette
        seam: a scene's plot absorbs its palette, the chrome
        wears the Current Palette -- and a plot that changes the
        palette re-plots the standing chrome in it, the wire's
        spelling of the hardware recolouring Infocom's
        interpreters did (Blorb: The Adaptive Palette Chunk).
        """

        gallery = self._gallery

        if gallery is None:
            return

        size = self.picture_data(number)

        if size is None:
            return

        url = self._pictured(gallery, number)

        if url is None:
            return

        height, width = size

        self._flowed()
        self._ops.append(
            {
                "special": "image",
                "image": number,
                "url": url,
                "x": column - 1,
                "y": line - 1,
                "width": width,
                "height": height,
            }
        )

        if number in gallery.adaptive:
            self._chrome[number] = (line, column)

        if gallery.serial != self._palette_serial:
            self._palette_serial = gallery.serial

            self._redressed()

    def _pictured(self, gallery: Gallery, number: int) -> str | None:
        """The picture plotted for the wire, its palette truly worn.

        The gallery decodes through the adaptive dance and the
        plotted pixels are re-encoded whole -- a display handed
        an adaptive stub's own bytes would paint the placeholder
        palette. Encodings are remembered per palette era, so the
        chrome only pays its decode bill again when a scene
        re-dresses it.
        """

        picture = gallery.picture(number)

        if picture is None:
            return None

        era = gallery.serial if number in gallery.adaptive else -1
        held = self._urls.get(number)

        if held is None or held[0] != era:
            spelled = b64encode(encoded(picture)).decode("ascii")
            held = (era, f"data:image/png;base64,{spelled}")

            self._urls[number] = held

        return held[1]

    def _redressed(self) -> None:
        """Re-plot the standing chrome in the fresh Current Palette.

        Infocom's interpreters recoloured the chrome through the
        hardware palette without replotting; the wire has no
        palette hardware, so the chrome replots -- the same
        positions, the new dress.
        """

        for held, (line, column) in list(self._chrome.items()):
            self.draw_picture(held, line, column)

    def erase_picture(self, number: int, line: int, column: int) -> None:
        """§15 erase_picture: the picture's rectangle, papered over."""

        size = self.picture_data(number)

        if size is None:
            return

        height, width = size

        self._flowed()
        self._ops.append(
            {
                "special": "fill",
                "x": column - 1,
                "y": line - 1,
                "width": width,
                "height": height,
                "color": _coloured(
                    self._stage.background, self._minted, _PAPER_DEFAULT
                ),
            }
        )

    def _flowed(self) -> None:
        """Drain the stage's pending paints into the cycle's ops.

        Called ahead of every picture op too, so the canvas keeps
        the turn's true order -- text written before a picture
        lands under it, text after lands over.
        """

        self._ops.extend(_oped(self._stage.paints(), self.font_width, self._minted))
        self._stage.sweep()

    # -- the conversation, one canvas per cycle -----------------------------

    def render(self, *, exit: bool = False) -> Stanza:  # noqa: A002 -- the field's name
        """Compose the stage into one scaled canvas update."""

        machine = self._machine()
        width, height = self._size

        if self._canvas_ident is None:
            self._canvas_ident = self._next_ident
            self._next_ident += 1

        self.page.window(
            self._canvas_ident,
            "graphics",
            0,
            (0, 0, width, height),
            graphsize=self._logical(),
            scaled=True,
        )

        self._flowed()
        self._journaled(self._ops)

        refresh, self._refresh_owed = self._refresh_owed, False
        repaint, self._repaint_owed = self._repaint_owed or refresh, False
        ops, self._ops = list(self._journal) if repaint else self._ops, []

        if ops:
            self.page.draw(self._canvas_ident, ops)

        waiting = machine.waiting

        if isinstance(waiting, Filing):
            self.page.prompt("write" if waiting.purpose == "save" else "read", "save")
        elif isinstance(waiting, Reading):
            # An input pause rests the scroll budgets, as every
            # face's read does (§8.8.3.2.6).
            self._stage.rest()

            if waiting.wants == "line":
                line, column = self._stage.screen_cursor()

                self.page.line_input(
                    self._canvas_ident,
                    waiting.capacity,
                    terminators=tuple(
                        TERMINATOR_NAMES[code]
                        for code in sorted(waiting.terminators)
                        if code in TERMINATOR_NAMES
                    ),
                    cursor=(column - 1, line - 1),
                    cell=(self.font_width, self.font_height),
                    # The editor writes in the window's own ink --
                    # without it the field wears the browser's
                    # default black, invisible on a dark stage.
                    ink=_coloured(self._stage.foreground, self._minted, _INK_DEFAULT),
                    mouse=SINGLE_CLICK in waiting.terminators,
                )
            else:
                # A keystroke read hears a click the way it hears
                # any key (§10.3.3).
                self.page.char_input(self._canvas_ident, mouse=True)

        self._timed(waiting)
        self._sung()

        return self.page.update(
            exit=exit,
            refresh=refresh,
            voxam=self._sidecar() if self._speaks_voxam else None,
        )

    def _journaled(self, ops: list[Stanza]) -> None:
        """Fold the cycle's ops into the repaint journal.

        A fill covering the whole stage starts the journal over,
        a setcolor restated ahead of it so a rescaled canvas's
        clear wears the right paper. Games repaper the stage at
        every scene, so the journal stays a scene deep.
        """

        width, height = self._logical()

        for op in ops:
            if (
                op["special"] == "fill"
                and op.get("x") == 0
                and op.get("y") == 0
                and op.get("width") == width
                and op.get("height") == height
            ):
                self._journal = [
                    {"special": "setcolor", "color": op["color"]},
                    dict(op),
                ]
            else:
                self._journal.append(op)

    def _echoed(self, line: str) -> None:
        """The typed line onto the stage at the read's own cursor.

        A Version 6 interpreter echoes into the window itself
        (§7.1.2): the wire's editor showed the typing, and the
        landed line prints here so the screen keeps it.
        """

        self._stage.write(line + "\n")

    def _pointed(self, stanza: Stanza) -> str:
        """A click on the stage, §10.3-spelled in units.

        The canvas hears clicks in the stage's own logical units,
        0-based; the header extension counts from (1,1), one step
        over (§10.3.2).
        """

        if self._canvas_ident is None or stanza.get("window") != self._canvas_ident:
            return PASS

        if not isinstance(self._machine().waiting, Reading):
            # No read stands to hear a click: the misaimed-event
            # shrug, as at the grid.
            return PASS

        typed = partials(stanza.get("partial")).get(self._canvas_ident, "")
        heard = self._machine().deliver_click(
            int(stanza.get("x", 0)) + 1, int(stanza.get("y", 0)) + 1, typed
        )

        return ADVANCE if heard else PASS

    def _reshaped(self, kind: str, stanza: Stanza) -> str:
        """An arrange re-boxes the canvas; a redraw owes the journal.

        The stage's units never move with the display's box, so
        the machine hears nothing of an arrange -- and a redraw
        means the display cleared its rescaled canvas, so the
        whole journal is owed (GlkOte: Redraw Events).
        """

        if kind == "redraw":
            self._repaint_owed = True

            return STAND

        self._sized(stanza)

        return STAND


def fronted(version: int, resources: Resources | None = None) -> GlkOteFrontend:
    """The face a story's screen model asks for.

    The §8.8 stage for Version 6, the two-window picture for
    every other version -- one seam, so the CLI and the web shell
    route alike.
    """

    if version == STAGE_VERSION:
        return StageFrontend(version, resources)

    return GlkOteFrontend(version, resources)


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


def _fronted(resources: Resources) -> Stanza | None:
    """The Blorb's cover as a ready-made image span, or None.

    The picture rides whole as a data: url, drawn inline at its
    own size -- the display's proportional cap shrinks a large
    cover to the page (Blorb: Frontispiece Chunk; GlkOte: The
    Line Data Array).
    """

    cover = resources.frontispiece()

    if cover is None:
        return None

    return {
        "special": "image",
        "image": cover.number,
        "url": pictured(cover),
        "width": cover.width,
        "height": cover.height,
        "alignment": "inlineup",
    }


def _oped(paints: list[Paint], cell: int, minted: Mapping[int, str]) -> list[Stanza]:
    """Stage paints as the dialect's draw ops, 0-based on the canvas.

    Text paints arrive one dressed character at a time; runs
    along a row in the same dress coalesce into one op, the wire
    staying light. Fills and shifts translate one to one, the
    §8.3.1 codes becoming the shared palette's CSS -- the minted
    sampled colours included.
    """

    ops: list[Stanza] = []

    for paint in paints:
        if isinstance(paint, TextPaint):
            op = _texted(paint, cell, minted)
            last = ops[-1] if ops else None

            if last is not None and _joins(last, op, cell):
                last["text"] += op["text"]
            else:
                ops.append(op)
        elif isinstance(paint, FillPaint):
            ops.append(
                {
                    "special": "fill",
                    "x": paint.column - 1,
                    "y": paint.line - 1,
                    "width": paint.width,
                    "height": paint.height,
                    "color": _coloured(paint.background, minted, _PAPER_DEFAULT),
                }
            )
        else:
            ops.append(
                {
                    "special": "shift",
                    "x": paint.column - 1,
                    "y": paint.line - 1,
                    "width": paint.width,
                    "height": paint.height,
                    "rise": paint.rise,
                }
            )

    return ops


def _texted(paint: TextPaint, cell: int, minted: Mapping[int, str]) -> Stanza:
    """One placed character as a text op, reverse pre-swapped.

    The dress travels resolved: ink and paper as CSS with the
    stage's own defaults for code 1, reverse video already
    swapped, bold and italic as the op's flags (§8.7.1).
    """

    held = paint.cell
    ink = _coloured(held.foreground, minted, _INK_DEFAULT)
    paper = _coloured(held.background, minted, _PAPER_DEFAULT)

    if held.style & REVERSE:
        ink, paper = paper, ink

    op: Stanza = {
        "special": "text",
        "x": paint.column - 1,
        "y": paint.line - 1,
        "text": held.character,
        "cell": [cell, cell],
        "fg": ink,
        "bg": paper,
    }

    if held.style & BOLD:
        op["bold"] = True

    if held.style & ITALIC:
        op["italic"] = True

    return op


def _joins(last: Stanza, op: Stanza, cell: int) -> bool:
    """Whether a fresh text op continues the last one's run."""

    return (
        last.get("special") == "text"
        and op["y"] == last["y"]
        and op["x"] == last["x"] + cell * len(last["text"])
        and all(op.get(key) == last.get(key) for key in ("fg", "bg", "bold", "italic"))
    )


def _plotted(ops: Sequence[Stanza], x: int, y: int, gallery: Gallery | None) -> str:
    """The colour showing at a canvas point, newest paint first.

    §8.3.1's sample asks for the pixel under the cursor, and the
    drawn ops are the stage's pixels: an image's own pixel
    answers -- a transparent hole deferring to what shows through
    beneath -- a fill answers its colour, and paint never laid
    answers the stage's default paper. Text ops are passed over:
    a game samples its art and its fills, not its letters.
    """

    for op in reversed(ops):
        if op["special"] == "image":
            css = _art_pixel(op, x, y, gallery)

            if css is not None:
                return css
        elif op["special"] == "fill" and _within(op, x, y):
            return str(op["color"])

    return _PAPER_DEFAULT


def _art_pixel(op: Stanza, x: int, y: int, gallery: Gallery | None) -> str | None:
    """One drawn image's pixel at a canvas point, None to look on.

    The point maps back through the op's drawn size to the art's
    own pixels -- Reso scaling undone by the same ratio that
    applied it -- and a fully transparent pixel defers to
    whatever the point shows through to.
    """

    if gallery is None or not _within(op, x, y):
        return None

    picture = gallery.picture(op["image"])

    if picture is None:
        return None

    px = (x - op["x"]) * picture.width // op["width"]
    py = (y - op["y"]) * picture.height // op["height"]

    if picture.clear is not None and picture.clear[py][px]:
        return None

    return "#{:02x}{:02x}{:02x}".format(*picture.rows[py][px])


def _within(op: Stanza, x: int, y: int) -> bool:
    """Whether a drawn op's rectangle covers a canvas point."""

    return bool(
        op["x"] <= x < op["x"] + op["width"] and op["y"] <= y < op["y"] + op["height"]
    )


def _coloured(code: int, minted: Mapping[int, str], default: str) -> str:
    """A colour code as CSS, the minted samples consulted first.

    Then the shared palette, and the stage's own default for
    everything else -- code 1 included.
    """

    return minted.get(code) or _css(code) or default


def _css(code: int) -> str | None:
    """A §8.3.1 code as CSS ink, None for the display's own default.

    The values are the shared palette every face shows -- the
    same RGB the pygame glass mixes (§8.3.7's equivalents).
    """

    value = COLOUR_VALUES.get(code)

    return None if value is None else "#{:02x}{:02x}{:02x}".format(*value)


def _inked(pair: tuple[int, int], *, reverse: bool) -> Ink | None:
    """§8.3.1 codes as the dialect's ink, None when all default.

    Reverse video swaps ink and paper, as every painted face
    swaps them (§8.7.1.1) -- a side left None keeps the display's
    own colour for that half.
    """

    fg, bg = pair

    if reverse:
        fg, bg = bg, fg

    held = (_css(fg), _css(bg))

    return None if held == (None, None) else held


def _ink_of(run: TextRun) -> Ink | None:
    """The ink a run wears, None on the colourless three-tuple."""

    return run[3] if len(run) == _INKED_RUN else None


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
