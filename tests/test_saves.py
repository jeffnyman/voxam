from pathlib import Path

from assertpy import assert_that

from voxam.saves import FileSaveSlot


def test_a_saved_game_round_trips_through_its_file(tmp_path: Path) -> None:
    slot = FileSaveSlot(tmp_path / "story.sav")

    assert_that(slot.write(b"FORM...")).is_true()
    assert_that(slot.read()).is_equal_to(b"FORM...")


def test_an_absent_file_reads_as_no_save(tmp_path: Path) -> None:
    slot = FileSaveSlot(tmp_path / "never-written.sav")

    assert_that(slot.read()).is_none()


# A path that cannot be written -- here, an existing directory -- is
# a failed save, reported as such rather than raised (§15 save).
def test_an_unwritable_path_is_a_failed_save(tmp_path: Path) -> None:
    slot = FileSaveSlot(tmp_path)

    assert_that(slot.write(b"FORM...")).is_false()
    assert_that(slot.read()).is_none()


# Auxiliary files land beside the save under a sanitized name plus
# the .aux extension (§7.6): whatever path-like mischief the story
# supplies stays inside the directory.
def test_an_auxiliary_file_round_trips(tmp_path: Path) -> None:
    slot = FileSaveSlot(tmp_path / "story.sav")

    assert_that(slot.write_aux("map", b"data")).is_true()
    assert_that(slot.read_aux("map")).is_equal_to(b"data")
    assert_that((tmp_path / "map.aux").exists()).is_true()


def test_a_path_like_name_is_defanged(tmp_path: Path) -> None:
    slot = FileSaveSlot(tmp_path / "story.sav")

    assert_that(slot.write_aux("../../e vil", b"x")).is_true()
    assert_that((tmp_path / "evil.aux").exists()).is_true()
    assert_that(slot.read_aux("../../e vil")).is_equal_to(b"x")


def test_a_missing_auxiliary_file_reads_as_none(tmp_path: Path) -> None:
    slot = FileSaveSlot(tmp_path / "story.sav")

    assert_that(slot.read_aux("never")).is_none()


def test_an_unwritable_auxiliary_path_is_a_failure(tmp_path: Path) -> None:
    slot = FileSaveSlot(tmp_path / "no-such-dir" / "story.sav")

    assert_that(slot.write_aux("map", b"x")).is_false()
