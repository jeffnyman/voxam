"""Reading and writing the 256 variable numbers (§4.2.2).

Variable number $00 means the stack: writing pushes and reading pulls
(§6.3). Numbers $01 to $0f are the current routine's locals, and $10
to $ff are the globals, stored as a word table in dynamic memory
(§6.2). This module unifies the three behind one read and one write.
"""

from voxam.zmachine.frames import CallStack
from voxam.zmachine.memory import Memory

# Variable $00 is the stack; locals then run to $0f, and globals from
# $10 to $ff (§4.2.2).
STACK_VARIABLE = 0x00
FIRST_GLOBAL = 0x10

WORD_SIZE = 2


class Variables:
    """One façade over the stack, locals, and globals (§4.2.2)."""

    def __init__(self, memory: Memory, calls: CallStack) -> None:
        """Bind the two stores that variables resolve into.

        Args:
            memory: The image whose globals table is read and written.
            calls: The call state holding the stack and locals.
        """

        self._memory = memory
        self._calls = calls
        self._globals = memory.header.global_variables_address

    def read(self, number: int) -> int:
        """Read a variable: pulling, a local, or a global (§4.2.2).

        Args:
            number: The variable number, 0 to 255, as decoded.

        Returns:
            The variable's value; for $00, the pulled top of stack
            (§6.3).

        Raises:
            ZMachineStackError: If the stack is empty or the local
                does not exist.
            ZMachineMemoryError: If the globals table lies outside
                readable memory.
        """

        if number == STACK_VARIABLE:
            return self._calls.pop()

        if number < FIRST_GLOBAL:
            return self._calls.local(number)

        return self._memory.read_word(self._global_address(number))

    def write(self, number: int, value: int) -> None:
        """Write a variable: pushing, a local, or a global (§4.2.2).

        Args:
            number: The variable number, 0 to 255, as decoded.
            value: The word value to store; for $00, pushed (§6.3).

        Raises:
            ZMachineStackError: If the local does not exist or the
                value does not fit in a word.
            ZMachineMemoryError: If the globals table lies outside
                writable memory.
        """

        if number == STACK_VARIABLE:
            self._calls.push(value)
        elif number < FIRST_GLOBAL:
            self._calls.set_local(number, value)
        else:
            self._memory.write_word(self._global_address(number), value)

    def _global_address(self, number: int) -> int:
        """Locate a global in the table at the header's address (§6.2)."""

        return self._globals + WORD_SIZE * (number - FIRST_GLOBAL)
