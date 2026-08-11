from collections.abc import Callable

from assertpy import assert_that

from voxam.zmachine.machine import Machine

# G0 receives the delivered address; G1 is set to 1 only when the
# branch falls through -- the "no match" marker.
FOUND = 0x100
MISSED = 0x102
TABLE = 0x150

# The shared tail: store to G0, branch on true over the miss marker
# (store G1 <- 1), then quit.
TAIL = bytes([0x10, 0xC5, 0x0D, 0x11, 0x01, 0xBA])


def scanner(
    code_machine: Callable[..., Machine], program: bytes, table: bytes
) -> Machine:
    machine = code_machine(program + TAIL, version=4)

    for offset, value in enumerate(table):
        machine.memory.write_byte(TABLE + offset, value)

    machine.run()

    return machine


# Three operands take the default form $82: word comparison over
# two-byte fields (§15 scan_table). The match delivers the field's
# address and branches past the miss marker.
def test_scan_finds_a_word_and_branches(
    code_machine: Callable[..., Machine],
) -> None:
    program = bytes([0xF7, 0x03, 0xBE, 0xEF, 0x01, 0x50, 0x00, 0x03])
    machine = scanner(
        code_machine, program, bytes([0x11, 0x11, 0xBE, 0xEF, 0x22, 0x22])
    )

    assert_that(machine.memory.read_word(FOUND)).is_equal_to(TABLE + 2)
    assert_that(machine.memory.read_word(MISSED)).is_zero()


def test_scan_misses_with_zero_and_no_branch(
    code_machine: Callable[..., Machine],
) -> None:
    program = bytes([0xF7, 0x03, 0x0B, 0xAD, 0x01, 0x50, 0x00, 0x03])
    machine = scanner(
        code_machine, program, bytes([0x11, 0x11, 0xBE, 0xEF, 0x22, 0x22])
    )

    assert_that(machine.memory.read_word(FOUND)).is_zero()
    assert_that(machine.memory.read_word(MISSED)).is_equal_to(1)


# Form $01: byte comparison over one-byte fields.
def test_the_form_byte_selects_byte_comparison(
    code_machine: Callable[..., Machine],
) -> None:
    program = bytes([0xF7, 0x45, 0xAB, 0x01, 0x50, 0x04, 0x01])
    machine = scanner(code_machine, program, bytes([0x11, 0x22, 0xAB, 0x33]))

    assert_that(machine.memory.read_word(FOUND)).is_equal_to(TABLE + 2)


# Form $84: word comparison over FOUR-byte fields. The padding word
# of the first field is a decoy copy of the target: only an
# implementation that strides by the field length skips it and finds
# the true second field (§15 scan_table).
def test_the_form_byte_sets_the_field_stride(
    code_machine: Callable[..., Machine],
) -> None:
    program = bytes([0xF7, 0x05, 0xBE, 0xEF, 0x01, 0x50, 0x03, 0x84])
    machine = scanner(
        code_machine,
        program,
        bytes([0x11, 0x11, 0xBE, 0xEF, 0xBE, 0xEF, 0x00, 0x00, 0x22, 0x22, 0x00, 0x00]),
    )

    assert_that(machine.memory.read_word(FOUND)).is_equal_to(TABLE + 4)


# A zero-length table is legal and empty-handed.
def test_scanning_nothing_finds_nothing(
    code_machine: Callable[..., Machine],
) -> None:
    program = bytes([0xF7, 0x03, 0xBE, 0xEF, 0x01, 0x50, 0x00, 0x00])
    machine = scanner(code_machine, program, bytes([0xBE, 0xEF]))

    assert_that(machine.memory.read_word(FOUND)).is_zero()
    assert_that(machine.memory.read_word(MISSED)).is_equal_to(1)
