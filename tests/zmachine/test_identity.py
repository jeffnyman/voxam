import io
from collections.abc import Callable
from pathlib import Path

import pytest
from assertpy import assert_that

from voxam.cli import _identity, main
from voxam.zmachine.machine import (
    INTERPRETER_PLATFORM,
    Identity,
    Machine,
)

FLAGS_1 = 0x01
TANDY_BIT = 0x08
INTERPRETER_NUMBER = 0x1E


# The legendary Tandy bit is written into a Version 3 header when
# the identity asks for it, and written off when it does not
# (§11.1.4).
def test_the_tandy_bit_is_written_both_ways(
    code_machine: Callable[..., Machine],
) -> None:
    proud = code_machine(bytes([0xBA]), identity=Identity(tandy=True))

    assert_that(proud.memory.read_byte(FLAGS_1) & TANDY_BIT).is_equal_to(TANDY_BIT)

    plain = code_machine(bytes([0xBA]))

    assert_that(plain.memory.read_byte(FLAGS_1) & TANDY_BIT).is_zero()


# From Version 4 the header carries an interpreter number instead
# (§11.1.3): the identity's platform lands at $1E, and Voxam's
# default appears when none is claimed.
def test_the_interpreter_number_is_introduced(
    code_machine: Callable[..., Machine],
) -> None:
    amiga = code_machine(bytes([0xBA]), version=5, identity=Identity(interpreter=4))

    assert_that(amiga.memory.read_byte(INTERPRETER_NUMBER)).is_equal_to(4)

    default = code_machine(bytes([0xBA]), version=5)

    assert_that(default.memory.read_byte(INTERPRETER_NUMBER)).is_equal_to(
        INTERPRETER_PLATFORM
    )


# The command line builds an identity from names or raw numbers,
# and nothing at all when nothing was asked.
def test_the_identity_flag_speaks_names_and_numbers() -> None:
    assert_that(_identity(None, tandy=False)).is_none()
    assert_that(_identity("amiga", tandy=False)).is_equal_to(
        Identity(interpreter=4, tandy=False)
    )
    assert_that(_identity("IBM-PC", tandy=False)).is_equal_to(
        Identity(interpreter=6, tandy=False)
    )
    assert_that(_identity("11", tandy=True)).is_equal_to(
        Identity(interpreter=11, tandy=True)
    )
    assert_that(_identity(None, tandy=True)).is_equal_to(
        Identity(interpreter=None, tandy=True)
    )


# A platform that is neither a known name nor a number is refused
# with the names on offer.
def test_unknown_interpreters_are_refused() -> None:
    with pytest.raises(ValueError, match="amiga"):
        _identity("zx-spectrum", tandy=False)


# The flags ride the command line end to end: a Version 3 story
# boots with the Tandy bit set, and a bad platform name reports
# without running anything.
def test_identity_flags_flow_through_the_cli(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    data = bytearray(96)
    data[0] = 3
    data[0x04:0x06] = (0x0060).to_bytes(2, "big")
    data[0x06:0x08] = (0x0040).to_bytes(2, "big")
    data[0x0E:0x10] = (0x0060).to_bytes(2, "big")
    data[0x40] = 0xBA
    path = tmp_path / "story.z3"
    path.write_bytes(bytes(data))

    exit_code = main(["--tandy", "--interpreter", "tandy-color", str(path)])

    assert_that(exit_code).is_equal_to(0)

    exit_code = main(["--interpreter", "zx-spectrum", str(path)])

    assert_that(exit_code).is_equal_to(2)
    assert_that(capsys.readouterr().out).contains("unknown interpreter")
