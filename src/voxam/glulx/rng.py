"""The random number generator behind the random opcode.

The stream is a xorshift32 owned by this module rather than
Python's random module -- the same generator, and the same reason,
as the Z-Machine's dice: a seed must produce the same session
forever, because recorded playthroughs must never be invalidated
by an interpreter upgrade. Glulx asks less of its generator than
the Z-Machine does -- there is no rising-sequence testing mode --
so this is the plain stream: full words, and ranges folded from
them (Glulx: The Random Number Generator).
"""

import os

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
    """The stream the random and setrandom opcodes draw on.

    The generator is deliberately not part of saved state, and a
    restart leaves it alone (Glulx: The Random Number Generator,
    Glulx: Game State).
    """

    def __init__(self, seed: int | None = None) -> None:
        """Start seeded for a session, or from true entropy.

        Args:
            seed: A session seed for reproducible playthroughs;
                None means true entropy.
        """

        # Whether the operator asked for a reproducible session,
        # which is what decides where a later reseed-to-entropy
        # draws its state from. See seed().
        self._seeded = seed is not None
        self._state = _entropy() if seed is None else _mixed(seed)

    def word(self) -> int:
        """The next full 32-bit value off the stream."""

        state = self._state
        state ^= (state << XORSHIFT_TRIPLE[0]) & STATE_MASK
        state ^= state >> XORSHIFT_TRIPLE[1]
        state ^= (state << XORSHIFT_TRIPLE[2]) & STATE_MASK
        self._state = state

        return state

    def below(self, limit: int) -> int:
        """A value in 0 through limit - 1, folded from the stream.

        Folding by modulo skews the distribution by well under one
        part in a million for any range a game's dice could ask --
        far below anything observable.
        """

        return self.word() % limit

    def seed(self, value: int) -> None:
        """Reseed the stream -- setrandom's work.

        A seed of zero asks for genuine unpredictability (Glulx:
        The Random Number Generator), and gets it in an ordinary
        session.

        In a session the operator seeded, it draws its new state off
        the seeded stream instead. This is a deliberate deviation,
        and a narrow one: `--seed` already overrides the same rule at
        game start, where the generator is likewise meant to be
        unpredictable, so honoring the flag here only makes it mean
        at turn five hundred what it meant at turn one. Without it a
        story that reseeds silently breaks the flag's whole promise,
        and no recording that reaches such a story could ever replay.
        A session given no seed reaches the entropy below, as always.
        """

        if value != 0:
            self._state = _mixed(value)
        elif self._seeded:
            # Off the stream itself: no counter to keep, successive
            # reseeds still differ, and the whole run stays a
            # function of the one seed the operator gave.
            self._state = _mixed(self.word())
        else:
            self._state = _entropy()
