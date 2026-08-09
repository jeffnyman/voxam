"""The machine loop: fetch, decode, dispatch (§6).

A Machine binds everything built so far -- the memory image, the call
state, the variable façade -- to a program counter, and executes one
instruction at a time. Opcodes it does not yet implement raise
ZMachineUnimplementedError, so pointing Voxam at any story reveals
the frontier of what remains to build.
"""

import operator
import sys
from collections.abc import Callable

from voxam.errors import (
    ZMachineArithmeticError,
    ZMachineInstructionError,
    ZMachineUnimplementedError,
)
from voxam.zmachine.dictionary import Dictionary, tokenize
from voxam.zmachine.frames import CallStack
from voxam.zmachine.header import PACKED_PC_VERSION
from voxam.zmachine.instruction import Instruction, Operand, OperandType
from voxam.zmachine.memory import Memory
from voxam.zmachine.objects import ObjectTable
from voxam.zmachine.packed import routine_address, string_address
from voxam.zmachine.riders import BRANCH_TARGET_ADJUSTMENT
from voxam.zmachine.rng import Randomizer
from voxam.zmachine.routine import Routine
from voxam.zmachine.story import Story
from voxam.zmachine.variables import Variables
from voxam.zmachine.zscii import decode_string, zscii_to_char

# Returning "false" means 0 and "true" means 1 (§6.4.5).
FALSE_VALUE = 0
TRUE_VALUE = 1

# A call to packed address 0 does nothing and returns false (§6.4.3).
NULL_ROUTINE = 0

# je compares its first operand against the others, so one operand
# alone is not permitted (§15 remarks).
JE_MINIMUM_OPERANDS = 2

# Words hold signed values in two's complement: $8000 and up are
# negative (§2.2). Results wrap back into a word; the Standard leaves
# out-of-range results unspecified, and wrapping is the convention
# (§2.3.2).
SIGN_BIT = 0x8000
WORD_RANGE = 0x10000
WORD_MASK = 0xFFFF
WORD_SIZE = 2


def signed(value: int) -> int:
    """Interpret a word as a signed number (§2.2)."""

    return value - WORD_RANGE if value & SIGN_BIT else value


def _quotient(left: int, right: int) -> int:
    """Divide, truncating toward zero as the Z-machine does (§2.2.1).

    Python's // floors toward negative infinity, which disagrees with
    the Z-machine for exactly one sign combination -- so the division
    is done on magnitudes and the sign applied afterward.
    """

    magnitude = abs(left) // abs(right)

    return magnitude if (left < 0) == (right < 0) else -magnitude


def _remainder(left: int, right: int) -> int:
    """Remainder after truncating division: its sign follows the dividend."""

    return left - _quotient(left, right) * right


class Machine:
    """A running Z-Machine (§6.1).

    The state of play: the memory image, the routine call state, and
    the program counter, advanced one instruction at a time.
    """

    def __init__(
        self,
        story: Story,
        output: Callable[[str], None] | None = None,
        input_source: Callable[[], str] | None = None,
    ) -> None:
        """Boot the machine into its §5.4/§5.5 starting state.

        Outside Version 6, execution begins at the header's initial
        address, inside no routine (§5.5). Version 6 instead calls the
        main routine (§5.4).

        Args:
            story: The validated story file to run.
            output: Where printed text goes; standard output when not
                given. A richer §8 screen model will replace this.
            input_source: Where typed commands come from, one line per
                call without its newline; the interactive terminal
                when not given.
        """

        self._story = story
        self._memory = Memory(story)
        self._calls = CallStack()
        self._variables = Variables(self._memory, self._calls)
        self._objects = ObjectTable(self._memory)
        self._rng = Randomizer()
        self._output = output if output is not None else sys.stdout.write
        self._input = input_source if input_source is not None else input
        self._words: Dictionary | None = None
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

    def _store_result(self, variable: int | None, value: int) -> None:
        """Deliver an instruction's result, discarding one with no home."""

        if variable is not None:
            self._variables.write(variable, value)

    def _op_call(self, instruction: Instruction) -> None:
        """Call a routine, or return false for address 0 (§6.4)."""

        values = [self._value(operand) for operand in instruction.operands]
        packed = values[0]

        if packed == NULL_ROUTINE:
            self._store_result(instruction.store_variable, FALSE_VALUE)

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

    def _binary(
        self, instruction: Instruction, operation: Callable[[int, int], int]
    ) -> None:
        """Run a signed two-operand operation, wrapping the result (§2.2)."""

        left = signed(self._value(instruction.operands[0]))
        right = signed(self._value(instruction.operands[1]))

        self._store_result(
            instruction.store_variable, operation(left, right) & WORD_MASK
        )

        self._pc = instruction.next_address

    def _divide(
        self, instruction: Instruction, operation: Callable[[int, int], int]
    ) -> None:
        """Run a signed division-family operation, policing §2.3.1.

        Operands resolve first-to-last before the divisor is examined
        (§4.5.2).
        """

        left = signed(self._value(instruction.operands[0]))
        right = signed(self._value(instruction.operands[1]))

        if right == 0:
            msg = f"division by zero at ${instruction.address:04x} (§2.3.1)"

            raise ZMachineArithmeticError(msg)

        self._store_result(
            instruction.store_variable, operation(left, right) & WORD_MASK
        )

        self._pc = instruction.next_address

    def _op_add(self, instruction: Instruction) -> None:
        """Add, signed (§2.2.1, §15)."""

        self._binary(instruction, operator.add)

    def _op_sub(self, instruction: Instruction) -> None:
        """Subtract, signed (§2.2.1, §15)."""

        self._binary(instruction, operator.sub)

    def _op_mul(self, instruction: Instruction) -> None:
        """Multiply, signed (§2.2.1, §15)."""

        self._binary(instruction, operator.mul)

    def _op_div(self, instruction: Instruction) -> None:
        """Divide, signed, truncating toward zero (§2.2.1, §15)."""

        self._divide(instruction, _quotient)

    def _op_mod(self, instruction: Instruction) -> None:
        """Take the remainder after signed division (§2.2.1, §15)."""

        self._divide(instruction, _remainder)

    def _op_loadw(self, instruction: Instruction) -> None:
        """Store the word at array + 2 * word-index (§15).

        Address arithmetic is unsigned: §2.2.1 lists the signed
        operations, and this is not among them.
        """

        array = self._value(instruction.operands[0])
        index = self._value(instruction.operands[1])

        self._store_result(
            instruction.store_variable,
            self._memory.read_word(array + WORD_SIZE * index),
        )

        self._pc = instruction.next_address

    def _op_loadb(self, instruction: Instruction) -> None:
        """Store the byte at array + byte-index (§15)."""

        array = self._value(instruction.operands[0])
        index = self._value(instruction.operands[1])

        self._store_result(
            instruction.store_variable, self._memory.read_byte(array + index)
        )

        self._pc = instruction.next_address

    def _op_storew(self, instruction: Instruction) -> None:
        """Write a word at array + 2 * word-index (§15)."""

        array = self._value(instruction.operands[0])
        index = self._value(instruction.operands[1])
        value = self._value(instruction.operands[2])

        self._memory.write_word(array + WORD_SIZE * index, value)
        self._pc = instruction.next_address

    def _op_storeb(self, instruction: Instruction) -> None:
        """Write a byte at array + byte-index (§15)."""

        array = self._value(instruction.operands[0])
        index = self._value(instruction.operands[1])
        value = self._value(instruction.operands[2])

        self._memory.write_byte(array + index, value)
        self._pc = instruction.next_address

    def _op_store(self, instruction: Instruction) -> None:
        """Write a value into the referenced variable (§15, §6.3.4).

        This is one of the seven indirect-reference opcodes: a
        reference to variable $00 overwrites the stack top in place.
        """

        reference = self._value(instruction.operands[0])
        value = self._value(instruction.operands[1])

        self._variables.write_in_place(reference, value)
        self._pc = instruction.next_address

    def _op_load(self, instruction: Instruction) -> None:
        """Store the referenced variable's value (§15, §6.3.4)."""

        reference = self._value(instruction.operands[0])

        self._store_result(
            instruction.store_variable, self._variables.read_in_place(reference)
        )

        self._pc = instruction.next_address

    def _step_variable(self, instruction: Instruction, delta: int) -> None:
        """Add a signed delta to the referenced variable (§15, §6.3.4)."""

        reference = self._value(instruction.operands[0])
        value = signed(self._variables.read_in_place(reference))

        self._variables.write_in_place(reference, (value + delta) & WORD_MASK)
        self._pc = instruction.next_address

    def _op_inc(self, instruction: Instruction) -> None:
        """Increment the referenced variable, signed (§15)."""

        self._step_variable(instruction, 1)

    def _op_dec(self, instruction: Instruction) -> None:
        """Decrement the referenced variable, signed (§15)."""

        self._step_variable(instruction, -1)

    def _branch(self, instruction: Instruction, condition: bool) -> None:
        """Act on a branch rider after a test (§4.7).

        The branch applies when the condition matches its sense; the
        sentinel offsets 0 and 1 return from the current routine
        instead of jumping (§4.7.1, §4.7.2).
        """

        branch = instruction.branch

        if branch is None or condition != branch.on_true:
            self._pc = instruction.next_address
        elif branch.returns_false:
            self._return(FALSE_VALUE)
        elif branch.returns_true:
            self._return(TRUE_VALUE)
        else:
            self._pc = branch.target(instruction.next_address)

    def _op_je(self, instruction: Instruction) -> None:
        """Branch if the first operand equals any of the others (§15).

        Equality is indifferent to signedness; je with fewer than two
        operands is not permitted (§15 remarks).
        """

        values = [self._value(operand) for operand in instruction.operands]

        if len(values) < JE_MINIMUM_OPERANDS:
            msg = (
                f"je at ${instruction.address:04x} has {len(values)} "
                f"operand(s), but needs at least two (§15)"
            )

            raise ZMachineInstructionError(msg)

        self._branch(instruction, values[0] in values[1:])

    def _op_jl(self, instruction: Instruction) -> None:
        """Branch if the first operand is less, signed (§2.2.1, §15)."""

        left = signed(self._value(instruction.operands[0]))
        right = signed(self._value(instruction.operands[1]))

        self._branch(instruction, left < right)

    def _op_jg(self, instruction: Instruction) -> None:
        """Branch if the first operand is greater, signed (§2.2.1, §15)."""

        left = signed(self._value(instruction.operands[0]))
        right = signed(self._value(instruction.operands[1]))

        self._branch(instruction, left > right)

    def _op_jz(self, instruction: Instruction) -> None:
        """Branch if the operand is zero (§15)."""

        self._branch(instruction, self._value(instruction.operands[0]) == 0)

    def _op_test(self, instruction: Instruction) -> None:
        """Branch if every flag in the bitmap is set (§15)."""

        bitmap = self._value(instruction.operands[0])
        flags = self._value(instruction.operands[1])

        self._branch(instruction, bitmap & flags == flags)

    def _op_jump(self, instruction: Instruction) -> None:
        """Move execution unconditionally by a signed offset (§15).

        The destination arithmetic matches a branch's (§4.7.2), but
        the offset is an ordinary operand, not branch data.
        """

        offset = signed(self._value(instruction.operands[0]))

        self._pc = instruction.next_address + offset - BRANCH_TARGET_ADJUSTMENT

    def _check_step(self, instruction: Instruction, delta: int) -> bool:
        """Step a referenced variable and compare it (§15, §6.3.4).

        Returns:
            Whether the new signed value passed its comparison: above
            it after incrementing, below it after decrementing.
        """

        reference = self._value(instruction.operands[0])
        comparison = signed(self._value(instruction.operands[1]))
        stepped = (signed(self._variables.read_in_place(reference)) + delta) & WORD_MASK

        self._variables.write_in_place(reference, stepped)

        if delta > 0:
            return signed(stepped) > comparison

        return signed(stepped) < comparison

    def _op_inc_chk(self, instruction: Instruction) -> None:
        """Increment a referenced variable; branch if now greater (§15)."""

        self._branch(instruction, self._check_step(instruction, 1))

    def _op_dec_chk(self, instruction: Instruction) -> None:
        """Decrement a referenced variable; branch if now less (§15)."""

        self._branch(instruction, self._check_step(instruction, -1))

    def _op_and(self, instruction: Instruction) -> None:
        """Bitwise AND, unsigned (§2.2.1, §15)."""

        left = self._value(instruction.operands[0])
        right = self._value(instruction.operands[1])

        self._store_result(instruction.store_variable, left & right)
        self._pc = instruction.next_address

    def _op_or(self, instruction: Instruction) -> None:
        """Bitwise OR, unsigned (§2.2.1, §15)."""

        left = self._value(instruction.operands[0])
        right = self._value(instruction.operands[1])

        self._store_result(instruction.store_variable, left | right)
        self._pc = instruction.next_address

    def _op_not(self, instruction: Instruction) -> None:
        """Bitwise complement, unsigned (§2.2.1, §15)."""

        value = self._value(instruction.operands[0])

        self._store_result(instruction.store_variable, ~value & WORD_MASK)
        self._pc = instruction.next_address

    def _op_check_arg_count(self, instruction: Instruction) -> None:
        """Branch if the numbered argument was supplied (§6.4.4.1, §15)."""

        wanted = self._value(instruction.operands[0])

        self._branch(instruction, wanted <= self._calls.argument_count)

    def _op_verify(self, instruction: Instruction) -> None:
        """Branch if the pristine story's checksum is correct (§15).

        Verification reads the file as shipped, not the mutated
        working image -- which is why the machine keeps its Story.
        """

        self._branch(instruction, self._story.header.verify())

    def _op_piracy(self, instruction: Instruction) -> None:
        """Branch, gullibly, as §15 asks interpreters to do."""

        self._branch(instruction, condition=True)

    def _op_get_parent(self, instruction: Instruction) -> None:
        """Store an object's parent (§15). No branch, unlike its kin."""

        obj = self._value(instruction.operands[0])

        self._store_result(instruction.store_variable, self._objects.parent(obj))
        self._pc = instruction.next_address

    def _op_get_sibling(self, instruction: Instruction) -> None:
        """Store an object's sibling, branching if one exists (§15)."""

        sibling = self._objects.sibling(self._value(instruction.operands[0]))

        self._store_result(instruction.store_variable, sibling)
        self._branch(instruction, sibling != 0)

    def _op_get_child(self, instruction: Instruction) -> None:
        """Store an object's first child, branching if one exists (§15)."""

        child = self._objects.child(self._value(instruction.operands[0]))

        self._store_result(instruction.store_variable, child)
        self._branch(instruction, child != 0)

    def _op_jin(self, instruction: Instruction) -> None:
        """Branch if the first object's parent is the second (§15)."""

        obj = self._value(instruction.operands[0])
        parent = self._value(instruction.operands[1])

        self._branch(instruction, self._objects.parent(obj) == parent)

    def _op_test_attr(self, instruction: Instruction) -> None:
        """Branch if the object's attribute is set (§15)."""

        obj = self._value(instruction.operands[0])
        attribute = self._value(instruction.operands[1])

        self._branch(instruction, self._objects.attribute(obj, attribute))

    def _op_set_attr(self, instruction: Instruction) -> None:
        """Set the object's attribute (§15)."""

        obj = self._value(instruction.operands[0])
        attribute = self._value(instruction.operands[1])

        self._objects.set_attribute(obj, attribute, on=True)
        self._pc = instruction.next_address

    def _op_clear_attr(self, instruction: Instruction) -> None:
        """Clear the object's attribute (§15)."""

        obj = self._value(instruction.operands[0])
        attribute = self._value(instruction.operands[1])

        self._objects.set_attribute(obj, attribute, on=False)
        self._pc = instruction.next_address

    def _op_insert_obj(self, instruction: Instruction) -> None:
        """Move an object to be a destination's first child (§15)."""

        obj = self._value(instruction.operands[0])
        destination = self._value(instruction.operands[1])

        self._objects.insert(obj, destination)
        self._pc = instruction.next_address

    def _op_remove_obj(self, instruction: Instruction) -> None:
        """Detach an object from its parent (§15)."""

        self._objects.remove(self._value(instruction.operands[0]))
        self._pc = instruction.next_address

    def _op_print_obj(self, instruction: Instruction) -> None:
        """Print an object's short name (§15)."""

        obj = self._value(instruction.operands[0])
        text, _ = decode_string(self._memory, self._objects.short_name_address(obj))

        self._output(text)
        self._pc = instruction.next_address

    def _op_put_prop(self, instruction: Instruction) -> None:
        """Write a property the object provides (§15)."""

        obj = self._value(instruction.operands[0])
        number = self._value(instruction.operands[1])
        value = self._value(instruction.operands[2])

        self._objects.put_property(obj, number, value)
        self._pc = instruction.next_address

    def _op_get_prop(self, instruction: Instruction) -> None:
        """Store a property's value, defaulted when absent (§15)."""

        obj = self._value(instruction.operands[0])
        number = self._value(instruction.operands[1])

        self._store_result(
            instruction.store_variable, self._objects.property_value(obj, number)
        )

        self._pc = instruction.next_address

    def _op_get_prop_addr(self, instruction: Instruction) -> None:
        """Store a property's data address, or 0 when absent (§15)."""

        obj = self._value(instruction.operands[0])
        number = self._value(instruction.operands[1])
        found = self._objects.find_property(obj, number)

        self._store_result(instruction.store_variable, 0 if found is None else found[0])

        self._pc = instruction.next_address

    def _op_get_prop_len(self, instruction: Instruction) -> None:
        """Store a property's length from its data address (§15).

        Address 0 must give 0 (§15), pairing with get_prop_addr's
        absent result.
        """

        address = self._value(instruction.operands[0])
        length = 0 if address == 0 else self._objects.property_length_at(address)

        self._store_result(instruction.store_variable, length)
        self._pc = instruction.next_address

    def _op_get_next_prop(self, instruction: Instruction) -> None:
        """Store the next property number the object provides (§15)."""

        obj = self._value(instruction.operands[0])
        number = self._value(instruction.operands[1])

        self._store_result(
            instruction.store_variable, self._objects.next_property(obj, number)
        )

        self._pc = instruction.next_address

    def _op_pull(self, instruction: Instruction) -> None:
        """Pull the stack into a referenced variable (§15, §6.3.4).

        The seventh indirect-reference opcode: pulling into variable
        $00 overwrites the new stack top in place. Version 6's user
        stacks are not yet implemented.
        """

        if instruction.opcode.stores:
            raise ZMachineUnimplementedError("pull", instruction.address)

        reference = self._value(instruction.operands[0])
        value = self._calls.pop()

        self._variables.write_in_place(reference, value)
        self._pc = instruction.next_address

    def _dictionary(self) -> Dictionary:
        """The standard dictionary, read once on first use (§13.1)."""

        if self._words is None:
            self._words = Dictionary(self._memory)

        return self._words

    def _op_sread(self, instruction: Instruction) -> None:
        """Read a typed command into the buffers (§15 read, §13.6).

        Versions 1 to 4 only, and without timed input; the §8.2
        status-line redisplay awaits the screen model.

        Raises:
            ZMachineUnimplementedError: For Version 5's storing aread,
                or a nonzero time and routine pair.
        """

        if instruction.opcode.stores:
            raise ZMachineUnimplementedError("aread", instruction.address)

        values = [self._value(operand) for operand in instruction.operands]

        if any(values[2:]):
            raise ZMachineUnimplementedError("timed sread", instruction.address)

        text_buffer = values[0]
        parse_buffer = values[1]

        # Byte 0 holds n where the buffer is a string array of length
        # n: the typed letters plus the zero terminator fit inside it,
        # so the capacity is n - 1 (§15 read).
        capacity = self._memory.read_byte(text_buffer) - 1
        line = self._input().lower()[:capacity]

        position = text_buffer + 1

        for character in line:
            self._memory.write_byte(position, ord(character))
            position += 1

        self._memory.write_byte(position, 0)

        self._parse(parse_buffer, line)
        self._pc = instruction.next_address

    def _parse(self, parse_buffer: int, line: str) -> None:
        """Write the lexical analysis into the parse buffer (§15 read).

        Each block: the word's dictionary address or 0, its letter
        count, and the position of its first letter in the text
        buffer, whose text starts at byte 1 (§13.6.3).
        """

        dictionary = self._dictionary()
        limit = self._memory.read_byte(parse_buffer)
        words = tokenize(line, dictionary.separators)[:limit]

        self._memory.write_byte(parse_buffer + 1, len(words))

        block = parse_buffer + 2

        for word, offset in words:
            self._memory.write_word(block, dictionary.lookup(word))
            self._memory.write_byte(block + 2, len(word))
            self._memory.write_byte(block + 3, offset + 1)
            block += 4

    def _op_show_status(self, instruction: Instruction) -> None:
        """Redraw nothing, for now (§8.2).

        The status line arrives with the screen model; until then the
        opcode legally does nothing visible.
        """

        self._pc = instruction.next_address

    def _op_random(self, instruction: Instruction) -> None:
        """Roll, seed, or re-randomize the generator (§2.4, §15).

        A positive range rolls; a negative range seeds the predictable
        state with its magnitude and yields 0; zero re-randomizes and
        yields 0.
        """

        value = signed(self._value(instruction.operands[0]))

        if value > 0:
            result = self._rng.roll(value)
        elif value < 0:
            self._rng.seed(-value)
            result = 0
        else:
            self._rng.randomize()
            result = 0

        self._store_result(instruction.store_variable, result)
        self._pc = instruction.next_address

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
    "add": Machine._op_add,
    "and": Machine._op_and,
    "aread": Machine._op_sread,
    "call": Machine._op_call,
    "check_arg_count": Machine._op_check_arg_count,
    "clear_attr": Machine._op_clear_attr,
    "call_1n": Machine._op_call,
    "call_1s": Machine._op_call,
    "call_2n": Machine._op_call,
    "call_2s": Machine._op_call,
    "call_vn": Machine._op_call,
    "call_vs": Machine._op_call,
    "dec": Machine._op_dec,
    "dec_chk": Machine._op_dec_chk,
    "div": Machine._op_div,
    "get_child": Machine._op_get_child,
    "get_next_prop": Machine._op_get_next_prop,
    "get_parent": Machine._op_get_parent,
    "get_prop": Machine._op_get_prop,
    "get_prop_addr": Machine._op_get_prop_addr,
    "get_prop_len": Machine._op_get_prop_len,
    "get_sibling": Machine._op_get_sibling,
    "inc": Machine._op_inc,
    "inc_chk": Machine._op_inc_chk,
    "insert_obj": Machine._op_insert_obj,
    "je": Machine._op_je,
    "jin": Machine._op_jin,
    "jg": Machine._op_jg,
    "jl": Machine._op_jl,
    "jump": Machine._op_jump,
    "jz": Machine._op_jz,
    "load": Machine._op_load,
    "loadb": Machine._op_loadb,
    "loadw": Machine._op_loadw,
    "mod": Machine._op_mod,
    "mul": Machine._op_mul,
    "new_line": Machine._op_new_line,
    "not": Machine._op_not,
    "or": Machine._op_or,
    "piracy": Machine._op_piracy,
    "print": Machine._op_print,
    "print_addr": Machine._op_print_addr,
    "print_char": Machine._op_print_char,
    "print_num": Machine._op_print_num,
    "print_obj": Machine._op_print_obj,
    "print_paddr": Machine._op_print_paddr,
    "print_ret": Machine._op_print_ret,
    "pull": Machine._op_pull,
    "push": Machine._op_push,
    "put_prop": Machine._op_put_prop,
    "remove_obj": Machine._op_remove_obj,
    "set_attr": Machine._op_set_attr,
    "show_status": Machine._op_show_status,
    "sread": Machine._op_sread,
    "quit": Machine._op_quit,
    "random": Machine._op_random,
    "ret": Machine._op_ret,
    "ret_popped": Machine._op_ret_popped,
    "rfalse": Machine._op_rfalse,
    "rtrue": Machine._op_rtrue,
    "store": Machine._op_store,
    "storeb": Machine._op_storeb,
    "storew": Machine._op_storew,
    "sub": Machine._op_sub,
    "test": Machine._op_test,
    "test_attr": Machine._op_test_attr,
    "verify": Machine._op_verify,
}
