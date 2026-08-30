"""The blessed frontend: the screen model painted onto a terminal.

The model in voxam.screen decides everything -- where each character
lands, what it wears, what scrolled -- and this painter's whole job
is to repaint the rows the model reports damaged, then park the
terminal cursor where the model says the game's cursor stands. The
division keeps the painter too thin to hide bugs: anything worth
testing lives in the model, and the golden-grid suite already holds
it to §8.

The terminal itself arrives through the `blessed` package, the
optional extra the frontend is named for. Only a sliver of it is
used -- geometry, cursor movement, and style sequences -- and that
sliver is a Protocol, so tests drive the painter with a stub and no
terminal at all.
"""

import sys
from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager
from time import monotonic
from typing import Protocol, cast

from voxam.editor import EXPIRED, LineEditor, read_line_edited
from voxam.frontend import GRAPHICS_FONT, Status
from voxam.png import Picture
from voxam.screen import (
    BOLD,
    ITALIC,
    REVERSE,
    Cell,
    ScreenModel,
)
from voxam.sixel import encode as sixel_encode
from voxam.speaker import Speaker

# Special keys arrive from blessed with names; §3.8.2.2 and §3.8.4
# give the input-only ZSCII characters they mean. The cursor keys
# travel as their §3.8.4 codepoints 129 to 132 -- characters no key
# actually types -- which the machine's input seam passes through
# whole, so Beyond Zork's menus can hear them. Anything unnamed
# passes through as the character it already is.
KEY_CHARACTERS = {
    "KEY_ENTER": "\n",
    "KEY_BACKSPACE": "\x7f",
    "KEY_DELETE": "\x7f",
    "KEY_ESCAPE": "\x1b",
    "KEY_UP": "\x81",
    "KEY_DOWN": "\x82",
    "KEY_LEFT": "\x83",
    "KEY_RIGHT": "\x84",
}


# The pause prompt a screenful of unread text waits behind
# (§8.8.3.2.6's courtesy, offered on every painted screen).
MORE_PROMPT = "[MORE]"

# The §8.3.1 colour codes the painter can mix, named as blessed
# knows them. Code 1 is the terminal's own default and needs no
# sequence at all.
COLOUR_NAMES = {
    2: "black",
    3: "red",
    4: "green",
    5: "yellow",
    6: "blue",
    7: "magenta",
    8: "cyan",
    9: "white",
}
DEFAULT_COLOUR = 1

# A screen without an answer for its size -- a pipe, a dumb TTY --
# paints as the classic 80 by 24 glass.
FALLBACK_COLUMNS = 80
FALLBACK_LINES = 24

# How often an infinite wait surfaces for air, in seconds. Each
# heartbeat lets the machine attend to background work -- an ended
# sound's §9.4.4 routine -- while the player thinks at a prompt;
# between heartbeats the wait costs nothing.
IDLE_HEARTBEAT = 0.2

# Sizing sixel pixels against a glass measured only in cells: no
# terminal cell is narrower than 8 pixels or shorter than 16 on a
# modern display, so scaling against these floors magnifies a cover
# as far as it can certainly fit when the terminal will not say
# more.
CELL_WIDTH_FLOOR = 8
CELL_HEIGHT_FLOOR = 16

# Terminal interrogation for the sixel path: a query is written to
# the glass and the answer comes back through the keyboard. The
# DEC primary device attributes query answers CSI ? <attributes> c
# with attribute 4 declaring sixel graphics; the XTWINOPS report
# 16 answers CSI 6 ; <height> ; <width> t, the pixel size of one
# character cell. A terminal that stays quiet past the patience
# window has said no.
DEVICE_ATTRIBUTES_QUERY = "\x1b[c"
DEVICE_ATTRIBUTES_END = "c"
SIXEL_ATTRIBUTE = "4"
CELL_SIZE_QUERY = "\x1b[16t"
CELL_SIZE_END = "t"
CELL_SIZE_REPORT = "6"
CELL_SIZE_FIELDS = 3
QUERY_PATIENCE = 0.15

# The §16 character graphics font, one Unicode stand-in per 8x8
# bitmap. Cells in font 3 hold the character code the game printed;
# painting translates each to the nearest shape a terminal font
# already has. The families, reading down the spec's table: arrows,
# diagonals, single box-drawing lines with every join, the map's
# solid blocks and their diagonal transitions, cell-edge strokes,
# Beyond Zork's stat gauge as eighth-blocks, and the late Anglian
# ("futhorc") runes the §16 remarks decode for a-z. Lossy cells are
# rounded toward whatever keeps the drawn map connected, a call the
# eyeball tests settled: a solid mass meeting a diagonal road keeps
# its mass (a quadrant, not a triangle that bites the room corner),
# and the single-pixel road tips continue their diagonal rather
# than leaving a gap where the road reaches the room.
FONT_3_CHARACTERS = {
    " ": " ",  # 32: blank
    "!": "←",  # 33: left arrow
    '"': "→",  # 34: right arrow
    "#": "╱",  # 35: diagonal, rising
    "$": "╲",  # 36: diagonal, falling
    "%": " ",  # 37: blank
    "&": "─",  # 38: horizontal line, low
    "'": "─",  # 39: horizontal line, high
    "(": "│",  # 40: vertical line, right of centre
    ")": "│",  # 41: vertical line, left of centre
    "*": "┴",  # 42: line up, joined to a horizontal
    "+": "┬",  # 43: line down, joined to a horizontal
    ",": "├",  # 44: vertical joined rightward
    "-": "┤",  # 45: vertical joined leftward
    ".": "└",  # 46: corner, up and right
    "/": "┌",  # 47: corner, down and right
    "0": "┐",  # 48: corner, down and left
    "1": "┘",  # 49: corner, up and left
    "2": "└",  # 50: up-right corner, diagonal tail dropped
    "3": "┌",  # 51: down-right corner, diagonal tail dropped
    "4": "┐",  # 52: down-left corner, diagonal tail dropped
    "5": "┘",  # 53: up-left corner, diagonal tail dropped
    "6": "█",  # 54: solid block
    "7": "▀",  # 55: block, upper five-eighths
    "8": "▄",  # 56: block, lower five-eighths
    "9": "▌",  # 57: block, left five-eighths
    ":": "▐",  # 58: block, right five-eighths
    ";": "▄",  # 59: lower block, line up dropped
    "<": "▀",  # 60: upper block, line down dropped
    "=": "▌",  # 61: left block, line right dropped
    ">": "▐",  # 62: right block, line left dropped
    "?": "▝",  # 63: quadrant, upper right
    "@": "▗",  # 64: quadrant, lower right
    "A": "▖",  # 65: quadrant, lower left
    "B": "▘",  # 66: quadrant, upper left
    "C": "▝",  # 67: upper-right mass meeting a diagonal
    "D": "▗",  # 68: lower-right mass meeting a diagonal
    "E": "▖",  # 69: lower-left mass meeting a diagonal
    "F": "▘",  # 70: upper-left mass meeting a diagonal
    "G": "╱",  # 71: top-right road tip
    "H": "╲",  # 72: bottom-right road tip
    "I": "╱",  # 73: bottom-left road tip
    "J": "╲",  # 74: top-left road tip
    "K": "▔",  # 75: top edge stroke
    "L": "▁",  # 76: bottom edge stroke
    "M": "▏",  # 77: left edge stroke
    "N": "▕",  # 78: right edge stroke
    "O": "═",  # 79: gauge rails, empty
    "P": "▏",  # 80: gauge, one eighth full
    "Q": "▎",  # 81: gauge, two eighths
    "R": "▍",  # 82: gauge, three eighths
    "S": "▌",  # 83: gauge, four eighths
    "T": "▋",  # 84: gauge, five eighths
    "U": "▊",  # 85: gauge, six eighths
    "V": "▉",  # 86: gauge, seven eighths
    "W": "█",  # 87: gauge, full
    "X": "▕",  # 88: gauge, right rim
    "Y": "▏",  # 89: gauge, left rim
    "Z": "╳",  # 90: diagonal cross
    "[": "┼",  # 91: four-way join
    "\\": "↑",  # 92: up arrow
    "]": "↓",  # 93: down arrow
    "^": "↕",  # 94: up-down arrow
    "_": "□",  # 95: outlined box
    "`": "?",  # 96: a drawn question mark
    "a": "ᚪ",  # 97: rune ac
    "b": "ᛒ",  # 98: rune beorc
    "c": "ᛇ",  # 99: rune eoh, the eo of the §16 remarks
    "d": "ᛞ",  # 100: rune daeg
    "e": "ᛖ",  # 101: rune eh
    "f": "ᚠ",  # 102: rune feoh
    "g": "ᚷ",  # 103: rune gyfu
    "h": "ᚻ",  # 104: rune haegl
    "i": "ᛁ",  # 105: rune is
    "j": "ᛄ",  # 106: rune ger
    "k": "ᛣ",  # 107: rune calc, the "other k"
    "l": "ᛚ",  # 108: rune lagu
    "m": "ᛗ",  # 109: rune man
    "n": "ᚾ",  # 110: rune nyd
    "o": "ᚩ",  # 111: rune os
    "p": "ᛈ",  # 112: rune peorth
    "q": "ᚳ",  # 113: rune cen, the Anglian k
    "r": "ᚱ",  # 114: rune rad
    "s": "ᛋ",  # 115: rune sigel
    "t": "ᛏ",  # 116: rune tir
    "u": "ᚢ",  # 117: rune ur
    "v": "ᛠ",  # 118: rune ear
    "w": "ᚹ",  # 119: rune wynn
    "x": "ᛉ",  # 120: rune eolh, standing in for z
    "y": "ᚣ",  # 121: rune yr
    "z": "ᛟ",  # 122: rune ethel, standing in for oe
}

# Codes 123 to 126 are the reverse-video twins of the up arrow, the
# down arrow, the double arrow, and the question mark -- the §16
# bitmaps invert them pixel for pixel. Beyond Zork highlights its
# scrolling markers with them, so the painter draws the same shape
# and flips reverse video instead.
FONT_3_REVERSED = {
    "{": "↑",  # 123: up arrow, reversed
    "|": "↓",  # 124: down arrow, reversed
    "}": "↕",  # 125: up-down arrow, reversed
    "~": "?",  # 126: question mark, reversed
}


class Terminal(Protocol):
    """The sliver of a blessed Terminal the painter uses.

    Attributes:
        width: The terminal's width in characters, 0 when unknown.
        height: The terminal's height in lines, 0 when unknown.
        normal: The sequence restoring default style and colour.
        reverse: The sequence starting reverse video.
        bold: The sequence starting bold type.
        italic: The sequence starting italic type.
    """

    width: int
    height: int
    normal: str
    reverse: str
    bold: str
    italic: str

    def move_xy(self, x: int, y: int) -> str:
        """The sequence moving the cursor to (x, y), zero-based."""

    def color_rgb(self, red: int, green: int, blue: int) -> str:
        """The sequence starting an exact foreground colour."""

    def on_color_rgb(self, red: int, green: int, blue: int) -> str:
        """The sequence starting an exact background colour."""

    def cbreak(self) -> AbstractContextManager[object]:
        """A context in which keystrokes arrive raw, one at a time."""

    def inkey(self, timeout: float | None = None) -> object:
        """One keystroke: a str-like, with a .name for special keys.

        With a timeout in seconds, an empty str-like comes back
        when it expires with nothing typed.
        """


class ScreenFrontend:
    """A frontend that keeps a screen model and paints it live.

    Every Frontend operation updates the model first; the damaged
    rows are then redrawn in place. The capability flags tell the
    header the truth this frontend makes true: a status line, a
    splittable screen, and the §8.7.1 styles.
    """

    suspends = False
    has_status_line = True
    has_screen_splitting = True
    has_bold = True
    has_italic = True
    has_fixed_pitch = True
    has_timed_input = True
    # The §16 font paints as Unicode stand-ins -- box drawing,
    # blocks, arrows, runes -- so character graphics are honestly
    # on offer here (§8.1.5.1).
    has_character_graphics = True
    # The §8.3.1 codes 2 to 9 paint as the terminal's own eight
    # colours through COLOUR_NAMES, so the claim is honest (§8.3.3).
    has_colours = True
    # A terminal cell is the unit here, whatever its real pixel
    # size (§8.4.2) -- the sixel cell query is presentation, not
    # measurement, so the font stays 1 by 1.
    font_width = 1
    font_height = 1
    # No in-play pictures: the sixel cover is a doorway courtesy,
    # and the header's cleared bit keeps the claim honest (§11.1.4).
    has_pictures = False
    # No arc_image band either: the cleared bit keeps those games
    # honestly in text at the terminal (arc_image: the contract).
    has_arc_images = False
    # Terminal mouse reporting is a protocol of its own; until the
    # painter learns it, the request bit clears honestly
    # (§10.3.1.1).
    has_mouse = False
    # No stage: Version 6 windows keep the two-window mimicry a
    # cell terminal can honour.
    has_stage = False

    def __init__(
        self,
        version: int,
        terminal: Terminal | None = None,
        out: Callable[[str], None] | None = None,
        speaker: Speaker | None = None,
    ) -> None:
        """Wrap a terminal around a fresh screen model.

        Args:
            version: The story version whose §8 rules the model
                follows.
            terminal: The terminal to paint on; None builds a real
                blessed Terminal.
            out: Where escape sequences and text go; None writes to
                standard output.
            speaker: The audio device the sound seam plays
                through; None claims no sound, honestly.
        """

        if terminal is None:
            # Imported here so the module loads without the extra;
            # only building a real terminal needs blessed itself.
            import blessed  # noqa: PLC0415

            terminal = cast("Terminal", blessed.Terminal())

        self._terminal = terminal
        self._out = out if out is not None else _stdout_write
        self._speaker = speaker
        # The header hears the truth: sound is on offer exactly
        # when a speaker arrived to make it true (§9.1.2).
        self.has_sounds = speaker is not None
        # The machine's between-keystrokes attention, wired by the
        # session once a machine exists: called on each heartbeat
        # of an infinite wait. None waits the old blocking way.
        self.idle: Callable[[], None] | None = None
        # The size read here is a starting guess: a terminal slow
        # to answer -- iTerm2 mid-launch, a webview shell -- leaves
        # it at the fallback. _sync_terminal_size re-reads it before
        # the first paint and on every idle beat, reshaping the
        # model and, through on_resize, the §8.4 header when it
        # moves. Set by the machine; None leaves the header be.
        self.screen_columns = terminal.width or FALLBACK_COLUMNS
        self.screen_lines = terminal.height or FALLBACK_LINES
        self.on_resize: Callable[[], None] | None = None
        self._model = ScreenModel(
            columns=self.screen_columns, lines=self.screen_lines, version=version
        )
        self._model.more = self._pause
        self._editor = LineEditor()
        # Whether a timed read left a half-typed line composed: the
        # next line read resumes it instead of starting fresh.
        self._composing = False
        self._prompt = ""

    @property
    def model(self) -> ScreenModel:
        """The screen model this painter keeps faithful."""

        return self._model

    def write(self, text: str) -> None:
        """Print story text through the model, then repaint."""

        self._model.write(text)
        self._repaint()

    def write_rectangle(self, rows: Sequence[str]) -> None:
        """Print a §15 rectangle through the model, then repaint."""

        self._model.write_rectangle(rows)
        self._repaint()

    def show_status(self, status: Status) -> None:
        """Draw the Version 3 status line (§8.2)."""

        self._model.show_status(status)
        self._repaint()

    def set_style(self, style: int) -> None:
        """Change the style for text that follows (§8.7.1)."""

        self._model.set_style(style)

    def set_font(self, font: int) -> None:
        """Change the font for text that follows (§8.1.2)."""

        self._model.set_font(font)

    def set_colour(self, foreground: int, background: int) -> None:
        """Change the colours for text that follows (§8.3.1)."""

        self._model.set_colour(foreground, background)

    def erase_window(self, window: int) -> None:
        """Erase a window to background (§8.7.3.2)."""

        self._model.erase_window(window)
        self._repaint()

    def erase_line(self, pixels: int | None = None) -> None:  # noqa: ARG002
        """Erase from the cursor to the end of the line (§8.7.3.4).

        A pixel width never arrives here: only a Version 6 game
        sends one, and a Version 6 game plays on the glass.
        """

        self._model.erase_line()
        self._repaint()

    def begin_input(self) -> None:
        """Remember the prompt: the line's text left of the cursor."""

        row, column = self._model.cursor
        self._prompt = self._model.row_text(row)[: column - 1]

    def resume_input(self) -> None:
        """Show the prompt again after a printing interrupt.

        §15's remark: the interpreter should redisplay the input
        line when a timed read's interrupt has printed -- the
        prompt rewrites at wherever the interrupt's output left
        the cursor.
        """

        self._model.write(self._prompt)
        self._repaint()

    def split_window(self, lines: int) -> None:
        """Resize the upper window (§8.7.2.1)."""

        self._model.split_window(lines)
        self._repaint()

    def set_window(self, window: int) -> None:
        """Select the window taking the next printing (§8.7.2)."""

        self._model.set_window(window)
        self._repaint()

    def set_cursor(self, line: int, column: int) -> None:
        """Move the upper window's cursor (§8.7.2.3.1)."""

        self._model.set_cursor(line, column)
        self._repaint()

    def cursor_position(self) -> tuple[int, int]:
        """The model's own answer for get_cursor (§8.7.2.3.2)."""

        return self._model.get_cursor()

    def set_buffering(self, buffered: bool) -> None:
        """Turn lower-window word wrapping on or off (§15 buffer_mode)."""

        self._model.set_buffering(buffered)

    def picture_data(self, number: int) -> tuple[int, int] | None:  # noqa: ARG002
        """No picture has a size here: cells are not a canvas (§15).

        The sixel cover is a doorway courtesy, not an in-play
        picture system; the header's cleared bit says so.
        """

        return None

    def picture_census(self) -> tuple[int, int]:
        """A census of zero pictures, release zero (§15 picture_data)."""

        return 0, 0

    def draw_picture(self, number: int, line: int, column: int) -> None:
        """Draw nothing: this frontend claimed no pictures (§11.1.4)."""

    def erase_picture(self, number: int, line: int, column: int) -> None:
        """Erase nothing: this frontend claimed no pictures (§11.1.4)."""

    def draw_arc_image(self, image: int, mode: int) -> None:
        """Hang nothing: this frontend claimed no arc images."""

    def place_window(
        self, window: int, line: int, column: int, height: int, width: int
    ) -> None:
        """Place nothing: this frontend claimed no stage."""

    def scroll_window(self, window: int, pixels: int) -> None:
        """Scroll nothing: this frontend claimed no stage."""

    def set_margins(self, window: int, left: int, right: int) -> None:
        """Set nothing: this frontend claimed no stage."""

    def set_line_count(self, window: int, count: int) -> None:
        """Count nothing: this frontend claimed no stage."""

    def bleep(self, number: int) -> None:  # noqa: ARG002
        """Ring the terminal bell: one bell serves both bleeps (§9)."""

        self._out("\a")

    def play_sound(self, number: int, volume: int, repeats: int | None) -> bool:
        """Hand a sampled sound to the speaker (§9.4)."""

        return self._speaker is not None and self._speaker.play(number, volume, repeats)

    def stop_sound(self, number: int | None) -> None:
        """Stop a sound, or all of them when None (§9.4)."""

        if self._speaker is not None:
            self._speaker.stop(number)

    def sound_playing(self) -> bool:
        """Whether the speaker is still sounding (§9 remarks)."""

        return self._speaker is not None and self._speaker.playing()

    def sound_finished(self) -> bool:
        """Whether a sound just ended naturally (§9.4.4)."""

        return self._speaker is not None and self._speaker.finished()

    def wait_for_sound(self) -> None:
        """Let the playing sound finish a cycle (§9 remarks)."""

        if self._speaker is not None:
            self._speaker.wait()

    def _translated_key(self, timeout: float | None) -> str | None:
        """One terminal read, translated; None for nothing usable.

        Named special keys become their §3.8.2.2 and §3.8.4 input
        characters; unnamed single characters pass through as
        themselves. An expired timeout and an unmapped escape
        sequence are both nothing usable.
        """

        with self._terminal.cbreak():
            key = self._terminal.inkey(timeout)

        name = getattr(key, "name", None)

        if name in KEY_CHARACTERS:
            return KEY_CHARACTERS[name]

        character = str(key)

        if len(character) == 1:
            return character

        return None

    def _waited_key(self) -> str | None:
        """One read of an infinite wait, attentive while it lasts.

        Without an idle callback this is a plain blocking read.
        With one, the wait is chopped into heartbeats: each expiry
        lets the terminal be re-measured -- a window resized while
        the player thinks at a prompt redraws within the beat --
        and the machine attend to background work, an ended sound's
        routine (§9.4.4), before listening again. One heartbeat's
        answer comes back as it is; None still means "nothing
        usable yet", and every caller already waits that out.
        """

        if self.idle is None:
            return self._translated_key(None)

        key = self._translated_key(IDLE_HEARTBEAT)

        if key is None:
            if self._sync_terminal_size():
                self._repaint()

            self.idle()

        return key

    def read_key(self, timeout: float | None = None) -> str | None:
        """Read one raw keystroke at the model's cursor.

        Keystrokes are not echoed -- §15 read_char leaves any
        echoing to the game. Without a timeout, empty and
        unhearable reads simply wait for a real keystroke; with
        one, an expired wait answers None, which is the machine's
        cue to fire a §15 interrupt on the wall clock -- so a timed
        read keeps its own clock, and only the infinite wait is
        chopped into attentive heartbeats.
        """

        self._model.rest()
        self._park()

        while True:
            key = (
                self._waited_key() if timeout is None else self._translated_key(timeout)
            )

            if key is not None:
                return key

            if timeout is not None:
                return None

    def read_line(self) -> str:
        """Read one line of raw typing, edited and echoed via the model.

        The terminal's own echo is never invited: keystrokes arrive
        raw through the same seam read_char uses, and every visible
        change to the glass is the painter's doing -- so a prompt
        on the bottom row can never make the real terminal scroll
        the screen behind the model's back. The line editor gives
        the classic vocabulary: backspace rubs out, the left and
        right cursor keys move within the line, and up and down
        walk the session's command history.
        """

        self._model.rest()
        self._park()

        fresh = not self._composing
        self._composing = False
        line = read_line_edited(
            self._editor, self._model, self._waited_key, self._repaint, fresh=fresh
        )

        # The untimed key source never expires, so the line is real.
        return cast("str", line)

    def read_line_until(self, seconds: float) -> str | None:
        """Read a line on the clock, or None when the wait expires.

        The live half of a §15 timed read: the machine calls with
        the read's interval, runs the game's interrupt on None, and
        calls again -- and the half-typed line survives between
        calls, composed in the editor and standing on the glass.
        Border Zone's whole real-time engine rides on these ticks.
        """

        self._model.rest()
        self._park()

        deadline = monotonic() + seconds

        def ticking_key() -> str | None:
            remaining = deadline - monotonic()

            if remaining <= 0:
                return EXPIRED

            wait = (
                min(remaining, IDLE_HEARTBEAT) if self.idle is not None else remaining
            )
            key = self._translated_key(wait)

            if key is None and self.idle is not None:
                if self._sync_terminal_size():
                    self._repaint()

                self.idle()

            return key

        fresh = not self._composing
        line = read_line_edited(
            self._editor, self._model, ticking_key, self._repaint, fresh=fresh
        )
        self._composing = line is None

        return line

    def click_position(self) -> tuple[int, int] | None:
        """No clicks arrive until the painter learns mouse reporting."""

        return None

    def abandon_input(self) -> None:
        """Erase the half-typed line a terminated timed read leaves.

        §15 read: a true-returning interrupt ends the read with all
        input erased -- so the composed line comes off the glass,
        rubbed out from the editor's own accounting, and the next
        read starts fresh.
        """

        if not self._composing:
            return

        pending = len(self._editor.text)
        self._model.retreat(self._editor.cursor)
        self._model.write(" " * pending)
        self._model.retreat(pending)
        self._editor.begin()
        self._composing = False
        self._repaint()

    def _answered(self, query: str, end: str) -> str:
        """Ask the terminal a question and collect its escape answer.

        The answer arrives back through the keyboard, gathered a
        keystroke at a time until its final character. A terminal
        that stays quiet past the patience window answers nothing,
        and a partial answer is discarded rather than believed.
        """

        self._out(query)

        pieces: list[str] = []

        with self._terminal.cbreak():
            while True:
                piece = str(self._terminal.inkey(QUERY_PATIENCE))

                if not piece:
                    return ""

                pieces.append(piece)

                if piece.endswith(end):
                    return "".join(pieces)

    def _sixel_capable(self) -> bool:
        """Whether the terminal declares sixel among its attributes.

        Detection is a safety net, not a gate: a --pixels request
        on a terminal that never learned sixel falls back to the
        half-block painting instead of spraying escape garbage
        across the glass.
        """

        answer = self._answered(DEVICE_ATTRIBUTES_QUERY, DEVICE_ATTRIBUTES_END)
        start = answer.find("?")

        if start < 0:
            return False

        return SIXEL_ATTRIBUTE in answer[start + 1 : -1].split(";")

    def _cell_size(self) -> tuple[int, int]:
        """One character cell's pixel width and height.

        The terminal's own report replaces the conservative floors
        when it answers, so a cover magnifies to the glass as it
        actually measures; a quiet or garbled answer keeps the
        floors.
        """

        answer = self._answered(CELL_SIZE_QUERY, CELL_SIZE_END)
        parts = answer.removeprefix("\x1b[").removesuffix(CELL_SIZE_END).split(";")

        if (
            len(parts) == CELL_SIZE_FIELDS
            and parts[0] == CELL_SIZE_REPORT
            and parts[1].isdigit()
            and parts[2].isdigit()
            and int(parts[1]) > 0
            and int(parts[2]) > 0
        ):
            return int(parts[2]), int(parts[1])

        return CELL_WIDTH_FLOOR, CELL_HEIGHT_FLOOR

    def show_frontispiece(self, picture: Picture, *, pixels: bool = False) -> None:
        """Show a cover picture until a key is pressed, then clear.

        By default the picture is scaled to fit the glass and
        painted centred in half-block cells: each ▀ carries two
        pixels, its foreground the upper and its background the
        lower, so any terminal with exact colours can show a
        picture at twice its row resolution. With pixels requested,
        the terminal is asked first: one that declares sixel draws
        the picture as real pixels, magnified to the glass's own
        measured cell size, and one that does not gets the
        half-block painting -- never garbage. Infocom's own
        interpreters opened this way -- cover art, a keypress, and
        the story. Afterwards the blank model is repainted whole,
        leaving the game a clean screen no splash pixel survives
        on.
        """

        if pixels and self._sixel_capable():
            self.clear()

            cell_width, cell_height = self._cell_size()
            scale = _pixel_scale(
                picture,
                self.screen_columns * cell_width,
                self.screen_lines * cell_height,
            )
            width_cells = picture.width * scale // cell_width
            left = max(0, (self.screen_columns - width_cells) // 2)

            self._out(self._terminal.move_xy(left, 0) + sixel_encode(picture, scale))
            self.read_key()
            self.clear()

            return

        pixels_grid = _fitted(picture, self.screen_columns, self.screen_lines * 2)
        left = (self.screen_columns - len(pixels_grid[0])) // 2
        top = (self.screen_lines - (len(pixels_grid) + 1) // 2) // 2

        self.clear()

        for index in range(0, len(pixels_grid), 2):
            upper = pixels_grid[index]
            lower = pixels_grid[index + 1] if index + 1 < len(pixels_grid) else None
            pieces = [self._terminal.move_xy(left, top + index // 2)]

            for column, (red, green, blue) in enumerate(upper):
                below = lower[column] if lower is not None else (0, 0, 0)
                pieces.append(self._terminal.color_rgb(red, green, blue))
                pieces.append(self._terminal.on_color_rgb(*below))
                pieces.append("▀")

            pieces.append(self._terminal.normal)
            self._out("".join(pieces))

        self.read_key()
        self.clear()

    def clear(self) -> None:
        """Paint the model's every row over the glass.

        At the start of a session the model is blank, so this
        wipes whatever the shell left on the terminal: the story
        begins on a clean screen instead of shingling its rows
        between old output. The cover flow uses it on both sides
        of the picture for the same reason.
        """

        self._sync_terminal_size()

        for row in range(1, self._model.lines + 1):
            self._paint_row(row)

    def _sync_terminal_size(self) -> bool:
        """Match the model to the terminal's current size (§8.4).

        A dimension the terminal reports as 0 is one it is not
        answering yet, so it is left as it stands rather than
        snapped to a guess. Returns whether anything moved.
        """

        columns = self._terminal.width or self.screen_columns
        lines = self._terminal.height or self.screen_lines

        if columns == self.screen_columns and lines == self.screen_lines:
            return False

        self.screen_columns = columns
        self.screen_lines = lines
        self._model.resize(columns, lines)

        if self.on_resize is not None:
            self.on_resize()

        return True

    def _repaint(self) -> None:
        """Redraw every damaged row, then park the cursor."""

        self._sync_terminal_size()

        for row in self._model.sweep():
            self._paint_row(row)

        self._park()

    def _paint_row(self, row: int) -> None:
        """Redraw one row from the model's cells."""

        pieces = [self._terminal.move_xy(0, row - 1)]
        dress = None

        for column in range(1, self._model.columns + 1):
            cell = self._model.cell(row, column)
            character, style = self._appearance(cell)
            wanted = (style, cell.foreground, cell.background)

            if wanted != dress:
                pieces.append(self._sequences(style, cell))
                dress = wanted

            pieces.append(character)

        pieces.append(self._terminal.normal)
        self._out("".join(pieces))

    def _appearance(self, cell: Cell) -> tuple[str, int]:
        """The character and style one cell paints as (§16).

        Cells in the character graphics font translate to their
        Unicode stand-ins; the four reverse-video shapes flip
        reverse instead of carrying it in the glyph. Every other
        font paints its characters as they are.
        """

        if cell.font != GRAPHICS_FONT:
            style = cell.style

            # A space has no glyph to embolden, but a terminal
            # brightens a bold-reverse blank anyway -- so a status
            # bar padded with bold spaces (Border Zone's) paints as
            # a patchwork of greys. Blanks shed bold before
            # painting, as the reference interpreters render them.
            if cell.character == " ":
                style &= ~BOLD

            return cell.character, style

        if cell.character in FONT_3_REVERSED:
            return FONT_3_REVERSED[cell.character], cell.style ^ REVERSE

        return FONT_3_CHARACTERS.get(cell.character, cell.character), cell.style

    def _sequences(self, style: int, cell: Cell) -> str:
        """The sequences dressing one cell, in its painted style."""

        pieces = [self._terminal.normal]

        if style & REVERSE:
            pieces.append(self._terminal.reverse)

        if style & BOLD:
            pieces.append(self._terminal.bold)

        if style & ITALIC:
            pieces.append(self._terminal.italic)

        if cell.foreground in COLOUR_NAMES:
            pieces.append(str(getattr(self._terminal, COLOUR_NAMES[cell.foreground])))

        if cell.background in COLOUR_NAMES:
            pieces.append(
                str(getattr(self._terminal, "on_" + COLOUR_NAMES[cell.background]))
            )

        return "".join(pieces)

    def _park(self) -> None:
        """Put the terminal cursor where the model's cursor stands."""

        row, column = self._model.cursor
        self._out(self._terminal.move_xy(column - 1, row - 1))

    def _pause(self) -> None:
        """Hold a screenful behind [MORE] until any key arrives.

        The model calls this mid-write, so the damage it has piled
        up paints first -- the player must see what they are being
        asked to read. The prompt is a reverse-video overlay at the
        cursor; the keypress is spent on the pause, and repainting
        the row from the model erases the prompt without a trace.
        """

        for damaged in self._model.sweep():
            self._paint_row(damaged)

        row, column = self._model.cursor
        column = min(column, max(self._model.columns - len(MORE_PROMPT) + 1, 1))
        self._out(
            self._terminal.move_xy(column - 1, row - 1)
            + self._terminal.normal
            + self._terminal.reverse
            + MORE_PROMPT
            + self._terminal.normal
        )

        # A heartbeat expiry answers None so background work can
        # run; only a real key ends the pause.
        while self._waited_key() is None:
            pass

        self._paint_row(row)
        self._park()


def _pixel_scale(picture: Picture, width_pixels: int, height_pixels: int) -> int:
    """The whole-number magnification a sixel cover certainly fits.

    The bounds are the glass's pixel dimensions: the queried cell
    size times the cells when the terminal answered, or the
    conservative floors when it kept quiet. A picture too large
    even unmagnified draws at native size and lets the terminal
    clip its edge.
    """

    width_bound = width_pixels // picture.width
    height_bound = height_pixels // picture.height

    return max(1, min(width_bound, height_bound))


def _fitted(
    picture: Picture, columns: int, rows: int
) -> list[list[tuple[int, int, int]]]:
    """Scale a picture onto a pixel canvas, averaging boxes.

    The canvas is the glass in half-block pixels: the screen's
    columns wide, twice its lines tall. A picture larger than the
    canvas shrinks to fit, keeping its shape; a smaller one stays
    its own size.
    """

    scale = min(columns / picture.width, rows / picture.height, 1.0)
    width = max(1, int(picture.width * scale))
    height = max(1, int(picture.height * scale))
    fitted = []

    for target_row in range(height):
        row_first = target_row * picture.height // height
        row_last = max(row_first + 1, (target_row + 1) * picture.height // height)
        row = []

        for target_column in range(width):
            first = target_column * picture.width // width
            last = max(first + 1, (target_column + 1) * picture.width // width)
            red = 0
            green = 0
            blue = 0
            count = 0

            for source_row in range(row_first, row_last):
                for source_column in range(first, last):
                    pixel = picture.rows[source_row][source_column]
                    red += pixel[0]
                    green += pixel[1]
                    blue += pixel[2]
                    count += 1

            row.append((red // count, green // count, blue // count))

        fitted.append(row)

    return fitted


def _stdout_write(text: str) -> None:
    """Write straight through to the terminal, unbuffered."""

    sys.stdout.write(text)
    sys.stdout.flush()
