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
from voxam.zmachine.machine import Machine
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
    arguments = parser.parse_args(argv)

    print("\nVoxam Interpreter for Z-Machine and Glulx\n")

    if arguments.accept is not None and arguments.replay is not None:
        print("voxam: --accept and --replay are one script apiece; pick one")

        return EXIT_UNUSABLE

    script_path = arguments.accept if arguments.accept is not None else arguments.replay

    if script_path is not None:
        return _replay_script(
            script_path,
            arguments.story,
            arguments.seed,
            handoff=arguments.replay is not None,
        )

    if arguments.story is None:
        return EXIT_OK

    return _play(arguments.story, arguments.seed, None, screen=not arguments.plain)


def _replay_script(
    script_path: Path,
    story: Path | None,
    seed_override: int | None,
    *,
    handoff: bool,
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

    code = _play(script.game, seed, source, PlainFrontend(tee))
    watch.finish()

    return code


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


def _play(
    story_path: Path,
    seed: int | None,
    input_source: Callable[[], str] | None,
    frontend: Frontend | None = None,
    *,
    screen: bool = False,
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

    if frontend is None and screen:
        painted = _screen_frontend(header.version)

        if painted is not None:
            frontend = painted
            input_source = painted.read_line
    print(
        f"Running {story_path.name}: release {header.release}, "
        f"serial {header.serial_number} (z{header.version})\n"
    )

    # Saved games live beside the story: zork1.z3 saves to zork1.sav.
    saves = FileSaveSlot(story_path.with_suffix(".sav"))

    try:
        Machine(
            story, frontend, input_source=input_source, seed=seed, saves=saves
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
