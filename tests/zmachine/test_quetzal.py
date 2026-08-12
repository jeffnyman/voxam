import dataclasses

import pytest
from assertpy import assert_that

from voxam.errors import ZMachineQuetzalError
from voxam.zmachine.machine import Machine
from voxam.zmachine.quetzal import read, write
from voxam.zmachine.snapshot import FrameSnapshot, Snapshot
from voxam.zmachine.story import Story

# The result global: variable $10, first entry of the table at $100.
RESULT_VARIABLE = 0x10
RESULT_ADDRESS = 0x100

# A routine planted at $60 is packed 0x30 under Version 3's scale
# factor of 2.
ROUTINE_A_PACKED = bytes([0x00, 0x30])

# The conftest story shape: dynamic memory below $1C0.
STATIC_BASE = 0x1C0


def build_story(
    code: bytes = b"", release: int = 0, checksum: int = 0, version: int = 3
) -> Story:
    data = bytearray(512)
    data[0] = version
    data[0x02:0x04] = release.to_bytes(2, "big")
    data[0x04:0x06] = (0x01C0).to_bytes(2, "big")
    data[0x06:0x08] = (0x0040).to_bytes(2, "big")
    data[0x0C:0x0E] = (0x0100).to_bytes(2, "big")
    data[0x0E:0x10] = STATIC_BASE.to_bytes(2, "big")
    data[0x1C:0x1E] = checksum.to_bytes(2, "big")
    data[0x40 : 0x40 + len(code)] = code

    return Story(bytes(data))


def layout(main: bytes, routine_a: bytes = b"") -> bytes:
    code = bytearray(0x40)
    code[: len(main)] = main
    code[0x20 : 0x20 + len(routine_a)] = routine_a

    return bytes(code)


def in_flight_snapshot() -> tuple[Snapshot, Story]:
    """A snapshot two steps in: a routine holding an argument, a
    header-default local, a pushed word, and a pending store."""

    main = bytes([0xE0, 0x1F, *ROUTINE_A_PACKED, 99, RESULT_VARIABLE, 0xBA])
    pushes_42 = bytes([0x02, 0x00, 0x07, 0x00, 0x08, 0xE8, 0x7F, 0x2A, 0xB8])
    story = build_story(layout(main, pushes_42))
    machine = Machine(story)

    machine.step()
    machine.step()

    return machine.snapshot(), story


def chunk(chunk_id: bytes, payload: bytes) -> bytes:
    pad = b"\x00" if len(payload) % 2 else b""

    return chunk_id + len(payload).to_bytes(4, "big") + payload + pad


def form(*chunks: bytes) -> bytes:
    body = b"IFZS" + b"".join(chunks)

    return b"FORM" + len(body).to_bytes(4, "big") + body


# The dummy frame of Quetzal §4.11.1 with an empty evaluation stack
# is eight zero bytes; a boot-fresh IFhd is eight identity zeros and
# a PC.
def dummy_stks() -> bytes:
    return bytes(8)


def bare_ifhd(story: Story, pc: int) -> bytes:
    release = story.header.release.to_bytes(2, "big")
    serial = story.data[0x12:0x18]
    checksum = story.header.stored_checksum.to_bytes(2, "big")

    return release + serial + checksum + pc.to_bytes(3, "big")


# The whole point of the codec: a state of play captured mid-call --
# locals, pushed words, argument count, pending store -- survives the
# trip into IFZS bytes and back, exactly (Quetzal §2, §3, §4).
def test_a_snapshot_survives_the_round_trip() -> None:
    snapshot, story = in_flight_snapshot()

    assert_that(read(write(snapshot, story), story)).is_equal_to(snapshot)


# The file honors its container format: a FORM of type IFZS whose
# first chunk is the 13-byte IFhd, padded to even length as §8.4.1
# demands of odd chunks (Quetzal §2.1, §5.4, §5.7).
def test_the_file_is_a_well_formed_ifzs_form() -> None:
    snapshot, story = in_flight_snapshot()
    data = write(snapshot, story)

    assert_that(data[:4]).is_equal_to(b"FORM")
    assert_that(data[8:12]).is_equal_to(b"IFZS")
    assert_that(data[12:16]).is_equal_to(b"IFhd")
    assert_that(int.from_bytes(data[16:20], "big")).is_equal_to(13)
    assert_that(data[33]).is_equal_to(0)
    assert_that(len(data) % 2).is_zero()
    assert_that(int.from_bytes(data[4:8], "big")).is_equal_to(len(data) - 8)


# Compression is exclusive-or against the pristine story, so a
# snapshot in which nothing has changed compresses to nothing at all
# (Quetzal §3.2, §3.4).
def test_unchanged_memory_compresses_to_nothing() -> None:
    story = build_story()
    snapshot = Snapshot(
        dynamic_memory=story.data[:STATIC_BASE],
        pc=0x40,
        frames=(
            FrameSnapshot(
                return_address=0,
                store_variable=None,
                locals=(),
                argument_count=0,
                stack=(),
            ),
        ),
    )
    data = write(snapshot, story)
    cmem_at = data.index(b"CMem")

    assert_that(int.from_bytes(data[cmem_at + 4 : cmem_at + 8], "big")).is_zero()


# A run of unchanged bytes longer than one length byte can carry
# (256) must split into adjacent runs -- and still decode (Quetzal
# §3.2, §3.3).
def test_changes_separated_by_a_long_run_survive() -> None:
    snapshot, story = in_flight_snapshot()
    doctored = bytearray(snapshot.dynamic_memory)
    doctored[0x50] ^= 0xAA
    doctored[0x1B0] ^= 0xBB
    snapshot = dataclasses.replace(snapshot, dynamic_memory=bytes(doctored))

    assert_that(read(write(snapshot, story), story)).is_equal_to(snapshot)


# Reading both memory encodings is required (Quetzal §3.6): a UMem
# dump of exactly dynamic memory reads back like any CMem would.
def test_a_umem_dump_reads_back() -> None:
    story = build_story()
    machine = Machine(story)
    snapshot = machine.snapshot()
    data = form(
        chunk(b"IFhd", bare_ifhd(story, snapshot.pc)),
        chunk(b"UMem", snapshot.dynamic_memory),
        chunk(b"Stks", dummy_stks()),
    )

    assert_that(read(data, story)).is_equal_to(snapshot)


# A UMem dump any other size than dynamic memory is an error
# (Quetzal §3.6).
def test_a_wrongly_sized_umem_dump_is_refused() -> None:
    story = build_story()
    data = form(
        chunk(b"IFhd", bare_ifhd(story, 0x40)),
        chunk(b"UMem", bytes(STATIC_BASE - 1)),
        chunk(b"Stks", dummy_stks()),
    )

    with pytest.raises(ZMachineQuetzalError, match="UMem dump must be exactly"):
        read(data, story)


# The two read errors of Quetzal §3.5: an incomplete run, and data
# that decodes to more than dynamic memory holds.
def test_cmem_ending_mid_run_is_refused() -> None:
    story = build_story()
    data = form(
        chunk(b"IFhd", bare_ifhd(story, 0x40)),
        chunk(b"CMem", b"\x00"),
        chunk(b"Stks", dummy_stks()),
    )

    with pytest.raises(ZMachineQuetzalError, match="no run length"):
        read(data, story)


def test_cmem_decoding_past_dynamic_memory_is_refused() -> None:
    story = build_story()
    data = form(
        chunk(b"IFhd", bare_ifhd(story, 0x40)),
        chunk(b"CMem", b"\x00\xff" * 2),
        chunk(b"Stks", dummy_stks()),
    )

    with pytest.raises(ZMachineQuetzalError, match="decodes to"):
        read(data, story)


# A save names its story by release, serial, and checksum; any
# difference is a refusal (Quetzal §5.3, and §6.1.2.1 of the
# Standard).
def test_a_save_from_a_different_game_is_refused() -> None:
    snapshot, story = in_flight_snapshot()
    data = write(snapshot, story)
    other = build_story(layout(bytes([0xBA])), release=7)

    with pytest.raises(ZMachineQuetzalError, match="different game"):
        read(data, other)


# A story too old to store a checksum gets one computed from its
# file when saving, and the same computation when checking
# (Quetzal §5.5) -- while a stored checksum is used as stored.
def test_a_stored_checksum_names_the_story() -> None:
    story = build_story(checksum=0xBEEF)
    machine = Machine(story)
    snapshot = machine.snapshot()

    assert_that(read(write(snapshot, story), story)).is_equal_to(snapshot)


# Extension chunks an interpreter does not understand are skipped
# without complaint (Quetzal §7.17, §8.6).
def test_unknown_chunks_are_skipped() -> None:
    story = build_story()
    snapshot = Machine(story).snapshot()
    data = form(
        chunk(b"IFhd", bare_ifhd(story, snapshot.pc)),
        chunk(b"ANNO", b"seven games down"),
        chunk(b"UMem", snapshot.dynamic_memory),
        chunk(b"Stks", dummy_stks()),
    )

    assert_that(read(data, story)).is_equal_to(snapshot)


# IFhd must come before the memory and stack chunks, to spare
# readers decoding them for the wrong story (Quetzal §5.4).
def test_a_memory_chunk_before_ifhd_is_refused() -> None:
    story = build_story()
    snapshot = Machine(story).snapshot()
    data = form(
        chunk(b"UMem", snapshot.dynamic_memory),
        chunk(b"IFhd", bare_ifhd(story, snapshot.pc)),
        chunk(b"Stks", dummy_stks()),
    )

    with pytest.raises(ZMachineQuetzalError, match="before IFhd"):
        read(data, story)


# The three required chunks of Quetzal §7.18, each missed in turn.
def test_a_missing_ifhd_is_refused() -> None:
    story = build_story()

    with pytest.raises(ZMachineQuetzalError, match="IFhd chunk is missing"):
        read(form(chunk(b"ANNO", b"empty")), story)


def test_a_missing_stks_is_refused() -> None:
    story = build_story()
    data = form(chunk(b"IFhd", bare_ifhd(story, 0x40)), chunk(b"CMem", b""))

    with pytest.raises(ZMachineQuetzalError, match="Stks chunk is missing"):
        read(data, story)


def test_a_missing_memory_chunk_is_refused() -> None:
    story = build_story()
    data = form(chunk(b"IFhd", bare_ifhd(story, 0x40)), chunk(b"Stks", dummy_stks()))

    with pytest.raises(ZMachineQuetzalError, match="CMem or UMem chunk is missing"):
        read(data, story)


def test_carrying_both_memory_chunks_is_refused() -> None:
    story = build_story()
    snapshot = Machine(story).snapshot()
    data = form(
        chunk(b"IFhd", bare_ifhd(story, 0x40)),
        chunk(b"CMem", b""),
        chunk(b"UMem", snapshot.dynamic_memory),
        chunk(b"Stks", dummy_stks()),
    )

    with pytest.raises(ZMachineQuetzalError, match="one or the other"):
        read(data, story)


def test_a_doubled_chunk_is_refused() -> None:
    story = build_story()
    data = form(
        chunk(b"IFhd", bare_ifhd(story, 0x40)),
        chunk(b"IFhd", bare_ifhd(story, 0x40)),
    )

    with pytest.raises(ZMachineQuetzalError, match="appears twice"):
        read(data, story)


# Malformed containers, each refused with the container rule it
# breaks (Quetzal §2.1, §8.3, §8.4, §8.5).
def test_a_file_without_a_form_chunk_is_refused() -> None:
    with pytest.raises(ZMachineQuetzalError, match="no FORM chunk"):
        read(b"JUNKJUNKJUNKJUNK", build_story())

    with pytest.raises(ZMachineQuetzalError, match="no FORM chunk"):
        read(b"FO", build_story())


def test_a_form_claiming_more_than_the_file_is_refused() -> None:
    with pytest.raises(ZMachineQuetzalError, match="FORM chunk claims"):
        read(b"FORM" + (99).to_bytes(4, "big") + b"IFZS", build_story())


def test_a_form_of_another_type_is_refused() -> None:
    data = b"FORM" + (4).to_bytes(4, "big") + b"AIFF"

    with pytest.raises(ZMachineQuetzalError, match="not the IFZS"):
        read(data, build_story())


def test_a_chunk_cut_short_mid_header_is_refused() -> None:
    body = b"IFZS" + b"IFhd"
    data = b"FORM" + len(body).to_bytes(4, "big") + body

    with pytest.raises(ZMachineQuetzalError, match="cut short mid-header"):
        read(data, build_story())


def test_a_chunk_claiming_past_the_form_is_refused() -> None:
    body = b"IFZS" + b"IFhd" + (99).to_bytes(4, "big")
    data = b"FORM" + len(body).to_bytes(4, "big") + body

    with pytest.raises(ZMachineQuetzalError, match="chunk claims"):
        read(data, build_story())


# The first 13 bytes of IFhd are guaranteed; fewer is not an IFhd
# (Quetzal §5.5).
def test_a_short_ifhd_is_refused() -> None:
    story = build_story()
    data = form(
        chunk(b"IFhd", bytes(5)),
        chunk(b"CMem", b""),
        chunk(b"Stks", dummy_stks()),
    )

    with pytest.raises(ZMachineQuetzalError, match="fewer than"):
        read(data, story)


# Frame decoding polices its format: truncations, reserved flag
# bits, gapped argument masks, a first frame that is not the dummy,
# and a Stks with no frames at all (Quetzal §4.3, §4.11).
def test_a_frame_cut_short_mid_header_is_refused() -> None:
    story = build_story()
    data = form(
        chunk(b"IFhd", bare_ifhd(story, 0x40)),
        chunk(b"CMem", b""),
        chunk(b"Stks", bytes(7)),
    )

    with pytest.raises(ZMachineQuetzalError, match="cut short mid-header"):
        read(data, story)


def test_a_frame_cut_short_mid_words_is_refused() -> None:
    story = build_story()
    stks = bytes(6) + (2).to_bytes(2, "big")
    data = form(
        chunk(b"IFhd", bare_ifhd(story, 0x40)),
        chunk(b"CMem", b""),
        chunk(b"Stks", stks),
    )

    with pytest.raises(ZMachineQuetzalError, match="cut short mid-words"):
        read(data, story)


def test_reserved_flag_bits_are_refused() -> None:
    story = build_story()
    stks = dummy_stks() + bytes([0, 5, 0, 0x20, 0, 0, 0, 0])
    data = form(
        chunk(b"IFhd", bare_ifhd(story, 0x40)),
        chunk(b"CMem", b""),
        chunk(b"Stks", stks),
    )

    with pytest.raises(ZMachineQuetzalError, match="reserved bits"):
        read(data, story)


def test_a_gapped_argument_mask_is_refused() -> None:
    story = build_story()
    stks = dummy_stks() + bytes([0, 5, 0, 0x00, 0, 0x05, 0, 0])
    data = form(
        chunk(b"IFhd", bare_ifhd(story, 0x40)),
        chunk(b"CMem", b""),
        chunk(b"Stks", stks),
    )

    with pytest.raises(ZMachineQuetzalError, match="has gaps"):
        read(data, story)


def test_a_first_frame_that_is_not_the_dummy_is_refused() -> None:
    story = build_story()
    stks = bytes([0, 0, 0, 0x01, 0, 0, 0, 0, 0, 7])
    data = form(
        chunk(b"IFhd", bare_ifhd(story, 0x40)),
        chunk(b"CMem", b""),
        chunk(b"Stks", stks),
    )

    with pytest.raises(ZMachineQuetzalError, match="must be the dummy"):
        read(data, story)


def test_an_empty_stks_is_refused() -> None:
    story = build_story()
    data = form(
        chunk(b"IFhd", bare_ifhd(story, 0x40)),
        chunk(b"CMem", b""),
        chunk(b"Stks", b""),
    )

    with pytest.raises(ZMachineQuetzalError, match="dummy frame is always present"):
        read(data, story)


# A discard-result call has its p flag set and its store byte
# written as zero, and comes back as a frame with no store variable
# (Quetzal §4.6).
def test_a_discard_result_frame_survives_the_round_trip() -> None:
    snapshot, story = in_flight_snapshot()
    discarding = FrameSnapshot(
        return_address=0x123,
        store_variable=None,
        locals=(1, 2),
        argument_count=2,
        stack=(9,),
    )
    snapshot = dataclasses.replace(snapshot, frames=(snapshot.frames[0], discarding))

    assert_that(read(write(snapshot, story), story)).is_equal_to(snapshot)


# What the format cannot carry is refused on the way out: a snapshot
# from another game's shape (Quetzal §5.3), an address past three
# bytes (Quetzal §4.3.1), and more arguments than the mask has bits
# (Quetzal §4.3.4).
def test_writing_a_foreign_snapshot_is_refused() -> None:
    snapshot, story = in_flight_snapshot()
    foreign = dataclasses.replace(
        snapshot, dynamic_memory=snapshot.dynamic_memory + b"\x00"
    )

    with pytest.raises(ZMachineQuetzalError, match="different game"):
        write(foreign, story)


def test_writing_an_oversized_pc_is_refused() -> None:
    snapshot, story = in_flight_snapshot()
    distant = dataclasses.replace(snapshot, pc=0x1000000)

    with pytest.raises(ZMachineQuetzalError, match="three bytes"):
        write(distant, story)


def test_writing_too_many_arguments_is_refused() -> None:
    snapshot, story = in_flight_snapshot()
    crowded = dataclasses.replace(
        snapshot,
        frames=(
            snapshot.frames[0],
            dataclasses.replace(snapshot.frames[1], argument_count=8),
        ),
    )

    with pytest.raises(ZMachineQuetzalError, match="seven argument bits"):
        write(crowded, story)


# The codec joins the machine end to end: save mid-flight in a
# routine that has pushed its answer, restore a fresh machine from
# the file's bytes, and the interrupted call still delivers it
# (§6.1.2 of the Standard).
def test_a_restored_save_finishes_the_game() -> None:
    snapshot, story = in_flight_snapshot()
    data = write(snapshot, story)

    machine = Machine(story)
    machine.restore(read(data, story))
    machine.run()

    assert_that(machine.memory.read_word(RESULT_ADDRESS)).is_equal_to(42)
