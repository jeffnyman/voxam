from collections.abc import Callable
from typing import cast

import pytest
from assertpy import assert_that

from voxam.errors import GlulxSessionEnd
from voxam.glass import INK_DEFAULT, PAPER_DEFAULT, Glass
from voxam.glulx.glk.api import Glk
from voxam.glulx.glk.glass import LINK_INK, GlassFrontend
from voxam.glulx.glk.objects import (
    EventType,
    FileMode,
    GraphicsWindow,
    KeyCode,
    Metrics,
    Style,
    TextBufferWindow,
    Window,
    WindowMethod,
    WindowType,
)
from voxam.glulx.glk.resources import ImageInfo
from voxam.painter import MORE_PROMPT
from voxam.png import Picture, decode

# One painted run, as the stub remembers it: 1-based pixel line
# and column, the text, its ink and paper, and the bold and italic
# flags.
Painted = tuple[int, int, str, tuple[int, int, int], tuple[int, int, int], bool, bool]

# One filled rectangle: 1-based pixel line and column, then the
# height, width, and color the glass was handed.
Filled = tuple[int, int, int, int, tuple[int, int, int]]


class StubGlass:
    """A glass that remembers its blits and answers scripted keys.

    Only the sliver of the Glass protocol this display actually
    drives is stubbed, so construction goes through a cast. Its
    font cell is one pixel square, so pixel positions and cell
    positions coincide and the expectations stay easy to read;
    WideGlass carries the real scaling. Running out of scripted
    keys plays the close button: EOFError, as the real glass
    raises it.
    """

    columns = 30
    lines = 8
    cell_width = 1
    cell_height = 1

    def __init__(self, keys: "list[str | None] | None" = None) -> None:
        self.keys = list(keys or [])
        self.timeouts: list[float | None] = []
        self.painted: list[Painted] = []
        self.fills: list[Filled] = []
        self.draws: list[tuple[object, int, int, tuple[int, int]]] = []
        self.presented = 0
        # Where the last click landed, in 1-based window pixels.
        self.click_position: tuple[int, int] | None = None

    def text(
        self,
        line: int,
        column: int,
        characters: str,
        ink: tuple[int, int, int],
        paper: tuple[int, int, int],
        *,
        bold: bool,
        italic: bool,
        graphics: bool,
    ) -> None:
        del graphics

        self.painted.append((line, column, characters, ink, paper, bold, italic))

    def fill(
        self,
        line: int,
        column: int,
        height: int,
        width: int,
        colour: tuple[int, int, int],
    ) -> None:
        self.fills.append((line, column, height, width, colour))

    def draw(
        self,
        rows: object,
        line: int,
        column: int,
        size: tuple[int, int],
    ) -> None:
        self.draws.append((rows, line, column, size))

    def present(self) -> None:
        self.presented += 1

    def key(self, timeout: float | None) -> str | None:
        self.timeouts.append(timeout)

        if not self.keys:
            raise EOFError

        return self.keys.pop(0)

    def click(self) -> tuple[int, int] | None:
        return self.click_position

    def photograph(self, data: bytes) -> object:
        del data

        # A stub carries no pygame decoders; the real window does.
        return None


class WideGlass(StubGlass):
    """A glass with a real font cell, for the scaling arithmetic."""

    cell_width = 9
    cell_height = 18


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


# The size is the whole glass in real pixels -- here one per
# cell -- and the metrics carry the font cell, so a text window
# still answers its size in characters.
def test_the_size_is_the_glasses_pixels() -> None:
    display, _ = glassed()

    assert_that(display.size()).is_equal_to((30, 8))
    assert_that(display.metrics).is_equal_to(Metrics(1, 1))


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
# caret -- one filled font cell -- where the next character will
# land: a window has no hardware cursor to park.
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
    assert_that(glass.fills).contains((4, 5, 1, 1, INK_DEFAULT))


# A typed line reaching the window's right edge leaves the caret
# nowhere on the glass to stand, and none is painted.
def test_a_full_line_keeps_the_caret_on_the_glass() -> None:
    display, glass = glassed()
    window = cast("TextBufferWindow", boxed(TextBufferWindow(), (0, 0, 30, 4)))

    display._typed = "x" * 30
    display._typing = window
    display.flush(window)

    assert_that(glass.fills).is_empty()


# At a real font cell the tree is arranged in pixels: a text
# window still lays out in characters by way of the metrics, each
# row lands a cell-height down and each character a cell-width
# along, and the caret is one font cell of ink.
def test_a_real_cell_scales_the_painting() -> None:
    stub = WideGlass()
    display = GlassFrontend(cast("Glass", stub))

    assert_that(display.size()).is_equal_to((270, 144))
    assert_that(display.metrics).is_equal_to(Metrics(9, 18))

    window = TextBufferWindow()
    window.metrics = Metrics(9, 18)
    window.rearrange((0, 0, 90, 72))

    assert_that(window.width).is_equal_to(10)

    saying(window, "> ")
    display._typed = "go"
    display._typing = window
    display.flush(window)

    assert_that(stub.painted).contains(
        (55, 19, "go", INK_DEFAULT, PAPER_DEFAULT, True, False)
    )
    assert_that(stub.fills).contains((55, 37, 18, 9, INK_DEFAULT))


# The graphics claim is true at a real window, and a fresh canvas
# is erased to its background -- initially white -- exactly once:
# its pixels are the game's own work and persist across repaints
# (Glk: Graphics Windows).
def test_a_canvas_opens_white_and_persists() -> None:
    display, glass = glassed()
    window = cast("GraphicsWindow", boxed(GraphicsWindow(), (0, 0, 10, 4)))

    assert_that(display.graphics).is_true()

    display.flush(window)

    assert_that(glass.fills).contains((1, 1, 4, 10, (255, 255, 255)))

    glass.fills.clear()
    display.flush(window)

    assert_that(glass.fills).is_empty()


# A chosen background dresses future clears and erases; a filled
# rectangle wears the game's own color. Both are window-relative
# and clipped to the canvas: overhang on any edge is legitimate
# and simply not drawn (Glk: Graphics in Graphics Windows).
def test_rectangles_fill_clip_and_wear_backgrounds() -> None:
    display, glass = glassed()
    window = cast("GraphicsWindow", boxed(GraphicsWindow(), (10, 10, 20, 20)))

    display.flush(window)
    glass.fills.clear()

    display.set_background_color(window, 0x336699)
    window.clear()
    display.flush(window)

    assert_that(glass.fills).contains((11, 11, 10, 10, (0x33, 0x66, 0x99)))

    glass.fills.clear()
    display.fill_rect(window, 0xFF0000, -2, -2, 5, 5)

    assert_that(glass.fills).contains((11, 11, 3, 3, (255, 0, 0)))

    display.erase_rect(window, 5, 5, 100, 100)

    assert_that(glass.fills).contains((16, 16, 5, 5, (0x33, 0x66, 0x99)))

    glass.fills.clear()
    display.fill_rect(window, 0xFF0000, 0, 0, 0, 4)
    display.fill_rect(window, 0xFF0000, 30, 0, 5, 5)
    display.fill_rect(window, 0xFF0000, 0, 30, 5, 5)

    assert_that(glass.fills).is_empty()


# A PNG Pict draws onto the canvas at its window-relative corner,
# the source rows handed over whole with the scaled size for the
# glass to stretch.
def test_a_pict_draws_scaled_on_the_canvas(tiny_png: bytes) -> None:
    display, glass = glassed()
    window = cast("GraphicsWindow", boxed(GraphicsWindow(), (10, 2, 30, 8)))
    info = ImageInfo(1, b"PNG ", tiny_png, 2, 2)

    assert_that(display.draw_image(window, info, 2, 1, 4, 4)).is_true()

    rows, line, column, size = glass.draws[-1]

    assert_that((line, column)).is_equal_to((4, 13))
    assert_that(size).is_equal_to((4, 4))
    assert_that(rows).is_equal_to(
        (((10, 20, 30), (40, 50, 60)), ((0, 0, 0), (0, 0, 0)))
    )


# Overhang is cut away by sampling only the visible pixels: the
# draw lands at the intersection, sliced one-to-one, each pixel
# read from its nearest-neighbour source in the scaled grid.
def test_overhang_clips_to_the_canvas(tiny_png: bytes) -> None:
    display, glass = glassed()
    window = cast("GraphicsWindow", boxed(GraphicsWindow(), (0, 0, 10, 6)))
    info = ImageInfo(1, b"PNG ", tiny_png, 2, 2)

    assert_that(display.draw_image(window, info, -1, -1, 4, 4)).is_true()

    rows, line, column, size = glass.draws[-1]

    assert_that((line, column)).is_equal_to((1, 1))
    assert_that(size).is_equal_to((3, 3))
    assert_that(rows).is_equal_to(
        (
            ((10, 20, 30), (40, 50, 60), (40, 50, 60)),
            ((0, 0, 0), (0, 0, 0), (0, 0, 0)),
            ((0, 0, 0), (0, 0, 0), (0, 0, 0)),
        )
    )


# A draw scaled to nothing or falling wholly off the canvas is
# legitimate -- "the excess is not drawn" -- and succeeds while
# drawing nothing.
def test_fully_clipped_draws_are_legitimate(tiny_png: bytes) -> None:
    display, glass = glassed()
    window = cast("GraphicsWindow", boxed(GraphicsWindow(), (0, 0, 10, 6)))
    info = ImageInfo(1, b"PNG ", tiny_png, 2, 2)

    assert_that(display.draw_image(window, info, 50, 0, 4, 4)).is_true()
    assert_that(display.draw_image(window, info, 0, 0, 0, 4)).is_true()
    assert_that(glass.draws).is_empty()


# A JPEG draws after all, through the window's own decoder: the
# glass photographs the bytes into rows, the frontend wraps them
# as an opaque picture, and the decode is remembered once per
# number like any other. A photograph with no pixels -- no rows,
# or empty ones -- refuses instead.
def test_a_jpeg_draws_through_the_windows_decoder() -> None:
    class Photobooth(StubGlass):
        def __init__(self) -> None:
            super().__init__()
            self.developed: list[bytes] = []

        def photograph(self, data: bytes) -> object:
            self.developed.append(data)

            return [[(1, 2, 3), (4, 5, 6)]]

    stub = Photobooth()
    display = GlassFrontend(cast("Glass", stub))
    window = cast("GraphicsWindow", boxed(GraphicsWindow(), (0, 0, 10, 6)))
    jpeg = ImageInfo(4, b"JPEG", b"\xff\xd8photo", 2, 1)

    assert_that(display.draw_image(window, jpeg, 0, 0, 2, 1)).is_true()
    assert_that(display.draw_image(window, jpeg, 4, 0, 2, 1)).is_true()

    rows, line, column, size = stub.draws[0]

    assert_that((line, column)).is_equal_to((1, 1))
    assert_that(size).is_equal_to((2, 1))
    assert_that(rows).is_equal_to((((1, 2, 3), (4, 5, 6)),))
    assert_that(stub.developed).is_length(1)

    class Darkroom(StubGlass):
        def photograph(self, data: bytes) -> object:
            del data

            return []

    dark = GlassFrontend(cast("Glass", Darkroom()))

    assert_that(dark.draw_image(window, jpeg, 0, 0, 2, 1)).is_false()

    class Blankroll(StubGlass):
        def photograph(self, data: bytes) -> object:
            del data

            return [[]]

    blank = GlassFrontend(cast("Glass", Blankroll()))

    assert_that(blank.draw_image(window, jpeg, 0, 0, 2, 1)).is_false()


# Only canvases draw here, as the gestalt told the game -- and at
# a stub glass, which photographs nothing, a JPEG refuses too:
# both answer False, the spec's channel for an undrawn image.
def test_undrawables_are_refused(tiny_png: bytes) -> None:
    display, glass = glassed()
    canvas = cast("GraphicsWindow", boxed(GraphicsWindow(), (0, 0, 10, 6)))
    buffer = cast("TextBufferWindow", boxed(TextBufferWindow(), (0, 0, 10, 6)))
    pict = ImageInfo(1, b"PNG ", tiny_png, 2, 2)
    jpeg = ImageInfo(2, b"JPEG", b"\xff\xd8not-a-png", 2, 2)

    assert_that(display.draw_image(buffer, pict, 0, 0, 2, 2)).is_false()
    assert_that(display.draw_image(canvas, jpeg, 0, 0, 2, 2)).is_false()
    assert_that(glass.draws).is_empty()


# A Pict decodes once per number, refusals included: the cache
# remembers nothing-to-draw as firmly as it remembers pixels.
def test_pictures_decode_once(monkeypatch: pytest.MonkeyPatch, tiny_png: bytes) -> None:
    attempts: list[bytes] = []

    def counting(data: bytes) -> Picture:
        attempts.append(data)

        return decode(data)

    monkeypatch.setattr("voxam.glulx.glk.glass.decode", counting)

    display, _ = glassed()
    window = cast("GraphicsWindow", boxed(GraphicsWindow(), (0, 0, 10, 6)))
    pict = ImageInfo(1, b"PNG ", tiny_png, 2, 2)
    jpeg = ImageInfo(2, b"JPEG", b"\xff\xd8not-a-png", 2, 2)

    display.draw_image(window, pict, 0, 0, 2, 2)
    display.draw_image(window, pict, 4, 0, 2, 2)
    display.draw_image(window, jpeg, 0, 0, 2, 2)
    display.draw_image(window, jpeg, 0, 0, 2, 2)

    assert_that(attempts).is_length(2)


# A translucent Pict settles onto the canvas with its real
# opacities: straight colors wearing their alpha, handed to the
# glass to blend on the blit -- the transparency gestalt's claim
# made true.
def test_translucent_picts_blend(indexed_png: "Callable[..., bytes]") -> None:
    display, glass = glassed()
    window = cast("GraphicsWindow", boxed(GraphicsWindow(), (0, 0, 10, 6)))
    data = indexed_png(((200, 0, 0), (9, 9, 9)), alphas=bytes([255, 128]))
    info = ImageInfo(6, b"PNG ", data, 2, 1)

    assert_that(display.draw_image(window, info, 0, 0, 2, 1)).is_true()

    rows, *_ = glass.draws[-1]

    assert_that(rows).is_equal_to((((200, 0, 0), (9, 9, 9, 128)),))


# A fully transparent pixel travels with alpha zero -- its color
# already composed away to black by the decoder, and irrelevant --
# so the glass lets what is drawn beneath show through: the same
# layering the Z-Machine's chrome rides.
def test_clear_pixels_travel_with_alpha_zero(holey_png: bytes) -> None:
    display, glass = glassed()
    window = cast("GraphicsWindow", boxed(GraphicsWindow(), (0, 0, 10, 6)))
    info = ImageInfo(3, b"PNG ", holey_png, 2, 1)

    assert_that(display.draw_image(window, info, 0, 0, 2, 1)).is_true()

    rows, *_ = glass.draws[-1]

    assert_that(rows).is_equal_to((((200, 0, 0), (0, 0, 0, 0)),))


# glk_window_clear only raises a flag for the repaint -- but paint
# arriving before that repaint must land on the cleared canvas,
# not be erased under it: the clear settles first, and the flush
# afterwards has nothing left to erase.
def test_a_clear_lands_under_the_next_paint(tiny_png: bytes) -> None:
    display, glass = glassed()
    window = cast("GraphicsWindow", boxed(GraphicsWindow(), (0, 0, 10, 6)))
    info = ImageInfo(1, b"PNG ", tiny_png, 2, 2)

    display.flush(window)
    glass.fills.clear()

    window.clear()

    assert_that(display.draw_image(window, info, 0, 0, 2, 2)).is_true()
    assert_that(glass.fills).is_equal_to([(1, 1, 6, 10, (255, 255, 255))])
    assert_that(glass.draws).is_length(1)

    glass.fills.clear()
    display.flush(window)

    assert_that(glass.fills).is_empty()

    window.clear()
    display.fill_rect(window, 0xFF0000, 0, 0, 2, 2)

    assert_that(glass.fills).is_equal_to(
        [(1, 1, 6, 10, (255, 255, 255)), (1, 1, 2, 2, (255, 0, 0))]
    )


# A click lands in whichever armed window it hit: the request
# clears, the event posts with the window's own coordinates --
# pixels on a canvas -- the interrupted read answers None so
# glk_select can deliver it, and the click seam hears exactly what
# the game heard. Once the request is spent, the next click finds
# nothing armed and is swallowed.
def test_a_click_posts_to_the_armed_canvas() -> None:
    clicks: list[tuple[int, int]] = []
    stub = StubGlass(["\xfe", "\xfe", "x"])
    display = GlassFrontend(
        cast("Glass", stub), on_click=lambda x, y: clicks.append((x, y))
    )
    library = Glk(display)
    canvas = library.glk_window_open(None, 0, 0, WindowType.GRAPHICS, 0)

    if canvas is None:
        pytest.fail("the canvas did not open")

    library.glk_request_mouse_event(canvas)
    stub.click_position = (6, 3)

    assert_that(display.read_char(canvas)).is_none()

    event = library.pending_events[0]

    assert_that(event.kind).is_equal_to(EventType.MOUSE_INPUT)
    assert_that(event.window).is_same_as(canvas)
    assert_that((event.val1, event.val2)).is_equal_to((5, 2))
    assert_that(canvas.mouse_request).is_false()
    assert_that(clicks).is_equal_to([(5, 2)])

    library.pending_events.clear()

    assert_that(display.read_char(canvas)).is_equal_to(ord("x"))


# A double click at the window is simply two clicks in Glk's
# eyes: the second click's own character delivers another mouse
# event, never a stray keystroke.
def test_a_double_click_is_another_click() -> None:
    stub = StubGlass(["\xfd"])
    display = GlassFrontend(cast("Glass", stub))
    library = Glk(display)
    canvas = library.glk_window_open(None, 0, 0, WindowType.GRAPHICS, 0)

    if canvas is None:
        pytest.fail("the canvas did not open")

    library.glk_request_mouse_event(canvas)
    stub.click_position = (6, 3)

    assert_that(display.read_char(canvas)).is_none()

    event = library.pending_events[0]

    assert_that(event.kind).is_equal_to(EventType.MOUSE_INPUT)
    assert_that((event.val1, event.val2)).is_equal_to((5, 2))


# A grid click speaks cells, not pixels: the position divides by
# the font cell, so the game hears which character was clicked on
# (Glk: Mouse Input Events).
def test_a_grid_click_speaks_cells() -> None:
    stub = WideGlass(["\xfe"])
    display = GlassFrontend(cast("Glass", stub))
    library = Glk(display)
    grid = library.glk_window_open(None, 0, 0, WindowType.TEXT_GRID, 0)

    if grid is None:
        pytest.fail("the grid did not open")

    library.glk_request_mouse_event(grid)
    stub.click_position = (28, 40)

    assert_that(display.read_char(grid)).is_none()

    event = library.pending_events[0]

    assert_that((event.val1, event.val2)).is_equal_to((3, 2))


# Only grids and canvases carry the mouse: a click in an armed
# text buffer, a click outside every armed box, and a click whose
# position the glass has already forgotten all deliver nothing,
# and the wait carries on to the next keystroke.
def test_clicks_elsewhere_are_swallowed() -> None:
    stub = StubGlass(["\xfe", "x"])
    display = GlassFrontend(cast("Glass", stub))
    library = Glk(display)
    window = library.glk_window_open(None, 0, 0, WindowType.TEXT_BUFFER, 0)

    if window is None:
        pytest.fail("the buffer did not open")

    library.glk_request_mouse_event(window)
    stub.click_position = (5, 3)

    assert_that(display.read_char(window)).is_equal_to(ord("x"))
    assert_that(library.pending_events).is_empty()

    beyond = StubGlass(["\xfe", "x"])
    outside = GlassFrontend(cast("Glass", beyond))
    far = Glk(outside)
    canvas = far.glk_window_open(None, 0, 0, WindowType.GRAPHICS, 0)

    if canvas is None:
        pytest.fail("the canvas did not open")

    far.glk_request_mouse_event(canvas)
    beyond.click_position = (200, 200)

    assert_that(outside.read_char(canvas)).is_equal_to(ord("x"))
    assert_that(far.pending_events).is_empty()

    ghost = StubGlass(["\xfe", "x"])
    forgetful = GlassFrontend(cast("Glass", ghost))
    haunt = Glk(forgetful)
    haunted = haunt.glk_window_open(None, 0, 0, WindowType.GRAPHICS, 0)

    if haunted is None:
        pytest.fail("the canvas did not open")

    haunt.glk_request_mouse_event(haunted)

    assert_that(forgetful.read_char(haunted)).is_equal_to(ord("x"))


# A linked run wears the reader's blue and joins the frame's link
# map: a click on it in a window with a hyperlink request delivers
# the value, clears the request, and the link seam hears exactly
# what the game heard. A spent request swallows the next click,
# and an armed window the click falls outside of keeps waiting.
def test_a_link_selects_by_click() -> None:
    values: list[int] = []
    stub = StubGlass(["\xfe", "\xfe", "x"])
    display = GlassFrontend(cast("Glass", stub), on_link=values.append)
    library = Glk(display)
    window = library.glk_window_open(None, 0, 0, WindowType.TEXT_BUFFER, 0)

    if window is None:
        pytest.fail("the buffer did not open")

    library.glk_set_window(window)
    library.glk_put_string("go ")
    library.glk_set_hyperlink(9)
    library.glk_put_string("north")
    library.glk_set_hyperlink(0)
    library.glk_request_hyperlink_event(window)
    display.flush(library.root)

    assert_that(stub.painted).contains(
        (8, 4, "north", LINK_INK, PAPER_DEFAULT, False, False)
    )

    stub.click_position = (5, 8)

    assert_that(display.read_char(window)).is_none()

    event = library.pending_events[0]

    assert_that(event.kind).is_equal_to(EventType.HYPERLINK)
    assert_that(event.window).is_same_as(window)
    assert_that(event.val1).is_equal_to(9)
    assert_that(window.hyperlink_request).is_false()
    assert_that(values).is_equal_to([9])

    library.pending_events.clear()

    assert_that(display.read_char(window)).is_equal_to(ord("x"))

    # A split grid armed for links, clicked past its box: nothing
    # delivers, and the keystroke behind the click goes through.
    split = StubGlass(["\xfe", "x"])
    beside = GlassFrontend(cast("Glass", split))
    apart = Glk(beside)
    root = apart.glk_window_open(None, 0, 0, WindowType.TEXT_BUFFER, 0)
    banner = apart.glk_window_open(
        root, WindowMethod.ABOVE | WindowMethod.FIXED, 1, WindowType.TEXT_GRID, 0
    )

    if banner is None:
        pytest.fail("the grid did not open")

    apart.glk_request_hyperlink_event(banner)
    split.click_position = (5, 7)

    assert_that(beside.read_char(banner)).is_equal_to(ord("x"))
    assert_that(apart.pending_events).is_empty()


# With a hyperlink and a mouse request both standing on a grid,
# the position decides: a click on the linked run selects the
# link, and a click on plain cells falls through to the mouse.
def test_the_position_decides_between_link_and_mouse() -> None:
    linked = WideGlass(["\xfe"])
    display = GlassFrontend(cast("Glass", linked))
    library = Glk(display)
    grid = library.glk_window_open(None, 0, 0, WindowType.TEXT_GRID, 0)

    if grid is None:
        pytest.fail("the grid did not open")

    library.glk_set_window(grid)
    library.glk_set_hyperlink(4)
    library.glk_put_string("menu")
    library.glk_set_hyperlink(0)
    library.glk_request_hyperlink_event(grid)
    library.glk_request_mouse_event(grid)
    display.flush(library.root)
    linked.click_position = (10, 10)

    assert_that(display.read_char(grid)).is_none()
    assert_that(library.pending_events[0].kind).is_equal_to(EventType.HYPERLINK)
    assert_that(library.pending_events[0].val1).is_equal_to(4)
    assert_that(grid.mouse_request).is_true()

    library.pending_events.clear()
    library.glk_request_hyperlink_event(grid)
    linked.keys = ["\xfe"]
    linked.click_position = (91, 1)

    assert_that(display.read_char(grid)).is_none()

    event = library.pending_events[0]

    assert_that(event.kind).is_equal_to(EventType.MOUSE_INPUT)
    assert_that((event.val1, event.val2)).is_equal_to((10, 0))
    assert_that(grid.hyperlink_request).is_true()


# When only the link is wanted, the wait discards keystrokes and
# the selection answers through the event queue, never the return
# value.
def test_read_hyperlink_waits_through_keystrokes() -> None:
    stub = StubGlass(["k", "\xfe"])
    display = GlassFrontend(cast("Glass", stub))
    library = Glk(display)
    window = library.glk_window_open(None, 0, 0, WindowType.TEXT_BUFFER, 0)

    if window is None:
        pytest.fail("the buffer did not open")

    library.glk_set_window(window)
    library.glk_set_hyperlink(6)
    library.glk_put_string("onward")
    library.glk_set_hyperlink(0)
    library.glk_request_hyperlink_event(window)
    display.flush(library.root)
    stub.click_position = (2, 8)

    assert_that(display.read_hyperlink(window)).is_none()
    assert_that(library.pending_events[0].kind).is_equal_to(EventType.HYPERLINK)
    assert_that(library.pending_events[0].val1).is_equal_to(6)


# When only the mouse is wanted, the wait discards keystrokes and
# ends on an interruption: the click answers through the event
# queue, never the return value.
def test_read_mouse_waits_through_keystrokes() -> None:
    stub = StubGlass(["k", "\xfe"])
    display = GlassFrontend(cast("Glass", stub))
    library = Glk(display)
    canvas = library.glk_window_open(None, 0, 0, WindowType.GRAPHICS, 0)

    if canvas is None:
        pytest.fail("the canvas did not open")

    library.glk_request_mouse_event(canvas)
    stub.click_position = (2, 2)

    assert_that(display.read_mouse(canvas)).is_none()
    assert_that(library.pending_events[0].kind).is_equal_to(EventType.MOUSE_INPUT)


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
