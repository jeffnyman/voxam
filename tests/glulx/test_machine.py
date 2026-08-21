"""The Glulx machine: the loop beats (Glulx: Dictionary of Opcodes)."""

from collections.abc import Callable

import pytest
from assertpy import assert_that

from voxam.errors import (
    GlulxFrontierError,
    GlulxInstructionError,
    GlulxMemoryError,
)
from voxam.glulx.machine import Machine
from voxam.glulx.stack import DestType
from voxam.glulx.story import Story

BOOT_PC = 0x4B
PLANT = 0x180
RESULT = 0x140

# A do-nothing start function: C0, no locals, quit.
IDLE = bytes([0xC0, 0x00, 0x00, 0x81, 0x20])

# The word-mode store target every plant writes its answer to.
TO_RESULT = bytes([0x00, 0x00, 0x01, 0x40])


def boot(image: Callable[..., bytes], code: bytes = IDLE, **kwargs: int) -> Machine:
    return Machine(Story(image(code=code, **kwargs)))


def planted(machine: Machine, code: bytes) -> None:
    """Write one instruction into RAM and step the machine over it."""

    machine.memory.write_run(PLANT, code)
    machine.pc = PLANT

    machine.step()


def result(machine: Machine) -> int:
    return machine.memory.read_word(RESULT)


# Boot calls the header's start function with no arguments: the
# frame stands and the pc rests on the first instruction.
def test_boot_calls_the_start_function(image: Callable[..., bytes]) -> None:
    machine = boot(image)

    assert_that(machine.pc).is_equal_to(BOOT_PC)
    assert_that(machine.stack.frameptr).is_equal_to(0)
    assert_that(machine.running).is_true()


# The smallest whole story: add two constants into memory and
# quit. Two instructions, one answer, a stopped machine.
def test_a_story_runs_to_quit(image: Callable[..., bytes]) -> None:
    program = (
        bytes([0xC0, 0x00, 0x00])
        + bytes([0x10, 0x11, 0x07, 0x03, 0x04])
        + TO_RESULT
        + bytes([0x81, 0x20])
    )
    machine = boot(image, program)

    assert_that(machine.run()).is_equal_to(2)
    assert_that(result(machine)).is_equal_to(7)
    assert_that(machine.running).is_false()


# callfi carries one argument into a C1 function, whose return
# value comes home through the call stub to the caller's target.
def test_calls_return_through_their_stubs(image: Callable[..., bytes]) -> None:
    main = (
        bytes([0xC0, 0x00, 0x00])
        + bytes([0x81, 0x61, 0x13, 0x07, 0x00, 0x00, 0x00, 0x60, 0x05])
        + TO_RESULT
        + bytes([0x81, 0x20])
    )
    func = (
        bytes([0xC1, 0x04, 0x01, 0x00, 0x00])
        + bytes([0x10, 0x19, 0x08, 0x00, 0x01])
        + bytes([0x31, 0x08])
    )
    machine = boot(image, main + bytes(24 - len(main)) + func)

    machine.run()

    assert_that(result(machine)).is_equal_to(6)

    # The general call takes its arguments off the stack; the
    # two- and three-argument conveniences carry theirs inline.
    # The one-local function drops the extras silently.
    varied = boot(image, main + bytes(24 - len(main)) + func)
    word_func = bytes([0x00, 0x00, 0x00, 0x60])

    def called_home(machine: Machine, plant: bytes) -> None:
        # The call is one step; the two-instruction callee is two
        # more before its return brings the result home.
        planted(machine, plant)
        machine.step()
        machine.step()

    varied.stack.push(5)
    called_home(
        varied,
        bytes([0x30, 0x13, 0x07]) + word_func + bytes([0x01]) + TO_RESULT,
    )

    assert_that(varied.memory.read_word(RESULT)).is_equal_to(6)

    varied.memory.write_word(RESULT, 0)
    called_home(
        varied,
        bytes([0x81, 0x62, 0x13, 0x71]) + word_func + bytes([0x05, 0x09]) + TO_RESULT,
    )

    assert_that(varied.memory.read_word(RESULT)).is_equal_to(6)

    varied.memory.write_word(RESULT, 0)
    called_home(
        varied,
        bytes([0x81, 0x63, 0x13, 0x11, 0x07])
        + word_func
        + bytes([0x05, 0x09, 0x02])
        + TO_RESULT,
    )

    assert_that(varied.memory.read_word(RESULT)).is_equal_to(6)


# tailcall replaces the frame without touching the stub below it:
# the tail-called function's return lands in the ORIGINAL caller's
# target, one stub for two calls.
def test_tailcall_replaces_the_frame(image: Callable[..., bytes]) -> None:
    main = (
        bytes([0xC0, 0x00, 0x00])
        + bytes([0x81, 0x60, 0x73, 0x00, 0x00, 0x00, 0x60])
        + TO_RESULT
        + bytes([0x81, 0x20])
    )
    first = (
        bytes([0xC0, 0x00, 0x00])
        + bytes([0x40, 0x81, 0x09])
        + bytes([0x34, 0x13, 0x00, 0x00, 0x00, 0x70, 0x01])
    )
    second = (
        bytes([0xC1, 0x04, 0x01, 0x00, 0x00])
        + bytes([0x10, 0x19, 0x08, 0x00, 0x01])
        + bytes([0x31, 0x08])
    )
    code = main + bytes(24 - len(main)) + first + bytes(40 - 24 - len(first)) + second
    machine = boot(image, code)

    machine.run()

    assert_that(result(machine)).is_equal_to(10)


# jump skips the debugtrap it is aimed over; a branch offset of 1
# is not a jump but a return, which at the top level ends the
# story (Glulx: Branches). jumpabs takes its address whole.
def test_branches_jump_and_return(image: Callable[..., bytes]) -> None:
    jumper = (
        bytes([0xC0, 0x00, 0x00])
        + bytes([0x20, 0x01, 0x06])
        + bytes([0x81, 0x01, 0x01, 0x07])
        + bytes([0x81, 0x20])
    )
    machine = boot(image, jumper)

    assert_that(machine.run()).is_equal_to(2)

    returner = boot(image, bytes([0xC0, 0x00, 0x00, 0x22, 0x11, 0x00, 0x01]))

    assert_that(returner.run()).is_equal_to(1)

    absolute = boot(
        image,
        bytes([0xC0, 0x00, 0x00])
        + bytes([0x81, 0x04, 0x03, 0x00, 0x00, 0x00, 0x52])
        + bytes([0x81, 0x20]),
    )

    assert_that(absolute.run()).is_equal_to(2)

    # The same opcode in its four-byte dress, and a branch offset
    # of 0: the other return code.
    long_form = boot(
        image,
        bytes([0xC0, 0x00, 0x00])
        + bytes([0xC0, 0x00, 0x01, 0x04, 0x03, 0x00, 0x00, 0x00, 0x55])
        + bytes([0x81, 0x20]),
    )

    assert_that(long_form.run()).is_equal_to(2)

    zero_return = boot(image, bytes([0xC0, 0x00, 0x00, 0x22, 0x11, 0x00, 0x00]))

    assert_that(zero_return.run()).is_equal_to(1)


# Every conditional branch fires on its own comparison -- signed
# where the spec says signed, unsigned where it says unsigned.
def test_conditional_branches_compare_their_way(
    image: Callable[..., bytes],
) -> None:
    machine = boot(image)

    # Each plant branches with offset 1 -- return -- so a taken
    # branch empties the stack and stops the machine; reboot after.
    taken = [
        bytes([0x22, 0x11, 0x00, 0x01]),
        bytes([0x23, 0x11, 0x05, 0x01]),
        bytes([0x24, 0x11, 0x01, 0x07, 0x07, 0x01]),
        bytes([0x25, 0x11, 0x01, 0x07, 0x08, 0x01]),
        bytes([0x26, 0x11, 0x01, 0xFF, 0x02, 0x01]),
        bytes([0x27, 0x11, 0x01, 0x02, 0xFF, 0x01]),
        bytes([0x28, 0x11, 0x01, 0x02, 0xFF, 0x01]),
        bytes([0x29, 0x11, 0x01, 0xFF, 0x02, 0x01]),
        bytes([0x2A, 0x11, 0x01, 0x02, 0xFF, 0x01]),
        bytes([0x2B, 0x11, 0x01, 0xFF, 0x02, 0x01]),
        bytes([0x2C, 0x11, 0x01, 0xFF, 0x02, 0x01]),
        bytes([0x2D, 0x11, 0x01, 0x02, 0xFF, 0x01]),
    ]

    for plant in taken:
        machine = boot(image)

        planted(machine, plant)

        assert_that(machine.running).is_false()

    # And every untaken side: the condition fails, the branch
    # stays home, and the machine keeps running.
    untaken = [
        bytes([0x22, 0x11, 0x05, 0x01]),
        bytes([0x23, 0x11, 0x00, 0x01]),
        bytes([0x24, 0x11, 0x01, 0x07, 0x08, 0x01]),
        bytes([0x25, 0x11, 0x01, 0x07, 0x07, 0x01]),
        bytes([0x26, 0x11, 0x01, 0x02, 0xFF, 0x01]),
        bytes([0x27, 0x11, 0x01, 0xFF, 0x02, 0x01]),
        bytes([0x28, 0x11, 0x01, 0xFF, 0x02, 0x01]),
        bytes([0x29, 0x11, 0x01, 0x02, 0xFF, 0x01]),
        bytes([0x2A, 0x11, 0x01, 0xFF, 0x02, 0x01]),
        bytes([0x2B, 0x11, 0x01, 0x02, 0xFF, 0x01]),
        bytes([0x2C, 0x11, 0x01, 0x02, 0xFF, 0x01]),
        bytes([0x2D, 0x11, 0x01, 0xFF, 0x02, 0x01]),
    ]

    for plant in untaken:
        quiet = boot(image)

        planted(quiet, plant)

        assert_that(quiet.running).is_true()


# Division truncates toward zero and remainders follow the
# dividend -- Python's floor division would say otherwise -- and
# the two impossible cases halt loudly (Glulx: Integer Math).
def test_division_truncates_toward_zero(image: Callable[..., bytes]) -> None:
    machine = boot(image)

    planted(machine, bytes([0x13, 0x11, 0x07, 0xF9, 0x02]) + TO_RESULT)

    assert_that(result(machine)).is_equal_to(0xFFFFFFFD)

    planted(machine, bytes([0x14, 0x11, 0x07, 0xF9, 0x02]) + TO_RESULT)

    assert_that(result(machine)).is_equal_to(0xFFFFFFFF)

    with pytest.raises(GlulxInstructionError, match="division by zero"):
        planted(machine, bytes([0x13, 0x11, 0x07, 0x07, 0x00]) + TO_RESULT)

    with pytest.raises(GlulxInstructionError, match="zero taking a remainder"):
        planted(machine, bytes([0x14, 0x11, 0x07, 0x07, 0x00]) + TO_RESULT)

    minimum = bytes([0x80, 0x00, 0x00, 0x00, 0xFF])

    with pytest.raises(GlulxInstructionError, match="division overflow"):
        planted(machine, bytes([0x13, 0x13, 0x07]) + minimum + TO_RESULT)

    with pytest.raises(GlulxInstructionError, match="overflow taking"):
        planted(machine, bytes([0x14, 0x13, 0x07]) + minimum + TO_RESULT)


# The rest of the integer family: negation and bitwork land masked,
# and every shift of 32 or more places leaves what the spec says --
# zeros, except the signed right shift of a negative value, which
# fills with its sign (Glulx: Integer Math).
def test_integers_negate_bitwork_and_shift(image: Callable[..., bytes]) -> None:
    machine = boot(image)
    cases = [
        (bytes([0x11, 0x11, 0x07, 0x09, 0x03]) + TO_RESULT, 6),
        (bytes([0x12, 0x11, 0x07, 0x06, 0x07]) + TO_RESULT, 42),
        (bytes([0x15, 0x71, 0x05]) + TO_RESULT, 0xFFFFFFFB),
        (bytes([0x18, 0x11, 0x07, 0x0F, 0x09]) + TO_RESULT, 9),
        (bytes([0x19, 0x11, 0x07, 0x0C, 0x03]) + TO_RESULT, 0x0F),
        (bytes([0x1A, 0x11, 0x07, 0x0F, 0x09]) + TO_RESULT, 6),
        (bytes([0x1B, 0x71, 0x00]) + TO_RESULT, 0xFFFFFFFF),
        (bytes([0x1C, 0x11, 0x07, 0x01, 0x04]) + TO_RESULT, 0x10),
        (bytes([0x1C, 0x11, 0x07, 0x01, 0x20]) + TO_RESULT, 0),
        (bytes([0x1E, 0x11, 0x07, 0x80, 0x04]) + TO_RESULT, 0x0FFFFFF8),
        (bytes([0x1E, 0x11, 0x07, 0x80, 0x21]) + TO_RESULT, 0),
        (bytes([0x1D, 0x11, 0x07, 0x80, 0x04]) + TO_RESULT, 0xFFFFFFF8),
        (bytes([0x1D, 0x11, 0x07, 0x80, 0x21]) + TO_RESULT, 0xFFFFFFFF),
        (bytes([0x1D, 0x11, 0x07, 0x01, 0x21]) + TO_RESULT, 0),
    ]

    for plant, expected in cases:
        planted(machine, plant)

        assert_that(result(machine)).is_equal_to(expected)


# copy moves words, copys and copyb move their narrowed widths
# through their narrowed indirections, and the sign-extenders
# widen what they are given (Glulx: Moving Data).
def test_data_moves_at_its_widths(image: Callable[..., bytes]) -> None:
    machine = boot(image)

    planted(machine, bytes([0x40, 0x71, 0x2A]) + TO_RESULT)

    assert_that(result(machine)).is_equal_to(0x2A)

    planted(machine, bytes([0x41, 0x63, 0x00, 0x01, 0x23, 0x45, 0x01, 0x40]))

    assert_that(machine.memory.read_short(RESULT)).is_equal_to(0x2345)

    planted(machine, bytes([0x42, 0x61, 0xAB, 0x01, 0x44]))

    assert_that(machine.memory.read_byte(0x144)).is_equal_to(0xAB)

    planted(machine, bytes([0x44, 0x72, 0x80, 0x00]) + TO_RESULT)

    assert_that(result(machine)).is_equal_to(0xFFFF8000)

    planted(machine, bytes([0x45, 0x71, 0x80]) + TO_RESULT)

    assert_that(result(machine)).is_equal_to(0xFFFFFF80)


# The array family: words, shorts, and bytes by index -- indexes
# wrapping at 32 bits, so -1 reaches backward -- and single bits
# numbered in both directions from the base's least significant
# bit (Glulx: Array Data).
def test_arrays_index_and_bits_count_both_ways(
    image: Callable[..., bytes],
) -> None:
    machine = boot(image)
    base = bytes([0x00, 0x00, 0x01, 0x40])

    planted(
        machine,
        bytes([0x4C, 0x13, 0x03]) + base + bytes([0x01, 0x11, 0x22, 0x33, 0x44]),
    )

    assert_that(machine.memory.read_word(0x144)).is_equal_to(0x11223344)

    planted(machine, bytes([0x48, 0x13, 0x07]) + base + bytes([0x01]) + TO_RESULT)

    assert_that(result(machine)).is_equal_to(0x11223344)

    planted(
        machine,
        bytes([0x4D, 0x13, 0x02]) + base + bytes([0x04, 0xBE, 0xEF]),
    )
    planted(machine, bytes([0x49, 0x13, 0x07]) + base + bytes([0x04]) + TO_RESULT)

    assert_that(result(machine)).is_equal_to(0xBEEF)

    planted(
        machine,
        bytes([0x4E, 0x13, 0x01, 0x00, 0x00, 0x01, 0x49, 0xFF, 0x77]),
    )
    planted(
        machine,
        bytes([0x4A, 0x13, 0x07, 0x00, 0x00, 0x01, 0x49, 0xFF]) + TO_RESULT,
    )

    assert_that(result(machine)).is_equal_to(0x77)
    assert_that(machine.memory.read_byte(0x148)).is_equal_to(0x77)

    machine.memory.write_byte(0x150, 0)
    planted(
        machine,
        bytes([0x4F, 0x13, 0x01, 0x00, 0x00, 0x01, 0x51, 0xFD, 0x01]),
    )

    assert_that(machine.memory.read_byte(0x150)).is_equal_to(0b0010_0000)

    planted(
        machine,
        bytes([0x4B, 0x13, 0x07, 0x00, 0x00, 0x01, 0x51, 0xFD]) + TO_RESULT,
    )

    assert_that(result(machine)).is_equal_to(1)

    planted(
        machine,
        bytes([0x4F, 0x13, 0x01, 0x00, 0x00, 0x01, 0x51, 0xFD, 0x00]),
    )

    assert_that(machine.memory.read_byte(0x150)).is_equal_to(0)


# The stack family: count, peek by index, swap, copy, and roll in
# both directions -- with every abuse the spec forbids halting
# loudly (Glulx: The Stack).
def test_the_stack_family_counts_swaps_copies_rolls(
    image: Callable[..., bytes],
) -> None:
    machine = boot(image)

    # A C0 boot already pushed its zero argument count, so the
    # stack starts one deep.
    for value in (1, 2, 3):
        machine.stack.push(value)

    planted(machine, bytes([0x50, 0x07]) + TO_RESULT)

    assert_that(result(machine)).is_equal_to(4)

    planted(machine, bytes([0x51, 0x71, 0x01]) + TO_RESULT)

    assert_that(result(machine)).is_equal_to(2)

    planted(machine, bytes([0x52]))

    assert_that(machine.stack.peek(0)).is_equal_to(2)
    assert_that(machine.stack.peek(1)).is_equal_to(3)

    planted(machine, bytes([0x54, 0x01, 0x02]))

    assert_that(machine.stack.count).is_equal_to(6)
    assert_that(machine.stack.peek(0)).is_equal_to(2)
    assert_that(machine.stack.peek(1)).is_equal_to(3)

    planted(machine, bytes([0x53, 0x11, 0x03, 0x01]))

    assert_that(machine.stack.peek(0)).is_equal_to(3)
    assert_that(machine.stack.peek(1)).is_equal_to(2)
    assert_that(machine.stack.peek(2)).is_equal_to(2)

    planted(machine, bytes([0x53, 0x11, 0x03, 0xFF]))

    assert_that(machine.stack.peek(0)).is_equal_to(2)

    planted(machine, bytes([0x53, 0x11, 0x00, 0x01]))
    planted(machine, bytes([0x53, 0x11, 0x02, 0x02]))
    planted(machine, bytes([0x54, 0x01, 0x00]))

    for wrong, complaint in (
        (bytes([0x51, 0x71, 0x63]) + TO_RESULT, "stkpeek"),
        (bytes([0x54, 0x01, 0xFF]), "negative count"),
        (bytes([0x54, 0x01, 0x63]), "exceeds the values"),
        (bytes([0x53, 0x11, 0xFF, 0x01]), "negative count"),
        (bytes([0x53, 0x11, 0x63, 0x01]), "exceeds the values"),
    ):
        with pytest.raises(GlulxInstructionError, match=complaint):
            planted(machine, wrong)

    empty = boot(image)

    with pytest.raises(GlulxInstructionError, match="fewer than two"):
        planted(empty, bytes([0x52]))


# catch stores its token and branches to the protected code; throw
# unwinds to that token and delivers its value to the catch's own
# target, execution resuming just past the catch.
def test_catch_and_throw_round_trip(image: Callable[..., bytes]) -> None:
    program = (
        bytes([0xC0, 0x00, 0x00])
        + bytes([0x32, 0x17, 0x00, 0x00, 0x01, 0x44, 0x0B])
        + bytes([0x40, 0x71, 0x63, 0x00, 0x00, 0x01, 0x48])
        + bytes([0x81, 0x20])
        + bytes([0x33, 0x61, 0x37, 0x01, 0x44])
    )
    machine = boot(image, program)

    assert_that(machine.run()).is_equal_to(4)
    assert_that(machine.memory.read_word(0x144)).is_equal_to(55)
    assert_that(machine.memory.read_word(0x148)).is_equal_to(99)

    broken = boot(image)

    with pytest.raises(GlulxInstructionError, match="catch token"):
        planted(broken, bytes([0x33, 0x11, 0x01, 0x03]))


# The lifecycle and map family: verify judges the checksum both
# ways, getmemsize and setmemsize speak to the map, protect guards
# a range across the restart opcode, and debugtrap halts loudly as
# the spec directs an interpreter with no debugger to.
def test_lifecycle_and_map_opcodes(image: Callable[..., bytes]) -> None:
    machine = boot(image)

    planted(machine, bytes([0x81, 0x21, 0x07]) + TO_RESULT)

    assert_that(result(machine)).is_equal_to(0)

    doctored = boot(image, checksum=7)

    planted(doctored, bytes([0x81, 0x21, 0x07]) + TO_RESULT)

    assert_that(doctored.memory.read_word(RESULT)).is_equal_to(1)

    planted(machine, bytes([0x81, 0x02, 0x07]) + TO_RESULT)

    assert_that(result(machine)).is_equal_to(0x300)

    planted(
        machine,
        bytes([0x81, 0x03, 0x73, 0x00, 0x00, 0x04, 0x00, 0x00, 0x00, 0x01, 0x44]),
    )

    assert_that(machine.memory.endmem).is_equal_to(0x400)
    assert_that(machine.memory.read_word(0x144)).is_equal_to(0)

    machine.memory.write_word(0x160, 0xFEEDF00D)
    planted(machine, bytes([0x81, 0x70, 0x21, 0x04, 0x01, 0x60]))

    assert_that(machine.memory.read_run(0x160, 4)).is_equal_to(bytes(4))

    machine.memory.write_word(0x160, 0xFEEDF00D)
    planted(
        machine,
        bytes([0x81, 0x71, 0x21, 0x02, 0x04, 0x01, 0x60, 0x01, 0x64]),
    )

    assert_that(machine.memory.read_word(0x164)).is_equal_to(0xFEEDF00D)

    machine.memory.write_word(0x140, 7)
    planted(machine, bytes([0x81, 0x27, 0x13, 0x00, 0x00, 0x01, 0x40, 0x04]))
    planted(machine, bytes([0x81, 0x22]))

    assert_that(machine.pc).is_equal_to(BOOT_PC)
    assert_that(machine.memory.read_word(0x140)).is_equal_to(7)
    assert_that(machine.memory.endmem).is_equal_to(0x300)

    trapped = boot(image)

    with pytest.raises(GlulxInstructionError, match="debugtrap with value 7"):
        planted(trapped, bytes([0x81, 0x01, 0x01, 0x07]))


# The frontiers are honest: a defined opcode whose era is not yet
# carried says so by name; an undefined number says the spec does
# not know it; a pc off the map says where it ran; and a runaway
# loop trips the run limit.
def test_frontiers_and_faults_are_loud(image: Callable[..., bytes]) -> None:
    machine = boot(image)

    with pytest.raises(GlulxFrontierError, match="accelfunc awaits its era"):
        planted(machine, bytes([0x81, 0x80]))

    with pytest.raises(GlulxInstructionError, match="does not define"):
        planted(machine, bytes([0x7F]))

    machine.pc = machine.memory.endmem

    with pytest.raises(GlulxMemoryError, match="ran off the memory map"):
        machine.step()

    looper = boot(
        image,
        bytes([0xC0, 0x00, 0x00]) + bytes([0x81, 0x04, 0x03, 0x00, 0x00, 0x00, 0x4B]),
    )

    with pytest.raises(GlulxInstructionError, match="exceeded 5"):
        looper.run(limit=5)


# A string-terminator stub where a function result belongs is an
# error in any era (Glulx: Call Stubs); the resume stubs proper
# are the strings module's business, tested with it.
def test_a_misplaced_terminator_stub_is_loud(image: Callable[..., bytes]) -> None:
    machine = boot(image)

    machine.stack.push_stub(DestType.RESUME_FUNCTION, 0, 0)

    with pytest.raises(GlulxInstructionError, match="string-terminator"):
        machine._pop_stub(1)
