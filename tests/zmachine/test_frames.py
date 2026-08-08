import pytest
from assertpy import assert_that

from voxam.errors import ZMachineStackError
from voxam.zmachine.frames import CallStack
from voxam.zmachine.routine import Routine


def routine_with(initial_locals: tuple[int, ...]) -> Routine:
    return Routine(
        address=0x200, initial_locals=initial_locals, first_instruction=0x201
    )


def test_starts_with_an_unreturnable_base_frame() -> None:
    calls = CallStack()

    assert_that(calls.depth).is_equal_to(1)

    with pytest.raises(ZMachineStackError, match="no routine has been called"):
        calls.pop_frame()


# Locals begin at the header's initial values and arguments then
# overwrite the first of them (§6.4.4). The third local keeps its
# default: that is how optional arguments work.
def test_arguments_overwrite_the_first_locals() -> None:
    calls = CallStack()
    calls.call(routine_with((7, 8, 9)), (1, 2), return_address=0x500, store_variable=0)

    assert_that(calls.local(1)).is_equal_to(1)
    assert_that(calls.local(2)).is_equal_to(2)
    assert_that(calls.local(3)).is_equal_to(9)
    assert_that(calls.argument_count).is_equal_to(2)
    assert_that(calls.depth).is_equal_to(2)


# More arguments than locals is legal (§6.4.4.1) -- and the count
# still reports what the caller supplied, which is what
# check_arg_count asks about.
def test_spare_arguments_are_thrown_away() -> None:
    calls = CallStack()
    calls.call(routine_with((5,)), (1, 2, 3), return_address=0x500, store_variable=0)

    assert_that(calls.local(1)).is_equal_to(1)
    assert_that(calls.argument_count).is_equal_to(3)


def test_locals_that_do_not_exist_cannot_be_touched() -> None:
    calls = CallStack()
    calls.call(routine_with((5, 6)), (), return_address=0x500, store_variable=0)

    with pytest.raises(ZMachineStackError, match="local 3 does not exist"):
        calls.local(3)

    with pytest.raises(ZMachineStackError, match="local 0 does not exist"):
        calls.set_local(0, 1)


def test_locals_can_be_written() -> None:
    calls = CallStack()
    calls.call(routine_with((0,)), (), return_address=0x500, store_variable=0)
    calls.set_local(1, 0xBEEF)

    assert_that(calls.local(1)).is_equal_to(0xBEEF)


# A routine starts with an empty stack, cannot reach past its own
# frame, and its values vanish when it returns (§6.3.1, §6.3.2).
def test_each_routine_sees_only_its_own_stack() -> None:
    calls = CallStack()
    calls.push(11)

    calls.call(routine_with(()), (), return_address=0x500, store_variable=0)

    with pytest.raises(ZMachineStackError, match="only sees values it pushed"):
        calls.pop()

    calls.push(22)

    assert_that(calls.pop()).is_equal_to(22)

    calls.push(33)
    calls.pop_frame()

    assert_that(calls.pop()).is_equal_to(11)


def test_popped_frames_carry_their_return_directions() -> None:
    calls = CallStack()
    calls.call(routine_with(()), (), return_address=0x1234, store_variable=0x05)

    frame = calls.pop_frame()

    assert_that(frame.return_address).is_equal_to(0x1234)
    assert_that(frame.store_variable).is_equal_to(0x05)
    assert_that(calls.depth).is_equal_to(1)


@pytest.mark.parametrize("value", [-1, 0x10000])
def test_rejects_values_that_do_not_fit_in_a_word(value: int) -> None:
    calls = CallStack()
    calls.call(routine_with((0,)), (), return_address=0x500, store_variable=0)

    with pytest.raises(ZMachineStackError, match="fit in a word"):
        calls.push(value)

    with pytest.raises(ZMachineStackError, match="fit in a word"):
        calls.set_local(1, value)
