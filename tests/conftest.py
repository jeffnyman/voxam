"""Shared pytest fixtures for all Voxam tests."""

import struct
import zlib
from collections.abc import Callable
from pathlib import Path

import pytest

from voxam.png import SIGNATURE
from voxam.zmachine.story import Story

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def tiny_png() -> bytes:
    """A 2-by-2 truecolour PNG: one bright row over a black one.

    Decodes to ((10, 20, 30), (40, 50, 60)) atop two black pixels
    -- the smallest real picture a gallery test can hang.
    """

    def piece(name: bytes, payload: bytes) -> bytes:
        return (
            len(payload).to_bytes(4, "big")
            + name
            + payload
            + zlib.crc32(name + payload).to_bytes(4, "big")
        )

    header = struct.pack(">IIBBBBB", 2, 2, 8, 2, 0, 0, 0)
    raw = b"\x00" + bytes(range(10, 70, 10)) + b"\x00" + bytes(6)

    return (
        SIGNATURE
        + piece(b"IHDR", header)
        + piece(b"IDAT", zlib.compress(raw))
        + piece(b"IEND", b"")
    )


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
