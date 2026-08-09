from collections.abc import Callable

import pytest
from assertpy import assert_that

from voxam.errors import ZMachineTextError
from voxam.zmachine.memory import Memory
from voxam.zmachine.zscii import decode_string, zscii_to_char

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


def test_a_truncated_escape_is_rejected(code_memory: Callable[..., Memory]) -> None:
    memory = code_memory(encode(5, 6))

    with pytest.raises(ZMachineTextError, match="inside a ZSCII escape"):
        decode_string(memory, CODE)


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


@pytest.mark.parametrize(("version", "zchars"), [(2, (1, 0)), (3, (1, 5)), (5, (2, 5))])
def test_abbreviations_are_a_reported_frontier(
    version: int, zchars: tuple[int, ...], code_memory: Callable[..., Memory]
) -> None:
    memory = code_memory(encode(*zchars), version=version)

    with pytest.raises(ZMachineTextError, match="abbreviations"):
        decode_string(memory, CODE)


def test_custom_alphabet_tables_are_a_reported_frontier(
    code_memory: Callable[..., Memory],
) -> None:
    memory = code_memory(encode(13), version=5)
    memory.write_word(0x34, 0x0100)

    with pytest.raises(ZMachineTextError, match="custom alphabet"):
        decode_string(memory, CODE)


@pytest.mark.parametrize(("code", "expected"), [(13, "\n"), (65, "A"), (126, "~")])
def test_zscii_output_codes(code: int, expected: str) -> None:
    assert_that(zscii_to_char(code)).is_equal_to(expected)


@pytest.mark.parametrize("code", [0, 12, 127, 200])
def test_unprintable_zscii_codes_are_rejected(code: int) -> None:
    with pytest.raises(ZMachineTextError, match="not yet printable"):
        zscii_to_char(code)
