"""Tests for the Å-machine's terminal face, streams replaced."""

import io
import sys
from pathlib import Path

import pytest
from assertpy import assert_that

from voxam.aamachine.output import Dress, tinted
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


# -- the dress ---------------------------------------------------------

ESC = "\x1b"


def dressed_voice(name: str = "gosling") -> TerminalVoice:
    """A dressed voice over a vendored story's own LOOK sheet."""

    story = storied(name)

    return TerminalVoice(story, 80, io.StringIO(), lambda _prompt: "", dressed=True)


# A bold class lands as the terminal's own bold, and leaving the
# span drops it.
def test_a_bold_span_wears_bold() -> None:
    voice = dressed_voice()
    voice.enter_span(10)
    voice.say("clue")
    voice.leave_span()

    assert_that(voice.told()).is_equal_to(f"{ESC}[0;1mclue{ESC}[0m")


# Italics wear underlines, the Dialog debugger's own rendering,
# and a nested normal!important turns them off -- Miss Gosling's
# sheets do exactly this inside italic quotations.
def test_italics_wear_underlines_and_normal_overrides() -> None:
    voice = dressed_voice()
    voice.enter_span(8)
    voice.say("a")
    voice.enter_span(7)
    voice.say("b")
    voice.leave_span()
    voice.say("c")
    voice.leave_span()

    assert_that(voice.told()).is_equal_to(f"{ESC}[0;4ma{ESC}[0mb{ESC}[0;4mc{ESC}[0m")


# A named color rides as truecolor ink, insistence stripped.
def test_a_named_color_wears_truecolor() -> None:
    voice = dressed_voice()
    voice.enter_span(1)

    assert_that(voice.told()).contains(f"{ESC}[0;1;38;2;205;49;49m")


# The body dress layers beneath everything: green ink on black
# paper, in italics-as-underline, exactly its sheet.
def test_the_body_wears_its_whole_sheet() -> None:
    voice = dressed_voice("body_not_status")
    voice.set_body(0)

    assert_that(voice.told()).is_equal_to(f"{ESC}[0;4;38;2;13;188;121;48;2;0;0;0m")


# The deprecated style bits compose and clear: bold and reverse
# on, bold off leaves reverse, unstyle drops the rest.
def test_the_deprecated_bits_compose() -> None:
    voice = dressed_voice()
    voice.set_style(3)
    voice.reset_style(2)
    voice.unstyle()

    assert_that(voice.told()).is_equal_to(f"{ESC}[0;1;7m{ESC}[0;7m{ESC}[0m")


# leave_all drops every open span's dress at once -- the machine
# clears its ledger without a leave call per div.
def test_leave_all_drops_the_stack() -> None:
    voice = dressed_voice()
    voice.enter_span(10)
    voice.enter_span(8)
    voice.leave_all()

    assert_that(voice.told()).ends_with(f"{ESC}[0m")


# A class LOOK never named wears the bare dress, and divs carry
# their dress around their breaks.
def test_unnamed_classes_and_divs_dress_too() -> None:
    voice = dressed_voice()
    voice.enter_div(17)
    voice.say("title")
    voice.leave_div(17)
    voice.enter_span(99)

    told = voice.told()

    assert_that(told).contains(f"{ESC}[0;1mtitle")
    assert_that(told).ends_with(f"{ESC}[0m")


# Inside a hidden status area no dress lands at all.
def test_a_hidden_status_swallows_the_dress() -> None:
    voice = dressed_voice()
    voice.enter_status(0, 0)
    voice.enter_span(10)
    voice.say("hidden")
    voice.leave_span()
    voice.leave_status()

    assert_that(voice.told()).does_not_contain(ESC)


# An undressed voice stays plain everywhere and reports itself
# honestly to VM_INFO's seams.
def test_the_honesty_gate_holds() -> None:
    plain = TerminalVoice(
        storied(), 80, io.StringIO(), lambda _prompt: "", dressed=False
    )
    plain.enter_span(10)
    plain.say("plain")
    plain.undressed()

    assert_that(plain.told()).is_equal_to("plain")
    assert_that(plain.has_styles).is_false()
    assert_that(plain.has_color).is_false()

    worn = dressed_voice()

    assert_that(worn.has_styles).is_true()
    assert_that(worn.has_color).is_true()


# The color parser speaks hex short and long, rgb(), and shrugs
# at what it cannot mix; the weight parser hears normal too.
def test_the_color_and_weight_parsers() -> None:
    assert_that(tinted("#fff")).is_equal_to((255, 255, 255))
    assert_that(tinted("#a1b2c3")).is_equal_to((161, 178, 195))
    assert_that(tinted("rgb(1, 2, 3)")).is_equal_to((1, 2, 3))
    assert_that(tinted("rgb(bad)")).is_none()
    assert_that(tinted("rgb(1, 2, x)")).is_none()
    assert_that(tinted("linen")).is_none()
    assert_that(tinted("")).is_none()

    dress = Dress({"font-weight": "normal", "font-style": "oblique"})

    assert_that(dress.bold).is_false()
    assert_that(dress.italic).is_true()


# A whole dressed session: the body test plays green-on-black and
# takes every attribute off at the end.
def test_a_dressed_session_closes_clean() -> None:
    story = storied("body_not_status")
    writer = io.StringIO()
    played(
        story,
        seed=7,
        reader=io.StringIO("\n"),
        writer=writer,
        width=80,
        dressed=True,
    )
    told = writer.getvalue()

    assert_that(told).contains(f"{ESC}[0;4;38;2;13;188;121;48;2;0;0;0m")
    assert_that(told).ends_with(f"{ESC}[0m")


# A leave with nothing worn is a story's imbalance, answered
# calmly with the bare dress rather than a crash.
def test_an_unworn_leave_stays_calm() -> None:
    voice = dressed_voice()
    voice.leave_span()
    voice.leave_div(0)

    assert_that(voice.told()).starts_with(f"{ESC}[0m{ESC}[0m")
