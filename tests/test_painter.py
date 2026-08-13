from assertpy import assert_that

from voxam.frontend import Status
from voxam.painter import FALLBACK_COLUMNS, FALLBACK_LINES, ScreenFrontend
from voxam.screen import BOLD, ITALIC, REVERSE, UPPER


class StubTerminal:
    """A terminal that emits readable markers instead of escapes."""

    width = 30
    height = 8
    normal = "<n>"
    reverse = "<rev>"
    bold = "<b>"
    italic = "<i>"
    red = "<red>"
    on_green = "<on_green>"

    def move_xy(self, x: int, y: int) -> str:
        return f"<@{x},{y}>"


def painted(version: int = 5, line: str = "look") -> tuple[ScreenFrontend, list[str]]:
    out: list[str] = []
    frontend = ScreenFrontend(
        version, terminal=StubTerminal(), out=out.append, read=lambda: line
    )

    return frontend, out


# A write lands in the model and the damaged row is repainted at
# its own position, ending in the normal sequence.
def test_writes_repaint_the_damaged_row() -> None:
    frontend, out = painted()

    frontend.write("hello")

    stream = "".join(out)

    assert_that(stream).contains("<@0,0>")
    assert_that(stream).contains("hello")
    assert_that(frontend.model.row_text(1)).is_equal_to("hello")


# The Version 3 status line paints the top row in reverse video
# (§8.2).
def test_the_status_line_paints_in_reverse() -> None:
    frontend, out = painted(version=3)

    frontend.show_status(Status("Kitchen", 10, 2, time_game=False))

    stream = "".join(out)

    assert_that(stream).contains("<@0,0>")
    assert_that(stream).contains("<rev>")
    assert_that(stream).contains("Kitchen")


# Styles and colours dress the painted cells with their sequences
# (§8.7.1, §8.3.1), and a run of same-dressed cells pays for its
# sequences once.
def test_styles_and_colours_reach_the_glass() -> None:
    frontend, out = painted()

    frontend.set_style(BOLD)
    frontend.set_style(ITALIC)
    frontend.set_colour(3, 4)
    frontend.write("dressed")

    stream = "".join(out)

    assert_that(stream).contains("<b>")
    assert_that(stream).contains("<i>")
    assert_that(stream).contains("<red>")
    assert_that(stream).contains("<on_green>")
    assert_that(stream.count("<red>")).is_equal_to(1)


# Reverse video passes through as its own sequence (§8.7.1).
def test_reverse_video_reaches_the_glass() -> None:
    frontend, out = painted()

    frontend.set_style(REVERSE)
    frontend.write("dark")

    assert_that("".join(out)).contains("<rev>")


# Window operations flow through the model and park the terminal
# cursor where the model's cursor stands.
def test_window_operations_park_the_cursor() -> None:
    frontend, out = painted()

    frontend.split_window(2)
    frontend.set_window(UPPER)
    frontend.set_cursor(2, 5)
    out.clear()
    frontend.write("X")

    assert_that(out[-1]).is_equal_to("<@5,1>")


# Erasure repaints the blanked rows.
def test_erasure_repaints() -> None:
    frontend, out = painted()

    frontend.write("about to go")
    out.clear()
    frontend.erase_window(-1)

    assert_that("".join(out)).contains("<@0,0>")
    assert_that(frontend.model.row_text(1)).is_equal_to("")


# erase_line clears from the cursor onward and repaints the row
# (§8.7.3.4).
def test_erase_line_repaints_the_row() -> None:
    frontend, _out = painted()

    frontend.write("wiped nearly")
    frontend.erase_line()

    assert_that(frontend.model.row_text(1)).is_equal_to("wiped nearly")


# Buffering flows through to the model without painting anything.
def test_buffering_paints_nothing() -> None:
    frontend, out = painted()

    out.clear()
    frontend.set_buffering(False)

    assert_that(out).is_empty()


# Both bleeps ring the terminal's one bell (§9).
def test_bleeps_ring_the_bell() -> None:
    frontend, out = painted()

    frontend.bleep(1)
    frontend.bleep(2)

    assert_that(out.count("\a")).is_equal_to(2)


# read_line hands back the typed line and echoes it through the
# model, so the grid agrees with what the terminal's cooked echo
# already showed.
def test_read_line_echoes_through_the_model() -> None:
    frontend, _out = painted(line="open mailbox")

    line = frontend.read_line()

    assert_that(line).is_equal_to("open mailbox")
    assert_that(frontend.model.row_text(1)).is_equal_to("open mailbox")


# Without a terminal handed in, a real blessed Terminal is built;
# on a captured, un-terminal stream it reports no size and the
# painter falls back to the classic 80 by 24 (§8.4).
def test_a_real_terminal_is_built_by_default() -> None:
    frontend = ScreenFrontend(3, out=lambda _text: None, read=lambda: "")

    assert_that(frontend.screen_columns).is_greater_than_or_equal_to(1)
    assert_that(frontend.screen_lines).is_greater_than_or_equal_to(1)
    assert_that(frontend.model.columns).is_equal_to(frontend.screen_columns)


# The fallback dimensions cover a terminal that reports no size.
def test_a_sizeless_terminal_falls_back() -> None:
    class Sizeless(StubTerminal):
        width = 0
        height = 0

    frontend = ScreenFrontend(
        5, terminal=Sizeless(), out=lambda _text: None, read=lambda: ""
    )

    assert_that(frontend.screen_columns).is_equal_to(FALLBACK_COLUMNS)
    assert_that(frontend.screen_lines).is_equal_to(FALLBACK_LINES)
