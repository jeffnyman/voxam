"""Unpacking packed addresses into byte addresses (§1.2.3).

A packed address is how a 16-bit word reaches a routine or string in
high memory: the word is scaled up by a version-dependent factor, and
Versions 6 and 7 add a header-declared offset on top. Routines and
strings use different offsets, hence the two functions.
"""

from voxam.zmachine.header import OFFSET_VERSIONS, Header

# The scale factor from packed to byte address (§1.2.3). Versions 6
# and 7 scale by 4 and then add an offset.
SCALE = {1: 2, 2: 2, 3: 2, 4: 4, 5: 4, 6: 4, 7: 4, 8: 8}

# The header stores the routine and string offsets divided by 8
# (§1.2.3), so unpacking multiplies them back up.
OFFSET_FACTOR = 8


def routine_address(header: Header, packed: int) -> int:
    """Unpack the byte address a packed routine address means (§1.2.3).

    Args:
        header: The header of the story the address lives in.
        packed: The packed address, as found in an operand or at $06.

    Returns:
        The byte address at which the routine begins.
    """

    address = packed * SCALE[header.version]

    if header.version in OFFSET_VERSIONS:
        address += OFFSET_FACTOR * header.routines_offset

    return address


def string_address(header: Header, packed: int) -> int:
    """Unpack the byte address a packed string address means (§1.2.3).

    Args:
        header: The header of the story the address lives in.
        packed: The packed address, as used by print_paddr.

    Returns:
        The byte address at which the encoded string begins.
    """

    address = packed * SCALE[header.version]

    if header.version in OFFSET_VERSIONS:
        address += OFFSET_FACTOR * header.static_strings_offset

    return address
