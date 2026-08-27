"""The web filmstrip: an acceptance walk photographed at the wire.

The walk drives the same Session the web face serves -- the exact
protocol truth a browser would receive -- collecting every update
stanza. The frames then render through the display's own shipped
glkote.js: a replay page is written beside the strip, and a
headless browser opens it once per frame, replaying the wire up
to that turn under virtual time and printing the pixels with its
own --screenshot. Nothing new is vendored: the page assets are
the package's, the browser is the player's.
"""

import importlib.resources
import json
import shutil
import subprocess
from pathlib import Path

from voxam.errors import GlkOteError
from voxam.glkote import Stanza
from voxam.png import decode
from voxam.web import Session
from voxam.zmachine.glkote import ZSCII_KEYS

# The init event the driver speaks: every dialect word granted,
# so the strip shows the fullest face the display can wear.
INIT: Stanza = {
    "type": "init",
    "gen": 0,
    "support": [
        "timer",
        "graphics",
        "graphicswin",
        "hyperlinks",
        "sound",
        "colors",
        "stage",
    ],
    "metrics": {
        "width": 1280,
        "height": 800,
        "gridcharwidth": 10,
        "gridcharheight": 20,
        "buffercharwidth": 10,
        "buffercharheight": 20,
    },
}

# How the browser is asked to render one frame: the display's own
# screenshot flags, virtual time running the replay's timeouts
# instantly.
BROWSER_FLAGS = (
    "--headless=new",
    "--disable-gpu",
    "--window-size=1280,900",
    "--virtual-time-budget=8000",
)

# Where a browser tends to live when PATH does not say: the names
# tried by which, then the standard Windows seats.
BROWSER_NAMES = ("chrome", "chromium", "google-chrome", "msedge")
BROWSER_SEATS = (
    Path("C:/Program Files/Google/Chrome/Application/chrome.exe"),
    Path("C:/Program Files (x86)/Google/Chrome/Application/chrome.exe"),
    Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"),
)

# A typed key on the wire, by the character the walk recorded --
# the inverse of the face's own table, so a walk's arrow lands as
# the display would have sent it.
KEY_NAMES = {character: name for name, character in ZSCII_KEYS.items()}

# The page files a strip's replay needs beside it, copied from the
# package so the strip renders with the shipped display, whole.
PAGE_ASSETS = ("glkote.js", "glkote.css", "jquery-1.12.4.min.js", "waiting.gif")

_REPLAY_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Voxam filmstrip</title>
<link rel="stylesheet" href="glkote.css" type="text/css">
<style type="text/css">
html, body { margin: 0; height: 100%; background: #444; }
#gameport { position: absolute; overflow: hidden; left: 50%;
  transform: translateX(-50%); width: 100%; max-width: 1280px;
  top: 0; bottom: 0; background: white; }
.Style_user1 { background: #333; color: #fff; }
.GridWindow { background: #333; color: #fff; }
.GridWindow .Style_user1 { background: #fff; color: #333; }
</style>
<script src="jquery-1.12.4.min.js"></script>
<script src="glkote.js"></script>
<script src="updates.js"></script>
<script>
/* Replay the wire up to ?upto=N, one update per beat; the beats
   run instantly under the browser's virtual time. */
var UPTO = Number(new URLSearchParams(location.search).get("upto")) || UPDATES.length;
var AT = 0;
function feed() {
  if (AT < UPTO && AT < UPDATES.length) {
    GlkOte.update(UPDATES[AT]);
    AT += 1;
    setTimeout(feed, 40);
  }
}
var Game = {
  accept: function(ev) {
    if (ev.type == 'init') { setTimeout(feed, 40); }
  }
};
</script>
</head>
<body onload="GlkOte.init();">
<div id="gameport">
<div id="windowport"></div>
<div id="loadingpane"><img src="waiting.gif" alt="LOADING"></div>
<div id="errorpane" style="display:none;"><div id="errorcontent">...</div></div>
</div>
</body>
</html>
"""


def walked(
    session: Session, commands: list[str]
) -> tuple[list[Stanza], list[int], str | None]:
    """Drive a walk through a session, collecting the wire whole.

    Each command becomes the event the standing input roster asks
    for -- a line for a line read, a spelled key for a keystroke
    read -- and a file prompt is answered with the cancel, as a
    replay owns no files. The marks say how many updates stand
    at each frame: mark zero is the boot screen, mark N the wire
    after N commands were answered.

    A walk that breaks mid-stride -- the session ends, or types
    into a wire asking for nothing -- keeps every frame it earned
    and says where it broke: a recording made at one face can
    diverge honestly at another, and the strip's whole purpose is
    showing such seams, not dying frameless at them.

    Raises:
        GlkOteError: When the wire answers an error stanza -- a
            broken session photographs nothing true.
    """

    updates = [_answered(session, INIT)]
    roster: dict[int, Stanza] = {}
    gen = 0

    def noted(update: Stanza) -> None:
        nonlocal gen

        gen = update.get("gen", gen)

        if "input" in update:
            roster.clear()
            roster.update({entry["id"]: entry for entry in update["input"]})

    noted(updates[0])

    marks = [len(updates)]

    for index, command in enumerate(commands):
        # A standing file prompt is cancelled before the walk
        # continues: the strip photographs play, not dialogs.
        while isinstance(updates[-1].get("specialinput"), dict):
            cancel: Stanza = {
                "type": "specialresponse",
                "gen": gen,
                "response": "fileref_prompt",
            }

            updates.append(_answered(session, cancel))
            noted(updates[-1])

        entry = next(
            (held for held in roster.values() if "type" in held),
            None,
        )

        if entry is None:
            note = (
                f"the walk broke at command {index + 1}: it types "
                f"{command!r}, but the wire asks for nothing"
            )

            return updates, marks, note

        if entry["type"] == "line":
            event = {
                "type": "line",
                "gen": gen,
                "window": entry["id"],
                "value": command,
            }
        else:
            event = {
                "type": "char",
                "gen": gen,
                "window": entry["id"],
                "value": KEY_NAMES.get(command, command),
            }

        updates.append(_answered(session, event))
        noted(updates[-1])
        marks.append(len(updates))

    return updates, marks, None


def _answered(session: Session, event: Stanza) -> Stanza:
    """One event through the session, its error stanzas made loud.

    Raises:
        GlkOteError: When the wire answers the protocol's error.
    """

    update = session.answer(event)

    if update.get("type") == "error":
        msg = f"the wire answered an error: {update.get('message')}"

        raise GlkOteError(msg)

    return update


def paged(directory: Path, updates: list[Stanza]) -> Path:
    """Write the strip's replay page and its assets; the page's path.

    The page renders with the shipped display files, copied whole
    so the strip stays reproducible after the package moves on.
    """

    directory.mkdir(parents=True, exist_ok=True)

    for name in PAGE_ASSETS:
        held = (importlib.resources.files("voxam") / "pages" / name).read_bytes()

        (directory / name).write_bytes(held)

    (directory / "updates.js").write_text(
        "var UPDATES = " + json.dumps(updates) + ";\n", encoding="utf-8"
    )

    page = directory / "replay.html"

    page.write_text(_REPLAY_PAGE, encoding="utf-8")

    return page


def browsed(named: str | None) -> Path | None:
    """The browser to photograph with, or None when none is found.

    A named path answers itself when it exists; an empty name
    means look -- PATH first, then the standard seats.
    """

    if named:
        path = Path(named)

        return path if path.exists() else None

    for name in BROWSER_NAMES:
        found = shutil.which(name)

        if found is not None:
            return Path(found)

    for seat in BROWSER_SEATS:
        if seat.exists():
            return seat

    return None


def shot(page: Path, directory: Path, marks: list[int], browser: Path) -> int:
    """Photograph every frame; how many frames the strip holds.

    One browser launch per frame: the page replays the wire up to
    the frame's mark under virtual time, and the browser's own
    screenshot flag prints the pixels.

    Raises:
        GlkOteError: When a frame's file never appears -- the
            browser refused, and a hole in the strip would read
            as a missing turn rather than a broken camera.
    """

    directory.mkdir(parents=True, exist_ok=True)

    for index, upto in enumerate(marks):
        frame = directory / f"turn-{index:04d}.png"

        subprocess.run(  # noqa: S603 -- the browser is the user's own
            [
                str(browser),
                *BROWSER_FLAGS,
                f"--screenshot={frame}",
                page.as_uri() + f"?upto={upto}",
            ],
            capture_output=True,
            check=False,
        )

        if not frame.exists():
            msg = f"the browser printed no frame at {frame}"

            raise GlkOteError(msg)

    return len(marks)


def parted(left: Path, right: Path) -> tuple[list[str], bool]:
    """Compare two filmstrips frame by frame, our decoder ruling.

    Same-named frames decode and compare pixel for pixel; frames
    only one strip holds are named; and the verdict line says
    where the strips part. The comparison belongs to the same
    decoder the strips' pictures rode out on, so the diff answers
    from pixel truth rather than file bytes -- two encoders'
    identical screens compare equal.

    Raises:
        GlkOteError: For a strip holding no frames at all.
        PNGError: For a frame the decoder cannot read.
    """

    held_left = _framed(left)
    held_right = _framed(right)
    lines: list[str] = []
    first: str | None = None
    differing = 0

    lonely = sorted(set(held_left) ^ set(held_right))

    for name in lonely:
        side = left if name in held_left else right

        lines.append(f"{name} stands only in {side}")

    shared = sorted(set(held_left) & set(held_right))

    for name in shared:
        told = _differed(left / name, right / name)

        if told is None:
            continue

        lines.append(told)

        differing += 1

        if first is None:
            first = name

    differs = bool(lonely) or differing > 0

    if not differs:
        lines.append(f"identical: {len(shared)} frames")
    else:
        start = first if first is not None else lonely[0]
        tail = f", {len(lonely)} unshared" if lonely else ""

        lines.append(
            f"the strips part at {start}: {differing} of {len(shared)} "
            f"shared frames differ{tail}"
        )

    return lines, differs


def _differed(mine: Path, theirs: Path) -> str | None:
    """How one frame pair differs, or None when it does not."""

    one = decode(mine.read_bytes())
    other = decode(theirs.read_bytes())

    if (one.width, one.height) != (other.width, other.height):
        return (
            f"{mine.name} differs: {one.width}x{one.height} against "
            f"{other.width}x{other.height}"
        )

    if one.rows == other.rows:
        return None

    changed = sum(
        1
        for row, other_row in zip(one.rows, other.rows, strict=True)
        for pixel, other_pixel in zip(row, other_row, strict=True)
        if pixel != other_pixel
    )

    return f"{mine.name} differs: {changed} of {one.width * one.height} pixels"


def _framed(strip: Path) -> set[str]:
    """The frame names a strip holds.

    Raises:
        GlkOteError: When the directory holds no frames -- an
            empty comparison would answer identical, dishonestly.
    """

    names = {held.name for held in strip.glob("*.png")}

    if not names:
        msg = f"no frames at {strip}"

        raise GlkOteError(msg)

    return names
