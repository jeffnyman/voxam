"""Command-line interface for Voxam."""

import argparse
from collections.abc import Sequence
from pathlib import Path

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
    arguments = parser.parse_args(argv)

    print("\nVoxam Interpreter for Z-Machine and Glulx\n")

    if arguments.story is None:
        return EXIT_OK

    try:
        story = Story.load(arguments.story)
    except (OSError, VoxamError) as error:
        print(f"voxam: {error}")

        return EXIT_UNUSABLE

    header = story.header
    print(
        f"Running {arguments.story.name}: release {header.release}, "
        f"serial {header.serial_number} (z{header.version})\n"
    )

    try:
        Machine(story).run()
    except ZMachineUnimplementedError as error:
        print(f"\nvoxam: {error}")

        return EXIT_FRONTIER
    except VoxamError as error:
        print(f"\nvoxam: {error}")

        return EXIT_UNUSABLE

    print()

    return EXIT_OK
