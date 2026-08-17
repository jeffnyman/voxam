"""Blorb resource files: pictures, sounds, and packaged stories.

A Blorb file is an IFF FORM of type IFRS holding a resource index
and the resources it points at (Blorb: Resource Index Chunk). Two
arrangements matter here: a story packaged inside the Blorb as an
Exec resource -- the single-file .zblorb of modern games -- and the
sidecar Blorb that carries only pictures and sounds for a story
file living beside it, which is how Infocom's re-released games
ship their audio and art.

This module reads the container and the index; what to do with a
PNG or an AIFF is the frontend's business, in releases to come.
"""

from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Self

from voxam import aiff
from voxam.errors import BlorbError, IFFError
from voxam.gallery import Gallery, Placard, Resolution, Scaling
from voxam.iff import Chunk, chunk, parse_form
from voxam.zmachine.quetzal import IDENTITY_SIZE, story_identity
from voxam.zmachine.story import Story

# The FORM type of a resource file (Blorb: Introduction).
RESOURCE_FORM = b"IFRS"

# The resource index: a count, then 12-byte entries of usage,
# number, and the file offset of the resource's chunk (Blorb:
# Resource Index Chunk). Exactly one index must appear.
INDEX_ID = b"RIdx"
COUNT_SIZE = 4
ENTRY_SIZE = 12

# The usages this reader knows (Blorb: Resource Index Chunk), and
# the executable format that concerns a Z-Machine (Blorb: Code
# Resource Chunks). An Exec resource is numbered 0.
USAGE_PICTURE = b"Pict"
USAGE_SOUND = b"Snd "
USAGE_EXEC = b"Exec"
ZCODE_ID = b"ZCOD"
EXEC_NUMBER = 0

# Pictures arrive as PNG or JPEG chunks, with Rect placeholders
# among the Version 6 art (Blorb: Picture Resource Chunks); PNG is
# the one Voxam can draw. A Rect carries two four-byte words --
# width, then height -- and no pixels at all.
PNG_ID = b"PNG "
RECT_ID = b"Rect"
RECT_SIZE = 8

# The resource file's release number, a two-byte word the
# picture_data census reports (Blorb: Release Number Chunk).
RELEASE_ID = b"RelN"
RELEASE_SIZE = 2

# The resolution chunk: six words of standard, minimum, and
# maximum window sizes, then 28-byte entries of a picture number
# and its three scaling ratios (Blorb: The Resolution Chunk).
RESOLUTION_ID = b"Reso"
RESOLUTION_HEADER = 24
RESOLUTION_ENTRY = 28
WORD_SIZE = 4

# The adaptive palette chunk: four-byte picture numbers naming the
# legacy Infocom chrome that wears the palette of whatever scene
# was plotted last (Blorb: The Adaptive Palette Chunk).
ADAPTIVE_ID = b"APal"

# The baked-palette chunk, Bocfel's extension to the adaptive
# dance: 12-byte records of a scene picture, an adaptive picture,
# and the replacement picture the packager pre-dressed in that
# scene's palette -- plotted in the adaptive picture's stead
# (Bocfel: The Bocfel Adaptive Palette Chunk).
BAKED_ID = b"BPal"
BAKED_ENTRY_SIZE = 12

# Optional chunks: the frontispiece names a picture resource to
# show as cover art (Blorb: Frontispiece Chunk), and the game
# identifier carries the same release, serial, and checksum bytes
# a Quetzal save uses, so a resource file can be matched to its
# story (Blorb: Game Identifier Chunk).
FRONTISPIECE_ID = b"Fspc"
IDENTITY_ID = b"IFhd"

# In Version 5 and later the sound_effect opcode says whether a
# sound repeats; a Version 3 game cannot, so its Blorb may carry a
# Loop chunk instead: eight-byte entries pairing a sound number
# with a flag, 1 to play the sound once and 0 to repeat it until
# stopped -- and an absent entry means once (Blorb: The Looping
# Chunk).
LOOPING_ID = b"Loop"
LOOP_ENTRY_SIZE = 8
PLAY_ONCE = 1


@dataclass(frozen=True)
class Resource:
    """One indexed resource: its usage, number, and chunk.

    Attributes:
        usage: The four-byte usage: Pict, Snd , or Exec.
        number: The number the game knows the resource by.
        chunk: The chunk the index points at.
    """

    usage: bytes
    number: int
    chunk: Chunk


class Blorb:
    """A parsed resource file: the index made walkable.

    Attributes:
        resources: Every indexed resource, in index order.
        frontispiece: The picture number offered as cover art, or
            None without one.
        identity: The IFhd payload naming the story these
            resources belong to, or None without one.
        loops: The sounds a Version 3 game plays on repeat until
            stopped, by number (Blorb: The Looping Chunk); empty
            without a Loop chunk, and ignored from Version 5 on,
            where the opcode itself says.
        release: The resource file's release number, 0 without a
            RelN chunk (Blorb: Release Number Chunk).
        resolution: The Reso chunk's scaling instructions, or
            None without one -- every picture non-scalable
            (Blorb: The Resolution Chunk).
        adaptive: The pictures whose palettes adapt to the scene
            plotted before them; empty without an APal chunk
            (Blorb: The Adaptive Palette Chunk).
        baked: Each (scene, adaptive) pair's pre-dressed
            replacement picture; empty without a BPal chunk
            (Bocfel: The Bocfel Adaptive Palette Chunk).
    """

    def __init__(  # noqa: PLR0913 -- one seat per optional chunk
        self,
        resources: tuple[Resource, ...],
        frontispiece: int | None,
        identity: bytes | None,
        loops: frozenset[int],
        *,
        release: int = 0,
        resolution: Resolution | None = None,
        adaptive: frozenset[int] = frozenset(),
        baked: dict[tuple[int, int], int] | None = None,
    ) -> None:
        """Hold a parsed index; parse() and load() build these."""

        self.resources = resources
        self.frontispiece = frontispiece
        self.identity = identity
        self.loops = loops
        self.release = release
        self.resolution = resolution
        self.adaptive = adaptive
        self.baked = baked or {}

    @classmethod
    def load(cls, path: Path) -> Self:
        """Read and parse a Blorb file from disk.

        Raises:
            BlorbError: If the bytes are not a well-formed Blorb.
            OSError: If the file cannot be read.
        """

        return cls.parse(path.read_bytes())

    @classmethod
    def parse(cls, data: bytes) -> Self:
        """Parse Blorb bytes into an indexed resource set.

        Raises:
            BlorbError: If the bytes are not an IFRS FORM, the
                index is missing, doubled, or malformed, or an
                entry points at no chunk.
        """

        try:
            form_type, chunks = parse_form(data)
        except IFFError as error:
            raise BlorbError(str(error)) from error

        if form_type != RESOURCE_FORM:
            msg = (
                f"the FORM type is {form_type!r}, not the IFRS of a "
                f"resource file (Blorb: Introduction)"
            )

            raise BlorbError(msg)

        indexes = [piece for piece in chunks if piece.chunk_id == INDEX_ID]

        if len(indexes) != 1:
            msg = (
                f"a Blorb carries exactly one RIdx resource index; "
                f"this one has {len(indexes)} (Blorb: Resource Index Chunk)"
            )

            raise BlorbError(msg)

        by_offset = {piece.offset: piece for piece in chunks}
        resources = tuple(_entries(indexes[0].payload, by_offset))
        frontispiece = _frontispiece(chunks)
        identity = next(
            (piece.payload for piece in chunks if piece.chunk_id == IDENTITY_ID),
            None,
        )

        return cls(
            resources,
            frontispiece,
            identity,
            _loops(chunks),
            release=_release(chunks),
            resolution=_resolution(chunks),
            adaptive=_adaptive(chunks),
            baked=_baked(chunks),
        )

    def resource(self, usage: bytes, number: int) -> Resource | None:
        """The resource a game asks for by usage and number."""

        for piece in self.resources:
            if piece.usage == usage and piece.number == number:
                return piece

        return None

    @property
    def story(self) -> bytes | None:
        """The packaged Z-code story, when the Blorb carries one.

        An Exec resource is numbered 0 (Blorb: Resource Index
        Chunk), and only the ZCOD executable format belongs to this
        machine (Blorb: Code Resource Chunks).
        """

        executable = self.resource(USAGE_EXEC, EXEC_NUMBER)

        if executable is None or executable.chunk.chunk_id != ZCODE_ID:
            return None

        return executable.chunk.payload

    @property
    def cover(self) -> Resource | None:
        """The picture to show before play, when one presents itself.

        The Fspc chunk names it outright (Blorb: Frontispiece
        Chunk). Failing that, a resource file carrying exactly one
        picture offers that picture -- Beyond Zork ships its splash
        so -- while the big Version 6 art sets, hundreds of scene
        pictures with no Fspc, offer nothing rather than a guess.
        """

        if self.frontispiece is not None:
            return self.resource(USAGE_PICTURE, self.frontispiece)

        pictures = [piece for piece in self.resources if piece.usage == USAGE_PICTURE]

        if len(pictures) == 1:
            return pictures[0]

        return None

    def gallery(self) -> Gallery:
        """The Version 6 art as a gallery: sizes eager, pixels lazy.

        PNG pictures and Rect placeholders make the census; a
        JPEG -- no Infocom Version 6 set carries one -- is left
        out, because a picture Voxam cannot draw is not
        "available" in picture_data's sense (§15).

        Raises:
            BlorbError: If a Rect does not hold its eight
                width-and-height bytes.
        """

        art: dict[int, bytes | Placard] = {}

        for piece in self.resources:
            if piece.usage != USAGE_PICTURE:
                continue

            if piece.chunk.chunk_id == PNG_ID:
                art[piece.number] = piece.chunk.payload
            elif piece.chunk.chunk_id == RECT_ID:
                art[piece.number] = _placard(piece)

        return Gallery(
            art,
            self.release,
            self.resolution,
            adaptive=self.adaptive,
            baked=self.baked,
        )

    def sounds(self) -> dict[int, aiff.Sound]:
        """Decode every sampled sound resource, by number.

        Blorb sounds are AIFF FORMs (Blorb: Sound Resource
        Chunks), stored whole -- reframing a resource's chunk
        recovers the FORM file the decoder reads.

        Raises:
            AIFFError: If a sound resource is not a decodable
                AIFF -- the OGG and MOD formats Blorb also allows
                never appear in the vendored resource files.
        """

        return {
            piece.number: aiff.decode(chunk(piece.chunk.chunk_id, piece.chunk.payload))
            for piece in self.resources
            if piece.usage == USAGE_SOUND
        }

    def matches(self, story: Story) -> bool:
        """Whether the resources name this story.

        The identity carries the same bytes a Quetzal save uses
        (Blorb: Game Identifier Chunk). A Blorb without one matches
        anything: the check is optional, and absence is not
        disagreement.
        """

        if self.identity is None:
            return True

        return self.identity[:IDENTITY_SIZE] == story_identity(story)

    def described(self) -> str:
        """A one-line census for the session banner."""

        pictures = sum(1 for piece in self.resources if piece.usage == USAGE_PICTURE)
        sounds = sum(1 for piece in self.resources if piece.usage == USAGE_SOUND)
        parts = []

        if pictures:
            parts.append(f"{pictures} picture{'s' if pictures != 1 else ''}")

        if sounds:
            parts.append(f"{sounds} sound{'s' if sounds != 1 else ''}")

        if self.story is not None:
            parts.append("a packaged story")

        return ", ".join(parts) if parts else "no resources"


def _entries(payload: bytes, by_offset: dict[int, Chunk]) -> list[Resource]:
    """Decode the index entries and resolve their chunks.

    Raises:
        BlorbError: If the count disagrees with the payload size,
            or an entry's offset points at no chunk.
    """

    if len(payload) < COUNT_SIZE:
        msg = "the RIdx chunk is too short to hold its own count"

        raise BlorbError(msg)

    count = int.from_bytes(payload[:COUNT_SIZE], "big")

    if len(payload) != COUNT_SIZE + count * ENTRY_SIZE:
        msg = (
            f"the RIdx count of {count} needs "
            f"{COUNT_SIZE + count * ENTRY_SIZE} bytes, but the chunk "
            f"holds {len(payload)} (Blorb: Resource Index Chunk)"
        )

        raise BlorbError(msg)

    resources = []

    for index in range(count):
        start = COUNT_SIZE + index * ENTRY_SIZE
        usage = payload[start : start + 4]
        number = int.from_bytes(payload[start + 4 : start + 8], "big")
        offset = int.from_bytes(payload[start + 8 : start + 12], "big")

        if offset not in by_offset:
            msg = (
                f"the {usage!r} {number} entry points at offset "
                f"{offset}, where no chunk begins (Blorb: Resource "
                f"Index Chunk)"
            )

            raise BlorbError(msg)

        resources.append(Resource(usage, number, by_offset[offset]))

    return resources


def _loops(chunks: tuple[Chunk, ...]) -> frozenset[int]:
    """The repeat-forever sound numbers, from at most one Loop chunk.

    A flag of zero repeats the sound until it is stopped; any
    other flag, or no entry at all, plays it once (Blorb: The
    Looping Chunk).

    Raises:
        BlorbError: For a doubled Loop chunk, or one whose length
            is not a whole number of eight-byte entries.
    """

    found = [piece for piece in chunks if piece.chunk_id == LOOPING_ID]

    if not found:
        return frozenset()

    if len(found) > 1:
        msg = (
            f"{len(found)} Loop chunks appear, but there may not "
            f"be more than one (Blorb: The Looping Chunk)"
        )

        raise BlorbError(msg)

    payload = found[0].payload

    if len(payload) % LOOP_ENTRY_SIZE:
        msg = (
            f"a Loop chunk is eight-byte entries, but this one "
            f"holds {len(payload)} bytes (Blorb: The Looping Chunk)"
        )

        raise BlorbError(msg)

    return frozenset(
        int.from_bytes(payload[start : start + 4], "big")
        for start in range(0, len(payload), LOOP_ENTRY_SIZE)
        if int.from_bytes(payload[start + 4 : start + 8], "big") != PLAY_ONCE
    )


def _placard(piece: Resource) -> Placard:
    """A Rect resource's size, made a placard.

    Raises:
        BlorbError: If the payload is not the eight bytes of a
            width word and a height word (Blorb: Picture Resource
            Chunks).
    """

    payload = piece.chunk.payload

    if len(payload) != RECT_SIZE:
        msg = (
            f"picture {piece.number} is a Rect of {len(payload)} bytes, "
            f"not the eight of a width and height (Blorb: Picture "
            f"Resource Chunks)"
        )

        raise BlorbError(msg)

    return Placard(
        width=int.from_bytes(payload[:4], "big"),
        height=int.from_bytes(payload[4:], "big"),
    )


def _release(chunks: tuple[Chunk, ...]) -> int:
    """The release number, from at most one RelN chunk.

    Raises:
        BlorbError: For a doubled RelN, or one that is not a
            two-byte word (Blorb: Release Number Chunk).
    """

    found = [piece for piece in chunks if piece.chunk_id == RELEASE_ID]

    if not found:
        return 0

    if len(found) > 1:
        msg = (
            f"{len(found)} RelN chunks appear, but there may not be "
            f"more than one (Blorb: Release Number Chunk)"
        )

        raise BlorbError(msg)

    if len(found[0].payload) != RELEASE_SIZE:
        msg = "the RelN chunk does not hold its two release-number bytes"

        raise BlorbError(msg)

    return int.from_bytes(found[0].payload, "big")


def _adaptive(chunks: tuple[Chunk, ...]) -> frozenset[int]:
    """The adaptive picture numbers, from at most one APal chunk.

    Raises:
        BlorbError: For a doubled APal, or one whose length is
            not a whole number of four-byte entries (Blorb: The
            Adaptive Palette Chunk).
    """

    found = [piece for piece in chunks if piece.chunk_id == ADAPTIVE_ID]

    if not found:
        return frozenset()

    if len(found) > 1:
        msg = (
            f"{len(found)} APal chunks appear, but there may not be "
            f"more than one (Blorb: The Adaptive Palette Chunk)"
        )

        raise BlorbError(msg)

    payload = found[0].payload

    if len(payload) % WORD_SIZE:
        msg = (
            f"an APal chunk is four-byte picture numbers, but this "
            f"one holds {len(payload)} bytes (Blorb: The Adaptive "
            f"Palette Chunk)"
        )

        raise BlorbError(msg)

    return frozenset(
        int.from_bytes(payload[start : start + WORD_SIZE], "big")
        for start in range(0, len(payload), WORD_SIZE)
    )


def _baked(chunks: tuple[Chunk, ...]) -> dict[tuple[int, int], int]:
    """The pre-dressed replacements, from at most one BPal chunk.

    Each 12-byte record maps a scene picture and an adaptive
    picture to the replacement whose palette the packager already
    applied (Bocfel: The Bocfel Adaptive Palette Chunk).

    Raises:
        BlorbError: For a doubled BPal, or one whose length is
            not a whole number of 12-byte records.
    """

    found = [piece for piece in chunks if piece.chunk_id == BAKED_ID]

    if not found:
        return {}

    if len(found) > 1:
        msg = (
            f"{len(found)} BPal chunks appear, but there may not be "
            f"more than one (Bocfel: The Bocfel Adaptive Palette Chunk)"
        )

        raise BlorbError(msg)

    payload = found[0].payload

    if len(payload) % BAKED_ENTRY_SIZE:
        msg = (
            f"a BPal chunk is 12-byte records, but this one holds "
            f"{len(payload)} bytes (Bocfel: The Bocfel Adaptive "
            f"Palette Chunk)"
        )

        raise BlorbError(msg)

    records = {}

    for start in range(0, len(payload), BAKED_ENTRY_SIZE):
        scene = int.from_bytes(payload[start : start + WORD_SIZE], "big")
        adaptive = int.from_bytes(
            payload[start + WORD_SIZE : start + 2 * WORD_SIZE], "big"
        )
        replacement = int.from_bytes(
            payload[start + 2 * WORD_SIZE : start + BAKED_ENTRY_SIZE], "big"
        )
        records[(scene, adaptive)] = replacement

    return records


def _resolution(chunks: tuple[Chunk, ...]) -> Resolution | None:
    """The scaling instructions, from at most one Reso chunk.

    Raises:
        BlorbError: For a doubled Reso; one whose length is not
            the six-word header plus whole 28-byte entries; a
            zero standard window dimension; or a half-zero ratio
            fraction, which the spec calls illegal (Blorb: The
            Resolution Chunk).
    """

    found = [piece for piece in chunks if piece.chunk_id == RESOLUTION_ID]

    if not found:
        return None

    if len(found) > 1:
        msg = (
            f"{len(found)} Reso chunks appear, but there may not be "
            f"more than one (Blorb: The Resolution Chunk)"
        )

        raise BlorbError(msg)

    payload = found[0].payload

    if (
        len(payload) < RESOLUTION_HEADER
        or (len(payload) - RESOLUTION_HEADER) % RESOLUTION_ENTRY
    ):
        msg = (
            f"a Reso chunk is a 24-byte header and 28-byte entries, "
            f"but this one holds {len(payload)} bytes (Blorb: The "
            f"Resolution Chunk)"
        )

        raise BlorbError(msg)

    width = int.from_bytes(payload[:WORD_SIZE], "big")
    height = int.from_bytes(payload[WORD_SIZE : 2 * WORD_SIZE], "big")

    if not width or not height:
        msg = (
            f"the Reso standard window is {width} by {height}, but "
            f"px and py must be non-zero (Blorb: The Resolution Chunk)"
        )

        raise BlorbError(msg)

    scalings = {}

    for start in range(RESOLUTION_HEADER, len(payload), RESOLUTION_ENTRY):
        words = [
            int.from_bytes(payload[at : at + WORD_SIZE], "big")
            for at in range(start, start + RESOLUTION_ENTRY, WORD_SIZE)
        ]
        number = words[0]
        scalings[number] = Scaling(
            standard=_standard_ratio(number, words[1], words[2]),
            minimum=_limit_ratio(number, words[3], words[4]),
            maximum=_limit_ratio(number, words[5], words[6]),
        )

    return Resolution(width, height, scalings)


def _standard_ratio(number: int, numerator: int, denominator: int) -> Fraction:
    """A picture's standard ratio, which has no zero form.

    Raises:
        BlorbError: For a zero denominator: only the minimum and
            maximum ratios may be zero, and only whole (Blorb:
            The Resolution Chunk).
    """

    if not denominator:
        msg = (
            f"picture {number}'s standard ratio divides by zero "
            f"(Blorb: The Resolution Chunk)"
        )

        raise BlorbError(msg)

    return Fraction(numerator, denominator)


def _limit_ratio(number: int, numerator: int, denominator: int) -> Fraction | None:
    """A minimum or maximum ratio; zero-over-zero means no limit.

    Raises:
        BlorbError: When only half the fraction is zero, which
            the spec calls illegal (Blorb: The Resolution Chunk).
    """

    if not numerator and not denominator:
        return None

    if not numerator or not denominator:
        msg = (
            f"picture {number} has a half-zero ratio of {numerator}/"
            f"{denominator}, which is illegal (Blorb: The Resolution "
            f"Chunk)"
        )

        raise BlorbError(msg)

    return Fraction(numerator, denominator)


def _frontispiece(chunks: tuple[Chunk, ...]) -> int | None:
    """The cover picture's number, from at most one Fspc chunk.

    Raises:
        BlorbError: For a doubled Fspc, or one without its four
            number bytes (Blorb: Frontispiece Chunk).
    """

    found = [piece for piece in chunks if piece.chunk_id == FRONTISPIECE_ID]

    if not found:
        return None

    if len(found) > 1:
        msg = (
            f"{len(found)} Fspc chunks appear, but there may not be "
            f"more than one (Blorb: Frontispiece Chunk)"
        )

        raise BlorbError(msg)

    if len(found[0].payload) != COUNT_SIZE:
        msg = "the Fspc chunk does not hold its four picture-number bytes"

        raise BlorbError(msg)

    return int.from_bytes(found[0].payload, "big")
