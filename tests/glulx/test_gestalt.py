"""Gestalt: every capability answered honestly (Glulx: Gestalt)."""

from collections.abc import Callable
from importlib.metadata import version

from assertpy import assert_that

from voxam.glulx.gestalt import terp_version
from voxam.glulx.machine import Machine
from voxam.glulx.story import Story

PLANT = 0x180
RESULT = 0x140

IDLE = bytes([0xC0, 0x00, 0x00, 0x81, 0x20])
TO_RESULT = bytes([0x00, 0x00, 0x01, 0x40])


def asked(image: Callable[..., bytes], selector: int, argument: int = 0) -> int:
    machine = Machine(Story(image(code=IDLE)))

    machine.memory.write_run(
        PLANT,
        bytes([0x81, 0x00, 0x11, 0x07, selector, argument]) + TO_RESULT,
    )

    machine.pc = PLANT

    machine.step()

    return machine.memory.read_word(RESULT)


# The interpreter's own version packs from the installed package, so
# the gestalt answer can never drift from pyproject.
def test_the_terp_version_packs_from_the_package() -> None:
    major, minor, patch = (int(part) for part in version("voxam").split("."))

    assert_that(terp_version()).is_equal_to((major << 16) | (minor << 8) | patch)


# Every selector answers for this build: the spec version, the
# eras already carried at 1, the eras still to come at 0, and the
# io systems that exist -- with Glk honestly not among them yet.
# Unknown selectors answer zero, which is how future programs
# probe old interpreters.
def test_every_selector_answers_for_this_build(
    image: Callable[..., bytes],
) -> None:
    answers = {
        0: 0x00030103,
        1: terp_version(),
        2: 1,
        3: 1,
        5: 1,
        6: 1,
        7: 0,
        8: 0,
        9: 0,
        10: 0,
        11: 0,
        12: 1,
        13: 0,
        99: 0,
    }

    for selector, expected in answers.items():
        assert_that(asked(image, selector)).is_equal_to(expected)

    assert_that(asked(image, 4, 0)).is_equal_to(1)
    assert_that(asked(image, 4, 1)).is_equal_to(1)
    assert_that(asked(image, 4, 2)).is_equal_to(0)
    assert_that(asked(image, 4, 9)).is_equal_to(0)
