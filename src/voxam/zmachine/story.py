"""Loading and validation of Z-Machine story files."""

from dataclasses import dataclass
from pathlib import Path
from typing import Self

from voxam.errors import ZMachineStoryError
from voxam.zmachine.header import HEADER_SIZE, Header

# The byte at address 0 holds the version number, 1 to 8 (§11.1).
VERSION_RANGE = range(1, 9)


@dataclass(frozen=True)
class Story:
    """A story file held in memory, validated enough to identify it.

    Attributes:
        data: The raw bytes of the story file.
    """

    data: bytes

    def __post_init__(self) -> None:
        """Reject byte content that cannot be a story file.

        Raises:
            StoryError: If the content is too short to hold a header or
                its version byte is out of range.
        """

        if len(self.data) < HEADER_SIZE:
            msg = (
                f"story file is {len(self.data)} bytes, but the header "
                f"alone requires {HEADER_SIZE} (§1.1.1.1)"
            )

            raise ZMachineStoryError(msg)

        if self.data[0] not in VERSION_RANGE:
            msg = (
                f"story file declares version {self.data[0]}, but only "
                f"versions 1 to 8 exist (§11.1)"
            )

            raise ZMachineStoryError(msg)

    @classmethod
    def load(cls, path: Path) -> Self:
        """Read and validate a story file from disk.

        Args:
            path: Location of the story file.

        Returns:
            The loaded story.

        Raises:
            StoryError: If the file cannot be a story file.
        """

        return cls(path.read_bytes())

    @property
    def header(self) -> Header:
        """Typed access to this story's header fields (§11.1)."""

        return Header(self.data)

    @property
    def version(self) -> int:
        """The Z-Machine version this story targets (§11.1)."""

        return self.header.version
