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

# The screen model's two windows: the scrolling lower window where
# the story unfolds, and the fixed upper window games draw status
# chrome into (§8.7.2). erase_window's -1 both unsplits the screen
# and reselects the lower window.
LOWER_WINDOW = 0
UPPER_WINDOW = 1
UNSPLIT_AND_CLEAR = -1


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

    Every attribute here is a claim the machine makes on the
    frontend's behalf in the story's header at boot (§11.1), and
    games adapt to those claims -- so each frontend must tell the
    truth about itself.

    Attributes:
        has_status_line: Whether this frontend can show a §8.2
            status line.
        has_screen_splitting: Whether this frontend can split the
            screen into windows (§8.6).
        has_bold: Whether boldface type is available (§8.7).
        has_italic: Whether italic type is available (§8.7).
        has_fixed_pitch: Whether a fixed-space style is available.
        has_timed_input: Whether input can be interrupted on a
            timer (§15 read).
        screen_lines: The screen height in lines; 255 means
            "infinite", the claim of a stream that never pages
            (§8.4).
        screen_columns: The screen width in characters (§8.4).
    """

    has_status_line: bool
    has_screen_splitting: bool
    has_bold: bool
    has_italic: bool
    has_fixed_pitch: bool
    has_timed_input: bool
    screen_lines: int
    screen_columns: int

    def write(self, text: str) -> None:
        """Show story text from the print stream."""

    def show_status(self, status: Status) -> None:
        """Present a freshly assembled status line (§8.2)."""

    def set_style(self, style: int) -> None:
        """Change the type style for text that follows (§8.7).

        The style is a bitmask: 0 returns to roman, 1 is reverse
        video, 2 boldface, 4 italic, 8 fixed pitch.
        """

    def erase_window(self, window: int) -> None:
        """Erase a window to its background (§8.7).

        Window -1 unsplits the screen and clears it all; -2 clears
        the whole screen without unsplitting; 0 and up name a single
        window.
        """

    def set_buffering(self, buffered: bool) -> None:
        """Turn word-wrap buffering on or off (§8.7)."""

    def split_window(self, lines: int) -> None:
        """Give the upper window this many lines; 0 unsplits (§8.7.2)."""

    def set_window(self, window: int) -> None:
        """Select the window that receives text (§8.7.2)."""

    def set_cursor(self, line: int, column: int) -> None:
        """Move the upper window's cursor (§8.7.2)."""


class PlainFrontend:
    """A dumb-terminal presentation: one unadorned stream of text.

    It claims no status line, no screen splitting, and no typography
    beyond the fixed pitch a stream inherently has -- with a screen
    80 characters wide and infinitely tall, since an unpaged stream
    has no real rows. Dropping a status is not a shortcut: it is the
    conforming behaviour of an interpreter that declared the truth
    about itself (§11.1).
    """

    has_status_line = False
    has_screen_splitting = False
    has_bold = False
    has_italic = False
    has_fixed_pitch = True
    has_timed_input = False
    screen_lines = 255
    screen_columns = 80

    def __init__(self, write: Callable[[str], None] | None = None) -> None:
        """Bind the text stream, standard output when not given."""

        self._write = write if write is not None else sys.stdout.write
        self._window = LOWER_WINDOW

    def write(self, text: str) -> None:
        """Pass story text through to the stream -- lower window only.

        Text sent to the upper window is a game's self-drawn status
        chrome: dropping it is what keeps a transcript the story and
        nothing else.
        """

        if self._window == LOWER_WINDOW:
            self._write(text)

    def show_status(self, status: Status) -> None:
        """Drop the status: a plain stream has no line to keep it on."""

    def set_style(self, style: int) -> None:
        """Drop the style: none were claimed, and §8.7 permits that.

        The header declared no boldface and no italic, so a game
        asking for them is asking politely for something it was told
        does not exist.
        """

    def erase_window(self, window: int) -> None:
        """Drop the erasure, honouring -1's side effect (§8.7).

        A stream has nothing to erase, but erasing window -1 also
        unsplits the screen and reselects the lower window -- and
        THAT matters here, or a game that clears its way out of the
        upper window would leave the stream muted forever. (Whether
        a full-screen clear should also leave a paragraph break in
        the transcript is an open question; the answer waits on
        reading real Version 4 transcripts without one.)
        """

        if window == UNSPLIT_AND_CLEAR:
            self._window = LOWER_WINDOW

    def set_buffering(self, buffered: bool) -> None:
        """Drop the toggle: an unwrapped stream needs no buffering."""

    def split_window(self, lines: int) -> None:
        """Drop the split: the stream has no rows to portion out."""

    def set_window(self, window: int) -> None:
        """Remember the selection, which is what routes write()."""

        self._window = window

    def set_cursor(self, line: int, column: int) -> None:
        """Drop the cursor move: it only means anything up top."""
