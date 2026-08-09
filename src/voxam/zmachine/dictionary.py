"""The dictionary table and lexical analysis (§13).

The dictionary lives in static memory at the address the header word
at $08 gives (§13.1): a list of word-separator codes, an entry length,
an entry count, and sorted entries whose first bytes are the encoded
text of each word (§13.2). Tokenization splits typed text at spaces
and separators; lookup encodes each word and hunts for its entry.
"""

from voxam.zmachine.memory import Memory
from voxam.zmachine.zscii import encode_word, zscii_to_char

# Entry text is 4 bytes through Version 3 and 6 bytes after (§13.3,
# §13.4).
V3_LAST_VERSION = 3
V3_TEXT_BYTES = 4
V4_TEXT_BYTES = 6

# An unrecognised word's dictionary address is 0 (§13.6.3).
NOT_IN_DICTIONARY = 0


class Dictionary:
    """A view of one dictionary table (§13.2).

    Usually the standard dictionary the header names, but tokenise
    may supply any table in the same format (§13.6).
    """

    def __init__(self, memory: Memory, base: int | None = None) -> None:
        """Read the table's header once (§13.2).

        Args:
            memory: The memory image holding the dictionary.
            base: The table's byte address; None means the standard
                dictionary named in the story header (§13.1).
        """

        self._memory = memory
        self._version = memory.header.version
        self._base = base if base is not None else memory.header.dictionary_address

        separator_count = memory.read_byte(self._base)

        self._separators = frozenset(
            zscii_to_char(memory.read_byte(self._base + 1 + index))
            for index in range(separator_count)
        )
        self._entry_length = memory.read_byte(self._base + 1 + separator_count)
        self._count = memory.read_word(self._base + 2 + separator_count)
        self._entries = self._base + 4 + separator_count
        self._text_bytes = (
            V3_TEXT_BYTES if self._version <= V3_LAST_VERSION else V4_TEXT_BYTES
        )

    @property
    def separators(self) -> frozenset[str]:
        """The word-separator characters (§13.2)."""

        return self._separators

    @property
    def entry_count(self) -> int:
        """How many words the dictionary holds (§13.2)."""

        return self._count

    def lookup(self, word: str) -> int:
        """Find a typed word's entry address, or 0 (§13.6.2).

        The word is encoded to dictionary form first, so lookup
        inherits the resolution guillotine: only the leading six or
        nine Z-characters distinguish words.

        Args:
            word: The typed word, however capitalized.

        Returns:
            The byte address of the entry, or 0 when absent.
        """

        target = encode_word(self._version, word)

        for index in range(self._count):
            address = self._entries + index * self._entry_length

            if self._text_at(address) == target:
                return address

        return NOT_IN_DICTIONARY

    def _text_at(self, address: int) -> bytes:
        """Read an entry's encoded text (§13.3)."""

        return bytes(
            self._memory.read_byte(address + offset)
            for offset in range(self._text_bytes)
        )


def tokenize(text: str, separators: frozenset[str]) -> list[tuple[str, int]]:
    """Split typed text into words (§13.6.1).

    Spaces divide words and are otherwise ignored; separators divide
    words while being words themselves.

    Args:
        text: The typed line.
        separators: The dictionary's word-separator characters.

    Returns:
        Each word with the offset it starts at within the text.
    """

    words: list[tuple[str, int]] = []
    start: int | None = None

    for position, character in enumerate(text):
        if character == " " or character in separators:
            if start is not None:
                words.append((text[start:position], start))
                start = None

            if character != " ":
                words.append((character, position))
        elif start is None:
            start = position

    if start is not None:
        words.append((text[start:], start))

    return words
