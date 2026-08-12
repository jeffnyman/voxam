from collections.abc import Callable

import pytest
from assertpy import assert_that

from voxam.errors import (
    ZMachineInstructionError,
    ZMachineMemoryError,
    ZMachineUnimplementedError,
)
from voxam.zmachine.machine import Machine
from voxam.zmachine.memory import Memory

TEXT_BUFFER = 0x120
PARSE_BUFFER = 0x140
DICTIONARY_BASE = 0x150

# sread text-buffer parse-buffer, then quit. In Version 5 the same
# bytes decode as the storing aread, growing a store byte.
SREAD = bytes([0xE4, 0x0F, 0x01, 0x20, 0x01, 0x40, 0xBA])
AREAD = bytes([0xE4, 0x0F, 0x01, 0x20, 0x01, 0x40, 0x10, 0xBA])

# Hand-encoded Version 3 entries, sorted: "go" then "hi" (§13.3).
GO = bytes([0x32, 0x85, 0x94, 0xA5])
HI = bytes([0x35, 0xC5, 0x94, 0xA5])

# The same words in Version 5's longer shape: nine z-characters in
# three words (§13.3).
GO5 = bytes([0x32, 0x85, 0x14, 0xA5, 0x94, 0xA5])
HI5 = bytes([0x35, 0xC5, 0x14, 0xA5, 0x94, 0xA5])

GO_ADDRESS = DICTIONARY_BASE + 6
HI_ADDRESS = DICTIONARY_BASE + 6 + 7


def plant_dictionary(memory: Memory, entries: tuple[bytes, ...] = (GO, HI)) -> None:
    memory.write_word(0x08, DICTIONARY_BASE)
    position = DICTIONARY_BASE

    for value in [2, ord(","), ord("."), 7]:
        memory.write_byte(position, value)
        position += 1

    memory.write_word(position, len(entries))
    position += 2

    for entry in entries:
        for offset, value in enumerate(entry):
            memory.write_byte(position + offset, value)

        position += 7


def reader(
    code_machine: Callable[..., Machine],
    line: str,
    version: int = 3,
    program: bytes = SREAD,
) -> Machine:
    machine = code_machine(program, version=version, input_source=lambda: line)
    plant_dictionary(machine.memory)
    machine.memory.write_byte(TEXT_BUFFER, 21)
    machine.memory.write_byte(PARSE_BUFFER, 5)

    return machine


def counted_text(memory: Memory) -> str:
    """Read the Version 5 counted layout: count in byte 1, text from 2."""

    count = memory.read_byte(TEXT_BUFFER + 1)

    return "".join(
        chr(memory.read_byte(TEXT_BUFFER + 2 + offset)) for offset in range(count)
    )


def text_in_buffer(memory: Memory) -> str:
    characters = []
    position = TEXT_BUFFER + 1

    while memory.read_byte(position) != 0:
        characters.append(chr(memory.read_byte(position)))
        position += 1

    return "".join(characters)


def parse_block(memory: Memory, index: int) -> tuple[int, int, int]:
    block = PARSE_BUFFER + 2 + 4 * index

    return (
        memory.read_word(block),
        memory.read_byte(block + 2),
        memory.read_byte(block + 3),
    )


# The typed line is lowercased and stored from byte 1 with a zero
# terminator (§15 read); each parse block holds dictionary address,
# letter count, and the position of the word's first letter (§13.6.3).
def test_sread_fills_both_buffers(code_machine: Callable[..., Machine]) -> None:
    machine = reader(code_machine, "go HI,zebra")

    machine.run()

    assert_that(text_in_buffer(machine.memory)).is_equal_to("go hi,zebra")
    assert_that(machine.memory.read_byte(PARSE_BUFFER + 1)).is_equal_to(4)
    assert_that(parse_block(machine.memory, 0)).is_equal_to((GO_ADDRESS, 2, 1))
    assert_that(parse_block(machine.memory, 1)).is_equal_to((HI_ADDRESS, 2, 4))
    assert_that(parse_block(machine.memory, 2)).is_equal_to((0, 1, 6))
    assert_that(parse_block(machine.memory, 3)).is_equal_to((0, 5, 7))


# Byte 0 of the text buffer holds the string array length n: the
# letters plus the terminator fit within it, so a capacity of 4
# guillotines the typed line (§15 read).
def test_sread_respects_the_buffer_capacity(
    code_machine: Callable[..., Machine],
) -> None:
    machine = reader(code_machine, "mailbox")
    machine.memory.write_byte(TEXT_BUFFER, 5)

    machine.run()

    assert_that(text_in_buffer(machine.memory)).is_equal_to("mail")
    assert_that(machine.memory.read_byte(PARSE_BUFFER + 1)).is_equal_to(1)
    assert_that(parse_block(machine.memory, 0)).is_equal_to((0, 4, 1))


def test_sread_stops_at_the_parse_limit(
    code_machine: Callable[..., Machine],
) -> None:
    machine = reader(code_machine, "go go go")
    machine.memory.write_byte(PARSE_BUFFER, 2)

    machine.run()

    assert_that(machine.memory.read_byte(PARSE_BUFFER + 1)).is_equal_to(2)


# From Version 5, the buffer is counted rather than terminated: the
# typed length lands in byte 1 and the lowercased letters from byte
# 2, with nothing written after them (§15 read).
def test_aread_fills_the_counted_buffer(
    code_machine: Callable[..., Machine],
) -> None:
    machine = reader(code_machine, "go HI", version=5, program=AREAD)
    machine.memory.write_byte(TEXT_BUFFER + 2 + 5, 0xAA)

    machine.run()

    assert_that(machine.memory.read_byte(TEXT_BUFFER + 1)).is_equal_to(5)
    assert_that(counted_text(machine.memory)).is_equal_to("go hi")
    assert_that(machine.memory.read_byte(TEXT_BUFFER + 2 + 5)).is_equal_to(0xAA)


# aread stores its terminating character, and input here always ends
# with the return key: 13, never 10 (§15 read).
def test_aread_stores_the_return_key(code_machine: Callable[..., Machine]) -> None:
    machine = reader(code_machine, "go", version=5, program=AREAD)

    machine.run()

    assert_that(machine.memory.read_word(0x100)).is_equal_to(13)


# From Version 5 the parse positions count from byte 2, where the
# text now starts (§13.6.3, §15 read).
def test_aread_parse_positions_start_at_byte_2(
    code_machine: Callable[..., Machine],
) -> None:
    machine = reader(code_machine, "go hi", version=5, program=AREAD)
    plant_dictionary(machine.memory, entries=(GO5, HI5))

    machine.run()

    assert_that(parse_block(machine.memory, 0)).is_equal_to((GO_ADDRESS, 2, 2))
    assert_that(parse_block(machine.memory, 1)).is_equal_to((HI_ADDRESS, 2, 5))


# A zero parse buffer skips lexing entirely from Version 5 (§15
# read): the text is stored and the parse region is never touched.
def test_aread_with_a_zero_parse_buffer_skips_lexing(
    code_machine: Callable[..., Machine],
) -> None:
    no_parse = bytes([0xE4, 0x0F, 0x01, 0x20, 0x00, 0x00, 0x10, 0xBA])
    machine = reader(code_machine, "go", version=5, program=no_parse)
    machine.memory.write_byte(PARSE_BUFFER + 1, 0xAA)

    machine.run()

    assert_that(counted_text(machine.memory)).is_equal_to("go")
    assert_that(machine.memory.read_byte(PARSE_BUFFER + 1)).is_equal_to(0xAA)


# Byte 0 is the whole capacity in Version 5 -- no terminator to
# reserve room for (§15 read).
def test_aread_respects_the_counted_capacity(
    code_machine: Callable[..., Machine],
) -> None:
    machine = reader(code_machine, "mailbox", version=5, program=AREAD)
    machine.memory.write_byte(TEXT_BUFFER, 4)

    machine.run()

    assert_that(machine.memory.read_byte(TEXT_BUFFER + 1)).is_equal_to(4)
    assert_that(counted_text(machine.memory)).is_equal_to("mail")


# A positive count already in byte 1 means characters left over from
# an interrupted timed read (§15 read) -- machinery Voxam does not
# have, so honoring it would type stale bytes nobody entered.
def test_leftover_input_is_a_reported_frontier(
    code_machine: Callable[..., Machine],
) -> None:
    machine = reader(code_machine, "go", version=5, program=AREAD)
    machine.memory.write_byte(TEXT_BUFFER + 1, 3)

    with pytest.raises(ZMachineUnimplementedError, match="leftover"):
        machine.run()


# §15 asks for a loud halt when a buffer is too small to be real:
# it almost always means a previous array overran it.
def test_a_crushed_text_buffer_halts_loudly(
    code_machine: Callable[..., Machine],
) -> None:
    machine = reader(code_machine, "go")
    machine.memory.write_byte(TEXT_BUFFER, 1)

    with pytest.raises(ZMachineMemoryError, match="claims a capacity"):
        machine.run()


def test_a_crushed_parse_buffer_halts_loudly(
    code_machine: Callable[..., Machine],
) -> None:
    machine = reader(code_machine, "go")
    machine.memory.write_byte(PARSE_BUFFER, 0)

    with pytest.raises(ZMachineMemoryError, match="claims room"):
        machine.run()


# Version 4 may pass a time and routine pair; nonzero values would
# need timed input (§15 read).
def test_timed_reading_is_a_reported_frontier(
    code_machine: Callable[..., Machine],
) -> None:
    timed = bytes([0xE4, 0x05, 0x01, 0x20, 0x01, 0x40, 0x0A, 0x00, 0xBA])
    machine = reader(code_machine, "go", version=4, program=timed)

    with pytest.raises(ZMachineUnimplementedError, match="timed read"):
        machine.run()


# A zero time and routine are the same as their absence.
def test_a_zero_time_is_not_timed(code_machine: Callable[..., Machine]) -> None:
    untimed = bytes([0xE4, 0x05, 0x01, 0x20, 0x01, 0x40, 0x00, 0x00, 0xBA])
    machine = reader(code_machine, "go", version=4, program=untimed)

    machine.run()

    assert_that(text_in_buffer(machine.memory)).is_equal_to("go")


# Under a plain frontend -- which declared no status line -- the
# opcode conformingly redraws nothing (§8.2, §11.1), and it must not
# even assemble a status: these globals point at no object, so an
# assembly attempt would halt on the object lookup.
def test_show_status_stays_quiet_without_a_status_line(
    code_machine: Callable[..., Machine],
) -> None:
    machine = code_machine(bytes([0xBC, 0xBA]))

    machine.run()

    assert_that(machine.running).is_false()


# read_char device 1, storing to G0, then quit.
READ_CHAR = bytes([0xF6, 0x7F, 0x01, 0x10, 0xBA])
RESULT = 0x100


# A keystroke is the first character of the next input line: the
# line-based seam's honest rendering of "press any key" (§15
# read_char).
def test_read_char_stores_the_first_characters_code(
    code_machine: Callable[..., Machine],
) -> None:
    machine = code_machine(READ_CHAR, version=4, input_source=lambda: "y")

    machine.run()

    assert_that(machine.memory.read_word(RESULT)).is_equal_to(ord("y"))


# A bare return is the return key itself, ZSCII 13 -- which is also
# how an acceptance script's lone > presses a key.
def test_an_empty_line_is_the_return_key(
    code_machine: Callable[..., Machine],
) -> None:
    machine = code_machine(READ_CHAR, version=4, input_source=lambda: "")

    machine.run()

    assert_that(machine.memory.read_word(RESULT)).is_equal_to(13)


# The first operand is always 1, the keyboard: no other input device
# was ever defined (§15 read_char).
def test_read_char_refuses_unknown_devices(
    code_machine: Callable[..., Machine],
) -> None:
    program = bytes([0xF6, 0x7F, 0x02, 0x10, 0xBA])
    machine = code_machine(program, version=4, input_source=lambda: "y")

    with pytest.raises(ZMachineInstructionError, match="only device"):
        machine.run()


# A nonzero time and routine pair would need timed input.
def test_timed_read_char_is_a_reported_frontier(
    code_machine: Callable[..., Machine],
) -> None:
    timed = bytes([0xF6, 0x57, 0x01, 0x0A, 0x02, 0x10, 0xBA])
    machine = code_machine(timed, version=4, input_source=lambda: "y")

    with pytest.raises(ZMachineUnimplementedError, match="timed read_char"):
        machine.run()


# A zero time and routine are the same as their absence.
def test_an_untimed_read_char_pair_is_not_timed(
    code_machine: Callable[..., Machine],
) -> None:
    untimed = bytes([0xF6, 0x57, 0x01, 0x00, 0x00, 0x10, 0xBA])
    machine = code_machine(untimed, version=4, input_source=lambda: " ")

    machine.run()

    assert_that(machine.memory.read_word(RESULT)).is_equal_to(ord(" "))


# Two reads from one source: a game loop's shape in miniature.
def test_sread_can_loop(code_machine: Callable[..., Machine]) -> None:
    lines = iter(["go", "hi"])
    program = SREAD[:-1] + SREAD
    machine = code_machine(program, input_source=lambda: next(lines))
    plant_dictionary(machine.memory)
    machine.memory.write_byte(TEXT_BUFFER, 21)
    machine.memory.write_byte(PARSE_BUFFER, 5)

    machine.run()

    assert_that(text_in_buffer(machine.memory)).is_equal_to("hi")
    assert_that(parse_block(machine.memory, 0)[0]).is_equal_to(HI_ADDRESS)
