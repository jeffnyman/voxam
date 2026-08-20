from collections.abc import Callable

import pytest
from assertpy import assert_that

from voxam.errors import (
    ZMachineInstructionError,
    ZMachineScreenError,
    ZMachineStackError,
    ZMachineUnimplementedError,
)
from voxam.frontend import PlainFrontend
from voxam.scribe import Scribe
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


# call_vs2 is an ordinary call grown a second type byte for up to
# seven arguments (§4.4.3.1). Five arguments force the decoder
# through that byte, and returning the fifth local proves the whole
# chain delivered. Version 4: the packed scale is 4, so the routine
# at $60 is packed $18, and routine headers still carry initial
# values (§5.2.1).
def test_call_vs2_carries_extra_arguments(
    code_machine: Callable[..., Machine],
) -> None:
    main = bytes(
        [0xEC, 0x15, 0x5F, 0x00, 0x18, 11, 22, 33, 44, 55, RESULT_VARIABLE, 0xBA]
    )
    returns_fifth = bytes([0x05] + [0x00, 0x00] * 5 + [0xAB, 0x05])
    machine = code_machine(layout(main, returns_fifth), version=4)

    machine.run()

    assert_that(machine.memory.read_word(RESULT_ADDRESS)).is_equal_to(55)


# call_vn2 is the discarding twin: it runs the routine and stores
# nothing (§6.4.1) -- proven by a side effect with no home for a
# result. It arrives only in Version 5 (§14), where routine headers
# have shed their initial values (§5.2.1).
def test_call_vn2_discards_but_still_calls(
    code_machine: Callable[..., Machine],
) -> None:
    main = bytes([0xFA, 0x15, 0x5F, 0x00, 0x18, 1, 2, 3, 4, 5, 0xBA])
    stores_marker = bytes([0x05, 0x0D, 0x11, 0x2A, 0xB0])
    machine = code_machine(layout(main, stores_marker), version=5)

    machine.run()

    assert_that(machine.memory.read_word(RESULT_ADDRESS + 2)).is_equal_to(42)
    assert_that(machine.memory.read_word(RESULT_ADDRESS)).is_zero()


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


# Code at or above the static-memory base cannot change (§1.1), so
# its decoded instructions are cached with their handlers -- the
# speed that makes Inform 7 games playable. The planted story puts
# its code at $1c0, exactly the static base, and the cache fills.
def test_static_code_is_decoded_once_and_cached() -> None:
    data = bytearray(512)
    data[0] = 3
    data[0x04:0x06] = (0x01C0).to_bytes(2, "big")
    data[0x06:0x08] = (0x01C0).to_bytes(2, "big")
    data[0x0C:0x0E] = (0x0100).to_bytes(2, "big")
    data[0x0E:0x10] = (0x01C0).to_bytes(2, "big")
    data[0x1C0:0x1CC] = bytes(
        [
            *[0x0D, 0x11, 0x02],
            *[0x0D, 0x10, 0x2A],
            *[0x04, 0x11, 0x01, 0x3F, 0xFA],
            0xBA,
        ]
    )
    machine = Machine(Story(bytes(data)), PlainFrontend(lambda _t: None), lambda: "")

    machine.run()

    assert_that(machine.memory.read_word(0x100)).is_equal_to(42)
    assert_that(machine._code_cache).contains_key(0x1C0, 0x1C3, 0x1C6)


# Code in dynamic memory may legally rewrite itself, so it is
# decoded fresh on every visit: the program overwrites its own
# store's constant mid-loop, and the second pass sees the new
# value. A cache without the static floor would replay the old 42.
def test_dynamic_code_may_rewrite_itself(
    code_machine: Callable[..., Machine],
) -> None:
    program = bytes(
        [
            *[0x0D, 0x11, 0x02],
            *[0x0D, 0x10, 0x2A],
            *[0xE2, 0x17, 0x00, 0x45, 0x00, 0x63],
            *[0x04, 0x11, 0x01, 0x3F, 0xF4],
            0xBA,
        ]
    )
    machine = code_machine(layout(program))

    machine.run()

    assert_that(machine.memory.read_word(0x100)).is_equal_to(0x63)


# Every §14 opcode now has a handler; the frontiers that remain are
# features inside opcodes -- the transcript stream here -- and they
# still halt loudly, naming themselves and their address, with the
# machine stopped exactly where it happened.
def test_unimplemented_opcodes_report_the_frontier(
    code_machine: Callable[..., Machine],
) -> None:
    machine = code_machine(layout(bytes([0xF3, 0x7F, 0x02])))

    with pytest.raises(ZMachineUnimplementedError, match="not yet implemented"):
        machine.run()

    assert_that(machine.running).is_true()


def test_the_frontier_report_names_the_feature_and_address(
    code_machine: Callable[..., Machine],
) -> None:
    machine = code_machine(layout(bytes([0xF3, 0x7F, 0x02])))

    with pytest.raises(ZMachineUnimplementedError) as excinfo:
        machine.run()

    assert_that(excinfo.value.opcode_name).is_equal_to("output stream 2")
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


# pop throws away the top of the stack without a home for it (§15
# pop) -- proven by pushing two values, popping one, and pulling
# what remains.
def test_pop_discards_the_stack_top(code_machine: Callable[..., Machine]) -> None:
    program = bytes(
        [0xE8, 0x7F, 0x2A, 0xE8, 0x7F, 0x63, 0xB9, 0xE9, 0x7F, RESULT_VARIABLE, 0xBA]
    )
    machine = code_machine(program)

    machine.run()

    assert_that(machine.memory.read_word(RESULT_ADDRESS)).is_equal_to(42)


# catch's cookie is specified exactly: the number of frames on the
# call stack (§15 catch, Quetzal §6.2). At rest, only the base
# frame stands.
def test_catch_stores_the_frame_count(code_machine: Callable[..., Machine]) -> None:
    machine = code_machine(bytes([0xB9, RESULT_VARIABLE, 0xBA]), version=5)

    machine.run()

    assert_that(machine.memory.read_word(RESULT_ADDRESS)).is_equal_to(1)


# throw unwinds to the caught frame and returns from it (§15
# throw): A catches, calls B, B calls C, and C's throw returns 42
# from A directly -- neither B's 98 nor A's own 99 is ever reached.
def test_throw_returns_across_intervening_frames(
    code_machine: Callable[..., Machine],
) -> None:
    main = bytes([0xE0, 0x3F, 0x00, 0x18, RESULT_VARIABLE, 0xBA])
    a = bytes([0x01, 0xB9, 0x01, 0xF9, 0x2F, 0x00, 0x1C, 0x01, 0x9B, 0x63])
    b = bytes([0x01, 0xF9, 0x2F, 0x00, 0x20, 0x01, 0x9B, 0x62])
    c = bytes([0x01, 0x3C, 0x2A, 0x01])

    code = bytearray(0x60)
    code[: len(main)] = main
    code[0x20 : 0x20 + len(a)] = a
    code[0x30 : 0x30 + len(b)] = b
    code[0x40 : 0x40 + len(c)] = c
    machine = code_machine(bytes(code), version=5)

    machine.run()

    assert_that(machine.memory.read_word(RESULT_ADDRESS)).is_equal_to(42)


# A cookie naming more frames than exist belongs to a catch that
# already returned; nothing can throw back to it (§15 throw).
def test_throwing_to_a_dead_frame_halts(
    code_machine: Callable[..., Machine],
) -> None:
    machine = code_machine(bytes([0x3C, 0x2A, 0x63, 0xBA]), version=5)

    with pytest.raises(ZMachineStackError, match="already returned"):
        machine.run()


# print_unicode prints by codepoint; controls and surrogates get the
# question mark §3.8.5.4 prescribes for missing letter-forms.
def test_print_unicode_prints_by_codepoint(
    code_machine: Callable[..., Machine],
) -> None:
    output: list[str] = []
    program = bytes([0xBE, 0x0B, 0x3F, 0x03, 0xB1, 0xBE, 0x0B, 0x3F, 0xD8, 0x00, 0xBA])
    machine = code_machine(program, version=5, output=output.append)

    machine.run()

    assert_that("".join(output)).is_equal_to("\u03b1?")


# check_unicode answers with a bitmap: bit 0 printable, bit 1
# receivable from the keyboard (§15 check_unicode). An alpha prints
# but ZSCII cannot carry it under the default table; a-umlaut does
# both; a surrogate does neither.
@pytest.mark.parametrize(
    ("codepoint", "expected"),
    [(0x00E4, 3), (0x03B1, 1), (0xD800, 0), (0x0007, 0)],
)
def test_check_unicode_reports_print_and_input(
    codepoint: int, expected: int, code_machine: Callable[..., Machine]
) -> None:
    program = bytes(
        [0xBE, 0x0C, 0x3F, *codepoint.to_bytes(2, "big"), RESULT_VARIABLE, 0xBA]
    )
    machine = code_machine(program, version=5)

    machine.run()

    assert_that(machine.memory.read_word(RESULT_ADDRESS)).is_equal_to(expected)


# The Standard revision at $32/$33 now reads 1.1 (§11.1.5).
def test_boot_declares_standard_1_1(code_machine: Callable[..., Machine]) -> None:
    machine = code_machine(bytes([0xBA]))

    assert_that(machine.memory.read_word(0x32)).is_equal_to(0x0101)


def stacked_v6_machine(
    code: bytes,
    words: dict[int, int] | None = None,
    frontend: PlainFrontend | None = None,
    scribe: Scribe | None = None,
) -> Machine:
    """A Version 6 machine: main routine at $100, globals at $80.

    Version 6 boots by calling a packed main routine (§5.4), so
    the code goes inside one; extra words seed user-stack tables.
    """

    data = bytearray(512)
    data[0] = 6
    data[0x04:0x06] = (0x01C0).to_bytes(2, "big")
    data[0x06:0x08] = (0x0040).to_bytes(2, "big")
    data[0x0C:0x0E] = (0x0080).to_bytes(2, "big")
    data[0x0E:0x10] = (0x01C0).to_bytes(2, "big")
    data[0x100] = 0x00
    data[0x101 : 0x101 + len(code)] = code

    for offset, value in (words or {}).items():
        data[offset : offset + 2] = value.to_bytes(2, "big")

    return Machine(Story(bytes(data)), frontend, lambda: "", scribe=scribe)


# buffer_screen remembers the advice and stores the mode each call
# replaces; -1 forces an update through -- instantly satisfied on
# glasses that paint at once -- without changing the mode
# (§8.8.7.1). Voxam ignoring the advice while acting as mode 0 is
# the conduct §8.8.7 itself licenses.
def test_buffer_screen_stores_the_mode_it_replaces() -> None:
    machine = stacked_v6_machine(
        bytes(
            [
                *[0xBE, 0x1D, 0x7F, 0x01, 0x10],
                *[0xBE, 0x1D, 0x3F, 0xFF, 0xFF, 0x11],
                *[0xBE, 0x1D, 0x7F, 0x00, 0x12],
                0xBA,
            ]
        )
    )

    machine.run()

    assert_that(machine.memory.read_word(0x80)).is_equal_to(0)
    assert_that(machine.memory.read_word(0x82)).is_equal_to(1)
    assert_that(machine.memory.read_word(0x84)).is_equal_to(1)


# A mode §8.8.7.1 does not define halts loudly.
def test_buffer_screen_refuses_undefined_modes() -> None:
    machine = stacked_v6_machine(bytes([0xBE, 0x1D, 0x7F, 0x05, 0x10, 0xBA]))

    with pytest.raises(ZMachineInstructionError, match="0, 1, and -1"):
        machine.run()


# In Version 6 the game writes its own transcript: the player's
# input is NOT echoed to stream 2 by the interpreter (§7.1.1.1).
def test_version_6_reads_do_not_echo_to_the_transcript() -> None:
    class PagingScribe:
        def __init__(self) -> None:
            self.pages: list[str] = []

        def transcript(self, text: str) -> None:
            self.pages.append(text)

        def command(self, line: str) -> None:
            """Never asked for in this test."""

        def playback(self) -> str | None:
            """Never asked for in this test."""

    scribe = PagingScribe()
    machine = stacked_v6_machine(
        bytes([0xF3, 0x7F, 0x02])
        + bytes([0xB2, 0xB5, 0xC5])
        + bytes([0xE4, 0x3F, 0x00, 0x60, 0x00, 0xBA]),
        words={0x60: 0x1400},
        scribe=scribe,
    )

    machine.run()

    assert_that(scribe.pages).is_equal_to(["hi"])


# A §6.6 user stack counts spare slots downward from its capacity,
# and the count doubles as the write index: pushing 42 onto a
# three-slot stack lands it in word 3, and the Version 6 pull --
# which stores, unlike its elders -- reads it back and walks the
# count up again (§15 push_stack, §15 pull).
def test_a_user_stack_round_trips_through_push_and_pull() -> None:
    machine = stacked_v6_machine(
        bytes(
            [
                *[0xBE, 0x18, 0x5F, 0x2A, 0x60, 0xC2],
                *[0xE9, 0x7F, 0x60, 0x10],
                0xBA,
            ]
        ),
        words={0x60: 3},
    )

    machine.run()

    assert_that(machine.memory.read_word(0x80)).is_equal_to(42)
    assert_that(machine.memory.read_word(0x60)).is_equal_to(3)
    assert_that(machine.memory.read_word(0x66)).is_equal_to(42)


# A full stack refuses quietly: nothing is written, the count does
# not move, and the branch is not taken -- §15 says overflow "is
# not an error condition". With a slot free, the same push takes
# its branch over the marker.
def test_push_stack_branches_only_on_success() -> None:
    overflowing = bytes(
        [
            *[0xBE, 0x18, 0x5F, 0x07, 0x60, 0xC5],
            *[0x0D, 0x11, 0x63],
            0xBA,
        ]
    )
    full = stacked_v6_machine(overflowing, words={0x60: 0})

    full.run()

    assert_that(full.memory.read_word(0x82)).is_equal_to(0x63)
    assert_that(full.memory.read_word(0x60)).is_zero()

    roomy = stacked_v6_machine(overflowing, words={0x60: 1})

    roomy.run()

    assert_that(roomy.memory.read_word(0x82)).is_zero()
    assert_that(roomy.memory.read_word(0x60)).is_zero()
    assert_that(roomy.memory.read_word(0x62)).is_equal_to(7)


# pop_stack discards from the game stack by default -- here two
# pushes vanish so the bare Version 6 pull reads the first -- and
# from a named user stack via its second operand, where discarding
# just walks the spare count up (§15 pop_stack).
def test_pop_stack_discards_from_either_stack() -> None:
    machine = stacked_v6_machine(
        bytes(
            [
                *[0xE8, 0x7F, 0x05],
                *[0xE8, 0x7F, 0x06],
                *[0xE8, 0x7F, 0x07],
                *[0xBE, 0x15, 0x7F, 0x02],
                *[0xE9, 0xFF, 0x10],
                *[0xBE, 0x15, 0x5F, 0x02, 0x60],
                0xBA,
            ]
        ),
        words={0x60: 1},
    )

    machine.run()

    assert_that(machine.memory.read_word(0x80)).is_equal_to(5)
    assert_that(machine.memory.read_word(0x60)).is_equal_to(3)


# §6.6 is explicit that nothing checks under-flow: pulling from a
# fresh stack walks the count past its capacity and reads whatever
# lies beyond the table.
def test_user_stack_underflow_is_unchecked_by_design() -> None:
    machine = stacked_v6_machine(
        bytes([*[0xE9, 0x7F, 0x60, 0x10], 0xBA]),
        words={0x60: 3, 0x68: 0xBEEF},
    )

    machine.run()

    assert_that(machine.memory.read_word(0x60)).is_equal_to(4)
    assert_that(machine.memory.read_word(0x80)).is_equal_to(0xBEEF)


# picture_data's census form -- picture 0 -- writes the count of
# available pictures and the file release into its array: zero and
# zero for an interpreter with no picture system, with no branch,
# since no pictures are available (§15 picture_data). The marker
# store proves the branch was not taken.
def test_picture_data_census_answers_zero_pictures() -> None:
    machine = stacked_v6_machine(
        bytes(
            [
                *[0xBE, 0x06, 0x5F, 0x00, 0x60, 0xC5],
                *[0x0D, 0x11, 0x63],
                0xBA,
            ]
        ),
        words={0x60: 0xDEAD, 0x62: 0xBEEF},
    )

    machine.run()

    assert_that(machine.memory.read_word(0x60)).is_zero()
    assert_that(machine.memory.read_word(0x62)).is_zero()
    assert_that(machine.memory.read_word(0x82)).is_equal_to(0x63)


# Any other picture number is invalid where no pictures exist: the
# array is left alone and the branch fails (§15 picture_data),
# which is what the header's cleared pictures bit promised.
def test_picture_data_leaves_invalid_numbers_unanswered() -> None:
    machine = stacked_v6_machine(
        bytes(
            [
                *[0xBE, 0x06, 0x5F, 0x05, 0x60, 0xC5],
                *[0x0D, 0x11, 0x63],
                0xBA,
            ]
        ),
        words={0x60: 0xDEAD},
    )

    machine.run()

    assert_that(machine.memory.read_word(0x60)).is_equal_to(0xDEAD)
    assert_that(machine.memory.read_word(0x82)).is_equal_to(0x63)


class PicturedFrontend(PlainFrontend):
    """A frontend hanging two pictures, recording draws and erasures."""

    has_pictures = True

    def __init__(self) -> None:
        super().__init__(lambda _text: None)
        self.drawn: list[tuple[int, int, int]] = []
        self.erased: list[tuple[int, int, int]] = []

    def picture_data(self, number: int) -> tuple[int, int] | None:
        return {1: (84, 314), 4: (21, 21)}.get(number)

    def picture_census(self) -> tuple[int, int]:
        return 2, 27

    def draw_picture(self, number: int, line: int, column: int) -> None:
        self.drawn.append((number, line, column))

    def erase_picture(self, number: int, line: int, column: int) -> None:
        self.erased.append((number, line, column))


# With pictures on the frontend, picture_data answers for real: a
# valid number writes height then width and branches, the census
# reports the count and the art's release and branches, and an
# invalid number still writes nothing and falls through (§15
# picture_data). Each skipped marker proves its branch was taken,
# and the Flags 1 pictures bit is finally set (§11.1.4).
def test_picture_data_answers_real_dimensions() -> None:
    machine = stacked_v6_machine(
        bytes(
            [
                *[0xBE, 0x06, 0x5F, 0x01, 0x60, 0xC5],
                *[0x0D, 0x11, 0x63],
                *[0xBE, 0x06, 0x5F, 0x00, 0x64, 0xC5],
                *[0x0D, 0x12, 0x63],
                *[0xBE, 0x06, 0x5F, 0x09, 0x68, 0xC5],
                *[0x0D, 0x13, 0x63],
                0xBA,
            ]
        ),
        words={0x68: 0xDEAD},
        frontend=PicturedFrontend(),
    )

    machine.run()

    assert_that(machine.memory.read_word(0x60)).is_equal_to(84)
    assert_that(machine.memory.read_word(0x62)).is_equal_to(314)
    assert_that(machine.memory.read_word(0x82)).is_zero()
    assert_that(machine.memory.read_word(0x64)).is_equal_to(2)
    assert_that(machine.memory.read_word(0x66)).is_equal_to(27)
    assert_that(machine.memory.read_word(0x84)).is_zero()
    assert_that(machine.memory.read_word(0x68)).is_equal_to(0xDEAD)
    assert_that(machine.memory.read_word(0x86)).is_equal_to(0x63)
    assert_that(machine.memory.read_byte(0x01) & 0x02).is_equal_to(0x02)


# draw_picture and erase_picture arrive at the frontend already
# placed: explicit coordinates ride the current window's own
# origin to the screen (§8.8.3.5), and zero or omitted ones fall
# back to the ledger cursor (§15 draw_picture).
def test_pictures_draw_where_the_ledger_says() -> None:
    frontend = PicturedFrontend()
    machine = stacked_v6_machine(
        bytes(
            [
                *[0xBE, 0x10, 0x57, 0x00, 0x05, 0x08],
                *[0xBE, 0x05, 0x57, 0x01, 0x0A, 0x14],
                *[0xBE, 0x10, 0x57, 0x00, 0x01, 0x01],
                *[0xEF, 0x5F, 0x09, 0x0B],
                *[0xBE, 0x05, 0x7F, 0x04],
                *[0xBE, 0x07, 0x57, 0x04, 0x02, 0x03],
                0xBA,
            ]
        ),
        frontend=frontend,
    )

    machine.run()

    assert_that(frontend.drawn).is_equal_to([(1, 14, 27), (4, 9, 11)])
    assert_that(frontend.erased).is_equal_to([(4, 2, 3)])


class StagedFrontend(PlainFrontend):
    """A frontend claiming the §8.8 stage, recording what it hears."""

    has_stage = True

    def __init__(self) -> None:
        super().__init__(lambda _text: None)
        self.events: list[tuple[object, ...]] = []

    def set_window(self, window: int) -> None:
        self.events.append(("select", window))

    def set_cursor(self, line: int, column: int) -> None:
        self.events.append(("cursor", line, column))

    def place_window(
        self, window: int, line: int, column: int, height: int, width: int
    ) -> None:
        self.events.append(("place", window, line, column, height, width))

    def erase_window(self, window: int) -> None:
        self.events.append(("erase", window))

    def scroll_window(self, window: int, pixels: int) -> None:
        self.events.append(("scroll", window, pixels))

    def set_margins(self, window: int, left: int, right: int) -> None:
        self.events.append(("margins", window, left, right))

    def set_line_count(self, window: int, count: int) -> None:
        self.events.append(("line_count", window, count))

    def erase_line(self, pixels: int | None = None) -> None:
        self.events.append(("erase_line", pixels))

    def cursor_position(self) -> tuple[int, int]:
        return (77, 33)


# A staged frontend hears the ledger's geometry: moves and sizes
# arrive as placements, every selection arrives with the selected
# window's ledger cursor riding along (§8.8.3.5), and a cursor
# move for the selected window is forwarded -- one aimed at a
# named, unselected window stays in the ledger until selection.
def test_staged_frontends_hear_the_ledger_geometry() -> None:
    frontend = StagedFrontend()
    machine = stacked_v6_machine(
        bytes(
            [
                *[0xBE, 0x10, 0x57, 0x03, 0x15, 0x29],
                *[0xBE, 0x11, 0x57, 0x03, 0x12, 0x64],
                *[0xEF, 0x57, 0x05, 0x09, 0x03],
                *[0xEB, 0x7F, 0x03],
                *[0xEF, 0x5F, 0x07, 0x0B],
                *[0xEB, 0x7F, 0x02],
                0xBA,
            ]
        ),
        frontend=frontend,
    )

    machine.run()

    assert_that(frontend.events).is_equal_to(
        [
            ("place", 3, 21, 41, 0, 0),
            ("place", 3, 21, 41, 18, 100),
            ("select", 3),
            ("cursor", 5, 9),
            ("cursor", 7, 11),
            ("select", 2),
        ]
    )


# erase_line reaches the stage in both of §15's spellings: value 1
# erases to the end of the line, and any other value is a pixel
# width, arriving as the value minus one (§8.8.5.2).
def test_staged_erase_line_carries_the_pixel_reach() -> None:
    frontend = StagedFrontend()
    machine = stacked_v6_machine(
        bytes([0xEE, 0x7F, 0x01, 0xEE, 0x7F, 0x1E, 0xBA]),
        frontend=frontend,
    )

    machine.run()

    assert_that(frontend.events).is_equal_to([("erase_line", None), ("erase_line", 29)])


# A staged frontend erases any of the eight windows -- no window
# is skipped as unrendered -- and erasing -1 selects window 0 in
# the ledger (§8.8.5.3.1), which the closing -3 erase proves.
def test_staged_erasures_reach_every_window() -> None:
    frontend = StagedFrontend()
    machine = stacked_v6_machine(
        bytes(
            [
                *[0xEB, 0x7F, 0x05],
                *[0xED, 0x7F, 0x06],
                *[0xED, 0x3F, 0xFF, 0xFF],
                *[0xED, 0x3F, 0xFF, 0xFD],
                0xBA,
            ]
        ),
        frontend=frontend,
    )

    machine.run()

    erasures = [event for event in frontend.events if event[0] == "erase"]

    assert_that(erasures).is_equal_to([("erase", 6), ("erase", -1), ("erase", 0)])


# On a staged frontend, get_cursor answers with the stage's own
# cursor -- the printing truth text flow moves -- rather than the
# ledger's stale copy. PunyInform saves and restores the cursor
# around its status redraw, and a stale answer reprints a line.
def test_staged_get_cursor_reads_the_stage() -> None:
    machine = stacked_v6_machine(
        bytes([*[0xF0, 0x7F, 0x60], 0xBA]),
        frontend=StagedFrontend(),
    )

    machine.run()

    assert_that(machine.memory.read_word(0x60)).is_equal_to(77)
    assert_that(machine.memory.read_word(0x62)).is_equal_to(33)


# A staged frontend hears scroll_window with the window resolved
# and the pixel amount signed; a character glass keeps the old
# conforming quiet (§15 scroll_window).
def test_staged_frontends_hear_the_scroll() -> None:
    frontend = StagedFrontend()
    machine = stacked_v6_machine(
        bytes(
            [
                *[0xBE, 0x14, 0x5F, 0x00, 0x12],
                *[0xBE, 0x14, 0x0F, 0xFF, 0xFD, 0xFF, 0xEE],
                0xBA,
            ]
        ),
        frontend=frontend,
    )

    machine.run()

    scrolls = [event for event in frontend.events if event[0] == "scroll"]

    assert_that(scrolls).is_equal_to([("scroll", 0, 18), ("scroll", 0, -18)])


# A staged frontend hears put_wind_prop's line-count writes --
# resolved window, signed value -- because games set them freely
# to manipulate when [MORE] is printed (§8.8.3.2.6); other
# property writes stay ledger-only.
def test_staged_frontends_hear_the_line_count() -> None:
    frontend = StagedFrontend()
    machine = stacked_v6_machine(
        bytes(
            [
                *[0xBE, 0x19, 0x57, 0x00, 0x0F, 0x63],
                *[0xBE, 0x19, 0x13, 0xFF, 0xFD, 0x0F, 0xFC, 0x19],
                *[0xBE, 0x19, 0x57, 0x00, 0x09, 0x02],
                0xBA,
            ]
        ),
        frontend=frontend,
    )

    machine.run()

    counted = [event for event in frontend.events if event[0] == "line_count"]

    assert_that(counted).is_equal_to([("line_count", 0, 0x63), ("line_count", 0, -999)])


# A staged frontend hears set_margins with its window resolved --
# the omitted-window form meaning the current one -- while the
# ledger keeps the properties as before (§15 set_margins).
def test_staged_frontends_hear_the_margins() -> None:
    frontend = StagedFrontend()
    machine = stacked_v6_machine(
        bytes(
            [
                *[0xBE, 0x08, 0x5F, 0x1E, 0x2D],
                *[0xBE, 0x08, 0x57, 0x09, 0x12, 0x03],
                0xBA,
            ]
        ),
        frontend=frontend,
    )

    machine.run()

    margins = [event for event in frontend.events if event[0] == "margins"]

    assert_that(margins).is_equal_to([("margins", 0, 30, 45), ("margins", 3, 9, 18)])


# The Version 6 split tiles the ledger itself (§8.8.4.1): window 1
# takes the top at the given height in units, window 0 the rest of
# the screen, and get_wind_prop sees it whatever the glass.
def test_v6_split_tiles_the_ledger() -> None:
    machine = stacked_v6_machine(
        bytes(
            [
                *[0xEA, 0x7F, 0x28],
                *[0xBE, 0x13, 0x5F, 0x01, 0x00, 0x10],
                *[0xBE, 0x13, 0x5F, 0x01, 0x02, 0x11],
                *[0xBE, 0x13, 0x5F, 0x00, 0x00, 0x12],
                *[0xBE, 0x13, 0x5F, 0x00, 0x02, 0x13],
                0xBA,
            ]
        )
    )

    machine.run()

    assert_that(machine.memory.read_word(0x80)).is_equal_to(1)
    assert_that(machine.memory.read_word(0x82)).is_equal_to(40)
    assert_that(machine.memory.read_word(0x84)).is_equal_to(41)
    assert_that(machine.memory.read_word(0x86)).is_equal_to(215)


# Drawing a picture the gallery does not hold is the one thing §15
# calls illegal, and the machine says so loudly.
def test_drawing_an_unknown_picture_is_refused() -> None:
    machine = stacked_v6_machine(
        bytes([*[0xBE, 0x05, 0x7F, 0x09], 0xBA]),
        frontend=PicturedFrontend(),
    )

    with pytest.raises(ZMachineScreenError, match="not in the gallery"):
        machine.run()


# The rest of the picture family passes in the conforming quiet --
# the header declared no pictures, and Infocom's own games draw
# without checking -- while make_menu fails its branch: the menus
# request was cleared at boot (§11.1.2, §11.1.4).
def test_picture_operations_pass_quietly_and_menus_fail() -> None:
    machine = stacked_v6_machine(
        bytes(
            [
                *[0xBE, 0x05, 0x7F, 0x01],
                *[0xBE, 0x07, 0x7F, 0x01],
                *[0xBE, 0x1C, 0x7F, 0x60],
                *[0xBE, 0x1B, 0x5F, 0x03, 0x00, 0xC5],
                *[0x0D, 0x11, 0x63],
                0xBA,
            ]
        )
    )

    machine.run()

    assert_that(machine.memory.read_word(0x82)).is_equal_to(0x63)


# The window opcodes drive the §8.8 ledger end to end: a window is
# moved and sized, its properties read back with get_wind_prop --
# window -3 naming the current selection -- its line count written
# with put_wind_prop, and its margins set with the window operand
# omitted, meaning the selected window (§15).
def test_the_window_ledger_round_trips_through_the_opcodes() -> None:
    machine = stacked_v6_machine(
        bytes(
            [
                *[0xBE, 0x10, 0x57, 0x03, 0x05, 0x08],
                *[0xBE, 0x11, 0x57, 0x03, 0x02, 0x28],
                *[0xBE, 0x13, 0x5F, 0x03, 0x00, 0x10],
                *[0xBE, 0x13, 0x5F, 0x03, 0x03, 0x11],
                *[0xBE, 0x19, 0x57, 0x00, 0x0F, 0x63],
                *[0xBE, 0x13, 0x5F, 0x00, 0x0F, 0x12],
                *[0xBE, 0x08, 0x5F, 0x05, 0x07],
                *[0xBE, 0x13, 0x1F, 0xFF, 0xFD, 0x06, 0x13],
                0xBA,
            ]
        )
    )

    machine.run()

    assert_that(machine.memory.read_word(0x80)).is_equal_to(5)
    assert_that(machine.memory.read_word(0x82)).is_equal_to(0x28)
    assert_that(machine.memory.read_word(0x84)).is_equal_to(0x63)
    assert_that(machine.memory.read_word(0x86)).is_equal_to(5)


# On a stage the selected window's cursor properties answer from
# the frontend's flowed cursor -- printing moves it, and the
# ledger's copy cannot know (§8.8.3.5). Shogun centres its title
# lines by reading property 4 back between prints; the stale copy
# overprinted them all on one row. An unselected window still
# answers from the ledger.
def test_staged_cursor_properties_answer_the_flowed_cursor() -> None:
    machine = stacked_v6_machine(
        bytes(
            [
                *[0xBE, 0x13, 0x1F, 0xFF, 0xFD, 0x04, 0x10],
                *[0xBE, 0x13, 0x5F, 0x00, 0x05, 0x11],
                *[0xBE, 0x13, 0x5F, 0x02, 0x04, 0x12],
                0xBA,
            ]
        ),
        frontend=StagedFrontend(),
    )

    machine.run()

    assert_that(machine.memory.read_word(0x80)).is_equal_to(77)
    assert_that(machine.memory.read_word(0x82)).is_equal_to(33)
    assert_that(machine.memory.read_word(0x84)).is_equal_to(1)


# window_style reaches the ledger with its optional operation --
# here turning scrolling off window 0 -- and the changed flags
# read back (§15 window_style).
def test_window_style_flows_through_the_ledger() -> None:
    machine = stacked_v6_machine(
        bytes(
            [
                *[0xBE, 0x12, 0x57, 0x00, 0x02, 0x02],
                *[0xBE, 0x13, 0x5F, 0x00, 0x0E, 0x10],
                0xBA,
            ]
        )
    )

    machine.run()

    assert_that(machine.memory.read_word(0x80)).is_equal_to(0x0D)


# Writing a true colour property is refused loudly (§8.8.3.2).
def test_true_colour_writes_halt() -> None:
    machine = stacked_v6_machine(bytes([*[0xBE, 0x19, 0x57, 0x00, 0x10, 0x01], 0xBA]))

    with pytest.raises(ZMachineScreenError, match="must not be written"):
        machine.run()


# The mouse courtesies: mouse_window constrains an arrow that does
# not exist and passes quietly; read_mouse reports a mouse parked
# at nowhere -- zeros in all four words, over whatever was there --
# both the honest behaviour of the header's cleared mouse request
# (§11.1.2, §15 read_mouse). Arthur sets up its pointer on the way
# up without asking.
def test_the_mouse_courtesies_answer_honestly() -> None:
    machine = stacked_v6_machine(
        bytes(
            [
                *[0xBE, 0x17, 0x7F, 0x01],
                *[0xBE, 0x16, 0x7F, 0x60],
                0xBA,
            ]
        ),
        words={0x60: 0xDEAD, 0x62: 0xBEEF, 0x64: 0xDEAD, 0x66: 0xBEEF},
    )

    machine.run()

    for offset in (0x60, 0x62, 0x64, 0x66):
        assert_that(machine.memory.read_word(offset)).is_zero()


# Version 6's set_cursor forms: -1 turns the cursor off, -2 -- with
# or without §15's "mysterious" second operand -- turns it back on,
# both quietly; an ordinary move lands in the current window's
# ledger properties, where get_cursor reads it back exactly, and a
# third operand names another window (§15 set_cursor). Arthur
# switches its cursor off before its title chrome.
def test_v6_cursor_forms_land_in_the_ledger() -> None:
    machine = stacked_v6_machine(
        bytes(
            [
                *[0xEF, 0x3F, 0xFF, 0xFF],
                *[0xEF, 0x1F, 0xFF, 0xFE, 0x00],
                *[0xEF, 0x5F, 0x02, 0x09],
                *[0xF0, 0x7F, 0x60],
                *[0xEF, 0x57, 0x05, 0x07, 0x03],
                *[0xBE, 0x13, 0x5F, 0x03, 0x04, 0x10],
                *[0xBE, 0x13, 0x5F, 0x03, 0x05, 0x11],
                0xBA,
            ]
        )
    )

    machine.run()

    assert_that(machine.memory.read_word(0x60)).is_equal_to(2)
    assert_that(machine.memory.read_word(0x62)).is_equal_to(9)
    assert_that(machine.memory.read_word(0x80)).is_equal_to(5)
    assert_that(machine.memory.read_word(0x82)).is_equal_to(7)


# scroll_window shifts pixels a character glass does not have: it
# passes in the conforming quiet until a graphics frontend brings
# real pixels to shift (§15 scroll_window). Arthur scrolls its
# story window at the very first prompt.
def test_scroll_window_passes_quietly() -> None:
    machine = stacked_v6_machine(bytes([*[0xBE, 0x14, 0x5F, 0x00, 0x08], 0xBA]))

    machine.run()

    assert_that(machine.running).is_false()


# The Version 6 stream-3 width form: text redirected with a width
# of -8 word-wraps into print_form's line shape -- counted lines,
# a zero terminator -- and print_form reads it back out, one line
# per screen line (§15 output_stream, §15 print_form). The header
# word at $30 takes the widest line (§7.1.2.1). Arthur formats its
# parser errors exactly this way.
def test_formatted_redirection_round_trips_through_print_form() -> None:
    pieces: list[str] = []
    typed = [0x61, 0x62, 0x63, 0x20, 0x64, 0x65, 0x66, 0x20, 0x67, 0x68, 0x69, 0x6A]
    presses = [byte for code in typed for byte in (0xE5, 0x7F, code)]
    machine = stacked_v6_machine(
        bytes(
            [
                *[0xF3, 0x53, 0x03, 0x60, 0xFF, 0xF8],
                *presses,
                *[0xF3, 0x3F, 0xFF, 0xFD],
                *[0xBE, 0x1A, 0x7F, 0x60],
                0xBA,
            ]
        ),
        frontend=PlainFrontend(pieces.append),
    )

    machine.run()

    assert_that("".join(pieces)).is_equal_to("abc def\nghij\n")
    assert_that(machine.memory.read_word(0x60)).is_equal_to(7)
    assert_that(machine.memory.read_word(0x69)).is_equal_to(4)
    assert_that(machine.memory.read_word(0x6F)).is_zero()
    assert_that(machine.memory.read_word(0x30)).is_equal_to(7)


class MeasuringFrontend(PlainFrontend):
    """A frontend whose glass measures: a 9-by-18 pixel cell."""

    screen_lines = 24
    font_width = 9
    font_height = 18


# On a glass that measures, a Version 6 story hears its screen in
# real pixels: the unit words at $22 and $24 carry columns and
# lines times the font metrics, the font bytes at $26 and $27
# arrive in §11's swapped Version 6 order, and window 0 boots
# sized in pixels with its font size property packing the real
# cell (§8.4.2, §8.8.3.2.5).
def test_v6_hears_real_pixels_from_a_measuring_glass() -> None:
    machine = stacked_v6_machine(
        bytes(
            [
                *[0xBE, 0x13, 0x5F, 0x00, 0x03, 0x10],
                *[0xBE, 0x13, 0x5F, 0x00, 0x0D, 0x11],
                0xBA,
            ]
        ),
        frontend=MeasuringFrontend(),
    )

    machine.run()

    assert_that(machine.memory.read_word(0x22)).is_equal_to(720)
    assert_that(machine.memory.read_word(0x24)).is_equal_to(432)
    assert_that(machine.memory.read_byte(0x26)).is_equal_to(18)
    assert_that(machine.memory.read_byte(0x27)).is_equal_to(9)
    assert_that(machine.memory.read_word(0x80)).is_equal_to(720)
    assert_that(machine.memory.read_word(0x82)).is_equal_to((18 << 8) | 9)


# The same wrap on a measuring glass: a width of -72 units is 8
# characters at a 9-pixel font, so the lines break exactly as -8
# breaks on the character glass -- and the $30 word, "total width
# in pixels" in §11's table, carries the widest line times the
# font width.
def test_measured_widths_wrap_in_characters_and_report_pixels() -> None:
    pieces: list[str] = []
    typed = [0x61, 0x62, 0x63, 0x20, 0x64, 0x65, 0x66, 0x20, 0x67, 0x68, 0x69, 0x6A]
    presses = [byte for code in typed for byte in (0xE5, 0x7F, code)]
    machine = stacked_v6_machine(
        bytes(
            [
                *[0xF3, 0x53, 0x03, 0x60, 0xFF, 0xB8],
                *presses,
                *[0xF3, 0x3F, 0xFF, 0xFD],
                *[0xBE, 0x1A, 0x7F, 0x60],
                0xBA,
            ]
        ),
        frontend=MeasuringFrontend(pieces.append),
    )

    machine.run()

    assert_that("".join(pieces)).is_equal_to("abc def\nghij\n")
    assert_that(machine.memory.read_word(0x30)).is_equal_to(63)


# A zero-or-positive width names a window, whose ledger width is
# the wrap limit; and a blank line -- impossible to carry in a
# format whose terminator is the zero count -- travels as a single
# space (§15 output_stream).
def test_window_widths_and_blank_lines_are_handled() -> None:
    machine = stacked_v6_machine(
        bytes(
            [
                *[0xBE, 0x11, 0x57, 0x03, 0x02, 0x05],
                *[0xF3, 0x57, 0x03, 0x60, 0x03],
                *[0xE5, 0x7F, 0x78],
                0xBB,
                0xBB,
                *[0xE5, 0x7F, 0x79],
                *[0xF3, 0x3F, 0xFF, 0xFD],
                0xBA,
            ]
        )
    )

    machine.run()

    assert_that(machine.memory.read_word(0x60)).is_equal_to(1)
    assert_that(machine.memory.read_byte(0x62)).is_equal_to(0x78)
    assert_that(machine.memory.read_word(0x63)).is_equal_to(1)
    assert_that(machine.memory.read_byte(0x65)).is_equal_to(0x20)
    assert_that(machine.memory.read_word(0x66)).is_equal_to(1)
    assert_that(machine.memory.read_byte(0x68)).is_equal_to(0x79)
    assert_that(machine.memory.read_word(0x69)).is_zero()


# A widthless Version 6 redirection keeps the flat count-and-bytes
# shape, and still reports its width at $30 (§7.1.2.1).
def test_v6_flat_redirection_reports_its_width() -> None:
    machine = stacked_v6_machine(
        bytes(
            [
                *[0xF3, 0x5F, 0x03, 0x60],
                *[0xE5, 0x7F, 0x61],
                *[0xE5, 0x7F, 0x62],
                *[0xF3, 0x3F, 0xFF, 0xFD],
                0xBA,
            ]
        )
    )

    machine.run()

    assert_that(machine.memory.read_word(0x60)).is_equal_to(2)
    assert_that(machine.memory.read_word(0x30)).is_equal_to(2)


# A word longer than the whole limit breaks at the limit -- the
# unbuffered §8.8.3.1.1 fallback -- whether it opens a line or
# forces the line before it out first.
def test_overlong_words_break_at_the_limit() -> None:
    pieces: list[str] = []
    typed = [0x61, 0x62, 0x63, 0x64, 0x65, 0x66, 0x67, 0x20, 0x68, 0x69]
    presses = [byte for code in typed for byte in (0xE5, 0x7F, code)]
    machine = stacked_v6_machine(
        bytes(
            [
                *[0xF3, 0x53, 0x03, 0x60, 0xFF, 0xFD],
                *presses,
                *[0xF3, 0x3F, 0xFF, 0xFD],
                *[0xBE, 0x1A, 0x7F, 0x60],
                0xBA,
            ]
        ),
        frontend=PlainFrontend(pieces.append),
    )

    machine.run()

    assert_that("".join(pieces)).is_equal_to("abc\ndef\ng\nhi\n")
