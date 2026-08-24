"""The Z face of GlkOte: the screen model composed, reads delivered."""

import io
import json
from collections.abc import Callable
from typing import Any

import pytest
from assertpy import assert_that

from voxam.errors import GlkOteError
from voxam.frontend import Status
from voxam.screen import BOLD, FIXED_PITCH, ITALIC, REVERSE, ROMAN
from voxam.zmachine.glkote import ADVANCE, PASS, STAND, GlkOteFrontend, _named, serve
from voxam.zmachine.machine import Machine
from voxam.zmachine.story import Story

INIT = {
    "type": "init",
    "gen": 0,
    "support": ["timer"],
    "metrics": {
        "width": 800,
        "height": 480,
        "gridcharwidth": 10,
        "gridcharheight": 20,
    },
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


def opened(
    code_machine: Callable[..., Machine],
    program: bytes = AREAD,
    version: int = 5,
    routine: bytes | None = None,
) -> tuple[GlkOteFrontend, Machine]:
    """A measured frontend fronting a machine at its first read."""

    frontend = GlkOteFrontend(version)

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
# next boot while the picture stands.
def test_the_grid_comes_and_goes_with_new_names(
    code_machine: Callable[..., Machine],
) -> None:
    frontend, _ = opened(code_machine)

    frontend.split_window(1)

    first = frontend.render()

    assert_that(first["windows"][1]["id"]).is_equal_to(2)

    frontend.split_window(0)

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
    assert_that(frontend.accept({"type": "refresh", "gen": 3})).is_equal_to(PASS)


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

    wrongful, spoken = served(
        [json.dumps(INIT), json.dumps({"type": "char", "gen": 1, "value": "A"})]
    )

    assert_that(wrongful).is_false()
    assert_that(spoken[-1]["message"]).contains("no key read suspended")
