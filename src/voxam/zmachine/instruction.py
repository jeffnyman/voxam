"""Decoding the operand portion of Z-Machine instructions (§4).

An instruction is opcode, operand types, operands, and then riders --
store variable, branch offset, text -- whose presence depends on which
opcode it is (§4.1). This module decodes everything up to the riders,
which is exactly the part determined by bit patterns alone.
"""

from dataclasses import dataclass
from enum import Enum, auto
from typing import Self

from voxam.errors import ZMachineInstructionError
from voxam.zmachine.memory import Memory

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
    """The operand portion of a single decoded instruction (§4.1).

    Store variables, branch offsets, and instruction text depend on
    which opcode this is, so they are not decoded here. That makes
    operands_end the address where any riders would begin, not
    necessarily where the instruction ends (§4.1).

    Attributes:
        address: The byte address the instruction begins at.
        form: The instruction form (§4.3).
        operand_count: The operand count label (§4.3).
        opcode_number: The opcode number within that count (§4.3).
        operands: The decoded operands, in the order given (§4.5.2).
        operands_end: The first byte address past the operands.
    """

    address: int
    form: Form
    operand_count: OperandCount
    opcode_number: int
    operands: tuple[Operand, ...]
    operands_end: int

    @classmethod
    def decode(cls, memory: Memory, address: int) -> Self:
        """Decode the instruction beginning at an address (§4.1).

        Args:
            memory: The memory image holding the instruction.
            address: The byte address of its opcode.

        Returns:
            The decoded operand portion of the instruction.

        Raises:
            ZMachineInstructionError: If a type byte specifies an
                operand after an omitted one (§4.4.3).
            ZMachineMemoryError: If the instruction runs outside the
                game-readable regions.
        """

        opcode_byte = memory.read_byte(address)
        version = memory.header.version
        pos = address + 1

        if opcode_byte == EXTENDED_OPCODE and version >= EXTENDED_MIN_VERSION:
            form = Form.EXTENDED
            operand_count = OperandCount.VAR
            opcode_number = memory.read_byte(pos)
            kinds = _field_types(memory.read_byte(pos + 1))

            pos += 2
        elif opcode_byte & FORM_MASK == VARIABLE_FORM_BITS:
            form = Form.VARIABLE
            operand_count = (
                OperandCount.VAR if opcode_byte & VAR_COUNT_BIT else OperandCount.OP2
            )
            opcode_number = opcode_byte & BOTTOM_FIVE_MASK
            kinds = _field_types(memory.read_byte(pos))

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

        return cls(
            address=address,
            form=form,
            operand_count=operand_count,
            opcode_number=opcode_number,
            operands=operands,
            operands_end=operands_end,
        )


def _field_types(type_byte: int) -> tuple[OperandType, ...]:
    """Split a type byte into its operand types, first field first (§4.4.3).

    Args:
        type_byte: The byte of four 2-bit type fields.

    Returns:
        The specified types, without the omitted tail.

    Raises:
        ZMachineInstructionError: If a field specifies an operand after
            an omitted one, which §4.4.3 forbids.
    """

    fields = [
        OperandType((type_byte >> shift) & TYPE_MASK) for shift in TYPE_FIELD_SHIFTS
    ]

    omitted_from = None

    for position, kind in enumerate(fields):
        if kind is OperandType.OMITTED:
            omitted_from = position if omitted_from is None else omitted_from
        elif omitted_from is not None:
            msg = (
                f"type byte ${type_byte:02x} specifies an operand after "
                f"an omitted one (§4.4.3)"
            )

            raise ZMachineInstructionError(msg)

    return tuple(fields[: len(fields) if omitted_from is None else omitted_from])


def _long_type(bit: int) -> OperandType:
    """Map a long-form type bit: 0 is small constant, 1 is variable (§4.4.2)."""

    return OperandType.VARIABLE if bit else OperandType.SMALL_CONSTANT


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
            operands.append(Operand(kind, memory.read_word(pos)))
            pos += 2
        else:
            operands.append(Operand(kind, memory.read_byte(pos)))
            pos += 1

    return tuple(operands), pos
