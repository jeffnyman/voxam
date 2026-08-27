"""Reading a resource file apart: the census told, the contents freed.

--decompose lists everything a Blorb holds -- every chunk, known
or not, in file order, with the facts Voxam's own decoders can
measure and the cross-references the descriptive chunks make --
and --extract writes the resources out as ordinary files, each in
the format its bytes already are, so a picture opens in a viewer
and a sound plays in a player (Blorb: Introduction).
"""

import struct
from pathlib import Path

from voxam import aiff
from voxam.aamachine.story import FORM_ID as AAM_FORM
from voxam.aamachine.story import Story as AAMachineStory
from voxam.aamachine.text import Speech
from voxam.blorb import (
    FRONTISPIECE_ID,
    GLULX_ID,
    IDENTITY_ID,
    IFICTION_ID,
    INDEX_ID,
    LOOPING_ID,
    PNG_ID,
    RECT_ID,
    RELEASE_ID,
    USAGE_DATA,
    USAGE_EXEC,
    USAGE_PICTURE,
    USAGE_SOUND,
    ZCODE_ID,
    Blorb,
)
from voxam.errors import AIFFError
from voxam.glulx.glk.resources import image_size
from voxam.iff import Chunk, chunk, parse_form

# The sound and data chunk kinds Blorb names beyond what the
# machines play (Blorb: Sound Resource Chunks; Data Resource
# Chunks).
JPEG_ID = b"JPEG"
OGG_ID = b"OGGV"
MOD_ID = b"MOD "
SONG_ID = b"SONG"
TEXT_ID = b"TEXT"
BINARY_ID = b"BINA"
FORM_ID = b"FORM"

# The Z-code header fields a story's own bytes answer (§11.1).
_Z_RELEASE_AT = 2
_Z_SERIAL_AT = 0x12
_Z_SERIAL_END = 0x18

# The Glulx header: magic, then version as major.minor.sub
# (Glulx: The Header).
_GLULX_VERSION_AT = 4

# An IFhd identity: release word, six serial bytes, checksum word
# (Blorb: Game Identifier Chunk).
_IFHD_NEED = 10

# The export names each resource kind earns: the extension its
# bytes already are.
_EXTENSIONS = {
    PNG_ID: ".png",
    JPEG_ID: ".jpg",
    OGG_ID: ".ogg",
    MOD_ID: ".mod",
    SONG_ID: ".song",
    TEXT_ID: ".txt",
    BINARY_ID: ".bin",
}

# The usages' lowercase file-name stems.
_STEMS = {USAGE_PICTURE: "pict", USAGE_SOUND: "snd", USAGE_DATA: "data"}


def decompose_report(name: str, data: bytes) -> str:
    """The census: every chunk in file order, measured and annotated.

    Raises:
        BlorbError: If the bytes are not a well-formed Blorb.
        IFFError: If the FORM itself cannot be walked.
    """

    form, chunks = parse_form(data)

    if form == AAM_FORM:
        return _aamachine_census(name, data, chunks)

    held = Blorb.parse(data)
    placed = {
        piece.chunk.offset: (piece.usage, piece.number) for piece in held.resources
    }

    lines = [f"{name}: FORM IFRS, {len(chunks)} chunks, {len(data):,} bytes", ""]

    for piece in chunks:
        seat = placed.get(piece.offset)
        usage = seat[0].decode("latin-1").strip() if seat else "-"
        number = str(seat[1]) if seat else "-"
        kind = piece.chunk_id.decode("latin-1").strip()
        facts = _measured(piece, seat, held)
        told = f"{usage:<4} {number:>3}  {kind:<4} {facts}"

        lines.append(f"{told.rstrip()} -- {len(piece.payload):,} bytes")

    return "\n".join(lines)


def _aamachine_census(name: str, data: bytes, chunks: tuple[Chunk, ...]) -> str:
    """The census of an Å-machine story: its chunks, measured.

    The HEAD row carries the format's own claims -- version,
    release, serial, and the embedded IFID when one rides -- and
    the META row the bibliography, so the report reads as the
    story introduces itself (Aa-machine: Story file).
    """

    story = AAMachineStory(data)
    speech = Speech(story)
    lines = [f"{name}: FORM AAVM, {len(chunks)} chunks, {len(data):,} bytes", ""]

    for piece in chunks:
        kind = piece.chunk_id.decode("latin-1").strip()
        facts = _aamachine_measured(piece, story, speech)
        told = f"-      -  {kind:<4} {facts}".rstrip()

        lines.append(f"{told} -- {len(piece.payload):,} bytes")

    if story.ifid is not None:
        lines.extend(["", f"IFID {story.ifid}"])

    return "\n".join(lines)


# What each Å-machine chunk is for, by the spec's own account
# (Aa-machine: Story file).
_AAM_NOTES = {
    b"CODE": "bytecode instructions",
    b"DICT": "game dictionary",
    b"FILE": "embedded resource file",
    b"INIT": "initial game state",
    b"LANG": "character set and decoders",
    b"LOOK": "style sheet",
    b"MAPS": "word-to-object maps",
    b"TAGS": "internal object names",
    b"URLS": "table of resources",
    b"WRIT": "compressed text",
}


def _aamachine_measured(piece: Chunk, story: "AAMachineStory", speech: Speech) -> str:
    """One Å-machine chunk's annotation for the census row."""

    if piece.chunk_id == b"HEAD":
        major, minor = story.version

        return f"format {major}.{minor}, release {story.release}, serial {story.serial}"

    if piece.chunk_id == b"META":
        told = [
            story.meta[field] for field in ("title", "author") if field in story.meta
        ]

        return ", ".join(told) if told else "story metadata"

    if piece.chunk_id == b"DICT":
        return f"game dictionary, {len(speech.words)} words"

    return _AAM_NOTES.get(piece.chunk_id, "")


def extracted(data: bytes, directory: Path) -> str:
    """Write the resources out as files; the log comes back.

    Each resource lands in the format its bytes already are --
    AIFF FORMs re-framed whole, header included, so a player can
    open them -- with the story as story.z5 or story.ulx and the
    iFiction record as ifiction.xml. A file already standing is
    never overwritten: it earns a note and the rest proceed.
    Structural chunks -- the index, the identity, the scaling and
    palette instructions -- describe the others and stay home.

    Raises:
        BlorbError: If the bytes are not a well-formed Blorb.
        OSError: If the directory cannot be made or written.
    """

    held = Blorb.parse(data)
    directory.mkdir(parents=True, exist_ok=True)

    lines = []

    for piece in held.resources:
        named = _filed(piece.usage, piece.number, piece.chunk)

        if named is None:
            lines.append(
                f"{_stemmed(piece.usage)}-{piece.number}: "
                f"a {piece.chunk.chunk_id.decode('latin-1').strip()} "
                "carries nothing to export"
            )

            continue

        filename, contents = named

        lines.append(_written(directory, filename, contents))

    if held.ifiction is not None:
        lines.append(_written(directory, "ifiction.xml", held.ifiction))

    return "\n".join(lines)


def _stemmed(usage: bytes) -> str:
    """A usage's lowercase file-name stem."""

    return _STEMS.get(usage, usage.decode("latin-1").strip().lower())


def _written(directory: Path, filename: str, contents: bytes) -> str:
    """Write one file, unless it already stands."""

    target = directory / filename

    if target.exists():
        return f"{filename}: already here, left alone"

    target.write_bytes(contents)

    return f"{filename} -- {len(contents):,} bytes"


def _filed(usage: bytes, number: int, piece: Chunk) -> tuple[str, bytes] | None:
    """One resource's export name and bytes; None for a placeholder."""

    if usage == USAGE_EXEC:
        if piece.chunk_id == ZCODE_ID:
            return f"story.z{piece.payload[0]}", piece.payload

        if piece.chunk_id == GLULX_ID:
            return "story.ulx", piece.payload

        return f"story.{piece.chunk_id.decode('latin-1').strip().lower()}", (
            piece.payload
        )

    if piece.chunk_id == RECT_ID:
        return None

    stem = f"{_stemmed(usage)}-{number}"

    if piece.chunk_id == FORM_ID:
        # A FORM resource is a complete nested IFF file -- an AIFF
        # sound, a data container -- so its header belongs to the
        # export (Blorb: Sound Resource Chunks).
        suffix = ".aiff" if usage == USAGE_SOUND else ".iff"

        return f"{stem}{suffix}", chunk(piece.chunk_id, piece.payload)

    return f"{stem}{_EXTENSIONS.get(piece.chunk_id, '.bin')}", piece.payload


def _measured(piece: Chunk, seat: tuple[bytes, int] | None, held: Blorb) -> str:
    """What Voxam's own decoders can say about one chunk."""

    if piece.chunk_id == ZCODE_ID:
        return (
            f"z{piece.payload[0]} story, release "
            f"{int.from_bytes(piece.payload[_Z_RELEASE_AT : _Z_RELEASE_AT + 2])}, "
            f"serial "
            f"{piece.payload[_Z_SERIAL_AT:_Z_SERIAL_END].decode('latin-1')}"
        )

    if piece.chunk_id == GLULX_ID:
        major = int.from_bytes(piece.payload[_GLULX_VERSION_AT : _GLULX_VERSION_AT + 2])
        minor, sub = piece.payload[_GLULX_VERSION_AT + 2 : _GLULX_VERSION_AT + 4]

        return f"Glulx {major}.{minor}.{sub} story"

    if piece.chunk_id in (PNG_ID, JPEG_ID):
        return _pictured(piece, seat, held)

    if piece.chunk_id == FORM_ID:
        return _sounded(piece, seat, held)

    if piece.chunk_id == RECT_ID:
        return _placarded(piece)

    return _described(piece, held)


def _pictured(piece: Chunk, seat: tuple[bytes, int] | None, held: Blorb) -> str:
    """A picture's size, and its cover credit when Fspc names it."""

    size = image_size(piece.payload)
    facts = f"{size[0]} x {size[1]}" if size is not None else "unmeasurable"

    if seat is not None and held.frontispiece == seat[1]:
        facts += " (the cover)"

    return facts


def _sounded(piece: Chunk, seat: tuple[bytes, int] | None, held: Blorb) -> str:
    """An AIFF sound's shape, and its Loop credit when one repeats."""

    try:
        sound = aiff.decode(chunk(piece.chunk_id, piece.payload))
    except AIFFError as error:
        return f"FORM, not a readable AIFF: {error}"

    facts = (
        f"AIFF, {sound.channels}-channel {sound.sample_size}-bit, {sound.duration:.1f}s"
    )

    if seat is not None and seat[1] in held.loops:
        facts += " (loops until stopped)"

    return facts


def _placarded(piece: Chunk) -> str:
    """A Rect placeholder's declared size (Blorb: Picture Resource Chunks)."""

    if len(piece.payload) >= 8:  # noqa: PLR2004 -- the Rect's own two words
        width, height = struct.unpack(">LL", piece.payload[:8])

        return f"placeholder, {width} x {height}"

    return "placeholder"


def _described(piece: Chunk, held: Blorb) -> str:  # noqa: PLR0911 -- one voice per chunk
    """The descriptive chunks, each speaking its own annotation."""

    if piece.chunk_id == INDEX_ID:
        return f"resource index, {len(held.resources)} entries"

    if piece.chunk_id == FRONTISPIECE_ID:
        return f"names Pict {held.frontispiece} the cover"

    if piece.chunk_id == IDENTITY_ID and len(piece.payload) >= _IFHD_NEED:
        return (
            f"story identity: release {int.from_bytes(piece.payload[:2])}, "
            f"serial {piece.payload[2:8].decode('latin-1')}"
        )

    if piece.chunk_id == RELEASE_ID:
        return f"resource release {held.release}"

    if piece.chunk_id == LOOPING_ID:
        return "looping: " + ", ".join(f"Snd {number}" for number in sorted(held.loops))

    if piece.chunk_id == IFICTION_ID:
        return "iFiction record"

    if piece.chunk_id in (OGG_ID, MOD_ID, SONG_ID):
        return {OGG_ID: "Ogg Vorbis", MOD_ID: "MOD music", SONG_ID: "MOD song"}[
            piece.chunk_id
        ]

    if piece.chunk_id == b"SNam":
        # The story name is big-endian UCS-2, the one chunk Blorb
        # spells wide (Blorb: Story Name Chunk).
        return piece.payload.decode("utf-16-be", errors="replace").strip()[:60]

    if piece.chunk_id in (b"AUTH", b"ANNO", b"(c) "):
        text = piece.payload.decode("latin-1", errors="replace").strip()

        return text[:60] if text else ""

    return ""
