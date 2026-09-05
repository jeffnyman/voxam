"""Compare two interpreters' Treaty of Babel reports, story by story.

A transcript is long enough that certifying a port against the
reference means comparing a corpus of recorded playthroughs. The
treaty's report is a small fixed block, so this sweep is not a sample
of the corpus but the whole of it: every story either machine can
play, reported by both and compared byte for byte.

    uv run python tools/sweep-babel.py --other csharp/publish/voxam

The Å-machine's stories are left out. The treaty's rule for them is
the reference's alone, and the port that this certifies does not run
Dialog at all.

The corpus is an optional submodule. Without it there is nothing to
sweep, and that is not a failure: the sweep says so and exits clean.
"""

import argparse
import subprocess
import sys
from pathlib import Path

# The repository this file lives in, whoever checked it out.
ROOT = Path(__file__).resolve().parents[1]

# What one report may take before the sweep gives up on it. A report
# reads a header and prints a handful of lines, so this is generous
# by a wide margin and only ever catches a hang.
TIMEOUT = 60

# The story shapes both machines open. The .aastory files in the
# corpus are the reference's alone.
BLORBS = (".blb", ".blorb", ".zblorb", ".gblorb")
BARE_Z = tuple(f".z{n}" for n in range(1, 9))
BARE_GLULX = (".ulx",)
SHARED = (*BLORBS, *BARE_Z, *BARE_GLULX)

# Where the corpus keeps the stories, minus the Dialog folder.
FOLDERS = (
    "entharion/zcode-infocom",
    "entharion/zcode-inform",
    "entharion/glulx-code",
    "entharion/zcode-checkers",
    "entharion/glulx-checkers",
)

# RegTest's contract, which the corpus sweep keeps too, so a script
# can gate on the answer: nothing differed, something did, or the
# question could not be asked.
EXIT_SAME = 0
EXIT_DIFFERENT = 1
EXIT_UNUSABLE = 2


def stories() -> list[Path]:
    """Every story in the corpus both machines can be asked about."""

    found = [
        held
        for folder in FOLDERS
        for held in sorted((ROOT / folder).glob("*"))
        if held.suffix.lower() in SHARED
    ]

    return sorted(found)


def invocation(named: str) -> list[str]:
    """One interpreter's command, its executable resolved.

    An interpreter named by a relative path is resolved against this
    checkout before it is run. Windows will not start a relative path
    written with forward slashes, and the sweep runs from the
    repository root whatever directory it was called from, so a bare
    `csharp/publish/voxam` has to be made absolute either way.
    """

    pieces = named.split()
    first = Path(pieces[0])

    for candidate in (first, ROOT / first):
        if candidate.is_file():
            return [str(candidate.resolve()), *pieces[1:]]

    return pieces


def reported(command: list[str], story: Path) -> str | None:
    """One interpreter's report for one story; None if it would not run."""

    try:
        finished = subprocess.run(  # noqa: S603 -- the interpreters are the runner's own
            [*command, str(story.relative_to(ROOT).as_posix())],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
            timeout=TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError) as error:
        print(f"voxam: {' '.join(command)} would not run: {error}")

        return None

    return finished.stdout


def main(argv: list[str] | None = None) -> int:
    """Sweep the corpus; the exit code says whether anything differed."""

    parser = argparse.ArgumentParser(
        prog="sweep-babel",
        description="compare two interpreters' --babel reports over the corpus",
    )
    parser.add_argument(
        "--voxam",
        default="uv run voxam",
        help="the reference interpreter (default: %(default)s)",
    )
    parser.add_argument(
        "--other",
        required=True,
        help="the interpreter to certify against it",
    )
    arguments = parser.parse_args(argv)

    found = stories()

    if not found:
        print("voxam: the corpus submodule is empty; nothing to sweep")

        return EXIT_SAME

    reference = [*invocation(arguments.voxam), "--babel"]
    other = [*invocation(arguments.other), "--babel"]
    differing: list[Path] = []

    for story in found:
        said = reported(reference, story)
        answered = reported(other, story)

        if said is None or answered is None:
            return EXIT_UNUSABLE

        if said != answered:
            differing.append(story)
            print(f"\n{story.relative_to(ROOT).as_posix()} differs:")
            print(f"  reference: {said!r}")
            print(f"  other    : {answered!r}")

    print(f"\n{len(found)} compared, {len(differing)} differing")

    return EXIT_DIFFERENT if differing else EXIT_SAME


if __name__ == "__main__":
    sys.exit(main())
