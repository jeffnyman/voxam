"""The Å-machine at the terminal: the plain voice, spoken live.

The drill is the reference Node frontend's own, certified against
its transcripts: a line wait takes the typed line whole, a key
wait takes it a keypress at a time with a return to finish, and
the terminal's own echo stands in for the readline echo the
transcripts carry. The voice here keeps files too: a save or
restore asks for its filename on the spot, the blocking face's
privilege (Aa-machine: Savefile).
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


class TerminalVoice(PlainVoice):
    """The plain voice with a terminal's file-keeping manners."""

    has_saves = True

    def __init__(
        self,
        story: Story,
        width: int,
        writer: TextIO,
        asked: Callable[[str], str],
    ) -> None:
        """Speak at a width, through a writer, asking by a prompt."""

        super().__init__(story, width=width)

        self._writer = writer
        self._asked = asked
        self._mark = 0

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
) -> None:
    """Play one story at the terminal, opening to quit.

    The seams exist for the tests: a reader replaces stdin, a
    writer stdout, and asked the filename prompt; live play needs
    none of them.
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

    voice = TerminalVoice(story, width, writer, asked)
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
    voice.poured()
