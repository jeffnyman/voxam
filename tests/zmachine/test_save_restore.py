from collections.abc import Callable

import pytest
from assertpy import assert_that

from voxam.errors import ZMachineInstructionError
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
        self.aux: dict[str, bytes] = {}

    def write(self, data: bytes) -> bool:
        if not self.writable:
            return False

        self.data = data

        return True

    def read(self) -> bytes | None:
        return self.data

    def write_aux(self, name: str, data: bytes) -> bool:
        if not self.writable:
            return False

        self.aux[name] = data

        return True

    def read_aux(self, name: str) -> bytes | None:
        return self.aux.get(name)


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


# The table forms save a raw region of memory to a named auxiliary
# file and load it back (§15 save, §7.6): here four bytes travel
# out under the name "map" and back into a different table, with
# save answering 1 and restore answering the byte count.
def test_a_table_round_trips_through_an_auxiliary_file(
    code_machine: Callable[..., Machine],
) -> None:
    program = bytes(
        [
            *[0xBE, 0x00, 0x13, 0x01, 0x20, 0x04, 0x01, 0x40, 0x10],
            *[0xBE, 0x01, 0x13, 0x01, 0x60, 0x04, 0x01, 0x40, 0x11],
            *[0xBA],
        ]
    )
    slot = MemorySlot()
    machine = code_machine(program, version=5, saves=slot)

    for offset, value in enumerate([7, 8, 9, 10]):
        machine.memory.write_byte(0x120 + offset, value)

    for offset, value in enumerate([3, ord("m"), ord("a"), ord("p")]):
        machine.memory.write_byte(0x140 + offset, value)

    machine.run()

    assert_that(slot.aux).is_equal_to({"map": bytes([7, 8, 9, 10])})
    assert_that(machine.memory.read_word(G0_ADDRESS)).is_equal_to(1)
    assert_that(machine.memory.read_word(G1_ADDRESS)).is_equal_to(4)
    assert_that([machine.memory.read_byte(0x160 + i) for i in range(4)]).is_equal_to(
        [7, 8, 9, 10]
    )


# Restore loads at most the asked-for bytes and answers with the
# count actually loaded (§15 restore); the rest of the table stays
# untouched.
def test_a_table_restore_is_bounded_by_its_length(
    code_machine: Callable[..., Machine],
) -> None:
    program = bytes([0xBE, 0x01, 0x13, 0x01, 0x60, 0x02, 0x01, 0x40, 0x11, 0xBA])
    slot = MemorySlot()
    slot.aux["map"] = bytes([7, 8, 9, 10])
    machine = code_machine(program, version=5, saves=slot)

    for offset, value in enumerate([3, ord("m"), ord("a"), ord("p")]):
        machine.memory.write_byte(0x140 + offset, value)

    for offset in range(4):
        machine.memory.write_byte(0x160 + offset, 0xAA)

    machine.run()

    assert_that(machine.memory.read_word(G1_ADDRESS)).is_equal_to(2)
    assert_that([machine.memory.read_byte(0x160 + i) for i in range(4)]).is_equal_to(
        [7, 8, 0xAA, 0xAA]
    )


# A file the slot does not have loads nothing and answers 0.
def test_a_missing_auxiliary_file_answers_0(
    code_machine: Callable[..., Machine],
) -> None:
    program = bytes([0xBE, 0x01, 0x13, 0x01, 0x60, 0x04, 0x01, 0x40, 0x11, 0xBA])
    machine = code_machine(program, version=5, saves=MemorySlot())

    for offset, value in enumerate([3, ord("m"), ord("a"), ord("p")]):
        machine.memory.write_byte(0x140 + offset, value)

    machine.run()

    assert_that(machine.memory.read_word(G1_ADDRESS)).is_zero()


# The table form takes a table, a length, and a name; fewer is a
# malformed instruction, refused with a citation (§15 save).
def test_a_short_table_form_is_refused(
    code_machine: Callable[..., Machine],
) -> None:
    machine = code_machine(bytes([0xBE, 0x00, 0x7F, 0x05, 0x10, 0xBA]), version=5)

    with pytest.raises(ZMachineInstructionError, match="table form takes"):
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


# The undo loop, all in one run: save_undo stores 1, restore_undo
# rewinds to the save_undo's own store byte, and the resumed
# save_undo answers 2 -- the only path to the 42 (§15 save_undo,
# §15 restore_undo).
#
#   $40  save_undo -> g0
#   $44  je g0, 2 [on true -> $4d]
#   $48  restore_undo -> g1
#   $4c  quit
#   $4d  store g2, 42
#   $50  quit
def test_save_undo_stores_1_and_restore_undo_answers_2(
    code_machine: Callable[..., Machine],
) -> None:
    program = bytes(
        [
            *[0xBE, 0x09, 0xFF, 0x10],
            *[0x41, 0x10, 0x02, 0xC7],
            *[0xBE, 0x0A, 0xFF, 0x11],
            *[0xBA],
            *[0x0D, 0x12, 0x2A],
            *[0xBA],
        ]
    )
    machine = code_machine(program, version=5)

    machine.run()

    assert_that(machine.memory.read_word(G0_ADDRESS)).is_equal_to(2)
    assert_that(machine.memory.read_word(G2_ADDRESS)).is_equal_to(42)


# restore_undo with nothing in hand stores 0 and moves on -- the
# quiet option §15 restore_undo offers an interpreter.
def test_restore_undo_with_nothing_held_stores_0(
    code_machine: Callable[..., Machine],
) -> None:
    program = bytes(
        [
            *[0xBE, 0x0A, 0xFF, 0x11],
            *[0x0D, 0x12, 0x09],
            *[0xBA],
        ]
    )
    machine = code_machine(program, version=5)

    machine.run()

    assert_that(machine.memory.read_word(G1_ADDRESS)).is_zero()
    assert_that(machine.memory.read_word(G2_ADDRESS)).is_equal_to(9)


# The undo snapshot is the interpreter's, not the story's: a file
# restore rewinds the state of play to before save_undo ever ran,
# yet the held snapshot survives and still answers (§6.1.1.2).
def test_the_undo_snapshot_survives_a_file_restore(
    code_machine: Callable[..., Machine],
) -> None:
    #   $40  save -> g0            (file, taken before any undo)
    #   $44  je g0, 2 [on true -> $55]
    #   $48  save_undo -> g1
    #   $4c  je g1, 2 [on true -> $5a]
    #   $50  restore -> g2         (file: rewinds past save_undo)
    #   $54  quit
    #   $55  restore_undo -> g3    (the held snapshot still answers)
    #   $59  quit
    #   $5a  store g4, 42
    #   $5d  quit
    program = bytes(
        [
            *[0xBE, 0x00, 0xFF, 0x10],
            *[0x41, 0x10, 0x02, 0xCF],
            *[0xBE, 0x09, 0xFF, 0x11],
            *[0x41, 0x11, 0x02, 0xCC],
            *[0xBE, 0x01, 0xFF, 0x12],
            *[0xBA],
            *[0xBE, 0x0A, 0xFF, 0x13],
            *[0xBA],
            *[0x0D, 0x14, 0x2A],
            *[0xBA],
        ]
    )
    machine = code_machine(program, version=5, saves=MemorySlot())

    machine.run()

    assert_that(machine.memory.read_word(G1_ADDRESS)).is_equal_to(2)
    assert_that(machine.memory.read_word(0x108)).is_equal_to(42)


# Undo levels stack and unwind LIFO: two captures, two restores,
# and the SECOND restore lands on the OLDER state -- g4 finishes 0,
# its value at the first capture, though it was 1 at the second
# (§15 restore_undo; Praxix's multiundo).
def test_undo_levels_unwind_newest_first(
    code_machine: Callable[..., Machine],
) -> None:
    #   $40  save_undo -> g0        (older capture: g4 = 0)
    #   $44  je g0, 2 [-> $5d]
    #   $48  store g4, 1
    #   $4b  save_undo -> g1        (newer capture: g4 = 1)
    #   $4f  je g1, 2 [-> $58]
    #   $53  restore_undo -> g2     (pops the newer)
    #   $57  quit
    #   $58  restore_undo -> g3     (pops the older)
    #   $5c  quit
    #   $5d  store g5, 42
    #   $60  quit
    program = bytes(
        [
            *[0xBE, 0x09, 0xFF, 0x10],
            *[0x41, 0x10, 0x02, 0xD7],
            *[0x0D, 0x14, 0x01],
            *[0xBE, 0x09, 0xFF, 0x11],
            *[0x41, 0x11, 0x02, 0xC7],
            *[0xBE, 0x0A, 0xFF, 0x12],
            *[0xBA],
            *[0xBE, 0x0A, 0xFF, 0x13],
            *[0xBA],
            *[0x0D, 0x15, 0x2A],
            *[0xBA],
        ]
    )
    machine = code_machine(program, version=5)

    machine.run()

    # The final state is the OLDER capture's: g1 and g4 rewound to 0,
    # though g1 was transiently 2 to route control. Both captures
    # consumed is the LIFO proof -- a FIFO would have ended the run
    # at the first restore with the newer one still in hand.
    assert_that(machine.memory.read_word(G0_ADDRESS)).is_equal_to(2)
    assert_that(machine.memory.read_word(G1_ADDRESS)).is_zero()
    assert_that(machine.memory.read_word(0x108)).is_zero()
    assert_that(machine.memory.read_word(0x10A)).is_equal_to(42)
    assert_that(len(machine._undo)).is_zero()


# The stack holds UNDO_DEPTH captures; the deque quietly forgets the
# oldest beyond that, bounding the memory spent.
def test_undo_captures_stop_at_the_depth_cap(
    code_machine: Callable[..., Machine],
) -> None:
    program = bytes([*[0xBE, 0x09, 0xFF, 0x10] * 17, 0xBA])
    machine = code_machine(program, version=5)

    machine.run()

    assert_that(len(machine._undo)).is_equal_to(16)


# A slot that refuses the write -- or no slot at all -- makes the
# table save answer 0, the same failure the game save reports.
def test_a_refused_table_save_answers_0(
    code_machine: Callable[..., Machine],
) -> None:
    program = bytes([0xBE, 0x00, 0x13, 0x01, 0x20, 0x04, 0x01, 0x40, 0x10, 0xBA])
    machine = code_machine(program, version=5, saves=MemorySlot(writable=False))

    for offset, value in enumerate([3, ord("m"), ord("a"), ord("p")]):
        machine.memory.write_byte(0x140 + offset, value)

    machine.run()

    assert_that(machine.memory.read_word(G0_ADDRESS)).is_zero()
