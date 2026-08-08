"""Shared pytest fixtures for the Z-Machine tests."""

from collections.abc import Callable

import pytest

from voxam.zmachine.machine import Machine
from voxam.zmachine.memory import Memory
from voxam.zmachine.story import Story


def _image(code: bytes, version: int) -> Story:
    """Build a 512-byte story with code planted at $40.

    The initial program counter points at the code, the globals table
    sits at $100, and static memory begins at $1C0 -- so planted code
    can read and write low globals and grow riders freely.
    """

    data = bytearray(512)
    data[0] = version
    data[0x04:0x06] = (0x01C0).to_bytes(2, "big")
    data[0x06:0x08] = (0x0040).to_bytes(2, "big")
    data[0x0C:0x0E] = (0x0100).to_bytes(2, "big")
    data[0x0E:0x10] = (0x01C0).to_bytes(2, "big")
    data[0x40 : 0x40 + len(code)] = code

    return Story(bytes(data))


@pytest.fixture
def code_memory() -> Callable[..., Memory]:
    """Provide a builder for a memory image with planted code."""

    def _build(code: bytes = b"", version: int = 3) -> Memory:
        return Memory(_image(code, version))

    return _build


@pytest.fixture
def code_machine() -> Callable[..., Machine]:
    """Provide a builder for a machine whose execution starts at $40."""

    def _build(
        code: bytes = b"",
        version: int = 3,
        output: Callable[[str], None] | None = None,
    ) -> Machine:
        return Machine(_image(code, version), output)

    return _build
