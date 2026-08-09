"""Decoding encoded text into readable strings (§3).

Encoded text is a sequence of words, each holding three 5-bit
Z-characters (§3.2). A Z-character is a storage unit, not a
character: what it means depends on the version, the current
alphabet, and its neighbours. The same bytes decode to different
text under different version bytes.
"""

from voxam.errors import ZMachineTextError
from voxam.zmachine.memory import Memory

# Only the last word of a string has its top bit set (§3.2).
STRING_TERMINATOR_BIT = 0x8000

# Three Z-characters per word: bits 14-10, 9-5, and 4-0 (§3.2).
Z_CHAR_SHIFTS = (10, 5, 0)
Z_CHAR_MASK = 0x1F

# Z-character 0 is a space (§3.5.1); in Version 1, Z-character 1 is a
# new-line (§3.5.2).
SPACE = 0
V1_NEWLINE = 1

# In Versions 1 and 2, Z-characters 2 and 3 shift the alphabet for one
# character and 4 and 5 lock it (§3.2.2). From Version 3, only 4 and 5
# shift -- absolutely, for one character -- and 1 to 3 introduce
# abbreviations (§3.2.3, §3.3).
LAST_SHIFT_LOCK_VERSION = 2
LOCK_CHARS = (4, 5)
SINGLE_SHIFTS = {4: 1, 5: 2}
FIRST_ABBREVIATION_VERSION = 3
ABBREVIATION_CHARS = (1, 2, 3)
V2_ABBREVIATION_CHAR = 1

# Abbreviation z then x names entry 32(z - 1) + x of the table the
# header points at; each entry is a word address, doubled to reach
# bytes (§3.3, §1.2.2).
ABBREVIATION_BANK_SIZE = 32
WORD_ADDRESS_SCALE = 2
WORD_SIZE = 2

# In alphabet A2, character 6 escapes to a ten-bit ZSCII code and
# character 7 is a new-line, except in Version 1 (§3.4, §3.5.3).
A2 = 2
ESCAPE = 6
A2_NEWLINE = 7

# The alphabet rows for Z-characters 6 to 31 (§3.5.3). Leading A2
# entries marked ? are placeholders: the escape (all versions) and
# the new-line (Version 2 up) are handled before any table lookup.
# Version 1 keeps the escape but has no A2 new-line -- its new-line
# is Z-character 1 -- freeing a slot for the < character (§3.5.4).
ALPHABET_A0 = "abcdefghijklmnopqrstuvwxyz"
ALPHABET_A1 = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
ALPHABET_A2 = "??0123456789.,!?_#'\"/\\-:()"
ALPHABET_A2_V1 = "?0123456789.,!?_#'\"/\\<-:()"

# ZSCII output codes: 13 is new-line, and 32 to 126 agree with ASCII
# (§3.8.2.5, §3.8.3).
ZSCII_NEWLINE = 13
ZSCII_PRINTABLE_START = 32
ZSCII_PRINTABLE_END = 126

FIRST_ALPHABET_CHARACTER = 6

# Dictionary-form encoding is fixed-length: 6 Z-characters through
# Version 3, 9 after, padded with 5s and guillotined past that
# (§3.7, §13.3, §13.4).
DICTIONARY_ZCHARS = {1: 6, 2: 6, 3: 6, 4: 9, 5: 9, 6: 9, 7: 9, 8: 9}
PAD = 5


def decode_string(memory: Memory, address: int) -> tuple[str, int]:
    """Decode the encoded string beginning at an address (§3.2).

    Args:
        memory: The memory image holding the string.
        address: The byte address of the string's first word.

    Returns:
        The decoded text and the first address past the string.

    Raises:
        ZMachineTextError: On an abbreviation breaking §3.3.1's rules,
            or text needing a custom alphabet table, which does not
            exist yet (§3.5.5).
        ZMachineMemoryError: If the string runs outside the
            story file (§1.1).
    """

    if memory.header.alphabet_table_address != 0:
        msg = "custom alphabet tables are not yet implemented (§3.5.5)"

        raise ZMachineTextError(msg)

    zchars, end = _zchars_at(memory, address)

    return _text_of(memory, zchars), end


def zscii_to_char(code: int) -> str:
    """Convert a ZSCII output code to a character (§3.8).

    Args:
        code: The ZSCII code, from an escape or a print_char operand.

    Returns:
        The character the code means.

    Raises:
        ZMachineTextError: For codes outside new-line and the ASCII
            range, which need the extra-character machinery (§3.8.5).
    """

    if code == ZSCII_NEWLINE:
        return "\n"

    if ZSCII_PRINTABLE_START <= code <= ZSCII_PRINTABLE_END:
        return chr(code)

    msg = f"ZSCII code {code} is not yet printable (§3.8)"

    raise ZMachineTextError(msg)


def encode_word(version: int, word: str) -> bytes:
    """Encode typed text in dictionary form (§3.7).

    The text is lowercased, encoded without abbreviations, padded
    with 5s, and cut to the dictionary resolution; the final word
    carries the terminator bit.

    Args:
        version: The story's version, which sets the resolution and
            the shift convention.
        word: The typed word to encode.

    Returns:
        The encoded bytes: four through Version 3, six after.
    """

    resolution = DICTIONARY_ZCHARS[version]
    zchars = _encode_zchars(version, word.lower())[:resolution]
    zchars += [PAD] * (resolution - len(zchars))

    encoded = b""

    for index in range(0, resolution, 3):
        packed = (
            (zchars[index] << Z_CHAR_SHIFTS[0])
            | (zchars[index + 1] << Z_CHAR_SHIFTS[1])
            | zchars[index + 2]
        )

        if index + 3 == resolution:
            packed |= STRING_TERMINATOR_BIT

        encoded += packed.to_bytes(2, "big")

    return encoded


def _encode_zchars(version: int, text: str) -> list[int]:
    """Turn lowercased text into shift-laden Z-characters (§3.7).

    From Version 3, each A2 character takes a single shift 5. In
    Versions 1 and 2 the shifts are relative, and a lock is used
    instead when the next two characters share an alphabet (§3.7.1).
    """

    a0, _, a2 = _alphabets(version)
    a2_search_start = 1 if version == 1 else 2

    targets: list[tuple[int, list[int]]] = []

    for character in text:
        if character in a0:
            targets.append((0, [a0.index(character) + FIRST_ALPHABET_CHARACTER]))
            continue

        position = a2.find(character, a2_search_start)

        if position >= 0:
            targets.append((A2, [position + FIRST_ALPHABET_CHARACTER]))
        else:
            code = ord(character)
            escape = [ESCAPE, (code >> 5) & Z_CHAR_MASK, code & Z_CHAR_MASK]
            targets.append((A2, escape))

    if version > LAST_SHIFT_LOCK_VERSION:
        out: list[int] = []

        for alphabet, chars in targets:
            if alphabet == A2:
                # Z-character 5 selects A2 for one character (§3.2.3).
                out.append(5)

            out.extend(chars)

        return out

    return _shift_locked(targets)


def _shift_locked(targets: list[tuple[int, list[int]]]) -> list[int]:
    """Emit Version 1 and 2 shifts, locking for runs (§3.2.2, §3.7.1)."""

    out: list[int] = []
    locked = 0

    for index, (alphabet, chars) in enumerate(targets):
        if alphabet != locked:
            run = index + 1 < len(targets) and targets[index + 1][0] == alphabet
            upward = (alphabet - locked) % 3 == 1

            if run:
                out.append(4 if upward else 5)
                locked = alphabet
            else:
                out.append(2 if upward else 3)

        out.extend(chars)

    return out


def _zchars_at(memory: Memory, address: int) -> tuple[list[int], int]:
    """Gather a string's Z-characters up to its terminator (§3.2).

    Returns:
        The Z-characters and the first address past the string.
    """

    zchars: list[int] = []
    pos = address

    while True:
        word = memory.fetch_word(pos)
        pos += WORD_SIZE

        zchars.extend((word >> shift) & Z_CHAR_MASK for shift in Z_CHAR_SHIFTS)

        if word & STRING_TERMINATOR_BIT:
            break

    return zchars, pos


def _text_of(memory: Memory, zchars: list[int], in_abbreviation: bool = False) -> str:
    """Interpret Z-characters under a version's rules (§3.2, §3.5).

    A string may legally end mid-construction, the remnant ignored
    (§3.6.1) -- except inside an abbreviation, where that and any
    further abbreviation are illegal (§3.3.1).
    """

    version = memory.header.version
    rows = _alphabets(version)
    out: list[str] = []
    locked = 0
    current = 0
    position = 0

    while position < len(zchars):
        char = zchars[position]
        position += 1

        if char == SPACE:
            out.append(" ")
            current = locked
        elif version == 1 and char == V1_NEWLINE:
            out.append("\n")
            current = locked
        elif _is_abbreviation(version, char):
            if in_abbreviation:
                msg = "an abbreviation may not use abbreviations (§3.3.1)"

                raise ZMachineTextError(msg)

            if position >= len(zchars):
                _require_complete(in_abbreviation)
                break

            out.append(_abbreviation(memory, char, zchars[position]))
            position += 1
            current = locked
        elif char < FIRST_ALPHABET_CHARACTER:
            current, locked = _shift(version, current, locked, char)
        elif current == A2 and char == ESCAPE:
            if position + 2 > len(zchars):
                _require_complete(in_abbreviation)
                break

            code = (zchars[position] << 5) | zchars[position + 1]
            out.append(zscii_to_char(code))
            position += 2
            current = locked
        elif current == A2 and version > 1 and char == A2_NEWLINE:
            out.append("\n")
            current = locked
        else:
            out.append(rows[current][char - FIRST_ALPHABET_CHARACTER])
            current = locked

    return "".join(out)


def _require_complete(in_abbreviation: bool) -> None:
    """Police §3.3.1: only abbreviations may not end mid-construction."""

    if in_abbreviation:
        msg = (
            "an abbreviation may not end with an incomplete "
            "multi-Z-character construction (§3.3.1)"
        )

        raise ZMachineTextError(msg)


def _abbreviation(memory: Memory, bank_char: int, index: int) -> str:
    """Expand abbreviation entry 32(z - 1) + x (§3.3).

    The table entry is a word address, doubled to reach the string's
    bytes (§1.2.2) -- the one place word addresses are used at all.
    """

    table = memory.header.abbreviations_table_address
    entry_number = ABBREVIATION_BANK_SIZE * (bank_char - 1) + index
    entry = memory.fetch_word(table + WORD_SIZE * entry_number)
    zchars, _ = _zchars_at(memory, WORD_ADDRESS_SCALE * entry)

    return _text_of(memory, zchars, in_abbreviation=True)


def _alphabets(version: int) -> tuple[str, str, str]:
    """Pick the version's alphabet rows (§3.5.3, §3.5.4)."""

    if version == 1:
        return ALPHABET_A0, ALPHABET_A1, ALPHABET_A2_V1

    return ALPHABET_A0, ALPHABET_A1, ALPHABET_A2


def _is_abbreviation(version: int, char: int) -> bool:
    """Whether a Z-character introduces an abbreviation (§3.3)."""

    if version >= FIRST_ABBREVIATION_VERSION:
        return char in ABBREVIATION_CHARS

    return version == LAST_SHIFT_LOCK_VERSION and char == V2_ABBREVIATION_CHAR


def _shift(version: int, current: int, locked: int, char: int) -> tuple[int, int]:
    """Apply a shift character, returning (current, locked) (§3.2.2, §3.2.3).

    In Versions 1 and 2, characters 2 and 3 rotate the alphabet for
    one character and 4 and 5 rotate the lock; from Version 3, 4 and
    5 select A1 or A2 absolutely, for one character.
    """

    if version > LAST_SHIFT_LOCK_VERSION:
        return SINGLE_SHIFTS[char], locked

    rotated = (current + (1 if char % 2 == 0 else 2)) % 3

    if char in LOCK_CHARS:
        return rotated, rotated

    return rotated, locked
