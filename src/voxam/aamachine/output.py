"""The Å-machine's output subsystem: the Voice the engine speaks through.

The specification splits an interpreter into an engine and a
device-specific output subsystem joined by an API of output calls
(Aa-machine: Output model). Voice is that API as a protocol, and
PlainVoice is the dumb-terminal subsystem: an 80-column word-wrapping
collector that ignores every status area, matching the reference
Node frontend's io object line for line -- which is what lets a
Voxam transcript diff clean against the community fork's own gold
output.

Style classes arrive as indexes into the LOOK chunk's table; the
plain voice honors only the em-sized vertical margins, the way the
reference terminal does.
"""

from typing import Protocol

from voxam.aamachine.story import Story
from voxam.errors import AAMachineError

# The columns a plain telling wraps at, the reference default.
_WIDTH = 80

# A LOOK table opens with its two-byte style count.
_COUNT_SIZE = 2


class Voice(Protocol):
    """The output API an Å-machine engine speaks through.

    Every call mirrors one output_* function of the specification's
    coupling API (Aa-machine: Output model). The has_* flags answer
    the VM_INFO interpreter-feature selectors that concern output.
    """

    has_links: bool
    has_styles: bool
    has_color: bool
    has_alignment: bool
    has_top_status: bool
    has_inline_status: bool
    has_saves: bool

    def say(self, text: str) -> None:
        """Print text, wrappable at its spaces and hyphens."""

    def nbsp(self) -> None:
        """Print a space no wrap may break at."""

    def space(self) -> None:
        """Print one breakable space."""

    def spaces(self, count: int) -> None:
        """Print a run of forced spaces."""

    def line(self) -> None:
        """Break the line."""

    def par(self) -> None:
        """End the paragraph."""

    def enter_div(self, style: int) -> None:
        """Open a div of the given style class."""

    def leave_div(self, style: int) -> None:
        """Close the current div, its class restated."""

    def enter_span(self, style: int) -> None:
        """Open a span of the given style class."""

    def leave_span(self) -> None:
        """Close the current span."""

    def set_body(self, style: int) -> None:
        """Dress the document body in a style class."""

    def enter_status(self, area: int, style: int) -> None:
        """Enter a status area, clearing it."""

    def leave_status(self) -> None:
        """Leave the status area."""

    def enter_link(self, words: str) -> None:
        """Open a link whose click types the given words."""

    def leave_link(self) -> None:
        """Close the current link."""

    def enter_link_res(self, resource: int) -> None:
        """Open a link to a resource."""

    def leave_link_res(self) -> None:
        """Close the resource link."""

    def enter_self_link(self) -> None:
        """Open a link whose click types its own text."""

    def leave_self_link(self) -> None:
        """Close the self link."""

    def embed_res(self, resource: int) -> None:
        """Embed a resource in the stream."""

    def can_embed_res(self, resource: int) -> bool:
        """Whether the resource could be embedded."""

    def progress(self, amount: int, total: int) -> None:
        """Draw a progress bar at amount of total."""

    def set_style(self, bits: int) -> None:
        """Turn on the deprecated style bits."""

    def reset_style(self, bits: int) -> None:
        """Turn off the deprecated style bits."""

    def unstyle(self) -> None:
        """Return to the default text style."""

    def clear(self) -> None:
        """Clear the main area, the div stack kept."""

    def clear_all(self) -> None:
        """Clear the main area and hide the status areas."""

    def clear_status(self) -> None:
        """Hide all status areas."""

    def clear_links(self) -> None:
        """Turn old links into static text."""

    def clear_old(self) -> None:
        """Clear text the player has already read."""

    def clear_div(self) -> None:
        """Clear or fold away the current div."""

    def leave_all(self) -> None:
        """Return to the initial output state."""

    def sync(self) -> None:
        """Bring the display up to date."""

    def script_on(self) -> bool:
        """Start a transcript; True on success."""

    def script_off(self) -> None:
        """Stop the transcript."""

    def script_active(self) -> bool:
        """Whether a transcript is running."""

    def reset(self) -> None:
        """Forget everything; the display starts over."""

    def measured(self, dimension: int) -> int:
        """The current div's width (0) or height (1) in characters."""

    def trace(self, text: str) -> None:
        """Print one debug tracepoint on its own line."""

    def save(self, data: bytes) -> bool:
        """Keep a savefile; True on success."""

    def restore(self) -> "bytes | None":
        """A previously kept savefile, None when there is none."""


class PlainVoice:
    """The dumb-terminal voice: 80 columns, no dress, no status.

    Words buffer until a space or hyphen lets them break, a line
    wraps when the pending word would overrun the width, and the
    status areas are silently swallowed -- the same behavior as
    the reference Node frontend, whose transcripts this voice's
    tellings diff against.
    """

    has_links = False
    has_styles = False
    has_color = False
    has_alignment = False
    has_top_status = False
    has_inline_status = False
    has_saves = False

    def __init__(self, story: Story, width: int = _WIDTH) -> None:
        """Ready an empty telling for one story's output."""

        self._styles = styled(story)
        self._width = width
        self._told: list[str] = []
        self.reset()

    def told(self) -> str:
        """Everything said so far, the pending word flushed out."""

        self._flush()

        return "".join(self._told)

    def reset(self) -> None:
        """Forget everything; the display starts over."""

        self._hidden = False
        self._word = ""
        self._spaces = 0
        self._x = 0
        self._newlines = 1

    def echoed(self, text: str) -> None:
        """Land an input echo raw, straight past the word-wrapper.

        The reference frontend's readline echoes typed characters
        without telling its own io; a diff-faithful telling does
        the same. No newline lands here -- that is the Enter key's
        doing, which only a line input's prompted() models.
        """

        self._flush()
        self._told.append(text)

    def prompted(self) -> None:
        """Note that a sent line's echo reset the cursor.

        The reference frontend resets its wrap state on delivering
        a line -- and, deliberately, not on delivering keys.
        """

        self._x = 0
        self._spaces = 0
        self._newlines = 1

    def say(self, text: str) -> None:
        """Print text, wrappable at its spaces and hyphens."""

        if self._hidden:
            return

        for piece in text:
            if piece == " ":
                self._flush()
                self._spaces += 1
            elif piece == "-":
                self._word += piece
                self._flush()
            else:
                self._word += piece

    def nbsp(self) -> None:
        """Print a space no wrap may break at."""

        if not self._hidden:
            self._word += " "

    def space(self) -> None:
        """Print one breakable space."""

        self.say(" ")

    def spaces(self, count: int) -> None:
        """Print a run of forced spaces, clamped to the line."""

        if self._hidden:
            return

        self._flush()
        count = min(count, self._width - self._x)
        self._told.append(" " * count)
        self._x += count
        self._newlines = 0

    def line(self) -> None:
        """Break the line."""

        if not self._hidden:
            self._flush()
            self._spaced(0)

    def par(self) -> None:
        """End the paragraph."""

        if not self._hidden:
            self._flush()
            self._spaced(1)

    def enter_div(self, style: int) -> None:
        """Open a div: break the line, honoring its top margin."""

        if not self._hidden:
            self._flush()
            self._spaced(self._margined(style, "margin-top"))

    def leave_div(self, style: int) -> None:
        """Close a div: break the line, honoring its bottom margin."""

        if not self._hidden:
            self._flush()
            self._spaced(self._margined(style, "margin-bottom"))

    def enter_span(self, style: int) -> None:
        """Open a span; plain text carries no dress."""

    def leave_span(self) -> None:
        """Close the span."""

    def set_body(self, style: int) -> None:
        """Dress the body; plain text carries no dress."""

    def enter_status(self, area: int, style: int) -> None:  # noqa: ARG002 -- swallowed whole, class and area alike
        """Enter a status area: swallowed whole on a plain telling."""

        self.line()
        self._hidden = True

    def leave_status(self) -> None:
        """Leave the status area; the telling speaks again."""

        self._hidden = False

    def enter_link(self, words: str) -> None:
        """Open a link; plain text renders it static."""

    def leave_link(self) -> None:
        """Close the link."""

    def enter_link_res(self, resource: int) -> None:
        """Open a resource link; plain text renders it static."""

    def leave_link_res(self) -> None:
        """Close the resource link."""

    def enter_self_link(self) -> None:
        """Open a self link; plain text renders it static."""

    def leave_self_link(self) -> None:
        """Close the self link."""

    def embed_res(self, resource: int) -> None:
        """Embed nothing; a plain telling cannot."""

    def can_embed_res(self, resource: int) -> bool:  # noqa: ARG002 -- the answer is no for every resource
        """A plain telling embeds nothing."""

        return False

    def progress(self, amount: int, total: int) -> None:
        """Draw the progress bar as an ASCII gauge on its own line."""

        if self._hidden:
            return

        room = (self._width if self._width > 0 else _WIDTH) - 3
        filled = int(room * amount / total + 0.5) if total else 0
        self.enter_div(-1)
        self.say("[" + "=" * filled + " " * (room - filled) + "]")
        self.leave_div(-1)

    def set_style(self, bits: int) -> None:
        """Set nothing; plain text carries no styles."""

    def reset_style(self, bits: int) -> None:
        """Reset nothing; plain text carries no styles."""

    def unstyle(self) -> None:
        """Unstyle nothing; plain text carries no styles."""

    def clear(self) -> None:
        """Clear by paragraph break; a telling keeps its past."""

        self.par()

    def clear_all(self) -> None:
        """Clear by paragraph break; a telling keeps its past."""

        self.par()

    def clear_status(self) -> None:
        """No status areas stand to hide."""

    def clear_links(self) -> None:
        """No links stand to retire."""

    def clear_old(self) -> None:
        """A telling keeps its past."""

    def clear_div(self) -> None:
        """A telling keeps its past."""

    def leave_all(self) -> None:
        """Return to the initial state: line broken, nothing hidden."""

        self.line()
        self._hidden = False

    def sync(self) -> None:
        """Flush the pending word to the telling."""

        self._flush()

    def trace(self, text: str) -> None:
        """Print one debug tracepoint raw on its own line."""

        if not self._hidden:
            self._flush()
            self._spaced(0)
            self._told.append(text)
            self._x = len(text)
            self._newlines = 0
            self._flush()
            self._spaced(0)

    def script_on(self) -> bool:
        """A plain telling is already its own transcript."""

        return False

    def script_off(self) -> None:
        """No transcript stands to stop."""

    def script_active(self) -> bool:
        """No transcript is ever running."""

        return False

    def measured(self, dimension: int) -> int:
        """The width in columns; the height is unknowable."""

        if dimension == 0:
            return max(self._width, 0)

        return 0

    def save(self, data: bytes) -> bool:  # noqa: ARG002 -- nothing is kept, whatever the bytes
        """A plain telling keeps no files."""

        return False

    def restore(self) -> bytes | None:
        """A plain telling keeps no files."""

        return None

    def _flush(self) -> None:
        """Land the pending spaces and word, wrapping first if needed."""

        pending = self._x + self._spaces + len(self._word)

        if self._width > 0 and pending > self._width:
            self._spaced(0)

        while self._spaces:
            if self._x:
                self._told.append(" ")
                self._x += 1

            self._spaces -= 1

        if self._word:
            self._told.append(self._word)
            self._x += len(self._word)
            self._newlines = 0
            self._word = ""

    def _spaced(self, wanted: int) -> None:
        """Ensure wanted + 1 newlines stand at the telling's end."""

        while self._newlines < wanted + 1:
            self._told.append("\n")
            self._newlines += 1

        self._x = 0
        self._spaces = 0

    def _margined(self, style: int, edge: str) -> int:
        """A style's em-sized margin, zero when it names none."""

        if 0 <= style < len(self._styles):
            claim = self._styles[style].get(edge, "").strip()

            if claim.endswith("em") and claim[:-2].strip().isdigit():
                return int(claim[:-2])

        return 0


def styled(story: Story) -> tuple[dict[str, str], ...]:
    """The LOOK chunk's style classes, each a key-value dress.

    Each class is a run of null-terminated CSS-shaped pairs ended
    by a blank entry; keys keep their source case, so readers must
    compare charitably (Aa-machine: LOOK).

    Raises:
        AAMachineError: For a table the chunk cannot hold whole.
    """

    payload = story.summed(b"LOOK").payload

    if len(payload) < _COUNT_SIZE:
        msg = "the LOOK chunk is too short for its own count (Aa-machine: LOOK)"

        raise AAMachineError(msg)

    count = int.from_bytes(payload[0:2], "big")

    if 2 + count * 2 > len(payload):
        msg = (
            f"the LOOK table claims {count} styles, past the chunk's "
            f"{len(payload)} bytes (Aa-machine: LOOK)"
        )

        raise AAMachineError(msg)

    styles = []

    for seat in range(count):
        at = int.from_bytes(payload[2 + seat * 2 : 4 + seat * 2], "big")
        dress: dict[str, str] = {}

        while at < len(payload) and payload[at]:
            ended = payload.find(b"\x00", at)

            if ended < 0:
                msg = f"style {seat} is missing its null ending (Aa-machine: LOOK)"

                raise AAMachineError(msg)

            told = payload[at:ended].decode("ascii", "replace")

            if ":" in told:
                key, _, value = told.partition(":")
                dress[key.strip()] = value.strip()

            at = ended + 1

        styles.append(dress)

    return tuple(styles)
