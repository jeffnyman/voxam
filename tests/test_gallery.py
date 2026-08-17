import struct
import zlib
from fractions import Fraction
from typing import cast

import pytest
from assertpy import assert_that

from voxam.errors import PNGError
from voxam.gallery import Gallery, Placard, Resolution, Scaling
from voxam.png import SIGNATURE, Picture


def indexed(
    colours: tuple[tuple[int, int, int], ...],
    alphas: bytes = b"",
    raw: bytes = b"\x00\x00\x01",
) -> bytes:
    """A 2-by-1 indexed-colour PNG in the APal style."""

    def piece(name: bytes, payload: bytes) -> bytes:
        return (
            len(payload).to_bytes(4, "big")
            + name
            + payload
            + zlib.crc32(name + payload).to_bytes(4, "big")
        )

    pieces = [
        SIGNATURE,
        piece(b"IHDR", struct.pack(">IIBBBBB", 2, 1, 8, 3, 0, 0, 0)),
        piece(b"PLTE", b"".join(bytes(colour) for colour in colours)),
    ]

    if alphas:
        pieces.append(piece(b"tRNS", alphas))

    pieces.append(piece(b"IDAT", zlib.compress(raw)))
    pieces.append(piece(b"IEND", b""))

    return b"".join(pieces)


def hung(png: bytes) -> Gallery:
    art: dict[int, bytes | Placard] = {
        3: png,
        7: Placard(width=314, height=84),
    }

    return Gallery(art, 27)


# Sizes answer without decoding a pixel: the PNG's own IHDR words
# and a placard's stored shape, height first as picture_data wants
# them (§15 picture_data).
def test_sizes_answer_height_first(tiny_png: bytes) -> None:
    gallery = hung(tiny_png)

    assert_that(gallery.size(3)).is_equal_to((2, 2))
    assert_that(gallery.size(7)).is_equal_to((84, 314))
    assert_that(gallery.size(99)).is_none()
    assert_that(gallery.count).is_equal_to(2)
    assert_that(gallery.release).is_equal_to(27)


# Pixels decode on the first ask and are remembered: the second
# ask answers the same object. A placard has no pixels to give,
# and an absent number gives None.
def test_pictures_decode_lazily_and_are_remembered(tiny_png: bytes) -> None:
    gallery = hung(tiny_png)
    first = cast("Picture", gallery.picture(3))

    assert_that(first).is_instance_of(Picture)
    assert_that(first.rows[0]).is_equal_to(((10, 20, 30), (40, 50, 60)))
    assert_that(gallery.picture(3)).is_same_as(first)
    assert_that(gallery.picture(7)).is_none()
    assert_that(gallery.picture(99)).is_none()


# The scaling ratio follows the Blorb spec to the letter: the
# Elbow Room Factor is the tighter axis of screen over standard
# window, a listed picture's standard ratio multiplies it, and
# the minimum and maximum clamp the result. An unlisted picture
# -- or a gallery with no Reso chunk at all -- stays at 1: one
# image pixel per screen pixel (Blorb: The Resolution Chunk).
def test_the_scaling_ratio_follows_the_elbow_room(tiny_png: bytes) -> None:
    bare = hung(tiny_png)

    assert_that(bare.scale(3, 720, 432)).is_equal_to(1)

    resolution = Resolution(
        320,
        200,
        {
            3: Scaling(Fraction(1), None, None),
            5: Scaling(Fraction(1, 2), None, None),
            8: Scaling(Fraction(1), Fraction(3), None),
            9: Scaling(Fraction(1), None, Fraction(2)),
        },
    )
    gallery = Gallery({}, 0, resolution)

    # ERF = min(720/320, 432/200) = 54/25: the height decides.
    assert_that(gallery.scale(3, 720, 432)).is_equal_to(Fraction(54, 25))
    assert_that(gallery.scale(5, 720, 432)).is_equal_to(Fraction(27, 25))
    assert_that(gallery.scale(8, 720, 432)).is_equal_to(3)
    assert_that(gallery.scale(9, 720, 432)).is_equal_to(2)
    assert_that(gallery.scale(99, 720, 432)).is_equal_to(1)


# The adaptive-palette dance (Blorb: The Adaptive Palette Chunk):
# chrome plotted before any scene wears its own palette, quietly;
# a plotted scene becomes the Current Palette; the chrome then
# wears it, re-dressing whenever the scene changes; a shorter
# scene palette changes only the entries it brought; and a
# palette-less picture disturbs nothing (tiny_png is truecolour).
def test_adaptive_chrome_wears_the_scene_palette(tiny_png: bytes) -> None:
    gallery = Gallery(
        {
            1: indexed(((10, 10, 10), (20, 20, 20))),
            2: indexed(((30, 30, 30), (40, 40, 40))),
            3: tiny_png,
            4: indexed(((99, 99, 99),), raw=b"\x00\x00\x00"),
            7: indexed(((1, 1, 1), (2, 2, 2))),
        },
        0,
        adaptive=frozenset({7}),
    )

    assert_that(gallery.adaptive).is_equal_to(frozenset({7}))
    assert_that(gallery.serial).is_zero()

    before = cast("Picture", gallery.picture(7))

    assert_that(before.rows[0]).is_equal_to(((1, 1, 1), (2, 2, 2)))
    assert_that(gallery.picture(7)).is_same_as(before)

    gallery.picture(1)

    assert_that(gallery.serial).is_equal_to(1)

    gallery.picture(1)

    assert_that(gallery.serial).is_equal_to(1)

    dressed = cast("Picture", gallery.picture(7))

    assert_that(dressed.rows[0]).is_equal_to(((10, 10, 10), (20, 20, 20)))
    assert_that(gallery.picture(7)).is_same_as(dressed)

    gallery.picture(3)

    assert_that(gallery.serial).is_equal_to(1)
    assert_that(gallery.picture(7)).is_same_as(dressed)

    gallery.picture(2)
    redressed = cast("Picture", gallery.picture(7))

    assert_that(redressed.rows[0]).is_equal_to(((30, 30, 30), (40, 40, 40)))

    gallery.picture(4)
    merged = cast("Picture", gallery.picture(7))

    assert_that(merged.rows[0]).is_equal_to(((99, 99, 99), (40, 40, 40)))


# An adaptive picture's transparency is its own even while wearing
# the Current Palette: the scene recolours the chrome, but the
# holes stay holes (Blorb: The Adaptive Palette Chunk).
def test_adaptive_chrome_keeps_its_holes() -> None:
    gallery = Gallery(
        {
            1: indexed(((10, 10, 10), (20, 20, 20))),
            7: indexed(((1, 1, 1), (2, 2, 2)), alphas=bytes([0])),
        },
        0,
        adaptive=frozenset({7}),
    )

    gallery.picture(1)
    dressed = cast("Picture", gallery.picture(7))

    assert_that(dressed.rows[0]).is_equal_to(((0, 0, 0), (20, 20, 20)))
    assert_that(dressed.clear).is_equal_to(((True, False),))


# An entry that does not open with the PNG signature and IHDR is
# refused loudly rather than measured wrongly -- whether the bytes
# are wrong or simply too few.
def test_malformed_art_is_refused() -> None:
    wrong = Gallery({1: b"not a png, but comfortably past twenty-four bytes"}, 0)

    with pytest.raises(PNGError, match="signature and IHDR"):
        wrong.size(1)

    with pytest.raises(PNGError, match="signature and IHDR"):
        Gallery({2: b"xx"}, 0).size(2)
