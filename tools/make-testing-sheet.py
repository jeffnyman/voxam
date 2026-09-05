"""Generate the manual testing sheet from the corpus itself.

Every story Voxam will actually open, each with the faces a tester
can paste: the reference's five, and the C# port's three where the
port plays that story at all. What counts as a story is decided by
Voxam's own readers rather than by a file extension, so a
resource-only blorb sitting beside its story is left out instead of
listed as a game that refuses to start.

Run it from anywhere; the repository is found from this file's own
place in it, and the corpus from the submodule beside it:

    uv run python tools/make-testing-sheet.py
    uv run python tools/make-testing-sheet.py ../elsewhere.md

Unasked, it writes VOXAM-MANUAL-TESTS.md into the directory it was
run from.
"""

import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from voxam.aamachine.story import Story
from voxam.babel import ifiction, ifid
from voxam.blorb import Blorb
from voxam.errors import VoxamError
from voxam.infocom import title as infocom_title

# The repository this file lives in, whoever checked it out and
# wherever they put it.
ROOT = Path(__file__).resolve().parents[1]

BLORBS = (".blb", ".blorb", ".zblorb", ".gblorb")
BARE_Z = tuple(f".z{n}" for n in range(1, 9))
BARE_GLULX = (".ulx",)
AASTORY = ".aastory"
PLAYABLE = (*BLORBS, *BARE_Z, *BARE_GLULX, AASTORY)

# The screen model that plays on the §8.8 stage, which is the one
# version whose wire needs a word the others do not.
STAGE_VERSION = 6

# What the sheet is called when the runner does not say.
DEFAULT_SHEET = "VOXAM-MANUAL-TESTS.md"

FOLDERS = [
    ("entharion/zcode-infocom", "Infocom's catalog", "The Z-Machine"),
    ("entharion/zcode-inform", "Inform and the moderns", "The Z-Machine"),
    ("entharion/glulx-code", "Glulx stories", "Glulx"),
    ("entharion/dialog-code", "Dialog stories", "The Å-machine"),
    ("entharion/zcode-checkers", "Z-Machine checkers", "The checkers"),
    ("entharion/glulx-checkers", "Glulx checkers", "The checkers"),
]

FACES = ["", "--plain ", "--graphics ", "--web ", "--glkote "]

# The port's own faces. It carries no pygame window and no wire, by
# design: GlkOte and the sidecar are the reference's alone. What it
# has instead is a window of its own, which is a separate binary
# rather than a flag.
PORT_CONSOLE = ["", "--plain "]
PORT_BINARY = "csharp/publish/voxam"
PORT_WINDOW = "csharp/publish-desktop/Voxam"

# The Å-machine is the reference's alone; the port carries the
# Z-Machine and Glulx.
PORTED = (*BLORBS, *BARE_Z, *BARE_GLULX)

# One story as the sheet describes it: where it lives, its Z
# version where it has one, and the name it answers to.
Described = tuple[Path, int | None, str | None]


def storied(path: Path) -> tuple[bool, int | None, str | None]:
    """Whether Voxam opens this file, its Z version, and its title.

    A blorb that packages no story is not a story: it's the
    sidecar of the one beside it, and listing it would send a
    tester to a refusal that is working as designed.
    """

    record = None

    try:
        if path.suffix.lower() in BLORBS:
            blorb = Blorb.load(path)
            data = blorb.glulx if blorb.glulx is not None else blorb.story

            if data is None:
                return (False, None, None)

            if blorb.ifiction is not None:
                record = ifiction(blorb.ifiction)
        else:
            data = path.read_bytes()
    except (OSError, VoxamError):
        return (False, None, None)

    named = record.title if record is not None and record.title else None

    if named is None:
        named = infocom_title(ifid(data))

    version = data[0] if data[:4] != b"Glul" and data else None

    return (True, version, named)


def aastoried(path: Path) -> tuple[bool, int | None, str | None]:
    """The Å-machine's own read, for a .aastory."""

    try:
        story = Story(path.read_bytes())
    except (OSError, VoxamError):
        return (False, None, None)

    return (True, None, story.meta.get("title"))


def described(path: Path) -> tuple[bool, int | None, str | None]:
    """One file read by whichever machine claims its extension."""

    if path.suffix.lower() == AASTORY:
        return aastoried(path)

    return storied(path)


def gathered(folder: str) -> list[Described]:
    """Every story in one corpus folder, in name order.

    A folder that is not there at all answers empty rather than
    raising: the corpus is an optional submodule, and a checkout
    without it should still produce a sheet that says so.
    """

    directory = ROOT / folder

    if not directory.is_dir():
        return []

    entries: list[Described] = []

    for held in sorted(directory.iterdir()):
        if not held.is_file() or held.suffix.lower() not in PLAYABLE:
            continue

        plays, version, title = described(held)

        if plays:
            entries.append((held, version, title))

    return entries


def stamped() -> tuple[str, str]:
    """The release this sheet was cut from, and its commit.

    Git is asked by resolved path rather than by name, and a
    checkout with no git at all is stamped "unknown" rather than
    failing: a sheet is worth having either way.
    """

    found = shutil.which("git")

    if found is None:
        return ("unknown", "unknown")

    def asked(*words: str) -> str:
        answer = subprocess.run(  # noqa: S603 -- git, resolved, with fixed words
            [found, "-C", str(ROOT), *words],
            capture_output=True,
            text=True,
            check=False,
        )

        return answer.stdout.strip() or "unknown"

    return (
        asked("describe", "--tags", "--always"),
        asked("rev-parse", "--short", "HEAD"),
    )


def staged(folder: str, held: Path) -> list[str]:
    """The Version 6 note: the one face that needs a word first."""

    return [
        "\nVersion 6 draws on the §8.8 stage. Every painted face plays "
        "it, but the wire refuses a display that has not said the "
        "stage's own word, so the generic init above earns `the display "
        "never learned the stage` rather than an update. Grant it:\n",
        "\n```bash\n",
        'echo \'{"type":"init","gen":0,"support":'
        '["timer","graphics","graphicswin","stage"],'
        '"metrics":{"width":80,"height":24}}\' \\\n',
        f"  | uv run voxam --glkote {folder}/{held.name}\n",
        "```\n",
    ]


def besides(held: Path) -> list[str]:
    """The note for a story whose art rides in a sidecar."""

    sidecar = next(
        (
            beside
            for beside in (held.with_suffix(suffix) for suffix in BLORBS)
            if beside.exists() and beside != held
        ),
        None,
    )

    if sidecar is None:
        return []

    return [
        f"\nArt rides beside it in `{sidecar.name}`, found by name "
        "without being asked for, so the pixel window and the browser "
        "should show pictures here.\n"
    ]


def blocked(folder: str, entry: Described) -> list[str]:
    """One story's whole section: its heading, notes, and commands."""

    held, version, title = entry
    mark = "Å-machine" if held.suffix.lower() == AASTORY else "Glulx"

    if version:
        mark = f"Version {version}"

    pieces = [f"\n#### {held.name}\n"]

    # A title only when the story or the catalog really says one:
    # the heading above is the filename, which names the game well
    # enough without a label invented here to fill the line.
    pieces.append(f"\n{title} — {mark}\n" if title else f"\n{mark}\n")

    if version == STAGE_VERSION:
        pieces += staged(folder, held)

    pieces += besides(held)
    pieces.append("\n```bash\n")
    pieces += [f"uv run voxam {flag}{folder}/{held.name}\n" for flag in FACES]
    pieces.append("```\n")
    pieces += ported(folder, held)

    return pieces


def ported(folder: str, held: Path) -> list[str]:
    """The same story at the port, where the port can play it.

    The plain stream is left out of the interesting part on purpose:
    the sweep already compares it against the reference transcript by
    transcript, so a tester adds nothing by reading it again. What no
    transcript can check is the painted console and the window, which
    is what these lines are for.
    """

    if held.suffix.lower() not in PORTED:
        return []

    return [
        "\nAnd at the port:\n",
        "\n```bash\n",
        *[f"{PORT_BINARY} {flag}{folder}/{held.name}\n" for flag in PORT_CONSOLE],
        f"{PORT_WINDOW} {folder}/{held.name}\n",
        "```\n",
    ]


def bodied(counts: list[tuple[str, int, int]]) -> list[str]:
    """Every folder's stories, sectioned by machine family.

    The counts list is filled as the walk goes, so the preamble's
    table and the body cannot disagree about what was found. Each
    entry carries how many of that folder's stories the port plays as
    well, which is all of them outside the Dialog corpus.
    """

    pieces: list[str] = []
    heading = None

    for folder, label, family in FOLDERS:
        entries = gathered(folder)

        if not entries:
            continue

        counts.append(
            (
                label,
                len(entries),
                sum(1 for held, _, _ in entries if held.suffix.lower() in PORTED),
            )
        )

        if family != heading:
            pieces.append(f"\n## {family}\n")
            heading = family

        pieces.append(f"\n### {label}\n")
        pieces.append(f"\n{len(entries)} stories in `{folder}`.\n")

        for entry in entries:
            pieces += blocked(folder, entry)

    return pieces


def opened(
    total: int, ported_total: int, counts: list[tuple[str, int, int]]
) -> list[str]:
    """The preamble: how to run this, and what the faces are."""

    version, commit = stamped()
    stamp = datetime.now(UTC).date().isoformat()
    commands = total * len(FACES) + ported_total * (len(PORT_CONSOLE) + 1)
    pieces = [
        "# Voxam manual testing sheet\n",
        f"\nGenerated {stamp} from `{version}` (`{commit}`), against the "
        "corpus in the `entharion` submodule. Regenerate it whenever the "
        "submodule pin moves; nothing here is written by hand.\n",
        f"\n**{total} stories at the reference's five faces, and "
        f"{ported_total} of them at the port's three: {commands} commands "
        "in all.** Nobody is expected to run them all. Take a folder, take "
        "a face, or take the handful you touched.\n",
        "\n## Before you start\n",
        "\nRun everything from the repository root, so `uv run` finds the "
        "working tree rather than an installed copy:\n",
        "\n```bash\ncd /path/to/voxam\n```\n",
        "\nThe corpus lives in an optional submodule. If `entharion/` is "
        "empty, none of this works:\n",
        "\n```bash\ngit submodule update --init --recursive\n```\n",
        "\nTwo faces need an extra, and say so plainly if it is missing:\n",
        "\n```bash\nuv sync --extra screen --extra graphics --extra sound\n```\n",
        "\n### The port has to be built first\n",
        "\nThe C# port is not installed; it is compiled. Both binaries "
        "publish through NativeAOT, and the paths in this sheet are where "
        "these two commands put them:\n",
        "\n```bash\n"
        "dotnet publish csharp/Voxam.Cli -c Release -o csharp/publish\n"
        "dotnet publish csharp/Voxam.Desktop -c Release -o csharp/publish-desktop\n"
        "```\n",
        "\nNativeAOT cannot cross-compile between operating systems, so "
        "each platform builds its own. On Windows add `.exe` to both "
        "paths, or let the shell find them without it.\n",
        "\n## What the five faces are\n",
        "\n| command | face | what to look at |\n"
        "|---|---|---|\n"
        "| `uv run voxam STORY` | painted terminal | the status line, "
        "cursor placement, colours, and that a resize redraws |\n"
        "| `uv run voxam --plain STORY` | plain stream | the words alone; "
        "this is the machine-readable face and carries no furniture |\n"
        "| `uv run voxam --graphics STORY` | pixel window | art, the "
        "§8.8 stage, themes, and the window's own title |\n"
        "| `uv run voxam --web STORY` | browser tab | type, ink, the "
        "preferences panel, the iFiction Card button, sound |\n"
        "| `uv run voxam --glkote STORY` | the wire | JSON stanzas, one "
        "to a line, both ways |\n",
        "\n### The wire needs driving\n",
        "\n`--glkote` speaks the GlkOte protocol on stdin and stdout. Pasted "
        "on its own it looks hung: it is waiting for the display's `init` "
        "stanza, which a human is not going to type. To smoke-test it, hand "
        "it one and let the pipe close:\n",
        '\n```bash\necho \'{"type":"init","gen":0,'
        '"support":["timer"],"metrics":{"width":80,"height":24}}\' '
        "| uv run voxam --glkote STORY\n```\n",
        "\nOne update stanza back, then a clean exit, is the pass. The "
        "per-story lines below keep the bare form, so swap it in when you "
        "want the wire rather than a hung terminal.\n",
        "\n### What a refusal looks like\n",
        "\nVoxam refuses loudly and by name rather than failing quietly, so "
        "a message beginning `voxam:` is usually the design working. A "
        "Version 6 story at a plain stream, a story whose face cannot draw, "
        "an Å-machine story asked for an instrument it does not carry: "
        "all of these say what they will not do and why. What is worth "
        "filing is silence, a traceback, or a face that shows the wrong "
        "thing confidently.\n",
        "\n## What the port's three faces are\n",
        "\nThe port carries the Z-Machine and Glulx, so every story below "
        "except the Dialog ones gets these as well. It has no pygame "
        "window and no wire, by design: GlkOte and the sidecar are the "
        "reference's alone, and the port's window is a binary of its own "
        "rather than a flag.\n",
        "\n| command | face | what to look at |\n"
        "|---|---|---|\n"
        "| `csharp/publish/voxam STORY` | painted console | the same "
        "shape the reference's terminal has: status line, wrapped text, "
        "a pause prompt |\n"
        "| `csharp/publish/voxam --plain STORY` | plain stream | already "
        "compared to the reference transcript by transcript in the sweep, "
        "so read this one only when something else looks wrong |\n"
        "| `csharp/publish-desktop/Voxam STORY` | the window | the "
        "Version 6 stage, Glulx pictures, the pointer, themes and sizes |\n",
        "\n### What is worth a tester's time here\n",
        "\nThe plain stream is certified mechanically: "
        "`tools/sweep-corpus.py` replays all forty-five acceptance "
        "recordings on both and compares them byte for byte, and CI does "
        "one from each machine on every push. Reading it by hand adds "
        "nothing.\n",
        "\nWhat no transcript can check is what the painted faces draw. "
        "The console and the window are where a manual pass earns its "
        "keep: a status line in the wrong place, art that does not "
        "appear, a click that lands nowhere, a caret drawn past the edge "
        "of the glass.\n",
        "\n### What the port will not do\n",
        "\nSound. There is no speaker on the C# side, so it claims none "
        "and refuses the channels rather than pretending. A story that "
        "asks for sound plays silently and says so; that is the design "
        "and not a defect. Everything else Glk 0.7.6 defines is "
        "served.\n",
        "\n## The corpus\n",
        "\n| section | stories | at the port |\n|---|---:|---:|\n",
    ]

    pieces += [
        f"| {label} | {count} | {ported_count} |\n"
        for label, count, ported_count in counts
    ]
    pieces.append(f"| **total** | **{total}** | **{ported_total}** |\n")

    return pieces


def sheet() -> str:
    """The whole sheet, body walked first so the counts are real."""

    counts: list[tuple[str, int, int]] = []
    body = bodied(counts)
    total = sum(count for _, count, _ in counts)
    ported_total = sum(count for _, _, count in counts)

    return "".join(opened(total, ported_total, counts)) + "".join(body)


def main(argv: list[str]) -> int:
    """Write the sheet where asked, or under its own name here.

    The default lands in the working directory rather than beside
    the script or at the repository root: a generated document is
    the runner's to place, and writing it into someone's checkout
    uninvited is how a tool earns a .gitignore line instead of
    trust.
    """

    if len(argv) > 1:
        print(f"usage: make-testing-sheet.py [OUTPUT.md]  (default: {DEFAULT_SHEET})")

        return 2

    out = Path(argv[0]) if argv else Path(DEFAULT_SHEET)

    out.write_text(sheet(), encoding="utf-8", newline="\n")
    print(f"wrote {out} ({out.stat().st_size:,} bytes)")

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
