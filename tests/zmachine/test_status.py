from collections.abc import Sequence

from assertpy import assert_that

from voxam.frontend import Status
from voxam.zmachine.header import (
    FLAGS_1,
    NO_STATUS_LINE_BIT,
    SCREEN_SPLIT_BIT,
    TIME_STATUS_BIT,
)
from voxam.zmachine.machine import Machine
from voxam.zmachine.story import Story

TABLE_BASE = 0x400
GLOBALS_BASE = 0x100
DICTIONARY_BASE = 0x150
TEXT_BUFFER = 0x200
PARSE_BUFFER = 0x220

# show_status, print "hi", quit: the status must not disturb the
# ordinary print stream around it.
SHOW_STATUS = bytes([0xBC, 0xB2, 0xB5, 0xC5, 0xBA])
SREAD = bytes([0xE4, 0x0F, 0x02, 0x00, 0x02, 0x20, 0xBA])

# 'h' and 'i' in one terminated word (§3.5.3).
HI = bytes([0xB5, 0xC5])


class Recorder:
    """A frontend with a status line, remembering all it is shown.

    Its claims are deliberately distinctive, so the boot-time header
    stamp can be traced back to the frontend that made them.
    """

    has_status_line = True
    has_screen_splitting = False
    has_bold = True
    has_italic = False
    has_fixed_pitch = True
    has_timed_input = True
    has_sounds = False
    has_character_graphics = False
    has_colours = False
    has_pictures = False
    has_stage = False
    screen_lines = 24
    screen_columns = 64
    font_width = 1
    font_height = 1

    def __init__(self) -> None:
        self.events: list[str] = []
        self.statuses: list[Status] = []
        self.text: list[str] = []

    def picture_data(self, number: int) -> tuple[int, int] | None:  # noqa: ARG002
        """No pictures: the status tests never ask."""

        return None

    def picture_census(self) -> tuple[int, int]:
        """A census of zero pictures, release zero."""

        return 0, 0

    def draw_picture(self, number: int, line: int, column: int) -> None:
        """Discard: the status tests never draw."""

    def place_window(
        self, window: int, line: int, column: int, height: int, width: int
    ) -> None:
        """Discard: the status tests have no stage."""

    def scroll_window(self, window: int, pixels: int) -> None:
        """Discard: the status tests have no stage."""

    def set_margins(self, window: int, left: int, right: int) -> None:
        """Discard: the status tests have no stage."""

    def set_line_count(self, window: int, count: int) -> None:
        """Discard: the status tests have no stage."""

    def erase_picture(self, number: int, line: int, column: int) -> None:
        """Discard: the status tests never erase pictures."""

    def write(self, text: str) -> None:
        self.events.append("write")
        self.text.append(text)

    def show_status(self, status: Status) -> None:
        self.events.append("status")
        self.statuses.append(status)

    def set_style(self, style: int) -> None:
        """Discard: the status tests never change styles."""

    def set_font(self, font: int) -> None:
        """Discard: the status tests never change fonts."""

    def set_colour(self, foreground: int, background: int) -> None:
        """Discard: the status tests never change colours."""

    def write_rectangle(self, rows: Sequence[str]) -> None:
        """Discard: the status tests never print rectangles."""

    def erase_window(self, window: int) -> None:
        """Discard: the status tests never erase."""

    def erase_line(self, pixels: int | None = None) -> None:
        """Discard: the status tests never erase a line."""

    def begin_input(self) -> None:
        """Discard: the status tests never take timed input."""

    def resume_input(self) -> None:
        """Discard: the status tests never take timed input."""

    def abandon_input(self) -> None:
        """Discard: the status tests never take timed input."""

    def set_buffering(self, buffered: bool) -> None:
        """Discard: the status tests never toggle buffering."""

    def split_window(self, lines: int) -> None:
        """Discard: the status tests never split."""

    def set_window(self, window: int) -> None:
        """Discard: the status tests never change windows."""

    def set_cursor(self, line: int, column: int) -> None:
        """Discard: the status tests never move the cursor."""

    def cursor_position(self) -> tuple[int, int]:
        """A stream's cursor rests at the origin."""

        return (1, 1)

    def bleep(self, number: int) -> None:
        """Discard: the status tests never make a sound."""

    def play_sound(self, number: int, volume: int, repeats: int | None) -> bool:
        """Refuse: the status tests never play a sound."""

        del number, volume, repeats

        return False

    def stop_sound(self, number: int | None) -> None:
        """Discard: nothing ever plays here."""

    def sound_playing(self) -> bool:
        """No sound is ever sounding here."""

        return False

    def sound_finished(self) -> bool:
        """No sound ever ends here."""

        return False

    def wait_for_sound(self) -> None:
        """Return at once: there is never a cycle to wait out."""


class Splitter(Recorder):
    """A frontend that can also split the screen (§8.6)."""

    has_screen_splitting = True


class GraphicsRecorder(Recorder):
    """A frontend that can also draw the §16 font."""

    has_character_graphics = True


class ColourRecorder(Recorder):
    """A frontend that can also show coloured text (§8.3)."""

    has_colours = True


def status_story(code: bytes, version: int = 3, flags: int = 0) -> Story:
    """Build a story whose object 1 is named "hi" (§12.3.1).

    The object table sits at $400: 31 property defaults, one Version
    3 entry, and its property table opening with the short name.
    """

    data = bytearray(2048)
    data[0] = version
    data[1] = flags
    data[0x04:0x06] = (0x0700).to_bytes(2, "big")
    data[0x06:0x08] = (0x0040).to_bytes(2, "big")
    data[0x0A:0x0C] = TABLE_BASE.to_bytes(2, "big")
    data[0x0C:0x0E] = GLOBALS_BASE.to_bytes(2, "big")
    data[0x0E:0x10] = (0x0700).to_bytes(2, "big")
    data[0x40 : 0x40 + len(code)] = code

    entry = TABLE_BASE + 62
    properties = entry + 9
    data[entry + 7 : entry + 9] = properties.to_bytes(2, "big")
    data[properties] = len(HI) // 2
    data[properties + 1 : properties + 1 + len(HI)] = HI

    return Story(bytes(data))


def plant_empty_dictionary(machine: Machine) -> None:
    machine.memory.write_word(0x08, DICTIONARY_BASE)
    machine.memory.write_byte(DICTIONARY_BASE, 0)
    machine.memory.write_byte(DICTIONARY_BASE + 1, 7)
    machine.memory.write_word(DICTIONARY_BASE + 2, 0)


def machine_with(
    frontend: Recorder,
    *,
    code: bytes = SHOW_STATUS,
    flags: int = 0,
    score: int = 0,
    turns: int = 0,
) -> Machine:
    machine = Machine(status_story(code, 3, flags), frontend, input_source=lambda: "go")
    machine.memory.write_word(GLOBALS_BASE, 1)
    machine.memory.write_word(GLOBALS_BASE + 2, score & 0xFFFF)
    machine.memory.write_word(GLOBALS_BASE + 4, turns)

    return machine


# The location is the short name of the object in the first global,
# and the numbers are the second and third globals (§8.2.2, §8.2.3.1).
# A negative score is legitimate and must survive signed (§8.2.3.1).
def test_show_status_assembles_the_globals() -> None:
    frontend = Recorder()
    machine = machine_with(frontend, score=-3, turns=42)

    machine.run()

    assert_that(frontend.statuses).is_equal_to(
        [Status(location="hi", score=-3, turns=42, time_game=False)]
    )
    assert_that(frontend.events).is_equal_to(["status", "write"])
    assert_that(frontend.text).is_equal_to(["hi"])
    assert_that(frontend.picture_data(1)).is_none()
    assert_that(frontend.picture_census()).is_equal_to((0, 0))


# With bit 1 of Flags 1 set, the same globals are a clock reading:
# hours and minutes instead of score and turns (§8.2.3.2).
def test_a_time_game_reports_a_clock() -> None:
    frontend = Recorder()
    machine = machine_with(frontend, flags=TIME_STATUS_BIT, score=23, turns=59)

    machine.run()

    assert_that(frontend.statuses).is_equal_to(
        [Status(location="hi", score=23, turns=59, time_game=True)]
    )


# In Versions 1 to 3 the status line is redisplayed before the player
# types (§8.2, §15 read): the status must reach the frontend before
# the input source is drained.
def test_sread_shows_the_status_before_reading() -> None:
    frontend = Recorder()
    events = frontend.events

    def source() -> str:
        events.append("input")

        return ""

    machine = Machine(status_story(SREAD), frontend, input_source=source)
    machine.memory.write_word(GLOBALS_BASE, 1)
    plant_empty_dictionary(machine)
    machine.memory.write_byte(TEXT_BUFFER, 10)
    machine.memory.write_byte(PARSE_BUFFER, 2)

    machine.run()

    assert_that(events).is_equal_to(["status", "input"])


# From Version 4 there is no status line at all (§8.2): even a capable
# frontend hears nothing from sread.
def test_v4_reading_shows_no_status() -> None:
    frontend = Recorder()
    machine = Machine(status_story(SREAD, version=4), frontend, lambda: "")
    plant_empty_dictionary(machine)
    machine.memory.write_byte(TEXT_BUFFER, 10)
    machine.memory.write_byte(PARSE_BUFFER, 2)

    machine.run()

    assert_that(frontend.statuses).is_empty()


# Booting stamps the frontend's honest capabilities into a Version 3
# header: bit 4 is set when there is NO status line, bit 5 when the
# screen can split (§11.1).
def test_boot_declares_capabilities_in_the_header() -> None:
    lined = machine_with(Recorder())
    flags = lined.memory.read_byte(FLAGS_1)

    assert_that(flags & NO_STATUS_LINE_BIT).is_zero()
    assert_that(flags & SCREEN_SPLIT_BIT).is_zero()

    splitter = machine_with(Splitter())
    flags = splitter.memory.read_byte(FLAGS_1)

    assert_that(flags & SCREEN_SPLIT_BIT).is_not_zero()


# From Version 4 the boot stamp changes vocabulary: interpreter
# identity, screen size, and typography, all traceable to the
# frontend's distinctive claims (§11.1, §11.1.3, §8.4).
def test_v4_boot_introduces_the_interpreter() -> None:
    machine = Machine(status_story(bytes([0xBA]), version=5), Recorder(), lambda: "")

    assert_that(machine.memory.read_byte(0x1E)).is_equal_to(6)
    assert_that(machine.memory.read_byte(0x1F)).is_equal_to(ord("V"))
    assert_that(machine.memory.read_byte(0x20)).is_equal_to(24)
    assert_that(machine.memory.read_byte(0x21)).is_equal_to(64)
    assert_that(machine.memory.read_byte(FLAGS_1)).is_equal_to(0x94)


# A Version 5 game may arrive asking for the §16 character graphics
# font in Flags 2. The boot stamp answers honestly: the request is
# cleared on a frontend without the font and left standing on one
# with it, and the unit measurements -- screen size in units at
# $22/$24, the 1-by-1 font at $26/$27 -- are recorded either way.
# Beyond Zork lays out its windows from the unit words (§8.1.5.1,
# §8.4.3, §8.1.1).
def test_v5_boot_answers_the_graphics_font_request() -> None:
    data = bytearray(status_story(bytes([0xBA]), version=5).data)
    data[0x11] = 0x08
    story = Story(bytes(data))

    plain = Machine(story, Recorder(), lambda: "")

    assert_that(plain.memory.read_byte(0x11) & 0x08).is_zero()
    assert_that(plain.memory.read_word(0x22)).is_equal_to(64)
    assert_that(plain.memory.read_word(0x24)).is_equal_to(24)
    assert_that(plain.memory.read_byte(0x26)).is_equal_to(1)
    assert_that(plain.memory.read_byte(0x27)).is_equal_to(1)

    graphical = Machine(story, GraphicsRecorder(), lambda: "")

    assert_that(graphical.memory.read_byte(0x11) & 0x08).is_equal_to(0x08)


# A Version 5 boot answers the colour question both ways: bit 0 of
# Flags 1 says whether colours are on offer, and the default
# background and foreground codes land at $2c/$2d either way --
# black and white are still a background and a foreground (§8.3.2,
# §8.3.3).
def test_v5_boot_declares_the_colour_offer() -> None:
    story = status_story(bytes([0xBA]), version=5)

    plain = Machine(story, Recorder(), lambda: "")

    assert_that(plain.memory.read_byte(FLAGS_1) & 0x01).is_zero()
    assert_that(plain.memory.read_byte(0x2C)).is_equal_to(2)
    assert_that(plain.memory.read_byte(0x2D)).is_equal_to(9)

    coloured = Machine(story, ColourRecorder(), lambda: "")

    assert_that(coloured.memory.read_byte(FLAGS_1) & 0x01).is_equal_to(0x01)


# Versions 1 and 2 predate every capability bit: their headers boot
# untouched.
def test_early_boots_leave_the_header_alone() -> None:
    machine = Machine(status_story(bytes([0xBA]), version=1), Recorder(), lambda: "")

    assert_that(machine.memory.read_byte(FLAGS_1)).is_zero()
    assert_that(machine.memory.read_byte(0x20)).is_zero()


# The recorder's sound seam exists only to satisfy the frontend
# protocol; poked directly, it refuses and reports nothing.
def test_the_recorder_sound_seam_is_inert() -> None:
    frontend = Recorder()

    frontend.stop_sound(None)
    frontend.wait_for_sound()

    assert_that(frontend.play_sound(3, 8, 1)).is_false()
    assert_that(frontend.sound_playing()).is_false()
    assert_that(frontend.sound_finished()).is_false()
    assert_that(frontend.cursor_position()).is_equal_to((1, 1))
