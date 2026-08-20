"""The Glulx stack: frames, locals, stubs (Glulx: The Call Frame)."""

from collections.abc import Callable

import pytest
from assertpy import assert_that

from voxam.errors import GlulxStackError
from voxam.glulx.stack import CallStub, DestType, LocalsFormat, Stack


# The string-resume DestTypes are hexadecimal: the spec prints "10"
# through "14" bare in a document that writes hex bare everywhere
# else, and both reference implementations -- glulxe and quixe --
# switch on 0x10 through 0x14 (Glulx: Call Stubs).
def test_the_dest_types_read_the_spec_in_hex() -> None:
    assert_that(list(DestType)).is_equal_to([0, 1, 2, 3, 0x10, 0x11, 0x12, 0x13, 0x14])


# The stack must stand a multiple of 256 tall, at least 256.
def test_the_stack_is_raised_on_the_256_byte_convenience() -> None:
    assert_that(Stack(0x100).size).is_equal_to(0x100)

    for wrong in (0x80, 0x120):
        with pytest.raises(GlulxStackError, match="multiple of 256"):
            Stack(wrong)


# Values push masked to 32 bits and pop in reverse; peek reads at
# depth without popping; count answers stkcount. The edges are
# loud: overflow at the top, and pops or peeks that would eat the
# call frame below.
def test_pushes_pops_and_peeks_hold_their_edges() -> None:
    stack = Stack(0x100)

    stack.push(0x1_2345_6789)
    stack.push(2)

    assert_that(stack.count).is_equal_to(2)
    assert_that(stack.peek()).is_equal_to(2)
    assert_that(stack.peek(1)).is_equal_to(0x2345_6789)
    assert_that(stack.pop()).is_equal_to(2)
    assert_that(stack.pop()).is_equal_to(0x2345_6789)

    with pytest.raises(GlulxStackError, match="underflowed"):
        stack.pop()

    with pytest.raises(GlulxStackError, match="peek"):
        stack.peek()

    for _ in range(0x40):
        stack.push(7)

    with pytest.raises(GlulxStackError, match="overflowed"):
        stack.push(8)


# The raw accessors read and write bytes, shorts, and words -- but
# unlike main memory, only at their natural alignments, and every
# violation names itself.
def test_raw_access_is_aligned_or_loud() -> None:
    stack = Stack(0x100)

    stack.write_byte(1, 0x1FF)
    stack.write_short(2, 0x12345)
    stack.write_word(4, 0x1_FFFF_FFFF)
    stack.write(8, 1, 7)
    stack.write(10, 2, 8)
    stack.write(12, 4, 9)

    assert_that(stack.read_byte(1)).is_equal_to(0xFF)
    assert_that(stack.read_short(2)).is_equal_to(0x2345)
    assert_that(stack.read_word(4)).is_equal_to(0xFFFFFFFF)
    assert_that(stack.read(8, 1)).is_equal_to(7)
    assert_that(stack.read(10, 2)).is_equal_to(8)
    assert_that(stack.read(12, 4)).is_equal_to(9)

    unaligned: tuple[Callable[[], object], ...] = (
        lambda: stack.read_short(3),
        lambda: stack.read_word(2),
        lambda: stack.write_short(3, 1),
        lambda: stack.write_word(2, 1),
    )

    for access in unaligned:
        with pytest.raises(GlulxStackError, match="natural alignment"):
            access()

    outside: tuple[Callable[[], object], ...] = (
        lambda: stack.read_byte(0x100),
        lambda: stack.read_byte(-1),
        lambda: stack.read_short(0x100),
        lambda: stack.read_word(0x100),
        lambda: stack.write_byte(0x100, 1),
        lambda: stack.write_short(0x100, 1),
        lambda: stack.write_word(0x100, 1),
    )

    for access in outside:
        with pytest.raises(GlulxStackError, match="off the"):
            access()


# A frame lays down its header, its format list -- zero-terminated,
# padded to keep the words aligned -- and its zeroed locals, each
# run padded up to its own natural alignment (Glulx: The Call
# Frame). The readback returns exactly what was declared.
def test_a_frame_lays_down_by_the_spec() -> None:
    stack = Stack(0x100)

    stack.push_frame((LocalsFormat(4, 2), LocalsFormat(1, 3)))

    assert_that(stack.frameptr).is_equal_to(0)
    assert_that(stack.locals_pos).is_equal_to(16)
    assert_that(stack.frame_len).is_equal_to(28)
    assert_that(stack.localsbase).is_equal_to(16)
    assert_that(stack.valstackbase).is_equal_to(28)
    assert_that(stack.sp).is_equal_to(28)
    assert_that(stack.locals_length).is_equal_to(12)
    assert_that(stack.locals_format()).is_equal_to(
        (LocalsFormat(4, 2), LocalsFormat(1, 3))
    )
    assert_that(stack.count).is_equal_to(0)

    lone = Stack(0x100)

    lone.push_frame((LocalsFormat(4, 1),))

    # One declared pair plus the terminator is already even: no
    # padding pair, so the locals start at 8 + 4.
    assert_that(lone.locals_pos).is_equal_to(12)


# Locals read and write by offset from localsbase, masked to their
# width -- and the segment's edges are real: the spec's "must not
# point outside" is a check here, where glulxe leaves it a remark.
def test_locals_live_within_their_segment() -> None:
    stack = Stack(0x100)

    stack.push_frame((LocalsFormat(4, 2), LocalsFormat(1, 3)))
    stack.set_local(0, 0x1_2345_6789)
    stack.set_local(8, 0x1AB, width=1)

    assert_that(stack.get_local(0)).is_equal_to(0x2345_6789)
    assert_that(stack.get_local(4)).is_equal_to(0)
    assert_that(stack.get_local(8, width=1)).is_equal_to(0xAB)

    with pytest.raises(GlulxStackError, match="outside"):
        stack.get_local(12)

    with pytest.raises(GlulxStackError, match="outside"):
        stack.set_local(-4, 1)

    with pytest.raises(GlulxStackError, match="outside"):
        stack.get_local(12, width=1)

    with pytest.raises(GlulxStackError, match="natural alignment"):
        stack.get_local(2)


# A frame refuses locals the format bytes cannot express, and a
# frame that will not fit refuses before touching anything.
def test_impossible_frames_are_refused() -> None:
    stack = Stack(0x100)

    with pytest.raises(GlulxStackError, match="types 1, 2, and 4"):
        stack.push_frame((LocalsFormat(3, 1),))

    with pytest.raises(GlulxStackError, match="fit its byte"):
        stack.push_frame((LocalsFormat(4, 256),))

    with pytest.raises(GlulxStackError, match="building a call frame"):
        stack.push_frame((LocalsFormat(4, 255),))


# A call stub records where to come home to; popping one restores
# the caller's frame registers from the frame's own header, while
# the program counter and result stay the machine's business
# (Glulx: Call Stubs).
def test_call_stubs_come_home() -> None:
    stack = Stack(0x200)

    stack.push_frame((LocalsFormat(4, 1),))
    stack.push(41)
    stack.push_stub(DestType.MEMORY, 0x1234, 0x5678)
    stack.push_frame(())
    stack.push(99)
    stack.leave_frame()

    stub = stack.pop_stub()

    assert_that(stub).is_equal_to(CallStub(DestType.MEMORY, 0x1234, 0x5678, 0))
    assert_that(stack.frameptr).is_equal_to(0)
    assert_that(stack.localsbase).is_equal_to(12)
    assert_that(stack.valstackbase).is_equal_to(16)
    assert_that(stack.pop()).is_equal_to(41)

    bare = Stack(0x100)

    with pytest.raises(GlulxStackError, match="popping a call stub"):
        bare.pop_stub()

    cramped = Stack(0x100)

    for _ in range(0x3D):
        cramped.push(7)

    with pytest.raises(GlulxStackError, match="pushing a call stub"):
        cramped.push_stub(0, 0, 0)


# The snapshot is the live bytes verbatim -- big-endian already,
# which is the whole byte-order ruling -- and a restore brings
# them back with the frame registers zeroed until the saver's own
# call stub is popped (Glulx: Contents of the Stack).
def test_snapshots_restore_and_reset_clears() -> None:
    stack = Stack(0x100)

    stack.push(0xDEADBEEF)
    stack.push(2)

    saved = stack.snapshot()

    assert_that(saved).is_equal_to(bytes([0xDE, 0xAD, 0xBE, 0xEF, 0, 0, 0, 2]))

    stack.push(3)
    stack.restore(saved)

    assert_that(stack.sp).is_equal_to(8)
    assert_that(stack.frameptr).is_equal_to(0)
    assert_that(stack.locals_format()).is_equal_to(())
    assert_that(stack.pop()).is_equal_to(2)

    with pytest.raises(GlulxStackError, match="cannot fit"):
        stack.restore(bytes(0x200))

    with pytest.raises(GlulxStackError, match="whole number of words"):
        stack.restore(bytes(6))

    stack.reset()

    assert_that(stack.sp).is_equal_to(0)
    assert_that(stack.count).is_equal_to(0)
