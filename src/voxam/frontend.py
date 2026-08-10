"""How a running story presents itself to the player (§8).

The Z-Machine defines a screen model but leaves its realization to
the interpreter: each interpreter shows what it can, declares as much
in the header, and games adapt to those declarations (§11.1). A
Frontend is Voxam's seam for that variability -- the machine speaks
in semantic operations, and each frontend renders the ones it
honestly claimed.
"""

import sys
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Status:
    """One status line's worth of game state (§8.2).

    Attributes:
        location: The short name of the object held in the first
            global variable -- the player's whereabouts (§8.2.2).
        score: The second global variable: the score in a score
            game, or the hour of a 24-hour clock in a time game
            (§8.2.3).
        turns: The third global variable: the turn count in a score
            game, or the minutes in a time game (§8.2.3).
        time_game: Whether the numbers are a clock reading rather
            than score and turns (§8.2.3.2).
    """

    location: str
    score: int
    turns: int
    time_game: bool


class Frontend(Protocol):
    """The presentation seam between the machine and the player (§8).

    Attributes:
        has_status_line: Whether this frontend can show a §8.2
            status line; the machine declares it in the header at
            boot (§11.1).
        has_screen_splitting: Whether this frontend can split the
            screen into windows (§8.6); likewise declared.
    """

    has_status_line: bool
    has_screen_splitting: bool

    def write(self, text: str) -> None:
        """Show story text from the print stream."""

    def show_status(self, status: Status) -> None:
        """Present a freshly assembled status line (§8.2)."""


class PlainFrontend:
    """A dumb-terminal presentation: one unadorned stream of text.

    It claims no status line and no screen splitting, so dropping a
    status is not a shortcut: it is the conforming behaviour of an
    interpreter that declared the truth about itself (§11.1).
    """

    has_status_line = False
    has_screen_splitting = False

    def __init__(self, write: Callable[[str], None] | None = None) -> None:
        """Bind the text stream, standard output when not given."""

        self._write = write if write is not None else sys.stdout.write

    def write(self, text: str) -> None:
        """Pass story text through to the stream."""

        self._write(text)

    def show_status(self, status: Status) -> None:
        """Drop the status: a plain stream has no line to keep it on."""
