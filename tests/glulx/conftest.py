"""Shared pytest fixtures for the Glulx tests."""

from collections.abc import Callable

import pytest

from voxam.glulx.story import CHECKSUM_AT


@pytest.fixture
def image() -> Callable[..., bytes]:
    """Provide a builder for tiny checksummed Glulx images."""

    def _build(
        version: int = 0x00030102,
        ramstart: int = 0x100,
        extstart: int = 0x200,
        endmem: int = 0x300,
        stack: int = 0x100,
        checksum: int | None = None,
        magic: bytes = b"Glul",
        size: int | None = None,
    ) -> bytes:
        data = bytearray(size if size is not None else extstart)
        data[0:4] = magic
        data[4:8] = version.to_bytes(4, "big")
        data[8:12] = ramstart.to_bytes(4, "big")
        data[12:16] = extstart.to_bytes(4, "big")
        data[16:20] = endmem.to_bytes(4, "big")
        data[20:24] = stack.to_bytes(4, "big")
        data[24:28] = (0x48).to_bytes(4, "big")
        data[28:32] = (0x54).to_bytes(4, "big")

        if checksum is None:
            checksum = sum(
                int.from_bytes(data[at : at + 4], "big")
                for at in range(0, len(data), 4)
                if at != CHECKSUM_AT
            ) % (1 << 32)

        data[CHECKSUM_AT : CHECKSUM_AT + 4] = checksum.to_bytes(4, "big")

        return bytes(data)

    return _build
