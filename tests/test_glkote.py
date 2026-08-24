"""The GlkOte update builder: what changed travels, the rest stays home."""

from typing import Any, cast

import pytest
from assertpy import assert_that

from voxam.errors import GlkOteError
from voxam.glkote import FLOWBREAK, Page

BOX = (0, 0, 640, 400)
TOP = (0, 0, 640, 30)


def buffered() -> Page:
    """A page with one buffer window declared."""

    page = Page()

    page.window(1, "buffer", 0, BOX)

    return page


def turned(page: Page) -> None:
    """Send one update and redeclare the lone buffer for the next."""

    page.update()

    page.window(1, "buffer", 0, BOX)


def spans(update: dict[str, Any]) -> list[dict[str, Any]]:
    """The text entries of the first content element."""

    return cast("list[dict[str, Any]]", update["content"][0]["text"])


# The first update always carries the whole windows array at
# generation one -- the display starts knowing nothing (GlkOte:
# The Generation Number).
def test_the_first_update_carries_the_whole_tree() -> None:
    page = buffered()

    update = page.update()

    assert_that(update).is_equal_to(
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
                    "width": 640,
                    "height": 400,
                }
            ],
        }
    )
    assert_that(page.gen).is_equal_to(1)


# Even an empty tree's first update says so out loud: the empty
# windows array closes everything, which is not the same as
# omitting it (GlkOte: Output: Updating the Display).
def test_an_empty_tree_still_speaks_first() -> None:
    page = Page()

    assert_that(page.update()).is_equal_to({"type": "update", "gen": 1, "windows": []})


# A cycle where nothing changed answers the pass stanza and holds
# the generation where it stood.
def test_an_unchanged_cycle_passes() -> None:
    page = buffered()

    page.update()
    page.window(1, "buffer", 0, BOX)

    assert_that(page.update()).is_equal_to({"type": "pass"})
    assert_that(page.gen).is_equal_to(1)


# A moved window resends the whole windows array; a stable tree
# with fresh content omits it.
def test_windows_travel_only_when_the_tree_moves() -> None:
    page = buffered()

    page.update()
    page.window(1, "buffer", 0, (0, 30, 640, 400))

    moved = page.update()

    assert_that(moved["gen"]).is_equal_to(2)
    assert_that(moved["windows"][0]["top"]).is_equal_to(30)

    page.window(1, "buffer", 0, (0, 30, 640, 400))
    page.buffer(1, [("normal", 0, "text")])

    steady = page.update()

    assert_that(steady).does_not_contain_key("windows")
    assert_that(steady).contains_key("content")


# Closing one window shrinks the array; closing the last sends the
# empty array that closes them all.
def test_closing_windows_shrinks_the_array() -> None:
    page = Page()

    page.window(1, "buffer", 0, BOX)
    page.window(2, "grid", 0, TOP, gridsize=(80, 1))
    page.update()

    page.window(1, "buffer", 0, BOX)

    fewer = page.update()

    assert_that([held["id"] for held in fewer["windows"]]).is_equal_to([1])

    empty = page.update()

    assert_that(empty["windows"]).is_equal_to([])


# A closed window's id is retired for good: the protocol forbids
# reuse (GlkOte: The Windows Update Array).
def test_a_retired_id_may_never_return() -> None:
    page = buffered()

    page.update()
    page.update()

    with pytest.raises(GlkOteError, match="may never return"):
        page.window(1, "buffer", 0, BOX)


# Newlines split runs into paragraph entries; text after the last
# newline leaves its paragraph open, and the next cycle's first
# entry continues it with the append flag -- until a newline
# closes it (GlkOte: Buffer Window Updates).
def test_paragraphs_split_and_append() -> None:
    page = buffered()

    page.buffer(1, [("normal", 0, "a\nb")])

    assert_that(spans(page.update())).is_equal_to(
        [
            {"content": [{"style": "normal", "text": "a"}]},
            {"content": [{"style": "normal", "text": "b"}]},
        ]
    )

    page.window(1, "buffer", 0, BOX)
    page.buffer(1, [("normal", 0, "c\n")])

    assert_that(spans(page.update())).is_equal_to(
        [{"append": True, "content": [{"style": "normal", "text": "c"}]}]
    )

    page.window(1, "buffer", 0, BOX)
    page.buffer(1, [("normal", 0, "d")])

    assert_that(spans(page.update())).is_equal_to(
        [{"content": [{"style": "normal", "text": "d"}]}]
    )


# Consecutive newlines become blank lines, the empty object; a
# leading newline on an open paragraph only closes it, and on a
# fresh window it is a blank line like any other.
def test_blank_lines_are_empty_objects() -> None:
    page = buffered()

    page.buffer(1, [("normal", 0, "x\n\n\ny")])

    assert_that(spans(page.update())).is_equal_to(
        [
            {"content": [{"style": "normal", "text": "x"}]},
            {},
            {},
            {"content": [{"style": "normal", "text": "y"}]},
        ]
    )

    page.window(1, "buffer", 0, BOX)
    page.buffer(1, [("normal", 0, "\nz")])

    assert_that(spans(page.update())).is_equal_to(
        [{"content": [{"style": "normal", "text": "z"}]}]
    )

    fresh = buffered()

    fresh.buffer(1, [("normal", 0, "\nz")])

    assert_that(spans(fresh.update())).is_equal_to(
        [{}, {"content": [{"style": "normal", "text": "z"}]}]
    )


# A clear rides the content entry, resets the open paragraph, and
# needs no text to be worth sending.
def test_a_clear_rides_the_entry() -> None:
    page = buffered()

    page.buffer(1, [("normal", 0, "before")])
    turned(page)

    page.buffer(1, [("normal", 0, "after")], clear=True)

    entry = page.update()["content"][0]

    assert_that(entry["clear"]).is_true()
    assert_that(entry["text"]).is_equal_to(
        [{"content": [{"style": "normal", "text": "after"}]}]
    )

    page.window(1, "buffer", 0, BOX)
    page.buffer(1, [], clear=True)

    assert_that(page.update()["content"]).is_equal_to([{"id": 1, "clear": True}])

    # An empty helping with nothing to clear is no helping at all.
    page.window(1, "buffer", 0, BOX)
    page.buffer(1, [("normal", 0, "")])

    assert_that(page.update()).is_equal_to({"type": "pass"})


# Runs wear their style names and hyperlink values; alike
# neighbours coalesce, and a style the protocol does not name is
# refused (GlkOte: The Line Data Array).
def test_runs_wear_style_and_link() -> None:
    page = buffered()

    page.buffer(
        1,
        [
            ("header", 0, "H"),
            ("normal", 3, "link"),
            ("normal", 0, "a"),
            ("normal", 0, "b"),
        ],
    )

    assert_that(spans(page.update())).is_equal_to(
        [
            {
                "content": [
                    {"style": "header", "text": "H"},
                    {"style": "normal", "text": "link", "hyperlink": 3},
                    {"style": "normal", "text": "ab"},
                ]
            }
        ]
    )

    with pytest.raises(GlkOteError, match="no style is named"):
        buffered().buffer(1, [("fancy", 0, "x")])


# A flow break closes the paragraph and flags the next entry --
# even when the next entry arrives a whole cycle later.
def test_a_flow_break_flags_what_follows() -> None:
    page = buffered()

    page.buffer(1, [("normal", 0, "para"), FLOWBREAK, ("normal", 0, "below")])

    assert_that(spans(page.update())).is_equal_to(
        [
            {"content": [{"style": "normal", "text": "para"}]},
            {"flowbreak": True, "content": [{"style": "normal", "text": "below"}]},
        ]
    )

    page.window(1, "buffer", 0, BOX)
    page.buffer(1, [("normal", 0, "held"), FLOWBREAK])
    turned(page)

    page.buffer(1, [("normal", 0, "later")])

    assert_that(spans(page.update())).is_equal_to(
        [{"flowbreak": True, "content": [{"style": "normal", "text": "later"}]}]
    )


def gridded() -> Page:
    """A page with one grid window declared."""

    page = Page()

    page.window(1, "grid", 0, TOP, gridsize=(80, 3))

    return page


# Only a grid's changed rows travel, trailing plain whitespace
# stripped first -- so a fresh grid sends only what shows, and a
# row gone blank sends a bare line number (GlkOte: Grid Window
# Updates).
def test_a_grid_sends_only_changed_rows() -> None:
    page = gridded()
    face = [[("normal", 0, "Score 10   ")], [], []]

    page.grid(1, face)

    assert_that(page.update()["content"]).is_equal_to(
        [
            {
                "id": 1,
                "lines": [
                    {"line": 0, "content": [{"style": "normal", "text": "Score 10"}]}
                ],
            }
        ]
    )

    page.window(1, "grid", 0, TOP, gridsize=(80, 3))
    page.grid(1, face)

    assert_that(page.update()).is_equal_to({"type": "pass"})

    page.window(1, "grid", 0, TOP, gridsize=(80, 3))
    page.grid(1, [[], [("alert", 0, "!  ")], []])

    assert_that(page.update()["content"][0]["lines"]).is_equal_to(
        [
            {"line": 0},
            {"line": 1, "content": [{"style": "alert", "text": "!  "}]},
        ]
    )


# A resized grid forgets its cache: what the display keeps across
# a resize is unspecified, so every row is resent.
def test_a_resized_grid_resends_its_rows() -> None:
    page = gridded()
    face = [[("normal", 0, "steady")], [], []]

    page.grid(1, face)
    page.update()

    page.window(1, "grid", 0, (0, 0, 640, 20), gridsize=(80, 2))
    page.grid(1, face[:2])

    update = page.update()

    assert_that(update["windows"][0]["gridheight"]).is_equal_to(2)
    assert_that(update["content"][0]["lines"]).is_equal_to(
        [{"line": 0, "content": [{"style": "normal", "text": "steady"}]}]
    )


# A posted line input carries the current generation and its
# dress; carried unchanged, it keeps that generation and the input
# array stays home (GlkOte: The Input Update Array).
def test_a_line_input_posts_and_carries() -> None:
    page = Page()

    page.window(1, "buffer", 0, BOX)
    page.window(2, "buffer", 0, TOP)
    page.line_input(1, 80, initial="go", terminators=("escape", "func5"))

    update = page.update()

    assert_that(update["input"]).is_equal_to(
        [
            {
                "id": 1,
                "type": "line",
                "maxlen": 80,
                "initial": "go",
                "terminators": ["escape", "func5"],
                "gen": 1,
            }
        ]
    )

    page.window(1, "buffer", 0, BOX)
    page.window(2, "buffer", 0, TOP)
    page.line_input(1, 80, initial="go", terminators=("escape", "func5"))
    page.buffer(2, [("normal", 0, "elsewhere")])

    carried = page.update()

    assert_that(carried).does_not_contain_key("input")
    assert_that(carried["gen"]).is_equal_to(2)

    with pytest.raises(GlkOteError, match="no terminator key"):
        buffered().line_input(1, 80, terminators=("tab",))


# Content reaching a window recreates its carried field at the new
# generation -- a carried field forbids content, a recreated one
# permits it (GlkOte: The Input Update Array).
def test_content_recreates_a_carried_field() -> None:
    page = buffered()

    page.line_input(1, 80)
    turned(page)

    page.line_input(1, 80)
    page.buffer(1, [("input", 0, "go north\n")])

    update = page.update()

    assert_that(update["input"]).is_equal_to(
        [{"id": 1, "type": "line", "maxlen": 80, "gen": 2}]
    )


# Changed parameters recreate the field even with no content: a
# carried field's initial and terminators would be ignored.
def test_changed_parameters_recreate_the_field() -> None:
    page = buffered()

    page.line_input(1, 80)
    turned(page)

    page.line_input(1, 80, initial="north")

    update = page.update()

    assert_that(update["input"]).is_equal_to(
        [{"id": 1, "type": "line", "maxlen": 80, "initial": "north", "gen": 2}]
    )


# Cancelling one field resends the shrunken roster; cancelling the
# last sends the empty array that cancels them all.
def test_cancelling_fields_resends_the_roster() -> None:
    page = Page()

    page.window(1, "buffer", 0, BOX)
    page.window(2, "buffer", 0, TOP)
    page.char_input(1)
    page.char_input(2)
    page.update()

    page.window(1, "buffer", 0, BOX)
    page.window(2, "buffer", 0, TOP)
    page.char_input(1)

    fewer = page.update()

    assert_that(fewer["input"]).is_equal_to([{"id": 1, "type": "char", "gen": 1}])

    page.window(1, "buffer", 0, BOX)
    page.window(2, "buffer", 0, TOP)

    empty = page.update()

    assert_that(empty["input"]).is_equal_to([])


# Character input in a grid carries its cursor; a mouse-and-link
# listener with no typing is the passive form, and one listening
# for nothing is left out entirely.
def test_char_and_passive_entries() -> None:
    page = Page()

    page.window(1, "grid", 0, TOP, gridsize=(80, 1))
    page.window(2, "graphics", 0, BOX, graphsize=(640, 400))
    page.char_input(1, cursor=(3, 0))
    page.passive_input(2, hyperlink=True, mouse=True)

    update = page.update()

    assert_that(update["input"]).is_equal_to(
        [
            {"id": 1, "type": "char", "gen": 1, "xpos": 3, "ypos": 0},
            {"id": 2, "hyperlink": True, "mouse": True},
        ]
    )

    quiet = buffered()

    quiet.passive_input(1)

    assert_that(quiet.update()).does_not_contain_key("input")


# The timer travels when it changes, as null when it stops, not at
# all while it holds steady -- and again on a deliberate restart,
# since resending restarts the display's clock (GlkOte: The Timer
# Update).
def test_the_timer_travels_only_on_change() -> None:
    page = buffered()

    page.timer(100)

    assert_that(page.update()["timer"]).is_equal_to(100)

    page.window(1, "buffer", 0, BOX)
    page.timer(100)

    assert_that(page.update()).is_equal_to({"type": "pass"})

    page.window(1, "buffer", 0, BOX)
    page.timer(100, restart=True)

    assert_that(page.update()["timer"]).is_equal_to(100)

    page.window(1, "buffer", 0, BOX)
    page.timer(0)

    assert_that(page.update()["timer"]).is_none()

    page.window(1, "buffer", 0, BOX)
    page.timer(0)

    assert_that(page.update()).is_equal_to({"type": "pass"})


# Drawing operations accumulate and travel in order; a fill names
# its whole rectangle or none of it, and an operation the protocol
# does not draw is refused (GlkOte: Graphics Window Updates).
def test_draw_ops_travel_in_order() -> None:
    page = Page()

    page.window(1, "graphics", 0, BOX, graphsize=(640, 400))
    page.draw(1, [{"special": "setcolor", "color": "#C0207F"}])
    page.draw(1, [{"special": "fill", "x": 0, "y": 0, "width": 8, "height": 8}])

    assert_that(page.update()["content"]).is_equal_to(
        [
            {
                "id": 1,
                "draw": [
                    {"special": "setcolor", "color": "#C0207F"},
                    {"special": "fill", "x": 0, "y": 0, "width": 8, "height": 8},
                ],
            }
        ]
    )

    with pytest.raises(GlkOteError, match="whole rectangle"):
        page.draw(1, [{"special": "fill", "x": 1}])

    with pytest.raises(GlkOteError, match="no drawing operation"):
        page.draw(1, [{"special": "sparkle"}])


# The cycle's pieces must agree: content belongs to a declared
# window of the right kind, buffers take no clicks, and grid input
# names its cursor.
def test_contradictory_cycles_are_refused() -> None:
    page = Page()

    page.buffer(9, [("normal", 0, "lost")])

    with pytest.raises(GlkOteError, match="never declared"):
        page.update()

    unasked = Page()

    unasked.char_input(9)

    with pytest.raises(GlkOteError, match="input was asked"):
        unasked.update()

    crowded = buffered()

    with pytest.raises(GlkOteError, match="declared twice"):
        crowded.window(1, "buffer", 0, BOX)

    rowed = buffered()

    rowed.grid(1, [[]])

    with pytest.raises(GlkOteError, match="not a grid"):
        rowed.update()

    clicked = buffered()

    clicked.char_input(1, mouse=True)

    with pytest.raises(GlkOteError, match="takes no clicks"):
        clicked.update()

    blind = Page()

    blind.window(1, "grid", 0, TOP, gridsize=(80, 1))
    blind.char_input(1)

    with pytest.raises(GlkOteError, match="at a cursor"):
        blind.update()

    with pytest.raises(GlkOteError, match="cannot be a"):
        Page().window(1, "porthole", 0, BOX)

    with pytest.raises(GlkOteError, match="columns and rows"):
        Page().window(1, "grid", 0, TOP)

    with pytest.raises(GlkOteError, match="drawable size"):
        Page().window(1, "buffer", 0, BOX, graphsize=(1, 1))


# One window, one helping: text, rows, and input arrive once per
# cycle each.
def test_second_helpings_are_refused() -> None:
    page = buffered()

    page.buffer(1, [("normal", 0, "once")])

    with pytest.raises(GlkOteError, match="fed text twice"):
        page.buffer(1, [("normal", 0, "twice")])

    rows = gridded()

    rows.grid(1, [[]])

    with pytest.raises(GlkOteError, match="fed rows twice"):
        rows.grid(1, [[]])

    asked = buffered()

    asked.line_input(1, 80)

    with pytest.raises(GlkOteError, match="input twice"):
        asked.char_input(1)


# A file ask rides the update as special input and forces one on
# its own; a second ask in a cycle, and names the protocol lacks,
# are loud.
def test_a_file_ask_rides_the_update() -> None:
    page = buffered()

    page.update()
    page.window(1, "buffer", 0, BOX)
    page.prompt("write", "save")

    assert_that(page.update()).is_equal_to(
        {
            "type": "update",
            "gen": 2,
            "specialinput": {
                "type": "fileref_prompt",
                "filemode": "write",
                "filetype": "save",
            },
        }
    )

    asked = buffered()

    asked.prompt("read", "data")

    with pytest.raises(GlkOteError, match="one file"):
        asked.prompt("read", "data")

    with pytest.raises(GlkOteError, match="no file prompt asks"):
        buffered().prompt("scribble", "save")


# An exit rides an update of its own making: the game is over,
# and that is worth a generation even when nothing else moved.
def test_exit_forces_a_real_update() -> None:
    page = buffered()

    page.update()
    page.window(1, "buffer", 0, BOX)

    assert_that(page.update(exit=True)).is_equal_to(
        {"type": "update", "gen": 2, "exit": True}
    )
