"""Glulx main memory: the ROM/RAM map (Glulx: The Memory Map).

Addresses 0 to RAMSTART are ROM -- the header included -- and
writing there is illegal; RAM runs from RAMSTART to ENDMEM. The
game file stores only the bytes up to EXTSTART, and everything
above starts zeroed; once execution begins there is no difference
between the memory below and above that line. Unlike the stack,
memory has no alignment rule: a four-byte read at an odd address
is legal Glulx.

The bounds checks here are unconditional, and for a reason Python
adds to the spec's own: a negative index into a bytearray silently
addresses from the *end* of the buffer rather than faulting, so an
unchecked negative address would quietly read or corrupt the top
of memory. The reference interpreter glulxe (vendored) hides its
checks behind a compile-time switch; here they are the law.
"""

from voxam.errors import GlulxMemoryError
from voxam.glulx.story import BOUNDARY, Story

BYTE_MASK = 0xFF
SHORT_MASK = 0xFFFF
WORD_MASK = 0xFFFFFFFF

# The operand widths a read or write may come in: the spec's bytes,
# shorts, and 32-bit words (Glulx: The Memory Map).
BYTE_WIDTH = 1
SHORT_WIDTH = 2
WORD_WIDTH = 4


class Memory:
    """The live memory map: ROM held sacred, RAM growable.

    The bounds tests are written out inline in the byte, short, and
    word accessors rather than delegated to a helper: these are the
    most-called functions a running machine has, and a second
    Python call per access costs more than the check itself.
    """

    def __init__(self, story: Story) -> None:
        """Lay the stored image into a map grown to ENDMEM.

        The story already held the header to its promises -- the
        boundaries aligned, ordered, and ROM big enough for the
        header -- so none of that is re-litigated here.

        Args:
            story: The validated story whose image to lay in.
        """

        self._image = story.data
        self._ramstart = story.ramstart
        self._boot_endmem = story.endmem
        self._protect_start = 0
        self._protect_end = 0
        self._data = bytearray()
        self._endmem = 0

        self.reset()

    @property
    def ramstart(self) -> int:
        """The first writable address (Glulx: The Memory Map)."""

        return self._ramstart

    @property
    def endmem(self) -> int:
        """The current end of the memory map.

        Kept as its own number rather than derived from the backing
        store's length: every bounds check consults it.
        """

        return self._endmem

    @property
    def data(self) -> bytearray:
        """The raw backing store, for the instruction decoder only.

        Everything else goes through the accessors. The decoder
        reads several bytes per instruction from an ever-advancing
        program counter, and per-call accessor overhead there is
        the machine's single largest cost; it does its own bounds
        test inline instead -- and must keep the guarantee the
        accessors provide, indices in 0 <= address < endmem,
        because a negative bytearray index silently addresses from
        the end.
        """

        return self._data

    def read_byte(self, address: int) -> int:
        """Read one byte anywhere in the map.

        Raises:
            GlulxMemoryError: For an address outside the map
                (Glulx: The Memory Map).
        """

        if address < 0 or address >= self._endmem:
            raise GlulxMemoryError(_out_of_range(address))

        return self._data[address]

    def read_short(self, address: int) -> int:
        """Read a big-endian 16-bit short, any alignment.

        Raises:
            GlulxMemoryError: For a short running outside the map
                (Glulx: The Memory Map).
        """

        if address < 0 or address > self._endmem - SHORT_WIDTH:
            raise GlulxMemoryError(_out_of_range(address))

        return int.from_bytes(self._data[address : address + SHORT_WIDTH], "big")

    def read_word(self, address: int) -> int:
        """Read a big-endian 32-bit word, any alignment.

        Raises:
            GlulxMemoryError: For a word running outside the map
                (Glulx: The Memory Map).
        """

        if address < 0 or address > self._endmem - WORD_WIDTH:
            raise GlulxMemoryError(_out_of_range(address))

        return int.from_bytes(self._data[address : address + WORD_WIDTH], "big")

    def read(self, address: int, width: int) -> int:
        """Read at an operand's width: 1, 2, or 4 bytes.

        Raises:
            GlulxMemoryError: For an access outside the map.
        """

        if width == WORD_WIDTH:
            return self.read_word(address)

        if width == BYTE_WIDTH:
            return self.read_byte(address)

        return self.read_short(address)

    def read_run(self, address: int, count: int) -> bytes:
        """Read a run of bytes; an empty run needs no address at all.

        Raises:
            GlulxMemoryError: For a run leaving the map.
        """

        if count == 0:
            return b""

        self._require_readable(address, count)

        return bytes(self._data[address : address + count])

    def write_byte(self, address: int, value: int) -> None:
        """Write one byte into RAM, the value masked to 8 bits.

        Raises:
            GlulxMemoryError: For a write into ROM or outside the
                map (Glulx: The Memory Map).
        """

        if address < self._ramstart or address >= self._endmem:
            raise GlulxMemoryError(_refused_write(address, self._ramstart))

        self._data[address] = value & BYTE_MASK

    def write_short(self, address: int, value: int) -> None:
        """Write a big-endian short into RAM, masked to 16 bits.

        Raises:
            GlulxMemoryError: For a write into ROM or outside the
                map (Glulx: The Memory Map).
        """

        if address < self._ramstart or address > self._endmem - SHORT_WIDTH:
            raise GlulxMemoryError(_refused_write(address, self._ramstart))

        self._data[address : address + SHORT_WIDTH] = (value & SHORT_MASK).to_bytes(
            SHORT_WIDTH, "big"
        )

    def write_word(self, address: int, value: int) -> None:
        """Write a big-endian word into RAM, masked to 32 bits.

        Raises:
            GlulxMemoryError: For a write into ROM or outside the
                map (Glulx: The Memory Map).
        """

        if address < self._ramstart or address > self._endmem - WORD_WIDTH:
            raise GlulxMemoryError(_refused_write(address, self._ramstart))

        self._data[address : address + WORD_WIDTH] = (value & WORD_MASK).to_bytes(
            WORD_WIDTH, "big"
        )

    def write(self, address: int, width: int, value: int) -> None:
        """Write at an operand's width: 1, 2, or 4 bytes.

        Raises:
            GlulxMemoryError: For a write into ROM or outside the
                map.
        """

        if width == WORD_WIDTH:
            self.write_word(address, value)
        elif width == BYTE_WIDTH:
            self.write_byte(address, value)
        else:
            self.write_short(address, value)

    def write_run(self, address: int, data: bytes) -> None:
        """Write a run of bytes into RAM; an empty run writes nowhere.

        Raises:
            GlulxMemoryError: For a run touching ROM or leaving the
                map.
        """

        if not data:
            return

        self._require_writable(address, len(data))

        self._data[address : address + len(data)] = data

    def fill(self, address: int, count: int, value: int = 0) -> None:
        """Set a run of RAM bytes to one value -- mzero's work.

        Raises:
            GlulxMemoryError: For a run touching ROM or leaving the
                map.
        """

        if count == 0:
            return

        self._require_writable(address, count)

        self._data[address : address + count] = bytes([value & BYTE_MASK]) * count

    def copy(self, destination: int, source: int, count: int) -> None:
        """Copy a run within memory -- mcopy's work.

        Overlap is handled correctly: the source is read out whole
        before a byte lands.

        Raises:
            GlulxMemoryError: For a source leaving the map, or a
                destination touching ROM or leaving it.
        """

        if count == 0:
            return

        self._require_readable(source, count)
        self._require_writable(destination, count)

        self._data[destination : destination + count] = bytes(
            self._data[source : source + count]
        )

    def set_size(self, size: int) -> None:
        """Resize the memory map -- setmemsize's work.

        Growth is zero-filled and shrinkage discards, but the map
        never shrinks below its boot ENDMEM, and every size sits on
        the 256-byte boundary the header's numbers do (Glulx: Game
        State). Refusing this while the allocation heap is active
        is the caller's duty when the heap era arrives: memory has
        no business knowing about the heap.

        Raises:
            GlulxMemoryError: For a size off its boundary or below
                the boot ENDMEM.
        """

        if size % BOUNDARY:
            msg = (
                f"a memory size of {size} is not a multiple of {BOUNDARY} "
                f"(Glulx: Game State)"
            )

            raise GlulxMemoryError(msg)

        if size < self._boot_endmem:
            msg = (
                f"memory cannot shrink to {size}, below the {self._boot_endmem} "
                f"it booted with (Glulx: Game State)"
            )

            raise GlulxMemoryError(msg)

        if size > self._endmem:
            self._data.extend(bytes(size - self._endmem))
        elif size < self._endmem:
            del self._data[size:]

        self._endmem = size

    def set_protection(self, start: int, length: int) -> None:
        """Mark the range restart and restore leave alone -- protect.

        One range exists at a time, a zero length turns protection
        off, and the range itself is deliberately not part of saved
        state (Glulx: Game State).
        """

        if length == 0:
            self._protect_start = 0
            self._protect_end = 0
        else:
            self._protect_start = start
            self._protect_end = start + length

    def original_run(self, address: int, count: int) -> bytes:
        """What the game file held over a span; zeroes past its end.

        The compressed save format XORs live RAM against the
        original image, "as if the game file were extended with as
        many zeroes as necessary" above EXTSTART (Glulx: The
        Save-Game Format). Whole spans rather than single bytes,
        because everything that asks XORs the answer -- and Inform
        calls saveundo every turn.
        """

        head = self._image[address : address + count]

        return head + bytes(count - len(head))

    def overwrite_ram(self, contents: bytes) -> None:
        """Lay restored RAM in from RAMSTART, sparing protection.

        The protected range is "silently unaffected" by a restore
        (Glulx: Game State). Skipping the writes is the right model
        rather than saving and replacing the bytes, because the
        restore may have resized memory underneath the range: a
        range beyond the new end must come back zeroed by the
        resize, not repopulated from the file.
        """

        start = self.ramstart
        end = start + len(contents)
        low = max(self._protect_start, start)
        high = min(self._protect_end, end)

        if high <= low:
            self._data[start:end] = contents

            return

        if low > start:
            self._data[start:low] = contents[: low - start]

        if high < end:
            self._data[high:end] = contents[high - start :]

    def reset(self) -> None:
        """Restore the boot image whole -- restart's work.

        The protected range is "silently unaffected" (Glulx: Game
        State), with no qualification about where it lies -- so it
        survives even above EXTSTART, where the reference glulxe
        (vendored) loses it by zero-filling without consulting the
        range; quixe keeps it, and the spec's words side with
        quixe. The map also returns to its boot size: a setmemsize
        grown map does not survive a restart.
        """

        saved = self._protected_copy()
        self._data = bytearray(self._boot_endmem)
        self._endmem = self._boot_endmem
        self._data[: len(self._image)] = self._image

        self._paste_protected(saved)

    def _protected_copy(self) -> tuple[int, bytes] | None:
        """The protected range's live bytes, None when none is set."""

        start = self._protect_start
        end = min(self._protect_end, self._endmem)

        if end <= start:
            return None

        return start, bytes(self._data[start:end])

    def _paste_protected(self, saved: tuple[int, bytes] | None) -> None:
        """Lay the protected bytes back, clipped to the new map."""

        if saved is None:
            return

        start, data = saved
        end = min(start + len(data), self._endmem)

        if end > start:
            self._data[start:end] = data[: end - start]

    def _require_readable(self, address: int, count: int) -> None:
        """Hold a run to the map (Glulx: The Memory Map).

        Raises:
            GlulxMemoryError: For a run leaving the map. Element
                counts arrive as exact Python integers, so the
                overflow gymnastics glulxe needs when a count times
                a size wraps its 32-bit arithmetic cannot happen
                here: the naive check is the correct one.
        """

        if address < 0 or address > self._endmem - count:
            raise GlulxMemoryError(_out_of_range(address))

    def _require_writable(self, address: int, count: int) -> None:
        """Hold a run to RAM (Glulx: The Memory Map).

        Raises:
            GlulxMemoryError: For a run starting in ROM or leaving
                the map.
        """

        if address < self._ramstart or address > self._endmem - count:
            raise GlulxMemoryError(_refused_write(address, self._ramstart))


def _out_of_range(address: int) -> str:
    """The one message every out-of-map access carries."""

    return f"the address ${address:x} is outside the memory map (Glulx: The Memory Map)"


def _refused_write(address: int, ramstart: int) -> str:
    """Why a write was refused: ROM below RAMSTART, or off the map."""

    if address < ramstart:
        return (
            f"the address ${address:x} is in ROM, which ends at "
            f"${ramstart:x}: it is illegal to write there "
            f"(Glulx: The Memory Map)"
        )

    return _out_of_range(address)
