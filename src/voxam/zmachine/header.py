"""Typed access to the fields of the Z-Machine header (§11.1)."""

from dataclasses import dataclass

from voxam.errors import ZMachineHeaderError

# Dynamic memory must contain at least 64 bytes (§1.1.1), and the first 64
# bytes are the header (§1.1.1.1), so no story file can be shorter.
HEADER_SIZE = 64

# Flags 1 lives at $01. A Version 3 game sets bit 1 to ask for an
# hours:minutes status line instead of score/turns (§8.2.3.2); the
# interpreter answers with bit 4, set when it has no status line to
# offer, and bit 5, set when it can split the screen (§11.1). Only
# Version 3's Flags 1 defines these bits.
FLAGS_1 = 0x01
TIME_STATUS_BIT = 0x02
NO_STATUS_LINE_BIT = 0x10
SCREEN_SPLIT_BIT = 0x20
STATUS_FLAGS_VERSION = 3

# From Version 4, Flags 1 changes meaning entirely: now it carries
# the typography and timing the interpreter can offer -- boldface
# (bit 2), italic (bit 3), fixed-space style (bit 4), and timed
# keyboard input (bit 7) (§11.1).
BOLD_BIT = 0x04
ITALIC_BIT = 0x08
FIXED_PITCH_BIT = 0x10
TIMED_INPUT_BIT = 0x80

# From Version 4 the interpreter also introduces itself: a platform
# number at $1e with a revision letter at $1f (§11.1.3), and the
# screen size in lines at $20 and characters at $21, where 255
# lines means "infinite" -- the right claim for an unpaged stream
# (§8.4, §11.1). Games consult these before drawing: Trinity quits
# outright on a zero-width screen.
INTERPRETER_NUMBER = 0x1E
INTERPRETER_VERSION = 0x1F
SCREEN_LINES = 0x20
SCREEN_COLUMNS = 0x21
SCREEN_FIELDS_VERSION = 4
INFINITE_LINES = 255

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

# Versions 6 and 7 locate routines and static strings via offsets,
# stored divided by 8, in the words at $28 and $2a (§1.2.3, §11.1).
ROUTINES_OFFSET = 0x28
STATIC_STRINGS_OFFSET = 0x2A
OFFSET_VERSIONS = (6, 7)

# From Version 5, the word at $34 may name a custom alphabet table;
# zero means the standard alphabets (§3.5.5, §11.1).
ALPHABET_TABLE = 0x34

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
    def alphabet_table_address(self) -> int:
        """The custom alphabet table's byte address, or 0 (§3.5.5).

        Zero means the standard alphabets. The field exists from
        Version 5; earlier versions leave the word zero anyway.
        """

        return self._word(ALPHABET_TABLE)

    @property
    def routines_offset(self) -> int:
        """The routines offset, as stored: divided by 8 (§1.2.3, §11.1).

        Raises:
            ZMachineHeaderError: Outside Versions 6 and 7, which are the
                only versions with offset-based packed addresses.
        """

        if self.version not in OFFSET_VERSIONS:
            msg = (
                f"version {self.version} has no routines offset; only "
                f"versions 6 and 7 unpack addresses with one (§1.2.3)"
            )

            raise ZMachineHeaderError(msg)

        return self._word(ROUTINES_OFFSET)

    @property
    def static_strings_offset(self) -> int:
        """The static strings offset, as stored: divided by 8 (§1.2.3, §11.1).

        Raises:
            ZMachineHeaderError: Outside Versions 6 and 7, which are the
                only versions with offset-based packed addresses.
        """

        if self.version not in OFFSET_VERSIONS:
            msg = (
                f"version {self.version} has no static strings offset; only "
                f"versions 6 and 7 unpack addresses with one (§1.2.3)"
            )

            raise ZMachineHeaderError(msg)

        return self._word(STATIC_STRINGS_OFFSET)

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

    @property
    def time_game(self) -> bool:
        """Whether the status line shows the time of day (§8.2.3.2).

        A Version 3 game claims a clock with bit 1 of Flags 1;
        Versions 1 and 2 predate the bit and always show score and
        turns.

        Raises:
            ZMachineHeaderError: From Version 4, where no status line
                exists for the bit to describe (§8.2).
        """

        if self.version > STATUS_FLAGS_VERSION:
            msg = (
                f"version {self.version} has no status line for a type "
                f"bit to describe (§8.2)"
            )

            raise ZMachineHeaderError(msg)

        if self.version < STATUS_FLAGS_VERSION:
            return False

        return bool(self.data[FLAGS_1] & TIME_STATUS_BIT)

    def declare_status_line(self, *, available: bool) -> None:
        """Record whether the interpreter offers a status line (§11.1).

        The header speaks in absences here: bit 4 of Flags 1 is set
        when no status line is available.

        Raises:
            ZMachineHeaderError: Outside Version 3, the only version
                whose Flags 1 defines the bit; or over the pristine
                story bytes, which never change.
        """

        self._require_version_3()
        self._set_flag(NO_STATUS_LINE_BIT, on=not available)

    def declare_screen_splitting(self, *, available: bool) -> None:
        """Record whether the interpreter can split the screen (§11.1).

        Raises:
            ZMachineHeaderError: Outside Version 3, the only version
                whose Flags 1 defines the bit; or over the pristine
                story bytes, which never change.
        """

        self._require_version_3()
        self._set_flag(SCREEN_SPLIT_BIT, on=available)

    def _require_version_3(self) -> None:
        """Refuse the Version 3 capability bits elsewhere (§11.1)."""

        if self.version != STATUS_FLAGS_VERSION:
            msg = (
                f"version {self.version} does not define this Flags 1 "
                f"capability bit; only version 3 does (§11.1)"
            )

            raise ZMachineHeaderError(msg)

    def introduce_interpreter(self, number: int, revision: int) -> None:
        """Record which interpreter is running the story (§11.1.3).

        Args:
            number: The platform number the interpreter claims.
            revision: The ASCII code of its revision letter.

        Raises:
            ZMachineHeaderError: Before Version 4, where the fields
                do not exist; or over the pristine story bytes.
        """

        self._require_screen_fields()

        live = self._live()
        live[INTERPRETER_NUMBER] = number
        live[INTERPRETER_VERSION] = revision

    def declare_screen_size(self, *, lines: int, columns: int) -> None:
        """Record the screen size in lines and characters (§8.4).

        255 lines means "infinite": the claim of a stream that never
        pages.

        Raises:
            ZMachineHeaderError: Before Version 4, where the fields
                do not exist; or over the pristine story bytes.
        """

        self._require_screen_fields()

        live = self._live()
        live[SCREEN_LINES] = lines
        live[SCREEN_COLUMNS] = columns

    def declare_presentation(
        self, *, bold: bool, italic: bool, fixed_pitch: bool, timed_input: bool
    ) -> None:
        """Record the typography and timing on offer (§11.1).

        From Version 4 the Flags 1 capability bits mean boldface,
        italic, fixed-space style, and timed keyboard input.

        Raises:
            ZMachineHeaderError: Before Version 4, whose Flags 1
                means other things; or over the pristine story bytes.
        """

        self._require_screen_fields()

        self._set_flag(BOLD_BIT, on=bold)
        self._set_flag(ITALIC_BIT, on=italic)
        self._set_flag(FIXED_PITCH_BIT, on=fixed_pitch)
        self._set_flag(TIMED_INPUT_BIT, on=timed_input)

    def _require_screen_fields(self) -> None:
        """Refuse the interpreter fields before Version 4 (§11.1)."""

        if self.version < SCREEN_FIELDS_VERSION:
            msg = (
                f"version {self.version} has no interpreter fields to "
                f"fill; they begin at version 4 (§11.1)"
            )

            raise ZMachineHeaderError(msg)

    def _set_flag(self, bit: int, *, on: bool) -> None:
        """Write one interpreter capability bit into Flags 1 (§11.1)."""

        live = self._live()

        if on:
            live[FLAGS_1] |= bit
        else:
            live[FLAGS_1] &= 0xFF ^ bit

    def _live(self) -> bytearray:
        """The working image's bytes, refusing the pristine story."""

        if not isinstance(self.data, bytearray):
            msg = (
                "the pristine story never changes; declare capabilities "
                "on the working image (§11.1.2)"
            )

            raise ZMachineHeaderError(msg)

        return self.data

    def verify(self) -> bool:
        """Report whether the computed and stored checksums agree (§15).

        Some early Version 3 files store no length or checksum at all
        (§11.1), so a mismatch against a stored zero may mean "absent"
        rather than "corrupt".
        """

        return self.computed_checksum == self.stored_checksum
