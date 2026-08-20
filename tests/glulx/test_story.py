"""Glulx story loading: every header promise held (Glulx: The Header)."""

from collections.abc import Callable
from pathlib import Path

import pytest
from assertpy import assert_that

from voxam.errors import GlulxStoryError
from voxam.glulx.story import Story


# The nine header words answer as themselves, the version dotted,
# and the checksum -- summed over the whole initial image with its
# own field zeroed -- agrees with the stored word.
def test_the_header_answers_and_the_checksum_verifies(
    image: Callable[..., bytes], tmp_path: Path
) -> None:
    path = tmp_path / "tiny.ulx"
    path.write_bytes(image())
    story = Story.load(path)

    assert_that(story.version).is_equal_to("3.1.2")
    assert_that(story.ramstart).is_equal_to(0x100)
    assert_that(story.extstart).is_equal_to(0x200)
    assert_that(story.endmem).is_equal_to(0x300)
    assert_that(story.stack_size).is_equal_to(0x100)
    assert_that(story.start_function).is_equal_to(0x48)
    assert_that(story.decoding_table).is_equal_to(0x54)
    assert_that(story.verify()).is_true()

    doctored = Story(image(checksum=7))

    assert_that(doctored.stored_checksum).is_equal_to(7)
    assert_that(doctored.verify()).is_false()


# The acceptance window is 2.0.0 through 3.1.*: minor versions are
# backwards compatible, subminor versions do not matter, and 2.0
# lacks only Unicode.
def test_the_version_window_is_2_0_0_through_3_1_star(
    image: Callable[..., bytes],
) -> None:
    assert_that(Story(image(version=0x00020000)).version).is_equal_to("2.0.0")
    assert_that(Story(image(version=0x000301FF)).version).is_equal_to("3.1.255")

    for outside in (0x0001FFFF, 0x00030200, 0x00040000):
        with pytest.raises(GlulxStoryError, match=r"2\.0\.0"):
            Story(image(version=outside))


# Every way a file can lie about itself halts loudly: too short for
# a header, the wrong magic, a boundary off its 256-byte seat, a
# map out of order, and a length that is not the declared EXTSTART.
def test_broken_header_promises_halt_loudly(image: Callable[..., bytes]) -> None:
    with pytest.raises(GlulxStoryError, match="36-byte header"):
        Story(image()[:20])

    with pytest.raises(GlulxStoryError, match="magic number"):
        Story(image(magic=b"Blul"))

    with pytest.raises(GlulxStoryError, match="multiple of 256"):
        Story(image(ramstart=0x120))

    with pytest.raises(GlulxStoryError, match="out of order"):
        Story(image(ramstart=0x300, endmem=0x200))

    with pytest.raises(GlulxStoryError, match="declares EXTSTART"):
        Story(image(size=0x300))
