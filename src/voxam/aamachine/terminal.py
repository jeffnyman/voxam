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
from voxam.aamachine.output import FiledVoice
from voxam.aamachine.story import Story


class TerminalVoice(FiledVoice):
    """The plain voice with a terminal's file-keeping manners.

    The filenames are asked for on the stream, which is all a
    filed voice needs of a face. Dressed, this one also wears the
    LOOK chunk's styles as terminal attributes and answers
    VM_INFO's styling and color questions with yes, the honesty
    gate being that only a real terminal is ever dressed.
    """

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

        super().__init__(story, width, asked)

        self._writer = writer
        self._mark = 0
        self._dressed = dressed
        self.has_styles = dressed
        self.has_color = dressed

    def undressed(self) -> None:
        """Take every attribute off, leaving the terminal clean."""

        if self._dressed:
            self._flush()
            self._told.append("\x1b[0m")

    def _fitted(self) -> None:
        """Land the current dress on the terminal, if one may land.

        The escape is injected past the word-wrapper the way an
        echo is: the wrapper counts columns, and a dress is
        zero-width.
        """

        if not self._dressed or self._hidden:
            return

        bold, italic, reverse, ink, paper = self._wardrobe.folded()
        pieces = ["0"]

        if bold:
            pieces.append("1")

        # Italics wear underlines, the Dialog debugger's own
        # rendering -- every terminal draws an underline, which is
        # what keeps the spec's distinguishability bar cleared
        # everywhere (Aa-machine: VM_INFO).
        if italic:
            pieces.append("4")

        if reverse:
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
