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
from pathlib import Path
from typing import Self

from voxam import aiff
from voxam.errors import BlorbError, IFFError
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
# the one Voxam can draw.
PNG_ID = b"PNG "

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
    """

    def __init__(
        self,
        resources: tuple[Resource, ...],
        frontispiece: int | None,
        identity: bytes | None,
        loops: frozenset[int],
    ) -> None:
        """Hold a parsed index; parse() and load() build these."""

        self.resources = resources
        self.frontispiece = frontispiece
        self.identity = identity
        self.loops = loops

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

        return cls(resources, frontispiece, identity, _loops(chunks))

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
