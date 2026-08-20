"""Loading and validation of Glulx story files (Glulx: The Header).

The header is the first 36 bytes: nine big-endian 32-bit words,
opening with the magic 'Glul'. It lives in ROM, so everything here
is fixed for the story's whole life -- which is why loading is the
right moment to hold the file to all of the header's promises: the
version window, the 256-byte alignment of every memory boundary,
and the checksum over the entire initial image.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Self

from voxam.errors import GlulxStoryError

# The magic number: ASCII 'Glul' (Glulx: The Header).
MAGIC = b"Glul"

# Nine 32-bit words (Glulx: The Header).
HEADER_SIZE = 36
VERSION_AT = 4
RAMSTART_AT = 8
EXTSTART_AT = 12
ENDMEM_AT = 16
STACK_SIZE_AT = 20
START_FUNCTION_AT = 24
DECODING_TABLE_AT = 28
CHECKSUM_AT = 32

# An interpreter written to specification 3.1.3 accepts game files
# from 2.0.0 through 3.1.*: minor versions are backwards compatible,
# subminor versions do not matter, and 2.0 differs from 3.0 only in
# lacking Unicode (Glulx: The Header).
VERSION_FLOOR = 0x00020000
VERSION_CEILING = 0x000301FF

# The version word packs major.minor.subminor as 16, 8, and 8 bits
# (Glulx: The Header).
MAJOR_SHIFT = 16
MINOR_SHIFT = 8
BYTE_MASK = 0xFF

# RAMSTART, EXTSTART, and ENDMEM must sit on 256-byte boundaries,
# and ROM must be at least 256 bytes so the header fits in it; the
# stack size is a multiple of 256 as well (Glulx: The Header,
# Glulx: The Stack).
BOUNDARY = 256

WORD_SIZE = 4
WORD_RANGE = 1 << 32


@dataclass(frozen=True)
class Story:
    """A Glulx story file held in memory, its header promises kept.

    Attributes:
        data: The raw bytes of the game file -- the initial memory
            image from 0 to EXTSTART (Glulx: The Header).
    """

    data: bytes

    def __post_init__(self) -> None:
        """Hold the file to every promise its header makes.

        Raises:
            GlulxStoryError: For a file too short for a header, the
                wrong magic, a version outside the accepted window,
                a misaligned memory boundary, boundaries out of
                order, or a file whose length is not the EXTSTART
                it declares.
        """

        if len(self.data) < HEADER_SIZE:
            msg = (
                f"a Glulx story opens with a {HEADER_SIZE}-byte header, "
                f"but only {len(self.data)} bytes are present "
                f"(Glulx: The Header)"
            )

            raise GlulxStoryError(msg)

        if self.data[: len(MAGIC)] != MAGIC:
            msg = (
                "the file does not open with the magic number 'Glul' "
                "(Glulx: The Header)"
            )

            raise GlulxStoryError(msg)

        self._require_version()
        self._require_map()

    def _require_version(self) -> None:
        """Hold the version to the 2.0.0 through 3.1.* window.

        Raises:
            GlulxStoryError: For a version outside the window an
                interpreter written to 3.1.3 accepts.
        """

        version = self._word(VERSION_AT)

        if not VERSION_FLOOR <= version <= VERSION_CEILING:
            msg = (
                f"the story declares Glulx version {_dotted(version)}, "
                f"but an interpreter written to 3.1.3 accepts 2.0.0 "
                f"through 3.1.* (Glulx: The Header)"
            )

            raise GlulxStoryError(msg)

    def _require_map(self) -> None:
        """Hold the memory boundaries to their alignment and order.

        Raises:
            GlulxStoryError: For a boundary off its 256-byte seat,
                boundaries out of order, or a file whose length is
                not the EXTSTART it declares.
        """

        for name, value in (
            ("RAMSTART", self.ramstart),
            ("EXTSTART", self.extstart),
            ("ENDMEM", self.endmem),
            ("the stack size", self.stack_size),
        ):
            if value % BOUNDARY:
                msg = (
                    f"{name} is {value}, which is not a multiple of "
                    f"{BOUNDARY} (Glulx: The Header)"
                )

                raise GlulxStoryError(msg)

        if not BOUNDARY <= self.ramstart <= self.extstart <= self.endmem:
            msg = (
                f"the memory map is out of order: ROM holds the header so "
                f"RAMSTART is at least {BOUNDARY}, and RAMSTART "
                f"({self.ramstart}) precedes EXTSTART ({self.extstart}) "
                f"precedes ENDMEM ({self.endmem}) (Glulx: The Header)"
            )

            raise GlulxStoryError(msg)

        if len(self.data) != self.extstart:
            msg = (
                f"the file is {len(self.data)} bytes, but its header "
                f"declares EXTSTART {self.extstart} -- the length of the "
                f"stored initial memory (Glulx: The Header)"
            )

            raise GlulxStoryError(msg)

    @classmethod
    def load(cls, path: Path) -> Self:
        """Read and validate a Glulx story file from disk.

        Args:
            path: Location of the story file.

        Returns:
            The loaded story.

        Raises:
            GlulxStoryError: If the file cannot be a Glulx story.
        """

        return cls(path.read_bytes())

    @property
    def version(self) -> str:
        """The declared Glulx version, dotted: 3.1.2 and kin."""

        return _dotted(self._word(VERSION_AT))

    @property
    def ramstart(self) -> int:
        """The first address the program can write to."""

        return self._word(RAMSTART_AT)

    @property
    def extstart(self) -> int:
        """The end of stored initial memory: the game file's length."""

        return self._word(EXTSTART_AT)

    @property
    def endmem(self) -> int:
        """The end of the memory map; above EXTSTART starts zeroed."""

        return self._word(ENDMEM_AT)

    @property
    def stack_size(self) -> int:
        """The stack the program needs, in bytes."""

        return self._word(STACK_SIZE_AT)

    @property
    def start_function(self) -> int:
        """The function execution will commence by calling."""

        return self._word(START_FUNCTION_AT)

    @property
    def decoding_table(self) -> int:
        """The string-decoding table's address; 0 means none."""

        return self._word(DECODING_TABLE_AT)

    @property
    def stored_checksum(self) -> int:
        """The checksum word the compiler stored."""

        return self._word(CHECKSUM_AT)

    @property
    def computed_checksum(self) -> int:
        """The checksum as an interpreter computes it.

        A simple sum of the entire initial contents of memory as
        big-endian 32-bit words, with the checksum field itself
        counted as zero (Glulx: The Header).
        """

        total = 0

        for at in range(0, len(self.data), WORD_SIZE):
            if at != CHECKSUM_AT:
                total += self._word(at)

        return total % WORD_RANGE

    def verify(self) -> bool:
        """Whether the stored and computed checksums agree."""

        return self.stored_checksum == self.computed_checksum

    def _word(self, at: int) -> int:
        """The big-endian 32-bit word at a byte address."""

        return int.from_bytes(self.data[at : at + WORD_SIZE], "big")


def _dotted(version: int) -> str:
    """A packed version word as its major.minor.subminor reading."""

    return (
        f"{version >> MAJOR_SHIFT}."
        f"{(version >> MINOR_SHIFT) & BYTE_MASK}."
        f"{version & BYTE_MASK}"
    )
