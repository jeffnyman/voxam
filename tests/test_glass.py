import sys
import types
import zlib
from collections.abc import Callable, Sequence
from fractions import Fraction
from typing import cast

import pytest
from assertpy import assert_that

from voxam.aiff import Sound
from voxam.blorb import Blorb
from voxam.frontend import GRAPHICS_FONT, Status
from voxam.gallery import Gallery, Placard, Resolution, Scaling
from voxam.glass import (
    GraphicsFrontend,
    _BandedGlass,
    _fitted_faces,
    _key_characters,
    layered,
    open_pygame_glass,
)
from voxam.glulx.glk.resources import Resources
from voxam.iff import chunk
from voxam.painter import IDLE_HEARTBEAT
from voxam.png import Picture
from voxam.screen import BOLD, REVERSE, UPPER, ScreenModel
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
        self.snapshots: list[str] = []
        self.pictures: list[object] = []
        self.drawn: list[
            tuple[Sequence[Sequence[tuple[int, ...]]], int, int, tuple[int, int]]
        ] = []
        self.typed: list[tuple[object, ...]] = []
        self.filled: list[tuple[object, ...]] = []
        self.shifted: list[tuple[int, int, int, int, int]] = []
        self.samples: list[tuple[int, int]] = []
        self.pixel = (10, 20, 30)
        self.clicked: tuple[int, int] | None = None
        self.entitled: list[str] = []

    def sample(self, line: int, column: int) -> tuple[int, int, int]:
        self.samples.append((line, column))

        return self.pixel

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

    def snapshot(self, path: str) -> None:
        self.snapshots.append(path)

    def entitle(self, title: str) -> None:
        self.entitled.append(title)

    def key(self, timeout: float | None) -> str | None:
        self.timeouts.append(timeout)

        return self.keys.pop(0) if self.keys else None

    def click(self) -> tuple[int, int] | None:
        return self.clicked

    def picture(self, rows: Sequence[Sequence[tuple[int, int, int]]]) -> None:
        self.pictures.append(rows)

    def photograph(
        self, data: bytes
    ) -> Sequence[Sequence[tuple[int, int, int]]] | None:
        del data

        # A stub carries no pygame decoders; the real window does.
        return None

    def draw(
        self,
        rows: Sequence[Sequence[tuple[int, ...]]],
        line: int,
        column: int,
        size: tuple[int, int],
    ) -> None:
        self.drawn.append((rows, line, column, size))


class MeddlingGlass(StubGlass):
    """A glass whose key read first runs a planted disturbance.

    The disturbance stands in for a timed interrupt printing while
    a read waits -- the machine's §15 seam, exercised without a
    machine.
    """

    def __init__(self, keys: list[str | None] | None = None) -> None:
        super().__init__(keys)
        self.meddler: Callable[[], None] | None = None

    def key(self, timeout: float | None) -> str | None:
        if self.meddler is not None:
            meddle, self.meddler = self.meddler, None
            meddle()

        return super().key(timeout)


def windowed(
    version: int = 5,
    keys: list[str | None] | None = None,
    theme: str = "classic",
) -> tuple[GraphicsFrontend, StubGlass]:
    # The mechanics tests pin "classic" so ink and paper stay the
    # plain WHITE and BLACK they assert; the default theme and the
    # rest have their own tests below.
    glass = StubGlass(keys)

    return GraphicsFrontend(version, glass=glass, theme=theme), glass


def runs_containing(glass: StubGlass, text: str) -> list[tuple[object, ...]]:
    return [entry for entry in glass.painted if text in str(entry[2])]


def real_png(width: int, height: int) -> bytes:
    """A genuine decodable truecolour PNG, one flat colour."""

    def framed(tag: bytes, payload: bytes) -> bytes:
        return (
            len(payload).to_bytes(4, "big")
            + tag
            + payload
            + zlib.crc32(tag + payload).to_bytes(4, "big")
        )

    header = (
        width.to_bytes(4, "big") + height.to_bytes(4, "big") + bytes([8, 2, 0, 0, 0])
    )
    raw = b"".join(b"\x00" + b"\x10\x20\x30" * width for _ in range(height))

    return (
        b"\x89PNG\r\n\x1a\n"
        + framed(b"IHDR", header)
        + framed(b"IDAT", zlib.compress(raw))
        + framed(b"IEND", b"")
    )


def arc_resources(art: bytes | None = None, kind: bytes = b"PNG ") -> Resources:
    """Band resources: one picture 8, a mode-9 PNG unless told else."""

    if art is None:
        art = real_png(40, 9)

    ridx = chunk(b"RIdx", (1).to_bytes(4, "big") + b"\x00" * 12)
    offset = 12 + len(ridx)
    index = (
        (1).to_bytes(4, "big")
        + b"Pict"
        + (8).to_bytes(4, "big")
        + offset.to_bytes(4, "big")
    )

    return Resources(
        Blorb.parse(chunk(b"FORM", b"IFRS" + chunk(b"RIdx", index) + chunk(kind, art)))
    )


# The glass takes the contract's fixed-band profile: the sidecar's
# art names its mode by aspect at boot, whole rows stand reserved
# above the screen -- the model, the header claim, and every paint
# below born re-based -- and the picture hangs, dedups, and clears
# to an empty band that never comes down. A clear() repaints the
# hanging art; a click in the band lands nowhere; art nothing can
# decode is ignored; and a glass with no sidecar, or art in no
# known mode, keeps the whole screen unclaimed.
def test_the_fixed_band_stands_from_boot() -> None:
    glass = StubGlass()
    frontend = GraphicsFrontend(5, glass=glass, arc=arc_resources())

    assert_that(frontend.has_arc_images).is_true()
    assert_that(frontend.screen_lines).is_equal_to(4)

    # A clear before anything hung reserves its silence.
    frontend.draw_arc_image(0, 9)

    assert_that(glass.filled).is_empty()

    frontend.write("hello")

    assert_that(runs_containing(glass, "hello")[0][0]).is_equal_to(5)

    frontend.draw_arc_image(8, 9)

    assert_that(glass.filled[-1][:4]).is_equal_to((1, 1, 72, 270))
    assert_that(glass.drawn[-1][1:]).is_equal_to((1, 1, (270, 61)))

    before = len(glass.drawn)

    frontend.draw_arc_image(8, 9)  # the same picture: nothing owed
    frontend.draw_arc_image(9, 9)  # no such picture: ignored
    frontend.draw_arc_image(8, 7)  # no such mode: ignored

    assert_that(glass.drawn).is_length(before)

    # A clear() strikes the band and paints the picture back.
    frontend.clear()

    assert_that(glass.drawn).is_length(before + 1)

    # Id 0 empties the band; the region stands reserved either way.
    frontend.draw_arc_image(0, 9)

    assert_that(glass.filled[-1][:4]).is_equal_to((1, 1, 72, 270))
    assert_that(frontend.screen_lines).is_equal_to(4)

    # A click in the band lands nowhere; below it, re-based cells.
    glass.clicked = (10, 40)

    assert_that(frontend.click_position()).is_none()

    glass.clicked = (10, 90)

    assert_that(frontend.click_position()).is_equal_to((2, 1))

    # No sidecar: the whole screen, no claim.
    bare, _ = windowed()

    assert_that(bare.has_arc_images).is_false()
    assert_that(bare.screen_lines).is_equal_to(8)

    # Art in no known mode reserves nothing.
    odd = GraphicsFrontend(5, glass=StubGlass(), arc=arc_resources(real_png(40, 20)))

    assert_that(odd.has_arc_images).is_false()

    # Art whose body will not decode is ignored at the draw; a
    # photographic picture asks the window, and this stub carries
    # no decoders -- both refusals silent, the band left standing.
    broken = StubGlass()
    torn = GraphicsFrontend(5, glass=broken, arc=arc_resources(real_png(40, 9)[:50]))

    torn.draw_arc_image(8, 9)

    assert_that(broken.drawn).is_empty()

    photographic = StubGlass()
    jpeg = (
        b"\xff\xd8\xff\xc0\x00\x08\x08"
        + (9).to_bytes(2, "big")
        + (40).to_bytes(2, "big")
    )
    unphotographed = GraphicsFrontend(
        5, glass=photographic, arc=arc_resources(jpeg, kind=b"JPEG")
    )

    unphotographed.draw_arc_image(8, 9)

    assert_that(photographic.drawn).is_empty()

    # A clear() with the band standing empty strikes and moves on;
    # one whose hung art has stopped decoding strikes and stands.
    torn.clear()

    assert_that(broken.drawn).is_empty()

    torn._hung = (8, 9)

    torn.clear()

    assert_that(broken.drawn).is_empty()

    # A band taller than the window itself reserves nothing.
    class Short(StubGlass):
        lines = 3

    cramped = GraphicsFrontend(5, glass=Short(), arc=arc_resources())

    assert_that(cramped.has_arc_images).is_false()


# The banded wrapper offsets the whole Glass surface -- the pixel
# roads the two-window screen never walks included, since the
# protocol demands them all -- and passes the rest through whole.
def test_the_banded_glass_offsets_the_whole_surface() -> None:
    inner = StubGlass()
    wrapper = _BandedGlass(inner, 4)

    wrapper.text(1, 1, "x", WHITE, BLACK, bold=False, italic=False, graphics=False)

    assert_that(inner.typed[-1][0]).is_equal_to(73)

    wrapper.fill(1, 1, 5, 5, BLACK)

    assert_that(inner.filled[-1][0]).is_equal_to(73)

    wrapper.shift(1, 1, 5, 5, 2)

    assert_that(inner.shifted[-1][0]).is_equal_to(73)

    wrapper.draw([[(1, 2, 3)]], 1, 1, (2, 2))

    assert_that(inner.drawn[-1][1]).is_equal_to(73)

    wrapper.sample(1, 1)

    assert_that(inner.samples[-1]).is_equal_to((73, 1))

    wrapper.present()

    assert_that(inner.presents).is_equal_to(1)

    wrapper.entitle("banded")

    assert_that(inner.entitled).is_equal_to(["banded"])

    assert_that(wrapper.key(None)).is_none()
    assert_that(wrapper.photograph(b"x")).is_none()
    assert_that(wrapper.click()).is_none()

    wrapper.picture([[(1, 2, 3)]])

    assert_that(inner.pictures).is_length(1)


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


# The home look is the gentle dark: an untouched glass sets its
# text in soft grey on charcoal, not the pure white on black that
# glares (#319).
def test_the_default_theme_softens_the_glass() -> None:
    glass = StubGlass()
    frontend = GraphicsFrontend(5, glass=glass)

    frontend.write("plain")

    (_, _, _, ink, paper, _, _, _) = runs_containing(glass, "plain")[0]

    assert_that(ink).is_equal_to((214, 214, 214))
    assert_that(paper).is_equal_to((28, 28, 28))


# Each theme is a whole dressing of the default ink and paper.
def test_a_theme_dresses_the_default_ink_and_paper() -> None:
    glass = StubGlass()
    frontend = GraphicsFrontend(5, glass=glass, theme="sepia")

    frontend.write("aged")

    (_, _, _, ink, paper, _, _, _) = runs_containing(glass, "aged")[0]

    assert_that(ink).is_equal_to((67, 56, 42))
    assert_that(paper).is_equal_to((244, 236, 216))


# Codes 9 and 2 -- "white" and "black" -- follow the theme, so a
# game resetting to them looks no harsher than one that left the
# colours alone; the other six stay their true values (§8.3.3).
def test_white_and_black_follow_the_theme() -> None:
    glass = StubGlass()
    frontend = GraphicsFrontend(5, glass=glass, theme="dark")

    frontend.set_colour(9, 2)
    frontend.write("reset")

    (_, _, _, ink, paper, _, _, _) = runs_containing(glass, "reset")[0]

    assert_that(ink).is_equal_to((214, 214, 214))
    assert_that(paper).is_equal_to((28, 28, 28))

    frontend.set_colour(3, 4)
    frontend.write("leaf")

    (_, _, _, ink, paper, _, _, _) = runs_containing(glass, "leaf")[0]

    assert_that(ink).is_equal_to((204, 0, 0))
    assert_that(paper).is_equal_to((0, 204, 0))


# The "classic" theme is the old look kept whole: pure white on
# black, codes 9 and 2 included.
def test_classic_keeps_pure_white_on_black() -> None:
    glass = StubGlass()
    frontend = GraphicsFrontend(5, glass=glass, theme="classic")

    frontend.set_colour(9, 2)
    frontend.write("pure")

    (_, _, _, ink, paper, _, _, _) = runs_containing(glass, "pure")[0]

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


# On the stage, erase_line's pixel form reaches the glass as a
# fill of exactly that width at the cursor (§8.8.5.2).
def test_a_staged_erase_line_fills_its_pixel_width() -> None:
    frontend, glass = windowed(version=6)

    frontend.place_window(2, 19, 19, 36, 90)
    frontend.set_window(2)
    frontend.erase_line(25)

    assert_that(glass.filled[-1]).is_equal_to((19, 19, 18, 25, (0, 0, 0)))


# On the stage, colour -1 is the colour of the pixel under the
# cursor (§8.3.1): the glass is read at the cursor's own unit
# position and the sampled colour dresses the text that follows --
# here both ink and paper, the second request reusing the code the
# first one earned (§8.3.5.2's dynamic range).
def test_colour_minus_one_samples_the_pixel_under_the_cursor() -> None:
    frontend, glass = windowed(version=6)

    frontend.place_window(2, 19, 19, 36, 90)
    frontend.set_window(2)
    frontend.set_cursor(1, 10)
    frontend.set_colour(-1, -1)

    assert_that(glass.samples).is_equal_to([(19, 28), (19, 28)])

    frontend.write("s")

    (_, _, _, ink, paper, _, _, _) = glass.typed[-1]

    assert_that(ink).is_equal_to((10, 20, 30))
    assert_that(paper).is_equal_to((10, 20, 30))


# The sample is read where printing left the cursor: text
# advances it, and colour -1 reads the pixel there -- window 0's
# own origin plus two cells of advance.
def test_the_sample_follows_the_advancing_cursor() -> None:
    frontend, glass = windowed(version=6)

    frontend.write("ab")
    frontend.set_colour(2, -1)

    assert_that(glass.samples).is_equal_to([(1, 19)])


# A window whose background was sampled erases in that colour: the
# fill arrives on the glass wearing the sampled RGB, not a code.
def test_a_sampled_background_erases_in_its_own_colour() -> None:
    frontend, glass = windowed(version=6)

    frontend.place_window(4, 19, 19, 36, 90)
    frontend.set_window(4)
    frontend.set_colour(2, -1)
    frontend.erase_window(4)

    assert_that(glass.filled[-1]).is_equal_to((19, 19, 36, 90, (10, 20, 30)))


# The Version 6 greys are real paint (§8.3.1): light, medium, and
# dark grey at codes 10 to 12, their values scaled from the spec's
# own true-colour equivalents.
def test_the_version_6_greys_are_real_paint() -> None:
    frontend, glass = windowed(version=6)

    frontend.set_colour(10, 12)
    frontend.write("g")

    (_, _, _, ink, paper, _, _, _) = glass.typed[-1]

    assert_that(ink).is_equal_to((181, 181, 181))
    assert_that(paper).is_equal_to((90, 90, 90))


# A screenful of scrolled text pauses behind a [MORE] in reverse
# video at the window's bottom; the answering key is spent, the
# prompt's cells fill back over, and play continues (§8.8.3.2.6).
def test_the_stage_pauses_behind_more() -> None:
    frontend, glass = windowed(version=6, keys=[None, "m", "x"])

    frontend.write("\n".join(str(n) for n in range(1, 9)))

    paused = [entry for entry in glass.typed if entry[2] == "[MORE]"]

    assert_that(paused).is_length(1)
    assert_that(paused[0][:2]).is_equal_to((127, 1))
    assert_that(glass.filled[-1]).is_equal_to((127, 1, 18, 54, (0, 0, 0)))

    # A read is the player catching up: the budget refills, and a
    # -999 count from the game never pauses again (§8.8.3.2.6).
    assert_that(frontend.read_key()).is_equal_to("x")

    frontend.set_line_count(0, -999)
    frontend.write("\n" * 30)

    assert_that([entry for entry in glass.typed if entry[2] == "[MORE]"]).is_length(1)

    bare, _ = windowed()

    bare.set_line_count(0, -999)


# The prompt cleans up after itself in the window's own colours:
# it wears them reversed, its erase fills the window's white --
# never the machine's black -- and any text the pause landed on is
# rebuilt from the grid. Zork Zero's death question kept losing
# its first word to exactly this patch (§8.8.3.2.6).
def test_more_wears_the_window_colours_and_restores_the_text() -> None:
    frontend, glass = windowed(version=6, keys=["m", "m"])

    frontend.set_colour(2, 9)
    frontend.write("\n".join(str(n) for n in range(1, 16)))

    prompts = [entry for entry in glass.typed if entry[2] == "[MORE]"]

    assert_that(prompts).is_length(2)
    assert_that(prompts[1][3]).is_equal_to((255, 255, 255))
    assert_that(prompts[1][4]).is_equal_to((0, 0, 0))
    assert_that(glass.filled).contains((127, 1, 18, 54, (255, 255, 255)))

    positions = [n for n, entry in enumerate(glass.typed) if entry[2] == "[MORE]"]
    restored = glass.typed[positions[1] + 1 :][:2]

    assert_that([entry[:3] for entry in restored]).is_equal_to(
        [(127, 1, "1"), (127, 10, "4")]
    )


# A prompt overhanging a narrow window near the screen's right
# edge restores only the cells that exist: the rebuild stops at
# the grid's last column instead of reading past it.
def test_a_more_pause_near_the_edge_stays_inside_the_grid() -> None:
    frontend, glass = windowed(version=6, keys=["m", "x"])

    frontend.place_window(0, 1, 235, 144, 36)
    frontend.write("\n".join("abcdefgh"))

    prompts = [entry for entry in glass.typed if entry[2] == "[MORE]"]

    assert_that(prompts).is_length(1)
    assert_that(prompts[0][:2]).is_equal_to((127, 235))


# The glass rewrites the remembered prompt after a printing
# interrupt (§15 read remarks) -- and on the stage, where the
# cursor speaks units, the snapshot stays empty and the redisplay
# stays quiet until a Version 6 game earns the arithmetic.
def test_the_prompt_returns_after_an_interrupts_output() -> None:
    frontend, _glass = windowed()

    frontend.write("\n>")
    frontend.begin_input()
    frontend.write("\n\n   All the generals were on holiday.\n\n")
    frontend.resume_input()

    row, _column = cast("ScreenModel", frontend.model).cursor

    assert_that(frontend.model.row_text(row)).is_equal_to(">")

    staged, glass = windowed(version=6)

    staged.write(">")
    staged.begin_input()
    before = len(glass.typed)
    staged.resume_input()

    assert_that(glass.typed).is_length(before)


# Typing on the stage rubs out in pixels: the editor redraws the
# line and blanks the remnant by overpainting a space at the
# window's true position (§15 read).
def test_v6_typing_rubs_out_in_pixels() -> None:
    frontend, glass = windowed(version=6, keys=["a", "\x7f", "\n"])

    frontend.read_line()

    blanks = [entry for entry in glass.typed if entry[:3] == (1, 1, " ")]

    assert_that(blanks).is_not_empty()


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


# The glass twin of the painter's timed read: pause on the
# deadline with the line composed, resume to completion, and
# abandonment erases the half-typed line from the window. The
# scripted clock advances only while a key is waited for -- where
# real time actually passes -- so the frontend may consult it as
# often as its own bookkeeping likes.
def test_timed_reads_pause_resume_and_abandon(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = {"now": 0.0}

    monkeypatch.setattr("voxam.glass.monotonic", lambda: clock["now"])

    frontend, glass = windowed(keys=["g", "o"])
    scripted = glass.key

    def waited(timeout: float | None) -> str | None:
        clock["now"] += 0.4

        return scripted(timeout)

    monkeypatch.setattr(glass, "key", waited)

    line = frontend.read_line_until(1.0)

    assert_that(line).is_none()
    assert_that(frontend.model.row_text(1)).is_equal_to("go")

    glass.keys = ["\n"]

    assert_that(frontend.read_line_until(1.0)).is_equal_to("go")

    frontend.abandon_input()  # nothing composed: quietly nothing
    glass.keys = ["n", "o"]

    assert_that(frontend.read_line_until(1.0)).is_none()

    frontend.abandon_input()

    assert_that(frontend.model.row_text(2)).is_equal_to("")

    # With the idle heartbeat armed, an empty read lets background
    # work run and the wait chunks at the heartbeat.
    frontend.idle = lambda: None
    glass.keys = [None, "g", "\n"]

    assert_that(frontend.read_line_until(9.0)).is_equal_to("g")


# The cell model pages like the stage: a screenful at the pygame
# window holds behind [MORE] in the window's colours reversed,
# spends one key on the pause, and repaints the row clean.
def test_cell_screenfuls_pause_behind_more() -> None:
    frontend, glass = windowed(keys=[None, "x"])
    frontend.idle = lambda: None

    frontend.write("line\n" * 8)

    assert_that(runs_containing(glass, "[MORE]")).is_not_empty()
    assert_that(glass.keys).is_empty()


# A line read underlines the cursor's cell -- the caret is a
# two-pixel bar at the cell's foot -- and it follows the typing
# across the row, so a player always sees where input lands.
def test_read_line_shows_a_moving_caret() -> None:
    frontend, glass = windowed(keys=["h", "i", "\n"])

    frontend.read_line()

    carets = [entry for entry in glass.filled if entry[2:4] == (2, 9)]

    assert_that(carets).is_not_empty()
    assert_that({entry[1] for entry in carets}).is_length(3)


# A keystroke read shows the caret too -- Bureaucracy's form hops
# its cursor between fields through read_char, and the caret is
# how a player follows it -- and the cell is restored afterwards.
def test_read_key_shows_and_removes_the_caret() -> None:
    frontend, glass = windowed(keys=["x"])

    frontend.read_key()

    carets = [entry for entry in glass.filled if entry[2:4] == (2, 9)]

    assert_that(carets).is_not_empty()
    assert_that(glass.painted).is_not_empty()


# A print landing elsewhere mid-read -- a timed interrupt
# updating an upper-window clock, Bureaucracy-style -- repaints
# its own rows and leaves the settled caret exactly where it is,
# rather than redrawing it every frame.
def test_mid_read_prints_leave_the_caret_alone() -> None:
    glass = MeddlingGlass(["x"])
    frontend = GraphicsFrontend(5, glass=glass)

    frontend.write("\n\n\n> ")
    frontend.split_window(1)

    def interruption() -> None:
        frontend.set_window(1)
        frontend.set_cursor(1, 1)
        frontend.write("TIME  9:00")
        frontend.set_window(0)

    glass.meddler = interruption
    frontend.read_key()

    carets = [entry for entry in glass.filled if entry[2:4] == (2, 9)]

    assert_that(carets).is_length(1)

    # The meddler is spent; a further read runs the quiet path.
    glass.keys = ["y"]
    frontend.read_key()


# The v6 stage draws no caret of its own: its games place and
# paint their cursors, and an uninvited underline would sit on
# top of their pixel layouts.
def test_v6_reads_draw_no_caret() -> None:
    frontend, glass = windowed(version=6, keys=["x"])

    frontend.read_key()

    assert_that(glass.filled).is_empty()


# A repaint with no damage presents nothing: the frame only flips
# when a row actually changed.
def test_undamaged_repaints_present_nothing() -> None:
    frontend, glass = windowed()

    frontend.write("hi")

    shown = glass.presents

    frontend.write("")

    assert_that(glass.presents).is_equal_to(shown)


# A burst of writes within one frame shares a single flip --
# Zugzwang's chessboard is nearly a thousand writes a turn -- with
# the cadence buying the next flip once real time has passed, and
# whatever is left owing settled the moment the glass stands to
# wait, so nothing painted is ever unseen while the window listens.
def test_presents_share_the_frames_cadence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = {"now": 100.0}

    monkeypatch.setattr("voxam.glass.monotonic", lambda: clock["now"])

    frontend, glass = windowed()

    frontend.write("a")

    first = glass.presents

    frontend.write("b")
    frontend.write("c")

    assert_that(glass.presents).is_equal_to(first)

    clock["now"] += 1.0

    frontend.write("d")

    assert_that(glass.presents).is_equal_to(first + 1)

    frontend.write("e")
    frontend.wait_for_sound()

    assert_that(glass.presents).is_equal_to(first + 2)

    frontend.wait_for_sound()

    assert_that(glass.presents).is_equal_to(first + 2)


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
        self.reads: list[tuple[int, int]] = []

    def get_at(self, position: tuple[int, int]) -> tuple[int, int, int, int]:
        self.reads.append(position)

        return (60, 70, 80, 255)

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
    events: list[object] | None = None,
    *,
    bold_advance: int = 9,
    clipboard: str = "",
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

    icons: list[object] = []
    flips: list[int] = []
    snapshots: list[tuple[object, object]] = []
    captions: list[str] = []
    module = types.SimpleNamespace(
        QUIT=1,
        KEYDOWN=2,
        MOUSEBUTTONDOWN=5,
        WINDOWEXPOSED=7,
        SRCALPHA=65536,
        K_v=200,
        K_INSERT=201,
        KMOD_CTRL=64,
        KMOD_SHIFT=1,
        KMOD_META=1024,
        scrap=types.SimpleNamespace(get_text=lambda: clipboard),
        icons=icons,
        flips=flips,
        snapshots=snapshots,
        captions=captions,
        image=types.SimpleNamespace(
            load=lambda path: ("icon", path),
            save=lambda surface, path: snapshots.append((surface, path)),
        ),
        init=lambda: None,
        display=types.SimpleNamespace(
            set_mode=lambda _size: screen,
            set_caption=captions.append,
            set_icon=icons.append,
            flip=lambda: flips.append(1),
        ),
        font=types.SimpleNamespace(SysFont=sysfont),
        event=types.SimpleNamespace(
            get=lambda: [queue.pop(0)] if queue else [],
            pump=lambda: None,
        ),
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


def keydown(
    module: types.SimpleNamespace, key: int, unicode: str = "", mod: int = 0
) -> object:
    return types.SimpleNamespace(type=module.KEYDOWN, key=key, unicode=unicode, mod=mod)


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


# With a zoom, the doorway grows the grid, never the type: half of
# a 2000-by-984 desktop holds 111 by 27 of the classic 9-by-18
# cells. Under a declared standard the grid keeps the art's
# aspect, walking the height down until the width fits; a tiny
# share keeps the classic 80 by 24 floor; and no dimension ever
# passes the header's one-byte 255.
def test_the_doorway_grows_the_grid_to_fill_the_room(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = fake_pygame()
    module.display.get_desktop_sizes = lambda: [(2000, 984)]

    monkeypatch.setitem(sys.modules, "pygame", module)

    roomy = open_pygame_glass(zoom=0.5)

    assert_that(roomy.cell_width).is_equal_to(9)
    assert_that(roomy.cell_height).is_equal_to(18)
    assert_that((roomy.columns, roomy.lines)).is_equal_to((111, 27))

    shaped = open_pygame_glass(standard=(320, 200), zoom=0.5)

    assert_that((shaped.columns, shaped.lines)).is_equal_to((86, 27))

    classic = open_pygame_glass(zoom=0.1)

    assert_that((classic.columns, classic.lines)).is_equal_to((80, 24))

    module.display.get_desktop_sizes = lambda: [(700, 3000)]
    narrow = open_pygame_glass(standard=(320, 200), zoom=1.0)

    assert_that((narrow.columns, narrow.lines)).is_equal_to((77, 24))

    module.display.get_desktop_sizes = lambda: [(9000, 9000)]
    vast = open_pygame_glass(zoom=1.0)

    assert_that((vast.columns, vast.lines)).is_equal_to((255, 255))


# The doorway reads a pixel back as plain RGB, shedding the alpha
# pygame reports -- §8.3.1 colour -1's sample, off the real
# surface at the 0-based position pygame counts in.
def test_the_pygame_doorway_samples_a_pixel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = fake_pygame()

    monkeypatch.setitem(sys.modules, "pygame", module)

    glass = open_pygame_glass()

    assert_that(glass.sample(19, 10)).is_equal_to((60, 70, 80))
    assert_that(module.screen.reads).is_equal_to([(9, 18)])


# Keys translate to their §3.8 characters, printables pass through,
# a timeout expires against the clock, and the close button ends
# the session as end of input.
# A left-button click is a keypress in §10.3's eyes: the doorway
# answers the input code 254 as its character and keeps the
# position -- 1-based pixels -- for click().
def test_the_pygame_doorway_hears_clicks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = fake_pygame()

    monkeypatch.setitem(sys.modules, "pygame", module)

    glass = open_pygame_glass()

    assert_that(glass.click()).is_none()

    scripted = iter(
        [[types.SimpleNamespace(type=module.MOUSEBUTTONDOWN, button=1, pos=(10, 25))]]
    )
    module.event.get = lambda: next(scripted, [])

    assert_that(glass.key(None)).is_equal_to("\xfe")
    assert_that(glass.click()).is_equal_to((11, 26))


# Two clicks landing fast and close double: the first delivers as
# a single, the second as §10.3.3's double-click code, and the
# run resets so a third fast click begins a new single. A slow
# second click, or one too far away, stays single.
def test_fast_close_clicks_double(monkeypatch: pytest.MonkeyPatch) -> None:
    module = fake_pygame()

    monkeypatch.setitem(sys.modules, "pygame", module)

    glass = open_pygame_glass()
    clock = {"now": 0}
    module.time.get_ticks = lambda: clock["now"]

    def press(x: int, y: int) -> str | None:
        scripted = iter(
            [[types.SimpleNamespace(type=module.MOUSEBUTTONDOWN, button=1, pos=(x, y))]]
        )
        module.event.get = lambda: next(scripted, [])

        return glass.key(None)

    assert_that(press(10, 25)).is_equal_to("\xfe")

    clock["now"] = 300

    assert_that(press(12, 26)).is_equal_to("\xfd")
    assert_that(glass.click()).is_equal_to((13, 27))

    clock["now"] = 600

    assert_that(press(12, 26)).is_equal_to("\xfe")

    clock["now"] = 1200

    assert_that(press(12, 26)).is_equal_to("\xfe")

    clock["now"] = 1300

    assert_that(press(30, 26)).is_equal_to("\xfe")

    clock["now"] = 1400

    assert_that(press(30, 27)).is_equal_to("\xfd")


# A translucent picture layers with its real opacities: straight
# colors wearing their alpha for the glass to blend, opaque
# pixels staying bare triples.
def test_layered_carries_partial_alpha() -> None:
    picture = Picture(
        2, 1, (((10, 20, 30), (40, 50, 60)),), ((False, False),), ((128, 255),)
    )

    assert_that(layered(picture)).is_equal_to((((10, 20, 30, 128), (40, 50, 60)),))


# The window's title bar takes the game's own name: the frontend
# entitles whatever glass it was handed, an untitled session
# leaves the caption alone, and the real doorway captions through
# pygame.
def test_the_window_wears_the_games_name(monkeypatch: pytest.MonkeyPatch) -> None:
    glass = StubGlass()
    GraphicsFrontend(3, glass=glass, title="Trinity — Voxam")

    assert_that(glass.entitled).is_equal_to(["Trinity — Voxam"])

    untitled = StubGlass()
    GraphicsFrontend(3, glass=untitled)

    assert_that(untitled.entitled).is_empty()

    module = fake_pygame()

    monkeypatch.setitem(sys.modules, "pygame", module)

    real = open_pygame_glass()

    real.entitle("Trinity — Voxam")

    assert_that(module.captions[-1]).is_equal_to("Trinity — Voxam")


# The real window photographs JPEG bytes through pygame's own
# decoder -- rows of RGB read off the loaded surface -- and
# answers None for bytes pygame cannot read.
def test_the_window_photographs_jpeg_bytes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = fake_pygame()

    monkeypatch.setitem(sys.modules, "pygame", module)

    glass = open_pygame_glass()

    class Developed:
        def get_size(self) -> tuple[int, int]:
            return (2, 1)

        def get_at(self, position: tuple[int, int]) -> tuple[int, int, int, int]:
            x, y = position

            return (x * 10, y, 7, 255)

    module.error = ValueError
    module.image.load = lambda _stream: Developed()

    assert_that(glass.photograph(b"\xff\xd8photo")).is_equal_to(
        (((0, 0, 7), (10, 0, 7)),)
    )
    # The stub glass, by contrast, honestly develops nothing.
    assert_that(StubGlass().photograph(b"\xff\xd8photo")).is_none()

    def refuse(_stream: object) -> object:
        raise ValueError("not an image")

    module.image.load = refuse

    assert_that(glass.photograph(b"junk")).is_none()


# Ctrl+V empties the clipboard through the key seam one character
# at a time, so pasted text is indistinguishable from typing: the
# Windows return pair and a lone carriage return each collapse to
# the newline the reader takes as a return key, a tab is dross no
# keyboard could deliver and vanishes, and a key typed after the
# paste waits its turn behind the drained characters.
def test_the_pygame_doorway_pastes_the_clipboard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = fake_pygame(clipboard="go\r\nnorth\rx\ty")

    monkeypatch.setitem(sys.modules, "pygame", module)

    glass = open_pygame_glass()
    scripted = iter(
        [
            [keydown(module, module.K_v, mod=module.KMOD_CTRL)],
            [keydown(module, 999, "z")],
        ]
    )
    module.event.get = lambda: next(scripted, [])

    assert_that([glass.key(None) for _ in range(11)]).is_equal_to(list("go\nnorth\nxy"))
    assert_that(glass.key(None)).is_equal_to("z")


# Every desktop's chord serves: Cmd+V arrives as KMOD_META on a
# Mac, Shift+Insert is the traditional alternative, and a plain v
# -- no chord held -- still just types a v. An empty clipboard
# pastes nothing and the session simply reads on.
def test_the_paste_chords_all_serve(monkeypatch: pytest.MonkeyPatch) -> None:
    module = fake_pygame(clipboard="hi")

    monkeypatch.setitem(sys.modules, "pygame", module)

    glass = open_pygame_glass()
    scripted = iter(
        [
            [keydown(module, module.K_v, mod=module.KMOD_META)],
            [keydown(module, module.K_INSERT, mod=module.KMOD_SHIFT)],
        ]
    )
    module.event.get = lambda: next(scripted, [])

    assert_that([glass.key(None) for _ in range(4)]).is_equal_to(list("hihi"))

    bare = fake_pygame(clipboard="")

    monkeypatch.setitem(sys.modules, "pygame", bare)

    quiet = open_pygame_glass()
    events = iter(
        [
            [keydown(bare, bare.K_v, "v", mod=bare.KMOD_CTRL)],
            [keydown(bare, bare.K_v, "v")],
        ]
    )
    bare.event.get = lambda: next(events, [])

    assert_that(quiet.key(None)).is_equal_to("v")


# The frontend answers click positions in the story's own units:
# character cells before Version 6, window pixels on the stage
# (§10.3.2, §8.8.1).
def test_click_positions_speak_the_versions_units() -> None:
    frontend, glass = windowed()

    assert_that(frontend.click_position()).is_none()

    glass.clicked = (10, 37)

    assert_that(frontend.click_position()).is_equal_to((2, 3))

    staged, staged_glass = windowed(version=6)
    staged_glass.clicked = (10, 37)

    assert_that(staged.click_position()).is_equal_to((10, 37))


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


# A driven glass wires no [MORE] callbacks -- a walk has no player
# to press the key -- while a played one keeps them. The snapshot
# seam settles, presents, and hands the glass its path; a banded
# glass photographs the whole window through its inner, band
# included; and the pygame glass saves its surface, pumping the
# event queue so a driven window stays alive between frames.
def test_driven_glasses_never_pause_and_photograph(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    driven = GraphicsFrontend(3, StubGlass(), driven=True)

    assert_that(driven.model.more).is_none()

    staged_front = GraphicsFrontend(6, StubGlass(), driven=True)

    assert_that(staged_front.model.more).is_none()

    played = GraphicsFrontend(3, StubGlass())

    assert_that(played.model.more).is_not_none()

    glass = StubGlass()
    front = GraphicsFrontend(3, glass, driven=True)

    front.snapshot("frame-0000.png")

    assert_that(glass.snapshots).is_equal_to(["frame-0000.png"])

    inner = StubGlass()
    banded = _BandedGlass(inner, 2)

    banded.snapshot("strip.png")

    assert_that(inner.snapshots).is_equal_to(["strip.png"])

    module = fake_pygame()

    monkeypatch.setitem(sys.modules, "pygame", module)

    window = open_pygame_glass()

    window.snapshot("real.png")

    assert_that(module.snapshots[-1][1]).is_equal_to("real.png")


# With VOXAM_SNAPSHOT set, every present also saves the surface
# to the named file -- a live session's own witness of what the
# window was given, for comparing against what it shows.
def test_snapshots_witness_every_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = fake_pygame()

    monkeypatch.setitem(sys.modules, "pygame", module)
    monkeypatch.setenv("VOXAM_SNAPSHOT", "witness.png")

    glass = open_pygame_glass()
    glass.present()

    assert_that(module.snapshots[-1][1]).is_equal_to("witness.png")

    monkeypatch.delenv("VOXAM_SNAPSHOT")

    bare = open_pygame_glass()
    before = len(module.snapshots)

    bare.present()

    assert_that(module.snapshots).is_length(before)


# An expose event -- the OS blanked the window behind our back --
# presents the surface again: its pixels still hold everything
# drawn, so a re-flip is the whole repair, and the key wait
# continues. Without this, a session waiting at a prompt shows
# black after an alt-tab.
def test_exposed_windows_present_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = fake_pygame()

    monkeypatch.setitem(sys.modules, "pygame", module)

    glass = open_pygame_glass()
    scripted = iter(
        [
            [types.SimpleNamespace(type=module.WINDOWEXPOSED)],
            [keydown(module, 999, "z")],
        ]
    )
    module.event.get = lambda: next(scripted, [])
    before = len(module.flips)

    assert_that(glass.key(None)).is_equal_to("z")
    assert_that(len(module.flips)).is_greater_than(before)


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


# The window wears the story version's own badge: the packaged
# z<version>.ico becomes the pygame icon, set before the display
# opens; a badge named outright -- glulx -- is worn as it is, and
# version 0 -- no story named -- leaves the icon alone.
def test_the_window_wears_the_version_badge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = fake_pygame()

    monkeypatch.setitem(sys.modules, "pygame", module)

    open_pygame_glass(None, 6)

    assert_that(module.icons).is_length(1)
    assert_that(str(module.icons[0][1])).ends_with("z6.ico")

    open_pygame_glass(None, "glulx")

    assert_that(module.icons).is_length(2)
    assert_that(str(module.icons[1][1])).ends_with("glulx.ico")

    open_pygame_glass(None, "aamachine")

    assert_that(module.icons).is_length(3)
    assert_that(str(module.icons[2][1])).ends_with("aamachine.ico")

    open_pygame_glass()

    assert_that(module.icons).is_length(3)


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
