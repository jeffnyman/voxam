import sys
import types
from collections.abc import Callable, Sequence
from fractions import Fraction

import pytest
from assertpy import assert_that

from voxam.aiff import Sound
from voxam.frontend import GRAPHICS_FONT, Status
from voxam.gallery import Gallery, Placard, Resolution, Scaling
from voxam.glass import (
    GraphicsFrontend,
    _fitted_faces,
    _key_characters,
    open_pygame_glass,
)
from voxam.painter import IDLE_HEARTBEAT
from voxam.png import Picture
from voxam.screen import BOLD, REVERSE, UPPER
from voxam.speaker import Fill, Finished, Speaker, Stream

WHITE = (255, 255, 255)
BLACK = (0, 0, 0)


class StubGlass:
    """A glass that records every blit and scripts every key."""

    columns = 30
    lines = 8
    cell_width = 9
    cell_height = 18

    def __init__(self, keys: list[str | None] | None = None) -> None:
        self.keys = list(keys or [])
        self.timeouts: list[float | None] = []
        self.painted: list[tuple[object, ...]] = []
        self.presents = 0
        self.pictures: list[object] = []
        self.drawn: list[
            tuple[Sequence[Sequence[tuple[int, ...]]], int, int, tuple[int, int]]
        ] = []
        self.typed: list[tuple[object, ...]] = []
        self.filled: list[tuple[object, ...]] = []
        self.shifted: list[tuple[int, int, int, int, int]] = []

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
        self.painted.append((row, column, text, ink, paper, bold, italic, graphics))

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
        self.typed.append(
            (line, column, characters, ink, paper, bold, italic, graphics)
        )

    def fill(
        self,
        line: int,
        column: int,
        height: int,
        width: int,
        colour: tuple[int, int, int],
    ) -> None:
        self.filled.append((line, column, height, width, colour))

    def shift(self, line: int, column: int, height: int, width: int, rise: int) -> None:
        self.shifted.append((line, column, height, width, rise))

    def present(self) -> None:
        self.presents += 1

    def key(self, timeout: float | None) -> str | None:
        self.timeouts.append(timeout)

        return self.keys.pop(0) if self.keys else None

    def picture(self, rows: Sequence[Sequence[tuple[int, int, int]]]) -> None:
        self.pictures.append(rows)

    def draw(
        self,
        rows: Sequence[Sequence[tuple[int, ...]]],
        line: int,
        column: int,
        size: tuple[int, int],
    ) -> None:
        self.drawn.append((rows, line, column, size))


def windowed(
    version: int = 5, keys: list[str | None] | None = None
) -> tuple[GraphicsFrontend, StubGlass]:
    glass = StubGlass(keys)

    return GraphicsFrontend(version, glass=glass), glass


def runs_containing(glass: StubGlass, text: str) -> list[tuple[object, ...]]:
    return [entry for entry in glass.painted if text in str(entry[2])]


# The frontend's font metrics are the glass's cell in real pixels
# -- the units a Version 6 story hears instead of the character
# glasses' 1-by-1 font (§8.4.2).
def test_the_font_metrics_are_the_glass_cell() -> None:
    frontend, _glass = windowed()

    assert_that(frontend.font_width).is_equal_to(9)
    assert_that(frontend.font_height).is_equal_to(18)


# A write lands in the model and the damaged row blits as runs of
# same-dressed cells, ending in a present.
def test_writes_blit_the_damaged_row() -> None:
    frontend, glass = windowed()

    frontend.write("hello")

    assert_that(frontend.model.row_text(1)).is_equal_to("hello")
    assert_that(runs_containing(glass, "hello")).is_not_empty()
    assert_that(glass.presents).is_greater_than(0)


# Reverse video swaps ink and paper; colours arrive as their RGB
# values (§8.7.1, §8.3.1).
def test_reverse_and_colours_dress_the_runs() -> None:
    frontend, glass = windowed()

    frontend.set_style(REVERSE)
    frontend.write("dark")

    (_, _, _, ink, paper, _, _, _) = runs_containing(glass, "dark")[0]

    assert_that(ink).is_equal_to(BLACK)
    assert_that(paper).is_equal_to(WHITE)

    frontend.set_style(0)
    frontend.set_colour(3, 4)
    frontend.write("leaf")

    (_, _, _, ink, paper, _, _, _) = runs_containing(glass, "leaf")[0]

    assert_that(ink).is_equal_to((204, 0, 0))
    assert_that(paper).is_equal_to((0, 204, 0))


# Bold text groups into one run wearing its flag.
def test_styles_group_into_runs() -> None:
    frontend, glass = windowed()

    frontend.set_style(BOLD)
    frontend.write("ab")

    (_, _, _, _, _, bold, _, graphics) = runs_containing(glass, "ab")[0]

    assert_that(bold).is_true()
    assert_that(graphics).is_false()


# The §16 font keeps its raw characters and marks the run as
# graphics: the glass owns the bitmaps now, reverse twins included,
# so no Unicode stand-in approximates a pixel and no ink swap
# fakes an inversion the spec already drew.
def test_font_3_runs_keep_their_characters_and_go_graphics() -> None:
    frontend, glass = windowed()

    frontend.set_font(GRAPHICS_FONT)
    frontend.write("({")

    (_, _, text, ink, paper, _, _, graphics) = runs_containing(glass, "({")[0]

    assert_that(text).is_equal_to("({")
    assert_that(graphics).is_true()
    assert_that(ink).is_equal_to(WHITE)
    assert_that(paper).is_equal_to(BLACK)


def galleried(png: bytes) -> tuple[GraphicsFrontend, StubGlass]:
    # The stub glass is 270 by 144 real pixels; a standard window
    # of 135 by 48 leaves an Elbow Room Factor of min(2, 3) = 2,
    # so listed picture 1 doubles while unlisted placard 7 stays
    # at one image pixel per screen pixel.
    glass = StubGlass()
    art: dict[int, bytes | Placard] = {
        1: png,
        7: Placard(width=3, height=2),
    }
    resolution = Resolution(135, 48, {1: Scaling(Fraction(1), None, None)})

    return GraphicsFrontend(6, glass=glass, gallery=Gallery(art, 27, resolution)), glass


# With a gallery hung, the frontend claims pictures and answers
# for them: real sizes -- Reso-scaled, since games lay out from
# these words -- and a real census; without one, the honest
# nothing (§15 picture_data, §11.1.4, Blorb: The Resolution
# Chunk).
def test_the_picture_seam_answers_from_the_gallery(tiny_png: bytes) -> None:
    frontend, _glass = galleried(tiny_png)

    assert_that(frontend.has_pictures).is_true()
    assert_that(frontend.picture_census()).is_equal_to((2, 27))
    assert_that(frontend.picture_data(1)).is_equal_to((4, 4))
    assert_that(frontend.picture_data(7)).is_equal_to((2, 3))
    assert_that(frontend.picture_data(9)).is_none()

    bare, _ = windowed()

    assert_that(bare.has_pictures).is_false()
    assert_that(bare.picture_census()).is_equal_to((0, 0))
    assert_that(bare.picture_data(1)).is_none()


# A picture draws its decoded pixels at the given screen position,
# stretched to the same Reso-scaled size picture_data reported; a
# Rect placard has none to draw, and drawing it shows nothing --
# the conforming answer, not a shortfall.
def test_pictures_draw_at_their_pixel_position(tiny_png: bytes) -> None:
    frontend, glass = galleried(tiny_png)

    frontend.draw_picture(1, 19, 37)

    ((rows, line, column, size),) = glass.drawn

    assert_that((line, column)).is_equal_to((19, 37))
    assert_that(size).is_equal_to((4, 4))
    assert_that(rows[0]).is_equal_to(((10, 20, 30), (40, 50, 60)))

    frontend.draw_picture(7, 1, 1)

    assert_that(glass.drawn).is_length(1)


# A scene plot that changes the Current Palette re-dresses the
# chrome already on screen, in place -- the hardware-palette
# recolouring of Infocom's own interpreters, which never replotted
# the banner (Blorb: The Adaptive Palette Chunk). A whole-screen
# erasure takes the chrome with it, and nothing is re-dressed.
def test_scene_plots_redress_the_drawn_chrome(
    indexed_png: Callable[..., bytes],
) -> None:
    glass = StubGlass()
    art: dict[int, bytes | Placard] = {
        1: indexed_png(((10, 10, 10), (20, 20, 20))),
        2: indexed_png(((30, 30, 30), (40, 40, 40))),
        7: indexed_png(((1, 1, 1), (2, 2, 2)), alphas=bytes([255, 255])),
    }
    frontend = GraphicsFrontend(
        6, glass=glass, gallery=Gallery(art, 0, adaptive=frozenset({7}))
    )

    frontend.draw_picture(1, 1, 1)
    frontend.draw_picture(7, 5, 9)
    glass.drawn.clear()

    frontend.draw_picture(2, 1, 1)

    ((_scene, _, _, _), (chrome, line, column, _size)) = glass.drawn

    assert_that((line, column)).is_equal_to((5, 9))
    assert_that(chrome[0]).is_equal_to(((30, 30, 30), (40, 40, 40)))

    # A single window's erasure leaves the chrome remembered; the
    # whole screen's takes it along.
    frontend.erase_window(1)
    frontend.erase_window(-1)
    glass.drawn.clear()
    frontend.draw_picture(1, 1, 1)

    assert_that(glass.drawn).is_length(1)


# A picture with clear pixels draws them see-through: the glass
# receives alpha-zero four-value pixels where the art has holes,
# so chrome like Arthur's banner frames the scene beneath instead
# of blotting it out (Blorb: Picture Resource Chunks).
def test_clear_pixels_travel_see_through(holey_png: bytes) -> None:
    glass = StubGlass()
    frontend = GraphicsFrontend(6, glass=glass, gallery=Gallery({9: holey_png}, 0))

    frontend.draw_picture(9, 1, 1)

    ((rows, _line, _column, _size),) = glass.drawn

    assert_that(rows[0]).is_equal_to(((200, 0, 0), (0, 0, 0, 0)))


# Erasing a picture paints its Reso-scaled region in the current
# background colour -- one background pixel, stretched by the
# glass -- and erasing a number the gallery does not hold quietly
# paints nothing (§15 erase_picture).
def test_erasure_paints_the_background_block(tiny_png: bytes) -> None:
    frontend, glass = galleried(tiny_png)

    frontend.set_colour(2, 4)
    frontend.erase_picture(7, 5, 6)

    ((rows, line, column, size),) = glass.drawn

    assert_that((line, column)).is_equal_to((5, 6))
    assert_that(rows).is_equal_to((((0, 204, 0),),))
    assert_that(size).is_equal_to((3, 2))

    frontend.erase_picture(99, 1, 1)

    assert_that(glass.drawn).is_length(1)


# A Version 6 session plays on the §8.8 stage: the frontend
# claims it, placements land there, and text follows the placed
# windows; other versions have no stage and placements change
# nothing.
def test_version_6_plays_on_the_stage() -> None:
    frontend, glass = windowed(version=6)

    assert_that(frontend.has_stage).is_true()

    frontend.place_window(2, 19, 19, 36, 90)
    frontend.set_window(2)
    frontend.set_cursor(1, 1)
    frontend.write("staged")

    assert_that(frontend.model.row_text(2)).is_equal_to("  staged")

    # The glass heard the text at the window's true unit position
    # -- (19, 19), not the nearest cell -- one dressed glyph at a
    # time.
    assert_that(glass.typed[0][:3]).is_equal_to((19, 19, "s"))
    assert_that(glass.typed[1][:3]).is_equal_to((19, 28, "t"))
    assert_that(glass.presents).is_greater_than(0)

    frontend.scroll_window(2, 18)

    assert_that(frontend.model.row_text(2)).is_equal_to("")
    assert_that(glass.shifted).is_equal_to([(19, 19, 36, 90, 18)])
    assert_that(glass.filled[-1]).is_equal_to((37, 19, 18, 90, (0, 0, 0)))

    frontend.set_cursor(1, 1)
    frontend.set_margins(2, 18, 0)
    frontend.write("m")

    assert_that(frontend.model.row_text(2)).is_equal_to("    m")
    assert_that(glass.typed[-1][:3]).is_equal_to((19, 37, "m"))

    bare, _ = windowed()

    assert_that(bare.has_stage).is_false()

    bare.place_window(2, 1, 1, 18, 18)
    bare.scroll_window(2, 18)
    bare.set_margins(2, 9, 9)


# The shadow keeps unchanged cells off the glass: a second write
# paints only its own cells, never the rest of the row -- which is
# what lets a drawn picture survive beside text (§8.8.3).
def test_unchanged_cells_stay_unpainted() -> None:
    frontend, glass = windowed()

    frontend.write("hi")
    glass.painted.clear()
    frontend.write("!")

    assert_that([entry[2] for entry in glass.painted]).is_equal_to(["!"])


# A stage erasure reaches the glass as a fill of the window's own
# unit rectangle -- pixel-true, so any picture in the region is
# legitimately painted over (§8.8.5.3) -- and a whole-screen
# erasure fills the whole screen; clear() after a frontispiece
# fills it too, and no cell blitting happens on the stage at all.
def test_stage_erasures_fill_their_true_rectangles() -> None:
    frontend, glass = windowed(version=6)

    frontend.place_window(4, 19, 19, 36, 90)
    frontend.erase_window(4)

    assert_that(glass.filled[-1]).is_equal_to((19, 19, 36, 90, (0, 0, 0)))

    frontend.erase_window(-2)

    assert_that(glass.filled[-1]).is_equal_to((1, 1, 144, 270, (0, 0, 0)))

    frontend.clear()

    assert_that(glass.filled[-1]).is_equal_to((1, 1, 144, 270, (0, 0, 0)))
    assert_that(glass.painted).is_empty()


# Typing on the stage rubs out in pixels: the erased cell arrives
# as a fill at the window's true position (§15 read).
def test_v6_typing_rubs_out_in_pixels() -> None:
    frontend, glass = windowed(version=6, keys=["a", "\x7f", "\n"])

    frontend.read_line()

    assert_that(glass.filled[-1]).is_equal_to((1, 1, 18, 9, (0, 0, 0)))


# The status line draws through the model like any other row --
# the v3 pre-read redraw path.
def test_the_status_line_blits() -> None:
    frontend, glass = windowed(version=3)

    frontend.show_status(Status("Kitchen", 10, 2, time_game=False))

    assert_that(runs_containing(glass, "Kitchen")).is_not_empty()


# The line editor runs on glass keys: typing echoes through the
# model, backspace rubs out, and enter delivers the line.
def test_read_line_edits_through_the_model() -> None:
    frontend, _glass = windowed(keys=["\x1b", "\x7f", "h", "a", "\x7f", "i", "\n"])

    line = frontend.read_line()

    assert_that(line).is_equal_to("hi")
    assert_that(frontend.model.row_text(1)).is_equal_to("hi")


# A repaint with no damage presents nothing: the frame only flips
# when a row actually changed.
def test_undamaged_repaints_present_nothing() -> None:
    frontend, glass = windowed()

    frontend.write("hi")

    shown = glass.presents

    frontend.write("")

    assert_that(glass.presents).is_equal_to(shown)


# A timed key answers None on expiry, the machine's wall-clock
# cue; the game's own timeout passes straight through.
def test_read_key_reports_expired_timeouts() -> None:
    frontend, glass = windowed()

    assert_that(frontend.read_key(0.5)).is_none()
    assert_that(glass.timeouts).is_equal_to([0.5])


# An infinite wait heartbeats through the idle callback, exactly
# as the terminal painter waits.
def test_infinite_waits_heartbeat_through_idle() -> None:
    frontend, glass = windowed(keys=[None, "y"])
    beats: list[int] = []
    frontend.idle = lambda: beats.append(1)

    assert_that(frontend.read_key()).is_equal_to("y")
    assert_that(beats).is_length(1)
    assert_that(glass.timeouts).is_equal_to([IDLE_HEARTBEAT, IDLE_HEARTBEAT])


# Window operations flow through the model: a split, a cursor
# move, and the cursor read back (§8.7.2).
def test_window_operations_flow_through_the_model() -> None:
    frontend, _glass = windowed()

    frontend.split_window(3)
    frontend.set_window(UPPER)
    frontend.set_cursor(2, 5)

    assert_that(frontend.cursor_position()).is_equal_to((2, 5))

    frontend.write_rectangle(["ab", "cd"])

    assert_that(frontend.model.row_text(2)).contains("ab")

    frontend.erase_window(-1)
    frontend.erase_line()
    frontend.set_buffering(False)
    frontend.bleep(1)

    assert_that(frontend.model.row_text(1)).is_equal_to("")


# The cover shows as a real bitmap, waits on a key, and clears.
def test_the_frontispiece_shows_and_clears() -> None:
    frontend, glass = windowed(keys=["x"])
    rows = (((255, 0, 0),) * 2, ((0, 255, 0),) * 2)

    frontend.show_frontispiece(Picture(2, 2, rows), pixels=True)

    assert_that(glass.pictures).is_length(1)
    assert_that(glass.presents).is_greater_than(0)
    assert_that(glass.keys).is_empty()


class SoundStream:
    """Captures the speaker's callbacks so a test can drive them."""

    def __init__(self, fill: Fill, finished: Finished) -> None:
        self.fill = fill
        self.finished = finished

    def start(self) -> None:
        pass

    def abort(self) -> None:
        pass

    def close(self) -> None:
        pass


# The sound seam delegates to a speaker when one arrived, and is
# inert without one -- the painter's own contract, third frontend.
def test_the_sound_seam_delegates_or_stays_inert() -> None:
    streams: list[SoundStream] = []

    def opener(_rate: float, fill: Fill, finished: Finished) -> Stream:
        stream = SoundStream(fill, finished)
        streams.append(stream)

        return stream

    speaker = Speaker({3: Sound(1, 8, 1000.0, 2, b"\x01\x02")}, frozenset(), opener)
    glass = StubGlass()
    frontend = GraphicsFrontend(5, glass=glass, speaker=speaker)

    assert_that(frontend.has_sounds).is_true()
    assert_that(frontend.play_sound(3, 8, 1)).is_true()
    assert_that(frontend.sound_playing()).is_true()

    frontend.stop_sound(None)
    frontend.wait_for_sound()

    assert_that(frontend.sound_finished()).is_false()

    quiet, _ = windowed()

    assert_that(quiet.has_sounds).is_false()
    assert_that(quiet.play_sound(3, 8, 1)).is_false()
    assert_that(quiet.sound_playing()).is_false()
    assert_that(quiet.sound_finished()).is_false()

    quiet.stop_sound(None)
    quiet.wait_for_sound()


# --- the real pygame adapter, driven by a fake module ---


class FakeFace:
    def __init__(self, advance: int) -> None:
        self._advance = advance

    def metrics(self, _character: str) -> list[tuple[int, int, int, int, int]]:
        return [(0, 0, 0, 0, self._advance)]

    def get_linesize(self) -> int:
        return 18

    def render(
        self, character: str, antialias: object, colour: object
    ) -> tuple[object, ...]:
        del antialias

        return ("glyph", character, colour)


class FakeRect:
    def __init__(self, x: int, y: int, width: int, height: int) -> None:
        self.x, self.y, self.width, self.height = x, y, width, height

    def clip(self, other: tuple[int, int, int, int]) -> "FakeRect":
        x, y, width, height = other
        left = max(self.x, x)
        top = max(self.y, y)
        right = min(self.x + self.width, x + width)
        bottom = min(self.y + self.height, y + height)

        return FakeRect(left, top, max(right - left, 0), max(bottom - top, 0))


class FakeRegion:
    def __init__(self, region: FakeRect) -> None:
        self.region = region

    def copy(self) -> tuple[object, ...]:
        return ("copied", self.region.x, self.region.y)


class FakeScreen:
    def __init__(self) -> None:
        self.fills: list[tuple[object, ...]] = []
        self.blits: list[tuple[object, ...]] = []

    def fill(self, colour: object, rect: object = None) -> None:
        self.fills.append((colour, rect))

    def blit(self, surface: object, position: object, area: object = None) -> None:
        self.blits.append(
            (surface, position) if area is None else (surface, position, area)
        )

    def get_size(self) -> tuple[int, int]:
        return (270, 144)

    def get_rect(self) -> FakeRect:
        return FakeRect(0, 0, *self.get_size())

    def subsurface(self, region: FakeRect) -> FakeRegion:
        return FakeRegion(region)


class FakeSurface:
    def __init__(self, size: tuple[int, int], flags: int = 0) -> None:
        self.size = size
        self.flags = flags
        self.pixels: list[tuple[object, ...]] = []

    def set_at(self, position: tuple[int, int], colour: object) -> None:
        self.pixels.append((position, colour))


def fake_pygame(
    events: list[object] | None = None, *, bold_advance: int = 9
) -> types.SimpleNamespace:
    screen = FakeScreen()
    queue = list(events or [])
    ticks = {"now": 0}

    def get_ticks() -> int:
        ticks["now"] += 300

        return ticks["now"]

    def sysfont(
        _families: str, _size: int, bold: bool = False, italic: bool = False
    ) -> FakeFace:
        del italic

        return FakeFace(bold_advance if bold else 9)

    module = types.SimpleNamespace(
        QUIT=1,
        KEYDOWN=2,
        SRCALPHA=65536,
        init=lambda: None,
        display=types.SimpleNamespace(
            set_mode=lambda _size: screen,
            set_caption=lambda _title: None,
            flip=lambda: None,
        ),
        font=types.SimpleNamespace(SysFont=sysfont),
        event=types.SimpleNamespace(get=lambda: [queue.pop(0)] if queue else []),
        time=types.SimpleNamespace(get_ticks=get_ticks, wait=lambda _ms: None),
        Surface=FakeSurface,
        transform=types.SimpleNamespace(
            scale=lambda surface, size: ("scaled", surface, size)
        ),
        screen=screen,
    )

    for number, name in enumerate(
        [
            "K_RETURN",
            "K_KP_ENTER",
            "K_BACKSPACE",
            "K_DELETE",
            "K_ESCAPE",
            "K_UP",
            "K_DOWN",
            "K_LEFT",
            "K_RIGHT",
        ]
        + [f"K_F{n}" for n in range(1, 13)],
        start=100,
    ):
        setattr(module, name, number)

    return module


def keydown(module: types.SimpleNamespace, key: int, unicode: str = "") -> object:
    return types.SimpleNamespace(type=module.KEYDOWN, key=key, unicode=unicode)


# The doorway builds a real glass over the fake module: the window
# sized from the measured cell, glyphs blitted over filled paper,
# spaces skipped.
def test_the_pygame_doorway_builds_and_paints(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = fake_pygame()

    monkeypatch.setitem(sys.modules, "pygame", module)

    glass = open_pygame_glass()

    assert_that(glass.cell_width).is_equal_to(9)
    assert_that(glass.cell_height).is_equal_to(18)

    glass.paint(
        1, 2, "a b", (1, 2, 3), (4, 5, 6), bold=False, italic=False, graphics=False
    )

    screen = module.screen

    assert_that(screen.fills[0][0]).is_equal_to((4, 5, 6))
    assert_that([blit[0][1] for blit in screen.blits]).is_equal_to(["a", "b"])

    glass.present()


# A graphics run blits §16's own bitmap: an 8x8 surface, ink on
# the lit pixels and paper elsewhere, stretched edge-to-edge over
# the cell so map lines meet with no seam -- and cached, so the
# same character in the same dress builds its tile once. Code 71
# is the proof no terminal could pass: a road tip of exactly one
# pixel. A character with no bitmap falls back to the face.
def test_the_pygame_doorway_draws_font_3_bitmaps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = fake_pygame()

    monkeypatch.setitem(sys.modules, "pygame", module)

    glass = open_pygame_glass()
    screen = module.screen
    screen.blits.clear()

    glass.paint(1, 1, "G", WHITE, BLACK, bold=False, italic=False, graphics=True)

    scaled, tile, size = screen.blits[0][0]

    assert_that(scaled).is_equal_to("scaled")
    assert_that(size).is_equal_to((9, 18))
    assert_that(tile.size).is_equal_to((8, 8))
    assert_that(tile.pixels).is_length(64)

    lit = [position for position, colour in tile.pixels if colour == WHITE]

    assert_that(lit).is_equal_to([(7, 0)])

    glass.paint(2, 1, "G", WHITE, BLACK, bold=False, italic=False, graphics=True)

    assert_that(screen.blits[1][0]).is_same_as(screen.blits[0][0])

    glass.paint(3, 1, "é", WHITE, BLACK, bold=False, italic=False, graphics=True)

    assert_that(screen.blits[2][0][0]).is_equal_to("glyph")


# Keys translate to their §3.8 characters, printables pass through,
# a timeout expires against the clock, and the close button ends
# the session as end of input.
def test_the_pygame_doorway_translates_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = fake_pygame()

    monkeypatch.setitem(sys.modules, "pygame", module)

    glass = open_pygame_glass()

    scripted = iter(
        [
            [],
            [types.SimpleNamespace(type=99)],
            [keydown(module, module.K_UP)],
            [keydown(module, 998, ""), keydown(module, 999, "z")],
            [],
            [],
            [types.SimpleNamespace(type=module.QUIT)],
        ]
    )
    module.event.get = lambda: next(scripted, [])

    assert_that(glass.key(None)).is_equal_to("\x81")
    assert_that(glass.key(None)).is_equal_to("z")
    assert_that(glass.key(0.5)).is_none()

    with pytest.raises(EOFError):
        glass.key(None)


# A cover picture becomes a surface, scales by whole steps, and
# blits centred over cleared paper.
def test_the_pygame_doorway_shows_pictures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = fake_pygame()

    monkeypatch.setitem(sys.modules, "pygame", module)

    glass = open_pygame_glass()
    screen = module.screen
    screen.fills.clear()
    screen.blits.clear()

    glass.picture((((1, 2, 3),) * 2, ((4, 5, 6),) * 2))

    assert_that(screen.fills[0][0]).is_equal_to((0, 0, 0))
    assert_that(screen.blits).is_length(1)

    glass.picture(())


# draw blits pixel rows with their top left at a 1-based pixel
# position -- §8.8.1's own origin -- stretched to the asked size,
# and an empty picture draws nothing at all.
def test_the_pygame_doorway_draws_at_pixel_positions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = fake_pygame()

    monkeypatch.setitem(sys.modules, "pygame", module)

    glass = open_pygame_glass()
    screen = module.screen
    screen.blits.clear()

    glass.draw((((1, 2, 3),) * 2, ((4, 5, 6),) * 2), 10, 30, (4, 4))

    ((blitted, position),) = screen.blits
    scaled, surface, size = blitted

    assert_that(position).is_equal_to((29, 9))
    assert_that(scaled).is_equal_to("scaled")
    assert_that(size).is_equal_to((4, 4))
    assert_that(surface.size).is_equal_to((2, 2))
    assert_that(surface.pixels[0]).is_equal_to(((0, 0), (1, 2, 3)))

    glass.draw((), 1, 1, (1, 1))

    assert_that(screen.blits).is_length(1)

    # A clear pixel rides its alpha-zero fourth value onto a
    # per-pixel-alpha surface, surviving the scale.
    glass.draw((((1, 2, 3), (7, 8, 9, 0)),), 1, 1, (2, 1))

    _, layered, _ = screen.blits[1][0]

    assert_that(layered.flags).is_equal_to(module.SRCALPHA)
    assert_that(layered.pixels[1]).is_equal_to(((1, 0), (7, 8, 9, 0)))


# A standard window size shapes the doorway's glass: the height
# keeps the classic 24 lines and the width follows the art's own
# proportions, so a game's layout arithmetic nests the way its
# artists drew it (Blorb: The Resolution Chunk).
def test_the_standard_shape_reaches_the_doorway(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = fake_pygame()

    monkeypatch.setitem(sys.modules, "pygame", module)

    shaped = open_pygame_glass((320, 200))

    assert_that(shaped.columns).is_equal_to(77)
    assert_that(shaped.lines).is_equal_to(24)

    classic = open_pygame_glass()

    assert_that(classic.columns).is_equal_to(80)


# Fills paint pixel rectangles, and shifts slide a region's pixels
# up or down, clipped to the screen; an off-screen shift moves
# nothing at all.
def test_the_pygame_doorway_fills_and_shifts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = fake_pygame()

    monkeypatch.setitem(sys.modules, "pygame", module)

    glass = open_pygame_glass()
    screen = module.screen
    screen.fills.clear()
    screen.blits.clear()

    glass.fill(3, 5, 10, 20, (7, 8, 9))

    assert_that(screen.fills[-1]).is_equal_to(((7, 8, 9), (4, 2, 20, 10)))

    glass.shift(1, 1, 50, 40, 18)

    surface, position, area = screen.blits[-1]

    assert_that(surface[0]).is_equal_to("copied")
    assert_that(position).is_equal_to((0, 0))
    assert_that(area).is_equal_to((0, 18, 40, 50))

    glass.shift(1, 1, 50, 40, -18)

    _surface, position, area = screen.blits[-1]

    assert_that(position).is_equal_to((0, 18))
    assert_that(area).is_equal_to((0, 0, 40, 32))

    glass.shift(1000, 1000, 10, 10, 5)

    assert_that(screen.blits).is_length(2)


# A face whose bold steps wider than the cell is dropped: bold
# falls back to the regular face rather than creeping columns --
# the macOS fake-bold defect, measured out.
def test_misfit_faces_are_dropped() -> None:
    creeping = fake_pygame(bold_advance=10)

    faces = _fitted_faces(creeping)

    assert_that(faces).does_not_contain_key((True, False))
    assert_that(faces).contains_key((False, False))

    true_faces = _fitted_faces(fake_pygame())

    assert_that(true_faces).contains_key((True, True))


def test_key_constants_map_to_their_characters() -> None:
    module = fake_pygame()
    characters = _key_characters(module)

    assert_that(characters[module.K_UP]).is_equal_to("\x81")
    assert_that(characters[module.K_F1]).is_equal_to("\x85")
    assert_that(characters[module.K_RETURN]).is_equal_to("\n")
