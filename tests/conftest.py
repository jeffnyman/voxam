"""Shared pytest fixtures for all Voxam tests."""

import struct
import zlib
from collections.abc import Callable
from pathlib import Path

import pytest

from voxam.aamachine.story import SUMMED
from voxam.iff import chunk as iff_chunk
from voxam.png import SIGNATURE
from voxam.zmachine.story import Story

FIXTURES = Path(__file__).parent / "fixtures"


def _piece(name: bytes, payload: bytes) -> bytes:
    return (
        len(payload).to_bytes(4, "big")
        + name
        + payload
        + zlib.crc32(name + payload).to_bytes(4, "big")
    )


@pytest.fixture
def tiny_png() -> bytes:
    """A 2-by-2 truecolour PNG: one bright row over a black one.

    Decodes to ((10, 20, 30), (40, 50, 60)) atop two black pixels
    -- the smallest real picture a gallery test can hang.
    """

    header = struct.pack(">IIBBBBB", 2, 2, 8, 2, 0, 0, 0)
    raw = b"\x00" + bytes(range(10, 70, 10)) + b"\x00" + bytes(6)

    return (
        SIGNATURE
        + _piece(b"IHDR", header)
        + _piece(b"IDAT", zlib.compress(raw))
        + _piece(b"IEND", b"")
    )


@pytest.fixture
def indexed_png() -> Callable[..., bytes]:
    """A factory for 2-by-1 indexed PNGs in the APal style."""

    def build(
        colours: tuple[tuple[int, int, int], ...],
        alphas: bytes = b"",
        raw: bytes = b"\x00\x00\x01",
    ) -> bytes:
        pieces = [
            SIGNATURE,
            _piece(b"IHDR", struct.pack(">IIBBBBB", 2, 1, 8, 3, 0, 0, 0)),
            _piece(b"PLTE", b"".join(bytes(colour) for colour in colours)),
        ]

        if alphas:
            pieces.append(_piece(b"tRNS", alphas))

        pieces.append(_piece(b"IDAT", zlib.compress(raw)))
        pieces.append(_piece(b"IEND", b""))

        return b"".join(pieces)

    return build


@pytest.fixture
def holey_png() -> bytes:
    """A 2-by-1 palette PNG: one red pixel, one fully transparent.

    The tRNS chunk marks the second palette entry clear -- the
    smallest piece of see-through Version 6 chrome a test can
    draw.
    """

    header = struct.pack(">IIBBBBB", 2, 1, 8, 3, 0, 0, 0)

    return (
        SIGNATURE
        + _piece(b"IHDR", header)
        + _piece(b"PLTE", bytes([200, 0, 0, 9, 9, 9]))
        + _piece(b"tRNS", bytes([255, 0]))
        + _piece(b"IDAT", zlib.compress(b"\x00\x00\x01"))
        + _piece(b"IEND", b"")
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


def _aastory(*, branded: bool) -> bytes:
    """A minimal valid Å-machine story: META, one Å aboard."""

    lang = (
        b"\x00\x00"
        + (8).to_bytes(2, "big")
        + b"\x00\x00\x00\x00"
        + bytes([1, 0xE5, 0xC5])
        + (0xC5).to_bytes(3, "big")
    )
    summed = {b"LANG": lang, b"DICT": b"\x00\x00"}
    crc = 0

    for name in SUMMED:
        crc = zlib.crc32(summed.get(name, b""), crc)

    head = (
        bytes([0, 5, 2, 0])
        + (7).to_bytes(2, "big")
        + b"260827"
        + crc.to_bytes(4, "big")
        + (16).to_bytes(2, "big")
        + (8).to_bytes(2, "big")
        + (32).to_bytes(2, "big")
        + (b"UUID://a5aa4f02-8f50-4649-a4bd-b1b5c5408b67//\x00" if branded else b"")
    )
    meta = bytes([2]) + b"\x01Cloak\x00" + b"\x02\x80kesson\x00"
    pieces = [iff_chunk(b"HEAD", head), iff_chunk(b"META", meta)]

    for name in SUMMED:
        pieces.append(iff_chunk(name, summed.get(name, b"")))

    return iff_chunk(b"FORM", b"AAVM" + b"".join(pieces))


@pytest.fixture
def aastory() -> bytes:
    """The branded story: an IFID rides its HEAD."""

    return _aastory(branded=True)


@pytest.fixture
def bare_aastory() -> bytes:
    """The same story without the optional IFID field."""

    return _aastory(branded=False)
