"""Reading and writing PNG pictures with the standard library alone.

Blorb resource files carry their pictures as PNG (Blorb: Picture
Resource Chunks), and a cover picture is worth showing before play
-- but Voxam's core stays pure stdlib, so the decoding is done here
by hand: chunk walking, zlib inflation, scanline unfiltering, and
pixel extraction, following the PNG specification (ISO/IEC 15948).
The encoder goes one step further and spells its own deflate
stream: zlib's compressed bytes vary by the library behind it --
madler zlib and zlib-ng disagree -- and the wire these pictures
ride is certified byte for byte, so the encoded form must be the
same on every build (RFC 1951).

The scope is the census of every picture in the vendored Infocom
resource files: palette images at bit depths 1 to 8, truecolour,
greyscale, and the alpha-bearing forms, none interlaced. Adam7
interlacing and 16-bit depths never appear there and are refused
with their names given.
"""

import struct
import zlib
from dataclasses import dataclass

from voxam.errors import PNGError

SIGNATURE = b"\x89PNG\r\n\x1a\n"

# Chunk layout: a four-byte length, a four-byte name, the payload,
# and a CRC the reader has no reason to distrust.
LENGTH_SIZE = 4
NAME_SIZE = 4
CRC_SIZE = 4

IHDR = b"IHDR"
PLTE = b"PLTE"
TRNS = b"tRNS"
IDAT = b"IDAT"
IEND = b"IEND"

# The colour types and their channel counts: greyscale, truecolour,
# palette indices, greyscale with alpha, truecolour with alpha.
CHANNELS = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}
GREYSCALE = 0
TRUECOLOUR = 2
PALETTE = 3
GREY_ALPHA = 4
TRUE_ALPHA = 6

# The bit depths each colour type allows here: the packed depths
# belong to greyscale and palette images, everything else is one
# full byte per channel.
PACKED_TYPES = (GREYSCALE, PALETTE)
PACKED_DEPTHS = (1, 2, 4, 8)
BYTE_DEPTH = 8

# Scanline filter types (PNG 9.2): each line names how its bytes
# were predicted from the pixels to its left and above.
FILTER_NONE = 0
FILTER_SUB = 1
FILTER_UP = 2
FILTER_AVERAGE = 3
FILTER_PAETH = 4

OPAQUE = 255
FULL_SCALE = 255


@dataclass(frozen=True)
class Picture:
    """A decoded picture: rows of (red, green, blue) pixels.

    Attributes:
        width: The width in pixels.
        height: The height in pixels.
        rows: One tuple of (red, green, blue) triples per row,
            each channel 0 to 255. With no alpha aboard these are
            composed over black -- the terminal a cover picture
            is shown on; with alpha carried they are the straight
            source colors, for a display that can truly blend.
        clear: Which pixels are fully transparent, one tuple of
            flags per row -- or None for a picture with no
            transparency at all. Version 6 art layers its chrome
            with see-through holes, and only full transparency
            matters there (Blorb: Picture Resource Chunks).
        alpha: Per-pixel opacity, one tuple of 0-255 values per
            row -- or None when no pixel is partially
            see-through, in which case the clear flags already
            say everything transparency has to say.
    """

    width: int
    height: int
    rows: tuple[tuple[tuple[int, int, int], ...], ...]
    clear: tuple[tuple[bool, ...], ...] | None = None
    alpha: tuple[tuple[int, ...], ...] | None = None


def decode(
    data: bytes, adapted: tuple[tuple[int, int, int], ...] | None = None
) -> Picture:
    """Decode PNG bytes into rows of RGB pixels.

    Args:
        data: The PNG file bytes.
        adapted: A palette to plot with instead of the file's own
            PLTE -- how an adaptive-palette picture wears the
            Current Palette (Blorb: The Adaptive Palette Chunk).
            Transparency still comes from the file's own tRNS.

    Raises:
        PNGError: If the bytes are not a PNG, or use a feature
            outside the supported scope -- interlacing, 16-bit
            depths -- or are internally inconsistent.
    """

    if not data.startswith(SIGNATURE):
        msg = "the bytes do not begin with the PNG signature"

        raise PNGError(msg)

    header, palette, alphas, compressed = _walk(data)

    if adapted is not None:
        palette = adapted
    width, height, depth, colour_type = header
    channels = CHANNELS[colour_type]
    bits = channels * depth
    stride = (width * bits + 7) // 8
    bytes_back = max(1, bits // 8)

    try:
        inflated = zlib.decompress(compressed)
    except zlib.error as error:
        raise PNGError(f"the image data does not inflate: {error}") from error

    if len(inflated) != height * (stride + 1):
        msg = (
            f"a {width}x{height} image needs {height * (stride + 1)} "
            f"bytes of scanlines, but {len(inflated)} inflated"
        )

        raise PNGError(msg)

    lines = _unfiltered(inflated, height, stride, bytes_back)
    translucent = _translucent(colour_type, alphas)
    alpha = (
        tuple(_alpha_row(line, width, depth, colour_type, alphas) for line in lines)
        if translucent
        else None
    )

    if alpha is not None and not any(
        0 < value < OPAQUE for row in alpha for value in row
    ):
        # Nothing is partially see-through: the clear flags say it
        # all, and the rows stay composed over black as ever, so a
        # picture of holes and solids decodes exactly as it always
        # has.
        alpha = None

    rows = tuple(
        _pixels(line, width, depth, colour_type, palette, alphas)
        if alpha is None
        else _straight_pixels(line, width, depth, colour_type, palette)
        for line in lines
    )
    clear = (
        tuple(_clear_row(line, width, depth, colour_type, alphas) for line in lines)
        if translucent
        else None
    )

    return Picture(width, height, rows, clear, alpha)


def encoded(picture: Picture) -> bytes:
    """Encode a Picture back into PNG bytes, its palette long applied.

    The write-side twin of decode, for art whose true colours only
    exist after the adaptive-palette dance: a display handed an
    adaptive stub's own bytes would paint the placeholder palette,
    so the plotted pixels travel instead (Blorb: The Adaptive
    Palette Chunk). Truecolour when every pixel is opaque,
    truecolour with alpha when any is not; every scanline rides
    unfiltered ahead of one hand-spelled zlib stream, so the bytes
    never vary by build (PNG 9.2, 11.2.4 IDAT; RFC 1951).
    """

    translucent = picture.clear is not None or picture.alpha is not None
    colour_type = TRUE_ALPHA if translucent else TRUECOLOUR
    lines = bytearray()

    for row in range(picture.height):
        lines.append(FILTER_NONE)

        for column in range(picture.width):
            lines.extend(picture.rows[row][column])

            if translucent:
                lines.append(_opacity(picture, row, column))

    # Width, height, one byte per channel, the colour type, and
    # the format's sole compression, filter, and interlace methods
    # -- all zero (PNG 11.2.1 IHDR).
    header = struct.pack(
        ">IIBBBBB", picture.width, picture.height, BYTE_DEPTH, colour_type, 0, 0, 0
    )

    return (
        SIGNATURE
        + _chunked(IHDR, header)
        + _chunked(IDAT, _deflated(bytes(lines)))
        + _chunked(IEND, b"")
    )


def _opacity(picture: Picture, row: int, column: int) -> int:
    """One pixel's alpha: clear flags rule, alpha values refine."""

    if picture.clear is not None and picture.clear[row][column]:
        return 0

    if picture.alpha is not None:
        return picture.alpha[row][column]

    return OPAQUE


def _chunked(name: bytes, payload: bytes) -> bytes:
    """One PNG chunk: length, name, payload, and its CRC (PNG 5.3)."""

    return (
        len(payload).to_bytes(LENGTH_SIZE, "big")
        + name
        + payload
        + zlib.crc32(name + payload).to_bytes(CRC_SIZE, "big")
    )


# The deflate stream _deflated writes: matches no shorter than
# three bytes and no longer than the format allows, found no
# further back than the window reaches (RFC 1951 3.2.3).
_WINDOW = 32768
_LEAST_MATCH = 3
_MOST_MATCH = 258
_END_OF_BLOCK = 256

# Each length symbol's first length and its extra bits, then each
# distance symbol's first distance and its extra bits (RFC 1951
# 3.2.5).
_LENGTH_STARTS = (
    *range(3, 11),
    11,
    13,
    15,
    17,
    19,
    23,
    27,
    31,
    35,
    43,
    51,
    59,
    67,
    83,
    99,
    115,
    131,
    163,
    195,
    227,
    258,
)
_LENGTH_EXTRAS = (
    *(0,) * 8,
    1,
    1,
    1,
    1,
    2,
    2,
    2,
    2,
    3,
    3,
    3,
    3,
    4,
    4,
    4,
    4,
    5,
    5,
    5,
    5,
    0,
)
_DISTANCE_STARTS = (
    1,
    2,
    3,
    4,
    5,
    7,
    9,
    13,
    17,
    25,
    33,
    49,
    65,
    97,
    129,
    193,
    257,
    385,
    513,
    769,
    1025,
    1537,
    2049,
    3073,
    4097,
    6145,
    8193,
    12289,
    16385,
    24577,
)
_DISTANCE_EXTRAS = (0, 0, 0, 0, *(n for n in range(1, 14) for _ in (0, 1)))


class _Writer:
    """Deflate's bitstream (RFC 1951 3.1.1).

    Data elements ride least significant bit first; Huffman codes
    ride most significant bit first, so code reverses them on the
    way in.
    """

    def __init__(self) -> None:
        self._bytes = bytearray()
        self._held = 0
        self._count = 0

    def bits(self, value: int, width: int) -> None:
        """Write width bits of value, least significant first."""

        self._held |= value << self._count
        self._count += width

        while self._count >= 8:  # noqa: PLR2004 -- the byte, drained
            self._bytes.append(self._held & 0xFF)
            self._held >>= 8
            self._count -= 8

    def code(self, value: int, width: int) -> None:
        """Write one Huffman code, most significant bit first."""

        told = 0

        for _ in range(width):
            told = (told << 1) | (value & 1)
            value >>= 1

        self.bits(told, width)

    def flushed(self) -> bytes:
        """The stream, its last partial byte padded with zeros."""

        if self._count:
            self._bytes.append(self._held & 0xFF)
            self._held = 0
            self._count = 0

        return bytes(self._bytes)


def _deflated(data: bytes) -> bytes:
    """A zlib stream whose bytes are the same on every build.

    zlib.compress would be shorter to write and to read, but its
    bytes are the backing library's own business -- zlib-ng and
    madler zlib compress differently -- and these bytes are part
    of the certified wire. So the stream is spelled by hand: the
    zlib dress (RFC 1950) around one final deflate block under the
    fixed Huffman codes, matches found greedily at the last place
    the next three bytes stood (RFC 1951 3.2.6).
    """

    writer = _Writer()

    writer.bits(1, 1)
    writer.bits(1, 2)

    table: dict[bytes, int] = {}
    position = 0

    while position < len(data):
        length, start = _matched(data, position, table)

        if length:
            _length_coded(writer, length)
            _distance_coded(writer, position - start)
        else:
            length = 1

            _symbol(writer, data[position])

        _remembered(data, position, length, table)

        position += length

    _symbol(writer, _END_OF_BLOCK)

    return b"\x78\x01" + writer.flushed() + zlib.adler32(data).to_bytes(4, "big")


def _matched(data: bytes, position: int, table: dict[bytes, int]) -> tuple[int, int]:
    """The longest match at the last place these three bytes stood.

    Zero for none: the tail too short to hold a match, bytes never
    seen, or a stand beyond the window's reach. A match may run
    into itself -- distance one, length many, is how a run spells
    itself (RFC 1951 3.2.3).
    """

    if position + _LEAST_MATCH > len(data):
        return 0, 0

    prior = table.get(data[position : position + _LEAST_MATCH])

    if prior is None or position - prior > _WINDOW:
        return 0, 0

    most = min(_MOST_MATCH, len(data) - position)
    length = _LEAST_MATCH

    while length < most and data[prior + length] == data[position + length]:
        length += 1

    return length, prior


def _remembered(
    data: bytes, position: int, length: int, table: dict[bytes, int]
) -> None:
    """Each covered position becomes its three bytes' last stand."""

    for held in range(position, position + length):
        if held + _LEAST_MATCH <= len(data):
            table[data[held : held + _LEAST_MATCH]] = held


def _symbol(writer: _Writer, symbol: int) -> None:
    """One literal-or-length symbol, fixed codes (RFC 1951 3.2.6)."""

    if symbol <= 143:  # noqa: PLR2004 -- the fixed code's own fences
        writer.code(0x30 + symbol, 8)
    elif symbol <= 255:  # noqa: PLR2004
        writer.code(0x190 + symbol - 144, 9)
    elif symbol <= 279:  # noqa: PLR2004
        writer.code(symbol - 256, 7)
    else:
        writer.code(0xC0 + symbol - 280, 8)


def _length_coded(writer: _Writer, length: int) -> None:
    """A match length: its symbol, then its extra bits."""

    told = len(_LENGTH_STARTS) - 1

    while _LENGTH_STARTS[told] > length:
        told -= 1

    _symbol(writer, 257 + told)

    if _LENGTH_EXTRAS[told]:
        writer.bits(length - _LENGTH_STARTS[told], _LENGTH_EXTRAS[told])


def _distance_coded(writer: _Writer, distance: int) -> None:
    """A match distance: its five-bit code, then its extra bits."""

    told = len(_DISTANCE_STARTS) - 1

    while _DISTANCE_STARTS[told] > distance:
        told -= 1

    writer.code(told, 5)

    if _DISTANCE_EXTRAS[told]:
        writer.bits(distance - _DISTANCE_STARTS[told], _DISTANCE_EXTRAS[told])


def palette(data: bytes) -> tuple[tuple[int, int, int], ...]:
    """A PNG's own PLTE entries, empty for a palette-less picture.

    What a plotted non-adaptive picture carries into the Current
    Palette (Blorb: The Adaptive Palette Chunk).

    Raises:
        PNGError: If the bytes are not a well-formed PNG.
    """

    if not data.startswith(SIGNATURE):
        msg = "the bytes do not begin with the PNG signature"

        raise PNGError(msg)

    _header, entries, _alphas, _compressed = _walk(data)

    return entries


def _walk(
    data: bytes,
) -> tuple[tuple[int, int, int, int], tuple[tuple[int, int, int], ...], bytes, bytes]:
    """Walk the chunks: header, palette, transparency, image data.

    Chunks outside the reader's business -- gamma, text -- pass
    unread, as the specification instructs for ancillary chunks.

    Raises:
        PNGError: For a missing or unsupported header, a palette
            image without a palette, or truncated chunks.
    """

    header: tuple[int, int, int, int] | None = None
    palette: tuple[tuple[int, int, int], ...] = ()
    alphas = b""
    compressed = []
    position = len(SIGNATURE)

    while position + LENGTH_SIZE + NAME_SIZE <= len(data):
        length = int.from_bytes(data[position : position + LENGTH_SIZE], "big")
        name = data[position + LENGTH_SIZE : position + LENGTH_SIZE + NAME_SIZE]
        start = position + LENGTH_SIZE + NAME_SIZE
        payload = data[start : start + length]
        position = start + length + CRC_SIZE

        if len(payload) < length:
            msg = f"the {name.decode('latin-1')} chunk is cut short"

            raise PNGError(msg)

        if name == IHDR:
            header = _header(payload)
        elif name == PLTE:
            triples = struct.iter_unpack("BBB", payload)
            palette = tuple(triples)
        elif name == TRNS:
            alphas = payload
        elif name == IDAT:
            compressed.append(payload)
        elif name == IEND:
            break

    if header is None:
        msg = "the picture has no IHDR header chunk"

        raise PNGError(msg)

    if header[3] == PALETTE and not palette:
        msg = "a palette picture arrived without its PLTE chunk"

        raise PNGError(msg)

    return header, palette, alphas, b"".join(compressed)


def _header(payload: bytes) -> tuple[int, int, int, int]:
    """Read IHDR, refusing what the census says never appears.

    Raises:
        PNGError: For interlacing, a depth and colour type pairing
            outside the supported scope, or an empty image.
    """

    try:
        width, height, depth, colour_type, _compression, _filter, interlace = (
            struct.unpack(">IIBBBBB", payload)
        )
    except struct.error as error:
        raise PNGError(f"the IHDR chunk is malformed: {error}") from error

    if interlace:
        msg = "Adam7 interlaced pictures are not supported"

        raise PNGError(msg)

    if width == 0 or height == 0:
        msg = "the picture has no pixels"

        raise PNGError(msg)

    supported = (
        depth in PACKED_DEPTHS
        if colour_type in PACKED_TYPES
        else depth == BYTE_DEPTH and colour_type in CHANNELS
    )

    if not supported:
        msg = (
            f"colour type {colour_type} at bit depth {depth} is not a supported pairing"
        )

        raise PNGError(msg)

    return width, height, depth, colour_type


def _unfiltered(data: bytes, height: int, stride: int, back: int) -> list[bytearray]:
    """Undo the scanline filters (PNG 9.2).

    Each line opens with a filter byte naming how its bytes were
    predicted -- from the byte one pixel left, the byte above, their
    average, or Paeth's choice among them -- and reconstruction adds
    the prediction back, line by line.

    Raises:
        PNGError: For a filter type the specification does not
            define.
    """

    lines: list[bytearray] = []
    previous = bytearray(stride)
    position = 0

    for _ in range(height):
        filter_type = data[position]
        line = bytearray(data[position + 1 : position + 1 + stride])
        position += 1 + stride

        if filter_type == FILTER_SUB:
            for index in range(back, stride):
                line[index] = (line[index] + line[index - back]) & 0xFF
        elif filter_type == FILTER_UP:
            for index in range(stride):
                line[index] = (line[index] + previous[index]) & 0xFF
        elif filter_type == FILTER_AVERAGE:
            for index in range(stride):
                left = line[index - back] if index >= back else 0
                line[index] = (line[index] + (left + previous[index]) // 2) & 0xFF
        elif filter_type == FILTER_PAETH:
            for index in range(stride):
                left = line[index - back] if index >= back else 0
                above = previous[index]
                corner = previous[index - back] if index >= back else 0
                line[index] = (line[index] + _paeth(left, above, corner)) & 0xFF
        elif filter_type != FILTER_NONE:
            msg = f"scanline filter type {filter_type} is not defined"

            raise PNGError(msg)

        lines.append(line)
        previous = line

    return lines


def _paeth(left: int, above: int, corner: int) -> int:
    """Paeth's predictor: whichever neighbour is nearest the guess."""

    guess = left + above - corner
    to_left = abs(guess - left)
    to_above = abs(guess - above)
    to_corner = abs(guess - corner)

    if to_left <= to_above and to_left <= to_corner:
        return left

    if to_above <= to_corner:
        return above

    return corner


def _pixels(  # noqa: PLR0913, PLR0917 -- one argument per PNG ingredient
    line: bytearray,
    width: int,
    depth: int,
    colour_type: int,
    palette: tuple[tuple[int, int, int], ...],
    alphas: bytes,
) -> tuple[tuple[int, int, int], ...]:
    """Turn one unfiltered scanline into RGB triples.

    Raises:
        PNGError: For a palette index beyond the palette.
    """

    if colour_type == TRUECOLOUR:
        return tuple(
            (line[3 * index], line[3 * index + 1], line[3 * index + 2])
            for index in range(width)
        )

    if colour_type == TRUE_ALPHA:
        return tuple(
            _over_black(
                line[4 * index : 4 * index + 3],
                line[4 * index + 3],
            )
            for index in range(width)
        )

    if colour_type == GREY_ALPHA:
        return tuple(
            _over_black(
                bytes([line[2 * index]] * 3),
                line[2 * index + 1],
            )
            for index in range(width)
        )

    values = _unpacked(line, width, depth)

    if colour_type == GREYSCALE:
        full = (1 << depth) - 1

        return tuple(
            (level, level, level)
            for level in (value * FULL_SCALE // full for value in values)
        )

    return tuple(_from_palette(value, palette, alphas) for value in values)


def _unpacked(line: bytearray, width: int, depth: int) -> list[int]:
    """Read width values of depth bits each, most significant first."""

    if depth == BYTE_DEPTH:
        return list(line[:width])

    per_byte = 8 // depth
    mask = (1 << depth) - 1

    return [
        (line[index // per_byte] >> (8 - depth * (index % per_byte + 1))) & mask
        for index in range(width)
    ]


def _from_palette(
    index: int, palette: tuple[tuple[int, int, int], ...], alphas: bytes
) -> tuple[int, int, int]:
    """One palette entry, composed over black where tRNS says so.

    Raises:
        PNGError: For an index beyond the palette.
    """

    if index >= len(palette):
        msg = f"pixel index {index} points beyond the {len(palette)}-entry palette"

        raise PNGError(msg)

    alpha = alphas[index] if index < len(alphas) else OPAQUE

    return _over_black(bytes(palette[index]), alpha)


def _over_black(channels: bytes | bytearray, alpha: int) -> tuple[int, int, int]:
    """Compose one pixel over black, the screen a cover shows on."""

    return (
        channels[0] * alpha // OPAQUE,
        channels[1] * alpha // OPAQUE,
        channels[2] * alpha // OPAQUE,
    )


def _straight_pixels(
    line: bytearray,
    width: int,
    depth: int,
    colour_type: int,
    palette: tuple[tuple[int, int, int], ...],
) -> tuple[tuple[int, int, int], ...]:
    """One scanline's source colors, uncomposed.

    Only the alpha-bearing color types arrive here: a picture
    with partial alpha keeps its straight colors, and a display
    that can truly blend does the composing itself.

    Raises:
        PNGError: For a palette index beyond the palette.
    """

    if colour_type == TRUE_ALPHA:
        return tuple(
            (line[4 * index], line[4 * index + 1], line[4 * index + 2])
            for index in range(width)
        )

    if colour_type == GREY_ALPHA:
        return tuple(
            (level, level, level)
            for level in (line[2 * index] for index in range(width))
        )

    # Composing over black at full opacity is the identity, so the
    # palette path reuses _from_palette for its bounds check alone.
    return tuple(
        _from_palette(value, palette, b"") for value in _unpacked(line, width, depth)
    )


def _alpha_row(
    line: bytearray, width: int, depth: int, colour_type: int, alphas: bytes
) -> tuple[int, ...]:
    """One scanline's opacity, pixel by pixel."""

    if colour_type == TRUE_ALPHA:
        return tuple(line[4 * index + 3] for index in range(width))

    if colour_type == GREY_ALPHA:
        return tuple(line[2 * index + 1] for index in range(width))

    return tuple(
        alphas[index] if index < len(alphas) else OPAQUE
        for index in _unpacked(line, width, depth)
    )


def _translucent(colour_type: int, alphas: bytes) -> bool:
    """Whether this picture can hold transparency at all."""

    return colour_type in (TRUE_ALPHA, GREY_ALPHA) or (
        colour_type == PALETTE and bool(alphas)
    )


def _clear_row(
    line: bytearray, width: int, depth: int, colour_type: int, alphas: bytes
) -> tuple[bool, ...]:
    """One scanline's fully-transparent flags, pixel by pixel."""

    if colour_type == TRUE_ALPHA:
        return tuple(line[4 * index + 3] == 0 for index in range(width))

    if colour_type == GREY_ALPHA:
        return tuple(line[2 * index + 1] == 0 for index in range(width))

    return tuple(
        index < len(alphas) and alphas[index] == 0
        for index in _unpacked(line, width, depth)
    )
