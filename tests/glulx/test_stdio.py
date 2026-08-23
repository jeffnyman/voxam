"""The stdio display: sessions on plain streams."""

from collections.abc import Callable
from io import StringIO

import pytest
from assertpy import assert_that

from voxam.errors import GlulxSessionEnd
from voxam.glulx.glk.api import Glk
from voxam.glulx.glk.objects import FileMode, KeyCode, TextBufferWindow, WindowType
from voxam.glulx.glk.stdio import StdioFrontend
from voxam.glulx.machine import Machine
from voxam.glulx.story import Story

IDLE = bytes([0xC0, 0x00, 0x00, 0x81, 0x20])
PLANT = 0x180

ABOVE_FIXED = 0x12


def hooked(
    text: str = "", size: tuple[int, int] | None = (60, 20)
) -> tuple[StdioFrontend, StringIO]:
    out = StringIO()

    return StdioFrontend(out, StringIO(text), size=size), out


# A script that carries clicks makes the mouse claim true, and
# each mouse event spends the marker line and one position pair --
# the very coordinates the recording's game was told. Without a
# click source the display stays honestly mouseless.
def test_scripted_clicks_answer_the_mouse() -> None:
    lines = iter(["\xfe"])
    clicks = iter([(7, 5)])
    display = StdioFrontend(
        StringIO(),
        StringIO(),
        size=(60, 20),
        input_source=lambda: next(lines),
        click_source=lambda: next(clicks, None),
    )
    window = TextBufferWindow()

    assert_that(display.mouse_input).is_true()
    assert_that(display.read_mouse(window)).is_equal_to((7, 5))

    plain, _ = hooked()

    assert_that(plain.mouse_input).is_false()
    assert_that(plain.read_mouse(window)).is_none()


# A script that speaks anything but a click while the game waits
# for one has diverged from its recording, and so have clicks that
# ran dry: either way the session ends with a loud note rather
# than replaying wrong.
def test_a_missing_click_ends_loudly() -> None:
    lines = iter(["look", "\xfe", "\xfe"])
    clicks = iter([(1, 1)])
    out = StringIO()
    display = StdioFrontend(
        out,
        StringIO(),
        size=(60, 20),
        input_source=lambda: next(lines),
        click_source=lambda: next(clicks, None),
    )
    window = TextBufferWindow()

    with pytest.raises(GlulxSessionEnd):
        display.read_mouse(window)

    assert_that(out.getvalue()).contains("a click the script does not spell")
    assert_that(display.read_mouse(window)).is_equal_to((1, 1))

    with pytest.raises(GlulxSessionEnd):
        display.read_mouse(window)


# Buffer text streams out as it accumulates, and each run prints
# exactly once no matter how often the display is flushed.
def test_buffer_text_streams_once() -> None:
    display, out = hooked()
    library = Glk(display)
    window = library.glk_window_open(None, 0, 0, WindowType.TEXT_BUFFER, 0)

    library.glk_set_window(window)
    library.glk_put_string("You are in a maze.")

    display.flush(library.root)
    display.flush(library.root)

    assert_that(out.getvalue()).is_equal_to("You are in a maze.")

    library.glk_put_string(" Again.")

    display.flush(library.root)

    assert_that(out.getvalue()).is_equal_to("You are in a maze. Again.")

    # A window with nothing to show -- a blank split -- renders as
    # nothing at all.
    library.glk_window_open(window, ABOVE_FIXED, 1, WindowType.BLANK, 0)

    display.flush(library.root)

    assert_that(out.getvalue()).is_equal_to("You are in a maze. Again.")


# A grid draws as a block above the buffer it split from -- visual
# order, not tree order -- redrawn only when its contents move,
# and skipped entirely while blank.
def test_grids_draw_as_blocks_above() -> None:
    display, out = hooked()
    library = Glk(display)
    below = library.glk_window_open(None, 0, 0, WindowType.TEXT_BUFFER, 0)
    status = library.glk_window_open(below, ABOVE_FIXED, 1, WindowType.TEXT_GRID, 0)

    display.flush(library.root)

    assert_that(out.getvalue()).is_equal_to("")

    library.glk_set_window(status)
    library.glk_put_string("Score: 10")
    library.glk_set_window(below)
    library.glk_put_string("A voice booms.")

    display.flush(library.root)

    assert_that(out.getvalue()).is_equal_to(
        "Score: 10\n" + "-" * 60 + "\nA voice booms."
    )

    # An unchanged grid stays quiet; a changed one redraws.
    display.flush(library.root)

    assert_that(out.getvalue()).is_equal_to(
        "Score: 10\n" + "-" * 60 + "\nA voice booms."
    )

    library.glk_set_window(status)
    library.glk_window_clear(status)
    library.glk_put_string("Score: 20")

    display.flush(library.root)

    assert_that(out.getvalue()).contains("Score: 20\n")


# The chosen size wins; without one, the terminal answers.
def test_the_display_measures_itself() -> None:
    display, _ = hooked()

    assert_that(display.size()).is_equal_to((60, 20))

    unsized = StdioFrontend(StringIO(), StringIO(), size=None)
    columns, lines = unsized.size()

    assert_that(columns).is_greater_than(0)
    assert_that(lines).is_greater_than(0)


# Lines come off the input cut to the buffer, keystrokes are the
# first character of a line -- a bare Return being the Return
# keycode -- and the end of input ends the session.
def test_input_reads_lines_and_keys() -> None:
    display, _ = hooked("go north\nx\n\n")
    window = TextBufferWindow()

    assert_that(display.read_line(window, 5)).is_equal_to(("go no", 0))
    assert_that(display.read_char(window)).is_equal_to(ord("x"))
    assert_that(display.read_char(window)).is_equal_to(KeyCode.RETURN)

    with pytest.raises(GlulxSessionEnd):
        display.read_line(window, 80)


# An input source replaces the stream: the harness's replay
# callable slots in, and its exhaustion ends the session the way
# end of input does. A witness hears every run of buffer text.
# A replayed key token arrives as its §3.8.4 input character and
# presses the Glk key it means: one recorded <up> moves a menu on
# either machine. Ordinary characters and the bare Return keep
# their old readings.
def test_replayed_key_tokens_press_their_glk_keys() -> None:
    lines = iter(["\x81", "\x82", "\x83", "\x84", "\x1b", "x", ""])
    display = StdioFrontend(
        StringIO(), StringIO(), size=(60, 20), input_source=lambda: next(lines)
    )
    window = TextBufferWindow()
    pressed = [display.read_char(window) for _ in range(7)]

    assert_that(pressed).is_equal_to(
        [
            KeyCode.UP,
            KeyCode.DOWN,
            KeyCode.LEFT,
            KeyCode.RIGHT,
            KeyCode.ESCAPE,
            ord("x"),
            KeyCode.RETURN,
        ]
    )


def test_the_harness_seams() -> None:
    lines = iter(["north", "south"])

    def source() -> str:
        try:
            return next(lines)
        except StopIteration:
            raise EOFError from None

    heard: list[str] = []
    out = StringIO()
    display = StdioFrontend(
        out,
        StringIO("never read\n"),
        size=(60, 20),
        input_source=source,
        witness=heard.append,
    )
    window = TextBufferWindow()

    assert_that(display.read_line(window, 80)).is_equal_to(("north", 0))
    assert_that(display.read_char(window)).is_equal_to(ord("s"))

    with pytest.raises(GlulxSessionEnd):
        display.read_line(window, 80)

    library = Glk(display)
    opened = library.glk_window_open(None, 0, 0, WindowType.TEXT_BUFFER, 0)

    library.glk_set_window(opened)
    library.glk_put_string("A hollow voice says...")

    display.flush(library.root)

    assert_that(heard).is_equal_to(["A hollow voice says..."])


# The file prompt asks in the stream: loading and saving speak
# their own verbs, an empty answer cancels, and so does the end of
# input.
def test_the_file_prompt_asks_in_the_stream() -> None:
    display, out = hooked("saves\n\n")

    assert_that(display.prompt_file(0, FileMode.READ)).is_equal_to("saves")
    assert_that(out.getvalue()).contains("Load from which file? ")
    assert_that(display.prompt_file(0, FileMode.WRITE)).is_none()
    assert_that(out.getvalue()).contains("Save to which file? ")
    assert_that(display.prompt_file(0, FileMode.WRITE)).is_none()


# The machine speaks through the display end to end: opcodes print
# into the window, and a select reads the player's line back --
# with no Glk echo, because the terminal already showed the
# typing.
def test_a_session_runs_end_to_end(image: Callable[..., bytes]) -> None:
    display, out = hooked("east\n")
    library = Glk(display)
    machine = Machine(Story(image(code=IDLE)), glk=library)

    if machine.bridge is None:
        pytest.fail("the bridge is installed")

    window = library.glk_window_open(None, 0, 0, WindowType.TEXT_BUFFER, 0)

    library.glk_set_window(window)

    machine.memory.write_run(
        PLANT,
        bytes([0x81, 0x49, 0x11, 0x02, 0x00])
        + bytes([0x70, 0x01, 0x48])
        + bytes([0x70, 0x01, 0x69])
        + bytes([0x81, 0x20]),
    )

    machine.pc = PLANT

    machine.run(limit=10)

    display.flush(library.root)

    assert_that(out.getvalue()).is_equal_to("Hi")

    held = [0] * 8

    library.glk_request_line_event(window, held, 0)

    event = machine.bridge.perform(0x00C0, [0x2C0])

    assert_that(event).is_equal_to(0)
    assert_that(held[:4]).is_equal_to([ord(ch) for ch in "east"])

    display.flush(library.root)

    assert_that(out.getvalue()).is_equal_to("Hi")
