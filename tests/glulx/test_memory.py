"""Glulx memory: ROM sacred, RAM growable (Glulx: The Memory Map)."""

from collections.abc import Callable

import pytest
from assertpy import assert_that

from voxam.errors import GlulxMemoryError
from voxam.glulx.memory import Memory
from voxam.glulx.story import Story


def mapped(image: Callable[..., bytes], **kwargs: int) -> Memory:
    return Memory(Story(image(**kwargs)))


# The stored image lays in low, everything above EXTSTART starts
# zeroed, and the accessors read bytes, shorts, and words at any
# alignment -- odd addresses included, which the stack forbids and
# memory expressly does not.
def test_the_image_lays_in_and_reads_at_any_alignment(
    image: Callable[..., bytes],
) -> None:
    memory = mapped(image)

    assert_that(memory.ramstart).is_equal_to(0x100)
    assert_that(memory.endmem).is_equal_to(0x300)
    assert_that(memory.read_word(0)).is_equal_to(0x476C756C)
    assert_that(memory.read_byte(0)).is_equal_to(ord("G"))
    assert_that(memory.read_short(0)).is_equal_to(0x476C)
    assert_that(memory.read_short(1)).is_equal_to(0x6C75)
    assert_that(memory.read_word(0x2FC)).is_equal_to(0)
    assert_that(memory.read(4, 4)).is_equal_to(0x00030102)
    assert_that(memory.read(0, 1)).is_equal_to(ord("G"))
    assert_that(memory.read(0, 2)).is_equal_to(0x476C)
    assert_that(memory.read_run(0, 4)).is_equal_to(b"Glul")
    assert_that(memory.read_run(0x2F0, 0)).is_equal_to(b"")


# Writes land in RAM masked to their width; ROM refuses with its
# name, and every edge of the map stays an edge.
def test_writes_land_masked_and_rom_refuses(image: Callable[..., bytes]) -> None:
    memory = mapped(image)

    memory.write_byte(0x100, 0x1FF)
    memory.write_short(0x102, 0x12345)
    memory.write_word(0x104, 0x1_FFFF_FFFF)
    memory.write(0x108, 1, 7)
    memory.write(0x10A, 2, 8)
    memory.write(0x10C, 4, 9)
    memory.write_run(0x110, b"hi")
    memory.write_run(0x110, b"")

    assert_that(memory.read_byte(0x100)).is_equal_to(0xFF)
    assert_that(memory.read_short(0x102)).is_equal_to(0x2345)
    assert_that(memory.read_word(0x104)).is_equal_to(0xFFFFFFFF)
    assert_that(memory.read(0x108, 1)).is_equal_to(7)
    assert_that(memory.read(0x10A, 2)).is_equal_to(8)
    assert_that(memory.read(0x10C, 4)).is_equal_to(9)
    assert_that(memory.read_run(0x110, 2)).is_equal_to(b"hi")

    refusals: tuple[Callable[[], object], ...] = (
        lambda: memory.write_byte(0x40, 1),
        lambda: memory.write_short(0x40, 1),
        lambda: memory.write_word(0x40, 1),
        lambda: memory.write_run(0x40, b"x"),
    )

    for refused in refusals:
        with pytest.raises(GlulxMemoryError, match="ROM"):
            refused()


# Every access that leaves the map halts loudly -- including the
# negative addresses a Python bytearray would otherwise quietly
# serve from its far end.
def test_the_maps_edges_are_loud(image: Callable[..., bytes]) -> None:
    memory = mapped(image)

    edges: tuple[Callable[[], object], ...] = (
        lambda: memory.read_byte(0x300),
        lambda: memory.read_byte(-1),
        lambda: memory.read_short(0x2FF),
        lambda: memory.read_short(-1),
        lambda: memory.read_word(0x2FD),
        lambda: memory.read_word(-1),
        lambda: memory.read_run(0x2FF, 2),
        lambda: memory.write_byte(0x300, 1),
        lambda: memory.write_short(0x2FF, 1),
        lambda: memory.write_word(0x2FD, 1),
        lambda: memory.write_run(0x2FF, b"xy"),
    )

    for outside in edges:
        with pytest.raises(GlulxMemoryError, match="outside the memory map"):
            outside()


# fill is mzero's engine and copy is mcopy's: fills mask their
# value, copies survive overlap in both directions because the
# source is read whole first, and zero counts touch nothing.
def test_fill_and_copy_serve_mzero_and_mcopy(image: Callable[..., bytes]) -> None:
    memory = mapped(image)

    memory.fill(0x100, 4, 0x1AB)
    memory.fill(0x100, 0, 7)

    assert_that(memory.read_run(0x100, 4)).is_equal_to(b"\xab\xab\xab\xab")

    memory.write_run(0x110, b"abcd")
    memory.copy(0x111, 0x110, 4)

    assert_that(memory.read_run(0x110, 5)).is_equal_to(b"aabcd")

    memory.write_run(0x120, b"abcd")
    memory.copy(0x11F, 0x120, 4)
    memory.copy(0x140, 0x140, 0)

    assert_that(memory.read_run(0x11F, 5)).is_equal_to(b"abcdd")

    with pytest.raises(GlulxMemoryError, match="outside"):
        memory.copy(0x100, 0x2FF, 2)

    with pytest.raises(GlulxMemoryError, match="ROM"):
        memory.copy(0x40, 0x100, 2)

    with pytest.raises(GlulxMemoryError, match="ROM"):
        memory.fill(0x40, 2)


# setmemsize grows the map zero-filled and shrinks it discarding,
# never below the boot ENDMEM and always on the 256-byte boundary
# (Glulx: Game State).
def test_set_size_grows_and_shrinks_within_the_law(
    image: Callable[..., bytes],
) -> None:
    memory = mapped(image)

    memory.set_size(0x500)

    assert_that(memory.endmem).is_equal_to(0x500)
    assert_that(memory.read_word(0x4FC)).is_equal_to(0)

    memory.write_word(0x400, 42)
    memory.set_size(0x400)

    assert_that(memory.endmem).is_equal_to(0x400)

    with pytest.raises(GlulxMemoryError, match="outside"):
        memory.read_word(0x400)

    with pytest.raises(GlulxMemoryError, match="multiple of 256"):
        memory.set_size(0x420)

    with pytest.raises(GlulxMemoryError, match="cannot shrink"):
        memory.set_size(0x200)

    memory.set_size(0x400)


# The protected range is "silently unaffected" by restart -- with
# no qualification about where it lies, so it survives even above
# EXTSTART, where the zeroed region begins; the reference glulxe
# loses that case and quixe keeps it, and the spec's words side
# with quixe (Glulx: Game State). Restart also returns a grown map
# to its boot size, and a zero length turns protection off.
def test_reset_honors_the_protected_range_and_the_boot_size(
    image: Callable[..., bytes],
) -> None:
    memory = mapped(image)

    memory.write_word(0x280, 0xDEADBEEF)
    memory.write_word(0x120, 0xABAD1DEA)
    memory.set_protection(0x280, 4)
    memory.set_size(0x500)
    memory.reset()

    assert_that(memory.endmem).is_equal_to(0x300)
    assert_that(memory.read_word(0x280)).is_equal_to(0xDEADBEEF)
    assert_that(memory.read_word(0x120)).is_equal_to(0)

    memory.set_protection(0x280, 0)
    memory.reset()

    assert_that(memory.read_word(0x280)).is_equal_to(0)


# A protected range hanging past the map's end is clipped, coming
# and going: only the bytes that exist are saved, and only the
# bytes that fit are pasted back.
def test_the_protected_range_clips_to_the_map(image: Callable[..., bytes]) -> None:
    memory = mapped(image)

    memory.write_word(0x2FC, 0xFEEDFACE)
    memory.set_protection(0x2FC, 8)
    memory.reset()

    assert_that(memory.read_word(0x2FC)).is_equal_to(0xFEEDFACE)

    beyond = mapped(image)

    beyond.set_size(0x400)
    beyond.write_word(0x3FC, 0xCAFED00D)
    beyond.set_protection(0x3FC, 4)
    beyond.reset()

    assert_that(beyond.endmem).is_equal_to(0x300)

    beyond.set_size(0x400)

    assert_that(beyond.read_word(0x3FC)).is_equal_to(0)


# The decoder's raw window is the live backing store itself.
def test_the_raw_window_is_the_backing_store(image: Callable[..., bytes]) -> None:
    memory = mapped(image)

    memory.write_byte(0x100, 0x2A)

    assert_that(memory.data[0x100]).is_equal_to(0x2A)
