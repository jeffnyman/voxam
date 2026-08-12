"""The machine loop: fetch, decode, dispatch (§6).

A Machine binds everything built so far -- the memory image, the call
state, the variable façade -- to a program counter, and executes one
instruction at a time. Opcodes it does not yet implement raise
ZMachineUnimplementedError, so pointing Voxam at any story reveals
the frontier of what remains to build.
"""

import operator
from collections.abc import Callable

from voxam.errors import (
    ZMachineArithmeticError,
    ZMachineInstructionError,
    ZMachineMemoryError,
    ZMachineQuetzalError,
    ZMachineUnimplementedError,
)
from voxam.frontend import Frontend, PlainFrontend, Status
from voxam.saves import SaveSlot
from voxam.zmachine.dictionary import Dictionary, tokenize
from voxam.zmachine.frames import CallStack
from voxam.zmachine.header import (
    FLAGS_2,
    PACKED_PC_VERSION,
    SCREEN_FIELDS_VERSION,
    STATUS_FLAGS_VERSION,
)
from voxam.zmachine.instruction import Instruction, Operand, OperandType
from voxam.zmachine.memory import Memory
from voxam.zmachine.objects import ObjectTable
from voxam.zmachine.packed import routine_address, string_address
from voxam.zmachine.quetzal import read as read_quetzal
from voxam.zmachine.quetzal import write as write_quetzal
from voxam.zmachine.riders import (
    BRANCH_TARGET_ADJUSTMENT,
    Branch,
    read_branch,
    read_store_variable,
)
from voxam.zmachine.rng import Randomizer
from voxam.zmachine.routine import Routine
from voxam.zmachine.snapshot import FrameSnapshot, Snapshot
from voxam.zmachine.story import Story
from voxam.zmachine.variables import FIRST_GLOBAL, Variables
from voxam.zmachine.zscii import ZSCII_NEWLINE, decode_string, zscii_to_char

# Returning "false" means 0 and "true" means 1 (§6.4.5).
FALSE_VALUE = 0
TRUE_VALUE = 1

# Through Version 3, save and restore branch; from Version 4 they
# store instead (§14, §15). A save's store byte answers 1 on success,
# 0 on failure -- and 2 when the game is picking up from a restore,
# which resumes at that very byte (§15 save, Quetzal §5.8.2).
BRANCHING_SAVE_FINAL_VERSION = 3
RESTORED_VALUE = 2

# A call to packed address 0 does nothing and returns false (§6.4.3).
NULL_ROUTINE = 0

# je compares its first operand against the others, so one operand
# alone is not permitted (§15 remarks).
JE_MINIMUM_OPERANDS = 2

# §11.1.3 asks an interpreter to identify itself in Version 4+
# headers as one of the classic machines; 6, the IBM PC, is the
# conventional stand-in for "some modern computer", and the revision
# letter is Voxam's own.
INTERPRETER_PLATFORM = 6
INTERPRETER_REVISION = ord("V")

# The Standard revision Voxam obeys, written at $32/$33 (§11.1.5).
# 1.0 until the 1.1 additions -- print_unicode and kin -- all land.
STANDARD_MAJOR = 1
STANDARD_MINOR = 0

# read_char's first operand is always 1, the keyboard: no other
# input device was ever defined (§15 read_char).
KEYBOARD_DEVICE = 1

# From Version 5, read's text buffer changes shape: byte 0 is the
# whole capacity, the typed count lands in byte 1, and the letters
# run from byte 2 with no terminator -- where Versions 1 to 4 put a
# zero-terminated string from byte 1 (§15 read). §15 also asks for a
# loud halt when a buffer is too small to be real: a text buffer
# under 3 bytes or a parse buffer under 6 almost certainly means a
# previous array overran them.
COUNTED_TEXT_VERSION = 5
MINIMUM_TEXT_CAPACITY = {False: 2, True: 1}
MINIMUM_PARSE_WORDS = 1

# sound_effect's first two numbers are the interpreter's own bleeps;
# from 3 upward they name sampled sounds, which need Blorb-era
# machinery (§9). A bare sound_effect means bleep 1.
HIGH_BLEEP = 1
FIRST_SAMPLED_SOUND = 3

# The four output streams (§7.1): the screen, the transcript, memory
# redirection into a table, and the player's command record. Positive
# selects, negative deselects, and stream 3 may nest 16 deep at most
# -- one deeper is a fault the interpreter must halt on (§7.1.2.1.1).
SCREEN_STREAM = 1
TRANSCRIPT_STREAM = 2
MEMORY_STREAM = 3
COMMANDS_STREAM = 4
REDIRECTION_LIMIT = 16

# A memory-redirected table opens with a word for the character
# count, data following from its third byte (§7.1.2.1). Selecting
# stream 3 takes two operands: the stream and the table.
REDIRECTION_DATA_OFFSET = 2
REDIRECTION_OPERANDS = 2

# print_table's optional third and fourth operands: the height of
# the rectangle, defaulting to one row, and the table characters
# skipped between rows (§15 print_table).
PRINT_TABLE_HEIGHT_OPERAND = 2
PRINT_TABLE_SKIP_OPERAND = 3

# tokenise's optional third and fourth operands: a custom dictionary
# to consult, and the flag that leaves unrecognised words' slots
# untouched (§15 tokenise).
TOKENISE_DICTIONARY_OPERAND = 2
TOKENISE_FLAG_OPERAND = 3

# scan_table's optional form byte is its fourth operand and defaults
# to $82: compare words (the top bit) over two-byte fields (the
# rest), examining the first word or byte of each field (§15
# scan_table).
SCAN_FORM_OPERAND = 3
DEFAULT_SCAN_FORM = 0x82
SCAN_WORD_BIT = 0x80
SCAN_FIELD_MASK = 0x7F

# The shift opcodes take places from -15 to +15; beyond that the
# Standard declares behaviour undefined (§15 log_shift, art_shift),
# and undefined behaviour halts loudly here rather than guessing.
SHIFT_LIMIT = 15

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
        frontend: Frontend | None = None,
        input_source: Callable[[], str] | None = None,
        seed: int | None = None,
        saves: SaveSlot | None = None,
    ) -> None:
        """Boot the machine into its §5.4/§5.5 starting state.

        Outside Version 6, execution begins at the header's initial
        address, inside no routine (§5.5). Version 6 instead calls the
        main routine (§5.4). Before the story wakes, the header is
        stamped with the frontend's honest capabilities -- Version 3's
        status and splitting bits, or Version 4's interpreter
        identity, screen size, and typography -- so the game can
        adapt to them (§11.1).

        Args:
            story: The validated story file to run.
            frontend: Where text and status go; a plain stream to
                standard output when not given.
            input_source: Where typed commands come from, one line per
                call without its newline; the interactive terminal
                when not given.
            seed: A session seed making the dice reproducible; None
                means true entropy.
            saves: Where saved games are kept; None means every save
                and restore reports failure, which is an answer the
                story already knows how to hear (§15).
        """

        self._story = story
        self._memory = Memory(story)
        self._calls = CallStack()
        self._variables = Variables(self._memory, self._calls)
        self._objects = ObjectTable(self._memory)
        self._rng = Randomizer(seed)
        self._frontend = frontend if frontend is not None else PlainFrontend()
        self._output = self._frontend.write
        self._input = input_source if input_source is not None else input
        self._words: Dictionary | None = None
        self._running = True
        self._screen_selected = True
        self._redirections: list[tuple[int, list[str]]] = []
        self._saves = saves
        self._undo: Snapshot | None = None

        self._declare_capabilities()
        self._start_execution()

    def _start_execution(self) -> None:
        """Point the machine at its first instruction (§5.4, §5.5).

        Outside Version 6, execution begins at the header's initial
        address, inside no routine (§5.5); Version 6 instead calls
        the main routine (§5.4). Boot does this once, and restart
        does it again over freshly reloaded memory (§6.1.3).
        """

        header = self._memory.header

        if header.version == PACKED_PC_VERSION:
            address = routine_address(header, header.main_routine_packed_address)
            routine = Routine.parse(self._memory, address)

            self._calls.call(routine, (), return_address=0, store_variable=None)

            self._pc = routine.first_instruction
        else:
            self._pc = header.initial_program_counter

    def _declare_capabilities(self) -> None:
        """Stamp the frontend's honest capabilities into the header.

        Version 3's Flags 1 carries the status-line and screen-split
        bits; from Version 4 the header instead takes the interpreter
        identity, screen size, and typography (§11.1). These are the
        fields marked Rst in §11's table: set at boot, and reset
        after every restore and restart, because the state being
        restored may have been saved under some other interpreter
        (§6.1.2.2).
        """

        header = self._memory.header

        header.declare_standard_revision(STANDARD_MAJOR, STANDARD_MINOR)

        if header.version == STATUS_FLAGS_VERSION:
            header.declare_status_line(available=self._frontend.has_status_line)
            header.declare_screen_splitting(
                available=self._frontend.has_screen_splitting
            )
        elif header.version >= SCREEN_FIELDS_VERSION:
            header.introduce_interpreter(INTERPRETER_PLATFORM, INTERPRETER_REVISION)
            header.declare_screen_size(
                lines=self._frontend.screen_lines,
                columns=self._frontend.screen_columns,
            )
            header.declare_presentation(
                bold=self._frontend.has_bold,
                italic=self._frontend.has_italic,
                fixed_pitch=self._frontend.has_fixed_pitch,
                timed_input=self._frontend.has_timed_input,
            )

    def snapshot(self) -> Snapshot:
        """Capture the entire state of play (§6.1, §6.1.1).

        Returns:
            The four §6.1 ingredients -- dynamic memory, the stack,
            the PC, and the routine call state -- frozen in the
            interpreter's private memory. The capture is inert:
            running the machine afterward cannot alter it.
        """

        return Snapshot(
            dynamic_memory=self._memory.dynamic_snapshot(),
            pc=self._pc,
            frames=self._calls.snapshot(),
        )

    def restore(self, snapshot: Snapshot) -> None:
        """Write a captured state of play back whole (§6.1.2).

        Everything is restored except 'Flags 2', whose bits belong to
        the player's session rather than the story's state (§6.1.2),
        and the Rst-marked header fields are then re-stamped, since
        the capture may not have been taken under this interpreter or
        this frontend (§6.1.2.2).

        Args:
            snapshot: A state of play captured from this same story.

        Raises:
            ZMachineMemoryError: If the snapshot's dynamic memory
                does not match this story's shape, meaning it was
                captured from a different game (§6.1.2.1).
            ZMachineStackError: If the snapshot's call chain is not
                one an honest capture could hold.
        """

        flags2 = self._memory.read_word(FLAGS_2)

        self._memory.restore_dynamic(snapshot.dynamic_memory)
        self._memory.write_word(FLAGS_2, flags2)
        self._calls.restore(snapshot.frames)
        self._pc = snapshot.pc
        self._declare_capabilities()

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

    def _print(self, text: str) -> None:
        """Send story text down the selected output streams (§7).

        While stream 3 is selected, text goes into the newest memory
        table and nowhere else -- not even other stream 3 tables
        (§7.1.2.2). Otherwise it reaches the screen, unless the game
        deselected that too, in which case it vanishes as asked.
        """

        if self._redirections:
            self._redirections[-1][1].append(text)
        elif self._screen_selected:
            self._output(text)

    def _op_log_shift(self, instruction: Instruction) -> None:
        """Shift a word logically: zeros fill from either end (§15)."""

        self._shift(instruction, arithmetic=False)

    def _op_art_shift(self, instruction: Instruction) -> None:
        """Shift a word arithmetically: right shifts keep the sign (§15)."""

        self._shift(instruction, arithmetic=True)

    def _shift(self, instruction: Instruction, *, arithmetic: bool) -> None:
        """Shift left for positive places, right for negative (§15).

        The two opcodes differ only rightward: log_shift zeroes the
        sign in, art_shift preserves it -- which Python's shift on a
        signed value does natively.

        Raises:
            ZMachineArithmeticError: For places beyond -15 to +15,
                where the Standard declares behaviour undefined.
        """

        number = self._value(instruction.operands[0])
        places = signed(self._value(instruction.operands[1]))

        if abs(places) > SHIFT_LIMIT:
            msg = (
                f"cannot shift by {places}: places runs from -15 to 15, "
                f"beyond which behaviour is undefined (§15)"
            )

            raise ZMachineArithmeticError(msg)

        if places >= 0:
            result = (number << places) & WORD_MASK
        elif arithmetic:
            result = (signed(number) >> -places) & WORD_MASK
        else:
            result = number >> -places

        self._store_result(instruction.store_variable, result)

        self._pc = instruction.next_address

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

        The branch applies when the condition matches its sense
        (§4.7.1, §4.7.2).
        """

        branch = instruction.branch

        if branch is None or condition != branch.on_true:
            self._pc = instruction.next_address
        else:
            self._take_branch(branch, instruction.next_address)

    def _apply_branch(self, branch: Branch, after: int, condition: bool) -> None:
        """Apply a decoded branch to a tested condition (§4.7).

        The rider-at-hand twin of _branch, for resuming a restore at
        a save's branch data, where there is no Instruction to hold
        the rider.
        """

        if condition != branch.on_true:
            self._pc = after
        else:
            self._take_branch(branch, after)

    def _take_branch(self, branch: Branch, after: int) -> None:
        """Follow a branch that applies: jump, or return (§4.7.1)."""

        if branch.returns_false:
            self._return(FALSE_VALUE)
        elif branch.returns_true:
            self._return(TRUE_VALUE)
        else:
            self._pc = branch.target(after)

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

    def _op_save(self, instruction: Instruction) -> None:
        """Save the state of play as a Quetzal file (§15 save, §6.1.1).

        The snapshot's PC is the address of this instruction's own
        rider -- the branch data through Version 3, the store byte
        from Version 4 (Quetzal §5.8) -- so a restore resumes right
        there and answers through the same rider. Success branches or
        stores 1; failure falls through or stores 0.
        """

        self._refuse_table_form(instruction)

        snapshot = Snapshot(
            dynamic_memory=self._memory.dynamic_snapshot(),
            pc=instruction.operands_end,
            frames=self._calls.snapshot(),
        )
        data = write_quetzal(snapshot, self._story)
        success = self._saves is not None and self._saves.write(data)

        if self._memory.header.version <= BRANCHING_SAVE_FINAL_VERSION:
            self._branch(instruction, success)
        else:
            self._store_result(instruction.store_variable, int(success))

            self._pc = instruction.next_address

    def _op_restore(self, instruction: Instruction) -> None:
        """Restore a saved state of play (§15 restore, §6.1.2).

        On success the machine does not continue here at all: the
        restored state resumes at the save's rider, taking its branch
        or storing 2 there (§15 save, Quetzal §5.8). Failure is a
        result the story hears -- no branch through Version 3, a
        stored 0 from Version 4 -- whether the slot was empty, the
        bytes were not a save, or the save names another game.
        """

        self._refuse_table_form(instruction)

        snapshot = None
        data = self._saves.read() if self._saves is not None else None

        if data is not None:
            try:
                snapshot = read_quetzal(data, self._story)
            except ZMachineQuetzalError:
                snapshot = None

        if snapshot is None:
            if self._memory.header.version > BRANCHING_SAVE_FINAL_VERSION:
                self._store_result(instruction.store_variable, FALSE_VALUE)

            self._pc = instruction.next_address

            return

        self.restore(snapshot)
        self._resume_from_save(snapshot.pc)

    def _op_save_undo(self, instruction: Instruction) -> None:
        """Save the state of play into the interpreter's hand (§15).

        Like save into memory instead of a file, called once per turn
        by Inform-era games to power UNDO -- which is why it is a
        plain capture and nothing slower. The held snapshot is not
        part of the state of play (§6.1.1.2): it lives outside the
        memory map, so a restore cannot resurrect it and an undo
        cannot be undone into growing forever. The PC captured is
        this instruction's own store byte, exactly as save records
        its rider (Quetzal §5.8.2).
        """

        self._undo = Snapshot(
            dynamic_memory=self._memory.dynamic_snapshot(),
            pc=instruction.operands_end,
            frames=self._calls.snapshot(),
        )

        self._store_result(instruction.store_variable, TRUE_VALUE)

        self._pc = instruction.next_address

    def _op_restore_undo(self, instruction: Instruction) -> None:
        """Restore the state save_undo holds (§15).

        On success the machine resumes at the save_undo's store byte
        and answers 2 there, just as a file restore answers its save
        (§15 save). With nothing in hand -- which a game may not
        legally rely on (§15 restore_undo) -- it stores 0 and moves
        on, the quiet option the spec offers. The held snapshot
        survives the restore: a single undo slot answers repeated
        UNDOs with the same turn, as classic interpreters did.
        """

        if self._undo is None:
            self._store_result(instruction.store_variable, FALSE_VALUE)

            self._pc = instruction.next_address

            return

        self.restore(self._undo)
        self._resume_from_save(self._undo.pc)

    def _resume_from_save(self, pc: int) -> None:
        """Pick up execution at the rider of the save that made us.

        A restored PC points at the saving instruction's rider
        (Quetzal §5.8): through Version 3 the branch data, taken as
        the successful save it was; from Version 4 the store byte,
        answered with 2 so the story knows it is being restored
        rather than saved (§15 save).
        """

        if self._memory.header.version <= BRANCHING_SAVE_FINAL_VERSION:
            branch, after = read_branch(self._memory, pc)

            self._apply_branch(branch, after, condition=True)
        else:
            variable, after = read_store_variable(self._memory, pc)

            self._variables.write(variable, RESTORED_VALUE)

            self._pc = after

    def _refuse_table_form(self, instruction: Instruction) -> None:
        """Halt on the Version 5 table-taking save and restore forms.

        From Version 5 the EXT opcodes may take operands naming a
        table of bytes to save instead of the state of play (§15).
        That is auxiliary-file machinery Voxam does not have yet, and
        pretending the operands were not there would quietly save the
        wrong thing.
        """

        if instruction.operands:
            raise ZMachineUnimplementedError(
                f"{instruction.opcode.name} with table operands",
                instruction.address,
            )

    def _op_restart(self, _instruction: Instruction) -> None:
        """Start the story over from the pristine file (§6.1.3).

        The entire state reloads from the original story and the
        stack empties -- but 'Flags 2' survives, the Rst header
        fields are re-stamped, and the interpreter's own bookkeeping
        (stream selection, memory redirection) returns to its boot
        state.
        """

        flags2 = self._memory.read_word(FLAGS_2)
        pristine = self._story.data[: self._story.header.static_memory_base]

        self._memory.restore_dynamic(pristine)
        self._memory.write_word(FLAGS_2, flags2)
        self._calls.restore(
            (
                FrameSnapshot(
                    return_address=0,
                    store_variable=None,
                    locals=(),
                    argument_count=0,
                    stack=(),
                ),
            )
        )
        self._redirections.clear()

        self._screen_selected = True

        self._declare_capabilities()
        self._start_execution()

    # Object 0 means "nothing" (§12.3), and the tree reads answer
    # questions about it in kind: nothing's parent, sibling, and
    # child are nothing. Formally there is no such object -- but the
    # early Inform libraries walk the tree from object 0 on routine
    # paths (Magic Toyshop, Library 5/12, does it before the first
    # command), so a strict halt bricks a generation of shipped
    # games at their title screens. Reads relax; writes and every
    # other object opcode stay loud until a real game earns more.

    def _op_get_parent(self, instruction: Instruction) -> None:
        """Store an object's parent (§15). No branch, unlike its kin."""

        obj = self._value(instruction.operands[0])
        parent = self._objects.parent(obj) if obj else 0

        self._store_result(instruction.store_variable, parent)
        self._pc = instruction.next_address

    def _op_get_sibling(self, instruction: Instruction) -> None:
        """Store an object's sibling, branching if one exists (§15)."""

        obj = self._value(instruction.operands[0])
        sibling = self._objects.sibling(obj) if obj else 0

        self._store_result(instruction.store_variable, sibling)
        self._branch(instruction, sibling != 0)

    def _op_get_child(self, instruction: Instruction) -> None:
        """Store an object's first child, branching if one exists (§15)."""

        obj = self._value(instruction.operands[0])
        child = self._objects.child(obj) if obj else 0

        self._store_result(instruction.store_variable, child)
        self._branch(instruction, child != 0)

    def _op_jin(self, instruction: Instruction) -> None:
        """Branch if the first object's parent is the second (§15)."""

        obj = self._value(instruction.operands[0])
        parent = self._value(instruction.operands[1])

        self._branch(instruction, self._objects.parent(obj) == parent)

    def _op_test_attr(self, instruction: Instruction) -> None:
        """Branch if the object's attribute is set (§15).

        Object 0 has no attributes set, because there is nothing to
        set them on (§12.3): another read the early Inform libraries
        make in earnest -- Magic Toyshop tests attribute 3 of object
        0 while emptying a box -- so it answers false rather than
        halting. set_attr and clear_attr on object 0 stay loud.
        """

        obj = self._value(instruction.operands[0])
        attribute = self._value(instruction.operands[1])
        held = bool(obj) and self._objects.attribute(obj, attribute)

        self._branch(instruction, held)

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

        self._print(text)
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

        One opcode, two eras: through Version 4 the text buffer takes
        a zero-terminated string from byte 1; from Version 5 the
        typed count lands in byte 1 with the letters from byte 2, the
        parse buffer may be zero to skip lexing, and the instruction
        stores its terminating character -- 13, the return key, since
        input here always ends in a newline (§15 read).

        A time and routine pair asks for interrupts during real
        waiting (§15); under the instant typist the line arrives
        before any interval elapses, so the pair is accepted and
        never consulted -- see read_char for the full argument.

        Raises:
            ZMachineUnimplementedError: For leftover characters
                preloaded in the buffer, which only an interrupted
                timed read can legitimately produce -- and the
                instant typist is never interrupted.
            ZMachineMemoryError: For a buffer too small to be real,
                which §15 asks interpreters to halt on.
        """

        values = [self._value(operand) for operand in instruction.operands]

        # In Versions 1 to 3 the status line is redisplayed before the
        # player types (§8.2, §15 read) -- when there is one to show.
        if (
            self._memory.header.version <= STATUS_FLAGS_VERSION
            and self._frontend.has_status_line
        ):
            self._frontend.show_status(self._status())

        text_buffer = values[0]
        parse_buffer = values[1]
        counted = self._memory.header.version >= COUNTED_TEXT_VERSION

        capacity = self._memory.read_byte(text_buffer)

        if capacity < MINIMUM_TEXT_CAPACITY[counted]:
            msg = (
                f"the text buffer at ${text_buffer:04x} claims a capacity "
                f"of {capacity}: almost certainly overrun by a previous "
                f"array (§15 read)"
            )

            raise ZMachineMemoryError(msg)

        if counted:
            # A positive count already in byte 1 means characters
            # left over from an interrupted timed read (§15 read) --
            # machinery that does not exist here yet, so honoring the
            # count would type stale bytes nobody entered.
            if self._memory.read_byte(text_buffer + 1):
                raise ZMachineUnimplementedError(
                    "read with leftover input", instruction.address
                )

            line = self._input().lower()[:capacity]

            self._memory.write_byte(text_buffer + 1, len(line))
            self._write_text(text_buffer + 2, line, terminate=False)
        else:
            # Byte 0 holds n where the buffer is a string array of
            # length n: the typed letters plus the zero terminator
            # fit inside it, so the capacity is n - 1 (§15 read).
            line = self._input().lower()[: capacity - 1]

            self._write_text(text_buffer + 1, line, terminate=True)

        # From Version 5 a zero parse buffer skips lexing (§15 read).
        if parse_buffer or not counted:
            self._parse(parse_buffer, line, first_letter=2 if counted else 1)

        if instruction.opcode.stores:
            self._store_result(instruction.store_variable, ZSCII_NEWLINE)

        self._pc = instruction.next_address

    def _write_text(self, position: int, line: str, *, terminate: bool) -> None:
        """Lay typed text into the buffer, zero-terminated or not."""

        for character in line:
            self._memory.write_byte(position, ord(character))
            position += 1

        if terminate:
            self._memory.write_byte(position, 0)

    def _parse(
        self,
        parse_buffer: int,
        line: str,
        first_letter: int,
        dictionary: Dictionary | None = None,
        *,
        keep_unrecognized: bool = False,
    ) -> None:
        """Write the lexical analysis into the parse buffer (§15 read).

        Each block: the word's dictionary address or 0, its letter
        count, and the position of its first letter in the text
        buffer -- whose text starts at byte 1 through Version 4 and
        byte 2 from Version 5 (§13.6.3, §15 read). With
        keep_unrecognized, an absent word's block is left untouched
        instead of zeroed, so successive tokenise passes against
        different dictionaries each fill in more slots (§15
        tokenise).

        Raises:
            ZMachineMemoryError: For a parse buffer too small to hold
                a single word, which §15 asks interpreters to halt
                on.
        """

        if dictionary is None:
            dictionary = self._dictionary()

        limit = self._memory.read_byte(parse_buffer)

        if limit < MINIMUM_PARSE_WORDS:
            msg = (
                f"the parse buffer at ${parse_buffer:04x} claims room for "
                f"{limit} words: almost certainly overrun by a previous "
                f"array (§15 read)"
            )

            raise ZMachineMemoryError(msg)

        words = tokenize(line, dictionary.separators)[:limit]

        self._memory.write_byte(parse_buffer + 1, len(words))

        block = parse_buffer + 2

        for word, offset in words:
            address = dictionary.lookup(word)

            if address or not keep_unrecognized:
                self._memory.write_word(block, address)
                self._memory.write_byte(block + 2, len(word))
                self._memory.write_byte(block + 3, offset + first_letter)

            block += 4

    def _op_print_table(self, instruction: Instruction) -> None:
        """Print a rectangle of ZSCII rows from a table (§15).

        Each row is width table bytes, with skip bytes passed over
        between rows -- a window onto a larger character map. Under
        the plain screen model each row after the first begins a
        fresh line; the cursor-true rectangle, right and down from
        wherever the cursor stands, belongs to a richer frontend.
        (§15 also declares heights past 1 undefined in the lower
        window; stacked lines are this interpreter's answer.)
        """

        values = [self._value(operand) for operand in instruction.operands]

        table = values[0]
        width = values[1]
        height = (
            values[PRINT_TABLE_HEIGHT_OPERAND]
            if len(values) > PRINT_TABLE_HEIGHT_OPERAND
            else 1
        )
        skip = (
            values[PRINT_TABLE_SKIP_OPERAND]
            if len(values) > PRINT_TABLE_SKIP_OPERAND
            else 0
        )
        position = table

        for row in range(height):
            if row:
                self._print("\n")

            self._print(
                "".join(
                    zscii_to_char(self._memory.read_byte(position + offset))
                    for offset in range(width)
                )
            )

            position += width + skip

        self._pc = instruction.next_address

    def _op_copy_table(self, instruction: Instruction) -> None:
        """Copy or zero a run of table bytes (§15 copy_table).

        A zero second table means "zero size bytes of first". A
        positive size copies without corruption however the tables
        overlap -- the source is read whole before a byte lands. A
        negative size forces a forward byte-at-a-time copy even
        through an overlap: Beyond Zork aims that smear at an array
        to fill it with spaces.
        """

        values = [self._value(operand) for operand in instruction.operands]

        first = values[0]
        second = values[1]
        size = signed(values[2])

        if second == 0:
            # The zeroing sentence of §15 says only "size bytes";
            # reading a negative size as its magnitude is the
            # convention.
            for offset in range(abs(size)):
                self._memory.write_byte(first + offset, 0)
        elif size < 0:
            for offset in range(-size):
                self._memory.write_byte(
                    second + offset, self._memory.read_byte(first + offset)
                )
        else:
            data = [self._memory.read_byte(first + offset) for offset in range(size)]

            for offset, value in enumerate(data):
                self._memory.write_byte(second + offset, value)

        self._pc = instruction.next_address

    def _op_tokenise(self, instruction: Instruction) -> None:
        """Lexically analyse text already in the buffer (§15 tokenise).

        The lexing half of read as its own opcode, which Inform-era
        parsers run repeatedly over one typed line. A nonzero third
        operand names a custom dictionary to consult instead of the
        game's own -- possibly unsorted (§13.5) -- and a nonzero
        fourth leaves unrecognised words' slots untouched, so passes
        accumulate.
        """

        values = [self._value(operand) for operand in instruction.operands]

        text_buffer = values[0]
        parse_buffer = values[1]
        supplied = values[TOKENISE_DICTIONARY_OPERAND:]
        base = supplied[0] if supplied and supplied[0] else None
        keep = len(values) > TOKENISE_FLAG_OPERAND and bool(
            values[TOKENISE_FLAG_OPERAND]
        )

        # tokenise exists from Version 5, so the buffer is always the
        # counted layout: length in byte 1, text from byte 2 (§15
        # read).
        count = self._memory.read_byte(text_buffer + 1)
        line = "".join(
            chr(self._memory.read_byte(text_buffer + 2 + offset))
            for offset in range(count)
        )
        dictionary = Dictionary(self._memory, base) if base is not None else None

        self._parse(
            parse_buffer,
            line,
            first_letter=2,
            dictionary=dictionary,
            keep_unrecognized=keep,
        )

        self._pc = instruction.next_address

    def _status(self) -> Status:
        """Assemble what the status line shows (§8.2).

        The location is the short name of the object in the first
        global variable; the numbers are the second and third globals,
        read as score and turns or as hours and minutes according to
        the header's status-line type (§8.2.2, §8.2.3).
        """

        location = self._variables.read(FIRST_GLOBAL)
        text, _ = decode_string(
            self._memory, self._objects.short_name_address(location)
        )

        return Status(
            location=text,
            score=signed(self._variables.read(FIRST_GLOBAL + 1)),
            turns=self._variables.read(FIRST_GLOBAL + 2),
            time_game=self._memory.header.time_game,
        )

    def _op_set_text_style(self, instruction: Instruction) -> None:
        """Hand the requested type style to the frontend (§8.7).

        Each frontend renders the styles it claimed in the header
        and ignores the rest, which §8.7 permits.
        """

        self._frontend.set_style(self._value(instruction.operands[0]))
        self._pc = instruction.next_address

    def _op_erase_window(self, instruction: Instruction) -> None:
        """Hand a window erasure to the frontend (§8.7).

        The operand is signed: -1 unsplits and clears everything,
        -2 clears everything without unsplitting.
        """

        self._frontend.erase_window(signed(self._value(instruction.operands[0])))
        self._pc = instruction.next_address

    def _op_buffer_mode(self, instruction: Instruction) -> None:
        """Hand the word-wrap buffering toggle to the frontend (§8.7)."""

        self._frontend.set_buffering(bool(self._value(instruction.operands[0])))
        self._pc = instruction.next_address

    def _op_split_window(self, instruction: Instruction) -> None:
        """Hand the upper window's new height to the frontend (§8.7.2)."""

        self._frontend.split_window(self._value(instruction.operands[0]))
        self._pc = instruction.next_address

    def _op_set_window(self, instruction: Instruction) -> None:
        """Hand the window selection to the frontend (§8.7.2)."""

        self._frontend.set_window(self._value(instruction.operands[0]))
        self._pc = instruction.next_address

    def _op_set_cursor(self, instruction: Instruction) -> None:
        """Hand an upper-window cursor move to the frontend (§8.7.2)."""

        line = self._value(instruction.operands[0])
        column = self._value(instruction.operands[1])

        self._frontend.set_cursor(line, column)
        self._pc = instruction.next_address

    def _op_output_stream(self, instruction: Instruction) -> None:
        """Select or deselect an output stream (§7, §15).

        A positive operand selects, its negative deselects, and 0
        does nothing. Stream 3 redirects text into a memory table --
        a word for the count, then the ZSCII characters -- and nests
        up to 16 deep; each deselection closes the newest table,
        writing its count.

        Raises:
            ZMachineInstructionError: On a 17th nested redirection
                (§7.1.2.1.1), a stream 3 selection with no table, a
                deselection of a stream 3 that is not on, or a
                stream number §7 does not define.
            ZMachineUnimplementedError: For the transcript and
                command-record streams.
        """

        values = [self._value(operand) for operand in instruction.operands]
        stream = signed(values[0])

        if stream == 0:
            pass
        elif stream == SCREEN_STREAM:
            self._screen_selected = True
        elif stream == -SCREEN_STREAM:
            self._screen_selected = False
        elif stream == MEMORY_STREAM:
            self._redirect_into(instruction, values)
        elif stream == -MEMORY_STREAM:
            self._end_redirection(instruction)
        elif abs(stream) in (TRANSCRIPT_STREAM, COMMANDS_STREAM):
            raise ZMachineUnimplementedError(
                f"output stream {abs(stream)}", instruction.address
            )
        else:
            msg = (
                f"output_stream at ${instruction.address:04x} names "
                f"stream {stream}, but §7.1 defines only 1 to 4"
            )

            raise ZMachineInstructionError(msg)

        self._pc = instruction.next_address

    def _redirect_into(self, instruction: Instruction, values: list[int]) -> None:
        """Open a stream 3 redirection into a table (§7.1.2.1)."""

        if len(values) < REDIRECTION_OPERANDS:
            msg = (
                f"output_stream 3 at ${instruction.address:04x} names no "
                f"table to redirect into (§7.1.2.1)"
            )

            raise ZMachineInstructionError(msg)

        if len(self._redirections) >= REDIRECTION_LIMIT:
            msg = (
                f"output_stream 3 at ${instruction.address:04x} would nest "
                f"{REDIRECTION_LIMIT + 1} deep; §7.1.2.1.1 allows "
                f"{REDIRECTION_LIMIT} at most"
            )

            raise ZMachineInstructionError(msg)

        self._redirections.append((values[1], []))

    def _end_redirection(self, instruction: Instruction) -> None:
        """Close the newest stream 3 table, writing its count (§7.1.2.1).

        New-lines are written as ZSCII 13 (§7.1.2.2.1); other
        characters carry their ZSCII codes.
        """

        if not self._redirections:
            msg = (
                f"output_stream -3 at ${instruction.address:04x}, but "
                f"stream 3 is not selected (§7.1.2)"
            )

            raise ZMachineInstructionError(msg)

        table, pieces = self._redirections.pop()
        text = "".join(pieces)
        position = table + REDIRECTION_DATA_OFFSET

        for character in text:
            code = ZSCII_NEWLINE if character == "\n" else ord(character)

            self._memory.write_byte(position, code)
            position += 1

        self._memory.write_word(table, len(text))

    def _op_sound_effect(self, instruction: Instruction) -> None:
        """Sound a bleep, the only sound most stories make (§9).

        A bare sound_effect means bleep 1; 1 and 2 are the high and
        low bleeps the interpreter itself provides. The extra
        operands -- effect, volume, routine -- belong to sampled
        sounds and are ignored for bleeps.

        Raises:
            ZMachineUnimplementedError: For numbers 3 and up, the
                sampled sounds.
        """

        values = [self._value(operand) for operand in instruction.operands]
        number = values[0] if values else HIGH_BLEEP

        if number >= FIRST_SAMPLED_SOUND:
            raise ZMachineUnimplementedError(
                f"sampled sound {number}", instruction.address
            )

        self._frontend.bleep(number)
        self._pc = instruction.next_address

    def _op_read_char(self, instruction: Instruction) -> None:
        """Read one keystroke, storing its ZSCII code (§15 read_char).

        The input seam speaks in lines, so a keystroke is the first
        character of the next line -- and a bare return is the
        return key itself, ZSCII 13. A recorded script presses a key
        with a one-character line, or return with an empty one.

        A time and routine pair asks for the routine every time/10
        seconds of real waiting (§15); under the instant typist no
        real time ever elapses, so zero intervals pass, the routine
        is never called, and the read completes as an untimed one.
        (All Roads gates its title menu behind exactly such a read.)
        Games whose progress requires interrupts actually firing --
        Border Zone's real-time clock -- are at odds with seeded
        replay itself, and wait on a virtual-time seam.

        Raises:
            ZMachineInstructionError: If the first operand is not 1,
                the keyboard, which §15 makes the only input device.
        """

        values = [self._value(operand) for operand in instruction.operands]

        if values[0] != KEYBOARD_DEVICE:
            msg = (
                f"read_char at ${instruction.address:04x} asks for input "
                f"device {values[0]}, but the keyboard, 1, is the only "
                f"device there is (§15 read_char)"
            )

            raise ZMachineInstructionError(msg)

        line = self._input()
        code = ord(line[0]) if line else ZSCII_NEWLINE

        self._store_result(instruction.store_variable, code)
        self._pc = instruction.next_address

    def _op_show_status(self, instruction: Instruction) -> None:
        """Redraw the status line on request (§8.2).

        A frontend without a status line has nothing to redraw: the
        conforming quiet of an interpreter that declared so (§11.1).
        """

        if self._frontend.has_status_line:
            self._frontend.show_status(self._status())

        self._pc = instruction.next_address

    def _op_scan_table(self, instruction: Instruction) -> None:
        """Search a table for a value, delivering its address (§15).

        The value examined sits first in each field; a match stores
        the field's address and branches, no match stores 0. The
        optional form byte -- $82 when absent -- chooses word or
        byte comparison with its top bit and carries each field's
        length in the rest.
        """

        values = [self._value(operand) for operand in instruction.operands]
        target = values[0]
        count = values[2]
        form = (
            values[SCAN_FORM_OPERAND]
            if len(values) > SCAN_FORM_OPERAND
            else DEFAULT_SCAN_FORM
        )

        width = form & SCAN_FIELD_MASK
        words = bool(form & SCAN_WORD_BIT)

        address = values[1]
        found = 0

        for _ in range(count):
            entry = (
                self._memory.read_word(address)
                if words
                else self._memory.read_byte(address)
            )

            if entry == target:
                found = address
                break

            address += width

        self._store_result(instruction.store_variable, found)
        self._branch(instruction, found != 0)

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
        self._print(text)
        self._pc = instruction.next_address

    def _op_print_ret(self, instruction: Instruction) -> None:
        """Print the literal string, a new-line, and return true (§14)."""

        text, _ = decode_string(self._memory, instruction.operands_end)
        self._print(text + "\n")
        self._return(TRUE_VALUE)

    def _op_print_paddr(self, instruction: Instruction) -> None:
        """Print the string at a packed address (§1.2.3)."""

        packed = self._value(instruction.operands[0])
        address = string_address(self._memory.header, packed)
        text, _ = decode_string(self._memory, address)
        self._print(text)
        self._pc = instruction.next_address

    def _op_print_addr(self, instruction: Instruction) -> None:
        """Print the string at a byte address (§14)."""

        address = self._value(instruction.operands[0])
        text, _ = decode_string(self._memory, address)
        self._print(text)
        self._pc = instruction.next_address

    def _op_print_char(self, instruction: Instruction) -> None:
        """Print the character a ZSCII code means (§3.8)."""

        self._print(zscii_to_char(self._value(instruction.operands[0])))
        self._pc = instruction.next_address

    def _op_print_num(self, instruction: Instruction) -> None:
        """Print an operand as a signed decimal number (§2.2)."""

        self._print(str(signed(self._value(instruction.operands[0]))))
        self._pc = instruction.next_address

    def _op_new_line(self, instruction: Instruction) -> None:
        """Print a new-line."""

        self._print("\n")
        self._pc = instruction.next_address

    def _op_push(self, instruction: Instruction) -> None:
        """Push the operand's value onto the stack (§6.3)."""

        self._calls.push(self._value(instruction.operands[0]))
        self._pc = instruction.next_address

    def _op_pop(self, instruction: Instruction) -> None:
        """Discard the top of the stack (§15 pop).

        The 0OP throwaway of Versions 1 to 4; from Version 5 the
        same number belongs to catch. No game in the corpus ever
        used it -- Czech found it in seconds.
        """

        self._calls.pop()

        self._pc = instruction.next_address

    def _op_ret_popped(self, _instruction: Instruction) -> None:
        """Return the top of the current routine's stack (§6.4.5)."""

        self._return(self._calls.pop())

    def _op_quit(self, _instruction: Instruction) -> None:
        """Halt the machine; run() then returns normally."""

        self._running = False


# Dispatch by opcode name: call and call_vs are the same behaviour
# under the two names §14 gives VAR:0 across versions, and call_vn
# differs only in having no store variable to fill (§6.4.1). The
# "2" variants are the same calls again, grown a second type byte
# for up to seven arguments (§4.4.3.1) -- the decoder handles that,
# so one handler serves all eight names.
_HANDLERS: dict[str, Callable[[Machine, Instruction], None]] = {
    "add": Machine._op_add,
    "and": Machine._op_and,
    "art_shift": Machine._op_art_shift,
    "aread": Machine._op_sread,
    "buffer_mode": Machine._op_buffer_mode,
    "call": Machine._op_call,
    "check_arg_count": Machine._op_check_arg_count,
    "clear_attr": Machine._op_clear_attr,
    "call_1n": Machine._op_call,
    "call_1s": Machine._op_call,
    "call_2n": Machine._op_call,
    "call_2s": Machine._op_call,
    "call_vn": Machine._op_call,
    "call_vn2": Machine._op_call,
    "copy_table": Machine._op_copy_table,
    "call_vs": Machine._op_call,
    "call_vs2": Machine._op_call,
    "dec": Machine._op_dec,
    "dec_chk": Machine._op_dec_chk,
    "div": Machine._op_div,
    "erase_window": Machine._op_erase_window,
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
    "log_shift": Machine._op_log_shift,
    "mod": Machine._op_mod,
    "mul": Machine._op_mul,
    "new_line": Machine._op_new_line,
    "not": Machine._op_not,
    "or": Machine._op_or,
    "output_stream": Machine._op_output_stream,
    "piracy": Machine._op_piracy,
    "pop": Machine._op_pop,
    "print": Machine._op_print,
    "print_addr": Machine._op_print_addr,
    "print_char": Machine._op_print_char,
    "print_num": Machine._op_print_num,
    "print_obj": Machine._op_print_obj,
    "print_paddr": Machine._op_print_paddr,
    "print_table": Machine._op_print_table,
    "print_ret": Machine._op_print_ret,
    "pull": Machine._op_pull,
    "push": Machine._op_push,
    "put_prop": Machine._op_put_prop,
    "remove_obj": Machine._op_remove_obj,
    "set_attr": Machine._op_set_attr,
    "set_cursor": Machine._op_set_cursor,
    "set_text_style": Machine._op_set_text_style,
    "set_window": Machine._op_set_window,
    "show_status": Machine._op_show_status,
    "sound_effect": Machine._op_sound_effect,
    "split_window": Machine._op_split_window,
    "sread": Machine._op_sread,
    "quit": Machine._op_quit,
    "random": Machine._op_random,
    "read_char": Machine._op_read_char,
    "restart": Machine._op_restart,
    "restore": Machine._op_restore,
    "restore_undo": Machine._op_restore_undo,
    "ret": Machine._op_ret,
    "ret_popped": Machine._op_ret_popped,
    "rfalse": Machine._op_rfalse,
    "rtrue": Machine._op_rtrue,
    "save": Machine._op_save,
    "save_undo": Machine._op_save_undo,
    "scan_table": Machine._op_scan_table,
    "store": Machine._op_store,
    "storeb": Machine._op_storeb,
    "storew": Machine._op_storew,
    "sub": Machine._op_sub,
    "test": Machine._op_test,
    "test_attr": Machine._op_test_attr,
    "tokenise": Machine._op_tokenise,
    "verify": Machine._op_verify,
}
