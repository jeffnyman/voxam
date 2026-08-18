import pytest
from assertpy import assert_that

from voxam.frontend import COURIER_FONT, PlainFrontend, Status


# With no stream given, story text lands on standard output: the
# interactive default.
def test_plain_frontend_defaults_to_standard_output(
    capsys: pytest.CaptureFixture[str],
) -> None:
    PlainFrontend().write("hello")

    assert_that(capsys.readouterr().out).is_equal_to("hello")


def test_plain_frontend_passes_text_through() -> None:
    pieces: list[str] = []

    PlainFrontend(pieces.append).write("west of house")

    assert_that(pieces).is_equal_to(["west of house"])


# A plain stream has no line to keep a status on, and it says so:
# dropping the status is the conforming behaviour of an interpreter
# that declared no status line (§8.2, §11.1).
def test_plain_frontend_declares_nothing_and_drops_the_status() -> None:
    pieces: list[str] = []
    frontend = PlainFrontend(pieces.append)

    frontend.show_status(Status("Kitchen", score=10, turns=20, time_game=False))

    assert_that(pieces).is_empty()
    assert_that(frontend.has_status_line).is_false()
    assert_that(frontend.has_screen_splitting).is_false()


# A stream has no styles (none were claimed, which §8.7 permits)
# and nothing to erase: both screen operations drop without
# disturbing the text.
def test_plain_frontend_drops_screen_operations() -> None:
    pieces: list[str] = []
    frontend = PlainFrontend(pieces.append)

    frontend.set_style(2)
    frontend.erase_window(-1)
    frontend.erase_line()
    frontend.erase_line(29)
    frontend.begin_input()
    frontend.resume_input()
    frontend.set_buffering(buffered=False)
    frontend.split_window(3)
    frontend.set_cursor(1, 1)
    frontend.bleep(1)
    frontend.draw_picture(1, 1, 1)
    frontend.erase_picture(1, 1, 1)
    frontend.place_window(1, 1, 1, 1, 1)
    frontend.write("after")

    assert_that(pieces).is_equal_to(["after"])
    assert_that(frontend.has_stage).is_false()
    assert_that(frontend.has_pictures).is_false()
    assert_that(frontend.picture_data(1)).is_none()
    assert_that(frontend.picture_census()).is_equal_to((0, 0))


# The routing rule that keeps Version 4 transcripts clean: a one- or
# two-line upper window is a game's self-drawn status chrome, and
# the stream shows the story alone (§8.7.2).
def test_status_bar_chrome_is_dropped() -> None:
    pieces: list[str] = []
    frontend = PlainFrontend(pieces.append)

    frontend.write("story ")
    frontend.split_window(1)
    frontend.set_window(1)
    frontend.set_cursor(1, 30)
    frontend.write("STATUS CHROME")
    frontend.set_window(0)
    frontend.write("continues")

    assert_that(pieces).is_equal_to(["story ", "continues"])


# A tall split is content, not chrome -- Trinity's fourteen-line
# title card -- and the cursor moves reconstruct its layout: a row
# change becomes a new-line, a column becomes padding, so centered
# stays centered.
def test_tall_upper_windows_render_with_their_layout() -> None:
    pieces: list[str] = []
    frontend = PlainFrontend(pieces.append)

    frontend.split_window(14)
    frontend.set_window(1)
    frontend.set_cursor(10, 25)
    frontend.write("T R I N I T Y")
    frontend.set_cursor(12, 29)
    frontend.write("An Interactive Fantasy")
    frontend.set_window(0)
    frontend.write("You step out of the white door.")

    assert_that("".join(pieces)).is_equal_to(
        "\n"
        + " " * 24
        + "T R I N I T Y\n"
        + " " * 28
        + "An Interactive Fantasy\n"
        + "You step out of the white door."
    )


# Cursor moves along one row pad only forward; the pen never backs
# up in a stream.
def test_content_cursor_pads_within_a_row() -> None:
    pieces: list[str] = []
    frontend = PlainFrontend(pieces.append)

    frontend.split_window(5)
    frontend.set_window(1)
    frontend.set_cursor(1, 5)
    frontend.write("abc")
    frontend.set_cursor(1, 10)
    frontend.write("z")
    frontend.set_cursor(1, 3)
    frontend.write("!")

    assert_that("".join(pieces)).is_equal_to("    abc  z!")


# Erasing window -1 unsplits AND reselects the lower window (§8.7):
# without honouring that side effect, a game that clears its way out
# of the upper window would mute the stream forever. It also ends
# the split, so a later status bar is chrome again.
def test_unsplitting_erasure_reselects_the_lower_window() -> None:
    pieces: list[str] = []
    frontend = PlainFrontend(pieces.append)

    frontend.set_window(1)
    frontend.write("chrome")
    frontend.erase_window(-2)
    frontend.write("still chrome")
    frontend.erase_window(-1)
    frontend.write("story again")
    frontend.split_window(14)
    frontend.erase_window(-1)
    frontend.set_window(1)
    frontend.write("chrome once more")
    frontend.set_window(0)

    assert_that(pieces).is_equal_to(["story again"])


# The plain frontend's whole self-portrait, as stamped into Version
# 4+ headers: no typography beyond a stream's inherent fixed pitch,
# 80 characters wide, infinitely tall since it never pages, and
# timed input honestly claimed now that the machine fires read
# interrupts on the patient typist's virtual clock (§8.4, §11.1,
# §15 read).
def test_plain_frontend_claims_a_bare_infinite_stream() -> None:
    frontend = PlainFrontend()

    assert_that(frontend.has_bold).is_false()
    assert_that(frontend.has_italic).is_false()
    assert_that(frontend.has_fixed_pitch).is_true()
    assert_that(frontend.has_timed_input).is_true()
    assert_that(frontend.has_sounds).is_false()
    assert_that(frontend.has_character_graphics).is_false()
    assert_that(frontend.has_colours).is_false()
    assert_that(frontend.screen_lines).is_equal_to(255)
    assert_that(frontend.screen_columns).is_equal_to(80)


# Only granted fonts arrive at a frontend, and on a plain stream
# the two on offer -- normal and fixed-pitch -- are both the one
# stream it already is, so the change drops silently (§8.1).
def test_plain_frontend_drops_font_changes() -> None:
    pieces: list[str] = []
    frontend = PlainFrontend(pieces.append)

    frontend.set_font(COURIER_FONT)
    frontend.write("unchanged")

    assert_that(pieces).is_equal_to(["unchanged"])


# A §15 rectangle becomes stacked lines on a stream, which has no
# cursor column to return to.
def test_plain_rectangles_stack_as_lines() -> None:
    pieces: list[str] = []
    frontend = PlainFrontend(pieces.append)

    frontend.write_rectangle(["ab", "cd"])

    assert_that(pieces).is_equal_to(["ab", "\n", "cd"])


# The plain frontend claims no sound and stays inert when the seam
# is poked anyway -- the silence every recording replays in (§9).
def test_the_plain_sound_seam_is_inert() -> None:
    pieces: list[str] = []
    frontend = PlainFrontend(pieces.append)

    frontend.play_sound(3, 8, 1)
    frontend.stop_sound(None)
    frontend.wait_for_sound()

    assert_that(frontend.sound_playing()).is_false()
    assert_that(frontend.sound_finished()).is_false()
    assert_that(pieces).is_empty()


# A stream's get_cursor reads the same upper-window ledger its
# set_cursor writes (§8.7.2.3.2).
def test_the_plain_cursor_ledger_reads_back() -> None:
    frontend = PlainFrontend(lambda _text: None)

    assert_that(frontend.cursor_position()).is_equal_to((1, 1))

    frontend.split_window(3)
    frontend.set_window(1)
    frontend.set_cursor(2, 5)

    assert_that(frontend.cursor_position()).is_equal_to((2, 5))
