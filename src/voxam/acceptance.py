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
    <key>            a special key: <up> <down> <left> <right>
                     for the cursor keys, <escape> for the escape
                     key, <space> for the space bar -- one press
                     per line
    (blank)          skipped

An inline comment starts at whitespace followed by #. A command that
must genuinely begin with # or ! -- or look like a <key> -- can be
written with the > prefix, which is otherwise optional. A > alone
types an empty line: the enter key.

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

# The special keys a recording can press, one line each. The
# translated command is the key's own input character -- the §3.8.4
# cursor codes Beyond Zork's menus listen for, the §3.8.2.6 escape,
# and the space bar, which line-stripping would otherwise erase --
# Journey's menus move their highlight with it. The keystroke seam
# spends each as a single press; the enter key stays what it always
# was: a bare >.
KEY_TOKENS = {
    "<up>": "\x81",
    "<down>": "\x82",
    "<left>": "\x83",
    "<right>": "\x84",
    "<escape>": "\x1b",
    "<space>": " ",
}

# What the replay transcript shows for a pressed key: the token,
# never the raw control character, which a piped Windows console
# could not even encode.
KEY_ECHOES = {character: token for token, character in KEY_TOKENS.items()}


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
                pressed = _key_token(line, number)
                commands.append(pressed if pressed is not None else _command(line))
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

        echo(KEY_ECHOES.get(command, command) + "\n")

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
# game's dialect, and a prefix match covers both. The commented
# entries were each paid for by a 0.6.0 recording campaign: a
# refusal the watch could not yet speak, discovered forty turns
# later as a missing side effect. Every entry needs an earner --
# an observed refusal, or a message the house libraries document --
# because a guessed sibling collides with honest prose: a bare
# "You're not holding" was tried here and withdrawn the same hour,
# when Trinity's empty-inventory report turned out to open with it.
REFUSAL_OPENINGS = (
    "I beg your pardon",
    "I didn't understand that sentence",
    "I don't know the word",
    "I only understood you as far as",
    "It's not clear what you're referring to",
    "Nice try",  # The Lurking Horror: a bare hand in the vat
    "That sentence isn't one I recognize",
    "That's not a verb I recogni",
    "There was no verb in that sentence",
    "What do you want",
    "You are not holding",  # Sherlock: the rubbing that came up blank
    "You aren't holding that",  # the Inform library's spelling of it
    "You can't be serious",  # The Lurking Horror's flat disbelief
    "You can't do that",
    "You can't go that way",
    "You can't quite reach",
    "You can't see any",
    "You must use a verb",
    "You should close it first",
    "You should open it first",
    "You're holding too many",  # The Lurking Horror's carry ceiling
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


# The enter key, which the grammar spells as a bare prompt: an
# empty command line is one press of return (§3.8.2.1).
ENTER_KEYS = ("\n", "\r")


class Recorder:
    """Writes a live session as an acceptance script, as it happens.

    The inverse of parse(): every line the player types and every
    key they press is written in the grammar the replayer reads,
    flushed input by input, so a session that ends badly -- a
    death, a crash, a closed terminal -- still leaves a replayable
    script up to its last keystroke. What the grammar cannot spell
    exactly is warned about, never silently mangled.
    """

    def __init__(
        self, path: Path, game: Path, seed: int, warn: Callable[[str], None]
    ) -> None:
        """Open a fresh script and stamp its directives.

        Args:
            path: Where the script is written. An existing file is
                refused: a recording never overwrites one.
            game: The story file being played, written relative to
                the script when it can be, so the pair travels
                together.
            seed: The session's seed -- the directive that makes
                the recording replayable at all.
            warn: Receives one message per input that could not be
                written exactly.

        Raises:
            AcceptanceError: If the path already exists.
            OSError: If the file cannot be created.
        """

        if path.exists():
            msg = f"{path} already exists; a recording never overwrites"

            raise AcceptanceError(msg)

        self._warn = warn
        self._path = path
        self._expected = 0
        self._handle = path.open("w", encoding="utf-8", newline="\n")

        try:
            where = game.resolve().relative_to(path.resolve().parent, walk_up=True)
        except ValueError:
            # A story with no relative spelling -- another drive --
            # is named absolutely; the pair just cannot move.
            where = game.resolve()

        self._write(f"! GAME={where.as_posix()}")
        self._write(f"! SEED={seed}")
        self._write("")

    @classmethod
    def resumed(cls, path: Path, warn: Callable[[str], None]) -> "Recorder":
        """Reopen an existing script to record onto its end.

        The mirror of a fresh recording's refusal to overwrite: a
        resume requires the script to exist, keeps its directives
        and every verified line exactly as they were, and appends
        -- new input can only ever land at the end, which is the
        append-only discipline recordings live by.

        Args:
            path: The script being continued.
            warn: Receives one message per input that could not be
                written exactly.

        Raises:
            AcceptanceError: If the path does not exist.
            OSError: If the file cannot be opened.
        """

        if not path.exists():
            msg = f"{path} does not exist; a resume continues a recording"

            raise AcceptanceError(msg)

        recorder = cls.__new__(cls)
        recorder._warn = warn
        recorder._path = path
        recorder._expected = path.stat().st_size
        recorder._handle = path.open("a", encoding="utf-8", newline="\n")

        return recorder

    def line(self, text: str) -> None:
        """Record one whole typed line."""

        encoded = _scripted(text)
        replayed = _replays_as(encoded)

        if replayed != text:
            self._warn(
                f"recorded {text!r} will replay as {replayed!r}; "
                f"the script grammar cannot spell it exactly"
            )

        self._write(encoded)

    def key(self, character: str) -> None:
        """Record one pressed key."""

        if character in KEY_ECHOES:
            self._write(KEY_ECHOES[character])

            return

        if character in ENTER_KEYS:
            self._write(PROMPT)

            return

        if not character.isprintable():
            self._warn(
                f"key {ord(character)} has no token in the grammar; not recorded"
            )

            return

        self.line(character)

    def close(self) -> None:
        """Finish the script file."""

        self._handle.close()

    def _write(self, line: str) -> None:
        """Put one script line on disk, immediately.

        The recorder is the file's only legitimate writer while a
        session runs: an editor saving over it mid-session
        interleaves or discards appends, which is how a recording
        grows mystery gaps. A size that moved between writes earns
        a loud warning naming the moment -- the recording carries
        on, since ending a live session would lose even more.
        """

        if self._path.stat().st_size != self._expected:
            self._warn(
                f"{self._path} changed on disk mid-recording -- another "
                f"editor? -- and appends may interleave or be lost; the "
                f"file has one writer at a time"
            )

        self._handle.write(line + "\n")
        self._handle.flush()
        self._expected = self._path.stat().st_size


def _scripted(text: str) -> str:
    """Spell a typed line in the script grammar.

    Most lines are themselves. An empty line is the enter key, a
    bare prompt. A line the parser would read as something else --
    a comment, a directive, a fence, a key token, a prompt -- takes
    the literal-command prompt prefix.
    """

    if not text:
        return PROMPT

    marked = text.startswith((COMMENT, DIRECTIVE, PROMPT, FENCE))
    keyish = text.startswith("<") and text.endswith(">")

    return f"{PROMPT} {text}" if marked or keyish else text


def _replays_as(line: str) -> str:
    """What parse() will make of one written line: the round trip."""

    pressed = _key_token(line, 0)

    return pressed if pressed is not None else _command(line)


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


def _key_token(line: str, number: int) -> str | None:
    """Translate a <key> line into the character it presses.

    A line that is not shaped like a key token belongs to the
    command grammar instead; one that is shaped like a token but
    names no known key fails loudly -- a typo must not quietly
    type its letters into the game. The `> <key>` prompt form
    stays a literal command, the escape for a game that really
    wants angle brackets.

    Raises:
        AcceptanceError: For an angle-bracketed token naming no
            known key.
    """

    if not (line.startswith("<") and line.endswith(">")):
        return None

    token = line.lower()

    if token in KEY_TOKENS:
        return KEY_TOKENS[token]

    known = ", ".join(sorted(KEY_TOKENS))
    msg = f"line {number}: unknown key {line!r}; the keys are: {known}"

    raise AcceptanceError(msg)


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
