import runpy

import pytest
from assertpy import assert_that

from voxam.cli import main


def test_main_prints_banner(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main()

    assert_that(exit_code).is_equal_to(0)
    assert_that(capsys.readouterr().out).contains("Voxam")


def test_running_as_module_invokes_the_cli(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        runpy.run_module("voxam", run_name="__main__")

    assert_that(excinfo.value.code).is_equal_to(0)
    assert_that(capsys.readouterr().out).contains("Voxam")
