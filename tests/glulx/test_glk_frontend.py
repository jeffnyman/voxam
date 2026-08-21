"""The display contract: what every frontend inherits."""

import pytest
from assertpy import assert_that

from voxam.errors import GlulxSessionEnd
from voxam.glulx.glk.api import Glk
from voxam.glulx.glk.frontend import Frontend, NullFrontend
from voxam.glulx.glk.objects import (
    CHARACTER_CELL,
    Event,
    EventType,
    SoundChannel,
    TextBufferWindow,
    Window,
)
from voxam.glulx.glk.resources import ImageInfo


class Bare(Frontend):
    """The minimum concrete display: everything else inherited."""

    def size(self) -> tuple[int, int]:
        return (80, 24)

    def flush(self, root: Window | None) -> None:
        pass

    def read_line(self, _window: Window, _maxlen: int) -> tuple[str, int] | None:
        return None

    def read_char(self, _window: Window) -> int | None:
        return None


# Every default answers "cannot": the capability flags are False,
# the optional hooks are inert, and the metrics are the character
# cell -- a display claims more only by overriding.
def test_the_contract_defaults_to_cannot() -> None:
    display = Bare()
    window = TextBufferWindow()
    channel = SoundChannel()
    picture = ImageInfo(1, b"PNG ", b"", 4, 4)

    assert_that(display.size()).is_equal_to((80, 24))

    display.flush(None)

    assert_that(display.read_line(window, 8)).is_none()
    assert_that(display.read_char(window)).is_none()

    assert_that(display.timer_input).is_false()
    assert_that(display.mouse_input).is_false()
    assert_that(display.hyperlink_input).is_false()
    assert_that(display.graphics).is_false()
    assert_that(display.sound).is_false()
    assert_that(display.echoes_input).is_false()
    assert_that(display.metrics_for(window)).is_equal_to(CHARACTER_CELL)

    assert_that(display.style_distinguish(window, 0, 1)).is_false()
    assert_that(display.style_measure(window, 0, 0)).is_none()
    assert_that(display.draw_image(window, picture, 0, 0, 4, 4)).is_false()
    assert_that(display.read_mouse(window)).is_none()
    assert_that(display.read_hyperlink(window)).is_none()
    assert_that(display.prompt_file(0, 0)).is_none()

    display.set_timer(100)
    display.erase_rect(window, 0, 0, 1, 1)
    display.fill_rect(window, 0xFF0000, 0, 0, 1, 1)
    display.set_background_color(window, 0xFF0000)
    display.flow_break(window)
    display.play_sound(channel, 3, 1, 0)
    display.stop_sound(channel)
    display.pause_sound(channel, True)
    display.set_volume(channel, 0x10000, 0)


# An unattached display swallows its own events; an attached one
# queues them with the library for the next select.
def test_posting_needs_an_attachment() -> None:
    display = Bare()
    event = Event(EventType.TIMER)

    display.post(event)

    library = Glk(display)

    display.post(event)

    assert_that(display.glk).is_same_as(library)
    assert_that(library.pending_events).is_equal_to([event])


# The null display shows nothing and, asked for input that can
# never arrive, ends the session rather than hanging forever.
def test_the_null_display_ends_rather_than_hangs() -> None:
    display = NullFrontend()
    window = TextBufferWindow()

    assert_that(display.size()).is_equal_to((80, 24))

    display.flush(None)

    with pytest.raises(GlulxSessionEnd):
        display.read_line(window, 80)

    with pytest.raises(GlulxSessionEnd):
        display.read_char(window)
