from contextlib import AbstractContextManager, nullcontext

import pytest
from assertpy import assert_that

from voxam.aiff import Sound
from voxam.frontend import GRAPHICS_FONT, Status
from voxam.painter import (
    FALLBACK_COLUMNS,
    FALLBACK_LINES,
    IDLE_HEARTBEAT,
    ScreenFrontend,
)
from voxam.png import Picture
from voxam.screen import BOLD, ITALIC, REVERSE, UPPER
from voxam.speaker import Fill, Finished, Speaker, Stream


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

    def color_rgb(self, red: int, green: int, blue: int) -> str:
        return f"<fg {red},{green},{blue}>"

    def on_color_rgb(self, red: int, green: int, blue: int) -> str:
        return f"<bg {red},{green},{blue}>"

    def cbreak(self) -> AbstractContextManager[object]:
        return nullcontext()

    def inkey(self, timeout: float | None = None) -> object:
        self.timeouts.append(timeout)

        return self.keys.pop(0)


def painted(
    version: int = 5, keys: list[StubKey] | None = None
) -> tuple[ScreenFrontend, list[str]]:
    out: list[str] = []
    frontend = ScreenFrontend(version, terminal=StubTerminal(keys), out=out.append)

    return frontend, out


def typing(text: str) -> list[StubKey]:
    """The keystrokes of a typed line, enter included."""

    return [*(StubKey(character) for character in text), StubKey("", "KEY_ENTER")]


# The picture seam is inert at the terminal: no sizes, a census
# of zero, and draws that paint nothing -- the sixel cover is a
# doorway courtesy, and the header's cleared pictures bit already
# said so (§11.1.4, §15 picture_data).
def test_the_picture_seam_is_inert() -> None:
    frontend, out = painted()

    frontend.draw_picture(1, 1, 1)
    frontend.erase_picture(1, 1, 1)
    frontend.place_window(1, 1, 1, 1, 1)

    assert_that(frontend.has_stage).is_false()
    assert_that(frontend.has_pictures).is_false()
    assert_that(frontend.picture_data(1)).is_none()
    assert_that(frontend.picture_census()).is_equal_to((0, 0))
    assert_that(out).is_empty()


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


# A printing interrupt strands the prompt above its output; the
# §15 remark asks the interpreter to redisplay the input line, and
# the painter rewrites the remembered prompt at the new cursor --
# Jigsaw's chapter epigraphs are the earner.
def test_the_prompt_returns_after_an_interrupts_output() -> None:
    frontend, _out = painted()

    frontend.write("\n>")
    frontend.begin_input()
    frontend.write("\n\n   All the generals were on holiday.\n\n")
    frontend.resume_input()

    row, _column = frontend.model.cursor

    assert_that(frontend.model.row_text(row)).is_equal_to(">")


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


# read_line reads raw keystrokes and echoes them through the model
# itself -- the terminal's own echo is never invited, so nothing
# but the painter ever writes to the glass.
def test_read_line_echoes_through_the_model() -> None:
    frontend, _out = painted(keys=typing("open mailbox"))

    line = frontend.read_line()

    assert_that(line).is_equal_to("open mailbox")
    assert_that(frontend.model.row_text(1)).is_equal_to("open mailbox")


# Backspace rubs out the last typed character, on the glass and in
# the returned line alike (§15 read's line editor).
def test_read_line_backspace_rubs_out() -> None:
    keys = [
        *(StubKey(character) for character in "loox"),
        StubKey("", "KEY_BACKSPACE"),
        StubKey("k"),
        StubKey("", "KEY_ENTER"),
    ]
    frontend, _out = painted(keys=keys)

    line = frontend.read_line()

    assert_that(line).is_equal_to("look")
    assert_that(frontend.model.row_text(1)).is_equal_to("look")


# With nothing typed there is nothing to rub: backspace at the
# start of a line is quietly nothing.
def test_read_line_backspace_stops_at_the_start() -> None:
    keys = [StubKey("", "KEY_BACKSPACE"), *typing("n")]
    frontend, _out = painted(keys=keys)

    assert_that(frontend.read_line()).is_equal_to("n")


# Escape, the §3.8.4 codes beyond the cursor keys, and unmapped
# escape sequences mean nothing to a line: read_line waits them
# out -- and cursor-up with no history yet is just as quiet.
def test_read_line_waits_out_keys_a_line_cannot_use() -> None:
    keys = [
        StubKey("", "KEY_ESCAPE"),
        StubKey("", "KEY_UP"),
        StubKey("\x1b[15~", "KEY_F5"),
        *typing("y"),
    ]
    frontend, _out = painted(keys=keys)

    line = frontend.read_line()

    assert_that(line).is_equal_to("y")
    assert_that(frontend.model.row_text(1)).is_equal_to("y")


# The cursor keys edit within the line: left walks back, an
# insertion lands at the cursor, and the model repaints the whole
# line -- glass and returned text agreeing (§15 read).
def test_read_line_edits_mid_line() -> None:
    keys = [
        *(StubKey(character) for character in "gt"),
        StubKey("", "KEY_LEFT"),
        StubKey("e"),
        StubKey("", "KEY_RIGHT"),
        StubKey("", "KEY_ENTER"),
    ]
    frontend, _out = painted(keys=keys)

    line = frontend.read_line()

    assert_that(line).is_equal_to("get")
    assert_that(frontend.model.row_text(1)).is_equal_to("get")


# Cursor-up recalls the previous command from the session's
# history, painted onto the glass like typing; the recalled line
# replaces a longer draft cleanly.
def test_read_line_recalls_history() -> None:
    keys = [
        *typing("inventory"),
        *(StubKey(character) for character in "lo"),
        StubKey("", "KEY_UP"),
        StubKey("", "KEY_ENTER"),
    ]
    frontend, _out = painted(keys=keys)

    first = frontend.read_line()
    second = frontend.read_line()

    assert_that(first).is_equal_to("inventory")
    assert_that(second).is_equal_to("inventory")
    assert_that(frontend.model.row_text(2)).is_equal_to("inventory")


# A bold space paints without its bold: there is no glyph to
# embolden, and a terminal would brighten the blank's reverse
# background into a patchwork -- Border Zone pads its status bar
# with exactly such spaces. Bold text keeps its dress.
def test_bold_spaces_shed_their_bold() -> None:
    frontend, out = painted()

    frontend.set_style(2)
    frontend.write("a b")
    text = "".join(out)

    assert_that(text).contains("<n><b>a")
    assert_that(text).contains("<n> ")
    assert_that(text).contains("<n><b>b")


# A screenful of prints pauses behind a reverse-video [MORE] at
# the cursor, spends one key on the pause, and repaints the row
# clean -- the top of Bureaucracy's post-form text wall survives.
# The idle heartbeat is armed and expires once before the real
# key: a heartbeat must never answer the pause, or [MORE] clicks
# itself after a fifth of a second.
def test_a_screenful_pauses_behind_more() -> None:
    frontend, out = painted(keys=[StubKey(""), StubKey("x")])
    frontend.idle = lambda: None

    frontend.write("line\n" * 8)
    text = "".join(out)

    assert_that(text).contains("<rev>[MORE]")
    assert_that(frontend.model.rendered()).does_not_contain("[MORE]")


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


# The cursor keys translate to their §3.8.4 codepoints 129 to 132,
# which the machine's input seam passes through whole -- how Beyond
# Zork's menus hear an arrow.
def test_read_key_translates_the_cursor_keys() -> None:
    frontend, _out = painted(
        keys=[
            StubKey("\x1b[A", "KEY_UP"),
            StubKey("\x1b[B", "KEY_DOWN"),
            StubKey("\x1b[D", "KEY_LEFT"),
            StubKey("\x1b[C", "KEY_RIGHT"),
        ]
    )

    assert_that(frontend.read_key()).is_equal_to("\x81")
    assert_that(frontend.read_key()).is_equal_to("\x82")
    assert_that(frontend.read_key()).is_equal_to("\x83")
    assert_that(frontend.read_key()).is_equal_to("\x84")


# An empty read is not a keystroke, and neither is an unmapped
# multi-character escape sequence -- a function key the story
# cannot hear yet: read_key waits for one it can.
def test_read_key_waits_out_empty_and_unmapped_reads() -> None:
    frontend, _out = painted(
        keys=[StubKey(""), StubKey("\x1b[15~", "KEY_F5"), StubKey("q")]
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
    frontend, _out = painted(keys=[StubKey("\x1b[15~", "KEY_F5")])

    assert_that(frontend.read_key(timeout=0.5)).is_none()


# A key that beats the clock comes back as itself.
def test_read_key_returns_keys_that_beat_the_clock() -> None:
    frontend, _out = painted(keys=[StubKey("z")])

    assert_that(frontend.read_key(timeout=0.5)).is_equal_to("z")


# clear() paints the blank model over the whole glass, so a story
# starts on a clean screen with no shell output showing through
# the rows it has not yet painted.
def test_clear_wipes_every_row() -> None:
    frontend, out = painted()

    frontend.clear()

    stream = "".join(out)

    for row in range(StubTerminal.height):
        assert_that(stream).contains(f"<@0,{row}>")


# A cover paints centred in half-block cells -- each ▀ carries two
# pixels, the upper as ink and the lower as ground, an odd bottom
# row grounding on black -- then a keypress dismisses it and the
# glass is left clean for the story.
def test_the_frontispiece_paints_in_half_blocks() -> None:
    terminal = StubTerminal([StubKey("x")])
    out: list[str] = []
    frontend = ScreenFrontend(5, terminal=terminal, out=out.append)
    picture = Picture(
        2,
        3,
        (
            ((255, 0, 0), (0, 255, 0)),
            ((0, 0, 255), (255, 255, 255)),
            ((10, 20, 30), (40, 50, 60)),
        ),
    )

    frontend.show_frontispiece(picture)

    stream = "".join(out)

    assert_that(stream).contains("▀")
    assert_that(stream).contains("<@14,3>")
    assert_that(stream).contains("<fg 255,0,0>")
    assert_that(stream).contains("<bg 0,0,255>")
    assert_that(stream).contains("<bg 0,0,0>")
    assert_that(terminal.keys).is_empty()


def response(text: str) -> list[StubKey]:
    """A terminal's escape answer, one keystroke per character."""

    return [StubKey(character) for character in text]


# With pixels requested, the terminal is asked first; one that
# declares sixel (attribute 4) draws the cover as real pixels
# between the enter and leave sequences, dismissed by a keypress.
def test_the_frontispiece_can_paint_in_sixel_pixels() -> None:
    terminal = StubTerminal(
        [*response("\x1b[?61;4c"), *response("\x1b[6;16;8t"), StubKey("x")]
    )
    out: list[str] = []
    frontend = ScreenFrontend(5, terminal=terminal, out=out.append)
    picture = Picture(2, 2, (((255, 0, 0),) * 2, ((255, 0, 0),) * 2))

    frontend.show_frontispiece(picture, pixels=True)

    stream = "".join(out)

    assert_that(stream).contains("\x1b[c")
    assert_that(stream).contains("\x1b[16t")
    assert_that(stream).contains("\x1bPq")
    assert_that(stream).contains("\x1b\\")
    assert_that(stream).does_not_contain("▀")
    assert_that(terminal.keys).is_empty()


# A terminal without sixel among its attributes gets the
# half-block painting instead -- never garbage -- and the cell
# size is never even asked for.
def test_pixels_fall_back_without_the_sixel_attribute() -> None:
    terminal = StubTerminal([*response("\x1b[?61c"), StubKey("x")])
    out: list[str] = []
    frontend = ScreenFrontend(5, terminal=terminal, out=out.append)
    picture = Picture(2, 2, (((255, 0, 0),) * 2, ((255, 0, 0),) * 2))

    frontend.show_frontispiece(picture, pixels=True)

    stream = "".join(out)

    assert_that(stream).does_not_contain("\x1b[16t")
    assert_that(stream).does_not_contain("\x1bPq")
    assert_that(stream).contains("▀")
    assert_that(terminal.keys).is_empty()


# A terminal that never answers has said no: the patience window
# expires once and the half-block painting takes over.
def test_pixels_fall_back_on_a_silent_terminal() -> None:
    terminal = StubTerminal([StubKey(""), StubKey("x")])
    out: list[str] = []
    frontend = ScreenFrontend(5, terminal=terminal, out=out.append)
    picture = Picture(2, 2, (((255, 0, 0),) * 2, ((255, 0, 0),) * 2))

    frontend.show_frontispiece(picture, pixels=True)

    stream = "".join(out)

    assert_that(stream).does_not_contain("\x1bPq")
    assert_that(stream).contains("▀")


# The terminal's own cell-size report replaces the conservative
# floors, so the same cover magnifies and centres differently on
# glass that measures differently; a garbled report keeps the
# floors.
def test_the_cell_size_report_drives_the_magnification() -> None:
    picture = Picture(2, 2, (((255, 0, 0),) * 2, ((255, 0, 0),) * 2))

    floored = StubTerminal(
        [*response("\x1b[?4c"), *response("\x1b[8;5;5t"), StubKey("x")]
    )
    out: list[str] = []
    frontend = ScreenFrontend(5, terminal=floored, out=out.append)

    frontend.show_frontispiece(picture, pixels=True)

    assert_that("".join(out)).contains("<@7,0>")

    measured = StubTerminal(
        [*response("\x1b[?4c"), *response("\x1b[6;32;10t"), StubKey("x")]
    )
    out = []
    frontend = ScreenFrontend(5, terminal=measured, out=out.append)

    frontend.show_frontispiece(picture, pixels=True)

    assert_that("".join(out)).contains("<@2,0>")


# A cover larger than the glass shrinks to fit, keeping its shape;
# the box average of a uniform picture is itself.
def test_large_covers_shrink_to_the_glass() -> None:
    terminal = StubTerminal([StubKey("x")])
    out: list[str] = []
    frontend = ScreenFrontend(5, terminal=terminal, out=out.append)
    rows = tuple(tuple((100, 150, 200) for _ in range(60)) for _ in range(32))

    frontend.show_frontispiece(Picture(60, 32, rows))

    stream = "".join(out)

    assert_that(stream).contains("<fg 100,150,200>")
    assert_that(stream).contains("<@0,0>")


# Without a terminal handed in, a real blessed Terminal is built;
# on a captured, un-terminal stream it reports no size and the
# painter falls back to the classic 80 by 24 (§8.4).
def test_a_real_terminal_is_built_by_default() -> None:
    frontend = ScreenFrontend(3, out=lambda _text: None)

    assert_that(frontend.screen_columns).is_greater_than_or_equal_to(1)
    assert_that(frontend.screen_lines).is_greater_than_or_equal_to(1)
    assert_that(frontend.model.columns).is_equal_to(frontend.screen_columns)


# The fallback dimensions cover a terminal that reports no size.
def test_a_sizeless_terminal_falls_back() -> None:
    class Sizeless(StubTerminal):
        width = 0
        height = 0

    frontend = ScreenFrontend(5, terminal=Sizeless(), out=lambda _text: None)

    assert_that(frontend.screen_columns).is_equal_to(FALLBACK_COLUMNS)
    assert_that(frontend.screen_lines).is_equal_to(FALLBACK_LINES)


class SoundStream:
    """Captures the speaker's callbacks so a test can drive them."""

    def __init__(self, fill: Fill, finished: Finished) -> None:
        self.fill = fill
        self.finished = finished
        self.aborted = False

    def start(self) -> None:
        pass

    def abort(self) -> None:
        self.aborted = True

    def close(self) -> None:
        pass


def sounded() -> tuple[Speaker, list[SoundStream]]:
    """A speaker holding one two-byte sound, with its streams."""

    streams: list[SoundStream] = []

    def opener(rate: float, fill: Fill, finished: Finished) -> Stream:
        del rate
        stream = SoundStream(fill, finished)
        streams.append(stream)

        return stream

    speaker = Speaker({3: Sound(1, 8, 1000.0, 2, b"\x01\x02")}, frozenset(), opener)

    return speaker, streams


# With a speaker aboard the painted frontend claims sound and the
# seam delegates every call; a natural ending surfaces through
# sound_finished, a manual stop never does (§9.4.4).
def test_the_sound_seam_delegates_to_the_speaker() -> None:
    speaker, streams = sounded()
    out: list[str] = []
    frontend = ScreenFrontend(
        5, terminal=StubTerminal(None), out=out.append, speaker=speaker
    )

    assert_that(frontend.has_sounds).is_true()

    frontend.play_sound(3, 8, 1)

    assert_that(streams).is_length(1)
    assert_that(frontend.sound_playing()).is_true()

    frontend.stop_sound(3)

    assert_that(frontend.sound_playing()).is_false()
    assert_that(streams[0].aborted).is_true()

    frontend.wait_for_sound()

    assert_that(frontend.sound_finished()).is_false()

    frontend.play_sound(3, 8, 1)
    streams[1].fill(bytearray(4))
    streams[1].finished()

    assert_that(frontend.sound_finished()).is_true()


# Without a speaker the painted frontend claims no sound and the
# seam is inert.
def test_the_sound_seam_is_inert_without_a_speaker() -> None:
    frontend, _ = painted()

    assert_that(frontend.has_sounds).is_false()

    frontend.play_sound(3, 8, 1)
    frontend.stop_sound(None)
    frontend.wait_for_sound()

    assert_that(frontend.sound_playing()).is_false()
    assert_that(frontend.sound_finished()).is_false()


# With an idle callback wired, an infinite wait is chopped into
# heartbeats: each expiry lets the machine attend to background
# work, and the typed line is unaffected.
def test_read_line_heartbeats_through_its_idle_callback() -> None:
    terminal = StubTerminal([StubKey(""), *typing("go")])
    out: list[str] = []
    frontend = ScreenFrontend(5, terminal=terminal, out=out.append)
    beats: list[int] = []
    frontend.idle = lambda: beats.append(1)

    assert_that(frontend.read_line()).is_equal_to("go")
    assert_that(beats).is_length(1)
    assert_that(set(terminal.timeouts)).is_equal_to({IDLE_HEARTBEAT})


# An infinite single-key wait heartbeats the same way.
def test_read_key_heartbeats_while_waiting_forever() -> None:
    terminal = StubTerminal([StubKey(""), StubKey("n")])
    out: list[str] = []
    frontend = ScreenFrontend(5, terminal=terminal, out=out.append)
    beats: list[int] = []
    frontend.idle = lambda: beats.append(1)

    assert_that(frontend.read_key()).is_equal_to("n")
    assert_that(beats).is_length(1)
    assert_that(terminal.timeouts).is_equal_to([IDLE_HEARTBEAT, IDLE_HEARTBEAT])


# A timed read keeps its own clock: the game's timeout passes
# through untouched and the idle callback never fires there.
def test_timed_read_keys_keep_their_own_clock() -> None:
    terminal = StubTerminal([StubKey("y")])
    out: list[str] = []
    frontend = ScreenFrontend(5, terminal=terminal, out=out.append)
    frontend.idle = lambda: pytest.fail("a timed read must not idle")

    assert_that(frontend.read_key(0.5)).is_equal_to("y")
    assert_that(terminal.timeouts).is_equal_to([0.5])


# The painted answer for get_cursor is the model's own
# (§8.7.2.3.2).
def test_cursor_position_reads_the_model() -> None:
    frontend, _out = painted()

    frontend.split_window(3)
    frontend.set_window(UPPER)
    frontend.set_cursor(2, 5)

    assert_that(frontend.cursor_position()).is_equal_to((2, 5))
