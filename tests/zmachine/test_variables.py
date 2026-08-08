from collections.abc import Callable

import pytest
from assertpy import assert_that

from voxam.errors import ZMachineStackError
from voxam.zmachine.frames import CallStack
from voxam.zmachine.memory import Memory
from voxam.zmachine.routine import Routine
from voxam.zmachine.variables import Variables

GLOBALS_TABLE = 0x100


def variables_over(memory: Memory) -> tuple[Variables, CallStack]:
    calls = CallStack()

    return Variables(memory, calls), calls


# Writing variable $00 pushes and reading it pulls (§6.3).
def test_variable_0_is_the_stack(code_memory: Callable[..., Memory]) -> None:
    variables, _ = variables_over(code_memory())

    variables.write(0x00, 42)

    assert_that(variables.read(0x00)).is_equal_to(42)

    with pytest.raises(ZMachineStackError, match="empty stack"):
        variables.read(0x00)


# Variables $01 to $0f are the current routine's locals (§4.2.2).
def test_low_numbers_are_locals(code_memory: Callable[..., Memory]) -> None:
    variables, calls = variables_over(code_memory())
    routine = Routine(address=0x200, initial_locals=(7, 8), first_instruction=0x201)
    calls.call(routine, (), return_address=0, store_variable=None)

    assert_that(variables.read(0x02)).is_equal_to(8)

    variables.write(0x01, 0xBEEF)

    assert_that(variables.read(0x01)).is_equal_to(0xBEEF)

    with pytest.raises(ZMachineStackError, match="local 3 does not exist"):
        variables.read(0x03)


# Variables $10 up are words in the globals table, whose address the
# header declares (§6.2); the test image puts that table at $100.
def test_high_numbers_are_globals_in_memory(
    code_memory: Callable[..., Memory],
) -> None:
    memory = code_memory()
    variables, _ = variables_over(memory)

    variables.write(0x10, 0x1234)
    variables.write(0x11, 0x5678)

    assert_that(variables.read(0x10)).is_equal_to(0x1234)
    assert_that(memory.read_word(GLOBALS_TABLE)).is_equal_to(0x1234)
    assert_that(memory.read_word(GLOBALS_TABLE + 2)).is_equal_to(0x5678)


def test_globals_read_what_the_story_shipped(
    code_memory: Callable[..., Memory],
) -> None:
    memory = code_memory()
    memory.write_word(GLOBALS_TABLE + 4, 0xCAFE)
    variables, _ = variables_over(memory)

    assert_that(variables.read(0x12)).is_equal_to(0xCAFE)
