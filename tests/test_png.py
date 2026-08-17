import struct
import zlib

import pytest
from assertpy import assert_that

from voxam.errors import PNGError
from voxam.png import SIGNATURE, decode, palette

BLACK = (0, 0, 0)
WHITE = (255, 255, 255)


def chunk(name: bytes, payload: bytes) -> bytes:
    return (
        len(payload).to_bytes(4, "big")
        + name
        + payload
        + zlib.crc32(name + payload).to_bytes(4, "big")
    )


def picture_bytes(
    width: int,
    height: int,
    depth: int,
    colour_type: int,
    raw: bytes,
    palette: bytes = b"",
    alphas: bytes = b"",
    interlace: int = 0,
    idat_pieces: int = 1,
    ended: bool = True,
) -> bytes:
    header = struct.pack(">IIBBBBB", width, height, depth, colour_type, 0, 0, interlace)
    compressed = zlib.compress(raw)
    pieces = [SIGNATURE, chunk(b"IHDR", header), chunk(b"gAMA", b"\x00\x01\x86\xa0")]

    if palette:
        pieces.append(chunk(b"PLTE", palette))

    if alphas:
        pieces.append(chunk(b"tRNS", alphas))

    split = max(1, len(compressed) // idat_pieces)

    for start in range(0, len(compressed), split):
        pieces.append(chunk(b"IDAT", compressed[start : start + split]))

    if ended:
        pieces.append(chunk(b"IEND", b""))

    return b"".join(pieces)


# A truecolour picture with unfiltered scanlines decodes to its
# pixels exactly.
def test_truecolour_pixels_decode_exactly() -> None:
    raw = bytes([0, 255, 0, 0, 0, 255, 0]) + bytes([0, 0, 0, 255, 255, 255, 255])
    picture = decode(picture_bytes(2, 2, 8, 2, raw))

    assert_that(picture.width).is_equal_to(2)
    assert_that(picture.height).is_equal_to(2)
    assert_that(picture.rows[0]).is_equal_to(((255, 0, 0), (0, 255, 0)))
    assert_that(picture.rows[1]).is_equal_to(((0, 0, 255), WHITE))


# The Sub filter adds the byte one pixel to the left back in
# (PNG 9.2).
def test_the_sub_filter_reconstructs_from_the_left() -> None:
    raw = bytes([1, 10, 20, 30, 5, 5, 5])
    picture = decode(picture_bytes(2, 1, 8, 2, raw))

    assert_that(picture.rows[0]).is_equal_to(((10, 20, 30), (15, 25, 35)))


# The Up filter adds the byte directly above back in; above the
# first line sits an imaginary row of zeros (PNG 9.2).
def test_the_up_filter_reconstructs_from_above() -> None:
    raw = bytes([2, 10, 20, 30]) + bytes([2, 1, 2, 3])
    picture = decode(picture_bytes(1, 2, 8, 2, raw))

    assert_that(picture.rows[0]).is_equal_to(((10, 20, 30),))
    assert_that(picture.rows[1]).is_equal_to(((11, 22, 33),))


# The Average filter adds back the mean of left and above, floored
# (PNG 9.2).
def test_the_average_filter_reconstructs_from_the_mean() -> None:
    raw = bytes([0, 10, 20, 30, 40, 50, 60]) + bytes([3, 5, 5, 5, 5, 5, 5])
    picture = decode(picture_bytes(2, 2, 8, 2, raw))

    assert_that(picture.rows[1][0]).is_equal_to((10, 15, 20))
    assert_that(picture.rows[1][1]).is_equal_to((30, 37, 45))


# Paeth's predictor picks whichever of left, above, and corner lies
# nearest its guess; this line makes each of the three win once
# (PNG 9.4).
def test_the_paeth_filter_tries_all_three_neighbours() -> None:
    raw = bytes([0, 1, 2, 3]) + bytes([4, 4, 252, 7])
    picture = decode(picture_bytes(3, 2, 8, 0, raw))

    assert_that(picture.rows[1]).is_equal_to(((5, 5, 5), (1, 1, 1), (9, 9, 9)))


# A palette picture at bit depth 4 -- Beyond Zork's own shape --
# unpacks two indices per byte, and its data may arrive split
# across several IDAT chunks.
def test_palette_nibbles_decode_across_split_idats() -> None:
    palette = bytes([255, 0, 0, 0, 255, 0, 0, 0, 255])
    raw = bytes([0, 0x01, 0x20]) + bytes([0, 0x21, 0x00])
    picture = decode(picture_bytes(3, 2, 4, 3, raw, palette=palette, idat_pieces=3))

    assert_that(picture.rows[0]).is_equal_to(((255, 0, 0), (0, 255, 0), (0, 0, 255)))
    assert_that(picture.rows[1]).is_equal_to(((0, 0, 255), (0, 255, 0), (255, 0, 0)))


# Bit depth 1 packs eight indices per byte, and a picture without
# an IEND chunk simply runs out of chunks.
def test_single_bit_palettes_decode() -> None:
    palette = bytes([0, 0, 0, 255, 255, 255])
    raw = bytes([0, 0b10110000])
    picture = decode(picture_bytes(4, 1, 1, 3, raw, palette=palette, ended=False))

    assert_that(picture.rows[0]).is_equal_to((WHITE, BLACK, WHITE, WHITE))


# Greyscale values scale up to the full 0-255 range: at depth 2,
# the four levels are 0, 85, 170, and 255.
def test_greyscale_depths_scale_to_full_range() -> None:
    raw = bytes([0, 0b00011011])
    picture = decode(picture_bytes(4, 1, 2, 0, raw))

    assert_that(picture.rows[0]).is_equal_to(
        (BLACK, (85, 85, 85), (170, 170, 170), WHITE)
    )


# Alpha channels compose over black, the screen a cover shows on:
# half-transparent orange darkens by half.
def test_alpha_composes_over_black() -> None:
    raw = bytes([0, 200, 100, 50, 128, 255, 255, 255, 0])
    picture = decode(picture_bytes(2, 1, 8, 6, raw))

    assert_that(picture.rows[0]).is_equal_to(((100, 50, 25), BLACK))
    assert_that(picture.clear).is_equal_to(((False, True),))


# Greyscale with alpha composes the same way.
def test_grey_alpha_composes_over_black() -> None:
    raw = bytes([0, 100, 255, 200, 0])
    picture = decode(picture_bytes(2, 1, 8, 4, raw))

    assert_that(picture.rows[0]).is_equal_to(((100, 100, 100), BLACK))
    assert_that(picture.clear).is_equal_to(((False, True),))


# A tRNS chunk gives palette entries alphas; entries beyond its end
# stay opaque.
def test_palette_transparency_composes_and_defaults_opaque() -> None:
    palette = bytes([200, 100, 50, 10, 20, 30])
    raw = bytes([0, 0, 1])
    picture = decode(
        picture_bytes(2, 1, 8, 3, raw, palette=palette, alphas=bytes([128]))
    )

    assert_that(picture.rows[0]).is_equal_to(((100, 50, 25), (10, 20, 30)))
    assert_that(picture.clear).is_equal_to(((False, False),))


# Only a zero alpha marks a pixel clear -- Version 6 chrome layers
# with fully see-through holes, and only full transparency matters
# there (Blorb: Picture Resource Chunks). A picture with no alpha
# at all carries no clear grid.
def test_fully_transparent_pixels_are_marked_clear() -> None:
    palette = bytes([200, 100, 50, 10, 20, 30])
    raw = bytes([0, 0, 1])
    picture = decode(
        picture_bytes(2, 1, 8, 3, raw, palette=palette, alphas=bytes([255, 0]))
    )

    assert_that(picture.rows[0]).is_equal_to(((200, 100, 50), BLACK))
    assert_that(picture.clear).is_equal_to(((False, True),))

    opaque = decode(picture_bytes(1, 1, 8, 2, bytes([0, 1, 2, 3])))

    assert_that(opaque.clear).is_none()


# The palette reader hands back a PNG's own PLTE -- what a plotted
# scene carries into the Current Palette -- a palette-less picture
# answers empty, and non-PNG bytes are refused (Blorb: The
# Adaptive Palette Chunk).
def test_the_palette_reader_answers_the_plte() -> None:
    data = picture_bytes(
        2, 1, 8, 3, bytes([0, 0, 1]), palette=bytes([1, 2, 3, 4, 5, 6])
    )

    assert_that(palette(data)).is_equal_to(((1, 2, 3), (4, 5, 6)))
    assert_that(palette(picture_bytes(1, 1, 8, 2, bytes(4)))).is_empty()

    with pytest.raises(PNGError, match="PNG signature"):
        palette(b"GIF89a nope")


# An adapted palette overrides the file's own at plot time, while
# transparency stays the file's (Blorb: The Adaptive Palette
# Chunk).
def test_an_adapted_palette_redresses_the_pixels() -> None:
    data = picture_bytes(
        2, 1, 8, 3, bytes([0, 0, 1]), palette=bytes([9] * 6), alphas=bytes([255, 0])
    )
    picture = decode(data, ((10, 11, 12), (20, 21, 22)))

    assert_that(picture.rows[0]).is_equal_to(((10, 11, 12), BLACK))
    assert_that(picture.clear).is_equal_to(((False, True),))


@pytest.mark.parametrize(
    ("data", "complaint"),
    [
        (b"GIF89a not a png", "PNG signature"),
        (picture_bytes(1, 1, 8, 2, bytes(4), interlace=1), "interlaced"),
        (picture_bytes(1, 1, 16, 2, bytes(7)), "not a supported pairing"),
        (picture_bytes(1, 1, 8, 5, bytes(4)), "not a supported pairing"),
        (picture_bytes(0, 1, 8, 2, b""), "no pixels"),
        (picture_bytes(1, 1, 8, 3, bytes(2)), "without its PLTE"),
        (SIGNATURE + chunk(b"IEND", b""), "no IHDR"),
        (SIGNATURE + b"\x00\x00\x00\x0dIHDR\x00", "cut short"),
        (SIGNATURE + chunk(b"IHDR", b"\x00\x01"), "malformed"),
    ],
)
def test_unusable_pictures_are_refused(data: bytes, complaint: str) -> None:
    with pytest.raises(PNGError, match=complaint):
        decode(data)


# Image data that does not inflate, inflates to the wrong size, or
# names an undefined filter is refused with the reason given.
def test_broken_image_data_is_refused() -> None:
    header = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    garbage = (
        SIGNATURE
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", b"not-deflated")
        + chunk(b"IEND", b"")
    )

    with pytest.raises(PNGError, match="does not inflate"):
        decode(garbage)

    with pytest.raises(PNGError, match="bytes of scanlines"):
        decode(picture_bytes(1, 1, 8, 2, bytes(9)))

    with pytest.raises(PNGError, match="filter type 5"):
        decode(picture_bytes(1, 1, 8, 2, bytes([5, 0, 0, 0])))


# A pixel pointing beyond the palette is corrupt, not black.
def test_palette_overruns_are_refused() -> None:
    palette = bytes([1, 2, 3])
    raw = bytes([0, 7])

    with pytest.raises(PNGError, match="beyond the 1-entry palette"):
        decode(picture_bytes(1, 1, 8, 3, raw, palette=palette))
