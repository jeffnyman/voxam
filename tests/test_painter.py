from contextlib import AbstractContextManager, nullcontext

from assertpy import assert_that

from voxam.frontend import GRAPHICS_FONT, Status
from voxam.painter import FALLBACK_COLUMNS, FALLBACK_LINES, ScreenFrontend
from voxam.screen import BOLD, ITALIC, REVERSE, UPPER


class StubKey(str):
    """A keystroke: a string wearing an optional special-key name."""

    name: str | None = None

    def __new__(cls, character: str, name: str | None = None) -> "StubKey":
        key = super().__new__(cls, character)
        key.name = name

        return key


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

    def __init__(self, keys: list[StubKey] | None = None) -> None:
        self.keys = list(keys or [])
        self.timeouts: list[float | None] = []

    def move_xy(self, x: int, y: int) -> str:
        return f"<@{x},{y}>"

    def cbreak(self) -> AbstractContextManager[object]:
        return nullcontext()

    def inkey(self, timeout: float | None = None) -> object:
        self.timeouts.append(timeout)

        return self.keys.pop(0)


def painted(
    version: int = 5, line: str = "look", keys: list[StubKey] | None = None
) -> tuple[ScreenFrontend, list[str]]:
    out: list[str] = []
    frontend = ScreenFrontend(
        version, terminal=StubTerminal(keys), out=out.append, read=lambda: line
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


# A §15 rectangle flows through the model and repaints, each row
# returning to the column where the rectangle began.
def test_rectangles_paint_right_and_down() -> None:
    frontend, _out = painted()

    frontend.split_window(3)
    frontend.set_window(UPPER)
    frontend.set_cursor(1, 4)
    frontend.write_rectangle(["ab", "cd"])

    assert_that(frontend.model.row_text(1)).is_equal_to("   ab")
    assert_that(frontend.model.row_text(2)).is_equal_to("   cd")


# Cells in the character graphics font paint as their §16 Unicode
# stand-ins: box-drawing for the map lines, runes for the letters.
def test_font_3_paints_its_unicode_stand_ins() -> None:
    frontend, out = painted()

    frontend.set_font(GRAPHICS_FONT)
    frontend.write("(f")

    stream = "".join(out)

    assert_that(stream).contains("│")
    assert_that(stream).contains("ᚠ")


# Codes 123 to 126 are the reverse-video twins of the arrows and
# the drawn question mark -- the §16 bitmaps invert them pixel for
# pixel -- so the painter draws the same shape and flips reverse
# video instead of carrying it in the glyph.
def test_font_3_reversed_shapes_flip_reverse_video() -> None:
    frontend, out = painted()

    frontend.set_font(GRAPHICS_FONT)
    frontend.write("{")

    stream = "".join(out)

    assert_that(stream).contains("↑")
    assert_that(stream).contains("<rev>")


# The map-connectivity calls the Beyond Zork eyeball tests settled:
# a solid mass meeting a diagonal road stays a quadrant block, so
# room corners keep their shape, and the single-pixel road tips
# continue their diagonal, so a road reaches its room without a
# gap (§16).
def test_font_3_keeps_the_map_connected() -> None:
    frontend, out = painted()

    frontend.set_font(GRAPHICS_FONT)
    frontend.write("CG")

    stream = "".join(out)

    assert_that(stream).contains("▝")
    assert_that(stream).contains("╱")


# A font 3 character beyond the §16 table -- an accented letter,
# say -- passes through as itself rather than vanishing.
def test_font_3_passes_unknown_characters_through() -> None:
    frontend, out = painted()

    frontend.set_font(GRAPHICS_FONT)
    frontend.write("é")

    assert_that("".join(out)).contains("é")


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


# A plain keystroke passes through read_key as itself, unechoed --
# §15 read_char leaves echoing to the game.
def test_read_key_passes_plain_keys_through() -> None:
    frontend, out = painted(keys=[StubKey("n")])

    out.clear()
    key = frontend.read_key()

    assert_that(key).is_equal_to("n")
    assert_that("".join(out)).does_not_contain("n")


# Named special keys translate to their §3.8.2.2 input characters:
# enter, delete, and escape all have ZSCII meanings.
def test_read_key_translates_special_keys() -> None:
    frontend, _out = painted(
        keys=[
            StubKey("", "KEY_ENTER"),
            StubKey("", "KEY_BACKSPACE"),
            StubKey("", "KEY_ESCAPE"),
        ]
    )

    assert_that(frontend.read_key()).is_equal_to("\n")
    assert_that(frontend.read_key()).is_equal_to("\x7f")
    assert_that(frontend.read_key()).is_equal_to("\x1b")


# An empty read is not a keystroke, and neither is an unmapped
# multi-character escape sequence -- an arrow key the story cannot
# hear yet: read_key waits for one it can.
def test_read_key_waits_out_empty_and_unmapped_reads() -> None:
    frontend, _out = painted(
        keys=[StubKey(""), StubKey("\x1b[C", "KEY_RIGHT"), StubKey("q")]
    )

    assert_that(frontend.read_key()).is_equal_to("q")


# With a timeout, an expired wait answers None -- the machine's
# cue to fire a wall-clock interrupt -- and the timeout is handed
# through to the terminal.
def test_read_key_reports_expired_timeouts() -> None:
    frontend, _out = painted(keys=[StubKey("")])

    result = frontend.read_key(timeout=0.5)

    assert_that(result).is_none()


# An unmapped escape sequence inside a timed wait is no keystroke
# either: the wait reports as expired rather than pretending.
def test_read_key_timeout_swallows_unmapped_sequences() -> None:
    frontend, _out = painted(keys=[StubKey("\x1b[C", "KEY_RIGHT")])

    assert_that(frontend.read_key(timeout=0.5)).is_none()


# A key that beats the clock comes back as itself.
def test_read_key_returns_keys_that_beat_the_clock() -> None:
    frontend, _out = painted(keys=[StubKey("z")])

    assert_that(frontend.read_key(timeout=0.5)).is_equal_to("z")


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
