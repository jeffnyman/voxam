"""The pre-Blorb picture files, decoded as pix2gif prescribes."""

from typing import cast

import pytest
from assertpy import assert_that

from voxam.errors import VoxamError
from voxam.picfile import (
    CLEAR_CODE,
    EGA_PALETTE,
    END_CODE,
    FIRST_DYNAMIC,
    FIRST_WIDTH,
    LAST_WIDTH,
    gallery,
)
from voxam.png import Picture


def packed(codes: list[int]) -> bytes:
    """Pack LZW codes least-significant-bit first, widths mirrored.

    The width schedule replicates the decoder's exactly: 9 bits
    growing toward 12 whenever the next dynamic code reaches the
    current mask, reset by the clear code -- and the code following
    a clear adds no table entry, just as the decoder skips one.
    """

    bits = bytearray()
    position = 0
    width = FIRST_WIDTH
    next_code = FIRST_DYNAMIC
    after_clear = False

    for code in codes:
        for index in range(width):
            if position % 8 == 0:
                bits.append(0)

            if (code >> index) & 1:
                bits[-1] |= 1 << (position % 8)

            position += 1

        if next_code == (1 << width) - 1 and width < LAST_WIDTH:
            width += 1

        if code == CLEAR_CODE:
            width = FIRST_WIDTH
            next_code = FIRST_DYNAMIC
            after_clear = True
        elif code != END_CODE:
            if after_clear:
                after_clear = False
            else:
                next_code += 1

    return bytes(bits)


def crafted(
    pixels: list[int],
    width: int,
    height: int,
    *,
    flags: int = 0,
    palette: tuple[int, int, int] | None = None,
    codes: list[int] | None = None,
) -> bytes:
    """Build a one-picture file around a literal code stream."""

    stream = packed(codes if codes is not None else [256, *pixels, 257])
    directory_end = 16 + 14 + 12
    palette_blob = bytes([1, *palette]) if palette else b""
    palette_at = directory_end if palette else 0
    pixels_at = directory_end + len(palette_blob)

    header = bytes([0, 0, 0, 0, 2, 0, 0, 0, 14, 0, 0, 0, 0, 0, 7, 0])
    entry = (
        (3).to_bytes(2, "little")
        + width.to_bytes(2, "little")
        + height.to_bytes(2, "little")
        + flags.to_bytes(2, "little")
        + pixels_at.to_bytes(3, "big")
        + palette_at.to_bytes(3, "big")
    )
    placeholder = (
        (9).to_bytes(2, "little") + bytes(6) + (0).to_bytes(3, "big") + bytes(1)
    )

    return header + entry + placeholder + palette_blob + stream


# A literal code stream decodes pixel for pixel, colours drawn
# from the default EGA palette; a directory entry with no data is
# a placeholder and hangs nothing, exactly as pix2gif skips them.
def test_decodes_literal_pixels_through_the_ega_palette() -> None:
    book = gallery(crafted([1, 2, 2, 1], 2, 2))

    assert_that(book.count).is_equal_to(1)
    assert_that(book.release).is_equal_to(7)
    assert_that(book.size(3)).is_equal_to((2, 2))
    assert_that(book.size(9)).is_none()

    picture = cast("Picture", book.picture(3))

    assert_that(picture.rows[0]).is_equal_to((EGA_PALETTE[1], EGA_PALETTE[2]))
    assert_that(picture.clear).is_none()


# A colour map loads from slot 2 of the palette, and the
# transparency flag's top four bits name the see-through colour.
def test_colour_maps_and_transparency() -> None:
    book = gallery(crafted([1, 2, 2, 1], 2, 2, flags=0x1001, palette=(10, 20, 30)))
    picture = cast("Picture", book.picture(3))
    clear = picture.clear

    assert_that(picture.rows[0][1]).is_equal_to((10, 20, 30))
    assert_that(clear).is_not_none()
    assert_that(clear[0] if clear else ()).is_equal_to((True, False))
    assert_that(clear[1] if clear else ()).is_equal_to((False, True))


# The KwKwK case: a code naming the very next table entry repeats
# the previous chain plus its own first pixel -- LZW's one special
# case, and the clear code resets the table mid-stream.
def test_the_lzw_special_cases_decode() -> None:
    book = gallery(crafted([5, 258, 256, 4], 4, 1, codes=[256, 5, 258, 256, 4, 257]))
    picture = cast("Picture", book.picture(3))

    assert_that(picture.rows[0]).is_equal_to(
        (EGA_PALETTE[5], EGA_PALETTE[5], EGA_PALETTE[5], EGA_PALETTE[4])
    )


# The code width grows from 9 toward 12 bits as the table fills;
# a long literal run crosses the first growth boundary, and both
# sides must agree bit for bit.
def test_the_code_width_grows_with_the_table() -> None:
    pixels = [(index * 7) % 256 for index in range(300)]
    book = gallery(crafted(pixels, 300, 1))
    picture = cast("Picture", book.picture(3))

    assert_that([EGA_PALETTE[p & 0x0F] for p in pixels]).is_equal_to(
        list(picture.rows[0])
    )


# Every way a file can lie about itself halts loudly: too short
# for a header, a directory past the end, data ending mid-code,
# and an end code before the pixels are all delivered.
def test_dishonest_files_halt_loudly() -> None:
    with pytest.raises(VoxamError, match="header"):
        gallery(b"\x00" * 4)

    with pytest.raises(VoxamError, match="directory"):
        gallery(bytes([0, 0, 0, 0, 2, 0, 0, 0, 14, 0, 0, 0, 0, 0, 7, 0]))

    truncated = crafted([1, 2, 2, 1], 2, 2)[:-1]

    with pytest.raises(VoxamError, match="mid-code"):
        gallery(truncated)

    with pytest.raises(VoxamError, match="of its"):
        gallery(crafted([1, 2], 2, 2, codes=[256, 1, 2, 257]))


# A code naming a longer chain walks the prefix links to its first
# pixel -- the everyday LZW case beyond single literals.
def test_chained_codes_walk_to_their_first_pixel() -> None:
    book = gallery(crafted([0] * 6, 6, 1, codes=[256, 1, 2, 258, 259, 257]))
    picture = cast("Picture", book.picture(3))

    assert_that(picture.rows[0]).is_equal_to(
        tuple(EGA_PALETTE[p] for p in (1, 2, 1, 2, 2, 1))
    )


# A narrow directory -- any entry size but 14 -- carries no colour
# map address, just a padding byte, and the default EGA palette
# stands (pix2gif).
def test_narrow_directories_have_no_colour_maps() -> None:
    stream = packed([256, 6, 257])
    pixels_at = 16 + 12
    header = bytes([0, 0, 0, 0, 1, 0, 0, 0, 13, 0, 0, 0, 0, 0, 7, 0])
    entry = (
        (4).to_bytes(2, "little")
        + (1).to_bytes(2, "little")
        + (1).to_bytes(2, "little")
        + (0).to_bytes(2, "little")
        + pixels_at.to_bytes(3, "big")
        + bytes(1)
    )
    book = gallery(header + entry + stream)
    picture = cast("Picture", book.picture(4))

    assert_that(picture.rows[0]).is_equal_to((EGA_PALETTE[6],))
