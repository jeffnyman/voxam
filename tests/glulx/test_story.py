"""Glulx story loading: every header promise held (Glulx: The Header)."""

from pathlib import Path

import pytest
from assertpy import assert_that

from voxam.errors import GlulxStoryError
from voxam.glulx.story import CHECKSUM_AT, Story


def built(
    version: int = 0x00030102,
    ramstart: int = 0x100,
    extstart: int = 0x200,
    endmem: int = 0x300,
    stack: int = 0x100,
    checksum: int | None = None,
    magic: bytes = b"Glul",
    size: int | None = None,
) -> bytes:
    """A tiny Glulx image; None computes the true checksum."""

    data = bytearray(size if size is not None else extstart)
    data[0:4] = magic
    data[4:8] = version.to_bytes(4, "big")
    data[8:12] = ramstart.to_bytes(4, "big")
    data[12:16] = extstart.to_bytes(4, "big")
    data[16:20] = endmem.to_bytes(4, "big")
    data[20:24] = stack.to_bytes(4, "big")
    data[24:28] = (0x48).to_bytes(4, "big")
    data[28:32] = (0x54).to_bytes(4, "big")

    if checksum is None:
        checksum = sum(
            int.from_bytes(data[at : at + 4], "big")
            for at in range(0, len(data), 4)
            if at != CHECKSUM_AT
        ) % (1 << 32)

    data[CHECKSUM_AT : CHECKSUM_AT + 4] = checksum.to_bytes(4, "big")

    return bytes(data)


# The nine header words answer as themselves, the version dotted,
# and the checksum -- summed over the whole initial image with its
# own field zeroed -- agrees with the stored word.
def test_the_header_answers_and_the_checksum_verifies(tmp_path: Path) -> None:
    path = tmp_path / "tiny.ulx"
    path.write_bytes(built())
    story = Story.load(path)

    assert_that(story.version).is_equal_to("3.1.2")
    assert_that(story.ramstart).is_equal_to(0x100)
    assert_that(story.extstart).is_equal_to(0x200)
    assert_that(story.endmem).is_equal_to(0x300)
    assert_that(story.stack_size).is_equal_to(0x100)
    assert_that(story.start_function).is_equal_to(0x48)
    assert_that(story.decoding_table).is_equal_to(0x54)
    assert_that(story.verify()).is_true()

    doctored = Story(built(checksum=7))

    assert_that(doctored.stored_checksum).is_equal_to(7)
    assert_that(doctored.verify()).is_false()


# The acceptance window is 2.0.0 through 3.1.*: minor versions are
# backwards compatible, subminor versions do not matter, and 2.0
# lacks only Unicode.
def test_the_version_window_is_2_0_0_through_3_1_star() -> None:
    assert_that(Story(built(version=0x00020000)).version).is_equal_to("2.0.0")
    assert_that(Story(built(version=0x000301FF)).version).is_equal_to("3.1.255")

    for outside in (0x0001FFFF, 0x00030200, 0x00040000):
        with pytest.raises(GlulxStoryError, match=r"2\.0\.0"):
            Story(built(version=outside))


# Every way a file can lie about itself halts loudly: too short for
# a header, the wrong magic, a boundary off its 256-byte seat, a
# map out of order, and a length that is not the declared EXTSTART.
def test_broken_header_promises_halt_loudly() -> None:
    with pytest.raises(GlulxStoryError, match="36-byte header"):
        Story(built()[:20])

    with pytest.raises(GlulxStoryError, match="magic number"):
        Story(built(magic=b"Blul"))

    with pytest.raises(GlulxStoryError, match="multiple of 256"):
        Story(built(ramstart=0x120))

    with pytest.raises(GlulxStoryError, match="out of order"):
        Story(built(ramstart=0x300, endmem=0x200))

    with pytest.raises(GlulxStoryError, match="declares EXTSTART"):
        Story(built(size=0x300))
