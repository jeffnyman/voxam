from collections.abc import Callable

import pytest
from assertpy import assert_that

from voxam.errors import ZMachineUnimplementedError
from voxam.zmachine.machine import Machine

# Globals $10, $11, $12 live at $100, $102, $104 in the conftest
# story shape.
G0_ADDRESS = 0x100
G1_ADDRESS = 0x102
G2_ADDRESS = 0x104

# 'Flags 2' is the word at $10 (§11.1).
FLAGS_2_ADDRESS = 0x10


class MemorySlot:
    """A save slot in a test's hand: inspectable, and breakable."""

    def __init__(self, data: bytes | None = None, *, writable: bool = True) -> None:
        self.data = data
        self.writable = writable

    def write(self, data: bytes) -> bool:
        if not self.writable:
            return False

        self.data = data

        return True

    def read(self) -> bytes | None:
        return self.data


# The Version 3 program: save branches to the 9-marker on success
# and falls through to restore on failure; a failed restore never
# branches and marks 8 instead (§15 save, §15 restore).
#
#   $40  save [on success -> $48]
#   $42  restore [rider never taken]
#   $44  store g1, 8
#   $47  quit
#   $48  store g1, 9
#   $4b  quit
V3_PROGRAM = bytes(
    [0xB5, 0xC8, 0xB6, 0x42, 0x0D, 0x11, 0x08, 0xBA, 0x0D, 0x11, 0x09, 0xBA]
)

# The Version 4 program proves the whole store contract in one run:
# save stores 1, the restore rewinds to the save's store byte, and
# the resumed save stores 2 -- which is the only way to the 42
# (§15 save, Quetzal §5.8.2).
#
#   $40  save -> g0
#   $42  je g0, 2 [on true -> $49]
#   $46  restore -> g1
#   $48  quit
#   $49  store g2, 42
#   $4c  quit
V4_PROGRAM = bytes(
    [0xB5, 0x10, 0x41, 0x10, 0x02, 0xC5, 0xB6, 0x11, 0xBA, 0x0D, 0x12, 0x2A, 0xBA]
)


# A Version 3 save that succeeds takes its branch (§15 save).
def test_v3_save_branches_on_success(code_machine: Callable[..., Machine]) -> None:
    slot = MemorySlot()
    machine = code_machine(V3_PROGRAM, saves=slot)

    machine.run()

    assert_that(machine.memory.read_word(G1_ADDRESS)).is_equal_to(9)
    assert_that((slot.data or b"")[:4]).is_equal_to(b"FORM")


# With nowhere to keep a save, saving fails and falls through; the
# restore then fails too, and its branch is never made (§15).
def test_v3_save_and_restore_fail_without_a_slot(
    code_machine: Callable[..., Machine],
) -> None:
    machine = code_machine(V3_PROGRAM)

    machine.run()

    assert_that(machine.memory.read_word(G1_ADDRESS)).is_equal_to(8)


# Restoring rewinds to the save point and takes the save's own
# branch, as the successful save it was (§15 restore, Quetzal §5.8.1)
# -- in a second machine whose own save failed, so only a real
# restore explains the 9. Memory poisoned before the run comes back
# rewound.
def test_v3_restore_resumes_at_the_saves_branch(
    code_machine: Callable[..., Machine],
) -> None:
    slot = MemorySlot()
    first = code_machine(V3_PROGRAM, saves=slot)

    first.run()

    second = code_machine(V3_PROGRAM, saves=MemorySlot(slot.data, writable=False))
    second.memory.write_word(G0_ADDRESS, 0xAAAA)

    second.run()

    assert_that(second.memory.read_word(G1_ADDRESS)).is_equal_to(9)
    assert_that(second.memory.read_word(G0_ADDRESS)).is_zero()


# A save may just as legally branch on failure; the resumed restore
# then falls through it, since the save it re-enters was a success
# (§4.7, Quetzal §5.8.1).
#
#   $40  save [on FAILURE -> $46]
#   $42  store g1, 9
#   $45  quit
#   $46  restore [rider never taken]
#   $48  store g1, 8
#   $4b  quit
def test_v3_restore_falls_through_a_branch_on_failure(
    code_machine: Callable[..., Machine],
) -> None:
    program = bytes(
        [0xB5, 0x46, 0x0D, 0x11, 0x09, 0xBA, 0xB6, 0x42, 0x0D, 0x11, 0x08, 0xBA]
    )
    slot = MemorySlot()
    first = code_machine(program, saves=slot)

    first.run()

    assert_that(first.memory.read_word(G1_ADDRESS)).is_equal_to(9)

    second = code_machine(program, saves=MemorySlot(slot.data, writable=False))

    second.run()

    assert_that(second.memory.read_word(G1_ADDRESS)).is_equal_to(9)


# Bytes that are not a saved game fail the restore like an empty
# slot would: an answer for the story, not a crash.
def test_restoring_garbage_fails_gracefully(
    code_machine: Callable[..., Machine],
) -> None:
    slot = MemorySlot(b"these bytes are nobody's saved game", writable=False)
    machine = code_machine(V3_PROGRAM, saves=slot)

    machine.run()

    assert_that(machine.memory.read_word(G1_ADDRESS)).is_equal_to(8)


# The Version 4 loop: save stores 1, restore rewinds, and the save's
# store byte answers 2 the second time through -- the story's only
# way of telling a restore from a save (§15 save, Quetzal §5.8.2).
def test_v4_save_stores_1_and_restore_answers_2(
    code_machine: Callable[..., Machine],
) -> None:
    machine = code_machine(V4_PROGRAM, version=4, saves=MemorySlot())

    machine.run()

    assert_that(machine.memory.read_word(G0_ADDRESS)).is_equal_to(2)
    assert_that(machine.memory.read_word(G2_ADDRESS)).is_equal_to(42)


# From Version 4, failure is a stored 0 -- for the save with nowhere
# to write, and for the restore with nothing to read (§15).
def test_v4_save_and_restore_store_0_on_failure(
    code_machine: Callable[..., Machine],
) -> None:
    machine = code_machine(V4_PROGRAM, version=4)

    machine.run()

    assert_that(machine.memory.read_word(G0_ADDRESS)).is_zero()
    assert_that(machine.memory.read_word(G2_ADDRESS)).is_zero()


# From Version 5, save and restore live on as EXT opcodes; the plain
# forms keep the Version 4 store contract (§14, §15).
def test_v5_extended_save_stores_its_result(
    code_machine: Callable[..., Machine],
) -> None:
    slot = MemorySlot()
    machine = code_machine(bytes([0xBE, 0x00, 0xFF, 0x10, 0xBA]), version=5, saves=slot)

    machine.run()

    assert_that(machine.memory.read_word(G0_ADDRESS)).is_equal_to(1)
    assert_that((slot.data or b"")[:4]).is_equal_to(b"FORM")


# The EXT forms may take operands naming a table to save instead of
# the state of play (§15) -- auxiliary-file machinery Voxam does not
# have, and a loud frontier beats quietly saving the wrong thing.
def test_table_form_save_is_a_frontier(code_machine: Callable[..., Machine]) -> None:
    machine = code_machine(bytes([0xBE, 0x00, 0x7F, 0x05, 0x10, 0xBA]), version=5)

    with pytest.raises(ZMachineUnimplementedError, match="table operands"):
        machine.run()


# Restart reloads everything from the pristine file -- but 'Flags 2'
# survives, which is also the only signal that can cross a restart
# and end this program (§6.1.3).
#
#   $40  loadw 0, 8 -> g0        (reads 'Flags 2')
#   $44  je g0, 1 [on true -> $51]
#   $48  store g1, 5
#   $4b  storew 0, 8, 1          (sets 'Flags 2')
#   $50  restart
#   $51  store g2, 9
#   $54  quit
def test_restart_reloads_everything_but_flags_2(
    code_machine: Callable[..., Machine],
) -> None:
    program = bytes(
        [
            *[0x0F, 0x00, 0x08, 0x10],
            *[0x41, 0x10, 0x01, 0xCB],
            *[0x0D, 0x11, 0x05],
            *[0xE1, 0x57, 0x00, 0x08, 0x01],
            *[0xB7],
            *[0x0D, 0x12, 0x09, 0xBA],
        ]
    )
    machine = code_machine(program)

    machine.run()

    assert_that(machine.memory.read_word(G1_ADDRESS)).is_zero()
    assert_that(machine.memory.read_word(G2_ADDRESS)).is_equal_to(9)
    assert_that(machine.memory.read_word(FLAGS_2_ADDRESS)).is_equal_to(1)
