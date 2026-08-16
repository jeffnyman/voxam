from assertpy import assert_that

from voxam.font3 import FONT_3_BITMAPS, PIXELS, ROWS


# Every §16 character code from 32 to 126 has a bitmap, each one
# exactly eight rows of eight pixels.
def test_the_table_covers_the_whole_font() -> None:
    assert_that(sorted(FONT_3_BITMAPS)).is_equal_to(list(range(32, 127)))
    assert_that(PIXELS).is_equal_to(8)

    for rows in FONT_3_BITMAPS.values():
        assert_that(rows).is_length(ROWS)


# The landmarks the spec draws in words: 32 is blank, 54 is solid,
# 87 -- the full gauge -- keeps its end rails rather than going
# solid, and 71's road tip is a single pixel in the top-right
# corner, the shape no character terminal could ever show.
def test_the_landmark_shapes() -> None:
    assert_that(FONT_3_BITMAPS[32]).is_equal_to(bytes(8))
    assert_that(FONT_3_BITMAPS[54]).is_equal_to(bytes([0xFF] * 8))
    assert_that(FONT_3_BITMAPS[87]).is_equal_to(
        bytes([0x00, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0x00])
    )
    assert_that(FONT_3_BITMAPS[71]).is_equal_to(bytes([0x01, 0, 0, 0, 0, 0, 0, 0]))


# The rising diagonal climbs one pixel per row, bottom-left to
# top-right -- bit 7 being the leftmost pixel of a row.
def test_the_rising_diagonal_climbs() -> None:
    assert_that(list(FONT_3_BITMAPS[35])).is_equal_to(
        [0x80 >> (7 - row) for row in range(8)]
    )


# The reverse twins at 123 to 126 are exact bitwise inversions of
# their plain shapes at 92 to 94 and 96 -- §16 draws them so, which
# is why the glass never needs to fake an inversion with an ink
# swap.
def test_the_reverse_twins_invert_their_plain_shapes() -> None:
    for twin, plain in ((123, 92), (124, 93), (125, 94), (126, 96)):
        inverted = bytes(row ^ 0xFF for row in FONT_3_BITMAPS[plain])

        assert_that(FONT_3_BITMAPS[twin]).is_equal_to(inverted)
