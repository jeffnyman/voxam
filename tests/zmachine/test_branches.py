from collections.abc import Callable

import pytest
from assertpy import assert_that

from voxam.errors import ZMachineInstructionError
from voxam.zmachine.machine import Machine
from voxam.zmachine.story import Story

RESULT_VARIABLE = 0x10
RESULT_ADDRESS = 0x100
COUNTER_VARIABLE = 0x11
COUNTER_ADDRESS = 0x102

NOT_TAKEN = 1
TAKEN = 2

# Two arms follow every test instruction: fall through and you store 1
# then quit; branch and you land past that, store 2, and quit. The arm
# is four bytes, so the skipping offset is 4 + 2 = 6 (§4.7.2).
ARMS = bytes(
    [0x0D, RESULT_VARIABLE, NOT_TAKEN, 0xBA, 0x0D, RESULT_VARIABLE, TAKEN, 0xBA]
)
SKIP = 6


def branch_program(test_bytes: bytes, on_true: bool = True) -> bytes:
    sense = 0xC0 if on_true else 0x40

    return test_bytes + bytes([sense | SKIP]) + ARMS


def with_routine(main: bytes, routine: bytes) -> bytes:
    code = bytearray(0x20)
    code[: len(main)] = main

    return bytes(code) + routine


def outcome(machine: Machine) -> int:
    machine.run()

    return machine.memory.read_word(RESULT_ADDRESS)


@pytest.mark.parametrize(
    ("left", "right", "expected"), [(5, 5, TAKEN), (5, 6, NOT_TAKEN)]
)
def test_je_branches_on_equality(
    left: int, right: int, expected: int, code_machine: Callable[..., Machine]
) -> None:
    machine = code_machine(branch_program(bytes([0x01, left, right])))

    assert_that(outcome(machine)).is_equal_to(expected)


# je matches its first operand against any of the others (§15): the
# third operand matches here even though the second does not.
def test_je_matches_any_later_operand(code_machine: Callable[..., Machine]) -> None:
    machine = code_machine(branch_program(bytes([0xC1, 0x57, 5, 3, 5])))

    assert_that(outcome(machine)).is_equal_to(TAKEN)


def test_je_needs_at_least_two_operands(code_machine: Callable[..., Machine]) -> None:
    machine = code_machine(branch_program(bytes([0xC1, 0x7F, 5])))

    with pytest.raises(ZMachineInstructionError, match="needs at least two"):
        machine.run()


# Comparison is signed (§2.2.1): -1 is less than 1, where an unsigned
# comparison would call 0xFFFF the greater.
@pytest.mark.parametrize(
    ("opcode_byte", "left", "right", "expected"),
    [
        (0xC2, 0xFFFF, 0x0001, TAKEN),
        (0xC2, 0x0001, 0xFFFF, NOT_TAKEN),
        (0xC3, 0x0001, 0xFFFF, TAKEN),
        (0xC3, 0xFFFF, 0x0001, NOT_TAKEN),
    ],
)
def test_jl_and_jg_compare_signed(
    opcode_byte: int,
    left: int,
    right: int,
    expected: int,
    code_machine: Callable[..., Machine],
) -> None:
    test_bytes = bytes(
        [opcode_byte, 0x0F, *left.to_bytes(2, "big"), *right.to_bytes(2, "big")]
    )
    machine = code_machine(branch_program(test_bytes))

    assert_that(outcome(machine)).is_equal_to(expected)


@pytest.mark.parametrize(("value", "expected"), [(0, TAKEN), (5, NOT_TAKEN)])
def test_jz_branches_on_zero(
    value: int, expected: int, code_machine: Callable[..., Machine]
) -> None:
    machine = code_machine(branch_program(bytes([0x90, value])))

    assert_that(outcome(machine)).is_equal_to(expected)


# With bit 7 clear the branch applies when the condition is false
# (§4.7): jz on a nonzero value then takes the branch.
def test_branches_can_apply_on_false(code_machine: Callable[..., Machine]) -> None:
    machine = code_machine(branch_program(bytes([0x90, 5]), on_true=False))

    assert_that(outcome(machine)).is_equal_to(TAKEN)


# The same skip encoded as a two-byte branch: sense bit set, bit 6
# clear, offset in the remaining fourteen bits (§4.7).
def test_long_branch_data_executes_too(code_machine: Callable[..., Machine]) -> None:
    machine = code_machine(bytes([0x90, 0x00, 0x80, SKIP]) + ARMS)

    assert_that(outcome(machine)).is_equal_to(TAKEN)


# Branch offsets 0 and 1 return false and true from the current
# routine rather than jumping (§4.7.1).
@pytest.mark.parametrize(("branch_byte", "expected"), [(0xC0, 0), (0xC1, 1)])
def test_sentinel_offsets_return_from_the_routine(
    branch_byte: int, expected: int, code_machine: Callable[..., Machine]
) -> None:
    main = bytes([0xE0, 0x3F, 0x00, 0x30, RESULT_VARIABLE, 0xBA])
    routine = bytes([0x00, 0x90, 0x00, branch_byte])
    machine = code_machine(with_routine(main, routine))
    machine.memory.write_word(RESULT_ADDRESS, 0xFFFF)

    assert_that(outcome(machine)).is_equal_to(expected)


@pytest.mark.parametrize(("flags", "expected"), [(0x0C, TAKEN), (0x0D, NOT_TAKEN)])
def test_test_wants_every_flag_set(
    flags: int, expected: int, code_machine: Callable[..., Machine]
) -> None:
    machine = code_machine(branch_program(bytes([0x07, 0xCC, flags])))

    assert_that(outcome(machine)).is_equal_to(expected)


# A forward jump over the first arm, then a backward jump from the
# far end into it: both directions of §15's signed offset arithmetic
# have to be right for the result to appear.
def test_jump_moves_both_directions(code_machine: Callable[..., Machine]) -> None:
    program = bytes(
        [
            0x8C,
            0x00,
            0x07,  # jump forward to $48
            0x0D,
            RESULT_VARIABLE,
            TAKEN,  # the destination of the jump back
            0xBA,
            0x00,  # never executed
            0x8C,
            0xFF,
            0xFA,  # at $48: jump back to $43
        ]
    )
    machine = code_machine(program)

    assert_that(outcome(machine)).is_equal_to(TAKEN)


# inc_chk steps the referenced variable first, then compares signed
# (§15): from 5, incrementing always leaves 6 in the counter, and the
# branch depends on what 6 is measured against.
@pytest.mark.parametrize(("comparison", "expected"), [(5, TAKEN), (10, NOT_TAKEN)])
def test_inc_chk_steps_then_compares(
    comparison: int, expected: int, code_machine: Callable[..., Machine]
) -> None:
    machine = code_machine(branch_program(bytes([0x05, COUNTER_VARIABLE, comparison])))
    machine.memory.write_word(COUNTER_ADDRESS, 5)

    assert_that(outcome(machine)).is_equal_to(expected)
    assert_that(machine.memory.read_word(COUNTER_ADDRESS)).is_equal_to(6)


def test_dec_chk_steps_then_compares(code_machine: Callable[..., Machine]) -> None:
    machine = code_machine(branch_program(bytes([0x04, COUNTER_VARIABLE, 5])))
    machine.memory.write_word(COUNTER_ADDRESS, 5)

    assert_that(outcome(machine)).is_equal_to(TAKEN)
    assert_that(machine.memory.read_word(COUNTER_ADDRESS)).is_equal_to(4)


# Bitwise operations are unsigned (§2.2.1).
def test_and_or_and_not(code_machine: Callable[..., Machine]) -> None:
    machine = code_machine(bytes([0x09, 0x0C, 0x0A, RESULT_VARIABLE, 0xBA]))

    assert_that(outcome(machine)).is_equal_to(0x08)

    machine = code_machine(bytes([0x08, 0x0C, 0x0A, RESULT_VARIABLE, 0xBA]))

    assert_that(outcome(machine)).is_equal_to(0x0E)

    machine = code_machine(bytes([0x9F, 0x0F, RESULT_VARIABLE, 0xBA]))

    assert_that(outcome(machine)).is_equal_to(0xFFF0)


# From Version 5, not lives in the VAR table instead (§14); the same
# handler serves both homes.
def test_not_from_the_var_table(code_machine: Callable[..., Machine]) -> None:
    machine = code_machine(bytes([0xF8, 0x7F, 0x0F, RESULT_VARIABLE, 0xBA]), version=5)

    assert_that(outcome(machine)).is_equal_to(0xFFF0)


# check_arg_count branches if the numbered argument was supplied
# (§6.4.4.1): the routine returns true when it got two arguments.
@pytest.mark.parametrize(
    ("main", "expected"),
    [
        (bytes([0xE0, 0x17, 0x00, 0x18, 7, 8, RESULT_VARIABLE, 0xBA]), 1),
        (bytes([0xE0, 0x1F, 0x00, 0x18, 7, RESULT_VARIABLE, 0xBA]), 0),
    ],
)
def test_check_arg_count_sees_what_was_supplied(
    main: bytes, expected: int, code_machine: Callable[..., Machine]
) -> None:
    routine = bytes([0x03, 0xFF, 0x7F, 0x02, 0xC1, 0xB1])
    machine = code_machine(with_routine(main, routine), version=5)
    machine.memory.write_word(RESULT_ADDRESS, 0xFFFF)

    assert_that(outcome(machine)).is_equal_to(expected)


# The synthetic image declares a zero file length, so the computed and
# stored checksums are both zero and verification succeeds (§15).
def test_verify_branches_on_a_good_checksum(
    code_machine: Callable[..., Machine],
) -> None:
    machine = code_machine(branch_program(bytes([0xBD])))

    assert_that(outcome(machine)).is_equal_to(TAKEN)


# A story whose header stores a checksum its bytes cannot produce: the
# verification reads the pristine story, and fails (§15).
def test_verify_refuses_a_bad_checksum() -> None:
    data = bytearray(512)
    data[0] = 3
    data[0x04:0x06] = (0x01C0).to_bytes(2, "big")
    data[0x06:0x08] = (0x0040).to_bytes(2, "big")
    data[0x0C:0x0E] = (0x0100).to_bytes(2, "big")
    data[0x0E:0x10] = (0x01C0).to_bytes(2, "big")
    data[0x1C:0x1E] = (0x1234).to_bytes(2, "big")
    program = branch_program(bytes([0xBD]))
    data[0x40 : 0x40 + len(program)] = program
    machine = Machine(Story(bytes(data)))

    assert_that(outcome(machine)).is_equal_to(NOT_TAKEN)


# §15 asks interpreters to be gullible: piracy always branches.
def test_piracy_is_gullible(code_machine: Callable[..., Machine]) -> None:
    machine = code_machine(branch_program(bytes([0xBF])), version=5)

    assert_that(outcome(machine)).is_equal_to(TAKEN)
