"""The composer: Glk's state read out as GlkOte updates."""

from typing import Any

import pytest
from assertpy import assert_that

from voxam.glkote import Page
from voxam.glulx.glk.api import Glk
from voxam.glulx.glk.frontend import Frontend, NullFrontend
from voxam.glulx.glk.glkote import Composer
from voxam.glulx.glk.objects import (
    KeyCode,
    Style,
    TextGridWindow,
    Window,
    WindowMethod,
    WindowType,
)

ABOVE_FIXED = WindowMethod.ABOVE | WindowMethod.FIXED


class Canvased(NullFrontend):
    """A silent display that claims graphics, so canvases open."""

    graphics = True


def rooted(frontend: Frontend | None = None) -> tuple[Glk, Window]:
    """A library with a buffer window at the root."""

    library = Glk(frontend if frontend is not None else NullFrontend())
    window = library.glk_window_open(None, 0, 0, WindowType.TEXT_BUFFER, 0)

    if window is None:
        pytest.fail("the root window opened")

    return library, window


def turned(composer: Composer, library: Glk, page: Page) -> dict[str, Any]:
    """One whole cycle: compose the library and take the update."""

    composer.compose(library, page)

    return page.update()


def saying(window: Window, text: str, style: int = Style.NORMAL) -> None:
    window.style = style

    for character in text:
        window.put_char(ord(character))


# A split tree composes to a flat pair of drawn windows -- the
# pair itself stays home -- with boxes and grid sizes translated
# from the model's own arrangement.
def test_a_split_tree_composes_flat() -> None:
    library, root = rooted()
    library.glk_window_open(root, ABOVE_FIXED, 2, WindowType.TEXT_GRID, 7)

    update = turned(Composer(), library, Page())

    assert_that(update["windows"]).is_equal_to(
        [
            {
                "id": 1,
                "type": "buffer",
                "rock": 0,
                "left": 0,
                "top": 2,
                "width": 80,
                "height": 22,
            },
            {
                "id": 2,
                "type": "grid",
                "rock": 7,
                "left": 0,
                "top": 0,
                "width": 80,
                "height": 2,
                "gridwidth": 80,
                "gridheight": 2,
            },
        ]
    )


# Ids are minted once and never come back: a closed grid's id is
# retired, and its replacement is a new window with a new number.
def test_ids_are_never_reused() -> None:
    library, root = rooted()
    composer = Composer()
    page = Page()
    grid = library.glk_window_open(root, ABOVE_FIXED, 2, WindowType.TEXT_GRID, 0)

    turned(composer, library, page)
    library.glk_window_close(grid, None)
    turned(composer, library, page)
    library.glk_window_open(root, ABOVE_FIXED, 2, WindowType.TEXT_GRID, 0)

    update = turned(composer, library, page)

    assert_that([held["id"] for held in update["windows"]]).is_equal_to([1, 3])
    assert_that(composer._idents).is_length(2)


# Buffer text drains destructively into named-style runs -- the
# seventh style spells blockquote, one word -- and a pending clear
# rides along, consumed.
def test_buffer_text_drains_into_named_runs() -> None:
    library, root = rooted()
    composer = Composer()
    page = Page()

    saying(root, "quoth", Style.BLOCK_QUOTE)

    update = turned(composer, library, page)

    assert_that(update["content"]).is_equal_to(
        [
            {
                "id": 1,
                "text": [{"content": [{"style": "blockquote", "text": "quoth"}]}],
            }
        ]
    )

    assert_that(turned(composer, library, page)).is_equal_to({"type": "pass"})

    library.glk_window_clear(root)

    cleared = turned(composer, library, page)

    assert_that(cleared["content"]).is_equal_to([{"id": 1, "clear": True}])
    assert_that(root.pending_clear).is_false()


# A style number beyond the eleven composes as normal, the same
# plainness the painted displays give it.
def test_a_wild_style_composes_normal() -> None:
    library, root = rooted()

    saying(root, "odd", 23)

    update = turned(Composer(), library, Page())

    assert_that(update["content"][0]["text"]).is_equal_to(
        [{"content": [{"style": "normal", "text": "odd"}]}]
    )


# Grid rows arrive through the same grouping the painted displays
# use: per-cell dress collapsed into runs, only what shows sent.
def test_grid_rows_compose_through_grouping() -> None:
    library, root = rooted()
    grid = library.glk_window_open(root, ABOVE_FIXED, 2, WindowType.TEXT_GRID, 0)

    if not isinstance(grid, TextGridWindow):
        pytest.fail("the split opened a grid")

    saying(grid, "Score", Style.SUBHEADER)

    update = turned(Composer(), library, Page())

    assert_that(update["content"]).is_equal_to(
        [
            {
                "id": 2,
                "lines": [
                    {"line": 0, "content": [{"style": "subheader", "text": "Score"}]}
                ],
            }
        ]
    )


# A line request composes whole: capacity as maxlen, the buffer's
# pre-filled text as initial, and terminators by name -- the keys
# the protocol cannot name dropped.
def test_a_line_request_composes_whole() -> None:
    library, root = rooted()
    held = [ord("g"), ord("o"), 0, 0, 0, 0, 0, 0]

    library.glk_request_line_event(root, held, 2)
    library.glk_set_terminators_line_event(
        root, [KeyCode.ESCAPE, KeyCode.TAB, KeyCode.FUNC5]
    )

    update = turned(Composer(), library, Page())

    assert_that(update["input"]).is_equal_to(
        [
            {
                "id": 1,
                "type": "line",
                "maxlen": 8,
                "initial": "go",
                "terminators": ["escape", "func5"],
                "gen": 1,
            }
        ]
    )

    # A request with no buffer at all holds nothing and asks for
    # nothing beyond its zero capacity.
    bare, spare = rooted()

    bare.glk_request_line_event(spare, None, 0)

    asked = turned(Composer(), bare, Page())

    assert_that(asked["input"]).is_equal_to(
        [{"id": 1, "type": "line", "maxlen": 0, "gen": 1}]
    )


# Grid input carries the cursor, clamped inside the grid the way
# the painted displays clamp it.
def test_grid_input_carries_the_clamped_cursor() -> None:
    library, root = rooted()
    grid = library.glk_window_open(root, ABOVE_FIXED, 2, WindowType.TEXT_GRID, 0)

    if not isinstance(grid, TextGridWindow):
        pytest.fail("the split opened a grid")

    grid.move_cursor(500, 500)
    library.glk_request_char_event(grid)

    update = turned(Composer(), library, Page())

    assert_that(update["input"]).is_equal_to(
        [{"id": 2, "type": "char", "gen": 1, "xpos": 79, "ypos": 1}]
    )


# Click and link listening translate to the passive form -- except
# on a buffer, where the protocol takes no clicks and the request
# is quietly set aside.
def test_clicks_and_links_translate() -> None:
    library, root = rooted()
    grid = library.glk_window_open(root, ABOVE_FIXED, 2, WindowType.TEXT_GRID, 0)

    library.glk_request_mouse_event(grid)
    library.glk_request_hyperlink_event(root)
    library.glk_request_mouse_event(root)

    update = turned(Composer(), library, Page())

    assert_that(update["input"]).is_equal_to(
        [{"id": 1, "hyperlink": True}, {"id": 2, "mouse": True}]
    )


# The timer cadence passes through without a restart claim: from
# polled state, a re-request at the same value is invisible.
def test_the_timer_passes_through() -> None:
    library, _ = rooted()
    composer = Composer()
    page = Page()

    library.glk_request_timer_events(250)

    assert_that(turned(composer, library, page)["timer"]).is_equal_to(250)
    assert_that(turned(composer, library, page)).is_equal_to({"type": "pass"})


# A canvas declares its drawable size and keeps its pending clear:
# clearing is a background fill, and the background lives with the
# display that draws, not with the model.
def test_a_canvas_keeps_its_pending_clear() -> None:
    library, root = rooted(Canvased())
    canvas = library.glk_window_open(root, ABOVE_FIXED, 8, WindowType.GRAPHICS, 0)

    if canvas is None:
        pytest.fail("the canvas opened")

    update = turned(Composer(), library, Page())

    entry = next(held for held in update["windows"] if held["type"] == "graphics")

    assert_that(entry["graphwidth"]).is_equal_to(80)
    assert_that(entry["graphheight"]).is_equal_to(8)
    assert_that(canvas.pending_clear).is_true()


# A blank window stays home: the protocol's window list knows only
# the three drawn kinds.
def test_a_blank_window_stays_home() -> None:
    library, root = rooted()
    library.glk_window_open(root, ABOVE_FIXED, 2, WindowType.BLANK, 0)

    update = turned(Composer(), library, Page())

    assert_that([held["type"] for held in update["windows"]]).is_equal_to(["buffer"])
