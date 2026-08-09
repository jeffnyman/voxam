"""Command-line interface for Voxam."""

import argparse
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from voxam.acceptance import AcceptanceScript, replay
from voxam.errors import VoxamError, ZMachineUnimplementedError
from voxam.zmachine.machine import Machine
from voxam.zmachine.story import Story

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
    arguments = parser.parse_args(argv)

    print("\nVoxam Interpreter for Z-Machine and Glulx\n")

    if arguments.accept is not None:
        return _replay_script(arguments.accept, arguments.story, arguments.seed)

    if arguments.story is None:
        return EXIT_OK

    return _play(arguments.story, arguments.seed, None)


def _replay_script(
    script_path: Path, story: Path | None, seed_override: int | None
) -> int:
    """Replay an acceptance script; --seed beats the script's seed."""

    if story is not None:
        print("voxam: an acceptance script names its own game; drop the story")

        return EXIT_UNUSABLE

    try:
        script = AcceptanceScript.parse(script_path)
    except (OSError, VoxamError) as error:
        print(f"voxam: {error}")

        return EXIT_UNUSABLE

    seed = seed_override if seed_override is not None else script.seed

    return _play(script.game, seed, replay(script.commands, sys.stdout.write))


def _play(
    story_path: Path, seed: int | None, input_source: Callable[[], str] | None
) -> int:
    """Load and run one story, mapping outcomes to exit codes."""

    try:
        story = Story.load(story_path)
    except (OSError, VoxamError) as error:
        print(f"voxam: {error}")

        return EXIT_UNUSABLE

    header = story.header
    print(
        f"Running {story_path.name}: release {header.release}, "
        f"serial {header.serial_number} (z{header.version})\n"
    )

    try:
        Machine(story, input_source=input_source, seed=seed).run()
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
