"""Accelerated functions: the Inform veneer, replaced (Glulx:
Accelerated Functions).
"""

from collections.abc import Callable

import pytest
from assertpy import assert_that

from voxam.glulx.machine import Machine
from voxam.glulx.story import Story

# An idle main, three pad bytes, then a lone 0x70 byte at $50 --
# an object type byte in ROM, which Z__Region must refuse.
IDLE = bytes([0xC0, 0x00, 0x00, 0x81, 0x20])
CODE = IDLE + bytes(3) + b"\x70"

PLANT = 0x180
RESULT = 0x140

# The miniature Inform world, laid out in RAM.
SELF_GLOBAL = 0x110
CPV_START = 0x120
CLASSES_TABLE = 0x140
K = 0x160
K2 = 0x190
OBJ = 0x1B0
CLASS_MC = 0x1E0
O_PTABLE = 0x200
K_PTABLE = 0x228
INLIST = 0x250
VAL3 = 0x258
VAL5 = 0x260
KVAL3 = 0x270
KVAL42 = 0x278
STRINGISH = 0x290
FUNC = 0x2C8

OBJ_MC = 0x0111
ROUT_MC = 0x0222
STR_MC = 0x0333
INDIV = 0x40


def entry(prop_id: int, length: int, address: int, *, protected: bool = False) -> bytes:
    flags = b"\x00\x01" if protected else b"\x00\x00"

    return (
        prop_id.to_bytes(2, "big")
        + length.to_bytes(2, "big")
        + address.to_bytes(4, "big")
        + flags
    )


def world(image: Callable[..., bytes]) -> Machine:
    """A machine holding a two-class, one-object Inform world."""

    machine = Machine(Story(image(code=CODE)))
    memory = machine.memory

    for address, type_byte, table, metaclass in (
        (K, 0x70, K_PTABLE, CLASS_MC),
        (K2, 0x70, 0, CLASS_MC),
        (OBJ, 0x71, O_PTABLE, 0),
        (CLASS_MC, 0x70, 0, CLASS_MC),
    ):
        memory.write_byte(address, type_byte)
        memory.write_word(address + 16, table)
        memory.write_word(address + 20, metaclass)

    memory.write_word(CLASSES_TABLE + 4, K)

    memory.write_word(O_PTABLE, 3)
    memory.write_run(
        O_PTABLE + 4,
        entry(2, 1, INLIST) + entry(3, 2, VAL3) + entry(5, 1, VAL5, protected=True),
    )

    memory.write_word(K_PTABLE, 2)
    memory.write_run(K_PTABLE + 4, entry(3, 1, KVAL3) + entry(INDIV + 2, 1, KVAL42))

    memory.write_word(INLIST, K)
    memory.write_word(VAL3, 0x1111)
    memory.write_word(VAL3 + 4, 0x2222)
    memory.write_word(VAL5, 0x5555)
    memory.write_word(KVAL3, 0x3333)
    memory.write_word(KVAL42, 0x4242)
    memory.write_byte(STRINGISH, 0xE0)
    memory.write_run(FUNC, bytes([0xC1, 0x00, 0x00, 0x31, 0x01, 0x2A]))
    memory.write_word(CPV_START + 4 * 4, 0xD4D4)

    for index, value in enumerate(
        (
            CLASSES_TABLE,
            INDIV,
            CLASS_MC,
            OBJ_MC,
            ROUT_MC,
            STR_MC,
            SELF_GLOBAL,
            7,
            CPV_START,
        )
    ):
        machine.accel.set_param(index, value)

    return machine


# Z__Region sorts every address: the header and beyond-memory are
# nothing, E0 is a string, C0 a routine, and 0x70 an object -- but
# only in RAM, where the header's own RAMSTART word draws the line.
def test_z_region_sorts_addresses(image: Callable[..., bytes]) -> None:
    accel = world(image).accel

    answers = {
        35: 0,
        0x300: 0,
        STRINGISH: 3,
        0x48: 2,
        OBJ: 1,
        K: 1,
        0x50: 0,
        SELF_GLOBAL: 0,
    }

    for address, expected in answers.items():
        assert_that(accel.func_1_z_region([address])).is_equal_to(expected)

    # A missing argument reads as zero, like an unfilled local.
    assert_that(accel.func_1_z_region([])).is_equal_to(0)


# CP__Tab finds a property entry by binary search -- or answers 0
# for a non-object, an object with no table, or an absent id. The
# old and new forms agree at the default attribute width.
def test_property_entries_are_found(image: Callable[..., bytes]) -> None:
    accel = world(image).accel
    third = O_PTABLE + 4 + 10

    assert_that(accel.func_2_cp_tab([OBJ, 3])).is_equal_to(third)
    assert_that(accel.func_8_cp_tab([OBJ, 3])).is_equal_to(third)
    assert_that(accel.func_2_cp_tab([OBJ, 4])).is_equal_to(0)
    assert_that(accel.func_2_cp_tab([STRINGISH, 3])).is_equal_to(0)
    assert_that(accel.func_2_cp_tab([CLASS_MC, 3])).is_equal_to(0)


# RA__Pr and RL__Pr answer a property's data address and byte
# length; a protected property is invisible until the global self
# is the object itself, and a class hides all but its individual
# properties.
def test_addresses_lengths_and_protection(
    image: Callable[..., bytes],
) -> None:
    machine = world(image)
    accel = machine.accel

    assert_that(accel.func_3_ra_pr([OBJ, 3])).is_equal_to(VAL3)
    assert_that(accel.func_9_ra_pr([OBJ, 3])).is_equal_to(VAL3)
    assert_that(accel.func_4_rl_pr([OBJ, 3])).is_equal_to(8)
    assert_that(accel.func_10_rl_pr([OBJ, 3])).is_equal_to(8)
    assert_that(accel.func_3_ra_pr([OBJ, 4])).is_equal_to(0)
    assert_that(accel.func_4_rl_pr([OBJ, 4])).is_equal_to(0)

    assert_that(accel.func_3_ra_pr([OBJ, 5])).is_equal_to(0)

    machine.memory.write_word(SELF_GLOBAL, OBJ)

    assert_that(accel.func_3_ra_pr([OBJ, 5])).is_equal_to(VAL5)

    # K is a class: its common property is hidden, its individual
    # one is not.
    assert_that(accel.func_3_ra_pr([K, 3])).is_equal_to(0)
    assert_that(accel.func_3_ra_pr([K, INDIV + 2])).is_equal_to(KVAL42)


# OC__Cl is ofclass, region by region: strings and routines match
# only their metaclasses, Class holds the classes and the
# metaclasses, Object holds the plain objects, and real membership
# walks the inheritance list.
def test_ofclass_walks_every_region(image: Callable[..., bytes]) -> None:
    accel = world(image).accel

    answers = [
        ([STRINGISH, STR_MC], 1),
        ([STRINGISH, K], 0),
        ([0x48, ROUT_MC], 1),
        ([0x48, K], 0),
        ([35, K], 0),
        ([K, CLASS_MC], 1),
        ([CLASS_MC, CLASS_MC], 1),
        ([OBJ, CLASS_MC], 0),
        ([OBJ, OBJ_MC], 1),
        ([K, OBJ_MC], 0),
        ([OBJ, STR_MC], 0),
        ([OBJ, OBJ], 0),
        ([OBJ, K], 1),
        ([OBJ, K2], 0),
        ([K, K], 0),
    ]

    for args, expected in answers:
        assert_that(accel.func_5_oc_cl(args)).described_as(str(args)).is_equal_to(
            expected
        )
        assert_that(accel.func_11_oc_cl(args)).is_equal_to(expected)


# RV__Pr reads a value, or the common default for a missing common
# property; a missing individual property -- and property zero --
# read as zero.
def test_values_fall_back_to_defaults(image: Callable[..., bytes]) -> None:
    accel = world(image).accel

    assert_that(accel.func_6_rv_pr([OBJ, 3])).is_equal_to(0x1111)
    assert_that(accel.func_12_rv_pr([OBJ, 3])).is_equal_to(0x1111)
    assert_that(accel.func_6_rv_pr([OBJ, 4])).is_equal_to(0xD4D4)
    assert_that(accel.func_6_rv_pr([OBJ, INDIV + 5])).is_equal_to(0)
    assert_that(accel.func_6_rv_pr([OBJ, 0])).is_equal_to(0)


# OP__Pr is provides: strings offer print and print_to_array,
# routines offer call, classes offer the individual range, and an
# object offers what its table holds.
def test_provides_answers_by_region(image: Callable[..., bytes]) -> None:
    accel = world(image).accel

    answers = [
        ([STRINGISH, INDIV + 6], 1),
        ([STRINGISH, INDIV + 7], 1),
        ([STRINGISH, INDIV + 5], 0),
        ([0x48, INDIV + 5], 1),
        ([0x48, INDIV + 6], 0),
        ([35, 3], 0),
        ([K, INDIV + 4], 1),
        ([OBJ, 3], 1),
        ([OBJ, 4], 0),
        ([OBJ, INDIV + 4], 0),
    ]

    for args, expected in answers:
        assert_that(accel.func_7_op_pr(args)).described_as(str(args)).is_equal_to(
            expected
        )
        assert_that(accel.func_13_op_pr(args)).is_equal_to(expected)


# A composite property id names a class by table index in its low
# half and the property in its high half -- resolved only when the
# object really is of that class.
def test_composite_ids_reach_the_class(image: Callable[..., bytes]) -> None:
    accel = world(image).accel
    composite = (3 << 16) | 1

    assert_that(accel.func_3_ra_pr([OBJ, composite])).is_equal_to(KVAL3)
    assert_that(accel.func_3_ra_pr([STRINGISH, composite])).is_equal_to(0)


# The table's own bookkeeping: what is available, what installing
# and cancelling do, and how unknown numbers are shrugged off.
def test_the_accelerator_bookkeeping(image: Callable[..., bytes]) -> None:
    machine = world(image)
    accel = machine.accel

    assert_that(accel.available).is_equal_to(frozenset(range(1, 14)))
    assert_that(accel.lookup(FUNC)).is_none()

    accel.set_func(99, FUNC)

    assert_that(accel.lookup(FUNC)).is_none()

    accel.set_func(1, FUNC)

    replacement = accel.lookup(FUNC)

    if replacement is None:
        pytest.fail("the replacement is installed")

    assert_that(replacement([OBJ])).is_equal_to(1)

    accel.set_func(0, FUNC)

    assert_that(accel.lookup(FUNC)).is_none()

    accel.set_param(99, 5)
    accel.set_param(6, (1 << 33) + 5)

    assert_that(accel.params[6]).is_equal_to(5)
    assert_that(accel.params).does_not_contain_key(99)


# The machine intercepts: once accelfunc installs a replacement, a
# call to that address answers immediately -- the function body is
# never entered -- and cancelling brings the real body back.
def test_calls_are_intercepted(image: Callable[..., bytes]) -> None:
    machine = world(image)

    machine.stack.push(OBJ)
    machine.stack.push(OBJ)

    plant = (
        bytes([0x81, 0x81, 0x11, 0x07, 0x07])
        + bytes([0x81, 0x80, 0x21, 0x01])
        + FUNC.to_bytes(2, "big")
        + bytes([0x30, 0x12, 0x07])
        + FUNC.to_bytes(2, "big")
        + bytes([0x01])
        + RESULT.to_bytes(4, "big")
        + bytes([0x81, 0x80, 0x21, 0x00])
        + FUNC.to_bytes(2, "big")
        + bytes([0x30, 0x12, 0x07])
        + FUNC.to_bytes(2, "big")
        + bytes([0x01])
        + (RESULT + 4).to_bytes(4, "big")
        + bytes([0x81, 0x20])
    )

    machine.memory.write_run(PLANT, plant)

    machine.pc = PLANT

    machine.run(limit=20)

    assert_that(machine.accel.params[7]).is_equal_to(7)
    assert_that(machine.memory.read_word(RESULT)).is_equal_to(1)
    assert_that(machine.memory.read_word(RESULT + 4)).is_equal_to(0x2A)
