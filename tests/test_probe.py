from pathlib import Path

import pytest
from assertpy import assert_that

from voxam.probe import Probe

# The tiny story's fixed addresses: text buffer, parse buffer, and
# dictionary, all in dynamic memory below the $1C0 static base.
TEXT_BUFFER = 0x120
PARSE_BUFFER = 0x140
DICTIONARY = 0x150

# sread text-buffer parse-buffer (§15).
SREAD = bytes([0xE4, 0x0F, 0x01, 0x20, 0x01, 0x40])

NEW_LINE = 0xBB
QUIT = 0xBA


def chars(text: str) -> bytes:
    """Emit a string one print_char at a time, ending the line."""

    code = bytearray()

    for character in text:
        code += bytes([0xE5, 0x7F, ord(character)])

    code.append(NEW_LINE)

    return bytes(code)


def tiny_story(code: bytes) -> bytes:
    data = bytearray(512)
    data[0] = 3
    data[0x04:0x06] = (0x01C0).to_bytes(2, "big")
    data[0x06:0x08] = (0x0040).to_bytes(2, "big")
    data[0x08:0x0A] = DICTIONARY.to_bytes(2, "big")
    data[0x0C:0x0E] = (0x0100).to_bytes(2, "big")
    data[0x0E:0x10] = (0x01C0).to_bytes(2, "big")
    data[TEXT_BUFFER] = 21
    data[PARSE_BUFFER] = 5
    data[DICTIONARY : DICTIONARY + 4] = bytes([0, 7, 0, 0])
    data[0x40 : 0x40 + len(code)] = code

    return bytes(data)


# The probe story: a prelude line nobody typed for, then three
# commands whose responses are a refusal, an acceptance, and the
# silence before quitting.
STORY_CODE = (
    chars("West of nowhere")
    + SREAD
    + chars("You can't see any such thing.")
    + SREAD
    + chars("Taken.")
    + SREAD
    + bytes([QUIT])
)

# A story that goes wrong after its first command: 2OP:0 is not an
# opcode, so the machine halts loudly there.
BROKEN_CODE = chars("So far so good") + SREAD + bytes([0x00, 0x00, 0x00])


def write_recording(tmp_path: Path, code: bytes, commands: list[str]) -> Path:
    (tmp_path / "tiny.z3").write_bytes(tiny_story(code))
    script = tmp_path / "tiny.accept"
    script.write_text(
        "! SEED=7\n! GAME=tiny.z3\n\n" + "\n".join(commands) + "\n",
        encoding="utf-8",
    )

    return script


# attempt() replays the recorded prefix as the known timeline and
# judges only the variant tail: the refusal-dialect response is
# flagged, the accepted one is not, and the prelude that preceded
# every command belongs to no step.
def test_attempt_judges_the_variant_tail(tmp_path: Path) -> None:
    probe = Probe.load(write_recording(tmp_path, STORY_CODE, ["look"]))

    run = probe.attempt(["take lamp", "open door"])

    assert_that(run.error).is_none()
    assert_that([step.command for step in run.steps]).is_equal_to(
        ["take lamp", "open door"]
    )
    assert_that(run.steps[0].response).contains("Taken.")
    assert_that(run.steps[0].refusal).is_none()
    assert_that(run.steps[1].response).does_not_contain("West of nowhere")


# drop_last re-tries a recording's ending without editing the file:
# with the recorded command dropped, the variant tail meets the
# response the recording would have met.
def test_drop_last_rewinds_the_recorded_ending(tmp_path: Path) -> None:
    probe = Probe.load(write_recording(tmp_path, STORY_CODE, ["look"]))

    run = probe.attempt(["examine sign", "take lamp"], drop_last=1)

    assert_that(run.steps[0].refusal).is_equal_to("You can't see any such thing.")
    assert_that(run.refusals).is_equal_to((run.steps[0],))
    assert_that(run.steps[1].refusal).is_none()


# run() owns the whole command list and judges every step -- the
# escape hatch for surgery the prefix-plus-tail shape cannot say.
def test_run_judges_every_command(tmp_path: Path) -> None:
    probe = Probe.load(write_recording(tmp_path, STORY_CODE, ["look"]))

    run = probe.run(["a", "b", "c"])

    assert_that(len(run.steps)).is_equal_to(3)
    assert_that(run.steps[0].refusal).is_not_none()
    assert_that(run.steps[1].response).contains("Taken.")


# Commands the machine never asked for -- the story quit first --
# get no step, and that is an answer too.
def test_unconsumed_commands_have_no_steps(tmp_path: Path) -> None:
    probe = Probe.load(write_recording(tmp_path, STORY_CODE, ["look"]))

    run = probe.run(["a", "b", "c", "d", "e"])

    assert_that(len(run.steps)).is_equal_to(3)
    assert_that(run.error).is_none()


# A machine that halts on a fault mid-probe reports the fault
# instead of crashing the probe: the harness outlives the frontier
# it is there to find.
def test_a_halting_story_surfaces_its_error(tmp_path: Path) -> None:
    probe = Probe.load(write_recording(tmp_path, BROKEN_CODE, ["boom"]))

    run = probe.attempt()

    assert_that(run.error).is_not_none()
    assert_that(run.steps).is_empty()


# Every run boots a fresh machine from the same seed, so runs can
# never contaminate each other: ask the same question twice, get
# the same answer twice.
def test_runs_are_isolated_and_deterministic(tmp_path: Path) -> None:
    probe = Probe.load(write_recording(tmp_path, STORY_CODE, ["look"]))

    first = probe.attempt(["take lamp"])
    second = probe.attempt(["take lamp"])

    assert_that(second.steps).is_equal_to(first.steps)


# The machine comes back with the run for post-mortem reads --
# here, the typed command still sitting in the story's text buffer.
def test_the_machine_survives_for_post_mortem_reads(tmp_path: Path) -> None:
    probe = Probe.load(write_recording(tmp_path, STORY_CODE, ["look"]))

    run = probe.run(["xyzzy"])
    memory = run.machine.memory

    typed = ""
    position = TEXT_BUFFER + 1

    while memory.read_byte(position) != 0:
        typed += chr(memory.read_byte(position))
        position += 1

    assert_that(typed).is_equal_to("xyzzy")


# A script whose game is missing fails loudly at load, not at the
# first run.
def test_a_missing_game_fails_at_load(tmp_path: Path) -> None:
    script = tmp_path / "orphan.accept"
    script.write_text("! GAME=absent.z3\nlook\n", encoding="utf-8")

    with pytest.raises(FileNotFoundError):
        Probe.load(script)
