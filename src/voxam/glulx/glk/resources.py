"""Glk's view of the Blorb resources: pictures, sounds, data files.

voxam.blorb reads the container; this decides what its contents
mean to Glk -- the pictures glk_image_draw names (Glk: Graphics),
the sounds a channel plays (Glk: Sound Resources), and the data
chunks a resource stream opens over (Glk: Resource Streams). The
split matters because the interpreter needs the same container to
find the executable chunk before any of this exists.

Image sizes are read out of the picture bytes here rather than
asked of the display, because glk_image_get_info must answer even
when nothing can be drawn -- a game may lay out a window from the
dimensions and then discover it has no graphics (Glk: Testing for
Graphics Capabilities).
"""

from dataclasses import dataclass

from voxam.blorb import USAGE_DATA, USAGE_PICTURE, USAGE_SOUND, Blorb
from voxam.iff import Chunk, chunk

FORM = b"FORM"
TEXT = b"TEXT"

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_PNG_HEADER_END = 24
_IHDR_WIDTH_AT = 16
_IHDR_HEIGHT_AT = 20

_JPEG_SIGNATURE = b"\xff\xd8"
_MARKER = 0xFF
# The start-of-frame markers carry the image dimensions. C4, C8,
# and CC sit in the SOF numbering but are not SOFs: they are the
# Huffman table, JPEG extension, and arithmetic coding markers.
_JPEG_SOF = frozenset(range(0xC0, 0xD0)) - {0xC4, 0xC8, 0xCC}
_STANDALONE_LOW = 0xD0
_STANDALONE_HIGH = 0xD7
_START_OF_IMAGE = 0xD8
_TEMPORARY = 0x01
_SOF_NEED = 9
_SOF_HEIGHT_AT = 5
_SOF_WIDTH_AT = 7


@dataclass(frozen=True)
class ImageInfo:
    """One picture resource, measured.

    Attributes:
        number: The number the game asks for it by.
        kind: The Blorb chunk type: PNG followed by a space, or
            JPEG (Blorb: Picture Resource Chunks).
        data: The picture bytes, ready for a display to decode.
        width: The width in pixels.
        height: The height in pixels.
    """

    number: int
    kind: bytes
    data: bytes
    width: int
    height: int


def image_size(data: bytes) -> tuple[int, int] | None:
    """Read the pixel dimensions of a PNG or a JPEG.

    PNG requires the IHDR chunk to come first, so width and height
    sit at fixed offsets; a JPEG hides them in a start-of-frame
    segment that has to be walked to.
    """

    if data.startswith(_PNG_SIGNATURE) and len(data) >= _PNG_HEADER_END:
        return (
            int.from_bytes(data[_IHDR_WIDTH_AT : _IHDR_WIDTH_AT + 4], "big"),
            int.from_bytes(data[_IHDR_HEIGHT_AT : _IHDR_HEIGHT_AT + 4], "big"),
        )

    if data.startswith(_JPEG_SIGNATURE):
        return _jpeg_size(data)

    return None


def _jpeg_size(data: bytes) -> tuple[int, int] | None:
    """Walk JPEG segments until a start-of-frame marker turns up."""

    position = 2
    end = len(data)

    while position + 4 <= end:
        if data[position] != _MARKER:
            return None

        marker = data[position + 1]

        if (
            marker in (_START_OF_IMAGE, _TEMPORARY)
            or _STANDALONE_LOW <= marker <= _STANDALONE_HIGH
        ):
            # Standalone markers carry no length word.
            position += 2

            continue

        length = int.from_bytes(data[position + 2 : position + 4], "big")

        if marker in _JPEG_SOF:
            if position + _SOF_NEED > end:
                return None

            return (
                int.from_bytes(
                    data[position + _SOF_WIDTH_AT : position + _SOF_WIDTH_AT + 2],
                    "big",
                ),
                int.from_bytes(
                    data[position + _SOF_HEIGHT_AT : position + _SOF_HEIGHT_AT + 2],
                    "big",
                ),
            )

        position += 2 + length

    return None


class Resources:
    """The pictures, sounds, and data available to a game.

    An instance with no Blorb behind it answers "nothing here" to
    everything, which is the right answer for a bare .ulx story.

    Attributes:
        blorb: The container, or None without one.
    """

    def __init__(self, blorb: Blorb | None = None) -> None:
        """Stand in front of a container, or of nothing."""

        self.blorb = blorb
        self._images: dict[int, ImageInfo | None] = {}

    def image(self, number: int) -> ImageInfo | None:
        """Look up a picture, measuring it on first use.

        A picture whose dimensions cannot be read answers None: a
        size glk_image_get_info cannot report is a picture the
        game cannot lay out (Glk: Graphics).
        """

        if number in self._images:
            return self._images[number]

        info = None
        found = (
            self.blorb.resource(USAGE_PICTURE, number)
            if self.blorb is not None
            else None
        )

        if found is not None:
            data = found.chunk.payload
            size = image_size(data)

            if size is not None:
                info = ImageInfo(number, found.chunk.chunk_id, data, *size)

        self._images[number] = info

        return info

    def sound(self, number: int) -> bytes | None:
        """Return a sound resource's bytes, or None if absent.

        AIFF sounds are stored as FORM chunks, and an AIFF file
        *is* that FORM -- header included (Blorb: Sound Resource
        Chunks). Handing an audio decoder the body alone would
        give it a file starting at "AIFF" with no container.
        """

        found = (
            self.blorb.resource(USAGE_SOUND, number) if self.blorb is not None else None
        )

        return None if found is None else _contents(found.chunk)

    def data(self, number: int) -> tuple[bytes, bool] | None:
        """Return a data resource as (bytes, is_text).

        Blorb marks a data chunk TEXT or BINA (Blorb: Data
        Resource Chunks); the distinction only matters when the
        resource is opened as a Unicode stream, where text means
        UTF-8 and binary means four-byte words (Glk: Resource
        Streams).
        """

        found = (
            self.blorb.resource(USAGE_DATA, number) if self.blorb is not None else None
        )

        if found is None:
            return None

        if found.chunk.chunk_id == FORM:
            return _contents(found.chunk), False

        return found.chunk.payload, found.chunk.chunk_id == TEXT


def _contents(piece: Chunk) -> bytes:
    """A chunk's bytes: the whole thing for a FORM, the body else.

    A FORM resource is a complete nested IFF file -- an AIFF
    sound, or a data container -- so its header belongs to the
    contents. Everything else (PNG, JPEG, TEXT, BINA) is raw
    payload.
    """

    if piece.chunk_id == FORM:
        return chunk(piece.chunk_id, piece.payload)

    return piece.payload
