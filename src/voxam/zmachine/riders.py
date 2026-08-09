"""Decoding the riders that may follow an instruction's operands.

A store variable (§4.6), a branch (§4.7), and encoded text (§3.2) are
the three sections an instruction may carry after its operands. Which
opcodes carry which is knowledge that lives in the opcode tables; this
module only knows how to read each rider once told it is present.
"""

from dataclasses import dataclass

from voxam.errors import ZMachineInstructionError
from voxam.zmachine.memory import Memory

# Offsets 0 and 1 are not jumps: they mean return false and return
# true from the current routine (§4.7.1).
RETURN_FALSE_OFFSET = 0
RETURN_TRUE_OFFSET = 1

# A branch destination is the address after the branch data, plus the
# offset, minus two (§4.7.2).
BRANCH_TARGET_ADJUSTMENT = 2

# Bit 7 of the first branch byte: set means branch on true, clear means
# branch on false (§4.7).
BRANCH_ON_TRUE_BIT = 0b1000_0000

# Bit 6 of the first branch byte: set means the branch occupies one
# byte, with an unsigned offset in the bottom 6 bits; clear means a
# signed 14-bit offset in the bottom 6 bits plus a second byte (§4.7).
SHORT_BRANCH_BIT = 0b0100_0000
OFFSET_HIGH_MASK = 0b0011_1111

# Two's complement bounds for the signed 14-bit long offset (§4.7).
LONG_OFFSET_SIGN = 1 << 13
LONG_OFFSET_RANGE = 1 << 14

# Encoded text is a sequence of words; only the last word of a string
# has its top bit set (§3.2).
STRING_TERMINATOR_BIT = 0x8000


@dataclass(frozen=True)
class Branch:
    """A decoded branch rider (§4.7).

    Attributes:
        on_true: Whether the branch is taken when the tested condition
            is true (bit 7 set) rather than false (bit 7 clear).
        offset: The branch offset. The values 0 and 1 do not mean a
            jump; they mean return false and return true (§4.7.1).
    """

    on_true: bool
    offset: int

    @property
    def returns_false(self) -> bool:
        """Whether this branch means "return false" (§4.7.1)."""

        return self.offset == RETURN_FALSE_OFFSET

    @property
    def returns_true(self) -> bool:
        """Whether this branch means "return true" (§4.7.1)."""

        return self.offset == RETURN_TRUE_OFFSET

    def target(self, after: int) -> int:
        """The destination address for a taken branch (§4.7.2).

        Args:
            after: The address immediately after the branch data.

        Returns:
            The address execution moves to when the branch is taken.

        Raises:
            ZMachineInstructionError: If the offset means a return
                rather than a jump (§4.7.1).
        """

        if self.returns_false or self.returns_true:
            msg = (
                f"branch offset {self.offset} means a return, not a "
                f"jump, and has no target address (§4.7.1)"
            )

            raise ZMachineInstructionError(msg)

        return after + self.offset - BRANCH_TARGET_ADJUSTMENT


def read_store_variable(memory: Memory, address: int) -> tuple[int, int]:
    """Read a store rider: the variable number for a result (§4.6).

    Args:
        memory: The memory image holding the instruction.
        address: The byte address of the store byte.

    Returns:
        The variable number and the first address past the rider.
    """

    return memory.fetch_byte(address), address + 1


def read_branch(memory: Memory, address: int) -> tuple[Branch, int]:
    """Read a branch rider of one or two bytes (§4.7).

    Args:
        memory: The memory image holding the instruction.
        address: The byte address of the first branch byte.

    Returns:
        The decoded branch and the first address past the rider.
    """

    first = memory.fetch_byte(address)
    on_true = bool(first & BRANCH_ON_TRUE_BIT)

    if first & SHORT_BRANCH_BIT:
        return Branch(on_true, first & OFFSET_HIGH_MASK), address + 1

    offset = ((first & OFFSET_HIGH_MASK) << 8) | memory.fetch_byte(address + 1)

    if offset & LONG_OFFSET_SIGN:
        offset -= LONG_OFFSET_RANGE

    return Branch(on_true, offset), address + 2


def text_end(memory: Memory, address: int) -> int:
    """Find the end of an encoded string without decoding it (§3.2).

    Args:
        memory: The memory image holding the instruction.
        address: The byte address of the string's first word.

    Returns:
        The first address past the word whose top bit is set.

    Raises:
        ZMachineMemoryError: If no terminator appears before the end
            of the story file.
    """

    pos = address

    while not memory.fetch_word(pos) & STRING_TERMINATOR_BIT:
        pos += 2

    return pos + 2
