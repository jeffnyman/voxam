"""The Glulx machine: the fetch-decode-execute loop.

This is the loop the whole package was built toward. Each step
reads an opcode number -- inline, because this runs once per
instruction -- looks up its operand signature and handler in one
combined table, decodes the operands, and executes. The eras the
machine does not carry yet answer by name from the full opcode
roster and halt as the frontier they are, never as a mystery.

The handlers receive their operands as a plain list: unsigned
32-bit integers for loads, StoreTargets for stores, in exactly
the shapes the dispatch table's signatures promise. The 32-bit
discipline was enforced a layer down, so the arithmetic here is
ordinary Python, masked only where a store leaves the machine.
"""

from typing import Any

from voxam.errors import (
    GlulxFrontierError,
    GlulxInstructionError,
    GlulxMemoryError,
)
from voxam.glulx import funcs, strings
from voxam.glulx.iosys import IOSystem
from voxam.glulx.memory import (
    BYTE_MASK,
    BYTE_WIDTH,
    SHORT_WIDTH,
    WORD_MASK,
    WORD_WIDTH,
    Memory,
)
from voxam.glulx.opcodes import Op, name
from voxam.glulx.operand import (
    FOUR_BYTE_OPCODE_BASE,
    ONE_BYTE_OPCODE_LIMIT,
    TWO_BYTE_OPCODE_BASE,
    TWO_BYTE_OPCODE_LIMIT,
    StoreTarget,
    decode_operands,
    operands,
    sign_extend,
    store,
)
from voxam.glulx.stack import DestType, Stack
from voxam.glulx.story import Story

SIGN_BIT = 0x8000_0000
WORD_RANGE = 1 << 32

# The most negative 32-bit value: the one dividend whose negation
# does not exist, making INT_MIN / -1 an overflow (Glulx: Integer
# Math).
INT_MIN = -0x8000_0000

# A branch offset of 0 or 1 does not jump: it returns 0 or 1 from
# the current function (Glulx: Branches).
RETURN_ZERO_OFFSET = 0
RETURN_ONE_OFFSET = 1

# The branch bias: offsets count from just past the instruction,
# less two (Glulx: Branches).
BRANCH_ADJUSTMENT = 2

SHIFT_LIMIT = 32
BITS_PER_BYTE = 8
BIT_INDEX_MASK = 0b111

# The call stubs that resume a string rather than store a result
# (Glulx: Call Stubs) -- the strings era's business.
RESUME_TYPES = frozenset(
    {
        DestType.RESUME_COMPRESSED,
        DestType.RESUME_NUMBER,
        DestType.RESUME_CSTRING,
        DestType.RESUME_UNICODE,
    }
)


def signed(value: int) -> int:
    """An unsigned 32-bit value reread as the signed one it spells."""

    return value - WORD_RANGE if value & SIGN_BIT else value


def _divided(a: int, b: int) -> int:
    """Signed division truncating toward zero (Glulx: Integer Math).

    Python's // floors, so -7 // 2 is -4 where Glulx wants -3;
    dividing the absolute values and reapplying the sign gives the
    truncation the spec requires.

    Raises:
        GlulxInstructionError: On a zero divisor, or the one
            overflow: the most negative value divided by -1.
    """

    x, y = signed(a), signed(b)

    if y == 0:
        msg = "division by zero (Glulx: Integer Math)"

        raise GlulxInstructionError(msg)

    if y == -1 and x == INT_MIN:
        msg = "division overflow: the most negative value by -1"

        raise GlulxInstructionError(msg)

    quotient = abs(x) // abs(y)

    return -quotient if (x < 0) != (y < 0) else quotient


def _remainder(a: int, b: int) -> int:
    """Signed remainder, its sign the dividend's (Glulx: Integer Math).

    Raises:
        GlulxInstructionError: On a zero divisor or the division
            overflow.
    """

    x, y = signed(a), signed(b)

    if y == 0:
        msg = "division by zero taking a remainder (Glulx: Integer Math)"

        raise GlulxInstructionError(msg)

    if y == -1 and x == INT_MIN:
        msg = "division overflow taking a remainder"

        raise GlulxInstructionError(msg)

    rest = abs(x) % abs(y)

    return -rest if x < 0 else rest


class Machine:
    """A Glulx virtual machine, booted and ready to step.

    Attributes:
        pc: The program counter.
        memory: The live memory map.
        stack: The value stack.
    """

    def __init__(self, story: Story) -> None:
        """Boot the machine: memory laid, stack raised, start called.

        Args:
            story: The validated story to run.
        """

        self._story = story
        self.memory = Memory(story)
        self.stack = Stack(story.stack_size)
        self.iosys = IOSystem()
        self.string_table = 0
        self.pc = 0
        self._running = True

        self.restart()

    @property
    def running(self) -> bool:
        """Whether execution has not yet been halted by quit."""

        return self._running

    def restart(self) -> None:
        """Return to the load state and call the start function.

        The protected range deliberately survives -- memory.reset
        honors it -- and execution begins by calling the header's
        start function with no arguments (Glulx: Game State,
        Glulx: The Header).
        """

        self.memory.reset()
        self.stack.reset()
        self.iosys.reset()
        self.string_table = self._story.decoding_table
        self._running = True
        self.pc = funcs.push_call_frame(
            self.memory, self.stack, self._story.start_function, []
        )

    def step(self) -> None:
        """Fetch, decode, and execute a single instruction.

        The opcode read is spelled out here rather than calling
        the operand module's decoder: this runs once per
        instruction, and so does the single combined lookup that
        yields signature and handler together.

        Raises:
            GlulxInstructionError: For an opcode number the spec
                does not define.
            GlulxFrontierError: For an opcode whose era the
                machine does not carry yet, named as such.
            VoxamError: On any rule the instruction breaks.
        """

        memory = self.memory
        pc = self.pc

        if pc >= memory.endmem:
            msg = f"execution ran off the memory map at ${pc:x} (Glulx: The Memory Map)"

            raise GlulxMemoryError(msg)

        first = memory.data[pc]

        if first < ONE_BYTE_OPCODE_LIMIT:
            opcode = first
            pc += 1
        elif first < TWO_BYTE_OPCODE_LIMIT:
            opcode = memory.read_short(pc) - TWO_BYTE_OPCODE_BASE
            pc += 2
        else:
            opcode = memory.read_word(pc) - FOUR_BYTE_OPCODE_BASE
            pc += 4

        entry = _DISPATCH.get(opcode)

        if entry is None:
            if opcode in Op.__members__.values():
                msg = f"the opcode {name(opcode)} awaits its era"

                raise GlulxFrontierError(msg)

            msg = (
                f"executed opcode {name(opcode)}, which Glulx 3.1.3 does "
                f"not define (Glulx: Dictionary of Opcodes)"
            )

            raise GlulxInstructionError(msg)

        oplist, handler = entry
        args, pc = decode_operands(memory, self.stack, pc, oplist)
        self.pc = pc

        handler(self, args)

    def run(self, limit: int | None = None) -> int:
        """Execute until the story quits; the step count comes back.

        The limit is a test and debugging guard, not a spec
        feature: a runaway loop in a broken story should fail
        rather than hang.

        Raises:
            GlulxInstructionError: On exceeding the given limit.
            VoxamError: On any rule the story breaks.
        """

        steps = 0

        while self._running:
            if limit is not None and steps >= limit:
                msg = f"execution exceeded {limit} instructions"

                raise GlulxInstructionError(msg)

            self.step()

            steps += 1

        return steps

    def _store(self, target: StoreTarget, value: int, width: int = 4) -> None:
        """Store through the operand machinery, at width."""

        store(self.memory, self.stack, target, value, width)

    def _jump(self, offset: int) -> None:
        """Branch by an offset -- or return 0 or 1 (Glulx: Branches)."""

        if offset in (RETURN_ZERO_OFFSET, RETURN_ONE_OFFSET):
            self._return(offset)
        else:
            # The pc already sits past the instruction, hence the
            # bias of two.
            self.pc = (self.pc + offset - BRANCH_ADJUSTMENT) & WORD_MASK

    def _return(self, value: int) -> None:
        """Leave the current function; an empty stack ends the story."""

        self.stack.leave_frame()

        if self.stack.sp == 0:
            self._running = False

            return

        self._pop_stub(value)

    def _pop_stub(self, value: int) -> None:
        """Pop a call stub and act on it (Glulx: Call Stubs).

        Raises:
            GlulxInstructionError: For a string-terminator stub
                where a function result belongs.
            GlulxFrontierError: For a string-resumption stub --
                the strings era's business, honestly named.
        """

        stub = self.stack.pop_stub()
        self.pc = stub.pc

        if stub.desttype == DestType.RESUME_FUNCTION:
            msg = (
                "a string-terminator call stub arrived where a function "
                "result belongs (Glulx: Call Stubs)"
            )

            raise GlulxInstructionError(msg)

        if stub.desttype in RESUME_TYPES:
            # A function called from inside a string has returned:
            # its value is discarded and the print picks up where
            # it left off (Glulx: Calling and Returning Within
            # Strings).
            strings.resume(self, stub)

            return

        self._store(StoreTarget(stub.desttype, stub.destaddr), value)

    def _call(self, addr: int, args: list[int], target: StoreTarget) -> None:
        """Push the come-home stub, then enter the function."""

        self.stack.push_stub(target.desttype, target.addr, self.pc)
        self.enter_function(addr, args)

    def enter_function(self, addr: int, args: list[int]) -> None:
        """Begin a call: every way of invoking a function lands here.

        The call opcodes and tailcall today; the accelerated
        functions and the string-decoding table's function nodes
        will land here too when their eras arrive, because that is
        what the spec means by a call including "any function
        invocation of that address".
        """

        self.pc = funcs.push_call_frame(self.memory, self.stack, addr, args)

    def _bit_address(self, base: int, index: int) -> tuple[int, int]:
        """A bit number resolved to its byte address and bit within.

        Bits number sequentially in both directions from the least
        significant bit of the base (Glulx: Array Data). Python's
        shift and mask floor for negative operands, which is
        exactly that rule -- the reference glulxe needs an
        explicit negative branch to get the same answer.
        """

        offset = signed(index)

        return (base + (offset >> 3)) & WORD_MASK, offset & BIT_INDEX_MASK

    def _op_nop(self, _args: list[Any]) -> None:
        """Do nothing, well (Glulx: Dictionary of Opcodes)."""

    def _op_add(self, args: list[Any]) -> None:
        self._store(args[2], args[0] + args[1])

    def _op_sub(self, args: list[Any]) -> None:
        self._store(args[2], args[0] - args[1])

    def _op_mul(self, args: list[Any]) -> None:
        self._store(args[2], args[0] * args[1])

    def _op_div(self, args: list[Any]) -> None:
        self._store(args[2], _divided(args[0], args[1]))

    def _op_mod(self, args: list[Any]) -> None:
        self._store(args[2], _remainder(args[0], args[1]))

    def _op_neg(self, args: list[Any]) -> None:
        self._store(args[1], -args[0])

    def _op_bitand(self, args: list[Any]) -> None:
        self._store(args[2], args[0] & args[1])

    def _op_bitor(self, args: list[Any]) -> None:
        self._store(args[2], args[0] | args[1])

    def _op_bitxor(self, args: list[Any]) -> None:
        self._store(args[2], args[0] ^ args[1])

    def _op_bitnot(self, args: list[Any]) -> None:
        self._store(args[1], ~args[0])

    def _op_shiftl(self, args: list[Any]) -> None:
        """Shift left; 32 places or more leave nothing (Glulx: Integer Math)."""

        places = signed(args[1])

        self._store(args[2], args[0] << places if 0 <= places < SHIFT_LIMIT else 0)

    def _op_ushiftr(self, args: list[Any]) -> None:
        """Shift right filling with zeros (Glulx: Integer Math)."""

        places = signed(args[1])

        self._store(args[2], args[0] >> places if 0 <= places < SHIFT_LIMIT else 0)

    def _op_sshiftr(self, args: list[Any]) -> None:
        """Shift right replicating the sign bit (Glulx: Integer Math).

        Python's shift on a signed value replicates the sign
        natively -- the behavior the spec wants and C only happens
        to provide.
        """

        places = signed(args[1])

        if 0 <= places < SHIFT_LIMIT:
            value = signed(args[0]) >> places
        else:
            value = WORD_MASK if args[0] & SIGN_BIT else 0

        self._store(args[2], value)

    def _op_jump(self, args: list[Any]) -> None:
        self._jump(args[0])

    def _op_jumpabs(self, args: list[Any]) -> None:
        """Jump to an absolute address, no bias, no return codes."""

        self.pc = args[0]

    def _op_jz(self, args: list[Any]) -> None:
        if args[0] == 0:
            self._jump(args[1])

    def _op_jnz(self, args: list[Any]) -> None:
        if args[0] != 0:
            self._jump(args[1])

    def _op_jeq(self, args: list[Any]) -> None:
        if args[0] == args[1]:
            self._jump(args[2])

    def _op_jne(self, args: list[Any]) -> None:
        if args[0] != args[1]:
            self._jump(args[2])

    def _op_jlt(self, args: list[Any]) -> None:
        if signed(args[0]) < signed(args[1]):
            self._jump(args[2])

    def _op_jge(self, args: list[Any]) -> None:
        if signed(args[0]) >= signed(args[1]):
            self._jump(args[2])

    def _op_jgt(self, args: list[Any]) -> None:
        if signed(args[0]) > signed(args[1]):
            self._jump(args[2])

    def _op_jle(self, args: list[Any]) -> None:
        if signed(args[0]) <= signed(args[1]):
            self._jump(args[2])

    def _op_jltu(self, args: list[Any]) -> None:
        if args[0] < args[1]:
            self._jump(args[2])

    def _op_jgeu(self, args: list[Any]) -> None:
        if args[0] >= args[1]:
            self._jump(args[2])

    def _op_jgtu(self, args: list[Any]) -> None:
        if args[0] > args[1]:
            self._jump(args[2])

    def _op_jleu(self, args: list[Any]) -> None:
        if args[0] <= args[1]:
            self._jump(args[2])

    def _op_call(self, args: list[Any]) -> None:
        addr, count, target = args

        self._call(addr, funcs.pop_arguments(self.stack, count, self.memory), target)

    def _op_callf(self, args: list[Any]) -> None:
        self._call(args[0], [], args[1])

    def _op_callfi(self, args: list[Any]) -> None:
        self._call(args[0], [args[1]], args[2])

    def _op_callfii(self, args: list[Any]) -> None:
        self._call(args[0], [args[1], args[2]], args[3])

    def _op_callfiii(self, args: list[Any]) -> None:
        self._call(args[0], [args[1], args[2], args[3]], args[4])

    def _op_return(self, args: list[Any]) -> None:
        self._return(args[0])

    def _op_tailcall(self, args: list[Any]) -> None:
        """Replace the frame without touching the stub below it."""

        addr, count = args
        call_args = funcs.pop_arguments(self.stack, count, self.memory)

        self.stack.leave_frame()
        self.enter_function(addr, call_args)

    def _op_catch(self, args: list[Any]) -> None:
        """Push a stub, store its token, then branch.

        The order is the spec's own: the offset was evaluated
        during operand decoding, then the stub is pushed and the
        token -- the resulting stack pointer -- computed, and only
        then is the token stored, which matters when either lives
        on the stack (Glulx: Continuations).
        """

        target, offset = args

        self.stack.push_stub(target.desttype, target.addr, self.pc)
        self._store(target, self.stack.sp)
        self._jump(offset)

    def _op_throw(self, args: list[Any]) -> None:
        """Unwind to a catch token and deliver a value there.

        Raises:
            GlulxInstructionError: For a token that is not a place
                on this stack (Glulx: Continuations).
        """

        value, token = args

        if token % WORD_WIDTH or token > self.stack.size:
            msg = (
                f"a throw's catch token of {token} is not a place on "
                f"this stack (Glulx: Continuations)"
            )

            raise GlulxInstructionError(msg)

        self.stack.sp = token

        self._pop_stub(value)

    def _op_copy(self, args: list[Any]) -> None:
        self._store(args[1], args[0])

    def _op_copys(self, args: list[Any]) -> None:
        self._store(args[1], args[0], SHORT_WIDTH)

    def _op_copyb(self, args: list[Any]) -> None:
        self._store(args[1], args[0], BYTE_WIDTH)

    def _op_sexs(self, args: list[Any]) -> None:
        self._store(args[1], sign_extend(args[0], 16))

    def _op_sexb(self, args: list[Any]) -> None:
        self._store(args[1], sign_extend(args[0], 8))

    def _op_aload(self, args: list[Any]) -> None:
        self._store(args[2], self.memory.read_word((args[0] + 4 * args[1]) & WORD_MASK))

    def _op_aloads(self, args: list[Any]) -> None:
        self._store(
            args[2], self.memory.read_short((args[0] + 2 * args[1]) & WORD_MASK)
        )

    def _op_aloadb(self, args: list[Any]) -> None:
        self._store(args[2], self.memory.read_byte((args[0] + args[1]) & WORD_MASK))

    def _op_aloadbit(self, args: list[Any]) -> None:
        addr, bit = self._bit_address(args[0], args[1])

        self._store(args[2], 1 if self.memory.read_byte(addr) & (1 << bit) else 0)

    def _op_astore(self, args: list[Any]) -> None:
        self.memory.write_word((args[0] + 4 * args[1]) & WORD_MASK, args[2])

    def _op_astores(self, args: list[Any]) -> None:
        self.memory.write_short((args[0] + 2 * args[1]) & WORD_MASK, args[2])

    def _op_astoreb(self, args: list[Any]) -> None:
        self.memory.write_byte((args[0] + args[1]) & WORD_MASK, args[2])

    def _op_astorebit(self, args: list[Any]) -> None:
        addr, bit = self._bit_address(args[0], args[1])
        value = self.memory.read_byte(addr)

        if args[2]:
            value |= 1 << bit
        else:
            value &= ~(1 << bit) & BYTE_MASK

        self.memory.write_byte(addr, value)

    def _op_stkcount(self, args: list[Any]) -> None:
        self._store(args[0], self.stack.count)

    def _op_stkpeek(self, args: list[Any]) -> None:
        """Peek by index; the index must name a value that exists."""

        index = signed(args[0])

        if index < 0 or index >= self.stack.count:
            msg = (
                f"stkpeek at {index} reaches outside the current stack "
                f"range (Glulx: The Stack)"
            )

            raise GlulxInstructionError(msg)

        self._store(args[1], self.stack.peek(index))

    def _op_stkswap(self, _args: list[Any]) -> None:
        if self.stack.count < 2:  # noqa: PLR2004 -- a swap takes a pair
            msg = "stkswap with fewer than two values (Glulx: The Stack)"

            raise GlulxInstructionError(msg)

        top, below = self.stack.pop(), self.stack.pop()

        self.stack.push(top)
        self.stack.push(below)

    def _op_stkcopy(self, args: list[Any]) -> None:
        count = signed(args[0])

        if count < 0:
            msg = "stkcopy with a negative count (Glulx: The Stack)"

            raise GlulxInstructionError(msg)

        if count == 0:
            return

        if self.stack.count < count:
            msg = f"stkcopy of {count} exceeds the values above the frame"

            raise GlulxInstructionError(msg)

        for value in [self.stack.peek(count - 1 - at) for at in range(count)]:
            self.stack.push(value)

    def _op_stkroll(self, args: list[Any]) -> None:
        """Rotate the top values by places, either direction.

        The reference glulxe splits the rotation in two because
        C's remainder is awkward for negative operands; Python's
        is not, and (-places) % count is the rotate-down distance
        for either sign (Glulx: The Stack).

        Raises:
            GlulxInstructionError: For a negative count, or one
                exceeding the values above the frame.
        """

        count, places = signed(args[0]), signed(args[1])

        if count < 0:
            msg = "stkroll with a negative count (Glulx: The Stack)"

            raise GlulxInstructionError(msg)

        if self.stack.count < count:
            msg = f"stkroll of {count} exceeds the values above the frame"

            raise GlulxInstructionError(msg)

        if count == 0:
            return

        shift = (-places) % count

        if shift == 0:
            return

        base = self.stack.sp - WORD_WIDTH * count
        values = [self.stack.read_word(base + WORD_WIDTH * at) for at in range(count)]
        values = values[shift:] + values[:shift]

        for at, value in enumerate(values):
            self.stack.write_word(base + WORD_WIDTH * at, value)

    def _op_streamchar(self, args: list[Any]) -> None:
        """Print one character, its low byte (Glulx: Output)."""

        strings.put_char(self, args[0] & BYTE_MASK)

    def _op_streamunichar(self, args: list[Any]) -> None:
        strings.put_char(self, args[0])

    def _op_streamnum(self, args: list[Any]) -> None:
        strings.stream_num(self, args[0])

    def _op_streamstr(self, args: list[Any]) -> None:
        strings.stream_string(self, args[0])

    def _op_getstringtbl(self, args: list[Any]) -> None:
        self._store(args[0], self.string_table)

    def _op_setstringtbl(self, args: list[Any]) -> None:
        """Point the decoder at another table (Glulx: Output).

        The address is taken on trust, exactly as the spec allows:
        a broken table announces itself at the next compressed
        print, not here.
        """

        self.string_table = args[0]

    def _op_getiosys(self, args: list[Any]) -> None:
        self._store(args[0], self.iosys.mode)
        self._store(args[1], self.iosys.rock)

    def _op_setiosys(self, args: list[Any]) -> None:
        self.iosys.select(args[0], args[1])

    def _op_getmemsize(self, args: list[Any]) -> None:
        self._store(args[0], self.memory.endmem)

    def _op_setmemsize(self, args: list[Any]) -> None:
        """Resize the map; success stores 0 (Glulx: Memory Map).

        The heap era will add the refusal the spec makes while the
        allocation heap is active: until malloc exists, no heap
        can be.
        """

        self.memory.set_size(args[0])
        self._store(args[1], 0)

    def _op_mzero(self, args: list[Any]) -> None:
        self.memory.fill(args[1], args[0])

    def _op_mcopy(self, args: list[Any]) -> None:
        self.memory.copy(args[2], args[1], args[0])

    def _op_protect(self, args: list[Any]) -> None:
        self.memory.set_protection(args[0], args[1])

    def _op_verify(self, args: list[Any]) -> None:
        """Recompute the checksum: 0 for sound, 1 for not (Glulx: Game State)."""

        self._store(args[0], 0 if self._story.verify() else 1)

    def _op_quit(self, _args: list[Any]) -> None:
        self._running = False

    def _op_restart(self, _args: list[Any]) -> None:
        self.restart()

    def _op_debugtrap(self, args: list[Any]) -> None:
        """Halt loudly: this interpreter has no debugger to hand off to.

        The spec directs an interpreter with no debugging faculty
        to treat the value as a fatal error and print it
        (Glulx: Miscellaneous).

        Raises:
            GlulxInstructionError: Always, carrying the value.
        """

        msg = f"debugtrap with value {args[0]} (Glulx: Miscellaneous)"

        raise GlulxInstructionError(msg)


_NONE = operands("")
_L = operands("L")
_LL = operands("LL")
_LLL = operands("LLL")
_S = operands("S")
_SS = operands("SS")
_LS = operands("LS")
_SL = operands("SL")
_LLS = operands("LLS")
_LLLS = operands("LLLS")
_LLLLS = operands("LLLLS")

# One combined table: each opcode's operand signature beside its
# handler, so a step costs a single lookup.
_DISPATCH: dict[int, tuple[Any, Any]] = {
    Op.NOP: (_NONE, Machine._op_nop),
    Op.ADD: (_LLS, Machine._op_add),
    Op.SUB: (_LLS, Machine._op_sub),
    Op.MUL: (_LLS, Machine._op_mul),
    Op.DIV: (_LLS, Machine._op_div),
    Op.MOD: (_LLS, Machine._op_mod),
    Op.NEG: (_LS, Machine._op_neg),
    Op.BITAND: (_LLS, Machine._op_bitand),
    Op.BITOR: (_LLS, Machine._op_bitor),
    Op.BITXOR: (_LLS, Machine._op_bitxor),
    Op.BITNOT: (_LS, Machine._op_bitnot),
    Op.SHIFTL: (_LLS, Machine._op_shiftl),
    Op.SSHIFTR: (_LLS, Machine._op_sshiftr),
    Op.USHIFTR: (_LLS, Machine._op_ushiftr),
    Op.JUMP: (_L, Machine._op_jump),
    Op.JUMPABS: (_L, Machine._op_jumpabs),
    Op.JZ: (_LL, Machine._op_jz),
    Op.JNZ: (_LL, Machine._op_jnz),
    Op.JEQ: (_LLL, Machine._op_jeq),
    Op.JNE: (_LLL, Machine._op_jne),
    Op.JLT: (_LLL, Machine._op_jlt),
    Op.JGE: (_LLL, Machine._op_jge),
    Op.JGT: (_LLL, Machine._op_jgt),
    Op.JLE: (_LLL, Machine._op_jle),
    Op.JLTU: (_LLL, Machine._op_jltu),
    Op.JGEU: (_LLL, Machine._op_jgeu),
    Op.JGTU: (_LLL, Machine._op_jgtu),
    Op.JLEU: (_LLL, Machine._op_jleu),
    Op.CALL: (_LLS, Machine._op_call),
    Op.CALLF: (_LS, Machine._op_callf),
    Op.CALLFI: (_LLS, Machine._op_callfi),
    Op.CALLFII: (_LLLS, Machine._op_callfii),
    Op.CALLFIII: (_LLLLS, Machine._op_callfiii),
    Op.RETURN: (_L, Machine._op_return),
    Op.TAILCALL: (_LL, Machine._op_tailcall),
    Op.CATCH: (_SL, Machine._op_catch),
    Op.THROW: (_LL, Machine._op_throw),
    Op.COPY: (_LS, Machine._op_copy),
    Op.COPYS: (operands("LS", arg_size=2), Machine._op_copys),
    Op.COPYB: (operands("LS", arg_size=1), Machine._op_copyb),
    Op.SEXS: (_LS, Machine._op_sexs),
    Op.SEXB: (_LS, Machine._op_sexb),
    Op.ALOAD: (_LLS, Machine._op_aload),
    Op.ALOADS: (_LLS, Machine._op_aloads),
    Op.ALOADB: (_LLS, Machine._op_aloadb),
    Op.ALOADBIT: (_LLS, Machine._op_aloadbit),
    Op.ASTORE: (_LLL, Machine._op_astore),
    Op.ASTORES: (_LLL, Machine._op_astores),
    Op.ASTOREB: (_LLL, Machine._op_astoreb),
    Op.ASTOREBIT: (_LLL, Machine._op_astorebit),
    Op.STREAMCHAR: (_L, Machine._op_streamchar),
    Op.STREAMUNICHAR: (_L, Machine._op_streamunichar),
    Op.STREAMNUM: (_L, Machine._op_streamnum),
    Op.STREAMSTR: (_L, Machine._op_streamstr),
    Op.GETSTRINGTBL: (_S, Machine._op_getstringtbl),
    Op.SETSTRINGTBL: (_L, Machine._op_setstringtbl),
    Op.GETIOSYS: (_SS, Machine._op_getiosys),
    Op.SETIOSYS: (_LL, Machine._op_setiosys),
    Op.STKCOUNT: (_S, Machine._op_stkcount),
    Op.STKPEEK: (_LS, Machine._op_stkpeek),
    Op.STKSWAP: (_NONE, Machine._op_stkswap),
    Op.STKROLL: (_LL, Machine._op_stkroll),
    Op.STKCOPY: (_L, Machine._op_stkcopy),
    Op.GETMEMSIZE: (_S, Machine._op_getmemsize),
    Op.SETMEMSIZE: (_LS, Machine._op_setmemsize),
    Op.MZERO: (_LL, Machine._op_mzero),
    Op.MCOPY: (_LLL, Machine._op_mcopy),
    Op.PROTECT: (_LL, Machine._op_protect),
    Op.VERIFY: (_S, Machine._op_verify),
    Op.QUIT: (_NONE, Machine._op_quit),
    Op.RESTART: (_NONE, Machine._op_restart),
    Op.DEBUGTRAP: (_L, Machine._op_debugtrap),
}
