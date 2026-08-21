"""Saving and restoring the machine state.

The format is Quetzal with Glulx's own chunks (Glulx: The
Save-Game Format): IFhd identifies the story as the first 128
bytes of memory, CMem holds dynamic memory XOR-compressed against
the game file, MAll the allocation heap, and Stks the stack whole.

What is *not* saved matters as much (Glulx: State Not Saved): Glk
state, the protected range, the random
number generator, the I/O system, and the string-decoding table
address all survive a restore untouched.

The stack chunk is a straight copy. The spec requires stack values
written big-endian, and the reference glulxe has to walk each
frame's locals format to byte-swap them -- but Voxam's stack chose
big-endian storage in its own era for exactly this moment, so
saving is a snapshot and restoring is the reverse, the locals
format never consulted.
"""

import re
from typing import TYPE_CHECKING

from voxam.errors import GlulxFrontierError, GlulxSaveError, IFFError
from voxam.iff import Chunk, parse_form, write_form

if TYPE_CHECKING:
    from voxam.glulx.glk.objects import Stream
    from voxam.glulx.machine import Machine

# The Quetzal FORM type, and Glulx's chunks within it (Glulx: The
# Save-Game Format).
SAVE_FORM = b"IFZS"
IDENTITY = b"IFhd"
COMPRESSED = b"CMem"
UNCOMPRESSED = b"UMem"
HEAP = b"MAll"
STACK = b"Stks"

# IFhd is the first 128 bytes of memory -- always in ROM, since
# RAMSTART is at least 256 (Glulx: Associated Story File).
IDENTITY_LENGTH = 128

# How many undo states to keep; the reference glulxe keeps the
# same number.
MAX_UNDO_LEVELS = 8

# The opcodes' spoken results: zero for success, one for failure
# (Glulx: Game State).
SUCCEEDED = 0
FAILED = 1

_LENGTH_SIZE = 4
_LONGEST_RUN = 0x100

# Splits the XOR'd image into alternating zero and non-zero runs,
# keeping the whole walk in C; only the surviving runs are visited
# from Python.
_RUNS = re.compile(rb"\x00+|[^\x00]+")


def _encode_memory(machine: "Machine") -> bytes:
    """RAM as a CMem body: XOR'd against the original, then packed.

    A run of zeroes is written as a zero byte followed by the run
    length minus one, so one byte encodes up to 256; a trailing
    run is dropped entirely, because the decoder treats anything
    past the chunk's end as unchanged (Glulx: Contents of Dynamic
    Memory).
    """

    memory = machine.memory
    length = memory.endmem - memory.ramstart
    out = bytearray(memory.endmem.to_bytes(4, "big"))

    current = memory.read_run(memory.ramstart, length)
    difference = (
        int.from_bytes(current, "big")
        ^ int.from_bytes(memory.original_run(memory.ramstart, length), "big")
    ).to_bytes(length, "big")

    runs = _RUNS.findall(difference)

    for index, run in enumerate(runs):
        if run[0]:
            out += run
        elif index < len(runs) - 1:
            remaining = len(run)

            while remaining:
                step = min(remaining, _LONGEST_RUN)
                out += bytes((0, step - 1))
                remaining -= step

    return bytes(out)


def _decode_memory(machine: "Machine", body: bytes) -> None:
    """Undo the CMem encoding into the live memory map.

    Raises:
        GlulxSaveError: For a chunk too short to hold its own
            size, or a zero byte with no run length behind it.
    """

    new_size = _memory_size(body)

    machine.memory.set_size(new_size)

    memory = machine.memory
    length = new_size - memory.ramstart

    # Expand the run-length encoding. This loop runs over the
    # *compressed* data, which is mostly runs, not over every byte
    # of RAM.
    difference = bytearray()
    cursor = 4

    while cursor < len(body) and len(difference) < length:
        byte = body[cursor]
        cursor += 1

        if byte == 0:
            if cursor >= len(body):
                msg = "a zero byte ends the memory chunk with no run length"

                raise GlulxSaveError(msg)

            difference.extend(bytes(body[cursor] + 1))
            cursor += 1
        else:
            difference.append(byte)

    del difference[length:]
    difference.extend(bytes(length - len(difference)))

    contents = (
        int.from_bytes(difference, "big")
        ^ int.from_bytes(memory.original_run(memory.ramstart, length), "big")
    ).to_bytes(length, "big")

    memory.overwrite_ram(contents)


def _decode_uncompressed(machine: "Machine", body: bytes) -> None:
    """A UMem chunk: the new size, then raw RAM.

    Raises:
        GlulxSaveError: For a chunk too short to hold its size.
    """

    new_size = _memory_size(body)

    machine.memory.set_size(new_size)
    machine.memory.overwrite_ram(body[4 : 4 + new_size - machine.memory.ramstart])


def _memory_size(body: bytes) -> int:
    """The four-byte size a memory chunk opens with.

    Raises:
        GlulxSaveError: For a chunk shorter than the size itself.
    """

    if len(body) < _LENGTH_SIZE:
        msg = "the save file's memory chunk cannot hold its own size"

        raise GlulxSaveError(msg)

    return int.from_bytes(body[:4], "big")


def serialize(machine: "Machine") -> bytes:
    """A complete save file for the current state.

    The caller must already have pushed the four-value call stub
    the spec requires, since it forms part of the stack chunk
    (Glulx: Contents of the Stack). No MAll chunk is written: with
    no heap era, the heap is never active, and an inactive heap's
    chunk may be omitted (Glulx: Memory Allocation Heap).
    """

    return write_form(
        SAVE_FORM,
        [
            Chunk(IDENTITY, machine.memory.read_run(0, IDENTITY_LENGTH)),
            Chunk(COMPRESSED, _encode_memory(machine)),
            Chunk(STACK, machine.stack.snapshot()),
        ],
    )


def deserialize(machine: "Machine", data: bytes) -> None:
    """Restore a state a save file holds.

    Order matters: memory first, because it sets the memory size,
    then the stack.

    Raises:
        GlulxSaveError: For bytes that are not an IFZS container,
            a story that is not this one, or a missing chunk.
        GlulxFrontierError: For a save with an active heap, which
            awaits the heap era.
    """

    try:
        form_type, pieces = parse_form(data)
    except IFFError as error:
        msg = f"the save file is not an IFF container: {error}"

        raise GlulxSaveError(msg) from error

    if form_type != SAVE_FORM:
        msg = f"the save file is a {form_type!r} FORM, not Quetzal's IFZS"

        raise GlulxSaveError(msg)

    chunks = {piece.chunk_id: piece.payload for piece in pieces}

    identity = chunks.get(IDENTITY)

    if identity is None:
        msg = "the save file has no IFhd chunk to name its story"

        raise GlulxSaveError(msg)

    if identity != machine.memory.read_run(0, IDENTITY_LENGTH):
        msg = "the save file belongs to a different story"

        raise GlulxSaveError(msg)

    _require_no_heap(chunks.get(HEAP, b""))

    if COMPRESSED in chunks:
        _decode_memory(machine, chunks[COMPRESSED])
    elif UNCOMPRESSED in chunks:
        _decode_uncompressed(machine, chunks[UNCOMPRESSED])
    else:
        msg = "the save file has no memory chunk"

        raise GlulxSaveError(msg)

    stack = chunks.get(STACK)

    if stack is None:
        msg = "the save file has no Stks chunk"

        raise GlulxSaveError(msg)

    machine.stack.restore(stack)


def _require_no_heap(body: bytes) -> None:
    """Refuse a save whose heap was active.

    An inactive heap's MAll chunk "can contain 0,0 or it may be
    omitted" (Glulx: Memory Allocation Heap); anything more names
    blocks this machine cannot rebuild yet.

    Raises:
        GlulxFrontierError: For an MAll chunk with content.
    """

    if any(body):
        msg = "the save file's allocation heap awaits the heap era"

        raise GlulxFrontierError(msg)


def save(machine: "Machine", stream: "Stream | None") -> int:
    """The save opcode's work: the state onto a Glk stream.

    A stream that is missing or unwritable fails with 1 rather
    than faulting -- the spoken failure is how a game learns to
    prompt again (Glulx: Game State).
    """

    if stream is None or not stream.writable:
        return FAILED

    stream.put_buffer(serialize(machine))

    return SUCCEEDED


def restore(machine: "Machine", stream: "Stream | None") -> int:
    """The restore opcode's work: the state off a Glk stream.

    On success the whole machine state -- stack included -- has
    been replaced, and the caller pops the call stub that was
    saved with it. Failure speaks 1 and changes nothing.
    """

    if stream is None or not stream.readable:
        return FAILED

    data = bytearray()

    while (byte := stream.get_char()) >= 0:
        data.append(byte)

    try:
        deserialize(machine, bytes(data))
    except GlulxSaveError:
        return FAILED

    return SUCCEEDED


def save_undo(machine: "Machine") -> int:
    """The saveundo opcode's work: the state into the undo chain.

    The chain keeps the newest handful of states; saving past the
    limit lets the oldest go, the way the reference does.
    """

    machine.undo_chain.append(serialize(machine))

    del machine.undo_chain[:-MAX_UNDO_LEVELS]

    return SUCCEEDED


def restore_undo(machine: "Machine") -> int:
    """The restoreundo opcode's work: the newest undo state back.

    An empty chain fails with 1; a successful restore consumes the
    state it restored.
    """

    if not machine.undo_chain:
        return FAILED

    deserialize(machine, machine.undo_chain.pop())

    return SUCCEEDED


def has_undo(machine: "Machine") -> int:
    """The hasundo opcode's answer: 0 with a state waiting, 1 bare.

    A zero here is a promise that restoreundo will succeed
    (Glulx: Game State).
    """

    return SUCCEEDED if machine.undo_chain else FAILED


def discard_undo(machine: "Machine") -> None:
    """The discardundo opcode's work: let the newest state go."""

    if machine.undo_chain:
        machine.undo_chain.pop()
