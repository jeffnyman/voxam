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

# In alphabet A2, character 6 escapes to a ten-bit ZSCII code and
# character 7 is a new-line, except in Version 1 (§3.4, §3.5.3).
A2 = 2
ESCAPE = 6
A2_NEWLINE = 7

# The alphabet rows for Z-characters 6 to 31 (§3.5.3). The first two
# A2 entries are placeholders: escape and new-line are handled before
# any table lookup. Version 1 has its own A2 row, with no new-line
# and a < character (§3.5.4).
ALPHABET_A0 = "abcdefghijklmnopqrstuvwxyz"
ALPHABET_A1 = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
ALPHABET_A2 = "??0123456789.,!?_#'\"/\\-:()"
ALPHABET_A2_V1 = "0123456789.,!?_#'\"/\\<-:()"

# ZSCII output codes: 13 is new-line, and 32 to 126 agree with ASCII
# (§3.8.2.5, §3.8.3).
ZSCII_NEWLINE = 13
ZSCII_PRINTABLE_START = 32
ZSCII_PRINTABLE_END = 126

FIRST_ALPHABET_CHARACTER = 6


def decode_string(memory: Memory, address: int) -> tuple[str, int]:
    """Decode the encoded string beginning at an address (§3.2).

    Args:
        memory: The memory image holding the string.
        address: The byte address of the string's first word.

    Returns:
        The decoded text and the first address past the string.

    Raises:
        ZMachineTextError: On text needing machinery that does not
            exist yet: abbreviations (§3.3) or a custom alphabet
            table (§3.5.5).
        ZMachineMemoryError: If the string runs outside the
            game-readable regions.
    """

    if memory.header.alphabet_table_address != 0:
        msg = "custom alphabet tables are not yet implemented (§3.5.5)"

        raise ZMachineTextError(msg)

    zchars: list[int] = []
    pos = address

    while True:
        word = memory.read_word(pos)
        pos += 2

        zchars.extend((word >> shift) & Z_CHAR_MASK for shift in Z_CHAR_SHIFTS)

        if word & STRING_TERMINATOR_BIT:
            break

    return _text_of(memory.header.version, zchars), pos


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


def _text_of(version: int, zchars: list[int]) -> str:
    """Interpret Z-characters under a version's rules (§3.2, §3.5)."""

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
            msg = "abbreviations are not yet implemented (§3.3)"

            raise ZMachineTextError(msg)
        elif char < FIRST_ALPHABET_CHARACTER:
            current, locked = _shift(version, current, locked, char)
        elif current == A2 and version > 1 and char == ESCAPE:
            out.append(_escaped(zchars, position))
            position += 2
            current = locked
        elif current == A2 and version > 1 and char == A2_NEWLINE:
            out.append("\n")
            current = locked
        else:
            out.append(rows[current][char - FIRST_ALPHABET_CHARACTER])
            current = locked

    return "".join(out)


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


def _escaped(zchars: list[int], position: int) -> str:
    """Assemble a ten-bit ZSCII escape from two Z-characters (§3.4).

    Args:
        zchars: The full Z-character sequence.
        position: The index of the escape's first payload character.

    Raises:
        ZMachineTextError: If the string ends inside the escape.
    """

    if position + 2 > len(zchars):
        msg = "the string ends inside a ZSCII escape (§3.4)"

        raise ZMachineTextError(msg)

    code = (zchars[position] << 5) | zchars[position + 1]

    return zscii_to_char(code)
