from collections.abc import Callable

import pytest
from assertpy import assert_that

from voxam.errors import (
    ZMachineInstructionError,
    ZMachineMemoryError,
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


# A positive count already in byte 1 is preloaded input (§15 read):
# the game planted "given " and printed it itself; the typed line
# appends after it, and the whole line is lexed as one -- so the
# dictionary finds "go" at its true buffer position past the
# preload. Beyond Zork restores half-typed commands this way.
def test_preloaded_input_is_kept_and_appended_to(
    code_machine: Callable[..., Machine],
) -> None:
    machine = reader(code_machine, "go", version=5, program=AREAD)
    plant_dictionary(machine.memory, entries=(GO5, HI5))
    machine.memory.write_byte(TEXT_BUFFER + 1, 6)

    for offset, character in enumerate("given "):
        machine.memory.write_byte(TEXT_BUFFER + 2 + offset, ord(character))

    machine.run()

    assert_that(counted_text(machine.memory)).is_equal_to("given go")
    assert_that(parse_block(machine.memory, 0)).is_equal_to((0, 5, 2))
    assert_that(parse_block(machine.memory, 1)).is_equal_to((GO_ADDRESS, 2, 8))


# The capacity bounds the whole line, preload included: with room
# for four and three preloaded, only one typed character fits.
def test_the_preload_counts_against_the_capacity(
    code_machine: Callable[..., Machine],
) -> None:
    machine = reader(code_machine, "mailbox", version=5, program=AREAD)
    machine.memory.write_byte(TEXT_BUFFER, 4)
    machine.memory.write_byte(TEXT_BUFFER + 1, 3)

    for offset, character in enumerate("pre"):
        machine.memory.write_byte(TEXT_BUFFER + 2 + offset, ord(character))

    machine.run()

    assert_that(counted_text(machine.memory)).is_equal_to("prem")


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


# Timed-read scaffolding: interrupt routines planted at $70, which
# packs to $1C in Versions 4 and 5. Each routine marks global $11
# on its way through -- the proof it fired -- before returning true
# (ending the read) or false (letting the typist finish).
ROUTINE_BASE = 0x70
ROUTINE_PACKED = 0x1C
MARK_THEN_TRUE = bytes([0x00, 0x0D, 0x11, 0x63, 0xB0])
MARK_THEN_FALSE = bytes([0x00, 0x0D, 0x11, 0x63, 0xB1])
QUIT_IN_INTERRUPT = bytes([0x00, 0xBA])
MARK = 0x63
MARK_GLOBAL = 0x102


def plant_routine(memory: Memory, code: bytes) -> None:
    for offset, value in enumerate(code):
        memory.write_byte(ROUTINE_BASE + offset, value)


# A time and routine pair asks for interrupts during real waiting;
# the patient typist lets one interval elapse before the line
# arrives, so the routine fires once. Returning true ends the read
# at once: the input is erased, the lexing sees emptiness, and the
# input source is never consulted (§15 read). The marked global is
# the proof the routine ran.
def test_a_timed_read_ends_when_the_interrupt_returns_true(
    code_machine: Callable[..., Machine],
) -> None:
    timed = bytes([0xE4, 0x05, 0x01, 0x20, 0x01, 0x40, 0x0A, 0x1C, 0xBA])
    machine = code_machine(timed, version=4, input_source=lambda: "boom")
    plant_dictionary(machine.memory)
    machine.memory.write_byte(TEXT_BUFFER, 21)
    machine.memory.write_byte(PARSE_BUFFER, 5)
    plant_routine(machine.memory, MARK_THEN_TRUE)

    machine.run()

    assert_that(text_in_buffer(machine.memory)).is_empty()
    assert_that(machine.memory.read_byte(PARSE_BUFFER + 1)).is_zero()
    assert_that(machine.memory.read_word(MARK_GLOBAL)).is_equal_to(MARK)


# A false return means the typist gets there first: the routine
# still fires its once, but the line arrives and the read completes
# as an untimed one (§15 read).
def test_a_false_interrupt_lets_the_line_arrive(
    code_machine: Callable[..., Machine],
) -> None:
    timed = bytes([0xE4, 0x05, 0x01, 0x20, 0x01, 0x40, 0x0A, 0x1C, 0xBA])
    machine = reader(code_machine, "go", version=4, program=timed)
    plant_routine(machine.memory, MARK_THEN_FALSE)

    machine.run()

    assert_that(text_in_buffer(machine.memory)).is_equal_to("go")
    assert_that(machine.memory.read_word(MARK_GLOBAL)).is_equal_to(MARK)


# In Version 5 the interrupted erasure speaks the counted dialect: a
# zero typed count in byte 1, zero parse words, and 0 stored where
# the terminating character would go (§15 read).
def test_an_interrupted_aread_erases_the_counted_buffer(
    code_machine: Callable[..., Machine],
) -> None:
    timed = bytes([0xE4, 0x05, 0x01, 0x20, 0x01, 0x40, 0x0A, 0x1C, 0x10, 0xBA])
    machine = code_machine(timed, version=5, input_source=lambda: "boom")
    plant_dictionary(machine.memory)
    machine.memory.write_byte(TEXT_BUFFER, 21)
    machine.memory.write_byte(PARSE_BUFFER, 5)
    machine.memory.write_word(RESULT, 0xBEEF)
    plant_routine(machine.memory, MARK_THEN_TRUE)

    machine.run()

    assert_that(machine.memory.read_byte(TEXT_BUFFER + 1)).is_zero()
    assert_that(machine.memory.read_byte(PARSE_BUFFER + 1)).is_zero()
    assert_that(machine.memory.read_word(RESULT)).is_zero()
    assert_that(machine.memory.read_word(MARK_GLOBAL)).is_equal_to(MARK)


# An interrupted read honors the zero parse buffer exactly as a
# completed one would: the erasure is written, but the parse region
# is never touched (§15 read).
def test_an_interrupted_aread_skips_a_zero_parse_buffer(
    code_machine: Callable[..., Machine],
) -> None:
    timed = bytes([0xE4, 0x05, 0x01, 0x20, 0x00, 0x00, 0x0A, 0x1C, 0x10, 0xBA])
    machine = code_machine(timed, version=5, input_source=lambda: "boom")
    machine.memory.write_byte(TEXT_BUFFER, 21)
    machine.memory.write_byte(PARSE_BUFFER + 1, 0xAA)
    plant_routine(machine.memory, MARK_THEN_TRUE)

    machine.run()

    assert_that(machine.memory.read_byte(TEXT_BUFFER + 1)).is_zero()
    assert_that(machine.memory.read_byte(PARSE_BUFFER + 1)).is_equal_to(0xAA)


# Before Version 4 the time and routine operands do not exist (§15
# read): a Version 3 story that passes them anyway gets an untimed
# read, and the routine never fires.
def test_version_3_reads_are_never_timed(
    code_machine: Callable[..., Machine],
) -> None:
    timed = bytes([0xE4, 0x05, 0x01, 0x20, 0x01, 0x40, 0x0A, 0x1C, 0xBA])
    machine = reader(code_machine, "go", program=timed)
    plant_routine(machine.memory, MARK_THEN_TRUE)

    machine.run()

    assert_that(text_in_buffer(machine.memory)).is_equal_to("go")
    assert_that(machine.memory.read_word(MARK_GLOBAL)).is_zero()


# A time with no routine to fire is not timed either (§15 read):
# the third operand alone asks for nothing.
def test_a_time_without_a_routine_is_not_timed(
    code_machine: Callable[..., Machine],
) -> None:
    lonely = bytes([0xE4, 0x07, 0x01, 0x20, 0x01, 0x40, 0x0A, 0xBA])
    machine = reader(code_machine, "go", version=4, program=lonely)

    machine.run()

    assert_that(text_in_buffer(machine.memory)).is_equal_to("go")


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


# The patient typist for a single keystroke: one interval elapses,
# the routine fires, and its true return ends the read with 0
# stored and no input consumed (§15 read_char) -- Z-Tornado's
# Pause routine in miniature. The stored result starts poisoned to
# prove the 0 was written, not merely never touched.
def test_a_timed_read_char_ends_when_the_interrupt_returns_true(
    code_machine: Callable[..., Machine],
) -> None:
    timed = bytes([0xF6, 0x57, 0x01, 0x0A, 0x1C, 0x10, 0xBA])
    machine = code_machine(timed, version=4, input_source=lambda: "boom")
    machine.memory.write_word(RESULT, 0xBEEF)
    plant_routine(machine.memory, MARK_THEN_TRUE)

    machine.run()

    assert_that(machine.memory.read_word(RESULT)).is_zero()
    assert_that(machine.memory.read_word(MARK_GLOBAL)).is_equal_to(MARK)


# A false return means the key arrives after the routine's one
# firing and stores as if the read were untimed (§15 read_char) --
# Z-Tornado's SeedRand harvesting entropy while the player types.
def test_a_false_interrupt_lets_the_key_arrive(
    code_machine: Callable[..., Machine],
) -> None:
    timed = bytes([0xF6, 0x57, 0x01, 0x0A, 0x1C, 0x10, 0xBA])
    machine = code_machine(timed, version=4, input_source=lambda: "y")
    plant_routine(machine.memory, MARK_THEN_FALSE)

    machine.run()

    assert_that(machine.memory.read_word(RESULT)).is_equal_to(ord("y"))
    assert_that(machine.memory.read_word(MARK_GLOBAL)).is_equal_to(MARK)


# A story may quit inside an interrupt; input has certainly ended
# then, so the read closes by the interrupted path and the machine
# stops where it stands.
def test_a_quit_inside_an_interrupt_stops_the_machine(
    code_machine: Callable[..., Machine],
) -> None:
    timed = bytes([0xF6, 0x57, 0x01, 0x0A, 0x1C, 0x10, 0xBA])
    machine = code_machine(timed, version=4, input_source=lambda: "boom")
    machine.memory.write_word(RESULT, 0xBEEF)
    plant_routine(machine.memory, QUIT_IN_INTERRUPT)

    machine.run()

    assert_that(machine.running).is_false()
    assert_that(machine.memory.read_word(RESULT)).is_zero()


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


CUSTOM_DICTIONARY = 0x160

# tokenise text parse [dictionary [flag]] as VAR:27 (§15 tokenise).
TOKENISE = bytes([0xFB, 0x0F, 0x01, 0x20, 0x01, 0x40, 0xBA])
TOKENISE_CUSTOM = bytes([0xFB, 0x03, 0x01, 0x20, 0x01, 0x40, 0x01, 0x60, 0xBA])
TOKENISE_KEEPING = bytes([0xFB, 0x01, 0x01, 0x20, 0x01, 0x40, 0x01, 0x60, 0x01, 0xBA])


def plant_text(memory: Memory, line: str) -> None:
    """Lay a line into the Version 5 counted text buffer by hand."""

    memory.write_byte(TEXT_BUFFER + 1, len(line))

    for offset, character in enumerate(line):
        memory.write_byte(TEXT_BUFFER + 2 + offset, ord(character))


def plant_custom(memory: Memory, entries: tuple[bytes, ...], count: int) -> None:
    """Plant a user dictionary with its own (possibly signed) count."""

    position = CUSTOM_DICTIONARY
    memory.write_byte(position, 0)
    memory.write_byte(position + 1, 7)
    memory.write_word(position + 2, count & 0xFFFF)
    position += 4

    for entry in entries:
        for offset, value in enumerate(entry):
            memory.write_byte(position + offset, value)

        position += 7


def tokeniser(
    code_machine: Callable[..., Machine], line: str, program: bytes = TOKENISE
) -> Machine:
    machine = code_machine(program, version=5)
    plant_dictionary(machine.memory, entries=(GO5, HI5))
    machine.memory.write_byte(PARSE_BUFFER, 5)
    plant_text(machine.memory, line)

    return machine


# tokenise is the lexing half of read as its own opcode: it analyses
# text already sitting in the counted buffer against the game's own
# dictionary (§15 tokenise).
def test_tokenise_analyses_the_buffer_in_place(
    code_machine: Callable[..., Machine],
) -> None:
    machine = tokeniser(code_machine, "go hi")

    machine.run()

    assert_that(machine.memory.read_byte(PARSE_BUFFER + 1)).is_equal_to(2)
    assert_that(parse_block(machine.memory, 0)).is_equal_to((GO_ADDRESS, 2, 2))
    assert_that(parse_block(machine.memory, 1)).is_equal_to((HI_ADDRESS, 2, 5))


# A nonzero third operand names a custom dictionary to consult
# instead of the game's own (§15 tokenise).
def test_tokenise_consults_a_custom_dictionary(
    code_machine: Callable[..., Machine],
) -> None:
    machine = tokeniser(code_machine, "go hi", program=TOKENISE_CUSTOM)
    plant_custom(machine.memory, (HI5,), count=1)

    machine.run()

    assert_that(parse_block(machine.memory, 0)).is_equal_to((0, 2, 2))
    assert_that(parse_block(machine.memory, 1)).is_equal_to(
        (CUSTOM_DICTIONARY + 4, 2, 5)
    )


# A count of -n means n entries unsorted (§13.5): convenient for a
# table altered in play, and no obstacle to a linear hunt.
def test_a_negative_count_reads_as_unsorted_entries(
    code_machine: Callable[..., Machine],
) -> None:
    machine = tokeniser(code_machine, "hi go", program=TOKENISE_CUSTOM)
    plant_custom(machine.memory, (HI5, GO5), count=-2)

    machine.run()

    assert_that(parse_block(machine.memory, 0)).is_equal_to(
        (CUSTOM_DICTIONARY + 4, 2, 2)
    )
    assert_that(parse_block(machine.memory, 1)).is_equal_to(
        (CUSTOM_DICTIONARY + 11, 2, 5)
    )


# With the flag set, unrecognised words leave their slots untouched,
# so successive passes against different dictionaries accumulate
# (§15 tokenise). The sentinel poked into "go"'s slot survives the
# custom-dictionary pass that does not know the word.
def test_the_flag_leaves_unrecognised_slots_untouched(
    code_machine: Callable[..., Machine],
) -> None:
    machine = tokeniser(code_machine, "go hi", program=TOKENISE_KEEPING)
    plant_custom(machine.memory, (HI5,), count=1)
    machine.memory.write_word(PARSE_BUFFER + 2, 0xBEEF)

    machine.run()

    assert_that(machine.memory.read_byte(PARSE_BUFFER + 1)).is_equal_to(2)
    assert_that(machine.memory.read_word(PARSE_BUFFER + 2)).is_equal_to(0xBEEF)
    assert_that(parse_block(machine.memory, 1)).is_equal_to(
        (CUSTOM_DICTIONARY + 4, 2, 5)
    )


# The parse buffer may be omitted outright from Version 5 --
# TerpEtude reads with the text buffer alone -- and behaves as a
# zero buffer: text stored, no lexing (§15 read).
def test_aread_with_no_parse_operand_skips_lexing(
    code_machine: Callable[..., Machine],
) -> None:
    lone = bytes([0xE4, 0x3F, 0x01, 0x20, 0x10, 0xBA])
    machine = reader(code_machine, "go", version=5, program=lone)
    machine.memory.write_byte(PARSE_BUFFER + 1, 0xAA)

    machine.run()

    assert_that(counted_text(machine.memory)).is_equal_to("go")
    assert_that(machine.memory.read_byte(PARSE_BUFFER + 1)).is_equal_to(0xAA)


# Through Version 4 the analysis is not optional: a read without a
# parse buffer refuses with a citation, not an index error.
def test_sread_without_a_parse_buffer_halts(
    code_machine: Callable[..., Machine],
) -> None:
    lone = bytes([0xE4, 0x3F, 0x01, 0x20, 0xBA])
    machine = reader(code_machine, "go", version=3, program=lone)

    with pytest.raises(ZMachineInstructionError, match="not optional"):
        machine.run()


# read_char may omit even its device operand -- Strict Z Test's
# closing keypress compiles bare -- and an absent device is the
# keyboard, there being no other (§15 read_char).
def test_read_char_with_no_operands_reads_the_keyboard(
    code_machine: Callable[..., Machine],
) -> None:
    bare = bytes([0xF6, 0xFF, 0x10, 0xBA])
    machine = code_machine(bare, version=4, input_source=lambda: "y")

    machine.run()

    assert_that(machine.memory.read_word(0x100)).is_equal_to(ord("y"))
