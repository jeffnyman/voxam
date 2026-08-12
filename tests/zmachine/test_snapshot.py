import dataclasses
from collections.abc import Callable

import pytest
from assertpy import assert_that

from voxam.errors import ZMachineMemoryError
from voxam.zmachine.header import FLAGS_1, FLAGS_2, SCREEN_SPLIT_BIT
from voxam.zmachine.machine import Machine

# The result global: variable $10, first entry of the table at $100.
RESULT_VARIABLE = 0x10
RESULT_ADDRESS = 0x100

# A routine planted at $60 is packed 0x30 under Version 3's scale
# factor of 2.
ROUTINE_A_PACKED = bytes([0x00, 0x30])

# store $10, 42 -- then quit.
STORE_42 = bytes([0x0D, RESULT_VARIABLE, 0x2A, 0xBA])


def layout(main: bytes, routine_a: bytes = b"") -> bytes:
    code = bytearray(0x40)
    code[: len(main)] = main
    code[0x20 : 0x20 + len(routine_a)] = routine_a

    return bytes(code)


# The elementary time loop: capture, run forward, restore, and the
# machine is back where it stood -- PC and dynamic memory both --
# ready to walk the same path again (§6.1, §6.1.2).
def test_restore_rewinds_memory_and_the_pc(
    code_machine: Callable[..., Machine],
) -> None:
    machine = code_machine(layout(STORE_42))
    boot_pc = machine.pc
    snapshot = machine.snapshot()

    machine.step()

    assert_that(machine.memory.read_word(RESULT_ADDRESS)).is_equal_to(42)
    assert_that(machine.pc).is_not_equal_to(boot_pc)

    machine.restore(snapshot)

    assert_that(machine.pc).is_equal_to(boot_pc)
    assert_that(machine.memory.read_word(RESULT_ADDRESS)).is_zero()

    machine.step()

    assert_that(machine.memory.read_word(RESULT_ADDRESS)).is_equal_to(42)


# A snapshot taken with a routine in flight restores the whole call
# state: after the rewind, the routine returns all over again and
# its result lands in the caller's variable a second time (§6.1).
def test_restore_rewinds_a_routine_in_flight(
    code_machine: Callable[..., Machine],
) -> None:
    main = bytes([0xE0, 0x3F, *ROUTINE_A_PACKED, RESULT_VARIABLE, 0xBA])
    returns_42 = bytes([0x00, 0x9B, 0x2A])
    machine = code_machine(layout(main, returns_42))

    machine.step()

    snapshot = machine.snapshot()

    machine.step()

    assert_that(machine.memory.read_word(RESULT_ADDRESS)).is_equal_to(42)

    machine.memory.write_word(RESULT_ADDRESS, 0)
    machine.restore(snapshot)
    machine.step()

    assert_that(machine.memory.read_word(RESULT_ADDRESS)).is_equal_to(42)


# 'Flags 2' belongs to the player's session, not the story's state:
# transcription switched on after the capture must survive the
# restore (§6.1.2).
def test_flags_2_survives_a_restore(code_machine: Callable[..., Machine]) -> None:
    machine = code_machine(layout(STORE_42))
    snapshot = machine.snapshot()

    machine.memory.write_word(FLAGS_2, 0x0001)
    machine.restore(snapshot)

    assert_that(machine.memory.read_word(FLAGS_2)).is_equal_to(0x0001)


# A capture may have been taken under some other interpreter whose
# capabilities differ, so the Rst-marked header fields are re-stamped
# after the restore (§6.1.2.2): a foreign screen-split claim is
# overwritten by this frontend's honest answer.
def test_interpreter_capabilities_are_restamped_after_restore(
    code_machine: Callable[..., Machine],
) -> None:
    machine = code_machine(layout(STORE_42))
    snapshot = machine.snapshot()

    foreign = bytearray(snapshot.dynamic_memory)
    foreign[FLAGS_1] |= SCREEN_SPLIT_BIT
    machine.restore(dataclasses.replace(snapshot, dynamic_memory=bytes(foreign)))

    split_claimed = machine.memory.read_byte(FLAGS_1) & SCREEN_SPLIT_BIT

    assert_that(split_claimed).is_zero()


# A snapshot whose dynamic memory does not match this story's shape
# came from a different game, which §6.1.2.1 asks us to refuse.
def test_restoring_a_foreign_snapshot_is_refused(
    code_machine: Callable[..., Machine],
) -> None:
    machine = code_machine(layout(STORE_42))
    snapshot = machine.snapshot()
    foreign = dataclasses.replace(
        snapshot, dynamic_memory=snapshot.dynamic_memory + b"\x00"
    )

    with pytest.raises(ZMachineMemoryError, match="different game"):
        machine.restore(foreign)


# The capture is inert: running the machine forward cannot reach
# back into a snapshot already taken (§6.1.1.2 keeps captures
# independent of the life the machine lives afterward).
def test_a_snapshot_is_inert_after_capture(
    code_machine: Callable[..., Machine],
) -> None:
    machine = code_machine(layout(STORE_42))
    snapshot = machine.snapshot()

    machine.step()

    captured = snapshot.dynamic_memory[RESULT_ADDRESS : RESULT_ADDRESS + 2]

    assert_that(captured).is_equal_to(b"\x00\x00")
