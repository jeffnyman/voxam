"""Acceptance scripts: recorded sessions the CLI can replay.

A script is a plain text file of typed commands plus a few
directives, most importantly which game to run and which seed to
roll with. The Standard itself suggests the technique: a seeded
generator is "useful for testing entire scripts" (§2.4 remarks).

The grammar, line by line:

    ! KEY=VALUE      a directive: GAME names the story file, SEED
                     makes the session reproducible
    # ...            a comment
    > command        a typed command, transcript style
    command          the same, without the prompt sugar
    (blank)          skipped

An inline comment starts at whitespace followed by #. A command that
must genuinely begin with # or ! can be written with the > prefix,
which is otherwise optional. A > alone types an empty line.
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

_INLINE_COMMENT = re.compile(r"\s+#")


@dataclass(frozen=True)
class AcceptanceScript:
    """One recorded session: a game, a seed, and the typed commands.

    Attributes:
        game: The story file the session plays.
        seed: The session seed, or None for true entropy.
        commands: The typed lines, in order.
    """

    game: Path
    seed: int | None
    commands: tuple[str, ...]

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
        lines = path.read_text(encoding="utf-8").splitlines()

        for number, raw in enumerate(lines, start=1):
            line = raw.strip()

            if not line or line.startswith(COMMENT):
                continue

            if line.startswith(DIRECTIVE):
                key, value = _directive(line, number)

                if key == "SEED":
                    seed = _seed(value, number)
                elif key == "GAME":
                    game = Path(value)
                else:
                    msg = f"line {number}: unknown directive {key}"

                    raise AcceptanceError(msg)
            else:
                commands.append(_command(line))

        if game is None:
            msg = f"{path.name} names no game; add '! GAME=<story file>'"

            raise AcceptanceError(msg)

        return cls(game=game, seed=seed, commands=tuple(commands))


def replay(commands: Iterable[str], echo: Callable[[str], object]) -> Callable[[], str]:
    """Build an input source typing the commands, then signalling EOF.

    Args:
        commands: The lines to type, in order.
        echo: Receives each command as it is typed, newline included,
            so the session transcript shows what was entered at each
            prompt. Its return value is ignored, so a raw stream
            write serves.

    Returns:
        An input source for a Machine.
    """

    iterator = iter(commands)

    def _next_command() -> str:
        try:
            command = next(iterator)
        except StopIteration:
            raise EOFError from None

        echo(command + "\n")

        return command

    return _next_command


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
