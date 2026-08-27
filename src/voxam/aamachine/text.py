"""The Å-machine's speech: bitstreams, the dictionary, the charset.

Strings live in WRIT as packed bitstreams, MSB first, each stream
opening on a byte boundary; the LANG chunk's decoding table walks
them a bit at a time -- a Huffman-inspired tree whose bytes spell
characters, jumps, an end mark, and an escape that carries the
far characters and whole dictionary words (Aa-machine: LANG;
WRIT). The dictionary's own words are plain arrays in the story's
character set: ASCII below $80, the LANG extended table above it
(Aa-machine: Text; DICT).

The escape changed shape at story format 0.4 -- seven fixed bits
before, a table-sized read after -- and this decoder speaks both,
choosing by the story's own version claim.
"""

import math

from voxam.aamachine.story import Story
from voxam.errors import AAMachineError

# The decoding table's byte meanings (Aa-machine: LANG): a direct
# character rides as $20 + x, the escape and end marks stand
# alone, and anything above $80 jumps to another table entry.
_END = 0x80
_ESCAPE = 0x5F
_DIRECT_TOP = 0x7F
_CHARACTER_BASE = 0x20

# Where the game-specific characters begin in the character set
# (Aa-machine: Text).
_EXTENDED_START = 0x80

# The old escape's fixed read, and its floor: format 0.3 and
# earlier read seven bits and refuse a result below $20
# (Aa-machine: LANG).
_OLD_ESCAPE_BITS = 7
_OLD_ESCAPE_FLOOR = 0x20

# The new escape's character band starts at $A0: the first 32
# extended characters travel directly in the tree (Aa-machine:
# LANG).
_NEW_ESCAPE_BASE = 0xA0
_DIRECT_EXTENDED = 32

# The format where the escape changed shape.
_NEW_ESCAPE_VERSION = (0, 4)

# A dictionary entry: a length byte and a two-byte offset, after
# the two-byte word count (Aa-machine: DICT).
_COUNT_SIZE = 2
_ENTRY_SIZE = 3

# The packing grain: bits fill bytes MSB first (Aa-machine: WRIT).
_BYTE_BITS = 8


class Speech:
    """One story's whole text apparatus, ready to spell.

    Attributes:
        words: The dictionary, decoded in order -- each word in
            the story's own character set.
    """

    def __init__(self, story: Story) -> None:
        """Gather the LANG table, the dictionary, and WRIT.

        The three chunks stand certified present: they are summed,
        and the story verified its checksum at the door.

        Raises:
            AAMachineError: For a dictionary the chunk cannot hold
                whole.
        """

        self._version = story.version
        self._extended = story.extended
        self._shift = story.shift
        self._lang = story.summed(b"LANG").payload
        self._table_at = int.from_bytes(self._lang[0:2], "big")
        self._writ = story.summed(b"WRIT").payload
        self.words = _worded_dictionary(story.summed(b"DICT").payload, self._extended)

    def spelled(self, address: int) -> str:
        """Decode one string from its byte address in WRIT.

        The walk starts at the table's root and returns there
        after every produced piece; a jump byte moves the walk,
        the end byte closes it (Aa-machine: LANG).

        Raises:
            AAMachineError: For an address outside WRIT, a walk
                past the table or the stream, or an escape the
                story has no characters or words to answer.
        """

        if not 0 <= address < len(self._writ):
            msg = (
                f"string address {address} lies outside WRIT's "
                f"{len(self._writ)} bytes (Aa-machine: WRIT)"
            )

            raise AAMachineError(msg)

        bits = _Bits(self._writ, address)
        pieces: list[str] = []
        entry = 0

        while True:
            told = self._entry(entry)[bits.take(1)]

            if told == _END:
                break

            if told == _ESCAPE:
                pieces.append(self._escaped(bits))
                entry = 0
            elif told <= _DIRECT_TOP:
                pieces.append(self._character(_CHARACTER_BASE + told))
                entry = 0
            else:
                entry = told - _END

        return "".join(pieces)

    def pointed(self, pointer: int, *, tiny: bool = False) -> str:
        """Decode the string a shifted pointer names.

        A string pointer is a shifted byte address in WRIT: tiny
        pointers are shifted right by one bit, short and long
        pointers by the header's own shift amount -- so the way
        back is a left shift by the same (Aa-machine: Runtime
        data).

        Raises:
            AAMachineError: Whatever spelled raises for the
                resolved address.
        """

        return self.spelled(pointer << (1 if tiny else self._shift))

    def _entry(self, entry: int) -> bytes:
        """One decoding-table pair, bounds held loud.

        Raises:
            AAMachineError: For an entry past the LANG chunk.
        """

        at = self._table_at + entry * 2

        if at + 2 > len(self._lang):
            msg = (
                f"the decoding walk reached entry {entry}, past the "
                f"LANG chunk's end (Aa-machine: LANG)"
            )

            raise AAMachineError(msg)

        return self._lang[at : at + 2]

    def _escaped(self, bits: "_Bits") -> str:
        """One escape's yield: a far character, or a whole word.

        Format 0.3 and earlier read seven fixed bits; 0.4 and
        later size the read by the extended characters beyond the
        tree's reach plus the dictionary, a word arriving with
        its own leading space (Aa-machine: LANG).

        Raises:
            AAMachineError: For an old escape below its floor, or
                a new escape with nothing to answer it.
        """

        if self._version < _NEW_ESCAPE_VERSION:
            told = bits.take(_OLD_ESCAPE_BITS)

            if told < _OLD_ESCAPE_FLOOR:
                msg = (
                    f"an escape read {told:#04x}, below the ${_OLD_ESCAPE_FLOOR:02x} "
                    f"floor the old escape requires (Aa-machine: LANG)"
                )

                raise AAMachineError(msg)

            return self._character(_EXTENDED_START + told)

        beyond = max(0, len(self._extended) - _DIRECT_EXTENDED)
        total = beyond + len(self.words)

        if total == 0:
            msg = (
                "an escape appears, but the story has no far characters "
                "and no dictionary words to answer it (Aa-machine: LANG)"
            )

            raise AAMachineError(msg)

        told = bits.take(_bit_width(total))

        if told < beyond:
            return self._character(_NEW_ESCAPE_BASE + told)

        if told - beyond >= len(self.words):
            msg = (
                f"an escape read {told}, past the {total} answers the "
                f"story holds (Aa-machine: LANG)"
            )

            raise AAMachineError(msg)

        return " " + self.words[told - beyond]

    def _character(self, code: int) -> str:
        """One character-set code as text (Aa-machine: Text).

        Raises:
            AAMachineError: For a game-specific code past the
                extended table.
        """

        return _charactered(code, self._extended)


def _charactered(code: int, extended: tuple[str, ...]) -> str:
    """One character-set code as text, the extended table ruling.

    Raises:
        AAMachineError: For a code past the extended table.
    """

    if code < _EXTENDED_START:
        return chr(code)

    if code - _EXTENDED_START < len(extended):
        return extended[code - _EXTENDED_START]

    msg = (
        f"character {code:#04x} points past the {len(extended)}-entry "
        f"extended table (Aa-machine: LANG)"
    )

    raise AAMachineError(msg)


def _bit_width(total: int) -> int:
    """How many bits the new escape reads: ceil(log2(total))."""

    return math.ceil(math.log2(total)) if total > 1 else 0


def _worded_dictionary(payload: bytes, extended: tuple[str, ...]) -> tuple[str, ...]:
    """The DICT chunk's words, decoded in order (Aa-machine: DICT).

    Raises:
        AAMachineError: For a table or a word the chunk cannot
            hold whole.
    """

    if len(payload) < _COUNT_SIZE:
        msg = "the DICT chunk is too short for its own count (Aa-machine: DICT)"

        raise AAMachineError(msg)

    count = int.from_bytes(payload[0:_COUNT_SIZE], "big")
    table_end = _COUNT_SIZE + count * _ENTRY_SIZE

    if table_end > len(payload):
        msg = (
            f"the DICT table claims {count} words, past the chunk's "
            f"{len(payload)} bytes (Aa-machine: DICT)"
        )

        raise AAMachineError(msg)

    words = []

    for held in range(count):
        at = _COUNT_SIZE + held * _ENTRY_SIZE
        length = payload[at]
        start = int.from_bytes(payload[at + 1 : at + 3], "big")

        if start + length > len(payload):
            msg = f"dictionary word {held} runs past the chunk's end (Aa-machine: DICT)"

            raise AAMachineError(msg)

        words.append(
            "".join(
                _charactered(code, extended) for code in payload[start : start + length]
            )
        )

    return tuple(words)


class _Bits:
    """A bitstream over WRIT, MSB first (Aa-machine: WRIT)."""

    def __init__(self, data: bytes, at: int) -> None:
        self._data = data
        self._byte = at
        self._bit = 0

    def take(self, count: int) -> int:
        """The next count bits as an integer, MSB first.

        Raises:
            AAMachineError: For a read past the stream's end.
        """

        told = 0

        for _ in range(count):
            if self._byte >= len(self._data):
                msg = "the bitstream ran out mid-string (Aa-machine: WRIT)"

                raise AAMachineError(msg)

            bit = (self._data[self._byte] >> (_BYTE_BITS - 1 - self._bit)) & 1
            told = (told << 1) | bit
            self._bit += 1

            if self._bit == _BYTE_BITS:
                self._bit = 0
                self._byte += 1

        return told
