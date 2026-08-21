"""Strings and output: the coroutine printer (Glulx: Strings)."""

from collections.abc import Callable

import pytest
from assertpy import assert_that

from voxam.errors import GlulxGlkError, GlulxStringError
from voxam.glulx import strings
from voxam.glulx.glk.api import Glk
from voxam.glulx.glk.objects import FileMode
from voxam.glulx.iosys import IOMode, IOSystem
from voxam.glulx.machine import Machine
from voxam.glulx.stack import DestType
from voxam.glulx.story import Story

PLANT = 0x140
TABLE = 0x190
TEXT = 0x1C0
BUFFER = 0x260
CURSOR = 0x2A0
FILTER = 0x58

# The observable-output harness: a C1 filter function that appends
# its one character argument to a RAM buffer and advances a cursor
# -- so every suspension-and-resume round trip leaves evidence.
FILTER_CODE = (
    bytes([0xC1, 0x04, 0x01, 0x00, 0x00])
    + bytes([0x4E, 0x63, 0x09, 0x00, 0x00, 0x02, 0x60, 0x02, 0xA0, 0x00])
    + bytes([0x10, 0x16, 0x06, 0x02, 0xA0, 0x01, 0x02, 0xA0])
    + bytes([0x31, 0x01, 0x00])
)

# An idle main, then the filter at $58.
CODE = bytes([0xC0, 0x00, 0x00, 0x81, 0x20]) + bytes(11) + FILTER_CODE

# setiosys 1, $58 -- select the filter -- and quit, for plants.
SELECT_FILTER = bytes([0x81, 0x49, 0x21, 0x01, 0x00, 0x58])
QUIT = bytes([0x81, 0x20])


def booted(image: Callable[..., bytes]) -> Machine:
    return Machine(Story(image(code=CODE)))


def glk_booted(image: Callable[..., bytes]) -> tuple[Machine, list[int]]:
    """A machine speaking Glk, its current stream held for reading."""

    library = Glk()
    held = [0] * 16

    library.glk_stream_set_current(
        library.glk_stream_open_memory_uni(held, FileMode.WRITE, 0)
    )

    machine = Machine(Story(image(code=CODE)), glk=library)

    machine.iosys.select(IOMode.GLK, 0)

    return machine, held


def spoken(image: Callable[..., bytes], plant: bytes) -> tuple[Machine, bytes]:
    """Run a plant under the filter; the captured output comes back."""

    machine = booted(image)

    machine.memory.write_run(PLANT, SELECT_FILTER + plant + QUIT)

    machine.pc = PLANT

    machine.run(limit=2000)

    count = machine.memory.read_word(CURSOR)

    return machine, machine.memory.read_run(BUFFER, count)


# The io system: three modes, and an unknown one selects the null
# system rather than erring -- what a probing program should find.
def test_the_io_system_selects_and_normalizes() -> None:
    iosys = IOSystem()

    iosys.select(IOMode.FILTER, 0x58)

    assert_that((iosys.mode, iosys.rock)).is_equal_to((1, 0x58))

    iosys.select(9, 7)

    assert_that((iosys.mode, iosys.rock)).is_equal_to((0, 0))

    iosys.select(IOMode.GLK, 3)
    iosys.reset()

    assert_that((iosys.mode, iosys.rock)).is_equal_to((0, 0))


# streamchar keeps its low byte, streamunichar the whole value, and
# streamnum prints a signed decimal one suspension at a time --
# every character a filter call, every resume picking up exactly
# where the print left off.
def test_characters_and_numbers_speak_through_the_filter(
    image: Callable[..., bytes],
) -> None:
    _, out = spoken(image, bytes([0x70, 0x02, 0x01, 0x48]))

    assert_that(out).is_equal_to(b"H")

    _, out = spoken(image, bytes([0x73, 0x01, 0x69]))

    assert_that(out).is_equal_to(b"i")

    _, out = spoken(image, bytes([0x71, 0x01, 0xD6]))

    assert_that(out).is_equal_to(b"-42")

    _, out = spoken(image, bytes([0x71, 0x01, 0x00]))

    assert_that(out).is_equal_to(b"0")


# The uncompressed strings: E0 bytes and E2 words, each character a
# suspension in filter mode, the resume stubs walking the string to
# its terminator.
def test_uncompressed_strings_stream_whole(image: Callable[..., bytes]) -> None:
    machine = booted(image)

    machine.memory.write_run(TEXT, bytes([0xE0, 0x41, 0x42, 0x00]))
    machine.memory.write_run(
        PLANT, SELECT_FILTER + bytes([0x72, 0x02, 0x01, 0xC0]) + QUIT
    )

    machine.pc = PLANT

    machine.run(limit=2000)

    assert_that(machine.memory.read_run(BUFFER, 2)).is_equal_to(b"AB")

    wide = booted(image)

    wide.memory.write_run(
        0x1D0,
        bytes([0xE2, 0x00, 0x00, 0x00])
        + (0x43).to_bytes(4, "big")
        + (0x44).to_bytes(4, "big")
        + bytes(4),
    )
    wide.memory.write_run(PLANT, SELECT_FILTER + bytes([0x72, 0x02, 0x01, 0xD0]) + QUIT)

    wide.pc = PLANT

    wide.run(limit=2000)

    assert_that(wide.memory.read_run(BUFFER, 2)).is_equal_to(b"CD")


def planted_table(machine: Machine, nodes: bytes, root: int) -> None:
    """Lay a decoding table at TABLE: header words, then the nodes."""

    machine.memory.write_run(
        TABLE,
        (12 + len(nodes)).to_bytes(4, "big")
        + (0).to_bytes(4, "big")
        + root.to_bytes(4, "big")
        + nodes,
    )


# A branch-and-char tree: root sends bit 0 to 'a', bit 1 to a
# second branch of 'b' and the terminator. The bits read low bit
# first, so "ab" is the byte 0x1A -- and in filter mode every
# character suspends mid-tree, the resume stub carrying the bit
# number back (Glulx: The String-Decoding Table).
def test_compressed_strings_walk_their_tree(image: Callable[..., bytes]) -> None:
    machine = booted(image)
    nodes = (
        bytes([0x00])
        + (TABLE + 21).to_bytes(4, "big")
        + (TABLE + 23).to_bytes(4, "big")
        + bytes([0x02, 0x61])
        + bytes([0x00])
        + (TABLE + 32).to_bytes(4, "big")
        + (TABLE + 34).to_bytes(4, "big")
        + bytes([0x02, 0x62])
        + bytes([0x01])
    )

    planted_table(machine, nodes, TABLE + 12)
    machine.memory.write_run(TEXT, bytes([0xE1, 0x1A]))
    machine.memory.write_run(
        PLANT,
        SELECT_FILTER
        + bytes([0x81, 0x41, 0x02, 0x01, 0x90])
        + bytes([0x72, 0x02, 0x01, 0xC0])
        + QUIT,
    )

    machine.pc = PLANT

    machine.run(limit=2000)

    assert_that(machine.memory.read_run(BUFFER, 2)).is_equal_to(b"ab")

    # The same string in the null mode decodes and discards.
    quiet = booted(image)

    planted_table(quiet, nodes, TABLE + 12)
    quiet.memory.write_run(TEXT, bytes([0xE1, 0x1A]))
    quiet.string_table = TABLE

    strings.stream_string(quiet, TEXT)

    assert_that(quiet.memory.read_word(CURSOR)).is_equal_to(0)


# The richer nodes: a unichar, an embedded C string, an indirect
# reference to a whole string, a double-indirect one, and an
# indirect function call carrying arguments from the node itself --
# each suspending into the filter and resuming mid-tree.
def test_the_richer_nodes_print_and_call(image: Callable[..., bytes]) -> None:
    # Root: bit 0 to a five-way chain, bit 1 to the terminator.
    # The chain node is picked per string by pointing the root's
    # zero branch at it.
    for node, expected in (
        (bytes([0x04]) + (0x21).to_bytes(4, "big"), b"!"),
        (bytes([0x03, 0x58, 0x59, 0x00]), b"XY"),
        (bytes([0x08]) + (TEXT + 8).to_bytes(4, "big"), b"Q"),
        (bytes([0x09]) + (TEXT + 16).to_bytes(4, "big"), b"Q"),
        (
            bytes([0x0A])
            + FILTER.to_bytes(4, "big")
            + (1).to_bytes(4, "big")
            + (0x23).to_bytes(4, "big"),
            b"#",
        ),
    ):
        fresh = booted(image)
        nodes = (
            bytes([0x00])
            + (TABLE + 21).to_bytes(4, "big")
            + (TABLE + 21 + len(node)).to_bytes(4, "big")
            + node
            + bytes([0x01])
        )

        planted_table(fresh, nodes, TABLE + 12)
        # An E0 target for the indirect nodes, and a pointer cell
        # for the double-indirect one.
        fresh.memory.write_run(TEXT + 8, bytes([0xE0, 0x51, 0x00]))
        fresh.memory.write_word(TEXT + 16, TEXT + 8)
        # The string: bit 0 (the node), then bit 1 (the terminator)
        # -- the byte 0b00000010.
        fresh.memory.write_run(TEXT, bytes([0xE1, 0x02]))
        fresh.memory.write_run(
            PLANT,
            SELECT_FILTER
            + bytes([0x81, 0x41, 0x02, 0x01, 0x90])
            + bytes([0x72, 0x02, 0x01, 0xC0])
            + QUIT,
        )

        fresh.pc = PLANT

        fresh.run(limit=2000)

        count = fresh.memory.read_word(CURSOR)

        assert_that(fresh.memory.read_run(BUFFER, count)).is_equal_to(expected)


# Every lie a string can tell halts loudly: a null address, a type
# byte that is no string or a reserved future one, a compressed
# print with no table, a node the table may not hold, and an
# indirect reference to something neither string nor function.
def test_broken_strings_halt_loudly(image: Callable[..., bytes]) -> None:
    machine = booted(image)

    with pytest.raises(GlulxStringError, match="null address"):
        strings.stream_string(machine, 0)

    machine.memory.write_byte(TEXT, 0x40)

    with pytest.raises(GlulxStringError, match="not a string at all"):
        strings.stream_string(machine, TEXT)

    machine.memory.write_byte(TEXT, 0xE5)

    with pytest.raises(GlulxStringError, match="reserved for the future"):
        strings.stream_string(machine, TEXT)

    machine.memory.write_run(TEXT, bytes([0xE1, 0x00]))
    machine.string_table = 0

    with pytest.raises(GlulxStringError, match="no decoding table"):
        strings.stream_string(machine, TEXT)

    planted_table(machine, bytes([0x07]), TABLE + 12)

    machine.string_table = TABLE

    with pytest.raises(GlulxStringError, match="not one the decoding table"):
        strings.stream_string(machine, TEXT)

    machine.memory.write_byte(0x250, 0x50)
    planted_table(machine, bytes([0x08]) + (0x250).to_bytes(4, "big"), TABLE + 12)

    with pytest.raises(GlulxStringError, match="neither a string nor"):
        strings.stream_string(machine, TEXT)


# The stub-discipline errors: a number print interrupted by the
# wrong stub, and a string ending into a stub that belongs to
# neither kind of resume.
def test_stub_discipline_is_enforced(image: Callable[..., bytes]) -> None:
    machine = booted(image)

    machine.iosys.select(IOMode.FILTER, FILTER)
    machine.stack.push_stub(DestType.RESUME_COMPRESSED, 0, 0)

    with pytest.raises(GlulxStringError, match="string-on-string"):
        strings.stream_num(machine, 5, in_middle=True, charnum=1)

    wrong = booted(image)

    wrong.memory.write_byte(TEXT, 0)
    wrong.stack.push_stub(DestType.MEMORY, 0, 0)

    with pytest.raises(GlulxStringError, match="function-terminator"):
        strings.stream_string(wrong, TEXT, in_middle=strings.CSTRING)


# Glk mode hands every character to the installed library: bytes
# through the narrow put, wider characters through the Unicode
# call, from every printing opcode alike. Without a library the
# mode can only be forced, and forcing it is refused by name.
def test_glk_output_reaches_the_library(image: Callable[..., bytes]) -> None:
    machine, held = glk_booted(image)

    strings.put_char(machine, 0x41)

    machine.memory.write_run(TEXT, bytes([0xE0, 0x42, 0x00]))
    strings.stream_string(machine, TEXT)

    machine.memory.write_run(
        0x1D0,
        bytes([0xE2, 0x00, 0x00, 0x00])
        + (0x2603).to_bytes(4, "big")
        + (0x43).to_bytes(4, "big")
        + bytes(4),
    )
    strings.stream_string(machine, 0x1D0)

    strings.stream_num(machine, 0xFFFFFFF9)

    assert_that(held[:7]).is_equal_to([0x41, 0x42, 0x2603, 0x43, ord("-"), ord("7"), 0])

    bare = booted(image)

    bare.iosys.select(IOMode.GLK, 0)

    with pytest.raises(GlulxGlkError, match="no Glk library"):
        strings.put_char(bare, 0x41)


# The null system decodes everything and prints nothing: characters,
# numbers, byte strings, and a compressed string long enough to
# roll the bit cursor into its second byte -- "bbbb" is ten bits.
def test_the_null_system_decodes_and_discards(
    image: Callable[..., bytes],
) -> None:
    machine = booted(image)

    strings.put_char(machine, 0x41)
    strings.stream_num(machine, 0x2A)
    machine.memory.write_run(TEXT, bytes([0xE0, 0x41, 0x00]))
    strings.stream_string(machine, TEXT)
    machine.memory.write_run(
        0x1D0, bytes([0xE2, 0x00, 0x00, 0x00]) + (0x41).to_bytes(4, "big") + bytes(4)
    )
    strings.stream_string(machine, 0x1D0)

    nodes = (
        bytes([0x00])
        + (TABLE + 21).to_bytes(4, "big")
        + (TABLE + 23).to_bytes(4, "big")
        + bytes([0x02, 0x61])
        + bytes([0x00])
        + (TABLE + 32).to_bytes(4, "big")
        + (TABLE + 34).to_bytes(4, "big")
        + bytes([0x02, 0x62])
        + bytes([0x01])
    )

    planted_table(machine, nodes, TABLE + 12)
    machine.memory.write_run(TEXT, bytes([0xE1, 0x55, 0x03]))

    machine.string_table = TABLE

    strings.stream_string(machine, TEXT)

    assert_that(machine.memory.read_word(CURSOR)).is_equal_to(0)


# The richer nodes in the null system walk without printing: the
# unichar, both embedded strings, and an argumentless indirect
# function call that still runs its function.
def test_the_richer_nodes_decode_in_the_null_system(
    image: Callable[..., bytes],
) -> None:
    for node in (
        bytes([0x04]) + (0x2603).to_bytes(4, "big"),
        bytes([0x03, 0x58, 0x00]),
        bytes([0x05]) + (0x59).to_bytes(4, "big") + bytes(4),
    ):
        machine = booted(image)
        nodes = (
            bytes([0x00])
            + (TABLE + 21).to_bytes(4, "big")
            + (TABLE + 21 + len(node)).to_bytes(4, "big")
            + node
            + bytes([0x01])
        )

        planted_table(machine, nodes, TABLE + 12)
        machine.memory.write_run(TEXT, bytes([0xE1, 0x02]))

        machine.string_table = TABLE

        strings.stream_string(machine, TEXT)

        assert_that(machine.memory.read_word(CURSOR)).is_equal_to(0)

    # A unistr node under the filter prints its low bytes.
    fresh = booted(image)
    wide = bytes([0x05]) + (0x59).to_bytes(4, "big") + bytes(4)
    nodes = (
        bytes([0x00])
        + (TABLE + 21).to_bytes(4, "big")
        + (TABLE + 21 + len(wide)).to_bytes(4, "big")
        + wide
        + bytes([0x01])
    )

    planted_table(fresh, nodes, TABLE + 12)
    fresh.memory.write_run(TEXT, bytes([0xE1, 0x02]))
    fresh.memory.write_run(
        PLANT,
        SELECT_FILTER
        + bytes([0x81, 0x41, 0x02, 0x01, 0x90])
        + bytes([0x72, 0x02, 0x01, 0xC0])
        + QUIT,
    )

    fresh.pc = PLANT

    fresh.run(limit=2000)

    assert_that(fresh.memory.read_run(BUFFER, 1)).is_equal_to(b"Y")

    # An argumentless indirect function call enters its function
    # with no arguments at all.
    called = booted(image)
    caller = bytes([0x08]) + FILTER.to_bytes(4, "big")
    nodes = (
        bytes([0x00])
        + (TABLE + 21).to_bytes(4, "big")
        + (TABLE + 21 + len(caller)).to_bytes(4, "big")
        + caller
        + bytes([0x01])
    )

    planted_table(called, nodes, TABLE + 12)
    called.memory.write_run(TEXT, bytes([0xE1, 0x02]))
    called.memory.write_run(
        PLANT,
        SELECT_FILTER
        + bytes([0x81, 0x41, 0x02, 0x01, 0x90])
        + bytes([0x72, 0x02, 0x01, 0xC0])
        + QUIT,
    )

    called.pc = PLANT

    called.run(limit=2000)

    assert_that(called.memory.read_run(BUFFER, 1)).is_equal_to(b"\x00")


# Glk mode walks empty embedded strings without a character to
# refuse, and a number already fully printed has nothing left to
# hand Glk either.
def test_glk_mode_survives_what_prints_nothing(
    image: Callable[..., bytes],
) -> None:
    for empty in (
        bytes([0x03, 0x00]),
        bytes([0x05]) + bytes(4),
    ):
        machine = booted(image)
        nodes = (
            bytes([0x00])
            + (TABLE + 21).to_bytes(4, "big")
            + (TABLE + 21 + len(empty)).to_bytes(4, "big")
            + empty
            + bytes([0x01])
        )

        planted_table(machine, nodes, TABLE + 12)
        machine.memory.write_run(TEXT, bytes([0xE1, 0x02]))

        machine.string_table = TABLE
        machine.iosys.select(IOMode.GLK, 0)

        strings.stream_string(machine, TEXT)

    spent = booted(image)

    spent.iosys.select(IOMode.GLK, 0)
    strings.stream_num(spent, 7, charnum=1)

    # And every node kind with a character to print delivers it: a
    # char node, and both embedded string kinds walked to their
    # terminators.
    for node, expected in (
        (bytes([0x02, 0x61]), [0x61]),
        (bytes([0x03, 0x58, 0x59, 0x00]), [0x58, 0x59]),
        (
            bytes([0x05])
            + (0x1F600).to_bytes(4, "big")
            + (0x5A).to_bytes(4, "big")
            + bytes(4),
            [0x1F600, 0x5A],
        ),
    ):
        noisy, held = glk_booted(image)
        nodes = (
            bytes([0x00])
            + (TABLE + 21).to_bytes(4, "big")
            + (TABLE + 21 + len(node)).to_bytes(4, "big")
            + node
            + bytes([0x01])
        )

        planted_table(noisy, nodes, TABLE + 12)
        noisy.memory.write_run(TEXT, bytes([0xE1, 0x02]))

        noisy.string_table = TABLE

        strings.stream_string(noisy, TEXT)

        assert_that(held[: len(expected)]).is_equal_to(expected)


# The bookkeeping opcodes: the table and io system read back what
# was set, and an unknown mode lands as the null system.
def test_the_bookkeeping_opcodes_answer(image: Callable[..., bytes]) -> None:
    machine = booted(image)

    machine.memory.write_run(
        PLANT,
        bytes([0x81, 0x49, 0x21, 0x09, 0x00, 0x07])
        + bytes([0x81, 0x48, 0x77, 0x00, 0x00, 0x02, 0xB0, 0x00, 0x00, 0x02, 0xB4])
        + bytes([0x81, 0x41, 0x02, 0x01, 0x90])
        + bytes([0x81, 0x40, 0x07, 0x00, 0x00, 0x02, 0xB8])
        + QUIT,
    )

    machine.pc = PLANT

    machine.run(limit=100)

    assert_that(machine.memory.read_word(0x2B0)).is_equal_to(0)
    assert_that(machine.memory.read_word(0x2B4)).is_equal_to(0)
    assert_that(machine.memory.read_word(0x2B8)).is_equal_to(TABLE)


# A restart returns the machine to the null system and the header's
# own decoding table.
def test_restart_resets_the_output_state(image: Callable[..., bytes]) -> None:
    machine = booted(image)

    machine.iosys.select(IOMode.FILTER, FILTER)
    machine.string_table = TABLE

    machine.restart()

    assert_that(machine.iosys.mode).is_equal_to(0)
    assert_that(machine.string_table).is_equal_to(0x54)
