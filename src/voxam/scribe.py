"""Session files: the transcript and the command script (§7, §10).

Output stream 2 is the game transcript and output stream 4 the
script of the player's commands (§7.1.1, §7.1.2.3); input stream 1
reads commands back from a file in the same format stream 4 writes
(§10.2.1). The Scribe is the seam a machine speaks these through:
sessions with somewhere to put the files -- the command line, which
names them by convention beside the story, zork1.z3 keeping its
transcript in zork1.scr and its commands in zork1.cmd -- hand the
machine a FileScribe; headless sessions hand nothing, and the
machine reports the streams as a frontier exactly as § 7's features
deserve. §7.1.1.2's courtesy -- decide where the transcript goes
once per session, not at every reselection -- is met by having no
question to ask at all: the convention decides, the file opens
lazily on first use, and reselection appends to the same open file.
"""

from pathlib import Path
from typing import IO, Protocol

from voxam.errors import VoxamError


class Scribe(Protocol):
    """The session-file seam a machine writes and reads through."""

    def transcript(self, text: str) -> None:
        """Append text to the game transcript (§7.1.1)."""

    def command(self, line: str) -> None:
        """Append one finished command to the script (§7.1.2.3)."""

    def playback(self) -> str | None:
        """The next command from the file; None ends stream 1 (§10.2)."""


class FileScribe:
    """Session files on disk, lazily opened, one file per session.

    Nothing is created until the game first asks: a session that
    never touches the streams leaves no files behind. The commands
    file doubles as input stream 1's source, which is §10.2.1's own
    rule -- the format read must be the format stream 4 writes.
    """

    def __init__(self, transcript_path: Path, commands_path: Path) -> None:
        """Name the files; neither is opened until first use.

        Args:
            transcript_path: Where output stream 2 writes.
            commands_path: Where output stream 4 writes and input
                stream 1 reads.
        """

        self._transcript_path = transcript_path
        self._commands_path = commands_path
        self._transcript_file: IO[str] | None = None
        self._commands_file: IO[str] | None = None
        self._playback_file: IO[str] | None = None
        self._playback_done = False

    def transcript(self, text: str) -> None:
        """Append text to the transcript file, opened on first use.

        Raises:
            VoxamError: If the file cannot be opened or written.
        """

        if self._transcript_file is None:
            self._transcript_file = self._opened(self._transcript_path)

        self._written(self._transcript_file, text, self._transcript_path)

    def command(self, line: str) -> None:
        """Append one command line to the script file (§7.1.2.3).

        Raises:
            VoxamError: If the file cannot be opened or written.
        """

        if self._commands_file is None:
            self._commands_file = self._opened(self._commands_path)

        self._written(self._commands_file, f"{line}\n", self._commands_path)

    def playback(self) -> str | None:
        """One command off the file; None for a missing or spent one.

        An absent file is not an error: §10.2.3 leaves the choice
        of file entirely to the interpreter, and a session with no
        commands file simply has nothing to play, so stream 1 ends
        before it begins.
        """

        if self._playback_done:
            return None

        if self._playback_file is None:
            try:
                self._playback_file = self._commands_path.open("r", encoding="utf-8")
            except OSError:
                self._playback_done = True

                return None

        line = self._playback_file.readline()

        if not line:
            self._playback_done = True

            return None

        return line.rstrip("\n")

    def close(self) -> None:
        """Close whichever files the session actually opened."""

        for handle in (
            self._transcript_file,
            self._commands_file,
            self._playback_file,
        ):
            if handle is not None:
                handle.close()

    def _opened(self, path: Path) -> IO[str]:
        """Open one session file for writing, loudly on failure.

        Raises:
            VoxamError: If the file cannot be opened.
        """

        try:
            return path.open("w", encoding="utf-8", newline="\n")
        except OSError as error:
            msg = f"the session file {path} cannot be opened: {error}"

            raise VoxamError(msg) from error

    def _written(self, handle: IO[str], text: str, path: Path) -> None:
        """Write to an open session file, loudly on failure.

        Raises:
            VoxamError: If the write fails -- a full disk mid-game
                is worth hearing about, not losing a transcript to.
        """

        try:
            handle.write(text)
        except OSError as error:
            msg = f"the session file {path} cannot be written: {error}"

            raise VoxamError(msg) from error
