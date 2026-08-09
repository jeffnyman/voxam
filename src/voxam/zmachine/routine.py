"""Parsing routine headers (§5).

A routine is a header -- one byte counting the local variables, plus,
in Versions 1 to 4, their initial values -- followed by instructions.
Nothing here executes; this module only reads the header and locates
the first instruction.
"""

from dataclasses import dataclass
from typing import Self

from voxam.errors import ZMachineRoutineError
from voxam.zmachine.memory import Memory

# A routine has between 0 and 15 local variables (§5.2).
MAX_LOCALS = 15

# Initial local values live in the routine header only through
# Version 4; from Version 5 they are all zero (§5.2.1).
LOCALS_IN_HEADER_LAST_VERSION = 4

WORD_SIZE = 2


@dataclass(frozen=True)
class Routine:
    """A parsed routine header (§5.2).

    Attributes:
        address: The byte address of the routine header.
        initial_locals: One initial value per local variable, from the
            header in Versions 1 to 4, all zero from Version 5
            (§5.2.1).
        first_instruction: The byte address execution begins at (§5.3).
    """

    address: int
    initial_locals: tuple[int, ...]
    first_instruction: int

    @classmethod
    def parse(cls, memory: Memory, address: int) -> Self:
        """Parse the routine header beginning at an address (§5.2).

        Args:
            memory: The memory image holding the routine.
            address: The byte address of the local-count byte.

        Returns:
            The parsed routine.

        Raises:
            ZMachineRoutineError: If the local count exceeds 15, which
                usually means the address is not a routine at all.
            ZMachineMemoryError: If the header runs outside the
                story file (§1.1).
        """

        count = memory.fetch_byte(address)

        if count > MAX_LOCALS:
            msg = (
                f"the byte at ${address:04x} claims {count} locals, but a "
                f"routine has at most {MAX_LOCALS} (§5.2); this is "
                f"probably not a routine address"
            )

            raise ZMachineRoutineError(msg)

        if memory.header.version <= LOCALS_IN_HEADER_LAST_VERSION:
            initial_locals = tuple(
                memory.fetch_word(address + 1 + WORD_SIZE * index)
                for index in range(count)
            )
            first_instruction = address + 1 + WORD_SIZE * count
        else:
            initial_locals = (0,) * count
            first_instruction = address + 1

        return cls(
            address=address,
            initial_locals=initial_locals,
            first_instruction=first_instruction,
        )
