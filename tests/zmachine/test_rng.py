from assertpy import assert_that

from voxam.zmachine.rng import Randomizer


# A seed under 1000 produces the rising sequence 1 to S, repeating --
# the Standard's suggested testing mode (§2 remarks).
def test_low_seeds_cycle_the_rising_sequence() -> None:
    rng = Randomizer()
    rng.seed(3)

    rolls = [rng.roll(10) for _ in range(5)]

    assert_that(rolls).is_equal_to([1, 2, 3, 1, 2])


# When the sequence outgrows the requested range, entries fold back
# into it.
def test_the_rising_sequence_folds_into_the_range() -> None:
    rng = Randomizer()
    rng.seed(10)

    rolls = [rng.roll(3) for _ in range(10)]

    assert_that(rolls).is_equal_to([1, 2, 3, 1, 2, 3, 1, 2, 3, 1])


# Seeds of 1000 and up run a conventional generator: the same seed
# must reproduce the same sequence (§2.4.2).
def test_high_seeds_reproduce_their_sequences() -> None:
    first = Randomizer()
    second = Randomizer()
    first.seed(5000)
    second.seed(5000)

    assert_that([first.roll(100) for _ in range(5)]).is_equal_to(
        [second.roll(100) for _ in range(5)]
    )


def test_random_mode_stays_in_range() -> None:
    rng = Randomizer()

    assert_that(rng.roll(1)).is_equal_to(1)

    for _ in range(25):
        assert_that(rng.roll(6)).is_between(1, 6)


def test_randomize_leaves_the_predictable_state() -> None:
    rng = Randomizer()
    rng.seed(3)
    rng.randomize()

    for _ in range(10):
        assert_that(rng.roll(4)).is_between(1, 4)
