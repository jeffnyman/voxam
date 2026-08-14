from assertpy import assert_that

from voxam.png import Picture
from voxam.sixel import encode

RED = (255, 0, 0)
BLUE = (0, 0, 255)


# A one-colour picture encodes as one palette register in percent,
# raster attributes carrying the pixel size, and a full-height run.
def test_a_flat_picture_encodes_one_register() -> None:
    picture = Picture(4, 2, (((RED,) * 4), ((RED,) * 4)))

    sequence = encode(picture)

    assert_that(sequence).starts_with('\x1bPq"1;1;4;2')
    assert_that(sequence).contains("#0;2;100;0;0")
    # two rows of four pixels: mask 0b000011 -> '?' + 3 = 'B'
    assert_that(sequence).contains("!4B")
    assert_that(sequence).ends_with("-\x1b\\")


# Two colours share a band: the second pass returns to the left
# edge with $ before overprinting its own pixels.
def test_band_colours_take_turns_from_the_left() -> None:
    picture = Picture(2, 1, (((RED, BLUE)),))

    sequence = encode(picture)

    assert_that(sequence).contains("#0;2;0;0;100")
    assert_that(sequence).contains("#1;2;100;0;0")
    assert_that(sequence).contains("$")
    # blue holds register 0 and paints the second column; red the first
    assert_that(sequence).contains("#0?@")
    assert_that(sequence).contains("#1@?")


# Integer scaling multiplies pixels in both directions: a single
# pixel at scale 3 is a 3x3 block.
def test_scaling_magnifies_whole_pixels() -> None:
    picture = Picture(1, 1, ((RED,),))

    sequence = encode(picture, scale=3)

    assert_that(sequence).contains('"1;1;3;3')
    # three rows high -> mask 0b111 -> '?' + 7 = 'F', three wide
    assert_that(sequence).contains("FFF")


# A picture richer than sixel's 256 registers posterizes down to a
# workable palette instead of refusing.
def test_rich_pictures_posterize_into_the_palette() -> None:
    rows = tuple(
        tuple((red, green, 0) for green in range(0, 32)) for red in range(0, 255, 16)
    )
    picture = Picture(32, 16, rows)

    sequence = encode(picture)

    assert_that(sequence).starts_with("\x1bPq")
    assert_that(sequence.count(";2;")).is_less_than_or_equal_to(256)
