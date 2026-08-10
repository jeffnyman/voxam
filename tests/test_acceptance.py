from pathlib import Path

import pytest
from assertpy import assert_that

from voxam.acceptance import AcceptanceScript, replay
from voxam.errors import AcceptanceError


def script_file(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "session.accept"
    path.write_text(content, encoding="utf-8")

    return path


# The whole grammar in one file: directives, comments in both forms,
# the optional prompt prefix, its escape, and a bare > for an empty
# line.
def test_parses_the_full_grammar(tmp_path: Path) -> None:
    script = AcceptanceScript.parse(
        script_file(
            tmp_path,
            """\
! SEED=99
! GAME=games/fade.z1

# A full-line comment.
   # An indented one.

x me. x Justin
wait      # inline comment
> open mailbox   # prompt style
> #literal
>
plain command
""",
        )
    )

    assert_that(script.game).is_equal_to(tmp_path / "games/fade.z1")
    assert_that(script.seed).is_equal_to(99)
    assert_that(script.commands).is_equal_to(
        (
            "x me. x Justin",
            "wait",
            "open mailbox",
            "#literal",
            "",
            "plain command",
        )
    )


# A relative game path counts from the script's own directory, so a
# script replays identically whatever directory it is run from; an
# absolute path passes through.
def test_game_paths_resolve_against_the_script(tmp_path: Path) -> None:
    nested = tmp_path / "acceptance"
    nested.mkdir()
    script_path = nested / "session.accept"
    script_path.write_text("! GAME=../games/zork.z3\nlook\n", encoding="utf-8")

    script = AcceptanceScript.parse(script_path)

    assert_that(script.game).is_equal_to(nested / ".." / "games" / "zork.z3")

    absolute = tmp_path / "elsewhere.z3"
    script_path.write_text(f"! GAME={absolute}\n", encoding="utf-8")

    assert_that(AcceptanceScript.parse(script_path).game).is_equal_to(absolute)


def test_the_seed_is_optional(tmp_path: Path) -> None:
    script = AcceptanceScript.parse(script_file(tmp_path, "! GAME=g.z3\nlook\n"))

    assert_that(script.seed).is_none()


def test_a_script_must_name_its_game(tmp_path: Path) -> None:
    with pytest.raises(AcceptanceError, match="names no game"):
        AcceptanceScript.parse(script_file(tmp_path, "look\n"))


def test_unknown_directives_fail_loudly(tmp_path: Path) -> None:
    with pytest.raises(AcceptanceError, match="unknown directive SEDE"):
        AcceptanceScript.parse(script_file(tmp_path, "! SEDE=99\n"))


def test_malformed_directives_are_rejected(tmp_path: Path) -> None:
    with pytest.raises(AcceptanceError, match="KEY=VALUE"):
        AcceptanceScript.parse(script_file(tmp_path, "! SEED 99\n"))


def test_an_unusable_seed_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(AcceptanceError, match="is not a number"):
        AcceptanceScript.parse(script_file(tmp_path, "! SEED=xyzzy\n"))


# The replay source types each command once, echoing it with its
# newline, and signals end of input forever after.
def test_replay_types_then_signals_eof() -> None:
    echoed: list[str] = []
    source = replay(["look", "quit"], echoed.append)

    assert_that(source()).is_equal_to("look")
    assert_that(source()).is_equal_to("quit")
    assert_that(echoed).is_equal_to(["look\n", "quit\n"])

    with pytest.raises(EOFError):
        source()

    with pytest.raises(EOFError):
        source()


# With a handoff, exhaustion yields to live input instead of ending
# -- and handed-off lines are not echoed, since a real terminal
# shows typing itself.
def test_replay_can_hand_off_to_live_input() -> None:
    echoed: list[str] = []
    live = iter(["north", "south"])
    source = replay(["look"], echoed.append, exhausted=lambda: next(live))

    assert_that(source()).is_equal_to("look")
    assert_that(source()).is_equal_to("north")
    assert_that(source()).is_equal_to("south")
    assert_that(echoed).is_equal_to(["look\n"])
