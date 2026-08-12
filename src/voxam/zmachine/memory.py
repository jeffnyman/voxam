"""The memory map of the Z-Machine (§1.1)."""

from voxam.errors import ZMachineMemoryError
from voxam.zmachine.header import HEADER_SIZE, Header
from voxam.zmachine.story import Story

# The maximum story length in bytes depends on the version (§1.1.4).
KIB = 1024
MAX_STORY_LENGTH = {
    1: 128 * KIB,
    2: 128 * KIB,
    3: 128 * KIB,
    4: 256 * KIB,
    5: 256 * KIB,
    6: 512 * KIB,
    7: 512 * KIB,
    8: 512 * KIB,
}

# Static memory never extends beyond this byte address, however large the
# story file is (§1.1.2).
STATIC_MEMORY_CAP = 0xFFFF

# The largest values a single byte or a big-endian word can hold (§2.1).
BYTE_MAX = 0xFF
WORD_MAX = 0xFFFF


class Memory:
    """The mutable working image of a story, with §1.1 access rules.

    A Story is the pristine file; Memory is the image a running game
    reads and writes. Keeping them separate is what will let restart
    and restore reload dynamic memory from an untouched original.

    Writes are permitted only below the static memory base (§1.1.1,
    §1.1.2). Reads are permitted through dynamic and static memory,
    whose top is the lower of the last file byte or $ffff (§1.1.2);
    high memory beyond that is reachable only through routine calls
    and print_paddr, which do not exist yet. The finer-grained header
    write rules (§11.1) are also not yet enforced.
    """

    def __init__(self, story: Story) -> None:
        """Build a working memory image from a validated story.

        Args:
            story: The loaded story file to image.

        Raises:
            ZMachineMemoryError: If the header's region boundaries do not
                describe a coherent memory map (§1.1), or the file exceeds
                its version's maximum length (§1.1.4).
        """

        self._data = bytearray(story.data)
        self._static_base = story.header.static_memory_base
        self._high_base = story.header.high_memory_base

        maximum = MAX_STORY_LENGTH[story.version]

        if len(self._data) > maximum:
            msg = (
                f"story file is {len(self._data)} bytes, but version "
                f"{story.version} allows at most {maximum} (§1.1.4)"
            )

            raise ZMachineMemoryError(msg)

        if self._static_base < HEADER_SIZE:
            msg = (
                f"static memory begins at ${self._static_base:04x}, which "
                f"would leave dynamic memory smaller than the "
                f"{HEADER_SIZE}-byte header (§1.1.1)"
            )

            raise ZMachineMemoryError(msg)

        if self._static_base > len(self._data):
            msg = (
                f"static memory begins at ${self._static_base:04x}, beyond "
                f"the end of the {len(self._data)}-byte file (§1.1)"
            )

            raise ZMachineMemoryError(msg)

        if self._high_base < self._static_base:
            msg = (
                f"high memory begins at ${self._high_base:04x}, inside "
                f"dynamic memory, which runs up to "
                f"${self._static_base:04x} (§1.1.3)"
            )

            raise ZMachineMemoryError(msg)

        # The top of static memory is the lower of the last file byte or
        # $ffff (§1.1.2); addresses past it cannot be directly accessed.
        self._read_limit = min(len(self._data), STATIC_MEMORY_CAP + 1)

    @property
    def header(self) -> Header:
        """A live, typed view of the header within this image (§11.1).

        The header sits in dynamic memory, and a running game may
        legally alter parts of it (§11.1.2.1), so this view reflects
        writes made through this Memory rather than the pristine story.
        """

        return Header(self._data)

    def dynamic_snapshot(self) -> bytes:
        """Capture dynamic memory whole, header included (§6.1).

        Returns:
            Every byte below the static memory base, frozen. Static
            and high memory never change, so this is all of memory a
            save needs (§6.1.1).
        """

        return bytes(self._data[: self._static_base])

    def restore_dynamic(self, image: bytes) -> None:
        """Write a captured dynamic memory image back whole (§6.1.2).

        The finer restore duties -- preserving 'Flags 2', re-stamping
        the interpreter's header fields -- belong to the machine
        (§6.1.2, §6.1.2.2); this write is deliberately verbatim.

        Args:
            image: A capture taken from a memory image of this exact
                shape.

        Raises:
            ZMachineMemoryError: If the image's size does not match
                this story's dynamic memory, which means it was
                captured from some other game (§6.1.2.1).
        """

        if len(image) != self._static_base:
            msg = (
                f"cannot restore a {len(image)}-byte dynamic memory image "
                f"over the {self._static_base} bytes this story defines: "
                f"it was captured from a different game (§6.1.2.1)"
            )

            raise ZMachineMemoryError(msg)

        self._data[: self._static_base] = image

    def read_byte(self, address: int) -> int:
        """Read the byte at an address in dynamic or static memory.

        Args:
            address: The byte address to read (§1.1).

        Returns:
            The value of the byte at that address.

        Raises:
            ZMachineMemoryError: If the address lies outside the
                game-readable regions (§1.1.2).
        """

        self._require_readable(address)

        return self._data[address]

    def fetch_byte(self, address: int) -> int:
        """Read a byte anywhere in the story, as the interpreter (§1.1.3).

        Game reads stop at the top of static memory, but the
        interpreter's own accesses -- instruction fetch, routine
        headers, encoded strings -- must reach all of high memory,
        beyond even $ffff in large stories.

        Args:
            address: The byte address to read.

        Returns:
            The value of the byte at that address.

        Raises:
            ZMachineMemoryError: If the address lies outside the file.
        """

        self._require_fetchable(address)

        return self._data[address]

    def fetch_word(self, address: int) -> int:
        """Read a big-endian word anywhere in the story (§1.1.3, §2.1).

        Args:
            address: The byte address of the word's first byte.

        Returns:
            The value of the word at that address.

        Raises:
            ZMachineMemoryError: If either byte lies outside the file.
        """

        self._require_fetchable(address)
        self._require_fetchable(address + 1)

        return int.from_bytes(self._data[address : address + 2], "big")

    def read_word(self, address: int) -> int:
        """Read the big-endian word at an address (§2.1).

        Args:
            address: The byte address of the word's first byte.

        Returns:
            The value of the word at that address.

        Raises:
            ZMachineMemoryError: If either byte of the word lies outside
                the game-readable regions (§1.1.2).
        """

        self._require_readable(address)
        self._require_readable(address + 1)

        return int.from_bytes(self._data[address : address + 2], "big")

    def write_byte(self, address: int, value: int) -> None:
        """Write a byte into dynamic memory.

        Args:
            address: The byte address to write (§1.1).
            value: The byte value to store.

        Raises:
            ZMachineMemoryError: If the address lies outside dynamic
                memory (§1.1.2) or the value does not fit in a byte.
        """

        self._require_writable(address)
        self._require_byte(value)

        self._data[address] = value

    def write_word(self, address: int, value: int) -> None:
        """Write a big-endian word into dynamic memory (§2.1).

        Args:
            address: The byte address of the word's first byte.
            value: The word value to store.

        Raises:
            ZMachineMemoryError: If either byte of the word lies outside
                dynamic memory (§1.1.2) or the value does not fit in a
                word.
        """

        self._require_writable(address)
        self._require_writable(address + 1)
        self._require_word(value)

        self._data[address : address + 2] = value.to_bytes(2, "big")

    def _require_fetchable(self, address: int) -> None:
        """Reject addresses outside the story file itself (§1.1)."""

        if not 0 <= address < len(self._data):
            msg = (
                f"cannot fetch ${address:04x}: the story file ends at "
                f"${len(self._data) - 1:04x} (§1.1)"
            )

            raise ZMachineMemoryError(msg)

    def _require_readable(self, address: int) -> None:
        """Reject addresses outside dynamic and static memory (§1.1.2)."""

        if not 0 <= address < self._read_limit:
            msg = (
                f"cannot read ${address:04x}: game-readable memory runs "
                f"from $0000 up to ${self._read_limit - 1:04x} (§1.1.2)"
            )

            raise ZMachineMemoryError(msg)

    def _require_writable(self, address: int) -> None:
        """Reject addresses outside dynamic memory (§1.1.1, §1.1.2)."""

        if not 0 <= address < self._static_base:
            msg = (
                f"cannot write ${address:04x}: only dynamic memory, below "
                f"${self._static_base:04x}, is writable (§1.1.2)"
            )

            raise ZMachineMemoryError(msg)

    def _require_byte(self, value: int) -> None:
        """Reject values that do not fit in a single byte."""

        if not 0 <= value <= BYTE_MAX:
            msg = f"value {value} does not fit in a byte"

            raise ZMachineMemoryError(msg)

    def _require_word(self, value: int) -> None:
        """Reject values that do not fit in a single word."""

        if not 0 <= value <= WORD_MAX:
            msg = f"value {value} does not fit in a word"

            raise ZMachineMemoryError(msg)
