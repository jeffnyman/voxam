"""Tests for the Å-machine's glass face, the window stubbed out.

Every test drives a StubGlass: it answers scripted keys and files
each paint into the frame that present() closes, so what a test
asserts is what a player would be looking at, and no window ever
opens in continuous integration.
"""

import zlib
from collections.abc import Sequence
from pathlib import Path

import pytest
from assertpy import assert_that

from voxam.aamachine.glass import GlassVoice, played
from voxam.aamachine.story import SUMMED, Story
from voxam.iff import chunk
from voxam.painter import MORE_PROMPT

# A minimal LANG: the four offsets and an empty extended table.
LANG = (
    b"\x00\x00"
    + (8).to_bytes(2, "big")
    + b"\x00\x00\x00\x00"
    + bytes([1, 0xE5, 0xC5])
    + (0xC5).to_bytes(3, "big")
)

FIXTURES = Path(__file__).parent.parent / "fixtures"

# The dark theme's own pair, which every undressed cell wears.
INK = (214, 214, 214)
PAPER = (28, 28, 28)

# What gosling's style 1 asks for and no §8.3.1 colour code can
# spell: bold, in the CSS basic red.
RED = (205, 49, 49)

# What body_not_status's style 0 asks for: green on black, italic.
GREEN = (13, 188, 121)
BLACK = (0, 0, 0)


def storied(name: str = "cloak-rel2") -> Story:
    """One vendored story, parsed."""

    return Story((FIXTURES / f"{name}.aastory").read_bytes())


class StubGlass:
    """A window that scripts every key and keeps every frame."""

    columns = 40
    lines = 24
    cell_width = 9
    cell_height = 18

    def __init__(self, keys: "Sequence[str] | None" = None) -> None:
        self.keys = list(keys or [])
        self.frames: list[list[tuple[object, ...]]] = []
        self.entitled: list[str] = []
        self.presses = 0
        self.drawn: list[tuple[int, int, tuple[int, int], int, int]] = []
        self.shot: Sequence[Sequence[tuple[int, int, int]]] | None = None
        self._painting: list[tuple[object, ...]] = []

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
        self._painting.append((row, column, text, ink, paper, bold, italic, graphics))

    def present(self) -> None:
        self.frames.append(self._painting)
        self._painting = []

    def entitle(self, title: str) -> None:
        self.entitled.append(title)

    def key(self, timeout: float | None) -> str | None:
        del timeout
        self.presses += 1

        return self.keys.pop(0) if self.keys else None

    def draw(
        self,
        rows: Sequence[Sequence[tuple[int, ...]]],
        line: int,
        column: int,
        size: tuple[int, int],
    ) -> None:
        self.drawn.append((line, column, size, len(rows), len(rows[0]) if rows else 0))

    def photograph(
        self, data: bytes
    ) -> Sequence[Sequence[tuple[int, int, int]]] | None:
        del data

        # A stub carries no pygame decoders; a test that wants a
        # photograph scripts one.
        return self.shot


class NarrowGlass(StubGlass):
    """A window too small to hold much before it has to pause."""

    columns = 20
    lines = 4


class PinholeGlass(StubGlass):
    """A window one pixel wide, so anything at all overruns it."""

    columns = 1
    cell_width = 1


def shown(glass: StubGlass, frame: int = -1) -> list[str]:
    """One frame as rows of text, later paints overwriting earlier."""

    rows = [[" "] * glass.columns for _ in range(glass.lines)]

    for row, column, text, *_ in glass.frames[frame]:
        for offset, character in enumerate(str(text)):
            rows[row - 1][column - 1 + offset] = character  # type: ignore[operator]

    return ["".join(row).rstrip() for row in rows]


def runs(glass: StubGlass, frame: int = -1) -> list[tuple[object, ...]]:
    """One frame's painted runs, the all-blank ones dropped."""

    return [
        (str(text).strip(), ink, paper, bold, italic)
        for _row, _column, text, ink, paper, bold, italic, _graphics in glass.frames[
            frame
        ]
        if str(text).strip()
    ]


def every_run(glass: StubGlass) -> list[tuple[object, ...]]:
    """Every frame's painted runs, in the order they were painted."""

    return [run for frame in range(len(glass.frames)) for run in runs(glass, frame)]


def poured_rows(voice: GlassVoice, count: int) -> None:
    """Say enough numbered rows to push a small window past a pause."""

    for number in range(count):
        voice.say(f"row {number}")
        voice.line()

    voice.poured()


def voiced(name: str = "cloak-rel2", glass: StubGlass | None = None) -> GlassVoice:
    """One voice speaking into a stub window."""

    return GlassVoice(storied(name), glass if glass is not None else StubGlass())


# Cloak of Darkness plays at the window: the opening lands in the
# grid, the typed command is echoed where it was typed, and the
# answer follows it.
def test_a_story_plays_at_the_glass() -> None:
    glass = StubGlass([*"north\n"])

    played(storied(), seed=7, glass=glass)

    assert_that("\n".join(shown(glass))).contains("> north", "You've only just arrived")


# The window wears the story's own name, which the META chunk
# carries; a story that names none leaves the caption alone.
def test_the_window_wears_the_story_name() -> None:
    glass = StubGlass()

    played(storied(), seed=7, glass=glass)

    assert_that(glass.entitled).is_equal_to(["Cloak of Darkness"])


def test_an_unnamed_story_leaves_the_caption_alone() -> None:
    glass = StubGlass()

    played(storied("aa-exercise"), seed=7, glass=glass)

    assert_that(glass.entitled).is_empty()


# The LOOK sheet's colours reach the window whole. Style 1 of Miss
# Gosling's sheet asks for bold in CSS red, and (205, 49, 49) is
# exactly the reason the voice keeps its own grid: the §8.3.1
# colour codes the Z-Machine's screen model stores cannot spell
# it (Aa-machine: LOOK).
def test_a_style_colour_reaches_the_window_whole() -> None:
    glass = StubGlass()
    voice = voiced("gosling", glass)

    voice.enter_span(1)
    voice.say("blood")
    voice.leave_span()
    voice.poured()

    assert_that(runs(glass)).contains(("blood", RED, PAPER, True, False))


# A dress lands on its own characters and stops there: the pour at
# every style change is what keeps the span's ink off the words
# that follow it.
def test_a_dress_ends_where_its_span_does() -> None:
    glass = StubGlass()
    voice = voiced("gosling", glass)

    voice.say("before ")
    voice.enter_span(1)
    voice.say("during")
    voice.leave_span()
    voice.say(" after")
    voice.poured()

    assert_that(runs(glass)).is_equal_to(
        [
            ("before", INK, PAPER, False, False),
            ("during", RED, PAPER, True, False),
            ("after", INK, PAPER, False, False),
        ]
    )


# A body class that names a background dresses the page and not
# only the characters standing on it, so the blank cells take the
# colour too.
def test_the_body_background_becomes_the_window_ground() -> None:
    glass = StubGlass()
    voice = voiced("body_not_status", glass)

    voice.set_body(0)
    voice.say("green")
    voice.poured()

    assert_that(runs(glass)).contains(("green", GREEN, BLACK, False, True))
    assert_that(
        [paper for _row, _column, _text, _ink, paper, *_ in glass.frames[-1]]
    ).does_not_contain(PAPER)


# A body class naming no background hands the window back its own
# ground, which is how body_not_status ends its walk.
def test_a_bare_body_restores_the_theme_ground() -> None:
    glass = StubGlass()
    voice = voiced("body_not_status", glass)

    voice.set_body(0)
    voice.set_body(2)
    voice.say("plain")
    voice.poured()

    assert_that(runs(glass)).is_equal_to([("plain", INK, PAPER, False, False)])


# The status areas are refused rather than half-drawn: the words
# never reach the window, and VM_INFO is told as much, which is
# the plain voice's own honest posture (Aa-machine: VM_INFO).
def test_a_status_area_is_swallowed_and_declared() -> None:
    glass = StubGlass()
    voice = voiced("body_not_status", glass)

    voice.say("story")
    voice.enter_status(0, 1)
    voice.say("a top status bar")
    voice.leave_status()
    voice.poured()

    assert_that("\n".join(shown(glass))).does_not_contain("status bar")
    assert_that(voice.has_top_status).is_false()
    assert_that(voice.has_inline_status).is_false()
    assert_that(voice.has_links).is_false()


# A windowful of unread text stops at a [MORE] before the scroll
# carries the top of it away, and the key that answers is spent on
# the pause rather than passed to the story.
def test_the_window_pauses_at_more() -> None:
    glass = NarrowGlass([" "] * 10)
    voice = voiced(glass=glass)

    poured_rows(voice, 10)

    assert_that([text for text, *_ in every_run(glass)]).contains(MORE_PROMPT)
    assert_that(glass.presses).is_greater_than(0)
    assert_that("\n".join(shown(glass))).does_not_contain(MORE_PROMPT)


# The [MORE] prompt wears the window's own colours swapped, which
# is how a pager has always marked itself out from the text it
# interrupts.
def test_the_more_prompt_is_marked_out() -> None:
    glass = NarrowGlass([" "] * 10)
    voice = voiced(glass=glass)

    poured_rows(voice, 10)

    assert_that(every_run(glass)).contains((MORE_PROMPT, PAPER, INK, False, False))


# CLEAR really clears at a window, which is the one thing a
# telling cannot do: the grid blanks and the next word lands at
# the top left (Aa-machine: CLEAR).
def test_a_wipe_blanks_the_window() -> None:
    glass = StubGlass()
    voice = voiced(glass=glass)

    voice.say("forgotten")
    voice.line()
    voice.poured()
    voice.clear()
    voice.say("after")
    voice.poured()

    assert_that(shown(glass)[0]).is_equal_to("after")
    assert_that("\n".join(shown(glass))).does_not_contain("forgotten")


# clear_all differs from clear only in hiding the status areas,
# and none stand to hide at this face.
def test_a_full_wipe_blanks_the_window_too() -> None:
    glass = StubGlass()
    voice = voiced(glass=glass)

    voice.say("forgotten")
    voice.poured()
    voice.clear_all()
    voice.say("after")
    voice.poured()

    assert_that(shown(glass)[0]).is_equal_to("after")


# A RESTART begins on a blank window: the voice forgets the grid
# along with everything else (Aa-machine: RESTART).
def test_a_restart_opens_on_a_blank_window() -> None:
    glass = StubGlass()
    voice = voiced(glass=glass)

    voice.say("before the restart")
    voice.poured()
    voice.reset()
    voice.poured()

    assert_that("\n".join(shown(glass)).strip()).is_empty()


# A window knows how many lines it has, which is the question a
# stream has to answer with a shrug; anything else it is asked
# stays unanswered (Aa-machine: VM_INFO).
def test_the_window_knows_both_its_dimensions() -> None:
    voice = voiced(glass=NarrowGlass())

    assert_that(voice.measured(0)).is_equal_to(20)
    assert_that(voice.measured(1)).is_equal_to(4)
    assert_that(voice.measured(2)).is_equal_to(0)


# The line editor echoes into the same grid the story writes to,
# so a rubbed-out character leaves the window as it leaves the
# line.
def test_the_editor_echoes_and_rubs_out() -> None:
    glass = StubGlass([*"abc", "\x7f", *"d\n"])
    voice = voiced(glass=glass)

    assert_that(voice.read_line()).is_equal_to("abd")
    assert_that(shown(glass)[0]).is_equal_to("abd")


# A keypress arrives as the machine's own code: the reserved ones
# by name, everything else as its codepoint (Aa-machine: Text).
def test_a_keypress_arrives_as_the_machine_knows_it() -> None:
    glass = StubGlass(["\x81", "\x7f", "q"])
    voice = voiced(glass=glass)

    assert_that(voice.read_key()).is_equal_to(0x10)
    assert_that(voice.read_key()).is_equal_to(0x08)
    assert_that(voice.read_key()).is_equal_to(ord("q"))


# A savefile is asked for in the window itself, kept, and revived:
# the blocking face's privilege, the filed voice's own manners
# (Aa-machine: Savefile).
def test_a_savefile_is_kept_and_revived(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    glass = StubGlass([*"keepsake\n", *"keepsake\n"])
    voice = voiced(glass=glass)

    assert_that(voice.save(b"the state")).is_true()
    assert_that((tmp_path / "keepsake.aasave").exists()).is_true()
    assert_that(voice.restore()).is_equal_to(b"the state")
    assert_that("\n".join(shown(glass))).contains("Save the story as:")


# A story that quits of its own accord ends the session on its own
# terms: every scripted key is spent and none is left over.
def test_a_quit_ends_the_session_cleanly() -> None:
    glass = StubGlass([*"quit\n", *"yes\n"])

    played(storied(), seed=7, glass=glass)

    assert_that(glass.keys).is_empty()
    assert_that("\n".join(shown(glass))).contains("Really quit?")


# A story waiting on a keypress gets one from the window rather
# than a whole line: codepoints opens on exactly that wait.
def test_a_key_wait_is_answered_at_the_window() -> None:
    glass = StubGlass(["a"])

    played(storied("codepoints"), seed=7, glass=glass)

    assert_that(glass.keys).is_empty()
    assert_that(glass.presses).is_greater_than(0)


# A typed line longer than the window is still the line the story
# receives: the echo wraps onto the next row, and the buffer, not
# the glass, is what gets submitted.
def test_a_line_longer_than_the_window_wraps() -> None:
    typed = "abcdefghijklmnopqrstuvwxy"
    glass = NarrowGlass([*typed, "\n"])
    voice = voiced(glass=glass)

    assert_that(voice.read_line()).is_equal_to(typed)
    assert_that(shown(glass)[0]).is_equal_to(typed[:20])
    assert_that(shown(glass)[1]).is_equal_to(typed[20:])


# A window the player shuts ends the session where it stands: the
# same end of input an exhausted stream gives the terminal face.
def test_a_closed_window_ends_the_session() -> None:
    glass = StubGlass()

    played(storied(), seed=7, glass=glass)

    assert_that(glass.frames).is_not_empty()


# A story carrying one picture, built rather than vendored: the
# resource table, the file, and a real PNG small enough to reason
# about.
def picturing(png: bytes, name: str = "art.png") -> Story:
    """A minimal story whose one resource is the given picture."""

    summed = {b"LANG": LANG, b"DICT": b"\x00\x00", b"LOOK": b"\x00\x00"}
    crc = 0

    for chunk_id in SUMMED:
        crc = zlib.crc32(summed.get(chunk_id, b""), crc)

    head = (
        bytes([0, 5, 2, 0])
        + (1).to_bytes(2, "big")
        + b"260902"
        + crc.to_bytes(4, "big")
        + (16).to_bytes(2, "big")
        + (8).to_bytes(2, "big")
        + (32).to_bytes(2, "big")
    )
    descriptor = (
        (0).to_bytes(3, "big") + f"file:{name}".encode("latin-1") + b"\x00" + b"\x00"
    )
    urls = (1).to_bytes(2, "big") + (4).to_bytes(2, "big") + descriptor
    pieces = [
        chunk(b"HEAD", head),
        chunk(b"URLS", urls),
        chunk(b"FILE", name.encode("latin-1") + b"\x00" + png),
    ]

    for chunk_id in SUMMED:
        pieces.append(chunk(chunk_id, summed.get(chunk_id, b"")))

    return Story(chunk(b"FORM", b"AAVM" + b"".join(pieces)))


# The window can draw, so it says so -- and says no to a resource
# whose bytes no decoder here can read (Aa-machine: CAN_EMBED_RES).
def test_the_window_claims_a_picture_it_can_draw(tiny_png: bytes) -> None:
    glass = StubGlass()

    assert_that(GlassVoice(picturing(tiny_png), glass).can_embed_res(0)).is_true()
    assert_that(GlassVoice(picturing(tiny_png), glass).can_embed_res(3)).is_false()
    unshowable = GlassVoice(picturing(b"not a picture"), glass)

    assert_that(unshowable.can_embed_res(0)).is_false()

    # And asking it to hang one anyway hangs nothing.
    unshowable.embed_res(0)

    assert_that(unshowable._hung).is_empty()


# A picture takes whole rows: the text before it stays above, the
# rows it needs are reserved, and the story carries on beneath.
def test_a_picture_takes_its_own_rows(tiny_png: bytes) -> None:
    glass = StubGlass()
    voice = GlassVoice(picturing(tiny_png), glass)

    # No line break before the picture: it still takes whole rows,
    # so the half-written line is finished first.
    voice.say("above")
    voice.embed_res(0)
    voice.say("below")
    voice.poured()

    rows = shown(glass)

    assert_that(rows[0]).is_equal_to("above")
    assert_that(glass.drawn).is_length(1)

    line, column, size, _tall, _wide = glass.drawn[0]

    # Row 1 is the first blank row under the text, in pixels from
    # the top, and the picture is drawn at the left edge.
    assert_that(line).is_equal_to(1 * glass.cell_height + 1)
    assert_that(column).is_equal_to(1)
    assert_that(size).is_equal_to((2, 2))

    # A two-pixel picture still owns a whole row, so the text that
    # follows is under it rather than beside it.
    assert_that(rows[2]).is_equal_to("below")


# A picture rides the scroll like the lines it was set among, and
# leaves at the top with them.
def test_a_picture_scrolls_away_with_its_lines(tiny_png: bytes) -> None:
    glass = NarrowGlass([" "] * 60)
    voice = GlassVoice(picturing(tiny_png), glass)

    poured_rows(voice, 2)
    voice.embed_res(0)

    assert_that(voice._hung).is_length(1)
    assert_that(voice._hung[0][0]).is_equal_to(2)

    # Each row that scrolls carries it one line nearer the top.
    for expected in (1, 0):
        poured_rows(voice, 1)

        assert_that(voice._hung[0][0]).is_equal_to(expected)

    # And the row after that takes it off the window entirely,
    # with the lines it was set among.
    poured_rows(voice, 1)

    assert_that(voice._hung).is_empty()


# A wipe takes the pictures with it, as it takes the words.
def test_a_wipe_takes_the_pictures(tiny_png: bytes) -> None:
    glass = StubGlass()
    voice = GlassVoice(picturing(tiny_png), glass)

    voice.embed_res(0)

    assert_that(voice._hung).is_not_empty()

    voice.clear()

    assert_that(voice._hung).is_empty()


# A picture wider than the window is brought down to fit, keeping
# its proportions rather than being cropped or spilling off the
# edge.
def test_a_wide_picture_is_brought_down_to_fit(tiny_png: bytes) -> None:
    glass = PinholeGlass()
    voice = GlassVoice(picturing(tiny_png), glass)

    voice.embed_res(0)
    voice.poured()

    _line, _column, size, _tall, _wide = glass.drawn[0]

    # One column of one pixel is all the room there is, and the
    # two-pixel picture comes down to it squarely.
    assert_that(size).is_equal_to((1, 1))


# A JPEG goes to the window's own decoder, which is where the
# decoders the interpreter does not carry live.
def test_a_photograph_goes_to_the_window(tiny_png: bytes) -> None:
    glass = StubGlass()
    glass.shot = (((9, 9, 9), (8, 8, 8)), ((7, 7, 7), (6, 6, 6)))
    voice = GlassVoice(picturing(tiny_png, name="art.jpeg"), glass)

    assert_that(voice.can_embed_res(0)).is_true()

    voice.embed_res(0)
    voice.poured()

    assert_that(glass.drawn).is_length(1)
    assert_that(glass.drawn[0][2]).is_equal_to((2, 2))

    # A window that cannot decode it refuses honestly.
    bare = StubGlass()

    assert_that(
        GlassVoice(picturing(tiny_png, name="art.jpeg"), bare).can_embed_res(0)
    ).is_false()


# Left to itself the face opens a real window wearing the third
# machine's own badge, which is the only line in it that a test
# cannot let run.
def test_a_bare_call_opens_a_real_window(monkeypatch: pytest.MonkeyPatch) -> None:
    glass = StubGlass()
    opened: list[object] = []

    def opening(
        standard: object = None, version: object = 0, zoom: object = None
    ) -> StubGlass:
        opened.append((standard, version, zoom))

        return glass

    monkeypatch.setattr("voxam.aamachine.glass.open_pygame_glass", opening)
    played(storied(), seed=7, zoom=0.5)

    assert_that(opened).is_equal_to([(None, "aamachine", 0.5)])
