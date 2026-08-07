from collections.abc import Callable

import pytest
from assertpy import assert_that

from voxam.errors import ZMachineInstructionError, ZMachineMemoryError
from voxam.zmachine.header import PACKED_PC_VERSION
from voxam.zmachine.instruction import (
    Form,
    Instruction,
    Operand,
    OperandCount,
    OperandType,
)
from voxam.zmachine.memory import Memory
from voxam.zmachine.story import Story

CODE = 0x40
STATIC_BASE = 0x1C0
SIZE = 512
ALL_VERSIONS = range(1, 9)


def memory_with(code: bytes, version: int = 3) -> Memory:
    data = bytearray(SIZE)
    data[0] = version
    data[0x04:0x06] = STATIC_BASE.to_bytes(2, "big")
    data[0x0E:0x10] = STATIC_BASE.to_bytes(2, "big")
    data[CODE : CODE + len(code)] = code

    return Memory(Story(bytes(data)))


def test_records_the_instruction_address() -> None:
    memory = memory_with(bytes([0x05, 0x10, 0x20]))

    instruction = Instruction.decode(memory, CODE)

    assert_that(instruction.address).is_equal_to(CODE)


def test_decodes_long_form() -> None:
    # 0x05 = 0b00000101: long form, 2OP, opcode 5, both operands small
    # constants (bits 6 and 5 are 0), one byte each (§4.3.2, §4.4.2).
    memory = memory_with(bytes([0x05, 0x10, 0x20]))

    instruction = Instruction.decode(memory, CODE)

    assert_that(instruction.form).is_equal_to(Form.LONG)
    assert_that(instruction.operand_count).is_equal_to(OperandCount.OP2)
    assert_that(instruction.opcode_number).is_equal_to(5)
    assert_that(instruction.operands).is_equal_to(
        (
            Operand(OperandType.SMALL_CONSTANT, 0x10),
            Operand(OperandType.SMALL_CONSTANT, 0x20),
        )
    )
    assert_that(instruction.operands_end).is_equal_to(CODE + 3)


# Bits 6 and 5 of a long-form opcode type the first and second operand:
# 0 means small constant, 1 means variable (§4.4.2).
@pytest.mark.parametrize(
    ("opcode_byte", "first", "second"),
    [
        (0x05, OperandType.SMALL_CONSTANT, OperandType.SMALL_CONSTANT),
        (0x25, OperandType.SMALL_CONSTANT, OperandType.VARIABLE),
        (0x45, OperandType.VARIABLE, OperandType.SMALL_CONSTANT),
        (0x65, OperandType.VARIABLE, OperandType.VARIABLE),
    ],
)
def test_long_form_types_come_from_bits_6_and_5(
    opcode_byte: int, first: OperandType, second: OperandType
) -> None:
    memory = memory_with(bytes([opcode_byte, 0x10, 0x20]))

    instruction = Instruction.decode(memory, CODE)

    assert_that(instruction.operands[0].kind).is_equal_to(first)
    assert_that(instruction.operands[1].kind).is_equal_to(second)


# In short form, bits 4 and 5 hold the operand type and the bottom four
# bits the opcode number (§4.3.1, §4.4.1).
@pytest.mark.parametrize(
    ("opcode_byte", "operand_bytes", "operand", "end"),
    [
        (0x8F, [0x12, 0x34], Operand(OperandType.LARGE_CONSTANT, 0x1234), 3),
        (0x9F, [0x07], Operand(OperandType.SMALL_CONSTANT, 0x07), 2),
        (0xAF, [0x42], Operand(OperandType.VARIABLE, 0x42), 2),
    ],
)
def test_decodes_short_form_1op(
    opcode_byte: int, operand_bytes: list[int], operand: Operand, end: int
) -> None:
    memory = memory_with(bytes([opcode_byte, *operand_bytes]))

    instruction = Instruction.decode(memory, CODE)

    assert_that(instruction.form).is_equal_to(Form.SHORT)
    assert_that(instruction.operand_count).is_equal_to(OperandCount.OP1)
    assert_that(instruction.opcode_number).is_equal_to(0xF)
    assert_that(instruction.operands).is_equal_to((operand,))
    assert_that(instruction.operands_end).is_equal_to(CODE + end)


def test_decodes_short_form_0op() -> None:
    # 0xB0 = 0b10110000: short form with type bits 11, so no operand
    # and a 0OP count (§4.3.1).
    memory = memory_with(bytes([0xB0]))

    instruction = Instruction.decode(memory, CODE)

    assert_that(instruction.form).is_equal_to(Form.SHORT)
    assert_that(instruction.operand_count).is_equal_to(OperandCount.OP0)
    assert_that(instruction.opcode_number).is_equal_to(0)
    assert_that(instruction.operands).is_empty()
    assert_that(instruction.operands_end).is_equal_to(CODE + 1)


def test_opcode_190_is_short_form_before_version_5() -> None:
    memory = memory_with(bytes([0xBE]), version=3)

    instruction = Instruction.decode(memory, CODE)

    assert_that(instruction.form).is_equal_to(Form.SHORT)
    assert_that(instruction.operand_count).is_equal_to(OperandCount.OP0)
    assert_that(instruction.opcode_number).is_equal_to(0xE)


def test_opcode_190_is_extended_form_from_version_5() -> None:
    # 0xBE, opcode number 0x0B, then type byte 0x6F = 0b01101111: small
    # constant, variable, omitted, omitted (§4.3.4, §4.4.3).
    memory = memory_with(bytes([0xBE, 0x0B, 0x6F, 0x07, 0x42]), version=5)

    instruction = Instruction.decode(memory, CODE)

    assert_that(instruction.form).is_equal_to(Form.EXTENDED)
    assert_that(instruction.operand_count).is_equal_to(OperandCount.VAR)
    assert_that(instruction.opcode_number).is_equal_to(0x0B)
    assert_that(instruction.operands).is_equal_to(
        (
            Operand(OperandType.SMALL_CONSTANT, 0x07),
            Operand(OperandType.VARIABLE, 0x42),
        )
    )
    assert_that(instruction.operands_end).is_equal_to(CODE + 5)


def test_decodes_variable_form_var() -> None:
    # The spec's own example type byte: 0x2F = 0b00101111 means large
    # constant, variable, omitted, omitted (§4.4.3).
    memory = memory_with(bytes([0xE0, 0x2F, 0x12, 0x34, 0x05]))

    instruction = Instruction.decode(memory, CODE)

    assert_that(instruction.form).is_equal_to(Form.VARIABLE)
    assert_that(instruction.operand_count).is_equal_to(OperandCount.VAR)
    assert_that(instruction.opcode_number).is_equal_to(0)
    assert_that(instruction.operands).is_equal_to(
        (
            Operand(OperandType.LARGE_CONSTANT, 0x1234),
            Operand(OperandType.VARIABLE, 0x05),
        )
    )
    assert_that(instruction.operands_end).is_equal_to(CODE + 5)


# 0xC1 = 0b11000001: variable form with bit 5 clear, so the count
# is 2OP (§4.3.3) -- but the type byte 0x57 specifies three small
# constants. This is how "@je a b c" assembles: the operands come
# from the type byte, not from the count label.
def test_variable_form_2op_can_carry_extra_operands() -> None:
    memory = memory_with(bytes([0xC1, 0x57, 0x01, 0x02, 0x03]))
    instruction = Instruction.decode(memory, CODE)

    assert_that(instruction.form).is_equal_to(Form.VARIABLE)
    assert_that(instruction.operand_count).is_equal_to(OperandCount.OP2)
    assert_that(instruction.opcode_number).is_equal_to(1)
    assert_that(instruction.operands).is_length(3)
    assert_that(instruction.operands_end).is_equal_to(CODE + 5)


def test_decodes_four_large_constants() -> None:
    # Type byte 0x00: four large constants, two bytes each (§4.4.3).
    code = bytes([0xE0, 0x00, 0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77, 0x88])
    memory = memory_with(code)

    instruction = Instruction.decode(memory, CODE)

    values = [operand.value for operand in instruction.operands]

    assert_that(values).is_equal_to([0x1122, 0x3344, 0x5566, 0x7788])
    assert_that(instruction.operands_end).is_equal_to(CODE + 10)


def test_rejects_operand_specified_after_an_omitted_one() -> None:
    # Type byte 0xCF = 0b11001111: omitted, then a large constant,
    # which §4.4.3 forbids.
    memory = memory_with(bytes([0xE0, 0xCF]))

    with pytest.raises(ZMachineInstructionError, match="after an omitted"):
        Instruction.decode(memory, CODE)


# The byte at the last readable address decodes as long form with
# two operands, whose first read falls off the end of the file.
def test_operands_cannot_run_past_readable_memory() -> None:
    memory = memory_with(b"")

    with pytest.raises(ZMachineMemoryError, match="game-readable memory"):
        Instruction.decode(memory, SIZE - 1)


@pytest.mark.parametrize("version", [v for v in ALL_VERSIONS if v != PACKED_PC_VERSION])
def test_decodes_the_first_real_instruction_of_every_fixture(
    version: int, load_fixture: Callable[[int], Story]
) -> None:
    memory = Memory(load_fixture(version))
    start = memory.header.initial_program_counter

    instruction = Instruction.decode(memory, start)

    assert_that(instruction.form).is_instance_of(Form)
    assert_that(instruction.operands_end).is_greater_than(start)
