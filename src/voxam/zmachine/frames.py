"""The routine call state: frames, locals, and the stack (§6).

The "state of play" includes the chain of routines that have called
each other (§6.1). Each link is a frame holding the caller's return
address, where the result should go, the routine's local variables,
and its own portion of the stack -- because a routine starts with an
empty stack and can never reach past its own frame (§6.3.1, §6.3.2).
"""

from dataclasses import dataclass, field

from voxam.errors import ZMachineStackError
from voxam.zmachine.memory import WORD_MAX
from voxam.zmachine.routine import Routine

# Local variables are numbered 1 to 15 (§4.2.2).
FIRST_LOCAL = 1

# §6.3.3 defines a call's "usage" as 4 plus its local count, and sets
# 1024 total usage as the classic floor a game may assume -- while
# noting later games need much more. This ceiling is 64 times that
# floor: far above any legitimate game, and low enough to turn
# runaway recursion into a loud halt rather than a silent hang.
# (Zork 1 release 15 has exactly such a bug, which crashed period
# interpreters by exhausting their fixed stacks.)
FRAME_USAGE = 4
USAGE_LIMIT = 64 * 1024


@dataclass
class Frame:
    """One routine invocation's private state (§6.1).

    Deliberately mutable: locals and the stack change as the routine
    runs.

    Attributes:
        return_address: Where execution resumes when this routine
            returns (§6.4).
        store_variable: The caller's variable for the return value, or
            None when the result is thrown away (§6.4.1).
        locals: The routine's local variable values, in order (§6.4.4).
        argument_count: How many arguments the caller supplied, which
            check_arg_count can ask about (§6.4.4.1).
        stack: This routine's portion of the stack, empty at routine
            start (§6.3.1).
    """

    return_address: int
    store_variable: int | None
    locals: list[int]
    argument_count: int
    stack: list[int] = field(default_factory=list)


class CallStack:
    """The chain of routine invocations (§6.1).

    Born holding one base frame: outside Version 6, execution begins
    at an instruction that is not inside any called routine (§5.5),
    and that resting place needs a stack to work with too.
    """

    def __init__(self) -> None:
        """Start the call state with an un-returnable base frame."""

        self._frames = [
            Frame(return_address=0, store_variable=None, locals=[], argument_count=0)
        ]
        self._usage = 0

    @property
    def depth(self) -> int:
        """How many frames deep the call state is, counting the base."""

        return len(self._frames)

    @property
    def argument_count(self) -> int:
        """How many arguments the current routine received (§6.4.4.1)."""

        return self._frames[-1].argument_count

    def call(
        self,
        routine: Routine,
        arguments: tuple[int, ...],
        return_address: int,
        store_variable: int | None,
    ) -> None:
        """Enter a routine, creating its frame (§6.4).

        Locals begin at the routine header's initial values -- zero
        from Version 5 -- and the arguments then overwrite the first
        locals (§6.4.4). Spare arguments are thrown away (§6.4.4.1).

        Args:
            routine: The parsed routine being called.
            arguments: The operand values after the routine address.
            return_address: Where execution resumes on return.
            store_variable: The caller's variable for the result, or
                None when the opcode throws it away.

        Raises:
            ZMachineStackError: If the call would push total stack
                usage past the ceiling (§6.3.3) -- the loud version
                of the stack overflow a period interpreter would
                crash with, and almost certainly runaway recursion.
        """

        initial = list(routine.initial_locals)

        self._claim_usage(FRAME_USAGE + len(initial))

        initial[: len(arguments)] = arguments[: len(initial)]

        self._frames.append(
            Frame(
                return_address=return_address,
                store_variable=store_variable,
                locals=initial,
                argument_count=len(arguments),
            )
        )

    def pop_frame(self) -> Frame:
        """Leave the current routine, discarding its state (§6.3.2).

        Returns:
            The abandoned frame, whose return_address and
            store_variable direct what happens next.

        Raises:
            ZMachineStackError: If only the base frame remains; there
                is no routine to return from.
        """

        if len(self._frames) == 1:
            msg = "cannot return: no routine has been called (§6.4)"

            raise ZMachineStackError(msg)

        frame = self._frames.pop()
        self._usage -= FRAME_USAGE + len(frame.locals) + len(frame.stack)

        return frame

    def local(self, number: int) -> int:
        """Read a local variable of the current routine (§4.2.2).

        Args:
            number: The local variable number, 1 to 15.

        Returns:
            The local's current value.

        Raises:
            ZMachineStackError: If the current routine has no such
                local, which §4.2.2 makes illegal to touch.
        """

        return self._frames[-1].locals[self._local_index(number)]

    def set_local(self, number: int, value: int) -> None:
        """Write a local variable of the current routine (§4.2.2).

        Args:
            number: The local variable number, 1 to 15.
            value: The word value to store.

        Raises:
            ZMachineStackError: If the current routine has no such
                local, or the value does not fit in a word.
        """

        self._require_word(value)

        self._frames[-1].locals[self._local_index(number)] = value

    def push(self, value: int) -> None:
        """Push a word onto the current routine's stack (§6.3).

        Args:
            value: The word value to push.

        Raises:
            ZMachineStackError: If the value does not fit in a word,
                or the push would pass the usage ceiling (§6.3.3).
        """

        self._require_word(value)
        self._claim_usage(1)

        self._frames[-1].stack.append(value)

    def pop(self) -> int:
        """Pull the top word off the current routine's stack (§6.3).

        Returns:
            The popped value.

        Raises:
            ZMachineStackError: If the current routine's stack is
                empty; a routine cannot reach past its own frame
                (§6.3.1).
        """

        stack = self._frames[-1].stack

        if not stack:
            msg = (
                "cannot pull from an empty stack: a routine only sees "
                "values it pushed itself (§6.3.1)"
            )

            raise ZMachineStackError(msg)

        self._usage -= 1

        return stack.pop()

    def peek(self) -> int:
        """Read the top of the stack without pulling it (§6.3.4).

        The seven indirect-reference opcodes read the stack top in
        place, leaving the depth unchanged.

        Returns:
            The value on top of the current routine's stack.

        Raises:
            ZMachineStackError: If the current routine's stack is
                empty.
        """

        stack = self._frames[-1].stack

        if not stack:
            msg = "cannot read the top of an empty stack in place (§6.3.4)"

            raise ZMachineStackError(msg)

        return stack[-1]

    def replace_top(self, value: int) -> None:
        """Overwrite the top of the stack in place (§6.3.4).

        Args:
            value: The word value to write over the current top.

        Raises:
            ZMachineStackError: If the current routine's stack is
                empty, or the value does not fit in a word.
        """

        self._require_word(value)

        stack = self._frames[-1].stack

        if not stack:
            msg = "cannot overwrite the top of an empty stack in place (§6.3.4)"

            raise ZMachineStackError(msg)

        stack[-1] = value

    def _local_index(self, number: int) -> int:
        """Map a local number to its list index, policing §4.2.2."""

        frame = self._frames[-1]

        if not FIRST_LOCAL <= number <= len(frame.locals):
            msg = (
                f"the current routine has {len(frame.locals)} locals, so "
                f"local {number} does not exist (§4.2.2)"
            )

            raise ZMachineStackError(msg)

        return number - FIRST_LOCAL

    def _require_word(self, value: int) -> None:
        """Reject values that do not fit in a word (§6.3)."""

        if not 0 <= value <= WORD_MAX:
            msg = f"value {value} does not fit in a word"

            raise ZMachineStackError(msg)

    def _claim_usage(self, amount: int) -> None:
        """Charge stack usage against the §6.3.3 ceiling.

        A period interpreter's fixed stack would overflow and crash
        here; halting loudly names the almost-certain culprit instead
        of hanging forever on an unbounded one.
        """

        if self._usage + amount > USAGE_LIMIT:
            msg = (
                f"stack usage passed {USAGE_LIMIT} (§6.3.3 promises games "
                f"far less): almost certainly runaway recursion"
            )

            raise ZMachineStackError(msg)

        self._usage += amount
