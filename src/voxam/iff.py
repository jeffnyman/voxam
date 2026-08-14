"""IFF containers: the FORM that saves and resources both live in.

Quetzal saved games (FORM type IFZS) and Blorb resource files (FORM
type IFRS) are both simple IFF files: one outer FORM chunk holding
a form type and a sequence of typed chunks, each padded to an even
length. This module is the container alone -- what a FORM is, how a
chunk is framed, where the pad bytes go -- and knows nothing about
what any chunk means. The structural rules are cited by their
Quetzal §8 numbers, where this project's vendored references
document the IFF container itself.
"""

from collections.abc import Iterable
from dataclasses import dataclass

from voxam.errors import IFFError

# FORM is the single outer chunk of any simple IFF file, its
# payload beginning with a four-byte form type (Quetzal §8.5).
FORM_ID = b"FORM"
TYPE_SIZE = 4

# A chunk is an ID, a 32-bit big-endian length, and that many bytes
# of data (Quetzal §8.3, §8.4); odd data gains a pad byte the
# length does not count (Quetzal §8.4.1).
CHUNK_HEADER_SIZE = 8
LENGTH_SIZE = 4


@dataclass(frozen=True)
class Chunk:
    """One typed chunk: a four-byte ID and its payload (Quetzal §8.3).

    Attributes:
        chunk_id: The four-byte chunk type.
        payload: The chunk's data, pad byte excluded.
        offset: Where the chunk's header begins in its file --
            the address a Blorb resource index speaks (Blorb:
            Resource Index Chunk). Zero on chunks built by hand.
    """

    chunk_id: bytes
    payload: bytes
    offset: int = 0


def chunk(chunk_id: bytes, payload: bytes) -> bytes:
    """Frame a payload as an IFF chunk, padding odd data (Quetzal §8.4.1).

    Args:
        chunk_id: The four-byte chunk type.
        payload: The data to carry.

    Returns:
        The framed bytes: ID, big-endian length, data, and a pad
        byte after odd data.
    """

    pad = b"\x00" if len(payload) % 2 else b""

    return chunk_id + len(payload).to_bytes(LENGTH_SIZE, "big") + payload + pad


def write_form(form_type: bytes, chunks: Iterable[Chunk]) -> bytes:
    """Assemble a FORM from its type and chunks (Quetzal §8.5).

    Args:
        form_type: The four-byte form type, IFZS or IFRS or other.
        chunks: The chunks to carry, in order.

    Returns:
        The complete IFF file bytes.
    """

    body = form_type + b"".join(
        chunk(piece.chunk_id, piece.payload) for piece in chunks
    )

    return chunk(FORM_ID, body)


def parse_form(data: bytes) -> tuple[bytes, tuple[Chunk, ...]]:
    """Open a FORM and walk every chunk inside it, in order.

    Every chunk is collected, known or not: what a chunk means is
    the caller's business, and a Blorb reader and a Quetzal reader
    care about different ones.

    Args:
        data: The complete IFF file bytes.

    Returns:
        The four-byte form type and the chunks, in file order.

    Raises:
        IFFError: If the bytes are not a FORM, the FORM claims more
            than the file holds, or a chunk is truncated.
    """

    if len(data) < CHUNK_HEADER_SIZE + TYPE_SIZE or data[:4] != FORM_ID:
        msg = "not an IFF file: no FORM chunk to open it (Quetzal §8.5)"

        raise IFFError(msg)

    length = int.from_bytes(data[4:8], "big")

    if CHUNK_HEADER_SIZE + length > len(data):
        msg = (
            f"the FORM chunk claims {length} bytes, but the file has "
            f"only {len(data) - CHUNK_HEADER_SIZE} after its header "
            f"(Quetzal §8.3.5)"
        )

        raise IFFError(msg)

    form_type = data[8:12]
    found: list[Chunk] = []
    position = CHUNK_HEADER_SIZE + TYPE_SIZE
    end = CHUNK_HEADER_SIZE + length

    while position < end:
        if position + CHUNK_HEADER_SIZE > end:
            msg = "a chunk is cut short mid-header (Quetzal §8.3.1)"

            raise IFFError(msg)

        header_offset = position
        chunk_id = data[position : position + 4]
        size = int.from_bytes(data[position + 4 : position + 8], "big")
        position += CHUNK_HEADER_SIZE

        if position + size > end:
            msg = (
                f"the {chunk_id!r} chunk claims {size} bytes, but the "
                f"FORM ends before them (Quetzal §8.4)"
            )

            raise IFFError(msg)

        found.append(Chunk(chunk_id, data[position : position + size], header_offset))
        position += size + size % 2

    return form_type, tuple(found)
