"""The Å-machine at the terminal: the plain voice, spoken live.

The drill is the reference Node frontend's own, certified against
its transcripts: a line wait takes the typed line whole, a key
wait takes it a keypress at a time with a return to finish, and
the terminal's own echo stands in for the readline echo the
transcripts carry. The voice here keeps files too: a save or
restore asks for its filename on the spot, the blocking face's
privilege (Aa-machine: Savefile).

At a real terminal the voice also dresses the text: the LOOK
chunk's classes ride every span, div, and body call, and the
ones a terminal can honor -- bold, italic, and color -- land as
the terminal's own attributes, with italics worn as underlines,
the Dialog debugger's own precedent. The escapes are injected
past the word-wrapper, which counts columns and must never see
a zero-width code. A piped session stays plain, so every
certified transcript still matches byte for byte, and VM_INFO
answers the styling and color questions truthfully per stream
(Aa-machine: VM_INFO).
"""

import shutil
import sys
from collections.abc import Callable
from typing import TextIO

from voxam.aamachine.machine import Machine
from voxam.aamachine.output import PlainVoice
from voxam.aamachine.story import Story

# The suffix a bare savefile name gains, the house courtesy.
SUFFIX = ".aasave"

# The named colors Dialog's style sheets actually use, as the
# CSS basics a terminal can mix (Aa-machine: LOOK).
_NAMED_COLORS = {
    "black": (0, 0, 0),
    "red": (205, 49, 49),
    "green": (13, 188, 121),
    "yellow": (229, 229, 16),
    "blue": (36, 114, 200),
    "magenta": (188, 63, 188),
    "cyan": (17, 168, 205),
    "white": (229, 229, 229),
    "gray": (128, 128, 128),
    "grey": (128, 128, 128),
    "orange": (255, 165, 0),
    "purple": (128, 0, 128),
    "brown": (165, 42, 42),
}

# The deprecated SET_STYLE bits (Aa-machine: SET_STYLE).
_BIT_REVERSE = 1
_BIT_BOLD = 2
_BIT_ITALIC = 4

# The CSS color spellings a terminal can mix: #rrggbb, #rgb, and
# rgb() with its three channels.
_LONG_HEX = 7
_SHORT_HEX = 4
_CHANNELS = 3


class _Dress:
    """One style class's terminal-visible claims.

    Bold and italic are tri-state: None inherits, and an explicit
    font-style of normal turns italics off -- Miss Gosling's own
    sheets say normal!important inside italic quotations.
    """

    def __init__(self, pairs: dict[str, str]) -> None:
        self.bold: bool | None = None
        self.italic: bool | None = None
        self.ink = _tinted(pairs.get("color", ""))
        self.paper = _tinted(pairs.get("background-color", ""))

        weight = _plained(pairs.get("font-weight", ""))

        if weight.startswith("bold"):
            self.bold = True
        elif weight == "normal":
            self.bold = False

        style = _plained(pairs.get("font-style", ""))

        if style in ("italic", "oblique"):
            self.italic = True
        elif style == "normal":
            self.italic = False


def _plained(value: str) -> str:
    """A CSS value with its !important insistence stripped."""

    return value.replace("!important", "").strip().lower()


def _tinted(value: str) -> "tuple[int, int, int] | None":
    """A CSS color as RGB: names, #hex, and rgb() all mix."""

    told = _plained(value)

    if told in _NAMED_COLORS:
        return _NAMED_COLORS[told]

    if told.startswith("#") and len(told) == _LONG_HEX:
        return (int(told[1:3], 16), int(told[3:5], 16), int(told[5:7], 16))

    if told.startswith("#") and len(told) == _SHORT_HEX:
        return (
            int(told[1] * 2, 16),
            int(told[2] * 2, 16),
            int(told[3] * 2, 16),
        )

    if told.startswith("rgb(") and told.endswith(")"):
        pieces = told[4:-1].split(",")

        if len(pieces) == _CHANNELS:
            try:
                return (
                    int(pieces[0].strip()),
                    int(pieces[1].strip()),
                    int(pieces[2].strip()),
                )
            except ValueError:
                return None

    return None


class TerminalVoice(PlainVoice):
    """The plain voice with a terminal's file-keeping manners.

    Dressed, it also wears the LOOK chunk's styles as terminal
    attributes and answers VM_INFO's styling and color questions
    with yes -- the honesty gate being that only a real terminal
    is ever dressed.
    """

    has_saves = True

    def __init__(
        self,
        story: Story,
        width: int,
        writer: TextIO,
        asked: Callable[[str], str],
        *,
        dressed: bool = False,
    ) -> None:
        """Speak at a width, through a writer, asking by a prompt."""

        super().__init__(story, width=width)

        self._writer = writer
        self._asked = asked
        self._mark = 0
        self._dressed = dressed
        self._wardrobe = [_Dress(pairs) for pairs in self._styles]
        self._body: _Dress | None = None
        self._worn: list[_Dress] = []
        self._bits = 0
        self.has_styles = dressed
        self.has_color = dressed

    def enter_span(self, style: int) -> None:
        """Open a span, wearing its class's dress."""

        self._worn.append(self._classed(style))
        self._fitted()

    def leave_span(self) -> None:
        """Close the span, the dress beneath restored."""

        if self._worn:
            self._worn.pop()

        self._fitted()

    def enter_div(self, style: int) -> None:
        """Open a div: the break as ever, then its class's dress."""

        super().enter_div(style)
        self._worn.append(self._classed(style))
        self._fitted()

    def leave_div(self, style: int) -> None:
        """Close a div: the dress beneath first, then the break."""

        if self._worn:
            self._worn.pop()

        self._fitted()
        super().leave_div(style)

    def set_body(self, style: int) -> None:
        """Dress the document body; every later dress layers on it."""

        self._body = self._classed(style)
        self._fitted()

    def set_style(self, bits: int) -> None:
        """Turn on the deprecated style bits (Aa-machine: SET_STYLE)."""

        self._bits |= bits
        self._fitted()

    def reset_style(self, bits: int) -> None:
        """Turn off the deprecated style bits."""

        self._bits &= ~bits
        self._fitted()

    def unstyle(self) -> None:
        """Return to the default text style."""

        self._bits = 0
        self._fitted()

    def leave_all(self) -> None:
        """Return to the initial state, the spans' dresses dropped.

        The machine clears its div ledger without a leave call per
        div, so the whole stack drops here with it; the body dress
        stays, being the document's rather than any division's.
        """

        super().leave_all()

        self._worn = []
        self._bits = 0
        self._fitted()

    def undressed(self) -> None:
        """Take every attribute off, leaving the terminal clean."""

        if self._dressed:
            self._flush()
            self._told.append("\x1b[0m")

    def _classed(self, style: int) -> _Dress:
        """One class's dress, a bare one for a class LOOK never named."""

        if 0 <= style < len(self._wardrobe):
            return self._wardrobe[style]

        return _Dress({})

    def _fitted(self) -> None:
        """Land the current dress on the terminal, if one may land.

        The escape is injected past the word-wrapper the way an
        echo is: the wrapper counts columns, and a dress is
        zero-width.
        """

        if not self._dressed or self._hidden:
            return

        bold = bool(self._bits & _BIT_BOLD)
        italic = bool(self._bits & _BIT_ITALIC)
        ink = paper = None

        for dress in (self._body, *self._worn):
            if dress is None:
                continue

            bold = dress.bold if dress.bold is not None else bold
            italic = dress.italic if dress.italic is not None else italic
            ink = dress.ink if dress.ink is not None else ink
            paper = dress.paper if dress.paper is not None else paper

        pieces = ["0"]

        if bold:
            pieces.append("1")

        # Italics wear underlines, the Dialog debugger's own
        # rendering -- every terminal draws an underline, which is
        # what keeps the spec's distinguishability bar cleared
        # everywhere (Aa-machine: VM_INFO).
        if italic:
            pieces.append("4")

        if self._bits & _BIT_REVERSE:
            pieces.append("7")

        if ink is not None:
            pieces.append(f"38;2;{ink[0]};{ink[1]};{ink[2]}")

        if paper is not None:
            pieces.append(f"48;2;{paper[0]};{paper[1]};{paper[2]}")

        self._flush()
        self._told.append("\x1b[" + ";".join(pieces) + "m")

    def poured(self) -> None:
        """Write everything told since the last pour."""

        told = self.told()
        self._writer.write(told[self._mark :])
        self._writer.flush()
        self._mark = len(told)

    def save(self, data: bytes) -> bool:
        """Ask where to keep the savefile; an empty answer cancels."""

        name = self._named("Save the story as: ")

        if not name:
            return False

        try:
            with open(name, "wb") as handle:  # noqa: PTH123 -- one write, the player's own path
                handle.write(data)
        except OSError:
            return False

        return True

    def restore(self) -> bytes | None:
        """Ask which savefile to revive; an empty answer cancels."""

        name = self._named("Restore the story from: ")

        if not name:
            return None

        try:
            with open(name, "rb") as handle:  # noqa: PTH123 -- one read, the player's own path
                return handle.read()
        except OSError:
            return None

    def _named(self, prompt: str) -> str:
        """One filename from the player, the pending story poured first.

        A bare name gains the .aasave suffix; the player's own
        dotted path is honored whole.
        """

        self.line()
        self.poured()

        name = self._asked(prompt).strip()
        self.prompted()

        if name and "." not in name:
            name += SUFFIX

        return name


def played(  # noqa: PLR0913 -- one seam per replaceable stream
    story: Story,
    *,
    seed: int | None = None,
    reader: TextIO | None = None,
    writer: TextIO | None = None,
    asked: Callable[[str], str] | None = None,
    width: int | None = None,
    dressed: bool | None = None,
) -> None:
    """Play one story at the terminal, opening to quit.

    The seams exist for the tests: a reader replaces stdin, a
    writer stdout, and asked the filename prompt; live play needs
    none of them. Dressed is the honesty gate for the LOOK
    styles: left to itself it asks the writer whether it is a
    real terminal, and a pipe stays plain.
    """

    reader = sys.stdin if reader is None else reader
    writer = sys.stdout if writer is None else writer

    if asked is None:

        def asked(prompt: str) -> str:
            writer.write(prompt)
            writer.flush()

            return reader.readline().rstrip("\r\n")

    if width is None:
        width = shutil.get_terminal_size().columns

    if dressed is None:
        dressed = writer.isatty()

    voice = TerminalVoice(story, width, writer, asked, dressed=dressed)
    machine = Machine(story, voice, seed=seed)
    waiting = machine.run()

    while waiting != "quit":
        voice.poured()
        line = reader.readline()

        if not line:
            voice.line()

            break

        line = line.rstrip("\r\n")

        if waiting == "line":
            voice.prompted()
            waiting = machine.deliver_line(line)
        else:
            at = 0

            while waiting == "key" and at < len(line):
                waiting = machine.deliver_key(ord(line[at]))
                at += 1

            if waiting == "key":
                waiting = machine.deliver_key(0x0D)

    voice.line()
    voice.undressed()
    voice.poured()
