"""Tests for the Å-machine's wire face and its stdio serving."""

import io
import json
import zlib
from pathlib import Path

import pytest
from assertpy import assert_that

from voxam.aamachine.glkote import GlkOteFrontend, fronted, serve
from voxam.aamachine.machine import Machine
from voxam.aamachine.story import SUMMED, Story
from voxam.errors import GlkOteError
from voxam.glkote import Stanza
from voxam.glulx.glk.resources import Resources
from voxam.iff import chunk as iff_chunk
from voxam.web import AAMachineSession

FIXTURES = Path(__file__).parent.parent / "fixtures"

INIT: Stanza = {
    "type": "init",
    "gen": 0,
    "metrics": {"width": 800, "height": 600},
    "support": ["timer", "hyperlinks", "graphics", "graphicswin"],
}


def storied(name: str = "cloak-rel2") -> Story:
    """One vendored story, parsed."""

    return Story((FIXTURES / f"{name}.aastory").read_bytes())


def sessioned(name: str = "cloak-rel2") -> AAMachineSession:
    """One story behind the burst model, already born."""

    session = AAMachineSession(storied(name), Resources(None), seed=7)
    session.answer(INIT)

    return session


def texted(update: Stanza) -> str:
    """Every buffer character in an update, flattened."""

    pieces = []

    for entry in update.get("content", []):
        for paragraph in entry.get("text", []):
            for run in paragraph.get("content", []):
                pieces.append(run.get("text", ""))

            pieces.append("\n")

    return "".join(pieces)


# The first update carries the doorway card, the opening prose,
# one buffer window, and a line input request.
def test_the_first_update_opens_the_document() -> None:
    session = AAMachineSession(storied(), Resources(None), seed=7)
    update = session.answer(INIT)

    assert_that(update["type"]).is_equal_to("update")
    assert_that(update["windows"]).is_length(1)
    assert_that(update["windows"][0]["type"]).is_equal_to("buffer")
    assert_that(update["input"][0]["type"]).is_equal_to("line")

    told = texted(update)

    assert_that(told).contains("Cloak of Darkness")
    assert_that(told).contains("by Linus Åkesson")
    assert_that(told).contains("Foyer of the Opera House")


# A line event walks a turn; the next update carries the fresh
# prose and asks again.
def test_a_line_event_walks_a_turn() -> None:
    session = sessioned()
    update = session.answer({"type": "line", "gen": 1, "window": 1, "value": "west"})

    assert_that(texted(update)).contains("Cloakroom")
    assert_that(update["input"][0]["type"]).is_equal_to("line")


# Quitting ends the session with the exit-flagged update and no
# input request.
def test_a_quit_exits_the_update() -> None:
    session = sessioned()
    session.answer({"type": "line", "gen": 1, "window": 1, "value": "quit"})
    update = session.answer({"type": "line", "gen": 2, "window": 1, "value": "y"})

    assert_that(update.get("exit")).is_true()
    assert_that(update.get("input", [])).is_empty()


# A key wait asks for a keystroke, and a char event answers it --
# names and characters both.
def test_char_events_answer_key_waits() -> None:
    session = sessioned("codepoints")
    update = session.answer(INIT)

    assert_that(update["input"][0]["type"]).is_equal_to("char")

    update = session.answer({"type": "char", "gen": 1, "window": 1, "value": "q"})

    assert_that(update.get("exit")).is_true()


# A named key travels by its reserved code; an unknown name earns
# the pass and the wait stands.
def test_named_keys_travel_and_unknown_names_pass() -> None:
    session = sessioned("codepoints")
    session.answer(INIT)
    update = session.answer({"type": "char", "gen": 1, "window": 1, "value": "func12"})

    assert_that(update).is_equal_to({"type": "pass"})

    update = session.answer({"type": "char", "gen": 1, "window": 1, "value": "down"})

    assert_that(update["type"]).is_equal_to("update")


# Misaimed input -- a line where a key is wanted, or input after
# the exit -- earns the polite pass, never a fault.
def test_misaimed_events_earn_the_pass() -> None:
    session = sessioned("codepoints")
    session.answer(INIT)
    update = session.answer({"type": "line", "gen": 1, "window": 1, "value": "q"})

    assert_that(update).is_equal_to({"type": "pass"})


# A refresh redraws the whole picture without disturbing the
# machine: the full scrollback returns behind a clear.
def test_a_refresh_redraws_whole() -> None:
    session = sessioned()
    session.answer({"type": "line", "gen": 1, "window": 1, "value": "west"})
    update = session.answer({"type": "refresh", "gen": 2})

    told = texted(update)

    assert_that(told).contains("Foyer of the Opera House")
    assert_that(told).contains("Cloakroom")


# An arrange event moves the window's box; one with no metrics
# passes.
def test_an_arrange_resizes_the_window() -> None:
    session = sessioned()
    update = session.answer(
        {"type": "arrange", "gen": 1, "metrics": {"width": 400, "height": 300}}
    )

    assert_that(update["windows"][0]["width"]).is_equal_to(400)

    update = session.answer({"type": "arrange", "gen": 1})

    assert_that(update).is_equal_to({"type": "pass"})


# An init without metrics is refused at the door.
def test_an_init_without_metrics_is_refused() -> None:
    face = fronted(storied())

    with pytest.raises(GlkOteError, match=r"metrics carry no size"):
        face.begin({"type": "init", "gen": 0})


# A story without META opens without the card.
def test_a_cardless_story_opens_plain() -> None:
    face = GlkOteFrontend(storied("aa-exercise"))
    face.begin(INIT)

    machine = Machine(storied("aa-exercise"), face.voice, seed=1234)
    face.waiting = machine.run()
    update = face.render(exit=True)

    assert_that(texted(update)).contains("Welcome to the Å-machine!")


# The stdio server drives a whole session: init in, updates out,
# a line delivered, the exit flagged.
def test_serve_drives_a_session_whole() -> None:
    events = [
        INIT,
        {"type": "line", "gen": 1, "window": 1, "value": "quit"},
        {"type": "refresh", "gen": 2},
        {"type": "arrange", "gen": 2, "metrics": {"width": 500}},
        {"type": "char", "gen": 2, "window": 1, "value": "x"},
        {"type": "line", "gen": 2, "window": 1, "value": "y"},
    ]
    reader = io.StringIO("".join(json.dumps(event) + "\n" for event in events))
    writer = io.StringIO()

    assert_that(serve(storied(), reader, writer, seed=7)).is_true()

    updates = [json.loads(line) for line in writer.getvalue().splitlines()]

    assert_that(updates[0]["type"]).is_equal_to("update")
    assert_that(updates[-1].get("exit")).is_true()
    assert_that(any(entry == {"type": "pass"} for entry in updates)).is_true()


# A conversation that opens with anything but an init is refused
# as the protocol's own error stanza.
def test_serve_refuses_a_wrong_opening() -> None:
    reader = io.StringIO(json.dumps({"type": "line", "value": "x"}) + "\n")
    writer = io.StringIO()

    assert_that(serve(storied(), reader, writer)).is_false()
    assert_that(writer.getvalue()).contains("opens with an init event")


# A stream that is not JSON answers the same way.
def test_serve_refuses_broken_json() -> None:
    writer = io.StringIO()

    assert_that(serve(storied(), io.StringIO("{broken\n"), writer)).is_false()
    assert_that(writer.getvalue()).contains("not JSON")


# A stream that simply ends -- before the init's answer or midway
# -- ends the session cleanly.
def test_serve_survives_a_closed_stream() -> None:
    writer = io.StringIO()
    events = json.dumps(INIT) + "\n"

    assert_that(serve(storied(), io.StringIO(events), writer, seed=7)).is_true()


# A META blurb joins the doorway card, its line feeds honored.
def test_a_blurb_joins_the_card() -> None:
    lang = (
        (8).to_bytes(2, "big")
        + (8).to_bytes(2, "big")
        + (9).to_bytes(2, "big")
        + (10).to_bytes(2, "big")
        + b"\x00\x00\x00\x00\x00"
    )
    summed = {b"LANG": lang, b"DICT": b"\x00\x00", b"LOOK": b"\x00\x00"}
    crc = 0

    for name in SUMMED:
        crc = zlib.crc32(summed.get(name, b""), crc)

    head = (
        bytes([0, 5, 2, 0])
        + (1).to_bytes(2, "big")
        + b"260827"
        + crc.to_bytes(4, "big")
        + bytes(6)
    )
    meta = bytes([2]) + b"\x01Tale\x00" + b"\x04Told\x10whole.\x00"
    pieces = [iff_chunk(b"HEAD", head), iff_chunk(b"META", meta)]

    for name in SUMMED:
        pieces.append(iff_chunk(name, summed.get(name, b"")))

    story = Story(iff_chunk(b"FORM", b"AAVM" + b"".join(pieces)))
    face = GlkOteFrontend(story)
    face.begin(INIT)
    update = face.render()

    told = texted(update)

    assert_that(told).contains("Tale")
    assert_that(told).contains("Told\nwhole.")
    assert_that(update.get("input", [])).is_empty()


# An event before any init has spoken earns the unopened error.
def test_an_event_before_init_is_unopened() -> None:
    session = AAMachineSession(storied(), Resources(None), seed=7)
    update = session.answer({"type": "line", "gen": 1, "value": "west"})

    assert_that(update["type"]).is_equal_to("error")
    assert_that(update["message"]).contains("opens with an init event")
