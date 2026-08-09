"""Decoding complete Z-Machine instructions (§4).

An instruction is opcode, operand types, operands, and then riders --
store variable, branch offset, text -- whose presence depends on which
opcode it is (§4.1). The bit patterns determine everything up to the
riders; the opcode tables (§14) supply the knowledge of what follows.
"""

from dataclasses import dataclass
from enum import Enum, auto
from typing import Self

from voxam.errors import ZMachineInstructionError
from voxam.zmachine.memory import Memory
from voxam.zmachine.opcodes import Opcode, OpcodeKind, lookup
from voxam.zmachine.riders import (
    Branch,
    read_branch,
    read_store_variable,
    text_end,
)

# The top two bits of the opcode byte select the form (§4.3).
FORM_MASK = 0b1100_0000
VARIABLE_FORM_BITS = 0b1100_0000
SHORT_FORM_BITS = 0b1000_0000

# Where each form keeps its opcode number (§4.3.1, §4.3.2, §4.3.3).
BOTTOM_FIVE_MASK = 0b0001_1111
BOTTOM_FOUR_MASK = 0b0000_1111

# In variable form, bit 5 chooses between 2OP and VAR (§4.3.3).
VAR_COUNT_BIT = 0b0010_0000

# Opcode 190 in Version 5 or later begins an extended-form instruction
# (§4.3); below Version 5 the same byte is ordinary short form.
EXTENDED_OPCODE = 0xBE
EXTENDED_MIN_VERSION = 5

# In short form, bits 4 and 5 hold the operand type (§4.4.1). In long
# form, bit 6 types the first operand and bit 5 the second (§4.4.2).
SHORT_TYPE_SHIFT = 4
LONG_FIRST_TYPE_BIT = 0b0100_0000
LONG_SECOND_TYPE_BIT = 0b0010_0000

# A type byte holds four 2-bit fields, first field in bits 7 and 6,
# fourth in bits 1 and 0 (§4.4.3).
TYPE_FIELD_SHIFTS = (6, 4, 2, 0)
TYPE_MASK = 0b11

# call_vs2 (VAR:12) and call_vn2 (VAR:26) take a second type byte for
# operands five through eight (§4.4.3.1).
DOUBLE_TYPE_OPCODES = (0x0C, 0x1A)


class Form(Enum):
    """The four instruction forms (§4.3)."""

    LONG = auto()
    SHORT = auto()
    VARIABLE = auto()
    EXTENDED = auto()


class OperandCount(Enum):
    """The four operand counts (§4.3)."""

    OP0 = auto()
    OP1 = auto()
    OP2 = auto()
    VAR = auto()


class OperandType(Enum):
    """The operand types, valued by their 2-bit codes (§4.2)."""

    LARGE_CONSTANT = 0b00
    SMALL_CONSTANT = 0b01
    VARIABLE = 0b10
    OMITTED = 0b11


@dataclass(frozen=True)
class Operand:
    """A decoded operand: how it was encoded and its raw value (§4.2).

    Attributes:
        kind: The operand type, which is also how the value must later
            be interpreted. Called a "kind" here because Python uses
            `type` as a builtin.
        value: The raw value. For a VARIABLE operand this is a variable
            number, not yet that variable's contents (§4.2.2).
    """

    kind: OperandType
    value: int


@dataclass(frozen=True)
class Instruction:
    """A single fully decoded instruction (§4.1).

    Attributes:
        address: The byte address the instruction begins at.
        form: The instruction form (§4.3).
        operand_count: The operand count label (§4.3).
        opcode_number: The opcode number within that count (§4.3).
        opcode: What §14 knows about the opcode: its name and which
            riders it carries.
        operands: The decoded operands, in the order given (§4.5.2).
        operands_end: The first byte address past the operands, where
            the riders begin.
        store_variable: The variable number a result goes to, when the
            opcode stores (§4.6).
        branch: The branch rider, when the opcode branches (§4.7).
        text: The byte span of the literal string, when the opcode
            carries one (§3.2).
        next_address: The first byte address past the whole
            instruction: where execution continues.
    """

    address: int
    form: Form
    operand_count: OperandCount
    opcode_number: int
    opcode: Opcode
    operands: tuple[Operand, ...]
    operands_end: int
    store_variable: int | None
    branch: Branch | None
    text: tuple[int, int] | None
    next_address: int

    @classmethod
    def decode(cls, memory: Memory, address: int) -> Self:
        """Decode the instruction beginning at an address (§4.1).

        Args:
            memory: The memory image holding the instruction.
            address: The byte address of its opcode.

        Returns:
            The decoded instruction.

        Raises:
            ZMachineInstructionError: If a type byte specifies an
                operand after an omitted one (§4.4.3), or no opcode is
                defined for the decoded number in this version (§14).
            ZMachineMemoryError: If the instruction runs outside the
                story file (§1.1).
        """

        opcode_byte = memory.fetch_byte(address)
        version = memory.header.version
        pos = address + 1

        if opcode_byte == EXTENDED_OPCODE and version >= EXTENDED_MIN_VERSION:
            form = Form.EXTENDED
            operand_count = OperandCount.VAR
            opcode_number = memory.fetch_byte(pos)
            kinds = _field_types(memory.fetch_byte(pos + 1))

            pos += 2
        elif opcode_byte & FORM_MASK == VARIABLE_FORM_BITS:
            form = Form.VARIABLE
            operand_count = (
                OperandCount.VAR if opcode_byte & VAR_COUNT_BIT else OperandCount.OP2
            )
            opcode_number = opcode_byte & BOTTOM_FIVE_MASK

            if (
                operand_count is OperandCount.VAR
                and opcode_number in DOUBLE_TYPE_OPCODES
            ):
                kinds = _field_types(memory.fetch_byte(pos), memory.fetch_byte(pos + 1))

                pos += 2
            else:
                kinds = _field_types(memory.fetch_byte(pos))

                pos += 1
        elif opcode_byte & FORM_MASK == SHORT_FORM_BITS:
            form = Form.SHORT
            kind = OperandType((opcode_byte >> SHORT_TYPE_SHIFT) & TYPE_MASK)
            omitted = kind is OperandType.OMITTED
            operand_count = OperandCount.OP0 if omitted else OperandCount.OP1
            opcode_number = opcode_byte & BOTTOM_FOUR_MASK
            kinds = () if omitted else (kind,)
        else:
            form = Form.LONG
            operand_count = OperandCount.OP2
            opcode_number = opcode_byte & BOTTOM_FIVE_MASK
            kinds = (
                _long_type(opcode_byte & LONG_FIRST_TYPE_BIT),
                _long_type(opcode_byte & LONG_SECOND_TYPE_BIT),
            )

        operands, operands_end = _read_operands(memory, pos, kinds)
        opcode = lookup(_opcode_kind(form, operand_count), opcode_number, version)
        store_variable, branch, text, next_address = _read_riders(
            memory, operands_end, opcode
        )

        return cls(
            address=address,
            form=form,
            operand_count=operand_count,
            opcode_number=opcode_number,
            opcode=opcode,
            operands=operands,
            operands_end=operands_end,
            store_variable=store_variable,
            branch=branch,
            text=text,
            next_address=next_address,
        )


def _field_types(*type_bytes: int) -> tuple[OperandType, ...]:
    """Split type bytes into their operand types, first field first (§4.4.3).

    The double-variable opcodes pass two bytes here, giving eight
    fields; the omitted-tail rule then applies across both (§4.4.3.1).

    Args:
        type_bytes: One or two bytes of four 2-bit type fields each.

    Returns:
        The specified types, without the omitted tail.

    Raises:
        ZMachineInstructionError: If a field specifies an operand after
            an omitted one, which §4.4.3 forbids.
    """

    fields = [
        OperandType((type_byte >> shift) & TYPE_MASK)
        for type_byte in type_bytes
        for shift in TYPE_FIELD_SHIFTS
    ]

    omitted_from = None

    for position, kind in enumerate(fields):
        if kind is OperandType.OMITTED:
            omitted_from = position if omitted_from is None else omitted_from
        elif omitted_from is not None:
            shown = " ".join(f"${type_byte:02x}" for type_byte in type_bytes)
            msg = f"type bytes {shown} specify an operand after an omitted one (§4.4.3)"

            raise ZMachineInstructionError(msg)

    return tuple(fields[: len(fields) if omitted_from is None else omitted_from])


def _long_type(bit: int) -> OperandType:
    """Map a long-form type bit: 0 is small constant, 1 is variable (§4.4.2)."""

    return OperandType.VARIABLE if bit else OperandType.SMALL_CONSTANT


_KIND_BY_COUNT = {
    OperandCount.OP0: OpcodeKind.ZERO_OP,
    OperandCount.OP1: OpcodeKind.ONE_OP,
    OperandCount.OP2: OpcodeKind.TWO_OP,
    OperandCount.VAR: OpcodeKind.VAR,
}


def _opcode_kind(form: Form, operand_count: OperandCount) -> OpcodeKind:
    """Pick the §14 table: extended form has its own, all else by count."""

    if form is Form.EXTENDED:
        return OpcodeKind.EXT

    return _KIND_BY_COUNT[operand_count]


def _read_riders(
    memory: Memory, pos: int, opcode: Opcode
) -> tuple[int | None, Branch | None, tuple[int, int] | None, int]:
    """Read whichever riders the opcode declares, in §4.1 order.

    Args:
        memory: The memory image holding the instruction.
        pos: The first byte address past the operands.
        opcode: The table knowledge saying which riders are present.

    Returns:
        The store variable, branch, text span, and the first address
        past the whole instruction.
    """

    store_variable = None
    branch = None
    text = None

    if opcode.stores:
        store_variable, pos = read_store_variable(memory, pos)

    if opcode.branches:
        branch, pos = read_branch(memory, pos)

    if opcode.has_text:
        end = text_end(memory, pos)
        text = (pos, end)
        pos = end

    return store_variable, branch, text, pos


def _read_operands(
    memory: Memory, pos: int, kinds: tuple[OperandType, ...]
) -> tuple[tuple[Operand, ...], int]:
    """Read operand values of the given types starting at pos (§4.5).

    Args:
        memory: The memory image holding the operands.
        pos: The byte address of the first operand.
        kinds: The operand types, none of them omitted.

    Returns:
        The decoded operands and the first address past them.
    """

    operands = []

    for kind in kinds:
        if kind is OperandType.LARGE_CONSTANT:
            operands.append(Operand(kind, memory.fetch_word(pos)))
            pos += 2
        else:
            operands.append(Operand(kind, memory.fetch_byte(pos)))
            pos += 1

    return tuple(operands), pos
