from collections.abc import Callable

import pytest
from assertpy import assert_that

from voxam.errors import ZMachineTextError
from voxam.zmachine.memory import Memory
from voxam.zmachine.zscii import decode_string, encode_word, zscii_to_char

CODE = 0x40


def encode(*zchars: int) -> bytes:
    padded = list(zchars)

    while len(padded) % 3:
        padded.append(5)

    data = b""

    for index in range(0, len(padded), 3):
        word = (padded[index] << 10) | (padded[index + 1] << 5) | padded[index + 2]

        if index + 3 == len(padded):
            word |= 0x8000

        data += word.to_bytes(2, "big")

    return data


# 'h' is Z-character 13 in A0 (a is 6), and Z-character 0 is a space
# (§3.5.1, §3.5.3). Five characters pad to two words, so the string
# ends four bytes along.
def test_decodes_lowercase_and_spaces(code_memory: Callable[..., Memory]) -> None:
    memory = code_memory(encode(13, 10, 0, 17, 20))

    text, end = decode_string(memory, CODE)

    assert_that(text).is_equal_to("he lo")
    assert_that(end).is_equal_to(CODE + 4)


# From Version 3, Z-character 4 selects A1 and 5 selects A2, for one
# character only (§3.2.3).
def test_single_shifts_last_one_character(code_memory: Callable[..., Memory]) -> None:
    memory = code_memory(encode(4, 13, 13, 5, 8, 13))

    text, _ = decode_string(memory, CODE)

    assert_that(text).is_equal_to("Hh0h")


# A shift is consumed even when the next Z-character is a space, which
# prints without consulting any alphabet (§3.2.3, §3.5.1).
def test_a_space_consumes_a_pending_shift(code_memory: Callable[..., Memory]) -> None:
    memory = code_memory(encode(4, 0, 13))

    text, _ = decode_string(memory, CODE)

    assert_that(text).is_equal_to(" h")


# Character 7 in A2 is a new-line from Version 2 (§3.5.3).
def test_a2_holds_the_newline(code_memory: Callable[..., Memory]) -> None:
    memory = code_memory(encode(13, 5, 7, 13))

    text, _ = decode_string(memory, CODE)

    assert_that(text).is_equal_to("h\nh")


# Character 6 in A2 escapes to a ten-bit ZSCII code: top five bits
# then bottom five (§3.4). 65 is 'A': 2 << 5 | 1.
def test_the_zscii_escape_builds_a_character(
    code_memory: Callable[..., Memory],
) -> None:
    memory = code_memory(encode(5, 6, 2, 1))

    text, _ = decode_string(memory, CODE)

    assert_that(text).is_equal_to("A")


# A string may legally end while a construction is incomplete: the
# remnant is simply ignored (§3.6.1). This happens routinely with
# dictionary words cut to the dictionary resolution.
def test_a_truncated_escape_is_ignored(code_memory: Callable[..., Memory]) -> None:
    memory = code_memory(encode(5, 6))

    text, _ = decode_string(memory, CODE)

    assert_that(text).is_equal_to("")


# In Versions 1 and 2, Z-character 2 shifts to the next alphabet for
# one character, and 4 locks it (§3.2.2).
def test_early_versions_shift_relatively(code_memory: Callable[..., Memory]) -> None:
    shifted = code_memory(encode(2, 13, 13), version=2)
    locked = code_memory(encode(4, 13, 14), version=2)

    assert_that(decode_string(shifted, CODE)[0]).is_equal_to("Hh")
    assert_that(decode_string(locked, CODE)[0]).is_equal_to("HI")


# Version 1 has no new-line in A2 -- Z-character 1 is the new-line
# (§3.5.2) -- so '0' moves up to character 7 and '<' joins the row at
# 27 (§3.5.4). The escape stays at character 6 (§3.4).
def test_version_1_has_its_own_rules(code_memory: Callable[..., Memory]) -> None:
    memory = code_memory(encode(13, 1, 3, 7, 3, 27), version=1)

    text, _ = decode_string(memory, CODE)

    assert_that(text).is_equal_to("h\n0<")


def test_version_1_keeps_the_escape(code_memory: Callable[..., Memory]) -> None:
    memory = code_memory(encode(3, 6, 2, 1), version=1)

    text, _ = decode_string(memory, CODE)

    assert_that(text).is_equal_to("A")


# Low enough that even bank 3's entries stay inside dynamic memory.
ABBREVIATION_TABLE = 0x120


def plant_abbreviation(
    memory: Memory, entry: int, encoded: bytes, at: int = 0x1A8
) -> None:
    memory.write_word(0x18, ABBREVIATION_TABLE)
    memory.write_word(ABBREVIATION_TABLE + 2 * entry, at // 2)

    for offset, value in enumerate(encoded):
        memory.write_byte(at + offset, value)


# Z-character 1 then 0 names abbreviation entry 0, whose string is
# spliced into the text (§3.3). The table entry is a word address.
def test_abbreviations_expand(code_memory: Callable[..., Memory]) -> None:
    memory = code_memory(encode(1, 0, 0, 13))
    plant_abbreviation(memory, 0, encode(13, 14))

    text, _ = decode_string(memory, CODE)

    assert_that(text).is_equal_to("hi h")


# The bank character selects among three banks of 32: entry number
# 32(z - 1) + x (§3.3).
@pytest.mark.parametrize(
    ("bank", "index", "entry"), [(1, 5, 5), (2, 1, 33), (3, 2, 66)]
)
def test_abbreviation_banks(
    bank: int, index: int, entry: int, code_memory: Callable[..., Memory]
) -> None:
    memory = code_memory(encode(bank, index))
    plant_abbreviation(memory, entry, encode(13, 14))

    text, _ = decode_string(memory, CODE)

    assert_that(text).is_equal_to("hi")


# In Version 2 only Z-character 1 abbreviates (§3.3); 2 and 3 remain
# shifts, as the shift tests elsewhere show.
def test_version_2_has_one_abbreviation_bank(
    code_memory: Callable[..., Memory],
) -> None:
    memory = code_memory(encode(1, 3), version=2)
    plant_abbreviation(memory, 3, encode(13, 14))

    text, _ = decode_string(memory, CODE)

    assert_that(text).is_equal_to("hi")


def test_abbreviations_may_not_nest(code_memory: Callable[..., Memory]) -> None:
    memory = code_memory(encode(1, 0))
    plant_abbreviation(memory, 0, encode(1, 1))

    with pytest.raises(ZMachineTextError, match="may not use abbreviations"):
        decode_string(memory, CODE)


# §3.3.1's other rule: an abbreviation may not end mid-construction,
# though a top-level string may (§3.6.1).
def test_abbreviations_may_not_end_incomplete(
    code_memory: Callable[..., Memory],
) -> None:
    memory = code_memory(encode(1, 0))
    plant_abbreviation(memory, 0, encode(5, 6))

    with pytest.raises(ZMachineTextError, match="incomplete"):
        decode_string(memory, CODE)


def test_a_truncated_abbreviation_is_ignored(
    code_memory: Callable[..., Memory],
) -> None:
    memory = code_memory(encode(5, 5, 1))

    text, _ = decode_string(memory, CODE)

    assert_that(text).is_equal_to("")


def test_custom_alphabet_tables_are_a_reported_frontier(
    code_memory: Callable[..., Memory],
) -> None:
    memory = code_memory(encode(13), version=5)
    memory.write_word(0x34, 0x0100)

    with pytest.raises(ZMachineTextError, match="custom alphabet"):
        decode_string(memory, CODE)


# Dictionary-form encoding (§3.7), all values hand-packed: 'h' and
# 'i' are 13 and 14; pads are 5s; the last word carries the top bit.
@pytest.mark.parametrize(
    ("version", "word", "expected"),
    [
        (3, "hi", bytes([0x35, 0xC5, 0x94, 0xA5])),
        (3, "HI", bytes([0x35, 0xC5, 0x94, 0xA5])),
        (3, "x1", bytes([0x74, 0xA9, 0x94, 0xA5])),
        (3, "@", bytes([0x14, 0xC2, 0x80, 0xA5])),
        (5, "hi", bytes([0x35, 0xC5, 0x14, 0xA5, 0x94, 0xA5])),
    ],
)
def test_encodes_words_in_dictionary_form(
    version: int, word: str, expected: bytes
) -> None:
    assert_that(encode_word(version, word)).is_equal_to(expected)


# Six Z-characters is the whole resolution through Version 3 (§3.7):
# everything past the guillotine is indistinguishable.
def test_encoding_guillotines_at_the_resolution() -> None:
    assert_that(encode_word(3, "hihihihi")).is_equal_to(encode_word(3, "hihihi"))
    assert_that(encode_word(3, "hihihihi")).is_equal_to(bytes([0x35, 0xCD, 0xB9, 0xAE]))


# Versions 1 and 2 encode with relative shifts, locking when at least
# two characters share the alphabet (§3.7.1): "12" locks down with 5,
# while a lone "1" takes the single shift 3.
def test_early_versions_lock_for_runs() -> None:
    assert_that(encode_word(2, "12")).is_equal_to(bytes([0x15, 0x2A, 0x94, 0xA5]))
    assert_that(encode_word(2, "1a")).is_equal_to(bytes([0x0D, 0x26, 0x94, 0xA5]))


# Coming back up from a locked A2, a run of A0 characters locks again
# with 4, and a lone one takes the single shift 2 (§3.2.2, §3.7.1):
# "12ab" packs to [5 9 10] [4 6 7] and "12a" to [5 9 10] [2 6 pad].
def test_early_versions_shift_back_up() -> None:
    assert_that(encode_word(2, "12ab")).is_equal_to(bytes([0x15, 0x2A, 0x90, 0xC7]))
    assert_that(encode_word(2, "12a")).is_equal_to(bytes([0x15, 0x2A, 0x88, 0xC5]))


@pytest.mark.parametrize(("code", "expected"), [(13, "\n"), (65, "A"), (126, "~")])
def test_zscii_output_codes(code: int, expected: str) -> None:
    assert_that(zscii_to_char(code)).is_equal_to(expected)


@pytest.mark.parametrize("code", [0, 12, 127, 200])
def test_unprintable_zscii_codes_are_rejected(code: int) -> None:
    with pytest.raises(ZMachineTextError, match="not yet printable"):
        zscii_to_char(code)
