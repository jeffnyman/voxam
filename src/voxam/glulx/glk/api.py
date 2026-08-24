"""The Glk function surface.

Every method named glk_* is what the game reaches when the bridge
era routes the glk opcode here by selector. The library holds the
window tree, the live object lists, and the current output stream;
nothing in it knows about Glulx -- ids, addresses, and the stack
are the bridge's translation.

Blocking by default, suspending on request: glkote's glkapi.js
cannot block, so its glk_select returns a sentinel and the
interpreter resumes from a callback. A display that can block is
simply asked for input and glk_select returns when it has some --
the cheapglk and glkterm arrangement. A display that cannot block
raises its suspends flag, and glk_select records the wait instead:
the machine returns to its host, and the host answers through
deliver_event.
"""

import datetime
import os
import tempfile
import unicodedata
from collections.abc import Callable, Iterable, Sequence
from io import BytesIO
from pathlib import Path
from typing import BinaryIO, Literal, cast

from voxam.errors import GlulxGlkError, GlulxSessionEnd
from voxam.glulx.glk.frontend import Frontend, NullFrontend
from voxam.glulx.glk.objects import (
    MAX_UNICODE,
    NEWLINE,
    BlankWindow,
    Buffer,
    Event,
    EventType,
    FileMode,
    FileRef,
    FileStream,
    FileUsage,
    GlkObject,
    GraphicsWindow,
    KeyCode,
    LineRequest,
    MemoryStream,
    PairWindow,
    SoundChannel,
    Stream,
    Style,
    TextBufferWindow,
    TextGridWindow,
    Window,
    WindowMethod,
    WindowStream,
    WindowType,
    to_char,
)
from voxam.glulx.glk.refs import Ref, RefStruct
from voxam.glulx.glk.resources import Resources

# Glk 0.7.6, the version the dispatch table is drawn from (Glk:
# The Version Number).
GLK_VERSION = 0x00000706

_MASK = 0xFFFFFFFF

FULL_VOLUME = 0x10000


class GlkGestalt:
    """The Glk gestalt selectors (Glk: The Gestalt System).

    These are Glk's own capability questions, asked through
    glk_gestalt -- not the Glulx machine's, which live in
    voxam.glulx.gestalt and answer for the VM.
    """

    VERSION = 0
    CHAR_INPUT = 1
    LINE_INPUT = 2
    CHAR_OUTPUT = 3
    MOUSE_INPUT = 4
    TIMER = 5
    GRAPHICS = 6
    DRAW_IMAGE = 7
    SOUND = 8
    SOUND_VOLUME = 9
    SOUND_NOTIFY = 10
    HYPERLINKS = 11
    HYPERLINK_INPUT = 12
    SOUND_MUSIC = 13
    GRAPHICS_TRANSPARENCY = 14
    UNICODE = 15
    UNICODE_NORM = 16
    LINE_INPUT_ECHO = 17
    LINE_TERMINATORS = 18
    LINE_TERMINATOR_KEY = 19
    DATE_TIME = 20
    SOUND2 = 21
    RESOURCE_STREAM = 22
    GRAPHICS_CHAR_INPUT = 23
    DRAW_IMAGE_SCALE = 24


# The CharOutput selector's answers (Glk: Output).
CHAR_OUTPUT_CANNOT_PRINT = 0
CHAR_OUTPUT_APPROX_PRINT = 1
CHAR_OUTPUT_EXACT_PRINT = 2

# Event types glk_select_poll may report; never input (Glk: Other
# Events).
_POLLABLE = frozenset(
    {
        EventType.TIMER,
        EventType.ARRANGE,
        EventType.REDRAW,
        EventType.SOUND_NOTIFY,
        EventType.VOLUME_NOTIFY,
    }
)

# The lowest special keycode; glk.h defines the range this way.
_SPECIAL_KEYS = 0x100000000 - KeyCode.MAXVAL

# Characters deleted from a game-supplied filename (Glk: File
# References).
_ILLEGAL_IN_NAME = frozenset('"\\/><:|?*')

# The suffix a file wears, by what it is for (Glk: File
# References).
_SUFFIXES = {
    FileUsage.SAVED_GAME: ".glksave",
    FileUsage.TRANSCRIPT: ".txt",
    FileUsage.INPUT_RECORD: ".txt",
}
_DEFAULT_SUFFIX = ".glkdata"

_LATIN_1_LIMIT = 0x100


class Waiting:
    """A suspended select: the seat the awaited event will land in.

    Attributes:
        struct: The event struct the game handed to glk_select,
            filled when the host delivers the event.
        writebacks: The bridge's deferred writes. An empty struct
            must not travel back into VM memory when the call
            returns, so the bridge parks the writes here and
            deliver_event runs them once the struct is filled.
    """

    def __init__(self, struct: RefStruct) -> None:
        """Open over the struct, with nothing yet to write back."""

        self.struct = struct
        self.writebacks: list[Callable[[], None]] = []


class Glk:
    """A Glk library instance.

    Attributes:
        frontend: The display rendered into and read from.
        save_dir: Where game-named files live; every sanitized
            filename resolves inside it.
        resources: The pictures, sounds, and data on offer.
        root: The root of the window tree, or None before the
            first window opens.
        current_stream: Where the printing functions send output,
            or None (Glk: Streams).
        windows: Every live window, newest first -- the order
            glkapi.js iterates, by prepending.
        streams: Every live stream, newest first.
        filerefs: Every live file reference, newest first.
        channels: Every live sound channel, newest first.
        stylehints: The hints set by stylehint_set, for a display
            that honors them.
        timer_interval: The requested timer cadence in
            milliseconds, zero for none.
        pending_events: Events a display has posted -- timers,
            sound notifications -- waiting for the next select.
        waiting: The suspended select an event has yet to answer,
            for a display that suspends; None while the machine
            runs.
        on_dispose: Set by the bridge, so a closed object's id
            stops resolving.
    """

    def __init__(
        self,
        frontend: Frontend | None = None,
        *,
        save_dir: Path | None = None,
        resources: Resources | None = None,
    ) -> None:
        """Open with no windows, over a display or over nothing."""

        self.frontend = frontend if frontend is not None else NullFrontend()
        self.save_dir = save_dir if save_dir is not None else Path.cwd()
        self.resources = resources if resources is not None else Resources()
        self.root: Window | None = None
        self.current_stream: Stream | None = None
        self.windows: list[Window] = []
        self.streams: list[Stream] = []
        self.filerefs: list[FileRef] = []
        self.channels: list[SoundChannel] = []
        self.stylehints: dict[tuple[int, int, int], int] = {}
        self.timer_interval = 0
        self.pending_events: list[Event] = []
        self.waiting: Waiting | None = None
        self.on_dispose: Callable[[GlkObject], None] | None = None

        self.frontend.attach(self)

    # -- internals -------------------------------------------------------

    def _dispose(self, obj: GlkObject) -> None:
        """Mark an object dead and tell the bridge to forget it."""

        obj.disposed = True

        if self.on_dispose is not None:
            self.on_dispose(obj)

    def _rearrange(self) -> None:
        """Lay the window tree out over the display again.

        Metrics are refreshed here rather than at window creation,
        so a display that changes its font mid-game only has to
        re-arrange.
        """

        if self.root is None:
            return

        for window in self.windows:
            window.metrics = self.frontend.metrics_for(window)

        width, height = self.frontend.size()

        self.root.rearrange((0, 0, width, height))

        for window in self.windows:
            if isinstance(window, GraphicsWindow) and window.moved:
                # The move cleared the canvas to background; the
                # game owes it a redraw and is told so (Glk:
                # Window Events).
                window.moved = False
                self.post_event(Event(EventType.REDRAW, window))

    # -- main (Glk: Your Program's Main Function) --------------------------

    def glk_exit(self) -> None:
        """End the session, showing whatever is pending first.

        Raises:
            GlulxSessionEnd: Always; that is the point.
        """

        self.frontend.flush(self.root)

        raise GlulxSessionEnd

    def glk_tick(self) -> None:
        """Yield time to the display; here, nothing (Glk: The Tick Thing)."""

    def glk_gestalt(self, selector: int, value: int) -> int:
        """Ask a capability question (Glk: The Gestalt System)."""

        return self.glk_gestalt_ext(selector, value, None)

    def glk_gestalt_ext(  # noqa: PLR0911, PLR0912 -- one flat answer per selector
        self, selector: int, value: int, array: Buffer | None
    ) -> int:
        """Ask a capability question with room for extra answers."""

        if selector == GlkGestalt.VERSION:
            return GLK_VERSION

        if selector == GlkGestalt.CHAR_INPUT:
            # Any Latin-1 printable, plus the special keycodes.
            # Unknown is not a key a game can ask to receive -- it
            # is what a display reports when it cannot name one
            # (Glk: Character Input).
            return int(_is_printable(value) or _SPECIAL_KEYS <= value < KeyCode.UNKNOWN)

        if selector == GlkGestalt.LINE_INPUT:
            # A line is made of printable characters; the special
            # keys can only end one, which is the LineTerminators
            # selector's business (Glk: Line Input).
            return int(_is_printable(value) and value != NEWLINE)

        if selector == GlkGestalt.CHAR_OUTPUT:
            printable = _is_printable(value)

            if array is not None and len(array) > 0:
                array[0] = 1 if printable else 0

            return CHAR_OUTPUT_EXACT_PRINT if printable else CHAR_OUTPUT_CANNOT_PRINT

        if selector == GlkGestalt.GRAPHICS:
            return int(self.frontend.graphics)

        if selector in (GlkGestalt.DRAW_IMAGE, GlkGestalt.DRAW_IMAGE_SCALE):
            # The argument is a window type, and images draw only
            # in graphics windows here: "libraries may implement
            # both, neither, or only one" (Glk: Testing for
            # Graphics Capabilities). Text buffer images -- margin
            # alignments, flow breaks -- remain unclaimed.
            return int(self.frontend.graphics and value == WindowType.GRAPHICS)

        if selector == GlkGestalt.GRAPHICS_TRANSPARENCY:
            # Alpha travels the whole way at a drawing display:
            # the decoder keeps translucent pictures' straight
            # colors and opacities, and the window blends them on
            # the blit -- "the appropriate degree of transparency"
            # made true (Glk: Testing for Graphics Capabilities).
            return int(self.frontend.graphics)

        if selector == GlkGestalt.GRAPHICS_CHAR_INPUT:
            # Character input is window-blind at every display
            # here -- the keyboard answers whichever window asked
            # -- so a canvas takes keystrokes wherever a canvas
            # can exist at all (Glk: Testing for Graphics
            # Capabilities).
            return int(self.frontend.graphics)

        if selector in (
            GlkGestalt.SOUND,
            GlkGestalt.SOUND2,
            GlkGestalt.SOUND_VOLUME,
            GlkGestalt.SOUND_NOTIFY,
        ):
            return int(self.frontend.sound)

        if selector == GlkGestalt.SOUND_MUSIC:
            # Music means MOD and song files (Glk: Testing for
            # Sound Capabilities); the only decoder aboard is
            # AIFF, so the claim stays honestly zero whatever
            # else the display can play.
            return 0

        if selector == GlkGestalt.MOUSE_INPUT:
            # The argument is a window type, and only grids and
            # graphics windows can carry a mouse position (Glk:
            # Mouse Input Events).
            return int(
                self.frontend.mouse_input
                and value in (WindowType.TEXT_GRID, WindowType.GRAPHICS)
            )

        if selector == GlkGestalt.TIMER:
            return int(self.frontend.timer_input)

        if selector == GlkGestalt.HYPERLINKS:
            # Link markup is accepted on any stream; whether a link
            # can be *selected* is the separate question below.
            return 1

        if selector == GlkGestalt.HYPERLINK_INPUT:
            return int(self.frontend.hyperlink_input)

        if selector in (
            GlkGestalt.UNICODE,
            GlkGestalt.UNICODE_NORM,
            GlkGestalt.LINE_INPUT_ECHO,
            GlkGestalt.LINE_TERMINATORS,
            GlkGestalt.LINE_TERMINATOR_KEY,
            GlkGestalt.DATE_TIME,
            GlkGestalt.RESOURCE_STREAM,
        ):
            return 1

        # Every selector from a Glk yet to be written: zero is the
        # honest answer for the unsupported and the unknown alike.
        return 0

    # -- windows (Glk: Window Opening, Closing, and Constraints) -----------

    def glk_window_iterate(
        self, window: Window | None, rockref: Ref | None
    ) -> Window | None:
        """Walk the live windows (Glk: Iterating Through Opaque Objects)."""

        return _iterate(self.windows, window, rockref)

    def glk_window_get_rock(self, window: Window | None) -> int:
        """The rock the window was opened with (Glk: Rocks)."""

        return 0 if window is None else window.rock

    def glk_window_get_root(self) -> Window | None:
        """The root of the window tree, or None with none open."""

        return self.root

    def glk_window_open(
        self, split: Window | None, method: int, size: int, wtype: int, rock: int
    ) -> Window | None:
        """Open a window, splitting an existing one after the first.

        An unsupported window type answers None rather than
        faulting, so a game can probe for graphics support by
        trying (Glk: Window Opening, Closing, and Constraints).

        Raises:
            GlulxGlkError: For a split that contradicts the tree
                -- a first window with a split, a later one
                without, or a method that is not a direction plus
                a division.
        """

        if self.root is None:
            if split is not None:
                msg = "window_open: splitwin must be null for the first window"

                raise GlulxGlkError(msg)
        elif split is None:
            msg = "window_open: splitwin must not be null"

            raise GlulxGlkError(msg)
        else:
            division = method & WindowMethod.DIVISION_MASK

            if division not in (WindowMethod.FIXED, WindowMethod.PROPORTIONAL):
                msg = "window_open: the method is neither fixed nor proportional"

                raise GlulxGlkError(msg)

            if (method & WindowMethod.DIR_MASK) not in (
                WindowMethod.LEFT,
                WindowMethod.RIGHT,
                WindowMethod.ABOVE,
                WindowMethod.BELOW,
            ):
                msg = "window_open: the method names no direction"

                raise GlulxGlkError(msg)

        window = _make_window(wtype, rock, graphics=self.frontend.graphics)

        if window is None:
            return None

        self.windows.insert(0, window)
        self.streams.insert(0, window.stream)

        if split is None:
            self.root = window
        else:
            parent = split.parent
            pair = PairWindow(split, window, window, method, size)

            self.windows.insert(0, pair)

            split.parent = pair
            window.parent = pair
            pair.parent = parent

            if parent is None:
                self.root = pair
            elif parent.child1 is split:
                parent.child1 = pair
            else:
                parent.child2 = pair

        self._rearrange()

        return window

    def glk_window_close(self, window: Window | None, result: RefStruct | None) -> None:
        """Close a window and its whole subtree.

        The sibling is promoted into the parent pair's place (Glk:
        Window Opening, Closing, and Constraints).

        Raises:
            GlulxGlkError: For the null window.
        """

        if window is None:
            msg = "window_close: invalid window"

            raise GlulxGlkError(msg)

        counts = window.stream.close()

        if result is not None:
            result.set_all(*counts)

        for descendant in _subtree(window):
            self._forget_window(descendant)

        parent = window.parent

        if parent is None:
            self.root = None
        else:
            sibling = parent.child2 if parent.child1 is window else parent.child1
            grandparent = parent.parent

            self._forget_window(parent)

            sibling.parent = grandparent

            if grandparent is None:
                self.root = sibling
            elif grandparent.child1 is parent:
                grandparent.child1 = sibling
            else:
                grandparent.child2 = sibling

        self._rearrange()

    def _forget_window(self, window: Window) -> None:
        """Drop one window and its stream from the live lists."""

        if window in self.windows:
            self.windows.remove(window)

        if window.stream in self.streams:
            self.streams.remove(window.stream)

        if self.current_stream is window.stream:
            self.current_stream = None

        self._dispose(window.stream)
        self._dispose(window)

    def glk_window_get_size(
        self, window: Window | None, widthref: Ref | None, heightref: Ref | None
    ) -> None:
        """The window's size in its own units (Glk: Changing Window Constraints)."""

        width, height = (0, 0) if window is None else (window.width, window.height)

        if widthref is not None:
            widthref.value = width

        if heightref is not None:
            heightref.value = height

    def glk_window_set_arrangement(
        self, window: Window | None, method: int, size: int, key: Window | None
    ) -> None:
        """Change a pair's split (Glk: Changing Window Constraints).

        The windows never flip or rotate: changing the direction
        within its axis moves the constraint to the other child
        while the glass stays where it is, which the model carries
        by swapping the children -- glkapi.js does the same.

        Raises:
            GlulxGlkError: When the window is not a pair, the
                method changes the split's axis, or the key is a
                pair or lives outside this pair's subtree.
        """

        if not isinstance(window, PairWindow):
            msg = "window_set_arrangement: not a pair window"

            raise GlulxGlkError(msg)

        direction = method & WindowMethod.DIR_MASK
        vertical = direction in (WindowMethod.LEFT, WindowMethod.RIGHT)
        backward = direction in (WindowMethod.LEFT, WindowMethod.ABOVE)

        if vertical != window.vertical:
            # "You can't flip or rotate them" (Glk: Changing
            # Window Constraints).
            msg = "window_set_arrangement: a split cannot change its axis"

            raise GlulxGlkError(msg)

        if key is not None:
            if isinstance(key, PairWindow):
                msg = "window_set_arrangement: the key cannot be a pair window"

                raise GlulxGlkError(msg)

            if key not in _subtree(window):
                msg = "window_set_arrangement: the key must live under the pair"

                raise GlulxGlkError(msg)

        if backward != window.backward:
            window.child1, window.child2 = window.child2, window.child1

        window.set_method(method)

        window.size = size

        if key is not None:
            window.key = key

        self._rearrange()

    def glk_window_get_arrangement(
        self,
        window: Window | None,
        methodref: Ref | None,
        sizeref: Ref | None,
        keyref: Ref | None,
    ) -> None:
        """Report a pair's split (Glk: Changing Window Constraints).

        Raises:
            GlulxGlkError: When the window is not a pair.
        """

        if not isinstance(window, PairWindow):
            msg = "window_get_arrangement: not a pair window"

            raise GlulxGlkError(msg)

        if methodref is not None:
            methodref.value = window.method

        if sizeref is not None:
            sizeref.value = window.size

        if keyref is not None:
            keyref.value = window.key

    def glk_window_get_type(self, window: Window | None) -> int:
        """The window's type number (Glk: The Types of Windows)."""

        return 0 if window is None else window.wintype

    def glk_window_get_parent(self, window: Window | None) -> Window | None:
        """The pair above the window, or None at the root."""

        return None if window is None else window.parent

    def glk_window_get_sibling(self, window: Window | None) -> Window | None:
        """The window on the other side of the parent pair."""

        if window is None or window.parent is None:
            return None

        parent = window.parent

        return parent.child2 if parent.child1 is window else parent.child1

    def glk_window_clear(self, window: Window | None) -> None:
        """Erase the window (Glk: Other Window Functions)."""

        if window is not None:
            window.clear()

    def glk_window_move_cursor(
        self, window: Window | None, xpos: int, ypos: int
    ) -> None:
        """Place a grid's cursor (Glk: Text Grid Windows).

        Raises:
            GlulxGlkError: When the window is not a text grid.
        """

        if not isinstance(window, TextGridWindow):
            msg = "window_move_cursor: not a text grid window"

            raise GlulxGlkError(msg)

        window.move_cursor(xpos, ypos)

    def glk_window_get_stream(self, window: Window | None) -> Stream | None:
        """The window's own output stream (Glk: Window Streams)."""

        return None if window is None else window.stream

    def glk_window_set_echo_stream(
        self, window: Window | None, stream: Stream | None
    ) -> None:
        """Copy the window's output to a stream too (Glk: Echo Streams)."""

        if window is not None:
            window.echo_stream = stream

    def glk_window_get_echo_stream(self, window: Window | None) -> Stream | None:
        """The window's echo stream, or None without one."""

        return None if window is None else window.echo_stream

    def glk_set_window(self, window: Window | None) -> None:
        """Send the printing functions to this window (Glk: How To Print)."""

        self.current_stream = None if window is None else window.stream

    # -- streams (Glk: Streams) --------------------------------------------

    def glk_stream_iterate(
        self, stream: Stream | None, rockref: Ref | None
    ) -> Stream | None:
        """Walk the live streams."""

        return _iterate(self.streams, stream, rockref)

    def glk_stream_get_rock(self, stream: Stream | None) -> int:
        """The rock the stream was opened with (Glk: Rocks)."""

        return 0 if stream is None else stream.rock

    def glk_stream_open_memory(
        self, buf: Buffer | None, fmode: int, rock: int
    ) -> Stream:
        """Open a stream over game memory (Glk: Memory Streams)."""

        return self._open_memory(buf, fmode, rock, unicode=False)

    def glk_stream_open_memory_uni(
        self, buf: Buffer | None, fmode: int, rock: int
    ) -> Stream:
        """Open a word-array stream over game memory."""

        return self._open_memory(buf, fmode, rock, unicode=True)

    def _open_memory(
        self, buf: Buffer | None, fmode: int, rock: int, *, unicode: bool
    ) -> Stream:
        """Open a memory stream in one of the modes that fit it.

        Raises:
            GlulxGlkError: For WriteAppend, which the spec forbids
                on a memory stream (Glk: Memory Streams).
        """

        if fmode not in (FileMode.READ, FileMode.WRITE, FileMode.READ_WRITE):
            msg = "stream_open_memory: illegal filemode"

            raise GlulxGlkError(msg)

        stream = MemoryStream(buf, fmode, rock, unicode=unicode)

        self.streams.insert(0, stream)

        return stream

    def glk_stream_close(self, stream: Stream | None, result: RefStruct | None) -> None:
        """Close a stream, reporting its counts (Glk: Closing Streams).

        Raises:
            GlulxGlkError: For the null stream.
        """

        if stream is None:
            msg = "stream_close: invalid stream"

            raise GlulxGlkError(msg)

        counts = stream.close()

        if result is not None:
            result.set_all(*counts)

        if stream in self.streams:
            self.streams.remove(stream)

        if self.current_stream is stream:
            self.current_stream = None

        self._dispose(stream)

    def glk_stream_set_current(self, stream: Stream | None) -> None:
        """Choose where the printing functions send output."""

        self.current_stream = stream

    def glk_stream_get_current(self) -> Stream | None:
        """The stream the printing functions write to, or None."""

        return self.current_stream

    def glk_stream_set_position(
        self, stream: Stream | None, position: int, mode: int
    ) -> None:
        """Move a stream's mark (Glk: Stream Positions)."""

        if stream is not None:
            stream.set_position(position, mode)

    def glk_stream_get_position(self, stream: Stream | None) -> int:
        """A stream's mark (Glk: Stream Positions)."""

        return 0 if stream is None else stream.get_position()

    # -- file references (Glk: File References) ----------------------------

    def glk_fileref_create_temp(self, usage: int, rock: int) -> FileRef:
        """A reference to a fresh temporary file."""

        handle, path = tempfile.mkstemp(prefix="voxam-glk-")

        os.close(handle)

        return self._new_fileref(Path(path), usage, rock, temporary=True)

    def glk_fileref_create_by_name(self, usage: int, name: str, rock: int) -> FileRef:
        """A reference to a file the game names itself."""

        return self._new_fileref(self._path_for(name, usage), usage, rock)

    def glk_fileref_create_by_prompt(
        self, usage: int, fmode: int, rock: int
    ) -> FileRef | None:
        """A reference to a file the player names.

        A cancelled prompt yields the null reference (Glk: File
        References).
        """

        name = self.frontend.prompt_file(usage, fmode)

        if not name:
            return None

        return self._new_fileref(self._path_for(name, usage), usage, rock)

    def glk_fileref_create_from_fileref(
        self, usage: int, fileref: FileRef | None, rock: int
    ) -> FileRef:
        """A reference to the same file, for a different usage.

        Raises:
            GlulxGlkError: For the null reference.
        """

        if fileref is None:
            msg = "fileref_create_from_fileref: invalid fileref"

            raise GlulxGlkError(msg)

        return self._new_fileref(Path(fileref.filename), usage, rock)

    def glk_fileref_destroy(self, fileref: FileRef | None) -> None:
        """Drop a reference; a temporary file dies with it (Glk: File References)."""

        if fileref is None:
            return

        if fileref in self.filerefs:
            self.filerefs.remove(fileref)

        if fileref.temporary:
            Path(fileref.filename).unlink(missing_ok=True)

        self._dispose(fileref)

    def glk_fileref_delete_file(self, fileref: FileRef | None) -> None:
        """Delete the file the reference names."""

        if fileref is not None:
            Path(fileref.filename).unlink(missing_ok=True)

    def glk_fileref_does_file_exist(self, fileref: FileRef | None) -> int:
        """Whether the named file exists right now."""

        return int(fileref is not None and Path(fileref.filename).is_file())

    def glk_fileref_iterate(
        self, fileref: FileRef | None, rockref: Ref | None
    ) -> FileRef | None:
        """Walk the live file references."""

        return _iterate(self.filerefs, fileref, rockref)

    def glk_fileref_get_rock(self, fileref: FileRef | None) -> int:
        """The rock the reference was created with (Glk: Rocks)."""

        return 0 if fileref is None else fileref.rock

    def _new_fileref(
        self, path: Path, usage: int, rock: int, *, temporary: bool = False
    ) -> FileRef:
        """Record a reference on the live list."""

        fileref = FileRef(str(path), usage, rock, temporary=temporary)

        self.filerefs.insert(0, fileref)

        return fileref

    def _path_for(self, name: str, usage: int) -> Path:
        """A game-supplied name, made a path inside the save dir.

        The recommended simplification, as cheapglk implements it:
        delete every character in the illegal set, truncate at the
        first period, use "null" if nothing is left, then append a
        suffix chosen by usage (Glk: File References). Not a spec
        requirement, but it is what lets Glk implementations
        exchange files -- and it means a name arriving from game
        bytecode cannot reach outside the save directory by any
        route.
        """

        stem = "".join(
            char for char in name.partition(".")[0] if char not in _ILLEGAL_IN_NAME
        )

        if not stem:
            stem = "null"

        suffix = _SUFFIXES.get(usage & FileUsage.TYPE_MASK, _DEFAULT_SUFFIX)

        return self.save_dir / (stem + suffix)

    # -- file streams (Glk: File Streams) ----------------------------------

    def glk_stream_open_file(
        self, fileref: FileRef | None, fmode: int, rock: int
    ) -> Stream | None:
        """Open a byte stream over the referenced file."""

        return self._open_file(fileref, fmode, rock, unicode=False)

    def glk_stream_open_file_uni(
        self, fileref: FileRef | None, fmode: int, rock: int
    ) -> Stream | None:
        """Open a word stream over the referenced file."""

        return self._open_file(fileref, fmode, rock, unicode=True)

    def _open_file(
        self, fileref: FileRef | None, fmode: int, rock: int, *, unicode: bool
    ) -> Stream | None:
        """Open a file stream, or None where it will not open (Glk: File Streams).

        Raises:
            GlulxGlkError: For the null reference, or a mode that
                is not one of the four.
        """

        if fileref is None:
            msg = "stream_open_file: invalid fileref"

            raise GlulxGlkError(msg)

        modes = {
            FileMode.READ: "rb",
            FileMode.WRITE: "wb",
            FileMode.READ_WRITE: "r+b",
            # Not "ab": POSIX append mode forces every write to the
            # end of the file, but Glk only asks that the *mark*
            # start there -- a later seek must be honored (Glk:
            # Stream Positions).
            FileMode.WRITE_APPEND: "r+b",
        }

        if fmode not in modes:
            msg = "stream_open_file: illegal filemode"

            raise GlulxGlkError(msg)

        path = Path(fileref.filename)

        if fmode in (FileMode.READ_WRITE, FileMode.WRITE_APPEND) and not path.exists():
            path.touch()

        try:
            # The variable mode string blurs open()'s overloads to
            # IO[Any]; every mode in the table is binary.
            handle = cast("BinaryIO", path.open(modes[fmode]))
        except OSError:
            # Opening may simply fail, and yields the null stream
            # (Glk: File Streams).
            return None

        if fmode == FileMode.WRITE_APPEND:
            handle.seek(0, 2)

        stream = FileStream(
            handle, fmode, rock, unicode=unicode, text_mode=fileref.text_mode
        )

        self.streams.insert(0, stream)

        return stream

    # -- resource streams (Glk: Resource Streams) --------------------------

    def glk_stream_open_resource(self, filenum: int, rock: int) -> Stream | None:
        """Open a byte stream over a Blorb data resource."""

        return self._open_resource(filenum, rock, unicode=False)

    def glk_stream_open_resource_uni(self, filenum: int, rock: int) -> Stream | None:
        """Open a word stream over a Blorb data resource."""

        return self._open_resource(filenum, rock, unicode=True)

    def _open_resource(
        self, filenum: int, rock: int, *, unicode: bool
    ) -> Stream | None:
        """Open a read-only stream over a data chunk, or None."""

        found = self.resources.data(filenum)

        if found is None:
            return None

        data, is_text = found

        # The same encoding matrix as a file, over bytes instead of
        # a file handle: text plus Unicode means UTF-8, binary
        # means four-byte words (Glk: Resource Streams).
        stream = FileStream(
            BytesIO(data), FileMode.READ, rock, unicode=unicode, text_mode=is_text
        )

        self.streams.insert(0, stream)

        return stream

    # -- sound channels (Glk: Sound) ---------------------------------------

    def glk_schannel_iterate(
        self, channel: SoundChannel | None, rockref: Ref | None
    ) -> SoundChannel | None:
        """Walk the live sound channels."""

        return _iterate(self.channels, channel, rockref)

    def glk_schannel_get_rock(self, channel: SoundChannel | None) -> int:
        """The rock the channel was created with (Glk: Rocks)."""

        return 0 if channel is None else channel.rock

    def glk_schannel_create(self, rock: int) -> SoundChannel | None:
        """Create a channel at full volume.

        The null channel comes back where sound cannot play (Glk:
        Creating and Destroying Sound Channels).
        """

        return self.glk_schannel_create_ext(rock, FULL_VOLUME)

    def glk_schannel_create_ext(self, rock: int, volume: int) -> SoundChannel | None:
        """Create a channel, or None where sound cannot play."""

        if not self.frontend.sound:
            return None

        channel = SoundChannel(volume, rock)

        self.channels.insert(0, channel)

        return channel

    def glk_schannel_destroy(self, channel: SoundChannel | None) -> None:
        """Stop and drop a channel."""

        if channel is None:
            return

        self.glk_schannel_stop(channel)

        if channel in self.channels:
            self.channels.remove(channel)

        self._dispose(channel)

    def glk_schannel_play(self, channel: SoundChannel | None, sound: int) -> int:
        """Play a sound once (Glk: Playing Sounds)."""

        return self.glk_schannel_play_ext(channel, sound, 1, 0)

    def glk_schannel_play_ext(
        self, channel: SoundChannel | None, sound: int, repeats: int, notify: int
    ) -> int:
        """Play a sound repeatedly; return whether it took (Glk: Playing Sounds)."""

        if channel is None:
            return 0

        self.glk_schannel_stop(channel)

        if repeats == 0 or self.resources.sound(sound) is None:
            # Zero repeats is a legal way to say "stop and play
            # nothing" (Glk: Playing Sounds).
            return 0

        if not self.frontend.play_sound(channel, sound, repeats, notify):
            return 0

        channel.sound = sound
        channel.repeats = repeats
        channel.notify = notify
        channel.paused = False

        return 1

    def glk_schannel_play_multi(
        self,
        channels: Sequence[SoundChannel | None] | None,
        sounds: Buffer | None,
        notify: int,
    ) -> int:
        """Start channels together; return how many took (Glk: Playing Sounds)."""

        started = 0

        for channel, sound in zip(channels or [], sounds or [], strict=False):
            started += self.glk_schannel_play_ext(channel, sound, 1, notify)

        return started

    def glk_schannel_stop(self, channel: SoundChannel | None) -> None:
        """Silence a channel (Glk: Playing Sounds)."""

        if channel is not None and channel.sound:
            self.frontend.stop_sound(channel)

            channel.sound = 0
            channel.paused = False

    def glk_schannel_pause(self, channel: SoundChannel | None) -> None:
        """Hold a channel where it is (Glk: Playing Sounds)."""

        if channel is not None and not channel.paused:
            channel.paused = True

            self.frontend.pause_sound(channel, True)

    def glk_schannel_unpause(self, channel: SoundChannel | None) -> None:
        """Let a held channel continue."""

        if channel is not None and channel.paused:
            channel.paused = False

            self.frontend.pause_sound(channel, False)

    def glk_schannel_set_volume(
        self, channel: SoundChannel | None, volume: int
    ) -> None:
        """Set a channel's volume at once (Glk: Other Sound Channel Functions)."""

        self.glk_schannel_set_volume_ext(channel, volume, 0, 0)

    def glk_schannel_set_volume_ext(
        self, channel: SoundChannel | None, volume: int, duration: int, notify: int
    ) -> None:
        """Set a channel's volume, with optional fade and notify.

        The duration and the completion event are the extended
        form's additions (Glk: Other Sound Channel Functions).
        """

        if channel is None:
            return

        channel.volume = volume

        self.frontend.set_volume(channel, volume, duration)

        if notify:
            self.post_event(Event(EventType.VOLUME_NOTIFY, None, 0, notify))

    def glk_sound_load_hint(self, sound: int, flag: int) -> None:
        """Advisory only: a sound is (or is not) about to be used."""

    # -- output (Glk: How To Print) ----------------------------------------

    def glk_put_char(self, ch: int) -> None:
        """Print one Latin-1 character to the current stream."""

        self.glk_put_char_stream(self.current_stream, ch)

    def glk_put_char_uni(self, ch: int) -> None:
        """Print one Unicode character to the current stream."""

        self.glk_put_char_stream_uni(self.current_stream, ch)

    def glk_put_char_stream(self, stream: Stream | None, ch: int) -> None:
        """Print one Latin-1 character to a named stream."""

        if stream is not None:
            stream.put_char(ch & 0xFF)

    def glk_put_char_stream_uni(self, stream: Stream | None, ch: int) -> None:
        """Print one Unicode character to a named stream."""

        if stream is not None:
            stream.put_char(ch)

    def glk_put_string(self, text: str) -> None:
        """Print a string to the current stream."""

        self.glk_put_string_stream(self.current_stream, text)

    def glk_put_string_uni(self, text: str) -> None:
        """Print a Unicode string to the current stream."""

        self.glk_put_string_stream(self.current_stream, text)

    def glk_put_string_stream(self, stream: Stream | None, text: str) -> None:
        """Print a string to a named stream."""

        if stream is not None:
            stream.put_string(text)

    def glk_put_string_stream_uni(self, stream: Stream | None, text: str) -> None:
        """Print a Unicode string to a named stream."""

        self.glk_put_string_stream(stream, text)

    def glk_put_buffer(self, buf: Buffer | None) -> None:
        """Print an array of characters to the current stream."""

        self.glk_put_buffer_stream(self.current_stream, buf)

    def glk_put_buffer_uni(self, buf: Buffer | None) -> None:
        """Print an array of Unicode characters."""

        self.glk_put_buffer_stream(self.current_stream, buf)

    def glk_put_buffer_stream(self, stream: Stream | None, buf: Buffer | None) -> None:
        """Print an array of characters to a named stream."""

        if stream is not None and buf is not None:
            stream.put_buffer(buf)

    def glk_put_buffer_stream_uni(
        self, stream: Stream | None, buf: Buffer | None
    ) -> None:
        """Print an array of Unicode characters to a named stream."""

        self.glk_put_buffer_stream(stream, buf)

    def glk_set_style(self, value: int) -> None:
        """Choose the style of coming output (Glk: Styles)."""

        self.glk_set_style_stream(self.current_stream, value)

    def glk_set_style_stream(self, stream: Stream | None, value: int) -> None:
        """Choose a stream's style; only window streams show one."""

        if isinstance(stream, WindowStream):
            stream.window.style = value

    # -- input from streams (Glk: How To Read) -----------------------------

    def glk_get_char_stream(self, stream: Stream | None) -> int:
        """Read one character, or -1 at the end."""

        return -1 if stream is None else stream.get_char()

    def glk_get_char_stream_uni(self, stream: Stream | None) -> int:
        """Read one Unicode character, or -1 at the end."""

        return self.glk_get_char_stream(stream)

    def glk_get_buffer_stream(self, stream: Stream | None, buf: Buffer | None) -> int:
        """Fill a buffer from a stream; return the count read."""

        if stream is None or buf is None:
            return 0

        return stream.get_buffer(buf)

    def glk_get_buffer_stream_uni(
        self, stream: Stream | None, buf: Buffer | None
    ) -> int:
        """Fill a word buffer from a stream."""

        return self.glk_get_buffer_stream(stream, buf)

    def glk_get_line_stream(self, stream: Stream | None, buf: Buffer | None) -> int:
        """Read a line from a stream; return the count read."""

        if stream is None or buf is None:
            return 0

        return stream.get_line(buf)

    def glk_get_line_stream_uni(self, stream: Stream | None, buf: Buffer | None) -> int:
        """Read a line of Unicode characters from a stream."""

        return self.glk_get_line_stream(stream, buf)

    # -- style hints (Glk: Suggesting the Appearance of Styles) ------------

    def glk_stylehint_set(self, wtype: int, styl: int, hint: int, value: int) -> None:
        """Record a styling suggestion for a display to honor."""

        self.stylehints[(wtype, styl, hint)] = value

    def glk_stylehint_clear(self, wtype: int, styl: int, hint: int) -> None:
        """Withdraw a styling suggestion."""

        self.stylehints.pop((wtype, styl, hint), None)

    def glk_style_distinguish(
        self, window: Window | None, style1: int, style2: int
    ) -> int:
        """Whether two styles look different (Glk: Testing the Appearance of Styles).

        Only the display knows; one that cannot say answers no,
        which is what the spec asks of the unsure.
        """

        if window is None or style1 == style2:
            return 0

        return int(self.frontend.style_distinguish(window, style1, style2))

    def glk_style_measure(
        self, window: Window | None, styl: int, hint: int, resultref: Ref | None
    ) -> int:
        """Measure one attribute of a style, if the display can."""

        if window is None:
            return 0

        measured = self.frontend.style_measure(window, styl, hint)

        if measured is None:
            return 0

        if resultref is not None:
            resultref.value = measured

        return 1

    # -- graphics (Glk: Graphics) ------------------------------------------

    def glk_image_get_info(
        self, image: int, widthref: Ref | None, heightref: Ref | None
    ) -> int:
        """Report a picture's size.

        Answered from the resource bytes, so it works even where
        nothing can be drawn (Glk: Testing for Graphics
        Capabilities).
        """

        info = self.resources.image(image)

        if widthref is not None:
            widthref.value = info.width if info is not None else 0

        if heightref is not None:
            heightref.value = info.height if info is not None else 0

        return int(info is not None)

    def glk_image_draw(
        self, window: Window | None, image: int, val1: int, val2: int
    ) -> int:
        """Draw a picture at its own size (Glk: Graphics in Graphics Windows)."""

        return self._draw(window, image, val1, val2, None, None)

    def glk_image_draw_scaled(  # noqa: PLR0913, PLR0917 -- the six values of the call
        self,
        window: Window | None,
        image: int,
        val1: int,
        val2: int,
        width: int,
        height: int,
    ) -> int:
        """Draw a picture scaled to a size."""

        return self._draw(window, image, val1, val2, width, height)

    def glk_image_draw_scaled_ext(  # noqa: PLR0913, PLR0917 -- the eight values
        self,
        window: Window | None,
        image: int,
        val1: int,
        val2: int,
        width: int,
        height: int,
        imagerule: int,
        maxwidth: int,
    ) -> int:
        """Draw a picture under the extended scaling rules.

        The rules beyond plain scaling are aspect-ratio hints for
        the display; the display era decides how far to honor
        them, so they pass through untouched here.
        """

        del imagerule, maxwidth

        return self._draw(window, image, val1, val2, width, height)

    def _draw(  # noqa: PLR0913, PLR0917 -- the drawing call's own shape
        self,
        window: Window | None,
        image: int,
        val1: int,
        val2: int,
        width: int | None,
        height: int | None,
    ) -> int:
        """Hand a measured picture to the display, if there is one."""

        info = self.resources.image(image)

        if window is None or info is None:
            return 0

        return int(
            self.frontend.draw_image(
                window,
                info,
                val1,
                val2,
                info.width if width is None else width,
                info.height if height is None else height,
            )
        )

    def glk_window_flow_break(self, window: Window | None) -> None:
        """Break text past the margin images (Glk: Graphics in Text Buffer Windows)."""

        if window is not None:
            self.frontend.flow_break(window)

    def glk_window_erase_rect(
        self, window: Window | None, left: int, top: int, width: int, height: int
    ) -> None:
        """Erase a rectangle to the background (Glk: Graphics in Graphics Windows)."""

        if window is not None:
            self.frontend.erase_rect(window, left, top, width, height)

    def glk_window_fill_rect(  # noqa: PLR0913, PLR0917 -- the rectangle, colored
        self,
        window: Window | None,
        color: int,
        left: int,
        top: int,
        width: int,
        height: int,
    ) -> None:
        """Fill a rectangle with a color."""

        if window is not None:
            self.frontend.fill_rect(window, color, left, top, width, height)

    def glk_window_set_background_color(
        self, window: Window | None, color: int
    ) -> None:
        """Choose the color future clears fill with."""

        if window is not None:
            self.frontend.set_background_color(window, color)

    # -- hyperlinks (Glk: Hyperlinks) --------------------------------------

    def glk_set_hyperlink(self, linkval: int) -> None:
        """Mark coming output as a link (Glk: Creating Hyperlinks)."""

        self.glk_set_hyperlink_stream(self.current_stream, linkval)

    def glk_set_hyperlink_stream(self, stream: Stream | None, linkval: int) -> None:
        """Everything written from here on belongs to this link."""

        if stream is not None:
            stream.hyperlink = linkval

    def glk_request_hyperlink_event(self, window: Window | None) -> None:
        """Ask for a link selection (Glk: Accepting Hyperlink Events)."""

        if window is not None:
            window.hyperlink_request = True

    def glk_cancel_hyperlink_event(self, window: Window | None) -> None:
        """Withdraw the link request."""

        if window is not None:
            window.hyperlink_request = False

    # -- mouse input (Glk: Mouse Input Events) -----------------------------

    def glk_request_mouse_event(self, window: Window | None) -> None:
        """Ask for a click in a grid or graphics window."""

        if window is not None:
            window.mouse_request = True

    def glk_cancel_mouse_event(self, window: Window | None) -> None:
        """Withdraw the click request."""

        if window is not None:
            window.mouse_request = False

    # -- events (Glk: Events) ----------------------------------------------

    def glk_select(self, event: RefStruct) -> None:
        """Wait until something happens, then report it.

        A blocking display is asked for input on the spot and the
        struct fills before this returns. A suspending display is
        never asked: whatever is already queued is delivered, and
        otherwise the wait is recorded for the host, who answers
        through deliver_event once the event arrives (Glk: Events).

        Raises:
            GlulxGlkError: When no outstanding request could ever
                be satisfied -- waiting longer would never end.
        """

        if not self.frontend.suspends:
            result = self._wait_for_event()

            event.set_all(*result.as_fields())

            return

        self.frontend.flush(self.root)

        if self.pending_events:
            event.set_all(*self.pending_events.pop(0).as_fields())

            return

        if not self._awaited():
            msg = "glk_select with no input requested: the game would wait forever"

            raise GlulxGlkError(msg)

        self.waiting = Waiting(event)

    def _awaited(self) -> bool:
        """Whether any outstanding request can ever be answered.

        A request counts only where the display claims the
        matching capability, the same rule the blocking loop
        enforces one refusal at a time. A running timer counts
        too: a suspending display's host raises timer events
        itself, which is more than a blocking display can promise
        when no input is requested alongside.
        """

        if any(
            held.line_request is not None or held.char_request for held in self.windows
        ):
            return True

        if self.frontend.mouse_input and any(
            held.mouse_request for held in self.windows
        ):
            return True

        if self.frontend.hyperlink_input and any(
            held.hyperlink_request for held in self.windows
        ):
            return True

        return bool(self.frontend.timer_input and self.timer_interval)

    def deliver_event(self, event: Event) -> None:
        """Complete a suspended select with the event a host collected.

        The struct fills and the bridge's deferred writes run, so
        the answer lands in VM memory exactly where the game will
        look when it steps on.

        Raises:
            GlulxGlkError: When nothing stands suspended. An event
                with no seat to land in is a driver's bug, and
                should be loud.
        """

        waiting = self.waiting

        if waiting is None:
            msg = "an event arrived with no select suspended to receive it"

            raise GlulxGlkError(msg)

        waiting.struct.set_all(*event.as_fields())

        for writeback in waiting.writebacks:
            writeback()

        self.waiting = None

    def glk_select_poll(self, event: RefStruct) -> None:
        """Report a queued non-input event without waiting.

        A poll must never return input, but it may return the
        events a display raises by itself -- a timer, a resize, a
        sound ending (Glk: Other Events). Those are exactly the
        ones sitting in the pending queue.
        """

        for index, queued in enumerate(self.pending_events):
            if queued.kind in _POLLABLE:
                event.set_all(*self.pending_events.pop(index).as_fields())

                return

        event.set_all(EventType.NONE, None, 0, 0)

    def display_resized(self) -> None:
        """Re-lay the windows after the display changed size.

        A display whose window can be resized calls this; the
        layout is redone and the game is told, so it can redraw
        anything it keeps track of itself (Glk: Window Arrangement
        Events).
        """

        self._rearrange()

        self.post_event(Event(EventType.ARRANGE, self.root, 0, 0))

    def post_event(self, event: Event) -> None:
        """Queue an event for the next select.

        Glk delivers these asynchronously; a blocking display has
        no other way to raise one.
        """

        self.pending_events.append(event)

    def _wait_for_event(self) -> Event:
        """Block until something happens, then report it.

        The loop exists for interruptions: a display may return
        None from an input call because a timer fired instead, in
        which case the input request stays pending and we come
        round again to pick the queued event up.

        Raises:
            GlulxGlkError: When nothing is queued and no
                outstanding request can ever be satisfied --
                waiting longer would never end.
        """

        while True:
            self.frontend.flush(self.root)

            if self.pending_events:
                return self.pending_events.pop(0)

            window = next(
                (held for held in self.windows if held.line_request is not None), None
            )

            if window is not None:
                event = self._collect_line(window)

                if event is not None:
                    return event

                continue

            window = next((held for held in self.windows if held.char_request), None)

            if window is not None:
                event = self._collect_char(window)

                if event is not None:
                    return event

                continue

            window = next((held for held in self.windows if held.mouse_request), None)

            if window is not None:
                position = self.frontend.read_mouse(window)

                if position is not None:
                    window.mouse_request = False

                    return Event(EventType.MOUSE_INPUT, window, *position)

                if self.frontend.mouse_input:
                    # It can click, so this was an interruption,
                    # not a refusal: come round again. A display
                    # that cannot click falls through to the error
                    # below instead.
                    continue

            window = next(
                (held for held in self.windows if held.hyperlink_request), None
            )

            if window is not None:
                value = self.frontend.read_hyperlink(window)

                if value:
                    window.hyperlink_request = False

                    return Event(EventType.HYPERLINK, window, value, 0)

                if self.frontend.hyperlink_input:
                    continue

            msg = "glk_select with no input requested: the game would wait forever"

            raise GlulxGlkError(msg)

    def _collect_line(self, window: Window) -> Event | None:
        """Ask the display for the line a window is waiting on."""

        request = window.line_request

        if request is None:  # pragma: no cover -- guarded by the caller's scan
            return None

        answer = self.frontend.read_line(window, request.capacity)

        if answer is None:
            return None

        return self.deliver_line(window, *answer)

    def deliver_line(self, window: Window, text: str, terminator: int = 0) -> Event:
        """Complete a window's line request with text from anywhere.

        Split out from the display ask because a display need not
        be asked for the window it answers about: a protocol
        display gets told which window the player typed into,
        which may not be the one glk_select happened to ask after.

        Raises:
            GlulxGlkError: When the window has no line request.
        """

        request = window.line_request

        if request is None:
            msg = "line input delivered to a window not expecting it"

            raise GlulxGlkError(msg)

        window.line_request = None
        length = _fill(request.buf, (ord(char) for char in text))

        if (
            request.echo
            and not self.frontend.echoes_input
            and isinstance(window, TextBufferWindow)
        ):
            # The line the player typed becomes part of the
            # window's text, in the Input style (Glk: Line Input
            # Events).
            previous = window.style
            window.style = Style.INPUT

            window.stream.put_string(text[:length] + "\n")

            window.style = previous

        return Event(EventType.LINE_INPUT, window, length, terminator)

    def _collect_char(self, window: Window) -> Event | None:
        """Ask the display for the keystroke a window awaits."""

        value = self.frontend.read_char(window)

        if value is None:
            return None

        return self.deliver_char(window, value)

    def deliver_char(self, window: Window, value: int) -> Event:
        """Complete a window's character request.

        Raises:
            GlulxGlkError: When the window has no character
                request.
        """

        if not window.char_request:
            msg = "character input delivered to a window not expecting it"

            raise GlulxGlkError(msg)

        window.char_request = False

        return Event(EventType.CHAR_INPUT, window, value & _MASK, 0)

    def glk_request_line_event(
        self, window: Window | None, buf: Buffer | None, initlen: int
    ) -> None:
        """Ask for a line of Latin-1 input (Glk: Line Input Events)."""

        self._request_line(window, buf, initlen, unicode=False)

    def glk_request_line_event_uni(
        self, window: Window | None, buf: Buffer | None, initlen: int
    ) -> None:
        """Ask for a line of Unicode input."""

        self._request_line(window, buf, initlen, unicode=True)

    def _request_line(
        self, window: Window | None, buf: Buffer | None, initlen: int, *, unicode: bool
    ) -> None:
        """Open a line request on a window.

        Raises:
            GlulxGlkError: For the null window, or one already
                waiting on a line.
        """

        if window is None:
            msg = "request_line_event: invalid window"

            raise GlulxGlkError(msg)

        if window.line_request is not None:
            msg = "request_line_event: input already requested"

            raise GlulxGlkError(msg)

        window.line_request = LineRequest(buf, initlen, unicode=unicode)

    def glk_cancel_line_event(
        self, window: Window | None, event: RefStruct | None
    ) -> None:
        """Withdraw a line request (Glk: Line Input Events).

        The full spec behavior returns any partial input; with a
        blocking display there is never any, so the answer is the
        no-event.
        """

        if window is not None:
            window.line_request = None

        if event is not None:
            event.set_all(EventType.NONE, None, 0, 0)

    def glk_request_char_event(self, window: Window | None) -> None:
        """Ask for one Latin-1 keystroke (Glk: Character Input Events)."""

        self._request_char(window, unicode=False)

    def glk_request_char_event_uni(self, window: Window | None) -> None:
        """Ask for one Unicode keystroke."""

        self._request_char(window, unicode=True)

    def _request_char(self, window: Window | None, *, unicode: bool) -> None:
        """Open a character request on a window.

        Raises:
            GlulxGlkError: For the null window.
        """

        if window is None:
            msg = "request_char_event: invalid window"

            raise GlulxGlkError(msg)

        window.char_request = True
        window.char_unicode = unicode

    def glk_cancel_char_event(self, window: Window | None) -> None:
        """Withdraw a character request."""

        if window is not None:
            window.char_request = False

    def glk_request_timer_events(self, millisecs: int) -> None:
        """Ask for a timer event every so often; zero stops them (Glk: Timer Events)."""

        self.timer_interval = millisecs

        self.frontend.set_timer(millisecs)

    def glk_set_echo_line_event(self, window: Window | None, value: int) -> None:
        """Choose whether the pending line echoes (Glk: Line Input Events)."""

        if window is not None and window.line_request is not None:
            window.line_request.echo = bool(value)

    def glk_set_terminators_line_event(
        self, window: Window | None, keycodes: Buffer | None
    ) -> None:
        """Choose the special keys that may end the pending line."""

        if window is not None and window.line_request is not None:
            window.line_request.terminators = tuple(keycodes or ())

    # -- the system clock (Glk: The System Clock) --------------------------

    def glk_current_time(self, timeref: RefStruct | None) -> None:
        """Store the current Unix time as a glktimeval_t."""

        now = _now()

        if timeref is not None:
            timeref.set_all(*_split_seconds(int(now)), int((now % 1) * 1_000_000))

    def glk_current_simple_time(self, factor: int) -> int:
        """The Unix time divided down, rounding toward the past."""

        if factor == 0:
            return -1

        return int(_now()) // factor

    def glk_time_to_date_utc(
        self, timeref: RefStruct | None, dateref: RefStruct | None
    ) -> None:
        """Explode a timestamp into a UTC glkdate_t (Glk: Time and Date Conversions)."""

        self._time_to_date(timeref, dateref, utc=True)

    def glk_time_to_date_local(
        self, timeref: RefStruct | None, dateref: RefStruct | None
    ) -> None:
        """Explode a timestamp into a local-time glkdate_t."""

        self._time_to_date(timeref, dateref, utc=False)

    def _time_to_date(
        self, timeref: RefStruct | None, dateref: RefStruct | None, *, utc: bool
    ) -> None:
        """Fill a date struct from a time struct."""

        if dateref is None:
            return

        if timeref is None:
            dateref.set_all(*([0] * 8))

            return

        high, low, microsec = cast("list[int]", timeref.fields)

        dateref.set_all(*_break_out(_join_seconds(high, low), microsec, utc=utc))

    def glk_simple_time_to_date_utc(
        self, time: int, factor: int, dateref: RefStruct | None
    ) -> None:
        """Explode a divided-down time into a UTC date."""

        self._simple_to_date(time, factor, dateref, utc=True)

    def glk_simple_time_to_date_local(
        self, time: int, factor: int, dateref: RefStruct | None
    ) -> None:
        """Explode a divided-down time into a local date."""

        self._simple_to_date(time, factor, dateref, utc=False)

    def _simple_to_date(
        self, time: int, factor: int, dateref: RefStruct | None, *, utc: bool
    ) -> None:
        """Fill a date struct from a divided-down time."""

        if dateref is not None:
            # Resolution is whole seconds, so microseconds come
            # back zero (Glk: Time and Date Conversions).
            dateref.set_all(*_break_out(time * factor, 0, utc=utc))

    def glk_date_to_time_utc(
        self, dateref: RefStruct | None, timeref: RefStruct | None
    ) -> None:
        """Collapse a UTC date into a glktimeval_t."""

        self._date_to_time(dateref, timeref, utc=True)

    def glk_date_to_time_local(
        self, dateref: RefStruct | None, timeref: RefStruct | None
    ) -> None:
        """Collapse a local date into a glktimeval_t."""

        self._date_to_time(dateref, timeref, utc=False)

    def _date_to_time(
        self, dateref: RefStruct | None, timeref: RefStruct | None, *, utc: bool
    ) -> None:
        """Fill a time struct from a date struct."""

        if timeref is None:
            return

        fields = None if dateref is None else cast("list[int]", dateref.fields)
        seconds = None if fields is None else _to_seconds(fields, utc=utc)

        if fields is None or seconds is None:
            # An unrepresentable time is -1 in both words (Glk:
            # Time and Date Conversions).
            timeref.set_all(-1, 0xFFFFFFFF, 0)

            return

        timeref.set_all(*_split_seconds(seconds), fields[7] % 1_000_000)

    def glk_date_to_simple_time_utc(
        self, dateref: RefStruct | None, factor: int
    ) -> int:
        """Collapse a UTC date into a divided-down time."""

        return self._date_to_simple(dateref, factor, utc=True)

    def glk_date_to_simple_time_local(
        self, dateref: RefStruct | None, factor: int
    ) -> int:
        """Collapse a local date into a divided-down time."""

        return self._date_to_simple(dateref, factor, utc=False)

    def _date_to_simple(
        self, dateref: RefStruct | None, factor: int, *, utc: bool
    ) -> int:
        """A date as a divided-down time, or -1 where impossible."""

        if dateref is None or factor == 0:
            return -1

        seconds = _to_seconds(cast("list[int]", dateref.fields), utc=utc)

        return -1 if seconds is None else seconds // factor

    # -- case mapping (Glk: Upper and Lower Case) --------------------------

    def glk_char_to_lower(self, ch: int) -> int:
        """Lowercase one Latin-1 character."""

        return _map_case(ch, lower=True)

    def glk_char_to_upper(self, ch: int) -> int:
        """Uppercase one Latin-1 character."""

        return _map_case(ch, lower=False)

    def glk_buffer_to_lower_case_uni(self, buf: Buffer | None, numchars: int) -> int:
        """Lowercase a Unicode buffer in place."""

        return _map_buffer(buf, numchars, str.lower)

    def glk_buffer_to_upper_case_uni(self, buf: Buffer | None, numchars: int) -> int:
        """Uppercase a Unicode buffer in place."""

        return _map_buffer(buf, numchars, str.upper)

    def glk_buffer_to_title_case_uni(
        self, buf: Buffer | None, numchars: int, lowerrest: int
    ) -> int:
        """Title-case the first character (Glk: Upper and Lower Case).

        Titlecase is a third Unicode case, not a synonym for
        uppercase: the ligature U+FB04 uppercases to "FFL" but
        title-cases to "Ffl", and U+01C4 has the distinct
        titlecase form U+01C5.
        """

        chars = _chars(buf, numchars)

        if not chars:
            return 0

        head = chars[0].title()
        rest = [char.lower() for char in chars[1:]] if lowerrest else chars[1:]

        return _store_chars(buf, head + "".join(rest))

    def glk_buffer_canon_decompose_uni(self, buf: Buffer | None, numchars: int) -> int:
        """Unicode NFD decomposition (Glk: Unicode String Normalization)."""

        return _normalize(buf, numchars, "NFD")

    def glk_buffer_canon_normalize_uni(self, buf: Buffer | None, numchars: int) -> int:
        """Decompose, then canonically compose -- Unicode NFC."""

        return _normalize(buf, numchars, "NFC")


# -- helpers ----------------------------------------------------------------

_WINDOW_TYPES: dict[int, type[Window]] = {
    WindowType.BLANK: BlankWindow,
    WindowType.TEXT_BUFFER: TextBufferWindow,
    WindowType.TEXT_GRID: TextGridWindow,
    WindowType.GRAPHICS: GraphicsWindow,
}


def _make_window(wtype: int, rock: int, *, graphics: bool) -> Window | None:
    """Build a window of a type, or None for a type not on offer.

    Raises:
        GlulxGlkError: For the pair type, which only splitting
            creates (Glk: Pair Windows).
    """

    if wtype == WindowType.PAIR:
        msg = "window_open: cannot open a pair window directly"

        raise GlulxGlkError(msg)

    if wtype == WindowType.GRAPHICS and not graphics:
        # Null rather than a fault, so a game can probe for
        # graphics by trying to open a window (Glk: Graphics
        # Windows).
        return None

    factory = _WINDOW_TYPES.get(wtype)

    return None if factory is None else factory(rock)


def _subtree(window: Window) -> list[Window]:
    """A window and all its descendants."""

    found = [window]

    if isinstance(window, PairWindow):
        found += _subtree(window.child1) + _subtree(window.child2)

    return found


def _iterate[Held: (Window, Stream, FileRef, SoundChannel)](
    objects: list[Held], current: Held | None, rockref: Ref | None
) -> Held | None:
    """One step of an object walk (Glk: Iterating Through Opaque Objects).

    The null object starts the walk; the object after the last --
    and an object no longer on the list at all -- ends it.
    """

    if current is None:
        found = objects[0] if objects else None
    else:
        try:
            index = objects.index(current)
        except ValueError:
            found = None
        else:
            found = objects[index + 1] if index + 1 < len(objects) else None

    if rockref is not None:
        rockref.value = found.rock if found is not None else 0

    return found


def _fill(buf: Buffer | None, values: Iterable[int]) -> int:
    """Write values into a buffer from the start; return how many fit.

    Stopping at the buffer's end is what the input functions want:
    they fill as much as fits and report that.
    """

    if buf is None:
        return 0

    written = 0
    capacity = len(buf)

    for value in values:
        if written >= capacity:
            break

        buf[written] = value
        written += 1

    return written


_PRINTABLE_ASCII = range(0x20, 0x7F)
_PRINTABLE_LATIN_1 = range(0xA0, 0x100)


def _is_printable(ch: int) -> bool:
    """Latin-1 printable, plus newline (Glk: Output)."""

    return ch == NEWLINE or ch in _PRINTABLE_ASCII or ch in _PRINTABLE_LATIN_1


def _map_case(ch: int, *, lower: bool) -> int:
    """One character's mapping, where one character can hold it.

    Only single-character mappings are representable; German
    sharp-s uppercasing to "SS" is the usual offender, and stays
    itself (Glk: Upper and Lower Case).
    """

    if not 0 <= ch <= MAX_UNICODE:
        return ch

    mapped = chr(ch).lower() if lower else chr(ch).upper()

    return ord(mapped) if len(mapped) == 1 else ch


def _chars(buf: Buffer | None, numchars: int) -> list[str]:
    """The first so-many characters of a buffer, as text."""

    if buf is None or numchars <= 0:
        return []

    return [to_char(buf[index]) for index in range(min(numchars, len(buf)))]


def _store_chars(buf: Buffer | None, text: str) -> int:
    """Write text back, truncating at the buffer's capacity.

    The true converted length is returned even when it exceeds the
    buffer, whose contents past that point are undefined (Glk:
    Upper and Lower Case).
    """

    _fill(buf, (ord(char) for char in text))

    return len(text)


def _normalize(buf: Buffer | None, numchars: int, form: Literal["NFC", "NFD"]) -> int:
    """Normalize a buffer in place to a Unicode normal form."""

    chars = _chars(buf, numchars)

    return _store_chars(buf, unicodedata.normalize(form, "".join(chars)))


def _map_buffer(
    buf: Buffer | None, numchars: int, transform: Callable[[str], str]
) -> int:
    """Case-map a buffer one character at a time.

    Per character, not on the joined string: Python applies
    context-sensitive rules to a whole string -- Greek sigma
    lowercases differently at the end of a word -- while the spec
    asks for "every character" mapped to its equivalent (Glk:
    Upper and Lower Case).
    """

    chars = _chars(buf, numchars)

    return _store_chars(buf, "".join(transform(char) for char in chars))


def _now() -> float:
    """The current Unix time. Split out so tests can pin it."""

    return datetime.datetime.now(datetime.UTC).timestamp()


def _split_seconds(seconds: int) -> tuple[int, int]:
    """A signed second count as the (high, low) pair of a glktimeval_t.

    The two words are one signed 64-bit number (Glk: The System
    Clock), so an arithmetic shift produces the high word for
    negative times too -- and -1 falls out as all-ones in both,
    which is the failure value.
    """

    return seconds >> 32, seconds & 0xFFFFFFFF


def _join_seconds(high: int, low: int) -> int:
    """The (high, low) pair back into one signed second count."""

    return (high << 32) | (low & 0xFFFFFFFF)


def _break_out(seconds: int, microsec: int, *, utc: bool) -> tuple[int, ...]:
    """Explode a timestamp into the eight fields of a glkdate_t."""

    try:
        moment = (
            datetime.datetime.fromtimestamp(seconds, datetime.UTC)
            if utc
            else datetime.datetime.fromtimestamp(seconds, datetime.UTC).astimezone()
        )
    except (OverflowError, OSError, ValueError):
        return (0,) * 8

    return (
        moment.year,
        moment.month,
        moment.day,
        # Python counts weekdays from Monday; Glk counts from
        # Sunday (Glk: The System Clock).
        (moment.weekday() + 1) % 7,
        moment.hour,
        moment.minute,
        moment.second,
        microsec,
    )


def _to_seconds(fields: list[int], *, utc: bool) -> int | None:
    """Turn glkdate_t fields into a timestamp, or None if impossible.

    The fields "need not be in their normal ranges; they will be
    normalized" (Glk: Time and Date Conversions). Months are
    normalized by hand because they have no fixed length;
    everything else is a plain timedelta from the first of the
    month, which lets a day of 40 or an hour of -3 work.
    """

    year, month, day, _weekday, hour, minute, second, microsec = fields[:8]
    year += (month - 1) // 12
    month = (month - 1) % 12 + 1

    try:
        base = datetime.datetime(year, month, 1, tzinfo=datetime.UTC if utc else None)
        moment = base + datetime.timedelta(
            days=day - 1,
            hours=hour,
            minutes=minute,
            seconds=second,
            microseconds=microsec,
        )

        return int(moment.timestamp())
    except (OverflowError, OSError, ValueError):
        return None
