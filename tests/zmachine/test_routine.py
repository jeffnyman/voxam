from collections.abc import Callable

import pytest
from assertpy import assert_that

from voxam.errors import ZMachineRoutineError
from voxam.zmachine.instruction import Instruction
from voxam.zmachine.memory import Memory
from voxam.zmachine.packed import routine_address
from voxam.zmachine.routine import Routine
from voxam.zmachine.story import Story

CODE = 0x40


# Two locals with initial values 0x1234 and 0x0AB0 follow the
# count byte as words (§5.2.1); execution begins after them (§5.3).
def test_parses_initial_locals_through_version_4(
    code_memory: Callable[..., Memory],
) -> None:
    memory = code_memory(bytes([2, 0x12, 0x34, 0x0A, 0xB0]), version=3)
    routine = Routine.parse(memory, CODE)

    assert_that(routine.address).is_equal_to(CODE)
    assert_that(routine.initial_locals).is_equal_to((0x1234, 0x0AB0))
    assert_that(routine.first_instruction).is_equal_to(CODE + 5)


# From Version 5 the header is just the count byte, and every
# initial value is zero (§5.2.1).
def test_locals_start_at_zero_from_version_5(
    code_memory: Callable[..., Memory],
) -> None:
    memory = code_memory(bytes([3]), version=5)
    routine = Routine.parse(memory, CODE)

    assert_that(routine.initial_locals).is_equal_to((0, 0, 0))
    assert_that(routine.first_instruction).is_equal_to(CODE + 1)


def test_a_routine_may_have_no_locals(code_memory: Callable[..., Memory]) -> None:
    memory = code_memory(bytes([0]), version=3)
    routine = Routine.parse(memory, CODE)

    assert_that(routine.initial_locals).is_empty()
    assert_that(routine.first_instruction).is_equal_to(CODE + 1)


# 15 locals is legal (§5.2); 16 means the address is likely not a
# routine at all.
def test_fifteen_locals_is_the_maximum(code_memory: Callable[..., Memory]) -> None:
    memory = code_memory(bytes([15]), version=5)

    assert_that(Routine.parse(memory, CODE).initial_locals).is_length(15)

    memory = code_memory(bytes([16]), version=5)

    with pytest.raises(ZMachineRoutineError, match="at most 15"):
        Routine.parse(memory, CODE)


# Following each fixture's first call: unpack its operand (§1.2.3),
# parse the routine it names (§5.2), and decode from its first
# instruction (§5.3). The main routine prints via a packed string
# address and quits.
@pytest.mark.parametrize("version", [1, 2, 3, 4, 5, 7, 8])
def test_follows_the_first_call_into_a_real_routine(
    version: int, load_fixture: Callable[[int], Story]
) -> None:
    memory = Memory(load_fixture(version))
    call = Instruction.decode(memory, memory.header.initial_program_counter)

    address = routine_address(memory.header, call.operands[0].value)
    routine = Routine.parse(memory, address)

    assert_that(routine.initial_locals).is_empty()

    first = Instruction.decode(memory, routine.first_instruction)
    second = Instruction.decode(memory, first.next_address)

    assert_that(first.opcode.name).is_equal_to("print_paddr")
    assert_that(second.opcode.name).is_equal_to("quit")


# Version 6 starts by calling a main routine whose packed address
# sits at $06 (§5.4), unpacked with the routines offset (§1.2.3).
def test_follows_the_version_6_main_routine(
    load_fixture: Callable[[int], Story],
) -> None:
    memory = Memory(load_fixture(6))
    address = routine_address(memory.header, memory.header.main_routine_packed_address)
    routine = Routine.parse(memory, address)
    first = Instruction.decode(memory, routine.first_instruction)

    assert_that(routine.initial_locals).is_empty()
    assert_that(first.opcode.name).is_equal_to("call_vs")
