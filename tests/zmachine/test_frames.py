import pytest
from assertpy import assert_that

from voxam.errors import ZMachineStackError
from voxam.zmachine.frames import USAGE_LIMIT, CallStack
from voxam.zmachine.routine import Routine
from voxam.zmachine.snapshot import FrameSnapshot


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


def keep_calling(calls: CallStack) -> None:
    while True:
        calls.call(routine_with((0,)), (), return_address=0, store_variable=0)


def keep_pushing(calls: CallStack) -> None:
    while True:
        calls.push(1)


# Runaway recursion must halt loudly, not hang: each call charges
# 4 + locals against the §6.3.3 usage ceiling.
def test_runaway_recursion_hits_the_usage_ceiling() -> None:
    calls = CallStack()

    with pytest.raises(ZMachineStackError, match="runaway recursion"):
        keep_calling(calls)


def test_runaway_pushing_hits_the_ceiling_too() -> None:
    calls = CallStack()

    with pytest.raises(ZMachineStackError, match="usage passed"):
        keep_pushing(calls)


# Returning reclaims a frame's whole usage -- locals and any stack
# leftovers included -- so deep but balanced call patterns never
# trouble the ceiling.
def test_balanced_calls_reclaim_their_usage() -> None:
    calls = CallStack()

    for _ in range(30_000):
        calls.call(routine_with((0, 0, 0)), (), return_address=0, store_variable=0)
        calls.push(42)
        calls.pop_frame()

    for _ in range(70_000):
        calls.push(7)
        calls.pop()

    assert_that(calls.depth).is_equal_to(1)


# The in-place operations of §6.3.4 need a top to work on: an empty
# stack refuses both the read and the overwrite.
def test_in_place_access_needs_a_stack_top() -> None:
    calls = CallStack()

    with pytest.raises(ZMachineStackError, match="read the top of an empty"):
        calls.peek()

    with pytest.raises(ZMachineStackError, match="overwrite the top of an empty"):
        calls.replace_top(42)


def test_replace_top_overwrites_without_growing() -> None:
    calls = CallStack()
    calls.push(11)
    calls.replace_top(42)

    assert_that(calls.peek()).is_equal_to(42)
    assert_that(calls.pop()).is_equal_to(42)

    with pytest.raises(ZMachineStackError, match="empty stack"):
        calls.pop()


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


# The whole call chain survives a round trip: a snapshot taken with
# a routine in flight restores its locals, its private stack, and
# its depth exactly (§6.1, §6.1.2).
def test_call_chain_survives_a_snapshot_round_trip() -> None:
    calls = CallStack()
    calls.call(routine_with((7, 8)), (1,), return_address=0x500, store_variable=3)
    calls.push(0x2A)

    frames = calls.snapshot()

    calls.set_local(2, 0xBEEF)
    calls.push(0x99)
    calls.call(routine_with(()), (), return_address=0x600, store_variable=None)

    calls.restore(frames)

    assert_that(calls.depth).is_equal_to(2)
    assert_that(calls.local(1)).is_equal_to(1)
    assert_that(calls.local(2)).is_equal_to(8)
    assert_that(calls.pop()).is_equal_to(0x2A)


# The capture is frozen: mutating the live call state after taking
# it cannot reach into the captured frames (§6.1).
def test_frame_snapshot_is_inert_after_capture() -> None:
    calls = CallStack()
    calls.call(routine_with((7,)), (), return_address=0x500, store_variable=0)
    calls.push(0x2A)

    frames = calls.snapshot()

    calls.set_local(1, 0xBEEF)
    calls.push(0x99)

    assert_that(frames[-1].locals).is_equal_to((7,))
    assert_that(frames[-1].stack).is_equal_to((0x2A,))


# Restoring recomputes stack usage from the frames themselves, so
# the restored state pays for exactly what it holds: popping back
# to the base frame works as if the chain had been built by calls.
def test_restore_recomputes_usage_and_the_chain_still_pops() -> None:
    calls = CallStack()
    calls.call(routine_with((5,)), (), return_address=0x500, store_variable=0)

    frames = calls.snapshot()
    fresh = CallStack()
    fresh.restore(frames)

    assert_that(fresh.pop_frame().return_address).is_equal_to(0x500)
    assert_that(fresh.depth).is_equal_to(1)


# Even a game at rest stands on the base frame (§5.5), so an empty
# chain cannot be a state of play.
def test_restoring_an_empty_call_chain_is_refused() -> None:
    calls = CallStack()

    with pytest.raises(ZMachineStackError, match="base frame always exists"):
        calls.restore(())


# A chain whose usage passes the §6.3.3 ceiling could never have
# been captured from this machine, so restoring one is refused.
def test_restoring_an_impossible_call_chain_is_refused() -> None:
    base = FrameSnapshot(
        return_address=0, store_variable=None, locals=(), argument_count=0, stack=()
    )
    bloated = FrameSnapshot(
        return_address=0x500,
        store_variable=None,
        locals=(),
        argument_count=0,
        stack=(0,) * (USAGE_LIMIT + 1),
    )

    with pytest.raises(ZMachineStackError, match="cannot be an honest capture"):
        CallStack().restore((base, bloated))
