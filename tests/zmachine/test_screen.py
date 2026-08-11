import pytest
from assertpy import assert_that

from voxam.errors import ZMachineUnimplementedError
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
    screen_lines = 24
    screen_columns = 80

    def __init__(self) -> None:
        self.styles: list[int] = []
        self.erased: list[int] = []
        self.buffering: list[bool] = []
        self.windows: list[tuple[str, int] | tuple[str, int, int]] = []
        self.bleeps: list[int] = []

    def write(self, text: str) -> None:
        """Discard: these programs print nothing."""

    def show_status(self, status: Status) -> None:
        """Discard: version 4 has no status line to show."""

    def set_style(self, style: int) -> None:
        self.styles.append(style)

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

    def bleep(self, number: int) -> None:
        self.bleeps.append(number)


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


# From number 3 upward, sound_effect names sampled sounds, which
# need Blorb-era machinery this interpreter does not have yet.
def test_sampled_sounds_are_a_reported_frontier() -> None:
    frontend = ScreenRecorder()
    machine = Machine(
        screen_story(bytes([0xF5, 0x7F, 0x03, 0xBA])), frontend, lambda: ""
    )

    with pytest.raises(ZMachineUnimplementedError, match="sampled sound 3"):
        machine.run()
