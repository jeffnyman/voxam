from collections.abc import Callable

import pytest
from assertpy import assert_that

from voxam.errors import ZMachineInstructionError, ZMachineUnimplementedError
from voxam.zmachine.machine import Machine

TABLE = 0x120
SECOND_TABLE = 0x140

# 'h' and 'i' in one terminated word (§3.5.3), printed as a literal.
PRINT_HI = bytes([0xB2, 0xB5, 0xC5])
NEW_LINE = bytes([0xBB])
QUIT = bytes([0xBA])

SELECT_TABLE = bytes([0xF3, 0x4F, 0x03, 0x01, 0x20])
SELECT_SECOND = bytes([0xF3, 0x4F, 0x03, 0x01, 0x40])
DESELECT = bytes([0xF3, 0x3F, 0xFF, 0xFD])
SCREEN_OFF = bytes([0xF3, 0x3F, 0xFF, 0xFF])
SCREEN_ON = bytes([0xF3, 0x7F, 0x01])


def run(code_machine: Callable[..., Machine], program: bytes) -> tuple[Machine, str]:
    output: list[str] = []
    machine = code_machine(program, version=4, output=output.append)

    machine.run()

    return machine, "".join(output)


# Stream 3 swallows everything: the table gets a count word and the
# ZSCII characters from its third byte, and the screen hears nothing
# at all while it is on (§7.1.2.1, §7.1.2.2).
def test_memory_redirection_captures_text(
    code_machine: Callable[..., Machine],
) -> None:
    machine, screen = run(
        code_machine, SELECT_TABLE + PRINT_HI + DESELECT + PRINT_HI + QUIT
    )

    assert_that(machine.memory.read_word(TABLE)).is_equal_to(2)
    assert_that(machine.memory.read_byte(TABLE + 2)).is_equal_to(ord("h"))
    assert_that(machine.memory.read_byte(TABLE + 3)).is_equal_to(ord("i"))
    assert_that(screen).is_equal_to("hi")


# New-lines are written to the table as ZSCII 13 (§7.1.2.2.1).
def test_redirected_newlines_become_zscii_13(
    code_machine: Callable[..., Machine],
) -> None:
    machine, _ = run(code_machine, SELECT_TABLE + NEW_LINE + DESELECT + QUIT)

    assert_that(machine.memory.read_word(TABLE)).is_equal_to(1)
    assert_that(machine.memory.read_byte(TABLE + 2)).is_equal_to(13)


# Nested redirections stack: text goes only into the newest table,
# and each deselection closes one (§7.1.2.1, §7.1.2.2).
def test_redirections_nest(code_machine: Callable[..., Machine]) -> None:
    machine, _ = run(
        code_machine,
        SELECT_TABLE + PRINT_HI + SELECT_SECOND + PRINT_HI + DESELECT + DESELECT + QUIT,
    )

    assert_that(machine.memory.read_word(TABLE)).is_equal_to(2)
    assert_that(machine.memory.read_word(SECOND_TABLE)).is_equal_to(2)


# Deselecting the screen sends text nowhere, exactly as asked (§7.1).
def test_the_screen_stream_can_be_turned_off(
    code_machine: Callable[..., Machine],
) -> None:
    _, screen = run(code_machine, SCREEN_OFF + PRINT_HI + SCREEN_ON + PRINT_HI + QUIT)

    assert_that(screen).is_equal_to("hi")


# Stream 0 has no effect (§15 output_stream).
def test_stream_zero_does_nothing(code_machine: Callable[..., Machine]) -> None:
    _, screen = run(code_machine, bytes([0xF3, 0x7F, 0x00]) + PRINT_HI + QUIT)

    assert_that(screen).is_equal_to("hi")


# A seventeenth nested redirection is a fault the interpreter must
# halt on (§7.1.2.1.1).
def test_a_seventeenth_redirection_halts(
    code_machine: Callable[..., Machine],
) -> None:
    machine = code_machine(SELECT_TABLE * 17 + QUIT, version=4)

    with pytest.raises(ZMachineInstructionError, match="16 at most"):
        machine.run()


def test_deselecting_an_unselected_stream_3_halts(
    code_machine: Callable[..., Machine],
) -> None:
    machine = code_machine(DESELECT + QUIT, version=4)

    with pytest.raises(ZMachineInstructionError, match="not selected"):
        machine.run()


def test_stream_3_needs_a_table(code_machine: Callable[..., Machine]) -> None:
    machine = code_machine(bytes([0xF3, 0x7F, 0x03]) + QUIT, version=4)

    with pytest.raises(ZMachineInstructionError, match="no table"):
        machine.run()


def test_undefined_streams_halt(code_machine: Callable[..., Machine]) -> None:
    machine = code_machine(bytes([0xF3, 0x7F, 0x05]) + QUIT, version=4)

    with pytest.raises(ZMachineInstructionError, match="only 1 to 4"):
        machine.run()


# The transcript and command-record streams await files to write to.
def test_transcript_streams_are_a_reported_frontier(
    code_machine: Callable[..., Machine],
) -> None:
    machine = code_machine(bytes([0xF3, 0x7F, 0x02]) + QUIT, version=4)

    with pytest.raises(ZMachineUnimplementedError, match="output stream 2"):
        machine.run()
