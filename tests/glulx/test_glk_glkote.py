"""The GlkOte face of Glk: composed updates, delivered events."""

import io
import json
from collections.abc import Callable
from typing import Any

import pytest
from assertpy import assert_that

from voxam.errors import GlkOteError, GlulxGlkError
from voxam.glkote import Page
from voxam.glulx.glk.api import Glk, Prompting
from voxam.glulx.glk.frontend import Frontend, NullFrontend
from voxam.glulx.glk.glkote import Composer, GlkOteFrontend, serve
from voxam.glulx.glk.objects import (
    CHARACTER_CELL,
    EventType,
    FileMode,
    FileUsage,
    GraphicsWindow,
    KeyCode,
    Metrics,
    PairWindow,
    Style,
    TextBufferWindow,
    TextGridWindow,
    Window,
    WindowMethod,
    WindowType,
)
from voxam.glulx.glk.resources import ImageInfo
from voxam.glulx.machine import Machine
from voxam.glulx.story import Story

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


# -- the frontend and its conversation ---------------------------------------


def opened(
    support: list[str] | None = None, metrics: dict[str, Any] | None = None
) -> GlkOteFrontend:
    """A frontend that has heard its init."""

    frontend = GlkOteFrontend()

    frontend.begin(
        {
            "type": "init",
            "gen": 0,
            "support": (
                support
                if support is not None
                else ["timer", "graphicswin", "hyperlinks"]
            ),
            "metrics": metrics if metrics is not None else {"width": 80, "height": 24},
        }
    )

    return frontend


def sessioned() -> tuple[Glk, GlkOteFrontend, Window]:
    """A library over a spoken-for display, a buffer at the root."""

    frontend = opened()
    library = Glk(frontend)
    window = library.glk_window_open(None, 0, 0, WindowType.TEXT_BUFFER, 0)

    if window is None:
        pytest.fail("the root window opened")

    return library, frontend, window


def canvased() -> tuple[Glk, GlkOteFrontend, Window]:
    """A session with a canvas split above the buffer root."""

    library, frontend, root = sessioned()
    canvas = library.glk_window_open(root, ABOVE_FIXED, 8, WindowType.GRAPHICS, 0)

    if canvas is None:
        pytest.fail("the canvas opened")

    return library, frontend, canvas


# The init event grants the capabilities: graphicswin for
# canvases -- bare graphics means buffer images, unclaimed --
# timer for timers, hyperlinks for links; clicks need no grant.
def test_the_init_grants_the_capabilities() -> None:
    frontend = opened()

    assert_that(frontend.suspends).is_true()
    assert_that(frontend.mouse_input).is_true()
    assert_that(frontend.timer_input).is_true()
    assert_that(frontend.graphics).is_true()
    assert_that(frontend.hyperlink_input).is_true()

    bare = opened(support=["graphics"])

    assert_that(bare.graphics).is_false()
    assert_that(bare.timer_input).is_false()
    assert_that(bare.hyperlink_input).is_false()
    assert_that(bare.mouse_input).is_true()


# The metrics measure the display and its cells, falling back from
# the qualified key to the generic to the default, the rules
# RemGlk reads by.
def test_metrics_measure_the_cells() -> None:
    frontend = opened(
        metrics={
            "width": 640,
            "height": 480,
            "gridcharwidth": 8,
            "gridcharheight": 16,
            "gridmarginx": 4,
            "charheight": 12,
            "marginy": 3,
            "margin": 2,
            "graphicsmarginx": 6,
        }
    )

    assert_that(frontend.size()).is_equal_to((640, 480))
    assert_that(frontend.metrics_for(TextGridWindow())).is_equal_to(
        Metrics(8, 16, 4, 3)
    )
    assert_that(frontend.metrics_for(TextBufferWindow())).is_equal_to(
        Metrics(1, 12, 2, 3)
    )
    assert_that(frontend.metrics_for(GraphicsWindow())).is_equal_to(Metrics(1, 1, 6, 3))

    pair = PairWindow(TextBufferWindow(), TextBufferWindow(), TextBufferWindow(), 0, 0)

    assert_that(frontend.metrics_for(pair)).is_equal_to(CHARACTER_CELL)


# A display that has not spoken its init has no size to answer
# with, and metrics that carry no size are refused outright.
def test_a_sizeless_display_is_refused() -> None:
    with pytest.raises(GlkOteError, match="not spoken its init"):
        GlkOteFrontend().size()

    with pytest.raises(GlkOteError, match="carry no size"):
        GlkOteFrontend().begin({"type": "init", "gen": 0, "metrics": {"width": 640}})


# A suspending display is never asked for input, its flush paints
# nothing, and an unattached one has no library to speak for.
def test_a_suspending_display_is_never_asked() -> None:
    frontend = opened()

    frontend.flush(None)

    with pytest.raises(GlulxGlkError, match="never asked for a line"):
        frontend.read_line(TextBufferWindow(), 80)

    with pytest.raises(GlulxGlkError, match="never asked for a keystroke"):
        frontend.read_char(TextBufferWindow())

    with pytest.raises(GlkOteError, match="not attached"):
        frontend.render()


# Render speaks a full update first, the pass while nothing moves,
# and an exit rides the finale.
def test_render_speaks_updates_and_passes() -> None:
    _, frontend, _ = sessioned()

    first = frontend.render()

    assert_that(first["type"]).is_equal_to("update")
    assert_that(first["gen"]).is_equal_to(1)
    assert_that(first["windows"]).is_length(1)

    assert_that(frontend.render()).is_equal_to({"type": "pass"})
    assert_that(frontend.render(exit=True)).is_equal_to(
        {"type": "update", "gen": 2, "exit": True}
    )


# A canvas's operations travel in call order, its pending clear
# settled ahead of them as the colorless whole-window fill -- and
# ahead of a background change, since a clear wears the old color.
def test_a_canvas_speaks_its_draws_in_order() -> None:
    _, frontend, canvas = canvased()

    frontend.set_background_color(canvas, 0x123456)
    frontend.fill_rect(canvas, 0xAB12CD34, 1, 2, 3, 4)
    frontend.erase_rect(canvas, 5, 6, 7, 8)

    update = frontend.render()
    entry = next(held for held in update["content"] if "draw" in held)

    assert_that(entry["draw"]).is_equal_to(
        [
            {"special": "fill"},
            {"special": "setcolor", "color": "#123456"},
            {
                "special": "fill",
                "color": "#12CD34",
                "x": 1,
                "y": 2,
                "width": 3,
                "height": 4,
            },
            {"special": "fill", "x": 5, "y": 6, "width": 7, "height": 8},
        ]
    )
    assert_that(canvas.pending_clear).is_false()


# A canvas cleared and then left alone still owes the display its
# fill, at the open and at every clear after.
def test_a_cleared_canvas_still_fills() -> None:
    library, frontend, canvas = canvased()

    first = frontend.render()
    drawn = next(held for held in first["content"] if "draw" in held)

    assert_that(drawn["draw"]).is_equal_to([{"special": "fill"}])

    library.glk_window_clear(canvas)

    again = frontend.render()

    assert_that(again["content"]).is_equal_to(
        [{"id": 2, "draw": [{"special": "fill"}]}]
    )


# A picture draws on a canvas by its Pict number -- the host
# resolves numbers from the Blorb -- and nowhere else.
def test_images_draw_on_canvases_alone() -> None:
    _, frontend, canvas = canvased()
    picture = ImageInfo(5, b"PNG ", b"", 2, 2)

    assert_that(frontend.draw_image(canvas, picture, 3, 4, 10, 20)).is_true()
    assert_that(frontend.draw_image(TextBufferWindow(), picture, 0, 0, 1, 1)).is_false()

    update = frontend.render()
    entry = next(held for held in update["content"] if "draw" in held)

    assert_that(entry["draw"][-1]).is_equal_to(
        {"special": "image", "image": 5, "x": 3, "y": 4, "width": 10, "height": 20}
    )


# Draws for a window that closed before the update vanish rather
# than crash: there is nothing to show and nowhere to show it.
def test_draws_for_a_closed_window_vanish() -> None:
    library, frontend, canvas = canvased()

    frontend.fill_rect(canvas, 0xFFFFFF, 0, 0, 1, 1)
    library.glk_window_close(canvas, None)

    update = frontend.render()

    assert_that(update.get("content", [])).is_empty()
    assert_that([held["type"] for held in update["windows"]]).is_equal_to(["buffer"])


# A timer re-request restarts the display's clock even at the same
# cadence: the restart rides through render, where polled state
# alone would stay silent.
def test_the_timer_restart_rides_through_render() -> None:
    library, frontend, _ = sessioned()

    library.glk_request_timer_events(100)

    assert_that(frontend.render()["timer"]).is_equal_to(100)

    library.glk_request_timer_events(100)

    assert_that(frontend.render()["timer"]).is_equal_to(100)
    assert_that(frontend.render()).is_equal_to({"type": "pass"})


# A line event lands in its request, the echo goes back out in the
# input style, and the re-asked field wears the new generation; a
# named terminator translates, an unnamed one is a plain Return.
def test_a_line_event_lands_and_echoes() -> None:
    library, frontend, window = sessioned()

    library.glk_request_line_event(window, [0] * 8, 0)
    frontend.render()

    event = frontend.accept({"type": "line", "gen": 1, "window": 1, "value": "go"})

    if event is None:
        pytest.fail("the line landed")

    assert_that(event.as_fields()).is_equal_to((EventType.LINE_INPUT, window, 2, 0))

    library.glk_request_line_event(window, [0] * 8, 0)

    update = frontend.render()

    assert_that(update["content"][0]["text"][0]["content"][0]).is_equal_to(
        {"style": "input", "text": "go"}
    )
    assert_that(update["input"][0]["gen"]).is_equal_to(2)

    library.glk_set_terminators_line_event(window, [KeyCode.ESCAPE])
    frontend.render()

    ended = frontend.accept(
        {"type": "line", "gen": 3, "window": 1, "value": "x", "terminator": "escape"}
    )

    if ended is None:
        pytest.fail("the terminated line landed")

    assert_that(ended.val2).is_equal_to(KeyCode.ESCAPE)


def keyed(value: object, *, unicode: bool = False) -> int:
    """One char event through a fresh session; the code it lands as."""

    library, frontend, window = sessioned()

    if unicode:
        library.glk_request_char_event_uni(window)
    else:
        library.glk_request_char_event(window)

    frontend.render()

    event = frontend.accept({"type": "char", "gen": 1, "window": 1, "value": value})

    if event is None:
        pytest.fail("the keystroke landed")

    return event.val1


# A char event's value is a literal character or a key's name; a
# character beyond Latin-1 lands as the unknown key when the
# request cannot carry it, and passes whole when it can.
def test_a_char_event_translates_its_key() -> None:
    assert_that(keyed("A")).is_equal_to(65)
    assert_that(keyed("left")).is_equal_to(KeyCode.LEFT)
    assert_that(keyed("borogove")).is_equal_to(KeyCode.UNKNOWN)
    assert_that(keyed(5)).is_equal_to(KeyCode.UNKNOWN)
    assert_that(keyed("λ")).is_equal_to(KeyCode.UNKNOWN)
    assert_that(keyed("λ", unicode=True)).is_equal_to(0x3BB)


# Clicks and link selections route to their windows' requests.
def test_clicks_and_links_arrive() -> None:
    library, frontend, root = sessioned()
    grid = library.glk_window_open(root, ABOVE_FIXED, 2, WindowType.TEXT_GRID, 0)

    library.glk_request_mouse_event(grid)
    library.glk_request_hyperlink_event(root)
    frontend.render()

    clicked = frontend.accept({"type": "mouse", "gen": 1, "window": 2, "x": 3, "y": 0})

    if clicked is None:
        pytest.fail("the click landed")

    assert_that(clicked.as_fields()).is_equal_to((EventType.MOUSE_INPUT, grid, 3, 0))

    linked = frontend.accept({"type": "hyperlink", "gen": 1, "window": 1, "value": 7})

    if linked is None:
        pytest.fail("the selection landed")

    assert_that(linked.as_fields()).is_equal_to((EventType.HYPERLINK, root, 7, 0))


# A timer event carries no window at all; a redraw names its
# canvas, or names none to mean every canvas, Glk's null window.
def test_timers_and_redraws_arrive() -> None:
    _, frontend, canvas = canvased()

    frontend.render()

    ticked = frontend.accept({"type": "timer", "gen": 1})

    if ticked is None:
        pytest.fail("the tick landed")

    assert_that(ticked.kind).is_equal_to(EventType.TIMER)

    named = frontend.accept({"type": "redraw", "gen": 1, "window": 2})

    if named is None:
        pytest.fail("the redraw landed")

    assert_that(named.as_fields()).is_equal_to((EventType.REDRAW, canvas, 0, 0))

    blanket = frontend.accept({"type": "redraw", "gen": 1})

    if blanket is None:
        pytest.fail("the blanket redraw landed")

    assert_that(blanket.window).is_none()


# An arrange remeasures the display, re-lays the tree, and answers
# with the arrange event -- taken from the end of the queue, so a
# moved canvas's redraw stays queued ahead for the next selects.
def test_an_arrange_relays_and_remeasures() -> None:
    library, frontend, canvas = canvased()

    frontend.render()

    event = frontend.accept(
        {"type": "arrange", "gen": 1, "metrics": {"width": 100, "height": 30}}
    )

    if event is None:
        pytest.fail("the arrange landed")

    assert_that(event.kind).is_equal_to(EventType.ARRANGE)
    assert_that(frontend.size()).is_equal_to((100, 30))
    assert_that(canvas.bbox).is_equal_to((0, 0, 100, 8))
    assert_that([held.kind for held in library.pending_events]).is_equal_to(
        [EventType.REDRAW]
    )


# A stale generation and the kinds this face does not carry mean
# nothing here, quietly.
def test_stale_and_foreign_stanzas_mean_nothing() -> None:
    _, frontend, _ = sessioned()

    frontend.render()

    assert_that(frontend.accept({"type": "char", "gen": 0, "window": 1})).is_none()
    assert_that(frontend.accept({"type": "refresh", "gen": 1})).is_none()
    assert_that(frontend.accept({"type": "external", "gen": 1, "value": 9})).is_none()
    assert_that(frontend.accept({"type": "debuginput", "gen": 1})).is_none()


# An event for a window this session never showed is loud, and so
# is one that names no window at all.
def test_an_unknown_window_is_loud() -> None:
    library, frontend, window = sessioned()

    library.glk_request_char_event(window)
    frontend.render()

    with pytest.raises(GlkOteError, match="no window is numbered 99"):
        frontend.accept({"type": "char", "gen": 1, "window": 99, "value": "A"})

    with pytest.raises(GlkOteError, match="no window is numbered None"):
        frontend.accept({"type": "mouse", "gen": 1, "x": 1, "y": 1})


# -- the serve loop ----------------------------------------------------------

# The suspension story from the machine tests: open a buffer, ask
# for a keystroke, select, quit on the far side of the resume.
AWAITS_KEY = (
    bytes([0xC0, 0x00, 0x00])
    + bytes([0x40, 0x81, 0x00])
    + bytes([0x40, 0x81, 0x03])
    + bytes([0x40, 0x81, 0x00])
    + bytes([0x40, 0x81, 0x00])
    + bytes([0x40, 0x81, 0x00])
    + bytes([0x81, 0x30, 0x11, 0x06, 0x23, 0x05, 0x01, 0x40])
    + bytes([0x40, 0x86, 0x01, 0x40])
    + bytes([0x81, 0x30, 0x12, 0x00, 0x00, 0xD2, 0x01])
    + bytes([0x40, 0x82, 0x01, 0xC0])
    + bytes([0x81, 0x30, 0x12, 0x00, 0x00, 0xC0, 0x01])
    + bytes([0x81, 0x20])
)

INIT_LINE = json.dumps(
    {
        "type": "init",
        "gen": 0,
        "support": ["timer", "graphicswin", "hyperlinks"],
        "metrics": {"width": 80, "height": 24},
    }
)


def served(
    image: Callable[..., bytes], lines: list[str], code: bytes = AWAITS_KEY
) -> tuple[bool, list[dict[str, Any]], Machine]:
    """One whole conversation over string pipes."""

    frontend = GlkOteFrontend()
    library = Glk(frontend)
    machine = Machine(Story(image(code=code)), glk=library)
    writer = io.StringIO()

    clean = serve(
        machine,
        library,
        frontend,
        io.StringIO("".join(line + "\n" for line in lines)),
        writer,
    )

    return clean, [json.loads(held) for held in writer.getvalue().splitlines()], machine


# The whole conversation: init, the first update with its window
# and its field, one keystroke, and the exit update -- blank lines
# on the wire skipped along the way.
def test_a_session_serves_end_to_end(image: Callable[..., bytes]) -> None:
    clean, stanzas, machine = served(
        image,
        [
            INIT_LINE,
            "",
            json.dumps({"type": "char", "gen": 1, "window": 1, "value": "A"}),
        ],
    )

    assert_that(clean).is_true()
    assert_that(machine.running).is_false()
    assert_that(stanzas[0]).is_equal_to(
        {
            "type": "update",
            "gen": 1,
            "windows": [
                {
                    "id": 1,
                    "type": "buffer",
                    "rock": 0,
                    "left": 0,
                    "top": 0,
                    "width": 80,
                    "height": 24,
                }
            ],
            "input": [{"id": 1, "type": "char", "gen": 1}],
        }
    )
    assert_that(stanzas[-1]).is_equal_to(
        {"type": "update", "gen": 2, "input": [], "exit": True}
    )


# The conversation opens with an init event, or not at all.
def test_the_conversation_opens_with_init(image: Callable[..., bytes]) -> None:
    clean, stanzas, _ = served(
        image, [json.dumps({"type": "char", "gen": 1, "window": 1, "value": "A"})]
    )

    assert_that(clean).is_false()
    assert_that(stanzas[0]["type"]).is_equal_to("error")
    assert_that(stanzas[0]["message"]).contains("opens with an init")


# A display that hangs up ends the session cleanly, mid-wait.
def test_a_hangup_ends_cleanly(image: Callable[..., bytes]) -> None:
    clean, stanzas, machine = served(image, [INIT_LINE])

    assert_that(clean).is_true()
    assert_that(machine.running).is_true()
    assert_that(stanzas).is_length(1)


# What is not JSON, and JSON that is not a stanza, are answered in
# kind: the protocol's own error stanza.
def test_garbage_is_answered_in_kind(image: Callable[..., bytes]) -> None:
    clean, stanzas, _ = served(image, [INIT_LINE, "{nope"])

    assert_that(clean).is_false()
    assert_that(stanzas[-1]["type"]).is_equal_to("error")
    assert_that(stanzas[-1]["message"]).contains("not JSON")

    listed, shaped, _ = served(image, [INIT_LINE, "[1, 2]"])

    assert_that(listed).is_false()
    assert_that(shaped[-1]["message"]).contains("a stanza is a JSON object")


# A stanza that asks for nothing is answered with the pass -- a
# lockstep display is owed a response for every event it sends.
def test_a_stale_event_draws_a_pass(image: Callable[..., bytes]) -> None:
    clean, stanzas, machine = served(
        image,
        [
            INIT_LINE,
            json.dumps({"type": "char", "gen": 0, "window": 1, "value": "A"}),
            json.dumps({"type": "char", "gen": 1, "window": 1, "value": "A"}),
        ],
    )

    assert_that(clean).is_true()
    assert_that(machine.running).is_false()
    assert_that([held["type"] for held in stanzas]).is_equal_to(
        ["update", "pass", "update"]
    )


# While a file prompt stands, render dresses it in the protocol's
# names -- the usage's text-mode bit stripped -- and a mode beyond
# the four is refused the way the file streams refuse it.
def test_a_prompt_renders_as_special_input() -> None:
    library, frontend, _ = sessioned()

    frontend.render()
    library.glk_fileref_create_by_prompt(FileUsage.SAVED_GAME, FileMode.WRITE, 0)

    update = frontend.render()

    assert_that(update["specialinput"]).is_equal_to(
        {"type": "fileref_prompt", "filemode": "write", "filetype": "save"}
    )

    scripted, spoken, _ = sessioned()

    spoken.render()
    scripted.glk_fileref_create_by_prompt(
        FileUsage.TRANSCRIPT | FileUsage.TEXT_MODE, FileMode.READ_WRITE, 0
    )

    assert_that(spoken.render()["specialinput"]).is_equal_to(
        {"type": "fileref_prompt", "filemode": "readwrite", "filetype": "transcript"}
    )

    rogue, faced, _ = sessioned()

    faced.render()
    rogue.waiting = Prompting(FileUsage.DATA, 7, 0)

    with pytest.raises(GlulxGlkError, match="cannot be prompted"):
        faced.render()


# The player's file answer completes the parked call and clears
# the wait -- the signal the serving loops read; a stale one, an
# answer to some other ask, and a dialog's object all leave the
# game standing where it should stand.
def test_a_file_answer_completes_the_wait() -> None:
    library, frontend, _ = sessioned()

    frontend.render()

    prompting = Prompting(FileUsage.SAVED_GAME, FileMode.WRITE, 0)
    stored: list[int] = []
    prompting.encode = lambda value: 0 if value is None else 5
    prompting.store = stored.append
    library.waiting = prompting

    stale = {"type": "specialresponse", "gen": 0, "response": "fileref_prompt"}

    assert_that(frontend.accept(stale)).is_none()
    assert_that(library.waiting).is_same_as(prompting)

    foreign = {"type": "specialresponse", "gen": 1, "response": "other", "value": "x"}

    assert_that(frontend.accept(foreign)).is_none()
    assert_that(library.waiting).is_same_as(prompting)

    named = {
        "type": "specialresponse",
        "gen": 1,
        "response": "fileref_prompt",
        "value": "saga",
    }

    assert_that(frontend.accept(named)).is_none()
    assert_that(stored).is_equal_to([5])
    assert_that(library.waiting).is_none()

    # A dialog's fileref object was never invited: it cancels.
    library.waiting = prompting
    frontend.accept(
        {
            "type": "specialresponse",
            "gen": 1,
            "response": "fileref_prompt",
            "value": {"dialog": True},
        }
    )

    assert_that(stored).is_equal_to([5, 0])


# A story that asks the player for a save file and quits.
PROMPTS = (
    bytes([0xC0, 0x00, 0x00])
    + bytes([0x40, 0x81, 0x00])
    + bytes([0x40, 0x81, 0x01])
    + bytes([0x40, 0x81, 0x01])
    + bytes([0x81, 0x30, 0x11, 0x06, 0x62, 0x03, 0x01, 0x40])
    + bytes([0x81, 0x20])
)


# The file ask end to end: the update wears the special input, a
# stale answer draws the pass, and the real one resumes the story
# without any event delivered -- the call itself was the
# destination.
def test_a_file_ask_serves_end_to_end(image: Callable[..., bytes]) -> None:
    clean, stanzas, machine = served(
        image,
        [
            INIT_LINE,
            json.dumps(
                {"type": "specialresponse", "gen": 0, "response": "fileref_prompt"}
            ),
            json.dumps(
                {
                    "type": "specialresponse",
                    "gen": 1,
                    "response": "fileref_prompt",
                    "value": "saga",
                }
            ),
        ],
        code=PROMPTS,
    )

    assert_that(clean).is_true()
    assert_that(machine.running).is_false()
    assert_that(stanzas[0]["specialinput"]).is_equal_to(
        {"type": "fileref_prompt", "filemode": "write", "filetype": "save"}
    )
    assert_that([held["type"] for held in stanzas]).is_equal_to(
        ["update", "pass", "update"]
    )


# Input delivered where no request stands is a driver's bug, and
# the conversation says so before it ends.
def test_a_wrongful_event_is_loud(image: Callable[..., bytes]) -> None:
    clean, stanzas, _ = served(
        image,
        [INIT_LINE, json.dumps({"type": "line", "gen": 1, "window": 1, "value": "go"})],
    )

    assert_that(clean).is_false()
    assert_that(stanzas[-1]["type"]).is_equal_to("error")
    assert_that(stanzas[-1]["message"]).contains("not expecting")
