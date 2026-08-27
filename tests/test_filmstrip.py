"""The web filmstrip: the wire walked, paged, and photographed."""

import shutil
import subprocess
from pathlib import Path

import pytest
from assertpy import assert_that

from voxam.errors import GlkOteError
from voxam.filmstrip import browsed, paged, parted, shot, walked
from voxam.glulx.glk.resources import Resources
from voxam.png import Picture, encoded
from voxam.web import ZSession
from voxam.zmachine.story import Story


def z_story(code: bytes, version: int = 3) -> Story:
    """A tiny story with code at $40 and read buffers planted."""

    data = bytearray(96)
    data[0] = version
    data[0x04:0x06] = (0x0060).to_bytes(2, "big")
    data[0x06:0x08] = (0x0040).to_bytes(2, "big")
    data[0x08:0x0A] = (0x005A).to_bytes(2, "big")
    data[0x0C:0x0E] = (0x005C).to_bytes(2, "big")
    data[0x0E:0x10] = (0x0060).to_bytes(2, "big")
    data[0x40 : 0x40 + len(code)] = code
    data[0x50] = 6
    data[0x58] = 1
    data[0x5A] = 0
    data[0x5B] = 7

    return Story(bytes(data))


# One line read then quit; one keystroke read then quit; a save
# ask ahead of the read; and a boot that quits asking nothing.
READS = bytes([0xE4, 0x0F, 0x00, 0x50, 0x00, 0x58, 0xBA])
PRESSES = bytes([0xF6, 0x7F, 0x01, 0x10, 0xBA])
SAVES = bytes([0xBE, 0x00, 0xFF, 0x10, 0xE4, 0x0F, 0x00, 0x50, 0x00, 0x58, 0x10, 0xBA])
QUITS = bytes([0xBA])


def session(code: bytes, version: int = 4) -> ZSession:
    return ZSession(z_story(code, version), Resources(), seed=7)


# The walk speaks the wire's own asks: a line read takes the
# command whole, the marks put frame zero at boot and frame N
# after N answers, and the collected updates carry the echo.
def test_walks_answer_the_standing_ask() -> None:
    updates, marks, note = walked(session(READS), ["look"])

    assert_that(marks).is_equal_to([1, 2])
    assert_that(note).is_none()
    assert_that(len(updates)).is_equal_to(2)

    told = str(updates[1].get("content"))

    assert_that(told).contains("look")


# A keystroke read takes one key, spelled as the display would
# have sent it: a named key inverts through the face's own table,
# and a plain character passes as itself.
def test_keys_spell_as_the_display_sends_them() -> None:
    named, _, _ = walked(session(PRESSES), ["\n"])

    assert_that(named).is_length(2)

    plain, _, _ = walked(session(PRESSES), ["q"])

    assert_that(plain).is_length(2)


# A standing file prompt is cancelled before the walk continues --
# the strip photographs play, not dialogs -- and the cancel's
# update joins the wire between the marks.
def test_file_prompts_cancel_on_the_way() -> None:
    updates, marks, _ = walked(session(SAVES, version=5), ["look"])

    assert_that(marks[-1]).is_equal_to(len(updates))
    assert_that(any("specialinput" in held for held in updates)).is_true()


# The wire's refusals are loud: a command with nothing asked is a
# mismatch said plainly, and an error stanza raises rather than
# photographing a corpse.
def test_walks_refuse_a_deaf_wire() -> None:
    _, _, note = walked(session(QUITS), ["look"])

    assert_that(note).contains("asks for nothing")
    assert_that(note).contains("command 1")

    broken = session(bytes([0x00]))

    with pytest.raises(GlkOteError, match="error"):
        walked(broken, [])


# The page writes beside the strip with the shipped display files
# whole, the wire baked in as updates.js.
def test_pages_carry_the_shipped_display(tmp_path: Path) -> None:
    updates, _, _ = walked(session(READS), [])
    page = paged(tmp_path / "page", updates)

    assert_that(page.name).is_equal_to("replay.html")
    assert_that((tmp_path / "page" / "glkote.js").exists()).is_true()
    assert_that((tmp_path / "page" / "glkote.css").exists()).is_true()
    assert_that((tmp_path / "page" / "updates.js").read_text("utf-8")).contains(
        "var UPDATES"
    )


# The browser is found where it is: a named path answers itself
# when real, PATH answers next, the standard seats after, and an
# empty world answers None.
def test_browsers_are_found_where_they_are(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    named = tmp_path / "chrome.exe"

    named.write_bytes(b"")

    assert_that(browsed(str(named))).is_equal_to(named)
    assert_that(browsed(str(tmp_path / "ghost.exe"))).is_none()

    monkeypatch.setattr(shutil, "which", lambda _name: str(named))

    assert_that(browsed(None)).is_equal_to(named)

    monkeypatch.setattr(shutil, "which", lambda _name: None)
    monkeypatch.setattr("voxam.filmstrip.BROWSER_SEATS", (named,))

    assert_that(browsed(None)).is_equal_to(named)

    monkeypatch.setattr("voxam.filmstrip.BROWSER_SEATS", (tmp_path / "empty-seat.exe",))

    assert_that(browsed(None)).is_none()


# The camera launches once per frame, each launch aimed at its
# mark, and a launch that prints nothing is a broken camera said
# loudly -- never a silent hole in the strip.
def test_shots_launch_once_per_frame(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    launches: list[list[str]] = []

    def printing(arguments: list[str], **_knobs: object) -> None:
        launches.append(arguments)

        for piece in arguments:
            if piece.startswith("--screenshot="):
                Path(piece.removeprefix("--screenshot=")).write_bytes(b"png")

    monkeypatch.setattr(subprocess, "run", printing)

    page = tmp_path / "page" / "replay.html"

    page.parent.mkdir(parents=True)
    page.write_text("strip", encoding="utf-8")

    frames = shot(page, tmp_path / "strip", [1, 3, 4], tmp_path / "chrome.exe")

    assert_that(frames).is_equal_to(3)
    assert_that((tmp_path / "strip" / "turn-0002.png").exists()).is_true()
    assert_that(launches[1][-1]).ends_with("?upto=3")

    def refusing(arguments: list[str], **_knobs: object) -> None:
        del arguments

    monkeypatch.setattr(subprocess, "run", refusing)

    with pytest.raises(GlkOteError, match="printed no frame"):
        shot(page, tmp_path / "hole", [1], tmp_path / "chrome.exe")


def framed(
    directory: Path, name: str, pixels: tuple[tuple[int, int, int], ...]
) -> None:
    """One encoded frame in a strip: our own encoder writes it."""

    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_bytes(encoded(Picture(len(pixels), 1, (pixels,))))


# The diff answers from pixel truth: identical strips say so with
# their count, a changed pixel names its frame and its tally, a
# frame one strip lacks stands alone, sizes that disagree are
# said, and the verdict line names where the strips part.
def test_strips_part_where_their_pixels_do(tmp_path: Path) -> None:
    left = tmp_path / "a"
    right = tmp_path / "b"
    same = ((1, 2, 3), (4, 5, 6))

    framed(left, "turn-0000.png", same)
    framed(right, "turn-0000.png", same)

    lines, differs = parted(left, right)

    assert_that(differs).is_false()
    assert_that(lines[-1]).is_equal_to("identical: 1 frames")

    framed(left, "turn-0001.png", same)
    framed(right, "turn-0001.png", ((9, 9, 9), (4, 5, 6)))
    framed(left, "turn-0002.png", same)

    lines, differs = parted(left, right)

    assert_that(differs).is_true()
    assert_that(lines).contains("turn-0001.png differs: 1 of 2 pixels")
    assert_that(str(lines)).contains("turn-0002.png stands only in")
    assert_that(lines[-1]).contains("the strips part at turn-0001.png")
    assert_that(lines[-1]).contains("1 of 2 shared frames differ, 1 unshared")

    framed(right, "turn-0000.png", ((7, 7, 7), (4, 5, 6)))

    lines, differs = parted(left, right)

    assert_that(lines[-1]).contains("the strips part at turn-0000.png")
    assert_that(lines[-1]).contains("2 of 2 shared frames differ")

    wide = tmp_path / "wide"
    narrow = tmp_path / "narrow"

    framed(wide, "turn-0000.png", same)
    framed(narrow, "turn-0000.png", ((1, 2, 3),))

    lines, differs = parted(wide, narrow)

    assert_that(differs).is_true()
    assert_that(lines[0]).contains("2x1 against 1x1")

    with pytest.raises(GlkOteError, match="no frames"):
        parted(tmp_path / "hollow", left)
