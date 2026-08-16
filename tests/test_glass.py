import sys
import types
from collections.abc import Sequence

import pytest
from assertpy import assert_that

from voxam.aiff import Sound
from voxam.frontend import GRAPHICS_FONT, Status
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

    def present(self) -> None:
        self.presents += 1

    def key(self, timeout: float | None) -> str | None:
        self.timeouts.append(timeout)

        return self.keys.pop(0) if self.keys else None

    def picture(self, rows: Sequence[Sequence[tuple[int, int, int]]]) -> None:
        self.pictures.append(rows)


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


class FakeScreen:
    def __init__(self) -> None:
        self.fills: list[tuple[object, ...]] = []
        self.blits: list[tuple[object, ...]] = []

    def fill(self, colour: object, rect: object = None) -> None:
        self.fills.append((colour, rect))

    def blit(self, surface: object, position: object) -> None:
        self.blits.append((surface, position))

    def get_size(self) -> tuple[int, int]:
        return (270, 144)


class FakeSurface:
    def __init__(self, size: tuple[int, int]) -> None:
        self.size = size
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
