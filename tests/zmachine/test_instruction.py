from collections.abc import Callable

import pytest
from assertpy import assert_that

from voxam.errors import ZMachineInstructionError, ZMachineMemoryError
from voxam.zmachine.instruction import (
    Form,
    Instruction,
    Operand,
    OperandCount,
    OperandType,
)
from voxam.zmachine.memory import Memory
from voxam.zmachine.riders import Branch
from voxam.zmachine.story import Story

ALL_VERSIONS = range(1, 9)

CODE = 0x40
SIZE = 512


def test_records_the_instruction_address(code_memory: Callable[..., Memory]) -> None:
    memory = code_memory(bytes([0x05, 0x10, 0x20]))

    instruction = Instruction.decode(memory, CODE)

    assert_that(instruction.address).is_equal_to(CODE)


def test_decodes_long_form(code_memory: Callable[..., Memory]) -> None:
    # 0x05 = 0b00000101: long form, 2OP, opcode 5 (inc_chk), both
    # operands small constants (bits 6 and 5 are 0), one byte each
    # (§4.3.2, §4.4.2).
    memory = code_memory(bytes([0x05, 0x10, 0x20]))

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
    opcode_byte: int,
    first: OperandType,
    second: OperandType,
    code_memory: Callable[..., Memory],
) -> None:
    memory = code_memory(bytes([opcode_byte, 0x10, 0x20]))

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
    opcode_byte: int,
    operand_bytes: list[int],
    operand: Operand,
    end: int,
    code_memory: Callable[..., Memory],
) -> None:
    memory = code_memory(bytes([opcode_byte, *operand_bytes]))

    instruction = Instruction.decode(memory, CODE)

    assert_that(instruction.form).is_equal_to(Form.SHORT)
    assert_that(instruction.operand_count).is_equal_to(OperandCount.OP1)
    assert_that(instruction.opcode_number).is_equal_to(0xF)
    assert_that(instruction.operands).is_equal_to((operand,))
    assert_that(instruction.operands_end).is_equal_to(CODE + end)


def test_decodes_short_form_0op(code_memory: Callable[..., Memory]) -> None:
    # 0xB0 = 0b10110000: short form with type bits 11, so no operand
    # and a 0OP count (§4.3.1). Opcode 0 is rtrue, which has no riders,
    # so the next address is simply the following byte.
    memory = code_memory(bytes([0xB0]))

    instruction = Instruction.decode(memory, CODE)

    assert_that(instruction.form).is_equal_to(Form.SHORT)
    assert_that(instruction.operand_count).is_equal_to(OperandCount.OP0)
    assert_that(instruction.opcode_number).is_equal_to(0)
    assert_that(instruction.opcode.name).is_equal_to("rtrue")
    assert_that(instruction.operands).is_empty()
    assert_that(instruction.next_address).is_equal_to(CODE + 1)


def test_opcode_190_is_not_an_instruction_before_version_5(
    code_memory: Callable[..., Memory],
) -> None:
    # Below Version 5 the byte 0xBE would parse as short form 0OP:14,
    # a slot §14 deliberately leaves undefined (§4.3).
    memory = code_memory(bytes([0xBE]), version=3)

    with pytest.raises(ZMachineInstructionError, match="0OP:14"):
        Instruction.decode(memory, CODE)


def test_opcode_190_is_extended_form_from_version_5(
    code_memory: Callable[..., Memory],
) -> None:
    # 0xBE, opcode number 0x0B (print_unicode), then type byte 0x6F =
    # 0b01101111: small constant, variable, omitted, omitted (§4.3.4,
    # §4.4.3).
    memory = code_memory(bytes([0xBE, 0x0B, 0x6F, 0x07, 0x42]), version=5)

    instruction = Instruction.decode(memory, CODE)

    assert_that(instruction.form).is_equal_to(Form.EXTENDED)
    assert_that(instruction.operand_count).is_equal_to(OperandCount.VAR)
    assert_that(instruction.opcode_number).is_equal_to(0x0B)
    assert_that(instruction.opcode.name).is_equal_to("print_unicode")
    assert_that(instruction.operands).is_equal_to(
        (
            Operand(OperandType.SMALL_CONSTANT, 0x07),
            Operand(OperandType.VARIABLE, 0x42),
        )
    )
    assert_that(instruction.next_address).is_equal_to(CODE + 5)


def test_decodes_variable_form_var(code_memory: Callable[..., Memory]) -> None:
    # The spec's own example type byte: 0x2F = 0b00101111 means large
    # constant, variable, omitted, omitted (§4.4.3). VAR:0 is call in
    # Version 3, which stores, so a store byte follows the operands.
    memory = code_memory(bytes([0xE0, 0x2F, 0x12, 0x34, 0x05, 0xFF]))

    instruction = Instruction.decode(memory, CODE)

    assert_that(instruction.form).is_equal_to(Form.VARIABLE)
    assert_that(instruction.operand_count).is_equal_to(OperandCount.VAR)
    assert_that(instruction.opcode.name).is_equal_to("call")
    assert_that(instruction.operands).is_equal_to(
        (
            Operand(OperandType.LARGE_CONSTANT, 0x1234),
            Operand(OperandType.VARIABLE, 0x05),
        )
    )
    assert_that(instruction.operands_end).is_equal_to(CODE + 5)
    assert_that(instruction.store_variable).is_equal_to(0xFF)
    assert_that(instruction.next_address).is_equal_to(CODE + 6)


def test_variable_form_2op_can_carry_extra_operands(
    code_memory: Callable[..., Memory],
) -> None:
    # 0xC1 = 0b11000001: variable form with bit 5 clear, so the count
    # is 2OP (§4.3.3) -- but the type byte 0x57 specifies three small
    # constants. This is how "@je a b c" assembles: the operands come
    # from the type byte, not from the count label.
    memory = code_memory(bytes([0xC1, 0x57, 0x01, 0x02, 0x03, 0xC4]))

    instruction = Instruction.decode(memory, CODE)

    assert_that(instruction.form).is_equal_to(Form.VARIABLE)
    assert_that(instruction.operand_count).is_equal_to(OperandCount.OP2)
    assert_that(instruction.opcode.name).is_equal_to("je")
    assert_that(instruction.operands).is_length(3)
    assert_that(instruction.branch).is_equal_to(Branch(True, 4))
    assert_that(instruction.next_address).is_equal_to(CODE + 6)


def test_decodes_a_store_rider(code_memory: Callable[..., Memory]) -> None:
    # 0x16: long form 2OP:22, mul, which stores (§4.6). Operands 3 and
    # 4, result to variable 0x10.
    memory = code_memory(bytes([0x16, 0x03, 0x04, 0x10]))

    instruction = Instruction.decode(memory, CODE)

    assert_that(instruction.opcode.name).is_equal_to("mul")
    assert_that(instruction.store_variable).is_equal_to(0x10)
    assert_that(instruction.branch).is_none()
    assert_that(instruction.text).is_none()
    assert_that(instruction.next_address).is_equal_to(CODE + 4)


def test_decodes_a_branch_rider(code_memory: Callable[..., Memory]) -> None:
    # 0x90: short form 1OP:0, jz, which branches (§4.7). The branch
    # byte 0xC3 means branch-on-true with a short offset of 3.
    memory = code_memory(bytes([0x90, 0x05, 0xC3]))

    instruction = Instruction.decode(memory, CODE)

    assert_that(instruction.opcode.name).is_equal_to("jz")
    assert_that(instruction.branch).is_equal_to(Branch(True, 3))
    assert_that(instruction.store_variable).is_none()
    assert_that(instruction.next_address).is_equal_to(CODE + 3)


def test_decodes_a_text_rider(code_memory: Callable[..., Memory]) -> None:
    # 0xB2: short form 0OP:2, print, whose literal string follows
    # immediately; two words, the second with its top bit set (§3.2).
    memory = code_memory(bytes([0xB2, 0x12, 0x34, 0x94, 0xA5]))

    instruction = Instruction.decode(memory, CODE)

    assert_that(instruction.opcode.name).is_equal_to("print")
    assert_that(instruction.text).is_equal_to((CODE + 1, CODE + 5))
    assert_that(instruction.next_address).is_equal_to(CODE + 5)


def test_decodes_the_double_type_bytes_of_call_vs2(
    code_memory: Callable[..., Memory],
) -> None:
    # 0xEC: variable form VAR:12, call_vs2, which takes a second type
    # byte (§4.4.3.1). The first byte 0x00 gives four large constants;
    # the second, 0x7F = 0b01111111, a fifth small constant. A store
    # byte follows the five operands.
    code = bytes([0xEC, 0x00, 0x7F])
    code += bytes([0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77, 0x88, 0x09])
    code += bytes([0x05])
    memory = code_memory(code, version=4)

    instruction = Instruction.decode(memory, CODE)

    values = [operand.value for operand in instruction.operands]

    assert_that(instruction.opcode.name).is_equal_to("call_vs2")
    assert_that(values).is_equal_to([0x1122, 0x3344, 0x5566, 0x7788, 0x09])
    assert_that(instruction.store_variable).is_equal_to(0x05)
    assert_that(instruction.next_address).is_equal_to(CODE + 13)


def test_decodes_four_large_constants(code_memory: Callable[..., Memory]) -> None:
    # Type byte 0x00: four large constants, two bytes each (§4.4.3).
    code = bytes([0xE0, 0x00, 0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77, 0x88])
    memory = code_memory(code)

    instruction = Instruction.decode(memory, CODE)

    values = [operand.value for operand in instruction.operands]

    assert_that(values).is_equal_to([0x1122, 0x3344, 0x5566, 0x7788])
    assert_that(instruction.operands_end).is_equal_to(CODE + 10)


def test_rejects_operand_specified_after_an_omitted_one(
    code_memory: Callable[..., Memory],
) -> None:
    # Type byte 0xCF = 0b11001111: omitted, then a large constant,
    # which §4.4.3 forbids.
    memory = code_memory(bytes([0xE0, 0xCF]))

    with pytest.raises(ZMachineInstructionError, match="after an omitted"):
        Instruction.decode(memory, CODE)


def test_rejects_numbers_that_are_not_opcodes(
    code_memory: Callable[..., Memory],
) -> None:
    # 0x00 parses as long form 2OP:0, a slot no version defines (§14).
    memory = code_memory(bytes([0x00, 0x01, 0x02]))

    with pytest.raises(ZMachineInstructionError, match="2OP:0 is not"):
        Instruction.decode(memory, CODE)


def test_operands_cannot_run_past_readable_memory(
    code_memory: Callable[..., Memory],
) -> None:
    # The byte at the last readable address decodes as long form with
    # two operands, whose first read falls off the end of the file.
    memory = code_memory(b"")

    with pytest.raises(ZMachineMemoryError, match="game-readable memory"):
        Instruction.decode(memory, SIZE - 1)


# Every fixture's first instruction calls its main routine, storing the
# discarded result to global 0xFF -- and §14's rename of the opcode at
# Version 4 is visible in the decoded name. Version 6 is absent because
# its packed initial address needs §1.2.3 unpacking to follow.
@pytest.mark.parametrize(
    ("version", "name"),
    [
        (1, "call"),
        (2, "call"),
        (3, "call"),
        (4, "call_vs"),
        (5, "call_vs"),
        (7, "call_vs"),
        (8, "call_vs"),
    ],
)
def test_decodes_the_first_real_instruction_of_every_fixture(
    version: int, name: str, load_fixture: Callable[[int], Story]
) -> None:
    memory = Memory(load_fixture(version))
    start = memory.header.initial_program_counter

    instruction = Instruction.decode(memory, start)

    assert_that(instruction.opcode.name).is_equal_to(name)
    assert_that(instruction.store_variable).is_equal_to(0xFF)
    assert_that(instruction.next_address).is_equal_to(start + 5)
