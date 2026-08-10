from collections.abc import Callable

import pytest
from assertpy import assert_that

from voxam.errors import ZMachineStackError, ZMachineUnimplementedError
from voxam.frontend import PlainFrontend
from voxam.zmachine.machine import Machine
from voxam.zmachine.story import Story

CODE = 0x40

# Synthetic programs place a first routine at $60 and a second at $70;
# under Version 3's scale factor of 2, those are packed 0x30 and 0x38.
ROUTINE_A_PACKED = bytes([0x00, 0x30])
ROUTINE_B_PACKED = bytes([0x00, 0x38])

# The result global: variable $10, first entry of the table at $100.
RESULT_VARIABLE = 0x10
RESULT_ADDRESS = 0x100


def layout(main: bytes, routine_a: bytes = b"", routine_b: bytes = b"") -> bytes:
    code = bytearray(0x40)
    code[: len(main)] = main
    code[0x20 : 0x20 + len(routine_a)] = routine_a
    code[0x30 : 0x30 + len(routine_b)] = routine_b

    return bytes(code)


def test_quit_halts_the_machine(code_machine: Callable[..., Machine]) -> None:
    machine = code_machine(layout(bytes([0xBA])))

    assert_that(machine.running).is_true()

    machine.run()

    assert_that(machine.running).is_false()


# The whole call contract of §6.4: enter the routine, run it, return
# its value into the caller's chosen variable, resume after the call.
def test_a_call_delivers_the_routines_result(
    code_machine: Callable[..., Machine],
) -> None:
    main = bytes([0xE0, 0x3F, *ROUTINE_A_PACKED, RESULT_VARIABLE, 0xBA])
    returns_42 = bytes([0x00, 0x9B, 0x2A])
    machine = code_machine(layout(main, returns_42))

    machine.run()

    assert_that(machine.memory.read_word(RESULT_ADDRESS)).is_equal_to(42)


# One argument, two locals: the argument lands in local 1 (§6.4.4)
# while local 2 keeps its header default (§6.4.4.1) -- verified by
# returning each local in turn.
@pytest.mark.parametrize(("local", "expected"), [(0x01, 99), (0x02, 7)])
def test_arguments_arrive_and_defaults_survive(
    local: int, expected: int, code_machine: Callable[..., Machine]
) -> None:
    main = bytes([0xE0, 0x1F, *ROUTINE_A_PACKED, 99, RESULT_VARIABLE, 0xBA])
    returns_local = bytes([0x02, 0x00, 0x05, 0x00, 0x07, 0xAB, local])
    machine = code_machine(layout(main, returns_local))

    machine.run()

    assert_that(machine.memory.read_word(RESULT_ADDRESS)).is_equal_to(expected)


# A call to packed address 0 does nothing and returns false (§6.4.3).
def test_calling_address_0_returns_false(
    code_machine: Callable[..., Machine],
) -> None:
    main = bytes([0xE0, 0x3F, 0x00, 0x00, RESULT_VARIABLE, 0xBA])
    machine = code_machine(layout(main))
    machine.memory.write_word(RESULT_ADDRESS, 0xFFFF)

    machine.run()

    assert_that(machine.memory.read_word(RESULT_ADDRESS)).is_equal_to(0)


# rtrue returns 1 and rfalse returns 0 (§6.4.5).
@pytest.mark.parametrize(("opcode_byte", "expected"), [(0xB0, 1), (0xB1, 0)])
def test_rtrue_and_rfalse(
    opcode_byte: int, expected: int, code_machine: Callable[..., Machine]
) -> None:
    main = bytes([0xE0, 0x3F, *ROUTINE_A_PACKED, RESULT_VARIABLE, 0xBA])
    machine = code_machine(layout(main, bytes([0x00, opcode_byte])))
    machine.memory.write_word(RESULT_ADDRESS, 0xFFFF)

    machine.run()

    assert_that(machine.memory.read_word(RESULT_ADDRESS)).is_equal_to(expected)


def test_ret_popped_returns_the_top_of_stack(
    code_machine: Callable[..., Machine],
) -> None:
    main = bytes([0xE0, 0x3F, *ROUTINE_A_PACKED, RESULT_VARIABLE, 0xBA])
    push_then_return = bytes([0x00, 0xE8, 0x7F, 0x2A, 0xB8])
    machine = code_machine(layout(main, push_then_return))

    machine.run()

    assert_that(machine.memory.read_word(RESULT_ADDRESS)).is_equal_to(42)


# Storing a result to variable $00 pushes it onto the caller's stack
# (§6.3): routine A calls B with store variable 0, then ret_popped
# hands B's result onward to the outermost caller.
def test_a_result_stored_to_variable_0_lands_on_the_callers_stack(
    code_machine: Callable[..., Machine],
) -> None:
    main = bytes([0xE0, 0x3F, *ROUTINE_A_PACKED, RESULT_VARIABLE, 0xBA])
    relay = bytes([0x00, 0xE0, 0x3F, *ROUTINE_B_PACKED, 0x00, 0xB8])
    returns_42 = bytes([0x00, 0x9B, 0x2A])
    machine = code_machine(layout(main, relay, returns_42))

    machine.run()

    assert_that(machine.memory.read_word(RESULT_ADDRESS)).is_equal_to(42)


def test_unimplemented_opcodes_report_the_frontier(
    code_machine: Callable[..., Machine],
) -> None:
    machine = code_machine(layout(bytes([0xB4])))

    with pytest.raises(ZMachineUnimplementedError, match="not yet implemented"):
        machine.run()

    assert_that(machine.running).is_true()


def test_the_frontier_report_names_the_opcode_and_address(
    code_machine: Callable[..., Machine],
) -> None:
    machine = code_machine(layout(bytes([0xB4])))

    with pytest.raises(ZMachineUnimplementedError) as excinfo:
        machine.run()

    assert_that(excinfo.value.opcode_name).is_equal_to("nop")
    assert_that(excinfo.value.address).is_equal_to(CODE)
    assert_that(machine.pc).is_equal_to(CODE)


# call_vn throws the routine's result away (§6.4.1): the machine runs
# to quit and the result global keeps its sentinel. Version 5 scales
# packed addresses by 4, so the routine at $60 is packed 0x18.
def test_call_vn_discards_the_result(code_machine: Callable[..., Machine]) -> None:
    main = bytes([0xF9, 0x3F, 0x00, 0x18, 0xBA])
    machine = code_machine(layout(main, bytes([0x00, 0xB0])), version=5)
    machine.memory.write_word(RESULT_ADDRESS, 0xFFFF)

    machine.run()

    assert_that(machine.memory.read_word(RESULT_ADDRESS)).is_equal_to(0xFFFF)


def test_call_vn_to_address_0_stores_nothing(
    code_machine: Callable[..., Machine],
) -> None:
    main = bytes([0xF9, 0x3F, 0x00, 0x00, 0xBA])
    machine = code_machine(layout(main), version=5)
    machine.memory.write_word(RESULT_ADDRESS, 0xFFFF)

    machine.run()

    assert_that(machine.memory.read_word(RESULT_ADDRESS)).is_equal_to(0xFFFF)


# 'h' and 'i' are Z-characters 13 and 14; a single word, terminator
# bit set, holds them plus a padding 5: 0x8000 | 13<<10 | 14<<5 | 5
# (§3.2, §3.5.3, §3.7).
HI = bytes([0xB5, 0xC5])


def test_print_prints_the_inline_string(
    code_machine: Callable[..., Machine],
) -> None:
    output: list[str] = []
    main = bytes([0xB2, *HI, 0xBA])
    machine = code_machine(layout(main), output=output.append)

    machine.run()

    assert_that("".join(output)).is_equal_to("hi")


# print_ret prints its string, a new-line, and returns true (§14).
def test_print_ret_prints_and_returns_true(
    code_machine: Callable[..., Machine],
) -> None:
    output: list[str] = []
    main = bytes([0xE0, 0x3F, *ROUTINE_A_PACKED, RESULT_VARIABLE, 0xBA])
    machine = code_machine(layout(main, bytes([0x00, 0xB3, *HI])), output=output.append)

    machine.run()

    assert_that("".join(output)).is_equal_to("hi\n")
    assert_that(machine.memory.read_word(RESULT_ADDRESS)).is_equal_to(1)


def test_print_addr_prints_from_a_byte_address(
    code_machine: Callable[..., Machine],
) -> None:
    output: list[str] = []
    main = bytes([0x87, 0x00, 0x60, 0xBA])
    machine = code_machine(layout(main, HI), output=output.append)

    machine.run()

    assert_that("".join(output)).is_equal_to("hi")


# The string sits at byte address $60, which under Version 3's scale
# factor of 2 is packed 0x30 (§1.2.3).
def test_print_paddr_prints_from_a_packed_address(
    code_machine: Callable[..., Machine],
) -> None:
    output: list[str] = []
    main = bytes([0x8D, 0x00, 0x30, 0xBA])
    machine = code_machine(layout(main, HI), output=output.append)

    machine.run()

    assert_that("".join(output)).is_equal_to("hi")


def test_new_line_prints_a_newline(code_machine: Callable[..., Machine]) -> None:
    output: list[str] = []
    machine = code_machine(layout(bytes([0xBB, 0xBA])), output=output.append)

    machine.run()

    assert_that("".join(output)).is_equal_to("\n")


def test_print_char_prints_a_zscii_code(
    code_machine: Callable[..., Machine],
) -> None:
    output: list[str] = []
    main = bytes([0xE5, 0x7F, 0x41, 0xBA])
    machine = code_machine(layout(main), output=output.append)

    machine.run()

    assert_that("".join(output)).is_equal_to("A")


# print_num interprets its operand as signed (§2.2): 0xFFFF is -1.
@pytest.mark.parametrize(
    ("operand", "expected"), [([0x00, 0x2A], "42"), ([0xFF, 0xFF], "-1")]
)
def test_print_num_prints_signed_decimals(
    operand: list[int], expected: str, code_machine: Callable[..., Machine]
) -> None:
    output: list[str] = []
    main = bytes([0xE6, 0x3F, *operand, 0xBA])
    machine = code_machine(layout(main), output=output.append)

    machine.run()

    assert_that("".join(output)).is_equal_to(expected)


# call_1s and call_2s are the storing call variants for one and two
# operands (§14); Version 4 scales packed addresses by 4, so the
# routine at $60 is packed 0x18.
def test_call_1s_delivers_a_result(code_machine: Callable[..., Machine]) -> None:
    main = bytes([0x88, 0x00, 0x18, RESULT_VARIABLE, 0xBA])
    returns_42 = bytes([0x00, 0x9B, 0x2A])
    machine = code_machine(layout(main, returns_42), version=4)

    machine.run()

    assert_that(machine.memory.read_word(RESULT_ADDRESS)).is_equal_to(42)


def test_call_2s_passes_its_argument(code_machine: Callable[..., Machine]) -> None:
    main = bytes([0x19, 0x18, 0x07, RESULT_VARIABLE, 0xBA])
    returns_local = bytes([0x01, 0x00, 0x05, 0xAB, 0x01])
    machine = code_machine(layout(main, returns_local), version=4)

    machine.run()

    assert_that(machine.memory.read_word(RESULT_ADDRESS)).is_equal_to(7)


# call_1n and call_2n discard their results (§6.4.1): the sentinel
# global survives and the program still runs to quit.
@pytest.mark.parametrize(
    ("main", "routine"),
    [
        (bytes([0x8F, 0x00, 0x18, 0xBA]), bytes([0x00, 0xB0])),
        (bytes([0x1A, 0x18, 0x07, 0xBA]), bytes([0x01, 0xB0])),
    ],
)
def test_the_discarding_call_variants(
    main: bytes, routine: bytes, code_machine: Callable[..., Machine]
) -> None:
    machine = code_machine(layout(main, routine), version=5)
    machine.memory.write_word(RESULT_ADDRESS, 0xFFFF)

    machine.run()

    assert_that(machine.running).is_false()
    assert_that(machine.memory.read_word(RESULT_ADDRESS)).is_equal_to(0xFFFF)


# Seeding via a negative range yields 0 and enters the predictable
# state, whose rising sequence the next rolls follow; a range of 0
# re-randomizes and also yields 0 (§2.4, §15).
def test_random_seeds_rolls_and_rerandomizes(
    code_machine: Callable[..., Machine],
) -> None:
    program = bytes(
        [
            0xE7,
            0x3F,
            0xFF,
            0xFD,
            RESULT_VARIABLE,  # random -3: seed
            0xE7,
            0x7F,
            0x03,
            0x11,  # random 3 -> 1
            0xE7,
            0x7F,
            0x03,
            0x12,  # random 3 -> 2
            0xE7,
            0x7F,
            0x00,
            0x13,  # random 0: re-randomize -> 0
            0xBA,
        ]
    )
    machine = code_machine(layout(program))
    machine.memory.write_word(RESULT_ADDRESS, 0xFFFF)

    machine.run()

    assert_that(machine.memory.read_word(RESULT_ADDRESS)).is_equal_to(0)
    assert_that(machine.memory.read_word(0x102)).is_equal_to(1)
    assert_that(machine.memory.read_word(0x104)).is_equal_to(2)
    assert_that(machine.memory.read_word(0x106)).is_equal_to(0)


# A routine that calls itself forever: the §6.3.3 usage ceiling
# turns what a 1980s interpreter crashed on -- and an unbounded
# stack would hang on -- into a loud halt. Zork 1 release 15 has
# exactly this bug in its room-contents lister.
def test_infinite_recursion_halts_loudly(
    code_machine: Callable[..., Machine],
) -> None:
    main = bytes([0xE0, 0x3F, *ROUTINE_A_PACKED, RESULT_VARIABLE, 0xBA])
    calls_itself = bytes([0x00, 0xE0, 0x3F, *ROUTINE_A_PACKED, 0x00])
    machine = code_machine(layout(main, calls_itself))

    with pytest.raises(ZMachineStackError, match="runaway recursion"):
        machine.run()


# A session seed reaches the dice: rolling 100 under seeds 1137 and
# 42 gives the pinned first values 67 and 9. This is the wiring the
# --seed argument and future acceptance fixtures rely on.
@pytest.mark.parametrize(("seed", "expected"), [(1137, 67), (42, 9)])
def test_a_session_seed_reaches_the_dice(
    seed: int, expected: int, code_machine: Callable[..., Machine]
) -> None:
    main = bytes([0xE7, 0x7F, 0x64, RESULT_VARIABLE, 0xBA])
    machine = code_machine(layout(main), seed=seed)

    machine.run()

    assert_that(machine.memory.read_word(RESULT_ADDRESS)).is_equal_to(expected)


# A story bigger than 64K keeps strings in high memory beyond the
# game-read cap; print_paddr must reach them through the interpreter's
# fetch path (§1.1.3). Packed 0x8100 doubles to byte address $10200.
def test_print_paddr_reaches_high_memory_beyond_the_cap() -> None:
    data = bytearray(0x10800)
    data[0] = 3
    data[0x04:0x06] = (0x0200).to_bytes(2, "big")
    data[0x06:0x08] = (0x0040).to_bytes(2, "big")
    data[0x0C:0x0E] = (0x0100).to_bytes(2, "big")
    data[0x0E:0x10] = (0x0200).to_bytes(2, "big")
    data[0x40:0x44] = bytes([0x8D, 0x81, 0x00, 0xBA])
    data[0x10200:0x10202] = HI

    output: list[str] = []
    machine = Machine(Story(bytes(data)), PlainFrontend(output.append))

    machine.run()

    assert_that("".join(output)).is_equal_to("hi")


# The milestone: every fixture -- Version 6 and its §5.4 main-routine
# boot included -- runs its whole program for real and says hello.
@pytest.mark.parametrize("version", range(1, 9))
def test_every_fixture_says_hello(
    version: int, load_fixture: Callable[[int], Story]
) -> None:
    output: list[str] = []
    machine = Machine(load_fixture(version), PlainFrontend(output.append))

    machine.run()

    assert_that("".join(output)).is_equal_to("hello from all z machine versions")
    assert_that(machine.running).is_false()
