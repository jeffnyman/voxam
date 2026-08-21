"""Operand decoding: sixteen modes, one discipline (Glulx: Instruction Format)."""

from collections.abc import Callable

import pytest
from assertpy import assert_that

from voxam.errors import GlulxInstructionError, GlulxMemoryError
from voxam.glulx.memory import Memory
from voxam.glulx.operand import (
    DISCARD,
    PUSH,
    Form,
    StoreTarget,
    decode_opcode,
    decode_operands,
    operands,
    sign_extend,
    store,
)
from voxam.glulx.stack import DestType, LocalsFormat, Stack
from voxam.glulx.story import Story

PC = 0x100


def rig(image: Callable[..., bytes], plant: bytes) -> tuple[Memory, Stack]:
    """A memory with instruction bytes planted at $100, and a stack."""

    memory = Memory(Story(image()))

    memory.write_run(PC, plant)

    return memory, Stack(0x200)


# An opcode number carries its own length in its top bits: 01,
# 8123, and C0000102 are one, two, and four bytes long.
def test_opcode_numbers_carry_their_own_length(image: Callable[..., bytes]) -> None:
    memory, _ = rig(image, bytes([0x70, 0x81, 0x23, 0xC0, 0x00, 0x01, 0x02]))

    assert_that(decode_opcode(memory, PC)).is_equal_to((0x70, PC + 1))
    assert_that(decode_opcode(memory, PC + 1)).is_equal_to((0x123, PC + 3))
    assert_that(decode_opcode(memory, PC + 3)).is_equal_to((0x102, PC + 7))


# The signature builder: L loads, S stores, and the width rides
# along for copyb and copys.
def test_the_signature_builder_reads_its_letters() -> None:
    signature = operands("LLS")

    assert_that(signature.forms).is_equal_to((Form.LOAD, Form.LOAD, Form.STORE))
    assert_that(len(signature)).is_equal_to(3)
    assert_that(signature.arg_size).is_equal_to(4)
    assert_that(operands("L", arg_size=1).arg_size).is_equal_to(1)


# The constant modes: zero from nowhere, and byte and short
# constants sign-extended to the unsigned 32-bit values the whole
# machine trades in -- the discipline enforced here and nowhere
# else.
def test_constant_modes_sign_extend_to_unsigned_words(
    image: Callable[..., bytes],
) -> None:
    plant = bytes([0x10, 0x32, 0xFF, 0x80, 0x00, 0xDE, 0xAD, 0xBE, 0xEF])
    memory, stack = rig(image, plant)

    args, after = decode_operands(memory, stack, PC, operands("LLLL"))

    assert_that(args).is_equal_to([0, 0xFFFFFFFF, 0xFFFF8000, 0xDEADBEEF])
    assert_that(after).is_equal_to(PC + 9)


# The memory modes read through main memory at the operand's width,
# their addresses one, two, or four bytes wide.
def test_memory_modes_read_through_main_memory(image: Callable[..., bytes]) -> None:
    plant = bytes([0x65, 0x07, 0x00, 0x01, 0x80, 0x00, 0x00, 0x01, 0x80])
    memory, stack = rig(image, plant)

    memory.write_word(0x180, 0x11223344)

    args, _ = decode_operands(memory, stack, PC, operands("LLL"))

    assert_that(args).is_equal_to([0x476C756C, 0x11223344, 0x11223344])


# Mode 8 pops the stack -- and operands evaluate left to right,
# which the spec calls out precisely because of this mode.
def test_the_stack_mode_pops_left_to_right(image: Callable[..., bytes]) -> None:
    memory, stack = rig(image, bytes([0x88]))

    stack.push(111)
    stack.push(222)

    args, _ = decode_operands(memory, stack, PC, operands("LL"))

    assert_that(args).is_equal_to([222, 111])


# The locals modes read the current frame by offset, and the RAM
# modes add RAMSTART -- with the addition truncated to 32 bits, so
# an offset near 0xFFFFFFFF wraps below RAMSTART, exactly as the
# spec's own example walks through.
def test_locals_and_ram_modes_offset_their_bases(
    image: Callable[..., bytes],
) -> None:
    plant = bytes([0xD9, 0x0F, 0x04, 0x80, 0xFF, 0xFF, 0xFF, 0x00])
    memory, stack = rig(image, plant)

    memory.write_word(0x180, 0x11223344)
    stack.push_frame((LocalsFormat(4, 4),))
    stack.set_local(4, 0xCAFE)

    args, _ = decode_operands(memory, stack, PC, operands("LLL"))

    assert_that(args).is_equal_to([0xCAFE, 0x11223344, 0x476C756C])


# Store operands come back as targets in the call stubs' own
# vocabulary: throwaway, push, memory, local offset, and RAM with
# RAMSTART added.
def test_store_operands_become_targets(image: Callable[..., bytes]) -> None:
    plant = bytes([0x80, 0x95, 0x0D, 0x20, 0x04, 0x80])
    memory, stack = rig(image, plant)

    args, _ = decode_operands(memory, stack, PC, operands("SSSSS"))

    assert_that(args).is_equal_to(
        [
            DISCARD,
            PUSH,
            StoreTarget(DestType.MEMORY, 0x20),
            StoreTarget(DestType.LOCAL, 0x04),
            StoreTarget(DestType.MEMORY, 0x180),
        ]
    )

    wide, wider = rig(image, bytes([0xF6, 0x01, 0x80, 0x00, 0x00, 0x00, 0x40]))
    args, _ = decode_operands(wide, wider, PC, operands("SS"))

    assert_that(args).is_equal_to(
        [
            StoreTarget(DestType.MEMORY, 0x180),
            StoreTarget(DestType.MEMORY, 0x140),
        ]
    )


# The modes the spec does not define halt loudly, in both
# directions -- and a constant can never serve a store.
def test_undefined_modes_halt_loudly(image: Callable[..., bytes]) -> None:
    for mode, signature in ((0x04, "L"), (0x0C, "L"), (0x04, "S"), (0x0C, "S")):
        memory, stack = rig(image, bytes([mode]))

        with pytest.raises(GlulxInstructionError, match="not one the spec defines"):
            decode_operands(memory, stack, PC, operands(signature))

    memory, stack = rig(image, bytes([0x01, 0x2A]))

    with pytest.raises(GlulxInstructionError, match="constant addressing mode"):
        decode_operands(memory, stack, PC, operands("S"))


# copyb's narrowed signature reads indirect operands at one byte.
def test_a_narrowed_signature_reads_at_its_width(
    image: Callable[..., bytes],
) -> None:
    memory, stack = rig(image, bytes([0x05, 0x00]))

    args, _ = decode_operands(memory, stack, PC, operands("L", arg_size=1))

    assert_that(args).is_equal_to([ord("G")])


# Operand bytes that run off the map halt loudly at every cursor:
# the mode nibbles, a constant's byte, and an address byte in each
# direction.
def test_operands_off_the_map_are_loud(image: Callable[..., bytes]) -> None:
    memory = Memory(Story(image()))
    stack = Stack(0x200)

    with pytest.raises(GlulxMemoryError, match="outside the memory map"):
        decode_operands(memory, stack, 0x300, operands("L"))

    for mode, signature in ((0x01, "L"), (0x05, "L"), (0x05, "S")):
        edged = Memory(Story(image()))

        edged.write_byte(0x2FF, mode)

        with pytest.raises(GlulxMemoryError, match="outside the memory map"):
            decode_operands(edged, stack, 0x2FF, operands(signature))


# store() speaks every destination: memory at width, locals,
# pushes -- a narrowed value still pushing as a full word, per
# glulxe's own store_operand_s -- silent discards, and a loud
# refusal for types the spec does not define. Call-stub tuples
# serve as targets too.
def test_store_speaks_every_destination(image: Callable[..., bytes]) -> None:
    memory, stack = rig(image, b"")

    stack.push_frame((LocalsFormat(4, 2),))
    store(memory, stack, StoreTarget(DestType.MEMORY, 0x140), 0x1_2222_3333)
    store(memory, stack, (int(DestType.LOCAL), 4), 7)
    store(memory, stack, PUSH, 0x1AB, width=1)
    store(memory, stack, DISCARD, 9)

    assert_that(memory.read_word(0x140)).is_equal_to(0x2222_3333)
    assert_that(stack.get_local(4)).is_equal_to(7)
    assert_that(stack.pop()).is_equal_to(0xAB)

    with pytest.raises(GlulxInstructionError, match="destination type 7"):
        store(memory, stack, (7, 0), 1)


# sign_extend truncates first -- sexb and sexs hand it full words
# and rely on that -- then widens the sign to unsigned 32 bits.
def test_sign_extend_truncates_then_widens() -> None:
    assert_that(sign_extend(0x7F, 8)).is_equal_to(0x7F)
    assert_that(sign_extend(0xFF, 8)).is_equal_to(0xFFFFFFFF)
    assert_that(sign_extend(0x1234_5680, 8)).is_equal_to(0xFFFFFF80)
    assert_that(sign_extend(0x8000, 16)).is_equal_to(0xFFFF8000)
    assert_that(sign_extend(0x7FFF, 16)).is_equal_to(0x7FFF)
