"""The Glk function surface, driven the way the bridge will."""

import datetime
from pathlib import Path
from typing import cast

import pytest
from assertpy import assert_that

from voxam.blorb import Blorb
from voxam.errors import GlulxGlkError, GlulxSessionEnd
from voxam.glulx.glk.api import (
    CHAR_OUTPUT_CANNOT_PRINT,
    CHAR_OUTPUT_EXACT_PRINT,
    GLK_VERSION,
    Glk,
    GlkGestalt,
    Prompting,
    Waiting,
)
from voxam.glulx.glk.dispatch import all_signatures
from voxam.glulx.glk.frontend import Frontend
from voxam.glulx.glk.objects import (
    Event,
    EventType,
    FileMode,
    FileUsage,
    KeyCode,
    PairWindow,
    Run,
    SeekMode,
    SoundChannel,
    Style,
    TextBufferWindow,
    TextGridWindow,
    Window,
    WindowMethod,
    WindowType,
)
from voxam.glulx.glk.refs import Ref, RefStruct
from voxam.glulx.glk.resources import Resources
from voxam.iff import chunk

RIDX_ENTRY = 12
FORM_PRELUDE = 12

ABOVE_FIXED = WindowMethod.ABOVE | WindowMethod.FIXED
BELOW_FIXED = WindowMethod.BELOW | WindowMethod.FIXED
LEFT_PROPORTIONAL = WindowMethod.LEFT | WindowMethod.PROPORTIONAL


def blorb(*entries: tuple[bytes, int, bytes, bytes]) -> Blorb:
    index = len(entries).to_bytes(4, "big")
    body = b""
    ridx = chunk(b"RIdx", index + b"\x00" * RIDX_ENTRY * len(entries))
    offset = FORM_PRELUDE + len(ridx)

    for usage, number, chunk_id, payload in entries:
        index += usage + number.to_bytes(4, "big") + offset.to_bytes(4, "big")
        framed = chunk(chunk_id, payload)
        body += framed
        offset += len(framed)

    return Blorb.parse(chunk(b"FORM", b"IFRS" + chunk(b"RIdx", index) + body))


def png(width: int, height: int) -> bytes:
    return (
        b"\x89PNG\r\n\x1a\n"
        + (13).to_bytes(4, "big")
        + b"IHDR"
        + width.to_bytes(4, "big")
        + height.to_bytes(4, "big")
    )


class Quiet(Frontend):
    """A recording display: 100x50, no input of its own."""

    def __init__(self) -> None:
        self.flushes = 0
        self.timers: list[int] = []
        self.calls: list[tuple[object, ...]] = []

    def size(self) -> tuple[int, int]:
        return (100, 50)

    def flush(self, _root: Window | None) -> None:
        self.flushes += 1

    def read_line(self, _window: Window, _maxlen: int) -> tuple[str, int] | None:
        return None

    def read_char(self, _window: Window) -> int | None:
        return None

    def set_timer(self, millisecs: int) -> None:
        self.timers.append(millisecs)


class Suspending(Quiet):
    """A display that cannot block: never asked, only delivered to."""

    suspends = True

    def read_line(self, _window: Window, _maxlen: int) -> tuple[str, int] | None:
        pytest.fail("a suspending display is never asked for a line")

    def read_char(self, _window: Window) -> int | None:
        pytest.fail("a suspending display is never asked for a key")


class Typist(Quiet):
    """Delivers scripted lines; a None entry posts a timer instead."""

    def __init__(self, lines: list[tuple[str, int] | None]) -> None:
        super().__init__()
        self.lines = lines

    def read_line(self, _window: Window, _maxlen: int) -> tuple[str, int] | None:
        answer = self.lines.pop(0)

        if answer is None:
            self.post(Event(EventType.TIMER))

        return answer


class Keyist(Quiet):
    """Delivers scripted keystrokes; None posts a timer instead."""

    def __init__(self, chars: list[int | None]) -> None:
        super().__init__()
        self.chars = chars

    def read_char(self, _window: Window) -> int | None:
        answer = self.chars.pop(0)

        if answer is None:
            self.post(Event(EventType.TIMER))

        return answer


class Clicker(Quiet):
    """Delivers scripted clicks; a None entry means "not yet"."""

    mouse_input = True

    def __init__(self, mice: list[tuple[int, int] | None]) -> None:
        super().__init__()
        self.mice = mice

    def read_mouse(self, _window: Window) -> tuple[int, int] | None:
        return self.mice.pop(0)


class Linker(Quiet):
    """Delivers scripted link selections; zero means "not yet"."""

    hyperlink_input = True

    def __init__(self, links: list[int]) -> None:
        super().__init__()
        self.links = links

    def read_hyperlink(self, _window: Window) -> int | None:
        return self.links.pop(0)


class Sounder(Quiet):
    """A display that plays sound, scripted to accept or refuse."""

    sound = True

    def __init__(self, accepts: bool = True) -> None:
        super().__init__()
        self.accepts = accepts

    def play_sound(
        self, _channel: SoundChannel, sound: int, repeats: int, notify: int
    ) -> bool:
        self.calls.append(("play", sound, repeats, notify))

        return self.accepts

    def stop_sound(self, _channel: SoundChannel) -> None:
        self.calls.append(("stop",))

    def pause_sound(self, _channel: SoundChannel, paused: bool) -> None:
        self.calls.append(("pause", paused))

    def set_volume(self, _channel: SoundChannel, volume: int, duration: int) -> None:
        self.calls.append(("volume", volume, duration))


class Artist(Quiet):
    """A display that draws, recording every graphics call."""

    graphics = True

    def draw_image(
        self,
        _window: Window,
        _image: object,
        val1: int,
        val2: int,
        width: int,
        height: int,
    ) -> bool:
        self.calls.append(("draw", val1, val2, width, height))

        return True

    def erase_rect(
        self, _window: Window, left: int, top: int, width: int, height: int
    ) -> None:
        self.calls.append(("erase", left, top, width, height))

    def fill_rect(
        self,
        _window: Window,
        color: int,
        _left: int,
        _top: int,
        _width: int,
        _height: int,
    ) -> None:
        self.calls.append(("fill", color))

    def set_background_color(self, _window: Window, color: int) -> None:
        self.calls.append(("background", color))

    def flow_break(self, _window: Window) -> None:
        self.calls.append(("flow",))


class Styler(Quiet):
    """A display that can tell styles apart and measure them."""

    def style_distinguish(self, _window: Window, _first: int, _second: int) -> bool:
        return True

    def style_measure(self, _window: Window, _style: int, _hint: int) -> int | None:
        return 7


class Prompter(Quiet):
    """A display whose file prompt answers a scripted name."""

    def __init__(self, name: str | None) -> None:
        super().__init__()
        self.name = name

    def prompt_file(self, _usage: int, _fmode: int) -> str | None:
        return self.name


def rooted(display: Frontend | None = None) -> tuple[Glk, Window]:
    """A library with one text-buffer window open as the root."""

    library = Glk(display if display is not None else Quiet())
    window = library.glk_window_open(None, 0, 0, WindowType.TEXT_BUFFER, 1)

    if window is None:
        pytest.fail("the root window did not open")

    return library, window


# The whole dispatch table must land somewhere: every declared
# selector's glk_name is a callable on the library. When a later
# Glk adds functions this surface lacks, this is the test that
# says so by name.
def test_every_dispatch_signature_has_a_function() -> None:
    for signature in all_signatures().values():
        assert_that(callable(getattr(Glk, signature.glk_name, None))).described_as(
            signature.glk_name
        ).is_true()


# glk_exit shows what is pending and ends the session; glk_tick
# does nothing at all.
def test_exit_flushes_and_ends() -> None:
    display = Quiet()
    library = Glk(display)

    library.glk_tick()

    with pytest.raises(GlulxSessionEnd):
        library.glk_exit()

    assert_that(display.flushes).is_equal_to(1)


# The gestalt selectors answer for this library over this display:
# version, character rules, and one answer per capability flag --
# with unknown selectors at zero for programs from the future.
def test_gestalt_answers_for_the_display() -> None:
    library = Glk(Quiet())

    answers = {
        (GlkGestalt.VERSION, 0): GLK_VERSION,
        (GlkGestalt.CHAR_INPUT, 0x41): 1,
        (GlkGestalt.CHAR_INPUT, KeyCode.RETURN): 1,
        (GlkGestalt.CHAR_INPUT, KeyCode.UNKNOWN): 0,
        (GlkGestalt.CHAR_INPUT, 0x07): 0,
        (GlkGestalt.LINE_INPUT, 0x41): 1,
        (GlkGestalt.LINE_INPUT, 0x0A): 0,
        (GlkGestalt.CHAR_OUTPUT, 0x41): CHAR_OUTPUT_EXACT_PRINT,
        (GlkGestalt.CHAR_OUTPUT, 0x07): CHAR_OUTPUT_CANNOT_PRINT,
        (GlkGestalt.GRAPHICS, 0): 0,
        (GlkGestalt.DRAW_IMAGE, WindowType.GRAPHICS): 0,
        (GlkGestalt.SOUND, 0): 0,
        (GlkGestalt.SOUND2, 0): 0,
        (GlkGestalt.MOUSE_INPUT, WindowType.TEXT_GRID): 0,
        (GlkGestalt.TIMER, 0): 0,
        (GlkGestalt.HYPERLINKS, 0): 1,
        (GlkGestalt.HYPERLINK_INPUT, 0): 0,
        (GlkGestalt.UNICODE, 0): 1,
        (GlkGestalt.UNICODE_NORM, 0): 1,
        (GlkGestalt.LINE_INPUT_ECHO, 0): 1,
        (GlkGestalt.LINE_TERMINATORS, 0): 1,
        (GlkGestalt.DATE_TIME, 0): 1,
        (GlkGestalt.RESOURCE_STREAM, 0): 1,
        (GlkGestalt.GRAPHICS_TRANSPARENCY, 0): 0,
        (GlkGestalt.GRAPHICS_CHAR_INPUT, 0): 0,
        (99, 0): 0,
    }

    for (selector, value), expected in answers.items():
        assert_that(library.glk_gestalt(selector, value)).described_as(
            f"selector {selector}"
        ).is_equal_to(expected)

    # A drawing display draws images only in graphics windows --
    # the spec's own "both, neither, or only one" (Glk: Testing
    # for Graphics Capabilities) -- and claims transparency now
    # that alpha travels the whole way to the blit.
    drawing = Glk(Artist())

    assert_that(
        drawing.glk_gestalt(GlkGestalt.DRAW_IMAGE, WindowType.GRAPHICS)
    ).is_equal_to(1)
    assert_that(
        drawing.glk_gestalt(GlkGestalt.DRAW_IMAGE_SCALE, WindowType.GRAPHICS)
    ).is_equal_to(1)
    assert_that(
        drawing.glk_gestalt(GlkGestalt.DRAW_IMAGE, WindowType.TEXT_BUFFER)
    ).is_equal_to(0)
    assert_that(drawing.glk_gestalt(GlkGestalt.GRAPHICS, 0)).is_equal_to(1)
    assert_that(drawing.glk_gestalt(GlkGestalt.GRAPHICS_TRANSPARENCY, 0)).is_equal_to(1)
    assert_that(drawing.glk_gestalt(GlkGestalt.GRAPHICS_CHAR_INPUT, 0)).is_equal_to(1)

    # A clicking display still only carries a mouse in grids and
    # graphics windows.
    clicking = Glk(Clicker([]))

    assert_that(
        clicking.glk_gestalt(GlkGestalt.MOUSE_INPUT, WindowType.TEXT_GRID)
    ).is_equal_to(1)
    assert_that(
        clicking.glk_gestalt(GlkGestalt.MOUSE_INPUT, WindowType.TEXT_BUFFER)
    ).is_equal_to(0)

    # The extended form reports printability into its array, when
    # one with room arrives.
    room = [9]

    library.glk_gestalt_ext(GlkGestalt.CHAR_OUTPUT, 0x41, room)

    assert_that(room).is_equal_to([1])

    library.glk_gestalt_ext(GlkGestalt.CHAR_OUTPUT, 0x07, room)

    assert_that(room).is_equal_to([0])
    assert_that(library.glk_gestalt_ext(GlkGestalt.CHAR_OUTPUT, 0x41, [])).is_equal_to(
        CHAR_OUTPUT_EXACT_PRINT
    )


# The first window opens with no split; every later one names the
# window it splits. The tree wires pairs in above whichever child
# was split, on either side.
def test_windows_split_into_a_tree() -> None:
    library, first = rooted()

    second = library.glk_window_open(first, ABOVE_FIXED, 3, WindowType.TEXT_GRID, 2)
    third = library.glk_window_open(second, LEFT_PROPORTIONAL, 40, WindowType.BLANK, 3)
    fourth = library.glk_window_open(first, BELOW_FIXED, 2, WindowType.TEXT_GRID, 4)

    root = library.glk_window_get_root()

    assert_that(library.glk_window_get_type(root)).is_equal_to(WindowType.PAIR)
    assert_that(library.glk_window_get_parent(root)).is_none()
    assert_that(library.glk_window_get_parent(None)).is_none()

    # first and fourth share a pair; so do second and third.
    assert_that(library.glk_window_get_sibling(first)).is_same_as(fourth)
    assert_that(library.glk_window_get_sibling(fourth)).is_same_as(first)
    assert_that(library.glk_window_get_sibling(second)).is_same_as(third)
    assert_that(library.glk_window_get_sibling(root)).is_none()
    assert_that(library.glk_window_get_sibling(None)).is_none()

    # The grid got its fixed three rows of the 100x50 display.
    width = Ref()
    height = Ref()

    library.glk_window_get_size(second, width, height)

    assert_that((width.value, height.value)).is_equal_to((60, 3))

    library.glk_window_get_size(None, width, height)

    assert_that((width.value, height.value)).is_equal_to((0, 0))

    library.glk_window_get_size(second, None, None)

    # The walk visits every live window, newest first, and answers
    # rocks along the way.
    rock = Ref()
    seen = []
    current = library.glk_window_iterate(None, rock)

    while current is not None:
        seen.append(rock.value)
        current = library.glk_window_iterate(current, rock)

    assert_that(rock.value).is_equal_to(0)
    assert_that(len(seen)).is_equal_to(7)

    # A window not on the list ends the walk; so does an empty one.
    assert_that(library.glk_window_iterate(TextBufferWindow(), None)).is_none()
    assert_that(Glk(Quiet()).glk_window_iterate(None, None)).is_none()

    assert_that(library.glk_window_get_rock(first)).is_equal_to(1)
    assert_that(library.glk_window_get_rock(None)).is_equal_to(0)


# Closing a window promotes its sibling into the pair's place --
# through the grandparent on either side, and to the root when the
# pair was the root.
def test_closing_promotes_the_sibling() -> None:
    library, first = rooted()

    second = library.glk_window_open(first, ABOVE_FIXED, 3, WindowType.TEXT_GRID, 2)
    third = library.glk_window_open(second, LEFT_PROPORTIONAL, 40, WindowType.BLANK, 3)
    fourth = library.glk_window_open(first, BELOW_FIXED, 2, WindowType.TEXT_GRID, 4)

    counts = RefStruct(2)

    library.glk_window_close(third, counts)

    assert_that(counts.fields).is_equal_to([0, 0])
    assert_that(library.glk_window_get_sibling(second)).is_instance_of(PairWindow)

    library.glk_window_close(fourth, None)

    assert_that(library.glk_window_get_sibling(first)).is_same_as(second)

    library.glk_window_close(second, None)

    assert_that(library.glk_window_get_root()).is_same_as(first)

    library.glk_window_close(first, None)

    assert_that(library.glk_window_get_root()).is_none()
    assert_that(library.windows).is_empty()
    assert_that(library.streams).is_empty()

    library.glk_window_close(first, None)

    assert_that(library.glk_window_get_root()).is_none()


# Closing a pair closes its whole subtree, and takes the current
# stream with it when a closed window held it.
def test_closing_a_pair_closes_the_subtree() -> None:
    library, first = rooted()

    library.glk_window_open(first, ABOVE_FIXED, 3, WindowType.TEXT_GRID, 2)

    library.glk_set_window(first)

    pair = library.glk_window_get_parent(first)

    library.glk_window_close(pair, None)

    assert_that(library.glk_window_get_root()).is_none()
    assert_that(library.windows).is_empty()
    assert_that(library.glk_stream_get_current()).is_none()

    with pytest.raises(GlulxGlkError, match="window_close"):
        library.glk_window_close(None, None)


# A split must be coherent: the first window takes no split, later
# ones need one, and the method must name a division and a
# direction. Pair windows cannot be opened directly at all.
def test_incoherent_splits_are_refused() -> None:
    library = Glk(Quiet())

    stray = TextBufferWindow()

    with pytest.raises(GlulxGlkError, match="must be null"):
        library.glk_window_open(stray, ABOVE_FIXED, 1, WindowType.TEXT_BUFFER, 0)

    library, first = rooted()

    with pytest.raises(GlulxGlkError, match="must not be null"):
        library.glk_window_open(None, 0, 0, WindowType.TEXT_BUFFER, 0)

    with pytest.raises(GlulxGlkError, match="neither fixed nor proportional"):
        library.glk_window_open(first, WindowMethod.ABOVE, 1, WindowType.BLANK, 0)

    with pytest.raises(GlulxGlkError, match="names no direction"):
        library.glk_window_open(
            first, WindowMethod.FIXED | 0x04, 1, WindowType.BLANK, 0
        )

    with pytest.raises(GlulxGlkError, match="pair window"):
        library.glk_window_open(first, ABOVE_FIXED, 1, WindowType.PAIR, 0)

    # An unsupported type answers None: graphics without a drawing
    # display, and types from a Glk yet to be written.
    assert_that(
        library.glk_window_open(first, ABOVE_FIXED, 1, WindowType.GRAPHICS, 0)
    ).is_none()
    assert_that(library.glk_window_open(first, ABOVE_FIXED, 1, 99, 0)).is_none()

    # A drawing display opens one happily.
    drawing, base = rooted(Artist())

    assert_that(
        drawing.glk_window_open(base, ABOVE_FIXED, 8, WindowType.GRAPHICS, 0)
    ).is_not_none()


# A canvas takes character input wherever a canvas can exist at
# all: the request arms like any other window's, the keyboard
# answers it, and the keystroke comes back on the canvas (Glk:
# Character Input Events).
def test_a_canvas_takes_character_input() -> None:
    class DrawingKeyist(Keyist):
        graphics = True

    library, first = rooted(DrawingKeyist([ord("m")]))
    canvas = library.glk_window_open(first, ABOVE_FIXED, 8, WindowType.GRAPHICS, 0)

    if canvas is None:
        pytest.fail("the canvas did not open")

    library.glk_request_char_event(canvas)

    event = RefStruct(4)

    library.glk_select(event)

    assert_that(event.fields).is_equal_to([EventType.CHAR_INPUT, canvas, ord("m"), 0])
    assert_that(canvas.char_request).is_false()


# A rearrange that moves a real canvas clears it and owes the
# game a redraw event -- "the window in question has been cleared
# to its background color, and must be redrawn" (Glk: Window
# Events). Opening one owes nothing: a fresh canvas is background
# and the game knows it.
def test_a_moved_canvas_earns_a_redraw_event() -> None:
    library, first = rooted(Artist())
    canvas = library.glk_window_open(first, ABOVE_FIXED, 8, WindowType.GRAPHICS, 0)

    if canvas is None:
        pytest.fail("the canvas did not open")

    assert_that(library.pending_events).is_empty()

    pair = library.glk_window_get_parent(canvas)
    library.glk_window_set_arrangement(pair, ABOVE_FIXED, 12, canvas)

    redraws = [
        event for event in library.pending_events if event.kind == EventType.REDRAW
    ]

    assert_that(redraws).is_length(1)
    assert_that(redraws[0].window).is_same_as(canvas)


# Changing a pair's direction moves the size constraint to the
# other child while the glass stays where it is -- the spec's own
# worked example (Glk: Changing Window Constraints).
def test_arrangements_change_and_report() -> None:
    library, first = rooted()

    second = library.glk_window_open(first, ABOVE_FIXED, 3, WindowType.TEXT_GRID, 2)
    pair = library.glk_window_get_parent(first)

    library.glk_window_set_arrangement(pair, BELOW_FIXED, 5, first)

    method = Ref()
    size = Ref()
    key = Ref()

    library.glk_window_get_arrangement(pair, method, size, key)

    assert_that(method.value).is_equal_to(BELOW_FIXED)
    assert_that(size.value).is_equal_to(5)
    assert_that(key.value).is_same_as(first)

    # The grid is still on top; the buffer below now carries the
    # fixed five rows.
    width = Ref()
    height = Ref()

    library.glk_window_get_size(first, width, height)

    assert_that((width.value, height.value)).is_equal_to((100, 5))

    library.glk_window_get_size(second, width, height)

    assert_that((width.value, height.value)).is_equal_to((100, 45))

    library.glk_window_set_arrangement(pair, ABOVE_FIXED, 2, None)
    library.glk_window_set_arrangement(pair, ABOVE_FIXED, 3, None)
    library.glk_window_get_arrangement(pair, None, None, None)

    with pytest.raises(GlulxGlkError, match="not a pair"):
        library.glk_window_set_arrangement(second, ABOVE_FIXED, 1, None)

    with pytest.raises(GlulxGlkError, match="not a pair"):
        library.glk_window_get_arrangement(None, None, None, None)

    with pytest.raises(GlulxGlkError, match="cannot change its axis"):
        library.glk_window_set_arrangement(
            pair, WindowMethod.LEFT | WindowMethod.FIXED, 1, None
        )

    with pytest.raises(GlulxGlkError, match="cannot be a pair"):
        library.glk_window_set_arrangement(pair, ABOVE_FIXED, 1, pair)

    # A key from outside the pair's own subtree is refused.
    inner = library.glk_window_open(second, ABOVE_FIXED, 1, WindowType.BLANK, 0)
    inner_pair = library.glk_window_get_parent(inner)

    with pytest.raises(GlulxGlkError, match="under the pair"):
        library.glk_window_set_arrangement(inner_pair, ABOVE_FIXED, 1, first)


# The window functions that just fetch or clear behave under both
# a window and the null window.
def test_window_oddments_tolerate_null() -> None:
    library, first = rooted()

    grid = library.glk_window_open(first, ABOVE_FIXED, 3, WindowType.TEXT_GRID, 2)

    library.glk_window_clear(first)
    library.glk_window_clear(None)

    assert_that(first.pending_clear).is_true()

    library.glk_window_move_cursor(grid, 1, 0)

    with pytest.raises(GlulxGlkError, match="not a text grid"):
        library.glk_window_move_cursor(first, 0, 0)

    assert_that(library.glk_window_get_stream(first)).is_same_as(first.stream)
    assert_that(library.glk_window_get_stream(None)).is_none()

    echo = library.glk_stream_open_memory([0] * 8, FileMode.WRITE, 0)

    library.glk_window_set_echo_stream(first, echo)
    library.glk_window_set_echo_stream(None, echo)

    assert_that(library.glk_window_get_echo_stream(first)).is_same_as(echo)
    assert_that(library.glk_window_get_echo_stream(None)).is_none()

    library.glk_set_window(None)

    assert_that(library.glk_stream_get_current()).is_none()


# Memory streams open in the three modes that fit them, join the
# stream walk, and close with their counts reported.
def test_memory_streams_open_and_close() -> None:
    library = Glk(Quiet())
    buffer = [0] * 4

    stream = library.glk_stream_open_memory(buffer, FileMode.WRITE, 5)
    wide = library.glk_stream_open_memory_uni([0] * 2, FileMode.READ_WRITE, 6)

    assert_that(library.glk_stream_get_rock(stream)).is_equal_to(5)
    assert_that(library.glk_stream_get_rock(None)).is_equal_to(0)

    rock = Ref()

    assert_that(library.glk_stream_iterate(None, rock)).is_same_as(wide)
    assert_that(rock.value).is_equal_to(6)
    assert_that(library.glk_stream_iterate(wide, None)).is_same_as(stream)
    assert_that(library.glk_stream_iterate(stream, rock)).is_none()

    with pytest.raises(GlulxGlkError, match="illegal filemode"):
        library.glk_stream_open_memory(buffer, FileMode.WRITE_APPEND, 0)

    library.glk_stream_set_current(stream)
    library.glk_put_string("hey")

    counts = RefStruct(2)

    library.glk_stream_close(stream, counts)

    assert_that(counts.fields).is_equal_to([0, 3])
    assert_that(library.glk_stream_get_current()).is_none()
    assert_that(library.streams).is_length(1)

    # Closing again finds it already off the lists.
    library.glk_stream_close(stream, None)

    with pytest.raises(GlulxGlkError, match="invalid stream"):
        library.glk_stream_close(None, None)


# The printing family reaches the current stream, masks bytes
# where the narrow functions promise bytes, and shrugs off the
# null stream and the null buffer.
def test_printing_reaches_the_current_stream() -> None:
    library = Glk(Quiet())

    # With no current stream, printing goes nowhere quietly.
    library.glk_put_char(0x41)
    library.glk_put_char_stream_uni(None, 0x41)
    library.glk_put_string("lost")
    library.glk_put_buffer([0x41])

    held = [0] * 12
    stream = library.glk_stream_open_memory(held, FileMode.WRITE, 0)

    library.glk_stream_set_current(stream)

    library.glk_put_char(0x141)
    library.glk_put_char_uni(0x2603)
    library.glk_put_string("ab")
    library.glk_put_string_uni("c")
    library.glk_put_buffer([0x64])
    library.glk_put_buffer_uni([0x2604])
    library.glk_put_char_stream(stream, 0x145)
    library.glk_put_char_stream_uni(stream, 0x2605)
    library.glk_put_string_stream(stream, "d")
    library.glk_put_string_stream_uni(stream, "e")
    library.glk_put_buffer_stream(stream, [0x66])
    library.glk_put_buffer_stream_uni(stream, [0x67])
    library.glk_put_buffer_stream(stream, None)

    assert_that(held).is_equal_to(
        [0x41, 0x3F, 0x61, 0x62, 0x63, 0x64, 0x3F, 0x45, 0x3F, 0x64, 0x65, 0x66]
    )

    library.glk_set_hyperlink(3)
    library.glk_set_hyperlink_stream(None, 4)

    assert_that(stream.hyperlink).is_equal_to(3)


# Styles land on window streams and fall silently off the others.
def test_styles_only_land_on_windows() -> None:
    library, first = rooted()

    library.glk_set_window(first)
    library.glk_set_style(Style.HEADER)

    assert_that(first.style).is_equal_to(Style.HEADER)

    memory = library.glk_stream_open_memory([0], FileMode.WRITE, 0)

    library.glk_set_style_stream(memory, Style.ALERT)

    assert_that(first.style).is_equal_to(Style.HEADER)


# The reading family delegates to the stream and answers "empty"
# for the null stream or the null buffer.
def test_reading_delegates_to_the_stream() -> None:
    library = Glk(Quiet())
    stream = library.glk_stream_open_memory([0x61, 0x62, 0x0A, 0x63], FileMode.READ, 0)

    assert_that(library.glk_get_char_stream(stream)).is_equal_to(0x61)
    assert_that(library.glk_get_char_stream_uni(stream)).is_equal_to(0x62)
    assert_that(library.glk_get_char_stream(None)).is_equal_to(-1)

    line = [0] * 4

    assert_that(library.glk_get_line_stream(stream, line)).is_equal_to(1)
    assert_that(line[:2]).is_equal_to([0x0A, 0])
    assert_that(library.glk_get_line_stream(None, line)).is_equal_to(0)
    assert_that(library.glk_get_line_stream_uni(stream, None)).is_equal_to(0)

    room = [0] * 2

    assert_that(library.glk_get_buffer_stream(stream, room)).is_equal_to(1)
    assert_that(room[0]).is_equal_to(0x63)
    assert_that(library.glk_get_buffer_stream(None, room)).is_equal_to(0)
    assert_that(library.glk_get_buffer_stream_uni(stream, None)).is_equal_to(0)

    library.glk_stream_set_position(stream, 0, SeekMode.START)
    library.glk_stream_set_position(None, 0, SeekMode.START)

    assert_that(library.glk_stream_get_position(stream)).is_equal_to(0)
    assert_that(library.glk_stream_get_position(None)).is_equal_to(0)


# File references sanitize game-supplied names into the save
# directory, wear a suffix by usage, and never escape.
def test_filerefs_sanitize_names(tmp_path: Path) -> None:
    library = Glk(Quiet(), save_dir=tmp_path)

    saved = library.glk_fileref_create_by_name(FileUsage.SAVED_GAME, 'sa<ve>:1.dat"', 1)
    notes = library.glk_fileref_create_by_name(FileUsage.TRANSCRIPT, "notes", 2)
    data = library.glk_fileref_create_by_name(FileUsage.DATA, "//", 3)

    assert_that(saved.filename).is_equal_to(str(tmp_path / "save1.glksave"))
    assert_that(notes.filename).is_equal_to(str(tmp_path / "notes.txt"))
    assert_that(data.filename).is_equal_to(str(tmp_path / "null.glkdata"))

    assert_that(library.glk_fileref_get_rock(saved)).is_equal_to(1)
    assert_that(library.glk_fileref_get_rock(None)).is_equal_to(0)

    rock = Ref()

    assert_that(library.glk_fileref_iterate(None, rock)).is_same_as(data)
    assert_that(library.glk_fileref_iterate(data, None)).is_same_as(notes)

    twin = library.glk_fileref_create_from_fileref(FileUsage.DATA, saved, 4)

    assert_that(twin.filename).is_equal_to(saved.filename)

    with pytest.raises(GlulxGlkError, match="invalid fileref"):
        library.glk_fileref_create_from_fileref(FileUsage.DATA, None, 0)


# A temporary file exists until its reference is destroyed; the
# prompt makes a reference only when the player answers.
def test_temporary_and_prompted_files(tmp_path: Path) -> None:
    library = Glk(Prompter("chosen"), save_dir=tmp_path)

    temp = library.glk_fileref_create_temp(FileUsage.DATA, 0)

    assert_that(library.glk_fileref_does_file_exist(temp)).is_equal_to(1)

    library.glk_fileref_destroy(temp)

    assert_that(library.glk_fileref_does_file_exist(temp)).is_equal_to(0)
    assert_that(library.glk_fileref_does_file_exist(None)).is_equal_to(0)

    library.glk_fileref_destroy(None)

    asked = library.glk_fileref_create_by_prompt(FileUsage.DATA, FileMode.WRITE, 0)

    if asked is None:
        pytest.fail("the prompt answered a name")

    assert_that(asked.filename).is_equal_to(str(tmp_path / "chosen.glkdata"))

    refused = Glk(Prompter(None), save_dir=tmp_path)

    assert_that(
        refused.glk_fileref_create_by_prompt(FileUsage.DATA, FileMode.WRITE, 0)
    ).is_none()

    # Deleting through a reference destroys the file, not the
    # reference.
    target = library.glk_fileref_create_by_name(FileUsage.DATA, "gone", 0)

    Path(target.filename).write_bytes(b"x")

    library.glk_fileref_delete_file(target)
    library.glk_fileref_delete_file(None)

    assert_that(Path(target.filename).exists()).is_false()


# File streams write and read through their reference; a file that
# will not open answers the null stream rather than faulting.
def test_file_streams_round_trip(tmp_path: Path) -> None:
    library = Glk(Quiet(), save_dir=tmp_path)
    fileref = library.glk_fileref_create_by_name(FileUsage.DATA, "story", 0)

    writer = library.glk_stream_open_file(fileref, FileMode.WRITE, 0)

    if writer is None:
        pytest.fail("the write stream opened")

    library.glk_put_string_stream(writer, "hello")
    library.glk_stream_close(writer, None)

    # WriteAppend starts at the end; ReadWrite starts at the top.
    appender = library.glk_stream_open_file(fileref, FileMode.WRITE_APPEND, 0)

    if appender is None:
        pytest.fail("the append stream opened")

    library.glk_put_string_stream(appender, "!")
    library.glk_stream_close(appender, None)

    reader = library.glk_stream_open_file(fileref, FileMode.READ, 0)

    if reader is None:
        pytest.fail("the read stream opened")

    line = [0] * 8

    assert_that(library.glk_get_line_stream(reader, line)).is_equal_to(6)
    library.glk_stream_close(reader, None)

    # ReadWrite conjures a missing file into being.
    fresh = library.glk_fileref_create_by_name(FileUsage.DATA, "fresh", 0)
    conjured = library.glk_stream_open_file_uni(fresh, FileMode.READ_WRITE, 0)

    if conjured is None:
        pytest.fail("the read-write stream opened")

    library.glk_stream_close(conjured, None)

    assert_that(Path(fresh.filename).exists()).is_true()

    # A directory in the file's seat will not open.
    blocked = library.glk_fileref_create_by_name(FileUsage.DATA, "blocked", 0)

    Path(blocked.filename).mkdir()

    assert_that(library.glk_stream_open_file(blocked, FileMode.READ, 0)).is_none()

    with pytest.raises(GlulxGlkError, match="invalid fileref"):
        library.glk_stream_open_file(None, FileMode.READ, 0)

    with pytest.raises(GlulxGlkError, match="illegal filemode"):
        library.glk_stream_open_file(fileref, 9, 0)


# Resource streams open read-only over Blorb data chunks, byte or
# word, and answer None for a number the Blorb does not carry.
def test_resource_streams_open_over_the_blorb() -> None:
    resources = Resources(
        blorb(
            (b"Data", 1, b"TEXT", b"hi"),
            (b"Data", 2, b"BINA", b"\x00\x00\x26\x03"),
        )
    )
    library = Glk(Quiet(), resources=resources)

    text = library.glk_stream_open_resource(1, 0)
    words = library.glk_stream_open_resource_uni(2, 0)

    if text is None or words is None:
        pytest.fail("both resource streams opened")

    assert_that(library.glk_get_char_stream(text)).is_equal_to(0x68)
    assert_that(library.glk_get_char_stream(words)).is_equal_to(0x2603)
    assert_that(library.glk_stream_open_resource(9, 0)).is_none()


# Pictures are measured from the Blorb; drawing needs a display
# that draws, a window, and a picture that exists.
def test_pictures_measure_and_draw() -> None:
    resources = Resources(blorb((b"Pict", 1, b"PNG ", png(32, 16))))
    display = Artist()
    library = Glk(display, resources=resources)
    base = library.glk_window_open(None, 0, 0, WindowType.TEXT_BUFFER, 0)

    width = Ref()
    height = Ref()

    assert_that(library.glk_image_get_info(1, width, height)).is_equal_to(1)
    assert_that((width.value, height.value)).is_equal_to((32, 16))
    assert_that(library.glk_image_get_info(9, width, height)).is_equal_to(0)
    assert_that((width.value, height.value)).is_equal_to((0, 0))
    assert_that(library.glk_image_get_info(1, None, None)).is_equal_to(1)

    assert_that(library.glk_image_draw(base, 1, 4, 5)).is_equal_to(1)
    assert_that(display.calls[-1]).is_equal_to(("draw", 4, 5, 32, 16))

    assert_that(library.glk_image_draw_scaled(base, 1, 0, 0, 64, 32)).is_equal_to(1)
    assert_that(display.calls[-1]).is_equal_to(("draw", 0, 0, 64, 32))

    assert_that(
        library.glk_image_draw_scaled_ext(base, 1, 0, 0, 8, 8, 0, 0)
    ).is_equal_to(1)

    assert_that(library.glk_image_draw(None, 1, 0, 0)).is_equal_to(0)
    assert_that(library.glk_image_draw(base, 9, 0, 0)).is_equal_to(0)

    library.glk_window_erase_rect(base, 1, 2, 3, 4)
    library.glk_window_fill_rect(base, 0xFF0000, 0, 0, 1, 1)
    library.glk_window_set_background_color(base, 0x00FF00)
    library.glk_window_flow_break(base)

    assert_that(display.calls[-4:]).is_equal_to(
        [("erase", 1, 2, 3, 4), ("fill", 0xFF0000), ("background", 0x00FF00), ("flow",)]
    )

    library.glk_window_erase_rect(None, 0, 0, 1, 1)
    library.glk_window_fill_rect(None, 0, 0, 0, 1, 1)
    library.glk_window_set_background_color(None, 0)
    library.glk_window_flow_break(None)


# Style hints are recorded and withdrawn; distinguishing and
# measuring are the display's answers, defaulting to no.
def test_style_hints_and_measures() -> None:
    library, first = rooted()

    library.glk_stylehint_set(WindowType.TEXT_BUFFER, Style.HEADER, 4, 1)

    assert_that(library.stylehints).is_length(1)

    library.glk_stylehint_clear(WindowType.TEXT_BUFFER, Style.HEADER, 4)
    library.glk_stylehint_clear(WindowType.TEXT_BUFFER, Style.HEADER, 4)

    assert_that(library.stylehints).is_empty()

    assert_that(
        library.glk_style_distinguish(first, Style.NORMAL, Style.HEADER)
    ).is_equal_to(0)
    assert_that(
        library.glk_style_distinguish(first, Style.HEADER, Style.HEADER)
    ).is_equal_to(0)
    assert_that(
        library.glk_style_distinguish(None, Style.NORMAL, Style.HEADER)
    ).is_equal_to(0)

    result = Ref()

    assert_that(library.glk_style_measure(first, Style.NORMAL, 0, result)).is_equal_to(
        0
    )
    assert_that(library.glk_style_measure(None, Style.NORMAL, 0, result)).is_equal_to(0)

    telling, styled = rooted(Styler())

    assert_that(
        telling.glk_style_distinguish(styled, Style.NORMAL, Style.HEADER)
    ).is_equal_to(1)
    assert_that(telling.glk_style_measure(styled, Style.NORMAL, 0, result)).is_equal_to(
        1
    )
    assert_that(result.value).is_equal_to(7)
    assert_that(telling.glk_style_measure(styled, Style.NORMAL, 0, None)).is_equal_to(1)


# Music means MOD and song files; the only decoder aboard is
# AIFF, so the music claim stays zero even where sampled sound
# plays (Glk: Testing for Sound Capabilities).
def test_music_is_never_claimed() -> None:
    library = Glk(Sounder())

    assert_that(library.glk_gestalt(GlkGestalt.SOUND, 0)).is_equal_to(1)
    assert_that(library.glk_gestalt(GlkGestalt.SOUND_MUSIC, 0)).is_equal_to(0)


# Sound channels exist only where the display plays; playing asks
# the display and records what the channel is doing.
def test_sound_channels_play_where_they_can() -> None:
    silent = Glk(Quiet())

    assert_that(silent.glk_schannel_create(0)).is_none()

    resources = Resources(blorb((b"Snd ", 3, b"FORM", b"AIFFdata")))
    display = Sounder()
    library = Glk(display, resources=resources)

    channel = library.glk_schannel_create(1)
    other = library.glk_schannel_create_ext(2, 0x8000)

    if channel is None or other is None:
        pytest.fail("both channels opened")

    assert_that(channel.volume).is_equal_to(0x10000)
    assert_that(other.volume).is_equal_to(0x8000)
    assert_that(library.glk_schannel_get_rock(channel)).is_equal_to(1)
    assert_that(library.glk_schannel_get_rock(None)).is_equal_to(0)

    rock = Ref()

    assert_that(library.glk_schannel_iterate(None, rock)).is_same_as(other)
    assert_that(library.glk_schannel_iterate(other, None)).is_same_as(channel)

    assert_that(library.glk_schannel_play(channel, 3)).is_equal_to(1)
    assert_that(channel.sound).is_equal_to(3)

    # A missing sound, zero repeats, and the null channel all
    # decline; a refusing display declines too.
    assert_that(library.glk_schannel_play(channel, 9)).is_equal_to(0)
    assert_that(library.glk_schannel_play_ext(channel, 3, 0, 0)).is_equal_to(0)
    assert_that(library.glk_schannel_play(None, 3)).is_equal_to(0)

    refusing = Glk(Sounder(accepts=False), resources=resources)
    denied = refusing.glk_schannel_create(0)

    assert_that(refusing.glk_schannel_play(denied, 3)).is_equal_to(0)

    assert_that(
        library.glk_schannel_play_multi([channel, other], [3, 9], 0)
    ).is_equal_to(1)
    assert_that(library.glk_schannel_play_multi(None, None, 0)).is_equal_to(0)

    library.glk_schannel_pause(channel)
    library.glk_schannel_pause(channel)
    library.glk_schannel_unpause(channel)
    library.glk_schannel_unpause(channel)
    library.glk_schannel_pause(None)
    library.glk_schannel_unpause(None)

    assert_that(display.calls).contains(("pause", True), ("pause", False))

    library.glk_schannel_set_volume(channel, 0x4000)

    assert_that(channel.volume).is_equal_to(0x4000)

    library.glk_schannel_set_volume_ext(channel, 0x2000, 100, 7)
    library.glk_schannel_set_volume_ext(None, 0, 0, 0)

    assert_that(library.pending_events[-1].kind).is_equal_to(EventType.VOLUME_NOTIFY)

    library.glk_sound_load_hint(3, 1)

    library.glk_schannel_stop(channel)
    library.glk_schannel_stop(channel)
    library.glk_schannel_stop(None)

    assert_that(channel.sound).is_equal_to(0)

    library.glk_schannel_destroy(other)
    library.glk_schannel_destroy(None)

    assert_that(library.channels).is_length(1)


# Requests raise flags on windows and clear again; asking twice
# for a line, or asking nothing at all, is refused.
def test_input_requests_raise_and_clear() -> None:
    library, first = rooted()
    held = [0] * 8

    library.glk_request_line_event(first, held, 0)

    with pytest.raises(GlulxGlkError, match="already requested"):
        library.glk_request_line_event_uni(first, held, 0)

    with pytest.raises(GlulxGlkError, match="invalid window"):
        library.glk_request_line_event(None, held, 0)

    library.glk_set_echo_line_event(first, 0)
    library.glk_set_terminators_line_event(first, [KeyCode.ESCAPE])

    request = first.line_request

    if request is None:
        pytest.fail("the request stands")

    assert_that(request.echo).is_false()
    assert_that(request.terminators).is_equal_to((KeyCode.ESCAPE,))

    cancelled = RefStruct(4)

    library.glk_cancel_line_event(first, cancelled)

    assert_that(first.line_request).is_none()
    assert_that(cancelled.fields[0]).is_equal_to(EventType.NONE)

    library.glk_cancel_line_event(None, None)

    # The echo and terminator setters shrug without a request.
    library.glk_set_echo_line_event(first, 1)
    library.glk_set_terminators_line_event(first, None)
    library.glk_set_echo_line_event(None, 1)
    library.glk_set_terminators_line_event(None, None)

    library.glk_request_char_event(first)

    assert_that(first.char_request).is_true()

    library.glk_cancel_char_event(first)
    library.glk_cancel_char_event(None)

    assert_that(first.char_request).is_false()

    library.glk_request_char_event_uni(first)

    assert_that(first.char_unicode).is_true()

    with pytest.raises(GlulxGlkError, match="invalid window"):
        library.glk_request_char_event(None)

    library.glk_request_mouse_event(first)

    assert_that(first.mouse_request).is_true()

    library.glk_cancel_mouse_event(first)
    library.glk_request_mouse_event(None)
    library.glk_cancel_mouse_event(None)

    library.glk_request_hyperlink_event(first)

    assert_that(first.hyperlink_request).is_true()

    library.glk_cancel_hyperlink_event(first)
    library.glk_request_hyperlink_event(None)
    library.glk_cancel_hyperlink_event(None)

    library.glk_request_timer_events(250)

    assert_that(library.timer_interval).is_equal_to(250)


# A line arrives: the buffer fills, the window echoes it in the
# Input style, and the event carries the length.
def test_a_line_arrives_and_echoes() -> None:
    display = Typist([("go north", 0)])
    library, first = rooted(display)
    held = [0] * 12

    library.glk_request_line_event(first, held, 0)

    event = RefStruct(4)

    library.glk_select(event)

    assert_that(event.fields).is_equal_to([EventType.LINE_INPUT, first, 8, 0])
    assert_that(held[:8]).is_equal_to([ord(ch) for ch in "go north"])
    assert_that(first.line_request).is_none()

    window = first

    if not isinstance(window, TextBufferWindow):
        pytest.fail("the root is a text buffer")

    assert_that(window.content).contains(Run(Style.INPUT, 0, "go north\n"))


# A line longer than its buffer is truncated to what fits, and a
# terminator key rides along in the event.
def test_a_long_line_truncates() -> None:
    display = Typist([("northwest", KeyCode.ESCAPE)])
    library, first = rooted(display)
    held = [0] * 5

    library.glk_request_line_event(first, held, 0)

    event = RefStruct(4)

    library.glk_select(event)

    assert_that(event.fields).is_equal_to(
        [EventType.LINE_INPUT, first, 5, KeyCode.ESCAPE]
    )
    assert_that(held).is_equal_to([ord(ch) for ch in "north"])


# Echo is suppressed when the request says so, when the display
# already echoes, and when the window keeps no scrollback.
def test_echo_suppression() -> None:
    library, first = rooted(Typist([("quiet", 0)]))

    library.glk_request_line_event(first, [0] * 8, 0)
    library.glk_set_echo_line_event(first, 0)
    library.glk_select(RefStruct(4))

    window = first

    if not isinstance(window, TextBufferWindow):
        pytest.fail("the root is a text buffer")

    assert_that(window.content).is_empty()

    grid_library, base = rooted(Typist([("grid", 0)]))
    grid = grid_library.glk_window_open(base, ABOVE_FIXED, 3, WindowType.TEXT_GRID, 0)

    if not isinstance(grid, TextGridWindow):
        pytest.fail("the split opened a grid")

    grid_library.glk_request_line_event(grid, [0] * 8, 0)
    grid_library.glk_select(RefStruct(4))

    assert_that("".join(grid.rows()).strip()).is_empty()


# A timer fires while a keystroke is pending; the request
# survives and is answered on the next select.
def test_a_timer_interrupts_a_keystroke() -> None:
    library, first = rooted(Keyist([None, 0x42]))

    library.glk_request_char_event(first)

    event = RefStruct(4)

    library.glk_select(event)

    assert_that(event.fields[0]).is_equal_to(EventType.TIMER)
    assert_that(first.char_request).is_true()

    library.glk_select(event)

    assert_that(event.fields).is_equal_to([EventType.CHAR_INPUT, first, 0x42, 0])


# A keystroke arrives; delivering one nobody asked for is refused.
def test_a_keystroke_arrives() -> None:
    library, first = rooted(Keyist([0x41]))

    library.glk_request_char_event(first)

    event = RefStruct(4)

    library.glk_select(event)

    assert_that(event.fields).is_equal_to([EventType.CHAR_INPUT, first, 0x41, 0])
    assert_that(first.char_request).is_false()

    with pytest.raises(GlulxGlkError, match="not expecting"):
        library.deliver_char(first, 0x42)

    with pytest.raises(GlulxGlkError, match="not expecting"):
        library.deliver_line(first, "stray")


# A click and a link selection deliver from outside the ask too,
# the way a protocol display delivers them -- values masked to 32
# bits, requests consumed, and ones nobody asked for refused.
def test_clicks_and_links_deliver_from_outside() -> None:
    library, first = rooted()

    library.glk_request_mouse_event(first)

    clicked = library.deliver_mouse(first, 3, 0x1_0000_0004)

    assert_that(clicked.as_fields()).is_equal_to((EventType.MOUSE_INPUT, first, 3, 4))
    assert_that(first.mouse_request).is_false()

    with pytest.raises(GlulxGlkError, match="not expecting"):
        library.deliver_mouse(first, 1, 1)

    library.glk_request_hyperlink_event(first)

    linked = library.deliver_hyperlink(first, 0x1_0000_0007)

    assert_that(linked.as_fields()).is_equal_to((EventType.HYPERLINK, first, 7, 0))
    assert_that(first.hyperlink_request).is_false()

    with pytest.raises(GlulxGlkError, match="not expecting"):
        library.deliver_hyperlink(first, 7)


# A suspending display is never asked for a file either: the call
# itself stands down with its tail unparked until a glk opcode
# parks it, and the host's answer runs what was parked. Answers
# with nothing standing are refused.
def test_a_file_prompt_suspends_the_call() -> None:
    library, _ = rooted(Suspending())

    answered = library.glk_fileref_create_by_prompt(
        FileUsage.SAVED_GAME, FileMode.WRITE, 7
    )

    assert_that(answered).is_none()

    waiting = library.waiting

    if not isinstance(waiting, Prompting):
        pytest.fail("the prompt suspended")

    assert_that((waiting.usage, waiting.fmode, waiting.rock)).is_equal_to(
        (FileUsage.SAVED_GAME, FileMode.WRITE, 7)
    )

    # Outside any glk call, no tail was parked: loudly so.
    with pytest.raises(GlulxGlkError, match="no store owed"):
        library.deliver_file("saga")

    stored: list[int] = []
    waiting.encode = lambda value: 0 if value is None else 99
    waiting.store = stored.append

    library.deliver_file("saga")

    assert_that(stored).is_equal_to([99])
    assert_that(library.waiting).is_none()

    with pytest.raises(GlulxGlkError, match="no prompt suspended"):
        library.deliver_file("saga")


# A cancel stores the null reference; a file answered at a select,
# or an event answered at a prompt, is a driver's bug and loud.
def test_files_and_events_land_only_in_their_own_waits() -> None:
    library, first = rooted(Suspending())

    library.glk_fileref_create_by_prompt(FileUsage.DATA, FileMode.READ, 0)

    waiting = library.waiting

    if not isinstance(waiting, Prompting):
        pytest.fail("the prompt suspended")

    stored: list[int] = []
    waiting.encode = lambda value: 0 if value is None else 1
    waiting.store = stored.append

    with pytest.raises(GlulxGlkError, match="no select suspended"):
        library.deliver_event(Event(EventType.TIMER))

    library.deliver_file(None)

    assert_that(stored).is_equal_to([0])

    library.glk_request_char_event(first)
    library.glk_select(RefStruct(4))

    with pytest.raises(GlulxGlkError, match="no prompt suspended"):
        library.deliver_file("saga")


# A timer fires while a line is pending: the request survives the
# interruption and is answered on the next select.
def test_a_timer_interrupts_a_line() -> None:
    display = Typist([None, ("after", 0)])
    library, first = rooted(display)

    library.glk_request_line_event(first, [0] * 8, 0)

    event = RefStruct(4)

    library.glk_select(event)

    assert_that(event.fields[0]).is_equal_to(EventType.TIMER)
    assert_that(first.line_request).is_not_none()

    library.glk_select(event)

    assert_that(event.fields[0]).is_equal_to(EventType.LINE_INPUT)


# A click and a link selection arrive through the same loop, each
# allowed a "not yet" round first.
def test_clicks_and_links_arrive() -> None:
    library, first = rooted(Clicker([None, (3, 4)]))

    library.glk_request_mouse_event(first)

    event = RefStruct(4)

    library.glk_select(event)

    assert_that(event.fields).is_equal_to([EventType.MOUSE_INPUT, first, 3, 4])
    assert_that(first.mouse_request).is_false()

    linked, page = rooted(Linker([0, 7]))

    linked.glk_request_hyperlink_event(page)

    linked.glk_select(event)

    assert_that(event.fields).is_equal_to([EventType.HYPERLINK, page, 7, 0])


# A select that can never be satisfied is refused rather than
# hung: requests a display cannot answer, or no requests at all.
def test_a_hopeless_select_is_refused() -> None:
    library, first = rooted()

    with pytest.raises(GlulxGlkError, match="wait forever"):
        library.glk_select(RefStruct(4))

    library.glk_request_mouse_event(first)
    library.glk_request_hyperlink_event(first)

    with pytest.raises(GlulxGlkError, match="wait forever"):
        library.glk_select(RefStruct(4))


# A suspending display is never asked for input. Its select
# records the wait instead -- the struct stays whole and empty,
# the seat the host's event will land in.
def test_a_suspending_select_records_the_wait() -> None:
    display = Suspending()
    library, first = rooted(display)

    library.glk_request_char_event(first)

    event = RefStruct(4)

    library.glk_select(event)

    waiting = library.waiting

    if not isinstance(waiting, Waiting):
        pytest.fail("the select suspended")

    assert_that(waiting.struct).is_same_as(event)
    assert_that(waiting.writebacks).is_empty()
    assert_that(event.fields).is_equal_to([0, 0, 0, 0])
    assert_that(display.flushes).is_greater_than(0)


# Whatever a display posted is delivered at once: a queued event
# needs no suspension, exactly as it needs no blocking.
def test_a_suspending_select_serves_the_queue_first() -> None:
    library, _ = rooted(Suspending())

    library.post_event(Event(EventType.TIMER))

    event = RefStruct(4)

    library.glk_select(event)

    assert_that(event.fields).is_equal_to([EventType.TIMER, None, 0, 0])
    assert_that(library.waiting).is_none()


# The hopeless-select guard holds while suspending too: requests
# count only where the display claims the capability, and a
# running timer is a legitimate wait -- the host raises timer
# events itself, which no blocking display can promise when no
# input is requested alongside.
def test_a_hopeless_suspension_is_refused() -> None:
    library, first = rooted(Suspending())

    with pytest.raises(GlulxGlkError, match="wait forever"):
        library.glk_select(RefStruct(4))

    library.glk_request_mouse_event(first)
    library.glk_request_hyperlink_event(first)

    with pytest.raises(GlulxGlkError, match="wait forever"):
        library.glk_select(RefStruct(4))

    able = Suspending()
    able.timer_input = True
    able.mouse_input = True
    able.hyperlink_input = True
    timed, _ = rooted(able)

    with pytest.raises(GlulxGlkError, match="wait forever"):
        timed.glk_select(RefStruct(4))

    timed.glk_request_timer_events(50)
    timed.glk_select(RefStruct(4))

    assert_that(timed.waiting).is_not_none()


# A claimed capability's request carries the wait; the delivered
# event lands in the struct even with nothing deferred to write.
def test_claimed_requests_carry_the_wait() -> None:
    able = Suspending()
    able.mouse_input = True
    library, first = rooted(able)

    library.glk_request_mouse_event(first)

    event = RefStruct(4)

    library.glk_select(event)

    assert_that(library.waiting).is_not_none()

    library.deliver_event(Event(EventType.MOUSE_INPUT, first, 3, 4))

    assert_that(event.fields).is_equal_to([EventType.MOUSE_INPUT, first, 3, 4])
    assert_that(library.waiting).is_none()

    linked = Suspending()
    linked.hyperlink_input = True
    pages, page = rooted(linked)

    pages.glk_request_hyperlink_event(page)
    pages.glk_select(RefStruct(4))

    assert_that(pages.waiting).is_not_none()


# The delivered event fills the struct and runs the deferred
# writes; an event with no seat to land in is refused.
def test_a_delivered_event_lands_in_its_seat() -> None:
    library, first = rooted(Suspending())
    held = [0] * 8

    library.glk_request_line_event(first, held, 0)

    event = RefStruct(4)

    library.glk_select(event)

    waiting = library.waiting

    if waiting is None:
        pytest.fail("the select suspended")

    written: list[str] = []
    waiting.writebacks = [lambda: written.append("wrote")]

    answered = library.deliver_line(first, "go")

    library.deliver_event(answered)

    assert_that(event.fields).is_equal_to([EventType.LINE_INPUT, first, 2, 0])
    assert_that(held[:2]).is_equal_to([ord("g"), ord("o")])
    assert_that(written).is_equal_to(["wrote"])
    assert_that(library.waiting).is_none()

    with pytest.raises(GlulxGlkError, match="no select suspended"):
        library.deliver_event(answered)


# The poll reports queued display events, skips over anything that
# is input, and never blocks.
def test_polling_skips_input_events() -> None:
    library, first = rooted()
    event = RefStruct(4)

    library.glk_select_poll(event)

    assert_that(event.fields[0]).is_equal_to(EventType.NONE)

    library.post_event(Event(EventType.CHAR_INPUT, first, 0x41, 0))
    library.post_event(Event(EventType.TIMER))

    library.glk_select_poll(event)

    assert_that(event.fields[0]).is_equal_to(EventType.TIMER)

    # The input event stays queued for a real select to take.
    library.glk_select(event)

    assert_that(event.fields[0]).is_equal_to(EventType.CHAR_INPUT)


# A resized display re-lays the tree and tells the game.
def test_a_resize_reaches_the_game() -> None:
    library, _ = rooted()

    library.display_resized()

    assert_that(library.pending_events[-1].kind).is_equal_to(EventType.ARRANGE)


# The character case functions map what a single character can
# hold and leave the rest alone.
def test_case_maps_single_characters() -> None:
    library = Glk(Quiet())

    assert_that(library.glk_char_to_lower(ord("A"))).is_equal_to(ord("a"))
    assert_that(library.glk_char_to_upper(ord("a"))).is_equal_to(ord("A"))
    assert_that(library.glk_char_to_upper(ord("ß"))).is_equal_to(ord("ß"))
    assert_that(library.glk_char_to_lower(0x110000)).is_equal_to(0x110000)


# The buffer case functions work in place, answer the true length
# even past the buffer, and map per character rather than per
# string.
def test_buffer_case_and_normalization() -> None:
    library = Glk(Quiet())

    word = [ord(ch) for ch in "Wave"]

    assert_that(library.glk_buffer_to_upper_case_uni(word, 4)).is_equal_to(4)
    assert_that(word).is_equal_to([ord(ch) for ch in "WAVE"])

    assert_that(library.glk_buffer_to_lower_case_uni(word, 4)).is_equal_to(4)
    assert_that(word).is_equal_to([ord(ch) for ch in "wave"])

    assert_that(library.glk_buffer_to_title_case_uni(word, 4, 0)).is_equal_to(4)
    assert_that(word).is_equal_to([ord(ch) for ch in "Wave"])

    shouted = [ord(ch) for ch in "WAVE"]

    assert_that(library.glk_buffer_to_title_case_uni(shouted, 4, 1)).is_equal_to(4)
    assert_that(shouted).is_equal_to([ord(ch) for ch in "Wave"])
    assert_that(library.glk_buffer_to_title_case_uni([], 0, 1)).is_equal_to(0)

    # ß uppercases to SS: two characters, so the true length is
    # answered while the buffer keeps what fits.
    sharp = [ord("ß")]

    assert_that(library.glk_buffer_to_upper_case_uni(sharp, 1)).is_equal_to(2)
    assert_that(sharp).is_equal_to([ord("S")])

    # é decomposes to two code points and composes back to one.
    accented = [0xE9, 0]

    assert_that(library.glk_buffer_canon_decompose_uni(accented, 1)).is_equal_to(2)
    assert_that(accented).is_equal_to([0x65, 0x301])
    assert_that(library.glk_buffer_canon_normalize_uni(accented, 2)).is_equal_to(1)
    assert_that(accented[0]).is_equal_to(0xE9)

    assert_that(library.glk_buffer_to_upper_case_uni(None, 4)).is_equal_to(0)


# The real clock runs when nobody pins it.
def test_the_real_clock_ticks() -> None:
    library = Glk(Quiet())

    assert_that(library.glk_current_simple_time(1)).is_greater_than(1_700_000_000)


# The clock answers real time split into two words, and divided
# down for the simple form.
def test_the_clock_answers_now(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("voxam.glulx.glk.api._now", lambda: 1_700_000_000.5)

    library = Glk(Quiet())
    time = RefStruct(3)

    library.glk_current_time(time)

    assert_that(time.fields).is_equal_to([0, 1_700_000_000, 500_000])

    library.glk_current_time(None)

    assert_that(library.glk_current_simple_time(60)).is_equal_to(1_700_000_000 // 60)
    assert_that(library.glk_current_simple_time(0)).is_equal_to(-1)


# A timestamp explodes into date fields -- weekdays counted from
# Sunday -- and collapses back, normalizing out-of-range fields.
def test_dates_explode_and_collapse() -> None:
    library = Glk(Quiet())
    time = RefStruct(3)
    date = RefStruct(8)

    # 2023-11-14 22:13:20 UTC, a Tuesday.
    time.set_all(0, 1_700_000_000, 250)

    library.glk_time_to_date_utc(time, date)

    assert_that(date.fields).is_equal_to([2023, 11, 14, 2, 22, 13, 20, 250])

    library.glk_date_to_time_utc(date, time)

    assert_that(time.fields).is_equal_to([0, 1_700_000_000, 250])

    # Month 14 normalizes into the next year.
    date.set_all(2023, 14, 1, 0, 0, 0, 0, 0)

    library.glk_date_to_time_utc(date, time)
    library.glk_time_to_date_utc(time, date)

    assert_that(date.fields[:3]).is_equal_to([2024, 2, 1])

    # The simple forms divide down and multiply back.
    library.glk_simple_time_to_date_utc(19675, 86400, date)

    assert_that(date.fields[:3]).is_equal_to([2023, 11, 14])
    assert_that(library.glk_date_to_simple_time_utc(date, 86400)).is_equal_to(19675)

    # The local forms agree with Python's own local calendar.
    expected = datetime.datetime.fromtimestamp(1_700_000_000, datetime.UTC).astimezone()

    time.set_all(0, 1_700_000_000, 250)

    library.glk_time_to_date_local(time, date)

    assert_that(date.fields[:3]).is_equal_to(
        [expected.year, expected.month, expected.day]
    )

    library.glk_date_to_time_local(date, time)

    fields = cast("list[int]", date.fields)
    recovered = datetime.datetime(
        fields[0],
        fields[1],
        fields[2],
        hour=fields[4],
        minute=fields[5],
        second=fields[6],
    ).timestamp()

    assert_that(time.fields[1]).is_equal_to(int(recovered))
    assert_that(library.glk_date_to_simple_time_local(date, 60)).is_equal_to(
        int(recovered) // 60
    )


# The bridge hears about every disposal, once it asks: closing a
# window reports the window and its stream, so stale ids stop
# resolving.
def test_disposals_are_reported() -> None:
    library, first = rooted()
    reported: list[object] = []

    library.on_dispose = reported.append

    library.glk_window_close(first, None)

    assert_that(reported).contains(first, first.stream)


# Destroying what is already gone stays quiet: a fileref or a
# channel off the lists is simply let go, and a kept reference is
# not temporary twice.
def test_double_destroys_stay_quiet(tmp_path: Path) -> None:
    library = Glk(Sounder(), save_dir=tmp_path)

    kept = library.glk_fileref_create_by_name(FileUsage.DATA, "kept", 0)

    library.glk_fileref_destroy(kept)
    library.glk_fileref_destroy(kept)

    assert_that(kept.disposed).is_true()

    channel = library.glk_schannel_create(0)

    library.glk_schannel_destroy(channel)
    library.glk_schannel_destroy(channel)

    assert_that(library.channels).is_empty()


# The quiet display's own input answers are "nothing yet" -- the
# contract the select loop leans on.
def test_the_quiet_display_answers_nothing() -> None:
    display = Quiet()
    window = TextBufferWindow()

    assert_that(display.read_line(window, 8)).is_none()
    assert_that(display.read_char(window)).is_none()


# The unanswerable clock questions answer their failure values
# rather than faulting: null refs, impossible years, zero factors.
def test_impossible_dates_fail_softly() -> None:
    library = Glk(Quiet())
    time = RefStruct(3)
    date = RefStruct(8)

    library.glk_time_to_date_utc(None, date)

    assert_that(date.fields).is_equal_to([0] * 8)

    library.glk_time_to_date_utc(time, None)
    library.glk_date_to_time_utc(date, None)

    # A year past every calendar collapses to the -1 sentinel.
    date.set_all(999_999_999, 1, 1, 0, 0, 0, 0, 0)

    library.glk_date_to_time_utc(date, time)

    assert_that(time.fields).is_equal_to([-1, 0xFFFFFFFF, 0])

    library.glk_date_to_time_utc(None, time)

    assert_that(time.fields).is_equal_to([-1, 0xFFFFFFFF, 0])

    assert_that(library.glk_date_to_simple_time_utc(date, 60)).is_equal_to(-1)
    assert_that(library.glk_date_to_simple_time_utc(None, 60)).is_equal_to(-1)
    assert_that(library.glk_date_to_simple_time_utc(date, 0)).is_equal_to(-1)

    # And a second count past every timestamp explodes to zeros.
    library.glk_simple_time_to_date_utc(1 << 40, 1 << 22, date)

    assert_that(date.fields).is_equal_to([0] * 8)

    library.glk_simple_time_to_date_local(0, 1, date)

    assert_that(date.fields[0]).is_greater_than_or_equal_to(1969)

    library.glk_simple_time_to_date_utc(0, 1, None)
