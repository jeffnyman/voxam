"""A txd-style listing of a story's code and strings (§4, §14).

Nothing in a story file says where its routines are; the authority
on finding them is Mark Howell's txd (vendored with ztools), whose
discovery rules are transcribed here: code is found by decoding
it. A trial decode accepts an address as a routine when its local
count is 0 to 15 and every instruction decodes cleanly -- no store
into a local the routine does not have, no branch back past the
routine's own start, no jump below the code region. A routine ends
at an instruction execution cannot fall through -- a return, quit,
or jump -- once no earlier branch points past it. The code region
then grows to a fixed point: every constant call operand may widen
it, and the sweep restarts until the bounds hold still. Stretches
that refuse to decode are reported as data rather than silently
skipped, code that decodes without a routine header is an orphan
fragment, and the encoded strings after the code close the report.
txd's backward refinement of the Version 1 to 4 low boundary is
not carried here: it recovers only routines whose initial local
values themselves masquerade as code.
"""

from collections.abc import Callable
from dataclasses import dataclass

from voxam.errors import (
    ZMachineInstructionError,
    ZMachineMemoryError,
    ZMachineRoutineError,
    ZMachineTextError,
)
from voxam.zmachine.header import PACKED_PC_VERSION
from voxam.zmachine.instruction import Instruction, OperandType
from voxam.zmachine.memory import Memory
from voxam.zmachine.packed import SCALE, routine_address, string_address
from voxam.zmachine.riders import BRANCH_TARGET_ADJUSTMENT, Branch
from voxam.zmachine.routine import (
    LOCALS_IN_HEADER_LAST_VERSION,
    MAX_LOCALS,
    Routine,
)
from voxam.zmachine.story import Story
from voxam.zmachine.zscii import decode_string

# The instructions execution cannot fall through: a routine ends at
# one of these once no earlier branch points past it (txd).
FINALS = frozenset(
    {"rtrue", "rfalse", "ret", "ret_popped", "print_ret", "quit", "jump"}
)

# The opcodes whose first operand is a packed routine address
# (§6.4.3) -- the seams the code region grows through.
CALLERS = frozenset(
    {
        "call",
        "call_1s",
        "call_1n",
        "call_2s",
        "call_2n",
        "call_vs",
        "call_vs2",
        "call_vn",
        "call_vn2",
    }
)

# The opcodes that name an interrupt routine in a later operand: a
# packed routine address for timed input or sound (§15).
INTERRUPTERS = {"sread": 3, "aread": 3, "read_char": 2, "sound_effect": 3}

# The opcodes whose first operand is a variable *number* -- §6.3.4's
# indirect references -- worn in brackets as txd draws them. pull
# forks: in Version 6 its operand is a user stack address instead.
INDIRECTS = frozenset({"inc", "dec", "inc_chk", "dec_chk", "store", "pull", "load"})

# txd's own opcode column: names pad to sixteen characters.
NAME_WIDTH = 16

# The low scan accepts a boundary only when this many consecutive
# routines decode back-to-back from it (txd).
TRIALS = 3

# Two's complement bounds for jump's signed word operand (§15).
SIGNED_SIGN = 0x8000
SIGNED_RANGE = 0x10000

SMALL_WIDTH = 2
LARGE_WIDTH = 4


@dataclass(frozen=True)
class _Gap:
    """A stretch between routines that refuses to decode as code.

    Attributes:
        start: The first byte address of the stretch.
        end: The first byte address past it.
    """

    start: int
    end: int


@dataclass(frozen=True)
class _Fragment:
    """One decoded stretch of code: a routine or an orphan.

    Attributes:
        address: The byte address the stretch begins at -- the
            header byte for a routine, the first instruction for
            an orphan fragment.
        initial_locals: The routine header's initial local values;
            None marks an orphan fragment, code with no header.
        instructions: The decoded instructions, in address order.
    """

    address: int
    initial_locals: tuple[int, ...] | None
    instructions: tuple[Instruction, ...]


def report(story: Story) -> str:
    """Compose the full listing for a loaded story.

    Args:
        story: The story file to list.

    Returns:
        The listing as a newline-joined block of text: the code
        region routine by routine, then the encoded strings.
    """

    memory = Memory(story)
    surveyor = _Surveyor(memory, len(story.data))
    items, low, end = surveyor.survey()
    lines = [f"[start of code at ${low:04x}]"]

    for item in items:
        if isinstance(item, _Gap):
            lines += ["", f"[data from ${item.start:04x} to ${item.end - 1:04x}]"]
        else:
            lines += ["", *_titled(item, surveyor.entry, memory), ""]
            lines += [_line(memory, each) for each in item.instructions]

    lines += ["", f"[end of code at ${end - 1:04x}]"]
    lines += _strings(memory, story.data, end)

    return "\n".join(lines)


class Tracer:
    """The listing's live sibling: a witness on the machine's step.

    Every instruction the machine executes is rendered exactly as
    the static listing renders it and written to the sink in
    execution order -- a golden trace. When another interpreter
    disagrees with Voxam about a story, the first differing line
    of their traces is the bug; when a session halts, the trace's
    last line is the instruction that halted it. The closing line
    carries the tallies observability wants: how many instructions
    ran, and from how many distinct addresses.
    """

    def __init__(self, sink: Callable[[str], object]) -> None:
        """Aim the trace at a sink, one rendered line per step.

        The sink's return value is ignored, so a file's write and
        a list's append both serve.
        """

        self._sink = sink
        self._executed = 0
        self._addresses: set[int] = set()

    def see(self, memory: Memory, instruction: Instruction) -> None:
        """Witness one instruction on its way to execution."""

        self._executed += 1
        self._addresses.add(instruction.address)
        self._sink(f"{_line(memory, instruction)}\n")

    def close(self) -> None:
        """Write the closing tallies."""

        self._sink(
            f"\n[end of trace: {self._executed} instructions "
            f"at {len(self._addresses)} distinct addresses]\n"
        )


class _Surveyor:
    """The discovery walk: txd's first pass, bounds only widening."""

    def __init__(self, memory: Memory, size: int) -> None:
        self._memory = memory
        self._size = size
        self._scale = SCALE[memory.header.version]

        if memory.header.version == PACKED_PC_VERSION:
            self.entry = routine_address(
                memory.header, memory.header.main_routine_packed_address
            )
        else:
            # txd's own assumption for every other version: the
            # main routine's header byte sits immediately before
            # the initial program counter (§5.5).
            self.entry = memory.header.initial_program_counter - 1

    def survey(self) -> tuple[list[_Fragment | _Gap], int, int]:
        """Walk the code region to its fixed point.

        Returns:
            The fragments and data gaps in address order, the low
            boundary of code, and the first address past it.
        """

        low = self._low_scan()

        while True:
            items, end, lowest = self._sweep(low)

            if lowest < low:
                low = lowest

                continue

            return items, low, end

    def _low_scan(self) -> int:
        """Find uncalled routines below the entry point (txd).

        From the base of high memory -- where code conventionally
        begins (§1.1) -- the first address from which TRIALS
        consecutive routines decode back-to-back is the low
        boundary; failing that, the entry point is.
        """

        pc = self._round(self._memory.header.high_memory_base)

        while pc < self.entry:
            if self._consecutive(pc):
                return pc

            pc += self._scale

        return self.entry

    def _consecutive(self, pc: int) -> bool:
        """Whether TRIALS headered routines decode in a row here."""

        for _ in range(TRIALS):
            outcome = self._routine(self._round(pc), pc)

            if outcome is None:
                return False

            _, _, pc = outcome

        return True

    def _sweep(self, low: int) -> tuple[list[_Fragment | _Gap], int, int]:
        """One pass over the region, txd's middle loop and high scan.

        Returns:
            The items decoded, the first address past the last of
            them, and the lowest plausible call target seen -- the
            signal to restart the sweep from further down.
        """

        items: list[_Fragment | _Gap] = []
        lowest = low
        high = self.entry
        gap: int | None = None
        pc = low

        while pc <= high or pc <= self.entry:
            outcome = self._fragment(pc, low)

            if outcome is None:
                gap = self._round(pc) if gap is None else gap
                pc = self._hunt(self._round(pc))

                continue

            fragment, calls, end = outcome

            if gap is not None:
                items.append(_Gap(gap, fragment.address))

                gap = None

            items.append(fragment)

            for target in calls:
                if self._plausible(target):
                    lowest = min(lowest, target)
                    high = max(high, target)

            pc = end

        # txd's high scan: code runs on past the last call target
        # for as long as it keeps decoding.
        while (outcome := self._fragment(pc, low)) is not None:
            fragment, calls, end = outcome

            for target in calls:
                if self._plausible(target):
                    lowest = min(lowest, target)

            items.append(fragment)
            pc = end

        return items, pc, lowest

    def _hunt(self, pc: int) -> int:
        """Skip forward through data to the next plausible header."""

        pc += self._scale

        while pc < self._size and self._memory.fetch_byte(pc) > MAX_LOCALS:
            pc += self._scale

        return pc

    def _plausible(self, address: int) -> bool:
        """Whether an address could hold a routine header (txd)."""

        return address < self._size and self._memory.fetch_byte(address) <= MAX_LOCALS

    def _fragment(self, pc: int, low: int) -> tuple[_Fragment, set[int], int] | None:
        """Try one stretch, exactly txd's two ways.

        A routine is tried at the aligned address first; failing
        that, an orphan fragment -- headerless code -- at the raw
        one.
        """

        outcome = self._routine(self._round(pc), low)

        if outcome is not None:
            return outcome

        if pc >= self._size:
            return None

        body = self._body(pc, MAX_LOCALS, low)

        if body is None:
            return None

        instructions, calls = body

        return (
            _Fragment(pc, None, tuple(instructions)),
            calls,
            instructions[-1].next_address,
        )

    def _routine(
        self, address: int, low: int
    ) -> tuple[_Fragment, set[int], int] | None:
        """Try a headered routine: local count 0 to 15, clean body."""

        try:
            routine = Routine.parse(self._memory, address)
        except (ZMachineRoutineError, ZMachineMemoryError):
            return None

        body = self._body(routine.first_instruction, len(routine.initial_locals), low)

        if body is None:
            return None

        instructions, calls = body

        return (
            _Fragment(address, routine.initial_locals, tuple(instructions)),
            calls,
            instructions[-1].next_address,
        )

    def _body(
        self, start: int, count: int, low: int
    ) -> tuple[list[Instruction], set[int]] | None:
        """Decode instructions until the routine provably ends.

        The validations are txd's: a store into a local the routine
        does not have, a branch back past the routine's start, or a
        jump below the code region each reject the whole stretch.
        A final instruction ends it only once no earlier branch
        points past it -- the horizon rule.
        """

        calls: set[int] = set()
        instructions: list[Instruction] = []
        horizon = start
        pc = start

        while True:
            try:
                decoded = Instruction.decode(self._memory, pc)
            except (ZMachineInstructionError, ZMachineMemoryError):
                return None

            name = decoded.opcode.name
            stored = decoded.store_variable

            if stored is not None and 0 < stored <= MAX_LOCALS and stored > count:
                return None

            branch = decoded.branch

            if branch is not None and not (branch.returns_true or branch.returns_false):
                target = branch.target(decoded.next_address)

                if target < start:
                    return None

                horizon = max(horizon, target)

            if name == "jump" and decoded.operands[0].kind is not OperandType.VARIABLE:
                target = _jump_target(decoded)

                if target < low:
                    return None

                horizon = max(horizon, target)

            self._called(decoded, calls)
            instructions.append(decoded)

            if name in FINALS and decoded.next_address > horizon:
                return instructions, calls

            horizon = max(horizon, decoded.next_address)
            pc = decoded.next_address

    def _called(self, decoded: Instruction, calls: set[int]) -> None:
        """Collect the routine addresses an instruction names.

        A packed address of 0 is a call to nothing (§6.4.3) and
        grows the region nowhere.
        """

        name = decoded.opcode.name
        operands = decoded.operands
        index = 0 if name in CALLERS else INTERRUPTERS.get(name, -1)

        if (
            index >= 0
            and len(operands) > index
            and operands[index].kind is not OperandType.VARIABLE
            and operands[index].value
        ):
            calls.add(routine_address(self._memory.header, operands[index].value))

    def _round(self, address: int) -> int:
        """The address rounded up to the version's code alignment."""

        return (address + self._scale - 1) // self._scale * self._scale


def _jump_target(decoded: Instruction) -> int:
    """The jump destination: past the instruction, offset less two.

    The signed operand shares a branch's arithmetic (§15 jump).
    """

    value = decoded.operands[0].value

    if value & SIGNED_SIGN:
        value -= SIGNED_RANGE

    return decoded.next_address + value - BRANCH_TARGET_ADJUSTMENT


def _titled(fragment: _Fragment, entry: int, memory: Memory) -> list[str]:
    """A fragment's title line, txd's own words."""

    if fragment.initial_locals is None:
        return ["orphan code fragment:"]

    count = len(fragment.initial_locals)
    opening = "Main routine" if fragment.address == entry else "Routine"
    title = f"{opening} ${fragment.address:04x}, {count} local"

    if count != 1:
        title += "s"

    if memory.header.version <= LOCALS_IN_HEADER_LAST_VERSION and count:
        values = ", ".join(f"{value:04x}" for value in fragment.initial_locals)
        title += f" ({values})"

    return [title]


def _line(memory: Memory, decoded: Instruction) -> str:
    """One instruction, rendered: address, name, operands, riders."""

    parts = []
    operands = _operands(memory, decoded)

    if operands:
        parts.append(operands)

    if decoded.store_variable is not None:
        parts.append(f"-> {_variable(decoded.store_variable)}")

    if decoded.branch is not None:
        parts.append(_branch_note(decoded.branch, decoded.next_address))

    if decoded.text is not None:
        text, _ = decode_string(memory, decoded.text[0])
        parts.append(f'"{_escaped(text)}"')

    name = f"{decoded.opcode.name:<{NAME_WIDTH}}" if parts else decoded.opcode.name

    return f"  ${decoded.address:04x}: {name}{' '.join(parts)}".rstrip()


def _operands(memory: Memory, decoded: Instruction) -> str:
    """The operand list, each drawn for what it means (txd).

    Call targets, jump destinations, interrupt routines, and
    print_paddr's string unpack to the $addresses they reach;
    §6.3.4's indirect variable references wear brackets; all else
    is a #constant or a variable's name.
    """

    name = decoded.opcode.name
    version = memory.header.version
    words = []

    for index, operand in enumerate(decoded.operands):
        if operand.kind is OperandType.VARIABLE:
            words.append(_variable(operand.value))
        elif index == 0 and name in CALLERS and operand.value:
            words.append(f"${routine_address(memory.header, operand.value):04x}")
        elif index == 0 and name == "jump":
            words.append(f"${_jump_target(decoded):04x}")
        elif (
            index == 0
            and name in INDIRECTS
            and not (name == "pull" and version == PACKED_PC_VERSION)
        ):
            words.append(f"[{_variable(operand.value)}]")
        elif index == 0 and name == "print_paddr":
            words.append(f"${string_address(memory.header, operand.value):04x}")
        elif index == INTERRUPTERS.get(name, -1) and operand.value:
            words.append(f"${routine_address(memory.header, operand.value):04x}")
        else:
            width = (
                SMALL_WIDTH
                if operand.kind is OperandType.SMALL_CONSTANT
                else LARGE_WIDTH
            )
            words.append(f"#{operand.value:0{width}x}")

    if name in CALLERS and len(words) > 1:
        return f"{words[0]} ({', '.join(words[1:])})"

    return ", ".join(words)


def _branch_note(branch: Branch, after: int) -> str:
    """A branch rider as ?target, ~ negating the sense (§4.7)."""

    sense = "" if branch.on_true else "~"

    if branch.returns_false:
        return f"?{sense}rfalse"

    if branch.returns_true:
        return f"?{sense}rtrue"

    return f"?{sense}${branch.target(after):04x}"


def _variable(number: int) -> str:
    """A variable number's name: sp, L00 to L0e, G00 to Gef (§4.2.2)."""

    if number == 0:
        return "sp"

    if number <= MAX_LOCALS:
        return f"L{number - 1:02x}"

    return f"G{number - MAX_LOCALS - 1:02x}"


def _strings(memory: Memory, data: bytes, start: int) -> list[str]:
    """The encoded strings after the code, decoded to the file's end.

    A tail of zero bytes is the compiler's padding and says so; any
    other undecodable tail is reported as unreadable rather than
    silently dropped.
    """

    scale = SCALE[memory.header.version]
    pc = (start + scale - 1) // scale * scale

    if pc >= len(data):
        return []

    lines = ["", f"[start of text at ${pc:04x}]", ""]

    while pc < len(data):
        try:
            text, end = decode_string(memory, pc)
        except (ZMachineTextError, ZMachineMemoryError):
            marker = "padding" if not any(data[pc:]) else "unreadable text"
            lines += ["", f"[{marker} from ${pc:04x}]"]

            break

        lines.append(f'  ${pc:04x}: "{_escaped(text)}"')
        pc = (end + scale - 1) // scale * scale

    return [*lines, "", "[end of file]"]


def _escaped(text: str) -> str:
    """Text as Inform draws it: ^ for a newline, ~ for a quote."""

    return text.replace('"', "~").replace("\n", "^")
