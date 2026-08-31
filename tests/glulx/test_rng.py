"""The Glulx dice: seeded forever (Glulx: The Random Number Generator)."""

from collections.abc import Callable

import pytest
from assertpy import assert_that

from voxam.glulx.machine import Machine
from voxam.glulx.rng import Randomizer
from voxam.glulx.story import Story

PLANT = 0x180
RESULT = 0x140

IDLE = bytes([0xC0, 0x00, 0x00, 0x81, 0x20])

# -9 through 0, as unsigned words: the mirror range of random #-10.
MIRROR_FLOOR = 0xFFFFFFF7
TO_RESULT = bytes([0x00, 0x00, 0x01, 0x40])


# The stream is Voxam's own xorshift32, not Python's: the same seed
# produces the same session forever, on any interpreter version --
# the promise every recorded playthrough depends on.
def test_a_seed_is_a_session_forever() -> None:
    first = Randomizer(7)
    second = Randomizer(7)
    run = [first.word() for _ in range(5)]

    assert_that([second.word() for _ in range(5)]).is_equal_to(run)
    assert_that(Randomizer(8).word()).is_not_equal_to(run[0])

    for _ in range(100):
        assert_that(first.below(10)).is_between(0, 9)

    reseeded = Randomizer(1)

    reseeded.seed(7)

    assert_that(reseeded.word()).is_equal_to(run[0])

    entropic = Randomizer()

    entropic.seed(0)
    entropic.word()


# The random opcode's three ranges: zero for a full word, positive
# for 0 up to the range, negative for the mirror below zero -- and
# setrandom reseeds mid-session, so two machines converge the
# moment they share a seed.
def test_the_random_opcode_rolls_its_three_ranges(
    image: Callable[..., bytes],
) -> None:
    def rolled(machine: Machine, plant: bytes) -> int:
        machine.memory.write_run(PLANT, plant)
        machine.pc = PLANT

        machine.step()

        return machine.memory.read_word(RESULT)

    seeded = Machine(Story(image(code=IDLE)), seed=7)
    twin = Machine(Story(image(code=IDLE)), seed=7)
    full = bytes([0x81, 0x10, 0x71, 0x00]) + TO_RESULT

    assert_that(rolled(seeded, full)).is_equal_to(rolled(twin, full))

    ranged = rolled(seeded, bytes([0x81, 0x10, 0x71, 0x0A]) + TO_RESULT)

    assert_that(ranged).is_between(0, 9)

    mirrored = rolled(seeded, bytes([0x81, 0x10, 0x71, 0xF6]) + TO_RESULT)

    assert_that(mirrored == 0 or mirrored >= MIRROR_FLOOR).is_true()

    drifted = Machine(Story(image(code=IDLE)), seed=9)

    rolled(drifted, bytes([0x81, 0x11, 0x21, 0x30, 0x39]))
    rolled(seeded, bytes([0x81, 0x11, 0x21, 0x30, 0x39]))

    assert_that(rolled(drifted, full)).is_equal_to(rolled(seeded, full))


# Issue #316: setrandom 0 asks for genuine unpredictability, and gets
# it -- but in a session the operator seeded, honoring that ask would
# break the promise --seed makes. So a seeded session reseeds off its
# own stream: two twins that reseed together stay twins, and the whole
# run remains a function of the one seed given.
def test_a_seeded_session_survives_a_reseed_to_entropy() -> None:
    first = Randomizer(7)
    second = Randomizer(7)

    first.word()
    second.word()

    first.seed(0)
    second.seed(0)

    run = [first.word() for _ in range(5)]

    assert_that([second.word() for _ in range(5)]).is_equal_to(run)

    # Successive reseeds still move the stream on, so a story asking
    # twice does not get the same dice twice.
    first.seed(0)

    assert_that(first.word()).is_not_equal_to(run[0])

    # And a differently seeded session is still a different session.
    other = Randomizer(8)

    other.word()
    other.seed(0)

    assert_that(other.word()).is_not_equal_to(run[0])


# With no --seed there is nothing to keep faith with, so the zero case
# reaches the operating system's entropy the specification asks for --
# and a seeded session never reaches it at all.
def test_the_entropy_path_is_the_unseeded_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "voxam.glulx.rng.os.urandom", lambda size: b"\x05\x06\x07\x08"[:size]
    )

    first = Randomizer()
    second = Randomizer()

    first.word()
    first.word()

    first.seed(0)
    second.seed(0)

    # Both landed on the same entropy, wherever their streams stood:
    # a reseed off the stream could not have converged them.
    assert_that(first.word()).is_equal_to(second.word())

    def refuse(size: int) -> bytes:
        pytest.fail(f"a seeded session asked for {size} bytes of entropy")

    monkeypatch.setattr("voxam.glulx.rng.os.urandom", refuse)

    Randomizer(7).seed(0)
