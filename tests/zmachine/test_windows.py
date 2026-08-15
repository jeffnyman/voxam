import pytest
from assertpy import assert_that

from voxam.errors import ZMachineScreenError
from voxam.zmachine.windows import (
    ATTRIBUTES,
    BUFFERING,
    COLOUR_DATA,
    FONT_SIZE,
    LEFT_MARGIN,
    LINE_COUNT,
    RIGHT_MARGIN,
    SCROLLING,
    TRANSCRIPTING,
    TRUE_FOREGROUND,
    WRAPPING,
    X_COORDINATE,
    X_SIZE,
    Y_COORDINATE,
    Y_SIZE,
    WindowLedger,
)


def ledger() -> WindowLedger:
    return WindowLedger(lines=24, columns=80, foreground=9, background=2)


# The §8.8 boot state: window 0 fills the screen with all four
# attributes -- running text wraps, scrolls, and echoes -- while
# the other seven begin buffered only and sizeless, exactly the
# defaults §8.8.3.1.2's example describes. Font size packs height
# high and width low (§8.8.3.2.5), colour data background high and
# foreground low (§8.8.3.2.4).
def test_the_boot_state_matches_the_spec_defaults() -> None:
    windows = ledger()

    assert_that(windows.property(0, Y_SIZE)).is_equal_to(24)
    assert_that(windows.property(0, X_SIZE)).is_equal_to(80)
    assert_that(windows.property(0, ATTRIBUTES)).is_equal_to(
        WRAPPING | SCROLLING | TRANSCRIPTING | BUFFERING
    )
    assert_that(windows.property(3, Y_SIZE)).is_zero()
    assert_that(windows.property(3, ATTRIBUTES)).is_equal_to(BUFFERING)
    assert_that(windows.property(5, FONT_SIZE)).is_equal_to(0x0101)
    assert_that(windows.property(5, COLOUR_DATA)).is_equal_to(0x0209)


# The code -3 -- or the unsigned word 65533 an operand carries --
# names the currently selected window, and a number naming none of
# the eight is refused (§8.8.3).
def test_minus_three_resolves_to_the_selection() -> None:
    windows = ledger()
    windows.selected = 5

    assert_that(windows.resolve(-3)).is_equal_to(5)
    assert_that(windows.resolve(0xFFFD)).is_equal_to(5)
    assert_that(windows.resolve(7)).is_equal_to(7)

    with pytest.raises(ZMachineScreenError, match="not one of the eight"):
        windows.resolve(8)


# Properties 0 to 15 are writeable; the true colours "must not be
# written", and the eighteen-entry table has no nineteenth
# (§8.8.3.2).
def test_property_writes_are_policed() -> None:
    windows = ledger()

    windows.write_property(0, LINE_COUNT, 999)

    assert_that(windows.property(0, LINE_COUNT)).is_equal_to(999)

    with pytest.raises(ZMachineScreenError, match="must not be written"):
        windows.write_property(0, TRUE_FOREGROUND, 1)

    with pytest.raises(ZMachineScreenError, match="eighteen"):
        windows.property(0, 18)


# A move places the top left in units, a resize sets the extent,
# and neither disturbs the other (§15 move_window, window_size).
def test_moves_and_resizes_are_recorded() -> None:
    windows = ledger()

    windows.move(3, 5, 8)
    windows.resize(3, 2, 40)

    assert_that(windows.property(3, Y_COORDINATE)).is_equal_to(5)
    assert_that(windows.property(3, X_COORDINATE)).is_equal_to(8)
    assert_that(windows.property(3, Y_SIZE)).is_equal_to(2)
    assert_that(windows.property(3, X_SIZE)).is_equal_to(40)


# window_style's four operations: set outright, turn on, turn off,
# reverse -- and a fifth is refused (§15 window_style).
def test_the_four_style_operations() -> None:
    windows = ledger()

    windows.restyle(2, WRAPPING | SCROLLING, 0)

    assert_that(windows.property(2, ATTRIBUTES)).is_equal_to(WRAPPING | SCROLLING)

    windows.restyle(2, BUFFERING, 1)

    assert_that(windows.property(2, ATTRIBUTES)).is_equal_to(
        WRAPPING | SCROLLING | BUFFERING
    )

    windows.restyle(2, SCROLLING, 2)

    assert_that(windows.property(2, ATTRIBUTES)).is_equal_to(WRAPPING | BUFFERING)

    windows.restyle(2, WRAPPING | TRANSCRIPTING, 3)

    assert_that(windows.property(2, ATTRIBUTES)).is_equal_to(TRANSCRIPTING | BUFFERING)

    with pytest.raises(ZMachineScreenError, match="not one of"):
        windows.restyle(2, 1, 4)


# Margin sizes land in their two properties (§8.8.3.2.1).
def test_margins_are_recorded() -> None:
    windows = ledger()

    windows.set_margins(1, 5, 7)

    assert_that(windows.property(1, LEFT_MARGIN)).is_equal_to(5)
    assert_that(windows.property(1, RIGHT_MARGIN)).is_equal_to(7)
