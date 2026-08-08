import runpy
import sys
from collections.abc import Callable
from pathlib import Path

import pytest
from assertpy import assert_that

from voxam.cli import main


def broken_story(tmp_path: Path, code: bytes) -> Path:
    data = bytearray(96)
    data[0] = 3
    data[0x04:0x06] = (0x0060).to_bytes(2, "big")
    data[0x06:0x08] = (0x0040).to_bytes(2, "big")
    data[0x0E:0x10] = (0x0060).to_bytes(2, "big")
    data[0x40 : 0x40 + len(code)] = code
    path = tmp_path / "story.z3"
    path.write_bytes(bytes(data))

    return path


def test_main_prints_banner(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main([])

    assert_that(exit_code).is_equal_to(0)
    assert_that(capsys.readouterr().out).contains("Voxam")


def test_running_as_module_invokes_the_cli(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "argv", ["voxam"])

    with pytest.raises(SystemExit) as excinfo:
        runpy.run_module("voxam", run_name="__main__")

    assert_that(excinfo.value.code).is_equal_to(0)
    assert_that(capsys.readouterr().out).contains("Voxam")


def test_runs_a_story_to_completion(
    fixture_path: Callable[[int], Path], capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = main([str(fixture_path(3))])

    out = capsys.readouterr().out

    assert_that(exit_code).is_equal_to(0)
    assert_that(out).contains("release 1, serial 260727 (z3)")
    assert_that(out).contains("hello from all z machine versions")


def test_reports_a_missing_file(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["no-such-story.z3"])

    assert_that(exit_code).is_equal_to(2)
    assert_that(capsys.readouterr().out).contains("voxam:")


def test_reports_an_invalid_story(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "tiny.z3"
    path.write_bytes(bytes(10))

    exit_code = main([str(path)])

    assert_that(exit_code).is_equal_to(2)
    assert_that(capsys.readouterr().out).contains("header")


# nop decodes fine but has no handler yet, so the CLI surfaces the
# frontier report and exits 1.
def test_reports_the_implementation_frontier(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = main([str(broken_story(tmp_path, bytes([0xB4])))])

    assert_that(exit_code).is_equal_to(1)
    assert_that(capsys.readouterr().out).contains("not yet implemented")


# The byte 0x00 decodes as 2OP:0, which no version defines, so the
# machine raises mid-run and the CLI exits 2.
def test_reports_a_story_that_breaks_the_rules(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = main([str(broken_story(tmp_path, bytes([0x00, 0x01, 0x02])))])

    assert_that(exit_code).is_equal_to(2)
    assert_that(capsys.readouterr().out).contains("2OP:0")
