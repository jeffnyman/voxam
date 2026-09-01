"""The Z face of GlkOte: the screen model composed, reads delivered."""

import io
import json
import struct
import zlib
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from assertpy import assert_that

from voxam.blorb import Blorb
from voxam.errors import GlkOteError, ZMachineScreenError
from voxam.frontend import Status
from voxam.gallery import Gallery
from voxam.glkote import KEPT_PARAGRAPHS
from voxam.glulx.glk.resources import Resources
from voxam.iff import chunk
from voxam.screen import BOLD, FIXED_PITCH, ITALIC, REVERSE, ROMAN
from voxam.zmachine.glkote import (
    ADVANCE,
    PASS,
    STAND,
    GlkOteFrontend,
    StageFrontend,
    _named,
    _plotted,
    fronted,
    serve,
)
from voxam.zmachine.header import SCREEN_COLUMNS, SCREEN_LINES
from voxam.zmachine.machine import Machine
from voxam.zmachine.story import Story

METRICS: dict[str, Any] = {
    "width": 800,
    "height": 480,
    "gridcharwidth": 10,
    "gridcharheight": 20,
}

INIT = {
    "type": "init",
    "gen": 0,
    "support": ["timer"],
    "metrics": METRICS,
}

TEXT_BUFFER = 0x120
PARSE_BUFFER = 0x140
DICTIONARY_BASE = 0x150
ROUTINE_BASE = 0x70

# aread text-buffer parse-buffer -> store; then quit.
AREAD = bytes([0xE4, 0x0F, 0x01, 0x20, 0x01, 0x40, 0x10, 0xBA])

# sread with a §15 time and routine pair, Version 4.
TIMED = bytes([0xE4, 0x05, 0x01, 0x20, 0x01, 0x40, 0x0A, 0x1C, 0xBA])

# read_char -> store; then quit.
READ_CHAR = bytes([0xF6, 0x7F, 0x01, 0x10, 0xBA])

# Interrupt routines: mark a global then return false or true.
MARK_THEN_FALSE = bytes([0x00, 0x0D, 0x11, 0x63, 0xB1])
MARK_THEN_TRUE = bytes([0x00, 0x0D, 0x11, 0x63, 0xB0])

# sound_effect 3 start volume-word routine, then the aread: the
# routine operand is ROUTINE_BASE packed for Version 5.
SOUNDED = bytes([0xF5, 0x51, 0x03, 0x02, 0x00, 0x08, 0x1C]) + AREAD


def banded_resources(*, front: bool = False, record: bytes | None = None) -> Resources:
    """Resources holding one 320x96 PNG as picture 8, maybe more."""

    art = (
        b"\x89PNG\r\n\x1a\n"
        + (13).to_bytes(4, "big")
        + b"IHDR"
        + (320).to_bytes(4, "big")
        + (96).to_bytes(4, "big")
    )
    fspc = chunk(b"Fspc", (8).to_bytes(4, "big")) if front else b""
    told = chunk(b"IFmd", record) if record is not None else b""
    ridx = chunk(b"RIdx", (1).to_bytes(4, "big") + b"\x00" * 12)
    offset = 12 + len(ridx) + len(fspc) + len(told)
    index = (
        (1).to_bytes(4, "big")
        + b"Pict"
        + (8).to_bytes(4, "big")
        + offset.to_bytes(4, "big")
    )

    return Resources(
        Blorb.parse(
            chunk(
                b"FORM",
                b"IFRS" + chunk(b"RIdx", index) + fspc + told + chunk(b"PNG ", art),
            )
        )
    )


def opened(
    code_machine: Callable[..., Machine],
    program: bytes = AREAD,
    version: int = 5,
    routine: bytes | None = None,
    resources: Resources | None = None,
) -> tuple[GlkOteFrontend, Machine]:
    """A measured frontend fronting a machine at its first read."""

    frontend = GlkOteFrontend(version, resources)

    frontend.begin(INIT)

    machine = code_machine(program, version=version, frontend=frontend)
    frontend.machine = machine

    machine.memory.write_byte(TEXT_BUFFER, 21)
    machine.memory.write_byte(PARSE_BUFFER, 5)
    machine.memory.write_word(0x08, DICTIONARY_BASE)

    for offset, value in enumerate([2, ord(","), ord("."), 0, 0, 0]):
        machine.memory.write_byte(DICTIONARY_BASE + offset, value)

    if routine is not None:
        for offset, value in enumerate(routine):
            machine.memory.write_byte(ROUTINE_BASE + offset, value)

    return frontend, machine


# The init measures the screen in cells before any machine boots
# over the display; metrics with no size are refused, and a render
# with no machine behind it is loud.
def test_the_init_measures_the_screen() -> None:
    frontend = GlkOteFrontend(5)

    frontend.begin(INIT)

    assert_that(frontend.screen_columns).is_equal_to(80)
    assert_that(frontend.screen_lines).is_equal_to(24)
    assert_that(frontend.has_timed_input).is_true()

    quiet = GlkOteFrontend(5)

    quiet.begin({"type": "init", "gen": 0, "metrics": {"width": 80, "height": 24}})

    assert_that(quiet.has_timed_input).is_false()

    with pytest.raises(GlkOteError, match="carry no size"):
        GlkOteFrontend(5).begin({"type": "init", "gen": 0, "metrics": {}})

    with pytest.raises(GlkOteError, match="fronts no machine"):
        frontend.render()


# Every §8.7 dress has its protocol name, reverse video ranking
# first -- the page's own CSS wears user1 as inverse.
def test_styles_wear_their_names() -> None:
    assert_that(_named(ROMAN)).is_equal_to("normal")
    assert_that(_named(ITALIC)).is_equal_to("emphasized")
    assert_that(_named(BOLD)).is_equal_to("subheader")
    assert_that(_named(BOLD | ITALIC)).is_equal_to("alert")
    assert_that(_named(FIXED_PITCH)).is_equal_to("preformatted")
    assert_that(_named(REVERSE | BOLD)).is_equal_to("user1")


# The lower window streams styled runs while the upper window
# grids through the model: a split appears with its rows, and the
# suspended read rides the update as the buffer's own field.
def test_the_lower_streams_and_the_upper_grids(
    code_machine: Callable[..., Machine],
) -> None:
    frontend, machine = opened(code_machine)

    frontend.write("Hello ")
    frontend.set_style(ITALIC)
    frontend.write("slanted")
    frontend.set_style(0)
    frontend.split_window(1)
    frontend.set_window(1)
    frontend.set_cursor(1, 1)
    frontend.write("Status")
    frontend.set_window(0)

    update = frontend.render()

    assert_that([held["type"] for held in update["windows"]]).is_equal_to(
        ["buffer", "grid"]
    )
    assert_that(update["windows"][1]["gridheight"]).is_equal_to(1)
    assert_that(update["content"][0]["text"][0]["content"]).is_equal_to(
        [
            {"style": "normal", "text": "Hello "},
            {"style": "emphasized", "text": "slanted"},
        ]
    )
    assert_that(update["content"][1]["lines"][0]["content"]).is_equal_to(
        [{"style": "normal", "text": "Status"}]
    )

    machine.run()

    asked = frontend.render()

    assert_that(asked["input"]).is_equal_to(
        [{"id": 1, "type": "line", "maxlen": 21, "gen": 2}]
    )


# The quieter protocol ops each find their place: rectangles
# stamp the grid or stack in the stream, erasures of the grid
# leave the buffer standing, a lower erase-line unsays nothing,
# and fonts and cursors ride the model's own ledger.
def test_the_quieter_ops_find_their_places(
    code_machine: Callable[..., Machine],
) -> None:
    frontend, _ = opened(code_machine)

    frontend.split_window(1)
    frontend.set_window(1)
    frontend.set_cursor(1, 1)
    frontend.write_rectangle(["AB"])
    frontend.erase_line()
    frontend.set_window(0)
    frontend.write_rectangle(["row"])
    frontend.erase_line()
    frontend.set_font(4)
    frontend.erase_window(1)

    assert_that(frontend.cursor_position()[0]).is_equal_to(1)

    update = frontend.render()

    assert_that(update["content"][0]["text"][0]["content"][0]["text"]).is_equal_to(
        "row"
    )
    assert_that(update["content"][0]).does_not_contain_key("clear")


# The Version 1 to 3 status line rides the grid's first row in
# reverse video, the model's own §8.2 formatting.
def test_the_status_line_rides_the_grid(
    code_machine: Callable[..., Machine],
) -> None:
    frontend, _ = opened(code_machine, version=3)

    frontend.show_status(Status("West of House", 0, 1, time_game=False))

    update = frontend.render()

    line = update["content"][-1]["lines"][0]["content"][0]

    assert_that(line["style"]).is_equal_to("user1")
    assert_that(line["text"]).contains("West of House")
    assert_that(line["text"]).contains("Score: 0")


# An erasure of the lower half clears the buffer whole; the typed
# line echoes in the input dress with its newline, since the
# machine never echoes.
def test_erasures_and_echoes(code_machine: Callable[..., Machine]) -> None:
    frontend, machine = opened(code_machine)

    frontend.write("before")
    frontend.erase_window(-1)

    update = frontend.render()

    assert_that(update["content"]).is_equal_to([{"id": 1, "clear": True}])

    machine.run()
    frontend.render()

    verdict = frontend.accept({"type": "line", "gen": 2, "window": 1, "value": "go"})

    assert_that(verdict).is_equal_to(ADVANCE)

    machine.run()

    landed = frontend.render(exit=True)

    assert_that(landed["content"][0]["text"][0]["content"]).is_equal_to(
        [{"style": "input", "text": "go"}]
    )


# A read under a §10.5.2.1 terminating table offers the function
# keys the wire can name -- a cursor-key entry stays legal but
# unnameable in the protocol's vocabulary -- and the key that ends
# the line stores its own code with nothing echoed, since only a
# return-ended read prints its return (§15 read).
def test_a_terminator_rides_the_wire(code_machine: Callable[..., Machine]) -> None:
    frontend, machine = opened(code_machine)

    machine.memory.write_word(0x2E, 0x1A0)

    for offset, code in enumerate((135, 133, 129, 0)):
        machine.memory.write_byte(0x1A0 + offset, code)

    machine.run()

    asked = frontend.render()

    assert_that(asked["input"]).is_equal_to(
        [
            {
                "id": 1,
                "type": "line",
                "maxlen": 21,
                "gen": 1,
                "terminators": ["func1", "func3"],
            }
        ]
    )

    verdict = frontend.accept(
        {"type": "line", "gen": 1, "window": 1, "value": "go", "terminator": "func3"}
    )

    assert_that(verdict).is_equal_to(ADVANCE)
    assert_that(machine.memory.read_word(0x100)).is_equal_to(135)

    machine.run()

    landed = frontend.render(exit=True)

    assert_that(landed).does_not_contain_key("content")


# A keystroke read arms the grid for clicks -- the whole clickable
# surface, since buffers take none -- and a click lands as §10.3's
# code 254: a wrong window passes with the read standing, while a
# story without a header extension still hears the click, it just
# cannot ask where.
def test_a_click_lands_on_a_keystroke_read(
    code_machine: Callable[..., Machine],
) -> None:
    frontend, machine = opened(code_machine, program=READ_CHAR)

    frontend.split_window(1)
    machine.run()

    asked = frontend.render()

    assert_that(asked["input"]).is_equal_to(
        [
            {"id": 1, "type": "char", "gen": 1},
            {"id": 2, "mouse": True},
        ]
    )

    stray = frontend.accept({"type": "mouse", "gen": 1, "window": 9, "x": 0, "y": 0})

    assert_that(stray).is_equal_to(PASS)

    verdict = frontend.accept({"type": "mouse", "gen": 1, "window": 2, "x": 4, "y": 0})

    assert_that(verdict).is_equal_to(ADVANCE)
    assert_that(machine.memory.read_word(0x100)).is_equal_to(254)


# A line read under a table naming the click code arms the grid
# too, and the click ends the line: the typed text rides the event
# as the buffer's partial input -- the field carries no §15
# preload, since the story prints its own -- the machine appends
# it after the held text, and the click's cell coordinates land
# one step over in the header extension, which counts the screen
# from (1,1).
def test_a_click_ends_a_line_read(code_machine: Callable[..., Machine]) -> None:
    frontend, machine = opened(code_machine)

    frontend.split_window(1)
    machine.memory.write_word(0x2E, 0x1A0)
    machine.memory.write_byte(0x1A0, 254)
    machine.memory.write_byte(0x1A1, 0)
    machine.memory.write_word(0x36, 0x1B0)
    machine.memory.write_word(0x1B0, 2)
    machine.memory.write_byte(TEXT_BUFFER + 1, 2)
    machine.memory.write_byte(TEXT_BUFFER + 2, ord("g"))
    machine.memory.write_byte(TEXT_BUFFER + 3, ord("o"))

    machine.run()

    asked = frontend.render()

    assert_that(asked["input"]).is_equal_to(
        [
            {"id": 1, "type": "line", "maxlen": 21, "gen": 1},
            {"id": 2, "mouse": True},
        ]
    )

    verdict = frontend.accept(
        {
            "type": "mouse",
            "gen": 1,
            "window": 2,
            "x": 3,
            "y": 0,
            "partial": {"1": " hi"},
        }
    )

    assert_that(verdict).is_equal_to(ADVANCE)
    assert_that(machine.memory.read_byte(TEXT_BUFFER + 1)).is_equal_to(5)
    assert_that(machine.memory.read_word(0x100)).is_equal_to(254)
    assert_that(machine.memory.read_word(0x1B2)).is_equal_to(4)
    assert_that(machine.memory.read_word(0x1B4)).is_equal_to(1)


# A click nothing can hear passes with the wait standing: with no
# grid there is nowhere to land, and a line read whose table never
# named the click code leaves it unheard.
def test_a_click_nothing_hears_passes(code_machine: Callable[..., Machine]) -> None:
    frontend, machine = opened(code_machine)

    machine.run()
    frontend.render()

    gridless = frontend.accept({"type": "mouse", "gen": 1, "window": 2, "x": 0, "y": 0})

    assert_that(gridless).is_equal_to(PASS)

    armed, lined = opened(code_machine)

    armed.split_window(1)
    lined.run()
    armed.render()

    verdict = armed.accept({"type": "mouse", "gen": 1, "window": 2, "x": 0, "y": 0})

    assert_that(verdict).is_equal_to(PASS)
    assert_that(lined.waiting).is_not_none()


# Named keys land as their §3.8 codes; a name the table lacks, and
# a key ZSCII cannot spell, pass with the read standing.
def test_named_keys_land(code_machine: Callable[..., Machine]) -> None:
    frontend, machine = opened(code_machine, program=READ_CHAR, version=4)

    machine.run()
    frontend.render()

    assert_that(
        frontend.accept({"type": "char", "gen": 1, "window": 1, "value": "borogove"})
    ).is_equal_to(PASS)
    assert_that(
        frontend.accept({"type": "char", "gen": 1, "window": 1, "value": "λ"})
    ).is_equal_to(PASS)
    assert_that(
        frontend.accept({"type": "char", "gen": 1, "window": 1, "value": "escape"})
    ).is_equal_to(ADVANCE)
    assert_that(machine.memory.read_word(0x100)).is_equal_to(27)


# A timed read feeds the display's clock and restarts it for a
# fresh read; a tick fires the interrupt and stands, a true return
# advances, and a tick with no timed read passes.
def test_ticks_stand_and_advance(code_machine: Callable[..., Machine]) -> None:
    frontend, machine = opened(
        code_machine, program=TIMED, version=4, routine=MARK_THEN_FALSE
    )

    machine.run()

    update = frontend.render()

    assert_that(update["timer"]).is_equal_to(1000)
    assert_that(frontend.accept({"type": "timer", "gen": 1})).is_equal_to(STAND)
    assert_that(machine.memory.read_word(0x102)).is_equal_to(0x63)
    assert_that(
        frontend.accept({"type": "line", "gen": 1, "window": 1, "value": "on"})
    ).is_equal_to(ADVANCE)

    ended, ending = opened(
        code_machine, program=TIMED, version=4, routine=MARK_THEN_TRUE
    )

    ending.run()
    ended.render()

    assert_that(ended.accept({"type": "timer", "gen": 1})).is_equal_to(ADVANCE)

    idle, resting = opened(code_machine)

    resting.run()
    idle.render()

    assert_that(idle.accept({"type": "timer", "gen": 1})).is_equal_to(PASS)


# A grid that closes and reopens is a new window with a new id --
# the protocol forbids reuse -- and an arrange remeasures for the
# next boot while the picture stands. The teardown is §8.7.3.3's
# whole-screen erasure: a bare unsplit holds until the next input,
# the quote-box courtesy.
def test_the_grid_comes_and_goes_with_new_names(
    code_machine: Callable[..., Machine],
) -> None:
    frontend, _ = opened(code_machine)

    frontend.split_window(1)

    first = frontend.render()

    assert_that(first["windows"][1]["id"]).is_equal_to(2)

    frontend.erase_window(-1)

    gone = frontend.render()

    assert_that([held["type"] for held in gone["windows"]]).is_equal_to(["buffer"])

    frontend.split_window(1)

    again = frontend.render()

    assert_that(again["windows"][1]["id"]).is_equal_to(3)

    verdict = frontend.accept(
        {"type": "arrange", "gen": 3, "metrics": {"width": 400, "height": 200}}
    )

    assert_that(verdict).is_equal_to(STAND)
    assert_that(frontend.accept({"type": "external", "gen": 3})).is_equal_to(PASS)


# The grid's box carries the display's interior margins on top of
# its rows (GlkOte: The Metrics Object) -- a box of bare rows clips
# its bottom and floats the buffer up into the status line -- and
# with no grid at all the buffer starts back at the very top.
def test_the_grid_box_wears_the_margins(
    code_machine: Callable[..., Machine],
) -> None:
    frontend, _ = opened(code_machine)

    frontend.begin(
        {
            "type": "init",
            "gen": 0,
            "metrics": {
                "width": 800,
                "height": 480,
                "gridcharwidth": 10,
                "gridcharheight": 20,
                "gridmarginx": 20,
                "gridmarginy": 12,
            },
        }
    )

    frontend.split_window(2)

    split = frontend.render()

    assert_that(split["windows"][1]["top"]).is_equal_to(0)
    assert_that(split["windows"][1]["height"]).is_equal_to(52)
    assert_that(split["windows"][0]["top"]).is_equal_to(52)
    assert_that(split["windows"][0]["height"]).is_equal_to(428)

    frontend.erase_window(-1)

    alone = frontend.render()

    assert_that(alone["windows"][0]["top"]).is_equal_to(0)
    assert_that(alone["windows"][0]["height"]).is_equal_to(480)


def sounding_resources(*, looped: bool = False) -> Resources:
    """Resources with a tiny AIFF as sound 3, maybe looping forever."""

    aiff_form = chunk(
        b"FORM",
        b"AIFF"
        + chunk(
            b"COMM",
            struct.pack(">hLh", 1, 2, 8) + struct.pack(">HQ", 16397, 1 << 63),
        )
        + chunk(b"SSND", struct.pack(">LL", 0, 0) + b"\x01\xfe"),
    )
    loop = chunk(b"Loop", struct.pack(">LL", 3, 0)) if looped else b""
    ridx = chunk(b"RIdx", (1).to_bytes(4, "big") + b"\x00" * 12)
    first = 12 + len(ridx) + len(loop)
    index = (
        (1).to_bytes(4, "big")
        + b"Snd "
        + (3).to_bytes(4, "big")
        + first.to_bytes(4, "big")
    )

    return Resources(
        Blorb.parse(chunk(b"FORM", b"IFRS" + chunk(b"RIdx", index) + loop + aiff_form))
    )


def hearing(
    code_machine: Callable[..., Machine],
    resources: Resources,
    program: bytes = AREAD,
    support: list[str] | None = None,
) -> tuple[GlkOteFrontend, Machine]:
    """A face granted the sound word, a machine at its buffers."""

    frontend = GlkOteFrontend(5, resources)

    frontend.begin(
        {**INIT, "support": support if support is not None else ["timer", "sound"]}
    )

    machine = code_machine(program, version=5, frontend=frontend)
    frontend.machine = machine

    machine.memory.write_byte(TEXT_BUFFER, 21)
    machine.memory.write_byte(PARSE_BUFFER, 5)

    for offset, value in enumerate(MARK_THEN_FALSE):
        machine.memory.write_byte(ROUTINE_BASE + offset, value)

    return frontend, machine


# The §9 sounds speak the wire's dialect: a play op carries the
# AIFF re-wrapped as a WAVE data: url on the one channel with the
# volume in eighths, zero repeats spell forever, Version 3's
# silence is answered by the Loop chunk, a stop lands only on the
# number sounding, and the bleeps ride as the display's own
# oscillator notes. Without the display's word nothing rides at
# all, and without a Blorb nothing is claimed even with it.
def test_z_sounds_speak_the_dialect(code_machine: Callable[..., Machine]) -> None:
    frontend, _ = hearing(code_machine, sounding_resources(looped=True))

    assert_that(frontend.has_sounds).is_true()
    assert_that(frontend.play_sound(3, 4, None)).is_true()
    assert_that(frontend.play_sound(3, 8, 0)).is_true()
    assert_that(frontend.play_sound(3, 8, 2)).is_true()
    assert_that(frontend.play_sound(9, 8, 1)).is_false()

    frontend.stop_sound(7)
    frontend.stop_sound(3)
    frontend.stop_sound(None)
    frontend.bleep(1)
    frontend.bleep(2)

    ops = frontend.render()["sounds"]

    assert_that([held.get("op") for held in ops]).is_equal_to(
        ["play", "play", "play", "stop", "bleep", "bleep"]
    )
    assert_that(ops[0]["url"]).starts_with("data:audio/wav;base64,")
    assert_that((ops[0]["repeats"], ops[0]["volume"])).is_equal_to((-1, 0.5))
    assert_that((ops[1]["repeats"], ops[1]["volume"])).is_equal_to((-1, 1.0))
    assert_that(ops[2]["repeats"]).is_equal_to(2)
    assert_that(ops[4]["bleep"]).is_equal_to(1)
    assert_that(ops[5]["bleep"]).is_equal_to(2)

    quiet, muted = hearing(code_machine, sounding_resources(), support=["timer"])

    assert_that(quiet.has_sounds).is_false()

    quiet.bleep(1)
    muted.run()

    assert_that(quiet.render()).does_not_contain_key("sounds")

    bare = GlkOteFrontend(5)

    bare.begin({**INIT, "support": ["sound"]})

    assert_that(bare.has_sounds).is_false()
    assert_that(bare.play_sound(3, 8, 1)).is_false()


# The whole §9.4 round over the wire: sound_effect starts the
# sample and keeps its routine, the wire's finish report fires the
# end-of-sound routine through the machine's own loop with the
# read still standing, and a report for a sound since stopped or
# replaced means nothing, §9.4.4's own rule.
def test_the_end_of_sound_routine_fires(
    code_machine: Callable[..., Machine],
) -> None:
    frontend, machine = hearing(code_machine, sounding_resources(), program=SOUNDED)

    machine.run()

    played = frontend.render()["sounds"][0]

    assert_that(played["sound"]).is_equal_to(3)
    assert_that((played["repeats"], played["volume"])).is_equal_to((1, 1.0))

    stray = frontend.accept({"type": "sound", "gen": 1, "channel": 1, "sound": 9})

    assert_that(stray).is_equal_to(PASS)

    verdict = frontend.accept({"type": "sound", "gen": 1, "channel": 1, "sound": 3})

    assert_that(verdict).is_equal_to(STAND)
    assert_that(machine.memory.read_word(0x102)).is_equal_to(0x63)
    assert_that(machine.waiting).is_not_none()

    silent = frontend.accept({"type": "sound", "gen": 1, "channel": 1, "sound": 3})

    assert_that(silent).is_equal_to(PASS)


# A display that lost its picture asks for it whole: the refresh
# event is accepted ahead of the generation gate -- a lost display
# is out of sync by definition -- and earns an update complete in
# content: every window, the buffer's kept scrollback behind a
# clear, the grid's every row with the blank ones as bare line
# numbers, the input field stamped anew at the new generation, and
# a running timer renamed. The keeping is bounded: a long session
# replays its recent paragraphs, not its whole life.
def test_a_refresh_earns_the_whole_picture(
    code_machine: Callable[..., Machine],
) -> None:
    frontend, machine = opened(code_machine)

    frontend.write("Once upon a time.\n")
    frontend.split_window(2)
    frontend.set_window(1)
    frontend.set_cursor(1, 1)
    frontend.write("Status")
    frontend.set_window(0)
    frontend.write("And then more.\n")
    machine.run()
    frontend.render()

    assert_that(frontend.accept({"type": "refresh", "gen": 99})).is_equal_to(STAND)

    whole = frontend.render()

    assert_that([held["type"] for held in whole["windows"]]).is_equal_to(
        ["buffer", "grid"]
    )

    texted = next(entry for entry in whole["content"] if entry["id"] == 1)

    assert_that(texted["clear"]).is_true()
    assert_that(
        [para["content"][0]["text"] for para in texted["text"] if "content" in para]
    ).is_equal_to(["Once upon a time.", "And then more."])

    gridded = next(entry for entry in whole["content"] if "lines" in entry)

    assert_that(gridded["lines"][0]["content"][0]["text"]).contains("Status")
    assert_that(gridded["lines"][1]).is_equal_to({"line": 1})
    assert_that(whole["input"][0]["gen"]).is_equal_to(whole["gen"])

    ticking, clock = opened(
        code_machine, program=TIMED, version=4, routine=MARK_THEN_FALSE
    )

    clock.run()
    ticking.render()
    ticking.accept({"type": "refresh", "gen": 1})

    assert_that(ticking.render()["timer"]).is_equal_to(1000)

    longwinded, teller = opened(code_machine)

    for number in range(KEPT_PARAGRAPHS + 10):
        longwinded.write(f"para {number}\n")

    teller.run()
    longwinded.render()
    longwinded.accept({"type": "refresh", "gen": 1})

    told = next(entry for entry in longwinded.render()["content"] if entry["id"] == 1)

    assert_that(told["text"]).is_length(KEPT_PARAGRAPHS)
    assert_that(told["text"][0]["content"][0]["text"]).is_equal_to("para 10")

    banded = GlkOteFrontend(5, banded_resources())

    banded.begin({**INIT, "support": ["timer", "graphicswin"]})

    artist = code_machine(AREAD, version=5, frontend=banded)
    banded.machine = artist

    banded.draw_arc_image(8, 12)
    banded.render()
    banded.accept({"type": "refresh", "gen": 5})

    hung = next(entry for entry in banded.render()["content"] if "draw" in entry)

    assert_that(hung["draw"][-1]["special"]).is_equal_to("image")


# An Inform quote box splits the upper window tall, writes, and
# shrinks the split back at once, trusting §8.6.1.2's no-clearing
# rule to leave the box standing on the screen -- so the grid
# stays at the turn's high water until the next input arrives,
# and a whole-screen erasure tears the box down with the split.
def test_a_quote_box_survives_the_shrink(
    code_machine: Callable[..., Machine],
) -> None:
    frontend, machine = opened(code_machine)

    frontend.split_window(3)
    frontend.set_window(1)
    frontend.set_cursor(2, 5)
    frontend.write("Will you read me a story?")
    frontend.set_window(0)
    frontend.split_window(1)

    update = frontend.render()

    assert_that(update["windows"][1]["gridheight"]).is_equal_to(3)

    boxed = next(
        line
        for entry in update["content"]
        if "lines" in entry
        for line in entry["lines"]
        if line["line"] == 1
    )

    assert_that(boxed["content"][0]["text"]).contains("Will you read me a story?")

    machine.run()
    frontend.render()
    frontend.accept({"type": "line", "gen": 2, "window": 1, "value": "go"})
    machine.run()

    shrunk = frontend.render(exit=True)

    assert_that(shrunk["windows"][1]["gridheight"]).is_equal_to(1)

    torn, _ = opened(code_machine)

    torn.split_window(3)
    torn.erase_window(-1)

    cleared = torn.render()

    assert_that([held["type"] for held in cleared["windows"]]).is_equal_to(["buffer"])

    # Version 3 keeps no high water: splitting clears the upper
    # window there (§8.6.1.1), so no box could survive anyway.
    classic, _ = opened(code_machine, version=3)

    classic.split_window(2)
    classic.split_window(0)

    plain = classic.render()

    assert_that(plain["windows"][1]["gridheight"]).is_equal_to(1)


# The §8.3 colours ride the wire under the display's own word:
# runs carry the shared palette's CSS ink, adjacent same-ink text
# coalesces, reverse video swaps ink and paper as every painted
# face swaps them, the grid's cells dress their spans through the
# model, and the model's background travels as both windows'
# paper -- Photopia's scenes bleed to the window's edge, not just
# under its letters. Without the word there is no claim at all.
def test_colours_ride_the_wire(code_machine: Callable[..., Machine]) -> None:
    frontend = GlkOteFrontend(5)

    frontend.begin({**INIT, "support": ["timer", "colors"]})

    machine = code_machine(AREAD, version=5, frontend=frontend)
    frontend.machine = machine

    assert_that(frontend.has_colours).is_true()

    frontend.set_colour(3, 1)
    frontend.write("red ")
    frontend.write("more")
    frontend.set_style(REVERSE)
    frontend.write("swap")
    frontend.set_style(0)
    frontend.set_colour(0, 6)
    frontend.write("sea")
    frontend.split_window(1)
    frontend.set_window(1)
    frontend.set_cursor(1, 1)
    frontend.write("Top")
    frontend.set_window(0)
    frontend.set_colour(1, 0)
    frontend.write("plain")

    update = frontend.render()

    assert_that(update["content"][0]["text"][0]["content"]).is_equal_to(
        [
            {"style": "normal", "text": "red more", "fg": "#cc0000"},
            {"style": "user1", "text": "swap", "bg": "#cc0000"},
            {"style": "normal", "text": "sea", "fg": "#cc0000", "bg": "#0000cc"},
            {"style": "normal", "text": "plain", "bg": "#0000cc"},
        ]
    )
    assert_that(update["content"][1]["lines"][0]["content"]).is_equal_to(
        [{"style": "normal", "text": "Top", "fg": "#cc0000", "bg": "#0000cc"}]
    )
    assert_that(update["windows"][0]["bg"]).is_equal_to("#0000cc")
    assert_that(update["windows"][1]["bg"]).is_equal_to("#0000cc")

    quiet = GlkOteFrontend(5)

    quiet.begin(INIT)

    assert_that(quiet.has_colours).is_false()


# The record's card joins the cover at the door: the title in the
# header dress, the headline and author emphasized, and the
# description's paragraphs blank-line separated -- needing no
# display grant, since a card is only text (Babel: The iFiction
# format).
def test_the_card_stands_at_the_door(code_machine: Callable[..., Machine]) -> None:
    record = (
        b"<ifindex><story><bibliographic><title>Tiny Case</title>"
        b"<headline>An interactive test</headline><author>A. Tester</author>"
        b"<description>One.<br/>Two.</description>"
        b"</bibliographic></story></ifindex>"
    )
    frontend = GlkOteFrontend(5, banded_resources(front=True, record=record))

    frontend.begin({**INIT, "support": ["timer", "graphics"]})

    machine = code_machine(AREAD, version=5, frontend=frontend)
    frontend.machine = machine

    text = frontend.render()["content"][0]["text"]

    assert_that(text[0]["content"][0]["special"]).is_equal_to("image")
    assert_that(text[1]["content"]).is_equal_to(
        [{"style": "header", "text": "Tiny Case"}]
    )
    assert_that(text[2]["content"]).is_equal_to(
        [{"style": "emphasized", "text": "An interactive test"}]
    )
    assert_that(text[3]["content"]).is_equal_to(
        [{"style": "emphasized", "text": "A. Tester"}]
    )
    assert_that(text[5]["content"]).is_equal_to([{"style": "normal", "text": "One."}])
    assert_that(text[7]["content"]).is_equal_to([{"style": "normal", "text": "Two."}])


# The doorway courtesy over the wire: a Blorb's Fspc cover stands
# at the top of the story's text -- once, before anything the
# machine prints, its own paragraph -- when the display grants
# bare graphics; without the grant, or without a cover, the story
# simply opens plain.
def test_the_cover_stands_at_the_door(code_machine: Callable[..., Machine]) -> None:
    frontend = GlkOteFrontend(5, banded_resources(front=True))

    frontend.begin({**INIT, "support": ["timer", "graphics"]})

    machine = code_machine(AREAD, version=5, frontend=frontend)
    frontend.machine = machine

    frontend.write("Hello")

    text = frontend.render()["content"][0]["text"]
    cover = text[0]["content"][0]

    assert_that(cover["special"]).is_equal_to("image")
    assert_that(cover["image"]).is_equal_to(8)
    assert_that(cover["alignment"]).is_equal_to("inlineup")
    assert_that((cover["width"], cover["height"])).is_equal_to((320, 96))
    assert_that(cover["url"]).starts_with("data:image/png;base64,")
    assert_that(text[1]["content"]).is_equal_to([{"style": "normal", "text": "Hello"}])

    plain = GlkOteFrontend(5, banded_resources(front=True))

    plain.begin(INIT)

    ungranted = code_machine(AREAD, version=5, frontend=plain)
    plain.machine = ungranted

    plain.write("Hello")

    opening = plain.render()["content"][0]["text"][0]["content"]

    assert_that(opening).is_equal_to([{"style": "normal", "text": "Hello"}])

    coverless = GlkOteFrontend(5, banded_resources())

    coverless.begin({**INIT, "support": ["timer", "graphics"]})

    unnamed = code_machine(AREAD, version=5, frontend=coverless)
    coverless.machine = unnamed

    coverless.write("Hello")

    bare = coverless.render()["content"][0]["text"][0]["content"]

    assert_that(bare).is_equal_to([{"style": "normal", "text": "Hello"}])


# The arc_image band hangs above the whole screen: a graphics
# window at the top, the picture inlined as a data: url shaped to
# the display's width, the buffer re-based below, and the header's
# rows shrunk to what remains. Ignorable calls are ignored -- an
# unanswered id, a mode outside the two named -- a clear gives the
# rows back and retires the canvas, a reopened band wears a fresh
# id, a redraw refeeds the drawing, and an arrange re-shapes it.
# The claim itself is honest twice over: no art or no graphicswin,
# no claim.
def test_the_band_hangs_above_the_screen(
    code_machine: Callable[..., Machine],
) -> None:
    frontend, machine = opened(code_machine, resources=banded_resources())

    frontend.begin(
        {
            "type": "init",
            "gen": 0,
            "support": ["timer", "graphicswin"],
            "metrics": {
                "width": 800,
                "height": 480,
                "gridcharwidth": 10,
                "gridcharheight": 20,
            },
        }
    )

    assert_that(frontend.has_arc_images).is_true()

    frontend.draw_arc_image(9, 12)  # no such picture: ignored
    frontend.draw_arc_image(8, 7)  # no such mode: ignored

    assert_that(frontend._band).is_none()

    frontend.draw_arc_image(8, 12)

    # 800 wide at 96/320 aspect is a 240-pixel band; twelve rows
    # of twenty pixels remain below, and the header says so.
    assert_that(machine.memory.read_byte(SCREEN_LINES)).is_equal_to(12)

    update = frontend.render()
    band = update["windows"][0]

    assert_that((band["type"], band["top"], band["height"])).is_equal_to(
        ("graphics", 0, 240)
    )
    assert_that(update["windows"][1]["top"]).is_equal_to(240)

    drawn = next(held for held in update["content"] if "draw" in held)["draw"]

    assert_that(drawn[0]).is_equal_to({"special": "fill"})
    assert_that(drawn[1]["url"]).starts_with("data:image/png;base64,")
    assert_that((drawn[1]["width"], drawn[1]["height"])).is_equal_to((800, 240))

    # A redraw refeeds the drawing whole.
    assert_that(
        frontend.accept({"type": "redraw", "gen": frontend.page.gen})
    ).is_equal_to(STAND)
    assert_that(
        next(held for held in frontend.render()["content"] if "draw" in held)["draw"]
    ).is_length(2)

    # An arrange re-shapes the band to the new width.
    frontend.accept(
        {
            "type": "arrange",
            "gen": frontend.page.gen,
            "metrics": {
                "width": 400,
                "height": 480,
                "gridcharwidth": 10,
                "gridcharheight": 20,
            },
        }
    )

    arranged = frontend.render()

    assert_that(arranged["windows"][0]["height"]).is_equal_to(120)

    # A clear takes the canvas down and gives the rows back; the
    # band reopened wears a fresh id.
    first_ident = arranged["windows"][0]["id"]

    frontend.draw_arc_image(0, 12)

    assert_that(machine.memory.read_byte(SCREEN_LINES)).is_equal_to(24)
    assert_that([held["type"] for held in frontend.render()["windows"]]).is_equal_to(
        ["buffer"]
    )

    frontend.draw_arc_image(8, 12)

    assert_that(frontend.render()["windows"][0]["id"]).is_greater_than(first_ident)

    # Re-drawing the hanging picture owes nothing new: the update
    # that follows is the pass stanza, the canvas untouched.
    frontend.render()
    frontend.draw_arc_image(8, 12)

    assert_that(frontend.render()).is_equal_to({"type": "pass"})

    # A redraw with no band has nothing here to repaint.
    frontend.draw_arc_image(0, 12)
    frontend.render()

    assert_that(
        frontend.accept({"type": "redraw", "gen": frontend.page.gen})
    ).is_equal_to(PASS)

    # A band drawn before any machine boots simply hangs: the
    # header's rows are told when there is a header to tell.
    early = GlkOteFrontend(5, banded_resources())

    early.begin(
        {
            "type": "init",
            "gen": 0,
            "support": ["graphicswin"],
            "metrics": {
                "width": 800,
                "height": 480,
                "gridcharwidth": 10,
                "gridcharheight": 20,
            },
        }
    )
    early.draw_arc_image(8, 9)

    assert_that(early._band).is_equal_to((8, 9))

    # The claim is honest: art without graphicswin, or a display
    # without art, never claims.
    artless = GlkOteFrontend(5)

    artless.begin(
        {
            "type": "init",
            "gen": 0,
            "support": ["graphicswin"],
            "metrics": {"width": 80, "height": 24},
        }
    )

    assert_that(artless.has_arc_images).is_false()

    canvasless, _ = opened(code_machine, resources=banded_resources())

    assert_that(canvasless.has_arc_images).is_false()


# A save asks through the protocol's special input: the update
# carries the fileref prompt in the write mode, the answered path
# advances the machine and keeps a real file, a restore asks in
# the read mode, a response to some other ask asks nothing here,
# and a dialog's non-string ref reads as the cancel it is.
def test_saves_ask_through_special_input(
    code_machine: Callable[..., Machine], tmp_path: Path
) -> None:
    program = bytes([0xBE, 0x00, 0xFF, 0x10, 0xBE, 0x01, 0xFF, 0x11, 0xBA])
    frontend, machine = opened(code_machine, program=program)

    machine.run()

    update = frontend.render()

    assert_that(update["specialinput"]).is_equal_to(
        {"type": "fileref_prompt", "filemode": "write", "filetype": "save"}
    )

    assert_that(
        frontend.accept(
            {
                "type": "specialresponse",
                "gen": frontend.page.gen,
                "response": "unknown_prompt",
                "value": "x",
            }
        )
    ).is_equal_to(PASS)

    kept = str(tmp_path / "expedition.sav")

    assert_that(
        frontend.accept(
            {
                "type": "specialresponse",
                "gen": frontend.page.gen,
                "response": "fileref_prompt",
                "value": kept,
            }
        )
    ).is_equal_to(ADVANCE)

    machine.run()

    asked = frontend.render()

    assert_that(asked["specialinput"]["filemode"]).is_equal_to("read")

    # A fileref object from some browser dialog is a cancel.
    assert_that(
        frontend.accept(
            {
                "type": "specialresponse",
                "gen": frontend.page.gen,
                "response": "fileref_prompt",
                "value": {"filename": kept},
            }
        )
    ).is_equal_to(ADVANCE)

    machine.run()

    assert_that(machine.running).is_false()


def reading_image() -> bytes:
    """A Version 4 story that reads one line and quits, whole."""

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

    return bytes(data)


def served(lines: list[str]) -> tuple[bool, list[dict[str, Any]]]:
    """One whole Z conversation over string pipes."""

    writer = io.StringIO()

    clean = serve(
        Story(reading_image()),
        GlkOteFrontend(4),
        io.StringIO("".join(line + "\n" for line in lines)),
        writer,
        seed=7,
    )

    return clean, [json.loads(held) for held in writer.getvalue().splitlines()]


# The whole conversation: init boots the machine at the measured
# size, the update carries the ask, the line echoes and answers,
# and the stray and the garbled are answered in kind.
def test_a_session_serves_end_to_end() -> None:
    clean, stanzas = served(
        [
            json.dumps(INIT),
            json.dumps({"type": "line", "gen": 0, "window": 1, "value": "stale"}),
            json.dumps(
                {
                    "type": "arrange",
                    "gen": 1,
                    "metrics": {"width": 400, "height": 200},
                }
            ),
            json.dumps({"type": "line", "gen": 2, "window": 1, "value": "go"}),
        ],
    )

    assert_that(clean).is_true()
    assert_that([held["type"] for held in stanzas]).is_equal_to(
        ["update", "pass", "update", "update"]
    )
    assert_that(stanzas[0]["input"][0]["type"]).is_equal_to("line")
    assert_that(stanzas[-1]["exit"]).is_true()

    refused, spoken = served([json.dumps({"type": "line", "gen": 0, "value": "x"})])

    assert_that(refused).is_false()
    assert_that(spoken[0]["message"]).contains("opens with an init")

    hung, quiet = served([json.dumps(INIT)])

    assert_that(hung).is_true()
    assert_that(quiet).is_length(1)

    garbled, noise = served([json.dumps(INIT), "{nope"])

    assert_that(garbled).is_false()
    assert_that(noise[-1]["message"]).contains("not JSON")

    # A misaimed keystroke -- a char event while a line read
    # stands -- is the blocking loop's shrug now, not a fatal
    # wiring fault: the session answers the pass stanza and lives.
    misaimed, spoken = served(
        [json.dumps(INIT), json.dumps({"type": "char", "gen": 1, "value": "A"})]
    )

    assert_that(misaimed).is_true()
    assert_that(spoken[-1]).is_equal_to({"type": "pass"})


STAGE_INIT = {
    "type": "init",
    "gen": 0,
    "support": ["timer", "stage", "sound"],
    "metrics": {"width": 1280, "height": 800},
}

# EXT save and EXT restore, each storing then quitting.
SAVED = bytes([0xBE, 0x00, 0xFF, 0x10, 0xBA])
RESTORED = bytes([0xBE, 0x01, 0xFF, 0x10, 0xBA])


def indexed_png(
    colours: tuple[tuple[int, int, int], ...], alphas: bytes = b""
) -> bytes:
    """A 2-by-1 indexed-colour PNG wearing the given palette.

    Any alphas ride as a tRNS chunk -- a zero makes that palette
    entry's pixels fully transparent, the v6 chrome's see-through
    holes.
    """

    def piece(name: bytes, payload: bytes) -> bytes:
        return (
            len(payload).to_bytes(4, "big")
            + name
            + payload
            + zlib.crc32(name + payload).to_bytes(4, "big")
        )

    pieces = [
        b"\x89PNG\r\n\x1a\n",
        piece(b"IHDR", struct.pack(">IIBBBBB", 2, 1, 8, 3, 0, 0, 0)),
        piece(b"PLTE", b"".join(bytes(colour) for colour in colours)),
    ]

    if alphas:
        pieces.append(piece(b"tRNS", alphas))

    pieces.append(piece(b"IDAT", zlib.compress(b"\x00\x00\x01")))
    pieces.append(piece(b"IEND", b""))

    return b"".join(pieces)


def staged_resources() -> Resources:
    """A stage Blorb: a 2x1 PNG, a 24x16 Rect, Reso, release 9.

    The Reso standard window is 640x400 -- roomier than the MCGA
    default, proving the stage takes the art's own word -- and
    picture 1 carries a standard ratio of 2, so its drawn size
    doubles even on the standard window itself.
    """

    art = indexed_png(((10, 20, 30), (40, 50, 60)))
    rect = (24).to_bytes(4, "big") + (16).to_bytes(4, "big")
    reln = chunk(b"RelN", (9).to_bytes(2, "big"))
    reso = chunk(
        b"Reso",
        b"".join(
            value.to_bytes(4, "big")
            for value in (640, 400, 640, 400, 640, 400, 1, 2, 1, 0, 0, 0, 0)
        ),
    )
    ridx_size = 8 + 4 + 2 * 12
    png_offset = 12 + ridx_size + len(reln) + len(reso)
    rect_offset = png_offset + 8 + len(art)
    index = (
        (2).to_bytes(4, "big")
        + b"Pict"
        + (1).to_bytes(4, "big")
        + png_offset.to_bytes(4, "big")
        + b"Pict"
        + (2).to_bytes(4, "big")
        + rect_offset.to_bytes(4, "big")
    )

    return Resources(
        Blorb.parse(
            chunk(
                b"FORM",
                b"IFRS"
                + chunk(b"RIdx", index)
                + reln
                + reso
                + chunk(b"PNG ", art)
                + chunk(b"Rect", rect),
            )
        )
    )


def staged(
    code: bytes = AREAD,
    resources: Resources | None = None,
    words: dict[int, int] | None = None,
) -> tuple[StageFrontend, Machine]:
    """A stage face fronting a Version 6 machine at its main routine.

    Version 6 boots by calling a packed main routine (§5.4), so
    the code goes inside one at $100; the read buffers and a tiny
    dictionary are planted as the two-window helper plants them.
    """

    frontend = StageFrontend(6, resources)

    frontend.begin(STAGE_INIT)

    data = bytearray(512)
    data[0] = 6
    data[0x04:0x06] = (0x01C0).to_bytes(2, "big")
    data[0x06:0x08] = (0x0040).to_bytes(2, "big")
    data[0x0C:0x0E] = (0x0080).to_bytes(2, "big")
    data[0x0E:0x10] = (0x01C0).to_bytes(2, "big")
    data[0x100] = 0x00
    data[0x101 : 0x101 + len(code)] = code

    for offset, value in (words or {}).items():
        data[offset : offset + 2] = value.to_bytes(2, "big")

    machine = Machine(Story(bytes(data)), frontend)
    frontend.machine = machine

    machine.memory.write_byte(TEXT_BUFFER, 21)
    machine.memory.write_byte(PARSE_BUFFER, 5)
    machine.memory.write_word(0x08, DICTIONARY_BASE)

    for offset, value in enumerate([2, ord(","), ord("."), 0, 0, 0]):
        machine.memory.write_byte(DICTIONARY_BASE + offset, value)

    return frontend, machine


def stage_ops(update: dict[str, Any]) -> list[dict[str, Any]]:
    """The canvas draw ops of an update."""

    return [op for entry in update.get("content", []) for op in entry.get("draw", [])]


# The stage opens at the art's own size: the Reso standard window
# when the Blorb names one, MCGA's 320 by 200 without -- and a
# display that never learned the dialect is refused at the door.
def test_the_stage_opens_at_the_arts_own_size() -> None:
    bare = StageFrontend(6)

    assert_that(bare.has_stage).is_true()
    assert_that(bare.has_colours).is_true()
    assert_that(bare.has_pictures).is_false()
    assert_that(bare.screen_columns).is_equal_to(40)
    assert_that(bare.screen_lines).is_equal_to(25)
    assert_that(bare.picture_data(1)).is_none()
    assert_that(bare.picture_census()).is_equal_to((0, 0))

    # A galleryless stage draws nothing, quietly.
    bare.draw_picture(1, 1, 1)

    dressed = StageFrontend(6, staged_resources())

    dressed.begin(STAGE_INIT)

    assert_that(dressed.screen_columns).is_equal_to(80)
    assert_that(dressed.screen_lines).is_equal_to(50)
    assert_that(dressed.has_pictures).is_true()
    assert_that(dressed.has_sounds).is_true()

    with pytest.raises(GlkOteError, match="never learned the stage"):
        StageFrontend(6).begin(INIT)


# The factory picks the face by the screen model: the stage for
# Version 6, the two-window picture for the rest.
def test_fronted_picks_the_face() -> None:
    assert_that(fronted(6)).is_instance_of(StageFrontend)

    plain = fronted(5)

    assert_that(plain).is_instance_of(GlkOteFrontend)
    assert_that(isinstance(plain, StageFrontend)).is_false()


# One scaled canvas carries the whole stage: the window entry
# names the art's logical space under the display's box, the
# opening curtain papers it, and the story's text lands as
# placed, coalesced text ops in the §8.8 units.
def test_the_stage_renders_one_scaled_canvas() -> None:
    frontend, machine = staged(bytes([0xBA]))

    frontend.write("Hi")
    frontend.write_rectangle(["!!"])
    machine.run()

    update = frontend.render(exit=True)
    window = update["windows"][0]

    assert_that(window["type"]).is_equal_to("graphics")
    assert_that(window["scaled"]).is_true()
    assert_that(window["graphwidth"]).is_equal_to(320)
    assert_that(window["graphheight"]).is_equal_to(200)
    assert_that(window["width"]).is_equal_to(1280)
    assert_that(window["height"]).is_equal_to(800)

    ops = stage_ops(update)

    assert_that(ops[0]).is_equal_to({"special": "setcolor", "color": "#000000"})
    assert_that(ops[1]).is_equal_to(
        {
            "special": "fill",
            "x": 0,
            "y": 0,
            "width": 320,
            "height": 200,
            "color": "#000000",
        }
    )
    assert_that(ops[2]).is_equal_to(
        {
            "special": "text",
            "x": 0,
            "y": 0,
            "text": "Hi!!",
            "cell": [8, 8],
            "fg": "#ffffff",
            "bg": "#000000",
        }
    )


# The dress travels resolved: colours as the shared palette's CSS,
# reverse video pre-swapped, bold and italic as flags -- and the
# under-cursor sample reads the painted stage, which here is the
# opening curtain's black.
def test_stage_text_wears_its_dress() -> None:
    frontend, machine = staged(bytes([0xBA]))

    frontend.set_style(BOLD)
    frontend.write("B")
    frontend.set_style(0)
    frontend.set_style(ITALIC)
    frontend.set_colour(3, 4)
    frontend.write("i")
    frontend.set_style(0)
    frontend.set_style(REVERSE)
    frontend.write("r")
    frontend.set_style(0)
    frontend.set_colour(-1, -1)
    frontend.write("s")
    machine.run()

    ops = stage_ops(frontend.render(exit=True))
    texts = [op for op in ops if op["special"] == "text"]

    assert_that(texts[0]["text"]).is_equal_to("B")
    assert_that(texts[0]["bold"]).is_true()
    assert_that(texts[1]["text"]).is_equal_to("i")
    assert_that(texts[1]["fg"]).is_equal_to("#cc0000")
    assert_that(texts[1]["bg"]).is_equal_to("#00cc00")
    assert_that(texts[1]["italic"]).is_true()
    assert_that(texts[2]["text"]).is_equal_to("r")
    assert_that(texts[2]["fg"]).is_equal_to("#00cc00")
    assert_that(texts[2]["bg"]).is_equal_to("#cc0000")
    assert_that(texts[3]["text"]).is_equal_to("s")
    assert_that(texts[3]["fg"]).is_equal_to("#000000")
    assert_that(texts[3]["bg"]).is_equal_to("#000000")


# The eight-window geometry lands where the game placed it: a
# placed window's text paints at its absolute units, the scroll
# slides as a shift op, and the pixel-width erase-line fills.
def test_the_stage_forwards_the_eight_window_ops() -> None:
    frontend, machine = staged(bytes([0xBA]))

    frontend.place_window(2, 41, 17, 64, 128)
    frontend.set_window(2)
    frontend.set_cursor(1, 1)
    frontend.set_font(4)
    frontend.set_buffering(False)
    frontend.write("W")
    frontend.erase_line(16)
    frontend.scroll_window(2, 8)
    frontend.set_margins(2, 0, 0)
    frontend.set_line_count(2, -999)
    frontend.split_window(0)
    machine.run()

    assert_that(frontend.cursor_position()).is_equal_to((1, 9))

    # A single window's erasure homes it and keeps any chrome.
    frontend.erase_window(2)

    ops = stage_ops(frontend.render(exit=True))
    placed = next(op for op in ops if op["special"] == "text")
    shift = next(op for op in ops if op["special"] == "shift")

    assert_that(placed["text"]).is_equal_to("W")
    assert_that(placed["x"]).is_equal_to(16)
    assert_that(placed["y"]).is_equal_to(40)
    assert_that(shift["rise"]).is_equal_to(8)
    assert_that([op["width"] for op in ops if op["special"] == "fill"]).contains(16)

    with pytest.raises(ZMachineScreenError, match="no line"):
        frontend.show_status(Status("Here", 0, 0, time_game=False))


# The pictures draw Reso-scaled at their unit positions, in the
# turn's true order against the flowing text; a Rect placard has
# a size for layout but no bytes, and an unknown number draws and
# erases nothing at all.
def test_the_stage_draws_its_pictures() -> None:
    frontend, machine = staged(bytes([0xBA]), resources=staged_resources())

    assert_that(frontend.picture_census()).is_equal_to((2, 9))
    assert_that(frontend.picture_data(1)).is_equal_to((2, 4))
    assert_that(frontend.picture_data(2)).is_equal_to((16, 24))
    assert_that(frontend.picture_data(7)).is_none()

    frontend.write("A")
    frontend.draw_picture(1, 11, 21)
    frontend.write("B")
    frontend.draw_picture(2, 1, 1)
    frontend.draw_picture(7, 1, 1)
    frontend.erase_picture(1, 11, 21)
    frontend.erase_picture(7, 1, 1)
    machine.run()

    ops = stage_ops(frontend.render(exit=True))
    kinds = [op["special"] for op in ops if op["special"] != "setcolor"]
    image = next(op for op in ops if op["special"] == "image")
    papered = ops[-1]

    assert_that(kinds).is_equal_to(["fill", "text", "image", "text", "fill"])
    assert_that(image["image"]).is_equal_to(1)
    assert_that(image["url"]).starts_with("data:image/png;base64,")
    assert_that((image["x"], image["y"])).is_equal_to((20, 10))
    assert_that((image["width"], image["height"])).is_equal_to((4, 2))
    assert_that((papered["width"], papered["height"])).is_equal_to((4, 2))


# A line read asks at the stage's own cursor with the editor's
# cell, the table's nameable terminators offered and the click
# armed when the table names it -- and the landed line echoes
# onto the stage, though a terminator-ended one stays uncommitted.
def test_the_stage_asks_and_echoes_the_line() -> None:
    frontend, machine = staged(AREAD, words={0x2E: 0x01A0})

    machine.memory.write_byte(0x01A0, 133)
    machine.memory.write_byte(0x01A1, 254)
    frontend.write("> ")
    machine.run()

    update = frontend.render()
    entry = update["input"][0]

    assert_that(entry["type"]).is_equal_to("line")
    assert_that(entry["maxlen"]).is_equal_to(21)
    assert_that(entry["xpos"]).is_equal_to(16)
    assert_that(entry["ypos"]).is_equal_to(0)
    assert_that(entry["cell"]).is_equal_to([8, 8])
    assert_that(entry["ink"]).is_equal_to("#ffffff")
    assert_that(entry["terminators"]).is_equal_to(["func1"])
    assert_that(entry["mouse"]).is_true()

    verdict = frontend.accept({"type": "line", "gen": update["gen"], "value": "go"})

    assert_that(verdict).is_equal_to(ADVANCE)

    machine.run()

    echoed = next(
        op for op in stage_ops(frontend.render(exit=True)) if op["special"] == "text"
    )

    assert_that(echoed["text"]).is_equal_to("go")
    assert_that(echoed["x"]).is_equal_to(16)

    quiet, ended = staged(AREAD, words={0x2E: 0x01A0})

    ended.memory.write_byte(0x01A0, 133)
    ended.run()

    asked = quiet.render()

    quiet.accept(
        {"type": "line", "gen": asked["gen"], "value": "held", "terminator": "func1"}
    )
    ended.run()

    silent = stage_ops(quiet.render(exit=True))

    assert_that([op for op in silent if op["special"] == "text"]).is_empty()


# A keystroke read is an invisible focus target that hears clicks
# the way it hears any key: the canvas's own click lands as the
# §10.3 single-click code, one unit step over, while a click on
# some other window -- or before any canvas stands -- passes.
def test_the_stage_hears_keys_and_clicks() -> None:
    unborn, _ = staged(READ_CHAR)

    assert_that(
        unborn.accept({"type": "mouse", "gen": 0, "window": 9, "x": 1, "y": 1})
    ).is_equal_to(PASS)

    frontend, machine = staged(READ_CHAR)

    machine.run()

    update = frontend.render()
    canvas = update["windows"][0]["id"]

    assert_that(update["input"][0]).is_equal_to(
        {"id": canvas, "type": "char", "gen": 1, "mouse": True}
    )

    astray = {"type": "mouse", "gen": 1, "window": canvas + 9, "x": 1, "y": 1}

    assert_that(frontend.accept(astray)).is_equal_to(PASS)

    landed = {"type": "mouse", "gen": 1, "window": canvas, "x": 9, "y": 15}

    assert_that(frontend.accept(landed)).is_equal_to(ADVANCE)

    machine.run()

    assert_that(machine.memory.read_word(0x80)).is_equal_to(254)


# An arrange re-boxes the canvas without the machine hearing a
# word -- the units never move -- and a redraw replays the journal:
# everything since the last whole-stage fill, the scene papered
# first, the pre-scene paints gone for good. A refresh replays it
# with the windows resent.
def test_the_stage_reshapes_and_replays() -> None:
    frontend, machine = staged(READ_CHAR)

    frontend.write("old")
    machine.run()

    first = frontend.render()

    frontend.erase_window(-1)
    frontend.write("new")

    second = frontend.render()

    assert_that(stage_ops(second)[0]["special"]).is_equal_to("fill")

    reboxed = {
        "type": "arrange",
        "gen": second["gen"],
        "metrics": {"width": 640, "height": 400},
    }

    assert_that(frontend.accept(reboxed)).is_equal_to(STAND)

    resized = frontend.render()

    assert_that(resized["windows"][0]["width"]).is_equal_to(640)
    assert_that(resized["windows"][0]["graphwidth"]).is_equal_to(320)

    redraw = {
        "type": "redraw",
        "gen": resized["gen"],
        "window": first["windows"][0]["id"],
    }

    assert_that(frontend.accept(redraw)).is_equal_to(STAND)

    replayed = stage_ops(frontend.render())

    assert_that(replayed[0]["special"]).is_equal_to("setcolor")
    assert_that([op.get("text") for op in replayed]).does_not_contain("old")
    assert_that([op.get("text") for op in replayed]).contains("new")

    assert_that(frontend.accept({"type": "refresh"})).is_equal_to(STAND)

    told = frontend.render()

    assert_that(told).contains_key("windows")
    assert_that([op.get("text") for op in stage_ops(told)]).contains("new")


# A display can misaim one event across the roster's swap -- the
# focus dance lands a keystroke in a field already replaced --
# and every misaimed delivery answers the blocking loop's shrug,
# never the machine's session-fatal wiring fault. Return,
# meanwhile, spells as the newline ZSCII knows and finally lands.
def test_misaimed_events_pass_and_return_lands(
    code_machine: Callable[..., Machine],
) -> None:
    frontend, machine = opened(code_machine)

    machine.run()

    lined = frontend.render()["gen"]

    astray = {"type": "char", "gen": lined, "value": "x"}

    assert_that(frontend.accept(astray)).is_equal_to(PASS)

    unasked = {"type": "specialresponse", "gen": lined, "response": "fileref_prompt"}

    assert_that(frontend.accept(unasked)).is_equal_to(PASS)

    keyed, pressed = opened(code_machine, READ_CHAR)

    pressed.run()

    asked = keyed.render()["gen"]

    typed = {"type": "line", "gen": asked, "value": "go"}

    assert_that(keyed.accept(typed)).is_equal_to(PASS)

    entered = {"type": "char", "gen": asked, "value": "return"}

    assert_that(keyed.accept(entered)).is_equal_to(ADVANCE)

    pressed.run()

    assert_that(pressed.memory.read_word(0x100)).is_equal_to(13)


# The guards hold at the pointers too: a click with only a file
# ask standing passes at the grid and at the stage alike.
def test_misaimed_clicks_pass(code_machine: Callable[..., Machine]) -> None:
    frontend, machine = opened(code_machine, SAVED)

    frontend.split_window(1)
    machine.run()

    update = frontend.render()
    grid = update["windows"][1]["id"]
    poked = {"type": "mouse", "gen": update["gen"], "window": grid, "x": 1, "y": 1}

    assert_that(frontend.accept(poked)).is_equal_to(PASS)

    staged_front, saving = staged(SAVED)

    saving.run()

    told = staged_front.render()
    canvas = told["windows"][0]["id"]
    tapped = {"type": "mouse", "gen": told["gen"], "window": canvas, "x": 1, "y": 1}

    assert_that(staged_front.accept(tapped)).is_equal_to(PASS)


def adaptive_resources() -> Resources:
    """A stage Blorb in the APal style: two scenes and one chrome.

    Pictures 1 and 3 are scenes wearing full palettes of their
    own; picture 2 is the adaptive chrome the APal chunk names,
    its stub palette waiting on whatever scene plots first.
    """

    scene = indexed_png(((200, 0, 0), (0, 200, 0)))
    stub = indexed_png(((1, 2, 3), (4, 5, 6)), alphas=b"\x00")
    other = indexed_png(((0, 0, 200), (200, 200, 0)))
    apal = chunk(b"APal", (2).to_bytes(4, "big"))
    wrapped = [chunk(b"PNG ", art) for art in (scene, stub, other)]
    ridx_size = 8 + 4 + 3 * 12
    offsets = []
    at = 12 + ridx_size + len(apal)

    for held in wrapped:
        offsets.append(at)
        at += len(held)

    index = (3).to_bytes(4, "big") + b"".join(
        b"Pict" + number.to_bytes(4, "big") + offset.to_bytes(4, "big")
        for number, offset in zip((1, 2, 3), offsets, strict=True)
    )

    return Resources(
        Blorb.parse(
            chunk(
                b"FORM",
                b"IFRS" + chunk(b"RIdx", index) + apal + b"".join(wrapped),
            )
        )
    )


# The chrome wears the scene: a scene's plot absorbs its palette
# and the standing chrome re-plots in the Current Palette -- new
# bytes at the same position, the wire's spelling of Infocom's
# hardware recolouring -- while encodings are remembered per
# palette era and a whole-screen erasure takes the chrome along.
def test_the_stage_chrome_wears_the_scene() -> None:
    frontend, machine = staged(READ_CHAR, resources=adaptive_resources())

    frontend.draw_picture(1, 1, 1)
    frontend.draw_picture(2, 1, 9)
    frontend.draw_picture(2, 1, 9)
    frontend.draw_picture(3, 9, 1)
    machine.run()

    update = frontend.render()
    images = [op for op in stage_ops(update) if op["special"] == "image"]

    assert_that([op["image"] for op in images]).is_equal_to([1, 2, 2, 3, 2])
    assert_that(images[1]["url"]).is_equal_to(images[2]["url"])
    assert_that(images[4]["url"]).is_not_equal_to(images[1]["url"])
    assert_that((images[4]["x"], images[4]["y"])).is_equal_to((8, 0))

    frontend.erase_window(-1)
    frontend.draw_picture(1, 1, 1)

    told = [op for op in stage_ops(frontend.render()) if op["special"] == "image"]

    assert_that([op["image"] for op in told]).is_equal_to([1])


# §8.3.1's under-cursor sample reads the painted stage itself:
# over a plotted picture the art's own pixel answers, a chrome's
# transparent hole deferring to the scene beneath, and the minted
# colour dresses the following text -- how Zork Zero's status
# text sits on its ribbons without a seam. One colour mints once.
def test_the_stage_samples_its_own_paint() -> None:
    frontend, machine = staged(READ_CHAR, resources=adaptive_resources())

    frontend.draw_picture(1, 9, 17)
    frontend.draw_picture(2, 9, 17)
    frontend.set_cursor(9, 17)
    frontend.set_colour(-1, -1)
    frontend.write("s")
    frontend.set_cursor(9, 17)
    frontend.set_colour(-1, -1)
    frontend.write("t")
    machine.run()

    ops = stage_ops(frontend.render())
    sampled = [op for op in ops if op.get("text") in ("s", "t")]

    assert_that(sampled).is_length(2)

    for held in sampled:
        assert_that(held["fg"]).is_equal_to("#c80000")
        assert_that(held["bg"]).is_equal_to("#c80000")


# The point sample walks the paint newest-first: a fill answers
# its colour inside its rectangle and defers outside it, an image
# without a gallery -- or naming art the gallery cannot decode --
# is passed over, and paint never laid answers the default paper.
def test_plotted_answers_the_top_paint() -> None:
    fill = {
        "special": "fill",
        "x": 0,
        "y": 0,
        "width": 4,
        "height": 4,
        "color": "#123456",
    }
    dye = {"special": "setcolor", "color": "#ffffff"}
    astray = {
        "special": "image",
        "image": 9,
        "x": 0,
        "y": 0,
        "width": 4,
        "height": 4,
    }

    assert_that(_plotted([], 0, 0, None)).is_equal_to("#000000")
    assert_that(_plotted([fill, dye], 1, 1, None)).is_equal_to("#123456")
    assert_that(_plotted([fill], 9, 9, None)).is_equal_to("#000000")
    assert_that(_plotted([fill, astray], 1, 1, None)).is_equal_to("#123456")

    gallery = Gallery({}, 0)

    assert_that(_plotted([fill, astray], 1, 1, gallery)).is_equal_to("#123456")


# A save asks for its file through the protocol's special input,
# a restore asks to read -- and the cancel is delivered like any
# player answer.
def test_the_stage_asks_for_its_file() -> None:
    frontend, machine = staged(SAVED)

    machine.run()

    update = frontend.render()

    assert_that(update["specialinput"]).is_equal_to(
        {"type": "fileref_prompt", "filemode": "write", "filetype": "save"}
    )

    verdict = frontend.accept(
        {"type": "specialresponse", "gen": update["gen"], "response": "fileref_prompt"}
    )

    assert_that(verdict).is_equal_to(ADVANCE)

    reader, restoring = staged(RESTORED)

    restoring.run()

    asked = reader.render()

    assert_that(asked["specialinput"]["filemode"]).is_equal_to("read")


# The sidecar rides when the display says the "voxam" token: the
# machine's honest bearings -- a zeroed story tallies score and
# turns with no location to name -- and, once a line lands, the
# very command the wire delivered (DESIGN: What the sidecar
# carries). Ungranted, the update carries no block at all.
def test_the_sidecar_rides_when_granted(
    code_machine: Callable[..., Machine],
) -> None:
    frontend, machine = opened(code_machine)

    frontend.begin({**INIT, "support": ["timer", "voxam"]})
    machine.run()

    update = frontend.render()

    assert_that(update["voxam"]).is_equal_to({"score": 0, "turns": 0})

    frontend.accept({"type": "line", "gen": update["gen"], "value": "go north"})
    machine.run()

    told = frontend.render(exit=True)

    assert_that(told["voxam"]["command"]).is_equal_to("go north")

    bare, quiet = opened(code_machine)

    quiet.run()

    assert_that("voxam" in bare.render()).is_false()


# The bearings name the location honestly: a planted object table
# answers the first global's object and short name, an unreadable
# object answers None rather than a halt, and the discontinuity
# bit is read once and rested (DESIGN: What the sidecar carries).
def test_the_sidecar_tells_location_and_discontinuity(
    code_machine: Callable[..., Machine],
) -> None:
    frontend, machine = opened(code_machine, READ_CHAR)

    frontend.begin({**INIT, "support": ["voxam"]})

    # The boot-cached object table sits at address 0: Version 5
    # defaults span 126 bytes, so object 1's entry begins at $7E
    # with its property pointer at $8A, and the properties at
    # $1A0 open with a one-word short name spelling "abc".
    machine.memory.write_word(0x100, 1)
    machine.memory.write_word(0x8A, 0x1A0)
    machine.memory.write_byte(0x1A0, 1)
    machine.memory.write_word(0x1A1, 0x98E8)

    machine.discontinuity = True
    machine.run()

    update = frontend.render()
    block = update["voxam"]

    assert_that(block["location"]).is_equal_to({"object": 1, "name": "abc"})
    assert_that(block["discontinuity"]).is_true()

    frontend.accept({"type": "char", "gen": update["gen"], "value": "x"})
    machine.run()

    assert_that("discontinuity" in frontend.render(exit=True)["voxam"]).is_false()

    # An object past every table answers None, gently.
    machine.memory.write_word(0x100, 500)

    assert_that(machine.bearings().location).is_none()


# A time game's globals are the clock, no score at all: the
# bearings stay honestly silent about them (§8.2.3).
def test_a_time_games_tally_stays_honest(
    code_machine: Callable[..., Machine],
) -> None:
    frontend, machine = opened(code_machine, READ_CHAR, version=3)

    machine.memory.write_byte(0x01, 0x02)

    bearings = machine.bearings()

    assert_that(bearings.score).is_none()
    assert_that(bearings.turns).is_none()

    # Through the face, the block honestly carries neither.
    block = frontend._sidecar()

    assert_that("score" in block).is_false()
    assert_that("turns" in block).is_false()


# The stage face speaks the sidecar too: the same token, the same
# honest block, over the scaled canvas.
def test_the_stage_speaks_the_sidecar_too() -> None:
    frontend, machine = staged(READ_CHAR)

    frontend.begin({**STAGE_INIT, "support": ["timer", "stage", "sound", "voxam"]})

    machine.discontinuity = True
    machine.run()

    block = frontend.render()["voxam"]

    assert_that(block["score"]).is_zero()
    assert_that(block["discontinuity"]).is_true()


def arranged(frontend: GlkOteFrontend, cell_width: int) -> dict[str, Any]:
    """An arrange in the same box, its grid cells a new width."""

    return {
        "type": "arrange",
        "gen": frontend.page.gen,
        "metrics": {**METRICS, "gridcharwidth": cell_width},
    }


def status_row(frontend: GlkOteFrontend) -> str:
    """The grid's first row, one render's worth."""

    lines = frontend.render()["content"][-1]["lines"]

    return "".join(run["text"] for run in lines[0]["content"])


# Issue #322: a display can change its own font size mid-session --
# the desktop shell's Display menu does exactly that, live -- so an
# arrange re-measures the grid and the screen model follows it. Left
# at the size it booted against, the model composes the §8.2 status
# line for a screen that is no longer there: on a narrowed grid the
# score is stranded off the right edge, and a widened one reaches
# for cells the model's rows do not have.
def test_an_arrange_resizes_the_screen_model(
    code_machine: Callable[..., Machine],
) -> None:
    frontend, _ = opened(code_machine, version=3)

    frontend.show_status(Status("West of House", 0, 1, time_game=False))

    booted = status_row(frontend)

    assert_that(booted).is_length(80)
    assert_that(booted).ends_with("Score: 0  Moves: 1 ")

    # A bigger font: the same box, holding fewer cells.
    frontend.accept(arranged(frontend, 13))

    narrowed = status_row(frontend)

    assert_that(frontend.screen_columns).is_equal_to(61)
    assert_that(narrowed).is_length(61)
    assert_that(narrowed).starts_with(" West of House")
    assert_that(narrowed).ends_with("Score: 0  Moves: 1 ")

    # And a smaller one, which used to reach past the row.
    frontend.accept(arranged(frontend, 8))

    widened = status_row(frontend)

    assert_that(frontend.screen_columns).is_equal_to(100)
    assert_that(widened).is_length(100)
    assert_that(widened).ends_with("Score: 0  Moves: 1 ")


# The §8.4 screen fields follow the same arrange, through the
# callback the machine hangs on the frontend at boot: a Version 5
# story asking how wide its screen is gets the size the display
# just gave, not the one it booted against.
def test_an_arrange_restamps_the_screen_header(
    code_machine: Callable[..., Machine],
) -> None:
    frontend, machine = opened(code_machine, version=5)

    assert_that(machine.memory.read_byte(SCREEN_COLUMNS)).is_equal_to(80)

    frontend.accept(arranged(frontend, 13))

    assert_that(machine.memory.read_byte(SCREEN_COLUMNS)).is_equal_to(61)
    assert_that(machine.memory.read_byte(SCREEN_LINES)).is_equal_to(24)


# An arrange arriving before any machine stands behind the display
# still reshapes the model; there is simply no header to re-stamp.
def test_an_arrange_with_no_machine_reshapes_all_the_same() -> None:
    bare = GlkOteFrontend(3)

    bare.begin(INIT)

    assert_that(bare.accept(arranged(bare, 13))).is_equal_to(STAND)
    assert_that(bare.screen_columns).is_equal_to(61)
