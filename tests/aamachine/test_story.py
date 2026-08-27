"""The Å-machine story file: the AAVM form read and refused."""

import zlib

import pytest
from assertpy import assert_that

from voxam.aamachine.story import SUMMED, Story
from voxam.errors import AAMachineError
from voxam.iff import chunk

# A minimal LANG: four offsets, the extended table at byte 8
# holding one character -- an Å, lowercase å beside it.
LANG = (
    b"\x00\x00"
    + (8).to_bytes(2, "big")
    + b"\x00\x00"
    + b"\x00\x00"
    + bytes([1, 0xE5, 0xC5])
    + (0xC5).to_bytes(3, "big")
)

# A META naming a title and an author whose Å is byte $80 -- the
# extended table's first seat -- with an unknown identifier to
# pass over.
META = bytes([3]) + b"\x01Cloak\x00" + b"\x02\x80kesson\x00" + b"\x63x\x00"

IFID = b"UUID://a5aa4f02-8f50-4649-a4bd-b1b5c5408b67//\x00"


def headed(
    *,
    version: tuple[int, int] = (0, 5),
    wordsz: int = 2,
    crc: int | None = None,
    ifid: bytes = b"",
) -> bytes:
    """A HEAD payload; None for the crc means compute it right."""

    if crc is None:
        running = 0

        for name in SUMMED:
            running = zlib.crc32(LANG if name == b"LANG" else b"", running)

        crc = running

    return (
        bytes([version[0], version[1], wordsz, 1])
        + (7).to_bytes(2, "big")
        + b"260827"
        + crc.to_bytes(4, "big")
        + (16).to_bytes(2, "big")
        + (8).to_bytes(2, "big")
        + (32).to_bytes(2, "big")
        + ifid
    )


def storied(
    head: bytes | None = None,
    *,
    meta: bytes | None = META,
    drop: bytes | None = None,
    lead: bytes = b"HEAD",
) -> bytes:
    """One assembled .aastory, tweakable toward every refusal."""

    pieces = [chunk(lead, head if head is not None else headed())]

    if meta is not None:
        pieces.append(chunk(b"META", meta))

    for name in SUMMED:
        if name == drop:
            continue

        pieces.append(chunk(name, LANG if name == b"LANG" else b""))

    pieces.append(chunk(b"FILE", b"one"))
    pieces.append(chunk(b"FILE", b"two"))

    return chunk(b"FORM", b"AAVM" + b"".join(pieces))


# The header's claims land whole: the version pair, the sizes,
# the serial, the verified checksum -- and the story's own
# character table spells the author's Å, byte $80 through LANG.
def test_stories_read_their_headers_whole() -> None:
    story = Story(storied())

    assert_that(story.version).is_equal_to((0, 5))
    assert_that(story.word_size).is_equal_to(2)
    assert_that(story.shift).is_equal_to(1)
    assert_that(story.release).is_equal_to(7)
    assert_that(story.serial).is_equal_to("260827")
    assert_that((story.heap_size, story.aux_size, story.ram_size)).is_equal_to(
        (16, 8, 32)
    )
    assert_that(story.ifid).is_none()
    assert_that(story.extended).is_equal_to(("Å",))
    assert_that(story.meta).is_equal_to({"title": "Cloak", "author": "Åkesson"})
    assert_that(len(story.files)).is_equal_to(2)
    assert_that(story.chunk(b"WRIT")).is_not_none()
    assert_that(story.chunk(b"URLS")).is_none()


# The optional IFID unwraps from its UUID dressing, uppercased as
# the treaty spells identities; a bare story answers None, and a
# field dressed wrong is refused by its own text.
def test_the_ifid_unwraps_or_refuses() -> None:
    branded = Story(storied(headed(ifid=IFID)))

    assert_that(branded.ifid).is_equal_to("A5AA4F02-8F50-4649-A4BD-B1B5C5408B67")

    with pytest.raises(AAMachineError, match="not UUID"):
        Story(storied(headed(ifid=b"GUID://nope//\x00")))


# Every door refusal speaks its reason: the wrong form, a HEAD
# missing or short, a future major version, an unspoken word
# size, a summed chunk missing, and a checksum that disagrees.
def test_the_door_refusals_speak() -> None:
    with pytest.raises(AAMachineError, match="FORM AAVM"):
        Story(chunk(b"FORM", b"IFRS" + chunk(b"HEAD", headed())))

    with pytest.raises(AAMachineError, match="first chunk"):
        Story(storied(lead=b"HEAP"))

    with pytest.raises(AAMachineError, match="fixed header"):
        Story(storied(headed()[:12]))

    with pytest.raises(AAMachineError, match="future"):
        Story(storied(headed(version=(2, 0))))

    with pytest.raises(AAMachineError, match=r"only.*size"):
        Story(storied(headed(wordsz=4)))

    with pytest.raises(AAMachineError, match="WRIT chunk is missing"):
        Story(storied(drop=b"WRIT"))

    with pytest.raises(AAMachineError, match="header claims"):
        Story(storied(headed(crc=0xDEADBEEF)))


# The META chunk's own refusals: a count past the bytes, a string
# missing its null -- and a story without META answers an empty
# bibliography rather than a missing one.
def test_meta_refusals_and_absence() -> None:
    bare = Story(storied(meta=None))

    assert_that(bare.meta).is_equal_to({})

    hollow = Story(storied(meta=b""))

    assert_that(hollow.meta).is_equal_to({})

    with pytest.raises(AAMachineError, match="mid-entry"):
        Story(storied(meta=bytes([2]) + b"\x01Cloak\x00"))

    with pytest.raises(AAMachineError, match="null ending"):
        Story(storied(meta=bytes([1]) + b"\x01Cloak"))

    with pytest.raises(AAMachineError, match="past the"):
        Story(storied(meta=bytes([1]) + b"\x01\x81x\x00"))


# The LANG chunk's own refusals: too short for its offsets, an
# extended table past the end, and a table that ends mid-entry.
def test_lang_refusals() -> None:
    def worded(lang: bytes) -> bytes:
        pieces = [chunk(b"HEAD", headed(crc=_summed_with(lang)))]

        for name in SUMMED:
            pieces.append(chunk(name, lang if name == b"LANG" else b""))

        return chunk(b"FORM", b"AAVM" + b"".join(pieces))

    def _summed_with(lang: bytes) -> int:
        running = 0

        for name in SUMMED:
            running = zlib.crc32(lang if name == b"LANG" else b"", running)

        return running

    with pytest.raises(AAMachineError, match="own offsets"):
        Story(worded(b"\x00\x00"))

    with pytest.raises(AAMachineError, match="past the chunk"):
        Story(worded(b"\x00\x00" + (99).to_bytes(2, "big") + b"\x00\x00\x00\x00"))

    with pytest.raises(AAMachineError, match="mid-entry"):
        Story(
            worded(b"\x00\x00" + (8).to_bytes(2, "big") + b"\x00\x00\x00\x00\x02\xe5")
        )
