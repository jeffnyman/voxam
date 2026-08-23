import io
import runpy
import struct
import sys
import types
import zlib
from collections.abc import Callable
from contextlib import AbstractContextManager, nullcontext
from importlib import metadata
from pathlib import Path
from typing import cast

import pytest
from assertpy import assert_that

from voxam.acceptance import Recorder
from voxam.blorb import Blorb, Resource
from voxam.cli import (
    _entitle_terminal,
    _gallery,
    _glass_frontend,
    _graphics_frontend,
    _picture_file_gallery,
    _recorded_glk,
    _recorded_keys,
    _recorded_ticks,
    _screen_frontend,
    _speaker,
    _terminal_frontend,
    _titled,
    main,
)
from voxam.gallery import Gallery, Resolution
from voxam.glass import Glass as PygameGlass
from voxam.glulx.glk.glass import GlassFrontend as GlulxGlassFrontend
from voxam.glulx.glk.objects import KeyCode as GlkKeyCode
from voxam.glulx.glk.terminal import TerminalFrontend
from voxam.iff import Chunk, chunk, write_form
from voxam.iff import chunk as iff_chunk
from voxam.painter import ScreenFrontend, Terminal
from voxam.png import SIGNATURE
from voxam.speaker import Speaker, open_sounddevice_stream


def broken_story(tmp_path: Path, code: bytes, version: int = 3) -> Path:
    data = bytearray(96)
    data[0] = version
    data[0x04:0x06] = (0x0060).to_bytes(2, "big")
    data[0x06:0x08] = (0x0040).to_bytes(2, "big")
    data[0x0E:0x10] = (0x0060).to_bytes(2, "big")
    data[0x40 : 0x40 + len(code)] = code
    path = tmp_path / "story.z3"
    path.write_bytes(bytes(data))

    return path


# A story that reads one command and quits, with buffers at $50 and
# $58 and an empty dictionary at $5a. The Version 4 variant serves
# frontends that would otherwise draw a status line from garbage
# globals (§8.2.2.1).
def reading_story(tmp_path: Path, version: int = 3) -> Path:
    data = bytearray(96)
    data[0] = version
    data[0x04:0x06] = (0x0060).to_bytes(2, "big")
    data[0x06:0x08] = (0x0040).to_bytes(2, "big")
    data[0x08:0x0A] = (0x005A).to_bytes(2, "big")
    data[0x0E:0x10] = (0x0060).to_bytes(2, "big")
    data[0x40:0x47] = bytes([0xE4, 0x0F, 0x00, 0x50, 0x00, 0x58, 0xBA])
    data[0x50] = 6
    data[0x58] = 1
    data[0x5A] = 0
    data[0x5B] = 7
    path = tmp_path / "reads.z3"
    path.write_bytes(bytes(data))

    return path


def test_main_prints_banner(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main([])

    assert_that(exit_code).is_equal_to(0)
    assert_that(capsys.readouterr().out).contains("Voxam")


# The version action answers inside parse_args, before the banner:
# one line, spelled from the installed distribution's metadata --
# the same number pyproject.toml declares -- and a clean exit.
def test_main_reports_the_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as caught:
        main(["--version"])

    assert_that(caught.value.code).is_equal_to(0)
    expected = f"voxam {metadata.version('voxam')}\n"
    assert_that(capsys.readouterr().out).is_equal_to(expected)


# A stream without the encoding knob -- a bare StringIO -- is left
# as it is; everything Voxam prints is unicode-clean already.
def test_main_survives_a_stream_without_reconfigure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stream = io.StringIO()
    monkeypatch.setattr(sys, "stdout", stream)

    assert_that(main([])).is_equal_to(0)
    assert_that(stream.getvalue()).contains("Voxam")


def test_running_as_module_invokes_the_cli(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "argv", ["voxam"])

    with pytest.raises(SystemExit) as excinfo:
        runpy.run_module("voxam", run_name="__main__")

    assert_that(excinfo.value.code).is_equal_to(0)
    assert_that(capsys.readouterr().out).contains("Voxam")


def test_runs_a_story_to_completion(
    fixture_path: Callable[[int], Path], capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = main([str(fixture_path(3))])

    out = capsys.readouterr().out

    assert_that(exit_code).is_equal_to(0)
    assert_that(out).contains("release 1, serial 260727 (z3)")
    assert_that(out).contains("hello from all z machine versions")


def test_reports_a_missing_file(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["no-such-story.z3"])

    assert_that(exit_code).is_equal_to(2)
    assert_that(capsys.readouterr().out).contains("voxam:")


def test_reports_an_invalid_story(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "tiny.z3"
    path.write_bytes(bytes(10))

    exit_code = main([str(path)])

    assert_that(exit_code).is_equal_to(2)
    assert_that(capsys.readouterr().out).contains("header")


def test_a_seed_is_accepted_for_reproducible_sessions(
    fixture_path: Callable[[int], Path], capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = main(["--seed", "1137", str(fixture_path(3))])

    assert_that(exit_code).is_equal_to(0)
    assert_that(capsys.readouterr().out).contains("hello from all z machine")


def test_typed_input_reaches_the_story(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO("look\n"))

    exit_code = main([str(reading_story(tmp_path))])

    assert_that(exit_code).is_equal_to(0)
    assert_that(capsys.readouterr().out).does_not_contain("voxam:")


# Running out of typed input ends the session cleanly rather than
# crashing mid-read.
def test_end_of_input_ends_the_session(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO(""))

    exit_code = main([str(reading_story(tmp_path))])

    assert_that(exit_code).is_equal_to(0)
    assert_that(capsys.readouterr().out).contains("end of input")


def accept_file(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "session.accept"
    path.write_text(content, encoding="utf-8")

    return path


def ztext(text: str) -> bytes:
    """Encode lowercase letters and spaces as terminated z-text."""

    codes = [0 if c == " " else 6 + ord(c) - ord("a") for c in text]

    while len(codes) % 3:
        codes.append(5)

    words = []

    for i in range(0, len(codes), 3):
        word = (codes[i] << 10) | (codes[i + 1] << 5) | codes[i + 2]

        if i + 3 == len(codes):
            word |= 0x8000

        words.append(word)

    return b"".join(word.to_bytes(2, "big") for word in words)


# A story that reads one command, answers it in the parser's refusal
# voice, and quits.
def refusing_story(tmp_path: Path) -> Path:
    data = bytearray(0xA0)
    data[0] = 3
    data[0x04:0x06] = (0x0090).to_bytes(2, "big")
    data[0x06:0x08] = (0x0040).to_bytes(2, "big")
    data[0x08:0x0A] = (0x007A).to_bytes(2, "big")
    data[0x0E:0x10] = (0x0090).to_bytes(2, "big")
    code = (
        bytes([0xE4, 0x0F, 0x00, 0x70, 0x00, 0x78])
        + bytes([0xB2])
        + ztext("you must use a verb")
        + bytes([0xBA])
    )
    data[0x40 : 0x40 + len(code)] = code
    data[0x70] = 6
    data[0x78] = 1
    data[0x7A] = 0
    data[0x7B] = 7
    path = tmp_path / "refuses.z3"
    path.write_bytes(bytes(data))

    return path


# The watch reads the conversation during --accept and points at the
# script line whose command drew the refusal.
def test_replay_warns_about_refused_commands(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    story = refusing_story(tmp_path)
    script = accept_file(tmp_path, f"! GAME={story}\n# opener\nfrotz\n")

    exit_code = main(["--accept", str(script)])

    out = capsys.readouterr().out

    assert_that(exit_code).is_equal_to(0)
    assert_that(out).contains("voxam: line 3: 'frotz' looks refused")


def test_clean_replays_draw_no_warnings(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    story = reading_story(tmp_path)
    script = accept_file(tmp_path, f"! GAME={story}\nlook\n")

    exit_code = main(["--accept", str(script)])

    assert_that(exit_code).is_equal_to(0)
    assert_that(capsys.readouterr().out).does_not_contain("looks refused")


# --trace rides any session: a replay wearing it writes every
# executed instruction to the named file, listing-style, closing
# with the tallies -- while an unwritable trace path refuses before
# any story runs.
def test_a_replay_writes_its_trace(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    story = reading_story(tmp_path)
    script = accept_file(tmp_path, f"! GAME={story}\nlook\n")
    trace = tmp_path / "session.trace"

    exit_code = main(["--accept", str(script), "--trace", str(trace)])

    assert_that(exit_code).is_equal_to(0)
    assert_that(capsys.readouterr().out).contains("Tracing to")

    written = trace.read_text(encoding="utf-8")

    assert_that(written).contains("sread")
    assert_that(written).contains("[end of trace:")

    blocked = main(["--accept", str(script), "--trace", str(tmp_path)])

    assert_that(blocked).is_equal_to(2)


# --trace describes a running session, so the static reports refuse
# it, and RegTest -- which runs machines of its own -- does too.
def test_trace_refusals(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    story = reading_story(tmp_path)

    listed = main(["--listing", str(story), "--trace", str(tmp_path / "t")])

    assert_that(listed).is_equal_to(2)
    assert_that(capsys.readouterr().out).contains("drop the session flags")

    tested = main(["--regtest", "suite.reg", "--trace", str(tmp_path / "t")])

    assert_that(tested).is_equal_to(2)
    assert_that(capsys.readouterr().out).contains("drop the other flags")


# The full replay loop: the script names its game, the command is
# typed and echoed, and the exhausted script ends the session.
def test_replays_an_acceptance_script(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    story = reading_story(tmp_path)
    script = accept_file(tmp_path, f"! GAME={story}\nlook   # around\n")

    exit_code = main(["--accept", str(script)])

    out = capsys.readouterr().out

    assert_that(exit_code).is_equal_to(0)
    assert_that(out).contains("Running reads.z3")
    assert_that(out).contains("look\n")
    assert_that(out).does_not_contain("# around")


def test_a_seed_argument_overrides_the_scripts_seed(tmp_path: Path) -> None:
    story = reading_story(tmp_path)
    script = accept_file(tmp_path, f"! SEED=99\n! GAME={story}\nlook\n")

    exit_code = main(["--accept", str(script), "--seed", "1137"])

    assert_that(exit_code).is_equal_to(0)


def test_a_script_and_a_story_argument_conflict(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    script = accept_file(tmp_path, "! GAME=g.z3\n")

    exit_code = main(["--accept", str(script), "some-story.z3"])

    assert_that(exit_code).is_equal_to(2)
    assert_that(capsys.readouterr().out).contains("drop the story")


def test_a_bad_script_is_reported(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    script = accept_file(tmp_path, "look\n")

    exit_code = main(["--accept", str(script)])

    assert_that(exit_code).is_equal_to(2)
    assert_that(capsys.readouterr().out).contains("names no game")


# --replay catches up through the script, then live input takes over
# at the prompt: here the script is empty, so the game's one read
# comes straight from stdin.
def test_replay_hands_off_to_the_terminal(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO("look\n"))
    story = reading_story(tmp_path)
    script = accept_file(tmp_path, f"! GAME={story}\n")

    exit_code = main(["--replay", str(script)])

    assert_that(exit_code).is_equal_to(0)
    assert_that(capsys.readouterr().out).does_not_contain("end of input")


def test_accept_and_replay_conflict(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    script = accept_file(tmp_path, "! GAME=g.z3\n")

    exit_code = main(["--accept", str(script), "--replay", str(script)])

    assert_that(exit_code).is_equal_to(2)
    assert_that(capsys.readouterr().out).contains("pick one")


# A start function that quits at once, and one that opens a Glk
# window, selects it, and prints "Hi" -- window id 1, because the
# registry mints reproducible ids.
GLULX_QUIT = bytes([0xC0, 0x00, 0x00, 0x81, 0x20])
GLULX_HI = (
    bytes([0xC0, 0x00, 0x00])
    + bytes([0x40, 0x81, 0x00])
    + bytes([0x40, 0x81, 0x03])
    + bytes([0x40, 0x81, 0x00])
    + bytes([0x40, 0x81, 0x00])
    + bytes([0x40, 0x81, 0x00])
    + bytes([0x81, 0x30, 0x11, 0x00, 0x23, 0x05])
    + bytes([0x40, 0x81, 0x01])
    + bytes([0x81, 0x30, 0x11, 0x00, 0x2F, 0x01])
    + bytes([0x81, 0x49, 0x11, 0x02, 0x00])
    + bytes([0x70, 0x01, 0x48])
    + bytes([0x70, 0x01, 0x69])
    + bytes([0x81, 0x20])
)


def glulx_story(
    tmp_path: Path, version: int = 0x00030102, code: bytes = GLULX_QUIT
) -> Path:
    """A tiny valid Glulx image, checksummed, written beside tmp."""

    data = bytearray(0x200)
    data[0:4] = b"Glul"
    data[4:8] = version.to_bytes(4, "big")
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
    path = tmp_path / "tiny.ulx"
    path.write_bytes(bytes(data))

    return path


# A Glulx story runs: the banner speaks its version and checksum
# verdict, the session plays through the stdio display, and a
# story that opens a window and prints is heard. A header that
# breaks its promises still fails loudly.
def test_a_glulx_story_runs(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main([str(glulx_story(tmp_path))])
    out = capsys.readouterr().out

    assert_that(exit_code).is_equal_to(0)
    assert_that(out).contains("Glulx 3.1.2, checksum verified")

    spoken = main([str(glulx_story(tmp_path, code=GLULX_HI))])

    assert_that(spoken).is_equal_to(0)
    assert_that(capsys.readouterr().out).contains("Hi")

    broken = main([str(glulx_story(tmp_path, version=0x00040000))])

    assert_that(broken).is_equal_to(2)
    assert_that(capsys.readouterr().out).contains("2.0.0")

    # A story that faults mid-run fails loudly at its own fault.
    crashing = main([str(glulx_story(tmp_path, code=bytes([0xC0, 0x00, 0x00, 0x7F])))])

    assert_that(crashing).is_equal_to(2)
    assert_that(capsys.readouterr().out).contains("does not define")


# A packaged .gblorb runs the same session its bare story would.
def test_a_gblorb_story_runs(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    image = glulx_story(tmp_path, code=GLULX_HI).read_bytes()
    packaged = tmp_path / "tiny.gblorb"

    placeholder = (1).to_bytes(4, "big") + b"Exec" + bytes(8)
    offset = 12 + len(iff_chunk(b"RIdx", placeholder))
    index = (
        (1).to_bytes(4, "big")
        + b"Exec"
        + (0).to_bytes(4, "big")
        + offset.to_bytes(4, "big")
    )
    body = b"IFRS" + iff_chunk(b"RIdx", index) + iff_chunk(b"GLUL", image)

    packaged.write_bytes(iff_chunk(b"FORM", body))

    exit_code = main([str(packaged)])

    assert_that(exit_code).is_equal_to(0)
    assert_that(capsys.readouterr().out).contains("Hi")


# Tracing is still a Z-Machine instrument, declined by name.
def test_glulx_declines_the_trace(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    story = glulx_story(tmp_path)

    traced = main([str(story), "--trace", str(tmp_path / "out.trace")])

    assert_that(traced).is_equal_to(2)
    assert_that(capsys.readouterr().out).contains("Z-Machine session instrument")

    recorded = main(
        [
            str(story),
            "--record",
            str(tmp_path / "out.accept"),
            "--trace",
            str(tmp_path / "out.trace"),
        ]
    )

    assert_that(recorded).is_equal_to(2)


# A start function that prints "Hi", asks for a line, and answers
# "Ok" -- the smallest story with a conversation to record.
def glulx_asks() -> bytes:
    return (
        bytes([0xC0, 0x00, 0x00])
        + bytes([0x40, 0x81, 0x00])
        + bytes([0x40, 0x81, 0x03])
        + bytes([0x40, 0x81, 0x00])
        + bytes([0x40, 0x81, 0x00])
        + bytes([0x40, 0x81, 0x00])
        + bytes([0x81, 0x30, 0x11, 0x00, 0x23, 0x05])
        + bytes([0x40, 0x81, 0x01])
        + bytes([0x81, 0x30, 0x11, 0x00, 0x2F, 0x01])
        + bytes([0x81, 0x49, 0x11, 0x02, 0x00])
        + bytes([0x70, 0x01, 0x48])
        + bytes([0x70, 0x01, 0x69])
        + bytes([0x40, 0x81, 0x00])
        + bytes([0x40, 0x81, 0x32])
        + bytes([0x40, 0x82, 0x01, 0x20])
        + bytes([0x40, 0x81, 0x01])
        + bytes([0x81, 0x30, 0x12, 0x00, 0x00, 0xD0, 0x04])
        + bytes([0x40, 0x82, 0x01, 0x10])
        + bytes([0x81, 0x30, 0x12, 0x00, 0x00, 0xC0, 0x01])
        + bytes([0x70, 0x01, 0x4F])
        + bytes([0x70, 0x01, 0x6B])
    )


# A Glulx session records to the acceptance grammar and replays
# from it: the same seed, the same commands, the same session --
# the discipline the Z-Machine has kept since 0.4, now spoken by
# the new machine.
def test_glulx_records_and_replays(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    story = glulx_story(tmp_path, code=glulx_asks() + bytes([0x81, 0x20]))
    target = tmp_path / "session.accept"

    monkeypatch.setattr("sys.stdin", io.StringIO("go north\n"))

    recorded = main([str(story), "--record", str(target), "--seed", "7"])
    out = capsys.readouterr().out

    assert_that(recorded).is_equal_to(0)
    assert_that(out).contains("Hi")
    assert_that(out).contains("Ok")

    script = target.read_text(encoding="utf-8")

    assert_that(script).contains("! SEED=7")
    assert_that(script).contains("go north")

    replayed = main(["--accept", str(target)])
    out = capsys.readouterr().out

    assert_that(replayed).is_equal_to(0)
    assert_that(out).contains("Hi")
    assert_that(out).contains("go north")
    assert_that(out).contains("Ok")
    assert_that(out).does_not_contain("looks refused")


# The refusal watch reads a Glulx conversation the same way it
# reads a Z-Machine one: a response spoken in the refusal dialect
# earns a warning naming the command and its line.
def test_glulx_replays_hear_refusals(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    head = glulx_asks() + bytes([0x70, 0x01, 0x0A]) + bytes([0x72, 0x02])
    refusal = b"\xe0I beg your pardon.\x00"
    address = 0x48 + len(head) + 2 + 2
    code = head + address.to_bytes(2, "big") + bytes([0x81, 0x20]) + refusal
    story = glulx_story(tmp_path, code=code)

    script = tmp_path / "session.accept"

    script.write_text(f"! GAME={story.name}\n! SEED=7\n\nplugh\n", encoding="utf-8")

    replayed = main(["--accept", str(script)])
    out = capsys.readouterr().out

    assert_that(replayed).is_equal_to(0)
    assert_that(out).contains("I beg your pardon")
    assert_that(out).contains("'plugh' looks refused")

    # A script naming a broken Glulx file fails at the header, not
    # at the prompt.
    corrupt = tmp_path / "broken.ulx"

    corrupt.write_bytes(b"Glul" + bytes(8))

    broken = tmp_path / "broken.accept"

    broken.write_text(f"! GAME={corrupt.name}\n! SEED=1\n\nlook\n", encoding="utf-8")

    assert_that(main(["--accept", str(broken)])).is_equal_to(2)
    assert_that(capsys.readouterr().out).contains("voxam:")


# A Glulx session finds its resources the way a Z session does: a
# like-named sidecar on its own, or wherever --resources points.
def test_glulx_resources_are_found(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    story = glulx_story(tmp_path)
    empty = iff_chunk(b"FORM", b"IFRS" + iff_chunk(b"RIdx", (0).to_bytes(4, "big")))

    (tmp_path / "tiny.blorb").write_bytes(empty)

    assert_that(main([str(story)])).is_equal_to(0)

    elsewhere = tmp_path / "art.blorb"

    elsewhere.write_bytes(empty)

    assert_that(main([str(story), "--resources", str(elsewhere)])).is_equal_to(0)

    capsys.readouterr()


# Where a piped stdout keeps the stdio display, a real terminal
# earns the painted one -- unless the blessed extra never arrived,
# in which case the stdio display carries on as always.
def test_a_terminal_selects_the_glulx_glass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from voxam.glulx.glk.terminal import TerminalFrontend  # noqa: PLC0415

    monkeypatch.setattr("sys.stdout.isatty", lambda: False)

    assert_that(_terminal_frontend()).is_none()

    monkeypatch.setattr("sys.stdout.isatty", lambda: True)

    assert_that(_terminal_frontend()).is_instance_of(TerminalFrontend)

    monkeypatch.setitem(sys.modules, "voxam.glulx.glk.terminal", None)

    assert_that(_terminal_frontend()).is_none()


# The Glulx glass brings a speaker along when the Blorb's sounds
# and the audio device allow, and claims sound exactly then --
# the same courtesy _speaker pays the Z-Machine's glasses.
def test_the_glulx_glass_brings_a_speaker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)

    bare = _terminal_frontend(None)

    if bare is None:
        pytest.fail("the glass opened")

    assert_that(bare.sound).is_false()

    # A recorder rides in through the glass's seams.
    recorder = Recorder(
        tmp_path / "session.accept", game=tmp_path / "story.ulx", seed=7, warn=print
    )

    assert_that(_terminal_frontend(None, recorder)).is_not_none()

    recorder.close()

    speaker = Speaker({}, frozenset(), open_sounddevice_stream)

    monkeypatch.setattr("voxam.cli._speaker", lambda _blorb: speaker)

    sounding = _terminal_frontend(None)

    if sounding is None:
        pytest.fail("the glass opened")

    assert_that(sounding.sound).is_true()


# At a real terminal a Glulx session plays on the glass: the shell
# is wiped before the story and the cursor retired below it after.
def test_a_glulx_session_plays_on_the_glass(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)

    exit_code = main([str(glulx_story(tmp_path))])

    assert_that(exit_code).is_equal_to(0)
    assert_that(capsys.readouterr().out).contains("Running")


# A replay keeps the stdio display even at a terminal -- its
# lines are what the grammar speaks -- and --plain keeps it by
# request. A live recording asks for the glass now, and falls
# back to recording at the stdio display when no glass answers.
def test_the_line_seam_keeps_the_stdio_display(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked: list[bool] = []

    monkeypatch.setattr("sys.stdout.isatty", lambda: True)
    monkeypatch.setattr(
        "voxam.cli._terminal_frontend",
        lambda *_args, **_kwargs: asked.append(True),
    )

    story = glulx_story(tmp_path, code=glulx_asks() + bytes([0x81, 0x20]))

    monkeypatch.setattr("sys.stdin", io.StringIO("go north\n"))

    target = tmp_path / "session.accept"
    recorded = main([str(story), "--record", str(target), "--seed", "7"])

    assert_that(recorded).is_equal_to(0)
    assert_that(asked).is_length(1)

    replayed = main(["--accept", str(target)])

    assert_that(replayed).is_equal_to(0)
    assert_that(asked).is_length(1)

    plain = main(["--plain", str(glulx_story(tmp_path))])

    assert_that(plain).is_equal_to(0)
    assert_that(asked).is_length(1)

    capsys.readouterr()


# The bridge between the glass's seams and the grammar: tokens
# where tokens exist, plain characters where they are ordinary,
# the bare prompt for Return, and loud warnings for everything
# the grammar cannot spell.
def test_the_glk_bridge_speaks_the_grammar(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "session.accept"
    recorder = Recorder(target, game=tmp_path / "story.ulx", seed=7, warn=print)
    line, key, click, link = _recorded_glk(recorder)

    key(GlkKeyCode.UP)
    key(GlkKeyCode.RETURN)
    key(ord("x"))
    key(GlkKeyCode.PAGE_UP)
    key(0x01)
    line("go north", 0)
    line("g", GlkKeyCode.ESCAPE)
    click(5, 2)
    link(12)
    recorder.close()

    written = target.read_text(encoding="utf-8").splitlines()

    assert_that(written).contains("<up>")
    assert_that(written).contains(">")
    assert_that(written).contains("x")
    assert_that(written).contains("go north")
    assert_that(written).contains("g")
    assert_that(written).contains("<click 5 2>")
    assert_that(written).contains("<link 12>")

    warned = capsys.readouterr().out

    assert_that(warned).contains("key 0xFFFFFFF6 has no token")
    assert_that(warned).contains("key 1 has no token")
    assert_that(warned).contains("terminator")


# A start function that opens a window, asks for one keystroke,
# and answers "up!" for the up arrow and "no" for anything else --
# the smallest story that can hear a key token.
def glulx_hears() -> bytes:
    return (
        bytes([0xC0, 0x00, 0x00])
        + bytes([0x40, 0x81, 0x00])
        + bytes([0x40, 0x81, 0x03])
        + bytes([0x40, 0x81, 0x00])
        + bytes([0x40, 0x81, 0x00])
        + bytes([0x40, 0x81, 0x00])
        + bytes([0x81, 0x30, 0x11, 0x00, 0x23, 0x05])
        + bytes([0x40, 0x81, 0x01])
        + bytes([0x81, 0x30, 0x11, 0x00, 0x2F, 0x01])
        + bytes([0x81, 0x49, 0x11, 0x02, 0x00])
        + bytes([0x40, 0x81, 0x01])
        + bytes([0x81, 0x30, 0x12, 0x00, 0x00, 0xD2, 0x01])
        + bytes([0x40, 0x82, 0x01, 0x20])
        + bytes([0x81, 0x30, 0x12, 0x00, 0x00, 0xC0, 0x01])
        + bytes([0x24, 0x36, 0x01, 0x01, 0x28, 0xFF, 0xFF, 0xFF, 0xFC, 0x0A])
        + bytes([0x70, 0x01, 0x6E])
        + bytes([0x70, 0x01, 0x6F])
        + bytes([0x81, 0x20])
        + bytes([0x70, 0x01, 0x75])
        + bytes([0x70, 0x01, 0x70])
        + bytes([0x70, 0x01, 0x21])
        + bytes([0x81, 0x20])
    )


# A real keystroke at the glass lands in the script as its token,
# and the replay presses the same key: record up, hear up -- the
# roundtrip that makes a menu-driven session replayable.
def test_glulx_keys_record_at_the_glass_and_replay(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    story = glulx_story(tmp_path, code=glulx_hears())
    target = tmp_path / "session.accept"

    class Key(str):
        name: str | None = None

        def __new__(cls, character: str, name: str | None = None) -> "Key":
            key = super().__new__(cls, character)
            key.name = name

            return key

    class Glass:
        width = 40
        height = 10
        normal = reverse = bold = italic = ""

        def __init__(self) -> None:
            self.keys = [Key("", "KEY_UP")]

        def move_xy(self, x: int, y: int) -> str:
            del x, y

            return ""

        def cbreak(self) -> AbstractContextManager[object]:
            return nullcontext()

        def inkey(self, timeout: float | None = None) -> object:
            del timeout

            return self.keys.pop(0)

    def scripted(
        blorb: object = None, recorder: Recorder | None = None
    ) -> TerminalFrontend:
        del blorb

        on_line = on_key = None

        if recorder is not None:
            on_line, on_key, _, _ = _recorded_glk(recorder)

        sink: list[str] = []

        return TerminalFrontend(
            cast("Terminal", Glass()), sink.append, on_line=on_line, on_key=on_key
        )

    monkeypatch.setattr("voxam.cli._terminal_frontend", scripted)

    recorded = main([str(story), "--record", str(target), "--seed", "7"])

    assert_that(recorded).is_equal_to(0)
    assert_that(target.read_text(encoding="utf-8")).contains("<up>")

    replayed = main(["--accept", str(target)])
    out = capsys.readouterr().out

    assert_that(replayed).is_equal_to(0)
    assert_that(out).contains("up!")
    assert_that(out).does_not_contain("\nno")

    # A live session without a recorder gets the glass unseamed.
    played = main([str(story)])

    assert_that(played).is_equal_to(0)


# A start function that opens a text grid, asks for one click,
# and answers "up!" when the click's x lands on cell 5 -- the
# smallest story that can hear the mouse. glulx_hears's skeleton,
# with the mouse request in place of the key request.
def glulx_awaits_click() -> bytes:
    return (
        bytes([0xC0, 0x00, 0x00])
        + bytes([0x40, 0x81, 0x00])
        + bytes([0x40, 0x81, 0x04])
        + bytes([0x40, 0x81, 0x00])
        + bytes([0x40, 0x81, 0x00])
        + bytes([0x40, 0x81, 0x00])
        + bytes([0x81, 0x30, 0x11, 0x00, 0x23, 0x05])
        + bytes([0x40, 0x81, 0x01])
        + bytes([0x81, 0x30, 0x11, 0x00, 0x2F, 0x01])
        + bytes([0x81, 0x49, 0x11, 0x02, 0x00])
        + bytes([0x40, 0x81, 0x01])
        + bytes([0x81, 0x30, 0x12, 0x00, 0x00, 0xD4, 0x01])
        + bytes([0x40, 0x82, 0x01, 0x20])
        + bytes([0x81, 0x30, 0x12, 0x00, 0x00, 0xC0, 0x01])
        + bytes([0x24, 0x36, 0x01, 0x01, 0x28, 0x00, 0x00, 0x00, 0x05, 0x0A])
        + bytes([0x70, 0x01, 0x6E])
        + bytes([0x70, 0x01, 0x6F])
        + bytes([0x81, 0x20])
        + bytes([0x70, 0x01, 0x75])
        + bytes([0x70, 0x01, 0x70])
        + bytes([0x70, 0x01, 0x21])
        + bytes([0x81, 0x20])
    )


# A real click at the pygame window lands in the script as
# <click x y> with the coordinates the game itself was told, and
# the replay answers the same mouse event with the same pair:
# record the click, hear the click -- the roundtrip the whole
# mouse era was for.
def test_glulx_clicks_record_at_the_window_and_replay(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    story = glulx_story(tmp_path, code=glulx_awaits_click())
    target = tmp_path / "session.accept"

    class Clicky(WindowStub):
        def click(self) -> tuple[int, int] | None:
            # 1-based window pixels; at the stub's 9x18 cell this
            # is the grid cell (5, 2).
            return (46, 37)

    def scripted(
        blorb: object = None,
        *,
        zoom: float | None = None,
        recorder: Recorder | None = None,
    ) -> GlulxGlassFrontend:
        del blorb, zoom

        on_line = on_key = on_click = None

        if recorder is not None:
            on_line, on_key, on_click, _ = _recorded_glk(recorder)

        return GlulxGlassFrontend(
            cast("PygameGlass", Clicky("\xfe")),
            on_line=on_line,
            on_key=on_key,
            on_click=on_click,
        )

    monkeypatch.setattr("voxam.cli._glass_frontend", scripted)

    recorded = main([str(story), "--graphics", "--record", str(target), "--seed", "7"])

    assert_that(recorded).is_equal_to(0)
    assert_that(target.read_text(encoding="utf-8")).contains("<click 5 2>")

    replayed = main(["--accept", str(target)])
    out = capsys.readouterr().out

    assert_that(replayed).is_equal_to(0)
    assert_that(out).contains("up!")
    assert_that(out).does_not_contain("no\n")

    # A live session without a recorder gets the window unseamed.
    played = main([str(story), "--graphics"])

    assert_that(played).is_equal_to(0)


# A start function that opens a text buffer, prints one linked
# character, asks for a hyperlink selection, and answers "up!"
# when the delivered value is 5 -- glulx_awaits_click's skeleton
# with set_hyperlink around the text and the hyperlink request in
# place of the mouse request.
def glulx_awaits_link() -> bytes:
    return (
        bytes([0xC0, 0x00, 0x00])
        + bytes([0x40, 0x81, 0x00])
        + bytes([0x40, 0x81, 0x03])
        + bytes([0x40, 0x81, 0x00])
        + bytes([0x40, 0x81, 0x00])
        + bytes([0x40, 0x81, 0x00])
        + bytes([0x81, 0x30, 0x11, 0x00, 0x23, 0x05])
        + bytes([0x40, 0x81, 0x01])
        + bytes([0x81, 0x30, 0x11, 0x00, 0x2F, 0x01])
        + bytes([0x81, 0x49, 0x11, 0x02, 0x00])
        + bytes([0x40, 0x81, 0x05])
        + bytes([0x81, 0x30, 0x12, 0x00, 0x01, 0x00, 0x01])
        + bytes([0x70, 0x01, 0x4C])
        + bytes([0x40, 0x81, 0x00])
        + bytes([0x81, 0x30, 0x12, 0x00, 0x01, 0x00, 0x01])
        + bytes([0x40, 0x81, 0x01])
        + bytes([0x81, 0x30, 0x12, 0x00, 0x01, 0x02, 0x01])
        + bytes([0x40, 0x82, 0x01, 0x20])
        + bytes([0x81, 0x30, 0x12, 0x00, 0x00, 0xC0, 0x01])
        + bytes([0x24, 0x36, 0x01, 0x01, 0x28, 0x00, 0x00, 0x00, 0x05, 0x0A])
        + bytes([0x70, 0x01, 0x6E])
        + bytes([0x70, 0x01, 0x6F])
        + bytes([0x81, 0x20])
        + bytes([0x70, 0x01, 0x75])
        + bytes([0x70, 0x01, 0x70])
        + bytes([0x70, 0x01, 0x21])
        + bytes([0x81, 0x20])
    )


# A real link click at the pygame window lands in the script as
# <link n> with the value the game itself was told, and the replay
# answers the same hyperlink event with the same value: select the
# link, hear the link.
def test_glulx_links_record_at_the_window_and_replay(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    story = glulx_story(tmp_path, code=glulx_awaits_link())
    target = tmp_path / "session.accept"

    class Linky(WindowStub):
        def click(self) -> tuple[int, int] | None:
            # 1-based window pixels, atop the linked 'L' on the
            # buffer's bottom row.
            return (5, 420)

    def scripted(
        blorb: object = None,
        *,
        zoom: float | None = None,
        recorder: Recorder | None = None,
    ) -> GlulxGlassFrontend:
        del blorb, zoom

        on_line = on_key = on_link = None

        if recorder is not None:
            on_line, on_key, _, on_link = _recorded_glk(recorder)

        return GlulxGlassFrontend(
            cast("PygameGlass", Linky("\xfe")),
            on_line=on_line,
            on_key=on_key,
            on_link=on_link,
        )

    monkeypatch.setattr("voxam.cli._glass_frontend", scripted)

    recorded = main([str(story), "--graphics", "--record", str(target), "--seed", "7"])

    assert_that(recorded).is_equal_to(0)
    assert_that(target.read_text(encoding="utf-8")).contains("<link 5>")

    replayed = main(["--accept", str(target)])
    out = capsys.readouterr().out

    assert_that(replayed).is_equal_to(0)
    assert_that(out).contains("up!")
    assert_that(out).does_not_contain("no\n")

    # A live session without a recorder gets the window unseamed.
    played = main([str(story), "--graphics"])

    assert_that(played).is_equal_to(0)


# An Infocom story plays under its own name: the header's IFID
# finds the catalog, the caption reaches the terminal's title bar
# when a terminal is listening -- and never a pipe, since a
# transcript is not a title bar. The unknown stay untitled,
# quietly, unreadable files included.
def test_infocom_stories_play_under_their_names(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plain = broken_story(tmp_path, bytes([0xBA]))

    assert_that(_titled(plain)).is_none()
    assert_that(_titled(tmp_path / "missing.z3")).is_none()

    data = bytearray(plain.read_bytes())
    data[0x02:0x04] = (88).to_bytes(2, "big")
    data[0x12:0x18] = b"840726"
    plain.write_bytes(bytes(data))

    assert_that(_titled(plain)).is_equal_to("Zork 1 — Voxam")

    # A piped session runs titled but writes no escape.
    played = main(["--plain", str(plain)])

    assert_that(played).is_equal_to(0)
    assert_that(capsys.readouterr().out).does_not_contain("\x1b]0;")

    monkeypatch.setattr("sys.stdout.isatty", lambda: False)
    _entitle_terminal("Zork 1 — Voxam")

    assert_that(capsys.readouterr().out).is_empty()

    monkeypatch.setattr("sys.stdout.isatty", lambda: True)
    _entitle_terminal(None)

    assert_that(capsys.readouterr().out).is_empty()

    _entitle_terminal("Zork 1 — Voxam")

    assert_that(capsys.readouterr().out).contains("\x1b]0;Zork 1 — Voxam\x07")


# --babel speaks the treaty for both machines -- no Z-only
# refusal here: a Z-code story answers its legacy identity, a
# Glulx story its own, junk is honestly neither, a second report
# is refused, and the session flags have nothing to do.
def test_babel_reports_ifids(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    story = broken_story(tmp_path, bytes([0xBA]))

    assert_that(main(["--babel", str(story)])).is_equal_to(0)
    assert_that(capsys.readouterr().out).contains("IFID: ZCODE-0-------")

    assert_that(main(["--babel", str(glulx_story(tmp_path))])).is_equal_to(0)
    assert_that(capsys.readouterr().out).contains("IFID: GLULX-")

    junk = tmp_path / "junk.dat"
    junk.write_bytes(b"MZ" + bytes(200))

    assert_that(main(["--babel", str(junk)])).is_equal_to(2)
    assert_that(capsys.readouterr().out).contains("neither Z-code nor Glulx")

    assert_that(main(["--babel", "--header", str(story)])).is_equal_to(2)
    assert_that(capsys.readouterr().out).contains("pick one")

    assert_that(main(["--babel"])).is_equal_to(2)
    assert_that(capsys.readouterr().out).contains("needs a story file")

    assert_that(main(["--babel", "--trace", "t.trace", str(story)])).is_equal_to(2)
    assert_that(capsys.readouterr().out).contains("only reads the story")

    assert_that(main(["--babel", str(tmp_path / "missing.z5")])).is_equal_to(2)
    assert_that(capsys.readouterr().out).contains("voxam:")


# The static reports are Z-Machine instruments; a Glulx story gets
# a plain refusal instead of a version-70 riddle.
def test_the_static_reports_decline_glulx(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = main(["--header", str(glulx_story(tmp_path))])

    assert_that(exit_code).is_equal_to(2)
    assert_that(capsys.readouterr().out).contains("is Glulx")


# The session files ride every command-line session: selecting the
# transcript stream writes story.scr beside the story, and the old
# frontier exit is gone -- SCRIPT is just a command that works.
def test_the_transcript_lands_beside_the_story(tmp_path: Path) -> None:
    story = broken_story(tmp_path, bytes([0xF3, 0x7F, 0x02, 0xB2, 0xB5, 0xC5, 0xBA]))
    exit_code = main([str(story)])

    assert_that(exit_code).is_equal_to(0)
    assert_that(story.with_suffix(".scr").read_text(encoding="utf-8")).is_equal_to("hi")


# Stream 4 records the typed command into story.cmd -- and input
# stream 1 plays such a file back, echoing the command to the
# screen while the empty stdin proves no keyboard was consulted.
def test_commands_record_and_play_back_beside_the_story(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO("north\n"))

    recording = reading_story(tmp_path)
    data = bytearray(recording.read_bytes())
    data[0x40:0x4A] = bytes(
        [0xF3, 0x7F, 0x04, 0xE4, 0x0F, 0x00, 0x50, 0x00, 0x58, 0xBA]
    )
    recording.write_bytes(bytes(data))

    assert_that(main([str(recording)])).is_equal_to(0)
    assert_that(recording.with_suffix(".cmd").read_text(encoding="utf-8")).is_equal_to(
        "north\n"
    )

    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    data[0x40:0x4A] = bytes(
        [0xF4, 0x7F, 0x01, 0xE4, 0x0F, 0x00, 0x50, 0x00, 0x58, 0xBA]
    )
    recording.write_bytes(bytes(data))

    assert_that(main([str(recording)])).is_equal_to(0)
    assert_that(capsys.readouterr().out).contains("north")


# The byte 0x00 decodes as 2OP:0, which no version defines, so the
# machine raises mid-run and the CLI exits 2.
def test_reports_a_story_that_breaks_the_rules(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = main([str(broken_story(tmp_path, bytes([0x00, 0x01, 0x02])))])

    assert_that(exit_code).is_equal_to(2)
    assert_that(capsys.readouterr().out).contains("2OP:0")


# The painted frontend steps aside without a terminal to paint on:
# a piped stdout keeps the plain stream (§8.4).
def test_no_terminal_means_no_screen_frontend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("sys.stdout.isatty", lambda: False)

    assert_that(_screen_frontend(3)).is_none()


# At a real terminal with the blessed extra installed, the painted
# frontend takes over.
def test_a_terminal_selects_the_screen_frontend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)

    assert_that(_screen_frontend(3)).is_instance_of(ScreenFrontend)


# Without the blessed extra the import fails and the plain stream
# carries on: the screen is optional, the game is not.
def test_a_missing_extra_falls_back_to_plain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)
    monkeypatch.setitem(sys.modules, "voxam.painter", None)

    assert_that(_screen_frontend(3)).is_none()


# --plain keeps the stream frontend even where a screen would do.
def test_plain_flag_keeps_the_stream(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO("look\n"))
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)

    exit_code = main(["--plain", str(reading_story(tmp_path))])

    assert_that(exit_code).is_equal_to(0)
    assert_that(capsys.readouterr().out).does_not_contain(chr(27))


def _png_chunk(name: bytes, payload: bytes) -> bytes:
    return (
        len(payload).to_bytes(4, "big")
        + name
        + payload
        + zlib.crc32(name + payload).to_bytes(4, "big")
    )


def tiny_png() -> bytes:
    """One red truecolour pixel."""

    header = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)

    return (
        SIGNATURE
        + _png_chunk(b"IHDR", header)
        + _png_chunk(b"IDAT", zlib.compress(bytes([0, 255, 0, 0])))
        + _png_chunk(b"IEND", b"")
    )


def covered_story(
    tmp_path: Path,
    pictures: list[tuple[int, Chunk]],
    fspc: int | None = None,
) -> Path:
    """Package the reading story and pictures into one .zblorb."""

    story = reading_story(tmp_path, version=4).read_bytes()
    entries = [(b"Exec", 0, Chunk(b"ZCOD", story))] + [
        (b"Pict", number, piece) for number, piece in pictures
    ]
    body = bytearray(b"IFRS")
    index_chunk_size = 8 + 4 + len(entries) * 12
    position = 8 + 4 + index_chunk_size
    index = bytearray(len(entries).to_bytes(4, "big"))
    pieces = bytearray()

    for usage, number, piece in entries:
        framed = chunk(piece.chunk_id, piece.payload)
        index += usage + number.to_bytes(4, "big") + position.to_bytes(4, "big")
        pieces += framed
        position += len(framed)

    body += chunk(b"RIdx", bytes(index)) + pieces

    if fspc is not None:
        body += chunk(b"Fspc", fspc.to_bytes(4, "big"))

    path = tmp_path / "covered.zblorb"
    path.write_bytes(chunk(b"FORM", bytes(body)))

    return path


# A PNG cover in the story's Blorb shows before play at a painted
# terminal: half-block art, a keypress, then the story.
def test_a_png_cover_shows_before_play(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    keys = iter(["x", *"look\n"])

    monkeypatch.setattr("sys.stdout.isatty", lambda: True)
    monkeypatch.setattr(
        "blessed.Terminal.inkey", lambda _self, _timeout=None: next(keys)
    )

    path = covered_story(tmp_path, [(1, Chunk(b"PNG ", tiny_png()))])
    exit_code = main([str(path)])

    assert_that(exit_code).is_equal_to(0)
    assert_that(capsys.readouterr().out).contains("▀")


# --pixels draws the same cover as sixel graphics: real pixels for
# a terminal that answers the capability question and reports its
# cell size.
def test_pixels_draws_the_cover_as_sixel(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    keys = iter([*"\x1b[?4c", *"\x1b[6;16;8t", "x", *"look\n"])

    monkeypatch.setattr("sys.stdout.isatty", lambda: True)
    monkeypatch.setattr(
        "blessed.Terminal.inkey", lambda _self, _timeout=None: next(keys)
    )

    path = covered_story(tmp_path, [(1, Chunk(b"PNG ", tiny_png()))])
    exit_code = main(["--pixels", str(path)])

    assert_that(exit_code).is_equal_to(0)
    assert_that(capsys.readouterr().out).contains("\x1bPq")


# A cover Voxam cannot draw -- Zork 1 ships a JPEG -- earns a note
# and the story plays on: art is a courtesy, never a gate.
def test_a_foreign_cover_earns_a_note(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    keys = iter("look\n")

    monkeypatch.setattr("sys.stdout.isatty", lambda: True)
    monkeypatch.setattr(
        "blessed.Terminal.inkey", lambda _self, _timeout=None: next(keys)
    )

    path = covered_story(tmp_path, [(1, Chunk(b"JPEG", b"\xff\xd8jpeg"))], fspc=1)
    exit_code = main([str(path)])

    assert_that(exit_code).is_equal_to(0)
    assert_that(capsys.readouterr().out).contains("cannot draw")


# A PNG that will not decode earns the same note.
def test_an_unreadable_cover_earns_a_note(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    keys = iter("look\n")

    monkeypatch.setattr("sys.stdout.isatty", lambda: True)
    monkeypatch.setattr(
        "blessed.Terminal.inkey", lambda _self, _timeout=None: next(keys)
    )

    path = covered_story(tmp_path, [(1, Chunk(b"PNG ", b"not a png"))], fspc=1)
    exit_code = main([str(path)])

    assert_that(exit_code).is_equal_to(0)
    assert_that(capsys.readouterr().out).contains("cannot be drawn")


# A crowd of pictures with no Fspc offers no cover at all: play
# begins without ceremony.
def test_a_crowd_of_pictures_offers_no_cover(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    keys = iter("look\n")

    monkeypatch.setattr("sys.stdout.isatty", lambda: True)
    monkeypatch.setattr(
        "blessed.Terminal.inkey", lambda _self, _timeout=None: next(keys)
    )

    path = covered_story(
        tmp_path,
        [(1, Chunk(b"PNG ", tiny_png())), (2, Chunk(b"PNG ", tiny_png()))],
    )
    exit_code = main([str(path)])

    assert_that(exit_code).is_equal_to(0)
    assert_that(capsys.readouterr().out).does_not_contain("▀")


# With a terminal claimed, play runs through the painted frontend:
# the story's text arrives wrapped in cursor movements, and typing
# reaches the story as raw keystrokes through read_line's own line
# editor -- the terminal's cooked input is never consulted.
def test_screen_play_runs_through_the_painter(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    keys = iter("look\n")

    monkeypatch.setattr("sys.stdout.isatty", lambda: True)
    monkeypatch.setattr(
        "blessed.Terminal.inkey", lambda _self, _timeout=None: next(keys)
    )

    exit_code = main([str(reading_story(tmp_path, version=4))])

    assert_that(exit_code).is_equal_to(0)


def sounded_blorb() -> Blorb:
    """A Blorb holding one tiny decodable AIFF sound."""

    common = Chunk(
        b"COMM",
        struct.pack(">hLh", 1, 1, 8) + struct.pack(">HQ", 16383 + 14, 22050 << 49),
    )
    sound_data = Chunk(b"SSND", bytes(8) + b"\x01")
    form = Chunk(b"FORM", write_form(b"AIFF", (common, sound_data))[8:])

    return Blorb((Resource(b"Snd ", 3, form),), None, None, frozenset())


# The speaker wants a Blorb with decodable sounds, the sounddevice
# extra, and a real output device; each miss is silence, never a
# halt -- and an undecodable sound earns its note first.
def test_the_speaker_needs_sounds_a_package_and_a_device(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert_that(_speaker(None)).is_none()
    assert_that(_speaker(Blorb((), None, None, frozenset()))).is_none()

    foreign = Blorb(
        (Resource(b"Snd ", 3, Chunk(b"OGGV", b"ogg")),), None, None, frozenset()
    )

    assert_that(_speaker(foreign)).is_none()
    assert_that(capsys.readouterr().out).contains("cannot be decoded")

    monkeypatch.setitem(sys.modules, "sounddevice", None)

    assert_that(_speaker(sounded_blorb())).is_none()


# A Blorb's Reso standard window size travels to the pygame
# doorway, so the opened window keeps the art's proportions --
# the spec's own window-sizing hint (Blorb: The Resolution
# Chunk); without a Blorb the classic shape stands.
def test_graphics_windows_take_the_standard_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def opened(
        standard: tuple[int, int] | None = None,
        _version: int = 0,
        zoom: float | None = None,
    ) -> WindowStub:
        captured["standard"] = standard
        captured["zoom"] = zoom

        return WindowStub("")

    monkeypatch.setattr("voxam.glass.open_pygame_glass", opened)

    shaped = Blorb((), None, None, frozenset(), resolution=Resolution(320, 200))

    assert_that(_graphics_frontend(6, shaped, 0.5)).is_not_none()
    assert_that(captured["standard"]).is_equal_to((320, 200))
    assert_that(captured["zoom"]).is_equal_to(0.5)

    assert_that(_graphics_frontend(6, None)).is_not_none()
    assert_that(captured["standard"]).is_none()
    assert_that(captured["zoom"]).is_none()


# The gallery helper hands the window only real art: no Blorb, or
# one without drawable pictures, is None -- which keeps the
# frontend's picture claim honest (§11.1.4).
def test_the_gallery_helper_filters_empty_blorbs() -> None:
    assert_that(_gallery(None)).is_none()
    assert_that(_gallery(sounded_blorb())).is_none()

    rect = Chunk(b"Rect", (10).to_bytes(4, "big") + (4).to_bytes(4, "big"))
    pictured = Blorb((Resource(b"Pict", 1, rect),), None, None, frozenset(), release=27)
    gallery = cast("Gallery", _gallery(pictured))

    assert_that(gallery).is_instance_of(Gallery)
    assert_that(gallery.count).is_equal_to(1)
    assert_that(gallery.release).is_equal_to(27)


# With sounddevice present, a device-less box stays silent and a
# real output device earns a speaker.
def test_the_speaker_arrives_with_a_device(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakePortAudioError(Exception):
        pass

    def refuse(**_arguments: str) -> None:
        raise FakePortAudioError

    deaf = types.SimpleNamespace(
        PortAudioError=FakePortAudioError, query_devices=refuse
    )

    monkeypatch.setitem(sys.modules, "sounddevice", deaf)

    assert_that(_speaker(sounded_blorb())).is_none()

    hearing = types.SimpleNamespace(
        PortAudioError=FakePortAudioError,
        query_devices=lambda **_arguments: {"name": "stub"},
    )

    monkeypatch.setitem(sys.modules, "sounddevice", hearing)

    assert_that(_speaker(sounded_blorb())).is_instance_of(Speaker)


# --record captures live play: it cannot join a replay, and it
# needs a story to record.
def test_record_refuses_scripts_and_bare_banners(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "out.accept"

    exit_code = main(["--record", str(target), "--accept", "x.accept"])

    assert_that(exit_code).is_equal_to(2)
    assert_that(capsys.readouterr().out).contains("a script already is one")

    exit_code = main(["--record", str(target)])

    assert_that(exit_code).is_equal_to(2)
    assert_that(capsys.readouterr().out).contains("needs a story")


# A recorded plain session becomes a replayable script: the game,
# a freshly rolled seed, and the typed commands -- and replaying
# it draws no warnings.
def test_a_recorded_session_replays(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    story = reading_story(tmp_path)
    target = tmp_path / "session.accept"

    monkeypatch.setattr("sys.stdin", io.StringIO("look\n"))

    exit_code = main(["--plain", "--record", str(target), str(story)])
    out = capsys.readouterr().out

    assert_that(exit_code).is_equal_to(0)
    assert_that(out).contains("Recording to")

    content = target.read_text(encoding="utf-8")

    assert_that(content).contains("! GAME=reads.z3")
    assert_that(content).contains("! SEED=")
    assert_that(content).contains("look")

    exit_code = main(["--accept", str(target)])
    out = capsys.readouterr().out

    assert_that(exit_code).is_equal_to(0)
    assert_that(out).does_not_contain("looks refused")


# An explicit --seed is the one written down, and an existing
# target file is refused before any play begins.
def test_recording_honours_the_seed_and_refuses_overwrites(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    story = reading_story(tmp_path)
    target = tmp_path / "session.accept"

    monkeypatch.setattr("sys.stdin", io.StringIO("look\n"))

    exit_code = main(["--plain", "--seed", "42", "--record", str(target), str(story)])

    assert_that(exit_code).is_equal_to(0)
    assert_that(target.read_text(encoding="utf-8")).contains("! SEED=42")

    exit_code = main(["--plain", "--record", str(target), str(story)])

    assert_that(exit_code).is_equal_to(2)
    assert_that(capsys.readouterr().out).contains("never overwrites")


# The key tee writes presses into the script and lets an expired
# timeout pass unrecorded.
def test_recorded_keys_tee_into_the_script(tmp_path: Path) -> None:
    target = tmp_path / "keys.accept"
    recorder = Recorder(target, game=tmp_path / "story.z5", seed=7, warn=print)
    presses = iter([None, "\x81", "\n"])
    source = _recorded_keys(recorder, lambda _timeout: next(presses))

    assert_that(source(0.5)).is_none()
    assert_that(source(None)).is_equal_to("\x81")
    assert_that(source(None)).is_equal_to("\n")

    recorder.close()

    lines = target.read_text(encoding="utf-8").splitlines()

    assert_that(lines).contains("<up>")
    assert_that(lines[-1]).is_equal_to(">")


# A click records as its token -- single or double -- with the
# glass's own coordinates; a click with no position takes the
# loud unrecorded path.
def test_recorded_clicks_tee_into_the_script(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "clicks.accept"
    recorder = Recorder(target, game=tmp_path / "story.z6", seed=7, warn=print)
    presses = iter(["\xfe", "\xfd", "\xfe"])
    positions = iter([(12, 5), (12, 6), None])
    source = _recorded_keys(
        recorder, lambda _timeout: next(presses), lambda: next(positions)
    )

    assert_that(source(None)).is_equal_to("\xfe")
    assert_that(source(None)).is_equal_to("\xfd")
    assert_that(source(None)).is_equal_to("\xfe")

    recorder.close()

    written = target.read_text(encoding="utf-8")

    assert_that(written).contains("<click 12 5>")
    assert_that(written).contains("<double-click 12 6>")
    assert_that(written).does_not_contain("\xfd")
    assert_that(written).does_not_contain("\xfe")
    assert_that(capsys.readouterr().out).contains("no position")


# A replayed <click x y> presses the mouse: the machine hears the
# click's input code with the script's coordinates, and the
# transcript shows a click was pressed.
def test_replayed_clicks_press_the_mouse(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # read_char device 1 to the stack, then quit -- enough to hear
    # one click. The stack store matters: this bare story has no
    # globals table, and a global store would land in the header.
    story = broken_story(tmp_path, bytes([0xF6, 0x7F, 0x01, 0x00, 0xBA]), version=5)
    script = tmp_path / "session.accept"

    script.write_text(
        f"! GAME={story.name}\n! SEED=1\n\n<click 7 9>\n", encoding="utf-8"
    )

    replayed = main(["--accept", str(script)])
    out = capsys.readouterr().out

    assert_that(replayed).is_equal_to(0)
    assert_that(out).contains("<click>")


# Timed-read lines tee through the recorder too: an expiry is not
# a line and records nothing, while the completed line lands in
# the script exactly once.
def test_recorded_ticks_tee_completed_lines(tmp_path: Path) -> None:
    target = tmp_path / "ticks.accept"
    recorder = Recorder(target, game=tmp_path / "story.z5", seed=7, warn=print)
    answers = iter([None, "look"])
    source = _recorded_ticks(recorder, lambda _seconds: next(answers))

    assert_that(source(1.0)).is_none()
    assert_that(source(1.0)).is_equal_to("look")

    recorder.close()

    lines = target.read_text(encoding="utf-8").splitlines()

    assert_that(lines[-1]).is_equal_to("look")


# Painted play records through the same tees: the line assembled
# by the painter's own editor lands in the script.
def test_a_painted_session_records_its_lines(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    keys = iter("look\n")

    monkeypatch.setattr("sys.stdout.isatty", lambda: True)
    monkeypatch.setattr(
        "blessed.Terminal.inkey", lambda _self, _timeout=None: next(keys)
    )

    target = tmp_path / "painted.accept"
    exit_code = main(["--record", str(target), str(reading_story(tmp_path, version=4))])

    assert_that(exit_code).is_equal_to(0)
    assert_that(target.read_text(encoding="utf-8")).contains("look")


# --resume replays the recording and appends the continuation to
# the same file: the first session records a command past the
# empty script; a second resume replays that command into the
# game's single read and quits with nothing left to append.
def test_a_resumed_recording_grows_at_the_end(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    story = reading_story(tmp_path)
    script = accept_file(tmp_path, f"! GAME={story}\n! SEED=9\n")

    monkeypatch.setattr("sys.stdin", io.StringIO("look\n"))

    exit_code = main(["--resume", str(script)])

    assert_that(exit_code).is_equal_to(0)
    assert_that(script.read_text(encoding="utf-8")).contains("look")

    before = script.read_text(encoding="utf-8")

    monkeypatch.setattr("sys.stdin", io.StringIO(""))

    exit_code = main(["--resume", str(script)])

    assert_that(exit_code).is_equal_to(0)
    assert_that(script.read_text(encoding="utf-8")).is_equal_to(before)


# The resume flag travels alone -- no other script flags, no
# story, no --seed: the recording keeps its own dice -- and it
# continues only a recording that exists.
def test_resume_refuses_conflicts_and_ghosts(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "session.accept"

    assert_that(main(["--resume", str(target), "--accept", "x"])).is_equal_to(2)
    assert_that(capsys.readouterr().out).contains("drop the other flags")

    assert_that(main(["--resume", str(target), "story.z3"])).is_equal_to(2)
    assert_that(capsys.readouterr().out).contains("names its own game")

    assert_that(main(["--resume", str(target), "--seed", "5"])).is_equal_to(2)
    assert_that(capsys.readouterr().out).contains("own dice")

    assert_that(main(["--resume", str(target)])).is_equal_to(2)
    assert_that(capsys.readouterr().out).contains("does not exist")


# --regtest runs a script in-process: a passing suite exits 0 in
# silence beyond the test names, a failing one speaks the
# reference's FAILED line and exits 1, an unusable script exits 2,
# and the flag travels alone.
def test_regtest_runs_in_process(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    story = refusing_story(tmp_path)
    passing = tmp_path / "pass.regtest"
    passing.write_text(
        f"** game: {story}\n* answer\n> frotz\nyou must use a verb\n",
        encoding="utf-8",
    )

    assert_that(main(["--regtest", str(passing)])).is_equal_to(0)
    assert_that(capsys.readouterr().out).contains("* answer")

    failing = tmp_path / "fail.regtest"
    failing.write_text(
        f"** game: {story}\n* answer\n> frotz\nbucket of cheese\n",
        encoding="utf-8",
    )

    assert_that(main(["--regtest", str(failing)])).is_equal_to(1)
    assert_that(capsys.readouterr().out).contains("FAILED: 1 errors")

    broken = tmp_path / "broken.regtest"
    broken.write_text("* nameless\n> look\n", encoding="utf-8")

    assert_that(main(["--regtest", str(broken)])).is_equal_to(2)
    assert_that(capsys.readouterr().out).contains("names no game")


def test_regtest_travels_alone(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "suite.regtest"

    assert_that(main(["--regtest", str(target), "--accept", "x"])).is_equal_to(2)
    assert_that(capsys.readouterr().out).contains("drop the other flags")

    assert_that(main(["--regtest", str(target), "story.z3"])).is_equal_to(2)
    assert_that(capsys.readouterr().out).contains("names its own game")

    assert_that(main(["--regtest", str(target), "--seed", "7"])).is_equal_to(2)
    assert_that(capsys.readouterr().out).contains("interpreter line")


class WindowStub:
    """A glass for CLI tests: scripted keys, recorded nothing."""

    columns = 80
    lines = 24
    cell_width = 9
    cell_height = 18

    def __init__(self, keys: str) -> None:
        self.keys = list(keys)

    def paint(
        self,
        row: int,
        column: int,
        text: str,
        ink: tuple[int, int, int],
        paper: tuple[int, int, int],
        *,
        bold: bool,
        italic: bool,
        graphics: bool,
    ) -> None:
        """Discard: the CLI tests never inspect the blits."""

    def text(
        self,
        line: int,
        column: int,
        characters: str,
        ink: tuple[int, int, int],
        paper: tuple[int, int, int],
        *,
        bold: bool,
        italic: bool,
        graphics: bool,
    ) -> None:
        """Discard: the CLI tests never inspect the blits."""

    def fill(
        self,
        line: int,
        column: int,
        height: int,
        width: int,
        colour: tuple[int, int, int],
    ) -> None:
        """Discard: the CLI tests never inspect the fills."""

    def shift(self, line: int, column: int, height: int, width: int, rise: int) -> None:
        """Discard: the CLI tests never inspect the scrolls."""

    def present(self) -> None:
        """Discard: the CLI tests never inspect the frame."""

    def key(self, timeout: float | None) -> str | None:
        del timeout

        return self.keys.pop(0) if self.keys else None

    def picture(self, rows: object) -> None:
        """Discard: the CLI tests never show a cover."""

    def photograph(self, data: bytes) -> object:
        """Decode nothing: the CLI tests never draw a JPEG."""

        del data

        return None

    def entitle(self, title: str) -> None:
        """Discard: the CLI tests never read the title bar."""

        del title


# --graphics plays through the pygame window: with the doorway
# monkeypatched to a stub glass, the whole session runs through
# the real GraphicsFrontend.
def test_graphics_play_runs_through_the_window(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "voxam.glass.open_pygame_glass",
        lambda _standard=None, _version=0, _zoom=None: WindowStub("look\n"),
    )

    exit_code = main(["--graphics", str(reading_story(tmp_path, version=4))])

    assert_that(exit_code).is_equal_to(0)


# --zoom is a fraction of the desktop; anything outside 0 to 1 is
# refused before a window could open at it.
def test_zoom_takes_a_fraction(capsys: pytest.CaptureFixture[str]) -> None:
    assert_that(main(["--zoom", "1.5", "story.z6"])).is_equal_to(2)
    assert_that(capsys.readouterr().out).contains("fraction of the desktop")


# Without the pygame extra, the explicit flag earns a note and the
# session falls back -- here to the plain stream, no terminal
# claimed.
def test_graphics_without_the_extra_notes_and_falls_back(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "pygame", None)
    monkeypatch.setattr("sys.stdin", io.StringIO("look\n"))

    exit_code = main(["--graphics", str(reading_story(tmp_path))])

    assert_that(exit_code).is_equal_to(0)
    assert_that(capsys.readouterr().out).contains("needs the pygame-ce extra")


# --graphics on a Glulx story plays through the pygame window:
# with the doorway monkeypatched to a stub glass, the whole
# session runs through the real GlassFrontend -- no terminal
# needed, so a piped session still earns the window.
def test_glulx_graphics_play_runs_through_the_window(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "voxam.glulx.glk.glass.open_pygame_glass",
        lambda _standard=None, _version=0, _zoom=None: WindowStub(""),
    )

    exit_code = main(["--graphics", str(glulx_story(tmp_path))])

    assert_that(exit_code).is_equal_to(0)
    assert_that(capsys.readouterr().out).contains("checksum verified")


# Without the pygame extra, a Glulx --graphics earns the same note
# the Z-Machine's does, and the session falls back down the glass
# chain -- here to the stdio display, no terminal claimed.
def test_glulx_graphics_without_the_extra_notes_and_falls_back(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "pygame", None)

    exit_code = main(["--graphics", str(glulx_story(tmp_path))])

    assert_that(exit_code).is_equal_to(0)
    assert_that(capsys.readouterr().out).contains("needs the pygame-ce extra")


# The Blorb's Reso standard window size travels to the pygame
# doorway for Glulx as it does for the Z-Machine, the window wears
# the glulx badge, and a recorder rides in through the seams.
def test_the_glulx_window_takes_the_standard_shape(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def opened(
        standard: tuple[int, int] | None = None,
        version: int | str = 0,
        zoom: float | None = None,
    ) -> WindowStub:
        captured["standard"] = standard
        captured["version"] = version
        captured["zoom"] = zoom

        return WindowStub("")

    monkeypatch.setattr("voxam.glulx.glk.glass.open_pygame_glass", opened)

    shaped = Blorb((), None, None, frozenset(), resolution=Resolution(320, 200))
    recorder = Recorder(
        tmp_path / "session.accept", game=tmp_path / "story.ulx", seed=7, warn=print
    )

    assert_that(_glass_frontend(shaped, zoom=0.5, recorder=recorder)).is_not_none()

    recorder.close()

    assert_that(captured["standard"]).is_equal_to((320, 200))
    assert_that(captured["version"]).is_equal_to("glulx")
    assert_that(captured["zoom"]).is_equal_to(0.5)

    assert_that(_glass_frontend(None)).is_not_none()
    assert_that(captured["standard"]).is_none()
    assert_that(captured["zoom"]).is_none()

    # The stub window, like any glass without pygame's decoders,
    # honestly photographs nothing -- and wears any name quietly.
    assert_that(WindowStub("").photograph(b"\xff\xd8photo")).is_none()
    WindowStub("").entitle("Trinity — Voxam")


# The pygame window brings a speaker along when the Blorb's sounds
# and the audio device allow, and claims sound exactly then -- the
# same courtesy _speaker pays every other glass.
def test_the_glulx_window_brings_a_speaker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "voxam.glulx.glk.glass.open_pygame_glass",
        lambda *_args, **_kwargs: WindowStub(""),
    )

    bare = _glass_frontend(None)

    if bare is None:
        pytest.fail("the window opened")

    assert_that(bare.sound).is_false()

    speaker = Speaker({}, frozenset(), open_sounddevice_stream)

    monkeypatch.setattr("voxam.cli._speaker", lambda _blorb: speaker)

    sounding = _glass_frontend(None)

    if sounding is None:
        pytest.fail("the window opened")

    assert_that(sounding.sound).is_true()


def test_graphics_and_plain_are_two_glasses(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = main(["--graphics", "--plain", str(reading_story(tmp_path))])

    assert_that(exit_code).is_equal_to(2)
    assert_that(capsys.readouterr().out).contains("two different glasses")


# A like-named MG1/EG1/CG1 file beside the story hangs its art the
# pre-Blorb way; an unreadable one earns a note and no gallery,
# and no sidecar at all is quietly nothing (pix2gif's convention).
def test_picture_file_sidecars_hang_or_decline(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    story = tmp_path / "poker.z6"
    story.write_bytes(b"")

    assert_that(_picture_file_gallery(story)).is_none()

    empty_book = bytes([0, 0, 0, 0, 0, 0, 0, 0, 14, 0, 0, 0, 0, 0, 7, 0])
    (tmp_path / "poker.eg1").write_bytes(empty_book)

    book = _picture_file_gallery(story)

    assert_that(book).is_not_none()
    assert_that(book.count if book else -1).is_zero()

    (tmp_path / "poker.eg1").write_bytes(b"XX")

    assert_that(_picture_file_gallery(story)).is_none()
    assert_that(capsys.readouterr().out).contains("picture file cannot be read")
