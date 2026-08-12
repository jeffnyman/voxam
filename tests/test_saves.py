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
