import pytest
from assertpy import assert_that

from voxam.errors import ZMachineScreenError
from voxam.frontend import Status
from voxam.screen import BOLD, REVERSE, ROMAN
from voxam.stage import StageModel


# A readable geometry: 20 by 10 cells of 10-by-10-unit type, so a
# screen of 200 by 100 units and every position a round number.
def staged() -> StageModel:
    return StageModel(columns=20, lines=10, font_width=10, font_height=10)


# The §8.8.3.3 boot stage: window 0 fills the screen, wraps whole
# words at its right edge, and scrolls its own text.
def test_window_0_boots_full_wrapping_and_scrolling() -> None:
    stage = staged()

    assert_that(stage.selected).is_zero()

    stage.write("a stretch of words that wraps at the twentieth column")

    assert_that(stage.row_text(1)).is_equal_to("a stretch of words")
    assert_that(stage.row_text(2)).is_equal_to("that wraps at the")
    assert_that(stage.row_text(3)).is_equal_to("twentieth column")


# Text past the bottom scrolls window 0's rectangle: the scroll is
# owed at the last line and paid when the next text arrives, so
# the final line stays at the window's foot.
def test_window_0_scrolls_at_its_bottom() -> None:
    stage = staged()

    stage.write("\n".join(str(number) for number in range(1, 12)))

    assert_that(stage.row_text(1)).is_equal_to("2")
    assert_that(stage.row_text(10)).is_equal_to("11")

    stage.write("\n12")

    assert_that(stage.row_text(1)).is_equal_to("3")
    assert_that(stage.row_text(10)).is_equal_to("12")

    # Consecutive blank lines at the bottom each earn their own
    # scroll: an owed one is paid before the next is owed.
    stage.write("\n\n13")

    assert_that(stage.row_text(10)).is_equal_to("13")
    assert_that(stage.row_text(9)).is_equal_to("")
    assert_that(stage.row_text(8)).is_equal_to("12")


# A placed window takes its text at its own position: the cursor
# is window-relative units, the printing lands on the grid, and
# get_cursor answers in the same units printing advanced it to.
def test_placed_windows_take_text_at_their_position() -> None:
    stage = staged()

    stage.place_window(3, 21, 51, 30, 80)
    stage.set_window(3)
    stage.set_cursor(11, 21)
    stage.write("boxed")

    assert_that(stage.row_text(4)).is_equal_to("       boxed")
    assert_that(stage.get_cursor()).is_equal_to((11, 71))
    assert_that(stage.cell(4, 8).character).is_equal_to("b")


# A window with wrapping off prints to its right margin, parks the
# cursor there, and ignores the rest (§8.8.3.1.1); a newline in a
# non-scrolling window pins at its bottom line.
def test_unwrapped_windows_pin_at_their_margin() -> None:
    stage = staged()

    stage.place_window(2, 11, 11, 20, 50)
    stage.set_window(2)
    stage.write("overflowing text")
    stage.write(" more")

    assert_that(stage.row_text(2)).is_equal_to(" overf")

    stage.write("\n\ndown")

    assert_that(stage.row_text(3)).is_equal_to(" down")


# With buffering off, wrapping breaks after the last character
# that fits (§8.8.3.1.2.2), and a space at the margin becomes the
# line break itself.
def test_unbuffered_wrapping_breaks_by_character() -> None:
    stage = staged()

    stage.set_buffering(False)
    stage.write("abcdefghijklmnopqrstuvwx")

    assert_that(stage.row_text(1)).is_equal_to("abcdefghijklmnopqrst")
    assert_that(stage.row_text(2)).is_equal_to("uvwx")

    stage.set_buffering(True)
    stage.write("yz" + " " * 17 + "end word")

    assert_that(stage.row_text(2)).is_equal_to("uvwxyz")
    assert_that(stage.row_text(3)).is_equal_to("  end word")


# A word too long for any line simply character-wraps: there is no
# whole line it could have waited for.
def test_giant_words_wrap_by_character() -> None:
    stage = staged()

    stage.write("a" * 25 + " tail")

    assert_that(stage.row_text(1)).is_equal_to("a" * 20)
    assert_that(stage.row_text(2)).is_equal_to("aaaaa tail")


# split_window tiles windows 1 and 0 vertically in units
# (§8.8.4.1): window 1 takes the top, window 0 the rest, and each
# cursor keeps its absolute screen position -- homing only when
# that position falls outside its window.
def test_split_tiles_the_two_windows() -> None:
    stage = staged()

    stage.write("\n\n\nfour")
    stage.split_window(20)
    stage.write(" deep")

    assert_that(stage.row_text(4)).is_equal_to("four deep")

    stage.set_window(1)
    stage.write("top")

    assert_that(stage.row_text(1)).is_equal_to("top")

    stage.set_window(0)
    stage.set_cursor(1, 1)
    stage.write("below")

    assert_that(stage.row_text(3)).is_equal_to("below")

    # A split to the full screen leaves window 0 no rows at all:
    # its cursor falls outside and homes, and its text goes
    # nowhere, quietly.
    stage.split_window(100)
    stage.set_window(0)
    stage.write("homed")

    assert_that(stage.get_cursor()).is_equal_to((1, 1))


# erase_window fills a window's own rectangle with its background,
# homes its cursor, and answers the cell rectangle it touched; -2
# erases the whole screen and moves nothing.
def test_erasures_fill_their_rectangles() -> None:
    stage = staged()

    stage.write("story text everywhere")
    stage.place_window(4, 11, 11, 20, 40)
    stage.set_window(4)
    stage.write("gone")

    rectangle = stage.erase_window(4)

    # Only the window's own rectangle blanks: "everywhere" on row
    # 2 loses exactly the cells the window covered.
    assert_that(rectangle).is_equal_to((2, 2, 2, 4))
    assert_that(stage.row_text(2)).is_equal_to("e    where")
    assert_that(stage.row_text(1)).is_equal_to("story text")
    assert_that(stage.get_cursor()).is_equal_to((1, 1))

    assert_that(stage.erase_window(-2)).is_equal_to((1, 1, 10, 20))
    assert_that(stage.row_text(1)).is_equal_to("")
    assert_that(stage.selected).is_equal_to(4)

    with pytest.raises(ZMachineScreenError, match="not one of the eight"):
        stage.erase_window(9)


# Erasing -1 clears the whole screen to window 0's background,
# re-tiles a split back to nothing (§8.8.4.2), and selects window
# 0 with its cursor homed (§8.8.5.3.1).
def test_erasing_minus_one_unsplits_and_selects_zero() -> None:
    stage = staged()

    stage.split_window(30)
    stage.set_window(1)
    stage.write("chrome")

    assert_that(stage.erase_window(-1)).is_equal_to((1, 1, 10, 20))
    assert_that(stage.selected).is_zero()
    assert_that(stage.rendered().strip()).is_equal_to("")

    stage.write("fresh")

    assert_that(stage.row_text(1)).is_equal_to("fresh")


# erase_line blanks from the cursor to the window's right edge; a
# cursor already past the window's rows erases nothing.
def test_erase_line_stops_at_the_window_edge() -> None:
    stage = staged()

    stage.place_window(5, 11, 11, 20, 60)
    stage.set_window(5)
    stage.write("wiped!")
    stage.set_cursor(1, 31)
    stage.erase_line()

    assert_that(stage.row_text(2)).is_equal_to(" wip")

    stage.set_cursor(31, 1)
    stage.erase_line()

    assert_that(stage.row_text(2)).is_equal_to(" wip")


# rub_out retreats one cell and blanks it, and at the window's
# left edge there is nothing left to rub.
def test_rub_out_retreats_one_cell() -> None:
    stage = staged()

    stage.write("hi")
    stage.rub_out()

    assert_that(stage.row_text(1)).is_equal_to("h")
    assert_that(stage.get_cursor()).is_equal_to((1, 11))

    stage.rub_out()
    stage.rub_out()

    assert_that(stage.row_text(1)).is_equal_to("")
    assert_that(stage.get_cursor()).is_equal_to((1, 1))


# A §15 rectangle prints right and down from the cursor without
# wrapping, each row at the starting column, pressing onto the
# window's bottom line when too tall.
def test_rectangles_stamp_down_from_the_cursor() -> None:
    stage = staged()

    stage.place_window(6, 21, 31, 30, 50)
    stage.set_window(6)
    stage.set_cursor(1, 11)
    stage.write_rectangle(["ab", "cd", "ef", "gh"])

    assert_that(stage.row_text(3)).is_equal_to("    ab")
    assert_that(stage.row_text(4)).is_equal_to("    cd")
    assert_that(stage.row_text(5)).is_equal_to("    gh")


# Style, colour, and font dress each window separately
# (§8.8.3.2.3): a selection change swaps the whole dress, roman
# clears the styles, and the background answers for the selected
# window.
def test_each_window_wears_its_own_dress() -> None:
    stage = staged()

    stage.set_style(REVERSE)
    stage.set_style(BOLD)
    stage.set_colour(3, 4)
    stage.set_font(3)
    stage.write("a")

    dressed = stage.cell(1, 1)

    assert_that(dressed.style).is_equal_to(REVERSE | BOLD)
    assert_that(dressed.foreground).is_equal_to(3)
    assert_that(dressed.font).is_equal_to(3)
    assert_that(stage.background).is_equal_to(4)

    stage.place_window(1, 1, 1, 10, 200)
    stage.set_window(1)

    assert_that(stage.background).is_equal_to(1)

    stage.set_style(ROMAN)
    stage.write("b")

    assert_that(stage.cell(1, 1).style).is_equal_to(ROMAN)

    stage.set_window(0)
    stage.set_style(ROMAN)
    stage.set_colour(0, 0)

    assert_that(stage.background).is_equal_to(4)


# A window that was never placed has no cells: its text goes
# nowhere, quietly, and a window hanging past the screen edge
# clips instead of crashing.
def test_sizeless_and_overhanging_windows_clip() -> None:
    stage = staged()

    stage.set_window(7)
    stage.write("nowhere\n")
    stage.write_rectangle(["x"])

    assert_that(stage.rendered().strip()).is_equal_to("")

    stage.place_window(7, 91, 191, 40, 40)
    stage.set_window(7)
    stage.write("edge")

    assert_that(stage.row_text(10)).is_equal_to(" " * 19 + "e")


# The stage refuses a §8.2 status line -- a Version 6 game draws
# its own -- and polices window numbers loudly.
def test_the_stage_refuses_status_and_strange_windows() -> None:
    stage = staged()

    with pytest.raises(ZMachineScreenError, match="draws its own status"):
        stage.show_status(Status("Nowhere", 0, 0, time_game=False))

    with pytest.raises(ZMachineScreenError, match="not one of the eight"):
        stage.set_window(8)


# Margins bound the wrapping text (§8.8.3.2.1): a newline returns
# to the left margin, words wrap at the right margin -- here 30
# and 50 units leave text columns 4 to 15 -- and erase_line
# reaches only to the right margin (§8.8.5.2).
def test_margins_bound_the_wrapping_text() -> None:
    stage = staged()

    stage.set_margins(0, 30, 50)
    stage.write("\nabc def ghi")

    assert_that(stage.row_text(2)).is_equal_to("   abc def ghi")

    stage.write(" jklmn")

    assert_that(stage.row_text(3)).is_equal_to("   jklmn")

    stage.set_cursor(11, 111)
    stage.erase_line()

    assert_that(stage.row_text(2)).is_equal_to("   abc def")

    # Loosening the margins around a cursor already inside them
    # moves nothing (§8.8.3.2.2.2).
    stage.set_margins(0, 20, 20)

    assert_that(stage.get_cursor()).is_equal_to((11, 111))


# Changing margins nudges a cursor they would strand to the left
# margin (§8.8.3.2.2.2); margins that leave no room at all swallow
# the text quietly.
def test_margins_nudge_a_stranded_cursor() -> None:
    stage = staged()

    stage.write("edge")
    stage.set_margins(0, 60, 60)

    assert_that(stage.get_cursor()).is_equal_to((1, 61))

    stage.set_margins(0, 110, 110)
    stage.write("gone")

    assert_that(stage.row_text(1)).is_equal_to("edge")


# scroll_window shifts a window's own rectangle by whole cell
# rows: positive up, negative down, exposed rows blanked, and a
# fraction of a cell row scrolls nothing (§8.8.3.6).
def test_scroll_window_shifts_the_rectangle() -> None:
    stage = staged()

    stage.write("one\ntwo\nthree")
    stage.scroll_window(0, 10)

    assert_that(stage.row_text(1)).is_equal_to("two")
    assert_that(stage.row_text(2)).is_equal_to("three")
    assert_that(stage.row_text(3)).is_equal_to("")

    stage.scroll_window(0, -10)

    assert_that(stage.row_text(1)).is_equal_to("")
    assert_that(stage.row_text(2)).is_equal_to("two")

    stage.scroll_window(0, 5)

    assert_that(stage.row_text(2)).is_equal_to("two")


# The damage sweep names changed rows once and clears its slate;
# a cursor sent below units 1 clamps to the window's origin; the
# stage reports its own cell dimensions.
def test_sweeps_and_cursor_clamps() -> None:
    stage = staged()

    stage.write("row one\nrow two")

    assert_that(stage.sweep()).is_equal_to([1, 2])
    assert_that(stage.sweep()).is_empty()

    stage.set_cursor(0, 0)

    assert_that(stage.get_cursor()).is_equal_to((1, 1))
    assert_that(stage.columns).is_equal_to(20)
    assert_that(stage.lines).is_equal_to(10)


# Erasing -1 on a stage never split leaves the tiling alone: there
# is nothing to unsplit (§8.8.4.2).
def test_erasing_minus_one_without_a_split_retiles_nothing() -> None:
    stage = staged()

    stage.write("words")

    assert_that(stage.erase_window(-1)).is_equal_to((1, 1, 10, 20))
    assert_that(stage.rendered().strip()).is_equal_to("")
