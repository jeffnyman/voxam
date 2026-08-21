"""The dynamic allocation heap (Glulx: Memory Allocation Heap).

Allocated blocks live above ENDMEM. The first malloc activates the
heap: the current end of memory becomes the heap's start address,
and the map grows from there. Freeing the last block deactivates it
and shrinks memory back to where it began, at which point
setmemsize becomes legal again.

The block list covers the heap completely and in address order --
the first block starts at the heap's start, each one ends where the
next begins, and the last ends at endmem. Free blocks are part of
that list rather than a separate free-list, which is why coalescing
is something the allocator does as it searches.

The bookkeeping lives here, not in the memory map, so a game
writing outside its blocks cannot corrupt it -- the spec says the
interpreter may keep it "in a private data structure", and Voxam
does exactly that. Writing anywhere in the heap range stays legal.
"""

from dataclasses import dataclass
from itertools import pairwise

from voxam.errors import GlulxMemoryError, GlulxSaveError
from voxam.glulx.memory import Memory

# Memory grows in 256-byte units, like every Glulx boundary.
BOUNDARY = 0x100


@dataclass
class Block:
    """One span of the heap, allocated or free.

    Attributes:
        address: Where the span begins.
        length: How many bytes it covers.
        free: Whether the span is unclaimed.
    """

    address: int
    length: int
    free: bool


class Heap:
    """The allocation heap for one machine.

    Attributes:
        start: The heap's start address; zero means inactive.
        blocks: Every span, allocated and free, in address order.
        alloc_count: How many blocks are currently allocated.
    """

    def __init__(self, memory: Memory) -> None:
        """Stand over a memory map, inactive."""

        self.memory = memory
        self.start = 0
        self.blocks: list[Block] = []
        self.alloc_count = 0

    @property
    def active(self) -> bool:
        """Whether any block is extant -- the heap owns the map."""

        return self.start != 0

    def clear(self) -> None:
        """Deactivate the heap and give its memory back.

        Freeing the last block lands here, and so does restart --
        the heap does not survive one (Glulx: Memory Allocation
        Heap).
        """

        self.blocks.clear()

        if self.start:
            self.memory.set_size(self.start)

        self.start = 0
        self.alloc_count = 0

    def alloc(self, length: int) -> int:
        """Claim a span; the address comes back, or 0 on failure.

        Allocation is never guaranteed: a refusal is an answer,
        not an error (Glulx: Memory Allocation Heap).

        Raises:
            GlulxMemoryError: For a zero-length request, which no
                answer could name.
        """

        if length == 0:
            msg = "a heap allocation must ask for at least one byte"

            raise GlulxMemoryError(msg)

        index = self._find_free(length)

        if index is None:
            index = self._extend(length)

            if index is None:
                return 0

        block = self.blocks[index]

        if block.length > length:
            # Split, leaving the remainder free and the list still
            # in address order.
            self.blocks.insert(
                index + 1, Block(block.address + length, block.length - length, True)
            )

            block.length = length

        block.free = False
        self.alloc_count += 1

        return block.address

    def _find_free(self, length: int) -> int | None:
        """First-fit search, coalescing free neighbors on the way.

        Merging happens during the search rather than eagerly,
        as the reference glulxe has it: a run of free blocks is
        only joined up when something actually needs the space.
        """

        index = 0

        while index < len(self.blocks):
            block = self.blocks[index]

            if block.free and block.length >= length:
                return index

            if not block.free:
                index += 1

                continue

            following = self.blocks[index + 1] if index + 1 < len(self.blocks) else None

            if following is None or not following.free:
                index += 1

                continue

            # Free, too small, and followed by free space: merge
            # and retry at the same position rather than advancing.
            block.length += following.length

            del self.blocks[index + 1]

        return None

    def _extend(self, length: int) -> int | None:
        """Grow the map; the new free block's index comes back.

        The heap doubles, or grows by the requested length, or by
        one boundary -- whichever is largest -- rounded up to the
        256-byte grain.
        """

        old_endmem = self.memory.endmem
        extension = (old_endmem - self.start) if self.start else 0
        extension = max(extension, length, BOUNDARY)
        extension = (extension + BOUNDARY - 1) & ~(BOUNDARY - 1)

        try:
            self.memory.set_size(old_endmem + extension)
        except (GlulxMemoryError, MemoryError):
            # Allocation is never guaranteed (Glulx: Memory
            # Allocation Heap).
            return None

        if self.start == 0:
            self.start = old_endmem

        if self.blocks and self.blocks[-1].free:
            self.blocks[-1].length += extension
        else:
            self.blocks.append(Block(old_endmem, extension, True))

        return len(self.blocks) - 1

    def free(self, address: int) -> None:
        """Release the block at an address, which must be extant.

        Freeing the last block deactivates the heap and hands the
        memory back (Glulx: Memory Allocation Heap).

        Raises:
            GlulxMemoryError: For an address that names no
                allocated block.
        """

        for block in self.blocks:
            if block.address == address and not block.free:
                break
        else:
            msg = f"no allocated heap block begins at {address:#x}"

            raise GlulxMemoryError(msg)

        block.free = True
        self.alloc_count -= 1

        if self.alloc_count <= 0:
            self.clear()

    def summary(self) -> list[int]:
        """The heap as the save format's MAll words.

        The layout is start, count, then address and length for
        each extant block (Glulx: Memory Allocation Heap); an
        inactive heap summarizes as nothing at all, and its chunk
        is omitted.
        """

        if not self.active:
            return []

        values = [self.start, self.alloc_count]

        for block in self.blocks:
            if not block.free:
                values += [block.address, block.length]

        return values

    def apply_summary(self, values: list[int]) -> None:
        """Rebuild the heap from a summary's words.

        Memory must already be the size it was when the summary
        was taken -- restoring the map is the caller's job -- and
        the free blocks are reconstructed from the gaps between
        extant ones, out to endmem.

        Raises:
            GlulxSaveError: When the heap is already active, the
                summary's pairs are cut short, or its blocks are
                out of address order.
        """

        if self.active:
            msg = "a heap summary cannot land on an active heap"

            raise GlulxSaveError(msg)

        if not values or values[:2] == [0, 0]:
            return

        extant = values[2:]

        if len(extant) % 2:
            msg = "the save file's heap summary is cut short mid-block"

            raise GlulxSaveError(msg)

        addresses = extant[0::2]

        if any(one >= two for one, two in pairwise(addresses)):
            msg = "the save file's heap blocks are out of address order"

            raise GlulxSaveError(msg)

        self.start = values[0]
        self.alloc_count = values[1]
        self.blocks = []

        position = 0
        cursor = self.start
        endmem = self.memory.endmem

        while position < len(extant) or cursor < endmem:
            if position >= len(extant):
                # Trailing free space, out to the end of the map.
                self.blocks.append(Block(cursor, endmem - cursor, True))

                break

            address, length = extant[position], extant[position + 1]

            if cursor < address:
                # A gap before the next extant block is free space.
                self.blocks.append(Block(cursor, address - cursor, True))

                cursor = address

                continue

            self.blocks.append(Block(address, length, False))

            position += 2
            cursor = address + length
