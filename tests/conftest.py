"""Shared pytest fixtures for all Voxam tests."""

from collections.abc import Callable
from pathlib import Path

import pytest

from voxam.zmachine.story import Story

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixture_path() -> Callable[[int], Path]:
    """Provide a locator for the simple-test story of a given version."""

    def _find(version: int) -> Path:
        (path,) = FIXTURES.glob(f"simple-test-r*-s260727.z{version}")

        return path

    return _find


@pytest.fixture
def load_fixture(
    fixture_path: Callable[[int], Path],
) -> Callable[[int], Story]:
    """Provide a loader for the simple-test story of a given version."""

    def _load(version: int) -> Story:
        return Story.load(fixture_path(version))

    return _load
