"""The Version 6 window ledger: §8.8's eight windows as pure state.

Version 6 keeps eight windows, each with a position and size in
units, a cursor, four attribute flags, and eighteen numbered
properties (§8.8.3). The properties are machine state before they
are anything visual -- get_wind_prop reads them and ZIPTEST's
window tests do little else -- so this ledger keeps them faithfully
with no glass in sight. The character frontends keep rendering
windows 0 and 1 as they always have; painting all eight is the
graphics frontend's work, in a release to come.
"""

from voxam.errors import ZMachineScreenError

# Eight windows, numbered 0 to 7; the code -3 -- the unsigned word
# 65533, as an operand carries it -- means "the currently selected
# window" (§8.8.3).
WINDOW_COUNT = 8
CURRENT_WINDOW = -3
UNSIGNED_CURRENT = 0xFFFD

# §8.8.3.2's eighteen properties, by number. Properties 0 to 15
# are writeable with put_wind_prop; the true colours must not be
# written.
Y_COORDINATE = 0
X_COORDINATE = 1
Y_SIZE = 2
X_SIZE = 3
Y_CURSOR = 4
X_CURSOR = 5
LEFT_MARGIN = 6
RIGHT_MARGIN = 7
NEWLINE_ROUTINE = 8
INTERRUPT_COUNTDOWN = 9
TEXT_STYLE = 10
COLOUR_DATA = 11
FONT_NUMBER = 12
FONT_SIZE = 13
ATTRIBUTES = 14
LINE_COUNT = 15
TRUE_FOREGROUND = 16
TRUE_BACKGROUND = 17
PROPERTY_COUNT = 18
LAST_WRITABLE = 15

# §8.8.3.1's four attributes, as the flag bits window_style speaks:
# wrapping, scrolling, copying to the transcript, and buffered
# printing. Window 0 begins with all four -- running text wraps,
# scrolls, and echoes -- while the others begin buffered only,
# exactly the defaults §8.8.3.1.2's example describes.
WRAPPING = 1
SCROLLING = 2
TRANSCRIPTING = 4
BUFFERING = 8

# window_style's operations on those flags (§15 window_style):
# set outright, turn bits on, turn bits off, or reverse them.
STYLE_SET = 0
STYLE_ON = 1
STYLE_OFF = 2
STYLE_REVERSE = 3

# The font size property carries height in its upper byte and
# width in its lower (§8.8.3.2.5); a character glass's 1-by-1 font
# packs to $0101, a measuring glass to its real cell. Colour data
# likewise carries background high and foreground low (§8.8.3.2.4).
BYTE_SHIFT = 8


class WindowLedger:
    """Eight windows' worth of §8.8 bookkeeping, and the selection.

    Attributes:
        selected: The currently selected window's number, which
            the code -3 resolves to (§8.8.3).
    """

    def __init__(  # noqa: PLR0913 -- a boot state names all its units
        self,
        height: int,
        width: int,
        foreground: int,
        background: int,
        *,
        font_width: int = 1,
        font_height: int = 1,
    ) -> None:
        """Set every window to its §8.8 boot state.

        Args:
            height: The screen height in units -- lines on a
                character glass whose font is 1 by 1, real pixels
                on a glass that measures.
            width: The screen width in units.
            foreground: The default foreground colour code.
            background: The default background colour code.
            font_width: One character cell's width in units.
            font_height: One character cell's height in units.
        """

        self.selected = 0
        self._windows: list[list[int]] = []

        for number in range(WINDOW_COUNT):
            window = [0] * PROPERTY_COUNT
            window[Y_COORDINATE] = 1
            window[X_COORDINATE] = 1
            window[Y_CURSOR] = 1
            window[X_CURSOR] = 1
            window[FONT_NUMBER] = 1
            window[FONT_SIZE] = (font_height << BYTE_SHIFT) | font_width
            window[COLOUR_DATA] = (background << BYTE_SHIFT) | foreground
            window[ATTRIBUTES] = BUFFERING

            if number == 0:
                window[Y_SIZE] = height
                window[X_SIZE] = width
                window[ATTRIBUTES] = WRAPPING | SCROLLING | TRANSCRIPTING | BUFFERING
            elif number == 1:
                # Screen-wide and flat: §8.8.4.1's split tiles this
                # window against 0 without touching widths, so a
                # width must already be here for the split to mean
                # anything.
                window[X_SIZE] = width

            self._windows.append(window)

    def resolve(self, window: int) -> int:
        """The window a number names, -3 meaning the selected one.

        Raises:
            ZMachineScreenError: For a number naming none of the
                eight (§8.8.3).
        """

        if window in (CURRENT_WINDOW, UNSIGNED_CURRENT):
            return self.selected

        if 0 <= window < WINDOW_COUNT:
            return window

        msg = f"window {window} is not one of the eight (§8.8.3)"

        raise ZMachineScreenError(msg)

    def property(self, window: int, number: int) -> int:
        """Read one §8.8.3.2 property, as get_wind_prop does.

        Raises:
            ZMachineScreenError: For a window naming none of the
                eight, or a property number past 17.
        """

        return self._windows[self.resolve(window)][self._known(number)]

    def write_property(self, window: int, number: int, value: int) -> None:
        """Write one property, as put_wind_prop does (§8.8.3.2).

        Raises:
            ZMachineScreenError: For an unknown window or
                property, or for the true colour properties,
                which "must not be written" (§8.8.3.2).
        """

        if self._known(number) > LAST_WRITABLE:
            msg = (
                f"window property {number} is a true colour, which "
                f"must not be written (§8.8.3.2)"
            )

            raise ZMachineScreenError(msg)

        self._windows[self.resolve(window)][number] = value

    def move(self, window: int, y: int, x: int) -> None:
        """Place a window's top left at (y, x) in units (§15).

        Whatever the window already printed stays where it was:
        §8.8.3 is explicit that nothing on screen belongs to a
        window once printed.
        """

        target = self._windows[self.resolve(window)]
        target[Y_COORDINATE] = y
        target[X_COORDINATE] = x

    def resize(self, window: int, height: int, width: int) -> None:
        """Set a window's size in units, as window_size does (§15)."""

        target = self._windows[self.resolve(window)]
        target[Y_SIZE] = height
        target[X_SIZE] = width

    def restyle(self, window: int, flags: int, operation: int) -> None:
        """Change a window's attribute flags (§15 window_style).

        Operation 0 sets the flags outright, 1 turns the given
        bits on, 2 turns them off, and 3 reverses them.

        Raises:
            ZMachineScreenError: For an operation §15 does not
                name.
        """

        target = self._windows[self.resolve(window)]

        if operation == STYLE_SET:
            target[ATTRIBUTES] = flags
        elif operation == STYLE_ON:
            target[ATTRIBUTES] |= flags
        elif operation == STYLE_OFF:
            target[ATTRIBUTES] &= ~flags & 0xFFFF
        elif operation == STYLE_REVERSE:
            target[ATTRIBUTES] ^= flags
        else:
            msg = (
                f"window_style operation {operation} is not one of "
                f"§15's four (set, on, off, reverse)"
            )

            raise ZMachineScreenError(msg)

    def set_margins(self, window: int, left: int, right: int) -> None:
        """Set a window's margin sizes, in units (§8.8.3.2.1).

        The §8.8.3.2.2.2 cursor nudge -- moving a cursor the new
        margins would strand -- waits on a glass that renders
        margins at all.
        """

        target = self._windows[self.resolve(window)]
        target[LEFT_MARGIN] = left
        target[RIGHT_MARGIN] = right

    def _known(self, number: int) -> int:
        """Police a property number against §8.8.3.2's eighteen.

        Raises:
            ZMachineScreenError: For a number past the table.
        """

        if not 0 <= number < PROPERTY_COUNT:
            msg = f"window property {number} is not one of §8.8.3.2's eighteen"

            raise ZMachineScreenError(msg)

        return number
