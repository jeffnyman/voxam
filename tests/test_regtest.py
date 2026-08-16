from collections.abc import Callable
from pathlib import Path

import pytest
from assertpy import assert_that

from voxam.errors import RegTestError
from voxam.regtest import COUNTED, LITERAL, PATTERN, parse_script, run_script

# Encodes "you must use a verb" the way test_cli's refusing story
# does: a story that reads one command, answers in the parser's
# voice, and quits -- output for checks to bite on.


def ztext(text: str) -> bytes:
    codes = [0 if c == " " else 6 + ord(c) - ord("a") for c in text]

    while len(codes) % 3:
        codes.append(5)

    words = []

    for index in range(0, len(codes), 3):
        word = (codes[index] << 10) | (codes[index + 1] << 5) | codes[index + 2]

        if index + 3 == len(codes):
            word |= 0x8000

        words.append(word)

    return b"".join(word.to_bytes(2, "big") for word in words)


def answering_story(tmp_path: Path) -> Path:
    data = bytearray(0xA0)
    data[0] = 3
    data[0x04:0x06] = (0x0090).to_bytes(2, "big")
    data[0x06:0x08] = (0x0040).to_bytes(2, "big")
    data[0x08:0x0A] = (0x007A).to_bytes(2, "big")
    data[0x0E:0x10] = (0x0090).to_bytes(2, "big")
    code = (
        bytes([0xE4, 0x0F, 0x00, 0x70, 0x00, 0x78])
        + bytes([0xB2])
        + ztext("you must use a verb")
        + bytes([0xBA])
    )
    data[0x40 : 0x40 + len(code)] = code
    data[0x70] = 6
    data[0x78] = 1
    data[0x7A] = 0
    data[0x7B] = 7
    path = tmp_path / "answers.z3"
    path.write_bytes(bytes(data))

    return path


def script_file(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "suite.regtest"
    path.write_text(content, encoding="utf-8")

    return path


# The parser reads the reference's format whole: directives, named
# tests, opening checks before the first command, per-command
# checks with their modifiers, and {char} commands translated to
# the input seam's own characters.
def test_the_format_parses_whole(tmp_path: Path) -> None:
    script = parse_script(
        script_file(
            tmp_path,
            "# a comment\n"
            "** game: some/story.z5\n"
            "** interpreter: /bin/voxam --plain --seed 777\n"
            "** pre: verbose\n"
            "\n"
            "* opening\n"
            "Welcome text\n"
            "/W[ea]lcome\n"
            "!grue\n"
            "\n"
            "* keys\n"
            "> look\n"
            "{count=2} door\n"
            "> {line} verbose\n"
            "> {char} y\n"
            "> {char} space\n"
            "> {char} down\n"
            "> {char} return\n"
            "> {char} 0x41\n"
            "> {char} 66\n"
            "\n"
            "* -hidden\n"
            "> unseen\n",
        )
    )

    assert_that(script.game).is_equal_to(Path("some/story.z5"))
    assert_that(script.seed).is_equal_to(777)
    assert_that(script.precommands).is_equal_to(("verbose",))
    assert_that([test.name for test in script.tests]).is_equal_to(
        ["opening", "keys", "-hidden"]
    )

    opening = script.tests[0]

    assert_that([check.kind for check in opening.opening]).is_equal_to(
        [LITERAL, PATTERN, LITERAL]
    )
    assert_that(opening.opening[1].text).is_equal_to("W[ea]lcome")
    assert_that(opening.opening[2].inverse).is_true()

    keys = script.tests[1]

    assert_that([step.send for step in keys.steps]).is_equal_to(
        ["look", "verbose", "y", " ", "\x82", "", "A", "B"]
    )
    assert_that(keys.steps[0].checks[0].kind).is_equal_to(COUNTED)
    assert_that(keys.steps[0].checks[0].count).is_equal_to(2)


# Everything the reference refuses -- and everything it accepts
# that this runner does not carry -- fails loudly, with its line.
@pytest.mark.parametrize(
    ("content", "complaint"),
    [
        ("** game: a.z3\n** mystery: 1\n", "not supported by this runner"),
        ("** game: a.z3\n* t\n** game: b.z3\n", "overrides are not supported"),
        ("** game: a.z3\n* t\n{sideways}text\n", "unknown test modifier"),
        ("** game: a.z3\n* t\n> {timer}\n", "not supported by this runner"),
        ("** game: a.z3\n* t\n> {char} pageup\n", "cannot press"),
        ("** game: a.z3\n> early\n", "before any"),
        ("** game: a.z3\nearly check\n", "before any"),
        ("** game: a.z3\n* t\n* t\n", "used twice"),
        ("* t\n> look\n", "names no game"),
        ("** interpreter: voxam --seed\n** game: a.z3\n", "names no number"),
        ("** game: a.z3\n* t\n> {char} 0xZZ\n", "cannot press"),
    ],
)
def test_unusable_scripts_are_refused(
    tmp_path: Path, content: str, complaint: str
) -> None:
    with pytest.raises(RegTestError, match=complaint):
        parse_script(script_file(tmp_path, content))


# A ** line without a colon is skipped, exactly as the reference
# skips it.
def test_colonless_directives_are_skipped(tmp_path: Path) -> None:
    script = parse_script(script_file(tmp_path, "** stray\n** game: a.z3\n"))

    assert_that(script.game).is_equal_to(Path("a.z3"))


# The runner boots a fresh machine per test and judges each
# response window: the opening text before any command, then each
# command's reply -- here the parser's one answer, checked three
# ways, with the failing fourth reported in the reference's voice.
def test_responses_are_judged_per_command(
    tmp_path: Path, fixture_path: Callable[[int], Path]
) -> None:
    story = answering_story(tmp_path)
    report: list[str] = []
    script = parse_script(
        script_file(
            tmp_path,
            f"** game: {story}\n"
            "* answered\n"
            "> frotz\n"
            "you must use a verb\n"
            "/must .* a verb\n"
            "!grue\n"
            "bucket of cheese\n",
        )
    )

    errors = run_script(script, report.append)

    assert_that(errors).is_equal_to(1)
    assert_that(report[0]).is_equal_to("* answered")
    assert_that(report[1]).contains('<LiteralCheck:7 "bucket of cheese">')
    assert_that(report[1]).contains("not found")

    hello = parse_script(
        script_file(
            tmp_path,
            f"** game: {fixture_path(3)}\n"
            "* opening\n"
            "hello from all z machine versions\n"
            "{count=1} hello\n"
            "{count=2} hello\n",
        )
    )
    report.clear()

    errors = run_script(hello, report.append)

    assert_that(errors).is_equal_to(1)
    assert_that(report[1]).contains("{count=2} ")
    assert_that(report[1]).contains("only found 1 times")


# The status and graphics windows answer as the reference's cheap
# mode answers -- empty -- so a positive check there fails and an
# inverse one passes; a plain inverse against real text fails with
# the reference's own words.
def test_windows_and_inversions_match_cheap_mode(
    tmp_path: Path, fixture_path: Callable[[int], Path]
) -> None:
    report: list[str] = []
    script = parse_script(
        script_file(
            tmp_path,
            f"** game: {fixture_path(3)}\n"
            "* windows\n"
            "{status}hello\n"
            "!{status}hello\n"
            "{graphics}hello\n"
            "!hello\n"
            "{count=3} grue\n",
        )
    )

    errors = run_script(script, report.append)

    assert_that(errors).is_equal_to(4)
    assert_that(report[1]).contains("{status}")
    assert_that(report[2]).contains("{graphics}")
    assert_that(report[3]).contains("inverse test should fail")
    assert_that(report[4]).contains("not found")


# A {vital} failure ends its test on the spot: the second check
# never runs, and the next test still does.
def test_vital_failures_end_the_test(
    tmp_path: Path, fixture_path: Callable[[int], Path]
) -> None:
    report: list[str] = []
    script = parse_script(
        script_file(
            tmp_path,
            f"** game: {fixture_path(3)}\n"
            "* doomed\n"
            "{vital} bucket of cheese\n"
            "also never judged\n"
            "* after\n"
            "hello\n",
        )
    )

    errors = run_script(script, report.append)

    assert_that(errors).is_equal_to(1)
    assert_that(report).is_length(3)
    assert_that(report[2]).is_equal_to("* after")


# Hidden tests are skipped as the reference's default pattern
# skips them, and a script of only hidden tests says so.
def test_hidden_tests_are_skipped(
    tmp_path: Path, fixture_path: Callable[[int], Path]
) -> None:
    report: list[str] = []
    script = parse_script(
        script_file(
            tmp_path,
            f"** game: {fixture_path(3)}\n* -quiet\nnever judged\n",
        )
    )

    errors = run_script(script, report.append)

    assert_that(errors).is_zero()
    assert_that(report).is_equal_to(["No tests performed!"])


# An unreadable game is one logged error, and the run carries on
# to the next test, as the reference carries on.
def test_a_broken_game_is_one_error(tmp_path: Path) -> None:
    report: list[str] = []
    script = parse_script(
        script_file(
            tmp_path,
            "** game: no-such-story.z3\n* broken\nanything\n",
        )
    )

    errors = run_script(script, report.append)

    assert_that(errors).is_equal_to(1)
    assert_that(report[1]).contains("Error")


# A long check text is shortened in the report, as the reference
# shortens it.
def test_long_check_texts_are_shortened(
    tmp_path: Path, fixture_path: Callable[[int], Path]
) -> None:
    report: list[str] = []
    sought = "a very long expectation that goes on well past the limit"
    script = parse_script(
        script_file(tmp_path, f"** game: {fixture_path(3)}\n* long\n{sought}\n")
    )

    run_script(script, report.append)

    assert_that(report[1]).contains(sought[:32] + "...")
    assert_that(report[1]).does_not_contain(sought)


# A script may run out while the game still wants input: the final
# window is judged all the same, through the end-of-input path.
def test_a_short_script_still_judges_its_last_window(tmp_path: Path) -> None:
    story = answering_story(tmp_path)
    report: list[str] = []
    script = parse_script(
        script_file(tmp_path, f"** game: {story}\n* quiet\n!anything\n")
    )

    errors = run_script(script, report.append)

    assert_that(errors).is_zero()
    assert_that(report).is_equal_to(["* quiet"])


# An interpreter line without a --seed simply leaves the dice to
# entropy, as the reference would.
def test_an_interpreter_line_without_a_seed_is_fine(tmp_path: Path) -> None:
    script = parse_script(
        script_file(tmp_path, "** interpreter: frotz -q\n** game: a.z3\n")
    )

    assert_that(script.seed).is_none()
