from collections.abc import Callable

import pytest
from assertpy import assert_that

from voxam.errors import (
    ZMachineInstructionError,
    ZMachineMemoryError,
)
from voxam.frontend import PlainFrontend
from voxam.zmachine.machine import Machine
from voxam.zmachine.memory import Memory
from voxam.zmachine.story import Story
from voxam.zmachine.zscii import encode_word

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
COUNT_THEN_TRUE = bytes([0x00, 0x95, 0x11, 0xB0])
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


# §15's remark: when a timed read's interrupt routine prints and
# input continues, the interpreter should redisplay the input line
# -- Jigsaw's chapter epigraphs arrive exactly this way. The
# machine tells the frontend the read began, and again after a
# PRINTING interrupt that returned false; a silent interrupt earns
# no redisplay, a terminating one erases the input instead, and a
# keystroke read has no input line to redisplay at all.
def test_a_printing_interrupt_redisplays_the_input_line(
    code_machine: Callable[..., Machine],
) -> None:
    class InputWatcher(PlainFrontend):
        def __init__(self) -> None:
            super().__init__(lambda _text: None)
            self.notices: list[str] = []

        def begin_input(self) -> None:
            self.notices.append("begin")

        def resume_input(self) -> None:
            self.notices.append("resume")

    timed = bytes([0xE4, 0x05, 0x01, 0x20, 0x01, 0x40, 0x0A, 0x1C, 0xBA])
    print_then_false = bytes([0x00, 0xE5, 0x7F, 0x58, 0xB1])

    watcher = InputWatcher()
    machine = code_machine(
        timed, version=4, input_source=lambda: "go", frontend=watcher
    )
    plant_dictionary(machine.memory)
    machine.memory.write_byte(TEXT_BUFFER, 21)
    machine.memory.write_byte(PARSE_BUFFER, 5)
    plant_routine(machine.memory, print_then_false)

    machine.run()

    assert_that(watcher.notices).is_equal_to(["begin", "resume"])
    assert_that(text_in_buffer(machine.memory)).is_equal_to("go")

    silent = InputWatcher()
    machine = code_machine(timed, version=4, input_source=lambda: "go", frontend=silent)
    plant_dictionary(machine.memory)
    machine.memory.write_byte(TEXT_BUFFER, 21)
    machine.memory.write_byte(PARSE_BUFFER, 5)
    plant_routine(machine.memory, MARK_THEN_FALSE)

    machine.run()

    assert_that(silent.notices).is_equal_to(["begin"])

    keys = InputWatcher()
    machine = code_machine(
        bytes([0xF6, 0x57, 0x01, 0x0A, 0x1C, 0x10, 0xBA]),
        version=4,
        input_source=lambda: "y",
        frontend=keys,
    )
    plant_routine(machine.memory, print_then_false)

    machine.run()

    assert_that(keys.notices).is_empty()


class InputNotices(PlainFrontend):
    """A frontend that logs the §15 redisplay seams as they fire."""

    def __init__(self) -> None:
        super().__init__(lambda _text: None)
        self.notices: list[str] = []

    def begin_input(self) -> None:
        self.notices.append("begin")

    def resume_input(self) -> None:
        self.notices.append("resume")


# A live timed source runs the read on the wall clock: the source
# waits the read's own interval (time/10 seconds), each expiry
# fires the routine, and the completed line arrives through the
# source -- the patient typist never runs and the input source is
# never consulted (§15 read).
def test_a_live_timed_read_ticks_until_the_line(
    code_machine: Callable[..., Machine],
) -> None:
    timed = bytes([0xE4, 0x05, 0x01, 0x20, 0x01, 0x40, 0x0A, 0x1C, 0xBA])
    answers = iter([None, None, "go"])
    intervals: list[float] = []

    def ticking(seconds: float) -> str | None:
        intervals.append(seconds)

        return next(answers)

    machine = code_machine(
        timed,
        version=4,
        input_source=lambda: "wrong",
        timed_input_source=ticking,
    )
    plant_dictionary(machine.memory)
    machine.memory.write_byte(TEXT_BUFFER, 21)
    machine.memory.write_byte(PARSE_BUFFER, 5)
    plant_routine(machine.memory, MARK_THEN_FALSE)

    machine.run()

    assert_that(text_in_buffer(machine.memory)).is_equal_to("go")
    assert_that(intervals).is_equal_to([1.0, 1.0, 1.0])
    assert_that(machine.memory.read_word(MARK_GLOBAL)).is_equal_to(MARK)


# A true return from a live tick's interrupt ends the read with the
# input erased -- from the buffers, and from the frontend, which is
# told to abandon the half-typed line (§15 read).
def test_a_live_timed_read_terminated_by_its_interrupt(
    code_machine: Callable[..., Machine],
) -> None:
    class Abandoner(PlainFrontend):
        def __init__(self) -> None:
            super().__init__(lambda _text: None)
            self.abandoned = 0

        def abandon_input(self) -> None:
            self.abandoned += 1

    timed = bytes([0xE4, 0x05, 0x01, 0x20, 0x01, 0x40, 0x0A, 0x1C, 0xBA])
    watcher = Abandoner()
    machine = code_machine(
        timed,
        version=4,
        input_source=lambda: "wrong",
        frontend=watcher,
        timed_input_source=lambda _seconds: None,
    )
    plant_dictionary(machine.memory)
    machine.memory.write_byte(TEXT_BUFFER, 21)
    machine.memory.write_byte(PARSE_BUFFER, 5)
    plant_routine(machine.memory, MARK_THEN_TRUE)

    machine.run()

    assert_that(text_in_buffer(machine.memory)).is_empty()
    assert_that(watcher.abandoned).is_equal_to(1)


# The §15 redisplay courtesy holds on the live clock too: a
# printing interrupt that lets input continue earns a resume.
def test_a_live_printing_interrupt_redisplays(
    code_machine: Callable[..., Machine],
) -> None:
    timed = bytes([0xE4, 0x05, 0x01, 0x20, 0x01, 0x40, 0x0A, 0x1C, 0xBA])
    print_then_false = bytes([0x00, 0xE5, 0x7F, 0x58, 0xB1])
    answers = iter([None, "go"])
    watcher = InputNotices()
    machine = code_machine(
        timed,
        version=4,
        input_source=lambda: "wrong",
        frontend=watcher,
        timed_input_source=lambda _seconds: next(answers),
    )
    plant_dictionary(machine.memory)
    machine.memory.write_byte(TEXT_BUFFER, 21)
    machine.memory.write_byte(PARSE_BUFFER, 5)
    plant_routine(machine.memory, print_then_false)

    machine.run()

    assert_that(watcher.notices).is_equal_to(["begin", "resume"])
    assert_that(text_in_buffer(machine.memory)).is_equal_to("go")


# An interrupt that prints only to the upper window -- Border
# Zone's clock repainting its status every tick -- never disturbs
# the input line, and earns no redisplay: without this rule every
# tick appended another prompt, a picket fence of > characters.
def test_an_upper_window_interrupt_earns_no_redisplay(
    code_machine: Callable[..., Machine],
) -> None:
    timed = bytes([0xE4, 0x05, 0x01, 0x20, 0x01, 0x40, 0x0A, 0x1C, 0xBA])
    # split_window 1; set_window 1; print_char 'X'; set_window 0; rfalse
    status_tick = bytes(
        [
            0x00,
            0xEA,
            0x7F,
            0x01,
            0xEB,
            0x7F,
            0x01,
            0xE5,
            0x7F,
            0x58,
            0xEB,
            0x7F,
            0x00,
            0xB1,
        ]
    )
    answers = iter([None, "go"])
    watcher = InputNotices()
    machine = code_machine(
        timed,
        version=4,
        input_source=lambda: "wrong",
        frontend=watcher,
        timed_input_source=lambda _seconds: next(answers),
    )
    plant_dictionary(machine.memory)
    machine.memory.write_byte(TEXT_BUFFER, 21)
    machine.memory.write_byte(PARSE_BUFFER, 5)
    plant_routine(machine.memory, status_tick)

    machine.run()

    assert_that(watcher.notices).is_equal_to(["begin"])
    assert_that(text_in_buffer(machine.memory)).is_equal_to("go")


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


class ClickingFrontend(PlainFrontend):
    """A frontend whose mouse has just clicked at (5, 3)."""

    has_mouse = True

    def __init__(self) -> None:
        super().__init__(lambda _text: None)

    def click_position(self) -> tuple[int, int] | None:
        return (5, 3)


# A mouse click arrives through the key seam as the character for
# its §10.3.3 input code -- 254 single, 253 double -- and the
# click's position lands in header extension words 1 and 2 before
# delivery (§10.3.2).
def test_clicks_deliver_their_code_and_coordinates(
    code_machine: Callable[..., Machine],
) -> None:
    extension = 0x160
    read_char = bytes([0xF6, 0x7F, 0x01, 0x10, 0xBA])
    keys = iter(["\xfe"])
    machine = code_machine(
        read_char,
        version=5,
        frontend=ClickingFrontend(),
        key_source=lambda _timeout: next(keys),
    )
    machine.memory.write_word(0x36, extension)
    machine.memory.write_word(extension, 2)

    machine.run()

    assert_that(machine.memory.read_word(0x100)).is_equal_to(254)
    assert_that(machine.memory.read_word(extension + 2)).is_equal_to(5)
    assert_that(machine.memory.read_word(extension + 4)).is_equal_to(3)


# Without a header extension the story still hears the click -- it
# just cannot ask where (§10.3.1). A double click is code 253.
def test_clicks_without_an_extension_still_arrive(
    code_machine: Callable[..., Machine],
) -> None:
    read_char = bytes([0xF6, 0x7F, 0x01, 0x10, 0xBA])
    keys = iter(["\xfd"])
    machine = code_machine(
        read_char,
        version=5,
        frontend=ClickingFrontend(),
        key_source=lambda _timeout: next(keys),
    )

    machine.run()

    assert_that(machine.memory.read_word(0x100)).is_equal_to(253)


# A scripted session presses the mouse through the click_source
# seam: the coordinates come from the script, not from a frontend
# that never saw a mouse -- and a source with no pair left leaves
# the extension words unwritten, like a mouseless frontend would.
def test_scripted_clicks_bring_their_own_coordinates(
    code_machine: Callable[..., Machine],
) -> None:
    extension = 0x160
    read_char = bytes([0xF6, 0x7F, 0x01, 0x10, 0xBA])
    keys = iter(["\xfe"])
    machine = code_machine(
        read_char,
        version=5,
        key_source=lambda _timeout: next(keys),
        click_source=lambda: (7, 9),
    )
    machine.memory.write_word(0x36, extension)
    machine.memory.write_word(extension, 2)

    machine.run()

    assert_that(machine.memory.read_word(0x100)).is_equal_to(254)
    assert_that(machine.memory.read_word(extension + 2)).is_equal_to(7)
    assert_that(machine.memory.read_word(extension + 4)).is_equal_to(9)

    spent = iter(["\xfe"])
    dry = code_machine(
        read_char,
        version=5,
        key_source=lambda _timeout: next(spent),
        click_source=lambda: None,
    )
    dry.memory.write_word(0x36, extension)
    dry.memory.write_word(extension, 2)

    dry.run()

    assert_that(dry.memory.read_word(0x100)).is_equal_to(254)
    assert_that(dry.memory.read_word(extension + 2)).is_equal_to(0)


# A timed keystroke read hears clicks the same way (§10.3.3).
def test_timed_reads_hear_clicks(code_machine: Callable[..., Machine]) -> None:
    extension = 0x160
    timed = bytes([0xF6, 0x57, 0x01, 0x0A, 0x1C, 0x10, 0xBA])
    keys = iter([None, "\xfe"])
    machine = code_machine(
        timed,
        version=5,
        frontend=ClickingFrontend(),
        key_source=lambda _timeout: next(keys),
    )
    machine.memory.write_word(0x36, extension)
    machine.memory.write_word(extension, 2)
    plant_routine(machine.memory, MARK_THEN_FALSE)

    machine.run()

    assert_that(machine.memory.read_word(0x100)).is_equal_to(254)
    assert_that(machine.memory.read_word(extension + 2)).is_equal_to(5)


# From Version 5 the mouse request answers honestly at boot
# (§10.3.1.1): a frontend with real clicks keeps Flags 2 bit 5,
# and the plain stream clears it -- which is how Solitaire Poker
# knows whether to draw its clickable buttons.
def test_the_mouse_request_answers_honestly_at_boot() -> None:
    def mouse_wanting_story() -> Story:
        data = bytearray(512)
        data[0] = 5
        data[0x04:0x06] = (0x01C0).to_bytes(2, "big")
        data[0x06:0x08] = (0x0040).to_bytes(2, "big")
        data[0x0C:0x0E] = (0x0100).to_bytes(2, "big")
        data[0x0E:0x10] = (0x01C0).to_bytes(2, "big")
        data[0x11] = 0x20
        data[0x40] = 0xBA  # quit

        return Story(bytes(data))

    clicked = Machine(mouse_wanting_story(), ClickingFrontend())

    assert_that(clicked.memory.read_byte(0x11) & 0x20).is_equal_to(0x20)

    plain = Machine(mouse_wanting_story(), PlainFrontend(lambda _text: None))

    assert_that(plain.memory.read_byte(0x11) & 0x20).is_zero()


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


# The typist is nimble as well as patient: when an interrupt ends
# a timed read and the game loops straight back to the SAME read
# -- Custard's pi-digit animation, retrying in a tight loop -- the
# burned interval was typing time, and the retry finds the key
# without the routine firing again. A timed read at a DIFFERENT
# address is a new question and earns its own patient interval.
# The program loops on one read_char until a key arrives, then
# reads twice more at fresh addresses; the counting routine proves
# exactly two firings: one ending the looped read's first pass,
# one for the last read when the queue is spent.
def test_a_terminating_interrupt_never_starves_the_typist(
    code_machine: Callable[..., Machine],
) -> None:
    reads = bytes(
        [
            *[0xF6, 0x57, 0x01, 0x0A, 0x1C, 0x10],
            *[0xA0, 0x10, 0xBF, 0xF8],
            *[0xF6, 0x57, 0x01, 0x0A, 0x1C, 0x12],
            *[0xF6, 0x57, 0x01, 0x0A, 0x1C, 0x13],
            0xBA,
        ]
    )
    lines = iter(["ab"])
    machine = code_machine(reads, version=4, input_source=lambda: next(lines))
    plant_routine(machine.memory, COUNT_THEN_TRUE)

    machine.run()

    assert_that(machine.memory.read_word(0x100)).is_equal_to(ord("a"))
    assert_that(machine.memory.read_word(0x104)).is_equal_to(ord("b"))
    assert_that(machine.memory.read_word(0x106)).is_zero()
    assert_that(machine.memory.read_word(MARK_GLOBAL)).is_equal_to(2)


# A line read is a fresh sitting: readiness earned by a terminated
# keystroke read does not carry to the prompt, and the whole next
# line arrives there intact -- how Z-Tornado's Pause and its
# ordinary prompts keep living together.
def test_a_line_read_resets_the_typists_readiness(
    code_machine: Callable[..., Machine],
) -> None:
    program = bytes(
        [
            *[0xF6, 0x57, 0x01, 0x0A, 0x1C, 0x10],
            *[0xE4, 0x0F, 0x01, 0x20, 0x01, 0x40],
            0xBA,
        ]
    )
    machine = reader(code_machine, "go", version=4, program=program)
    plant_routine(machine.memory, MARK_THEN_TRUE)

    machine.run()

    assert_that(machine.memory.read_word(0x100)).is_zero()
    assert_that(text_in_buffer(machine.memory)).is_equal_to("go")


# A line longer than one character is a run of keystrokes: the
# queue spends it one read_char at a time, drawing no new line
# until it is empty (§15 read_char). The input source is an
# iterator so a second fetch would fail the test loudly.
def test_a_longer_line_types_one_keystroke_at_a_time(
    code_machine: Callable[..., Machine],
) -> None:
    keys = bytes(
        [0xF6, 0x7F, 0x01, 0x10, 0xF6, 0x7F, 0x01, 0x11, 0xF6, 0x7F, 0x01, 0x12, 0xBA]
    )
    lines = iter(["abc"])
    machine = code_machine(keys, version=4, input_source=lambda: next(lines))

    machine.run()

    assert_that(machine.memory.read_word(0x100)).is_equal_to(ord("a"))
    assert_that(machine.memory.read_word(0x102)).is_equal_to(ord("b"))
    assert_that(machine.memory.read_word(0x104)).is_equal_to(ord("c"))


# A frontend that reads the keyboard raw hands keystrokes over one
# at a time through key_source, bypassing the line queue: enter
# arrives as a real newline character and lands as ZSCII 13, and a
# key ZSCII has no code for -- the grinning face below -- is a key
# the story cannot hear, ignored rather than fatal (§3.8).
def test_a_key_source_bypasses_the_line_queue(
    code_machine: Callable[..., Machine],
) -> None:
    keys = bytes(
        [0xF6, 0x7F, 0x01, 0x10, 0xF6, 0x7F, 0x01, 0x11, 0xF6, 0x7F, 0x01, 0x12, 0xBA]
    )
    strokes = iter([None, "y", "\N{GRINNING FACE}", "\n", "\x1b"])
    machine = code_machine(
        keys,
        version=4,
        input_source=lambda: "boom",
        key_source=lambda _timeout: next(strokes),
    )

    machine.run()

    assert_that(machine.memory.read_word(0x100)).is_equal_to(ord("y"))
    assert_that(machine.memory.read_word(0x102)).is_equal_to(13)
    assert_that(machine.memory.read_word(0x104)).is_equal_to(27)


# A scripted arrow travels the line queue too: the .accept grammar
# delivers a <down> line as its §3.8.4 character, and the keystroke
# seam spends it as the single press read_char hears.
def test_scripted_arrows_reach_read_char(
    code_machine: Callable[..., Machine],
) -> None:
    machine = code_machine(READ_CHAR, version=4, input_source=lambda: "\x82")

    machine.run()

    assert_that(machine.memory.read_word(RESULT)).is_equal_to(130)


# The cursor keys arrive from a raw keyboard as their §3.8.4
# codepoints, defined for input only, and land in read_char's
# store as ZSCII 129 to 132 -- how Beyond Zork's menus hear an
# arrow.
def test_cursor_keys_reach_read_char_as_their_codes(
    code_machine: Callable[..., Machine],
) -> None:
    keys = bytes([0xF6, 0x7F, 0x01, 0x10, 0xF6, 0x7F, 0x01, 0x11, 0xBA])
    strokes = iter(["\x81", "\x84"])
    machine = code_machine(
        keys,
        version=4,
        key_source=lambda _timeout: next(strokes),
    )

    machine.run()

    assert_that(machine.memory.read_word(0x100)).is_equal_to(129)
    assert_that(machine.memory.read_word(0x102)).is_equal_to(132)


# On a raw keyboard a timed read runs on the wall clock: every
# expired interval -- a None from the key source -- fires the
# interrupt routine, and the key that finally arrives is stored
# with the marks of the routine's firings beside it (§15
# read_char).
def test_a_timed_read_char_fires_on_the_wall_clock(
    code_machine: Callable[..., Machine],
) -> None:
    timed = bytes([0xF6, 0x57, 0x01, 0x0A, 0x1C, 0x10, 0xBA])
    waits = iter([None, None, "y"])
    seen: list[float | None] = []

    def source(timeout: float | None) -> str | None:
        seen.append(timeout)

        return next(waits)

    machine = code_machine(timed, version=4, key_source=source)
    plant_routine(machine.memory, MARK_THEN_FALSE)

    machine.run()

    assert_that(machine.memory.read_word(RESULT)).is_equal_to(ord("y"))
    assert_that(machine.memory.read_word(MARK_GLOBAL)).is_equal_to(MARK)
    assert_that(seen).is_equal_to([1.0, 1.0, 1.0])


# A true return from the wall-clock interrupt ends the read at
# once, storing 0 without waiting for any key (§15 read_char).
def test_a_wall_clock_interrupt_can_end_the_read(
    code_machine: Callable[..., Machine],
) -> None:
    timed = bytes([0xF6, 0x57, 0x01, 0x0A, 0x1C, 0x10, 0xBA])
    machine = code_machine(timed, version=4, key_source=lambda _timeout: None)
    machine.memory.write_word(RESULT, 0xBEEF)
    plant_routine(machine.memory, MARK_THEN_TRUE)

    machine.run()

    assert_that(machine.memory.read_word(RESULT)).is_zero()
    assert_that(machine.memory.read_word(MARK_GLOBAL)).is_equal_to(MARK)


# A key ZSCII cannot express inside a timed wait is skipped without
# firing the interrupt: the player did type, just nothing the story
# hears (§3.8).
def test_a_wall_clock_read_skips_unhearable_keys(
    code_machine: Callable[..., Machine],
) -> None:
    timed = bytes([0xF6, 0x57, 0x01, 0x0A, 0x1C, 0x10, 0xBA])
    waits = iter(["\N{GRINNING FACE}", "q"])
    machine = code_machine(timed, version=4, key_source=lambda _timeout: next(waits))
    plant_routine(machine.memory, MARK_THEN_FALSE)

    machine.run()

    assert_that(machine.memory.read_word(RESULT)).is_equal_to(ord("q"))
    assert_that(machine.memory.read_word(MARK_GLOBAL)).is_zero()


# The queue never invents a return: enter is an explicit empty line
# after the keystrokes, so a one-character line stays exactly one
# key -- the assumption every recording made before the queue
# existed -- and Bureaucracy's licence form types a field as its
# line plus the empty line behind it (§15 read_char).
def test_enter_is_an_explicit_empty_line(
    code_machine: Callable[..., Machine],
) -> None:
    keys = bytes(
        [0xF6, 0x7F, 0x01, 0x10, 0xF6, 0x7F, 0x01, 0x11, 0xF6, 0x7F, 0x01, 0x12, 0xBA]
    )
    lines = iter(["ab", ""])
    machine = code_machine(keys, version=4, input_source=lambda: next(lines))

    machine.run()

    assert_that(machine.memory.read_word(0x100)).is_equal_to(ord("a"))
    assert_that(machine.memory.read_word(0x102)).is_equal_to(ord("b"))
    assert_that(machine.memory.read_word(0x104)).is_equal_to(13)


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


# encode_text translates buffer characters to dictionary form (§15):
# five characters from position 1 of the zscii-text buffer -- the
# operands followed to the letter, no hunting for a 0 -- land at
# coded-text as the very bytes a dictionary key wears (§3.7),
# lowercasing on the way exactly as lookup does.
def test_encode_text_writes_the_dictionary_form(
    code_machine: Callable[..., Machine],
) -> None:
    program = bytes([0xFC, 0x14, 0x01, 0x50, 0x05, 0x01, 0x01, 0x80, 0xBA])
    machine = code_machine(program, version=5)

    for offset, character in enumerate("xHello"):
        machine.memory.write_byte(0x150 + offset, ord(character))

    machine.run()

    encoded = bytes(machine.memory.read_byte(0x180 + index) for index in range(6))

    assert_that(encoded).is_equal_to(encode_word(5, "hello"))


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
