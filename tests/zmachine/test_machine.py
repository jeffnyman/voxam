from collections.abc import Callable

import pytest
from assertpy import assert_that

from voxam.errors import ZMachineUnimplementedError
from voxam.zmachine.machine import Machine
from voxam.zmachine.story import Story

CODE = 0x40

# Synthetic programs place a first routine at $60 and a second at $70;
# under Version 3's scale factor of 2, those are packed 0x30 and 0x38.
ROUTINE_A_PACKED = bytes([0x00, 0x30])
ROUTINE_B_PACKED = bytes([0x00, 0x38])

# The result global: variable $10, first entry of the table at $100.
RESULT_VARIABLE = 0x10
RESULT_ADDRESS = 0x100


def layout(main: bytes, routine_a: bytes = b"", routine_b: bytes = b"") -> bytes:
    code = bytearray(0x40)
    code[: len(main)] = main
    code[0x20 : 0x20 + len(routine_a)] = routine_a
    code[0x30 : 0x30 + len(routine_b)] = routine_b

    return bytes(code)


def test_quit_halts_the_machine(code_machine: Callable[..., Machine]) -> None:
    machine = code_machine(layout(bytes([0xBA])))

    assert_that(machine.running).is_true()

    machine.run()

    assert_that(machine.running).is_false()


# The whole call contract of §6.4: enter the routine, run it, return
# its value into the caller's chosen variable, resume after the call.
def test_a_call_delivers_the_routines_result(
    code_machine: Callable[..., Machine],
) -> None:
    main = bytes([0xE0, 0x3F, *ROUTINE_A_PACKED, RESULT_VARIABLE, 0xBA])
    returns_42 = bytes([0x00, 0x9B, 0x2A])
    machine = code_machine(layout(main, returns_42))

    machine.run()

    assert_that(machine.memory.read_word(RESULT_ADDRESS)).is_equal_to(42)


# One argument, two locals: the argument lands in local 1 (§6.4.4)
# while local 2 keeps its header default (§6.4.4.1) -- verified by
# returning each local in turn.
@pytest.mark.parametrize(("local", "expected"), [(0x01, 99), (0x02, 7)])
def test_arguments_arrive_and_defaults_survive(
    local: int, expected: int, code_machine: Callable[..., Machine]
) -> None:
    main = bytes([0xE0, 0x1F, *ROUTINE_A_PACKED, 99, RESULT_VARIABLE, 0xBA])
    returns_local = bytes([0x02, 0x00, 0x05, 0x00, 0x07, 0xAB, local])
    machine = code_machine(layout(main, returns_local))

    machine.run()

    assert_that(machine.memory.read_word(RESULT_ADDRESS)).is_equal_to(expected)


# A call to packed address 0 does nothing and returns false (§6.4.3).
def test_calling_address_0_returns_false(
    code_machine: Callable[..., Machine],
) -> None:
    main = bytes([0xE0, 0x3F, 0x00, 0x00, RESULT_VARIABLE, 0xBA])
    machine = code_machine(layout(main))
    machine.memory.write_word(RESULT_ADDRESS, 0xFFFF)

    machine.run()

    assert_that(machine.memory.read_word(RESULT_ADDRESS)).is_equal_to(0)


# rtrue returns 1 and rfalse returns 0 (§6.4.5).
@pytest.mark.parametrize(("opcode_byte", "expected"), [(0xB0, 1), (0xB1, 0)])
def test_rtrue_and_rfalse(
    opcode_byte: int, expected: int, code_machine: Callable[..., Machine]
) -> None:
    main = bytes([0xE0, 0x3F, *ROUTINE_A_PACKED, RESULT_VARIABLE, 0xBA])
    machine = code_machine(layout(main, bytes([0x00, opcode_byte])))
    machine.memory.write_word(RESULT_ADDRESS, 0xFFFF)

    machine.run()

    assert_that(machine.memory.read_word(RESULT_ADDRESS)).is_equal_to(expected)


def test_ret_popped_returns_the_top_of_stack(
    code_machine: Callable[..., Machine],
) -> None:
    main = bytes([0xE0, 0x3F, *ROUTINE_A_PACKED, RESULT_VARIABLE, 0xBA])
    push_then_return = bytes([0x00, 0xE8, 0x7F, 0x2A, 0xB8])
    machine = code_machine(layout(main, push_then_return))

    machine.run()

    assert_that(machine.memory.read_word(RESULT_ADDRESS)).is_equal_to(42)


# Storing a result to variable $00 pushes it onto the caller's stack
# (§6.3): routine A calls B with store variable 0, then ret_popped
# hands B's result onward to the outermost caller.
def test_a_result_stored_to_variable_0_lands_on_the_callers_stack(
    code_machine: Callable[..., Machine],
) -> None:
    main = bytes([0xE0, 0x3F, *ROUTINE_A_PACKED, RESULT_VARIABLE, 0xBA])
    relay = bytes([0x00, 0xE0, 0x3F, *ROUTINE_B_PACKED, 0x00, 0xB8])
    returns_42 = bytes([0x00, 0x9B, 0x2A])
    machine = code_machine(layout(main, relay, returns_42))

    machine.run()

    assert_that(machine.memory.read_word(RESULT_ADDRESS)).is_equal_to(42)


def test_unimplemented_opcodes_report_the_frontier(
    code_machine: Callable[..., Machine],
) -> None:
    machine = code_machine(layout(bytes([0xB2, 0x80, 0x00])))

    with pytest.raises(ZMachineUnimplementedError, match="not yet implemented"):
        machine.run()

    assert_that(machine.running).is_true()


def test_the_frontier_report_names_the_opcode_and_address(
    code_machine: Callable[..., Machine],
) -> None:
    machine = code_machine(layout(bytes([0xB2, 0x80, 0x00])))

    with pytest.raises(ZMachineUnimplementedError) as excinfo:
        machine.run()

    assert_that(excinfo.value.opcode_name).is_equal_to("print")
    assert_that(excinfo.value.address).is_equal_to(CODE)
    assert_that(machine.pc).is_equal_to(CODE)


# call_vn throws the routine's result away (§6.4.1): the machine runs
# to quit and the result global keeps its sentinel. Version 5 scales
# packed addresses by 4, so the routine at $60 is packed 0x18.
def test_call_vn_discards_the_result(code_machine: Callable[..., Machine]) -> None:
    main = bytes([0xF9, 0x3F, 0x00, 0x18, 0xBA])
    machine = code_machine(layout(main, bytes([0x00, 0xB0])), version=5)
    machine.memory.write_word(RESULT_ADDRESS, 0xFFFF)

    machine.run()

    assert_that(machine.memory.read_word(RESULT_ADDRESS)).is_equal_to(0xFFFF)


def test_call_vn_to_address_0_stores_nothing(
    code_machine: Callable[..., Machine],
) -> None:
    main = bytes([0xF9, 0x3F, 0x00, 0x00, 0xBA])
    machine = code_machine(layout(main), version=5)
    machine.memory.write_word(RESULT_ADDRESS, 0xFFFF)

    machine.run()

    assert_that(machine.memory.read_word(RESULT_ADDRESS)).is_equal_to(0xFFFF)


# Every fixture -- Version 6 and its §5.4 main-routine boot included --
# executes its opening call chain for real and halts at the same
# frontier: the print_paddr that will fall in the milestone branch.
@pytest.mark.parametrize("version", range(1, 9))
def test_every_fixture_runs_to_the_print_frontier(
    version: int, load_fixture: Callable[[int], Story]
) -> None:
    machine = Machine(load_fixture(version))

    with pytest.raises(ZMachineUnimplementedError) as excinfo:
        machine.run()

    assert_that(excinfo.value.opcode_name).is_equal_to("print_paddr")
