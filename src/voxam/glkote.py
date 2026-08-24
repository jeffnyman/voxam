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

from typing import Any

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

# The window kinds the protocol draws; pairs and blanks are the
# server's business and never appear (GlkOte: The Windows Update
# Array).
_KINDS = frozenset({"buffer", "grid", "graphics"})

# The drawing operations a graphics content entry may carry
# (GlkOte: Graphics Window Updates).
_SPECIALS = frozenset({"setcolor", "fill", "image"})
_RECT = ("x", "y", "width", "height")

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
        self._timer_shown = 0
        self._retired: set[int] = set()

        # The cycle in progress, cleared by every update.
        self._declared: dict[int, Stanza] = {}
        self._texts: dict[int, Stanza] = {}
        self._changed: dict[int, list[Stanza]] = {}
        self._draws: dict[int, list[Stanza]] = {}
        self._requests: dict[int, Stanza] = {}
        self._timer_request: tuple[int, bool] | None = None

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
    ) -> None:
        """Declare a window that stands visible this cycle.

        Every visible window is declared every cycle; one left out
        is closed, its id retired for good -- the protocol forbids
        reuse (GlkOte: The Windows Update Array). The box arrives
        as (left, top, right, bottom) in pixels, the shape the
        window models already keep; a grid names its columns and
        rows, a graphics window its drawable size.

        Raises:
            GlkOteError: For an unknown kind, a retired or
                twice-declared id, or sizes that contradict the
                kind.
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
        runs: list[tuple[str, int, str] | object],
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
        below the margin images.

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
        self, runs: list[tuple[str, int, str] | object]
    ) -> tuple[list[list[Stanza]], set[int]]:
        """Split a run stream into paragraphs at newlines and breaks.

        Returns the paragraphs as span lists, and the indices of
        those that follow a flow break.
        """

        segments: list[list[Stanza]] = [[]]
        breaks: set[int] = set()

        for run in runs:
            if run is FLOWBREAK:
                segments.append([])
                breaks.add(len(segments) - 1)

                continue

            style, link, text = run  # type: ignore[misc]
            pieces = text.split("\n")

            self._spanned(segments[-1], style, link, pieces[0])

            for piece in pieces[1:]:
                segments.append([])
                self._spanned(segments[-1], style, link, piece)

        return segments, breaks

    def _spanned(self, spans: list[Stanza], style: str, link: int, text: str) -> None:
        """Add one piece of styled text to a paragraph's spans.

        Adjacent pieces wearing the same dress coalesce -- two
        machine styles may share one protocol name -- and the
        hyperlink key appears only on a real link (GlkOte: The
        Line Data Array).

        Raises:
            GlkOteError: For a style the protocol does not name.
        """

        if style not in _STYLE_NAMES:
            msg = f"no style is named {style!r} (GlkOte: The Line Data Array)"

            raise GlkOteError(msg)

        if not text:
            return

        if (
            spans
            and spans[-1]["style"] == style
            and spans[-1].get("hyperlink", 0) == link
        ):
            spans[-1]["text"] += text

            return

        span: Stanza = {"style": style, "text": text}

        if link:
            span["hyperlink"] = link

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

    def grid(self, ident: int, rows: list[list[tuple[str, int, str]]]) -> None:
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

            for style, link, text in row:
                self._spanned(spans, style, link, text)

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
        (GlkOte: Graphics Window Updates).

        Raises:
            GlkOteError: For an operation the protocol does not
                draw, or a fill with only part of a rectangle.
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

        self._draws.setdefault(ident, []).extend(ops)

    def line_input(  # noqa: PLR0913 -- the shape of an input field
        self,
        ident: int,
        maxlen: int,
        *,
        initial: str = "",
        terminators: tuple[str, ...] = (),
        cursor: tuple[int, int] | None = None,
        hyperlink: bool = False,
        mouse: bool = False,
    ) -> None:
        """Ask for a line of input in a window.

        Raises:
            GlkOteError: For a terminator the protocol cannot
                name, or a second request in one window.
        """

        entry: Stanza = {"id": ident, "type": "line", "maxlen": maxlen}

        if initial:
            entry["initial"] = initial

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

    def timer(self, interval: int, *, restart: bool = False) -> None:
        """Note the timer cadence in milliseconds, zero for none.

        Sent only when it changes -- resending even the same value
        restarts the display's clock, so a caller that means to
        restart says so (GlkOte: The Timer Update).
        """

        self._timer_request = (interval, restart)

    # -- the update itself -------------------------------------------------

    def update(self, *, exit: bool = False) -> Stanza:  # noqa: A002 -- the field's name
        """Assemble the cycle into an update stanza, or the pass.

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
        conflicted = {entry["id"] for entry in content}
        input_changed = self._input_changed(conflicted)
        timer_field = self._timer_field()

        changed = (
            windows_changed
            or bool(content)
            or input_changed
            or timer_field is not _UNSET
            or exit
        )

        if not changed:
            self._rested()

            return {"type": "pass"}

        gen = self._gen + 1
        stanza: Stanza = {"type": "update", "gen": gen}

        if windows_changed:
            stanza["windows"] = windows

        if content:
            stanza["content"] = content

        if input_changed:
            stanza["input"] = self._roster(gen, conflicted)

        if timer_field is not _UNSET:
            stanza["timer"] = timer_field
            self._timer_shown = timer_field if isinstance(timer_field, int) else 0

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

            if "type" in entry:
                held = self._asked.get(ident)
                carried = (
                    held is not None
                    and "gen" in held
                    and _bared(held) == candidate
                    and ident not in conflicted
                )
                entry["gen"] = held["gen"] if carried and held else gen

            roster.append(entry)
            asked[ident] = entry

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

    def _buried(self) -> None:
        """Retire the windows this cycle no longer declares."""

        previously = {held["id"] for held in self._shown or []}

        for ident in previously - set(self._declared):
            self._rows.pop(ident, None)
            self._open.pop(ident, None)
            self._flowing.pop(ident, None)
            self._asked.pop(ident, None)
            self._retired.add(ident)

    def _rested(self) -> None:
        """Clear the cycle, ready for the next round of feeding."""

        self._declared = {}
        self._texts = {}
        self._changed = {}
        self._draws = {}
        self._requests = {}
        self._timer_request = None


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
