"""Quetzal, the common format for saved games (Quetzal 1.4).

A Quetzal file is an IFF FORM of type IFZS (Quetzal §2.1) carrying
three required chunks (Quetzal §7.18): IFhd names the story the save
belongs to, CMem or UMem carries dynamic memory, and Stks carries
the call chain. That is exactly a Snapshot with an identity stamp,
so this module is a pure codec: Snapshot in, bytes out, and back.

Writing always compresses (CMem); reading accepts both forms, as
Quetzal §3.6 requires.
"""

from voxam.errors import ZMachineQuetzalError
from voxam.zmachine.snapshot import FrameSnapshot, Snapshot
from voxam.zmachine.story import Story

# The FORM type of a saved game is IFZS (Quetzal §2.1); FORM itself
# is the single outer chunk of any simple IFF file (Quetzal §8.5).
FORM_ID = b"FORM"
SAVE_FORM = b"IFZS"

# The chunks this codec understands. Anything else is skipped
# unread, as extension chunks must be (Quetzal §7.17, §8.6).
IFHD_ID = b"IFhd"
CMEM_ID = b"CMem"
UMEM_ID = b"UMem"
STKS_ID = b"Stks"

# A chunk is an ID, a 32-bit big-endian length, and that many bytes
# of data (Quetzal §8.3, §8.4); odd data gains a pad byte the length
# does not count (Quetzal §8.4.1).
CHUNK_HEADER_SIZE = 8
LENGTH_SIZE = 4

# IFhd carries release, serial, checksum, and a 3-byte PC -- 13
# bytes now, possibly more one day, but the first 13 are guaranteed
# (Quetzal §5.4, §5.5). The first ten name the story (Quetzal §5.3).
IFHD_LENGTH = 13
IDENTITY_SIZE = 10

# Return PCs and the saved PC are 3-byte byte addresses (Quetzal
# §4.3.1, §5.4.6).
ADDRESS_SIZE = 3
ADDRESS_LIMIT = 0xFFFFFF

# A frame's flags byte is 000pvvvv: p set on discard-result calls,
# vvvv the local count (Quetzal §4.3.2, §4.6). The arguments byte is
# 0gfedcba, one bit per supplied argument (Quetzal §4.3.4, §4.7).
DISCARD_FLAG = 0x10
LOCALS_MASK = 0x0F
FLAGS_RESERVED = 0xE0
ARGUMENTS_LIMIT = 7

# The fixed part of a frame: 3 address bytes, flags, store variable,
# arguments mask, and a word counting the evaluation stack
# (Quetzal §4.3).
FRAME_HEADER_SIZE = 8
WORD_SIZE = 2

# A zero byte in CMem data pairs with a length byte for a run of
# n+1 zeros (Quetzal §3.2), so one pair carries at most 256.
LONGEST_RUN = 256


def write(snapshot: Snapshot, story: Story) -> bytes:
    """Serialize a state of play as a Quetzal file (Quetzal §2).

    Args:
        snapshot: The captured state of play to preserve.
        story: The pristine story the snapshot was captured from; its
            identity is stamped into IFhd and its original bytes are
            the reference CMem compresses against (Quetzal §3.2,
            §5.3).

    Returns:
        A complete IFZS FORM: IFhd, then CMem, then Stks.

    Raises:
        ZMachineQuetzalError: If the snapshot does not belong to this
            story, or holds values the format cannot carry.
    """

    dynamic = snapshot.dynamic_memory

    if len(dynamic) != story.header.static_memory_base:
        msg = (
            f"cannot save a {len(dynamic)}-byte dynamic memory image "
            f"for a story whose dynamic memory is "
            f"{story.header.static_memory_base} bytes: the snapshot "
            f"belongs to a different game (Quetzal §5.3)"
        )

        raise ZMachineQuetzalError(msg)

    chunks = (
        _chunk(IFHD_ID, _encode_identity(snapshot.pc, story))
        + _chunk(CMEM_ID, _compress(dynamic, story))
        + _chunk(STKS_ID, _encode_frames(snapshot.frames))
    )
    body = SAVE_FORM + chunks

    return FORM_ID + len(body).to_bytes(LENGTH_SIZE, "big") + body


def read(data: bytes, story: Story) -> Snapshot:
    """Parse a Quetzal file back into a state of play (Quetzal §2).

    Args:
        data: The bytes of an IFZS FORM.
        story: The pristine story being played; the file's IFhd must
            match its identity (Quetzal §5.3, §6.1.2.1 of the
            Standard), and CMem decompresses against its original
            bytes.

    Returns:
        The state of play the file preserves, ready for
        Machine.restore.

    Raises:
        ZMachineQuetzalError: If the bytes are not a well-formed
            IFZS FORM, a required chunk is missing or doubled, the
            save belongs to a different game, or any chunk's content
            breaks its rules.
    """

    ifhd, memory_chunk, stks = _split(data)
    pc = _check_identity(ifhd, story)
    dynamic = _decode_memory(memory_chunk, story)
    frames = _decode_frames(stks)

    return Snapshot(dynamic_memory=dynamic, pc=pc, frames=frames)


def _chunk(chunk_id: bytes, payload: bytes) -> bytes:
    """Wrap a payload as an IFF chunk, padding odd data (Quetzal §8.4.1)."""

    pad = b"\x00" if len(payload) % 2 else b""

    return chunk_id + len(payload).to_bytes(LENGTH_SIZE, "big") + payload + pad


def _identity(story: Story) -> bytes:
    """The ten bytes naming a story: release, serial, checksum.

    Saves are matched to stories by the release number, serial
    number, and checksum (Quetzal §5.3). A story too old to store a
    checksum gets one calculated from its file, on saving and
    checking alike (Quetzal §5.5).
    """

    header = story.header
    checksum = header.stored_checksum or header.computed_checksum

    return (
        header.release.to_bytes(WORD_SIZE, "big")
        + header.serial_number.encode("ascii")
        + checksum.to_bytes(WORD_SIZE, "big")
    )


def _encode_identity(pc: int, story: Story) -> bytes:
    """Build the 13 IFhd bytes (Quetzal §5.4)."""

    return _identity(story) + _address(pc)


def _address(value: int) -> bytes:
    """Encode a 3-byte byte address (Quetzal §4.3.1, §5.4.6)."""

    if value > ADDRESS_LIMIT:
        msg = (
            f"address ${value:x} does not fit in the three bytes "
            f"Quetzal stores (Quetzal §4.3.1)"
        )

        raise ZMachineQuetzalError(msg)

    return value.to_bytes(ADDRESS_SIZE, "big")


def _compress(dynamic: bytes, story: Story) -> bytes:
    """Compress dynamic memory against the original (Quetzal §3.2).

    The current bytes are exclusive-ored with the pristine story's,
    so unchanged memory becomes zero, and runs of zeros collapse to a
    zero byte plus a count of n+1. Trailing zeros are dropped whole:
    a reader assumes the missing tail is unchanged (Quetzal §3.4).
    """

    changed = bytes(
        live ^ pristine for live, pristine in zip(dynamic, story.data, strict=False)
    ).rstrip(b"\x00")

    encoded = bytearray()
    position = 0

    while position < len(changed):
        if changed[position]:
            encoded.append(changed[position])
            position += 1
            continue

        run = position

        while run < len(changed) and not changed[run]:
            run += 1

        for length in range(position, run, LONGEST_RUN):
            encoded += bytes([0, min(run - length, LONGEST_RUN) - 1])

        position = run

    return bytes(encoded)


def _decompress(encoded: bytes, story: Story, size: int) -> bytes:
    """Undo CMem compression against the original story (Quetzal §3.2).

    Raises:
        ZMachineQuetzalError: If the data ends mid-run or decodes to
            more than dynamic memory holds -- the two read errors of
            Quetzal §3.5.
    """

    changed = bytearray()
    position = 0

    while position < len(encoded):
        byte = encoded[position]

        if byte:
            changed.append(byte)
            position += 1
            continue

        if position + 1 == len(encoded):
            msg = (
                "compressed memory ends with a zero byte and no run "
                "length (Quetzal §3.5)"
            )

            raise ZMachineQuetzalError(msg)

        changed += bytes(encoded[position + 1] + 1)
        position += 2

    if len(changed) > size:
        msg = (
            f"compressed memory decodes to {len(changed)} bytes, but "
            f"dynamic memory holds only {size} (Quetzal §3.5)"
        )

        raise ZMachineQuetzalError(msg)

    changed += bytes(size - len(changed))

    return bytes(
        live ^ pristine
        for live, pristine in zip(changed, story.data[:size], strict=True)
    )


def _encode_frames(frames: tuple[FrameSnapshot, ...]) -> bytes:
    """Lay the call chain out as Stks data, oldest first (Quetzal §4).

    The base frame becomes the dummy frame of Quetzal §4.11: every
    field zero except its evaluation stack count.
    """

    encoded = bytearray()

    for index, frame in enumerate(frames):
        if index == 0:
            encoded += _address(0) + bytes([0, 0, 0])
        else:
            if frame.argument_count > ARGUMENTS_LIMIT:
                msg = (
                    f"a frame holding {frame.argument_count} arguments "
                    f"does not fit the seven argument bits (Quetzal §4.3.4)"
                )

                raise ZMachineQuetzalError(msg)

            flags = len(frame.locals)
            store = frame.store_variable

            if store is None:
                flags |= DISCARD_FLAG
                store = 0

            encoded += _address(frame.return_address)
            encoded += bytes([flags, store, (1 << frame.argument_count) - 1])

        encoded += len(frame.stack).to_bytes(WORD_SIZE, "big")

        for word in frame.locals + frame.stack:
            encoded += word.to_bytes(WORD_SIZE, "big")

    return bytes(encoded)


def _decode_frames(data: bytes) -> tuple[FrameSnapshot, ...]:
    """Parse Stks data back into a call chain (Quetzal §4).

    Raises:
        ZMachineQuetzalError: If a frame is cut short, uses reserved
            flag bits, holds a gap-riddled argument mask, or the
            required dummy frame is not dummy (Quetzal §4.11.1).
    """

    frames: list[FrameSnapshot] = []
    position = 0

    while position < len(data):
        if position + FRAME_HEADER_SIZE > len(data):
            msg = "a stack frame is cut short mid-header (Quetzal §4.3)"

            raise ZMachineQuetzalError(msg)

        return_address = int.from_bytes(data[position : position + ADDRESS_SIZE], "big")
        flags, store, mask = data[position + 3 : position + 6]
        stack_count = int.from_bytes(data[position + 6 : position + 8], "big")
        position += FRAME_HEADER_SIZE

        if flags & FLAGS_RESERVED:
            msg = (
                f"a frame's flags byte ${flags:02x} uses reserved bits: "
                f"only 000pvvvv is defined (Quetzal §4.3.2)"
            )

            raise ZMachineQuetzalError(msg)

        if mask & (mask + 1):
            msg = (
                f"a frame's argument mask ${mask:02x} has gaps: arguments "
                f"are supplied in order (Quetzal §4.3.4)"
            )

            raise ZMachineQuetzalError(msg)

        local_count = flags & LOCALS_MASK
        words_size = (local_count + stack_count) * WORD_SIZE

        if position + words_size > len(data):
            msg = "a stack frame is cut short mid-words (Quetzal §4.3)"

            raise ZMachineQuetzalError(msg)

        words = [
            int.from_bytes(data[offset : offset + WORD_SIZE], "big")
            for offset in range(position, position + words_size, WORD_SIZE)
        ]
        position += words_size

        if not frames:
            if return_address or flags or store or mask:
                msg = (
                    "the first frame must be the dummy: every field "
                    "zero but its stack count (Quetzal §4.11.1)"
                )

                raise ZMachineQuetzalError(msg)

            store_variable = None
        else:
            store_variable = None if flags & DISCARD_FLAG else store

        frames.append(
            FrameSnapshot(
                return_address=return_address,
                store_variable=store_variable,
                locals=tuple(words[:local_count]),
                argument_count=mask.bit_count(),
                stack=tuple(words[local_count:]),
            )
        )

    if not frames:
        msg = (
            "the Stks chunk is empty: the dummy frame is always "
            "present (Quetzal §4.11.2)"
        )

        raise ZMachineQuetzalError(msg)

    return tuple(frames)


def _split(data: bytes) -> tuple[bytes, tuple[bytes, bytes], bytes]:
    """Pull the three required chunks out of the FORM (Quetzal §7.18).

    Returns:
        The IFhd payload, the memory chunk as an (id, payload) pair,
        and the Stks payload.

    Raises:
        ZMachineQuetzalError: If the bytes are not a well-formed
            IFZS FORM, or a required chunk is missing or doubled.
    """

    found = _walk(data)

    if IFHD_ID not in found:
        msg = "the required IFhd chunk is missing (Quetzal §7.18)"

        raise ZMachineQuetzalError(msg)

    if STKS_ID not in found:
        msg = "the required Stks chunk is missing (Quetzal §7.18)"

        raise ZMachineQuetzalError(msg)

    if CMEM_ID in found and UMEM_ID in found:
        msg = (
            "CMem and UMem both appear: a save carries one or the other (Quetzal §7.18)"
        )

        raise ZMachineQuetzalError(msg)

    if CMEM_ID in found:
        memory_chunk = (CMEM_ID, found[CMEM_ID])
    elif UMEM_ID in found:
        memory_chunk = (UMEM_ID, found[UMEM_ID])
    else:
        msg = "the required CMem or UMem chunk is missing (Quetzal §7.18)"

        raise ZMachineQuetzalError(msg)

    return found[IFHD_ID], memory_chunk, found[STKS_ID]


def _walk(data: bytes) -> dict[bytes, bytes]:
    """Walk the IFF container, collecting the chunks this codec knows.

    Unknown chunks are skipped unread (Quetzal §7.17, §8.6), and odd
    chunks stride over their pad byte (Quetzal §8.4.1).

    Raises:
        ZMachineQuetzalError: If the bytes are not an IFZS FORM, a
            chunk is truncated or doubled, or IFhd does not come
            first (Quetzal §5.4).
    """

    if len(data) < CHUNK_HEADER_SIZE + LENGTH_SIZE or data[:4] != FORM_ID:
        msg = "not an IFF file: no FORM chunk to open it (Quetzal §8.5)"

        raise ZMachineQuetzalError(msg)

    length = int.from_bytes(data[4:8], "big")

    if CHUNK_HEADER_SIZE + length > len(data):
        msg = (
            f"the FORM chunk claims {length} bytes, but the file has "
            f"only {len(data) - CHUNK_HEADER_SIZE} after its header "
            f"(Quetzal §8.3.5)"
        )

        raise ZMachineQuetzalError(msg)

    if data[8:12] != SAVE_FORM:
        msg = (
            f"the FORM type is {data[8:12]!r}, not the IFZS of a "
            f"saved game (Quetzal §2.1)"
        )

        raise ZMachineQuetzalError(msg)

    found: dict[bytes, bytes] = {}
    position = 12
    end = CHUNK_HEADER_SIZE + length

    while position < end:
        if position + CHUNK_HEADER_SIZE > end:
            msg = "a chunk is cut short mid-header (Quetzal §8.3.1)"

            raise ZMachineQuetzalError(msg)

        chunk_id = data[position : position + 4]
        size = int.from_bytes(data[position + 4 : position + 8], "big")
        position += CHUNK_HEADER_SIZE

        if position + size > end:
            msg = (
                f"the {chunk_id!r} chunk claims {size} bytes, but the "
                f"FORM ends before them (Quetzal §8.4)"
            )

            raise ZMachineQuetzalError(msg)

        if chunk_id in (IFHD_ID, CMEM_ID, UMEM_ID, STKS_ID):
            if chunk_id in found:
                msg = f"the {chunk_id!r} chunk appears twice (Quetzal §7.18)"

                raise ZMachineQuetzalError(msg)

            if chunk_id != IFHD_ID and IFHD_ID not in found:
                msg = (
                    f"the {chunk_id!r} chunk arrives before IFhd, which "
                    f"must come first (Quetzal §5.4)"
                )

                raise ZMachineQuetzalError(msg)

            found[chunk_id] = data[position : position + size]

        position += size + size % 2

    return found


def _check_identity(ifhd: bytes, story: Story) -> int:
    """Match the save to the story and return its PC (Quetzal §5.3).

    Raises:
        ZMachineQuetzalError: If the chunk is too short, or the
            release, serial, and checksum do not name this story --
            the refusal §6.1.2.1 of the Standard asks for.
    """

    if len(ifhd) < IFHD_LENGTH:
        msg = (
            f"the IFhd chunk holds {len(ifhd)} bytes, fewer than the "
            f"{IFHD_LENGTH} its first bytes always contain (Quetzal §5.5)"
        )

        raise ZMachineQuetzalError(msg)

    if ifhd[:IDENTITY_SIZE] != _identity(story):
        msg = (
            "this save names a different game: its release, serial, "
            "and checksum do not match the story being played "
            "(Quetzal §5.3, §6.1.2.1)"
        )

        raise ZMachineQuetzalError(msg)

    return int.from_bytes(ifhd[IDENTITY_SIZE:IFHD_LENGTH], "big")


def _decode_memory(memory_chunk: tuple[bytes, bytes], story: Story) -> bytes:
    """Recover dynamic memory from CMem or UMem (Quetzal §3).

    Raises:
        ZMachineQuetzalError: If a UMem dump is not exactly dynamic
            memory's size (Quetzal §3.6), or CMem data breaks the
            §3.5 rules.
    """

    chunk_id, payload = memory_chunk
    size = story.header.static_memory_base

    if chunk_id == UMEM_ID:
        if len(payload) != size:
            msg = (
                f"a UMem dump must be exactly dynamic memory: {size} "
                f"bytes, not {len(payload)} (Quetzal §3.6)"
            )

            raise ZMachineQuetzalError(msg)

        return payload

    return _decompress(payload, story, size)
