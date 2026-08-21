"""The allocation heap: blocks above the map's end (Glulx: Memory
Allocation Heap).
"""

from collections.abc import Callable

import pytest
from assertpy import assert_that

from voxam.errors import GlulxMemoryError, GlulxSaveError
from voxam.glulx import gestalt
from voxam.glulx.heap import Block, Heap
from voxam.glulx.machine import Machine
from voxam.glulx.story import Story

IDLE = bytes([0xC0, 0x00, 0x00, 0x81, 0x20])
PLANT = 0x180
RESULT = 0x140

BOOT_END = 0x300


def booted(image: Callable[..., bytes]) -> Machine:
    return Machine(Story(image(code=IDLE)))


# The first malloc activates the heap at the old end of memory and
# grows the map; freeing the last block hands everything back and
# the gestalt answers follow along.
def test_the_heap_activates_and_retires(image: Callable[..., bytes]) -> None:
    machine = booted(image)

    assert_that(machine.heap.active).is_false()
    assert_that(gestalt.answer(machine, 8, 0)).is_equal_to(0)
    assert_that(gestalt.answer(machine, 7, 0)).is_equal_to(1)

    first = machine.heap.alloc(0x40)

    assert_that(first).is_equal_to(BOOT_END)
    assert_that(machine.heap.start).is_equal_to(BOOT_END)
    assert_that(machine.memory.endmem).is_equal_to(BOOT_END + 0x100)
    assert_that(gestalt.answer(machine, 8, 0)).is_equal_to(BOOT_END)

    machine.heap.free(first)

    assert_that(machine.heap.active).is_false()
    assert_that(machine.memory.endmem).is_equal_to(BOOT_END)


# Allocation splits free space, reuses freed blocks first-fit, and
# coalesces adjacent free spans only when something needs the room.
def test_blocks_split_reuse_and_coalesce(image: Callable[..., bytes]) -> None:
    machine = booted(image)
    heap = machine.heap

    first = heap.alloc(0x40)
    second = heap.alloc(0x40)
    third = heap.alloc(0x40)

    assert_that((second, third)).is_equal_to((BOOT_END + 0x40, BOOT_END + 0x80))

    # Freeing the first two leaves two small free spans; a request
    # too big for either merges them on the way past.
    heap.free(first)
    heap.free(second)

    merged = heap.alloc(0x60)

    assert_that(merged).is_equal_to(first)

    # The remainder of the merged span is free again and taken by
    # a fit-sized request.
    assert_that(heap.alloc(0x20)).is_equal_to(first + 0x60)
    assert_that(heap.alloc(0x40)).is_equal_to(BOOT_END + 0xC0)

    # A free span walled in by allocated neighbors cannot merge;
    # the request extends the map past the allocated tail instead.
    heap.free(third)

    assert_that(heap.alloc(0x50)).is_equal_to(BOOT_END + 0x100)

    # And a free tail with nothing after it merges with the
    # extension when the map grows again.
    heap.free(BOOT_END + 0x100)

    assert_that(heap.alloc(0x200)).is_equal_to(BOOT_END + 0x100)


# Growing doubles the heap once one exists, and a grown request
# merges into a trailing free block rather than fragmenting.
def test_the_heap_doubles_as_it_grows(image: Callable[..., bytes]) -> None:
    machine = booted(image)
    heap = machine.heap

    first = heap.alloc(0x100)

    assert_that(machine.memory.endmem).is_equal_to(BOOT_END + 0x100)

    # The heap is full; the next request doubles it.
    second = heap.alloc(0x100)

    assert_that(second).is_equal_to(BOOT_END + 0x100)
    assert_that(machine.memory.endmem).is_equal_to(BOOT_END + 0x200)

    # A big request from a full heap extends by the request,
    # rounded to the boundary, and lands after the extant blocks.
    third = heap.alloc(0x210)

    assert_that(third).is_equal_to(BOOT_END + 0x200)
    assert_that(machine.memory.endmem).is_equal_to(BOOT_END + 0x500)

    # Free the tail block, then overask: the extension merges into
    # the trailing free span.
    heap.free(third)

    fourth = heap.alloc(0x800)

    assert_that(fourth).is_equal_to(BOOT_END + 0x200)

    heap.free(fourth)
    heap.free(first)
    heap.free(second)


# The refusals: a zero-length request is an error, an impossible
# extension is a spoken zero, and freeing what was never allocated
# is an error whether it is unknown or already free.
def test_the_heap_refuses_loudly_or_softly(
    image: Callable[..., bytes], monkeypatch: pytest.MonkeyPatch
) -> None:
    machine = booted(image)
    heap = machine.heap

    with pytest.raises(GlulxMemoryError, match="at least one byte"):
        heap.alloc(0)

    with pytest.raises(GlulxMemoryError, match="no allocated heap block"):
        heap.free(0x9999)

    first = heap.alloc(0x40)

    heap.alloc(0x40)
    heap.free(first)

    with pytest.raises(GlulxMemoryError, match="no allocated heap block"):
        heap.free(first)

    def refuse(_size: int) -> None:
        msg = "no more memory today"

        raise GlulxMemoryError(msg)

    monkeypatch.setattr(machine.memory, "set_size", refuse)

    # Allocation is never guaranteed: the answer is zero, not a
    # fault.
    assert_that(heap.alloc(0x4000)).is_equal_to(0)


# setmemsize is illegal while the heap owns the map, and legal
# again the moment it lets go; restart retires the heap outright.
def test_the_heap_owns_the_map(image: Callable[..., bytes]) -> None:
    machine = booted(image)

    first = machine.heap.alloc(0x40)

    machine.memory.write_run(
        PLANT,
        bytes([0x81, 0x03, 0x72])
        + (0x400).to_bytes(2, "big")
        + RESULT.to_bytes(4, "big"),
    )

    machine.pc = PLANT

    with pytest.raises(GlulxMemoryError, match="illegal while the allocation heap"):
        machine.step()

    machine.heap.free(first)

    machine.pc = PLANT

    machine.step()

    assert_that(machine.memory.endmem).is_equal_to(0x400)

    machine.heap.alloc(0x40)

    machine.restart()

    assert_that(machine.heap.active).is_false()
    assert_that(machine.memory.endmem).is_equal_to(BOOT_END)


# malloc and mfree through the opcodes: the address stores, and
# the free retires the block.
def test_malloc_and_mfree_dispatch(image: Callable[..., bytes]) -> None:
    machine = booted(image)

    plant = (
        bytes([0x81, 0x78, 0x72])
        + (0x40).to_bytes(2, "big")
        + RESULT.to_bytes(4, "big")
        + bytes([0x81, 0x79, 0x03])
        + BOOT_END.to_bytes(4, "big")
        + bytes([0x81, 0x20])
    )

    machine.memory.write_run(PLANT, plant)

    machine.pc = PLANT

    machine.run(limit=10)

    assert_that(machine.memory.read_word(RESULT)).is_equal_to(BOOT_END)
    assert_that(machine.heap.active).is_false()


# A summary names the extant blocks; applying one rebuilds them
# with the gaps and the tail reconstructed as free space.
def test_summaries_rebuild_the_heap(image: Callable[..., bytes]) -> None:
    machine = booted(image)
    heap = machine.heap

    assert_that(heap.summary()).is_empty()

    first = heap.alloc(0x40)
    second = heap.alloc(0x30)
    third = heap.alloc(0x20)

    heap.free(second)

    words = heap.summary()

    assert_that(words).is_equal_to([BOOT_END, 2, first, 0x40, third, 0x20])

    # Rebuild on a fresh twin whose memory is already the right
    # size, and the gap and tail come back free.
    twin = booted(image)

    twin.memory.set_size(machine.memory.endmem)
    twin.heap.apply_summary(words)

    assert_that(twin.heap.blocks).is_equal_to(
        [
            Block(first, 0x40, False),
            Block(first + 0x40, 0x30, True),
            Block(third, 0x20, False),
            Block(third + 0x20, 0x70, True),
        ]
    )
    assert_that(twin.heap.summary()).is_equal_to(words)

    # A summary whose last block runs flush to the end of memory
    # rebuilds with no trailing free span at all.
    flush = booted(image)

    flush.memory.set_size(0x400)
    flush.heap.apply_summary([BOOT_END, 1, BOOT_END, 0x100])

    assert_that(flush.heap.blocks).is_equal_to([Block(BOOT_END, 0x100, False)])

    # The empty forms apply as nothing at all.
    bare = Heap(booted(image).memory)

    bare.apply_summary([])
    bare.apply_summary([0, 0])

    assert_that(bare.active).is_false()


# The summaries that cannot be applied: onto an active heap, cut
# short mid-block, or with blocks out of address order.
def test_wrong_summaries_are_refused(image: Callable[..., bytes]) -> None:
    machine = booted(image)

    machine.heap.alloc(0x40)

    with pytest.raises(GlulxSaveError, match="active heap"):
        machine.heap.apply_summary([0x300, 1, 0x300, 0x40])

    fresh = booted(image)

    with pytest.raises(GlulxSaveError, match="cut short"):
        fresh.heap.apply_summary([0x300, 2, 0x300])

    with pytest.raises(GlulxSaveError, match="out of address order"):
        fresh.heap.apply_summary([0x300, 2, 0x340, 0x10, 0x300, 0x10])
