from collections.abc import Callable

from assertpy import assert_that

from voxam.zmachine.dictionary import Dictionary, tokenize
from voxam.zmachine.memory import Memory
from voxam.zmachine.zscii import encode_word

DICTIONARY_BASE = 0x150


def plant_dictionary(
    memory: Memory,
    entries: list[bytes],
    separators: bytes = b",.",
    entry_length: int = 7,
    base: int = DICTIONARY_BASE,
) -> None:
    memory.write_word(0x08, base)
    position = base

    memory.write_byte(position, len(separators))
    position += 1

    for code in separators:
        memory.write_byte(position, code)
        position += 1

    memory.write_byte(position, entry_length)
    position += 1

    memory.write_word(position, len(entries))
    position += 2

    for entry in entries:
        for offset, value in enumerate(entry):
            memory.write_byte(position + offset, value)

        position += entry_length


# Two hand-encoded Version 3 entries in sorted order: "go" packs to
# 3285 94A5 and "hi" to 35C5 94A5 (§13.3, §13.5).
GO = bytes([0x32, 0x85, 0x94, 0xA5])
HI = bytes([0x35, 0xC5, 0x94, 0xA5])


def standard_dictionary(memory: Memory) -> Dictionary:
    plant_dictionary(memory, [GO, HI])

    return Dictionary(memory)


def test_reads_the_dictionary_header(code_memory: Callable[..., Memory]) -> None:
    dictionary = standard_dictionary(code_memory())

    assert_that(dictionary.separators).is_equal_to(frozenset({",", "."}))
    assert_that(dictionary.entry_count).is_equal_to(2)


# The header occupies 4 + n bytes -- six with two separators -- and
# the second entry sits one entry length past the first (§13.2).
def test_lookup_finds_a_word(code_memory: Callable[..., Memory]) -> None:
    dictionary = standard_dictionary(code_memory())

    assert_that(dictionary.lookup("go")).is_equal_to(DICTIONARY_BASE + 6)
    assert_that(dictionary.lookup("hi")).is_equal_to(DICTIONARY_BASE + 6 + 7)


def test_lookup_is_case_insensitive(code_memory: Callable[..., Memory]) -> None:
    dictionary = standard_dictionary(code_memory())

    assert_that(dictionary.lookup("HI")).is_equal_to(dictionary.lookup("hi"))


def test_lookup_misses_give_address_0(code_memory: Callable[..., Memory]) -> None:
    dictionary = standard_dictionary(code_memory())

    assert_that(dictionary.lookup("zebra")).is_equal_to(0)


# Only the leading six Z-characters exist in a Version 3 entry, so
# words agreeing past the guillotine find the same entry (§3.7).
def test_lookup_inherits_the_guillotine(code_memory: Callable[..., Memory]) -> None:
    memory = code_memory()
    truncated = bytes([0x35, 0xCD, 0xB9, 0xAE])
    plant_dictionary(memory, [truncated])
    dictionary = Dictionary(memory)

    assert_that(dictionary.lookup("hihihihi")).is_equal_to(DICTIONARY_BASE + 6)
    assert_that(dictionary.lookup("hihihi")).is_equal_to(DICTIONARY_BASE + 6)


# tokenise may name any table in dictionary format (§13.6): the base
# override reads one somewhere other than the header's address.
def test_a_dictionary_can_live_at_any_base(
    code_memory: Callable[..., Memory],
) -> None:
    memory = code_memory()
    plant_dictionary(memory, [HI], base=0x180)

    dictionary = Dictionary(memory, base=0x180)

    assert_that(dictionary.lookup("hi")).is_equal_to(0x180 + 6)


# Version 4 and later entries carry six bytes of text (§13.4).
def test_version_4_entries_have_longer_text(
    code_memory: Callable[..., Memory],
) -> None:
    memory = code_memory(version=5)
    plant_dictionary(memory, [encode_word(5, "hi") + bytes(3)], entry_length=9)

    dictionary = Dictionary(memory)

    assert_that(dictionary.lookup("hi")).is_equal_to(DICTIONARY_BASE + 6)
    assert_that(dictionary.lookup("go")).is_equal_to(0)


# The Standard's own example (§13.6.1): "fred,go fishing" divides
# into four words, the comma among them.
def test_tokenize_matches_the_specs_example() -> None:
    words = tokenize("fred,go fishing", frozenset({","}))

    assert_that(words).is_equal_to([("fred", 0), (",", 4), ("go", 5), ("fishing", 8)])


def test_tokenize_ignores_stray_spaces() -> None:
    words = tokenize("  open  mailbox ", frozenset())

    assert_that(words).is_equal_to([("open", 2), ("mailbox", 8)])


def test_tokenize_of_nothing_is_no_words() -> None:
    assert_that(tokenize("", frozenset({","}))).is_empty()
    assert_that(tokenize("   ", frozenset({","}))).is_empty()
