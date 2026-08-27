"""The Å-machine over the GlkOte wire: the document in a buffer.

The face is deliberately the reference terminal's document model
on the wire: one buffer window carries the whole telling through
the certified plain voice at width zero -- the display does the
wrapping -- and the status areas stay honestly unclaimed, the
way the reference Node frontend leaves them. A line wait asks
for a line, a key wait for a keystroke, and the story's META
bibliography opens the page as the doorway card, the house
courtesy every machine's face extends.

Savefiles stay with the blocking faces for now: a save over the
wire needs the suspended-file dance the Z-Machine's Filing wait
performs, and that is a named road, not this rung.
"""

import json
from typing import TextIO

from voxam.aamachine.machine import Machine
from voxam.aamachine.output import PlainVoice
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
        self.voice = PlainVoice(story, width=0)
        self.waiting = ""
        self._mark = 0
        self._size = (0, 0)
        self._refresh = False
        self._opening: list[TextRun] = _carded(story)

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

    def render(self, *, exit: bool = False) -> Stanza:  # noqa: A002 -- the field's name
        """Compose everything told since the last update."""

        width, height = self._size
        self.page.window(_BUFFER, "buffer", 0, (0, 0, width, height))

        told = self.voice.told()
        runs: list[TextRun | object] = list(self._opening)

        if told[self._mark :]:
            runs.append(("normal", 0, told[self._mark :]))

        self._opening = []
        self._mark = len(told)

        if runs:
            self.page.buffer(_BUFFER, runs)

        if not exit:
            if self.waiting == "line":
                self.page.line_input(_BUFFER, _CAPACITY)
            elif self.waiting == "key":
                self.page.char_input(_BUFFER)

        refresh, self._refresh = self._refresh, False

        return self.page.update(exit=exit, refresh=refresh)

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

            return ADVANCE

        if kind == "char" and self.waiting == "key":
            code = _keyed(str(stanza.get("value", "")))

            if code is None:
                return PASS

            self.waiting = machine.deliver_key(code)

            return ADVANCE

        return PASS


def _keyed(value: str) -> int | None:
    """A char event's value as a machine keypress, or None."""

    if len(value) == 1:
        return ord(value)

    return _KEYS.get(value)


def _carded(story: Story) -> list[TextRun]:
    """The META bibliography as the page's doorway card.

    The title stands as a header, the author beneath it, and the
    blurb as its own paragraphs -- the same card every face opens
    with, drawn from the chunk instead of the treaty record
    (Aa-machine: META).
    """

    runs: list[TextRun] = []
    title = story.meta.get("title")
    author = story.meta.get("author")
    blurb = story.meta.get("blurb")

    if title:
        runs.append(("header", 0, title + "\n"))

    if author:
        runs.append(("emphasized", 0, f"by {author}\n"))

    if blurb:
        runs.append(("normal", 0, blurb.replace("\x10", "\n") + "\n"))

    if runs:
        runs.append(("normal", 0, "\n"))

    return runs


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
