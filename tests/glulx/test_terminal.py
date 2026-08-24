from contextlib import AbstractContextManager, nullcontext
from typing import cast

import pytest
from assertpy import assert_that

from voxam.aiff import Sound
from voxam.glulx.glk.api import Glk
from voxam.glulx.glk.objects import (
    BlankWindow,
    EventType,
    FileMode,
    KeyCode,
    LineRequest,
    PairWindow,
    SoundChannel,
    Style,
    TextBufferWindow,
    TextGridWindow,
    Window,
    WindowMethod,
)
from voxam.glulx.glk.painted import (
    FOREVER,
    Timer,
    _steps,
    grouped,
)
from voxam.glulx.glk.terminal import TerminalFrontend
from voxam.painter import IDLE_HEARTBEAT, MORE_PROMPT, Terminal
from voxam.speaker import Fill, Finished, Speaker, Stream


class StubKey(str):
    """A keystroke: a string wearing an optional special-key name."""

    name: str | None = None

    def __new__(cls, character: str, name: str | None = None) -> "StubKey":
        key = super().__new__(cls, character)
        key.name = name

        return key


class StubTerminal:
    """A terminal that emits readable markers instead of escapes.

    Only the sliver of the Terminal protocol this display actually
    uses is stubbed -- the colour mixers wait for the day styles
    earn colour hints -- so construction goes through a cast.
    """

    width = 30
    height = 8
    normal = "<n>"
    reverse = "<rev>"
    bold = "<b>"
    italic = "<i>"

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


class TickingTerminal(StubTerminal):
    """A terminal whose clock moves one second per keystroke read."""

    def __init__(
        self, keys: list[StubKey] | None = None, clock: list[float] | None = None
    ) -> None:
        super().__init__(keys)

        self.clock = clock if clock is not None else [0.0]

    def inkey(self, timeout: float | None = None) -> object:
        self.clock[0] += 1.0

        return super().inkey(timeout)


def framed(
    terminal: StubTerminal,
    out: "list[str] | None" = None,
    size: tuple[int, int] | None = None,
) -> TerminalFrontend:
    sink = out.append if out is not None else None

    return TerminalFrontend(cast("Terminal", terminal), sink, size=size)


def glassed(
    keys: list[StubKey] | None = None, terminal: StubTerminal | None = None
) -> tuple[TerminalFrontend, list[str]]:
    out: list[str] = []
    display = framed(terminal or StubTerminal(keys), out)

    return display, out


def typing(text: str) -> list[StubKey]:
    """The keystrokes of a typed line, enter included."""

    return [*(StubKey(character) for character in text), StubKey("", "KEY_ENTER")]


def boxed(window: Window, box: tuple[int, int, int, int]) -> Window:
    window.rearrange(box)

    return window


def saying(window: TextBufferWindow, text: str, style: int = Style.NORMAL) -> None:
    window.style = style

    for character in text:
        window.put_char(ord(character))


def writing(grid: TextGridWindow, x: int, y: int, text: str) -> None:
    grid.move_cursor(x, y)

    for character in text:
        grid.put_char(ord(character))


# The size is the terminal's own measure, the classic 80x24 when
# the terminal cannot say, or whatever the caller chose.
def test_the_size_is_the_terminals_measure() -> None:
    display, _ = glassed()

    assert_that(display.size()).is_equal_to((30, 8))

    class Sizeless(StubTerminal):
        width = 0
        height = 0

    assert_that(framed(Sizeless(), []).size()).is_equal_to((80, 24))
    assert_that(framed(StubTerminal(), [], size=(10, 5)).size()).is_equal_to((10, 5))


# Clearing paints every row blank and parks the cursor out of the
# way: the story begins on a clean screen, whatever the shell left
# behind.
def test_clearing_wipes_the_glass() -> None:
    out: list[str] = []
    display = framed(StubTerminal(), out, size=(4, 2))

    display.clear()

    assert_that(out[-1]).is_equal_to("<@0,0>    <@0,1>    <@0,1>")


# With no window tree there is nothing to paint, and nothing is.
def test_no_tree_paints_nothing() -> None:
    display, out = glassed()

    display.flush(None)

    assert_that(out).is_empty()


# A buffer window scrolls the way a terminal does: the newest line
# sits at the bottom of the box, rows above it blank-padded, and
# the cursor parks out of the way when no input is wanted.
def test_a_buffer_paints_bottom_aligned() -> None:
    display, out = glassed()
    window = cast("TextBufferWindow", boxed(TextBufferWindow(), (0, 0, 10, 4)))

    saying(window, "Hello\n")
    display.flush(window)

    painted = out[-1]

    assert_that(painted).contains("<@0,2>Hello     ")
    assert_that(painted).starts_with("<@0,0>          ")
    assert_that(painted).ends_with("<@0,7>")


# Styled runs wear their terminal sequences, and a plain run wears
# nothing at all.
def test_styled_runs_dress_for_the_terminal() -> None:
    display, out = glassed()
    window = cast("TextBufferWindow", boxed(TextBufferWindow(), (0, 0, 20, 2)))

    saying(window, "plain ")
    saying(window, "slanted", Style.EMPHASIZED)
    display.flush(window)

    assert_that(out[-1]).contains("plain <i>slanted<n>")


# A grid paints in place at its own box, its per-cell styles
# collapsed into runs.
def test_a_grid_paints_in_place() -> None:
    display, out = glassed()
    grid = cast("TextGridWindow", boxed(TextGridWindow(), (2, 1, 12, 3)))

    writing(grid, 0, 0, "Score: 10")
    grid.style = Style.SUBHEADER
    writing(grid, 0, 1, "Moves")
    display.flush(grid)

    painted = out[-1]

    assert_that(painted).contains("<@2,1>Score: 10 ")
    assert_that(painted).contains("<@2,2><b>Moves<n>     ")


# A split screen paints both halves, and the cursor follows the
# window that is taking input -- whichever side of the pair it is.
def test_a_split_screen_paints_both_windows() -> None:
    display, out = glassed()
    story = TextBufferWindow()
    status = TextGridWindow()
    pair = PairWindow(story, status, status, WindowMethod.ABOVE | WindowMethod.FIXED, 1)

    pair.rearrange((0, 0, 20, 8))
    writing(status, 0, 0, "Status")
    saying(story, "You are in a maze.\n")
    display.flush(pair)

    painted = out[-1]

    assert_that(painted).contains("Status")
    assert_that(painted).contains("You are in a maze.")
    assert_that(painted).ends_with("<@0,7>")

    display._typed = "n"
    display._typing = story
    display.flush(pair)

    assert_that(out[-1]).ends_with("<@1,7>")

    display._typing = status
    display.flush(pair)

    assert_that(out[-1]).ends_with("<@7,0>")


# A blank window shows blankness, measured by its box: the game is
# told it has no size, but the glass still has rows to cover.
def test_a_blank_window_shows_blankness() -> None:
    display, out = glassed()

    display.flush(boxed(BlankWindow(), (0, 0, 5, 2)))

    assert_that(out[-1]).contains("<@0,0>     <@0,1>     ")


# A window the game cleared starts over: the kept text is
# forgotten along with the flag.
def test_a_cleared_window_starts_over() -> None:
    display, out = glassed()
    window = cast("TextBufferWindow", boxed(TextBufferWindow(), (0, 0, 20, 3)))

    saying(window, "Before the clear.\n")
    display.flush(window)

    assert_that(out[-1]).contains("Before the clear.")

    window.clear()
    saying(window, "After.\n")
    display.flush(window)

    assert_that(out[-1]).does_not_contain("Before the clear.")
    assert_that(out[-1]).contains("After.")
    assert_that(window.pending_clear).is_false()


# A rearranged window rewraps its kept text to the new width --
# and a window squeezed to nothing paints nothing, keeping its
# text for better days.
def test_a_resized_window_rewraps() -> None:
    display, out = glassed()
    window = cast("TextBufferWindow", boxed(TextBufferWindow(), (0, 0, 20, 3)))

    saying(window, "hello wide world\n")
    display.flush(window)

    assert_that(out[-1]).contains("hello wide world")

    window.rearrange((0, 0, 10, 3))
    display.flush(window)

    assert_that(out[-1]).contains("<@0,0>hello wide<@0,1>world")

    window.rearrange((0, 0, 10, 0))
    display.flush(window)

    assert_that(out[-1]).is_equal_to("<@0,7>")


# A width of zero would be no width to wrap to; the fallback keeps
# the arithmetic sensible until the layout says better.
def test_a_widthless_window_wraps_to_the_fallback() -> None:
    display, _ = glassed()
    window = cast("TextBufferWindow", boxed(TextBufferWindow(), (0, 0, 0, 3)))

    saying(window, "narrow\n")
    display.flush(window)

    assert_that(display._buffers[window].width).is_equal_to(80)


# More text than a windowful holds waits behind the pause prompt,
# and a keystroke turns the page instead of reaching the game.
def test_a_windowful_waits_behind_the_pause() -> None:
    keys = [*([StubKey(" ")] * 5), StubKey("x")]
    display, out = glassed(keys)
    window = cast("TextBufferWindow", boxed(TextBufferWindow(), (0, 0, 10, 3)))

    saying(window, "".join(f"line {index}\n" for index in range(8)))
    display.flush(window)

    assert_that(out[-1]).contains(f"<b><rev>{MORE_PROMPT}<n>")
    assert_that(out[-1]).ends_with(f"<@{len(MORE_PROMPT)},2>")

    code = display.read_char(window)

    assert_that(code).is_equal_to(ord("x"))
    assert_that(out[-1]).does_not_contain(MORE_PROMPT)
    assert_that(out[-1]).contains("line 7")


# The line being typed is drawn in the input style as part of the
# layout, and accepted whole when Return arrives.
def test_typing_shows_in_the_input_style() -> None:
    display, out = glassed(typing("go"))
    window = cast("TextBufferWindow", boxed(TextBufferWindow(), (0, 0, 20, 3)))

    saying(window, "> ")
    display.flush(window)

    assert_that(display.read_line(window, 80)).is_equal_to(("go", 0))
    assert_that("".join(out)).contains("> <b>go<n>")


# A terminator key ends the line and is reported as having done
# so (Glk: Line Input Events).
def test_a_terminator_ends_the_line() -> None:
    display, _ = glassed([StubKey("x"), StubKey("", "KEY_ESCAPE")])
    window = cast("TextBufferWindow", boxed(TextBufferWindow(), (0, 0, 20, 3)))
    window.line_request = LineRequest(None)
    window.line_request.terminators = (KeyCode.ESCAPE,)

    assert_that(display.read_line(window, 80)).is_equal_to(("x", KeyCode.ESCAPE))


# Backspace rubs out; Escape clears the whole line and typing
# starts over.
def test_the_line_edits_classically() -> None:
    display, _ = glassed(
        [
            StubKey("a"),
            StubKey("b"),
            StubKey("", "KEY_BACKSPACE"),
            StubKey("c"),
            StubKey("", "KEY_ENTER"),
            StubKey("o"),
            StubKey("", "KEY_ESCAPE"),
            StubKey("n"),
            StubKey("", "KEY_ENTER"),
        ]
    )
    window = cast("TextBufferWindow", boxed(TextBufferWindow(), (0, 0, 20, 3)))

    assert_that(display.read_line(window, 80)).is_equal_to(("ac", 0))
    assert_that(display.read_line(window, 80)).is_equal_to(("n", 0))


# The line never grows past what the game's buffer can hold.
def test_the_line_respects_the_buffer() -> None:
    display, _ = glassed(typing("abc"))
    window = cast("TextBufferWindow", boxed(TextBufferWindow(), (0, 0, 20, 3)))

    assert_that(display.read_line(window, 2)).is_equal_to(("ab", 0))


# An unmapped escape sequence is nothing usable and is waited
# past; a control character reaches the editor and does nothing.
def test_garbage_keys_are_nothing() -> None:
    display, _ = glassed(
        [StubKey("ab"), StubKey("\x01"), StubKey("z"), StubKey("", "KEY_ENTER")]
    )
    window = cast("TextBufferWindow", boxed(TextBufferWindow(), (0, 0, 20, 3)))

    assert_that(display.read_line(window, 80)).is_equal_to(("z", 0))


# Keystrokes translate to Glk character codes: named keys to their
# keycodes, control characters to theirs, anything else to itself.
def test_read_char_speaks_glk() -> None:
    display, _ = glassed(
        [
            StubKey("a"),
            StubKey("", "KEY_UP"),
            StubKey("\t"),
            StubKey("\r"),
        ]
    )
    window = cast("TextBufferWindow", boxed(TextBufferWindow(), (0, 0, 20, 3)))

    assert_that(display.read_char(window)).is_equal_to(ord("a"))
    assert_that(display.read_char(window)).is_equal_to(KeyCode.UP)
    assert_that(display.read_char(window)).is_equal_to(KeyCode.TAB)
    assert_that(display.read_char(window)).is_equal_to(KeyCode.RETURN)


# A timer firing mid-line posts its event and hands control back
# with the request still pending; the half-typed line survives to
# the next call (Glk: Timer Events).
def test_a_timer_fires_between_keystrokes(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = [0.0]
    monkeypatch.setattr("voxam.glulx.glk.painted.monotonic", lambda: clock[0])
    terminal = TickingTerminal(
        [StubKey("g"), StubKey(""), StubKey("o"), StubKey("", "KEY_ENTER")], clock
    )
    display, _ = glassed(terminal=terminal)
    library = Glk(display)
    window = cast("TextBufferWindow", boxed(TextBufferWindow(), (0, 0, 20, 3)))

    display.set_timer(1500)

    assert_that(display.read_line(window, 80)).is_none()
    assert_that(library.pending_events[0].kind).is_equal_to(EventType.TIMER)
    assert_that(display.read_line(window, 80)).is_equal_to(("go", 0))

    display.set_timer(0)

    assert_that(display.timer.timeout()).is_none()


# A grid window taking line input shows it at the cursor, clamped
# to the grid when the game left the cursor past an edge.
def test_a_grid_takes_input_at_its_cursor() -> None:
    display, out = glassed([*typing("hi"), StubKey("", "KEY_ENTER")])
    grid = cast("TextGridWindow", boxed(TextGridWindow(), (0, 0, 10, 2)))

    display.flush(grid)
    grid.move_cursor(3, 0)

    assert_that(display.read_line(grid, 80)).is_equal_to(("hi", 0))
    assert_that("".join(out)).contains("<@3,0><b>hi<n>")

    grid.move_cursor(20, 5)

    assert_that(display.read_line(grid, 80)).is_equal_to(("", 0))
    assert_that("".join(out)).contains("<@9,1>")


# The file prompt asks on the bottom line, Return answers, Escape
# and an empty answer cancel -- and the interrupted line of play
# is standing where it was afterwards.
def test_the_file_prompt_asks_on_the_bottom_line(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = [0.0]
    monkeypatch.setattr("voxam.glulx.glk.painted.monotonic", lambda: clock[0])
    terminal = TickingTerminal(
        [
            StubKey("g"),
            StubKey(""),
            StubKey("s"),
            StubKey(""),
            StubKey("", "KEY_ENTER"),
            StubKey("", "KEY_ESCAPE"),
            StubKey("", "KEY_ENTER"),
            StubKey("o"),
            StubKey("", "KEY_ENTER"),
        ],
        clock,
    )
    display, out = glassed(terminal=terminal)
    Glk(display)
    window = cast("TextBufferWindow", boxed(TextBufferWindow(), (0, 0, 20, 3)))

    display.set_timer(1500)

    assert_that(display.read_line(window, 80)).is_none()
    assert_that(display.prompt_file(0, FileMode.WRITE)).is_equal_to("s")
    assert_that("".join(out)).contains("Save to which file? ")
    assert_that(display.prompt_file(0, FileMode.READ)).is_none()
    assert_that("".join(out)).contains("Load from which file? ")
    assert_that(display.prompt_file(0, FileMode.WRITE)).is_none()
    assert_that(display.read_line(window, 80)).is_equal_to(("go", 0))


# A file prompt outranks the pager: every window is forced to the
# end first, so the player answers a question instead of fighting
# a pause prompt for the keyboard.
def test_the_file_prompt_catches_the_windows_up() -> None:
    display, out = glassed([StubKey("", "KEY_ENTER")])
    window = cast("TextBufferWindow", boxed(TextBufferWindow(), (0, 0, 10, 3)))

    saying(window, "".join(f"line {index}\n" for index in range(8)))
    display.flush(window)

    assert_that(out[-1]).contains(MORE_PROMPT)
    assert_that(display.prompt_file(0, FileMode.WRITE)).is_none()
    assert_that(out[-1]).does_not_contain(MORE_PROMPT)


# Retiring leaves the cursor under the story, so whatever the
# session prints next lands below the game's last words.
def test_retiring_parks_below_the_story() -> None:
    display, out = glassed()

    display.retire()

    assert_that(out[-1]).is_equal_to("<@0,7>\n")


# Two styles are distinguishable exactly when they dress
# differently here.
def test_styles_distinguish_by_their_dress() -> None:
    display, _ = glassed()
    window = TextBufferWindow()

    assert_that(
        display.style_distinguish(window, Style.EMPHASIZED, Style.NORMAL)
    ).is_true()
    assert_that(
        display.style_distinguish(window, Style.HEADER, Style.SUBHEADER)
    ).is_false()


# Style measurements answer in the terminal's only unit, the
# character cell, and decline what a cell cannot measure.
def test_style_measures_answer_in_cells() -> None:
    display, _ = glassed()
    window = TextBufferWindow()

    measures = [
        display.style_measure(window, style, hint)
        for style, hint in [
            (Style.NORMAL, 3),
            (Style.HEADER, 4),
            (Style.NORMAL, 4),
            (Style.EMPHASIZED, 5),
            (Style.NORMAL, 5),
            (Style.NORMAL, 6),
            (Style.NORMAL, 0),
            (Style.NORMAL, 1),
            (Style.NORMAL, 2),
        ]
    ]

    assert_that(measures).is_equal_to([0, 1, 0, 1, 0, 0, 0, 0, None])


# A grid row's per-cell dress collapses into runs keyed by style
# and link together, a missing style or link reading as plain --
# so a linked run stays distinct from its neighbours.
def test_grouping_collapses_a_row_into_runs() -> None:
    assert_that(grouped(["a", "b"], [Style.ALERT], [0, 0])).is_equal_to(
        [((Style.ALERT, 0), "a"), ((Style.NORMAL, 0), "b")]
    )
    assert_that(grouped(["c", "d"], [Style.NORMAL, Style.NORMAL], [0, 0])).is_equal_to(
        [((Style.NORMAL, 0), "cd")]
    )
    assert_that(grouped(["e", "f"], [Style.NORMAL, Style.NORMAL], [7])).is_equal_to(
        [((Style.NORMAL, 7), "e"), ((Style.NORMAL, 0), "f")]
    )


# Without an output seam of its own, the display writes straight
# to standard output, unbuffered.
def test_the_default_seam_is_stdout(capsys: pytest.CaptureFixture[str]) -> None:
    display = framed(StubTerminal(), size=(2, 1))

    display.clear()

    assert_that(capsys.readouterr().out).is_equal_to("<@0,0>  <@0,0>")


# The timer keeps its own deadline arithmetic: setting arms it,
# zero disarms it, and a due timer rearms itself for the next
# round (Glk: Timer Events).
def test_the_timer_comes_round_and_round(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = [0.0]
    monkeypatch.setattr("voxam.glulx.glk.painted.monotonic", lambda: clock[0])
    timer = Timer()

    assert_that(timer.timeout()).is_none()
    assert_that(timer.due()).is_false()

    timer.set(2000)

    assert_that(timer.timeout()).is_equal_to(2.0)
    assert_that(timer.due()).is_false()

    clock[0] = 3.0

    assert_that(timer.timeout()).is_equal_to(0.0)
    assert_that(timer.due()).is_true()
    assert_that(timer.timeout()).is_equal_to(2.0)


# The recording seams hear input the moment it is accepted: every
# finished line with its terminator, file-prompt answers included
# (an escape-cancelled prompt records the empty line that cancels
# on replay), and every keystroke a character read delivered.
def test_the_recording_seams_hear_input() -> None:
    lines: list[tuple[str, int]] = []
    keys: list[int] = []
    pressed = [
        *typing("go"),
        StubKey("a"),
        StubKey("", "KEY_ESCAPE"),
        StubKey("x"),
        *typing("save"),
        StubKey("", "KEY_ESCAPE"),
    ]
    out: list[str] = []
    display = TerminalFrontend(
        cast("Terminal", StubTerminal(pressed)),
        out.append,
        on_line=lambda text, terminator: lines.append((text, terminator)),
        on_key=keys.append,
    )
    window = cast("TextBufferWindow", boxed(TextBufferWindow(), (0, 0, 20, 3)))
    window.line_request = LineRequest(None)
    window.line_request.terminators = (KeyCode.ESCAPE,)

    assert_that(display.read_line(window, 80)).is_equal_to(("go", 0))
    assert_that(display.read_line(window, 80)).is_equal_to(("a", KeyCode.ESCAPE))
    assert_that(display.read_char(window)).is_equal_to(ord("x"))
    assert_that(display.prompt_file(0, FileMode.WRITE)).is_equal_to("save")
    assert_that(display.prompt_file(0, FileMode.WRITE)).is_none()

    assert_that(lines).is_equal_to(
        [("go", 0), ("a", KeyCode.ESCAPE), ("save", 0), ("", 0)]
    )
    assert_that(keys).is_equal_to([ord("x")])


# A timer interrupting a read delivers nothing to the seams: no
# line was accepted and no keystroke reached the game.
def test_the_seams_ignore_a_timer(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = [0.0]
    monkeypatch.setattr("voxam.glulx.glk.painted.monotonic", lambda: clock[0])

    keys: list[int] = []
    out: list[str] = []
    display = TerminalFrontend(
        cast("Terminal", TickingTerminal([StubKey("")], clock)),
        out.append,
        on_key=keys.append,
    )
    Glk(display)
    window = cast("TextBufferWindow", boxed(TextBufferWindow(), (0, 0, 20, 3)))

    display.set_timer(500)

    assert_that(display.read_char(window)).is_none()
    assert_that(keys).is_empty()


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
    """A speaker with a two-byte sound and a frameless one."""

    streams: list[SoundStream] = []

    def opener(rate: float, fill: Fill, finished: Finished) -> Stream:
        del rate

        stream = SoundStream(fill, finished)
        streams.append(stream)

        return stream

    sounds = {
        3: Sound(1, 8, 1000.0, 2, b"\x01\x02"),
        7: Sound(1, 8, 1000.0, 0, b""),
    }

    return Speaker(sounds, frozenset(), opener), streams


def soundful(
    keys: list[StubKey] | None = None,
) -> tuple[TerminalFrontend, Speaker, list[SoundStream]]:
    speaker, streams = sounded()
    out: list[str] = []
    display = TerminalFrontend(
        cast("Terminal", StubTerminal(keys)), out.append, speaker=speaker
    )

    return display, speaker, streams


# A speaker aboard makes the sound claim true; without one the
# display claims nothing and refuses every play.
def test_a_speaker_makes_the_sound_claim_true() -> None:
    display, _ = glassed()

    assert_that(display.sound).is_false()
    assert_that(display.play_sound(SoundChannel(), 3, 1, 0)).is_false()

    sounding, _, _ = soundful()

    assert_that(sounding.sound).is_true()


# A play starts the speaker, an unknown number refuses without
# stopping what is already sounding, and a stop silences it.
def test_sounds_play_through_the_speaker() -> None:
    display, speaker, _ = soundful()
    channel = SoundChannel()

    assert_that(display.play_sound(channel, 3, 1, 0)).is_true()
    assert_that(speaker.playing()).is_true()
    assert_that(display.play_sound(channel, 99, 1, 0)).is_false()
    assert_that(speaker.playing()).is_true()

    display.stop_sound(channel)

    assert_that(speaker.playing()).is_false()


# The newest play takes the speaker; the displaced channel has
# nothing sounding left to stop.
def test_a_new_play_displaces_the_old() -> None:
    display, speaker, _ = soundful()
    first = SoundChannel()
    second = SoundChannel()

    display.play_sound(first, 3, 1, 0)
    display.play_sound(second, 3, 1, 0)
    display.stop_sound(first)

    assert_that(speaker.playing()).is_true()

    display.stop_sound(second)

    assert_that(speaker.playing()).is_false()


# Glk's until-stopped repeat count reaches the speaker as its own
# forever: the sound cycles without ever reporting an end, where a
# single play runs out with its buffer.
def test_repeats_translate_to_the_speakers() -> None:
    display, _, streams = soundful()

    display.play_sound(SoundChannel(), 3, FOREVER, 0)

    assert_that(streams[-1].fill(bytearray(4))).is_false()

    display.play_sound(SoundChannel(), 3, 1, 0)

    assert_that(streams[-1].fill(bytearray(4))).is_true()


# Glk's 0x10000 volume scale lands on the speaker's eight steps,
# rounded, and louder-than-loud is loud.
def test_volume_translates_to_steps() -> None:
    assert_that(_steps(0x10000)).is_equal_to(8)
    assert_that(_steps(0x8000)).is_equal_to(4)
    assert_that(_steps(0xFFFF)).is_equal_to(8)
    assert_that(_steps(0x20000)).is_equal_to(8)
    assert_that(_steps(0)).is_equal_to(0)


# A pause is silence and an unpause starts the sound over: the
# speaker owns no playback positions to resume from.
def test_pause_is_silence_and_resume_starts_over() -> None:
    display, speaker, streams = soundful()
    channel = SoundChannel()
    channel.sound = 3
    channel.repeats = 1

    display.play_sound(channel, 3, 1, 0)
    display.pause_sound(channel, True)

    assert_that(speaker.playing()).is_false()

    display.pause_sound(channel, False)

    assert_that(speaker.playing()).is_true()
    assert_that(streams).is_length(2)

    # Unpausing a channel with nothing on it starts nothing.
    display.pause_sound(SoundChannel(), False)

    assert_that(streams).is_length(2)


# A volume change is remembered on the channel by Glk itself; the
# display has nothing to do until the next play reads it.
def test_a_volume_change_waits_for_the_next_play() -> None:
    display, _, _ = soundful()

    display.set_volume(SoundChannel(), 0x4000, 0)


# The hush at session end silences whatever still sounds -- and is
# safe to ask of a display that never had a speaker.
def test_hush_silences_the_session() -> None:
    display, speaker, _ = soundful()

    display.play_sound(SoundChannel(), 3, 1, 0)
    display.hush()

    assert_that(speaker.playing()).is_false()

    silent, _ = glassed()

    silent.hush()


# A sound that ends of its own accord posts the completion event
# the play asked for, and the answer to the interrupted read is
# None so glk_select can deliver it (Glk: Playing Sounds).
def test_a_sound_ending_posts_its_notification() -> None:
    display, _, _ = soundful([StubKey("x")])
    library = Glk(display)
    window = cast("TextBufferWindow", boxed(TextBufferWindow(), (0, 0, 20, 3)))
    channel = SoundChannel()
    channel.sound = 7
    channel.notify = 5

    assert_that(display.play_sound(channel, 7, 1, 5)).is_true()
    assert_that(display.read_char(window)).is_none()

    event = library.pending_events[0]

    assert_that(event.kind).is_equal_to(EventType.SOUND_NOTIFY)
    assert_that(event.val1).is_equal_to(7)
    assert_that(event.val2).is_equal_to(5)
    assert_that(channel.sound).is_equal_to(0)
    assert_that(display.read_char(window)).is_equal_to(ord("x"))


# A play that asked for no notification ends in silence: the
# channel clears and the keystroke goes through undisturbed.
def test_a_quiet_ending_posts_nothing() -> None:
    display, _, _ = soundful([StubKey("x")])
    library = Glk(display)
    window = cast("TextBufferWindow", boxed(TextBufferWindow(), (0, 0, 20, 3)))
    channel = SoundChannel()
    channel.sound = 7

    display.play_sound(channel, 7, 1, 0)

    assert_that(display.read_char(window)).is_equal_to(ord("x"))
    assert_that(library.pending_events).is_empty()
    assert_that(channel.sound).is_equal_to(0)


# A channel stopped before its ending was heard is forgotten: the
# speaker's answer finds no channel to blame it on and no event.
def test_a_forgotten_ending_posts_nothing() -> None:
    display, _, _ = soundful([StubKey("x")])
    library = Glk(display)
    window = cast("TextBufferWindow", boxed(TextBufferWindow(), (0, 0, 20, 3)))
    channel = SoundChannel()
    channel.notify = 5

    display.play_sound(channel, 7, 1, 5)
    display.stop_sound(channel)

    assert_that(display.read_char(window)).is_equal_to(ord("x"))
    assert_that(library.pending_events).is_empty()


# While a sound plays, an infinite wait is chopped into heartbeats
# so the ending can be heard between keystrokes -- but a timer
# already waiting less keeps its own shorter watch.
def test_a_playing_sound_chops_the_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = [0.0]
    monkeypatch.setattr("voxam.glulx.glk.painted.monotonic", lambda: clock[0])

    speaker, _ = sounded()
    terminal = StubTerminal([StubKey("x"), StubKey("y"), StubKey("z")])
    out: list[str] = []
    display = TerminalFrontend(cast("Terminal", terminal), out.append, speaker=speaker)
    window = cast("TextBufferWindow", boxed(TextBufferWindow(), (0, 0, 20, 3)))

    display.play_sound(SoundChannel(), 3, FOREVER, 0)

    assert_that(display.read_char(window)).is_equal_to(ord("x"))
    assert_that(terminal.timeouts[-1]).is_equal_to(IDLE_HEARTBEAT)

    display.set_timer(10_000)

    assert_that(display.read_char(window)).is_equal_to(ord("y"))
    assert_that(terminal.timeouts[-1]).is_equal_to(IDLE_HEARTBEAT)

    display.set_timer(50)

    assert_that(display.read_char(window)).is_equal_to(ord("z"))
    assert_that(terminal.timeouts[-1]).is_equal_to(0.05)
