from collections.abc import Callable

import pytest
from assertpy import assert_that

from voxam.errors import ZMachineTextError
from voxam.zmachine.memory import Memory
from voxam.zmachine.zscii import (
    char_to_zscii,
    decode_string,
    encode_word,
    extras,
    zscii_to_char,
)

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


@pytest.mark.parametrize("code", [9, 11, 12, 127, 252])
def test_unprintable_zscii_codes_are_rejected(code: int) -> None:
    with pytest.raises(ZMachineTextError, match="not yet printable"):
        zscii_to_char(code)


ALPHABET_TABLE = 0x160


def plant_alphabet(memory: Memory, a0: str, a1: str, a2: str) -> None:
    """Point $34 at a custom table built from three 26-char rows."""

    memory.write_word(0x34, ALPHABET_TABLE)

    for row, text in enumerate((a0, a1, a2)):
        for index, character in enumerate(text):
            memory.write_byte(ALPHABET_TABLE + row * 26 + index, ord(character))


def rot13(text: str) -> str:
    return "".join(chr((ord(c) - ord("a") + 13) % 26 + ord("a")) for c in text)


# From Version 5 the header may name a custom alphabet table: 78
# bytes of ZSCII giving new meanings to Z-characters 6 to 31
# (§3.5.5, §3.5.5.1). Under a rot13 A0, the Z-characters that spell
# "he lo" in the standard rows spell something else entirely.
def test_a_custom_table_redefines_the_alphabets(
    code_memory: Callable[..., Memory],
) -> None:
    memory = code_memory(encode(13, 10, 0, 17, 20), version=5)
    plant_alphabet(memory, rot13("abcdefghijklmnopqrstuvwxyz"), "?" * 26, "?" * 26)

    text, _ = decode_string(memory, CODE)

    assert_that(text).is_equal_to("ur yb")


# A2's characters 6 and 7 stay the escape and the new-line whatever
# the table says (§3.5.5.1): with X planted in both slots, the
# escape still escapes and the new-line still breaks.
def test_a2_escape_and_newline_defy_the_table(
    code_memory: Callable[..., Memory],
) -> None:
    memory = code_memory(encode(5, 6, 3, 1, 5, 7, 13), version=5)
    plant_alphabet(
        memory,
        "abcdefghijklmnopqrstuvwxyz",
        "?" * 26,
        "XX" + "?" * 24,
    )

    text, _ = decode_string(memory, CODE)

    assert_that(text).is_equal_to("a\nh")


# Below Version 5 the word at $34 is not an alphabet table pointer,
# whatever a story left there (§3.5.5).
def test_the_table_word_is_ignored_before_version_5(
    code_memory: Callable[..., Memory],
) -> None:
    memory = code_memory(encode(13, 10), version=3)
    memory.write_word(0x34, 0x0160)

    text, _ = decode_string(memory, CODE)

    assert_that(text).is_equal_to("he")


# Typed words must be encoded under the same rows the dictionary was
# compiled with (§3.5.5): under rot13 rows, "ur" encodes to the
# Z-characters that spell "he" in the standard rows.
def test_encoding_follows_the_custom_rows() -> None:
    rows = (rot13("abcdefghijklmnopqrstuvwxyz"), "?" * 26, "??" + "!" * 24)

    assert_that(encode_word(5, "ur", rows)).is_equal_to(encode_word(5, "he"))


# Under the standard alphabets a lowercased character is never in
# A1, but a custom table may put it nowhere else: the encoder then
# reaches it with single shift 4 (§3.2.3, §3.5.5).
def test_encoding_reaches_a_character_only_a1_holds() -> None:
    rows = ("?" * 26, "z" + "?" * 25, "??" + "!" * 24)

    assert_that(encode_word(5, "z", rows)).is_equal_to(encode(4, 6, 5, 5, 5, 5, 5, 5))


# ZSCII 0 is defined for output with no effect in any stream
# (§3.8.2.1): converting it yields nothing at all, where every
# other unprintable still halts.
def test_the_null_prints_as_nothing() -> None:
    assert_that(zscii_to_char(0)).is_equal_to("")


# A null in a custom alphabet slot converts to nothing, which would
# shift every later letter's Z-character; the placeholder keeps the
# row exactly 26 wide, so its neighbours still decode correctly
# (§3.5.5.1, §3.8.2.1).
def test_a_null_alphabet_slot_does_not_shift_the_row(
    code_memory: Callable[..., Memory],
) -> None:
    memory = code_memory(encode(6, 7), version=5)
    plant_alphabet(memory, "\x00" + "bcdefghijklmnopqrstuvwxyz", "?" * 26, "?" * 26)

    text, _ = decode_string(memory, CODE)

    assert_that(text).is_equal_to("?b")


# Codes 155 to 223 are the extra characters, mapped by the default
# Unicode translation table of §3.8.5.3 -- and 224 up stays
# undefined under the default table.
@pytest.mark.parametrize(
    ("code", "expected"),
    [(155, "\u00e4"), (161, "\u00df"), (219, "\u00a3"), (223, "\u00bf")],
)
def test_extra_characters_follow_the_default_table(code: int, expected: str) -> None:
    assert_that(zscii_to_char(code)).is_equal_to(expected)


def test_codes_past_the_default_table_still_halt() -> None:
    with pytest.raises(ZMachineTextError, match="not yet printable"):
        zscii_to_char(224)


# The extras are defined for input as well as output (§3.8.5.2.2):
# every code from 155 to 223 survives the round trip through its
# character and back.
def test_extra_characters_round_trip_through_input() -> None:
    for code in range(155, 224):
        assert_that(char_to_zscii(zscii_to_char(code))).is_equal_to(code)

    assert_that(char_to_zscii("a")).is_equal_to(97)
    assert_that(char_to_zscii("\n")).is_equal_to(13)


def test_characters_outside_zscii_are_refused() -> None:
    with pytest.raises(ZMachineTextError, match="no ZSCII code"):
        char_to_zscii("\u03b1")


# A ten-bit escape naming an extra character decodes through the
# default table: 155 is 0b100_11011, so hi 4 and lo 27 (§3.4,
# §3.8.5).
def test_an_escape_reaches_the_extra_characters(
    code_memory: Callable[..., Memory],
) -> None:
    memory = code_memory(encode(5, 6, 4, 27))

    text, _ = decode_string(memory, CODE)

    assert_that(text).is_equal_to("\u00e4")


# Encoding a word with an accented letter escapes to its ZSCII code,
# not its Unicode codepoint (§3.7, §3.8.5.2.2) -- the difference
# between finding and missing a dictionary entry in a German game.
def test_encoding_escapes_extras_as_zscii() -> None:
    assert_that(encode_word(5, "\u00e4")).is_equal_to(
        encode(5, 6, 4, 27, 5, 5, 5, 5, 5)
    )


UNICODE_TABLE = 0x1A0


def plant_unicode_table(memory: Memory, codepoints: list[int]) -> None:
    """Point the header extension's word 3 at a custom repertoire."""

    memory.write_word(0x36, 0x190)
    memory.write_word(0x190, 3)
    memory.write_word(0x196, UNICODE_TABLE)
    memory.write_byte(UNICODE_TABLE, len(codepoints))

    for index, codepoint in enumerate(codepoints):
        memory.write_word(UNICODE_TABLE + 1 + 2 * index, codepoint)


# A custom Unicode translation table redefines the extra characters
# wholesale (§3.8.5.2): with three Greek letters installed, ZSCII
# 155 to 157 speak Greek, and 158 -- past the table's count -- is
# undefined even though the default table went further.
def test_a_custom_translation_table_redefines_the_extras(
    code_memory: Callable[..., Memory],
) -> None:
    memory = code_memory(encode(5, 6, 4, 27), version=5)
    plant_unicode_table(memory, [0x3B1, 0x3B2, 0x3B3])

    text, _ = decode_string(memory, CODE)

    assert_that(text).is_equal_to("\u03b1")
    assert_that(extras(memory)).is_equal_to("\u03b1\u03b2\u03b3")

    with pytest.raises(ZMachineTextError, match="not yet printable"):
        zscii_to_char(158, extras(memory))


# The custom repertoire is defined for input too (§3.8.5.2.2): a
# typed alpha lands as ZSCII 155 under the Greek table.
def test_custom_extras_are_defined_for_input(
    code_memory: Callable[..., Memory],
) -> None:
    memory = code_memory(b"", version=5)
    plant_unicode_table(memory, [0x3B1])

    assert_that(char_to_zscii("\u03b1", extras(memory))).is_equal_to(155)

    with pytest.raises(ZMachineTextError, match="no ZSCII code"):
        char_to_zscii("\u00e4", extras(memory))


# A zero-count table is legal and leaves every extra character
# undefined (§3.8.5.2.2).
def test_an_empty_translation_table_undefines_all_extras(
    code_memory: Callable[..., Memory],
) -> None:
    memory = code_memory(b"", version=5)
    plant_unicode_table(memory, [])

    assert_that(extras(memory)).is_equal_to("")

    with pytest.raises(ZMachineTextError, match="not yet printable"):
        zscii_to_char(155, extras(memory))


# Delete and escape are defined for input only (§3.8.2.2): both
# classic delete bytes mean ZSCII 8, and the terminal escape means
# 27 -- Bureaucracy insists on the former, the unicode checker
# quits by the latter.
@pytest.mark.parametrize(
    ("character", "code"), [("\x08", 8), ("\x7f", 8), ("\x1b", 27)]
)
def test_input_only_codes_are_received(character: str, code: int) -> None:
    assert_that(char_to_zscii(character)).is_equal_to(code)
