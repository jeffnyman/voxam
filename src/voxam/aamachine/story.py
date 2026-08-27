"""The Å-machine story file: the AAVM form read whole.

The third machine's stories are IFF: form AAVM, HEAD first, and a
CRC-32 running over seven starred chunks in the spec's own order.
An interpreter may treat the whole file as one read-only address
space (Aa-machine specification 1.0: Story file); this reader
keeps the chunks and the header's claims, everything verified
loud at the door -- a story that lies about its checksum is a
story worth refusing before it runs.

The compatibility ledger is deliberate: the reader speaks the
community fork's 1.0 specification and accepts the 0.x stories
the Dialog compilers of the world actually emit -- the minor
version is backward-compatible by the spec's own numbering, and
a major version from the future is refused by name.
"""

import zlib

from voxam.errors import AAMachineError
from voxam.iff import Chunk, parse_form

FORM_ID = b"AAVM"
HEAD_ID = b"HEAD"
META_ID = b"META"
FILE_ID = b"FILE"

# The chunks the HEAD's CRC-32 runs over, in the spec's own,
# deliberate order (Aa-machine: Story file).
SUMMED = (b"LOOK", b"LANG", b"MAPS", b"DICT", b"INIT", b"CODE", b"WRIT")

# The fixed header: version pair, word size, shift amount,
# release, serial, checksum, and the three area sizes; the
# optional IFID rides after (Aa-machine: HEAD).
HEAD_SIZE = 22
IFID_SIZE = 46

# The only word size the specification currently speaks.
WORD_SIZE = 2

# The newest major version this reader understands: the community
# fork's own. Minor versions are backward-compatible by the
# spec's numbering, so every 0.x story is welcome here too.
SUPPORTED_MAJOR = 1

# The META chunk's identifiers, by the names the spec gives them
# (Aa-machine: META).
META_NAMES = {1: "title", 2: "author", 3: "noun", 4: "blurb", 5: "date"}


class Story:
    """One parsed Å-machine story, its header's claims verified.

    Attributes:
        version: The file format version as (major, minor).
        word_size: The machine word size in bytes, currently 2.
        shift: The shift amount for short and long string pointers.
        release: The story's release number.
        serial: The six-character serial, as the header spells it.
        checksum: The HEAD's CRC-32 claim, already verified.
        heap_size: The heap/env/choice area size, in words.
        aux_size: The aux/trail area size, in words.
        ram_size: The random access area size, in words.
        ifid: The embedded IFID's UUID, uppercased; None when the
            optional field is absent (Aa-machine: HEAD).
        meta: The META chunk's bibliography by field name --
            title, author, noun, blurb, date -- empty without one.
        chunks: Every chunk, in file order.
        files: The FILE chunks alone, which may repeat.
    """

    def __init__(self, data: bytes) -> None:
        """Parse and verify one story file's bytes.

        Raises:
            AAMachineError: For a form that is not AAVM, a HEAD
                missing, late, or short, a word size or major
                version this reader does not speak, a summed
                chunk missing, or a checksum that disagrees.
            IFFError: If the FORM itself cannot be walked.
        """

        form, chunks = parse_form(data)

        if form != FORM_ID:
            msg = (
                f"an Å-machine story is FORM AAVM, not FORM "
                f"{form.decode('ascii', 'replace')} (Aa-machine: Story file)"
            )

            raise AAMachineError(msg)

        if not chunks or chunks[0].chunk_id != HEAD_ID:
            msg = "HEAD must be the first chunk in the form (Aa-machine: Story file)"

            raise AAMachineError(msg)

        head = chunks[0].payload

        if len(head) < HEAD_SIZE:
            msg = (
                f"the HEAD holds {len(head)} bytes, but the fixed header "
                f"is {HEAD_SIZE} (Aa-machine: HEAD)"
            )

            raise AAMachineError(msg)

        self.version = (head[0], head[1])

        if self.version[0] > SUPPORTED_MAJOR:
            msg = (
                f"story format {self.version[0]}.{self.version[1]} is from "
                f"a future specification; this reader speaks up to "
                f"{SUPPORTED_MAJOR}.x (Aa-machine: Story file)"
            )

            raise AAMachineError(msg)

        self.word_size = head[2]

        if self.word_size != WORD_SIZE:
            msg = (
                f"a word of {self.word_size} bytes; {WORD_SIZE} is the only "
                f"size the specification speaks (Aa-machine: Runtime data)"
            )

            raise AAMachineError(msg)

        self.shift = head[3]
        self.release = int.from_bytes(head[4:6], "big")
        self.serial = head[6:12].decode("ascii", "replace")
        self.checksum = int.from_bytes(head[12:16], "big")
        self.heap_size = int.from_bytes(head[16:18], "big")
        self.aux_size = int.from_bytes(head[18:20], "big")
        self.ram_size = int.from_bytes(head[20:22], "big")
        self.ifid = _branded(head[HEAD_SIZE : HEAD_SIZE + IFID_SIZE])
        self.chunks = chunks
        self.files = tuple(held for held in chunks if held.chunk_id == FILE_ID)

        self._held: dict[bytes, Chunk] = {}

        for held in chunks:
            self._held.setdefault(held.chunk_id, held)

        self._certified()

        # LANG stands certified present, being a summed chunk.
        self.extended = _extended(self._held[b"LANG"])
        self.meta = _metadata(self._held.get(META_ID), self.extended)

    def chunk(self, chunk_id: bytes) -> Chunk | None:
        """The first chunk of a kind, None when the story has none."""

        return self._held.get(chunk_id)

    def _certified(self) -> None:
        """Verify the HEAD's CRC-32 over the summed chunks.

        Raises:
            AAMachineError: For a summed chunk missing, or a
                checksum that disagrees with the header's claim.
        """

        crc = 0

        for name in SUMMED:
            held = self._held.get(name)

            if held is None:
                msg = (
                    f"the {name.decode('ascii')} chunk is missing, and the "
                    f"checksum runs over it (Aa-machine: Story file)"
                )

                raise AAMachineError(msg)

            crc = zlib.crc32(held.payload, crc)

        if crc != self.checksum:
            msg = (
                f"the story's contents sum to {crc:08x}, but the header "
                f"claims {self.checksum:08x} (Aa-machine: HEAD)"
            )

            raise AAMachineError(msg)


def _branded(tail: bytes) -> str | None:
    """The HEAD's optional IFID, unwrapped from its UUID dressing.

    Raises:
        AAMachineError: For a field present but dressed wrong --
            the spec spells it "UUID://...//" and null-terminated
            (Aa-machine: HEAD).
    """

    if not tail:
        return None

    told = tail.split(b"\x00", 1)[0].decode("ascii", "replace")

    if not (told.startswith("UUID://") and told.endswith("//")):
        msg = (
            f"the HEAD's IFID field reads {told!r}, not UUID://...// (Aa-machine: HEAD)"
        )

        raise AAMachineError(msg)

    return told[len("UUID://") : -len("//")].upper()


# The LANG chunk opens with four two-byte offsets; the extended
# character table's is the second (Aa-machine: LANG).
_LANG_OFFSETS = 4


def _extended(lang: Chunk) -> tuple[str, ...]:
    """The LANG chunk's extended characters as Unicode, in order.

    Character bytes at $80 and above index this table wherever
    the story spells text -- the META bibliography included, which
    is how an author's Å survives the trip (Aa-machine: LANG).

    Raises:
        AAMachineError: For a table the chunk cannot hold whole.
    """

    payload = lang.payload

    if len(payload) < _LANG_OFFSETS:
        msg = "the LANG chunk is too short for its own offsets (Aa-machine: LANG)"

        raise AAMachineError(msg)

    at = int.from_bytes(payload[2:4], "big")

    if at >= len(payload):
        msg = "the LANG extended table sits past the chunk's end (Aa-machine: LANG)"

        raise AAMachineError(msg)

    count = payload[at]
    table_end = at + 1 + count * 5

    if table_end > len(payload):
        msg = "the LANG extended table ends mid-entry (Aa-machine: LANG)"

        raise AAMachineError(msg)

    return tuple(
        chr(
            int.from_bytes(
                payload[at + 1 + entry * 5 + 2 : at + 1 + entry * 5 + 5], "big"
            )
        )
        for entry in range(count)
    )


def _metadata(held: Chunk | None, extended: tuple[str, ...]) -> dict[str, str]:
    """The META bibliography by field name; empty without a chunk.

    Unknown identifiers are passed over -- the chunk is optional
    and additive by design -- but a chunk that runs out of bytes
    mid-entry is refused rather than half-read.

    Raises:
        AAMachineError: For a META chunk truncated mid-entry.
    """

    if held is None:
        return {}

    payload = held.payload

    if not payload:
        return {}

    fields: dict[str, str] = {}
    at = 1

    for _ in range(payload[0]):
        if at >= len(payload):
            msg = "the META chunk ends mid-entry (Aa-machine: META)"

            raise AAMachineError(msg)

        identifier = payload[at]
        ended = payload.find(b"\x00", at + 1)

        if ended < 0:
            msg = "a META string is missing its null ending (Aa-machine: META)"

            raise AAMachineError(msg)

        name = META_NAMES.get(identifier)

        if name is not None:
            fields[name] = _worded(payload[at + 1 : ended], extended)

        at = ended + 1

    return fields


# Where the extended characters begin in a spelled string's bytes.
_EXTENDED_START = 0x80


def _worded(raw: bytes, extended: tuple[str, ...]) -> str:
    """A spelled string's text, the story's own character space.

    Bytes below $80 are ASCII; $80 and above index the LANG
    chunk's extended character table -- the author's Å is byte
    $80 pointing at its Unicode seat, not any general-purpose
    encoding (Aa-machine: LANG).

    Raises:
        AAMachineError: For a byte past the extended table.
    """

    pieces = []

    for byte in raw:
        if byte < _EXTENDED_START:
            pieces.append(chr(byte))
        elif byte - _EXTENDED_START < len(extended):
            pieces.append(extended[byte - _EXTENDED_START])
        else:
            msg = (
                f"a spelled byte {byte:#04x} points past the "
                f"{len(extended)}-entry extended table (Aa-machine: LANG)"
            )

            raise AAMachineError(msg)

    return "".join(pieces)
