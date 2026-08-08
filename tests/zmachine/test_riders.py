from collections.abc import Callable

import pytest
from assertpy import assert_that

from voxam.errors import ZMachineInstructionError, ZMachineMemoryError
from voxam.zmachine.memory import Memory
from voxam.zmachine.riders import Branch, read_branch, read_store_variable, text_end

CODE = 0x40
SIZE = 512


def test_reads_a_store_variable(code_memory: Callable[..., Memory]) -> None:
    memory = code_memory(bytes([0x42]))

    variable, after = read_store_variable(memory, CODE)

    assert_that(variable).is_equal_to(0x42)
    assert_that(after).is_equal_to(CODE + 1)


# Bit 7 gives the branch sense and bit 6 marks a one-byte branch with
# an unsigned offset in the bottom 6 bits (§4.7). 63 is the largest
# offset the short encoding can hold.
@pytest.mark.parametrize(
    ("branch_byte", "on_true", "offset"),
    [
        (0xC5, True, 5),
        (0x45, False, 5),
        (0x7F, False, 63),
        (0xFF, True, 63),
    ],
)
def test_reads_short_branches(
    branch_byte: int,
    on_true: bool,
    offset: int,
    code_memory: Callable[..., Memory],
) -> None:
    memory = code_memory(bytes([branch_byte]))

    branch, after = read_branch(memory, CODE)

    assert_that(branch).is_equal_to(Branch(on_true, offset))
    assert_that(after).is_equal_to(CODE + 1)


# With bit 6 clear the offset is a signed 14-bit number in the bottom
# 6 bits of the first byte plus all of the second (§4.7). The extremes
# of that range are 8191 and -8192.
@pytest.mark.parametrize(
    ("first", "second", "on_true", "offset"),
    [
        (0x80, 0x50, True, 80),
        (0x9F, 0xFF, True, 8191),
        (0xBF, 0xFF, True, -1),
        (0xA0, 0x00, True, -8192),
        (0x25, 0x00, False, -6912),
    ],
)
def test_reads_long_branches(
    first: int,
    second: int,
    on_true: bool,
    offset: int,
    code_memory: Callable[..., Memory],
) -> None:
    memory = code_memory(bytes([first, second]))

    branch, after = read_branch(memory, CODE)

    assert_that(branch).is_equal_to(Branch(on_true, offset))
    assert_that(after).is_equal_to(CODE + 2)


def test_offsets_0_and_1_mean_returns(code_memory: Callable[..., Memory]) -> None:
    # 0xC0 and 0xC1: short branches with offsets 0 and 1, which mean
    # "return false" and "return true" rather than a jump (§4.7.1).
    false_branch, _ = read_branch(code_memory(bytes([0xC0])), CODE)
    true_branch, _ = read_branch(code_memory(bytes([0xC1])), CODE)

    assert_that(false_branch.returns_false).is_true()
    assert_that(false_branch.returns_true).is_false()
    assert_that(true_branch.returns_true).is_true()
    assert_that(true_branch.returns_false).is_false()


def test_ordinary_offsets_are_not_returns(code_memory: Callable[..., Memory]) -> None:
    branch, _ = read_branch(code_memory(bytes([0xC5])), CODE)

    assert_that(branch.returns_false).is_false()
    assert_that(branch.returns_true).is_false()


def test_computes_a_branch_target() -> None:
    # Destination is the address after the branch data, plus the
    # offset, minus two (§4.7.2).
    assert_that(Branch(True, 5).target(100)).is_equal_to(103)
    assert_that(Branch(True, -1).target(100)).is_equal_to(97)


@pytest.mark.parametrize("offset", [0, 1])
def test_return_offsets_have_no_target(offset: int) -> None:
    with pytest.raises(ZMachineInstructionError, match="return, not a"):
        Branch(True, offset).target(100)


def test_finds_the_end_of_encoded_text(code_memory: Callable[..., Memory]) -> None:
    # Three words; only the last has its top bit set (§3.2).
    memory = code_memory(bytes([0x12, 0x34, 0x56, 0x78, 0x94, 0xA5]))

    assert_that(text_end(memory, CODE)).is_equal_to(CODE + 6)


def test_a_single_terminated_word_is_a_whole_string(
    code_memory: Callable[..., Memory],
) -> None:
    memory = code_memory(bytes([0x80, 0x00]))

    assert_that(text_end(memory, CODE)).is_equal_to(CODE + 2)


def test_unterminated_text_cannot_scan_past_readable_memory(
    code_memory: Callable[..., Memory],
) -> None:
    # Every word in the image has a clear top bit, so the scan runs
    # until the memory guards stop it.
    memory = code_memory(b"")

    with pytest.raises(ZMachineMemoryError, match="game-readable memory"):
        text_end(memory, CODE)


def test_branch_bytes_cannot_run_past_readable_memory(
    code_memory: Callable[..., Memory],
) -> None:
    # The byte at the last readable address has bit 6 clear, making a
    # two-byte branch whose second byte is off the end of the file.
    memory = code_memory(b"")

    with pytest.raises(ZMachineMemoryError, match="game-readable memory"):
        read_branch(memory, SIZE - 1)
