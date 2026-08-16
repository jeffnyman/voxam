from fractions import Fraction
from typing import cast

import pytest
from assertpy import assert_that

from voxam.errors import PNGError
from voxam.gallery import Gallery, Placard, Resolution, Scaling
from voxam.png import Picture


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


# An entry that does not open with the PNG signature and IHDR is
# refused loudly rather than measured wrongly -- whether the bytes
# are wrong or simply too few.
def test_malformed_art_is_refused() -> None:
    wrong = Gallery({1: b"not a png, but comfortably past twenty-four bytes"}, 0)

    with pytest.raises(PNGError, match="signature and IHDR"):
        wrong.size(1)

    with pytest.raises(PNGError, match="signature and IHDR"):
        Gallery({2: b"xx"}, 0).size(2)
