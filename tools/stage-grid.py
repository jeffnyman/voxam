"""Print the Version 6 stage's grid for an acceptance walk, and compare two.

The corpus sweep certifies a port against this interpreter through the
character faces, which say nothing about §8.8's stage: its eight
windows, their unit geometry, and the cells they plot. This asks that
question instead. The walk is the same, the geometry is the same, and
what comes out is the grid the stage holds when the walk ends.

    uv run python tools/stage-grid.py acceptance/arthur-r74-s890714.accept

With an executable that answers `--stage-grid SCRIPT` the way this one
does, the two grids are compared row for row, and the exit code is
RegTest's contract, so a script can gate on it: nothing differs,
something differs, or the question could not be asked.

    uv run python tools/stage-grid.py SCRIPT --voxam path/to/voxam

No window is opened. The frontend is the real one, driving a glass
that measures but never draws, because the grid being compared is the
model's own and a pixel is not needed to read it. The session is
driven, so the stage never pauses at [MORE]: a script is typing, and
there is nobody to press the key.
"""

import argparse
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from voxam import blorb as blorb_module
from voxam.acceptance import AcceptanceScript, replay
from voxam.gallery import Gallery
from voxam.glass import GraphicsFrontend
from voxam.zmachine.machine import Machine
from voxam.zmachine.story import Story

# The certification geometry, spelled the same on both sides and
# printed in the header, so a drift shows up as a difference rather
# than as a puzzle.
COLUMNS = 80
LINES = 24
UNIT_WIDTH = 11
UNIT_HEIGHT = 21

IDENTICAL = 0
DIFFERING = 1
UNUSABLE = 2


class Measuring:
    """A glass that measures but never draws (the Glass protocol)."""

    def __init__(self) -> None:
        """Take the certification geometry, in cells and in units."""

        self.columns = COLUMNS
        self.lines = LINES
        self.cell_width = UNIT_WIDTH
        self.cell_height = UNIT_HEIGHT

    def paint(self, *args: object, **kwargs: object) -> None:
        """Ignore a painted run."""

    def text(self, *args: object, **kwargs: object) -> None:
        """Ignore a drawn string."""

    def fill(self, *args: object, **kwargs: object) -> None:
        """Ignore a filled rectangle."""

    def shift(self, *args: object, **kwargs: object) -> None:
        """Ignore a slid rectangle."""

    def sample(self, line: int, column: int) -> tuple[int, int, int]:
        """Answer black for any pixel: no glass has been drawn on."""

        del line, column

        return (0, 0, 0)

    def present(self) -> None:
        """Ignore a flip."""

    def snapshot(self, path: str) -> None:
        """Ignore a snapshot request."""

        del path

    def entitle(self, title: str) -> None:
        """Ignore a title."""

        del title

    def key(self, timeout: float | None) -> str | None:
        """Answer no key: a driven walk types through the script."""

        del timeout

        return None

    def click(self) -> tuple[int, int] | None:
        """Answer no click."""

        return None

    def picture(self, rows: object) -> None:
        """Ignore a picture."""

        del rows

    def photograph(self, *args: object, **kwargs: object) -> None:
        """Ignore a photograph request."""

    def draw(self, *args: object, **kwargs: object) -> None:
        """Ignore a drawn image."""


def hanging(game: Path) -> Gallery | None:
    """The art beside a story, or None when no Blorb accompanies it.

    Args:
        game: The story file the walk plays.

    Returns:
        The gallery its resource file hangs, or None.
    """

    for suffix in (".blb", ".blorb", ".zblorb", ".gblorb"):
        beside = Path(game).with_suffix(suffix)

        if beside.is_file():
            return blorb_module.Blorb.load(beside).gallery()

    return None


def grid_here(script_path: Path, seed: int | None) -> str:
    """Replay a walk on this interpreter's stage and answer its grid.

    Args:
        script_path: The acceptance script to replay.
        seed: A seed overriding the script's own, or None to keep it.

    Returns:
        The header line and the stage's grid, one row per line.
    """

    script = AcceptanceScript.parse(script_path)
    story = Story(Path(script.game).read_bytes())
    frontend = GraphicsFrontend(
        story.header.version, Measuring(), gallery=hanging(script.game), driven=True
    )
    source = replay(script.commands, echo=frontend.write)
    machine = Machine(story, frontend, input_source=source, seed=seed or script.seed)
    try:
        machine.run()
    except EOFError:
        # The walk ends where its commands do, which is ordinary.
        pass
    except Exception as error:
        # How a walk ends is worth saying, but it is each
        # interpreter's own voice and no part of the grid, so it keeps
        # off the output being compared.
        sys.stderr.write(f"# ended: {error}\n")

    header = f"# stage {COLUMNS}x{LINES} units {UNIT_WIDTH}x{UNIT_HEIGHT}\n"

    return header + frontend.model.rendered() + "\n"


def grid_there(voxam: Path, script_path: Path, seed: int | None) -> str:
    """Ask another interpreter for the same grid.

    Args:
        voxam: An executable answering `--stage-grid SCRIPT`.
        script_path: The acceptance script to replay.
        seed: A seed overriding the script's own, or None to keep it.

    Returns:
        Its standard output, verbatim.

    Raises:
        SystemExit: If the executable refuses or cannot be run.
    """

    command = [str(voxam), "--stage-grid", str(script_path)]

    if seed is not None:
        command += ["--seed", str(seed)]

    try:
        finished = subprocess.run(command, capture_output=True, check=False)  # noqa: S603
    except OSError as error:
        sys.stderr.write(f"voxam: {voxam} could not be run: {error}\n")

        raise SystemExit(UNUSABLE) from error

    if finished.returncode != 0:
        sys.stderr.write(finished.stderr.decode("utf-8", "replace"))

        raise SystemExit(UNUSABLE)

    return finished.stdout.decode("utf-8", "replace").replace("\r\n", "\n")


def parted(reference: str, port: str) -> int:
    """Compare two grids row for row and report where they part.

    Args:
        reference: This interpreter's grid.
        port: The other interpreter's grid.

    Returns:
        RegTest's exit code: identical, or differing.
    """

    left = reference.split("\n")
    right = port.split("\n")

    if left == right:
        print(f"{len(left) - 1} rows, identical")

        return IDENTICAL

    for number, (mine, theirs) in enumerate(zip(left, right, strict=False), start=1):
        if mine != theirs:
            print(f"row {number} differs")
            print(f"  reference: {mine!r}")
            print(f"  port:      {theirs!r}")

    if len(left) != len(right):
        print(f"the grids are {len(left)} rows and {len(right)} rows")

    return DIFFERING


def main(argv: Sequence[str] | None = None) -> int:
    """Print one grid, or compare two.

    Args:
        argv: The command line, or None for the process's own.

    Returns:
        The process exit code.
    """

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("script", type=Path, help="the acceptance script to replay")
    parser.add_argument(
        "--voxam",
        type=Path,
        help="an interpreter answering --stage-grid, compared against this one",
    )
    parser.add_argument("--seed", type=int, help="override the script's own seed")
    arguments = parser.parse_args(argv)

    if not arguments.script.is_file():
        sys.stderr.write(f"voxam: {arguments.script} is not an acceptance script\n")

        return UNUSABLE

    reference = grid_here(arguments.script, arguments.seed)

    if arguments.voxam is None:
        sys.stdout.write(reference)

        return IDENTICAL

    return parted(
        reference, grid_there(arguments.voxam, arguments.script, arguments.seed)
    )


if __name__ == "__main__":
    raise SystemExit(main())
