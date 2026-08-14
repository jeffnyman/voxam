from collections.abc import Callable

import pytest
from assertpy import assert_that

from voxam.errors import ZMachineArithmeticError, ZMachineMemoryError
from voxam.zmachine.machine import Machine

# Results land in global $10, the first word of the table at $100;
# global $11 lives at $102.
RESULT_VARIABLE = 0x10
RESULT_ADDRESS = 0x100
SECOND_VARIABLE = 0x11
SECOND_ADDRESS = 0x102

# A scratch area in dynamic memory, clear of the globals table.
TABLE = 0x120


def run(machine: Machine) -> int:
    machine.run()

    return machine.memory.read_word(RESULT_ADDRESS)


def test_adds_small_constants(code_machine: Callable[..., Machine]) -> None:
    machine = code_machine(bytes([0x14, 5, 3, RESULT_VARIABLE, 0xBA]))

    assert_that(run(machine)).is_equal_to(8)


# Arithmetic is signed and wraps: 32767 + 1 is -32768, and -1 + 1 is 0
# (§2.2, §2.3.2). Large constants need variable-form 2OP encoding.
@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [(0x7FFF, 0x0001, 0x8000), (0xFFFF, 0x0001, 0x0000)],
)
def test_addition_wraps_at_the_sign_boundary(
    left: int, right: int, expected: int, code_machine: Callable[..., Machine]
) -> None:
    main = bytes([0xD4, 0x0F, *left.to_bytes(2, "big"), *right.to_bytes(2, "big")])
    machine = code_machine(main + bytes([RESULT_VARIABLE, 0xBA]))

    assert_that(run(machine)).is_equal_to(expected)


def test_subtraction_can_go_negative(code_machine: Callable[..., Machine]) -> None:
    machine = code_machine(bytes([0x15, 3, 5, RESULT_VARIABLE, 0xBA]))

    assert_that(run(machine)).is_equal_to(0xFFFE)


def test_multiplies_and_wraps(code_machine: Callable[..., Machine]) -> None:
    machine = code_machine(bytes([0x16, 6, 7, RESULT_VARIABLE, 0xBA]))

    assert_that(run(machine)).is_equal_to(42)

    overflow = bytes([0xD6, 0x0F, 0x40, 0x00, 0x00, 0x04, RESULT_VARIABLE, 0xBA])

    assert_that(run(code_machine(overflow))).is_equal_to(0)


# Division truncates toward zero, so -7 / 2 is -3, not Python's -4
# (§2.2.1). All four sign combinations pin the rule.
@pytest.mark.parametrize(
    ("dividend", "divisor", "expected"),
    [
        (7, 2, 3),
        (-7, 2, -3),
        (7, -2, -3),
        (-7, -2, 3),
    ],
)
def test_division_truncates_toward_zero(
    dividend: int, divisor: int, expected: int, code_machine: Callable[..., Machine]
) -> None:
    main = bytes(
        [
            0xD7,
            0x0F,
            *(dividend & 0xFFFF).to_bytes(2, "big"),
            *(divisor & 0xFFFF).to_bytes(2, "big"),
            RESULT_VARIABLE,
            0xBA,
        ]
    )

    assert_that(run(code_machine(main))).is_equal_to(expected & 0xFFFF)


# The remainder's sign follows the dividend (§2.2.1).
@pytest.mark.parametrize(
    ("dividend", "divisor", "expected"),
    [(7, 2, 1), (-7, 2, -1), (7, -2, 1)],
)
def test_remainder_follows_the_dividend(
    dividend: int, divisor: int, expected: int, code_machine: Callable[..., Machine]
) -> None:
    main = bytes(
        [
            0xD8,
            0x0F,
            *(dividend & 0xFFFF).to_bytes(2, "big"),
            *(divisor & 0xFFFF).to_bytes(2, "big"),
            RESULT_VARIABLE,
            0xBA,
        ]
    )

    assert_that(run(code_machine(main))).is_equal_to(expected & 0xFFFF)


# Dividing by zero must halt the interpreter (§2.3.1), for div and
# mod alike.
@pytest.mark.parametrize("opcode_byte", [0xD7, 0xD8])
def test_division_by_zero_halts(
    opcode_byte: int, code_machine: Callable[..., Machine]
) -> None:
    main = bytes([opcode_byte, 0x0F, 0x00, 0x07, 0x00, 0x00, RESULT_VARIABLE, 0xBA])
    machine = code_machine(main)

    with pytest.raises(ZMachineArithmeticError, match="division by zero"):
        machine.run()


def test_loadw_reads_a_table_word(code_machine: Callable[..., Machine]) -> None:
    main = bytes([0xCF, 0x0F, 0x01, 0x20, 0x00, 0x01, RESULT_VARIABLE, 0xBA])
    machine = code_machine(main)
    machine.memory.write_word(TABLE + 2, 0xBEEF)

    assert_that(run(machine)).is_equal_to(0xBEEF)


def test_loadb_reads_a_table_byte(code_machine: Callable[..., Machine]) -> None:
    main = bytes([0xD0, 0x0F, 0x01, 0x20, 0x00, 0x03, RESULT_VARIABLE, 0xBA])
    machine = code_machine(main)
    machine.memory.write_byte(TABLE + 3, 0xAB)

    assert_that(run(machine)).is_equal_to(0xAB)


def test_storew_writes_a_table_word(code_machine: Callable[..., Machine]) -> None:
    main = bytes([0xE1, 0x03, 0x01, 0x20, 0x00, 0x01, 0xBE, 0xEF, 0xBA])
    machine = code_machine(main)

    machine.run()

    assert_that(machine.memory.read_word(TABLE + 2)).is_equal_to(0xBEEF)


def test_storeb_writes_a_table_byte(code_machine: Callable[..., Machine]) -> None:
    main = bytes([0xE2, 0x07, 0x01, 0x20, 0x00, 0x03, 0xAB, 0xBA])
    machine = code_machine(main)

    machine.run()

    assert_that(machine.memory.read_byte(TABLE + 3)).is_equal_to(0xAB)


# storeb's operand is a word, and a large one lands as its least
# significant byte -- the same rule §15 spells out for put_prop
# into one-byte properties. Sherlock stores $ffff as a flag while
# the sun rises over the Abbey, and earned the settlement.
def test_storeb_keeps_the_least_significant_byte(
    code_machine: Callable[..., Machine],
) -> None:
    main = bytes([0xE2, 0x03, 0x01, 0x20, 0x00, 0x03, 0xFF, 0xFF, 0xBA])
    machine = code_machine(main)

    machine.run()

    assert_that(machine.memory.read_byte(TABLE + 3)).is_equal_to(0xFF)


# The memory guards still govern: a storew aimed at static memory is
# rejected exactly as a raw write would be (§1.1.2).
def test_storew_cannot_reach_static_memory(
    code_machine: Callable[..., Machine],
) -> None:
    main = bytes([0xE1, 0x03, 0x01, 0xC0, 0x00, 0x00, 0x00, 0x01])
    machine = code_machine(main)

    with pytest.raises(ZMachineMemoryError, match="only dynamic memory"):
        machine.run()


def test_store_writes_the_referenced_variable(
    code_machine: Callable[..., Machine],
) -> None:
    machine = code_machine(bytes([0x0D, RESULT_VARIABLE, 42, 0xBA]))

    assert_that(run(machine)).is_equal_to(42)


# The subtlest trap in the instruction set (§6.3.4): store and load
# referencing variable $00 work on the stack top in place. The chain
# pushes 11, overwrites it with 42, loads it without pulling, and
# only the final store pops -- both globals must see 42, and neither
# step may underflow.
def test_store_and_load_treat_the_stack_top_in_place(
    code_machine: Callable[..., Machine],
) -> None:
    program = bytes(
        [
            0xE8,
            0x7F,
            0x0B,  # push 11
            0x0D,
            0x00,
            0x2A,  # store [sp] 42: replaces the top
            0x9E,
            0x00,
            RESULT_VARIABLE,  # load [sp]: reads, no pull
            0x2D,
            SECOND_VARIABLE,
            0x00,  # store g11 <- sp: pops
            0xBA,
        ]
    )
    machine = code_machine(program)

    machine.run()

    assert_that(machine.memory.read_word(RESULT_ADDRESS)).is_equal_to(42)
    assert_that(machine.memory.read_word(SECOND_ADDRESS)).is_equal_to(42)


# inc is signed, so a variable holding -1 increments to 0, and dec
# wraps 0 down to -1 (§15).
def test_inc_and_dec_are_signed(code_machine: Callable[..., Machine]) -> None:
    machine = code_machine(bytes([0x95, RESULT_VARIABLE, 0xBA]))
    machine.memory.write_word(RESULT_ADDRESS, 0xFFFF)

    assert_that(run(machine)).is_equal_to(0)

    machine = code_machine(bytes([0x96, RESULT_VARIABLE, 0xBA]))

    assert_that(run(machine)).is_equal_to(0xFFFF)


def test_inc_steps_the_stack_top_in_place(
    code_machine: Callable[..., Machine],
) -> None:
    program = bytes(
        [
            0xE8,
            0x7F,
            0x05,  # push 5
            0x95,
            0x00,  # inc [sp] in place
            0x2D,
            SECOND_VARIABLE,
            0x00,  # store g11 <- sp: pops
            0xBA,
        ]
    )
    machine = code_machine(program)

    machine.run()

    assert_that(machine.memory.read_word(SECOND_ADDRESS)).is_equal_to(6)


# A reference operand of type Variable is indirect: the variable
# number is fetched from that variable first (§4.2.3). Global $11
# holds the number $10, so "inc [g11]" increments global $10.
def test_references_can_be_indirect(code_machine: Callable[..., Machine]) -> None:
    machine = code_machine(bytes([0xA5, SECOND_VARIABLE, 0xBA]))
    machine.memory.write_word(SECOND_ADDRESS, RESULT_VARIABLE)
    machine.memory.write_word(RESULT_ADDRESS, 7)

    assert_that(run(machine)).is_equal_to(8)


def shifter(opcode: int, number: int, places: int) -> bytes:
    return bytes(
        [
            0xBE,
            opcode,
            0x0F,
            *number.to_bytes(2, "big"),
            *(places & 0xFFFF).to_bytes(2, "big"),
            RESULT_VARIABLE,
            0xBA,
        ]
    )


# Both shifts move left for positive places and wrap out the top
# (§15 log_shift, art_shift); leftward they are indistinguishable.
@pytest.mark.parametrize("opcode", [0x02, 0x03])
@pytest.mark.parametrize(
    ("number", "places", "expected"),
    [(0x0001, 3, 0x0008), (0x8000, 1, 0x0000), (0xFFFF, 1, 0xFFFE), (42, 0, 42)],
)
def test_shifts_left_and_wraps(
    opcode: int,
    number: int,
    places: int,
    expected: int,
    code_machine: Callable[..., Machine],
) -> None:
    machine = code_machine(shifter(opcode, number, places), version=5)

    assert_that(run(machine)).is_equal_to(expected)


# Rightward they part ways: log_shift zeroes the sign in, art_shift
# preserves it on the way down (§15 log_shift, art_shift).
@pytest.mark.parametrize(
    ("opcode", "number", "places", "expected"),
    [
        (0x02, 0x8000, -1, 0x4000),
        (0x02, 0xFFFF, -12, 0x000F),
        (0x03, 0x8000, -1, 0xC000),
        (0x03, 0xFFFE, -1, 0xFFFF),
        (0x03, 0x0008, -3, 0x0001),
    ],
)
def test_right_shifts_differ_on_the_sign(
    opcode: int,
    number: int,
    places: int,
    expected: int,
    code_machine: Callable[..., Machine],
) -> None:
    machine = code_machine(shifter(opcode, number, places), version=5)

    assert_that(run(machine)).is_equal_to(expected)


# Beyond -15 to +15 the Standard declares behaviour undefined
# (§15); Praxix probes the zone on purpose, marking its assertions
# "unspecified", so the shifts complete with the conventional
# answer instead of halting: a word shifted 16 or more places holds
# nothing -- except the arithmetic right shift, whose sign fills
# forever. The extreme distances also prove the clamp: no giant
# intermediate integer, same settled outcome.
@pytest.mark.parametrize(
    ("opcode", "number", "places", "expected"),
    [
        (0x02, 0x0011, 16, 0x0000),
        (0x02, 0x4001, -16, 0x0000),
        (0x02, 0xFFFF, -17, 0x0000),
        (0x03, 0x0011, 16, 0x0000),
        (0x03, 0x7FFF, -16, 0x0000),
        (0x03, 0xFFFF, -16, 0xFFFF),
        (0x03, 0x8000, -32768, 0xFFFF),
        (0x02, 0x0001, 32767, 0x0000),
    ],
)
def test_overshifts_settle_instead_of_halting(
    opcode: int,
    number: int,
    places: int,
    expected: int,
    code_machine: Callable[..., Machine],
) -> None:
    machine = code_machine(shifter(opcode, number, places), version=5)

    assert_that(run(machine)).is_equal_to(expected)


# Table indices are signed by the conventions §15 left open: Inform
# emits negative indices to step backward from a table, and the sum
# wraps to what a 16-bit address can carry. Praxix found both
# missing in its second minute; eleven recorded games never used
# either.
def test_a_negative_word_index_steps_backward(
    code_machine: Callable[..., Machine],
) -> None:
    program = bytes([0xCF, 0x0F, 0x01, 0x04, 0xFF, 0xFF, RESULT_VARIABLE, 0xBA])
    machine = code_machine(program)
    machine.memory.write_word(0x102, 0xBEEF)

    assert_that(run(machine)).is_equal_to(0xBEEF)


def test_a_negative_byte_index_steps_backward(
    code_machine: Callable[..., Machine],
) -> None:
    program = bytes([0xD0, 0x0F, 0x01, 0x04, 0xFF, 0xFF, RESULT_VARIABLE, 0xBA])
    machine = code_machine(program)
    machine.memory.write_byte(0x103, 0x2A)

    assert_that(run(machine)).is_equal_to(0x2A)


def test_a_negative_index_stores_backward(
    code_machine: Callable[..., Machine],
) -> None:
    program = bytes([0xE1, 0x07, 0x01, 0x08, 0xFF, 0xFE, 0x2A, 0xBA])
    machine = code_machine(program)

    machine.run()

    assert_that(machine.memory.read_word(0x104)).is_equal_to(42)


def test_the_table_address_wraps_at_16_bits(
    code_machine: Callable[..., Machine],
) -> None:
    program = bytes([0xCF, 0x0F, 0xFF, 0x06, 0x00, 0x80, RESULT_VARIABLE, 0xBA])
    machine = code_machine(program)

    assert_that(run(machine)).is_equal_to(0x0040)
