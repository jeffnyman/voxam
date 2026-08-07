"""Typed access to the fields of the Z-Machine header (§11.1)."""

from dataclasses import dataclass

from voxam.errors import ZMachineHeaderError

# Dynamic memory must contain at least 64 bytes (§1.1.1), and the first 64
# bytes are the header (§1.1.1.1), so no story file can be shorter.
HEADER_SIZE = 64

# Field locations from the table in §11.1.
RELEASE = 0x02
HIGH_MEMORY_BASE = 0x04
INITIAL_PC = 0x06
DICTIONARY = 0x08
OBJECT_TABLE = 0x0A
GLOBAL_VARIABLES = 0x0C
STATIC_MEMORY_BASE = 0x0E
SERIAL_START = 0x12
SERIAL_END = 0x18
ABBREVIATIONS_TABLE = 0x18
FILE_LENGTH = 0x1A
CHECKSUM = 0x1C

# The file length is stored divided by a version-dependent constant
# (§11.1.6).
FILE_LENGTH_SCALE = {1: 2, 2: 2, 3: 2, 4: 4, 5: 4, 6: 8, 7: 8, 8: 8}

# Verification sums the bytes from $0040 up to the stored file length,
# modulo $10000; padding beyond that length must be excluded (§15, verify).
CHECKSUM_START = 0x40
CHECKSUM_MODULO = 0x10000

# In Version 6 the word at $06 is the packed address of a "main" routine
# rather than the byte address of a first instruction (§11.1).
PACKED_PC_VERSION = 6


@dataclass(frozen=True)
class Header:
    """A typed view of the header fields within story file memory.

    Over a Story's bytes this is a fixed view of the pristine file; over
    a Memory's bytearray it is a live view of the working image, since
    a running game may legally alter parts of the header (§11.1.2.1).

    Attributes:
        data: The full story file or memory image, of which the first
            64 bytes form the header (§1.1.1.1).
    """

    data: bytes | bytearray

    def __post_init__(self) -> None:
        """Reject byte content too short to contain a header.

        Raises:
            ZMachineHeaderError: If fewer than 64 bytes are present.
        """

        if len(self.data) < HEADER_SIZE:
            msg = (
                f"a header requires {HEADER_SIZE} bytes, but only "
                f"{len(self.data)} are present (§1.1.1.1)"
            )

            raise ZMachineHeaderError(msg)

    def _word(self, offset: int) -> int:
        """Read the big-endian word at a byte offset (§2.1)."""

        return int.from_bytes(self.data[offset : offset + 2], "big")

    @property
    def version(self) -> int:
        """The Z-Machine version this story targets (§11.1)."""

        return self.data[0]

    @property
    def release(self) -> int:
        """The release number of this story (§11.1)."""

        return self._word(RELEASE)

    @property
    def serial_number(self) -> str:
        """Six ASCII characters, conventionally the compile date (§11.1)."""

        return self.data[SERIAL_START:SERIAL_END].decode("ascii")

    @property
    def declared_file_length(self) -> int:
        """The story length in bytes, unscaled from the header word (§11.1.6).

        The file on disk may be longer than this: interpreters must allow
        for padding beyond the declared length (§15, verify remarks).
        """

        return self._word(FILE_LENGTH) * FILE_LENGTH_SCALE[self.version]

    @property
    def stored_checksum(self) -> int:
        """The checksum the compiler recorded at $1c (§11.1)."""

        return self._word(CHECKSUM)

    @property
    def computed_checksum(self) -> int:
        """The checksum of the story bytes actually present (§15, verify)."""

        story = self.data[CHECKSUM_START : self.declared_file_length]

        return sum(story) % CHECKSUM_MODULO

    @property
    def high_memory_base(self) -> int:
        """The byte address at which high memory begins (§11.1)."""

        return self._word(HIGH_MEMORY_BASE)

    @property
    def dictionary_address(self) -> int:
        """The byte address of the dictionary (§11.1)."""

        return self._word(DICTIONARY)

    @property
    def object_table_address(self) -> int:
        """The byte address of the object table (§11.1)."""

        return self._word(OBJECT_TABLE)

    @property
    def global_variables_address(self) -> int:
        """The byte address of the global variables table (§11.1)."""

        return self._word(GLOBAL_VARIABLES)

    @property
    def static_memory_base(self) -> int:
        """The byte address at which static memory begins (§11.1)."""

        return self._word(STATIC_MEMORY_BASE)

    @property
    def abbreviations_table_address(self) -> int:
        """The byte address of the abbreviations table (§11.1)."""

        return self._word(ABBREVIATIONS_TABLE)

    @property
    def initial_program_counter(self) -> int:
        """The byte address of the first instruction to execute (§11.1).

        Raises:
            ZMachineHeaderError: In Version 6, where the word at $06 is a
                packed routine address instead.
        """

        if self.version == PACKED_PC_VERSION:
            msg = (
                "version 6 stores a packed routine address at $06, not an "
                "initial program counter; use main_routine_packed_address "
                "(§11.1)"
            )

            raise ZMachineHeaderError(msg)

        return self._word(INITIAL_PC)

    @property
    def main_routine_packed_address(self) -> int:
        """The packed address of the initial routine in Version 6 (§11.1).

        Unpacking this address requires the rules of §1.2.3, which will
        arrive alongside routine calls.

        Raises:
            ZMachineHeaderError: In any version other than 6, where the
                word at $06 is a byte address instead.
        """

        if self.version != PACKED_PC_VERSION:
            msg = (
                f"version {self.version} stores an initial program counter "
                f"at $06, not a packed routine address; use "
                f"initial_program_counter (§11.1)"
            )

            raise ZMachineHeaderError(msg)

        return self._word(INITIAL_PC)

    def verify(self) -> bool:
        """Report whether the computed and stored checksums agree (§15).

        Some early Version 3 files store no length or checksum at all
        (§11.1), so a mismatch against a stored zero may mean "absent"
        rather than "corrupt".
        """

        return self.computed_checksum == self.stored_checksum
