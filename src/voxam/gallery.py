"""The picture gallery: a Blorb's Version 6 art, sized and served.

Version 6 games treat their pictures as data before decoration:
picture_data reads dimensions to lay out windows, and only then is
anything drawn (§15 picture_data). So the gallery answers sizes
cheaply -- a PNG's own IHDR words, a Rect placeholder's eight
bytes -- and decodes pixels lazily, one picture at a time as
draw_picture first asks, which keeps a two-thousand-picture Zork
Zero from paying its whole decode bill at boot. Rect entries are
the Blorb format's invisible pictures: real sizes games measure
and position by, with nothing to draw (Blorb: Picture Resource
Chunks).
"""

from dataclasses import dataclass

from voxam.errors import PNGError
from voxam.png import IHDR, SIGNATURE, Picture, decode

# The IHDR chunk opens every PNG at a fixed seat: the eight-byte
# signature, the chunk length and name, then the width and height
# words (PNG: 5.6 Chunk ordering, 11.2.1 IHDR).
IHDR_NAME_AT = 12
WIDTH_AT = 16
HEIGHT_AT = 20
HEADER_END = 24


@dataclass(frozen=True)
class Placard:
    """A Rect placeholder: a picture-shaped size with no pixels.

    Attributes:
        width: The width in pixels games lay out by.
        height: The height in pixels.
    """

    width: int
    height: int


class Gallery:
    """A Blorb's drawable art, by number: sizes eager, pixels lazy.

    Attributes:
        release: The release number of the picture file, which the
            picture_data census reports (§15 picture_data).
    """

    def __init__(self, art: dict[int, bytes | Placard], release: int) -> None:
        """Hang the art: PNG bytes or placards, by picture number.

        Args:
            art: Each picture number's PNG file bytes, or a
                Placard where the Blorb held a Rect.
            release: The picture file's release number.
        """

        self._art = art
        self._decoded: dict[int, Picture] = {}
        self.release = release

    @property
    def count(self) -> int:
        """How many pictures hang here, placards included."""

        return len(self._art)

    def size(self, number: int) -> tuple[int, int] | None:
        """A picture's height and width in pixels, None for none.

        The order is picture_data's: height first (§15). A PNG
        answers from its IHDR words without decoding a pixel.

        Raises:
            PNGError: If a PNG entry's opening bytes are not the
                signature and IHDR the format requires.
        """

        entry = self._art.get(number)

        if entry is None:
            return None

        if isinstance(entry, Placard):
            return entry.height, entry.width

        return _measured(entry)

    def picture(self, number: int) -> Picture | None:
        """A picture's decoded pixels, None for a placard or none.

        Decoding happens on the first ask and is remembered, the
        cache picture_table only ever hints at (§15).

        Raises:
            PNGError: If a PNG entry cannot be decoded.
        """

        entry = self._art.get(number)

        if entry is None or isinstance(entry, Placard):
            return None

        if number not in self._decoded:
            self._decoded[number] = decode(entry)

        return self._decoded[number]


def _measured(data: bytes) -> tuple[int, int]:
    """A PNG's height and width, read straight off its IHDR.

    Raises:
        PNGError: If the bytes do not open with the signature and
            IHDR chunk every PNG must lead with.
    """

    if (
        len(data) < HEADER_END
        or not data.startswith(SIGNATURE)
        or data[IHDR_NAME_AT:WIDTH_AT] != IHDR
    ):
        msg = "a gallery picture does not open with a PNG signature and IHDR"

        raise PNGError(msg)

    height = int.from_bytes(data[HEIGHT_AT:HEADER_END], "big")
    width = int.from_bytes(data[WIDTH_AT:HEIGHT_AT], "big")

    return height, width
