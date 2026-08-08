"""The machine loop: fetch, decode, dispatch (§6).

A Machine binds everything built so far -- the memory image, the call
state, the variable façade -- to a program counter, and executes one
instruction at a time. Opcodes it does not yet implement raise
ZMachineUnimplementedError, so pointing Voxam at any story reveals
the frontier of what remains to build.
"""

import sys
from collections.abc import Callable

from voxam.errors import ZMachineUnimplementedError
from voxam.zmachine.frames import CallStack
from voxam.zmachine.header import PACKED_PC_VERSION
from voxam.zmachine.instruction import Instruction, Operand, OperandType
from voxam.zmachine.memory import Memory
from voxam.zmachine.packed import routine_address, string_address
from voxam.zmachine.routine import Routine
from voxam.zmachine.story import Story
from voxam.zmachine.variables import Variables
from voxam.zmachine.zscii import decode_string, zscii_to_char

# Returning "false" means 0 and "true" means 1 (§6.4.5).
FALSE_VALUE = 0
TRUE_VALUE = 1

# A call to packed address 0 does nothing and returns false (§6.4.3).
NULL_ROUTINE = 0

# Words hold signed values in two's complement: $8000 and up are
# negative (§2.2).
SIGN_BIT = 0x8000
WORD_RANGE = 0x10000


def signed(value: int) -> int:
    """Interpret a word as a signed number (§2.2)."""

    return value - WORD_RANGE if value & SIGN_BIT else value


class Machine:
    """A running Z-Machine (§6.1).

    The state of play: the memory image, the routine call state, and
    the program counter, advanced one instruction at a time.
    """

    def __init__(
        self, story: Story, output: Callable[[str], None] | None = None
    ) -> None:
        """Boot the machine into its §5.4/§5.5 starting state.

        Outside Version 6, execution begins at the header's initial
        address, inside no routine (§5.5). Version 6 instead calls the
        main routine (§5.4).

        Args:
            story: The validated story file to run.
            output: Where printed text goes; standard output when not
                given. A richer §8 screen model will replace this.
        """

        self._memory = Memory(story)
        self._calls = CallStack()
        self._variables = Variables(self._memory, self._calls)
        self._output = output if output is not None else sys.stdout.write
        self._running = True

        header = self._memory.header

        if header.version == PACKED_PC_VERSION:
            address = routine_address(header, header.main_routine_packed_address)
            routine = Routine.parse(self._memory, address)

            self._calls.call(routine, (), return_address=0, store_variable=None)

            self._pc = routine.first_instruction
        else:
            self._pc = header.initial_program_counter

    @property
    def memory(self) -> Memory:
        """The working memory image, live as the game mutates it."""

        return self._memory

    @property
    def pc(self) -> int:
        """The byte address of the next instruction to execute."""

        return self._pc

    @property
    def running(self) -> bool:
        """Whether execution has not yet been halted by quit."""

        return self._running

    def run(self) -> None:
        """Execute instructions until the story quits.

        Raises:
            ZMachineUnimplementedError: On reaching an opcode Voxam
                does not yet implement; the error names it and where.
            VoxamError: On any rule the story or the machine breaks.
        """

        while self._running:
            self.step()

    def step(self) -> None:
        """Fetch, decode, and execute a single instruction.

        Raises:
            ZMachineUnimplementedError: If the decoded opcode has no
                handler yet.
            VoxamError: On any rule the instruction breaks.
        """

        instruction = Instruction.decode(self._memory, self._pc)
        handler = _HANDLERS.get(instruction.opcode.name)

        if handler is None:
            raise ZMachineUnimplementedError(
                instruction.opcode.name, instruction.address
            )

        handler(self, instruction)

    def _value(self, operand: Operand) -> int:
        """Resolve an operand to a value, reading variables (§4.2.2)."""

        if operand.kind is OperandType.VARIABLE:
            return self._variables.read(operand.value)

        return operand.value

    def _return(self, value: int) -> None:
        """Leave the current routine, delivering its result (§6.4.5).

        Args:
            value: The value the routine returns.
        """

        frame = self._calls.pop_frame()
        self._pc = frame.return_address

        if frame.store_variable is not None:
            self._variables.write(frame.store_variable, value)

    def _op_call(self, instruction: Instruction) -> None:
        """Call a routine, or return false for address 0 (§6.4)."""

        values = [self._value(operand) for operand in instruction.operands]
        packed = values[0]

        if packed == NULL_ROUTINE:
            if instruction.store_variable is not None:
                self._variables.write(instruction.store_variable, FALSE_VALUE)

            self._pc = instruction.next_address

            return

        address = routine_address(self._memory.header, packed)
        routine = Routine.parse(self._memory, address)

        self._calls.call(
            routine,
            tuple(values[1:]),
            return_address=instruction.next_address,
            store_variable=instruction.store_variable,
        )

        self._pc = routine.first_instruction

    def _op_ret(self, instruction: Instruction) -> None:
        """Return the operand's value from the current routine (§6.4.5)."""

        self._return(self._value(instruction.operands[0]))

    def _op_rtrue(self, _instruction: Instruction) -> None:
        """Return true from the current routine (§6.4.5)."""

        self._return(TRUE_VALUE)

    def _op_rfalse(self, _instruction: Instruction) -> None:
        """Return false from the current routine (§6.4.5)."""

        self._return(FALSE_VALUE)

    def _op_print(self, instruction: Instruction) -> None:
        """Print the literal string following the opcode (§3.2)."""

        text, _ = decode_string(self._memory, instruction.operands_end)
        self._output(text)
        self._pc = instruction.next_address

    def _op_print_ret(self, instruction: Instruction) -> None:
        """Print the literal string, a new-line, and return true (§14)."""

        text, _ = decode_string(self._memory, instruction.operands_end)
        self._output(text + "\n")
        self._return(TRUE_VALUE)

    def _op_print_paddr(self, instruction: Instruction) -> None:
        """Print the string at a packed address (§1.2.3)."""

        packed = self._value(instruction.operands[0])
        address = string_address(self._memory.header, packed)
        text, _ = decode_string(self._memory, address)
        self._output(text)
        self._pc = instruction.next_address

    def _op_print_addr(self, instruction: Instruction) -> None:
        """Print the string at a byte address (§14)."""

        address = self._value(instruction.operands[0])
        text, _ = decode_string(self._memory, address)
        self._output(text)
        self._pc = instruction.next_address

    def _op_print_char(self, instruction: Instruction) -> None:
        """Print the character a ZSCII code means (§3.8)."""

        self._output(zscii_to_char(self._value(instruction.operands[0])))
        self._pc = instruction.next_address

    def _op_print_num(self, instruction: Instruction) -> None:
        """Print an operand as a signed decimal number (§2.2)."""

        self._output(str(signed(self._value(instruction.operands[0]))))
        self._pc = instruction.next_address

    def _op_new_line(self, instruction: Instruction) -> None:
        """Print a new-line."""

        self._output("\n")
        self._pc = instruction.next_address

    def _op_push(self, instruction: Instruction) -> None:
        """Push the operand's value onto the stack (§6.3)."""

        self._calls.push(self._value(instruction.operands[0]))
        self._pc = instruction.next_address

    def _op_ret_popped(self, _instruction: Instruction) -> None:
        """Return the top of the current routine's stack (§6.4.5)."""

        self._return(self._calls.pop())

    def _op_quit(self, _instruction: Instruction) -> None:
        """Halt the machine; run() then returns normally."""

        self._running = False


# Dispatch by opcode name: call and call_vs are the same behaviour
# under the two names §14 gives VAR:0 across versions, and call_vn
# differs only in having no store variable to fill (§6.4.1).
_HANDLERS: dict[str, Callable[[Machine, Instruction], None]] = {
    "call": Machine._op_call,
    "call_vn": Machine._op_call,
    "call_vs": Machine._op_call,
    "new_line": Machine._op_new_line,
    "print": Machine._op_print,
    "print_addr": Machine._op_print_addr,
    "print_char": Machine._op_print_char,
    "print_num": Machine._op_print_num,
    "print_paddr": Machine._op_print_paddr,
    "print_ret": Machine._op_print_ret,
    "push": Machine._op_push,
    "ret": Machine._op_ret,
    "rtrue": Machine._op_rtrue,
    "rfalse": Machine._op_rfalse,
    "ret_popped": Machine._op_ret_popped,
    "quit": Machine._op_quit,
}
