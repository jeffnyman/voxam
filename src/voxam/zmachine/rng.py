"""The random number generator and its two states (§2.4).

The generator is "random" at game start and after restarts, and
becomes "predictable" when seeded. Predictable mode follows the
Standard's suggested algorithm (§2 remarks): a seed under 1000
cycles the rising sequence 1 to S -- which visits every possible
value, for testing -- while larger seeds run a conventional seeded
generator, for replaying whole scripts.
"""

import random

# Seeds below this cycle the rising sequence; from here up they seed
# the conventional generator (§2 remarks).
SEQUENCE_SEED_LIMIT = 1000


class Randomizer:
    """The two-state generator behind the random opcode (§2.4)."""

    def __init__(self) -> None:
        """Start in the random state, as at game start (§2.4)."""

        self._generator = random.Random()
        self._sequence_limit: int | None = None
        self._sequence_at = 0

    def roll(self, limit: int) -> int:
        """Produce a value from 1 to limit (§2.4.1).

        In rising-sequence mode the next entry is folded into range;
        when the sequence limit is within the requested range, the
        results are simply 1, 2, ..., S, repeating.

        Args:
            limit: The top of the requested range, at least 1.

        Returns:
            A value between 1 and limit inclusive.
        """

        if self._sequence_limit is not None:
            self._sequence_at = self._sequence_at % self._sequence_limit + 1

            return (self._sequence_at - 1) % limit + 1

        return self._generator.randint(1, limit)

    def seed(self, value: int) -> None:
        """Switch to the predictable state with a seed (§2.4.2)."""

        if value < SEQUENCE_SEED_LIMIT:
            self._sequence_limit = value
            self._sequence_at = 0
        else:
            self._sequence_limit = None
            self._generator.seed(value)

    def randomize(self) -> None:
        """Return to the random state, seeded as randomly as possible.

        The random opcode with a range of 0 asks for exactly this
        (§15 random).
        """

        self._sequence_limit = None
        self._generator = random.Random()
