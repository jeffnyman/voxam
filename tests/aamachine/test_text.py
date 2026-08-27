"""Tests for the Å-machine's text decoding.

The stories here are built by hand around tiny decoding tables,
so every bitstream's meaning is spelled out in the test that
walks it (Aa-machine: LANG; DICT; WRIT).
"""

import zlib

import pytest
from assertpy import assert_that

from voxam.aamachine.story import SUMMED, Story
from voxam.aamachine.text import Speech
from voxam.errors import AAMachineError
from voxam.iff import chunk as iff_chunk

# The workhorse table: entry 0 offers the letter a or a jump to
# entry 1; entry 1 offers the escape or the end mark. Every walk
# below is a sentence in this two-entry language.
TABLE = bytes([0x41, 0x81, 0x5F, 0x80])

# A one-entry table whose either bit jumps far past the chunk.
RUNAWAY_TABLE = bytes([0xFF, 0xFF])

# A one-entry table whose first bit is the character-set byte
# $80: the first extended character, ridden directly.
EXTENDED_TABLE = bytes([0x60, 0x80])


def langed(table: bytes, extended: tuple[int, ...] = ()) -> bytes:
    """A LANG payload: offset header, decoding table, extended table."""

    charactered = bytes([len(extended)]) + b"".join(
        bytes([point & 0xFF, point & 0xFF]) + point.to_bytes(3, "big")
        for point in extended
    )

    return (
        (8).to_bytes(2, "big")
        + (8 + len(table)).to_bytes(2, "big")
        + b"\x00\x00\x00\x00"
        + table
        + charactered
    )


def worded(*words: bytes) -> bytes:
    """A DICT payload holding the given words, arrays after the table."""

    table_end = 2 + 3 * len(words)
    entries = []
    arrays = []
    at = table_end

    for word in words:
        entries.append(bytes([len(word)]) + at.to_bytes(2, "big"))
        arrays.append(word)
        at += len(word)

    return len(words).to_bytes(2, "big") + b"".join(entries) + b"".join(arrays)


def storied(
    lang: bytes,
    writ: bytes = b"",
    dictionary: bytes = b"\x00\x00",
    version: tuple[int, int] = (0, 5),
    shift: int = 0,
) -> Story:
    """A minimal story around the given LANG, WRIT, and DICT."""

    summed = {b"LANG": lang, b"WRIT": writ, b"DICT": dictionary}
    crc = 0

    for name in SUMMED:
        crc = zlib.crc32(summed.get(name, b""), crc)

    head = (
        bytes([*version, 2, shift])
        + (1).to_bytes(2, "big")
        + b"260827"
        + crc.to_bytes(4, "big")
        + bytes(6)
    )
    pieces = [iff_chunk(b"HEAD", head)]

    for name in SUMMED:
        pieces.append(iff_chunk(name, summed.get(name, b"")))

    return Story(iff_chunk(b"FORM", b"AAVM" + b"".join(pieces)))


def packed(bits: str) -> bytes:
    """Bits as WRIT bytes, MSB first, zero-padded to the boundary.

    Spaces group the bits by meaning -- one walk step, one escape
    read -- and pack to nothing.
    """

    told = bits.replace(" ", "")
    padded = told + "0" * (-len(told) % 8)

    return bytes(int(padded[at : at + 8], 2) for at in range(0, len(padded), 8))


# The simplest whole walk: bit 0 spells the letter a from the
# root, and the 1-1 path reaches entry 1's end mark. The walk
# returns to the root after each character, so two letters are
# just the letter bit twice.
def test_direct_characters_spell_and_the_end_mark_closes() -> None:
    speech = Speech(storied(langed(TABLE), writ=packed("0 0 11")))

    assert_that(speech.spelled(0)).is_equal_to("aa")


# Streams begin on byte boundaries: a string at address 1 decodes
# untroubled by the noise byte before it (Aa-machine: WRIT).
def test_a_stream_opens_on_its_own_byte_boundary() -> None:
    speech = Speech(storied(langed(TABLE), writ=b"\xff" + packed("0 11")))

    assert_that(speech.spelled(1)).is_equal_to("a")


# Table bytes $60 to $7f spell characters $80 and up directly:
# the first 32 extended characters ride the tree without any
# escape (Aa-machine: LANG).
def test_the_tree_carries_near_extended_characters_directly() -> None:
    speech = Speech(
        storied(langed(EXTENDED_TABLE, extended=(0xC5,)), writ=packed("0 1"))
    )

    assert_that(speech.spelled(0)).is_equal_to("Å")


# A direct extended character with no table behind it is refused
# by the character set, not silently blanked.
def test_a_character_past_the_extended_table_is_refused() -> None:
    speech = Speech(storied(langed(EXTENDED_TABLE), writ=packed("0 1")))

    with pytest.raises(AAMachineError, match=r"past the 0-entry extended table"):
        speech.spelled(0)


# Before format 0.4 the escape reads seven fixed bits and spells
# character $80 + X: here X is $20, the escape band's own floor,
# landing on extended seat 32 (Aa-machine: LANG).
def test_the_old_escape_reads_seven_bits(far_extended: tuple[int, ...]) -> None:
    speech = Speech(
        storied(
            langed(TABLE, extended=far_extended),
            writ=packed("10 0100000 11"),
            version=(0, 3),
        )
    )

    assert_that(speech.spelled(0)).is_equal_to("é")


# The old escape refuses a read below $20: those seats belong to
# the control characters no string may spell (Aa-machine: LANG).
def test_the_old_escape_refuses_a_read_below_its_floor() -> None:
    speech = Speech(
        storied(langed(TABLE), writ=packed("10 0011111 11"), version=(0, 3))
    )

    with pytest.raises(AAMachineError, match=r"below the \$20 floor"):
        speech.spelled(0)


# From format 0.4 the escape's read is sized by the far extended
# characters plus the dictionary: 33 extended characters put one
# beyond the tree's reach, one word joins it, and the two-answer
# read takes a single bit. X = 0 is the far character.
def test_the_new_escape_reaches_the_far_characters(
    far_extended: tuple[int, ...],
) -> None:
    speech = Speech(
        storied(
            langed(TABLE, extended=far_extended),
            writ=packed("10 0 11"),
            dictionary=worded(b"xyzzy"),
        )
    )

    assert_that(speech.spelled(0)).is_equal_to("é")


# The same escape's other answer: X past the far characters is a
# dictionary word, arriving with its own leading space.
def test_the_new_escape_spells_a_dictionary_word(
    far_extended: tuple[int, ...],
) -> None:
    speech = Speech(
        storied(
            langed(TABLE, extended=far_extended),
            writ=packed("0 10 1 11"),
            dictionary=worded(b"xyzzy"),
        )
    )

    assert_that(speech.spelled(0)).is_equal_to("a xyzzy")


# One answer in all the world means a zero-bit read: the escape
# produces the lone dictionary word without consuming anything.
def test_a_lone_answer_takes_a_zero_bit_read() -> None:
    speech = Speech(
        storied(langed(TABLE), writ=packed("10 11"), dictionary=worded(b"plugh"))
    )

    assert_that(speech.spelled(0)).is_equal_to(" plugh")


# An escape in a story with no far characters and no words has
# nothing it could mean; the walk refuses it loud.
def test_an_escape_with_nothing_to_answer_is_refused() -> None:
    speech = Speech(storied(langed(TABLE), writ=packed("10 11")))

    with pytest.raises(AAMachineError, match=r"no far characters"):
        speech.spelled(0)


# A read sized for three answers can still spell a fourth: the
# out-of-range X is refused by name, not wrapped or clamped.
def test_the_new_escape_refuses_a_read_past_its_answers() -> None:
    speech = Speech(
        storied(
            langed(TABLE),
            writ=packed("10 11 11"),
            dictionary=worded(b"plugh", b"plover", b"zork"),
        )
    )

    with pytest.raises(AAMachineError, match=r"past the 3 answers"):
        speech.spelled(0)


# A jump byte aims at a table entry; one aimed past the LANG
# chunk stops the walk with the entry named.
def test_a_jump_past_the_table_is_refused() -> None:
    speech = Speech(storied(langed(RUNAWAY_TABLE), writ=packed("0 1")))

    with pytest.raises(AAMachineError, match=r"entry 127, past the LANG"):
        speech.spelled(0)


# A stream that never reaches the end mark runs out of WRIT; the
# walk refuses to invent bits past the chunk.
def test_a_stream_that_runs_out_is_refused() -> None:
    speech = Speech(storied(langed(TABLE), writ=b"\x00"))

    with pytest.raises(AAMachineError, match=r"ran out mid-string"):
        speech.spelled(0)


# An address outside WRIT never opens a stream at all.
def test_an_address_outside_writ_is_refused() -> None:
    speech = Speech(storied(langed(TABLE), writ=packed("11")))

    with pytest.raises(AAMachineError, match=r"outside WRIT's 1 bytes"):
        speech.spelled(9)


# A tiny string pointer is a byte address shifted right by one
# bit, whatever the header's shift says: pointer 1 names the
# stream at byte 2 (Aa-machine: Runtime data).
def test_a_tiny_pointer_shifts_by_one_bit() -> None:
    speech = Speech(storied(langed(TABLE), writ=b"\xff\xff" + packed("0 11"), shift=3))

    assert_that(speech.pointed(1, tiny=True)).is_equal_to("a")


# Short and long pointers shift by the header's own amount: with
# a shift of 2, pointer 1 names the stream at byte 4 (Aa-machine:
# Runtime data).
def test_a_pointer_shifts_by_the_header_amount() -> None:
    speech = Speech(storied(langed(TABLE), writ=b"\xff" * 4 + packed("0 11"), shift=2))

    assert_that(speech.pointed(1)).is_equal_to("a")


# The dictionary decodes in order, through the story's own
# character space: byte $80 is the extended table's first seat
# (Aa-machine: DICT).
def test_the_dictionary_speaks_the_story_character_set() -> None:
    speech = Speech(
        storied(
            langed(TABLE, extended=(0xC5,)),
            dictionary=worded(b"\x80mulet", b"lamp"),
        )
    )

    assert_that(speech.words).is_equal_to(("Åmulet", "lamp"))


# A DICT too short for even its own count is refused at the door.
def test_a_dict_too_short_for_its_count_is_refused() -> None:
    with pytest.raises(AAMachineError, match=r"too short for its own count"):
        Speech(storied(langed(TABLE), dictionary=b"\x00"))


# A count that claims more entries than the chunk holds is a lie
# the table refuses whole.
def test_a_dict_table_past_the_chunk_is_refused() -> None:
    with pytest.raises(AAMachineError, match=r"claims 9 words"):
        Speech(storied(langed(TABLE), dictionary=(9).to_bytes(2, "big")))


# An entry whose character array runs past the chunk's end is
# refused by its seat number.
def test_a_dict_word_past_the_chunk_is_refused() -> None:
    tabled = (1).to_bytes(2, "big") + bytes([200]) + (5).to_bytes(2, "big")

    with pytest.raises(AAMachineError, match=r"word 0 runs past"):
        Speech(storied(langed(TABLE), dictionary=tabled))


@pytest.fixture
def far_extended() -> tuple[int, ...]:
    """Thirty-three extended characters, the last beyond the tree.

    Thirty-two ride the decoding tree directly; the thirty-third
    -- an e-acute at seat 32 -- is reachable only by escape, in
    both the old seven-bit shape and the new sized read.
    """

    return (*(0x100 + seat for seat in range(32)), 0xE9)
