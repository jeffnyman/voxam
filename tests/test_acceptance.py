from pathlib import Path

import pytest
from assertpy import assert_that

from voxam.acceptance import AcceptanceScript, RefusalWatch, refusal_in, replay
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


# A <key> line presses a special key: the cursor tokens translate
# to their §3.8.4 input characters, case-blind, and the escape key
# rides along. The `> <key>` prompt form stays a literal command --
# the hatch for a game that really wants angle brackets.
def test_key_tokens_press_their_characters(tmp_path: Path) -> None:
    script = AcceptanceScript.parse(
        script_file(
            tmp_path,
            """\
! GAME=games/bz.z5
<down>
<UP>
<left>
<right>
<escape>
> <down>
""",
        )
    )

    assert_that(script.commands).is_equal_to(
        ("\x82", "\x81", "\x83", "\x84", "\x1b", "<down>")
    )


# A token naming no known key is a typo, and a typo must not
# quietly type its letters into the game.
def test_unknown_key_tokens_fail_loudly(tmp_path: Path) -> None:
    path = script_file(tmp_path, "! GAME=g.z5\n<f9>\n")

    with pytest.raises(AcceptanceError, match=r"unknown key.*the keys are"):
        AcceptanceScript.parse(path)


# The replay transcript shows a pressed key as its token, never as
# the raw control character a piped console could not encode.
def test_replay_echoes_key_tokens_readably() -> None:
    echoed: list[str] = []
    source = replay(["\x82", "look"], echoed.append)

    assert_that(source()).is_equal_to("\x82")
    assert_that(source()).is_equal_to("look")
    assert_that(echoed).is_equal_to(["<down>\n", "look\n"])


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


# Fenced sections are skipped raw -- commands, comments, and even
# directives -- and text after the backticks labels the fence.
def test_fenced_sections_are_skipped(tmp_path: Path) -> None:
    script = AcceptanceScript.parse(
        script_file(
            tmp_path,
            """\
! GAME=g.z3
before
``` thief fight, redo under new seed
w. n
kill thief
! SEED=1234
```
after
""",
        )
    )

    assert_that(script.commands).is_equal_to(("before", "after"))
    assert_that(script.seed).is_none()


# An unclosed fence deliberately skips the rest of the file: one
# edit turns a full script into "replay only up to here".
def test_an_unclosed_fence_skips_the_rest(tmp_path: Path) -> None:
    script = AcceptanceScript.parse(
        script_file(tmp_path, "! GAME=g.z3\nkeep\n```\ndropped\nalso dropped\n")
    )

    assert_that(script.commands).is_equal_to(("keep",))


def test_fences_can_park_several_sections(tmp_path: Path) -> None:
    script = AcceptanceScript.parse(
        script_file(
            tmp_path,
            "! GAME=g.z3\none\n```\nx\n```\ntwo\n```\ny\n```\nthree\n",
        )
    )

    assert_that(script.commands).is_equal_to(("one", "two", "three"))


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


# Line numbers count lines of the FILE, comments and fences included,
# so a warning can point straight at the script.
def test_commands_remember_their_file_lines(tmp_path: Path) -> None:
    script = AcceptanceScript.parse(
        script_file(
            tmp_path,
            "! GAME=g.z3\n\n# a comment\nfirst\n```\nskipped\n```\nsecond\n",
        )
    )

    assert_that(script.commands).is_equal_to(("first", "second"))
    assert_that(script.lines).is_equal_to((4, 8))


def test_replay_reports_each_command_position() -> None:
    positions: list[int] = []
    echoed: list[str] = []
    source = replay(["look", "wait"], echoed.append, typed=positions.append)

    source()
    source()

    assert_that(positions).is_equal_to([0, 1])


# Real refusals drawn from the recordings that motivated the watch:
# each cost hours because it scrolled past unread.
@pytest.mark.parametrize(
    "response",
    [
        "You should close it first.",
        "You can't see any statuette here!",
        'I don\'t know the word "leviathan".',
        "What do you want to pay the $69 to?",
        "Which door do you mean, the cell door or the bronze door?",
        "You must use a verb!",
        "I beg your pardon?",
        "You can't go that way.",
        "You can't do that since you gashed your arm!",
        "Your load is too heavy. You'll have to drop something.",
        "You can't quite reach it.",
        '[I don\'t know the word "bloody".]',
        "That's not a verb I recognise.",
        "That's not a verb I recognize.",
        "I didn't understand that sentence.",
        "I only understood you as far as wanting to go.",
        "You can't see any such thing.",
    ],
)
def test_the_refusal_dialect_is_recognized(response: str) -> None:
    assert_that(refusal_in(response)).is_equal_to(response)


@pytest.mark.parametrize(
    "response",
    [
        "Taken.",
        "The bedroom door is now locked.",
        "You have purchased a flashlight for $24.",
        "Time passes...",
        "Considering the frigid temperature of the water, you should "
        "probably not plan an extended stay.",
        "Okay, Jeff, what do you want to do now?",
        "The sign says you can't go that way in winter.",
        "[Your score has just gone up by five points.]",
        "Your load of firewood tumbles onto the hearth.",
    ],
)
def test_ordinary_responses_pass_unremarked(response: str) -> None:
    assert_that(refusal_in(response)).is_none()


# Daemon chatter surrounds real refusals; only the offending line
# comes back, so the warning stays readable.
def test_the_offending_line_is_extracted() -> None:
    response = (
        "(with the room key)\n"
        "You should close it first.\n"
        "Your stomach is growling loudly.\n"
    )

    assert_that(refusal_in(response)).is_equal_to("You should close it first.")


def watched_script(tmp_path: Path) -> AcceptanceScript:
    return AcceptanceScript.parse(
        script_file(tmp_path, "! GAME=g.z3\n# opener\nlock door\nwait\n")
    )


# The response to a command is everything printed before the next is
# typed; a refusal in it names the command and its script line.
def test_the_watch_warns_with_command_and_line(tmp_path: Path) -> None:
    warnings: list[str] = []
    watch = RefusalWatch(watched_script(tmp_path), warnings.append)

    watch.typed(0)
    watch.saw("You should close it first.\n")
    watch.typed(1)
    watch.saw("Time passes...\n")
    watch.finish()

    assert_that(warnings).is_equal_to(
        ["line 3: 'lock door' looks refused: You should close it first."]
    )


def test_the_watch_judges_the_final_response(tmp_path: Path) -> None:
    warnings: list[str] = []
    watch = RefusalWatch(watched_script(tmp_path), warnings.append)

    watch.typed(0)
    watch.saw("Locked.\n")
    watch.typed(1)
    watch.saw("You can't see any door here!\n")
    watch.finish()

    assert_that(warnings).is_equal_to(
        ["line 4: 'wait' looks refused: You can't see any door here!"]
    )


# finish is idempotent: at a --replay handoff the watch closes early,
# and the session-end finish must not re-judge live typing.
def test_finishing_twice_warns_once(tmp_path: Path) -> None:
    warnings: list[str] = []
    watch = RefusalWatch(watched_script(tmp_path), warnings.append)

    watch.typed(0)
    watch.saw("I beg your pardon?\n")
    watch.finish()
    watch.saw("You can't go that way.\n")
    watch.finish()

    assert_that(warnings).is_length(1)
