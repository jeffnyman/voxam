"""Replay every acceptance recording, and compare two sweeps.

The recordings under `acceptance/` are complete playthroughs of real
games, and they are the only net that exercises whole stories rather
than hand-built fixtures. They are seeded, so a given checkout answers
the same bytes every time: two sweeps that differ mean the machine's
behavior changed, deliberately or not.

    uv run python tools/sweep-corpus.py record before
    git checkout <other>
    uv run python tools/sweep-corpus.py record after
    uv run python tools/sweep-corpus.py compare before after

The comparison's exit codes are RegTest's contract, so a script can
gate on them: nothing changed, something changed, or the question
could not be asked.

The corpus is an optional submodule. Without it there's nothing to
sweep, and that's not a failure: `record` says so and exits clean.
"""

import argparse
import difflib
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

# The repository this file lives in, whoever checked it out. A
# sweep can be pointed at another checkout with --root, which is
# how a release is compared against the one before it: this tool
# need only exist in one of the two.
ROOT = Path(__file__).resolve().parents[1]

# What one script may take before the sweep gives up on it. Every
# recording but one finishes in seconds; Bronze is Inform 7 and runs
# roughly forty times the instructions per turn that Inform 6 does,
# so it needs --timeout raised on purpose rather than a default that
# makes everybody else wait for it.
DEFAULT_TIMEOUT = 120

# RegTest's contract, which --strip-diff already answers on.
EXIT_OK = 0
EXIT_DIFFERED = 1
EXIT_UNUSABLE = 2

MANIFEST = "manifest.json"

# The short sweep: seventeen recordings that between them execute
# every line of voxam the whole forty-five execute, and cover every
# story file version and both machines besides.
#
# The first fifteen are a greedy cover measured under coverage.py,
# one recording at a time: Arthur alone reaches 81% of the lines the
# corpus touches, because Version 6 drags in the stage, the graphics
# window and the sound path; Tiny House adds 15% more as Glulx, a
# separate machine entirely. Everything after those two is picking
# up scraps, and thirty recordings add no line at all.
#
# The last two are here on principle rather than measurement: the
# greedy set happened to miss Versions 2 and 7, and a smoke test
# that cannot open a version is worth more than one that shaves
# four seconds.
#
# What this list is NOT is a substitute for the whole corpus at
# release time. Line coverage says which code ran, never whether it
# answered correctly: the iFiction card was wrong for four releases
# with every line of its parser covered. Thirty recordings that add
# no new line can still each notice a different wrong sentence.
SMOKE = (
    "arthur-r74-s890714",  # z6: the stage, graphics, sound
    "tiny-house-r1-s100425",  # Glulx, in a gblorb
    "violet-r3-s081101",  # z8
    "journey-r83-s890706",  # z6: its own window layout
    "zork1-r2-sAS000C",  # z1, and 3.7.1's shift-locked dictionary
    "zugzwang-r2-s990710",  # z5
    "advent-r5-s961209-glulx",  # Glulx, bare .ulx rather than blorbed
    "lurkinghorror-r221-s870918",  # z3 with sound
    "shogun-r322-s890706",  # z6
    "curses-r16-s951024",  # z5, and a fenced recording
    "impossible-stairs-r3-s241006",  # z8
    "beyondzork-r57-s871221",  # z5 with the character screen
    "zork1-german-beta-r3-s880113",  # 3.8.5, non-ASCII input
    "bureaucracy-r116-s870602",  # z4
    "zork0-r393-s890714",  # z6
    "zork1-r15-sUG3AU5",  # z2, which the cover missed
    "custard-r1-s000314",  # z7, which the cover missed
)


def scripts(root: Path, *, subset: bool = False) -> list[Path]:
    """Every recording, in name order; empty without the corpus.

    A subset sweep takes the named short list instead, and insists
    on finding all of it: a recording renamed out from under the
    list should fail loudly rather than quietly shrink the net.

    Raises:
        LookupError: When a named recording is not in the corpus.
    """

    recordings = root / "acceptance"

    if not recordings.is_dir():
        return []

    if not subset:
        return sorted(recordings.glob("*.accept"))

    found = []

    for name in SMOKE:
        script = recordings / f"{name}.accept"

        if not script.is_file():
            msg = f"the short sweep names {name}, which is not in {recordings}"

            raise LookupError(msg)

        found.append(script)

    return sorted(found)


def replayed(script: Path, out: Path, timeout: int, root: Path) -> dict[str, Any]:
    """Replay one recording; its transcript and how it went.

    A run that times out keeps the transcript it earned, and is
    marked incomplete: a truncated walk is not evidence about a
    machine, and the comparison refuses to read it as any.
    """

    began = time.monotonic()
    complete = True
    # The swept checkout's own source goes first on the path, so a
    # sweep of an older tree runs that tree's machine rather than
    # the one this tool was installed beside. Only --version reads
    # the installed metadata, which stays whatever is installed.
    running = dict(os.environ)
    running["PYTHONPATH"] = str(root / "src")

    try:
        answer = subprocess.run(  # noqa: S603 -- this interpreter, fixed words
            [sys.executable, "-m", "voxam", "--accept", str(script)],
            capture_output=True,
            check=False,
            cwd=root,
            env=running,
            timeout=timeout,
        )
        told = answer.stdout + answer.stderr
        code = answer.returncode
    except subprocess.TimeoutExpired as expired:
        told = (expired.stdout or b"") + (expired.stderr or b"")
        code = -1
        complete = False

    seconds = time.monotonic() - began
    transcript = out / f"{script.stem}.txt"

    transcript.write_bytes(told)

    return {
        "name": script.stem,
        "seconds": round(seconds, 2),
        "exit": code,
        "complete": complete,
        "bytes": len(told),
        "digest": hashlib.sha256(told).hexdigest(),
    }


def stocked(root: Path) -> bool:
    """Whether the story corpus is actually fetched.

    The recordings are tracked in the repository; the games they
    name are not, and live in an optional submodule. A checkout
    without it holds forty-five walks and nothing to walk, so the
    directory being empty is the thing worth asking about, not the
    recordings being absent.
    """

    corpus = root / "entharion"

    return corpus.is_dir() and any(corpus.iterdir())


def recorded(out: Path, timeout: int, root: Path, *, subset: bool = False) -> int:
    """Replay the corpus into a directory, with a manifest."""

    found = scripts(root, subset=subset)

    if not found:
        print(f"no recordings under {root / 'acceptance'}; nothing to sweep")

        return EXIT_OK

    if not stocked(root):
        print(
            f"{len(found)} recordings, but no games: {root / 'entharion'} is "
            "an optional submodule and this checkout has not fetched it."
        )
        print("  git submodule update --init --recursive")

        return EXIT_OK

    out.mkdir(parents=True, exist_ok=True)

    entries: list[dict[str, Any]] = []

    for index, script in enumerate(found, start=1):
        print(f"[{index:>2}/{len(found)}] {script.stem}", flush=True)
        entries.append(replayed(script, out, timeout, root))

    (out / MANIFEST).write_text(
        json.dumps(
            {
                "timeout": timeout,
                "root": str(root),
                "subset": subset,
                "entries": entries,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )

    incomplete = [entry for entry in entries if not entry["complete"]]
    slowest = sorted(entries, key=lambda entry: entry["seconds"], reverse=True)[:5]

    print(f"\n{len(entries)} recordings into {out}")
    print("\nslowest:")

    for entry in slowest:
        print(f"  {entry['seconds']:>8.2f}s  {entry['name']}")

    if incomplete:
        print(f"\nincomplete at {timeout}s, and not comparable:")

        for entry in incomplete:
            print(f"  {entry['name']}")

        print("\n  raise --timeout to include them")

    # The smoke verdict. Every recording in this corpus exits zero
    # when it is well: a story that ends by quitting and one that
    # ends by running out of input both do. So a non-zero exit is a
    # crash, a refusal the walk did not expect, or a story that no
    # longer opens, and an incomplete run is a hang or a machine
    # gone slow enough to be worth someone's attention.
    faulted = [entry for entry in entries if entry["exit"] != 0]

    if faulted:
        print("\nrecordings that did not end well:")

        for entry in faulted:
            how = "timed out" if not entry["complete"] else f"exit {entry['exit']}"
            print(f"  {entry['name']}: {how}")

        return EXIT_DIFFERED

    return EXIT_OK


def loaded(directory: Path) -> dict[str, dict[str, Any]] | None:
    """One sweep's manifest, keyed by recording name."""

    manifest = directory / MANIFEST

    if not manifest.is_file():
        print(f"voxam: {manifest} is not a sweep directory")

        return None

    held: Any = json.loads(manifest.read_text(encoding="utf-8"))
    entries: list[dict[str, Any]] = held["entries"]

    return {entry["name"]: entry for entry in entries}


def parted(left: Path, right: Path) -> int:
    """Compare two sweeps; the verdict is RegTest's contract.

    Only recordings both sweeps ran to completion are compared. A
    recording that one side skipped, or that timed out on either,
    is reported and left out of the verdict, because a truncated
    transcript can only produce a difference that means nothing.
    """

    mine = loaded(left)
    theirs = loaded(right)

    if mine is None or theirs is None:
        return EXIT_UNUSABLE

    shared = sorted(set(mine) & set(theirs))
    only_left = sorted(set(mine) - set(theirs))
    only_right = sorted(set(theirs) - set(mine))
    skipped = [
        name
        for name in shared
        if not (mine[name]["complete"] and theirs[name]["complete"])
    ]
    compared = [name for name in shared if name not in skipped]
    differed = [
        name for name in compared if mine[name]["digest"] != theirs[name]["digest"]
    ]

    for names, why in ((only_left, left.name), (only_right, right.name)):
        if names:
            print(f"only in {why}: {', '.join(names)}")

    if skipped:
        print(f"not comparable (incomplete on one side): {', '.join(skipped)}")

    for name in differed:
        print(f"\ndiffers: {name}")

        for line in _differed(left / f"{name}.txt", right / f"{name}.txt"):
            print(f"  {line}")

    print(f"\n{len(compared)} compared, {len(differed)} differing")

    return EXIT_DIFFERED if differed else EXIT_OK


def _differed(mine: Path, theirs: Path, most: int = 12) -> list[str]:
    """The first handful of differing lines, as a unified diff."""

    left = mine.read_text(encoding="utf-8", errors="replace").splitlines()
    right = theirs.read_text(encoding="utf-8", errors="replace").splitlines()
    walked = difflib.unified_diff(left, right, lineterm="", n=0)
    lines = [line for line in walked if not line.startswith(("---", "+++"))]

    if len(lines) > most:
        return [*lines[:most], f"... and {len(lines) - most} more"]

    return lines


def main(argv: list[str]) -> int:
    """Record a sweep, or compare two of them."""

    parser = argparse.ArgumentParser(
        prog="sweep-corpus.py",
        description="Replay every acceptance recording, and compare sweeps.",
    )
    doing = parser.add_subparsers(dest="doing", required=True)

    keeping = doing.add_parser("record", help="replay the corpus into a directory")
    keeping.add_argument("out", type=Path, help="where the transcripts go")
    keeping.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help=f"seconds one recording may take (default {DEFAULT_TIMEOUT})",
    )
    keeping.add_argument(
        "--root",
        type=Path,
        default=ROOT,
        help="a checkout to sweep instead of this one, its own source run",
    )
    keeping.add_argument(
        "--subset",
        action="store_true",
        help=(
            f"the {len(SMOKE)} recordings that reach every line the whole "
            "corpus reaches, for a smoke test rather than a comparison"
        ),
    )

    against = doing.add_parser("compare", help="compare two sweep directories")
    against.add_argument("left", type=Path)
    against.add_argument("right", type=Path)

    asked = parser.parse_args(argv)

    if asked.doing == "record":
        timeout: int = asked.timeout
        out: Path = asked.out
        root: Path = asked.root.resolve()

        if not (root / "src" / "voxam").is_dir():
            print(f"voxam: {root} is not a Voxam checkout")

            return EXIT_UNUSABLE

        try:
            return recorded(out, timeout, root, subset=asked.subset)
        except LookupError as missing:
            print(f"voxam: {missing}")

            return EXIT_UNUSABLE

    left: Path = asked.left
    right: Path = asked.right

    return parted(left, right)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
