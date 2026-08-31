"""Function entry: types, frames, seated arguments (Glulx: Functions)."""

from collections.abc import Callable

import pytest
from assertpy import assert_that

from voxam.errors import GlulxFunctionError
from voxam.glulx.funcs import (
    FunctionHeader,
    pop_arguments,
    push_call_frame,
    read_function_header,
)
from voxam.glulx.memory import Memory
from voxam.glulx.stack import LocalsFormat, Stack
from voxam.glulx.story import Story

FUNC = 0x140


def rig(image: Callable[..., bytes], header: bytes) -> tuple[Memory, Stack]:
    """A memory with a function header planted at $140, and a stack."""

    memory = Memory(Story(image()))

    memory.write_run(FUNC, header)

    return memory, Stack(0x200)


# A header is a type byte and a zero-terminated locals-format list,
# with the code starting just past it.
def test_a_function_header_reads_whole(image: Callable[..., bytes]) -> None:
    memory, _ = rig(image, bytes([0xC1, 0x04, 0x02, 0x01, 0x03, 0x00, 0x00]))

    assert_that(read_function_header(memory, FUNC)).is_equal_to(
        FunctionHeader(0xC1, (LocalsFormat(4, 2), LocalsFormat(1, 3)), FUNC + 7)
    )

    bare, _ = rig(image, bytes([0xC0, 0x00, 0x00]))

    assert_that(read_function_header(bare, FUNC).code_addr).is_equal_to(FUNC + 3)


# The type taxonomy matters: C2 through DF are functions of a kind
# reserved for the future, and everything else is no function at
# all -- the difference tells an author whether an address is wrong
# or merely too new.
def test_the_type_taxonomy_names_the_failure(image: Callable[..., bytes]) -> None:
    reserved, _ = rig(image, bytes([0xC5]))

    with pytest.raises(GlulxFunctionError, match="reserved for the future"):
        read_function_header(reserved, FUNC)

    for wrong in (0x00, 0xE0):
        other, _ = rig(image, bytes([wrong]))

        with pytest.raises(GlulxFunctionError, match="not a function at all"):
            read_function_header(other, FUNC)

    illegal, _ = rig(image, bytes([0xC1, 0x03, 0x01, 0x00, 0x00]))

    with pytest.raises(GlulxFunctionError, match="local type of 3"):
        read_function_header(illegal, FUNC)


# A C0 function finds its arguments on the value stack: pushed
# backwards, so the first argument sits topmost with the count
# above it.
def test_a_c0_function_takes_arguments_on_the_stack(
    image: Callable[..., bytes],
) -> None:
    memory, stack = rig(image, bytes([0xC0, 0x00, 0x00]))

    pc = push_call_frame(memory, stack, FUNC, [7, 8, 9])

    assert_that(pc).is_equal_to(FUNC + 3)
    assert_that(stack.pop()).is_equal_to(3)
    assert_that(stack.pop()).is_equal_to(7)
    assert_that(stack.pop()).is_equal_to(8)
    assert_that(stack.pop()).is_equal_to(9)


# A C1 function finds its arguments written into its locals in
# order: values truncate to narrow locals -- deprecated but legal
# -- extras drop silently, unfilled locals stay zero, and each run
# seats at its own natural alignment.
def test_a_c1_function_takes_arguments_in_its_locals(
    image: Callable[..., bytes],
) -> None:
    memory, stack = rig(image, bytes([0xC1, 0x04, 0x02, 0x01, 0x03, 0x00, 0x00]))

    push_call_frame(
        memory, stack, FUNC, [0x11223344, 0x55, 0x1FF, 0xAA, 0xBB, 0xCC, 0xDD]
    )

    assert_that(stack.get_local(0)).is_equal_to(0x11223344)
    assert_that(stack.get_local(4)).is_equal_to(0x55)
    assert_that(stack.get_local(8, width=1)).is_equal_to(0xFF)
    assert_that(stack.get_local(9, width=1)).is_equal_to(0xAA)
    assert_that(stack.get_local(10, width=1)).is_equal_to(0xBB)
    assert_that(stack.count).is_equal_to(0)

    sparse, thin = rig(image, bytes([0xC1, 0x04, 0x02, 0x00, 0x00]))

    push_call_frame(sparse, thin, FUNC, [1])

    assert_that(thin.get_local(0)).is_equal_to(1)
    assert_that(thin.get_local(4)).is_equal_to(0)

    padded, aligned = rig(image, bytes([0xC1, 0x01, 0x01, 0x04, 0x01, 0x00, 0x00]))

    push_call_frame(padded, aligned, FUNC, [0x11, 0x22])

    assert_that(aligned.get_local(0, width=1)).is_equal_to(0x11)
    assert_that(aligned.get_local(4)).is_equal_to(0x22)

    skipped, hollow = rig(image, bytes([0xC1, 0x04, 0x01, 0x01, 0x02, 0x00, 0x00]))

    push_call_frame(skipped, hollow, FUNC, [9])

    assert_that(hollow.get_local(4, width=1)).is_equal_to(0)


# Arguments collect from the stack -- first argument topmost -- or
# from a word array in memory, for the accelerated functions to
# come; a count with its sign bit set is a count gone wrong.
def test_arguments_collect_from_stack_or_memory(
    image: Callable[..., bytes],
) -> None:
    memory, stack = rig(image, b"")

    stack.push(1)
    stack.push(2)
    stack.push(3)

    assert_that(pop_arguments(stack, 3, memory)).is_equal_to([3, 2, 1])
    assert_that(pop_arguments(stack, 0, memory)).is_equal_to([])

    memory.write_word(0x180, 41)
    memory.write_word(0x184, 42)

    assert_that(pop_arguments(stack, 2, memory, addr=0x180)).is_equal_to([41, 42])

    with pytest.raises(GlulxFunctionError, match="sign bit"):
        pop_arguments(stack, 0x8000_0001, memory)


# A header below RAMSTART cannot change, so a caller that offers
# somewhere to keep one gets the same object back every time. The
# span that has to be safe runs from the function's address to the
# code it names, which is what the boundary is tested against.
def test_a_header_in_rom_is_kept(image: Callable[..., bytes]) -> None:
    planted = bytes([0xC1, 0x04, 0x02, 0x00, 0x00])
    memory = Memory(Story(image(code=planted)))
    headers: dict[int, FunctionHeader] = {}
    rom = 0x48

    assert_that(rom).is_less_than(memory.ramstart)

    first = read_function_header(memory, rom, headers)
    second = read_function_header(memory, rom, headers)

    assert_that(list(headers)).is_equal_to([rom])
    assert_that(second).is_same_as(first)


# Above RAMSTART the story may write over its own function headers,
# so nothing there is kept and every call reads what is there now.
def test_a_header_in_ram_is_read_afresh(image: Callable[..., bytes]) -> None:
    memory, _ = rig(image, bytes([0xC1, 0x04, 0x02, 0x00, 0x00]))
    headers: dict[int, FunctionHeader] = {}

    assert_that(FUNC).is_greater_than(memory.ramstart)

    first = read_function_header(memory, FUNC, headers)

    assert_that(headers).is_empty()

    memory.write_run(FUNC, bytes([0xC0, 0x01, 0x03, 0x00, 0x00]))

    second = read_function_header(memory, FUNC, headers)

    assert_that(first.locals_format).is_equal_to((LocalsFormat(4, 2),))
    assert_that(second.locals_format).is_equal_to((LocalsFormat(1, 3),))
    assert_that(second.functype).is_equal_to(0xC0)
