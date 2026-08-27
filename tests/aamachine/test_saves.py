"""Tests for the Å-machine savefile, the AASV form both ways."""

from pathlib import Path

import pytest
from assertpy import assert_that

from voxam.aamachine import saves
from voxam.aamachine.machine import Machine
from voxam.aamachine.output import PlainVoice
from voxam.aamachine.story import Story
from voxam.errors import AAMachineError
from voxam.iff import chunk as iff_chunk

FIXTURES = Path(__file__).parent.parent / "fixtures"


def storied(name: str = "cloak-rel2") -> Story:
    """One vendored story, parsed."""

    return Story((FIXTURES / f"{name}.aastory").read_bytes())


def captured(story: Story) -> saves.State:
    """A real mid-game state: cloak, one turn in."""

    machine = Machine(story, PlainVoice(story), seed=7)
    machine.run()
    machine.deliver_line("west")

    return machine._captured(9)


# The whole round trip: a real mid-game state encodes to an AASV
# form and revives identical, landing where it was told to.
def test_a_state_survives_the_round_trip() -> None:
    story = storied()
    state = captured(story)
    data = saves.kept(story, state)

    assert_that(data[:4]).is_equal_to(b"FORM")
    assert_that(data[8:12]).is_equal_to(b"AASV")
    assert_that(saves.revived(story, data)).is_equal_to(state)


# The wrong form is refused by name.
def test_a_wrong_form_is_refused() -> None:
    with pytest.raises(AAMachineError, match=r"FORM AASV"):
        saves.revived(storied(), iff_chunk(b"FORM", b"AAVM"))


# A savefile missing one of its three chunks is refused by name.
def test_a_missing_chunk_is_refused() -> None:
    story = storied()
    hollow = iff_chunk(
        b"FORM", b"AASV" + iff_chunk(b"HEAD", story.summed(b"HEAD").payload)
    )

    with pytest.raises(AAMachineError, match=r"missing its DATA"):
        saves.revived(story, hollow)


# A savefile whose HEAD is not this story's is another game's.
def test_a_foreign_head_is_refused() -> None:
    story = storied()
    data = saves.kept(story, captured(story))
    other = storied("gosling")

    with pytest.raises(AAMachineError, match=r"another game or another release"):
        saves.revived(other, data)


# DATA that unpacks to the wrong size cannot be this story's
# state.
def test_short_data_is_refused() -> None:
    story = storied()
    payload = (
        iff_chunk(b"HEAD", story.summed(b"HEAD").payload)
        + iff_chunk(b"DATA", b"\x01\x02")
        + iff_chunk(b"REGS", bytes(156))
    )

    with pytest.raises(AAMachineError, match=r"unpacks to 2 bytes"):
        saves.revived(story, iff_chunk(b"FORM", b"AASV" + payload))


# A REGS chunk shorter than its fixed registers is refused, and
# one claiming divs past its end likewise.
def test_a_short_or_overclaiming_regs_is_refused() -> None:
    with pytest.raises(AAMachineError, match=r"REGS chunk is too short"):
        saves._registered(bytes(10))

    overclaiming = bytes(154) + (9).to_bytes(2, "big")

    with pytest.raises(AAMachineError, match=r"claims 9 open divs"):
        saves._registered(overclaiming)


# DATA ending inside a null run is refused rather than guessed.
def test_a_torn_null_run_is_refused() -> None:
    with pytest.raises(AAMachineError, match=r"inside a null run"):
        saves._grown(b"\x01\x00")


# The run-length coding is its own inverse, the longest runs
# split at the 256-null seam.
def test_the_run_length_coding_inverts() -> None:
    data = b"\x07" + b"\x00" * 700 + b"\x09\x00"

    assert_that(saves._grown(saves._shrunk(data))).is_equal_to(data)


# The open divs travel: a state saved with divs open revives
# them in order.
def test_open_divs_travel_whole() -> None:
    story = storied()
    counted, ram, aux, heap, regs, flow, stacks, _ = captured(story)
    state = (counted, ram, aux, heap, regs, flow, stacks, (3, 7))
    data = saves.kept(story, state)

    assert_that(saves.revived(story, data)[7]).is_equal_to((3, 7))


# An INIT already long enough pads nothing.
def test_a_long_init_needs_no_padding() -> None:
    story = storied()

    assert_that(saves._grounded(story, 4)).is_equal_to(
        story.summed(b"INIT").payload[:4]
    )
