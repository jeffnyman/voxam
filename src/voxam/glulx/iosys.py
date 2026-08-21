"""The current output system: a mode and its rock (Glulx: Output).

Only the selection lives here. Actually emitting a character is the
machine's business, because filter mode calls back into the VM and
Glk mode goes out through the dispatch layer -- neither of which
this module should know about.
"""

from enum import IntEnum


class IOMode(IntEnum):
    """The output systems setiosys accepts (Glulx: Output)."""

    # Output is discarded -- the mode the machine starts in.
    NULL = 0
    # Each character passes to the Glulx function the rock names.
    FILTER = 1
    # Output goes to the current Glk stream.
    GLK = 2


class IOSystem:
    """Which output system is current, and its rock.

    Attributes:
        mode: The current IOMode value.
        rock: Filter mode's function address; otherwise decoration.
    """

    def __init__(self) -> None:
        """Start in the null system, as the machine does."""

        self.mode: int = IOMode.NULL
        self.rock = 0

    def select(self, mode: int, rock: int) -> None:
        """Select an output system.

        An unrecognized mode is not an error: the spec says setting
        an unsupported system selects the null system instead,
        which is exactly what a program probing with an unknown
        mode should find (Glulx: Output).
        """

        if mode not in (IOMode.NULL, IOMode.FILTER, IOMode.GLK):
            mode = IOMode.NULL
            rock = 0

        self.mode = mode
        self.rock = rock

    def reset(self) -> None:
        """Return to the null system -- restart's share."""

        self.mode = IOMode.NULL
        self.rock = 0
