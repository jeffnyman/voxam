"""Save and undo: the state bottled and poured back (Glulx: The
Save-Game Format).
"""

from collections.abc import Callable

import pytest
from assertpy import assert_that

from voxam.errors import GlulxSaveError
from voxam.glulx import serial
from voxam.glulx.glk.api import Glk
from voxam.glulx.glk.dispatch import CLASS_STREAM
from voxam.glulx.glk.objects import FileMode, SeekMode
from voxam.glulx.machine import Machine
from voxam.glulx.stack import DestType
from voxam.glulx.story import Story
from voxam.iff import Chunk, parse_form, write_form

IDLE = bytes([0xC0, 0x00, 0x00, 0x81, 0x20])
PLANT = 0x180
RESULT = 0x140
SECOND = 0x148
MARKER = 0x160

RESTORED = 0xFFFFFFFF


def booted(image: Callable[..., bytes]) -> Machine:
    return Machine(Story(image(code=IDLE)))


def identity(machine: Machine) -> bytes:
    return machine.memory.read_run(0, serial.IDENTITY_LENGTH)


# The whole state comes back: changed RAM, memory grown past the
# boot size -- zero-extended above EXTSTART in the file's stead --
# and the stack, stub and all, byte for byte.
def test_the_state_survives_the_bottle(image: Callable[..., bytes]) -> None:
    machine = booted(image)

    machine.memory.write_byte(0x150, 0x42)
    machine.memory.set_size(0x400)
    machine.memory.write_byte(0x350, 0x77)
    machine.stack.push(123)
    machine.stack.push_stub(DestType.MEMORY, RESULT, 0x1234)

    saved = serial.serialize(machine)

    machine.memory.write_byte(0x150, 0)
    machine.memory.set_size(0x300)
    machine.stack.pop_stub()
    machine.stack.pop()

    serial.deserialize(machine, saved)

    assert_that(machine.memory.endmem).is_equal_to(0x400)
    assert_that(machine.memory.read_byte(0x150)).is_equal_to(0x42)
    assert_that(machine.memory.read_byte(0x350)).is_equal_to(0x77)

    stub = machine.stack.pop_stub()

    assert_that((stub.desttype, stub.destaddr, stub.pc)).is_equal_to(
        (DestType.MEMORY, RESULT, 0x1234)
    )
    assert_that(machine.stack.pop()).is_equal_to(123)


# The compression earns its name: an unchanged machine's memory
# chunk is nothing but its four size bytes, and a long gap between
# two changes packs into 256-zero runs rather than a byte apiece.
def test_the_memory_chunk_compresses(image: Callable[..., bytes]) -> None:
    machine = booted(image)
    machine.stack.push_stub(DestType.DISCARD, 0, 0)

    _, pieces = parse_form(serial.serialize(machine))
    chunks = {piece.chunk_id: piece.payload for piece in pieces}

    assert_that(chunks[serial.COMPRESSED]).is_length(4)

    machine.memory.write_byte(0x100, 0x11)
    machine.memory.write_byte(0x2B0, 0x22)

    saved = serial.serialize(machine)

    assert_that(len(saved)).is_less_than(0x150)

    machine.memory.write_byte(0x100, 0)
    machine.memory.write_byte(0x2B0, 0)

    serial.deserialize(machine, saved)

    assert_that(machine.memory.read_byte(0x100)).is_equal_to(0x11)
    assert_that(machine.memory.read_byte(0x2B0)).is_equal_to(0x22)


# An uncompressed UMem chunk restores the same way the packed form
# does; a memory body holding more bytes than RAM is trimmed to
# fit.
def test_the_uncompressed_form_restores(image: Callable[..., bytes]) -> None:
    machine = booted(image)

    machine.memory.write_byte(MARKER, 0x5A)
    machine.stack.push_stub(DestType.DISCARD, 0, 0)

    raw = machine.memory.read_run(0x100, 0x200)
    file = write_form(
        serial.SAVE_FORM,
        [
            Chunk(serial.IDENTITY, identity(machine)),
            Chunk(serial.UNCOMPRESSED, (0x300).to_bytes(4, "big") + raw),
            Chunk(serial.STACK, machine.stack.snapshot()),
        ],
    )

    machine.memory.write_byte(MARKER, 0)

    serial.deserialize(machine, file)

    assert_that(machine.memory.read_byte(MARKER)).is_equal_to(0x5A)

    # A compressed body longer than RAM: the surplus is trimmed.
    stuffed = write_form(
        serial.SAVE_FORM,
        [
            Chunk(serial.IDENTITY, identity(machine)),
            Chunk(serial.COMPRESSED, (0x300).to_bytes(4, "big") + b"\x41" * 0x250),
            Chunk(serial.STACK, machine.stack.snapshot()),
        ],
    )

    serial.deserialize(machine, stuffed)

    assert_that(machine.memory.read_byte(0x2FF)).is_equal_to(0x41)


# The protected range is silently unaffected by a restore, at
# every position it can sit: inside RAM, flush against its start,
# flush against its end, and entirely outside it.
def test_protection_survives_a_restore(image: Callable[..., bytes]) -> None:
    for start, length, kept in (
        (0x180, 0x10, 0x185),
        (0x100, 0x10, 0x105),
        (0x2F0, 0x10, 0x2F5),
    ):
        machine = booted(image)

        machine.stack.push_stub(DestType.DISCARD, 0, 0)

        saved = serial.serialize(machine)

        machine.memory.set_protection(start, length)
        machine.memory.write_byte(kept, 0x55)
        machine.memory.write_byte(0x1C0, 0x66)

        serial.deserialize(machine, saved)

        assert_that(machine.memory.read_byte(kept)).is_equal_to(0x55)
        assert_that(machine.memory.read_byte(0x1C0)).is_equal_to(0)

    # A range beyond the map protects nothing, and the write goes
    # through whole.
    outside = booted(image)

    outside.stack.push_stub(DestType.DISCARD, 0, 0)

    saved = serial.serialize(outside)

    outside.memory.set_protection(0x500, 4)
    outside.memory.write_byte(0x1C0, 0x66)

    serial.deserialize(outside, saved)

    assert_that(outside.memory.read_byte(0x1C0)).is_equal_to(0)


# Every way a save file can be wrong is refused by name: not IFF,
# the wrong FORM, no story identity, someone else's story, no
# memory, no stack, a memory chunk cut short, and a zero byte with
# no run length behind it.
def test_wrong_save_files_are_refused(image: Callable[..., bytes]) -> None:
    machine = booted(image)

    machine.stack.push_stub(DestType.DISCARD, 0, 0)

    whole = identity(machine)
    memory = Chunk(serial.COMPRESSED, (0x300).to_bytes(4, "big"))
    stack = Chunk(serial.STACK, machine.stack.snapshot())

    wrongs = [
        (b"junk", "not an IFF container"),
        (write_form(b"IFRS", [memory]), "not Quetzal's IFZS"),
        (write_form(serial.SAVE_FORM, [memory, stack]), "no IFhd"),
        (
            write_form(
                serial.SAVE_FORM,
                [Chunk(serial.IDENTITY, bytes(128)), memory, stack],
            ),
            "different story",
        ),
        (
            write_form(serial.SAVE_FORM, [Chunk(serial.IDENTITY, whole), stack]),
            "no memory chunk",
        ),
        (
            write_form(serial.SAVE_FORM, [Chunk(serial.IDENTITY, whole), memory]),
            "no Stks chunk",
        ),
        (
            write_form(
                serial.SAVE_FORM,
                [
                    Chunk(serial.IDENTITY, whole),
                    Chunk(serial.COMPRESSED, b"\x00"),
                    stack,
                ],
            ),
            "cannot hold its own size",
        ),
        (
            write_form(
                serial.SAVE_FORM,
                [
                    Chunk(serial.IDENTITY, whole),
                    Chunk(serial.COMPRESSED, (0x300).to_bytes(4, "big") + b"\x41\x00"),
                    stack,
                ],
            ),
            "no run length",
        ),
    ]

    for data, complaint in wrongs:
        with pytest.raises(GlulxSaveError, match=complaint):
            serial.deserialize(machine, data)


# The heap rides the save: an active heap writes its MAll chunk
# and comes back rebuilt, blocks and gaps alike; an inactive one
# writes no chunk at all, and restoring an inactive save onto an
# active heap deactivates it.
def test_the_heap_rides_the_save(image: Callable[..., bytes]) -> None:
    machine = booted(image)

    machine.stack.push_stub(DestType.DISCARD, 0, 0)

    bare = serial.serialize(machine)

    _, pieces = parse_form(bare)

    assert_that([piece.chunk_id for piece in pieces]).does_not_contain(serial.HEAP)

    first = machine.heap.alloc(0x40)
    second = machine.heap.alloc(0x30)

    saved = serial.serialize(machine)

    _, pieces = parse_form(saved)

    assert_that([piece.chunk_id for piece in pieces]).contains(serial.HEAP)

    machine.heap.free(first)

    serial.deserialize(machine, saved)

    assert_that(machine.heap.summary()).is_equal_to(
        [0x300, 2, first, 0x40, second, 0x30]
    )

    # An inactive-heap save lands on an active heap by clearing it.
    serial.deserialize(machine, bare)

    assert_that(machine.heap.active).is_false()
    assert_that(machine.memory.endmem).is_equal_to(0x300)


# The undo chain holds the newest handful of states and no more;
# restoring consumes, discarding drops, and an empty chain answers
# honestly.
def test_the_undo_chain_keeps_the_newest(image: Callable[..., bytes]) -> None:
    machine = booted(image)

    machine.stack.push_stub(DestType.DISCARD, 0, 0)

    assert_that(serial.has_undo(machine)).is_equal_to(serial.FAILED)
    assert_that(serial.restore_undo(machine)).is_equal_to(serial.FAILED)

    serial.discard_undo(machine)

    for turn in range(10):
        machine.memory.write_byte(MARKER, turn)

        serial.save_undo(machine)

    assert_that(machine.undo_chain).is_length(serial.MAX_UNDO_LEVELS)
    assert_that(serial.has_undo(machine)).is_equal_to(serial.SUCCEEDED)

    serial.discard_undo(machine)

    assert_that(serial.restore_undo(machine)).is_equal_to(serial.SUCCEEDED)
    assert_that(machine.memory.read_byte(MARKER)).is_equal_to(8)
    assert_that(machine.undo_chain).is_length(6)


# The saveundo dance, through the opcodes: the first pass stores
# zero and walks on; after a restoreundo elsewhere, execution is
# back at the instruction after saveundo with -1 stored and the
# turn's changes gone.
def test_the_saveundo_dance(image: Callable[..., bytes]) -> None:
    machine = booted(image)
    saveundo = bytes([0x81, 0x25, 0x07]) + RESULT.to_bytes(4, "big")

    machine.memory.write_run(PLANT, saveundo)

    machine.pc = PLANT

    machine.step()

    resumed = PLANT + len(saveundo)

    assert_that(machine.memory.read_word(RESULT)).is_equal_to(0)
    assert_that(machine.pc).is_equal_to(resumed)

    machine.memory.write_byte(MARKER, 0x99)
    machine.memory.write_run(
        PLANT + 0x20, bytes([0x81, 0x26, 0x07]) + SECOND.to_bytes(4, "big")
    )

    machine.pc = PLANT + 0x20

    machine.step()

    assert_that(machine.pc).is_equal_to(resumed)
    assert_that(machine.memory.read_word(RESULT)).is_equal_to(RESTORED)
    assert_that(machine.memory.read_byte(MARKER)).is_equal_to(0)

    # The restore reverted the second plant along with everything
    # else -- it was written after the save -- so it needs planting
    # again. With the chain now spent, restoreundo speaks failure
    # in place and walks on.
    machine.memory.write_run(
        PLANT + 0x20, bytes([0x81, 0x26, 0x07]) + SECOND.to_bytes(4, "big")
    )

    machine.pc = PLANT + 0x20

    machine.step()

    assert_that(machine.memory.read_word(SECOND)).is_equal_to(1)


# hasundo and discardundo through the opcodes: a state waits, is
# let go, and waits no more.
def test_hasundo_and_discardundo_dispatch(image: Callable[..., bytes]) -> None:
    machine = booted(image)

    plant = (
        bytes([0x81, 0x25, 0x00])
        + bytes([0x81, 0x28, 0x07])
        + RESULT.to_bytes(4, "big")
        + bytes([0x81, 0x29])
        + bytes([0x81, 0x28, 0x07])
        + SECOND.to_bytes(4, "big")
        + bytes([0x81, 0x20])
    )

    machine.memory.write_run(PLANT, plant)

    machine.pc = PLANT

    machine.run(limit=10)

    assert_that(machine.memory.read_word(RESULT)).is_equal_to(0)
    assert_that(machine.memory.read_word(SECOND)).is_equal_to(1)


# Save and restore through a Glk stream: the file lands in the
# stream, and restoring pours the state back -- execution resumes
# after the save with -1 stored, the turn's changes gone.
def test_save_and_restore_ride_a_glk_stream(
    image: Callable[..., bytes],
) -> None:
    library = Glk()
    machine = Machine(Story(image(code=IDLE)), glk=library)

    if machine.bridge is None:
        pytest.fail("the bridge is installed")

    held = [0] * 4096
    stream = library.glk_stream_open_memory(held, FileMode.READ_WRITE, 0)
    ident = machine.bridge.registry.register(stream, CLASS_STREAM)

    save = bytes([0x81, 0x23, 0x71, ident]) + RESULT.to_bytes(4, "big")

    machine.memory.write_run(PLANT, save)

    machine.pc = PLANT

    machine.step()

    resumed = PLANT + len(save)

    assert_that(machine.memory.read_word(RESULT)).is_equal_to(0)
    assert_that(bytes(held[:4])).is_equal_to(b"FORM")

    machine.memory.write_byte(MARKER, 0x99)

    library.glk_stream_set_position(stream, 0, SeekMode.START)

    machine.memory.write_run(
        PLANT + 0x20, bytes([0x81, 0x24, 0x71, ident]) + SECOND.to_bytes(4, "big")
    )

    machine.pc = PLANT + 0x20

    machine.step()

    assert_that(machine.pc).is_equal_to(resumed)
    assert_that(machine.memory.read_word(RESULT)).is_equal_to(RESTORED)
    assert_that(machine.memory.read_byte(MARKER)).is_equal_to(0)
    assert_that(machine.memory.read_word(SECOND)).is_equal_to(0)


# Every way a save or restore can fail speaks 1 rather than
# faulting: an id naming no stream, a stream that cannot be
# written or read, junk where a save file belongs, and a machine
# with no Glk at all.
def test_failed_saves_speak_one(image: Callable[..., bytes]) -> None:
    library = Glk()
    machine = Machine(Story(image(code=IDLE)), glk=library)

    if machine.bridge is None:
        pytest.fail("the bridge is installed")

    save_unknown = bytes([0x81, 0x23, 0x71, 0x63]) + RESULT.to_bytes(4, "big")

    machine.memory.write_run(PLANT, save_unknown)

    machine.pc = PLANT

    machine.step()

    assert_that(machine.memory.read_word(RESULT)).is_equal_to(1)

    # A read-only stream cannot take a save; a write-only stream
    # cannot give a restore; junk fails the parse.
    readable = library.glk_stream_open_memory([0x41] * 8, FileMode.READ, 0)
    writable = library.glk_stream_open_memory([0] * 8, FileMode.WRITE, 0)

    assert_that(serial.save(machine, readable)).is_equal_to(serial.FAILED)
    assert_that(serial.restore(machine, writable)).is_equal_to(serial.FAILED)
    assert_that(serial.restore(machine, readable)).is_equal_to(serial.FAILED)

    restore_unknown = bytes([0x81, 0x24, 0x71, 0x63]) + SECOND.to_bytes(4, "big")

    machine.memory.write_run(PLANT, restore_unknown)

    machine.pc = PLANT

    machine.step()

    assert_that(machine.memory.read_word(SECOND)).is_equal_to(1)

    # No library at all: the stream can never resolve.
    bare = booted(image)

    bare.memory.write_run(PLANT, save_unknown)

    bare.pc = PLANT

    bare.step()

    assert_that(bare.memory.read_word(RESULT)).is_equal_to(1)


# Undo states survive a restart: the chain is not part of the
# reset, so a state saved before the restart still pours back
# after it.
def test_undo_survives_restart(image: Callable[..., bytes]) -> None:
    machine = booted(image)

    machine.memory.write_byte(MARKER, 0x42)
    machine.stack.push_stub(DestType.DISCARD, 0, 0)

    serial.save_undo(machine)

    machine.restart()

    assert_that(machine.memory.read_byte(MARKER)).is_equal_to(0)
    assert_that(serial.restore_undo(machine)).is_equal_to(serial.SUCCEEDED)
    assert_that(machine.memory.read_byte(MARKER)).is_equal_to(0x42)
