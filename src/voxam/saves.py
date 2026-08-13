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
    """A home for one saved game's bytes, and its auxiliary files."""

    def write(self, data: bytes) -> bool:
        """Keep a saved game, reporting whether it was kept."""
        ...

    def read(self) -> bytes | None:
        """Produce the saved game last kept, or None without one."""
        ...

    def write_aux(self, name: str, data: bytes) -> bool:
        """Keep a named auxiliary file (§7.6), reporting success."""
        ...

    def read_aux(self, name: str) -> bytes | None:
        """Produce a named auxiliary file, or None without one."""
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

    def write_aux(self, name: str, data: bytes) -> bool:
        """Write a named auxiliary file beside the save (§7.6)."""

        try:
            self._aux_path(name).write_bytes(data)
        except OSError:
            return False

        return True

    def read_aux(self, name: str) -> bytes | None:
        """Read a named auxiliary file back, or None without one."""

        try:
            return self._aux_path(name).read_bytes()
        except OSError:
            return None

    def _aux_path(self, name: str) -> Path:
        """A safe sibling path for a game-supplied name (§7.6).

        The name came from story memory, so anything path-like is
        stripped: only letters, digits, dashes, and underscores
        survive, and the .aux extension §7.6.1.1 suggests is added.
        """

        stem = "".join(c for c in name if c.isalnum() or c in "-_") or "aux"

        return self.path.with_name(f"{stem}.aux")
