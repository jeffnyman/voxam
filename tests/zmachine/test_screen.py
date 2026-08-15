from collections.abc import Callable, Sequence

from assertpy import assert_that

from voxam.frontend import Status
from voxam.zmachine.machine import Machine
from voxam.zmachine.story import Story


class ScreenRecorder:
    """A frontend remembering every screen operation it is handed."""

    has_status_line = False
    has_screen_splitting = False
    has_bold = True
    has_italic = True
    has_fixed_pitch = True
    has_timed_input = False
    has_sounds = False
    has_character_graphics = False
    has_colours = False
    screen_lines = 24
    screen_columns = 80

    def __init__(self) -> None:
        self.styles: list[int] = []
        self.fonts: list[int] = []
        self.colours: list[tuple[int, int]] = []
        self.erased: list[int] = []
        self.buffering: list[bool] = []
        self.windows: list[tuple[str, int] | tuple[str, int, int]] = []
        self.bleeps: list[int] = []
        self.rectangles: list[tuple[str, ...]] = []
        self.cursor = (1, 1)
        self.sounds: list[tuple[int, int, int | None]] = []
        self.stops: list[int | None] = []
        self.waits = 0
        self.playing = False
        self.refuses: set[int] = set()
        self.finishes: list[bool] = []

    def write(self, text: str) -> None:
        """Discard: these programs print nothing."""

    def write_rectangle(self, rows: Sequence[str]) -> None:
        self.rectangles.append(tuple(rows))

    def show_status(self, status: Status) -> None:
        """Discard: version 4 has no status line to show."""

    def set_style(self, style: int) -> None:
        self.styles.append(style)

    def set_font(self, font: int) -> None:
        self.fonts.append(font)

    def set_colour(self, foreground: int, background: int) -> None:
        self.colours.append((foreground, background))

    def erase_window(self, window: int) -> None:
        self.erased.append(window)

    def set_buffering(self, buffered: bool) -> None:
        self.buffering.append(buffered)

    def split_window(self, lines: int) -> None:
        self.windows.append(("split", lines))

    def set_window(self, window: int) -> None:
        self.windows.append(("select", window))

    def set_cursor(self, line: int, column: int) -> None:
        self.windows.append(("cursor", line, column))

    def cursor_position(self) -> tuple[int, int]:
        return self.cursor

    def bleep(self, number: int) -> None:
        self.bleeps.append(number)

    def play_sound(self, number: int, volume: int, repeats: int | None) -> bool:
        self.sounds.append((number, volume, repeats))

        return number not in self.refuses

    def stop_sound(self, number: int | None) -> None:
        self.stops.append(number)

    def sound_playing(self) -> bool:
        return self.playing

    def sound_finished(self) -> bool:
        return self.finishes.pop(0) if self.finishes else False

    def wait_for_sound(self) -> None:
        self.waits += 1


def screen_story(code: bytes, version: int = 4) -> Story:
    data = bytearray(512)
    data[0] = version
    data[0x04:0x06] = (0x01C0).to_bytes(2, "big")
    data[0x06:0x08] = (0x0040).to_bytes(2, "big")
    data[0x0C:0x0E] = (0x0100).to_bytes(2, "big")
    data[0x0E:0x10] = (0x01C0).to_bytes(2, "big")
    data[0x40 : 0x40 + len(code)] = code

    return Story(bytes(data))


def run(code: bytes) -> ScreenRecorder:
    frontend = ScreenRecorder()
    machine = Machine(screen_story(code), frontend, lambda: "")

    machine.run()

    return frontend


# The style bitmask passes through untouched: bold (2), then back
# to roman (0) (§8.7).
def test_text_styles_reach_the_frontend() -> None:
    frontend = run(bytes([0xF1, 0x7F, 0x02, 0xF1, 0x7F, 0x00, 0xBA]))

    assert_that(frontend.styles).is_equal_to([2, 0])


# erase_window's operand is signed: $ffff means -1, unsplit and
# clear everything; $fffe means -2, clear without unsplitting (§8.7).
def test_erasures_arrive_signed() -> None:
    frontend = run(
        bytes(
            [
                0xED,
                0x3F,
                0xFF,
                0xFF,
                0xED,
                0x3F,
                0xFF,
                0xFE,
                0xED,
                0x7F,
                0x00,
                0xED,
                0x7F,
                0x01,
                0xBA,
            ]
        )
    )

    assert_that(frontend.erased).is_equal_to([-1, -2, 0, 1])


# buffer_mode's flag arrives as a truth: on, then off (§8.7).
def test_buffering_toggles_reach_the_frontend() -> None:
    frontend = run(bytes([0xF2, 0x7F, 0x01, 0xF2, 0x7F, 0x00, 0xBA]))

    assert_that(frontend.buffering).is_equal_to([True, False])


# A status-line redraw in miniature, the way Version 4 games do it
# themselves: split three lines off, select the upper window, place
# the cursor, then come back down (§8.7.2).
def test_window_operations_reach_the_frontend_in_order() -> None:
    frontend = run(
        bytes(
            [
                0xEA,
                0x7F,
                0x03,
                0xEB,
                0x7F,
                0x01,
                0xEF,
                0x5F,
                0x01,
                0x02,
                0xEB,
                0x7F,
                0x00,
                0xBA,
            ]
        )
    )

    assert_that(frontend.windows).is_equal_to(
        [("split", 3), ("select", 1), ("cursor", 1, 2), ("select", 0)]
    )


# Numbers 1 and 2 are the interpreter's own bleeps, and a bare
# sound_effect means bleep 1 (§9).
def test_bleeps_reach_the_frontend() -> None:
    frontend = run(bytes([0xF5, 0x7F, 0x02, 0xF5, 0xFF, 0xBA]))

    assert_that(frontend.bleeps).is_equal_to([2, 1])


# From number 3 upward, sound_effect names sampled sounds. On a
# frontend that has honestly cleared the header's sound request,
# they pass in the conforming quiet The Lurking Horror and Sherlock
# were shipped to accept: no bleep, no halt, play on (§9, §11.1).
def test_sampled_sounds_pass_in_conforming_silence() -> None:
    frontend = ScreenRecorder()
    machine = Machine(
        screen_story(bytes([0xF5, 0x7F, 0x03, 0xBA])), frontend, lambda: ""
    )

    machine.run()

    assert_that(frontend.bleeps).is_empty()


def sounded_run(code: bytes, version: int = 5) -> ScreenRecorder:
    """Run code on a frontend claiming sound, and hand it back."""

    frontend = ScreenRecorder()
    frontend.has_sounds = True
    machine = Machine(screen_story(code, version=version), frontend, lambda: "")

    machine.run()

    return frontend


# The full §9.4 forms reach a frontend with a speaker: a start
# decodes its volume word -- 255 is loudest, the high byte counts
# total plays with 255 meaning until stopped, 15 clamps to §9.3's
# 8 -- a stop names its sound, number 0 stops them all, and The
# Lurking Horror's bogus effect 8 pardons to nothing (§15
# sound_effect, §9 remarks).
def test_sampled_sound_effects_drive_the_frontend() -> None:
    frontend = sounded_run(
        bytes(
            [
                *[0xF5, 0x51, 0x03, 0x02, 0x00, 0xFF, 0x00],
                *[0xF5, 0x51, 0x04, 0x02, 0xFF, 0x0F, 0x00],
                *[0xF5, 0x5F, 0x05, 0x02],
                *[0xF5, 0x5F, 0x03, 0x03],
                *[0xF5, 0x5F, 0x00, 0x04],
                *[0xF5, 0x5F, 0x04, 0x08],
                0xBA,
            ]
        )
    )

    assert_that(frontend.sounds).is_equal_to([(3, 8, 1), (4, 8, 0), (5, 8, 1)])
    assert_that(frontend.stops).is_equal_to([3, None])


# A Version 3 game cannot speak repeats -- §15 keeps the high byte
# zero -- so the machine passes None and the Blorb's Loop chunk
# decides; a volume of zero clamps up to §9.3's quietest 1.
def test_version_3_sounds_leave_repeats_to_the_blorb() -> None:
    frontend = sounded_run(
        bytes(
            [
                *[0xF5, 0x57, 0x03, 0x02, 0x08],
                *[0xF5, 0x57, 0x04, 0x02, 0x00],
                0xBA,
            ]
        ),
        version=3,
    )

    assert_that(frontend.sounds).is_equal_to([(3, 8, None), (4, 1, None)])


# The §9 remarks' pacing rule: a second sound started while one
# begun since the last keyboard input still plays waits for that
# one to finish a cycle before replacing it.
def test_a_second_sound_in_one_round_waits_a_cycle() -> None:
    frontend = ScreenRecorder()
    frontend.has_sounds = True
    frontend.playing = True
    machine = Machine(
        screen_story(
            bytes(
                [
                    *[0xF5, 0x51, 0x03, 0x02, 0x00, 0xFF, 0x00],
                    *[0xF5, 0x51, 0x04, 0x02, 0x00, 0xFF, 0x00],
                    0xBA,
                ]
            ),
            version=5,
        ),
        frontend,
        lambda: "",
    )

    machine.run()

    assert_that(frontend.waits).is_equal_to(1)
    assert_that(frontend.sounds).is_length(2)


# A sound that ends of its own accord calls its end-of-sound
# routine, once, between instructions (§9.4.4); a start the
# frontend refused -- The Lurking Horror asks for sound 4095 --
# arms no routine at all.
def test_the_end_of_sound_routine_fires_on_natural_endings() -> None:
    routine = bytes([0x00, 0xF1, 0x7F, 0x02, 0xB0])
    heard = screen_story(
        bytes(
            [
                *[0xF5, 0x51, 0x03, 0x02, 0x00, 0xFF, 0x70],
                *[0xF1, 0x7F, 0x00],
                0xBA,
            ]
        ),
        version=5,
    )
    data = bytearray(heard.data)
    data[0x1C0 : 0x1C0 + len(routine)] = routine
    frontend = ScreenRecorder()
    frontend.has_sounds = True
    frontend.finishes = [False, True]
    machine = Machine(Story(bytes(data)), frontend, lambda: "")

    machine.run()

    assert_that(frontend.styles).is_equal_to([0, 2])

    refused = ScreenRecorder()
    refused.has_sounds = True
    refused.refuses = {4095}
    refused.finishes = [True]
    machine = Machine(
        screen_story(
            bytes([*[0xF5, 0x11, 0x0F, 0xFF, 0x02, 0x00, 0xFF, 0x70], 0xBA]),
            version=5,
        ),
        refused,
        lambda: "",
    )

    machine.run()

    assert_that(refused.sounds).is_equal_to([(4095, 8, 1)])
    assert_that(refused.styles).is_empty()


# Colour requests on a frontend that truthfully declares no colour
# are no-ops by the spec's own conditional -- "if coloured text is
# available" (§8.3.1) -- for both the classic and the 15-bit form.
def test_colour_requests_are_no_ops_without_colour(
    code_machine: Callable[..., Machine],
) -> None:
    program = bytes(
        [0x7B, 0x02, 0x04, 0xBE, 0x0D, 0x2F, 0x7F, 0xFF, 0x00, 0x0D, 0x10, 0x2A, 0xBA]
    )
    machine = code_machine(program, version=5)

    machine.run()

    assert_that(machine.memory.read_word(0x100)).is_equal_to(42)


# Where the frontend claims colours, the §8.3.1 pair is forwarded:
# red type on a cyan screen, exactly as asked.
def test_colours_reach_a_frontend_that_claims_them() -> None:
    frontend = ScreenRecorder()
    frontend.has_colours = True
    machine = Machine(
        screen_story(bytes([0x1B, 0x03, 0x08, 0xBA]), version=5), frontend, lambda: ""
    )

    machine.run()

    assert_that(frontend.colours).is_equal_to([(3, 8)])


# The 15-bit form is its own claim, made in the header extension's
# flags, and Voxam does not make it: set_true_colour stays quiet
# even where the classic colours are on offer (§8.3.7).
def test_true_colour_stays_quiet_even_with_colours() -> None:
    frontend = ScreenRecorder()
    frontend.has_colours = True
    program = bytes([0xBE, 0x0D, 0x2F, 0x7F, 0xFF, 0x00, 0xBA])
    machine = Machine(screen_story(program, version=5), frontend, lambda: "")

    machine.run()

    assert_that(frontend.colours).is_empty()


# set_font grants the fonts on offer and stores the font each one
# replaced, always positive: font 3 on a graphics-claiming frontend
# stores the normal font 1 it displaced, font 0 asks which font is
# current without changing it, and returning to font 1 stores the 3
# it replaces (§15 set_font). Only the granted changes reach the
# frontend.
def test_set_font_stores_the_font_it_replaces() -> None:
    frontend = ScreenRecorder()
    frontend.has_character_graphics = True
    program = bytes(
        [
            *[0xBE, 0x04, 0x7F, 0x03, 0x10],
            *[0xBE, 0x04, 0x7F, 0x00, 0x11],
            *[0xBE, 0x04, 0x7F, 0x01, 0x12],
            0xBA,
        ]
    )
    machine = Machine(screen_story(program, version=5), frontend, lambda: "")

    machine.run()

    assert_that(machine.memory.read_word(0x100)).is_equal_to(1)
    assert_that(machine.memory.read_word(0x102)).is_equal_to(3)
    assert_that(machine.memory.read_word(0x104)).is_equal_to(3)
    assert_that(frontend.fonts).is_equal_to([3, 1])


# The refusals all store 0 and change nothing: character graphics
# where none were claimed (§8.1.5.1), the picture font by
# instruction (§8.1.4), and the numbers no Standard has yet defined
# (§8.1.6). The fixed-pitch font is always granted -- a character
# terminal is Courier all the way down (§8.1.2).
def test_set_font_refuses_what_is_not_on_offer(
    code_machine: Callable[..., Machine],
) -> None:
    program = bytes(
        [
            *[0xBE, 0x04, 0x7F, 0x03, 0x10],
            *[0xBE, 0x04, 0x7F, 0x02, 0x11],
            *[0xBE, 0x04, 0x7F, 0x63, 0x12],
            *[0xBE, 0x04, 0x7F, 0x04, 0x13],
            0xBA,
        ]
    )
    machine = code_machine(program, version=5)

    machine.run()

    assert_that(machine.memory.read_word(0x100)).is_equal_to(0)
    assert_that(machine.memory.read_word(0x102)).is_equal_to(0)
    assert_that(machine.memory.read_word(0x104)).is_equal_to(0)
    assert_that(machine.memory.read_word(0x106)).is_equal_to(1)


# §15 print_table: the rectangle reaches a screen frontend as rows,
# to spread right and down from wherever its cursor stands -- the
# shape Beyond Zork's map is stamped in.
def test_print_table_hands_the_frontend_a_rectangle() -> None:
    frontend = ScreenRecorder()
    machine = Machine(
        screen_story(bytes([0xFE, 0x17, 0x01, 0x20, 0x02, 0x02, 0xBA]), version=5),
        frontend,
        lambda: "",
    )

    for offset, character in enumerate("ABCD"):
        machine.memory.write_byte(0x120 + offset, ord(character))

    machine.run()

    assert_that(frontend.rectangles).is_equal_to([("AB", "CD")])


# A restart returns the font to normal along with the rest of the
# interpreter's bookkeeping, and tells the frontend so its screen
# agrees (§6.1.3). The program rides Flags 2, the one word restart
# preserves: the first run sets a spare bit, chooses font 3, and
# restarts; the second finds the bit, asks set_font 0 which font
# survived, and quits.
def test_restart_returns_the_font_to_normal() -> None:
    frontend = ScreenRecorder()
    frontend.has_character_graphics = True
    program = bytes(
        [
            *[0x10, 0x00, 0x11, 0x00],  # loadb 0 $11 -> sp
            *[0xA0, 0x00, 0xC8],  # jz sp ?first-run
            *[0xBE, 0x04, 0x7F, 0x00, 0x10],  # set_font 0 -> g0
            0xBA,  # quit
            *[0xE2, 0x57, 0x00, 0x11, 0x01],  # storeb 0 $11 1
            *[0xBE, 0x04, 0x7F, 0x03, 0x00],  # set_font 3 -> sp
            0xB7,  # restart
        ]
    )
    machine = Machine(screen_story(program, version=5), frontend, lambda: "")

    machine.run()

    assert_that(machine.memory.read_word(0x100)).is_equal_to(1)
    assert_that(frontend.fonts).is_equal_to([3, 1])


# A Version 6 boot stamps the whole header truthfully: unit words
# and a 1-by-1 font -- ZIPTEST divides one by the other before its
# first menu -- colours, the Flags 1 capability bits (no pictures,
# sound as claimed), and the Flags 2 requests the interpreter
# cannot oblige cleared: pictures, mouse, and menus (§11.1).
def v6_story(code: bytes, flags_2: int = 0) -> Story:
    """A Version 6 story: main routine at $100, globals at $80."""

    data = bytearray(512)
    data[0] = 6
    data[0x04:0x06] = (0x01C0).to_bytes(2, "big")
    data[0x06:0x08] = (0x0040).to_bytes(2, "big")
    data[0x0C:0x0E] = (0x0080).to_bytes(2, "big")
    data[0x0E:0x10] = (0x01C0).to_bytes(2, "big")
    data[0x10:0x12] = flags_2.to_bytes(2, "big")
    data[0x100] = 0x00
    data[0x101 : 0x101 + len(code)] = code

    return Story(bytes(data))


def test_a_version_6_boot_stamps_the_header() -> None:
    frontend = ScreenRecorder()
    frontend.has_sounds = True
    machine = Machine(v6_story(bytes([0xBA]), flags_2=0x0128), frontend, lambda: "")

    machine.run()

    memory = machine.memory

    assert_that(memory.read_word(0x22)).is_equal_to(80)
    assert_that(memory.read_word(0x24)).is_equal_to(24)
    assert_that(memory.read_byte(0x26)).is_equal_to(1)
    assert_that(memory.read_byte(0x27)).is_equal_to(1)

    flags_1 = memory.read_byte(0x01)

    assert_that(flags_1 & 0x02).is_zero()
    assert_that(flags_1 & 0x20).is_equal_to(0x20)
    assert_that(memory.read_word(0x10) & 0x0128).is_zero()


# In Version 6 any of the eight windows may be selected, but the
# character glass hears only about the two it renders: selecting
# window 5 stays in the §8.8 ledger, selecting window 1 reaches
# the frontend (§8.8.3).
def test_v6_window_selection_reaches_the_glass_for_two() -> None:
    frontend = ScreenRecorder()
    machine = Machine(
        v6_story(bytes([0xEB, 0x7F, 0x05, 0xEB, 0x7F, 0x01, 0xBA])),
        frontend,
        lambda: "",
    )

    machine.run()

    assert_that(frontend.windows).is_equal_to([("select", 1)])


# nop does nothing, on purpose (§15) -- unneeded by any story
# until ZIPTEST's Call/Stacks test executed one mid-suite.
def test_nop_does_nothing() -> None:
    frontend = run(bytes([0xB4, 0xBA]))

    assert_that(frontend.styles).is_empty()
    assert_that(frontend.bleeps).is_empty()


# get_cursor writes the row into word 0 of its array and the
# column into word 1 -- no size word, the array is not a table
# (§15 get_cursor); the answer is the frontend's own.
def test_get_cursor_writes_row_and_column() -> None:
    frontend = ScreenRecorder()
    frontend.cursor = (3, 7)
    machine = Machine(
        screen_story(bytes([0xF0, 0x7F, 0x60, 0xBA])), frontend, lambda: ""
    )

    machine.run()

    assert_that(machine.memory.read_word(0x60)).is_equal_to(3)
    assert_that(machine.memory.read_word(0x62)).is_equal_to(7)
