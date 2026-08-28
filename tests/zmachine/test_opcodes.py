import pytest
from assertpy import assert_that

from voxam.errors import ZMachineInstructionError
from voxam.zmachine.opcodes import Opcode, OpcodeKind, lookup

ALL_VERSIONS = range(1, 9)


def test_an_ordinary_opcode_spans_all_versions() -> None:
    for version in ALL_VERSIONS:
        opcode = lookup(OpcodeKind.TWO_OP, 0x16, version)

        assert_that(opcode).is_equal_to(Opcode("mul", stores=True))


# jump's "?(label)" syntax is misleading: its destination is an
# ordinary operand, so §14 gives it no branch flag.
def test_jump_does_not_carry_a_branch_rider() -> None:
    opcode = lookup(OpcodeKind.ONE_OP, 0xC, 3)

    assert_that(opcode.name).is_equal_to("jump")
    assert_that(opcode.branches).is_false()


def test_scan_table_both_stores_and_branches() -> None:
    opcode = lookup(OpcodeKind.VAR, 0x17, 5)

    assert_that(opcode.stores).is_true()
    assert_that(opcode.branches).is_true()


# Standard 1.1 reserves EXT 128-255 for private use (§14.2) and asks
# that unknown extended opcodes from EXT:30 up be simply ignored
# (§14.2.1): the private band answers the silent no-op, the band
# reserved for future Standards answers the warning one, and below
# 30 an unknown number stays the loud error §14.2 asks for -- while
# 0x80 itself is the arc_image draw in Versions 5, 7, and 8, with
# Version 6 keeping the number private.
def test_private_ext_opcodes_pass_unclaimed() -> None:
    for number in (0x81, 0xC3, 0xFF):
        opcode = lookup(OpcodeKind.EXT, number, 5)

        assert_that(opcode).is_equal_to(Opcode("ext_private"))

    for number in (0x1E, 0x40, 0x7F):
        opcode = lookup(OpcodeKind.EXT, number, 5)

        assert_that(opcode).is_equal_to(Opcode("ext_reserved"))

    for version in (5, 7, 8):
        assert_that(lookup(OpcodeKind.EXT, 0x80, version).name).is_equal_to(
            "draw_image"
        )

    assert_that(lookup(OpcodeKind.EXT, 0x80, 6)).is_equal_to(Opcode("ext_private"))

    with pytest.raises(ZMachineInstructionError, match="not an opcode"):
        lookup(OpcodeKind.EXT, 0x0E, 5)


def test_only_the_print_opcodes_carry_text() -> None:
    assert_that(lookup(OpcodeKind.ZERO_OP, 0x2, 3).has_text).is_true()
    assert_that(lookup(OpcodeKind.ZERO_OP, 0x3, 3).has_text).is_true()
    assert_that(lookup(OpcodeKind.ZERO_OP, 0x0, 3).has_text).is_false()


# 0OP:9 is pop, a stack operation, until Version 5 turns it into the
# storing catch (§14).
@pytest.mark.parametrize(
    ("version", "name", "stores"),
    [(1, "pop", False), (4, "pop", False), (5, "catch", True), (8, "catch", True)],
)
def test_0op_9_forks_at_version_5(version: int, name: str, stores: bool) -> None:
    opcode = lookup(OpcodeKind.ZERO_OP, 0x9, version)

    assert_that(opcode.name).is_equal_to(name)
    assert_that(opcode.stores).is_equal_to(stores)


# save branches in Versions 1 to 3, stores in Version 4, and leaves
# the 0OP table entirely from Version 5 (§14).
@pytest.mark.parametrize(
    ("version", "stores", "branches"),
    [(1, False, True), (3, False, True), (4, True, False)],
)
def test_0op_save_changes_rider_by_version(
    version: int, stores: bool, branches: bool
) -> None:
    opcode = lookup(OpcodeKind.ZERO_OP, 0x5, version)

    assert_that(opcode.name).is_equal_to("save")
    assert_that(opcode.stores).is_equal_to(stores)
    assert_that(opcode.branches).is_equal_to(branches)


def test_0op_save_is_gone_from_version_5() -> None:
    with pytest.raises(ZMachineInstructionError, match="0OP:5 is not"):
        lookup(OpcodeKind.ZERO_OP, 0x5, 5)


# 1OP:15 is the storing not until Version 5 replaces it with the
# non-storing call_1n (§14).
@pytest.mark.parametrize(
    ("version", "name", "stores"),
    [(1, "not", True), (4, "not", True), (5, "call_1n", False)],
)
def test_1op_15_forks_at_version_5(version: int, name: str, stores: bool) -> None:
    opcode = lookup(OpcodeKind.ONE_OP, 0xF, version)

    assert_that(opcode.name).is_equal_to(name)
    assert_that(opcode.stores).is_equal_to(stores)


# VAR:0 is renamed from call to call_vs at Version 4; both store (§14).
@pytest.mark.parametrize(
    ("version", "name"), [(1, "call"), (3, "call"), (4, "call_vs"), (8, "call_vs")]
)
def test_var_0_is_renamed_at_version_4(version: int, name: str) -> None:
    opcode = lookup(OpcodeKind.VAR, 0x0, version)

    assert_that(opcode.name).is_equal_to(name)
    assert_that(opcode.stores).is_true()


# sread becomes the storing aread at Version 5 (§14).
@pytest.mark.parametrize(
    ("version", "name", "stores"),
    [(1, "sread", False), (4, "sread", False), (5, "aread", True)],
)
def test_var_4_forks_at_version_5(version: int, name: str, stores: bool) -> None:
    opcode = lookup(OpcodeKind.VAR, 0x4, version)

    assert_that(opcode.name).is_equal_to(name)
    assert_that(opcode.stores).is_equal_to(stores)


# pull stores only in Version 6; Versions 7 and 8 revert to Version 5
# behaviour, making the version spans non-contiguous (§14).
@pytest.mark.parametrize(
    ("version", "stores"),
    [(1, False), (5, False), (6, True), (7, False), (8, False)],
)
def test_pull_stores_only_in_version_6(version: int, stores: bool) -> None:
    opcode = lookup(OpcodeKind.VAR, 0x9, version)

    assert_that(opcode.name).is_equal_to("pull")
    assert_that(opcode.stores).is_equal_to(stores)


def test_extended_opcodes_do_not_exist_before_their_version() -> None:
    assert_that(lookup(OpcodeKind.EXT, 0x5, 6).name).is_equal_to("draw_picture")

    with pytest.raises(ZMachineInstructionError, match="EXT:5 is not"):
        lookup(OpcodeKind.EXT, 0x5, 5)


def test_undefined_numbers_are_rejected_in_every_version() -> None:
    for version in ALL_VERSIONS:
        with pytest.raises(ZMachineInstructionError, match="2OP:0 is not"):
            lookup(OpcodeKind.TWO_OP, 0x0, version)


# The slot the extended marker byte would occupy is deliberately
# absent from the table (§4.3, §14).
def test_0op_14_is_never_an_opcode() -> None:
    for version in ALL_VERSIONS:
        with pytest.raises(ZMachineInstructionError, match="0OP:14 is not"):
            lookup(OpcodeKind.ZERO_OP, 0xE, version)
