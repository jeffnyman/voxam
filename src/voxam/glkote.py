"""The GlkOte update protocol, spoken from the game's side.

GlkOte is a display library: a web page that draws windows and
raises input events, designed to be driven by a server that does
the window arithmetic -- the role RemGlk plays for the C
interpreters, and the role Voxam plays here (GlkOte: What is
GlkOte?). The conversation is JSON both ways; this module builds
the game's half of it, the update: which windows stand where, what
text arrived, which inputs are wanted (GlkOte: Output: Updating
the Display).

Nothing here knows about any one machine. A Page is fed plain
facts -- boxes, styled runs, requests -- and keeps the protocol's
own state: the generation number, what the display has already
been shown, which input fields it holds. The Glulx library feeds
it through its composer; the Z-Machine will feed it the same way
from its own screen model.
"""

import json
from typing import Any, Final, TextIO, cast

from voxam.babel import IFiction
from voxam.errors import GlkOteError

# The eleven style names, in the order Glk numbers them; the
# display renders each as a CSS class, so a style IS its name here
# (GlkOte: The Line Data Array). Note blockquote is one word.
STYLES = (
    "normal",
    "emphasized",
    "preformatted",
    "header",
    "subheader",
    "alert",
    "note",
    "blockquote",
    "input",
    "user1",
    "user2",
)

# The keys a line request may name as terminators; the protocol
# knows no others (GlkOte: The Input Update Array).
TERMINATORS = frozenset({"escape", *(f"func{number}" for number in range(1, 13))})

# In a stream of buffer runs, the point where text must resume
# below the margin images: the current paragraph closes and the
# next one wears the flowbreak flag (GlkOte: Buffer Window
# Updates).
FLOWBREAK = object()

# A text run: (style name, link value, text), optionally wearing
# the colour dialect's ink as a fourth member -- (fg, bg) CSS
# colours, each None where the display's own theme rules.
Ink = tuple[str | None, str | None]
TextRun = tuple[str, int, str] | tuple[str, int, str, Ink]
_INKED_RUN: Final = 4

# How many sent paragraphs each buffer window keeps for a
# refresh's re-telling: a display that lost its picture gets the
# recent scrollback, not the whole session.
KEPT_PARAGRAPHS = 200

# The window kinds the protocol draws; pairs and blanks are the
# server's business and never appear (GlkOte: The Windows Update
# Array).
_KINDS = frozenset({"buffer", "grid", "graphics"})

# What a file prompt may ask, by the protocol's own names
# (GlkOte: Special Input Requests).
_FILE_MODES = frozenset({"read", "write", "readwrite", "writeappend"})
_FILE_KINDS = frozenset({"data", "save", "transcript", "command"})

# The drawing operations a graphics content entry may carry.
# GlkOte names the first three (GlkOte: Graphics Window Updates);
# text and shift are the stage dialect's own -- placed characters
# and sliding rectangles, VΘXΔM's words for a §8.8 screen on a
# canvas whose both wire ends are ours.
_SPECIALS = frozenset({"setcolor", "fill", "image", "text", "shift"})
_RECT = ("x", "y", "width", "height")

# What the dialect's own operations must name: a text op places a
# string of cells, a shift op slides a whole rectangle by a rise.
_TEXT_FIELDS = ("x", "y", "text", "cell")
_SHIFT_FIELDS = (*_RECT, "rise")

# "Absent" and "null" mean different things to a timer field, so
# absence needs a value of its own (GlkOte: The Timer Update).
_UNSET = object()

_STYLE_NAMES = frozenset(STYLES)

type Stanza = dict[str, Any]


class Page:
    """The display's picture of the session, update by update.

    Fed each cycle -- every visible window declared, content and
    requests alongside -- and asked for the update stanza, a Page
    sends only what changed. The distinction is load-bearing: an
    absent windows or input array means "unchanged", while an
    empty one closes every window or cancels every field, and an
    update where nothing changed at all is the pass stanza, its
    generation unbumped (GlkOte: Output: Updating the Display;
    GlkOte: The Generation Number).

    Attributes:
        gen: The generation of the last update sent -- zero before
            the first, matching the display's own init event. The
            event half of the protocol reads it to judge inbound
            event generations.
    """

    def __init__(self) -> None:
        """Open before the first update, at generation zero."""

        self._gen = 0
        # None rather than an empty list: the first update always
        # carries the full windows array, even the empty one that
        # closes nothing.
        self._shown: list[Stanza] | None = None
        self._rows: dict[int, list[list[Stanza]]] = {}
        self._open: dict[int, bool] = {}
        self._flowing: dict[int, bool] = {}
        self._asked: dict[int, Stanza] = {}
        self._typed: dict[int, str] = {}
        self._timer_shown = 0
        self._retired: set[int] = set()
        self._kept: dict[int, list[Stanza]] = {}

        # The cycle in progress, cleared by every update.
        self._declared: dict[int, Stanza] = {}
        self._texts: dict[int, Stanza] = {}
        self._changed: dict[int, list[Stanza]] = {}
        self._draws: dict[int, list[Stanza]] = {}
        self._requests: dict[int, Stanza] = {}
        self._timer_request: tuple[int, bool] | None = None
        self._prompt: Stanza | None = None
        self._sounds: list[Stanza] = []

    @property
    def gen(self) -> int:
        """The generation of the last update sent."""

        return self._gen

    # -- feeding the cycle (GlkOte: Output: Updating the Display) ----------

    def window(  # noqa: PLR0913 -- the shape of a window entry
        self,
        ident: int,
        kind: str,
        rock: int,
        box: tuple[int, int, int, int],
        *,
        gridsize: tuple[int, int] | None = None,
        graphsize: tuple[int, int] | None = None,
        bg: str | None = None,
        scaled: bool = False,
    ) -> None:
        """Declare a window that stands visible this cycle.

        Every visible window is declared every cycle; one left out
        is closed, its id retired for good -- the protocol forbids
        reuse (GlkOte: The Windows Update Array). The box arrives
        as (left, top, right, bottom) in pixels, the shape the
        window models already keep; a grid names its columns and
        rows, a graphics window its drawable size. A bg is the
        dialect's own word: the window's paper as a CSS colour,
        absent when the display's own theme is the paper. Scaled
        is the stage dialect's word, for a graphics window alone:
        the drawable size is a logical space -- §8.8's own units
        -- and the display magnifies it to fill the box, rather
        than showing it pixel for pixel.

        Raises:
            GlkOteError: For an unknown kind, a retired or
                twice-declared id, sizes that contradict the kind,
                or a scaled window that is no graphics window.
        """

        if kind not in _KINDS:
            msg = f"a window cannot be a {kind!r} (GlkOte: The Windows Update Array)"

            raise GlkOteError(msg)

        if ident in self._retired:
            msg = (
                f"window id {ident} was closed and may never return "
                "(GlkOte: The Windows Update Array)"
            )

            raise GlkOteError(msg)

        if ident in self._declared:
            msg = f"window {ident} declared twice in one cycle"

            raise GlkOteError(msg)

        left, top, right, bottom = box
        entry: Stanza = {
            "id": ident,
            "type": kind,
            "rock": rock,
            "left": left,
            "top": top,
            "width": right - left,
            "height": bottom - top,
        }

        if (gridsize is None) != (kind != "grid"):
            msg = "a grid names its columns and rows, and only a grid does"

            raise GlkOteError(msg)

        if (graphsize is None) != (kind != "graphics"):
            msg = "a graphics window names its drawable size, and only one does"

            raise GlkOteError(msg)

        if gridsize is not None:
            entry["gridwidth"], entry["gridheight"] = gridsize

            self._resized(ident, entry)

        if graphsize is not None:
            entry["graphwidth"], entry["graphheight"] = graphsize

        if scaled:
            if kind != "graphics":
                msg = "only a graphics window draws in a scaled logical space"

                raise GlkOteError(msg)

            entry["scaled"] = True

        if bg is not None:
            entry["bg"] = bg

        self._declared[ident] = entry

    def _resized(self, ident: int, entry: Stanza) -> None:
        """Drop a grid's row cache when its cell grid changed.

        What the display does with retained lines across a resize
        is unspecified, so every row is resent -- idempotent and
        always correct.
        """

        for held in self._shown or []:
            if held["id"] == ident and (
                held.get("gridwidth"),
                held.get("gridheight"),
            ) != (entry["gridwidth"], entry["gridheight"]):
                self._rows.pop(ident, None)

    def buffer(
        self,
        ident: int,
        runs: list[TextRun | object],
        *,
        clear: bool = False,
    ) -> None:
        """Feed a buffer window's new text, one cycle's worth.

        Runs are (style name, link value, text) with newlines
        embedded; the split into paragraph entries happens here,
        because the append flag is state the display remembers
        between updates: text after the last newline leaves its
        paragraph open, and the next cycle's first entry continues
        it (GlkOte: Buffer Window Updates). A clear closes the
        open paragraph and rides the entry; a FLOWBREAK in the
        stream closes it too, and the paragraph after it is moved
        below the margin images. A dict in the stream is a
        ready-made special span -- a picture set into the flow --
        joining the open paragraph as it stands (GlkOte: The Line
        Data Array).

        Raises:
            GlkOteError: For a second helping in one cycle, or an
                unknown style name.
        """

        if ident in self._texts:
            msg = f"window {ident} was fed text twice in one cycle"

            raise GlkOteError(msg)

        entry: Stanza = {"id": ident}

        if clear:
            entry["clear"] = True
            self._open[ident] = False

        segments, breaks = self._segmented(runs)
        entries = self._paragraphs(ident, segments, breaks)

        if entries:
            entry["text"] = entries

        # An empty helping is the same as none at all: only a
        # substantive entry is kept, since an empty content array
        # equals an omitted one (GlkOte: The Content Update Array).
        if "text" in entry or "clear" in entry:
            self._texts[ident] = entry

    def _segmented(
        self, runs: list[TextRun | object]
    ) -> tuple[list[list[Stanza]], set[int]]:
        """Split a run stream into paragraphs at newlines and breaks.

        Returns the paragraphs as span lists, and the indices of
        those that follow a flow break.
        """

        segments: list[list[Stanza]] = [[]]
        breaks: set[int] = set()

        for run in runs:
            if run is FLOWBREAK:
                # A break right after a newline flags the fresh
                # paragraph rather than minting a blank one.
                if segments[-1]:
                    segments.append([])

                breaks.add(len(segments) - 1)

                continue

            if isinstance(run, dict):
                # A ready-made special span joins the paragraph
                # where it stands, copied so the caller's dict
                # stays its own.
                segments[-1].append(dict(run))

                continue

            style, link, text, ink = _unrolled(run)
            pieces = text.split("\n")

            self._spanned(segments[-1], style, link, pieces[0], ink)

            for piece in pieces[1:]:
                segments.append([])
                self._spanned(segments[-1], style, link, piece, ink)

        return segments, breaks

    def _spanned(
        self,
        spans: list[Stanza],
        style: str,
        link: int,
        text: str,
        ink: "tuple[str | None, str | None] | None" = None,
    ) -> None:
        """Add one piece of styled text to a paragraph's spans.

        Adjacent pieces wearing the same dress coalesce -- two
        machine styles may share one protocol name -- and the
        hyperlink key appears only on a real link, the fg and bg
        of the colour dialect only on real ink (GlkOte: The Line
        Data Array).

        Raises:
            GlkOteError: For a style the protocol does not name.
        """

        if style not in _STYLE_NAMES:
            msg = f"no style is named {style!r} (GlkOte: The Line Data Array)"

            raise GlkOteError(msg)

        if not text:
            return

        fg, bg = ink if ink is not None else (None, None)

        # A special span has no style name, so text after a placed
        # picture starts its own span rather than coalescing.
        if (
            spans
            and spans[-1].get("style") == style
            and spans[-1].get("hyperlink", 0) == link
            and spans[-1].get("fg") == fg
            and spans[-1].get("bg") == bg
        ):
            spans[-1]["text"] += text

            return

        span: Stanza = {"style": style, "text": text}

        if link:
            span["hyperlink"] = link

        if fg is not None:
            span["fg"] = fg

        if bg is not None:
            span["bg"] = bg

        spans.append(span)

    def _paragraphs(
        self, ident: int, segments: list[list[Stanza]], breaks: set[int]
    ) -> list[Stanza]:
        """Turn paragraphs into the text entries of a content update.

        The rules of the seams: a trailing empty paragraph is the
        stream ending at a line boundary and emits nothing; a
        leading empty one on an open paragraph only closes it; an
        empty one anywhere else is a blank line, the empty object
        (GlkOte: Buffer Window Updates).
        """

        opened = self._open.get(ident, False)
        flowing = self._flowing.pop(ident, False)
        entries: list[Stanza] = []

        for index, spans in enumerate(segments):
            flagged = index in breaks or (index == 0 and flowing)

            if index == len(segments) - 1 and not spans:
                # The stream ended at a boundary; a flow break
                # right at the end waits for the next helping.
                if flagged:
                    self._flowing[ident] = True

                opened = False

                continue

            if index == 0 and not spans and opened:
                opened = False

                continue

            piece: Stanza = {}

            if index == 0 and spans and opened:
                piece["append"] = True

            if flagged:
                piece["flowbreak"] = True

            if spans:
                piece["content"] = spans

            entries.append(piece)
            opened = index == len(segments) - 1

        self._open[ident] = opened

        return entries

    def grid(self, ident: int, rows: list[list[TextRun]]) -> None:
        """Feed a grid window's whole face; only changed rows travel.

        Rows arrive as coalesced (style name, link, text) runs.
        Trailing plain whitespace is stripped before comparing,
        because the display pads short lines with it anyway -- so
        a blank row equals an empty line, a fresh grid sends only
        what shows, and a cleared grid needs no flag at all
        (GlkOte: Grid Window Updates; GlkOte: The Line Data
        Array).

        Raises:
            GlkOteError: For a second helping in one cycle, or an
                unknown style name.
        """

        if ident in self._changed:
            msg = f"window {ident} was fed rows twice in one cycle"

            raise GlkOteError(msg)

        held = self._rows.get(ident, [])
        normalized: list[list[Stanza]] = []
        updates: list[Stanza] = []

        for index, row in enumerate(rows):
            spans: list[Stanza] = []

            for run in row:
                self._spanned(spans, *_unrolled(run))

            spans = _trimmed(spans)

            normalized.append(spans)

            if spans != (held[index] if index < len(held) else []):
                line: Stanza = {"line": index}

                if spans:
                    line["content"] = spans

                updates.append(line)

        self._rows[ident] = normalized
        self._changed[ident] = updates

    def draw(self, ident: int, ops: list[Stanza]) -> None:
        """Feed drawing operations for a graphics window.

        Operations accumulate across a cycle -- a turn's fills and
        images arrive as they happen -- and travel in order
        (GlkOte: Graphics Window Updates). Text and shift are the
        stage dialect's own words: a text op places a string of
        dressed cells at a unit position, a shift op slides a
        rectangle's pixels vertically -- GlkOte never grew either,
        but both ends of this wire are ours.

        Raises:
            GlkOteError: For an operation the protocol does not
                draw, a fill with only part of a rectangle, or a
                dialect op missing a field it must name.
        """

        for op in ops:
            if op.get("special") not in _SPECIALS:
                msg = (
                    f"no drawing operation is named {op.get('special')!r} "
                    "(GlkOte: Graphics Window Updates)"
                )

                raise GlkOteError(msg)

            corners = [side for side in _RECT if side in op]

            if op["special"] == "fill" and corners and len(corners) != len(_RECT):
                # "All four of these fields must be specified if
                # any is" (GlkOte: Graphics Window Updates).
                msg = "a fill names its whole rectangle or none of it"

                raise GlkOteError(msg)

            if op["special"] == "text" and any(
                field not in op for field in _TEXT_FIELDS
            ):
                msg = "a text op places its string in cells: x, y, text, cell"

                raise GlkOteError(msg)

            if op["special"] == "shift" and any(
                field not in op for field in _SHIFT_FIELDS
            ):
                msg = "a shift op slides a whole rectangle by a rise"

                raise GlkOteError(msg)

        self._draws.setdefault(ident, []).extend(ops)

    def line_input(  # noqa: PLR0913 -- the shape of an input field
        self,
        ident: int,
        maxlen: int,
        *,
        initial: str = "",
        terminators: tuple[str, ...] = (),
        cursor: tuple[int, int] | None = None,
        cell: tuple[int, int] | None = None,
        ink: str | None = None,
        hyperlink: bool = False,
        mouse: bool = False,
    ) -> None:
        """Ask for a line of input in a window.

        A cell is the stage dialect's word: the editor's cell size
        in the canvas's own logical units, so the display can
        place and dress the field at the game's cursor. An ink is
        the editor's own text colour -- without one the field
        writes in the browser's default, which on a dark stage is
        invisible ink. A stage's line request names its cursor
        and its cell.

        Raises:
            GlkOteError: For a terminator the protocol cannot
                name, or a second request in one window.
        """

        entry: Stanza = {"id": ident, "type": "line", "maxlen": maxlen}

        if initial:
            entry["initial"] = initial

        if cell is not None:
            entry["cell"] = list(cell)

        if ink is not None:
            entry["ink"] = ink

        if terminators:
            for name in terminators:
                if name not in TERMINATORS:
                    msg = (
                        f"no terminator key is named {name!r} "
                        "(GlkOte: The Input Update Array)"
                    )

                    raise GlkOteError(msg)

            entry["terminators"] = list(terminators)

        self._requested(entry, cursor, hyperlink=hyperlink, mouse=mouse)

    def char_input(
        self,
        ident: int,
        *,
        cursor: tuple[int, int] | None = None,
        hyperlink: bool = False,
        mouse: bool = False,
    ) -> None:
        """Ask for a single keystroke in a window.

        Raises:
            GlkOteError: For a second request in one window.
        """

        self._requested(
            {"id": ident, "type": "char"}, cursor, hyperlink=hyperlink, mouse=mouse
        )

    def passive_input(
        self, ident: int, *, hyperlink: bool = False, mouse: bool = False
    ) -> None:
        """Ask for clicks or link selections alone, no typing.

        With neither flag raised this asks for nothing, which the
        protocol spells by leaving the window out entirely
        (GlkOte: The Input Update Array).

        Raises:
            GlkOteError: For a second request in one window.
        """

        if hyperlink or mouse:
            self._requested({"id": ident}, None, hyperlink=hyperlink, mouse=mouse)

    def _requested(
        self,
        entry: Stanza,
        cursor: tuple[int, int] | None,
        *,
        hyperlink: bool,
        mouse: bool,
    ) -> None:
        """File one window's input request for the cycle.

        Raises:
            GlkOteError: For a second request in one window.
        """

        ident = entry["id"]

        if ident in self._requests:
            msg = f"window {ident} asked for input twice in one cycle"

            raise GlkOteError(msg)

        if cursor is not None:
            entry["xpos"], entry["ypos"] = cursor

        if hyperlink:
            entry["hyperlink"] = True

        if mouse:
            entry["mouse"] = True

        self._requests[ident] = entry

    def prompt(self, filemode: str, filetype: str) -> None:
        """Ask the player for a file, through the display's own ask.

        The update carries it as special input, and the display
        disables the game until the answer comes back (GlkOte:
        Special Input Requests).

        Raises:
            GlkOteError: For a mode or kind the protocol does not
                name, or a second ask in one cycle.
        """

        if self._prompt is not None:
            msg = "one file may be asked for per cycle"

            raise GlkOteError(msg)

        if filemode not in _FILE_MODES or filetype not in _FILE_KINDS:
            msg = (
                f"no file prompt asks {filemode!r} of a {filetype!r} "
                "(GlkOte: Special Input Requests)"
            )

            raise GlkOteError(msg)

        self._prompt = {
            "type": "fileref_prompt",
            "filemode": filemode,
            "filetype": filetype,
        }

    def sounds(self, ops: list[Stanza]) -> None:
        """Feed sound channel operations, one cycle's worth.

        The dialect is VΘXΔM's own: GlkOte never grew a sound
        vocabulary, but both ends of this wire are ours, so the
        update carries channel ops -- play, stop, volume -- in
        the order they happened, each play with its sound inlined
        whole as a data: url. A display that never learned the
        word simply ignores the field, which is the conforming
        quiet every sound game ships ready to accept.
        """

        self._sounds.extend(ops)

    def timer(self, interval: int, *, restart: bool = False) -> None:
        """Note the timer cadence in milliseconds, zero for none.

        Sent only when it changes -- resending even the same value
        restarts the display's clock, so a caller that means to
        restart says so (GlkOte: The Timer Update).
        """

        self._timer_request = (interval, restart)

    def typed(self, partials: dict[int, str]) -> None:
        """Note what the player has typed so far, window by window.

        Replaced whole each time: every event that can carry
        partial input carries the complete current picture, and a
        finished line's window is absent from its own event
        (GlkOte: Partial Input). A field that must be recreated --
        content reached its window, or its dress changed -- takes
        the noted text as its initial, so an interruption never
        eats a half-typed command; a carried field is left alone,
        since the display preserves its editing state itself.
        """

        self._typed = dict(partials)

    # -- the update itself -------------------------------------------------

    def update(
        self,
        *,
        exit: bool = False,  # noqa: A002 -- the field's name
        refresh: bool = False,
    ) -> Stanza:
        """Assemble the cycle into an update stanza, or the pass.

        A refresh assembles the whole picture instead: the display
        lost its state, so every window travels, buffers replay
        their kept scrollback behind a clear, grids resend every
        row, standing input fields are stamped anew, and a running
        timer is renamed -- an ordinary update in form, complete
        in content (GlkOte: the refresh input event).

        Raises:
            GlkOteError: When the cycle's pieces contradict each
                other -- content for an undeclared window, rows
                for a buffer, a click request on one, grid input
                with no cursor.
        """

        self._validated()

        windows = list(self._declared.values())
        windows_changed = self._shown is None or windows != self._shown
        content = self._content()

        self._retold(content)

        if refresh:
            content = self._retold_whole()

        conflicted = {entry["id"] for entry in content}
        input_changed = self._input_changed(conflicted)
        timer_field = self._timer_field()

        changed = (
            windows_changed
            or bool(content)
            or input_changed
            or timer_field is not _UNSET
            or self._prompt is not None
            or bool(self._sounds)
            or refresh
            or exit
        )

        if not changed:
            self._rested()

            return {"type": "pass"}

        gen = self._gen + 1
        stanza: Stanza = {"type": "update", "gen": gen}

        if windows_changed or refresh:
            stanza["windows"] = windows

        if content:
            stanza["content"] = content

        if input_changed or refresh:
            stanza["input"] = self._roster(gen, conflicted)

        if timer_field is not _UNSET:
            stanza["timer"] = timer_field
            self._timer_shown = timer_field if isinstance(timer_field, int) else 0
        elif refresh and self._timer_shown:
            stanza["timer"] = self._timer_shown

        if self._prompt is not None:
            stanza["specialinput"] = self._prompt

        if self._sounds:
            stanza["sounds"] = self._sounds
            self._sounds = []

        if exit:
            stanza["exit"] = True

        self._buried()

        self._gen = gen
        self._shown = windows

        self._rested()

        return stanza

    def _validated(self) -> None:
        """Refuse a cycle whose pieces contradict each other.

        Raises:
            GlkOteError: On the first contradiction found.
        """

        for fed, wanted, what in (
            (self._texts, "buffer", "text"),
            (self._changed, "grid", "rows"),
            (self._draws, "graphics", "drawing"),
        ):
            for ident in fed:
                held = self._declared.get(ident)

                if held is None:
                    msg = f"{what} arrived for window {ident}, never declared"

                    raise GlkOteError(msg)

                if held["type"] != wanted:
                    msg = f"{what} arrived for window {ident}, not a {wanted}"

                    raise GlkOteError(msg)

        for ident, entry in self._requests.items():
            held = self._declared.get(ident)

            if held is None:
                msg = f"input was asked of window {ident}, never declared"

                raise GlkOteError(msg)

            if entry.get("mouse") and held["type"] == "buffer":
                # "Buffer windows do not support mouse-click
                # input" (GlkOte: The Input Update Array).
                msg = f"window {ident} is a buffer, and a buffer takes no clicks"

                raise GlkOteError(msg)

            if held["type"] == "grid" and "type" in entry and "xpos" not in entry:
                msg = f"grid window {ident} takes input at a cursor, and none came"

                raise GlkOteError(msg)

            # The stage dialect: a canvas's editor is placed and
            # sized by the game, or it cannot be drawn.
            if (
                held["type"] == "graphics"
                and entry.get("type") == "line"
                and ("xpos" not in entry or "cell" not in entry)
            ):
                msg = (
                    f"graphics window {ident} takes its editor at a "
                    "placed cell, and none came"
                )

                raise GlkOteError(msg)

            if ("cell" in entry or "ink" in entry) and held["type"] != "graphics":
                msg = f"window {ident} is no stage; only a canvas's editor has a cell"

                raise GlkOteError(msg)

    def _content(self) -> list[Stanza]:
        """The content array: every window with something to show."""

        content: list[Stanza] = []

        for ident in self._declared:
            if ident in self._texts:
                content.append(self._texts[ident])
            elif self._changed.get(ident):
                content.append({"id": ident, "lines": self._changed[ident]})
            elif self._draws.get(ident):
                content.append({"id": ident, "draw": self._draws[ident]})

        return content

    def _input_changed(self, conflicted: set[int]) -> bool:
        """Whether the input array must travel this update.

        The array is sent when a field was posted or cancelled --
        which is exactly when the roster differs from what the
        display holds -- and when content reached a window whose
        field would otherwise be carried, since a carried field
        forbids content and must be recreated at the new
        generation (GlkOte: The Input Update Array).
        """

        if set(self._requests) != set(self._asked):
            return True

        return any(
            _bared(self._asked[ident]) != entry
            or ("gen" in self._asked[ident] and ident in conflicted)
            for ident, entry in self._requests.items()
        )

    def _roster(self, gen: int, conflicted: set[int]) -> list[Stanza]:
        """The input array, each field wearing its generation.

        A field carried unchanged keeps the generation it was
        created at; one posted, altered, or standing in a window
        that received content is stamped anew -- the protocol's
        "new version of the input field at the current
        generation", which is also what makes echoing a line and
        asking again in one update legal. A cancel-and-reask with
        identical parameters and no content is indistinguishable
        from a carried field here, and carries.
        """

        roster: list[Stanza] = []
        asked: dict[int, Stanza] = {}

        for ident, candidate in self._requests.items():
            entry = dict(candidate)
            carried = False

            if "type" in entry:
                held = self._asked.get(ident)
                carried = (
                    held is not None
                    and "gen" in held
                    and _bared(held) == candidate
                    and ident not in conflicted
                )
                entry["gen"] = held["gen"] if carried and held else gen

            # The memo keeps the game's own dress, so a steady
            # request stays carried; only the spoken entry takes
            # the player's half-typed text as its initial, and
            # only when the field is being made anew (GlkOte:
            # Partial Input).
            asked[ident] = entry
            spoken = entry

            if not carried and entry.get("type") == "line":
                typed = self._typed.get(ident)

                if typed:
                    spoken = {**entry, "initial": typed}

            roster.append(spoken)

        roster.sort(key=lambda entry: entry["id"])

        self._asked = asked

        return roster

    def _timer_field(self) -> object:
        """The timer field to send, or the unset sentinel.

        A change travels, a cancel travels as null, and a steady
        cadence stays silent -- resending would restart the
        display's clock (GlkOte: The Timer Update).
        """

        if self._timer_request is None:
            return _UNSET

        interval, restart = self._timer_request

        if interval > 0 and (interval != self._timer_shown or restart):
            return interval

        if interval == 0 and self._timer_shown != 0:
            return None

        return _UNSET

    def _retold(self, content: list[Stanza]) -> None:
        """Keep each buffer's sent paragraphs for a refresh's re-telling.

        Bounded at KEPT_PARAGRAPHS: a display that reconnects gets
        the recent scrollback, not the whole session -- and a
        clear starts the keeping over, exactly as it starts the
        display over.
        """

        for entry in content:
            ident = entry["id"]

            if ident not in self._texts:
                continue

            held = self._kept.setdefault(ident, [])

            if entry.get("clear"):
                held.clear()

            held.extend(dict(piece) for piece in entry.get("text", []))
            del held[:-KEPT_PARAGRAPHS]

    def _retold_whole(self) -> list[Stanza]:
        """The complete picture, for a display that lost its own.

        Buffers replay their kept scrollback behind a clear --
        pictures and covers ride along, since their data: urls
        were kept with the text -- grids resend every row, the
        blank ones as bare line numbers, and canvases carry
        whatever this cycle's re-feed drew, because pixels are the
        game's to repaint (GlkOte: Redraw Events).
        """

        content: list[Stanza] = []

        for ident, held in self._declared.items():
            if held["type"] == "buffer":
                entry: Stanza = {"id": ident, "clear": True}
                kept = self._kept.get(ident, [])

                if kept:
                    entry["text"] = [dict(piece) for piece in kept]

                content.append(entry)
            elif held["type"] == "grid":
                content.append(
                    {
                        "id": ident,
                        "lines": [
                            {"line": index, "content": spans}
                            if spans
                            else {"line": index}
                            for index, spans in enumerate(self._rows.get(ident, []))
                        ],
                    }
                )
            elif self._draws.get(ident):
                content.append({"id": ident, "draw": self._draws[ident]})

        return content

    def _buried(self) -> None:
        """Retire the windows this cycle no longer declares."""

        previously = {held["id"] for held in self._shown or []}

        for ident in previously - set(self._declared):
            self._rows.pop(ident, None)
            self._open.pop(ident, None)
            self._flowing.pop(ident, None)
            self._asked.pop(ident, None)
            self._typed.pop(ident, None)
            self._kept.pop(ident, None)
            self._retired.add(ident)

    def _rested(self) -> None:
        """Clear the cycle, ready for the next round of feeding."""

        self._declared = {}
        self._texts = {}
        self._changed = {}
        self._draws = {}
        self._requests = {}
        self._timer_request = None
        self._prompt = None


def _unrolled(run: object) -> "tuple[str, int, str, Ink | None]":
    """A text run in either length: colourless, or wearing ink."""

    held = cast("TextRun", run)

    if len(held) == _INKED_RUN:
        return held[0], held[1], held[2], held[3]

    return held[0], held[1], held[2], None


def _trimmed(spans: list[Stanza]) -> list[Stanza]:
    """Strip a grid row's trailing plain whitespace.

    The display pads short lines with exactly this (GlkOte: The
    Line Data Array), so stripping it first makes equal rows
    compare equal however the padding fell.
    """

    while spans:
        last = spans[-1]

        if last["style"] != "normal" or "hyperlink" in last:
            break

        text = last["text"].rstrip(" ")

        if text:
            if text != last["text"]:
                spans[-1] = {**last, "text": text}

            break

        spans.pop()

    return spans


def _bared(entry: Stanza) -> Stanza:
    """An input entry with its generation set aside, for comparing."""

    return {key: value for key, value in entry.items() if key != "gen"}


def measured(metrics: Stanza, prefix: str) -> tuple[float, float, float, float]:
    """One window kind's cell measures, with the spec's fallback chain.

    (width, height, margin x, margin y): a partial metrics object
    falls back from the qualified name to the generic to the
    default, the rules RemGlk reads by (GlkOte: The Metrics
    Object). Shared because both machines measure the same way.
    """

    def field(name: str, *fallbacks: str, default: float) -> float:
        for key in (prefix + name, *fallbacks):
            if key in metrics:
                return float(metrics[key])

        return default

    return (
        field("charwidth", "charwidth", default=1),
        field("charheight", "charheight", default=1),
        field("marginx", "marginx", "margin", default=0),
        field("marginy", "marginy", "margin", default=0),
    )


def carded(record: "IFiction") -> list[tuple[str, str]]:
    """The iFiction card as (style name, text) runs.

    The four fields WinFrotz's own little window shows: the title
    in the header dress, the headline and author emphasized, then
    the description's paragraphs separated by blank lines -- each
    <br/>-broken line its own paragraph -- and a closing blank
    line before the story begins. A record with none of them
    makes no card at all (Babel: The iFiction format).
    """

    lines: list[tuple[str, str]] = []

    if record.title:
        lines.append(("header", record.title + "\n"))

    if record.headline:
        lines.append(("emphasized", record.headline + "\n"))

    if record.author:
        lines.append(("emphasized", record.author + "\n"))

    if record.description:
        paragraphs = [held for held in record.description.split("\n") if held]

        lines.append(("normal", "\n" + "\n\n".join(paragraphs) + "\n"))

    if lines:
        lines.append(("normal", "\n"))

    return lines


def partials(partial: object) -> dict[int, str]:
    """An event's partial-input object as ident-keyed text.

    JSON spells the window ids as object keys -- strings -- and
    anything not shaped like typing is quietly no typing at all
    (GlkOte: Partial Input).
    """

    if not isinstance(partial, dict):
        return {}

    stashed: dict[int, str] = {}

    for key, text in partial.items():
        if isinstance(text, str) and str(key).isdigit():
            stashed[int(key)] = text

    return stashed


def read_stanza(reader: TextIO) -> Stanza | None:
    """The next stanza from the display, or None when it hung up.

    Raises:
        GlkOteError: For JSON that is not an object.
        json.JSONDecodeError: For what is not JSON at all.
    """

    for line in reader:
        if not line.strip():
            continue

        parsed = json.loads(line)

        if not isinstance(parsed, dict):
            msg = "a stanza is a JSON object"

            raise GlkOteError(msg)

        return cast("Stanza", parsed)

    return None


def write_stanza(writer: TextIO, stanza: Stanza) -> None:
    """One stanza out, compact, on its own line, flushed.

    Flushed every time: an update parked in a pipe's buffer is a
    display waiting forever.
    """

    writer.write(json.dumps(stanza, separators=(",", ":")) + "\n")
    writer.flush()
