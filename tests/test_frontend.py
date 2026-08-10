import pytest
from assertpy import assert_that

from voxam.frontend import PlainFrontend, Status


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
