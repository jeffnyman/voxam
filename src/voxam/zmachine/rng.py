"""The random number generator and its two states (§2.4).

The generator is "random" at game start and after restarts, and
becomes "predictable" when seeded. Predictable mode follows the
Standard's suggested algorithm (§2 remarks): a seed under 1000
cycles the rising sequence 1 to S -- which visits every possible
value, for testing -- while larger seeds run a seeded generator,
for replaying whole scripts.

The stream itself is a xorshift32 owned by this module rather than
Python's random module, so that a seed produces the same session
forever: recorded playthroughs must never be invalidated by an
interpreter upgrade. Its quality comfortably clears the bar the
Standard sets (§2 remarks warn only against the poorest of the old
C generators).
"""

import os

# Seeds below this cycle the rising sequence; from here up they seed
# the conventional generator (§2 remarks).
SEQUENCE_SEED_LIMIT = 1000

# The xorshift32 triple and the mixing constants used to spread a
# seed across the 32-bit state.
STATE_MASK = 0xFFFFFFFF
XORSHIFT_TRIPLE = (13, 17, 5)
MIX_INCREMENT = 0x9E3779B9
MIX_MULTIPLIER_1 = 0x85EBCA6B
MIX_MULTIPLIER_2 = 0xC2B2AE35

ENTROPY_BYTES = 4


def _mixed(value: int) -> int:
    """Spread a seed over the state space, never yielding zero.

    A xorshift state of zero is a fixed point, and small seeds used
    raw would start the stream in a correlated corner; one round of
    integer mixing avoids both.
    """

    value = (value + MIX_INCREMENT) & STATE_MASK
    value ^= value >> 16
    value = (value * MIX_MULTIPLIER_1) & STATE_MASK
    value ^= value >> 13
    value = (value * MIX_MULTIPLIER_2) & STATE_MASK
    value ^= value >> 16

    return value or MIX_INCREMENT


def _entropy() -> int:
    """A fresh state from the operating system's entropy."""

    return _mixed(int.from_bytes(os.urandom(ENTROPY_BYTES), "big"))


class Randomizer:
    """The two-state generator behind the random opcode (§2.4)."""

    def __init__(self, seed: int | None = None) -> None:
        """Start in the random state, as at game start (§2.4).

        Args:
            seed: A session seed for reproducible playthroughs. This
                seeds the stream directly without entering the
                predictable state: the game still sees ordinary dice,
                just the same dice every session. None means true
                entropy.
        """

        self._state = _entropy() if seed is None else _mixed(seed)
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

        # Folding by modulo skews the distribution by under one part
        # in 131072 for the largest legal range (§2.4.1) -- far below
        # anything a game's dice could notice.
        return self._next() % limit + 1

    def seed(self, value: int) -> None:
        """Switch to the predictable state with a seed (§2.4.2)."""

        if value < SEQUENCE_SEED_LIMIT:
            self._sequence_limit = value
            self._sequence_at = 0
        else:
            self._sequence_limit = None
            self._state = _mixed(value)

    def randomize(self) -> None:
        """Return to the random state, seeded as randomly as possible.

        The random opcode with a range of 0 asks for exactly this
        (§15 random).
        """

        self._sequence_limit = None
        self._state = _entropy()

    def _next(self) -> int:
        """Advance the xorshift32 stream one step."""

        state = self._state
        state ^= (state << XORSHIFT_TRIPLE[0]) & STATE_MASK
        state ^= state >> XORSHIFT_TRIPLE[1]
        state ^= (state << XORSHIFT_TRIPLE[2]) & STATE_MASK
        self._state = state

        return state
