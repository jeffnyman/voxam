"""Acceptance scripts: recorded sessions the CLI can replay.

A script is a plain text file of typed commands plus a few
directives, most importantly which game to run and which seed to
roll with. The Standard itself suggests the technique: a seeded
generator is "useful for testing entire scripts" (§2.4 remarks).

The grammar, line by line:

    ! KEY=VALUE      a directive: GAME names the story file, SEED
                     makes the session reproducible
    # ...            a comment
    ```              a fence: toggles skipping of whole sections
    > command        a typed command, transcript style
    command          the same, without the prompt sugar
    (blank)          skipped

An inline comment starts at whitespace followed by #. A command that
must genuinely begin with # or ! can be written with the > prefix,
which is otherwise optional. A > alone types an empty line.

Everything between a pair of fences is skipped raw, directives
included; text after the backticks labels the fence and is ignored.
An unclosed fence skips the rest of the file, which makes "replay
only up to here" a one-line edit.
"""

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Self

from voxam.errors import AcceptanceError

COMMENT = "#"
DIRECTIVE = "!"
PROMPT = ">"
FENCE = "```"

_INLINE_COMMENT = re.compile(r"\s+#")


@dataclass(frozen=True)
class AcceptanceScript:
    """One recorded session: a game, a seed, and the typed commands.

    Attributes:
        game: The story file the session plays.
        seed: The session seed, or None for true entropy.
        commands: The typed lines, in order.
        lines: Each command's line number in the script file, in the
            same order -- so a warning can point at the file.
    """

    game: Path
    seed: int | None
    commands: tuple[str, ...]
    lines: tuple[int, ...]

    @classmethod
    def parse(cls, path: Path) -> Self:
        """Read an acceptance script file.

        Args:
            path: The script's location.

        Returns:
            The parsed script.

        Raises:
            AcceptanceError: On an unknown or malformed directive, an
                unusable seed, or a script that names no game.
            OSError: If the file cannot be read.
        """

        game: Path | None = None
        seed: int | None = None
        commands: list[str] = []
        numbers: list[int] = []
        fenced = False
        lines = path.read_text(encoding="utf-8").splitlines()

        for number, raw in enumerate(lines, start=1):
            line = raw.strip()

            if line.startswith(FENCE):
                fenced = not fenced
                continue

            if fenced or not line or line.startswith(COMMENT):
                continue

            if line.startswith(DIRECTIVE):
                key, value = _directive(line, number)

                if key == "SEED":
                    seed = _seed(value, number)
                elif key == "GAME":
                    game = _game_path(path, value)
                else:
                    msg = f"line {number}: unknown directive {key}"

                    raise AcceptanceError(msg)
            else:
                commands.append(_command(line))
                numbers.append(number)

        if game is None:
            msg = f"{path.name} names no game; add '! GAME=<story file>'"

            raise AcceptanceError(msg)

        return cls(game=game, seed=seed, commands=tuple(commands), lines=tuple(numbers))


def replay(
    commands: Iterable[str],
    echo: Callable[[str], object],
    exhausted: Callable[[], str] | None = None,
    typed: Callable[[int], None] | None = None,
) -> Callable[[], str]:
    """Build an input source typing the commands, then handing over.

    Args:
        commands: The lines to type, in order.
        echo: Receives each command as it is typed, newline included,
            so the session transcript shows what was entered at each
            prompt. Its return value is ignored, so a raw stream
            write serves.
        exhausted: Where input comes from once the script runs out.
            None means the session ends there, as at end of input;
            the interactive terminal instead makes the script a
            catch-up that leaves the player at the prompt. Handed-off
            lines are not echoed: a terminal shows typing itself.
        typed: Told each command's position, zero-based, just before
            it is typed -- which is also the moment the previous
            command's response is complete. A RefusalWatch listens
            here.

    Returns:
        An input source for a Machine.
    """

    iterator = enumerate(commands)

    def _next_command() -> str:
        try:
            index, command = next(iterator)
        except StopIteration:
            if exhausted is None:
                raise EOFError from None

            return exhausted()

        if typed is not None:
            typed(index)

        echo(command + "\n")

        return command

    return _next_command


# The parser's refusal dialect: responses meaning a typed command did
# not do what it said. A replay marches straight past them -- this is
# how a statuette stays in its chest and a Weasel skips his meeting
# -- so the watch turns each into a loud warning instead. Curated
# from the Infocom house parser and the Inform library; matching is
# case-insensitive, and the list grows by experience. A refusal LEADS
# its line: prose that merely contains the words -- Seastalker's
# standing "Okay, Jeff, what do you want to do now?" prompt -- stays
# unremarked. "That's not a verb I recogni" is truncated on purpose:
# Inform spells the next letters -ise or -ize depending on the
# game's dialect, and a prefix match covers both.
REFUSAL_OPENINGS = (
    "I beg your pardon",
    "I didn't understand that sentence",
    "I don't know the word",
    "I only understood you as far as",
    "It's not clear what you're referring to",
    "That sentence isn't one I recognize",
    "That's not a verb I recogni",
    "There was no verb in that sentence",
    "What do you want",
    "You can't do that",
    "You can't go that way",
    "You can't quite reach",
    "You can't see any",
    "You must use a verb",
    "You should close it first",
    "You should open it first",
    "Your load is too heavy",
)

# Disambiguation questions bury their tell mid-line -- "Which door
# do you mean..." -- so this family is sought anywhere in the line.
REFUSAL_TELLS = ("do you mean",)


def refusal_in(response: str) -> str | None:
    """Find the first line of a response spoken in the refusal dialect.

    Args:
        response: Everything a story printed in reply to one command.

    Returns:
        The offending line of the response, stripped, or None when
        the response contains no known refusal.
    """

    for line in response.splitlines():
        candidate = line.strip()

        # AMFV brackets its parser messages -- [I don't know the word
        # "bloody".] -- so the anchor looks past a leading bracket.
        lowered = candidate.lower().removeprefix("[")

        opens = any(lowered.startswith(p.lower()) for p in REFUSAL_OPENINGS)
        tells = any(t in lowered for t in REFUSAL_TELLS)

        if opens or tells:
            return candidate

    return None


class RefusalWatch:
    """Reads a replayed conversation for silently refused commands.

    The response to a command is everything the story prints before
    the next command is typed. The watch collects that output, and
    when the response speaks the refusal dialect it warns with the
    command and its line in the script file -- at recording time,
    not forty turns later when the missing side effect surfaces.
    """

    def __init__(self, script: AcceptanceScript, warn: Callable[[str], None]) -> None:
        """Bind the script being replayed and a warning sink.

        Args:
            script: The parsed script, for commands and line numbers.
            warn: Receives one message per refused command.
        """

        self._script = script
        self._warn = warn
        self._pieces: list[str] = []
        self._awaiting: int | None = None

    def saw(self, text: str) -> None:
        """Collect story output as the response in progress."""

        self._pieces.append(text)

    def typed(self, index: int) -> None:
        """Judge the previous response; start collecting the next."""

        self._judge()

        self._awaiting = index
        self._pieces.clear()

    def finish(self) -> None:
        """Judge the final command's response, ending the watch."""

        self._judge()

        self._awaiting = None
        self._pieces.clear()

    def _judge(self) -> None:
        """Warn if the collected response refused its command."""

        if self._awaiting is None:
            return

        offense = refusal_in("".join(self._pieces))

        if offense is not None:
            line = self._script.lines[self._awaiting]
            command = self._script.commands[self._awaiting]

            self._warn(f"line {line}: {command!r} looks refused: {offense.strip()}")


def _game_path(script: Path, value: str) -> Path:
    """Resolve GAME against the script's own directory.

    A relative game path means "from where this script lives", so a
    script replays identically whatever directory it is run from.
    Absolute paths pass through. Forward slashes work everywhere.
    """

    game = Path(value)

    return game if game.is_absolute() else script.parent / game


def _directive(line: str, number: int) -> tuple[str, str]:
    """Split a directive line into its key and value."""

    body = line[len(DIRECTIVE) :].strip()
    key, separator, value = body.partition("=")

    if not separator or not key.strip():
        msg = f"line {number}: a directive is '! KEY=VALUE', not {line!r}"

        raise AcceptanceError(msg)

    return key.strip().upper(), value.strip()


def _seed(value: str, number: int) -> int:
    """Read a SEED directive's value as a number."""

    try:
        return int(value)
    except ValueError:
        msg = f"line {number}: the seed {value!r} is not a number"

        raise AcceptanceError(msg) from None


def _command(line: str) -> str:
    """Reduce a command line to what the player would have typed.

    The optional > prefix is dropped; a command starting with # after
    the prefix is taken verbatim, which is the escape for the rare
    command that begins with a marker character.
    """

    if line.startswith(PROMPT):
        rest = line[len(PROMPT) :].lstrip()

        if rest.startswith(COMMENT):
            return rest

        return _uncommented(rest)

    return _uncommented(line)


def _uncommented(line: str) -> str:
    """Cut an inline comment: whitespace followed by #."""

    return _INLINE_COMMENT.split(line, maxsplit=1)[0].rstrip()
