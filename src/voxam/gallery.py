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
Chunks). The Reso chunk's scaling instructions ride along too:
on a screen roomier than the art's standard window, scalable
pictures grow by the Elbow Room Factor, and picture_data must
report the grown size, because games lay out their whole stage
from those words (Blorb: The Resolution Chunk).
"""

from dataclasses import dataclass, field
from fractions import Fraction

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


@dataclass(frozen=True)
class Scaling:
    """One scalable picture's ratios (Blorb: The Resolution Chunk).

    Attributes:
        standard: The standard ratio the Elbow Room Factor
            multiplies.
        minimum: The floor the result never drops below; None
            means no minimum.
        maximum: The ceiling it never rises above; None means no
            maximum.
    """

    standard: Fraction
    minimum: Fraction | None
    maximum: Fraction | None


@dataclass(frozen=True)
class Resolution:
    """The Reso chunk: a standard window and its scalable art.

    Attributes:
        width: The standard window width in pixels -- the screen
            the author drew for.
        height: The standard window height in pixels.
        scalings: Each scalable picture's ratios, by number. A
            picture with no entry is not scalable at all: one
            image pixel per screen pixel, whatever the room
            (Blorb: The Resolution Chunk).
    """

    width: int
    height: int
    scalings: dict[int, Scaling] = field(default_factory=dict)


class Gallery:
    """A Blorb's drawable art, by number: sizes eager, pixels lazy.

    Attributes:
        release: The release number of the picture file, which the
            picture_data census reports (§15 picture_data).
    """

    def __init__(
        self,
        art: dict[int, bytes | Placard],
        release: int,
        resolution: Resolution | None = None,
    ) -> None:
        """Hang the art: PNG bytes or placards, by picture number.

        Args:
            art: Each picture number's PNG file bytes, or a
                Placard where the Blorb held a Rect.
            release: The picture file's release number.
            resolution: The Reso chunk's scaling instructions;
                None means every picture is non-scalable.
        """

        self._art = art
        self._decoded: dict[int, Picture] = {}
        self.release = release
        self._resolution = resolution

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

    def scale(self, number: int, screen_width: int, screen_height: int) -> Fraction:
        """A picture's scaling ratio on a screen of this size.

        The Elbow Room Factor is how many times the standard
        window fits the screen, the tighter axis deciding; a
        listed picture's standard ratio multiplies it, clamped
        between its minimum and maximum. A picture with no entry
        -- or a Blorb with no Reso chunk -- is not scalable and
        stays at 1 (Blorb: The Resolution Chunk). The ratio is
        exact: a Fraction, so the reported and drawn sizes can
        never drift apart.
        """

        if self._resolution is None:
            return Fraction(1)

        scaling = self._resolution.scalings.get(number)

        if scaling is None:
            return Fraction(1)

        room = min(
            Fraction(screen_width, self._resolution.width),
            Fraction(screen_height, self._resolution.height),
        )
        ratio = room * scaling.standard

        if scaling.minimum is not None and ratio < scaling.minimum:
            return scaling.minimum

        if scaling.maximum is not None and ratio > scaling.maximum:
            return scaling.maximum

        return ratio

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
