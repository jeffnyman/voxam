"""Tests for the Å-machine engine, certified against the reference.

The vendored stories and golds are the community fork's own test
batteries: aa-exercise stresses every opcode, body_not_status is
a format 1.0 story exercising SET_BODY, and codepoints walks the
character set, the keypress loop, and the progress bars. Each
gold is the reference JS engine's transcript at seed 1234 --
aa-exercise's regenerated without its SAVEFILE feature lines,
since this engine honestly reports no savefile support yet.

The aa-exercise fixture is the reference repository's own story
with two repairs its assembler skipped: a truthful FORM length
and the HEAD's real CRC-32. The reference engine checks neither;
Voxam's door checks both.
"""

from pathlib import Path

from assertpy import assert_that

from voxam.aamachine.machine import Machine, walked
from voxam.aamachine.output import PlainVoice
from voxam.aamachine.story import Story

FIXTURES = Path(__file__).parent.parent / "fixtures"


def fixed(name: str) -> Story:
    """One vendored story, parsed."""

    return Story((FIXTURES / f"{name}.aastory").read_bytes())


def golden(name: str) -> str:
    """One vendored gold transcript."""

    return (FIXTURES / f"{name}.gold").read_text(encoding="utf-8")


def scripted(name: str) -> str:
    """One vendored input script, terminators and all."""

    return (FIXTURES / f"{name}.in").read_text(encoding="utf-8")


# The whole-instruction-set certification: the reference test
# suite runs to completion and the transcript matches the
# reference engine's own, word for word and wrap for wrap.
def test_the_exercise_matches_the_reference_gold() -> None:
    assert_that(walked(fixed("aa-exercise"), "", seed=1234)).is_equal_to(
        golden("aa-exercise")
    )


# The full-game certification: Miss Gosling's Last Case (Daniel
# Stelzer, CC-BY 4.0 and MIT -- see LICENSE-gosling.txt), a 351-line
# walk through a real Dialog game: the parser, the endings decoder,
# the wordmaps, links, long-term storage, and the seeded dice all
# land exactly where the reference engine put them.
def test_the_gosling_walk_matches_its_gold() -> None:
    told = walked(fixed("gosling"), scripted("gosling"), seed=1234)

    assert_that(told).is_equal_to(golden("gosling"))


# The format 1.0 fork of opcode $67: SET_BODY, not ENTER_STATUS,
# and LEAVE_STATUS at $EF.
def test_a_format_one_story_matches_its_gold() -> None:
    told = walked(fixed("body_not_status"), scripted("body_not_status"), seed=1234)

    assert_that(told).is_equal_to(golden("body_not_status"))


# The character set, the keypress loop, the wrap buffer, and the
# progress bars, all against the reference transcript. The input
# script's final line carries no newline -- deliberately, and the
# echo honors that.
def test_the_codepoints_walk_matches_its_gold() -> None:
    told = walked(fixed("codepoints"), scripted("codepoints"), seed=1234)

    assert_that(told).is_equal_to(golden("codepoints"))


# The machine reports how it stopped: the exercise quits on its
# own, and the running flag goes down with it.
def test_a_quit_story_stops_running() -> None:
    story = fixed("aa-exercise")
    machine = Machine(story, PlainVoice(story), seed=1234)

    assert_that(machine.run()).is_equal_to("quit")
    assert_that(machine.running).is_false()


# An unseeded machine still runs whole -- the dice just come from
# the clock, the way the reference engine's do.
def test_an_unseeded_machine_still_runs() -> None:
    story = fixed("aa-exercise")
    machine = Machine(story, PlainVoice(story))

    assert_that(machine.run()).is_equal_to("quit")
