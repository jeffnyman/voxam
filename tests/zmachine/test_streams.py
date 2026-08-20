from collections.abc import Callable

import pytest
from assertpy import assert_that

from voxam.errors import ZMachineInstructionError, ZMachineUnimplementedError
from voxam.zmachine.machine import Machine

TABLE = 0x120
SECOND_TABLE = 0x140

FLAGS_2 = 0x10
TEXT_BUFFER = 0x160
GLOBAL_0 = 0x100


class StubScribe:
    """A scribe that keeps every session file in a list."""

    def __init__(self, plays: list[str] | None = None) -> None:
        self.pages: list[str] = []
        self.lines: list[str] = []
        self.plays = list(plays or [])

    def transcript(self, text: str) -> None:
        self.pages.append(text)

    def command(self, line: str) -> None:
        self.lines.append(line)

    def playback(self) -> str | None:
        return self.plays.pop(0) if self.plays else None


# 'h' and 'i' in one terminated word (§3.5.3), printed as a literal.
PRINT_HI = bytes([0xB2, 0xB5, 0xC5])
NEW_LINE = bytes([0xBB])
QUIT = bytes([0xBA])

SELECT_TABLE = bytes([0xF3, 0x4F, 0x03, 0x01, 0x20])
SELECT_SECOND = bytes([0xF3, 0x4F, 0x03, 0x01, 0x40])
DESELECT = bytes([0xF3, 0x3F, 0xFF, 0xFD])
SCREEN_OFF = bytes([0xF3, 0x3F, 0xFF, 0xFF])
SCREEN_ON = bytes([0xF3, 0x7F, 0x01])
SELECT_TRANSCRIPT = bytes([0xF3, 0x7F, 0x02])
DESELECT_TRANSCRIPT = bytes([0xF3, 0x3F, 0xFF, 0xFE])
SELECT_COMMANDS = bytes([0xF3, 0x7F, 0x04])
DESELECT_COMMANDS = bytes([0xF3, 0x3F, 0xFF, 0xFC])
FILE_INPUT = bytes([0xF4, 0x7F, 0x01])
KEYBOARD_INPUT = bytes([0xF4, 0x7F, 0x00])

# aread with the text buffer alone -- no parse, no dictionary --
# storing its terminator to the stack (§15 read).
AREAD_ONLY = bytes([0xE4, 0x3F, 0x01, 0x60, 0x00])
READ_KEY = bytes([0xF6, 0x7F, 0x01, 0x10])


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


# Input stream 0 is the keyboard, which is already where every
# session's keys come from -- selecting it changes nothing (§10.2).
def test_input_stream_zero_is_the_keyboard_already(
    code_machine: Callable[..., Machine],
) -> None:
    _, screen = run(code_machine, bytes([0xF4, 0x7F, 0x00]) + PRINT_HI + QUIT)

    assert_that(screen).is_equal_to("hi")


# Input stream 1 -- a command file the game itself asks to read
# from mid-play (§10.2.2) -- awaits a file to read from.
def test_input_stream_one_is_a_reported_frontier(
    code_machine: Callable[..., Machine],
) -> None:
    machine = code_machine(bytes([0xF4, 0x7F, 0x01]) + QUIT, version=4)

    with pytest.raises(ZMachineUnimplementedError, match="input stream 1"):
        machine.run()


def test_undefined_input_streams_halt(
    code_machine: Callable[..., Machine],
) -> None:
    machine = code_machine(bytes([0xF4, 0x7F, 0x02]) + QUIT, version=4)

    with pytest.raises(ZMachineInstructionError, match="only 0 and 1"):
        machine.run()


def scribed(
    code_machine: Callable[..., Machine],
    program: bytes,
    scribe: StubScribe,
    *lines: str,
    output: list[str] | None = None,
) -> Machine:
    """A Version 5 machine with session files and a text buffer."""

    feed = iter(lines)
    machine = code_machine(
        program,
        version=5,
        scribe=scribe,
        input_source=lambda: next(feed, ""),
        output=output.append if output is not None else None,
    )

    machine.memory.write_byte(TEXT_BUFFER, 20)

    return machine


def buffered_text(machine: Machine) -> str:
    """The counted text a Version 5 read left in the buffer."""

    count = machine.memory.read_byte(TEXT_BUFFER + 1)

    return "".join(
        chr(machine.memory.read_byte(TEXT_BUFFER + 2 + offset))
        for offset in range(count)
    )


def with_interrupt(program: bytes) -> bytes:
    """The program padded to $64, where an rfalse routine waits."""

    return program + bytes(0x24 - len(program)) + bytes([0x00, 0xB1])


# The transcript hears story text while stream 2 is on, and 'Flags
# 2' bit 0 holds the stream's status at every moment -- §7.4's own
# rule, which 'A Mind Forever Voyaging' depends on.
def test_the_transcript_hears_selected_story_text(
    code_machine: Callable[..., Machine],
) -> None:
    scribe = StubScribe()
    machine = scribed(
        code_machine,
        SELECT_TRANSCRIPT + PRINT_HI + DESELECT_TRANSCRIPT + PRINT_HI + QUIT,
        scribe,
    )

    machine.run()

    assert_that(scribe.pages).is_equal_to(["hi"])
    assert_that(machine.memory.read_word(FLAGS_2) & 1).is_equal_to(0)

    still_on = StubScribe()
    running = scribed(code_machine, SELECT_TRANSCRIPT + PRINT_HI + QUIT, still_on)

    running.run()

    assert_that(running.memory.read_word(FLAGS_2) & 1).is_equal_to(1)


# The flag is the switch: a game working 'Flags 2' directly --
# §7.3's only mechanism in Versions 1 and 2 -- turns the transcript
# on and off without ever touching output_stream (§7.4).
def test_the_flag_alone_works_the_transcript(
    code_machine: Callable[..., Machine],
) -> None:
    scribe = StubScribe()
    program = (
        bytes([0xE1, 0x57, 0x10, 0x00, 0x01])
        + PRINT_HI
        + bytes([0xE1, 0x57, 0x10, 0x00, 0x00])
        + PRINT_HI
        + QUIT
    )
    machine = scribed(code_machine, program, scribe)

    machine.run()

    assert_that(scribe.pages).is_equal_to(["hi"])


# The streams are independent: a deselected screen starves nothing
# but itself (§7.1) -- while stream 3 starves everything (§7.1.2.2).
def test_the_transcript_survives_the_screen_and_starves_under_stream_3(
    code_machine: Callable[..., Machine],
) -> None:
    scribe = StubScribe()
    output: list[str] = []
    machine = scribed(
        code_machine,
        SELECT_TRANSCRIPT
        + SCREEN_OFF
        + PRINT_HI
        + SCREEN_ON
        + SELECT_TABLE
        + PRINT_HI
        + DESELECT
        + QUIT,
        scribe,
        output=output,
    )

    machine.run()

    assert_that(scribe.pages).is_equal_to(["hi"])
    assert_that("".join(output)).is_empty()


# §7.1.1.1: the player's input echoes to the transcript, so typed
# commands appear between the game's own text.
def test_reads_echo_into_the_transcript(
    code_machine: Callable[..., Machine],
) -> None:
    scribe = StubScribe()
    machine = scribed(
        code_machine, SELECT_TRANSCRIPT + AREAD_ONLY + QUIT, scribe, "Look"
    )

    machine.run()

    assert_that(scribe.pages).is_equal_to(["look\n"])


# A game that turns the flag on in a session with no transcript
# file hears about it at the first print, address and all.
def test_the_flag_without_a_file_is_loud(
    code_machine: Callable[..., Machine],
) -> None:
    program = bytes([0xE1, 0x57, 0x10, 0x00, 0x01]) + PRINT_HI + QUIT
    machine = code_machine(program, version=5)

    with pytest.raises(ZMachineUnimplementedError, match="output stream 2"):
        machine.run()


# Stream 4 records each command whole as it finishes, and only
# while selected (§7.1.2.3).
def test_stream_4_records_finished_commands(
    code_machine: Callable[..., Machine],
) -> None:
    scribe = StubScribe()
    machine = scribed(
        code_machine,
        SELECT_COMMANDS + AREAD_ONLY + DESELECT_COMMANDS + AREAD_ONLY + QUIT,
        scribe,
        "look",
        "again",
    )

    machine.run()

    assert_that(scribe.lines).is_equal_to(["look"])


# read_char keypresses record too (§7.1.2.3): a printable key as a
# one-character line, the return key as an empty one, and a key
# with no such shape -- escape here -- not at all.
def test_read_char_keys_record_in_the_shapes_the_queue_spends(
    code_machine: Callable[..., Machine],
) -> None:
    scribe = StubScribe()
    machine = scribed(
        code_machine,
        SELECT_COMMANDS + READ_KEY + READ_KEY + READ_KEY + QUIT,
        scribe,
        "x",
        "",
        "\x1b",
    )

    machine.run()

    assert_that(scribe.lines).is_equal_to(["x", ""])


def test_selecting_stream_4_without_a_file_is_loud(
    code_machine: Callable[..., Machine],
) -> None:
    machine = code_machine(SELECT_COMMANDS + QUIT, version=4)

    with pytest.raises(ZMachineUnimplementedError, match="output stream 4"):
        machine.run()


# Deselecting either file stream never needs the files: a session
# without them simply has nothing to turn off.
def test_deselecting_the_file_streams_needs_no_files(
    code_machine: Callable[..., Machine],
) -> None:
    machine = code_machine(DESELECT_TRANSCRIPT + DESELECT_COMMANDS + QUIT, version=4)

    machine.run()

    assert_that(machine.running).is_false()


# Input stream 1 plays commands from the file, echoing each to the
# screen since no fingers typed it there; a spent file reverts to
# the keyboard mid-session (§10.2, §10.2.2).
def test_input_stream_1_plays_the_command_file(
    code_machine: Callable[..., Machine],
) -> None:
    scribe = StubScribe(plays=["Look"])
    output: list[str] = []
    # The count byte is zeroed between the reads, as a real game's
    # parser does -- a leftover count is §15 preloaded input.
    zero_count = bytes([0xE2, 0x17, 0x01, 0x61, 0x00, 0x00])
    machine = scribed(
        code_machine,
        FILE_INPUT + AREAD_ONLY + zero_count + AREAD_ONLY + QUIT,
        scribe,
        "typed",
        output=output,
    )

    machine.run()

    assert_that("".join(output)).is_equal_to("Look\n")
    assert_that(buffered_text(machine)).is_equal_to("typed")


# The played echo passes the same §7 gate as any print: with the
# transcript on, the file's command lands there once, through the
# screen, and is never recorded back onto stream 4.
def test_a_played_line_echoes_once_and_records_never(
    code_machine: Callable[..., Machine],
) -> None:
    scribe = StubScribe(plays=["look"])
    machine = scribed(
        code_machine,
        SELECT_TRANSCRIPT + SELECT_COMMANDS + FILE_INPUT + AREAD_ONLY + QUIT,
        scribe,
    )

    machine.run()

    assert_that(scribe.pages).is_equal_to(["look\n"])
    assert_that(scribe.lines).is_empty()


# Stream 1 serves keystrokes as well (§7.1.2.3 records them, so
# §10.2.1's format carries them): a one-character line is a key, an
# empty line the return key -- and stream 0 hands back the keyboard
# even with commands still unplayed.
def test_input_stream_1_serves_keystrokes(
    code_machine: Callable[..., Machine],
) -> None:
    scribe = StubScribe(plays=["x", "", "never"])
    machine = scribed(
        code_machine,
        FILE_INPUT + READ_KEY + READ_KEY + KEYBOARD_INPUT + AREAD_ONLY + QUIT,
        scribe,
        "typed",
    )

    machine.run()

    assert_that(machine.memory.read_word(GLOBAL_0)).is_equal_to(13)
    assert_that(buffered_text(machine)).is_equal_to("typed")


# A command file already dry when a keystroke is wanted falls
# straight through to the session's ordinary keys (§10.2.2).
def test_a_dry_file_hands_keystrokes_back(
    code_machine: Callable[..., Machine],
) -> None:
    scribe = StubScribe()
    machine = scribed(code_machine, FILE_INPUT + READ_KEY + QUIT, scribe, "k")

    machine.run()

    assert_that(machine.memory.read_word(GLOBAL_0)).is_equal_to(ord("k"))


# A timed line read under stream 1 keeps the patient typist: the
# live wall clock never engages, the §15 interrupt fires its once,
# and the line still comes off the file.
def test_timed_line_reads_stay_patient_under_stream_1(
    code_machine: Callable[..., Machine],
) -> None:
    scribe = StubScribe(plays=["look"])
    program = with_interrupt(
        FILE_INPUT + bytes([0xE4, 0x15, 0x01, 0x60, 0x00, 0x0A, 0x19, 0x00]) + QUIT
    )
    feed = iter(())
    machine = code_machine(
        program,
        version=5,
        scribe=scribe,
        input_source=lambda: next(feed, ""),
        timed_input_source=lambda _seconds: pytest.fail("the wall clock engaged"),
    )

    machine.memory.write_byte(TEXT_BUFFER, 20)
    machine.run()

    assert_that(buffered_text(machine)).is_equal_to("look")


# A timed read_char under stream 1 likewise: the raw keyboard never
# hears the question, and the key comes off the file.
def test_timed_keystrokes_come_off_the_file_under_stream_1(
    code_machine: Callable[..., Machine],
) -> None:
    scribe = StubScribe(plays=["x"])
    program = with_interrupt(
        FILE_INPUT + bytes([0xF6, 0x57, 0x01, 0x0A, 0x19, 0x10]) + QUIT
    )
    machine = code_machine(
        program,
        version=5,
        scribe=scribe,
        key_source=lambda _timeout: pytest.fail("the raw keyboard was asked"),
    )

    machine.run()

    assert_that(machine.memory.read_word(GLOBAL_0)).is_equal_to(ord("x"))
