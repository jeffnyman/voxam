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
TANDY_BIT = 0x08
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

# Flags 2 lives in the word at $10. Its bits describe the player's
# session -- transcription on, fixed-pitch forced -- rather than the
# story's state, which is why a restore or restart writes everything
# back EXCEPT this word (§6.1.2, §6.1.3). Bit 7, in the word's low
# byte at $11, is the game asking for sound effects: Version 5
# games like Sherlock, and exactly one Version 3 -- The Lurking
# Horror, which §11.1's remarks name for this same bit. The
# interpreter's only move is to clear the request it cannot oblige.
FLAGS_2 = 0x10
FLAGS_2_LOW = 0x11
SOUND_BIT = 0x80

# Bit 3 of Flags 2 is a Version 5 game asking for the §16 character
# graphics font -- Beyond Zork draws its maps in it -- and an
# interpreter without the font must clear the request (§8.1.5.1).
# Version 6 gives the same bit to pictures instead (§11.1).
GRAPHICS_BIT = 0x08

# Two more Flags 2 requests the interpreter clears when it cannot
# oblige (§11.1.2): bit 5 is the game asking for a mouse, and bit 8
# -- bit 0 of the word's high byte at $10 -- a Version 6 game
# asking for menus.
MOUSE_BIT = 0x20
MENUS_BIT = 0x01

# The arc_image contract reads the same picture bit in Versions 5,
# 7, and 8: a band-drawing interpreter claims it there too, and a
# game that finds it clear never reaches for the draw opcode
# (arc_image: the contract, part A).
ARC_PICTURES_VERSION = 5

# Version 6 grows Flags 1 further: bit 1 declares that picture
# displaying is available and bit 5 that sound effects are -- the
# general availability of the opcodes behind them, per the §11.1.4
# remarks; §9.1.1 asks for the sound bit by name.
PICTURES_BIT = 0x02
SOUND_PRESENCE_BIT = 0x20
PICTURE_FLAGS_VERSION = 6

# From Version 5 the header carries the current font's width at $26
# and height at $27, in screen units (§8.1.1). Version 6 swaps the
# two bytes -- moot for a character terminal, whose units make every
# font 1 by 1.
FONT_WIDTH = 0x26
FONT_HEIGHT = 0x27
FONT_FIELDS_VERSION = 5

# From Version 5 the screen's width and height are also recorded in
# units, in the words at $22 and $24 (§8.4.3). A character terminal's
# unit is one character, so these mirror the byte fields at $21 and
# $20.
SCREEN_WIDTH_UNITS = 0x22
SCREEN_HEIGHT_UNITS = 0x24

# From Version 5, bit 0 of Flags 1 answers whether colours are
# available, and the interpreter's default background and foreground
# live at $2c and $2d as §8.3.1 codes (§8.3.2, §8.3.3).
COLOURS_BIT = 0x01
DEFAULT_BACKGROUND_ADDRESS = 0x2C
DEFAULT_FOREGROUND_ADDRESS = 0x2D
COLOURS_VERSION = 5

# From Version 5 the word at $2E may name a "terminating characters
# table": a zero-terminated list of input codes that end a read
# alongside new-line (§10.5.2.1, §11.1).
TERMINATING_TABLE = 0x2E

# An interpreter obeying revision n.m of the Standard writes n at
# $32 and m at $33 (§11.1.5); games check it before using late
# opcodes like print_unicode.
STANDARD_MAJOR_ADDRESS = 0x32
STANDARD_MINOR_ADDRESS = 0x33

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
# zero means the standard alphabets (§3.5.5, §11.1). The word at $36
# names the header extension table, whose third word may in turn
# name a custom Unicode translation table (§3.8.5.2, §11.1).
ALPHABET_TABLE = 0x34
HEADER_EXTENSION = 0x36
UNICODE_TABLE_WORD = 3

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
    def terminating_table_address(self) -> int:
        """The terminating characters table's byte address, or 0 (§10.5.2.1).

        Zero means new-line alone ends a read. The field exists
        from Version 5; earlier versions leave the word zero
        anyway.
        """

        return self._word(TERMINATING_TABLE)

    @property
    def unicode_translation_address(self) -> int:
        """The custom Unicode translation table's address, or 0 (§3.8.5.2).

        Word 3 of the header extension table, when the extension
        exists and reaches that far; zero otherwise, meaning the
        default table of §3.8.5.3.
        """

        extension = self._word(HEADER_EXTENSION)

        if extension == 0 or self._word(extension) < UNICODE_TABLE_WORD:
            return 0

        return self._word(extension + 2 * UNICODE_TABLE_WORD)

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

    def declare_standard_revision(self, major: int, minor: int) -> None:
        """Record which Standard revision the interpreter obeys (§11.1.5).

        Args:
            major: The revision's major number, written at $32.
            minor: The minor number, written at $33.

        Raises:
            ZMachineHeaderError: Over the pristine story bytes, which
                never change.
        """

        live = self._live()
        live[STANDARD_MAJOR_ADDRESS] = major
        live[STANDARD_MINOR_ADDRESS] = minor

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

    def declare_tandy(self, *, on: bool) -> None:
        """Claim, or decline to claim, a Tandy machine (§11.1.4).

        Bit 3 of Version 3's Flags 1 is "the legendary 'Tandy'
        bit": some early Infocom games were sold by the Tandy
        Corporation and answer it -- Zork I pretends not to have
        sequels, The Witness mutes some of its prose (§11.1
        Remarks). The bit belongs to the interpreter, so it is
        written both ways.

        Raises:
            ZMachineHeaderError: Outside Version 3, where the same
                bit means other things; or over the pristine story
                bytes, which never change.
        """

        self._require_version_3()
        self._set_flag(TANDY_BIT, on=on)

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

    def declare_sound(self, *, available: bool) -> None:
        """Clear the game's sound request when it cannot be met (§11.1).

        Flags 2 carries requests rather than capabilities: bit 7 is
        the game asking for sound effects, and the interpreter
        either obliges or clears the bit so the game knows to play
        on in silence -- the conforming quiet The Lurking Horror
        and Sherlock were both shipped to accept.

        Raises:
            ZMachineHeaderError: Over the pristine story bytes,
                which never change.
        """

        if available:
            return

        live = self._live()
        live[FLAGS_2_LOW] &= 0xFF ^ SOUND_BIT

    def declare_character_graphics(self, *, available: bool) -> None:
        """Clear the game's font 3 request when it cannot be met (§8.1.5.1).

        Bit 3 of Flags 2 is the game asking for the §16 character
        graphics font. An interpreter that can draw it leaves the
        request standing; one that cannot clears the bit, and the
        game knows to build its maps from plainer characters.

        Raises:
            ZMachineHeaderError: Over the pristine story bytes,
                which never change.
        """

        if available:
            return

        live = self._live()
        live[FLAGS_2_LOW] &= 0xFF ^ GRAPHICS_BIT

    def declare_mouse(self, *, available: bool) -> None:
        """Clear the game's mouse request when it cannot be met (§11.1.2).

        Bit 5 of Flags 2 is the game asking for a mouse; it is one
        of the requests the interpreter "clears again if it cannot
        provide".

        Raises:
            ZMachineHeaderError: Over the pristine story bytes,
                which never change.
        """

        if available:
            return

        live = self._live()
        live[FLAGS_2_LOW] &= 0xFF ^ MOUSE_BIT

    def declare_menus(self, *, available: bool) -> None:
        """Clear the game's menu request when it cannot be met (§11.1.2).

        Bit 8 of Flags 2 -- bit 0 of the word's high byte -- is a
        Version 6 game asking for menus, cleared like any request
        the interpreter cannot oblige.

        Raises:
            ZMachineHeaderError: Over the pristine story bytes,
                which never change.
        """

        if available:
            return

        live = self._live()
        live[FLAGS_2] &= 0xFF ^ MENUS_BIT

    def declare_pictures(self, *, available: bool) -> None:
        """Record whether picture displaying is available (§11.1.4).

        Bit 1 of Version 6's Flags 1 declares the general
        availability of the picture opcodes -- a capability the
        interpreter states outright, where Flags 2 bit 3 is the
        game's request. The arc_image contract reads the same bit
        in Versions 5, 7, and 8: there it answers for the band and
        its one draw opcode (arc_image: the contract, part A).

        Raises:
            ZMachineHeaderError: Before Version 5, where the bit
                belongs to the status-line type; or over the
                pristine story bytes.
        """

        if self.version < ARC_PICTURES_VERSION:
            msg = f"version {self.version} has no pictures bit to write (§11.1.4)"

            raise ZMachineHeaderError(msg)

        self._set_flag(PICTURES_BIT, on=available)

    def declare_sound_presence(self, *, available: bool) -> None:
        """Record whether sound effects are available (§9.1.1).

        In Version 6 the interpreter sets bit 5 of Flags 1 when it
        can provide sound effects beyond a bleep -- the capability
        declaration beside Flags 2 bit 7's request.

        Raises:
            ZMachineHeaderError: Before Version 6, where the bit
                belongs to screen splitting; or over the pristine
                story bytes.
        """

        if self.version < PICTURE_FLAGS_VERSION:
            msg = f"version {self.version} has no sound presence bit to write (§9.1.1)"

            raise ZMachineHeaderError(msg)

        self._set_flag(SOUND_PRESENCE_BIT, on=available)

    def declare_font_size(self, *, width: int, height: int) -> None:
        """Record the current font's size in screen units (§8.1.1).

        §11's table swaps the two bytes between the versions: $26
        is the font width in Version 5 but the font height in
        Version 6, and $27 the other way about. A 1-by-1 font made
        the swap invisible; a real font must honour it.

        Raises:
            ZMachineHeaderError: Before Version 5, where the fields
                do not exist; or over the pristine story bytes.
        """

        if self.version < FONT_FIELDS_VERSION:
            msg = f"version {self.version} has no font size fields to write (§8.1.1)"

            raise ZMachineHeaderError(msg)

        live = self._live()

        if self.version == PACKED_PC_VERSION:
            live[FONT_WIDTH] = height
            live[FONT_HEIGHT] = width
        else:
            live[FONT_WIDTH] = width
            live[FONT_HEIGHT] = height

    def declare_screen_units(self, *, width: int, height: int) -> None:
        """Record the screen's size in units (§8.4.3).

        Beyond Zork lays its windows out from these words -- edge
        positions are computed as width-in-units minus an offset --
        so leaving them unwritten sends its cursor arithmetic below
        zero.

        Raises:
            ZMachineHeaderError: Before Version 5, where the fields
                do not exist; or over the pristine story bytes.
        """

        if self.version < FONT_FIELDS_VERSION:
            msg = f"version {self.version} has no screen unit fields to write (§8.4.3)"

            raise ZMachineHeaderError(msg)

        live = self._live()
        live[SCREEN_WIDTH_UNITS : SCREEN_WIDTH_UNITS + 2] = width.to_bytes(2, "big")
        live[SCREEN_HEIGHT_UNITS : SCREEN_HEIGHT_UNITS + 2] = height.to_bytes(2, "big")

    def declare_colours(
        self, *, available: bool, foreground: int, background: int
    ) -> None:
        """Record the colour offer and the default colours (§8.3.2, §8.3.3).

        An interpreter with colours sets bit 0 of Flags 1; one
        without clears it. The default background and foreground
        codes are written at $2c and $2d either way -- black and
        white are still a background and a foreground.

        Raises:
            ZMachineHeaderError: Before Version 5, where the bit
                and the fields mean nothing; or over the pristine
                story bytes.
        """

        if self.version < COLOURS_VERSION:
            msg = f"version {self.version} has no colour fields to write (§8.3)"

            raise ZMachineHeaderError(msg)

        self._set_flag(COLOURS_BIT, on=available)

        live = self._live()
        live[DEFAULT_BACKGROUND_ADDRESS] = background
        live[DEFAULT_FOREGROUND_ADDRESS] = foreground

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
