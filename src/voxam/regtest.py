"""Running RegTest scripts in-process: the community's tester, everywhere.

RegTest is Andrew Plotkin's regression tester for interactive
fiction: a public-domain format of named tests, typed commands, and
per-turn checks, documented at
<https://eblong.com/zarf/plotex/regtest.html>. The reference
implementation drives an interpreter subprocess through POSIX
pipes; this runner reads the same format and drives the machine
through its own input seam instead -- no subprocess, no pipes, no
platform to be particular about, and a fresh machine per test at
in-process speed.

The subset is the format's core: line and {char} commands, the
literal, {count=N}, and /regular-expression/ checks, and the !,
{status}, {graphics}, and {vital} modifiers. The status and
graphics windows answer as the reference's own "cheap" mode
answers -- empty, a stream keeps no grid -- and everything the
reference accepts that this runner does not fails loudly rather
than passing differently. Game paths are read exactly as the
reference reads them, relative to the working directory, so one
script means one thing under both runners; the seed rides the
`** interpreter:` line as a --seed argument, which both runners
carry faithfully.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from voxam.acceptance import replay
from voxam.errors import RegTestError, VoxamError
from voxam.frontend import PlainFrontend
from voxam.zmachine.machine import Machine
from voxam.zmachine.story import Story

# The check kinds, named as the reference names its classes -- the
# failure report speaks the same voice under both runners.
LITERAL = "LiteralCheck"
PATTERN = "RegExpCheck"
COUNTED = "LiteralCountCheck"

# A long check text is shortened in the report, as the reference
# shortens it.
SHOWN_LIMIT = 32

# The keys a {char} command may name, translated to the §3.8 input
# characters this machine hears: the cursor keys as their §3.8.4
# codes, return as the empty line the keystroke seam spends as
# ZSCII 13, and the function keys as codes 133 to 144. Keys with no
# ZSCII to mean -- tab, home, the page keys -- fail loudly.
KEY_CHARACTERS = {
    "up": "\x81",
    "down": "\x82",
    "left": "\x83",
    "right": "\x84",
    "return": "",
    "delete": "\x7f",
    "escape": "\x1b",
    **{f"func{number}": chr(0x84 + number) for number in range(1, 13)},
}

# Test names beginning with a dash or underscore are hidden: the
# reference's default pattern skips them, and so does this runner.
HIDDEN_PREFIXES = ("-", "_")

_MODIFIER = re.compile(r"!|\{[a-z]*\}")
_COMMAND_KIND = re.compile(r"\{([a-z_]*)\}")
_COUNT_PREFIX = re.compile(r"\{count=([0-9]+)\}")


@dataclass(frozen=True)
class Check:
    """One assertion against a command's output window.

    Attributes:
        kind: LiteralCheck, RegExpCheck, or LiteralCountCheck.
        text: The literal or pattern sought.
        line: The script line the check came from, for the report.
        count: The least number of occurrences a counted literal
            demands.
        inverse: Whether the sense is reversed (the ! modifier).
        in_status: Whether the check reads the status window.
        in_graphics: Whether the check reads the graphics window.
        vital: Whether a failure ends the test ({vital}).
    """

    kind: str
    text: str
    line: int
    count: int = 1
    inverse: bool = False
    in_status: bool = False
    in_graphics: bool = False
    vital: bool = False


@dataclass(frozen=True)
class Step:
    """One typed input and the checks on its response."""

    send: str
    checks: tuple[Check, ...] = ()


@dataclass(frozen=True)
class Test:
    """One named test: opening checks, then steps."""

    name: str
    opening: tuple[Check, ...]
    steps: tuple[Step, ...]


@dataclass(frozen=True)
class Script:
    """One parsed RegTest file."""

    game: Path
    seed: int | None
    precommands: tuple[str, ...]
    tests: tuple[Test, ...]


@dataclass
class _Building:
    """A test under construction, checks flowing to the right sink."""

    name: str
    opening: list[Check] = field(default_factory=list)
    steps: list[Step] = field(default_factory=list)

    def check(self, check: Check) -> None:
        if not self.steps:
            self.opening.append(check)

            return

        last = self.steps[-1]
        self.steps[-1] = Step(last.send, (*last.checks, check))

    def built(self) -> Test:
        return Test(self.name, tuple(self.opening), tuple(self.steps))


def parse_script(path: Path) -> Script:
    """Read a RegTest file (regtest.html: Test Format).

    Raises:
        RegTestError: For anything the reference would refuse --
            an unknown ** option, modifier, or command type, a
            duplicated test name, a script naming no game -- and
            for reference features this runner does not carry.
        OSError: If the file cannot be read.
    """

    game: Path | None = None
    seed: int | None = None
    precommands: list[str] = []
    tests: list[Test] = []
    names: set[str] = set()
    building: _Building | None = None

    for number, raw in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        line = raw.strip()

        if not line or line.startswith("#"):
            continue

        if line.startswith("**"):
            game, seed = _directive(
                line[2:],
                number,
                building=building,
                precommands=precommands,
                game=game,
                seed=seed,
            )
        elif line.startswith("*"):
            if building is not None:
                tests.append(building.built())

            name = line[1:].strip()

            if name in names:
                msg = f"line {number}: test name used twice: {name}"

                raise RegTestError(msg)

            names.add(name)
            building = _Building(name)
        elif line.startswith(">"):
            if building is None:
                msg = f"line {number}: a command arrived before any * test"

                raise RegTestError(msg)

            building.steps.append(Step(_sent(line[1:].strip(), number)))
        else:
            if building is None:
                msg = f"line {number}: a check arrived before any * test"

                raise RegTestError(msg)

            building.check(_check(line, number))

    if building is not None:
        tests.append(building.built())

    if game is None:
        msg = f"{path.name} names no game; add '** game: <story file>'"

        raise RegTestError(msg)

    return Script(game, seed, tuple(precommands), tuple(tests))


def run_script(script: Script, report: Callable[[str], None]) -> int:
    """Run every visible test, in the reference's own voice.

    Args:
        script: The parsed script.
        report: Receives each test banner and failure line.

    Returns:
        The total number of failed checks and errors.
    """

    errors = 0
    performed = 0

    for test in script.tests:
        if test.name.startswith(HIDDEN_PREFIXES):
            continue

        performed += 1

        report(f"* {test.name}")

        errors += _run_test(script, test, report)

    if not performed:
        report("No tests performed!")

    return errors


class _VitalCheckError(Exception):
    """A {vital} check failed: the current test ends here."""


def _run_test(script: Script, test: Test, report: Callable[[str], None]) -> int:
    """One test on a fresh machine; every response window judged."""

    steps = tuple(Step(send) for send in script.precommands) + test.steps
    pieces: list[str] = []
    errors = 0
    last_typed = -1

    def judge(index: int) -> None:
        nonlocal errors

        window = "".join(pieces).split("\n")
        checks = test.opening if index == 0 else steps[index - 1].checks

        for check in checks:
            failure = _evaluated(check, window)

            if failure is not None:
                errors += 1

                report(f"{_described(check)}: {failure}")

                if check.vital:
                    raise _VitalCheckError

        pieces.clear()

    def typed(index: int) -> None:
        nonlocal last_typed

        judge(index)

        last_typed = index

    source = replay((step.send for step in steps), echo=lambda _text: None, typed=typed)

    try:
        machine = Machine(
            Story.load(script.game),
            PlainFrontend(pieces.append),
            input_source=source,
            seed=script.seed,
        )

        machine.run()
        judge(last_typed + 1)
    except EOFError:
        judge(last_typed + 1)
    except _VitalCheckError:
        pass
    except (OSError, VoxamError) as error:
        # The reference logs a failed test and carries on to the
        # next; an unreadable game or a machine halt is one error.
        errors += 1

        report(f"{type(error).__name__}: {error}")

    return errors


def _directive(  # noqa: PLR0913 -- the parser's whole state passes through
    body: str,
    number: int,
    *,
    building: "_Building | None",
    precommands: list[str],
    game: Path | None,
    seed: int | None,
) -> tuple[Path | None, int | None]:
    """One ** option line; a colonless one is skipped, faithfully.

    Raises:
        RegTestError: For options the reference refuses, and for
            reference options this runner does not carry --
            per-test overrides, checkclass, remformat.
    """

    key, separator, value = body.partition(":")

    if not separator:
        return game, seed

    key = key.strip()
    value = value.strip()

    if building is not None:
        msg = f"line {number}: per-test ** {key} overrides are not supported here"

        raise RegTestError(msg)

    if key == "game":
        return Path(value), seed

    if key == "interpreter":
        return game, _seed_among(value.split(), number)

    if key in ("pre", "precommand"):
        precommands.append(_sent(value, number))

        return game, seed

    msg = f"line {number}: ** {key} is not supported by this runner"

    raise RegTestError(msg)


def _seed_among(arguments: list[str], number: int) -> int | None:
    """The --seed value on an interpreter line, if one rides there.

    The reference passes interpreter arguments through untouched;
    this runner reads the one that matters to determinism and
    ignores the rest, so a script can be replayable under both.
    """

    for position, argument in enumerate(arguments):
        if argument != "--seed":
            continue

        try:
            return int(arguments[position + 1])
        except (IndexError, ValueError):
            msg = f"line {number}: --seed on the interpreter line names no number"

            raise RegTestError(msg) from None

    return None


def _sent(text: str, number: int) -> str:
    """A command line as the input seam will speak it.

    A plain line passes through; a {char} command becomes the
    single character the keystroke queue spends as one press, the
    return key travelling as the empty line. Command types beyond
    line and char belong to the reference's RemGlk mode and fail
    loudly here.

    Raises:
        RegTestError: For an unsupported command type or a key
            with no §3.8 character to mean.
    """

    match = _COMMAND_KIND.match(text)

    if match is None:
        return text.strip()

    kind = match.group(1)
    rest = text[match.end() :].strip()

    if kind == "line":
        return rest

    if kind != "char":
        msg = f"line {number}: {{{kind}}} commands are not supported by this runner"

        raise RegTestError(msg)

    return _pressed(rest, number)


def _pressed(rest: str, number: int) -> str:
    """The single character a {char} command presses.

    Raises:
        RegTestError: For a key with no §3.8 character to mean.
    """

    if len(rest) <= 1:
        return rest

    lowered = rest.lower()

    if lowered == "space":
        return " "

    if lowered in KEY_CHARACTERS:
        return KEY_CHARACTERS[lowered]

    source = rest[2:] if lowered.startswith("0x") else rest
    base = 16 if lowered.startswith("0x") else 10

    try:
        return chr(int(source, base))
    except ValueError:
        msg = f"line {number}: cannot press {rest!r}"

        raise RegTestError(msg) from None


def _check(body: str, number: int) -> Check:
    """One check line: modifiers peeled, then the check itself.

    Raises:
        RegTestError: For a modifier the reference does not name.
    """

    inverse = False
    in_status = False
    in_graphics = False
    vital = False

    while True:
        match = _MODIFIER.match(body)

        if match is None:
            break

        prefix = match.group()
        body = body[match.end() :].strip()

        if prefix in ("!", "{invert}"):
            inverse = True
        elif prefix == "{status}":
            in_status = True
        elif prefix in ("{graphic}", "{graphics}"):
            in_graphics = True
        elif prefix == "{vital}":
            vital = True
        else:
            msg = f"line {number}: unknown test modifier: {prefix}"

            raise RegTestError(msg)

    counted = _COUNT_PREFIX.match(body)

    if body.startswith("/"):
        kind, text, count = PATTERN, body[1:].strip(), 1
    elif counted is not None:
        kind, text, count = (
            COUNTED,
            body[counted.end() :].strip(),
            int(counted.group(1)),
        )
    else:
        kind, text, count = LITERAL, body, 1

    return Check(
        kind,
        text,
        number,
        count=count,
        inverse=inverse,
        in_status=in_status,
        in_graphics=in_graphics,
        vital=vital,
    )


def _evaluated(check: Check, lines: list[str]) -> str | None:
    """Judge one check against a window; None passes.

    The status and graphics windows are empty, exactly as the
    reference's cheap mode keeps them: a stream has no grid.
    """

    window = [] if check.in_status or check.in_graphics else lines

    if check.kind == PATTERN:
        failure = (
            None if any(re.search(check.text, line) for line in window) else "not found"
        )
    elif check.kind == COUNTED:
        failure = _counted(check, window)
    else:
        failure = None if any(check.text in line for line in window) else "not found"

    if check.inverse:
        return None if failure is not None else "inverse test should fail"

    return failure


def _counted(check: Check, window: list[str]) -> str | None:
    """Tally a counted literal the way the reference tallies.

    Occurrences may overlap, and the tally stops at enough.
    """

    counter = 0

    for line in window:
        start = 0

        while True:
            position = line.find(check.text, start)

            if position < 0:
                break

            counter += 1
            start = position + 1

            if counter >= check.count:
                return None

    if counter == 0:
        return "not found"

    return f"only found {counter} times"


def _described(check: Check) -> str:
    """The check as the reference's report shows it."""

    text = check.text

    if len(text) > SHOWN_LIMIT:
        text = text[:SHOWN_LIMIT] + "..."

    detail = f"{{count={check.count}}} " if check.kind == COUNTED else ""
    flags = "!" if check.inverse else ""

    if check.in_status:
        flags += "{status}"

    if check.in_graphics:
        flags += "{graphics}"

    return f'<{check.kind}:{check.line} {detail}{flags}"{text}">'
