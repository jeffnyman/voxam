from typing import cast

import pytest
from assertpy import assert_that

from voxam.errors import GlulxSessionEnd
from voxam.glass import INK_DEFAULT, PAPER_DEFAULT, Glass
from voxam.glulx.glk.api import Glk
from voxam.glulx.glk.glass import GlassFrontend
from voxam.glulx.glk.objects import (
    EventType,
    FileMode,
    KeyCode,
    Style,
    TextBufferWindow,
    Window,
)
from voxam.painter import MORE_PROMPT

# One painted run, as the stub remembers it: 1-based row and
# column, the text, its ink and paper, and the bold and italic
# flags.
Painted = tuple[int, int, str, tuple[int, int, int], tuple[int, int, int], bool, bool]


class StubGlass:
    """A glass that remembers its blits and answers scripted keys.

    Only the sliver of the Glass protocol this display actually
    drives is stubbed -- the pixel methods wait for the graphics
    road stop -- so construction goes through a cast. Running out
    of scripted keys plays the close button: EOFError, as the real
    glass raises it.
    """

    columns = 30
    lines = 8
    cell_width = 9
    cell_height = 18

    def __init__(self, keys: "list[str | None] | None" = None) -> None:
        self.keys = list(keys or [])
        self.timeouts: list[float | None] = []
        self.painted: list[Painted] = []
        self.presented = 0

    def paint(
        self,
        row: int,
        column: int,
        text: str,
        ink: tuple[int, int, int],
        paper: tuple[int, int, int],
        *,
        bold: bool,
        italic: bool,
        graphics: bool,
    ) -> None:
        del graphics

        self.painted.append((row, column, text, ink, paper, bold, italic))

    def present(self) -> None:
        self.presented += 1

    def key(self, timeout: float | None) -> str | None:
        self.timeouts.append(timeout)

        if not self.keys:
            raise EOFError

        return self.keys.pop(0)


class TickingGlass(StubGlass):
    """A glass whose clock moves one second per keystroke read."""

    def __init__(
        self,
        keys: "list[str | None] | None" = None,
        clock: list[float] | None = None,
    ) -> None:
        super().__init__(keys)

        self.clock = clock if clock is not None else [0.0]

    def key(self, timeout: float | None) -> str | None:
        self.clock[0] += 1.0

        return super().key(timeout)


def glassed(
    keys: "list[str | None] | None" = None, glass: StubGlass | None = None
) -> tuple[GlassFrontend, StubGlass]:
    stub = glass or StubGlass(keys)

    return GlassFrontend(cast("Glass", stub)), stub


def boxed(window: Window, box: tuple[int, int, int, int]) -> Window:
    window.rearrange(box)

    return window


def saying(window: TextBufferWindow, text: str, style: int = Style.NORMAL) -> None:
    window.style = style

    for character in text:
        window.put_char(ord(character))


# The size is the glass's own grid, measured in cells -- and with
# the default 1x1 metrics, cells are the only unit Glk hears.
def test_the_size_is_the_glasses_grid() -> None:
    display, _ = glassed()

    assert_that(display.size()).is_equal_to((30, 8))


# Without an injected glass, construction opens the real pygame
# window: the Blorb's standard shape and the zoom travel to the
# doorway, and the window wears the glulx badge.
def test_construction_opens_a_real_window_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def opened(
        standard: tuple[int, int] | None = None,
        version: int | str = 0,
        zoom: float | None = None,
    ) -> StubGlass:
        captured["standard"] = standard
        captured["version"] = version
        captured["zoom"] = zoom

        return StubGlass()

    monkeypatch.setattr("voxam.glulx.glk.glass.open_pygame_glass", opened)

    display = GlassFrontend(standard=(320, 200), zoom=0.5)

    assert_that(display.size()).is_equal_to((30, 8))
    assert_that(captured["standard"]).is_equal_to((320, 200))
    assert_that(captured["version"]).is_equal_to("glulx")
    assert_that(captured["zoom"]).is_equal_to(0.5)


# A buffer paints bottom-aligned onto 1-based cells: the text and
# the fresh line its newline opened sit at the bottom of the box,
# blank rows padded above, and one present puts the frame on
# screen.
def test_a_buffer_paints_bottom_aligned_on_one_based_cells() -> None:
    display, glass = glassed()
    window = cast("TextBufferWindow", boxed(TextBufferWindow(), (0, 0, 10, 4)))

    saying(window, "Hello\n")
    display.flush(window)

    assert_that(glass.painted).contains(
        (1, 1, " " * 10, INK_DEFAULT, PAPER_DEFAULT, False, False)
    )
    assert_that(glass.painted).contains(
        (3, 1, "Hello", INK_DEFAULT, PAPER_DEFAULT, False, False)
    )
    assert_that(glass.painted).contains(
        (3, 6, " " * 5, INK_DEFAULT, PAPER_DEFAULT, False, False)
    )
    assert_that(glass.presented).is_equal_to(1)


# Styled runs dress with the fitted faces, and a reversed style
# swaps ink and paper -- the same three attributes the terminal
# glass dresses in.
def test_styled_runs_dress_with_faces_and_reverse() -> None:
    display, glass = glassed()
    window = cast("TextBufferWindow", boxed(TextBufferWindow(), (0, 0, 20, 3)))

    saying(window, "slanted ", Style.EMPHASIZED)
    saying(window, "heavy ", Style.HEADER)
    saying(window, "loud", Style.ALERT)
    display.flush(window)

    assert_that(glass.painted).contains(
        (3, 1, "slanted ", INK_DEFAULT, PAPER_DEFAULT, False, True)
    )
    assert_that(glass.painted).contains(
        (3, 9, "heavy ", INK_DEFAULT, PAPER_DEFAULT, True, False)
    )
    assert_that(glass.painted).contains(
        (3, 15, "loud", PAPER_DEFAULT, INK_DEFAULT, True, False)
    )


# A line exactly as wide as its window leaves nothing to pad, and
# the empty run paints no zero-width blit.
def test_a_full_line_leaves_nothing_to_pad() -> None:
    display, glass = glassed()
    window = cast("TextBufferWindow", boxed(TextBufferWindow(), (0, 0, 5, 2)))

    saying(window, "abcde\n")
    display.flush(window)

    assert_that([entry for entry in glass.painted if not entry[2]]).is_empty()


# More text than a windowful holds waits behind the pause prompt,
# reversed so it stands out; a keystroke turns the page instead of
# reaching the game.
def test_the_pause_prompt_reverses_and_turns() -> None:
    display, glass = glassed([" ", " ", " ", " ", " ", "x"])
    window = cast("TextBufferWindow", boxed(TextBufferWindow(), (0, 0, 10, 3)))

    saying(window, "".join(f"line {index}\n" for index in range(8)))
    display.flush(window)

    assert_that(glass.painted).contains(
        (3, 1, MORE_PROMPT, PAPER_DEFAULT, INK_DEFAULT, True, False)
    )

    assert_that(display.read_char(window)).is_equal_to(ord("x"))

    # The stub keeps every frame; a fresh flush shows the current
    # one, caught up past the pause with the last lines standing.
    glass.painted.clear()
    display.flush(window)

    assert_that(
        [entry for entry in glass.painted if MORE_PROMPT in entry[2]]
    ).is_empty()
    assert_that(
        [entry for entry in glass.painted if entry[2] == "line 7"]
    ).is_not_empty()


# The line being typed is drawn in the input style with a block
# caret painted where the next character will land -- a window has
# no hardware cursor to park.
def test_typing_wears_a_block_caret() -> None:
    display, glass = glassed()
    window = cast("TextBufferWindow", boxed(TextBufferWindow(), (0, 0, 10, 4)))

    saying(window, "> ")
    display._typed = "go"
    display._typing = window
    display.flush(window)

    assert_that(glass.painted).contains(
        (4, 3, "go", INK_DEFAULT, PAPER_DEFAULT, True, False)
    )
    assert_that(glass.painted).contains(
        (4, 5, " ", PAPER_DEFAULT, INK_DEFAULT, False, False)
    )


# A typed line reaching the window's right edge leaves the caret
# nowhere on the glass to stand, and none is painted.
def test_a_full_line_keeps_the_caret_on_the_glass() -> None:
    display, glass = glassed()
    window = cast("TextBufferWindow", boxed(TextBufferWindow(), (0, 0, 30, 4)))

    display._typed = "x" * 30
    display._typing = window
    display.flush(window)

    caret = [
        entry
        for entry in glass.painted
        if entry[3] == PAPER_DEFAULT and entry[4] == INK_DEFAULT
    ]

    assert_that(caret).is_empty()


# A line collects at the keyboard in the glass's §3.8 alphabet:
# backspace rubs out, escape clears the line, return accepts --
# and the line seam hears what was accepted.
def test_read_line_collects_at_the_keyboard() -> None:
    lines: list[tuple[str, int]] = []
    stub = StubGlass(["a", "b", "\x7f", "c", "\n", "o", "\x1b", "n", "\n"])
    display = GlassFrontend(
        cast("Glass", stub),
        on_line=lambda text, terminator: lines.append((text, terminator)),
    )
    window = cast("TextBufferWindow", boxed(TextBufferWindow(), (0, 0, 20, 3)))

    assert_that(display.read_line(window, 80)).is_equal_to(("ac", 0))
    assert_that(display.read_line(window, 80)).is_equal_to(("n", 0))
    assert_that(lines).is_equal_to([("ac", 0), ("n", 0)])


# Keystrokes translate to Glk character codes: the arrow and
# function key characters to their keycodes, ordinary typing to
# itself -- and the key seam hears each one.
def test_read_char_speaks_glk() -> None:
    keys: list[int] = []
    stub = StubGlass(["a", "\x81", "\x85", "\x90"])
    display = GlassFrontend(cast("Glass", stub), on_key=keys.append)
    window = cast("TextBufferWindow", boxed(TextBufferWindow(), (0, 0, 20, 3)))

    assert_that(display.read_char(window)).is_equal_to(ord("a"))
    assert_that(display.read_char(window)).is_equal_to(KeyCode.UP)
    assert_that(display.read_char(window)).is_equal_to(KeyCode.FUNC1)
    assert_that(display.read_char(window)).is_equal_to(KeyCode.FUNC12)
    assert_that(keys).is_equal_to([ord("a"), KeyCode.UP, KeyCode.FUNC1, KeyCode.FUNC12])


# This display does not claim the mouse yet, so a stray click is
# swallowed rather than delivered to a game that never asked for
# it; the next real keystroke goes through.
def test_a_click_is_swallowed() -> None:
    display, _ = glassed(["\xfe", "x"])
    window = cast("TextBufferWindow", boxed(TextBufferWindow(), (0, 0, 20, 3)))

    assert_that(display.read_char(window)).is_equal_to(ord("x"))


# The window's close button ends the session the way an exhausted
# input stream does: a session end, not a crash.
def test_the_close_button_ends_the_session() -> None:
    display, _ = glassed([])
    window = cast("TextBufferWindow", boxed(TextBufferWindow(), (0, 0, 20, 3)))

    with pytest.raises(GlulxSessionEnd):
        display.read_char(window)


# A timer firing mid-line posts its event and hands control back
# with the request still pending; the half-typed line survives to
# the next call (Glk: Timer Events).
def test_a_timer_fires_between_keystrokes(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = [0.0]
    monkeypatch.setattr("voxam.glulx.glk.painted.monotonic", lambda: clock[0])
    display, _ = glassed(glass=TickingGlass(["g", None, "o", "\n"], clock))
    library = Glk(display)
    window = cast("TextBufferWindow", boxed(TextBufferWindow(), (0, 0, 20, 3)))

    display.set_timer(1500)

    assert_that(display.read_line(window, 80)).is_none()
    assert_that(library.pending_events[0].kind).is_equal_to(EventType.TIMER)
    assert_that(display.read_line(window, 80)).is_equal_to(("go", 0))


# The timer's deadline reaches the glass as the key wait's own
# timeout, and a stopped timer leaves the wait unbounded -- the
# spine's watch, kept at the window exactly as at the terminal.
def test_the_timers_deadline_reaches_the_glass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = [0.0]
    monkeypatch.setattr("voxam.glulx.glk.painted.monotonic", lambda: clock[0])
    display, glass = glassed(["x", "y"])
    window = cast("TextBufferWindow", boxed(TextBufferWindow(), (0, 0, 20, 3)))

    display.set_timer(2000)

    assert_that(display.read_char(window)).is_equal_to(ord("x"))
    assert_that(glass.timeouts[-1]).is_equal_to(2.0)

    display.set_timer(0)

    assert_that(display.read_char(window)).is_equal_to(ord("y"))
    assert_that(glass.timeouts[-1]).is_none()


# The file prompt asks on the bottom row of the glass, and Return
# answers -- the shared spine, painting through this display's own
# cells.
def test_the_file_prompt_asks_on_the_bottom_row() -> None:
    display, glass = glassed(["s", "\n"])

    assert_that(display.prompt_file(0, FileMode.WRITE)).is_equal_to("s")

    asked = [
        entry
        for entry in glass.painted
        if entry[0] == glass.lines and entry[2].startswith("Save to which file? ")
    ]

    assert_that(asked).is_not_empty()


# Clearing paints every row blank and presents: the story begins
# on a clean window, whatever stood on the surface before.
def test_clearing_wipes_the_window() -> None:
    display, glass = glassed()

    display.clear()

    assert_that(glass.painted).is_length(8)
    assert_that(glass.painted[0]).is_equal_to(
        (1, 1, " " * 30, INK_DEFAULT, PAPER_DEFAULT, False, False)
    )
    assert_that(glass.presented).is_equal_to(1)

    # Retiring is the terminal's parting act; a window has nothing
    # to yield and quietly does nothing.
    display.retire()

    assert_that(glass.presented).is_equal_to(1)
