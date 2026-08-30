import struct
import zlib

import pytest
from assertpy import assert_that

from voxam.errors import PNGError
from voxam.png import SIGNATURE, Picture, decode, encoded, palette

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


# A truecolour picture with a translucent pixel keeps its straight
# source colors and carries the alpha channel whole, the clear
# flags still marking the fully transparent -- a display that can
# blend does the composing itself.
def test_partial_alpha_travels_straight() -> None:
    raw = bytes([0, 100, 150, 200, 128, 10, 20, 30, 0, 40, 50, 60, 255])
    picture = decode(picture_bytes(3, 1, 8, 6, raw))

    assert_that(picture.rows[0]).is_equal_to(
        ((100, 150, 200), (10, 20, 30), (40, 50, 60))
    )
    assert_that(picture.alpha).is_equal_to(((128, 0, 255),))
    assert_that(picture.clear).is_equal_to(((False, True, False),))


# With only full opacity and full transparency aboard, the alpha
# channel is dropped and the picture decodes exactly as it always
# has: composed rows, and the clear flags saying everything.
def test_binary_alpha_stays_composed() -> None:
    raw = bytes([0, 100, 150, 200, 255, 10, 20, 30, 0])
    picture = decode(picture_bytes(2, 1, 8, 6, raw))

    assert_that(picture.alpha).is_none()
    assert_that(picture.rows[0]).is_equal_to(((100, 150, 200), (0, 0, 0)))
    assert_that(picture.clear).is_equal_to(((False, True),))


# Grey-with-alpha and palette pictures carry partial alpha the
# same way: straight greys, straight palette entries, and the
# opacities aboard beside them.
def test_grey_and_palette_partial_alpha() -> None:
    raw = bytes([0, 200, 77, 100, 255])
    grey = decode(picture_bytes(2, 1, 8, 4, raw))

    assert_that(grey.rows[0]).is_equal_to(((200, 200, 200), (100, 100, 100)))
    assert_that(grey.alpha).is_equal_to(((77, 255),))

    plotted = decode(
        picture_bytes(
            2,
            1,
            8,
            3,
            bytes([0, 0, 1]),
            palette=bytes([200, 0, 0, 9, 9, 9]),
            alphas=bytes([255, 128]),
        )
    )

    assert_that(plotted.rows[0]).is_equal_to(((200, 0, 0), (9, 9, 9)))
    assert_that(plotted.alpha).is_equal_to(((255, 128),))
    assert_that(plotted.clear).is_equal_to(((False, False),))


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


# A half-transparent pixel keeps its straight orange and carries
# its opacity: composing is the display's business now, and the
# clear flags still mark the fully see-through.
def test_partial_alpha_keeps_straight_colors() -> None:
    raw = bytes([0, 200, 100, 50, 128, 255, 255, 255, 0])
    picture = decode(picture_bytes(2, 1, 8, 6, raw))

    assert_that(picture.rows[0]).is_equal_to(((200, 100, 50), WHITE))
    assert_that(picture.alpha).is_equal_to(((128, 0),))
    assert_that(picture.clear).is_equal_to(((False, True),))


# Greyscale with alpha composes the same way.
def test_grey_alpha_composes_over_black() -> None:
    raw = bytes([0, 100, 255, 200, 0])
    picture = decode(picture_bytes(2, 1, 8, 4, raw))

    assert_that(picture.rows[0]).is_equal_to(((100, 100, 100), BLACK))
    assert_that(picture.clear).is_equal_to(((False, True),))


# A tRNS chunk gives palette entries alphas; entries beyond its
# end stay opaque, and a partial entry rides the alpha channel
# with its straight palette color.
def test_palette_transparency_defaults_opaque() -> None:
    palette = bytes([200, 100, 50, 10, 20, 30])
    raw = bytes([0, 0, 1])
    picture = decode(
        picture_bytes(2, 1, 8, 3, raw, palette=palette, alphas=bytes([128]))
    )

    assert_that(picture.rows[0]).is_equal_to(((200, 100, 50), (10, 20, 30)))
    assert_that(picture.alpha).is_equal_to(((128, 255),))
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


# The encoder's stream is spelled by hand so its bytes are the
# same on every build -- zlib-ng and madler zlib disagree, and the
# wire these pictures ride is certified byte for byte -- so the
# bytes themselves are pinned (RFC 1951).
def test_encoded_bytes_never_vary() -> None:
    plain = Picture(2, 1, (((1, 2, 3), (4, 5, 6)),))

    assert_that(encoded(plain).hex()).is_equal_to(
        "89504e470d0a1a0a0000000d49484452000000020000000108020000007b40"
        "e8dd0000000f494441547801636064626661650300003f0016738177810000"
        "000049454e44ae426082"
    )

    holed = Picture(2, 1, (((9, 9, 9), (4, 5, 6)),), clear=((True, False),))

    assert_that(encoded(holed).hex()).is_equal_to(
        "89504e470d0a1a0a0000000d4948445200000002000000010806000000f422"
        "7f8a0000001149444154780163e0e4e464606165fb0f0001f0012a9e28c690"
        "0000000049454e44ae426082"
    )

    misty = Picture(1, 1, (((10, 20, 30),),), alpha=((128,),))

    assert_that(encoded(misty).hex()).is_equal_to(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15"
        "c4890000000d49444154780163e012916b0000012500bd1c36baec00000000"
        "49454e44ae426082"
    )


# The deflate matcher, walked whole and read back by real zlib: a
# solid run spells itself through overlapping distance-one matches;
# a repeating stripe matches at a distance wide enough to need
# extra bits; and a picture whose opening pixels return only past
# the window's reach must spell them fresh, never point that far
# back (RFC 1951 3.2.3, 3.2.6).
def test_the_deflate_matcher_round_trips() -> None:
    def shaded(index: int) -> tuple[int, int, int]:
        return ((index * 7) % 251, (index * 11) % 241, (index * 13) % 239)

    solid = Picture(100, 1, (((7, 7, 7),) * 100,))
    striped = Picture(64, 1, (tuple(shaded(index % 8) for index in range(64)),))
    pixels = [shaded(index) for index in range(11200)]
    pixels[-4:] = pixels[:4]
    distant = Picture(11200, 1, (tuple(pixels),))

    # Six distinct nine-bit literals close the stream exactly on a
    # byte boundary: 3 + 8 + 9 * 6 + 7 bits, nothing left to pad.
    aligned = Picture(2, 1, (((200, 201, 202), (203, 204, 205)),))

    for picture in (solid, striped, distant, aligned):
        back = decode(encoded(picture))

        assert_that(back.rows).is_equal_to(picture.rows)


# The encoder is decode's write-side twin: plain truecolour rides
# opaque, clear flags travel as zero alpha, and partial alpha
# rides whole -- so what the wire carries decodes back to the very
# pixels the gallery plotted. A fully-clear pixel's colour is the
# one thing that does not survive, composed over black as decode
# always composes what cannot show.
def test_encoded_pictures_round_trip() -> None:
    plain = Picture(2, 1, (((1, 2, 3), (4, 5, 6)),))
    back = decode(encoded(plain))

    assert_that((back.width, back.height)).is_equal_to((2, 1))
    assert_that(back.rows).is_equal_to(plain.rows)
    assert_that(back.clear).is_none()
    assert_that(back.alpha).is_none()

    holed = Picture(2, 1, (((9, 9, 9), (4, 5, 6)),), clear=((True, False),))
    hollow = decode(encoded(holed))

    assert_that(hollow.clear).is_equal_to(((True, False),))
    assert_that(hollow.rows[0][1]).is_equal_to((4, 5, 6))

    misty = Picture(1, 1, (((10, 20, 30),),), alpha=((128,),))
    misted = decode(encoded(misty))

    assert_that(misted.alpha).is_equal_to(((128,),))
    assert_that(misted.rows[0][0]).is_equal_to((10, 20, 30))
