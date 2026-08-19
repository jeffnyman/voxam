import pytest
from assertpy import assert_that

from voxam.errors import ZMachineScreenError
from voxam.frontend import GRAPHICS_FONT, NORMAL_FONT, Status
from voxam.screen import (
    BOLD,
    ITALIC,
    LOWER,
    REVERSE,
    ROMAN,
    UPPER,
    ScreenModel,
)

WIDTH = 20
HEIGHT = 6


def small(version: int = 3) -> ScreenModel:
    return ScreenModel(columns=WIDTH, lines=HEIGHT, version=version)


# The start-of-game screen is cleared with the cursor at the bottom
# left through Version 4, so text scrolls upward as the game gets
# under way (§8.6.3, §8.7.3.3).
def test_versions_through_4_start_at_the_bottom() -> None:
    screen = small(version=4)

    screen.write("hello")

    assert_that(screen.row_text(HEIGHT)).is_equal_to("hello")


# From Version 5 the start-of-game cursor sits at the top left
# (§8.7.3.3).
def test_version_5_starts_at_the_top() -> None:
    screen = small(version=5)

    screen.write("hello")

    assert_that(screen.row_text(1)).is_equal_to("hello")


# While buffering is on, a word that would overrun the margin wraps
# whole onto the next line (§15 buffer_mode).
def test_buffered_text_wraps_at_word_boundaries() -> None:
    screen = small(version=5)

    screen.write("a mellifluous parsing")

    assert_that(screen.row_text(1)).is_equal_to("a mellifluous")
    assert_that(screen.row_text(2)).is_equal_to("parsing")


# A space that would wrap becomes the line break itself: the next
# line never opens with the gap.
def test_a_margin_space_becomes_the_break() -> None:
    screen = small(version=5)

    screen.write("aaaaaaaaaaaaaaaaaaaa bb")

    assert_that(screen.row_text(1)).is_equal_to("a" * WIDTH)
    assert_that(screen.row_text(2)).is_equal_to("bb")


# A word too long for any line has no whole line to wait for, so it
# character-wraps.
def test_an_overlong_word_character_wraps() -> None:
    screen = small(version=5)

    screen.write("x" * (WIDTH + 3))

    assert_that(screen.row_text(1)).is_equal_to("x" * WIDTH)
    assert_that(screen.row_text(2)).is_equal_to("xxx")


# With buffering off, text breaks wherever the margin falls (§15
# buffer_mode).
def test_unbuffered_text_breaks_at_the_margin() -> None:
    screen = small(version=5)

    screen.set_buffering(False)
    screen.write("abcdefghij klmnopqrstuv")

    assert_that(screen.row_text(1)).is_equal_to("abcdefghij klmnopqrs")
    assert_that(screen.row_text(2)).is_equal_to("tuv")


# When text reaches the bottom of the lower window it scrolls
# upward, and the upper region stays put (§8.6.2, §8.7.3.1).
def test_the_lower_window_scrolls_and_the_upper_does_not() -> None:
    screen = small(version=5)

    screen.split_window(1)
    screen.set_window(UPPER)
    screen.write("STATUS")
    screen.set_window(LOWER)

    for number in range(1, 8):
        screen.write(f"line {number}\n")

    assert_that(screen.row_text(1)).is_equal_to("STATUS")
    assert_that(screen.row_text(2)).is_equal_to("line 3")
    assert_that(screen.row_text(HEIGHT)).is_equal_to("line 7")


# The fresh line a scroll exposes is blank without reverse video,
# even while the text style is Reverse (§8.7.3.1).
def test_scrolling_never_reverses_the_fresh_line() -> None:
    screen = small(version=5)

    screen.set_style(REVERSE)

    for number in range(1, 8):
        screen.write(f"row {number}\n")

    screen.write("row 8")

    assert_that(screen.cell(HEIGHT, 10).style).is_equal_to(ROMAN)


# Styles dress the characters printed after them; Roman clears the
# combination (§8.7.1, §15 set_text_style).
def test_styles_combine_and_roman_clears() -> None:
    screen = small(version=5)

    screen.set_style(BOLD)
    screen.set_style(ITALIC)
    screen.write("ab")
    screen.set_style(ROMAN)
    screen.write("c")

    assert_that(screen.cell(1, 1).style).is_equal_to(BOLD | ITALIC)
    assert_that(screen.cell(1, 3).style).is_equal_to(ROMAN)


# Changing style mid-word is legal, so each pending character keeps
# the style it was printed in (§8.7.1.2).
def test_styles_may_change_mid_word() -> None:
    screen = small(version=5)

    screen.write("pa")
    screen.set_style(BOLD)
    screen.write("rser")

    assert_that(screen.cell(1, 2).style).is_equal_to(ROMAN)
    assert_that(screen.cell(1, 3).style).is_equal_to(BOLD)


# The line editor's rubout retreats the cursor one cell and blanks
# it, and stops at the left edge rather than chewing into an
# earlier row (§15 read).
def test_rub_out_erases_the_last_typed_character() -> None:
    screen = small(version=5)

    screen.write("ab")
    screen.rub_out()

    assert_that(screen.row_text(1)).is_equal_to("a")
    assert_that(screen.cursor).is_equal_to((1, 2))

    screen.rub_out()
    screen.rub_out()

    assert_that(screen.row_text(1)).is_equal_to("")
    assert_that(screen.cursor).is_equal_to((1, 1))


# Rubout follows the selected window: upper-window typing is edited
# in place, and at the window's left edge there is nothing to rub.
def test_rub_out_works_in_the_upper_window() -> None:
    screen = small(version=5)

    screen.split_window(2)
    screen.set_window(UPPER)
    screen.set_cursor(1, 3)
    screen.write("x")
    screen.rub_out()

    assert_that(screen.row_text(1)).is_equal_to("")
    assert_that(screen.cursor).is_equal_to((1, 3))

    screen.set_cursor(1, 1)
    screen.rub_out()

    assert_that(screen.cursor).is_equal_to((1, 1))


# A hung more callback fires after a screenful of lower-window
# lines -- the window's height less the prompt's own line -- and
# the count starts over after each pause (§8.8.3.2.6's courtesy,
# offered on the two-window screen).
def test_more_fires_at_a_screenful() -> None:
    screen = small(version=5)
    pauses: list[int] = []
    screen.more = lambda: pauses.append(1)

    screen.write("\n\n\n\n")

    assert_that(pauses).is_empty()

    screen.write("\n")

    assert_that(pauses).is_length(1)

    screen.write("\n\n\n\n\n")

    assert_that(pauses).is_length(2)


# Input rests the budget, and erasing the lower window refills it:
# read text and erased text alike cannot be unread.
def test_rest_and_erase_refill_the_more_budget() -> None:
    screen = small(version=5)
    pauses: list[int] = []
    screen.more = lambda: pauses.append(1)

    screen.write("\n\n\n\n")
    screen.rest()
    screen.write("\n\n\n\n")

    assert_that(pauses).is_empty()

    screen.erase_window(0)
    screen.write("\n\n\n\n")

    assert_that(pauses).is_empty()


# The upper window neither scrolls nor counts, and a split narrows
# the page to the lower window that remains.
def test_upper_window_feeds_no_more_budget() -> None:
    screen = small(version=5)
    pauses: list[int] = []
    screen.more = lambda: pauses.append(1)

    screen.split_window(2)
    screen.set_window(UPPER)
    screen.write("\n\n\n\n\n\n\n\n")

    assert_that(pauses).is_empty()

    screen.set_window(0)
    screen.write("\n\n\n")

    assert_that(pauses).is_length(1)


# The line editor's cursor motion retreats without erasing: the
# text stays painted, the motion clamps at the left edge, and the
# cells actually moved come back (§15 read).
def test_retreat_moves_the_cursor_without_erasing() -> None:
    screen = small(version=5)

    screen.write("ab")

    assert_that(screen.retreat(1)).is_equal_to(1)
    assert_that(screen.row_text(1)).is_equal_to("ab")
    assert_that(screen.cursor).is_equal_to((1, 2))
    assert_that(screen.retreat(5)).is_equal_to(1)
    assert_that(screen.cursor).is_equal_to((1, 1))


# Retreat follows the selected window, clamped at the upper
# window's left edge just the same.
def test_retreat_works_in_the_upper_window() -> None:
    screen = small(version=5)

    screen.split_window(2)
    screen.set_window(UPPER)
    screen.set_cursor(1, 3)

    assert_that(screen.retreat(9)).is_equal_to(2)
    assert_that(screen.cursor).is_equal_to((1, 1))


# A §15 rectangle in the upper window spreads right and down from
# the cursor: each row returns to the starting column, so a map can
# sit beside a story box without erasing its left edge -- which is
# precisely how Beyond Zork stamps its map (§15 print_table).
def test_upper_rectangles_keep_their_left_edge() -> None:
    screen = small(version=5)

    screen.split_window(4)
    screen.set_window(UPPER)
    screen.set_cursor(2, 5)
    screen.write_rectangle(["ab", "cd"])

    assert_that(screen.row_text(2)).is_equal_to("    ab")
    assert_that(screen.row_text(3)).is_equal_to("    cd")


# A rectangle taller than the upper window presses its last rows
# onto the bottom line, as upper-window newlines do (§8.7.2).
def test_tall_rectangles_press_on_the_window_bottom() -> None:
    screen = small(version=5)

    screen.split_window(2)
    screen.set_window(UPPER)
    screen.set_cursor(1, 1)
    screen.write_rectangle(["a", "b", "c"])

    assert_that(screen.row_text(1)).is_equal_to("a")
    assert_that(screen.row_text(2)).is_equal_to("c")


# In the lower window, where §15 leaves heights past 1 undefined,
# the rows are ordinary stacked lines.
def test_lower_rectangles_stack_as_lines() -> None:
    screen = small(version=5)

    screen.write_rectangle(["ab", "cd"])

    assert_that(screen.row_text(1)).is_equal_to("ab")
    assert_that(screen.row_text(2)).is_equal_to("cd")


# Cells remember the font they were printed in, and changing font
# mid-word is as legal as changing style there (§8.1.2, §8.1.3.1);
# drawing §16's shapes from that record is the painter's business.
def test_cells_wear_the_current_font() -> None:
    screen = small(version=5)

    screen.write("ma")
    screen.set_font(GRAPHICS_FONT)
    screen.write("p!")
    screen.set_font(NORMAL_FONT)
    screen.write("x")

    assert_that(screen.cell(1, 2).font).is_equal_to(NORMAL_FONT)
    assert_that(screen.cell(1, 3).font).is_equal_to(GRAPHICS_FONT)
    assert_that(screen.cell(1, 5).font).is_equal_to(NORMAL_FONT)


# Colour code 0 keeps the colour already current, on either side
# of the pair (§8.3.1).
def test_colour_zero_keeps_the_current_colour() -> None:
    screen = small(version=5)

    screen.set_colour(3, 6)
    screen.set_colour(0, 4)
    screen.set_colour(5, 0)
    screen.write("x")

    assert_that(screen.cell(1, 1).foreground).is_equal_to(5)
    assert_that(screen.cell(1, 1).background).is_equal_to(4)
    assert_that(screen.background).is_equal_to(4)


# The model reports its own dimensions, which the painter and the
# header both consult (§8.4).
def test_the_screen_knows_its_dimensions() -> None:
    screen = small()

    assert_that(screen.columns).is_equal_to(WIDTH)
    assert_that(screen.lines).is_equal_to(HEIGHT)


# Versions 1 and 2 are teletypes: their screens can only be printed
# to, and the window opcodes have nothing to talk to (§8.5.1).
def test_teletype_versions_refuse_windows() -> None:
    screen = small(version=1)

    with pytest.raises(ZMachineScreenError, match=r"§8\.5\.1"):
        screen.split_window(2)

    with pytest.raises(ZMachineScreenError, match=r"§8\.5\.1"):
        screen.set_window(UPPER)


# Selecting the upper window homes its cursor to the top left every
# time (§8.6.1, §8.7.2), and printing there overlays the screen
# without disturbing the lower window's cursor.
def test_selecting_the_upper_window_homes_its_cursor() -> None:
    screen = small(version=5)

    screen.split_window(2)
    screen.set_window(UPPER)
    screen.set_cursor(2, 5)
    screen.set_window(LOWER)
    screen.set_window(UPPER)
    screen.write("TOP")

    assert_that(screen.row_text(1)).is_equal_to("TOP")


# In Version 3 the upper window hangs below the interpreter's status
# line, so its first row is the screen's second (§8.6.1.1).
def test_the_version_3_upper_window_sits_below_the_status_line() -> None:
    screen = small(version=3)

    screen.split_window(1)
    screen.set_window(UPPER)
    screen.write("BELOW")

    assert_that(screen.row_text(1)).is_equal_to("")
    assert_that(screen.row_text(2)).is_equal_to("BELOW")


# A Version 3 split clears the freshly split upper window
# (§8.6.1.1.2); from Version 4 the screen's appearance is left
# alone (§8.6.1).
def test_version_3_splits_clear_and_version_5_splits_do_not() -> None:
    torn = small(version=3)
    torn.write("\n\nold text here\n\n\n")
    torn.split_window(2)

    assert_that(torn.row_text(2)).is_equal_to("")

    kept = small(version=5)
    kept.write("old text here")
    kept.split_window(2)

    assert_that(kept.row_text(1)).is_equal_to("old text here")


# A split that would swallow the lower window's cursor pushes it
# down to the line just below the new upper window (§8.7.2.2).
def test_a_split_cannot_swallow_the_lower_cursor() -> None:
    screen = small(version=5)

    screen.write("top line")
    screen.split_window(3)
    screen.write("pushed")

    assert_that(screen.row_text(4)).is_equal_to("pushed")


# A split made while the upper window is selected keeps its cursor
# when still inside the new size, homing it otherwise (§8.7.2.1.1).
def test_a_split_over_the_selected_upper_window_keeps_or_homes() -> None:
    screen = small(version=5)

    screen.split_window(3)
    screen.set_window(UPPER)
    screen.set_cursor(3, 4)
    screen.split_window(4)

    assert_that(screen.get_cursor()).is_equal_to((3, 4))

    screen.split_window(2)

    assert_that(screen.get_cursor()).is_equal_to((1, 1))


# The upper window may take the whole screen -- Z-Tornado plays
# its entire game that way -- but not more than exists, and never
# a negative height (§8.7.2.1).
def test_a_full_height_split_is_legal_and_larger_is_not() -> None:
    screen = small(version=5)

    screen.split_window(HEIGHT)
    screen.set_window(UPPER)
    screen.set_cursor(HEIGHT, 1)
    screen.write("floor")

    assert_that(screen.row_text(HEIGHT)).is_equal_to("floor")

    with pytest.raises(ZMachineScreenError, match=r"§8\.7\.2\.1"):
        screen.split_window(HEIGHT + 1)

    with pytest.raises(ZMachineScreenError, match=r"§8\.7\.2\.1"):
        screen.split_window(-1)


# Only windows 0 and 1 exist before Version 6 (§8.7.2).
def test_unknown_windows_cannot_be_selected() -> None:
    screen = small(version=5)

    with pytest.raises(ZMachineScreenError, match=r"§8\.7\.2"):
        screen.set_window(3)


# set_cursor speaks (row, column) with (1,1) at the window's top
# left, and moving outside the current upper size is illegal
# (§8.7.2.3.1).
def test_the_upper_cursor_moves_within_the_window_only() -> None:
    screen = small(version=5)

    screen.split_window(2)
    screen.set_window(UPPER)
    screen.set_cursor(2, 3)
    screen.write("X")

    assert_that(screen.row_text(2)).is_equal_to("  X")

    with pytest.raises(ZMachineScreenError, match=r"§8\.7\.2\.3\.1"):
        screen.set_cursor(3, 1)


# The opcode has no effect when the lower window is selected --
# the spec's own sentence, so the quiet is conforming (§8.7.2.3.1).
def test_set_cursor_in_the_lower_window_does_nothing() -> None:
    screen = small(version=5)

    screen.split_window(2)
    screen.set_cursor(2, 2)
    screen.write("stays put")

    assert_that(screen.row_text(3)).is_equal_to("stays put")


# get_cursor reports the upper window's cursor whichever window is
# selected (§8.7.2.3.2).
def test_get_cursor_speaks_for_the_upper_window() -> None:
    screen = small(version=5)

    screen.split_window(2)
    screen.set_window(UPPER)
    screen.set_cursor(2, 7)
    screen.set_window(LOWER)
    screen.write("elsewhere")

    assert_that(screen.get_cursor()).is_equal_to((2, 7))


# Printing on the bottom right of the upper window is legal, the
# cursor staying put as §8.7.3.1's author suggests; a newline at
# the window's bottom line has nowhere further to go.
def test_the_upper_window_never_scrolls() -> None:
    screen = small(version=5)

    screen.split_window(2)
    screen.set_window(UPPER)
    screen.set_cursor(2, WIDTH - 1)
    screen.write("abc\nz")

    assert_that(screen.row_text(2)[-2:]).is_equal_to("ac")
    assert_that(screen.row_text(2)[:1]).is_equal_to("z")


# Erasing window -1 unsplits the screen, clears the lot, selects
# the lower window, and homes its cursor by version: bottom left in
# Version 4, top left from Version 5 (§8.7.3.3).
def test_erase_minus_one_resets_the_screen() -> None:
    late = small(version=5)
    late.split_window(2)
    late.set_window(UPPER)
    late.write("gone")
    late.erase_window(-1)
    late.write("fresh")

    assert_that(late.split).is_equal_to(0)
    assert_that(late.selected).is_equal_to(LOWER)
    assert_that(late.row_text(1)).is_equal_to("fresh")

    middle = small(version=4)
    middle.erase_window(-1)
    middle.write("low")

    assert_that(middle.row_text(HEIGHT)).is_equal_to("low")


# Erasing window -2 clears the screen but keeps the split and the
# cursors exactly as they were (§15 erase_window).
def test_erase_minus_two_keeps_the_split() -> None:
    screen = small(version=5)

    screen.split_window(2)
    screen.write("about to vanish")
    screen.erase_window(-2)

    assert_that(screen.split).is_equal_to(2)
    assert_that(screen.rendered().strip()).is_equal_to("")


# Erasing a single window blanks only its own rows; from Version 5
# the erased window's cursor homes to its top left (§8.7.3.2.1).
def test_erasing_one_window_spares_the_other() -> None:
    screen = small(version=5)

    screen.split_window(1)
    screen.set_window(UPPER)
    screen.write("KEPT")
    screen.set_window(LOWER)
    screen.write("dust")
    screen.erase_window(LOWER)
    screen.write("swept")

    assert_that(screen.row_text(1)).is_equal_to("KEPT")
    assert_that(screen.row_text(2)).is_equal_to("swept")

    screen.erase_window(UPPER)

    assert_that(screen.row_text(1)).is_equal_to("")
    assert_that(screen.row_text(2)).is_equal_to("swept")


# In Version 4 erasing the lower window homes its cursor to the
# bottom left, where its cursor always lives (§8.7.3.2.1).
def test_version_4_lower_erasure_homes_to_the_bottom() -> None:
    screen = small(version=4)

    screen.write("one\ntwo")
    screen.erase_window(LOWER)
    screen.write("floor")

    assert_that(screen.row_text(HEIGHT)).is_equal_to("floor")


# Only real windows can be erased (§15 erase_window).
def test_unknown_windows_cannot_be_erased() -> None:
    screen = small(version=5)

    with pytest.raises(ZMachineScreenError, match="erase_window"):
        screen.erase_window(9)


# erase_line clears from the cursor to the right edge in the
# selected window (§8.7.3.4).
def test_erase_line_clears_to_the_right_edge() -> None:
    screen = small(version=5)

    screen.split_window(1)
    screen.set_window(UPPER)
    screen.write("wiped almost all")
    screen.set_cursor(1, 6)
    screen.erase_line()

    assert_that(screen.row_text(1)).is_equal_to("wiped")

    screen.set_window(LOWER)
    screen.write("keep tail")
    screen.erase_line()

    assert_that(screen.row_text(2)).is_equal_to("keep tail")


# Erased blanks wear the current background without reverse video,
# even while the text style is Reverse (§8.7.3.2).
def test_erasure_is_never_reversed() -> None:
    screen = small(version=5)

    screen.set_style(REVERSE)
    screen.set_colour(2, 4)
    screen.write("vivid")
    screen.erase_window(LOWER)

    blank = screen.cell(1, 1)

    assert_that(blank.style).is_equal_to(ROMAN)
    assert_that(blank.background).is_equal_to(4)


# The Version 3 status line: location on the left, score and turns
# on the right, the whole row in reverse video (§8.2).
def test_the_status_line_shows_score_and_moves() -> None:
    screen = ScreenModel(columns=40, lines=HEIGHT, version=3)

    screen.show_status(Status("West of House", 35, 110, time_game=False))

    assert_that(screen.row_text(1)).contains("West of House")
    assert_that(screen.row_text(1)).contains("Score: 35  Moves: 110")
    assert_that(screen.cell(1, 2).style).is_equal_to(REVERSE)


# A time game's status line shows an hours:minutes clock instead
# (§8.2.3.2).
def test_the_status_line_tells_the_time() -> None:
    screen = ScreenModel(columns=40, lines=HEIGHT, version=3)

    screen.show_status(Status("Bedroom", 2, 7, time_game=True))

    assert_that(screen.row_text(1)).contains("Time: 2:07")


# A location too long for its room breaks with an ellipsis, as
# §8.2.2.2's author suggests.
def test_a_long_location_gains_an_ellipsis() -> None:
    screen = small(version=3)

    screen.show_status(Status("The Halls of the Dead King", 0, 0, False))

    assert_that(screen.row_text(1)).contains("...")


# From Version 4 the game paints its own status area and the
# interpreter's line is over (§8.2).
def test_later_versions_have_no_interpreter_status_line() -> None:
    screen = small(version=4)

    with pytest.raises(ZMachineScreenError, match=r"§8\.2"):
        screen.show_status(Status("Anywhere", 0, 0, False))


# The cursor property speaks screen coordinates for whichever
# window is selected.
def test_the_cursor_property_follows_the_selection() -> None:
    screen = small(version=5)

    screen.split_window(2)
    screen.set_window(UPPER)
    screen.set_cursor(2, 4)

    assert_that(screen.cursor).is_equal_to((2, 4))

    screen.set_window(LOWER)
    screen.write("abc")

    assert_that(screen.cursor).is_equal_to((3, 4))


# Inspection flushes pending buffered text, so the grid always
# shows what a player would see.
def test_inspection_flushes_the_pending_word() -> None:
    screen = small(version=5)

    screen.write("half")

    assert_that(screen.row_text(1)).is_equal_to("half")


# A golden grid: a miniature licence-form screen assembled from
# splits, cursor moves, and overlays -- the certification style the
# Bureaucracy recording taught us to want.
def test_a_form_renders_as_a_golden_grid() -> None:
    screen = ScreenModel(columns=24, lines=8, version=4)

    screen.split_window(4)
    screen.set_window(UPPER)
    screen.set_cursor(
        1,
        5,
    )
    screen.write("LICENCE FORM")
    screen.set_cursor(3, 1)
    screen.write("Name:")
    screen.set_cursor(3, 7)
    screen.write("NYMAN")
    screen.set_window(LOWER)
    screen.write("Thank you, Ms Nyman.")

    expected = "\n".join(
        [
            "    LICENCE FORM",
            "",
            "Name: NYMAN",
            "",
            "",
            "",
            "",
            "Thank you, Ms Nyman.",
        ]
    )

    assert_that(screen.rendered()).is_equal_to(expected)
