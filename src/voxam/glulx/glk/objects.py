"""Glk's object model: windows, streams, filerefs, sound channels.

The four opaque classes a game can hold references to (Glk: Opaque
Objects) are declared here, along with the constants that describe
them. Behavior that reaches across objects -- opening windows,
dispatching events -- belongs to the api era; this module is the
model those functions will operate on.

Objects carry no dispatch-layer identity. The 32-bit ids Glulx sees
are the bridge era's business, so nothing here knows a VM exists.
"""

import math
from collections.abc import Iterable, Iterator
from typing import BinaryIO, ClassVar, NamedTuple, Protocol

# What a non-Unicode stream substitutes for a character it cannot
# hold: '?', the placeholder the spec names (Glk: Output).
UNPRINTABLE = 0x3F

MAX_UNICODE = 0x10FFFF

NEWLINE = 0x0A

_MASK = 0xFFFFFFFF

# The surrogate block: reserved for UTF-16 pairs, so the values are
# not independently encodable characters.
_SURROGATE_FIRST = 0xD800
_SURROGATE_LAST = 0xDFFF

# One past the last character a byte stream can hold.
_BYTE_LIMIT = 0x100

# The UTF-8 lead-byte thresholds: below the first is ASCII, and
# each of the others starts a sequence of that many bytes.
_ASCII_LIMIT = 0x80
_LEAD_TWO = 0xC0
_LEAD_THREE = 0xE0
_LEAD_FOUR = 0xF0


def to_char(value: int) -> str:
    """Render a Glulx character value as text.

    Glulx characters are arbitrary 32-bit values, so a game can
    print something that is not a Unicode code point at all --
    glulxercise does exactly that. Anything outside the Unicode
    range, and the surrogate block (which is not independently
    encodable), becomes '?' (Glk: Output).
    """

    if value > MAX_UNICODE or _SURROGATE_FIRST <= value <= _SURROGATE_LAST:
        return chr(UNPRINTABLE)

    return chr(value)


class Buffer(Protocol):
    """What a stream asks of a character array: sized and indexed.

    The bridge era's live view onto VM memory satisfies this; so
    does a plain list of ints, which is what the tests hand in.
    """

    def __len__(self) -> int:
        """The array's capacity, in characters."""

        ...

    def __getitem__(self, index: int) -> int:
        """The character at an index."""

        ...

    def __setitem__(self, index: int, value: int) -> None:
        """Store a character at an index."""

    def __iter__(self) -> Iterator[int]:
        """The characters in order."""

        ...


# -- the constant families --------------------------------------------------


class WindowType:
    """The window types (Glk: The Types of Windows).

    ALL is not a type a window can have: it is the wildcard the
    gestalt selectors accept when asking about every type at once.
    """

    ALL = 0
    PAIR = 1
    BLANK = 2
    TEXT_BUFFER = 3
    TEXT_GRID = 4
    GRAPHICS = 5


class WindowMethod:
    """The split-method bits window_open takes.

    Masked bitfields (Glk: Window Opening, Closing, and
    Constraints) -- a namespace rather than an enum on purpose,
    because BORDER shares the value zero with LEFT.
    """

    LEFT = 0x00
    RIGHT = 0x01
    ABOVE = 0x02
    BELOW = 0x03
    DIR_MASK = 0x0F

    FIXED = 0x10
    PROPORTIONAL = 0x20
    DIVISION_MASK = 0xF0

    BORDER = 0x000
    NO_BORDER = 0x100
    BORDER_MASK = 0x100


class EventType:
    """The event types glk_select can report (Glk: Events)."""

    NONE = 0
    TIMER = 1
    CHAR_INPUT = 2
    LINE_INPUT = 3
    MOUSE_INPUT = 4
    ARRANGE = 5
    REDRAW = 6
    SOUND_NOTIFY = 7
    HYPERLINK = 8
    VOLUME_NOTIFY = 9


class Style:
    """The eleven text styles (Glk: Styles)."""

    NORMAL = 0
    EMPHASIZED = 1
    PREFORMATTED = 2
    HEADER = 3
    SUBHEADER = 4
    ALERT = 5
    NOTE = 6
    BLOCK_QUOTE = 7
    INPUT = 8
    USER1 = 9
    USER2 = 10
    NUMSTYLES = 11


class SeekMode:
    """Where a stream seek measures from (Glk: Stream Positions)."""

    START = 0
    CURRENT = 1
    END = 2


class FileMode:
    """How a stream is opened (Glk: File Streams)."""

    WRITE = 0x01
    READ = 0x02
    READ_WRITE = 0x03
    WRITE_APPEND = 0x05


class FileUsage:
    """What a file is for (Glk: The Types of File References).

    A namespace rather than an enum: the usage is a masked field,
    and BINARY_MODE shares the value zero with DATA.
    """

    DATA = 0x00
    SAVED_GAME = 0x01
    TRANSCRIPT = 0x02
    INPUT_RECORD = 0x03
    TYPE_MASK = 0x0F

    BINARY_MODE = 0x000
    TEXT_MODE = 0x100


class KeyCode:
    """The special keys of character input (Glk: Character Input).

    The function keys are not contiguous with END: glk.h leaves
    0xFFFFFFF2 through 0xFFFFFFF0 unassigned. MAXVAL is glk.h's own
    bookkeeping -- the last keycode is 0x100000000 minus this.
    """

    UNKNOWN = 0xFFFFFFFF
    LEFT = 0xFFFFFFFE
    RIGHT = 0xFFFFFFFD
    UP = 0xFFFFFFFC
    DOWN = 0xFFFFFFFB
    RETURN = 0xFFFFFFFA
    DELETE = 0xFFFFFFF9
    ESCAPE = 0xFFFFFFF8
    TAB = 0xFFFFFFF7
    PAGE_UP = 0xFFFFFFF6
    PAGE_DOWN = 0xFFFFFFF5
    HOME = 0xFFFFFFF4
    END = 0xFFFFFFF3
    FUNC1 = 0xFFFFFFEF
    FUNC2 = 0xFFFFFFEE
    FUNC3 = 0xFFFFFFED
    FUNC4 = 0xFFFFFFEC
    FUNC5 = 0xFFFFFFEB
    FUNC6 = 0xFFFFFFEA
    FUNC7 = 0xFFFFFFE9
    FUNC8 = 0xFFFFFFE8
    FUNC9 = 0xFFFFFFE7
    FUNC10 = 0xFFFFFFE6
    FUNC11 = 0xFFFFFFE5
    FUNC12 = 0xFFFFFFE4
    MAXVAL = 28


# -- the opaque base --------------------------------------------------------


class GlkObject:
    """Base for the four opaque classes.

    The disposed flag exists because Glulx can hold an id for an
    object the game has already closed. The registry is told to
    forget it, but a stale reference reaching a method should fault
    loudly rather than operate on a corpse.

    Attributes:
        rock: The 32-bit value the game filed the object under
            (Glk: Rocks).
        disposed: Whether the object has been destroyed.
    """

    glk_class: ClassVar[int] = -1

    def __init__(self, rock: int = 0) -> None:
        """Take the rock the game supplied, reduced to 32 bits."""

        self.rock = rock & _MASK
        self.disposed = False


# -- streams ----------------------------------------------------------------


class Run(NamedTuple):
    """A span of window text sharing one style and link value."""

    style: int
    hyperlink: int
    text: str


class Placed(NamedTuple):
    """One picture set into a buffer's text flow.

    What a display that lays text around pictures needs to lay
    this one: the Pict's number, the picture whole as a data: url,
    the size the draw asked for, the §imagealign value naming how
    the text meets it, and the link value it was drawn under (Glk:
    Graphics in Text Buffer Windows).
    """

    image: int
    url: str
    width: int
    height: int
    alignment: int
    hyperlink: int


class FlowBreak:
    """A flow break in a buffer's text flow.

    Text past the break starts below any margin images standing at
    the point of the break (Glk: Graphics in Text Buffer Windows).
    """


class Stream(GlkObject):
    """Base stream: a sink, a source, or both (Glk: Streams).

    Attributes:
        readable: Whether characters can be read from it.
        writable: Whether characters can be written to it.
        unicode: Whether it holds full words; a byte stream
            substitutes '?' for anything above 0xFF (Glk: Output).
        readcount: Characters read so far.
        writecount: Characters written so far, discards included.
        hyperlink: The link value written output belongs to; zero
            means "not a link" (Glk: Creating Hyperlinks).
    """

    glk_class: ClassVar[int] = 1

    def __init__(
        self,
        rock: int = 0,
        *,
        readable: bool = False,
        writable: bool = False,
        unicode: bool = False,
    ) -> None:
        """Open with the directions and width the subclass chose."""

        super().__init__(rock)

        self.readable = readable
        self.writable = writable
        self.unicode = unicode
        self.readcount = 0
        self.writecount = 0
        self.hyperlink = 0

    def put_char(self, character: int) -> None:
        """Write one character, counting it even if it goes nowhere.

        The write count reported at close must include characters a
        stream discards -- "it will count the number of characters
        written into the stream, not the number that fit" (Glk:
        Memory Streams) -- so it is incremented before any capacity
        check.
        """

        if not self.writable:
            return

        if not self.unicode and not 0 <= character < _BYTE_LIMIT:
            character = UNPRINTABLE

        self.writecount += 1

        self._emit(character)

    def put_string(self, text: str) -> None:
        """Write a string, one character at a time."""

        for character in text:
            self.put_char(ord(character))

    def put_buffer(self, values: Iterable[int]) -> None:
        """Write a sequence of character values."""

        for value in values:
            self.put_char(value)

    def _emit(self, character: int) -> None:
        """Actually place the character. Each stream type overrides."""

    def get_char(self) -> int:
        """Read one character, or -1 at end of stream."""

        if not self.readable:
            return -1

        value = self._read()

        if value >= 0:
            self.readcount += 1

        return value

    def _read(self) -> int:
        """Actually fetch a character. Each stream type overrides."""

        return -1

    def get_buffer(self, buf: Buffer) -> int:
        """Fill a buffer; return how many characters were read.

        No terminal null is placed (Glk: How To Read).
        """

        count = 0

        for index in range(len(buf)):
            value = self.get_char()

            if value < 0:
                break

            buf[index] = value
            count = index + 1

        return count

    def get_line(self, buf: Buffer) -> int:
        """Read up to a newline, null-terminating; return the length.

        At most one less than the buffer's capacity is stored, the
        newline is kept if one is read, and the result is always
        terminated -- the terminal null not counted (Glk: How To
        Read).
        """

        capacity = len(buf)

        if capacity == 0:
            return 0

        count = 0

        while count < capacity - 1:
            value = self.get_char()

            if value < 0:
                break

            buf[count] = value
            count += 1

            if value == NEWLINE:
                break

        buf[count] = 0

        return count

    def get_position(self) -> int:
        """The stream's mark; zero where seeking is meaningless."""

        return 0

    def set_position(self, position: int, mode: int) -> None:
        """Move the mark. Ignored where seeking is meaningless.

        Window streams have no position at all (Glk: Stream
        Positions), which is why doing nothing is the base.
        """

    def close(self) -> tuple[int, int]:
        """Close, answering stream_result_t (Glk: Closing Streams)."""

        self.disposed = True

        return self.readcount, self.writecount


class WindowStream(Stream):
    """A window's output stream, never readable (Glk: Window Streams).

    Always Unicode: the byte-stream rule -- substitute '?' above
    0xFF -- is about how a stream *stores* characters, which for a
    memory or file stream is a real constraint and for a window is
    not. A window shows text, and what it can render is the
    display's affair. glkote's glkapi.js sets the same flag on the
    same object.
    """

    def __init__(self, window: "Window", rock: int = 0) -> None:
        """Bind to the window whose output this is."""

        super().__init__(rock, writable=True, unicode=True)

        self.window = window

    def _emit(self, character: int) -> None:
        """Hand the character to the window to hold."""

        self.window.put_char(character)


class MemoryStream(Stream):
    """A stream over an array in the game's memory (Glk: Memory Streams).

    The buffer is whatever the bridge hands over -- a live view, so
    writes land straight in VM memory. A null buffer is legal: the
    stream then discards writes but still counts them, which is how
    a game measures output length (Glk: Memory Streams).
    """

    def __init__(
        self,
        buf: Buffer | None,
        fmode: int,
        rock: int = 0,
        *,
        unicode: bool = False,
    ) -> None:
        """Open over a buffer, in a file mode's directions."""

        super().__init__(
            rock,
            readable=fmode in (FileMode.READ, FileMode.READ_WRITE),
            writable=fmode
            in (FileMode.WRITE, FileMode.READ_WRITE, FileMode.WRITE_APPEND),
            unicode=unicode,
        )

        self.buf = buf
        self.position = 0

    @property
    def capacity(self) -> int:
        """The buffer's length; zero for the null buffer."""

        return 0 if self.buf is None else len(self.buf)

    def _emit(self, character: int) -> None:
        """Store within the buffer; advance past its end regardless.

        The position advancing past the end is what lets a game
        discover how much output it would have produced.
        """

        if self.buf is not None and self.position < len(self.buf):
            self.buf[self.position] = character

        self.position += 1

    def _read(self) -> int:
        """Fetch at the mark, or -1 past the end."""

        if self.buf is None or self.position >= len(self.buf):
            return -1

        value = self.buf[self.position]
        self.position += 1

        return value

    def get_position(self) -> int:
        """The mark, in characters from the buffer's start."""

        return self.position

    def set_position(self, position: int, mode: int) -> None:
        """Move the mark, clamped to the buffer (Glk: Stream Positions)."""

        if mode == SeekMode.CURRENT:
            position += self.position
        elif mode == SeekMode.END:
            position += self.capacity

        self.position = max(0, min(position, self.capacity))


class FileStream(Stream):
    """A stream over a file (Glk: File Streams).

    Four combinations, and they are all different: a byte stream
    holds one Latin-1 byte per character in either mode; a Unicode
    stream holds four-byte big-endian words in binary mode and
    UTF-8, with no byte-order mark, in text mode (Glk: File
    Streams).

    The UTF-8 case is what makes a text file written through
    glk_stream_open_file_uni readable by anything else -- and
    byte-identical to one written through glk_stream_open_file when
    only ASCII is involved, which the spec requires.
    """

    def __init__(
        self,
        handle: BinaryIO,
        fmode: int,
        rock: int = 0,
        *,
        unicode: bool = False,
        text_mode: bool = False,
    ) -> None:
        """Wrap an open binary handle in a file mode's directions."""

        super().__init__(
            rock,
            readable=fmode in (FileMode.READ, FileMode.READ_WRITE),
            writable=fmode
            in (FileMode.WRITE, FileMode.READ_WRITE, FileMode.WRITE_APPEND),
            unicode=unicode,
        )

        self.handle = handle
        self.utf8 = unicode and text_mode
        self.width = 4 if (unicode and not text_mode) else 1

    def _emit(self, character: int) -> None:
        """Encode one character the way this stream's mode does."""

        if self.utf8:
            self.handle.write(to_char(character).encode("utf-8"))
        else:
            self.handle.write(character.to_bytes(self.width, "big"))

    def _read(self) -> int:
        """Decode one character, or -1 at end of file."""

        if self.utf8:
            return self._read_utf8()

        data = self.handle.read(self.width)

        if len(data) < self.width:
            return -1

        return int.from_bytes(data, "big")

    def _read_utf8(self) -> int:
        """Decode one UTF-8 sequence, one byte at a time.

        The length is read off the leading byte rather than
        decoding the whole file, because a stream may be positioned
        anywhere and the caller wants exactly one character.
        """

        first = self.handle.read(1)

        if not first:
            return -1

        lead = first[0]

        if lead < _ASCII_LIMIT:
            return lead

        if lead >= _LEAD_FOUR:
            extra = 3
        elif lead >= _LEAD_THREE:
            extra = 2
        elif lead >= _LEAD_TWO:
            extra = 1
        else:
            # A stray continuation byte.
            return UNPRINTABLE

        try:
            return ord((first + self.handle.read(extra)).decode("utf-8"))
        except UnicodeDecodeError:
            return UNPRINTABLE

    def get_position(self) -> int:
        """The mark, straight from the handle."""

        return self.handle.tell()

    def set_position(self, position: int, mode: int) -> None:
        """Move the mark; an unknown mode measures from the start."""

        whence = {SeekMode.START: 0, SeekMode.CURRENT: 1, SeekMode.END: 2}

        self.handle.seek(position, whence.get(mode, 0))

    def close(self) -> tuple[int, int]:
        """Close the file along with the stream."""

        counts = super().close()

        self.handle.close()

        return counts


# -- windows ----------------------------------------------------------------


class LineRequest:
    """A pending line request on a window (Glk: Line Input Events).

    Attributes:
        buf: The buffer the line lands in, or None.
        initlen: How many characters of it are pre-filled.
        unicode: Whether the buffer holds words rather than bytes.
        echo: Whether the finished line is echoed to the window
            (Glk: Line Input Events, via set_echo_line_event).
        terminators: The special keys that may end the line.
    """

    def __init__(
        self,
        buf: Buffer | None,
        initlen: int = 0,
        *,
        unicode: bool = False,
        echo: bool = True,
    ) -> None:
        """Record what the request asked for."""

        self.buf = buf
        self.initlen = initlen
        self.unicode = unicode
        self.echo = echo
        self.terminators: tuple[int, ...] = ()

    @property
    def capacity(self) -> int:
        """The buffer's length; zero for the null buffer."""

        return 0 if self.buf is None else len(self.buf)


class Metrics(NamedTuple):
    """What a text window costs in the display's own layout unit.

    The window tree is arranged in display units. A terminal's unit
    *is* the character cell, so its metrics are 1x1 and every
    measurement is the same number either way. A graphical display
    lays out in pixels and gives the size of its font's cell here,
    which is what lets a text window report its size in characters
    while a graphics window reports the pixels the spec says it
    must (Glk: Graphics Windows).

    The cell is a float because a display may measure one. GlkOte
    says so outright -- "we can wind up with a non-integer
    charwidth value" -- and rounding it either way is wrong in one
    direction or the other: too small and a window claims more
    columns than fit, too large and it wastes them. The counts that
    come out of it are integers; the cell itself need not be.

    The margins are what a window spends on padding and borders,
    over and above its characters. They are nothing on a terminal,
    which is why they default so.
    """

    width: float = 1
    height: float = 1
    margin_x: float = 0
    margin_y: float = 0


def _cells(extent: int, cell: float, margin: float) -> int:
    """How many characters fit an extent, margin taken out.

    Rounded down, for the same reason the other direction rounds
    up: a window claiming a column it does not have room for spills
    over its own edge.
    """

    return max(0, int((extent - margin) / cell)) if cell > 0 else 0


# The metrics of a display whose unit is already the character.
CHARACTER_CELL = Metrics(1, 1)


class Window(GlkObject):
    """Base window. Subclasses differ in how they hold contents.

    Attributes:
        parent: The pair window this hangs under, or None at the
            root.
        stream: The window's own output stream.
        echo_stream: A stream that receives a copy of the window's
            output, or None (Glk: Echo Streams).
        style: The style new output is written in.
        line_request: The pending line request, or None.
        char_request: Whether character input is requested.
        char_unicode: Whether the character request wants words.
        hyperlink_request: Whether a hyperlink click is requested.
        mouse_request: Whether a mouse click is requested.
        metrics: The display's cell measurements for this window.
        pending_clear: Set by clear, cleared by a display once it
            redraws. A window that keeps its own contents (a grid)
            erases them itself; one whose contents live in the
            display -- a buffer's scrollback, a graphics window's
            pixels -- can only ask.
        bbox: (left, top, right, bottom), in display units.
    """

    glk_class: ClassVar[int] = 0
    wintype: ClassVar[int] = WindowType.BLANK

    def __init__(self, rock: int = 0) -> None:
        """Open unattached, with nothing requested."""

        super().__init__(rock)

        self.parent: PairWindow | None = None
        self.stream = WindowStream(self)
        self.echo_stream: Stream | None = None
        self.style: int = Style.NORMAL
        self.line_request: LineRequest | None = None
        self.char_request = False
        self.char_unicode = False
        self.hyperlink_request = False
        self.mouse_request = False
        self.metrics = CHARACTER_CELL
        self.pending_clear = False
        self.bbox = (0, 0, 0, 0)

    @property
    def width(self) -> int:
        """The window's width in its own units -- here, display units."""

        return max(0, self.bbox[2] - self.bbox[0])

    @property
    def height(self) -> int:
        """The window's height in its own units."""

        return max(0, self.bbox[3] - self.bbox[1])

    def extent(
        self,
        size: int,
        *,
        vertical: bool,  # noqa: ARG002 -- the axis matters only to text windows
    ) -> int:
        """Display units needed for a size in this window's units.

        A fixed split is expressed in the key window's measurement
        system (Glk: Window Opening, Closing, and Constraints),
        which for a graphics window means pixels and for a text
        window means characters plus whatever the display spends
        around them. The conversion lives here so that rule stays
        in one place.
        """

        return size

    def put_char(self, character: int) -> None:
        """Hold a character from this window's stream.

        The base discards -- a blank window supports no output --
        but the copy to any echo stream happens for every type
        (Glk: Echo Streams).
        """

        if self.echo_stream is not None:
            self.echo_stream.put_char(character)

    def clear(self) -> None:
        """Erase the window's contents.

        A graphics window is filled with its background color, a
        blank window has nothing to erase (Glk: Graphics Windows).
        Both are the display's to do, so the base does no more than
        raise the flag.
        """

        self.pending_clear = True

    def rearrange(self, box: tuple[int, int, int, int]) -> None:
        """Take a new bounding box from the layout."""

        self.bbox = box


class SizelessWindow(Window):
    """A window with no measurement system, and so no size.

    glk_window_get_size "returns the actual size of the window, in
    its measurement system" (Glk: Changing Window Constraints) --
    and a blank window has nothing in it, while a pair window is a
    split rather than a place. The spec answers (0,0) for blank
    windows outright (Glk: Blank Windows); glkapi.js reaches the
    same answer for pairs by only assigning a size to the three
    types that have one.

    The bounding box is still there and still correct; it is what a
    display draws borders from. This is only what the *game* is
    told.
    """

    @property
    def width(self) -> int:
        """Always zero: no measurement system to answer in."""

        return 0

    @property
    def height(self) -> int:
        """Always zero, as the width is."""

        return 0


class BlankWindow(SizelessWindow):
    """A window that is always blank (Glk: Blank Windows)."""

    wintype: ClassVar[int] = WindowType.BLANK


class GraphicsWindow(Window):
    """A grid of pixels (Glk: Graphics Windows).

    The pixels themselves live in the display; the model holds the
    box and the requests, and its size *is* the box, because a
    graphics window measures in pixels.

    Attributes:
        moved: Raised by a rearrange that changed a real box. The
            display's pixels are absolute and do not travel with
            the box, so the canvas is cleared and the game is owed
            a redraw event for it (Glk: Window Events).
    """

    wintype: ClassVar[int] = WindowType.GRAPHICS

    def __init__(self, rock: int = 0) -> None:
        """Open asking to be cleared: a fresh canvas is background.

        The background color is initially white (Glk: Graphics
        Windows), and whatever the display holds where the canvas
        now hangs is someone else's leavings.
        """

        super().__init__(rock)

        self.pending_clear = True
        self.moved = False

    def rearrange(self, box: tuple[int, int, int, int]) -> None:
        """Take a new box; a changed one loses the canvas.

        The spec allows a resized window's contents to be thrown
        away so long as the game hears a redraw event -- "the
        window in question has been cleared to its background
        color, and must be redrawn" (Glk: Window Events). A fresh
        window whose old box was empty owes no such event: it
        opens as background and the game knows it.
        """

        if box != self.bbox:
            self.pending_clear = True
            self.moved = self.moved or (self.width > 0 and self.height > 0)

        super().rearrange(box)


class TextWindow(Window):
    """Shared by the two text window types: measured in characters.

    A graphical display arranges in pixels, so a text window's own
    size is that extent divided by the font's cell -- which is the
    number the game gets from glk_window_get_size and the number it
    lays its text out against.
    """

    @property
    def width(self) -> int:
        """The width in characters, by way of the metrics."""

        return _cells(
            self.bbox[2] - self.bbox[0], self.metrics.width, self.metrics.margin_x
        )

    @property
    def height(self) -> int:
        """The height in characters, by way of the metrics."""

        return _cells(
            self.bbox[3] - self.bbox[1], self.metrics.height, self.metrics.margin_y
        )

    def extent(self, size: int, *, vertical: bool) -> int:
        """Room for a count of characters, margin included.

        Rounded up: a window a fraction of a pixel short would have
        its last line pushed out past its own border.
        """

        cell = self.metrics.width if vertical else self.metrics.height
        margin = self.metrics.margin_x if vertical else self.metrics.margin_y

        return math.ceil(size * cell + margin)


class TextBufferWindow(TextWindow):
    """A scrolling text window (Glk: Text Buffer Windows).

    Contents accumulate as runs of text sharing a style and a link
    value, oldest first -- with any pictures and flow breaks a
    claiming display placed among them, in flow order -- until a
    display drains them.
    """

    wintype: ClassVar[int] = WindowType.TEXT_BUFFER

    def __init__(self, rock: int = 0) -> None:
        """Open empty."""

        super().__init__(rock)

        self.content: list[Run | Placed | FlowBreak] = []

    def put_char(self, character: int) -> None:
        """Append to the last run, or start a new one.

        A run continues only while both the style and the link
        value hold -- and only across text: a placed picture or a
        flow break ends the run it follows.
        """

        super().put_char(character)

        char = to_char(character)
        link = self.stream.hyperlink
        last = self.content[-1] if self.content else None

        if isinstance(last, Run) and (last.style, last.hyperlink) == (
            self.style,
            link,
        ):
            self.content[-1] = Run(last.style, last.hyperlink, last.text + char)
        else:
            self.content.append(Run(self.style, link, char))

    def put_placed(self, placed: Placed) -> None:
        """Set a picture into the flow, after everything written so far."""

        self.content.append(placed)

    def put_break(self) -> None:
        """Set a flow break into the flow (Glk: Graphics in Text Buffer Windows)."""

        self.content.append(FlowBreak())

    def text(self) -> str:
        """The accumulated text, styles and pictures flattened away."""

        return "".join(run.text for run in self.content if isinstance(run, Run))

    def take_text(self) -> str:
        """Return accumulated text and reset, for a display to render."""

        out = self.text()

        self.content.clear()

        return out

    def take_content(self) -> list[Run | Placed | FlowBreak]:
        """Return accumulated flow and reset, keeping their styles.

        The same drain as take_text, for a display that renders
        styles -- and lays pictures -- rather than flattening them.
        """

        out = self.content[:]

        self.content.clear()

        return out

    def clear(self) -> None:
        """Erase the held runs along with raising the flag."""

        super().clear()

        self.content.clear()


class TextGridWindow(TextWindow):
    """A character grid with a cursor (Glk: Text Grid Windows).

    The characters, their styles, and their link values are held as
    parallel row lists, resized whenever the layout hands over a
    new box.
    """

    wintype: ClassVar[int] = WindowType.TEXT_GRID

    def __init__(self, rock: int = 0) -> None:
        """Open with no rows; the first rearrange sizes the grid."""

        super().__init__(rock)

        self.lines: list[list[str]] = []
        self.styles: list[list[int]] = []
        self.links: list[list[int]] = []
        self.cursor_x = 0
        self.cursor_y = 0

    def rearrange(self, box: tuple[int, int, int, int]) -> None:
        """Take a new box and resize the grid to fit it."""

        super().rearrange(box)

        self._resize(self.width, self.height)

    def _resize(self, width: int, height: int) -> None:
        """Grow or trim the rows, keeping what still fits."""

        self.lines = [
            (self.lines[row] + [" "] * width)[:width]
            if row < len(self.lines)
            else [" "] * width
            for row in range(height)
        ]
        self.styles = [
            (self.styles[row] + [Style.NORMAL] * width)[:width]
            if row < len(self.styles)
            else [Style.NORMAL] * width
            for row in range(height)
        ]
        self.links = [
            (self.links[row] + [0] * width)[:width]
            if row < len(self.links)
            else [0] * width
            for row in range(height)
        ]
        self.cursor_x = min(self.cursor_x, max(0, width))
        self.cursor_y = min(self.cursor_y, max(0, height))

    def move_cursor(self, x: int, y: int) -> None:
        """Put the cursor where the game asks.

        Past-the-edge positions are legal: output there falls into
        the void until the cursor comes back inside.
        """

        self.cursor_x = x
        self.cursor_y = y

    def put_char(self, character: int) -> None:
        """Write at the cursor and advance (Glk: Text Grid Windows).

        A newline moves to the start of the next row and prints
        nothing; the right edge wraps; anything landing outside the
        grid is dropped.
        """

        super().put_char(character)

        width, height = self.width, self.height

        if character == NEWLINE:
            self.cursor_x = 0
            self.cursor_y += 1
            return

        if self.cursor_x >= width:
            self.cursor_x = 0
            self.cursor_y += 1

        if 0 <= self.cursor_y < height and 0 <= self.cursor_x < width:
            self.lines[self.cursor_y][self.cursor_x] = to_char(character)
            self.styles[self.cursor_y][self.cursor_x] = self.style
            self.links[self.cursor_y][self.cursor_x] = self.stream.hyperlink

        self.cursor_x += 1

    def clear(self) -> None:
        """Fill the grid with blanks and home the cursor."""

        self._resize(self.width, self.height)

        for row in self.lines:
            for index in range(len(row)):
                row[index] = " "

        self.cursor_x = 0
        self.cursor_y = 0

    def rows(self) -> list[str]:
        """The grid as one string per row."""

        return ["".join(row) for row in self.lines]


class PairWindow(SizelessWindow):
    """An internal node: a split of two (Glk: Window Arrangement).

    Attributes:
        child1: The window on the split's unconstrained side --
            the original window, until a re-arrangement flips the
            direction and swaps the children.
        child2: The window on the side the direction names, which
            carries the size constraint -- the split-off window,
            at first.
        key: The window the split's size is *measured* against.
            Only the measurement: the constraint sits on child2's
            side wherever the key lives, and the spec's own worked
            example puts them apart on purpose (Glk: Changing
            Window Constraints).
        size: The split's size, in the key window's units, or as a
            percentage for a proportional split.
        sized_box: The box the constrained side received, kept for
            displays that draw borders.
    """

    wintype: ClassVar[int] = WindowType.PAIR

    def __init__(
        self, child1: Window, child2: Window, key: Window, method: int, size: int
    ) -> None:
        """Join two windows under a split method."""

        super().__init__(0)

        self.child1 = child1
        self.child2 = child2
        self.key = key
        self.size = size
        self.sized_box = (0, 0, 0, 0)
        self.set_method(method)

    def set_method(self, method: int) -> None:
        """Unpack a method word into the split's parts."""

        self.direction = method & WindowMethod.DIR_MASK
        self.division = method & WindowMethod.DIVISION_MASK
        self.has_border = (method & WindowMethod.BORDER_MASK) == WindowMethod.BORDER
        self.vertical = self.direction in (WindowMethod.LEFT, WindowMethod.RIGHT)
        self.backward = self.direction in (WindowMethod.LEFT, WindowMethod.ABOVE)

    @property
    def method(self) -> int:
        """The split's parts recomposed into a method word."""

        border = WindowMethod.BORDER if self.has_border else WindowMethod.NO_BORDER

        return self.direction | self.division | border

    def rearrange(self, box: tuple[int, int, int, int]) -> None:
        """Split the box between the two children.

        The box is in display units. A proportional split is a
        percentage and needs no conversion; a fixed one is
        expressed in the *key window's* measurement system (Glk:
        Window Opening, Closing, and Constraints), so characters
        for a text window and pixels for a graphics window --
        Window.extent supplies the conversion, which is nothing on
        a terminal.
        """

        super().rearrange(box)

        left, top, right, bottom = box
        extent = (right - left) if self.vertical else (bottom - top)

        if self.division == WindowMethod.PROPORTIONAL:
            split = (extent * self.size) // 100
        else:
            split = self.key.extent(self.size, vertical=self.vertical)

        split = max(0, min(split, extent))

        # How much of the extent the first box gets; the second box
        # takes the rest.
        first = split if self.backward else extent - split

        if self.vertical:
            middle = left + first
            box1 = (left, top, middle, bottom)
            box2 = (middle, top, right, bottom)
        else:
            middle = top + first
            box1 = (left, top, right, middle)
            box2 = (left, middle, right, bottom)

        # The direction decides the sides outright: child2 sits on
        # the named side and takes the split's size, however deep
        # the key window has since been buried -- "the key window
        # for the original split is still the key window ... even
        # though it's now a grandchild" (Glk: Window Opening,
        # Closing, and Constraints).
        if self.backward:
            self.sized_box, other_box = box1, box2
        else:
            self.sized_box, other_box = box2, box1

        self.child2.rearrange(self.sized_box)
        self.child1.rearrange(other_box)


# -- other opaque classes ---------------------------------------------------


class FileRef(GlkObject):
    """A reference to a file (Glk: File References).

    Attributes:
        filename: The path the reference names.
        usage: What the file is for, masked to the type bits.
        text_mode: Whether the file opens in text mode.
        temporary: Whether the file dies with the reference.
    """

    glk_class: ClassVar[int] = 2

    def __init__(
        self, filename: str, usage: int, rock: int = 0, *, temporary: bool = False
    ) -> None:
        """Record what the file is and how it is meant to open."""

        super().__init__(rock)

        self.filename = filename
        self.usage = usage & FileUsage.TYPE_MASK
        self.text_mode = bool(usage & FileUsage.TEXT_MODE)
        self.temporary = temporary


class SoundChannel(GlkObject):
    """A sound channel (Glk: Sound).

    Attributes:
        volume: As a fraction of 0x10000, which is full volume
            (Glk: Other Sound Channel Functions).
        sound: The resource number playing, or 0 for silence.
        repeats: How many plays were asked for.
        notify: The nonzero value a finished play reports with.
        paused: Whether the channel is paused.
    """

    glk_class: ClassVar[int] = 3

    def __init__(self, volume: int = 0x10000, rock: int = 0) -> None:
        """Open silent, at the volume asked for."""

        super().__init__(rock)

        self.volume = volume
        self.sound = 0
        self.repeats = 0
        self.notify = 0
        self.paused = False


# -- events -----------------------------------------------------------------


class Event:
    """One Glk event: the four fields of event_t (Glk: Events).

    Attributes:
        kind: The event type -- event_t calls this field "type",
            which Python spells better as something else.
        window: The window the event belongs to, or None.
        val1: The first value; meaning depends on the type.
        val2: The second value.
    """

    def __init__(
        self,
        kind: int = EventType.NONE,
        window: Window | None = None,
        val1: int = 0,
        val2: int = 0,
    ) -> None:
        """Build an event, defaulting to "nothing happened"."""

        self.kind = kind
        self.window = window
        self.val1 = val1
        self.val2 = val2

    def as_fields(self) -> tuple[int, Window | None, int, int]:
        """The four fields in event_t order."""

        return self.kind, self.window, self.val1, self.val2
