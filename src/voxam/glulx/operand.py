"""Operand decoding: opcodes, addressing modes, and stores.

Everything here is (Glulx: Instruction Format): an opcode number
whose own top bits say whether it spans one, two, or four bytes;
then the operands' addressing modes, packed two nibbles per byte;
then the operand data itself. Operands are evaluated strictly left
to right -- the spec calls that out because several modes pop the
stack, and order is the difference between right and wrong.

This module is also where the 32-bit discipline is enforced. Loads
always yield unsigned values in 0 through 0xFFFFFFFF -- the
constant modes sign-extend and are then reduced to the equivalent
unsigned value -- and store() masks on the way out. Everything
above this layer may therefore use ordinary Python arithmetic
without masking at every step, which matters because Python
integers never overflow on their own.

The sixteen modes decode arithmetically rather than by table: they
fall into four groups of four -- constant, memory, local, RAM --
so mode >> 2 selects the group and mode & 3 the operand's width.
This is the hottest loop the machine will have, and the dictionary
lookups of the obvious version cost more than the decoding does.
"""

from dataclasses import dataclass
from enum import IntEnum
from typing import NamedTuple

from voxam.errors import GlulxInstructionError, GlulxMemoryError
from voxam.glulx.memory import WORD_MASK, Memory
from voxam.glulx.stack import DestType, Stack

# The opcode number's own length rides in its top bits: below 0x80
# one byte, below 0xC0 two bytes less 0x8000, else four bytes less
# 0xC0000000 -- so 01, 8001, and C0000001 all name opcode 1
# (Glulx: Instruction Format).
ONE_BYTE_OPCODE_LIMIT = 0x80
TWO_BYTE_OPCODE_LIMIT = 0xC0
TWO_BYTE_OPCODE_BASE = 0x8000
FOUR_BYTE_OPCODE_BASE = 0xC000_0000

# A mode byte carries two operands' modes: the first in its low
# nibble, the second in its high (Glulx: Instruction Format).
MODE_MASK = 0x0F
HIGH_NIBBLE_SHIFT = 4

# mode >> 2 is the group -- constant, memory, local, RAM -- and
# mode & 3 the width code: none, byte, short, word.
GROUP_SHIFT = 2
SIZE_MASK = 0b11
CONSTANT_GROUP = 0
MEMORY_GROUP = 1
LOCAL_GROUP = 2
STACK_MODE = 8

BYTE_BITS = 8
SHORT_BITS = 16

WIDTH_MASKS = {1: 0xFF, 2: 0xFFFF, 4: WORD_MASK}


class Form(IntEnum):
    """Whether an operand is read from or written to."""

    LOAD = 0
    STORE = 1


@dataclass(frozen=True)
class OperandList:
    """An opcode's operand signature.

    Attributes:
        forms: Each operand's direction, left to right.
        arg_size: The width the indirect modes move -- 4 for
            almost every opcode; copyb and copys narrow it to 1
            and 2 (Glulx: Instruction Format).
    """

    forms: tuple[Form, ...]
    arg_size: int = 4

    def __len__(self) -> int:
        """How many operands the signature carries."""

        return len(self.forms)


def operands(spec: str, arg_size: int = 4) -> OperandList:
    """Build an OperandList from a signature like "LLS".

    Args:
        spec: One letter per operand: L loads, S stores.
        arg_size: The indirect modes' width; see OperandList.

    Returns:
        The signature, ready for decode_operands.
    """

    return OperandList(
        tuple(Form.LOAD if letter == "L" else Form.STORE for letter in spec),
        arg_size,
    )


class StoreTarget(NamedTuple):
    """Where a store operand's value goes, once it is known.

    Attributes:
        desttype: A DestType value -- the same vocabulary call
            stubs speak (Glulx: Call Stubs).
        addr: The address or locals offset that type reads.
    """

    desttype: int
    addr: int


DISCARD = StoreTarget(DestType.DISCARD, 0)
PUSH = StoreTarget(DestType.STACK, 0)

# Hoisted: the decoder tests this once per operand.
_LOAD = Form.LOAD


def decode_opcode(memory: Memory, pc: int) -> tuple[int, int]:
    """Read the opcode number at pc.

    Returns:
        The opcode number and the address just past it.

    Raises:
        GlulxMemoryError: For an opcode running off the map.
    """

    first = memory.read_byte(pc)

    if first < ONE_BYTE_OPCODE_LIMIT:
        return first, pc + 1

    if first < TWO_BYTE_OPCODE_LIMIT:
        return memory.read_short(pc) - TWO_BYTE_OPCODE_BASE, pc + 2

    return memory.read_word(pc) - FOUR_BYTE_OPCODE_BASE, pc + 4


def decode_operands(  # noqa: PLR0912, PLR0915 -- the hot loop stays whole
    memory: Memory,
    stack: Stack,
    pc: int,
    oplist: OperandList,
) -> tuple[list[int | StoreTarget], int]:
    """Decode one instruction's operands, left to right.

    Load operands come back as plain unsigned integers, store
    operands as StoreTargets; the caller tells them apart by the
    same OperandList it passed in. The branching is deliberately
    written out flat rather than factored into helpers: this loop
    runs once per instruction executed, and each call boundary
    removed here was measured to matter in the prior art this
    machine is adopted from.

    Returns:
        The decoded operands and the address just past them.

    Raises:
        GlulxInstructionError: For an addressing mode the spec
            does not define, or a constant mode on a store
            operand (Glulx: Instruction Format).
        GlulxMemoryError: For operand data running off the map.
        GlulxStackError: For a stack mode popping an empty stack,
            or a locals mode outside the frame's segment.
    """

    forms = oplist.forms
    count = len(forms)
    width = oplist.arg_size
    read_short = memory.read_short
    read_word = memory.read_word
    # Single-byte reads dominate -- mode nibbles and byte operands
    # -- so they index the backing store with the bounds test
    # inline; the pc is never negative, having come from masked
    # arithmetic.
    data = memory.data
    endmem = memory.endmem

    # The mode nibbles come first, packed two per byte, then the
    # operand data; both are read in step, from two cursors.
    modeaddr = pc
    pc += (count + 1) // 2

    args: list[int | StoreTarget] = []
    modeval = 0

    for index in range(count):
        if index & 1:
            mode = modeval >> HIGH_NIBBLE_SHIFT
            modeaddr += 1
        else:
            if modeaddr >= endmem:
                raise GlulxMemoryError(_off_the_map(modeaddr))

            modeval = data[modeaddr]
            mode = modeval & MODE_MASK

        group = mode >> GROUP_SHIFT
        size = mode & SIZE_MASK

        if forms[index] is _LOAD:
            if group == CONSTANT_GROUP:
                if size == 0:
                    value = 0
                elif size == 1:
                    if pc >= endmem:
                        raise GlulxMemoryError(_off_the_map(pc))

                    value = sign_extend(data[pc], BYTE_BITS)
                    pc += 1
                elif size == 2:  # noqa: PLR2004 -- the width code itself
                    value = sign_extend(read_short(pc), SHORT_BITS)
                    pc += 2
                else:
                    value = read_word(pc)
                    pc += 4
            elif size == 0:
                if mode != STACK_MODE:
                    raise GlulxInstructionError(_unknown_mode(mode, "load"))

                value = stack.pop()
            else:
                if size == 1:
                    if pc >= endmem:
                        raise GlulxMemoryError(_off_the_map(pc))

                    addr = data[pc]
                    pc += 1
                elif size == 2:  # noqa: PLR2004 -- the width code itself
                    addr = read_short(pc)
                    pc += 2
                else:
                    addr = read_word(pc)
                    pc += 4

                if group == MEMORY_GROUP:
                    value = memory.read(addr, width)
                elif group == LOCAL_GROUP:
                    value = stack.get_local(addr, width)
                else:
                    # Address addition truncates to 32 bits, so a
                    # RAM offset near 0xFFFFFFFF wraps around below
                    # RAMSTART (Glulx: Instruction Format).
                    value = memory.read((addr + memory.ramstart) & WORD_MASK, width)

            args.append(value)

            continue

        if size == 0:
            if mode == 0:
                args.append(DISCARD)
            elif mode == STACK_MODE:
                args.append(PUSH)
            else:
                raise GlulxInstructionError(_unknown_mode(mode, "store"))

            continue

        if group == CONSTANT_GROUP:
            msg = (
                "a constant addressing mode cannot serve a store "
                "operand (Glulx: Instruction Format)"
            )

            raise GlulxInstructionError(msg)

        if size == 1:
            if pc >= endmem:
                raise GlulxMemoryError(_off_the_map(pc))

            addr = data[pc]
            pc += 1
        elif size == 2:  # noqa: PLR2004 -- the width code itself
            addr = read_short(pc)
            pc += 2
        else:
            addr = read_word(pc)
            pc += 4

        if group == MEMORY_GROUP:
            args.append(StoreTarget(DestType.MEMORY, addr))
        elif group == LOCAL_GROUP:
            # DestType 2 is relative to localsbase, not an absolute
            # stack position, so the offset stores as decoded
            # (Glulx: Call Stubs).
            args.append(StoreTarget(DestType.LOCAL, addr))
        else:
            args.append(
                StoreTarget(DestType.MEMORY, (addr + memory.ramstart) & WORD_MASK)
            )

    return args, pc


def store(
    memory: Memory,
    stack: Stack,
    target: StoreTarget | tuple[int, int],
    value: int,
    width: int = 4,
) -> None:
    """Write a value where the target says.

    Call-stub destinations arrive here too, as plain tuples: the
    vocabulary is the same (Glulx: Call Stubs). The width narrows
    only for copyb and copys -- and a narrowed value pushed to the
    stack still lands as a full four-byte word, exactly as the
    reference glulxe's store_operand_s does.

    Raises:
        GlulxInstructionError: For a destination type the spec
            does not define.
        GlulxMemoryError: For a memory destination off the map or
            in ROM.
        GlulxStackError: For a local destination outside the
            frame's segment, or a push overflowing the stack.
    """

    desttype, addr = target
    value &= WIDTH_MASKS[width]

    if desttype == DestType.DISCARD:
        return

    if desttype == DestType.MEMORY:
        memory.write(addr, width, value)
    elif desttype == DestType.LOCAL:
        stack.set_local(addr, value, width)
    elif desttype == DestType.STACK:
        stack.push(value)
    else:
        msg = (
            f"a store reached destination type {desttype}, which the "
            f"spec does not define (Glulx: Call Stubs)"
        )

        raise GlulxInstructionError(msg)


def sign_extend(value: int, bits: int) -> int:
    """The low bits of a value, sign-extended to unsigned 32 bits.

    The value truncates to its low bits first: the operand modes
    feed this already-narrow values, but sexb and sexs pass full
    words and rely on the truncation -- the reference glulxe
    spells that out as an explicit mask.
    """

    mask = (1 << bits) - 1
    sign = 1 << (bits - 1)

    return (((value & mask) ^ sign) - sign) & WORD_MASK


def _off_the_map(address: int) -> str:
    """The message an operand read past the map carries."""

    return f"the address ${address:x} is outside the memory map (Glulx: The Memory Map)"


def _unknown_mode(mode: int, direction: str) -> str:
    """The message an undefined addressing mode carries."""

    return (
        f"addressing mode {mode} in a {direction} operand is not one "
        f"the spec defines (Glulx: Instruction Format)"
    )
