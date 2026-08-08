from collections.abc import Callable

import pytest
from assertpy import assert_that

from voxam.errors import ZMachineHeaderError
from voxam.zmachine.memory import Memory
from voxam.zmachine.packed import routine_address, string_address


# The packed-to-byte scale factor is 2 through Version 3, 4 through
# Version 5, and 8 in Version 8 (§1.2.3).
@pytest.mark.parametrize(
    ("version", "factor"), [(1, 2), (3, 2), (4, 4), (5, 4), (8, 8)]
)
def test_scales_packed_addresses_by_version(
    version: int, factor: int, code_memory: Callable[..., Memory]
) -> None:
    header = code_memory(version=version).header

    assert_that(routine_address(header, 0x0100)).is_equal_to(0x0100 * factor)
    assert_that(string_address(header, 0x0100)).is_equal_to(0x0100 * factor)


# The words at $28 and $2a hold the routine and string offsets,
# each stored divided by 8 (§1.2.3). With different offsets, the
# same packed address unpacks to different byte addresses.
def test_versions_6_and_7_add_distinct_offsets(
    code_memory: Callable[..., Memory],
) -> None:
    memory = code_memory(version=6)
    memory.write_word(0x28, 3)
    memory.write_word(0x2A, 5)
    header = memory.header

    assert_that(routine_address(header, 0x0100)).is_equal_to(4 * 0x0100 + 8 * 3)
    assert_that(string_address(header, 0x0100)).is_equal_to(4 * 0x0100 + 8 * 5)


def test_version_7_unpacks_with_offsets_too(
    code_memory: Callable[..., Memory],
) -> None:
    memory = code_memory(version=7)
    memory.write_word(0x28, 2)
    header = memory.header

    assert_that(routine_address(header, 0x0010)).is_equal_to(4 * 0x0010 + 8 * 2)


def test_other_versions_have_no_offsets(code_memory: Callable[..., Memory]) -> None:
    header = code_memory(version=3).header

    with pytest.raises(ZMachineHeaderError, match="no routines offset"):
        _ = header.routines_offset

    with pytest.raises(ZMachineHeaderError, match="no static strings offset"):
        _ = header.static_strings_offset
