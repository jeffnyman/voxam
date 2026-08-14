"""Command-line interface for Voxam."""

import argparse
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from voxam.acceptance import AcceptanceScript, RefusalWatch, replay
from voxam.errors import VoxamError, ZMachineUnimplementedError
from voxam.frontend import Frontend, PlainFrontend
from voxam.saves import FileSaveSlot
from voxam.zmachine.machine import Identity, Machine
from voxam.zmachine.story import Story

if TYPE_CHECKING:
    from voxam.painter import ScreenFrontend

# Exit codes: 0 for a story that ran to quit, 1 for halting at a not
# yet implemented opcode, 2 for a file that could not be run at all.
EXIT_OK = 0
EXIT_FRONTIER = 1
EXIT_UNUSABLE = 2


def main(argv: Sequence[str] | None = None) -> int:
    """Run the Voxam command line.

    Args:
        argv: Command-line arguments; None means the process's own.

    Returns:
        The process exit code.
    """

    parser = argparse.ArgumentParser(
        prog="voxam",
        description="An interpreter for Z-Machine (and, one day, Glulx) stories.",
    )
    parser.add_argument(
        "story",
        nargs="?",
        type=Path,
        help="a story file to run; omit to just show the banner",
    )
    parser.add_argument(
        "--seed",
        type=int,
        help="seed the dice for a reproducible session",
    )
    parser.add_argument(
        "--accept",
        type=Path,
        help="replay an acceptance script instead of playing interactively",
    )
    parser.add_argument(
        "--replay",
        type=Path,
        help="replay an acceptance script, then keep playing at the prompt",
    )
    parser.add_argument(
        "--plain",
        action="store_true",
        help="keep the plain stream frontend even at a terminal",
    )
    parser.add_argument(
        "--interpreter",
        help="claim a §11.1.3 platform, by name (amiga, ibm-pc, ...) or number",
    )
    parser.add_argument(
        "--tandy",
        action="store_true",
        help="set the legendary Tandy bit for version 3 games (§11.1.4)",
    )
    arguments = parser.parse_args(argv)

    print("\nVoxam Interpreter for Z-Machine and Glulx\n")

    if arguments.accept is not None and arguments.replay is not None:
        print("voxam: --accept and --replay are one script apiece; pick one")

        return EXIT_UNUSABLE

    try:
        identity = _identity(arguments.interpreter, tandy=arguments.tandy)
    except ValueError as error:
        print(f"voxam: {error}")

        return EXIT_UNUSABLE

    script_path = arguments.accept if arguments.accept is not None else arguments.replay

    if script_path is not None:
        return _replay_script(
            script_path,
            arguments.story,
            arguments.seed,
            handoff=arguments.replay is not None,
            identity=identity,
        )

    if arguments.story is None:
        return EXIT_OK

    return _play(
        arguments.story,
        arguments.seed,
        None,
        screen=not arguments.plain,
        identity=identity,
    )


def _replay_script(
    script_path: Path,
    story: Path | None,
    seed_override: int | None,
    *,
    handoff: bool,
    identity: Identity | None = None,
) -> int:
    """Replay an acceptance script; --seed beats the script's seed.

    With handoff, the exhausted script yields to the interactive
    terminal instead of ending the session.
    """

    if story is not None:
        print("voxam: an acceptance script names its own game; drop the story")

        return EXIT_UNUSABLE

    try:
        script = AcceptanceScript.parse(script_path)
    except (OSError, VoxamError) as error:
        print(f"voxam: {error}")

        return EXIT_UNUSABLE

    seed = seed_override if seed_override is not None else script.seed
    watch = RefusalWatch(script, warn=lambda message: print(f"voxam: {message}"))

    def tee(text: str) -> None:
        sys.stdout.write(text)
        watch.saw(text)

    # At handoff the last scripted response is complete; the watch is
    # closed there so live typing is never blamed on the script.
    def handed_off() -> str:
        watch.finish()

        return input()

    source = replay(
        script.commands,
        sys.stdout.write,
        exhausted=handed_off if handoff else None,
        typed=watch.typed,
    )

    code = _play(script.game, seed, source, PlainFrontend(tee), identity=identity)
    watch.finish()

    return code


# The §11.1.3 interpreter numbers, by the names Infocom used.
INTERPRETER_NUMBERS = {
    "dec-20": 1,
    "apple-iie": 2,
    "macintosh": 3,
    "amiga": 4,
    "atari-st": 5,
    "ibm-pc": 6,
    "commodore-128": 7,
    "commodore-64": 8,
    "apple-iic": 9,
    "apple-iigs": 10,
    "tandy-color": 11,
}


def _identity(interpreter: str | None, *, tandy: bool) -> Identity | None:
    """Build the claimed identity from the command line.

    Args:
        interpreter: A §11.1.3 platform name or number, or None
            for Voxam's default introduction.
        tandy: Whether the legendary Tandy bit is requested.

    Returns:
        The identity to claim, or None when nothing was asked.

    Raises:
        ValueError: For an interpreter that is neither a known
            name nor a number.
    """

    if interpreter is None and not tandy:
        return None

    number: int | None = None

    if interpreter is not None:
        lowered = interpreter.lower()

        if lowered in INTERPRETER_NUMBERS:
            number = INTERPRETER_NUMBERS[lowered]
        elif interpreter.isdigit():
            number = int(interpreter)
        else:
            names = ", ".join(sorted(INTERPRETER_NUMBERS))
            msg = (
                f"unknown interpreter {interpreter!r}; use a number or one of: {names}"
            )

            raise ValueError(msg)

    return Identity(interpreter=number, tandy=tandy)


def _screen_frontend(version: int) -> "ScreenFrontend | None":
    """A painted frontend, when the glass and the extra allow.

    The screen frontend wants a real terminal to paint on and the
    blessed package the `screen` extra installs; missing either,
    the caller falls back to the plain stream, which is always
    there.
    """

    if not sys.stdout.isatty():
        return None

    try:
        # Imported here because the blessed extra is optional: the
        # plain stream must keep working without it.
        from voxam.painter import ScreenFrontend  # noqa: PLC0415
    except ImportError:
        return None

    return ScreenFrontend(version)


def _play(  # noqa: PLR0913 -- one knob per session seam
    story_path: Path,
    seed: int | None,
    input_source: Callable[[], str] | None,
    frontend: Frontend | None = None,
    *,
    screen: bool = False,
    identity: Identity | None = None,
) -> int:
    """Load and run one story, mapping outcomes to exit codes.

    With screen requested, a painted frontend is used when the
    terminal is real and the blessed extra is installed; otherwise
    play falls back to the plain stream.
    """

    try:
        story = Story.load(story_path)
    except (OSError, VoxamError) as error:
        print(f"voxam: {error}")

        return EXIT_UNUSABLE

    header = story.header
    key_source: Callable[[float | None], str | None] | None = None

    if frontend is None and screen:
        painted = _screen_frontend(header.version)

        if painted is not None:
            frontend = painted
            input_source = painted.read_line
            key_source = painted.read_key

    print(
        f"Running {story_path.name}: release {header.release}, "
        f"serial {header.serial_number} (z{header.version})\n"
    )

    # Saved games live beside the story: zork1.z3 saves to zork1.sav.
    saves = FileSaveSlot(story_path.with_suffix(".sav"))

    try:
        Machine(
            story,
            frontend,
            input_source=input_source,
            seed=seed,
            saves=saves,
            key_source=key_source,
            identity=identity,
        ).run()
    except EOFError:
        print("\nvoxam: end of input")

        return EXIT_OK
    except ZMachineUnimplementedError as error:
        print(f"\nvoxam: {error}")

        return EXIT_FRONTIER
    except VoxamError as error:
        print(f"\nvoxam: {error}")

        return EXIT_UNUSABLE

    print()

    return EXIT_OK
