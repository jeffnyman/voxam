"""Where saved games live (§6.1.1.1).

The Standard leaves the format of a saved game to the interpreter
(§6.1.1.1) -- Voxam writes Quetzal -- and says nothing at all about
where the bytes go. A SaveSlot is that decision, kept apart from the
machine: the machine asks the slot to keep or produce bytes, and
failure is an answer, not an accident, because save and restore
report failure to the story as an ordinary result (§15).
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class SaveSlot(Protocol):
    """A home for one saved game's bytes."""

    def write(self, data: bytes) -> bool:
        """Keep a saved game, reporting whether it was kept."""
        ...

    def read(self) -> bytes | None:
        """Produce the saved game last kept, or None without one."""
        ...


@dataclass(frozen=True)
class FileSaveSlot:
    """A save slot bound to one file path.

    Attributes:
        path: Where the saved game lives on disk.
    """

    path: Path

    def write(self, data: bytes) -> bool:
        """Write the saved game to the path (§15 save).

        A refused disk is a failed save, not a crash.
        """

        try:
            self.path.write_bytes(data)
        except OSError:
            return False

        return True

    def read(self) -> bytes | None:
        """Read the saved game back (§15 restore).

        None means the path has no saved game to give.
        """

        try:
            return self.path.read_bytes()
        except OSError:
            return None
