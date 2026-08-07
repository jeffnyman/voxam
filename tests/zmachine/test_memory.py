from collections.abc import Callable

import pytest
from assertpy import assert_that

from voxam.errors import ZMachineMemoryError
from voxam.zmachine.memory import Memory
from voxam.zmachine.story import Story

ALL_VERSIONS = range(1, 9)
STATIC_BASE = 128
HIGH_BASE = 256
SIZE = 512


def memory_image(
    version: int = 3,
    static_base: int = STATIC_BASE,
    high_base: int = HIGH_BASE,
    size: int = SIZE,
    seed: dict[int, int] | None = None,
) -> Memory:
    data = bytearray(size)
    data[0] = version
    data[0x04:0x06] = high_base.to_bytes(2, "big")
    data[0x0E:0x10] = static_base.to_bytes(2, "big")

    for address, value in (seed or {}).items():
        data[address] = value

    return Memory(Story(bytes(data)))


@pytest.mark.parametrize("version", ALL_VERSIONS)
def test_every_fixture_builds_a_coherent_memory(
    version: int, load_fixture: Callable[[int], Story]
) -> None:
    memory = Memory(load_fixture(version))

    assert_that(memory.read_byte(0)).is_equal_to(version)


def test_reads_static_memory() -> None:
    memory = memory_image(seed={200: 0x11, 201: 0x22})

    assert_that(memory.read_byte(200)).is_equal_to(0x11)
    assert_that(memory.read_word(200)).is_equal_to(0x1122)


def test_caps_static_memory_at_ffff() -> None:
    memory = memory_image(size=0x10800, seed={0xFFFF: 0x42})

    assert_that(memory.read_byte(0xFFFF)).is_equal_to(0x42)

    with pytest.raises(ZMachineMemoryError, match="game-readable memory"):
        memory.read_byte(0x10000)


def test_rejects_read_beyond_the_file() -> None:
    memory = memory_image()

    assert_that(memory.read_byte(SIZE - 1)).is_equal_to(0)

    with pytest.raises(ZMachineMemoryError, match="game-readable memory"):
        memory.read_byte(SIZE)


def test_rejects_word_read_straddling_the_file_end() -> None:
    memory = memory_image()

    with pytest.raises(ZMachineMemoryError, match="game-readable memory"):
        memory.read_word(SIZE - 1)


def test_rejects_negative_address() -> None:
    # Python's own indexing would happily serve data[-1] as the last
    # byte of the file; the guard has to catch this before Python does.
    memory = memory_image()

    with pytest.raises(ZMachineMemoryError, match="cannot read"):
        memory.read_byte(-1)

    with pytest.raises(ZMachineMemoryError, match="cannot write"):
        memory.write_byte(-1, 0)


def test_round_trips_a_byte_in_dynamic_memory() -> None:
    memory = memory_image()
    memory.write_byte(64, 0xAB)

    assert_that(memory.read_byte(64)).is_equal_to(0xAB)


def test_allows_write_to_the_last_dynamic_byte() -> None:
    memory = memory_image()
    memory.write_byte(STATIC_BASE - 1, 0x77)

    assert_that(memory.read_byte(STATIC_BASE - 1)).is_equal_to(0x77)


def test_words_are_stored_big_endian() -> None:
    memory = memory_image()
    memory.write_word(64, 0xBEEF)

    assert_that(memory.read_word(64)).is_equal_to(0xBEEF)
    assert_that(memory.read_byte(64)).is_equal_to(0xBE)
    assert_that(memory.read_byte(65)).is_equal_to(0xEF)


def test_rejects_write_at_the_static_boundary() -> None:
    memory = memory_image()

    with pytest.raises(ZMachineMemoryError, match="only dynamic memory"):
        memory.write_byte(STATIC_BASE, 0x77)


def test_rejects_word_write_straddling_the_boundary() -> None:
    memory = memory_image()

    with pytest.raises(ZMachineMemoryError, match="only dynamic memory"):
        memory.write_word(STATIC_BASE - 1, 0xBEEF)


def test_dynamic_write_round_trips_on_a_real_image(
    load_fixture: Callable[[int], Story],
) -> None:
    memory = Memory(load_fixture(3))
    memory.write_byte(64, 0x55)

    assert_that(memory.read_byte(64)).is_equal_to(0x55)


@pytest.mark.parametrize("value", [-1, 256])
def test_rejects_byte_values_that_do_not_fit(value: int) -> None:
    memory = memory_image()

    with pytest.raises(ZMachineMemoryError, match="fit in a byte"):
        memory.write_byte(64, value)


@pytest.mark.parametrize("value", [-1, 0x10000])
def test_rejects_word_values_that_do_not_fit(value: int) -> None:
    memory = memory_image()

    with pytest.raises(ZMachineMemoryError, match="fit in a word"):
        memory.write_word(64, value)


def test_rejects_static_base_inside_the_header() -> None:
    with pytest.raises(ZMachineMemoryError, match="smaller than the 64-byte"):
        memory_image(static_base=63)


def test_rejects_static_base_beyond_the_file() -> None:
    with pytest.raises(ZMachineMemoryError, match="beyond the end"):
        memory_image(static_base=SIZE + 1)


def test_rejects_high_memory_overlapping_dynamic() -> None:
    with pytest.raises(ZMachineMemoryError, match="inside dynamic memory"):
        memory_image(high_base=STATIC_BASE - 1)


def test_allows_high_memory_overlapping_static() -> None:
    memory = memory_image(high_base=STATIC_BASE)

    assert_that(memory.read_byte(0)).is_equal_to(3)


def test_rejects_file_exceeding_version_maximum() -> None:
    with pytest.raises(ZMachineMemoryError, match="allows at most"):
        memory_image(version=1, size=128 * 1024 + 2)


def test_header_view_reflects_live_memory() -> None:
    memory = memory_image()
    memory.write_word(0x02, 0x0042)

    assert_that(memory.header.release).is_equal_to(0x0042)


def test_story_remains_pristine_after_memory_writes(
    load_fixture: Callable[[int], Story],
) -> None:
    story = load_fixture(3)
    memory = Memory(story)
    original = story.header.release

    memory.write_word(0x02, original + 1)

    assert_that(memory.header.release).is_equal_to(original + 1)
    assert_that(story.header.release).is_equal_to(original)
