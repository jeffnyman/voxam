"""The session files: lazy, session-scoped, loud on failure."""

from pathlib import Path
from typing import IO, cast

import pytest
from assertpy import assert_that

from voxam.errors import VoxamError
from voxam.scribe import FileScribe


def opened(tmp_path: Path) -> tuple[FileScribe, Path, Path]:
    transcript = tmp_path / "story.scr"
    commands = tmp_path / "story.cmd"

    return FileScribe(transcript, commands), transcript, commands


# Nothing is created until the game first asks; once it has, the
# same file serves for the whole session -- §7.1.1.2's decide-once
# courtesy -- however often the stream toggles.
def test_files_open_lazily_and_serve_the_whole_session(tmp_path: Path) -> None:
    scribe, transcript, commands = opened(tmp_path)

    assert_that(transcript.exists()).is_false()
    assert_that(commands.exists()).is_false()

    scribe.transcript("You are in a maze.\n")
    scribe.transcript(">plugh\n")
    scribe.command("plugh")
    scribe.command("xyzzy")
    scribe.close()

    assert_that(transcript.read_text(encoding="utf-8")).is_equal_to(
        "You are in a maze.\n>plugh\n"
    )
    assert_that(commands.read_text(encoding="utf-8")).is_equal_to("plugh\nxyzzy\n")


# Playback reads the commands file line by line -- §10.2.1's format
# is stream 4's own -- and a missing or spent file simply ends the
# stream with None, ever after.
def test_playback_reads_the_command_file_to_its_end(tmp_path: Path) -> None:
    scribe, _, commands = opened(tmp_path)

    commands.write_text("look\n\ngo north\n", encoding="utf-8")

    assert_that(scribe.playback()).is_equal_to("look")
    assert_that(scribe.playback()).is_equal_to("")
    assert_that(scribe.playback()).is_equal_to("go north")
    assert_that(scribe.playback()).is_none()
    assert_that(scribe.playback()).is_none()

    scribe.close()

    absent, _, _ = opened(tmp_path / "elsewhere")

    assert_that(absent.playback()).is_none()


# A file that cannot be opened or written halts loudly: a transcript
# lost to a full disk is worth hearing about.
def test_unwritable_session_files_are_loud(tmp_path: Path) -> None:
    blocked = FileScribe(tmp_path, tmp_path)

    with pytest.raises(VoxamError, match="cannot be opened"):
        blocked.transcript("hi")

    with pytest.raises(VoxamError, match="cannot be opened"):
        blocked.command("look")

    class Failing:
        def write(self, _text: str) -> int:
            raise OSError("disk full")

        def close(self) -> None:
            pass

    scribe, _, _ = opened(tmp_path)

    scribe.transcript("hi")
    scribe.close()
    scribe._transcript_file = cast("IO[str]", Failing())

    with pytest.raises(VoxamError, match="cannot be written"):
        scribe.transcript("more")

    scribe.close()
