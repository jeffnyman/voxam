from pathlib import Path

import pytest
from assertpy import assert_that

from voxam.errors import ZMachineStoryError
from voxam.zmachine.story import HEADER_SIZE, Story


def story_bytes(version: int = 3, size: int = HEADER_SIZE) -> bytes:
    return bytes([version]) + bytes(size - 1)


def test_rejects_content_too_short_for_header() -> None:
    with pytest.raises(ZMachineStoryError, match="63 bytes"):
        Story(story_bytes(size=HEADER_SIZE - 1))


def test_rejects_empty_content() -> None:
    with pytest.raises(ZMachineStoryError, match="0 bytes"):
        Story(b"")


@pytest.mark.parametrize("version", range(1, 9))
def test_accepts_every_valid_version(version: int) -> None:
    story = Story(story_bytes(version=version))

    assert_that(story.version).is_equal_to(version)


@pytest.mark.parametrize("version", [0, 9, 255])
def test_rejects_versions_that_do_not_exist(version: int) -> None:
    with pytest.raises(ZMachineStoryError, match=f"version {version}"):
        Story(story_bytes(version=version))


def test_loads_from_disk(tmp_path: Path) -> None:
    path = tmp_path / "test.z3"
    path.write_bytes(story_bytes(version=3))

    story = Story.load(path)

    assert_that(story.version).is_equal_to(3)
