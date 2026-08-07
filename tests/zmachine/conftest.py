"""Shared pytest fixtures for the Z-Machine tests."""

from collections.abc import Callable
from pathlib import Path

import pytest

from voxam.zmachine.story import Story

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def load_fixture() -> Callable[[int], Story]:
    """Provide a loader for the simple-test story of a given version."""

    def _load(version: int) -> Story:
        (path,) = FIXTURES.glob(f"simple-test-r*-s260727.z{version}")

        return Story.load(path)

    return _load
