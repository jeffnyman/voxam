"""Infocom's original picture files: MG1, CG1, and EG1.

Before Blorb existed, Version 6 art shipped beside the story in
per-platform picture files -- .MG1 for MCGA, .CG1 for CGA, .EG1
for EGA -- found by the story's own name, which is why the DOS
instructions for Frobozz Magic Videopoker say to rename a Zork
Zero graphics file to FMVPOKER.EG1. The format was never publicly
specified; the authority here is Mark Howell's pix2gif (vendored
with ztools), transcribed rule for rule: a 16-byte header of
little-endian words, a directory of picture entries with 3-byte
big-endian data offsets, an optional per-picture colour map loaded
from slot 2 of the default EGA palette, a transparency flag whose
top four bits name the see-through colour, and pixel data in an
LZW variant with 9-to-12-bit codes packed least-significant-bit
first.
"""

from voxam.errors import VoxamError
from voxam.gallery import Gallery, Placard
from voxam.png import Picture

# The default 16-colour EGA palette, exactly as pix2gif carries it;
# a picture with its own colour map replaces entries from slot 2.
EGA_PALETTE = (
    (0, 0, 0),
    (0, 0, 170),
    (0, 170, 0),
    (0, 170, 170),
    (170, 0, 0),
    (170, 0, 170),
    (170, 170, 0),
    (170, 170, 170),
    (85, 85, 85),
    (85, 85, 255),
    (85, 255, 85),
    (85, 255, 255),
    (255, 85, 85),
    (255, 85, 255),
    (255, 255, 85),
    (255, 255, 255),
)

HEADER_SIZE = 16
COUNT_OFFSET = 4
DIRECTORY_ENTRY_WIDE = 14
TRANSPARENCY_FLAG = 0x0001
TRANSPARENT_SHIFT = 12
# pix2gif's own remark: "Fix for some buggy _Arthur_ pictures" --
# a colour map never brings more than 14 entries, since it loads
# from slot 2 of a 16-slot palette.
COLOURS_CAP = 14

# The LZW dialect: 8-bit pixels, so the clear code is 256, the end
# code 257, dynamic codes from 258, and code width grows from 9
# bits toward 12 when the next code reaches the current mask.
CODE_SIZE = 8
CLEAR_CODE = 1 << CODE_SIZE
END_CODE = CLEAR_CODE + 1
FIRST_DYNAMIC = CLEAR_CODE + 2
TABLE_SIZE = 4096
FIRST_WIDTH = CODE_SIZE + 1
LAST_WIDTH = 12


def gallery(data: bytes) -> Gallery:
    """Hang a picture file's art as a Gallery of decoded pictures.

    Args:
        data: The whole .MG1/.CG1/.EG1 file.

    Returns:
        A gallery answering sizes and pixels by picture number; the
        file's version word stands in for a release number.

    Raises:
        VoxamError: For a file too short to hold what its own
            header and directory promise.
    """

    if len(data) < HEADER_SIZE:
        msg = (
            f"a picture file's header is {HEADER_SIZE} bytes, but only "
            f"{len(data)} are present (pix2gif)"
        )

        raise VoxamError(msg)

    images = int.from_bytes(data[COUNT_OFFSET : COUNT_OFFSET + 2], "little")
    entry_size = data[8]
    version = int.from_bytes(data[14:16], "little")
    art: dict[int, bytes | Placard | Picture] = {}
    position = HEADER_SIZE

    for _ in range(images):
        entry, position = _entry(
            data, position, wide=entry_size == DIRECTORY_ENTRY_WIDE
        )
        number, width, height, flags, pixels_at, palette_at = entry

        if pixels_at == 0:
            # A directory entry with no data is a placeholder --
            # pix2gif skips them the same way.
            continue

        art[number] = _picture(data, width, height, flags, pixels_at, palette_at)

    return Gallery(art, version)


def _entry(
    data: bytes, position: int, *, wide: bool
) -> tuple[tuple[int, int, int, int, int, int], int]:
    """One directory entry: numbers, sizes, flags, and offsets."""

    if position + (14 if wide else 12) > len(data):
        msg = f"the picture directory runs past the file's {len(data)} bytes (pix2gif)"

        raise VoxamError(msg)

    number = int.from_bytes(data[position : position + 2], "little")
    width = int.from_bytes(data[position + 2 : position + 4], "little")
    height = int.from_bytes(data[position + 4 : position + 6], "little")
    flags = int.from_bytes(data[position + 6 : position + 8], "little")
    pixels_at = int.from_bytes(data[position + 8 : position + 11], "big")

    if wide:
        palette_at = int.from_bytes(data[position + 11 : position + 14], "big")
        position += 14
    else:
        palette_at = 0
        position += 12

    return (number, width, height, flags, pixels_at, palette_at), position


def _picture(  # noqa: PLR0913, PLR0917 -- one argument per directory field
    data: bytes, width: int, height: int, flags: int, pixels_at: int, palette_at: int
) -> Picture:
    """Decode one picture: palette, transparency, and pixels."""

    palette = list(EGA_PALETTE)

    if palette_at:
        colours = min(data[palette_at], COLOURS_CAP)

        for index in range(colours):
            at = palette_at + 1 + index * 3
            palette[2 + index] = (data[at], data[at + 1], data[at + 2])

    transparent = (flags >> TRANSPARENT_SHIFT) if flags & TRANSPARENCY_FLAG else None
    pixels = _decompress(data, pixels_at, width * height)
    rows = tuple(
        tuple(
            palette[pixel & 0x0F] for pixel in pixels[row * width : (row + 1) * width]
        )
        for row in range(height)
    )
    clear = (
        tuple(
            tuple(
                pixel == transparent
                for pixel in pixels[row * width : (row + 1) * width]
            )
            for row in range(height)
        )
        if transparent is not None
        else None
    )

    return Picture(width, height, rows, clear)


def _decompress(data: bytes, position: int, wanted: int) -> bytearray:
    """Unpack the LZW pixel stream, exactly as pix2gif reads it.

    Codes are read least-significant-bit first from a continuous
    bit stream; the code width starts at 9 bits and grows toward
    12 whenever the next dynamic code reaches the current width's
    mask; the clear code resets both. Enough codes for the
    picture's pixels must arrive before the data runs out.

    Raises:
        VoxamError: If the stream ends before its end code.
    """

    prefixes = [TABLE_SIZE] * TABLE_SIZE
    pixels_of = list(range(TABLE_SIZE))
    bit = position * 8
    limit = len(data) * 8
    width = FIRST_WIDTH
    next_code = FIRST_DYNAMIC
    old = 0
    out = bytearray()

    def read_code() -> int:
        nonlocal bit, width

        if bit + width > limit:
            msg = f"the picture data ends mid-code at bit {bit} (pix2gif)"

            raise VoxamError(msg)

        code = 0
        taken = 0

        while taken < width:
            piece = min(8 - (bit & 7), width - taken)
            code |= ((data[bit >> 3] >> (bit & 7)) & ((1 << piece) - 1)) << taken
            bit += piece
            taken += piece

        if next_code == (1 << width) - 1 and width < LAST_WIDTH:
            width += 1

        return code

    while True:
        code = read_code()

        if code == END_CODE:
            if len(out) < wanted:
                msg = (
                    f"the picture ended after {len(out)} of its "
                    f"{wanted} pixels (pix2gif)"
                )

                raise VoxamError(msg)

            return out

        if code == CLEAR_CODE:
            width = FIRST_WIDTH
            next_code = FIRST_DYNAMIC
            code = read_code()
        else:
            first = old if code == next_code else code

            while prefixes[first] != TABLE_SIZE:
                first = prefixes[first]

            prefixes[next_code] = old
            pixels_of[next_code] = pixels_of[first]
            next_code += 1

        old = code
        chain = []

        while code != TABLE_SIZE:
            chain.append(pixels_of[code])
            code = prefixes[code]

        out.extend(reversed(chain))
