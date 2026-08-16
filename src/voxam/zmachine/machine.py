"""The machine loop: fetch, decode, dispatch (§6).

A Machine binds everything built so far -- the memory image, the call
state, the variable façade -- to a program counter, and executes one
instruction at a time. Opcodes it does not yet implement raise
ZMachineUnimplementedError, so pointing Voxam at any story reveals
the frontier of what remains to build.
"""

import operator
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass

from voxam.errors import (
    ZMachineArithmeticError,
    ZMachineInstructionError,
    ZMachineMemoryError,
    ZMachineQuetzalError,
    ZMachineStackError,
    ZMachineTextError,
    ZMachineUnimplementedError,
)
from voxam.frontend import (
    COURIER_FONT,
    CURRENT_FONT,
    GRAPHICS_FONT,
    LOWER_WINDOW,
    NORMAL_FONT,
    UPPER_WINDOW,
    Frontend,
    PlainFrontend,
    Status,
)
from voxam.saves import SaveSlot
from voxam.zmachine.dictionary import Dictionary, tokenize
from voxam.zmachine.frames import CallStack
from voxam.zmachine.header import (
    FLAGS_2,
    FONT_FIELDS_VERSION,
    PACKED_PC_VERSION,
    SCREEN_FIELDS_VERSION,
    STATUS_FLAGS_VERSION,
)
from voxam.zmachine.instruction import Instruction, Operand, OperandType
from voxam.zmachine.memory import BYTE_MAX, Memory
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
from voxam.zmachine.variables import FIRST_GLOBAL, STACK_VARIABLE, Variables
from voxam.zmachine.windows import (
    CURRENT_WINDOW,
    X_CURSOR,
    X_SIZE,
    Y_CURSOR,
    WindowLedger,
)
from voxam.zmachine.zscii import (
    ZSCII_NEWLINE,
    char_to_zscii,
    decode_string,
    extras,
    zscii_to_char,
)

# Returning "false" means 0 and "true" means 1 (§6.4.5).
FALSE_VALUE = 0
TRUE_VALUE = 1

# The interpreter keeps a short stack of undo snapshots: games call
# save_undo once per turn, players unwind several turns, and Praxix
# tests the levels are distinct. Sixteen bounds the memory spent --
# a snapshot is at most a dynamic-memory image -- and the deque
# quietly forgets the oldest beyond that.
UNDO_DEPTH = 16

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


@dataclass(frozen=True)
class Identity:
    """Who the interpreter claims to be (§11.1.3, §11.1.4).

    Attributes:
        interpreter: The §11.1.3 platform number to introduce in
            Version 4 and later headers; None claims Voxam's
            default, the IBM PC.
        tandy: Whether to set Version 3's legendary Tandy bit,
            which some early Infocom games answer with altered
            text (§11.1 Remarks).
    """

    interpreter: int | None = None
    tandy: bool = False


DEFAULT_IDENTITY = Identity()

# The Standard revision Voxam obeys, written at $32/$33 (§11.1.5).
# 1.1: the unicode cluster, the prompt-bearing table saves, and the
# 1.1 clarifications the checkers certified along the way.
STANDARD_MAJOR = 1
STANDARD_MINOR = 1

# read_char's first operand is always 1, the keyboard: no other
# input device was ever defined (§15 read_char); its optional time
# and routine follow in the second and third slots (§15).
KEYBOARD_DEVICE = 1
READ_CHAR_TIME_OPERAND = 1
READ_CHAR_ROUTINE_OPERAND = 2

# From Version 4, read and read_char accept a time and routine pair:
# every time/10 seconds of waiting the routine is called, and a true
# return ends the read at once -- erasing any typed input and storing
# 0 where a terminating character would go (§15 read, §15 read_char).
TIMED_READ_VERSION = 4
INTERRUPT_TERMINATOR = 0

# set_font stores 0 for a font it will not grant (§15 set_font), and
# a character terminal's screen units are characters, so every font
# it offers is 1 by 1 (§8.1.1).
FONT_REFUSED = 0
FONT_UNIT = 1

# The conventional palette claim at $2c/$2d, as §8.3.1 codes: white
# type on a black screen (§8.3.3).
DEFAULT_FOREGROUND_COLOUR = 9
DEFAULT_BACKGROUND_COLOUR = 2

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
# from 3 upward they name sampled sounds (§9.2), and a bare
# sound_effect means bleep 1. The effects are prepare, start, stop,
# and finish (§15 sound_effect); number 0 stops or finishes them
# all. The third operand carries the §9.3 volume in its low byte --
# 255 meaning loudest -- and, from Version 5, the total play count
# in its high byte, 255 meaning until stopped (§9.4.3).
HIGH_BLEEP = 1
FIRST_SAMPLED_SOUND = 3
PREPARE_EFFECT = 1
START_EFFECT = 2
STOP_EFFECT = 3
FINISH_EFFECT = 4
STOP_ALL_SOUNDS = 0
LOUDEST_VOLUME = 255
FULL_VOLUME = 8
LOWEST_VOLUME = 1
REPEATS_SHIFT = 8
FOREVER_BYTE = 255
FOREVER_REPEATS = 0
SOUND_REPEATS_VERSION = 5
SOUND_VOLUME_OPERAND = 2
SOUND_ROUTINE_OPERAND = 3

# window_style's optional third operand picks the §15 operation --
# set, on, off, reverse -- defaulting to an outright set; and
# set_margins names its window last, defaulting to the current one.
STYLE_OPERATION_OPERAND = 2
MARGIN_WINDOW_OPERAND = 2

# read_mouse fills four words: y, x, button bits, menu word (§15).
MOUSE_WORDS = 4

# Version 6's output_stream may add a width as its third operand:
# the redirected text is then word-wrapped -- to a window's width
# if the operand is zero or positive, to a box of -width units if
# negative -- and the table takes print_form's line shape instead
# of the flat count-and-bytes (§15 output_stream). The total width
# of printing lands in the header word at $30 (§7.1.2.1).
REDIRECTION_WIDTH_OPERAND = 2
TOTAL_WIDTH_ADDRESS = 0x30

# Version 6 set_cursor: -1 turns the cursor off, -2 turns it back
# on, and an ordinary move may name its window third (§15).
CURSOR_OFF = 0xFFFF
CURSOR_ON = 0xFFFE
CURSOR_WINDOW_OPERAND = 2

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


# The codepoint ranges no letter-form exists for: the C0 and C1
# controls and the UTF-16 surrogates (§3.8.5.4.1, §3.8.5.4.3).
C0_CONTROL_END = 0x20
C1_CONTROL_START = 0x7F
C1_CONTROL_END = 0x9F
SURROGATE_START = 0xD800
SURROGATE_END = 0xDFFF


def _unicode_printable(code: int) -> bool:
    """Whether a stream frontend has a letter-form for a codepoint."""

    if code < C0_CONTROL_END or C1_CONTROL_START <= code <= C1_CONTROL_END:
        return False

    return not SURROGATE_START <= code <= SURROGATE_END


def _wrapped(text: str, limit: int) -> list[str]:
    """Greedy word-wrap onto lines at most limit units wide (§7.2).

    Forced new-lines end their lines; a word longer than the whole
    limit breaks at the limit, which is §8.8.3.1.1's unbuffered
    fallback.
    """

    lines = []

    for paragraph in text.split("\n"):
        current = ""

        for word in paragraph.split(" "):
            candidate = f"{current} {word}" if current else word

            if len(candidate) <= limit:
                current = candidate

                continue

            if current:
                lines.append(current)

            remainder = word

            while len(remainder) > limit:
                lines.append(remainder[:limit])
                remainder = remainder[limit:]

            current = remainder

        lines.append(current)

    return lines


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

    def __init__(  # noqa: PLR0913, PLR0917 -- one knob per input seam
        self,
        story: Story,
        frontend: Frontend | None = None,
        input_source: Callable[[], str] | None = None,
        seed: int | None = None,
        saves: SaveSlot | None = None,
        key_source: Callable[[float | None], str | None] | None = None,
        identity: Identity | None = None,
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
            key_source: Where single keystrokes come from, one
                character per call, when a frontend can read the
                keyboard raw. Called with a timeout in seconds it
                may answer None when the wait expires, which is how
                timed reads run on the wall clock; called with None
                it blocks for a real keystroke. A machine without a
                key source spends input_source lines through the
                keystroke queue instead.
            identity: Who the interpreter claims to be -- platform
                number and Tandy bit; None claims the defaults
                (§11.1.3, §11.1.4).
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
        self._key_source = key_source
        self._identity = identity if identity is not None else DEFAULT_IDENTITY
        self._words: Dictionary | None = None
        self._running = True
        self._screen_selected = True
        self._font = NORMAL_FONT
        self._redirections: list[tuple[int, list[str], int | None]] = []
        self._saves = saves
        self._undo: deque[Snapshot] = deque(maxlen=UNDO_DEPTH)
        self._pending_keys: deque[str] = deque()
        self._sound_routine = 0
        self._sound_since_input = False
        self._windows = self._fresh_windows()

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
        header.declare_sound(available=self._frontend.has_sounds)

        if header.version == STATUS_FLAGS_VERSION:
            header.declare_status_line(available=self._frontend.has_status_line)
            header.declare_screen_splitting(
                available=self._frontend.has_screen_splitting
            )
            header.declare_tandy(on=self._identity.tandy)
        elif header.version >= SCREEN_FIELDS_VERSION:
            platform = (
                self._identity.interpreter
                if self._identity.interpreter is not None
                else INTERPRETER_PLATFORM
            )
            header.introduce_interpreter(platform, INTERPRETER_REVISION)
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

            # The unit fields belong to Version 5 and later --
            # Version 6 included: ZIPTEST divides the unit width by
            # the font width before its first menu, so leaving them
            # zero is a division by zero at boot. The metrics come
            # from _unit_metrics: one character per unit everywhere
            # except a Version 6 story on a glass that measures,
            # which hears its §8.8 screen in real pixels.
            if header.version >= FONT_FIELDS_VERSION:
                font_width, font_height = self._unit_metrics()

                header.declare_screen_units(
                    width=self._frontend.screen_columns * font_width,
                    height=self._frontend.screen_lines * font_height,
                )
                header.declare_font_size(width=font_width, height=font_height)
                header.declare_colours(
                    available=self._frontend.has_colours,
                    foreground=DEFAULT_FOREGROUND_COLOUR,
                    background=DEFAULT_BACKGROUND_COLOUR,
                )

                if header.version == PACKED_PC_VERSION:
                    # In Version 6, Flags 2 bit 3 asks for pictures
                    # rather than the §16 font (§11.1), and no
                    # frontend draws them yet; the mouse and menu
                    # requests fall the same way (§11.1.2). Flags 1
                    # declares picture and sound availability
                    # outright (§11.1.4, §9.1.1).
                    header.declare_character_graphics(available=False)
                    header.declare_mouse(available=False)
                    header.declare_menus(available=False)
                    header.declare_pictures(available=False)
                    header.declare_sound_presence(available=self._frontend.has_sounds)
                else:
                    header.declare_character_graphics(
                        available=self._frontend.has_character_graphics
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
            self.poll_sound()
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

        §15 declares places beyond -15 to +15 undefined, and this
        used to halt loudly there -- until Praxix probed the zone on
        purpose, marking its own assertions "unspecified". The house
        rule, first written for object 0: an undefined zone completes
        with the coherent conventional answer when a published
        checker asserts survival. Shifting a word by 16 or more
        leaves nothing behind: zeros everywhere, except that the
        arithmetic right shift sign-fills forever.
        """

        number = self._value(instruction.operands[0])
        places = signed(self._value(instruction.operands[1]))

        # Past 16 places every outcome is already settled, so the
        # distance is clamped before Python builds a giant integer
        # to throw away.
        distance = min(abs(places), WORD_SIZE * 8)

        if places >= 0:
            result = (number << distance) & WORD_MASK
        elif arithmetic:
            result = (signed(number) >> distance) & WORD_MASK
        else:
            result = number >> distance

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

    def _table_address(self, array: int, index: int, scale: int) -> int:
        """The address of a table entry, on a 16-bit bus (§15 loadw).

        §15 says only "array + 2*word-index"; the Inform library and
        the checkers settle what it left open. The index is signed --
        Inform emits negative indices to step backward from a table
        -- and the sum wraps to what a 16-bit address can carry.
        Praxix found both conventions missing in its second minute;
        eleven recorded games never used either.
        """

        return (array + scale * signed(index)) & WORD_MASK

    def _op_loadw(self, instruction: Instruction) -> None:
        """Store the word at array + 2 * word-index (§15)."""

        array = self._value(instruction.operands[0])
        index = self._value(instruction.operands[1])

        self._store_result(
            instruction.store_variable,
            self._memory.read_word(self._table_address(array, index, WORD_SIZE)),
        )

        self._pc = instruction.next_address

    def _op_loadb(self, instruction: Instruction) -> None:
        """Store the byte at array + byte-index (§15)."""

        array = self._value(instruction.operands[0])
        index = self._value(instruction.operands[1])

        self._store_result(
            instruction.store_variable,
            self._memory.read_byte(self._table_address(array, index, 1)),
        )

        self._pc = instruction.next_address

    def _op_storew(self, instruction: Instruction) -> None:
        """Write a word at array + 2 * word-index (§15)."""

        array = self._value(instruction.operands[0])
        index = self._value(instruction.operands[1])
        value = self._value(instruction.operands[2])

        self._memory.write_word(self._table_address(array, index, WORD_SIZE), value)
        self._pc = instruction.next_address

    def _op_storeb(self, instruction: Instruction) -> None:
        """Write a byte at array + byte-index (§15).

        The operand is a word, and §15 does not say which part of a
        large one lands; the least significant byte is the coherent
        conventional answer -- the same rule §15 spells out for
        put_prop into one-byte properties -- and Sherlock depends on
        it, storing $ffff as a flag while the sun rises over the
        Abbey. This used to halt loudly; the shipped game earned
        the settlement.
        """

        array = self._value(instruction.operands[0])
        index = self._value(instruction.operands[1])
        value = self._value(instruction.operands[2])

        self._memory.write_byte(self._table_address(array, index, 1), value & BYTE_MAX)
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

        if instruction.operands:
            self._save_table(instruction)

            return

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

        if instruction.operands:
            self._restore_table(instruction)

            return

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
        plain capture and nothing slower. Captures stack up to
        UNDO_DEPTH deep, oldest quietly forgotten, so several turns
        can unwind in a row. The held snapshots are not part of the
        state of play (§6.1.1.2): they live outside the memory map,
        so a restore cannot resurrect them and an undo cannot be
        undone into growing forever. The PC captured is this
        instruction's own store byte, exactly as save records its
        rider (Quetzal §5.8.2).
        """

        self._undo.append(
            Snapshot(
                dynamic_memory=self._memory.dynamic_snapshot(),
                pc=instruction.operands_end,
                frames=self._calls.snapshot(),
            )
        )

        self._store_result(instruction.store_variable, TRUE_VALUE)

        self._pc = instruction.next_address

    def _op_restore_undo(self, instruction: Instruction) -> None:
        """Restore the state save_undo holds (§15).

        On success the machine resumes at the save_undo's store byte
        and answers 2 there, just as a file restore answers its save
        (§15 save). Each restore consumes the newest capture, so
        repeated UNDOs walk backward through distinct turns until
        the stack runs dry -- and with nothing in hand, which a game
        may not legally rely on (§15 restore_undo), it stores 0 and
        moves on, the quiet option the spec offers.
        """

        if not self._undo:
            self._store_result(instruction.store_variable, FALSE_VALUE)

            self._pc = instruction.next_address

            return

        snapshot = self._undo.pop()

        self.restore(snapshot)
        self._resume_from_save(snapshot.pc)

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

    # The table forms take at least a table, a length, and a name
    # (§15 save); Standard 1.1 adds an optional prompt flag, which
    # is accepted and left to the slot's own location policy --
    # prompting is a frontend affair the machine cannot see.
    TABLE_FORM_OPERANDS = 3

    def _save_table(self, instruction: Instruction) -> None:
        """Save a region of memory to a named auxiliary file (§15).

        Not the state of play: a raw run of bytes -- preferences, a
        map, whatever the game likes -- under a game-chosen name
        (§7.6). Stores 1 on success and 0 on failure, like the game
        save it shares an opcode with.
        """

        values = [self._value(operand) for operand in instruction.operands]

        self._require_table_form(instruction, values)

        table, count, name = values[:3]
        data = bytes(self._memory.read_byte(table + offset) for offset in range(count))
        kept = self._saves is not None and self._saves.write_aux(
            self._aux_name(name), data
        )

        self._store_result(instruction.store_variable, int(kept))

        self._pc = instruction.next_address

    def _restore_table(self, instruction: Instruction) -> None:
        """Load a named auxiliary file back into memory (§15 restore).

        At most the asked-for number of bytes arrive, and the result
        is the number actually loaded -- 0 for a file the slot does
        not have.
        """

        values = [self._value(operand) for operand in instruction.operands]

        self._require_table_form(instruction, values)

        table, count, name = values[:3]
        data = (
            self._saves.read_aux(self._aux_name(name))
            if self._saves is not None
            else None
        )
        loaded = (data or b"")[:count]

        for offset, value in enumerate(loaded):
            self._memory.write_byte(table + offset, value)

        self._store_result(instruction.store_variable, len(loaded))

        self._pc = instruction.next_address

    def _require_table_form(self, instruction: Instruction, values: list[int]) -> None:
        """Reject a table form missing its table, length, or name."""

        if len(values) < self.TABLE_FORM_OPERANDS:
            msg = (
                f"{instruction.opcode.name} at ${instruction.address:04x} "
                f"has {len(values)} operand(s), but the table form takes "
                f"a table, a length, and a name (§15 save)"
            )

            raise ZMachineInstructionError(msg)

    def _aux_name(self, address: int) -> str:
        """Read a game-supplied filename: a count byte, then text (§15)."""

        length = self._memory.read_byte(address)

        return "".join(
            zscii_to_char(
                self._memory.read_byte(address + 1 + offset),
                self._extras(),
                self._memory.header.version,
            )
            for offset in range(length)
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

        # The current font is interpreter bookkeeping, so a restart
        # returns it to normal along with the rest -- and tells the
        # frontend, or its screen would keep drawing §16 shapes the
        # machine no longer believes in.
        self._font = NORMAL_FONT
        self._frontend.set_font(NORMAL_FONT)

        # Sound is bookkeeping too: the speaker falls silent and any
        # end-of-sound routine dies with the state that armed it.
        self._frontend.stop_sound(None)
        self._sound_routine = 0
        self._sound_since_input = False

        # The §8.8 window ledger returns to its boot state with the
        # rest of the interpreter's own memory.
        self._windows = self._fresh_windows()

        self._declare_capabilities()
        self._start_execution()

    # Object 0 means "nothing" (§12.3), and the object opcodes
    # answer questions about it in kind: nothing's relatives are
    # nothing, nothing has no attributes or properties, and mutating
    # nothing changes nothing. The reads were earned by the early
    # Inform libraries (Magic Toyshop walks the tree from object 0
    # before the first command); the writes by Strict Z Test, whose
    # stated assumption is §12.3's own -- operations on object 0
    # "should either fail or, if that is not an option, do nothing",
    # and a halt mid-suite is not an option a checker survives.
    # print_obj 0 and put_prop 0 remain unearned and loud.

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
        """Branch if the first object's parent is the second (§15).

        Nothing's parent is nothing, so jin 0 0 is true and jin 0 n
        is false -- exactly what Strict Z Test expects.
        """

        obj = self._value(instruction.operands[0])
        parent = self._value(instruction.operands[1])
        parent_of = self._objects.parent(obj) if obj else 0

        self._branch(instruction, parent_of == parent)

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
        """Set the object's attribute (§15).

        An attribute beyond the version's §12.3.1 range changes
        nothing. Sherlock touches attribute 48 as the wax head
        melts -- a game bug so storied that Frotz carries a named
        pardon for it -- and the quiet no-op is the same settlement
        without the name. Testing such an attribute stays loud: no
        game has earned that door.
        """

        obj = self._value(instruction.operands[0])
        attribute = self._value(instruction.operands[1])

        if obj and self._objects.attribute_exists(attribute):
            self._objects.set_attribute(obj, attribute, on=True)

        self._pc = instruction.next_address

    def _op_clear_attr(self, instruction: Instruction) -> None:
        """Clear the object's attribute (§15).

        The out-of-range quiet of set_attr holds here too; it is
        clear_attr that Sherlock actually reaches with 48.
        """

        obj = self._value(instruction.operands[0])
        attribute = self._value(instruction.operands[1])

        if obj and self._objects.attribute_exists(attribute):
            self._objects.set_attribute(obj, attribute, on=False)

        self._pc = instruction.next_address

    def _op_insert_obj(self, instruction: Instruction) -> None:
        """Move an object to be a destination's first child (§15)."""

        obj = self._value(instruction.operands[0])
        destination = self._value(instruction.operands[1])

        # Moving nothing, or moving into nothing, changes nothing.
        if obj and destination:
            self._objects.insert(obj, destination)

        self._pc = instruction.next_address

    def _op_remove_obj(self, instruction: Instruction) -> None:
        """Detach an object from its parent (§15)."""

        obj = self._value(instruction.operands[0])

        if obj:
            self._objects.remove(obj)

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
        value = self._objects.property_value(obj, number) if obj else 0

        self._store_result(instruction.store_variable, value)

        self._pc = instruction.next_address

    def _op_get_prop_addr(self, instruction: Instruction) -> None:
        """Store a property's data address, or 0 when absent (§15)."""

        obj = self._value(instruction.operands[0])
        number = self._value(instruction.operands[1])
        found = self._objects.find_property(obj, number) if obj else None

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
        found = self._objects.next_property(obj, number) if obj else 0

        self._store_result(instruction.store_variable, found)

        self._pc = instruction.next_address

    def _op_pull(self, instruction: Instruction) -> None:
        """Pull the stack into a referenced variable (§15, §6.3.4).

        The seventh indirect-reference opcode: pulling into variable
        $00 overwrites the new stack top in place. Version 6 turns
        the opcode around: there it stores its result like any
        other, and an operand names a §6.6 user stack to pull from
        instead of the game stack.
        """

        if instruction.opcode.stores:
            value = (
                self._user_pull(self._value(instruction.operands[0]))
                if instruction.operands
                else self._calls.pop()
            )

            self._store_result(instruction.store_variable, value)
            self._pc = instruction.next_address

            return

        reference = self._value(instruction.operands[0])
        value = self._calls.pop()

        self._variables.write_in_place(reference, value)
        self._pc = instruction.next_address

    def _user_pull(self, stack: int) -> int:
        """Pull the top value from a §6.6 user stack.

        The first word counts the stack's spare slots and doubles
        as the index of the top value's slot, so a pull walks the
        count back up and reads the word it then points at. §6.6
        is explicit that nothing checks under-flow: pulling more
        than was pushed reads on past the table, exactly as the
        Z-machine promises.
        """

        spare = self._memory.read_word(stack) + 1

        self._memory.write_word(stack, spare)

        return self._memory.read_word(stack + 2 * spare)

    def _op_push_stack(self, instruction: Instruction) -> None:
        """Push onto a user stack, branching on success (§15).

        The stack is a table whose first word counts its spare
        slots (§6.6); the count is also the write index, so a push
        stores at the counted slot and walks the count down. A
        full stack does nothing at all -- overflow "is not an
        error condition", says §15 -- and the branch simply does
        not happen. ZIPTEST's user-stacks test pushes 1 to 5 and
        expects them back in reverse.
        """

        values = [self._value(operand) for operand in instruction.operands]
        value, stack = values[0], values[1]
        spare = self._memory.read_word(stack)

        if spare:
            self._memory.write_word(stack + 2 * spare, value)
            self._memory.write_word(stack, spare - 1)

        self._branch(instruction, spare != 0)

    def _op_pop_stack(self, instruction: Instruction) -> None:
        """Throw items away from the top of a stack (§15 pop_stack).

        By default the game stack; with a second operand, a §6.6
        user stack, where discarding is nothing more than walking
        the spare count up.
        """

        values = [self._value(operand) for operand in instruction.operands]
        items = values[0]

        if len(values) > 1:
            stack = values[1]

            self._memory.write_word(stack, self._memory.read_word(stack) + items)
        else:
            for _ in range(items):
                self._calls.pop()

        self._pc = instruction.next_address

    def _extras(self) -> str:
        """The extra-character repertoire in force (§3.8.5).

        Read afresh each time, like the alphabet rows: a custom
        translation table may live in dynamic memory.
        """

        return extras(self._memory)

    def _op_print_unicode(self, instruction: Instruction) -> None:
        """Print one Unicode character by codepoint (§15 print_unicode).

        §3.8.5.4.1 requires letter-forms for all of Latin-1 and asks
        for a question mark where none exists; a stream frontend has
        forms for everything except the control ranges and the
        surrogates, which get the question mark.
        """

        code = self._value(instruction.operands[0])

        self._print(chr(code) if _unicode_printable(code) else "?")

        self._pc = instruction.next_address

    def _op_check_unicode(self, instruction: Instruction) -> None:
        """Store what the interpreter can do with a codepoint (§15).

        Bit 0: it can be printed. Bit 1: it can arrive from the
        keyboard -- which for the line-based seam means ZSCII can
        carry it, through ASCII or the extra characters in force.
        """

        code = self._value(instruction.operands[0])
        result = 0

        if _unicode_printable(code):
            result |= 1

        try:
            char_to_zscii(chr(code), self._extras())
            result |= 2
        except ZMachineTextError:
            pass

        self._store_result(instruction.store_variable, result)

        self._pc = instruction.next_address

    def _dictionary(self) -> Dictionary:
        """The standard dictionary, read once on first use (§13.1)."""

        if self._words is None:
            self._words = Dictionary(self._memory)

        return self._words

    def _interrupt(self, packed: int) -> int:
        """Run a timed-input interrupt routine to completion (§15 read).

        The routine is called with no arguments through the ordinary
        call machinery, its result routed through the evaluation
        stack -- pushed by the return, popped here, leaving the
        interrupted frame's stack exactly as it was. Nested frames
        run until the interrupt's own frame unwinds.

        Args:
            packed: The routine's packed address, already nonzero.

        Returns:
            The routine's return value -- or true when the story
            quit mid-interrupt, because input has certainly ended.
        """

        address = routine_address(self._memory.header, packed)
        routine = Routine.parse(self._memory, address)
        floor = self._calls.depth

        self._calls.call(
            routine, (), return_address=self._pc, store_variable=STACK_VARIABLE
        )

        self._pc = routine.first_instruction

        while self._running and self._calls.depth > floor:
            self.step()

        if not self._running:
            return TRUE_VALUE

        return self._variables.read(STACK_VARIABLE)

    def _timed_out(self, values: list[int], time_index: int) -> bool:
        """Let the patient typist's one interval elapse (§15 read).

        The instant typist never let real time pass, so a time and
        routine pair was accepted and ignored. The patient typist
        waits exactly one interval before finishing the line: the
        routine fires once, and a true return means the read ends
        with no input consumed. A false return means the typist got
        there first, and the read proceeds as an untimed one.

        Args:
            values: The instruction's resolved operands.
            time_index: Where the time operand sits, with the
                routine in the slot after it.

        Returns:
            Whether the interrupt terminated the read.
        """

        if self._memory.header.version < TIMED_READ_VERSION:
            return False

        time = values[time_index] if len(values) > time_index else 0
        routine = values[time_index + 1] if len(values) > time_index + 1 else 0

        if not time or not routine:
            return False

        return bool(self._interrupt(routine))

    def _op_sread(self, instruction: Instruction) -> None:
        """Read a typed command into the buffers (§15 read, §13.6).

        One opcode, two eras: through Version 4 the text buffer takes
        a zero-terminated string from byte 1; from Version 5 the
        typed count lands in byte 1 with the letters from byte 2, the
        parse buffer may be zero to skip lexing, and the instruction
        stores its terminating character -- 13, the return key, since
        input here always ends in a newline (§15 read).

        A time and routine pair asks for interrupts during real
        waiting (§15); the patient typist lets one interval elapse
        before the line arrives, so the routine fires once, and a
        true return erases the input and ends the read with 0 stored
        -- see read_char for the full argument.

        A positive count already in byte 1 is preloaded input (§15
        read): characters the game placed in the buffer and printed
        itself, which Beyond Zork uses to restore a half-typed
        command after a function key. The typed line appends after
        them, and the whole line is lexed as one. (A live player
        could backspace into the preload; a scripted line cannot --
        the one editing gesture the line-based seam cannot speak.)

        Raises:
            ZMachineMemoryError: For a buffer too small to be real,
                which §15 asks interpreters to halt on.
        """

        # A keyboard input starts a new §9 pacing epoch: sounds
        # begun before this read no longer make a newer one wait.
        self._sound_since_input = False

        values = [self._value(operand) for operand in instruction.operands]

        # In Versions 1 to 3 the status line is redisplayed before the
        # player types (§8.2, §15 read) -- when there is one to show.
        if (
            self._memory.header.version <= STATUS_FLAGS_VERSION
            and self._frontend.has_status_line
        ):
            self._frontend.show_status(self._status())

        text_buffer = values[0]
        # The parse buffer may be omitted outright from Version 5 --
        # TerpEtude reads with the text buffer alone -- and an
        # omitted buffer skips lexing exactly as a zero one does
        # (§15 read). Through Version 4 the analysis is not optional.
        parse_buffer = values[1] if len(values) > 1 else 0
        counted = self._memory.header.version >= COUNTED_TEXT_VERSION

        if not counted and not parse_buffer:
            msg = (
                f"read at ${instruction.address:04x} names no parse "
                f"buffer, but lexing is not optional before Version 5 "
                f"(§15 read)"
            )

            raise ZMachineInstructionError(msg)

        capacity = self._memory.read_byte(text_buffer)

        if capacity < MINIMUM_TEXT_CAPACITY[counted]:
            msg = (
                f"the text buffer at ${text_buffer:04x} claims a capacity "
                f"of {capacity}: almost certainly overrun by a previous "
                f"array (§15 read)"
            )

            raise ZMachineMemoryError(msg)

        if self._timed_out(values, time_index=2):
            # All input is erased and the read ends at once (§15
            # read): a counted buffer reports zero letters typed, a
            # terminated one an empty string, and the lexing the
            # normal path would have done sees that emptiness.
            if counted:
                self._memory.write_byte(text_buffer + 1, 0)
            else:
                self._write_text(text_buffer + 1, "", terminate=True)

            if parse_buffer or not counted:
                self._parse(parse_buffer, "", first_letter=2 if counted else 1)

            if instruction.opcode.stores:
                self._store_result(instruction.store_variable, INTERRUPT_TERMINATOR)

            self._pc = instruction.next_address

            return

        if counted:
            preloaded = min(self._memory.read_byte(text_buffer + 1), capacity)
            held = "".join(
                zscii_to_char(
                    self._memory.read_byte(text_buffer + 2 + offset),
                    self._extras(),
                    self._memory.header.version,
                )
                for offset in range(preloaded)
            )
            typed = self._input().lower()[: capacity - preloaded]
            line = held + typed

            self._memory.write_byte(text_buffer + 1, len(line))
            self._write_text(text_buffer + 2 + preloaded, typed, terminate=False)
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
        """Lay typed text into the buffer, zero-terminated or not.

        Characters land as ZSCII codes: a typed accented letter is
        its §3.8.5 extra-character code, not its Unicode codepoint.
        """

        for character in line:
            self._memory.write_byte(position, char_to_zscii(character, self._extras()))
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
        between rows -- a window onto a larger character map. On
        the screen the rectangle spreads right and down from the
        cursor, each row returning to the column where it began
        (§15 print_table): Beyond Zork stamps its map beside the
        story box this way. Into a stream 3 table, or with the
        screen deselected, the rows travel as newline-separated
        lines instead, which is also what a plain transcript shows.
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

        rows = []
        position = table

        for _row in range(height):
            rows.append(
                "".join(
                    zscii_to_char(
                        self._memory.read_byte(position + offset),
                        self._extras(),
                        self._memory.header.version,
                    )
                    for offset in range(width)
                )
            )

            position += width + skip

        if self._redirections or not self._screen_selected:
            for index, row_text in enumerate(rows):
                if index:
                    self._print("\n")

                self._print(row_text)
        else:
            self._frontend.write_rectangle(rows)

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

    def _op_set_colour(self, instruction: Instruction) -> None:
        """Set text colours -- where coloured text is available (§8.3.1).

        The spec's own conditional does the work both ways: a
        frontend that claimed colours in the header receives the
        pair, and one that truthfully declared none makes the
        request a legitimate no-op, exactly as a monochrome
        terminal of the era would treat it.
        """

        if self._frontend.has_colours:
            self._frontend.set_colour(
                self._value(instruction.operands[0]),
                self._value(instruction.operands[1]),
            )

        self._pc = instruction.next_address

    def _op_set_true_colour(self, instruction: Instruction) -> None:
        """Let a 15-bit colour request pass unanswered (§8.3.7).

        True colour is its own claim, made in the header
        extension's flags word, and Voxam does not make it -- so
        the request reduces to the conforming quiet, with or
        without the classic §8.3.1 colours on offer.
        """

        self._pc = instruction.next_address

    def _op_set_text_style(self, instruction: Instruction) -> None:
        """Hand the requested type style to the frontend (§8.7).

        Each frontend renders the styles it claimed in the header
        and ignores the rest, which §8.7 permits.
        """

        self._frontend.set_style(self._value(instruction.operands[0]))
        self._pc = instruction.next_address

    def _op_set_font(self, instruction: Instruction) -> None:
        """Choose a §8.1.2 font, storing the one it replaces (§15).

        Font 0 asks which font is current without changing it. A
        font on offer is chosen and the previous font's ID comes
        back, always positive; one not on offer changes nothing
        and stores 0, the refusal §8.1.3 builds permission on.
        """

        font = self._value(instruction.operands[0])

        if font == CURRENT_FONT:
            self._store_result(instruction.store_variable, self._font)
        elif self._font_available(font):
            previous = self._font
            self._font = font

            self._frontend.set_font(font)
            self._store_result(instruction.store_variable, previous)
        else:
            self._store_result(instruction.store_variable, FONT_REFUSED)

        self._pc = instruction.next_address

    def _font_available(self, font: int) -> bool:
        """Whether the frontend has a §8.1.2 font to offer.

        The normal and fixed-pitch fonts are one and the same face
        on a character terminal, so both are always granted; the
        §16 character graphics font belongs to frontends that
        claimed it. Everything else is refused: the picture font
        by instruction (§8.1.4), and the higher numbers because no
        Standard has yet said what they mean (§8.1.6).
        """

        if font in (NORMAL_FONT, COURIER_FONT):
            return True

        return font == GRAPHICS_FONT and self._frontend.has_character_graphics

    def _op_erase_window(self, instruction: Instruction) -> None:
        """Hand a window erasure to the frontend (§8.7).

        The operand is signed: -1 unsplits and clears everything,
        -2 clears everything without unsplitting. In Version 6 any
        of the eight windows may be named, -3 meaning the current
        one -- but the character glass hears only about the two it
        renders, and erasing a window it never painted is already
        true (§8.8.3). Arthur clears its layout windows right
        after the prologue.
        """

        window = signed(self._value(instruction.operands[0]))

        if self._memory.header.version == PACKED_PC_VERSION and (
            window >= LOWER_WINDOW or window == CURRENT_WINDOW
        ):
            target = self._windows.resolve(window)

            if target > UPPER_WINDOW:
                self._pc = instruction.next_address

                return

            window = target

        self._frontend.erase_window(window)
        self._pc = instruction.next_address

    def _op_buffer_mode(self, instruction: Instruction) -> None:
        """Hand the word-wrap buffering toggle to the frontend (§8.7)."""

        self._frontend.set_buffering(bool(self._value(instruction.operands[0])))
        self._pc = instruction.next_address

    def _op_split_window(self, instruction: Instruction) -> None:
        """Hand the upper window's new height to the frontend (§8.7.2)."""

        self._frontend.split_window(self._value(instruction.operands[0]))
        self._pc = instruction.next_address

    def _unit_metrics(self) -> tuple[int, int]:
        """One character cell's width and height, in units.

        Version 6 alone measures its screen in real pixels
        (§8.8.1), so only there do the frontend's font metrics
        become the story's units. Every other version keeps one
        unit per character (§8.4.2): Beyond Zork lays out its
        windows by mixing unit arithmetic with character-cell
        set_cursor moves, which only agrees when the two scales
        are the same scale.
        """

        if self._memory.header.version == PACKED_PC_VERSION:
            return self._frontend.font_width, self._frontend.font_height

        return FONT_UNIT, FONT_UNIT

    def _fresh_windows(self) -> WindowLedger:
        """A boot-state §8.8 window ledger sized to this glass.

        Built for every version -- it is inert outside Version 6,
        whose opcodes are the only readers -- so no handler has to
        ask whether it exists. Its numbers are units: real pixels
        on a measuring glass, characters everywhere else.
        """

        font_width, font_height = self._unit_metrics()

        return WindowLedger(
            height=self._frontend.screen_lines * font_height,
            width=self._frontend.screen_columns * font_width,
            foreground=DEFAULT_FOREGROUND_COLOUR,
            background=DEFAULT_BACKGROUND_COLOUR,
            font_width=font_width,
            font_height=font_height,
        )

    def _op_set_window(self, instruction: Instruction) -> None:
        """Hand the window selection to the frontend (§8.7.2).

        In Version 6 the selection also lands in the §8.8 ledger,
        where any of the eight may be chosen and -3 keeps the
        current one; the character glass hears only about windows
        0 and 1, the two it renders.
        """

        window = self._value(instruction.operands[0])

        if self._memory.header.version == PACKED_PC_VERSION:
            selected = self._windows.resolve(window)
            self._windows.selected = selected

            if selected <= UPPER_WINDOW:
                self._frontend.set_window(selected)
        else:
            self._frontend.set_window(window)

        self._pc = instruction.next_address

    def _op_move_window(self, instruction: Instruction) -> None:
        """Place a window at (y, x) in the ledger (§15 move_window).

        §15 itself says "nothing actually happens" on screen --
        windows are notional transparencies -- so the ledger is the
        whole of the truth until a glass renders all eight.
        """

        values = [self._value(operand) for operand in instruction.operands]

        self._windows.move(values[0], values[1], values[2])
        self._pc = instruction.next_address

    def _op_window_size(self, instruction: Instruction) -> None:
        """Resize a window in the ledger (§15 window_size).

        "Does not change the current display", says §15 -- the
        bookkeeping is the observable behaviour.
        """

        values = [self._value(operand) for operand in instruction.operands]

        self._windows.resize(values[0], values[1], values[2])
        self._pc = instruction.next_address

    def _op_window_style(self, instruction: Instruction) -> None:
        """Change a window's attribute flags (§15 window_style)."""

        values = [self._value(operand) for operand in instruction.operands]
        operation = (
            values[STYLE_OPERATION_OPERAND]
            if len(values) > STYLE_OPERATION_OPERAND
            else 0
        )

        self._windows.restyle(values[0], values[1], operation)
        self._pc = instruction.next_address

    def _op_get_wind_prop(self, instruction: Instruction) -> None:
        """Store one §8.8.3.2 window property (§15 get_wind_prop)."""

        values = [self._value(operand) for operand in instruction.operands]
        value = self._windows.property(values[0], values[1])

        self._store_result(instruction.store_variable, value)
        self._pc = instruction.next_address

    def _op_put_wind_prop(self, instruction: Instruction) -> None:
        """Write one window property (§15 put_wind_prop)."""

        values = [self._value(operand) for operand in instruction.operands]

        self._windows.write_property(values[0], values[1], values[2])
        self._pc = instruction.next_address

    def _op_set_margins(self, instruction: Instruction) -> None:
        """Set a window's margin sizes (§15 set_margins).

        The window operand comes last and may be omitted, meaning
        the current window. The §8.8.3.2.2.2 cursor nudge waits on
        a glass that renders margins at all.
        """

        values = [self._value(operand) for operand in instruction.operands]
        window = (
            values[MARGIN_WINDOW_OPERAND]
            if len(values) > MARGIN_WINDOW_OPERAND
            else CURRENT_WINDOW
        )

        self._windows.set_margins(window, values[0], values[1])
        self._pc = instruction.next_address

    def _op_set_cursor(self, instruction: Instruction) -> None:
        """Move the cursor (§8.7.2, §15 set_cursor).

        Outside Version 6 the move goes to the frontend's upper
        window as it always has. Version 6 multiplies the forms --
        see _v6_cursor -- and its moves land in the §8.8 ledger,
        the same place its get_cursor reads, because the v5
        glass's upper-window policing would halt on windows it
        does not render.
        """

        if self._memory.header.version == PACKED_PC_VERSION:
            self._v6_cursor([self._value(o) for o in instruction.operands])
        else:
            line = self._value(instruction.operands[0])
            column = self._value(instruction.operands[1])

            self._frontend.set_cursor(line, column)

        self._pc = instruction.next_address

    def _v6_cursor(self, values: list[int]) -> None:
        """The Version 6 set_cursor forms (§15 set_cursor).

        A line of -1 turns the blinking cursor off and -2 -- with
        or without §15's "mysterious" second operand, 0 in every
        known case -- turns it back on: chrome a character glass
        has no cursor of its own to honour, passed quietly. An
        ordinary move may name any window, defaulting to the
        current one, and lands in that window's cursor properties;
        Arthur turns its cursor off before its title chrome.
        """

        line = values[0]

        if line in (CURSOR_OFF, CURSOR_ON):
            return

        column = values[1]
        window = (
            values[CURSOR_WINDOW_OPERAND]
            if len(values) > CURSOR_WINDOW_OPERAND
            else CURRENT_WINDOW
        )
        target = self._windows.resolve(window)

        self._windows.write_property(target, Y_CURSOR, line)
        self._windows.write_property(target, X_CURSOR, column)

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

        self._redirections.append((values[1], [], self._redirection_limit(values)))

    def _redirection_limit(self, values: list[int]) -> int | None:
        """The wrap width a Version 6 redirection asked for, if any.

        Zero or positive names a window, whose current width in
        units is the limit; negative means a box of -width units
        (§15 output_stream). No width -- or any version but 6 --
        is the flat, unformatted table. The wrap itself counts
        characters, so the unit width divides by the font width:
        on the 1-by-1 character glasses the numbers are the same,
        while a measuring glass turns 720 pixels back into 80
        characters.
        """

        if (
            len(values) <= REDIRECTION_WIDTH_OPERAND
            or self._memory.header.version != PACKED_PC_VERSION
        ):
            return None

        width = signed(values[REDIRECTION_WIDTH_OPERAND])
        font_width, _ = self._unit_metrics()

        if width < 0:
            return max(1, -width // font_width)

        return max(1, self._windows.property(width, X_SIZE) // font_width)

    def _end_redirection(self, instruction: Instruction) -> None:
        """Close the newest stream 3 table, writing its count (§7.1.2.1).

        New-lines are written as ZSCII 13 (§7.1.2.2.1); other
        characters carry their ZSCII codes. A redirection opened
        with a width writes print_form's line shape instead, and
        in Version 6 the longest line's width lands in the header
        word at $30 (§7.1.2.1).
        """

        if not self._redirections:
            msg = (
                f"output_stream -3 at ${instruction.address:04x}, but "
                f"stream 3 is not selected (§7.1.2)"
            )

            raise ZMachineInstructionError(msg)

        table, pieces, limit = self._redirections.pop()
        text = "".join(pieces)

        if limit is None:
            position = table + REDIRECTION_DATA_OFFSET

            # The table holds ZSCII, not Unicode (§3.8.5.4 counts
            # stream 3 among the places extra characters legally
            # appear): an oe-ligature lands as code 220, not
            # codepoint 339.
            for character in text:
                self._memory.write_byte(
                    position, char_to_zscii(character, self._extras())
                )
                position += 1

            self._memory.write_word(table, len(text))
            widest = max((len(part) for part in text.split("\n")), default=0)
        else:
            widest = self._write_formatted(table, text, limit)

        if self._memory.header.version == PACKED_PC_VERSION:
            # The $30 word is "total width in pixels" (§11's table)
            # -- characters times the font width, which the 1-by-1
            # glasses have always quietly satisfied.
            font_width, _ = self._unit_metrics()

            self._memory.write_word(TOTAL_WIDTH_ADDRESS, widest * font_width)

    def _write_formatted(self, table: int, text: str, limit: int) -> int:
        """Write print_form's line shape: counted lines, a zero end.

        Each line is a word holding its character count, then the
        characters (§15 print_form). The count doubles as the
        terminator, so a truly empty line cannot be carried; a
        blank line travels as a single space, the nearest printable
        truth.

        Returns:
            The widest line written, for the header's $30 word.
        """

        position = table
        widest = 0

        for line in _wrapped(text, limit):
            carried = line if line else " "
            widest = max(widest, len(carried))

            self._memory.write_word(position, len(carried))
            position += REDIRECTION_DATA_OFFSET

            for character in carried:
                self._memory.write_byte(
                    position, char_to_zscii(character, self._extras())
                )
                position += 1

        self._memory.write_word(position, 0)

        return widest

    def _op_sound_effect(self, instruction: Instruction) -> None:
        """Sound a bleep, or drive a sampled sound (§9).

        A bare sound_effect means bleep 1; 1 and 2 are the high and
        low bleeps the interpreter itself provides. From 3 upward
        the numbers name sampled sounds: on a frontend that has
        honestly cleared the header's sound request, the request
        passes in the conforming quiet The Lurking Horror and
        Sherlock were both shipped to accept -- the extra operands
        ignored, and the end-of-sound routine of a sound that never
        plays never called. A frontend with a speaker hears the
        full §9.4 forms instead, number 0 included, which stops or
        finishes every sound at once (§15 sound_effect).
        """

        values = [self._value(operand) for operand in instruction.operands]
        number = values[0] if values else HIGH_BLEEP

        if HIGH_BLEEP <= number < FIRST_SAMPLED_SOUND:
            self._frontend.bleep(number)
        elif self._frontend.has_sounds:
            self._sampled_sound(number, values)

        self._pc = instruction.next_address

    def _sampled_sound(self, number: int, values: list[int]) -> None:
        """Drive one sampled-sound effect through the frontend (§9.4).

        The §9 remarks name The Lurking Horror's own bugs, and
        those are the pardons here: an effect outside the four
        (its sound_effect 4 8) passes quietly, a number no
        resource answers (its sound_effect 4095 2 15) starts
        nothing and keeps any current sound playing, and the 15 of
        that same call is a volume clamped to §9.3's 8. The
        remarks also set the pacing: a new sound, started while
        one begun since the last keyboard input still plays, waits
        for that one to finish a cycle first -- The Lurking Horror
        assumes an interpreter as slow as Infocom's Amiga one.
        """

        effect = values[1] if len(values) > 1 else START_EFFECT

        if effect in (STOP_EFFECT, FINISH_EFFECT):
            self._frontend.stop_sound(number if number != STOP_ALL_SOUNDS else None)

            return

        if effect != START_EFFECT:
            # Prepare asks for nothing here -- every sound is
            # already decoded (§9.4.1) -- and any other effect is
            # the pardoned bug above.
            return

        word = (
            values[SOUND_VOLUME_OPERAND]
            if len(values) > SOUND_VOLUME_OPERAND
            else LOUDEST_VOLUME
        )
        volume = word & BYTE_MAX

        if volume == LOUDEST_VOLUME:
            # 255 is "loudest possible" (§9.3, §15 sound_effect).
            volume = FULL_VOLUME
        else:
            volume = min(max(volume, LOWEST_VOLUME), FULL_VOLUME)

        repeats: int | None

        if self._memory.header.version >= SOUND_REPEATS_VERSION:
            high = word >> REPEATS_SHIFT
            # 255 repeats until stopped; zero is illegal here, and
            # §15's own suggestion is to read it as once.
            repeats = FOREVER_REPEATS if high == FOREVER_BYTE else max(high, 1)
        else:
            # Version 3 cannot say -- §15 keeps the high byte 0 --
            # so None lets the Blorb's Loop chunk decide.
            repeats = None

        if self._sound_since_input and self._frontend.sound_playing():
            self._frontend.wait_for_sound()

        routine = (
            values[SOUND_ROUTINE_OPERAND] if len(values) > SOUND_ROUTINE_OPERAND else 0
        )

        if self._frontend.play_sound(number, volume, repeats):
            self._sound_routine = routine
            self._sound_since_input = True

    def poll_sound(self) -> None:
        """Fire the end-of-sound routine of a sound that just ended.

        The routine runs only after the sound has played its
        requested number of times -- the frontend's finished()
        answers exactly that, once -- and never for a sound
        stopped or replaced (§9.4.4). The result is discarded: an
        end-of-sound routine is not a §15 read interrupt, and
        terminates nothing.

        The run loop polls between instructions, and a painted
        session wires this into the painter's idle heartbeat too,
        so a sound ending while the player thinks at a prompt is
        attended to there and then -- the routine is cleared
        before it fires, so a poll from inside the routine's own
        nested execution finds nothing to do.
        """

        if self._sound_routine and self._frontend.sound_finished():
            routine, self._sound_routine = self._sound_routine, 0

            self._interrupt(routine)

    def _keystroke(self) -> int:
        """Take one key from the queue, refilled a line at a time.

        An empty queue draws the next scripted line: an empty line
        is the return key alone, ZSCII 13, and a longer line queues
        its characters to be typed one read_char at a time. The
        queue never invents a return -- a script presses enter with
        an explicit empty line -- so a one-character line remains
        exactly one keystroke, as every recording before the queue
        existed assumes. Line reads always fetch fresh lines: a
        queue left partly spent stays for the next read_char, where
        a mistyped recording will surface it deterministically.

        Returns:
            The ZSCII code of the next keystroke.
        """

        if self._key_source is not None:
            # A raw keyboard needs no queue: the frontend hands over
            # one real keystroke at a time, enter and all. A key
            # ZSCII has no code for is a key the story cannot hear
            # (§3.8) -- ignored, as every interpreter ignores it,
            # rather than fatal.
            while True:
                key = self._key_source(None)

                if key is None:
                    continue

                try:
                    return char_to_zscii(key, self._extras())
                except ZMachineTextError:
                    continue

        if not self._pending_keys:
            line = self._input()

            if not line:
                return ZSCII_NEWLINE

            self._pending_keys.extend(line)

        return char_to_zscii(self._pending_keys.popleft(), self._extras())

    def _op_read_char(self, instruction: Instruction) -> None:
        """Read one keystroke, storing its ZSCII code (§15 read_char).

        The input seam speaks in lines, so keystrokes come from a
        queue that spends one scripted line a character at a time: a
        one-character line is a single key, a longer line is that
        many keys in sequence, and a bare empty line is the return
        key itself, ZSCII 13. Bureaucracy's licence form types whole
        fields this way -- each field a line of keystrokes, each
        enter an empty line after it.

        A time and routine pair asks for the routine every time/10
        seconds of real waiting (§15). The patient typist waits one
        interval before pressing the key: the routine fires once,
        and a true return ends the read at once with 0 stored and no
        input consumed -- which is how Z-Tornado's Pause routine
        (an interrupt that just returns true) animates without
        eating the script. A false return means the key arrives and
        the read completes as an untimed one. Routines that need
        MANY intervals -- Border Zone's real-time clock -- would
        want a longer-suffering typist, a knob left unbuilt until a
        game demands it.

        Raises:
            ZMachineInstructionError: If the first operand is not 1,
                the keyboard, which §15 makes the only input device.
        """

        # A keystroke is keyboard input too: it starts a new §9
        # pacing epoch, just as a whole read does.
        self._sound_since_input = False

        values = [self._value(operand) for operand in instruction.operands]

        # The device operand itself may be omitted -- Strict Z Test's
        # closing keypress compiles bare -- and an absent device is
        # the keyboard, there being no other (§15 read_char).
        if values and values[0] != KEYBOARD_DEVICE:
            msg = (
                f"read_char at ${instruction.address:04x} asks for input "
                f"device {values[0]}, but the keyboard, 1, is the only "
                f"device there is (§15 read_char)"
            )

            raise ZMachineInstructionError(msg)

        time = (
            values[READ_CHAR_TIME_OPERAND]
            if len(values) > READ_CHAR_TIME_OPERAND
            else 0
        )
        routine = (
            values[READ_CHAR_ROUTINE_OPERAND]
            if len(values) > READ_CHAR_ROUTINE_OPERAND
            else 0
        )

        if self._key_source is not None and time and routine:
            # A raw keyboard runs the timed read on the wall clock:
            # the routine fires every time/10 seconds the player
            # does not type (§15 read_char), and a true return ends
            # the read with 0 stored.
            code = self._timed_keystroke(self._key_source, time, routine)

            if code is None:
                code = INTERRUPT_TERMINATOR

            self._store_result(instruction.store_variable, code)
            self._pc = instruction.next_address

            return

        if self._timed_out(values, time_index=1):
            self._store_result(instruction.store_variable, INTERRUPT_TERMINATOR)
            self._pc = instruction.next_address

            return

        self._store_result(instruction.store_variable, self._keystroke())
        self._pc = instruction.next_address

    def _timed_keystroke(
        self, source: Callable[[float | None], str | None], time: int, routine: int
    ) -> int | None:
        """Wait for a key against the wall clock (§15 read_char).

        Each expired time/10-second interval fires the interrupt
        routine; a true return -- or a story that quit inside the
        interrupt -- ends the read with None. A key that arrives
        before the interval beats the clock, and the routine does
        not fire for it. Keys ZSCII cannot express are ignored as
        ever (§3.8).
        """

        interval = time / 10

        while True:
            key = source(interval)

            if key is None:
                if self._interrupt(routine):
                    return None

                continue

            try:
                return char_to_zscii(key, self._extras())
            except ZMachineTextError:
                continue

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

    def _op_get_cursor(self, instruction: Instruction) -> None:
        """Write the cursor's row and column into an array (§15).

        Word 0 takes the row and word 1 the column -- the array is
        not a table, so there is no size word. The answer is the
        upper window's cursor, the one set_cursor can move
        (§8.7.2.3.2); ZIPTEST's CURGET test reads it back after
        every move it makes.
        """

        array = self._value(instruction.operands[0])

        if self._memory.header.version == PACKED_PC_VERSION:
            # Version 6 reads the current window's cursor from the
            # §8.8 ledger -- the same place its set_cursor writes,
            # so the round trip is exact.
            row = self._windows.property(CURRENT_WINDOW, Y_CURSOR)
            column = self._windows.property(CURRENT_WINDOW, X_CURSOR)
        else:
            row, column = self._frontend.cursor_position()

        self._memory.write_word(array, row)
        self._memory.write_word(array + 2, column)
        self._pc = instruction.next_address

    def _op_print_form(self, instruction: Instruction) -> None:
        """Print a formatted table, line by line (§15 print_form).

        The table is the shape a width-bearing output_stream 3
        writes: each line a word holding its character count then
        the characters themselves, the sequence ending at a zero
        word. Each line prints followed by a new-line --
        print_table's elaborated cousin flows down the screen, not
        rightward across it. Arthur formats even its parser errors
        this way.
        """

        position = self._value(instruction.operands[0])

        while True:
            count = self._memory.read_word(position)

            if count == 0:
                break

            position += REDIRECTION_DATA_OFFSET
            line = "".join(
                zscii_to_char(
                    self._memory.read_byte(position + offset),
                    self._extras(),
                    self._memory.header.version,
                )
                for offset in range(count)
            )

            self._print(line + "\n")

            position += count

        self._pc = instruction.next_address

    def _op_picture_quiet(self, instruction: Instruction) -> None:
        """Let a picture operation pass in the conforming quiet.

        The header honestly declares no picture displaying
        (§11.1.4), and what was declared unavailable is not
        performed: draw_picture and erase_picture paint nothing --
        Infocom's own games draw without consulting the header,
        the §11.1.4 remarks even name Zork Zero's Macintosh
        release for it, so a loud halt here would stop Arthur at
        its title card -- and picture_table is only ever a cache
        hint (§15). When a real graphics frontend arrives, these
        become its work.
        """

        self._pc = instruction.next_address

    def _op_picture_data(self, instruction: Instruction) -> None:
        """Answer for pictures the interpreter does not have (§15).

        With a valid picture number the opcode would write the
        picture's height and width and branch; number 0 asks for
        the census instead, writing the count of available
        pictures and the picture file's release into the array,
        branching if any pictures exist. An interpreter with no
        picture system has one honest answer for both: a census
        of zero, an invalid number for everything else, and no
        branch either way -- exactly what the header's cleared
        pictures bit promised (§11.1.4).
        """

        values = [self._value(operand) for operand in instruction.operands]
        number = values[0]
        array = values[1]

        if number == 0:
            self._memory.write_word(array, 0)
            self._memory.write_word(array + 2, 0)

        self._branch(instruction, False)

    def _op_scroll_window(self, instruction: Instruction) -> None:
        """Let a manual scroll pass in the conforming quiet (§15).

        scroll_window shifts a window's pixels up or down, blanking
        what is exposed -- unrelated, §15 notes, to the scrolling
        attribute. A character glass scrolls its own lower window
        by §8.7 as text flows, and renders the other windows as
        flowing text besides, so there are no pixels here to shift:
        the true pixel scroll waits on the graphics frontend.
        Arthur scrolls its story window at the first prompt.
        """

        self._pc = instruction.next_address

    def _op_mouse_window(self, instruction: Instruction) -> None:
        """Let a mouse constraint pass in the conforming quiet (§15).

        mouse_window confines the mouse arrow to a window; the
        header's mouse request was cleared at boot (§11.1.2), and
        there is no arrow to confine. Arthur constrains the mouse
        on its way up regardless -- v6 games set up the pointer
        without consulting the header, just as they draw.
        """

        self._pc = instruction.next_address

    def _op_read_mouse(self, instruction: Instruction) -> None:
        """Report a mouse that never moves or clicks (§15 read_mouse).

        The array's four words take the y coordinate, the x
        coordinate, the button bits, and the menu word; a mouse
        the header already declined reports zeros for all four --
        parked at nowhere, no buttons down, no menu touched.
        """

        array = self._value(instruction.operands[0])

        for word in range(MOUSE_WORDS):
            self._memory.write_word(array + 2 * word, 0)

        self._pc = instruction.next_address

    def _op_make_menu(self, instruction: Instruction) -> None:
        """Fail a menu request the header already refused (§15).

        make_menu branches when the menu is successfully built;
        the Flags 2 menus request was cleared at boot (§11.1.2),
        and an interpreter without menus simply never succeeds.
        """

        self._branch(instruction, False)

    def _op_nop(self, instruction: Instruction) -> None:
        """Do nothing, on purpose (§15 nop).

        Probably the result of a bug in Infocom's compiler, says
        §15 -- yet no story executed one until ZIPTEST's
        Call/Stacks test walked through it mid-suite.
        """

        self._pc = instruction.next_address

    def _op_print_char(self, instruction: Instruction) -> None:
        """Print the character a ZSCII code means (§3.8)."""

        self._print(
            zscii_to_char(
                self._value(instruction.operands[0]),
                self._extras(),
                self._memory.header.version,
            )
        )
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

    def _op_catch(self, instruction: Instruction) -> None:
        """Store the magic cookie naming this stack frame (§15 catch).

        The cookie is specified exactly -- the number of frames on
        the call stack (Quetzal §6.2) -- so that saved games carry
        caught cookies between interpreters intact.
        """

        self._store_result(instruction.store_variable, self._calls.depth)

        self._pc = instruction.next_address

    def _op_throw(self, instruction: Instruction) -> None:
        """Unwind to a caught frame and return from it (§15 throw).

        The opposite of catch: the call state rewinds to where the
        cookie was caught, and then returns from that routine with
        the given value, as if it had executed ret.

        Raises:
            ZMachineStackError: For a cookie naming more frames than
                exist -- a catch that has already returned, which
                nothing can throw back to.
        """

        value = self._value(instruction.operands[0])
        frame = self._value(instruction.operands[1])

        if frame > self._calls.depth or frame < 1:
            msg = (
                f"cannot throw to stack frame {frame}: the call stack "
                f"is {self._calls.depth} deep, so that catch has "
                f"already returned (§15 throw)"
            )

            raise ZMachineStackError(msg)

        while self._calls.depth > frame:
            self._calls.pop_frame()

        self._return(value)

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
    "catch": Machine._op_catch,
    "check_unicode": Machine._op_check_unicode,
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
    "draw_picture": Machine._op_picture_quiet,
    "erase_picture": Machine._op_picture_quiet,
    "get_wind_prop": Machine._op_get_wind_prop,
    "make_menu": Machine._op_make_menu,
    "mouse_window": Machine._op_mouse_window,
    "move_window": Machine._op_move_window,
    "new_line": Machine._op_new_line,
    "nop": Machine._op_nop,
    "picture_data": Machine._op_picture_data,
    "picture_table": Machine._op_picture_quiet,
    "print_form": Machine._op_print_form,
    "put_wind_prop": Machine._op_put_wind_prop,
    "read_mouse": Machine._op_read_mouse,
    "set_margins": Machine._op_set_margins,
    "window_size": Machine._op_window_size,
    "window_style": Machine._op_window_style,
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
    "print_unicode": Machine._op_print_unicode,
    "print_ret": Machine._op_print_ret,
    "pop_stack": Machine._op_pop_stack,
    "pull": Machine._op_pull,
    "push": Machine._op_push,
    "push_stack": Machine._op_push_stack,
    "put_prop": Machine._op_put_prop,
    "remove_obj": Machine._op_remove_obj,
    "get_cursor": Machine._op_get_cursor,
    "set_attr": Machine._op_set_attr,
    "set_cursor": Machine._op_set_cursor,
    "set_font": Machine._op_set_font,
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
    "scroll_window": Machine._op_scroll_window,
    "ret": Machine._op_ret,
    "ret_popped": Machine._op_ret_popped,
    "rfalse": Machine._op_rfalse,
    "rtrue": Machine._op_rtrue,
    "save": Machine._op_save,
    "save_undo": Machine._op_save_undo,
    "scan_table": Machine._op_scan_table,
    "set_colour": Machine._op_set_colour,
    "set_true_colour": Machine._op_set_true_colour,
    "store": Machine._op_store,
    "storeb": Machine._op_storeb,
    "storew": Machine._op_storew,
    "sub": Machine._op_sub,
    "test": Machine._op_test,
    "test_attr": Machine._op_test_attr,
    "throw": Machine._op_throw,
    "tokenise": Machine._op_tokenise,
    "verify": Machine._op_verify,
}
