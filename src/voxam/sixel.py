"""Encoding pictures as DEC sixel graphics.

Sixel is the terminal's own pixel protocol: an escape sequence
carrying a palette and columns of six vertical pixels at a time,
drawn at the cursor in real pixels rather than character cells.
Windows Terminal speaks it from release 1.22, and through it a
cover picture shows at its true resolution -- the same image a
graphical interpreter would draw.

The encoder is pure stdlib like the PNG reader it feeds on: sixel
palettes hold at most 256 colours, which suits Infocom's palette
art natively; richer pictures posterize down first.
"""

from voxam.png import Picture

ENTER = "\x1bPq"
LEAVE = "\x1b\\"

# Sixel data characters carry six vertical pixels as a bitmask on
# top of an offset; ! introduces a run length, $ returns to the
# left edge for the band's next colour, - moves down one band.
OFFSET = 0x3F
BAND = 6
RUN_WORTHWHILE = 3

# A sixel palette holds registers 0 to 255, defined in percentages;
# pictures with more distinct colours posterize each channel to six
# levels first, which no cover in the vendored art needs.
PALETTE_LIMIT = 256
POSTERIZE_STEP = 51
PERCENT = 100
FULL = 255


def encode(picture: Picture, scale: int = 1) -> str:
    """Encode a picture as a sixel sequence, integer-scaled up.

    Args:
        picture: The decoded picture to draw.
        scale: A whole-number magnification; sixel pixels are
            screen pixels, so a small original is enlarged to be
            seen at all.

    Returns:
        The complete escape sequence, enter to leave.
    """

    palette, indices = _indexed(picture)
    width = picture.width * scale
    height = picture.height * scale
    pieces = [ENTER, f'"1;1;{width};{height}']

    for register, (red, green, blue) in enumerate(palette):
        pieces.append(
            f"#{register};2;"
            f"{red * PERCENT // FULL};"
            f"{green * PERCENT // FULL};"
            f"{blue * PERCENT // FULL}"
        )

    for band_top in range(0, height, BAND):
        rows = [
            indices[(band_top + drop) // scale]
            for drop in range(min(BAND, height - band_top))
        ]
        present = sorted({register for row in rows for register in row})

        for position, register in enumerate(present):
            if position:
                pieces.append("$")

            pieces.append(f"#{register}")
            pieces.append(_band_run(rows, register, width, scale))

        pieces.append("-")

    pieces.append(LEAVE)

    return "".join(pieces)


def _band_run(rows: list[list[int]], register: int, width: int, scale: int) -> str:
    """One colour's run-length-encoded pass across a six-row band."""

    pieces = []
    running = ""
    length = 0

    for column in range(width):
        mask = 0

        for drop, row in enumerate(rows):
            if row[column // scale] == register:
                mask |= 1 << drop

        character = chr(OFFSET + mask)

        if character == running:
            length += 1
            continue

        pieces.append(_run(running, length))
        running = character
        length = 1

    pieces.append(_run(running, length))

    return "".join(pieces)


def _run(character: str, length: int) -> str:
    """A run of one sixel character, counted when that is shorter."""

    if length > RUN_WORTHWHILE:
        return f"!{length}{character}"

    return character * length


def _indexed(
    picture: Picture,
) -> tuple[list[tuple[int, int, int]], list[list[int]]]:
    """The picture as a palette and rows of register numbers.

    A picture with more distinct colours than sixel's 256 registers
    posterizes each channel to six levels first -- a loss no cover
    in the vendored art ever pays, their palettes being small.
    """

    colours = {pixel for row in picture.rows for pixel in row}

    if len(colours) > PALETTE_LIMIT:
        rows = [
            [
                (
                    pixel[0] // POSTERIZE_STEP * POSTERIZE_STEP,
                    pixel[1] // POSTERIZE_STEP * POSTERIZE_STEP,
                    pixel[2] // POSTERIZE_STEP * POSTERIZE_STEP,
                )
                for pixel in row
            ]
            for row in picture.rows
        ]
        colours = {pixel for row in rows for pixel in row}
    else:
        rows = [list(row) for row in picture.rows]

    palette = sorted(colours)
    registers = {colour: register for register, colour in enumerate(palette)}

    return palette, [[registers[pixel] for pixel in row] for row in rows]
