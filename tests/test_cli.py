import io
import runpy
import struct
import sys
import types
import zlib
from collections.abc import Callable
from pathlib import Path

import pytest
from assertpy import assert_that

from voxam.acceptance import Recorder
from voxam.blorb import Blorb, Resource
from voxam.cli import _recorded_keys, _screen_frontend, _speaker, main
from voxam.iff import Chunk, chunk, write_form
from voxam.painter import ScreenFrontend
from voxam.png import SIGNATURE
from voxam.speaker import Speaker


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


# get_cursor decodes fine but has no handler yet -- ZIPTEST named
# it a frontier -- so the CLI surfaces the report and exits 1.
def test_reports_the_implementation_frontier(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = main(
        [str(broken_story(tmp_path, bytes([0xF0, 0x7F, 0x00]), version=4))]
    )

    assert_that(exit_code).is_equal_to(1)
    assert_that(capsys.readouterr().out).contains("not yet implemented")


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
