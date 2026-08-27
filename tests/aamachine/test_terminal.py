"""Tests for the Å-machine's terminal face, streams replaced."""

import io
import sys
from pathlib import Path

import pytest
from assertpy import assert_that

from voxam.aamachine.story import Story
from voxam.aamachine.terminal import TerminalVoice, played

FIXTURES = Path(__file__).parent.parent / "fixtures"


def storied(name: str = "cloak-rel2") -> Story:
    """One vendored story, parsed."""

    return Story((FIXTURES / f"{name}.aastory").read_bytes())


def acted(
    story: Story,
    commands: str,
    answers: "list[str] | None" = None,
    width: int = 80,
) -> str:
    """Play a story with scripted streams; the output comes back."""

    told = iter(answers or [])
    writer = io.StringIO()
    played(
        story,
        seed=7,
        reader=io.StringIO(commands),
        writer=writer,
        asked=lambda _prompt: next(told, ""),
        width=width,
    )

    return writer.getvalue()


# Cloak of Darkness plays at the terminal: the opening lands, a
# command walks, and the quit closes politely.
def test_cloak_plays_at_the_terminal() -> None:
    told = acted(storied(), "west\nquit\ny\n")

    assert_that(told).contains("Hurrying through the rainswept November night")
    assert_that(told).contains("Cloakroom")
    assert_that(told).contains("Thanks for playing!")


# A script that runs dry ends the session on a broken line.
def test_a_dry_script_ends_the_session() -> None:
    told = acted(storied(), "")

    assert_that(told).contains("Foyer of the Opera House")
    assert_that(told).ends_with("\n")


# A key wait takes the line a keypress at a time, return closing
# an exhausted line -- the codepoints battery's own drill.
def test_key_waits_take_lines_as_keypresses() -> None:
    told = acted(storied("codepoints"), "q\n")

    assert_that(told).contains("Codepoint Exercise")


# A save and restore round-trip through real files: hang the
# cloak, restore, and it is worn again.
def test_saves_round_trip_through_files(tmp_path: Path) -> None:
    keep = str(tmp_path / "cloak")
    told = acted(
        storied(),
        "save\nwest\nhang cloak on hook\nrestore\ninventory\nquit\ny\n",
        answers=[keep, keep],
    )

    assert_that((tmp_path / "cloak.aasave").exists()).is_true()
    assert_that(told).contains("Game state restored successfully.")
    assert_that(told).contains("wearing a velvet cloak")


# An empty filename cancels a save, and the story hears the
# refusal.
def test_an_empty_name_cancels_the_save() -> None:
    told = acted(storied(), "save\nquit\ny\n", answers=[""])

    assert_that(told).contains("Failed to save the game state.")


# A save that cannot be written, and a restore that cannot be
# read, both land as polite failures.
def test_unwritable_and_unreadable_files_fail_politely(tmp_path: Path) -> None:
    nowhere = str(tmp_path / "no" / "such" / "dir" / "file.aasave")
    told = acted(
        storied(),
        "save\nrestore\nquit\ny\n",
        answers=[nowhere, str(tmp_path / "absent.aasave")],
    )

    assert_that(told).contains("Failed to save the game state.")
    assert_that(told).contains("Failed to restore the game state.")


# A dotted name is honored whole; only a bare one gains the
# suffix.
def test_a_dotted_name_keeps_its_own_suffix(tmp_path: Path) -> None:
    keep = str(tmp_path / "game.sav")
    acted(storied(), "save\nquit\ny\n", answers=[keep])

    assert_that((tmp_path / "game.sav").exists()).is_true()


# The live seams fall back to the real streams and the real
# terminal width when nothing replaces them.
def test_the_live_seams_default(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    played(storied("body_not_status"), seed=7)

    told = capsys.readouterr().out

    assert_that(told).is_not_empty()


# The default asked() writes its prompt and reads its answer from
# the session's own streams.
def test_the_default_prompt_asks_the_reader(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)

    reader = io.StringIO("save\nkept\nquit\ny\n")
    writer = io.StringIO()
    played(storied(), seed=7, reader=reader, writer=writer, width=80)

    assert_that(writer.getvalue()).contains("Save the story as: ")
    assert_that((tmp_path / "kept.aasave").exists()).is_true()


# The terminal voice's file manners stand alone: a bare name
# gains the suffix through the asked seam.
def test_the_voice_asks_for_names(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)

    story = storied()
    voice = TerminalVoice(story, 80, io.StringIO(), lambda _prompt: "held")

    assert_that(voice.save(b"data")).is_true()
    assert_that((tmp_path / "held.aasave").exists()).is_true()
    assert_that(voice.restore()).is_equal_to(b"data")


# An exhausted key line closes with the return key, and both
# save and restore prompts honor a cancelling empty answer.
def test_an_exhausted_key_line_sends_return() -> None:
    told = acted(storied("codepoints"), "\nq\n")

    assert_that(told).contains("Codepoint Exercise")


# An empty restore name cancels like an empty save name.
def test_an_empty_name_cancels_the_restore() -> None:
    told = acted(storied(), "restore\nquit\ny\n", answers=[""])

    assert_that(told).contains("Failed to restore the game state.")
