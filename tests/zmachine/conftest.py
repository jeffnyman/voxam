"""Shared pytest fixtures for the Z-Machine tests."""

from collections.abc import Callable
from pathlib import Path

import pytest

from voxam.zmachine.memory import Memory
from voxam.zmachine.story import Story

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def load_fixture() -> Callable[[int], Story]:
    """Provide a loader for the simple-test story of a given version."""

    def _load(version: int) -> Story:
        (path,) = FIXTURES.glob(f"simple-test-r*-s260727.z{version}")

        return Story.load(path)

    return _load


@pytest.fixture
def code_memory() -> Callable[..., Memory]:
    """Provide a builder for a 512-byte memory image with planted code.

    The code bytes are planted at $40, the first address past the
    header; the static memory base is $1C0, leaving room for riders
    to be read after any planted instruction.
    """

    def _build(code: bytes = b"", version: int = 3) -> Memory:
        data = bytearray(512)
        data[0] = version
        data[0x04:0x06] = (0x01C0).to_bytes(2, "big")
        data[0x0E:0x10] = (0x01C0).to_bytes(2, "big")
        data[0x40 : 0x40 + len(code)] = code

        return Memory(Story(bytes(data)))

    return _build
