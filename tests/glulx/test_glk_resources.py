"""Glk's view of the Blorb: pictures measured, sounds reframed."""

from assertpy import assert_that

from voxam.blorb import Blorb
from voxam.glulx.glk.resources import ImageInfo, Resources, image_size
from voxam.iff import chunk

RIDX_ENTRY = 12
FORM_PRELUDE = 12


def blorb(*entries: tuple[bytes, int, bytes, bytes]) -> Blorb:
    """Assemble a parsed Blorb from (usage, number, id, payload) rows."""
    index = len(entries).to_bytes(4, "big")
    body = b""
    ridx = chunk(b"RIdx", index + b"\x00" * RIDX_ENTRY * len(entries))
    offset = FORM_PRELUDE + len(ridx)

    for usage, number, chunk_id, payload in entries:
        index += usage + number.to_bytes(4, "big") + offset.to_bytes(4, "big")
        framed = chunk(chunk_id, payload)
        body += framed
        offset += len(framed)

    return Blorb.parse(chunk(b"FORM", b"IFRS" + chunk(b"RIdx", index) + body))


def png(width: int, height: int) -> bytes:
    return (
        b"\x89PNG\r\n\x1a\n"
        + (13).to_bytes(4, "big")
        + b"IHDR"
        + width.to_bytes(4, "big")
        + height.to_bytes(4, "big")
    )


def jpeg(width: int, height: int) -> bytes:
    return (
        b"\xff\xd8"  # start of image
        + b"\xff\x01"  # a standalone marker, walked over
        + b"\xff\xe0\x00\x04\x00\x00"  # an APP0 segment, walked over
        + b"\xff\xc0\x00\x08\x08"  # SOF0, length, precision
        + height.to_bytes(2, "big")
        + width.to_bytes(2, "big")
    )


# PNG puts its dimensions at fixed offsets behind the required
# IHDR; JPEG hides them in a start-of-frame segment behind
# whatever markers come first.
def test_dimensions_are_read_from_the_bytes() -> None:
    assert_that(image_size(png(320, 200))).is_equal_to((320, 200))
    assert_that(image_size(jpeg(640, 400))).is_equal_to((640, 400))


# Damaged or foreign bytes answer None rather than a wrong size: a
# PNG cut before its header, a JPEG that loses marker alignment,
# one that ends mid-frame-header, one with no frame at all, and
# something that is no image whatsoever.
def test_unmeasurable_bytes_answer_none() -> None:
    assert_that(image_size(b"\x89PNG\r\n\x1a\nIH")).is_none()
    assert_that(image_size(b"\xff\xd8\x00\x00\x00\x00")).is_none()
    assert_that(image_size(b"\xff\xd8\xff\xc0\x00\x08\x08")).is_none()
    assert_that(image_size(b"\xff\xd8\xff\xe0\x00\x04\x00\x00")).is_none()
    assert_that(image_size(b"GIF89a")).is_none()


# With no Blorb behind it, everything answers "nothing here" --
# the right answer for a bare .ulx story.
def test_no_blorb_answers_nothing() -> None:
    bare = Resources()

    assert_that(bare.image(1)).is_none()
    assert_that(bare.sound(1)).is_none()
    assert_that(bare.data(1)).is_none()
    assert_that(bare.frontispiece()).is_none()


# The Fspc chunk names the cover outright; a Blorb full of
# pictures but no Fspc offers nothing rather than a guess (Blorb:
# Frontispiece Chunk).
def test_the_frontispiece_answers_only_when_named() -> None:
    unnamed = Resources(blorb((b"Pict", 1, b"PNG ", png(32, 16))))

    assert_that(unnamed.frontispiece()).is_none()


# A picture is measured on first use and remembered after -- the
# unmeasurable and the absent are remembered as None the same way.
def test_pictures_are_measured_once() -> None:
    held = Resources(
        blorb(
            (b"Pict", 1, b"PNG ", png(32, 16)),
            (b"Pict", 2, b"Rect", b"\x00" * 8),
        )
    )

    assert_that(held.image(1)).is_equal_to(ImageInfo(1, b"PNG ", png(32, 16), 32, 16))
    assert_that(held.image(1)).is_same_as(held.image(1))
    assert_that(held.image(2)).is_none()
    assert_that(held.image(9)).is_none()


# An AIFF sound is stored as a FORM, and an AIFF file *is* that
# FORM -- so the answer is the chunk reframed, header included.
def test_sounds_come_back_reframed() -> None:
    held = Resources(
        blorb(
            (b"Snd ", 3, b"FORM", b"AIFFdata"),
            (b"Snd ", 4, b"OGGV", b"oggbytes"),
        )
    )

    assert_that(held.sound(3)).is_equal_to(
        b"FORM" + (8).to_bytes(4, "big") + b"AIFFdata"
    )
    assert_that(held.sound(4)).is_equal_to(b"oggbytes")
    assert_that(held.sound(9)).is_none()


# A data chunk is TEXT or BINA payload -- or a whole nested FORM,
# which keeps its header and is never text (Blorb: Data Resource
# Chunks).
def test_data_chunks_tell_text_from_binary() -> None:
    held = Resources(
        blorb(
            (b"Data", 1, b"TEXT", b"hello"),
            (b"Data", 2, b"BINA", b"\x00\x01"),
            (b"Data", 3, b"FORM", b"IFZSdata"),
        )
    )

    assert_that(held.data(1)).is_equal_to((b"hello", True))
    assert_that(held.data(2)).is_equal_to((b"\x00\x01", False))
    assert_that(held.data(3)).is_equal_to(
        (b"FORM" + (8).to_bytes(4, "big") + b"IFZSdata", False)
    )
    assert_that(held.data(9)).is_none()
