"""The browser face: one session served over HTTP, turn by turn."""

import json
import re
import threading
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import pytest
from assertpy import assert_that

import voxam
from voxam.blorb import Blorb
from voxam.glulx.glk.resources import Resources
from voxam.glulx.story import Story
from voxam.iff import chunk
from voxam.web import Face, GlulxSession, ZSession, serve_web, webbed
from voxam.zmachine.story import Story as ZStory

PAGES = Path(__file__).resolve().parents[1] / "src" / "voxam" / "pages"

RIDX_ENTRY = 12
FORM_PRELUDE = 12

# The suspension story from the machine tests: open a buffer, ask
# for a keystroke, select, quit on the far side of the resume.
AWAITS_KEY = (
    bytes([0xC0, 0x00, 0x00])
    + bytes([0x40, 0x81, 0x00])
    + bytes([0x40, 0x81, 0x03])
    + bytes([0x40, 0x81, 0x00])
    + bytes([0x40, 0x81, 0x00])
    + bytes([0x40, 0x81, 0x00])
    + bytes([0x81, 0x30, 0x11, 0x06, 0x23, 0x05, 0x01, 0x40])
    + bytes([0x40, 0x86, 0x01, 0x40])
    + bytes([0x81, 0x30, 0x12, 0x00, 0x00, 0xD2, 0x01])
    + bytes([0x40, 0x82, 0x01, 0xC0])
    + bytes([0x81, 0x30, 0x12, 0x00, 0x00, 0xC0, 0x01])
    + bytes([0x81, 0x20])
)

INIT = {
    "type": "init",
    "gen": 0,
    "support": ["timer", "graphicswin", "hyperlinks"],
    "metrics": {"width": 80, "height": 24},
}


def glulx_image(code: bytes = AWAITS_KEY) -> bytes:
    """A tiny valid Glulx image, checksummed."""

    data = bytearray(0x200)
    data[0:4] = b"Glul"
    data[4:8] = (0x00030102).to_bytes(4, "big")
    data[8:12] = (0x100).to_bytes(4, "big")
    data[12:16] = (0x200).to_bytes(4, "big")
    data[16:20] = (0x300).to_bytes(4, "big")
    data[20:24] = (0x100).to_bytes(4, "big")
    data[24:28] = (0x48).to_bytes(4, "big")
    data[0x48 : 0x48 + len(code)] = code
    checksum = sum(
        int.from_bytes(data[at : at + 4], "big") for at in range(0, len(data), 4)
    )
    data[32:36] = (checksum % (1 << 32)).to_bytes(4, "big")

    return bytes(data)


def png(width: int, height: int) -> bytes:
    return (
        b"\x89PNG\r\n\x1a\n"
        + (13).to_bytes(4, "big")
        + b"IHDR"
        + width.to_bytes(4, "big")
        + height.to_bytes(4, "big")
    )


def jpeg(width: int, height: int) -> bytes:
    return (
        b"\xff\xd8"
        + b"\xff\xc0\x00\x08\x08"
        + height.to_bytes(2, "big")
        + width.to_bytes(2, "big")
    )


def pictured() -> Resources:
    """Resources holding one PNG, one JPEG, and one placeholder."""

    entries = (
        (b"Pict", 1, b"PNG ", png(2, 2)),
        (b"Pict", 2, b"JPEG", jpeg(4, 4)),
        (b"Pict", 3, b"Rect", bytes(8)),
    )
    index = len(entries).to_bytes(4, "big")
    body = b""
    ridx = chunk(b"RIdx", index + b"\x00" * RIDX_ENTRY * len(entries))
    offset = FORM_PRELUDE + len(ridx)

    for usage, number, chunk_id, payload in entries:
        index += usage + number.to_bytes(4, "big") + offset.to_bytes(4, "big")
        framed = chunk(chunk_id, payload)
        body += framed
        offset += len(framed)

    return Resources(
        Blorb.parse(chunk(b"FORM", b"IFRS" + chunk(b"RIdx", index) + body))
    )


def faced(caption: str | None = "Sensory Jam — Voxam") -> Face:
    """A Face over a fresh session of the keystroke story."""

    return Face(GlulxSession(Story(glulx_image()), pictured(), seed=7), caption)


def posted(face: Face, stanza: dict[str, Any] | str | bytes) -> dict[str, Any]:
    """One POST /event through the Face, the answer parsed back."""

    body = (
        stanza
        if isinstance(stanza, bytes)
        else (stanza if isinstance(stanza, str) else json.dumps(stanza)).encode("utf-8")
    )
    status, kind, payload = face.respond("POST", "/event", body)

    assert_that(status).is_equal_to(200)
    assert_that(kind).is_equal_to("application/json")

    answer: dict[str, Any] = json.loads(payload)

    return answer


# The page arrives wearing the story's own name -- and the plain
# Voxam name when no record or catalog could offer one.
def test_the_page_wears_the_story_name() -> None:
    status, kind, payload = faced().respond("GET", "/", b"")
    page = payload.decode("utf-8")

    assert_that(status).is_equal_to(200)
    assert_that(kind).is_equal_to("text/html; charset=utf-8")
    assert_that(page).contains("<title>Sensory Jam — Voxam</title>")
    assert_that(page).does_not_contain("VOXAM_TITLE")

    _, _, unnamed = faced(caption=None).respond("GET", "/", b"")

    assert_that(unnamed.decode("utf-8")).contains("<title>Voxam</title>")


# The page carries its own preferences panel: the shared script
# that builds it, an html attribute the CSS keys off, a dark
# palette behind prefers-color-scheme, and the pre-paint script
# that wears the kept choices before the first frame.
def test_the_page_carries_a_preferences_panel() -> None:
    face = faced()
    _, _, payload = face.respond("GET", "/", b"")
    page = payload.decode("utf-8")

    assert_that(page).contains('<html lang="en" data-theme="system">')
    assert_that(page).contains('<script src="voxam-prefs.js"')
    assert_that(page).contains("@media (prefers-color-scheme: dark)")
    assert_that(page).contains('localStorage.getItem("voxam-display")')
    assert_that(page).contains('localStorage.setItem("voxam-display"')

    # The ink alone was kept under its own key before the panel
    # existed, and a reader who chose one keeps it.
    assert_that(page).contains('localStorage.getItem("voxam-theme")')

    # Every named ink needs a palette to wear, and one that never
    # reached the stylesheet would read as the default on every
    # load but the one that set it. Two are exempt by design:
    # "paper" is what :root already holds, and "custom" is mixed
    # onto the root as inline properties rather than dressed by a
    # block at all.
    panel = face.respond("GET", "/voxam-prefs.js", b"")[2].decode("utf-8")
    axis = re.search(r'key: "theme"(.*?)(?:key: "|\Z)', panel, re.S)
    offered = set(re.findall(r'\["([a-z]+)", "', axis.group(1) if axis else ""))
    dressed = set(re.findall(r'html\[data-theme="([a-z]+)"\]', page))

    assert_that(offered).is_not_empty()
    assert_that(offered - dressed).is_equal_to({"paper", "custom"})

    # And every colour the mixer offers must be a property the page
    # actually reads, or a reader would tune a knob wired to
    # nothing.
    mixed = set(re.findall(r'\n    \["([a-z-]+)", "[A-Z]', panel))
    read = set(re.findall(r"var\(--([a-z-]+)", page))

    assert_that(mixed).is_not_empty()
    assert_that(mixed - read).is_empty()

    # The same for the sliders, which name the property each one
    # writes. A slider wired to a property nothing reads would move
    # under the hand and change nothing on the page.
    written = set(re.findall(r'property: "--([a-z-]+)"', panel))

    assert_that(written).is_not_empty()
    assert_that(written - read).is_empty()

    # And the column is counted in the story's own characters, which
    # only means anything if the gameport is set in the story's own
    # type.
    assert_that(page).contains("--measure: 98ch;")
    assert_that(
        re.search(r"#gameport \{[^}]*var\(--story-face\)", page, re.S)
    ).is_not_none()


# The shared display files are one file each, copied to both faces
# that wear this page, and a change to one that misses the other is
# exactly the drift that left the shell showing GlkOte's own
# colours for an era. The vendored stylesheet is in the list too:
# Voxam's corrections to it live in the pages, so the file itself
# has no reason ever to differ.
def test_both_faces_carry_the_same_display_assets() -> None:
    shared = Path(__file__).parent.parent / "desktop" / "ui"
    served = Path(voxam.__file__).parent / "pages"

    for name in ("voxam-prefs.js", "voxam-audio.js", "glkote.js", "glkote.css"):
        assert_that((shared / name).read_bytes()).described_as(name).is_equal_to(
            (served / name).read_bytes()
        )


# The display's own files serve under their names and types; the
# license rides in the package but is nobody's fetch, and unknown
# roads answer 404.
def test_the_assets_serve_with_their_types() -> None:
    face = faced()

    for name, kind in (
        ("glkote.js", "text/javascript"),
        ("glkote.css", "text/css"),
        ("jquery-1.12.4.min.js", "text/javascript"),
        ("voxam-prefs.js", "text/javascript"),
        ("waiting.gif", "image/gif"),
    ):
        status, served, payload = face.respond("GET", f"/{name}", b"")

        assert_that(status).is_equal_to(200)
        assert_that(served).is_equal_to(kind)
        assert_that(payload).is_not_empty()

    # Both vendored licenses ride in the package beside the files
    # they cover, and neither is a road a browser may walk.
    for license_file in ("LICENSE-glkote.txt", "LICENSE-jquery.txt"):
        assert_that(face.respond("GET", f"/{license_file}", b"")[0]).is_equal_to(404)
        assert_that((PAGES / license_file).read_text(encoding="utf-8")).contains(
            "MIT License"
        )

    assert_that(face.respond("GET", "/nothing", b"")[0]).is_equal_to(404)
    assert_that(face.respond("PUT", "/", b"")[0]).is_equal_to(404)


# Pictures serve by Blorb number with their own content types; a
# placeholder rectangle, a missing number, and a road that names
# no number at all are 404s.
def test_pictures_serve_by_number() -> None:
    face = faced()

    status, kind, payload = face.respond("GET", "/pict/1", b"")

    assert_that((status, kind)).is_equal_to((200, "image/png"))
    assert_that(payload[:4]).is_equal_to(b"\x89PNG")

    status, kind, _ = face.respond("GET", "/pict/2", b"")

    assert_that((status, kind)).is_equal_to((200, "image/jpeg"))

    assert_that(face.respond("GET", "/pict/3", b"")[0]).is_equal_to(404)
    assert_that(face.respond("GET", "/pict/9", b"")[0]).is_equal_to(404)
    assert_that(face.respond("GET", "/pict/abc", b"")[0]).is_equal_to(404)


# The tab wears the machine's own mark -- the same window icons
# the pygame title bars wear: a Glulx face answers the glulx
# icon, a Z face its version's own, and the page asks by link.
def test_the_tab_wears_the_machine_icon() -> None:
    status, kind, payload = faced().respond("GET", "/favicon.ico", b"")

    assert_that((status, kind)).is_equal_to((200, "image/x-icon"))
    assert_that(payload[:4]).is_equal_to(b"\x00\x00\x01\x00")

    data = bytearray(96)
    data[0] = 4
    data[0x04:0x06] = (0x0060).to_bytes(2, "big")
    data[0x06:0x08] = (0x0040).to_bytes(2, "big")
    data[0x08:0x0A] = (0x005A).to_bytes(2, "big")
    data[0x0E:0x10] = (0x0060).to_bytes(2, "big")

    zed = Face(ZSession(ZStory(bytes(data)), pictured(), seed=7), None)

    assert_that(zed.session.icon).is_equal_to("z4.ico")
    assert_that(zed.respond("GET", "/favicon.ico", b"")[2][:4]).is_equal_to(
        b"\x00\x00\x01\x00"
    )

    _, _, page = faced().respond("GET", "/", b"")

    assert_that(page.decode("utf-8")).contains('rel="icon"')


# A whole turn travels by POST: the init births the session and
# answers the first update, the keystroke answers the exit.
def test_a_turn_travels_by_post() -> None:
    face = faced()

    first = posted(face, INIT)

    assert_that(first["type"]).is_equal_to("update")
    assert_that(first["gen"]).is_equal_to(1)
    assert_that(first["windows"]).is_length(1)
    assert_that(first["input"]).is_equal_to([{"id": 1, "type": "char", "gen": 1}])

    last = posted(face, {"type": "char", "gen": 1, "window": 1, "value": "A"})

    assert_that(last).is_equal_to(
        {"type": "update", "gen": 2, "input": [], "exit": True}
    )


# A stale event draws the pass, exactly as the stdio face answers.
def test_a_stale_event_passes() -> None:
    face = faced()

    posted(face, INIT)

    assert_that(
        posted(face, {"type": "char", "gen": 0, "window": 1, "value": "A"})
    ).is_equal_to({"type": "pass"})


# A reload is a fresh init, and a fresh init starts the story
# over: new machine, new windows, generation one again -- even
# after the last one ended, and even after a fault.
def test_a_reload_starts_the_story_over() -> None:
    face = faced()

    posted(face, INIT)
    posted(face, {"type": "char", "gen": 1, "window": 1, "value": "A"})

    reborn = posted(face, INIT)

    assert_that(reborn["gen"]).is_equal_to(1)
    assert_that(reborn["windows"]).is_length(1)


# A fault answers the protocol's error stanza and keeps answering
# it -- the session is dead until a reload -- and an event before
# any init is told where conversations begin.
def test_a_fault_holds_until_the_reload() -> None:
    face = faced()

    posted(face, INIT)

    fault = posted(face, {"type": "line", "gen": 1, "window": 1, "value": "go"})

    assert_that(fault["type"]).is_equal_to("error")
    assert_that(fault["message"]).contains("not expecting")

    again = posted(face, {"type": "char", "gen": 1, "window": 1, "value": "A"})

    assert_that(again).is_equal_to(fault)
    assert_that(posted(face, INIT)["gen"]).is_equal_to(1)

    fresh = faced()

    assert_that(posted(fresh, {"type": "char", "gen": 0})["message"]).contains(
        "opens with an init"
    )


# A story that asks the player for a save file and quits.
PROMPTS = (
    bytes([0xC0, 0x00, 0x00])
    + bytes([0x40, 0x81, 0x00])
    + bytes([0x40, 0x81, 0x01])
    + bytes([0x40, 0x81, 0x01])
    + bytes([0x81, 0x30, 0x11, 0x06, 0x62, 0x03, 0x01, 0x40])
    + bytes([0x81, 0x20])
)


# A game's ask for a file crosses the wire as special input, and
# the posted answer resumes the turn -- no event delivered, the
# call itself was the destination.
def test_a_file_ask_crosses_the_wire() -> None:
    face = Face(
        GlulxSession(Story(glulx_image(PROMPTS)), pictured(), seed=7), "Saves — Voxam"
    )

    first = posted(face, INIT)

    assert_that(first["specialinput"]).is_equal_to(
        {"type": "fileref_prompt", "filemode": "write", "filetype": "save"}
    )

    done = posted(
        face,
        {
            "type": "specialresponse",
            "gen": 1,
            "response": "fileref_prompt",
            "value": "saga",
        },
    )

    assert_that(done).is_equal_to({"type": "update", "gen": 2, "exit": True})


# What is not JSON, and JSON that is not a stanza, answer 200 with
# the protocol's own error stanza: the display renders that far
# better than a bare status would.
def test_garbage_posts_answer_in_kind() -> None:
    face = faced()

    assert_that(posted(face, "{nope")["message"]).contains("not JSON")
    assert_that(posted(face, "[1, 2]")["message"]).contains("a stanza is a JSON object")
    assert_that(posted(face, b"\xff\xfe")["message"]).contains("not JSON")


# A Z-Machine story serves through the same face: init births a
# machine over the screen model, a posted line echoes and answers,
# and a reload starts the story over.
def test_a_z_story_serves_through_the_face() -> None:
    data = bytearray(96)
    data[0] = 4
    data[0x04:0x06] = (0x0060).to_bytes(2, "big")
    data[0x06:0x08] = (0x0040).to_bytes(2, "big")
    data[0x08:0x0A] = (0x005A).to_bytes(2, "big")
    data[0x0E:0x10] = (0x0060).to_bytes(2, "big")
    data[0x40:0x47] = bytes([0xE4, 0x0F, 0x00, 0x50, 0x00, 0x58, 0xBA])
    data[0x50] = 6
    data[0x58] = 1
    data[0x5A] = 0
    data[0x5B] = 7

    face = Face(
        ZSession(ZStory(bytes(data)), pictured(), seed=7), "Sensory Jam — Voxam"
    )

    first = posted(face, INIT)

    assert_that(first["gen"]).is_equal_to(1)
    assert_that(first["input"]).is_equal_to(
        [{"id": 1, "type": "line", "maxlen": 6, "gen": 1}]
    )

    done = posted(face, {"type": "line", "gen": 1, "window": 1, "value": "look"})

    assert_that(done["exit"]).is_true()
    assert_that(done["content"][0]["text"][0]["content"][0]["style"]).is_equal_to(
        "input"
    )
    assert_that(posted(face, INIT)["gen"]).is_equal_to(1)
    assert_that(
        posted(face, {"type": "line", "gen": 0, "window": 1, "value": "stale"})
    ).is_equal_to({"type": "pass"})

    # A standing verdict renders the picture as it stands: the
    # arrange moved the boxes, and the update says so.
    arranged = posted(
        face, {"type": "arrange", "gen": 1, "metrics": {"width": 400, "height": 200}}
    )

    assert_that(arranged["type"]).is_equal_to("update")
    assert_that(arranged["windows"][0]["width"]).is_equal_to(400)

    # An event before any init is told where conversations begin.
    unopened = Face(ZSession(ZStory(bytes(data)), pictured(), seed=7), None)

    assert_that(
        posted(unopened, {"type": "line", "gen": 0, "value": "x"})["message"]
    ).contains("opens with an init")


# The whole server, once, over a real socket: the page, a turn,
# and a wrong road, through the stdlib handler shell.
def test_the_server_answers_over_a_real_socket() -> None:
    server = webbed(faced(), 0)
    port = server.server_port
    runner = threading.Thread(target=server.serve_forever)

    runner.start()

    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/") as answer:
            assert_that(answer.status).is_equal_to(200)
            assert_that(answer.read().decode("utf-8")).contains("Sensory Jam")

        opened = urllib.request.Request(
            f"http://127.0.0.1:{port}/event",
            data=json.dumps(INIT).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )

        with urllib.request.urlopen(opened) as answer:  # noqa: S310 -- localhost http
            first = json.loads(answer.read())

            assert_that(first["gen"]).is_equal_to(1)

        with pytest.raises(urllib.error.HTTPError, match="404") as missing:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/nothing")

        missing.value.close()
    finally:
        server.shutdown()
        runner.join()
        server.server_close()


class Still:
    """A server stand-in that never listens."""

    server_port = 4321

    def __init__(self, *, interrupted: bool) -> None:
        self.interrupted = interrupted
        self.closed = False

    def serve_forever(self) -> None:
        if self.interrupted:
            raise KeyboardInterrupt

    def server_close(self) -> None:
        self.closed = True


# Serving announces its address and ends cleanly either way: the
# quiet return, or the player's own Ctrl+C.
def test_serving_ends_cleanly(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    quiet = Still(interrupted=False)

    monkeypatch.setattr("voxam.web.webbed", lambda _face, _port: quiet)

    assert_that(serve_web(faced(), 0)).is_equal_to(0)
    assert_that(quiet.closed).is_true()
    assert_that(capsys.readouterr().out).contains("http://127.0.0.1:4321")

    stopped = Still(interrupted=True)

    monkeypatch.setattr("voxam.web.webbed", lambda _face, _port: stopped)

    assert_that(serve_web(faced(), 0)).is_equal_to(0)
    assert_that(stopped.closed).is_true()


# The sepia status bar had been pixel-for-pixel the prose beneath
# it, and the paper bar's text was lighter than the story's own.
# The §8.2 line is reverse video from end to end, so an upper
# window dressed as the story's inverse inverted it a second time
# and landed back where it started. Every ink now names its own
# bar, and this holds every one of them apart from its paper.
def test_every_ink_names_a_bar_apart_from_its_paper() -> None:
    _, _, payload = faced().respond("GET", "/", b"")
    page = payload.decode("utf-8")

    inks = [
        dict(re.findall(r"--([a-z-]+):\s*([^;]+);", block))
        for block in re.findall(r"\{([^{}]*--paper:[^{}]*)\}", page)
    ]

    assert_that(inks).is_length(5)

    for held in inks:
        assert_that(held["bar"]).is_not_equal_to(held["paper"])
        assert_that(held["bar-ink"]).is_not_equal_to(held["ink"])


# The burst model sends nothing back until the machine reaches its
# next wait, so a story that thinks for a long time leaves the page
# perfectly still -- Dead Cities spends over a minute opening
# itself, and a still page reads as a dead interpreter. The chip
# says otherwise, but only after a delay, so an ordinary turn never
# flashes it.
def test_the_page_carries_a_working_light() -> None:
    _, _, payload = faced().respond("GET", "/", b"")
    page = payload.decode("utf-8")

    assert_that(page).contains('<div id="working" role="status" aria-live="polite">')
    assert_that(page).contains("#working[data-shown]")
    assert_that(page).contains("prefers-reduced-motion")

    # The seconds are hidden from assistive technology: the chip
    # announces itself once, and a number ticking every second
    # would otherwise say it again and again.
    assert_that(page).contains('<span id="working-for" aria-hidden="true">')
    assert_that(page).contains("setInterval(tell, 1000)")

    # Raised when the turn goes out, lowered by both the answer and
    # the failure: a fault must never leave it burning.
    accept = page.split("accept: function(event) {")[1].split("};")[0]

    assert_that(accept).contains("voxamWorking(true)")
    assert_that(accept.count("voxamWorking(false)")).is_equal_to(2)


# A form control takes its colour from the browser's own stylesheet,
# not from the page around it, so the field the player types into
# stays black however the story is dressed -- unreadable on a dark
# ink. Both halves of the typed line have to be asked for: the field
# while it is being typed, and the echo once the machine has it.
def test_the_typed_line_wears_the_story_ink() -> None:
    _, _, payload = faced().respond("GET", "/", b"")
    page = payload.decode("utf-8")

    for rule in (".Input", ".Style_input"):
        dressed = page.split(f"\n{rule} {{")[1].split("}")[0]

        assert_that(dressed).contains("color: inherit")


# Both timers have to be put out, not just the one that showed the
# chip: a turn that answers while the seconds are running would
# otherwise leave them counting over a finished session.
def test_the_working_light_stops_counting() -> None:
    _, _, payload = faced().respond("GET", "/", b"")
    page = payload.decode("utf-8")
    lowered = page.split("function voxamWorking(thinking) {")[1].split("var Game")[0]

    assert_that(lowered).contains("clearTimeout(VOXAM_WORKING_TIMER)")
    assert_that(lowered).contains("clearInterval(VOXAM_WORKING_TICK)")
