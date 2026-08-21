"""The built-in search opcodes (Glulx: Searching).

All three look through fixed-size structures in memory for one
whose key matches. They exist for speed: Inform's property and
dictionary lookups dominate its running time, and the spec notes
Advent runs 15-20% faster with binary-search property lookup than
with the equivalent Inform code -- a gap that matters even more in
Python than it does in C.

Keys are compared as byte strings. The reference glulxe carries two
comparison paths -- short keys copied into a stack buffer, long
keys re-read from memory on every comparison, because buffering
would mean allocating. Python has no such constraint, so the key is
fetched once as bytes and every comparison is a single bytes
compare. The equivalence holds because a search never writes
memory, and Python's bytes ordering is lexicographic over unsigned
bytes -- exactly the big-endian unsigned ordering the sorted form
requires.
"""

from voxam.errors import GlulxInstructionError
from voxam.glulx.memory import Memory

_MASK = 0xFFFFFFFF

# The failure answers: the index form fails with -1, the address
# form with 0 (Glulx: Searching).
NOT_FOUND_INDEX = 0xFFFFFFFF
NOT_FOUND_ADDRESS = 0

# The Options flags. Not every flag applies to every search:
# RETURN_INDEX means nothing to linkedsearch, and
# ZERO_KEY_TERMINATES nothing to binarysearch.
KEY_INDIRECT = 0x01
ZERO_KEY_TERMINATES = 0x02
RETURN_INDEX = 0x04

_DIRECT_SIZES = (1, 2, 4)


def _fetch_key(memory: Memory, key: int, keysize: int, options: int) -> bytes:
    """The key operand as the bytes every entry compares against.

    With KeyIndirect the operand is the key's address and any size
    is legal; without it the operand is the key itself, sitting in
    the low bytes big-endian, and must fit a word (Glulx:
    Searching).

    Raises:
        GlulxInstructionError: For a direct key of a size no word
            can hold.
    """

    if options & KEY_INDIRECT:
        return memory.read_run(key, keysize)

    if keysize not in _DIRECT_SIZES:
        msg = (
            f"a direct search key must hold one, two, or four bytes, "
            f"not {keysize} (Glulx: Searching)"
        )

        raise GlulxInstructionError(msg)

    return (key & ((1 << (8 * keysize)) - 1)).to_bytes(keysize, "big")


def linear_search(  # noqa: PLR0913, PLR0917 -- the opcode's own seven operands
    memory: Memory,
    key: int,
    keysize: int,
    start: int,
    structsize: int,
    numstructs: int,
    keyoffset: int,
    options: int,
) -> int:
    """Search an array of structures in order (Glulx: Searching).

    A count of 0xFFFFFFFF means no upper limit: the search then
    runs until it matches or, with ZeroKeyTerminates, until it
    meets an all-zero key.
    """

    keybuf = _fetch_key(memory, key, keysize, options)
    return_index = bool(options & RETURN_INDEX)
    zero_terminates = bool(options & ZERO_KEY_TERMINATES)
    zeros = bytes(keysize)

    address = start

    for count in range(numstructs):
        entry = memory.read_run((address + keyoffset) & _MASK, keysize)

        if entry == keybuf:
            return count if return_index else address

        # Checked after the match, so a search *for* the all-zero
        # key still finds it rather than stopping short.
        if zero_terminates and entry == zeros:
            break

        address = (address + structsize) & _MASK

    return NOT_FOUND_INDEX if return_index else NOT_FOUND_ADDRESS


def binary_search(  # noqa: PLR0913, PLR0917 -- the opcode's own seven operands
    memory: Memory,
    key: int,
    keysize: int,
    start: int,
    structsize: int,
    numstructs: int,
    keyoffset: int,
    options: int,
) -> int:
    """Search a key-ordered array of structures (Glulx: Searching).

    The structures must sit in ascending key order with no
    duplicates, and the count must be exact -- the unlimited
    0xFFFFFFFF is not legal here, and ZeroKeyTerminates does not
    apply.
    """

    keybuf = _fetch_key(memory, key, keysize, options)
    return_index = bool(options & RETURN_INDEX)

    low, high = 0, numstructs

    while low < high:
        middle = (low + high) // 2
        address = (start + middle * structsize) & _MASK
        entry = memory.read_run((address + keyoffset) & _MASK, keysize)

        if entry == keybuf:
            return middle if return_index else address

        if entry < keybuf:
            low = middle + 1
        else:
            high = middle

    return NOT_FOUND_INDEX if return_index else NOT_FOUND_ADDRESS


def linked_search(  # noqa: PLR0913, PLR0917 -- the opcode's own six operands
    memory: Memory,
    key: int,
    keysize: int,
    start: int,
    keyoffset: int,
    nextoffset: int,
    options: int,
) -> int:
    """Follow a linked list of structures (Glulx: Searching).

    A zero in the link field ends the list. ReturnIndex does not
    apply -- a list has no indexes -- so the answer is an address
    or 0.
    """

    keybuf = _fetch_key(memory, key, keysize, options)
    zero_terminates = bool(options & ZERO_KEY_TERMINATES)
    zeros = bytes(keysize)

    address = start

    while address != 0:
        entry = memory.read_run((address + keyoffset) & _MASK, keysize)

        if entry == keybuf:
            return address

        if zero_terminates and entry == zeros:
            break

        address = memory.read_word((address + nextoffset) & _MASK)

    return NOT_FOUND_ADDRESS
