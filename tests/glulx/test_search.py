"""The search opcodes: three shapes of lookup (Glulx: Searching)."""

from collections.abc import Callable

import pytest
from assertpy import assert_that

from voxam.errors import GlulxInstructionError
from voxam.glulx import search
from voxam.glulx.machine import Machine
from voxam.glulx.story import Story

IDLE = bytes([0xC0, 0x00, 0x00, 0x81, 0x20])
PLANT = 0x180
RESULT = 0x140
TABLE = 0x2C0

MISS_INDEX = 0xFFFFFFFF


def booted(image: Callable[..., bytes]) -> Machine:
    return Machine(Story(image(code=IDLE)))


# A direct key sits in the operand's low bytes, big-endian, and
# must fit a word; an indirect key is read from memory and may be
# any size at all.
def test_keys_arrive_direct_or_indirect(image: Callable[..., bytes]) -> None:
    machine = booted(image)

    # Direct: the upper bytes of the operand are ignored.
    machine.memory.write_run(TABLE, bytes([0x78, 0x00]))

    found = search.linear_search(machine.memory, 0x12345678, 1, TABLE, 1, 2, 0, 0)

    assert_that(found).is_equal_to(TABLE)

    # Indirect: a three-byte key is legal, because the key is an
    # address, not a value.
    machine.memory.write_run(TABLE, bytes([0xAA, 0xBB, 0xCC]))
    machine.memory.write_run(TABLE + 8, bytes([0xAA, 0xBB, 0xCC]))

    found = search.linear_search(
        machine.memory, TABLE + 8, 3, TABLE, 3, 1, 0, search.KEY_INDIRECT
    )

    assert_that(found).is_equal_to(TABLE)

    with pytest.raises(GlulxInstructionError, match="one, two, or four"):
        search.linear_search(machine.memory, 0, 3, TABLE, 3, 1, 0, 0)


# The linear search walks structures in order: a hit answers the
# address or the index, a miss answers 0 or -1, and the key may
# sit anywhere inside the structure.
def test_linear_search_walks_in_order(image: Callable[..., bytes]) -> None:
    machine = booted(image)

    # Four structs of four bytes; the two-byte key sits at offset 2.
    for index, key in enumerate((0x1111, 0x2222, 0x3333, 0x4444)):
        machine.memory.write_run(TABLE + 4 * index, bytes(2) + key.to_bytes(2, "big"))

    hit = search.linear_search(machine.memory, 0x3333, 2, TABLE, 4, 4, 2, 0)

    assert_that(hit).is_equal_to(TABLE + 8)
    assert_that(
        search.linear_search(
            machine.memory, 0x3333, 2, TABLE, 4, 4, 2, search.RETURN_INDEX
        )
    ).is_equal_to(2)

    assert_that(
        search.linear_search(machine.memory, 0x9999, 2, TABLE, 4, 4, 2, 0)
    ).is_equal_to(0)
    assert_that(
        search.linear_search(
            machine.memory, 0x9999, 2, TABLE, 4, 4, 2, search.RETURN_INDEX
        )
    ).is_equal_to(MISS_INDEX)


# A zero key ends a terminated search -- but only after the match
# check, so a search *for* the zero key still finds it. With the
# unlimited count, the zero terminator is what makes the search
# finite.
def test_zero_keys_terminate_after_matching(
    image: Callable[..., bytes],
) -> None:
    machine = booted(image)

    for index, key in enumerate((0x11, 0x00, 0x33)):
        machine.memory.write_run(TABLE + 2 * index, bytes([key, 0]))

    # 0x33 sits beyond the zero key, so a terminated search misses
    # it; an unterminated one still gets there.
    assert_that(
        search.linear_search(
            machine.memory, 0x33, 1, TABLE, 2, 3, 0, search.ZERO_KEY_TERMINATES
        )
    ).is_equal_to(0)
    assert_that(
        search.linear_search(machine.memory, 0x33, 1, TABLE, 2, 3, 0, 0)
    ).is_equal_to(TABLE + 4)

    # The zero key itself is findable.
    assert_that(
        search.linear_search(
            machine.memory, 0x00, 1, TABLE, 2, 3, 0, search.ZERO_KEY_TERMINATES
        )
    ).is_equal_to(TABLE + 2)

    # 0xFFFFFFFF structures means "no limit": the terminator is
    # the only end the search has.
    assert_that(
        search.linear_search(
            machine.memory,
            0x77,
            1,
            TABLE,
            2,
            0xFFFFFFFF,
            0,
            search.ZERO_KEY_TERMINATES,
        )
    ).is_equal_to(0)


# The binary search halves a sorted array: hits at the ends drive
# both halvings, and a miss between keys answers the failure value
# for either form.
def test_binary_search_halves_a_sorted_array(
    image: Callable[..., bytes],
) -> None:
    machine = booted(image)
    keys = (0x10, 0x20, 0x30, 0x40, 0x50)

    for index, key in enumerate(keys):
        machine.memory.write_run(TABLE + 2 * index, bytes([key, 0]))

    for index, key in enumerate(keys):
        assert_that(
            search.binary_search(machine.memory, key, 1, TABLE, 2, 5, 0, 0)
        ).is_equal_to(TABLE + 2 * index)

    assert_that(
        search.binary_search(
            machine.memory, 0x50, 1, TABLE, 2, 5, 0, search.RETURN_INDEX
        )
    ).is_equal_to(4)
    assert_that(
        search.binary_search(machine.memory, 0x25, 1, TABLE, 2, 5, 0, 0)
    ).is_equal_to(0)
    assert_that(
        search.binary_search(
            machine.memory, 0x25, 1, TABLE, 2, 5, 0, search.RETURN_INDEX
        )
    ).is_equal_to(MISS_INDEX)


# The linked search follows next pointers wherever they lead: a
# zero link ends the list, and the zero-key terminator cuts it
# short the same way it cuts the linear walk.
def test_linked_search_follows_the_chain(image: Callable[..., bytes]) -> None:
    machine = booted(image)

    # Three nodes, deliberately out of address order: key byte at
    # +0, next pointer at +4.
    chain = (
        (TABLE, 0x11, TABLE + 0x20),
        (TABLE + 0x20, 0x22, TABLE + 0x10),
        (TABLE + 0x10, 0x33, 0),
    )

    for address, key, link in chain:
        machine.memory.write_byte(address, key)
        machine.memory.write_word(address + 4, link)

    assert_that(
        search.linked_search(machine.memory, 0x33, 1, TABLE, 0, 4, 0)
    ).is_equal_to(TABLE + 0x10)
    assert_that(
        search.linked_search(machine.memory, 0x99, 1, TABLE, 0, 4, 0)
    ).is_equal_to(0)

    # A zero key in the middle node ends a terminated walk before
    # the tail -- and is itself findable.
    machine.memory.write_byte(TABLE + 0x20, 0)

    assert_that(
        search.linked_search(
            machine.memory, 0x33, 1, TABLE, 0, 4, search.ZERO_KEY_TERMINATES
        )
    ).is_equal_to(0)
    assert_that(
        search.linked_search(
            machine.memory, 0x00, 1, TABLE, 0, 4, search.ZERO_KEY_TERMINATES
        )
    ).is_equal_to(TABLE + 0x20)


# The three opcodes reach their functions through the dispatch
# table, operands in spec order, the answer stored.
def test_the_search_opcodes_dispatch(image: Callable[..., bytes]) -> None:
    machine = booted(image)

    for index, key in enumerate((0x10, 0x20, 0x30)):
        machine.memory.write_run(TABLE + 2 * index, bytes([key, 0]))

    linear = (
        bytes([0x81, 0x50, 0x11, 0x12, 0x11, 0x71])
        + bytes([0x20, 0x01])
        + TABLE.to_bytes(2, "big")
        + bytes([0x02, 0x03, 0x00, 0x00])
        + RESULT.to_bytes(4, "big")
    )
    binary = (
        bytes([0x81, 0x51, 0x11, 0x12, 0x11, 0x71])
        + bytes([0x30, 0x01])
        + TABLE.to_bytes(2, "big")
        + bytes([0x02, 0x03, 0x00, 0x04])
        + (RESULT + 4).to_bytes(4, "big")
    )

    # The linked chain: one node whose key is the target.
    machine.memory.write_byte(TABLE + 0x10, 0x77)
    machine.memory.write_word(TABLE + 0x14, 0)

    linked = (
        bytes([0x81, 0x52, 0x11, 0x12, 0x11, 0x07])
        + bytes([0x77, 0x01])
        + (TABLE + 0x10).to_bytes(2, "big")
        + bytes([0x00, 0x04, 0x00])
        + (RESULT + 8).to_bytes(4, "big")
    )

    machine.memory.write_run(PLANT, linear + binary + linked + bytes([0x81, 0x20]))

    machine.pc = PLANT

    machine.run(limit=10)

    assert_that(machine.memory.read_word(RESULT)).is_equal_to(TABLE + 2)
    assert_that(machine.memory.read_word(RESULT + 4)).is_equal_to(2)
    assert_that(machine.memory.read_word(RESULT + 8)).is_equal_to(TABLE + 0x10)
