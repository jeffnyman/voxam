"""The Å-machine over the GlkOte wire: the document in a buffer.

The face is deliberately the reference terminal's document model
on the wire: one buffer window carries the whole telling through
the certified plain voice at width zero -- the display does the
wrapping -- and the status areas stay honestly unclaimed, the
way the reference Node frontend leaves them. A line wait asks
for a line, a key wait for a keystroke, and the story's META
bibliography opens the page as the doorway card, the house
courtesy every machine's face extends.

The document travels dressed: the wardrobe's bold and italic
ride the display's own stock styles -- subheader and emphasized,
with alert for both at once, which the specification's bar
permits to equal bold -- and the sheet's colors ride as per-span
ink under the display's colors grant, the same dialect word the
Z-Machine's §8.3 colors travel by. VM_INFO answers the styling
question with yes on any display and the color question with the
grant's own truth (Aa-machine: VM_INFO).

Savefiles stay with the blocking faces for now: a save over the
wire needs the suspended-file dance the Z-Machine's Filing wait
performs, and that is a named road, not this rung.
"""

import base64
import json
from typing import TextIO

from voxam.aamachine.machine import Machine
from voxam.aamachine.output import Outfit, StyledVoice
from voxam.aamachine.story import Story
from voxam.errors import GlkOteError, VoxamError
from voxam.glkote import (
    Page,
    Stanza,
    TextRun,
    partials,
    read_stanza,
    write_stanza,
)
from voxam.glulx.glk.resources import image_size

# The verdicts accept hands back: run on, redraw the standing
# wait, or answer the protocol's pass.
ADVANCE = "advance"
STAND = "stand"
PASS = "pass"  # noqa: S105 -- a verdict, not a secret

# The one window the document lives in.
_BUFFER = 1

# The longest line the input field accepts, the wire's own cap.
_CAPACITY = 256

# The reserved keypress codes by their GlkOte names (Aa-machine:
# Text; GlkOte: Char Input Events).
_KEYS = {
    "return": 0x0D,
    "delete": 0x08,
    "up": 0x10,
    "down": 0x11,
    "left": 0x12,
    "right": 0x13,
}

# Events that never carry a partial-input field.
_NO_PARTIAL = frozenset({"init", "specialresponse", "refresh", "debuginput"})

# The bare outfit every session opens in.
_PLAIN: Outfit = (False, False, False, None, None)


class WireVoice(StyledVoice):
    """The wire's voice: the plain document, its dress marked.

    The telling stays exactly the certified document at width
    zero; each style change lands as a mark -- an offset into the
    telling and the outfit worn from there -- and the face cuts
    the drained text into styled runs along them. Styling is
    always claimable on the wire, the display's stock styles
    rendering bold and italic; color waits on the display's own
    grant, which the face sets at begin.

    A resource the story carries is marked the same way, at the
    offset it was asked for, and the face sets the picture into
    the flow there. Only a resource this story holds is claimed:
    a URL naming somebody's network is not an interpreter's
    business, and a display told no shows whatever the story says
    instead (Aa-machine: CAN_EMBED_RES).
    """

    has_styles = True

    def __init__(self, story: Story) -> None:
        """Speak at width zero; the display wraps."""

        super().__init__(story, 0)

        self._story = story
        self.marks: list[tuple[int, Outfit]] = []
        self.embeds: list[tuple[int, Stanza]] = []

    def _fitted(self) -> None:
        """Mark the outfit change at the telling's current end."""

        self.marks.append((len(self.told()), self._wardrobe.folded()))

    def can_embed_res(self, resource: int) -> bool:
        """Whether this story carries the resource, decodably."""

        return _pictured(self._story, resource) is not None

    def embed_res(self, resource: int) -> None:
        """Mark a resource at the telling's current end.

        The span is built here rather than at render, so what is
        marked is a picture already known to be showable: the face
        has nothing left to decide when it walks the marks.
        """

        picture = _pictured(self._story, resource)

        if picture is not None:
            self.embeds.append((len(self.told()), picture))


class GlkOteFrontend:
    """One Å-machine session's face on the wire.

    The voice attribute is what the machine speaks through: the
    certified plain voice at width zero, its telling drained into
    the buffer window a cycle at a time.

    Attributes:
        page: The update builder.
        voice: The machine's voice.
        waiting: The machine's standing wait -- "line", "key", or
            "quit" -- kept here so render can ask for the right
            input.
    """

    def __init__(self, story: Story) -> None:
        """Ready the page and the voice for one story."""

        self._story = story
        self.page = Page()
        self.voice = WireVoice(story)
        self.waiting = ""
        self._mark = 0
        self._size = (0, 0)
        self._refresh = False
        self._outfit: Outfit = _PLAIN
        # The sidecar seam: granted by the display's "voxam"
        # token; the serving loop attaches the machine so the
        # discontinuity bit can be read (DESIGN: What the sidecar
        # carries). The card is read from the META chunk once,
        # here, because a story's bibliography cannot change while
        # it runs; it rides the first real update and is rested.
        self.machine: Machine | None = None
        self._speaks_voxam = False
        self._last_command: str | None = None
        self._card = _catalogued(story)

    def begin(self, stanza: Stanza) -> None:
        """Open the session on the init event's word.

        Raises:
            GlkOteError: When the metrics carry no size.
        """

        metrics = stanza.get("metrics")

        if not isinstance(metrics, dict) or "width" not in metrics:
            msg = "the init event's metrics carry no size (GlkOte: The Metrics Object)"

            raise GlkOteError(msg)

        self._size = (int(metrics["width"]), int(metrics.get("height", 0)))

        # Color is the dialect's own word: per-span ink travels
        # only to a display that says it renders it, the same
        # grant the Z-Machine's colors ride (Aa-machine: VM_INFO).
        support = stanza.get("support", [])
        self.voice.has_color = isinstance(support, list) and "colors" in support
        self._speaks_voxam = isinstance(support, list) and "voxam" in support

    def render(self, *, exit: bool = False) -> Stanza:  # noqa: A002 -- the field's name
        """Compose everything told since the last update."""

        width, height = self._size
        self.page.window(_BUFFER, "buffer", 0, (0, 0, width, height))

        told = self.voice.told()
        runs: list[TextRun | object] = []

        # Dress changes and pictures are both marked by their
        # offset into the telling, so they are walked as one
        # sequence: the text between two marks is cut once, and
        # whatever the mark was lands after it.
        marked: list[tuple[int, int, Outfit | Stanza]] = [
            (at, 0, outfit) for at, outfit in self.voice.marks
        ]
        marked += [(at, 1, picture) for at, picture in self.voice.embeds]

        for at, _kind, payload in sorted(marked, key=lambda mark: mark[:2]):
            if at > self._mark:
                runs.append(self._dressed(told[self._mark : at]))
                self._mark = at

            if isinstance(payload, dict):
                runs.append(payload)
            else:
                self._outfit = payload

        self.voice.marks.clear()
        self.voice.embeds.clear()

        if told[self._mark :]:
            runs.append(self._dressed(told[self._mark :]))

        self._mark = len(told)

        if runs:
            self.page.buffer(_BUFFER, runs)

        if not exit:
            if self.waiting == "line":
                self.page.line_input(_BUFFER, _CAPACITY)
            elif self.waiting == "key":
                self.page.char_input(_BUFFER)

        refresh, self._refresh = self._refresh, False

        return self.page.update(
            exit=exit,
            refresh=refresh,
            voxam=self._sidecar() if self._speaks_voxam else None,
        )

    def _sidecar(self) -> Stanza:
        """The voxam block, the Å-machine's honest share of it.

        The Å-machine keeps no location or score registers the
        wire could read, so only the wire's own facts travel: the
        last delivered line and the discontinuity bit, read once
        and rested. The story's card rides the first block and is
        rested the same way (DESIGN: What the sidecar carries).
        """

        block: Stanza = {}

        if self._card is not None:
            block["card"] = self._card
            self._card = None

        if self._last_command is not None:
            block["command"] = self._last_command

        if self.machine is not None and self.machine.discontinuity:
            self.machine.discontinuity = False
            block["discontinuity"] = True

        return block

    def _dressed(self, text: str) -> TextRun:
        """One run of telling, worn as the current outfit.

        Bold rides the display's subheader style and italic its
        emphasized; both at once ride alert, which the stock
        sheet renders bold -- the specification allows bold
        italic to equal either (Aa-machine: VM_INFO). The sheet's
        colors ride as the dialect's per-span ink, under the
        display's own grant.
        """

        bold, italic, _, ink, paper = self._outfit

        if bold and italic:
            style = "alert"
        elif bold:
            style = "subheader"
        elif italic:
            style = "emphasized"
        else:
            style = "normal"

        if self.voice.has_color and (ink is not None or paper is not None):
            return (style, 0, text, (_css(ink), _css(paper)))

        return (style, 0, text)

    def accept(self, machine: Machine, stanza: Stanza) -> str:  # noqa: PLR0911 -- one verdict per event kind
        """Translate one event; a delivery runs the machine on.

        A misaimed event -- input the machine is not waiting for
        -- earns the polite pass, never a fault: a stale display
        is a display to answer, not a session to end.
        """

        kind = stanza.get("type")

        if kind not in _NO_PARTIAL:
            self.page.typed(partials(stanza.get("partial")))

        if kind == "refresh":
            self._refresh = True

            return STAND

        if kind == "arrange":
            metrics = stanza.get("metrics")

            if isinstance(metrics, dict) and "width" in metrics:
                self._size = (int(metrics["width"]), int(metrics.get("height", 0)))

                return STAND

            return PASS

        if kind == "line" and self.waiting == "line":
            self.voice.prompted()
            self.waiting = machine.deliver_line(str(stanza.get("value", "")))
            self._last_command = str(stanza.get("value", ""))

            return ADVANCE

        if kind == "char" and self.waiting == "key":
            code = _keyed(str(stanza.get("value", "")))

            if code is None:
                return PASS

            self.waiting = machine.deliver_key(code)

            return ADVANCE

        return PASS


def _css(tint: "tuple[int, int, int] | None") -> str | None:
    """An RGB tint as the CSS the ink rides in, None riding whole."""

    if tint is None:
        return None

    return f"rgb({tint[0]},{tint[1]},{tint[2]})"


def _keyed(value: str) -> int | None:
    """A char event's value as a machine keypress, or None."""

    if len(value) == 1:
        return ord(value)

    return _KEYS.get(value)


def _pictured(story: Story, resource: int) -> "Stanza | None":
    """One resource as the display's own image span, or None.

    The bytes ride inside the update as a data: url, exactly as a
    Glulx picture does, so no host road is owed on the far side.
    A resource whose bytes no decoder here can measure is not
    claimed at all, rather than sent as a picture of unknown size
    for a display to guess at.
    """

    found = story.embedded(resource)

    if found is None:
        return None

    name, data = found
    size = image_size(data)

    if size is None:
        return None

    kind = "image/jpeg" if name.lower().endswith((".jpg", ".jpeg")) else "image/png"
    width, height = size

    return {
        "special": "image",
        "image": resource,
        "url": f"data:{kind};base64,{base64.b64encode(data).decode('ascii')}",
        "width": width,
        "height": height,
        "alignment": "inlinedown",
    }


def _catalogued(story: Story) -> Stanza | None:
    """The META bibliography as the sidecar's card, or None.

    The Å-machine carries its own bibliography rather than a
    treaty record, and it says the same things in its own words:
    a title, an author, and a blurb whose paragraph breaks are
    the chunk's own 0x10 bytes. There is no headline to give
    (Aa-machine: META).

    This used to open the page as text, the way the painted faces
    still show a card at the door, which put a publisher's blurb
    in the middle of the story's own first words. A display that
    speaks the sidecar is handed the same facts to keep aside
    instead, and a story that says none of the three has no card
    at all (DESIGN: What the sidecar carries).
    """

    blurb = story.meta.get("blurb")
    block: Stanza = {
        name: held
        for name, held in (
            ("title", story.meta.get("title")),
            ("author", story.meta.get("author")),
            ("description", blurb.replace("\x10", "\n") if blurb else None),
        )
        if held
    }

    return block or None


def fronted(story: Story) -> GlkOteFrontend:
    """The face for one story, the seam the sessions build through."""

    return GlkOteFrontend(story)


def serve(
    story: Story,
    reader: TextIO,
    writer: TextIO,
    *,
    seed: int | None = None,
) -> bool:
    """Drive one Å session over the protocol, stanza by stanza.

    The init comes first; thereafter the burst model: the machine
    runs to a wait, the update goes out, the answer is delivered.
    True is a session that ended cleanly; a broken conversation
    answers the protocol's own error stanza and is False.
    """

    try:
        opening = read_stanza(reader)

        if opening is None or opening.get("type") != "init":
            msg = (
                "the conversation opens with an init event "
                "(GlkOte: The Application's Life Story)"
            )

            raise GlkOteError(msg)

        face = fronted(story)
        face.begin(opening)

        machine = Machine(story, face.voice, seed=seed)
        face.machine = machine
        face.waiting = machine.run()

        while True:
            write_stanza(writer, face.render(exit=face.waiting == "quit"))

            if face.waiting == "quit":
                return True

            while True:
                stanza = read_stanza(reader)

                if stanza is None:
                    return True

                verdict = face.accept(machine, stanza)

                if verdict == ADVANCE:
                    break

                if verdict == STAND:
                    write_stanza(writer, face.render())

                    continue

                write_stanza(writer, {"type": "pass"})
    except json.JSONDecodeError as error:
        write_stanza(writer, {"type": "error", "message": f"voxam: not JSON: {error}"})

        return False
    except VoxamError as error:
        write_stanza(writer, {"type": "error", "message": f"voxam: {error}"})

        return False
