"""How a running story presents itself to the player (§8).

The Z-Machine defines a screen model but leaves its realization to
the interpreter: each interpreter shows what it can, declares as much
in the header, and games adapt to those declarations (§11.1). A
Frontend is Voxam's seam for that variability -- the machine speaks
in semantic operations, and each frontend renders the ones it
honestly claimed.
"""

import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol

# The screen model's two windows: the scrolling lower window where
# the story unfolds, and the fixed upper window games draw into
# (§8.7.2). erase_window's -1 both unsplits the screen and reselects
# the lower window.
LOWER_WINDOW = 0
UPPER_WINDOW = 1
UNSPLIT_AND_CLEAR = -1

# Games put two very different things in the upper window: one- or
# two-line status bars redrawn every turn, and tall splits holding
# real content -- title cards, quotations, maps. A stream should
# mute the first and show the second, and the split height is the
# tell (Trinity's status bar is 1 line; its title card is 14).
STATUS_CHROME_LINES = 2

# The §8.1.2 font IDs: the normal font, a picture font no
# interpreter should implement (§8.1.4), the §16 character graphics
# font Beyond Zork draws its maps in, and a fixed-pitch Courier.
# Selecting font 0 changes nothing and asks which font is current.
NORMAL_FONT = 1
PICTURE_FONT = 2
GRAPHICS_FONT = 3
COURIER_FONT = 4
CURRENT_FONT = 0


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
        has_sounds: Whether sampled sound effects can actually
            play (§9).
        has_character_graphics: Whether the §16 character graphics
            font can be drawn (§8.1.5.1).
        has_colours: Whether coloured text can be shown (§8.3).
        has_mouse: Whether mouse clicks can arrive as input codes
            (§10.3) -- true only at a windowed glass.
        has_pictures: Whether pictures can actually be drawn
            (§11.1.4) -- true only where a gallery of art hangs
            behind a glass with pixels.
        has_stage: Whether a Version 6 session plays on a §8.8
            stage of eight placeable windows. When true, the
            machine forwards window geometry and cursor moves;
            when false, it keeps the character frontends' flowing
            mimicry -- the behaviour every recording replays in.
        screen_lines: The screen height in lines; 255 means
            "infinite", the claim of a stream that never pages
            (§8.4).
        screen_columns: The screen width in characters (§8.4).
        font_width: The width of one character cell in the units
            the header speaks -- 1 on a character glass, whose
            unit is a character, and real pixels on a glass that
            measures (§8.4.2). Only Version 6 stories ever hear
            a value other than 1: the machine keeps every other
            version's unit at one character, because games like
            Beyond Zork mix unit arithmetic with character-cell
            cursor moves and the two scales must agree.
        font_height: The height of one character cell in units.
    """

    has_status_line: bool
    has_screen_splitting: bool
    has_bold: bool
    has_italic: bool
    has_fixed_pitch: bool
    has_timed_input: bool
    has_sounds: bool
    has_character_graphics: bool
    has_colours: bool
    has_pictures: bool
    has_mouse: bool
    has_stage: bool
    screen_lines: int
    screen_columns: int
    font_width: int
    font_height: int

    def write(self, text: str) -> None:
        """Show story text from the print stream."""

    def write_rectangle(self, rows: Sequence[str]) -> None:
        """Print a rectangle of text, right and down from the cursor.

        The shape of §15 print_table: each row after the first
        begins one line down, at the column where the rectangle
        began -- how Beyond Zork stamps its map beside the story.
        A frontend without a cursor renders the rows as lines.
        """

    def show_status(self, status: Status) -> None:
        """Present a freshly assembled status line (§8.2)."""

    def set_style(self, style: int) -> None:
        """Change the type style for text that follows (§8.7).

        The style is a bitmask: 0 returns to roman, 1 is reverse
        video, 2 boldface, 4 italic, 8 fixed pitch.
        """

    def set_font(self, font: int) -> None:
        """Change the typeface for text that follows (§8.1.2).

        Only fonts the machine granted arrive here: the normal
        font 1, the fixed-pitch font 4, and -- where character
        graphics were claimed -- the §16 font 3.
        """

    def set_colour(self, foreground: int, background: int) -> None:
        """Change the printing colours for text that follows (§8.3.1).

        The codes are §8.3.1's: 0 keeps a colour current, 1 is the
        interpreter's default, and 2 to 9 name the colours. Only
        frontends that claimed colours receive the change.
        """

    def erase_window(self, window: int) -> None:
        """Erase a window to its background (§8.7).

        Window -1 unsplits the screen and clears it all; -2 clears
        the whole screen without unsplitting; 0 and up name a single
        window.
        """

    def erase_line(self, pixels: int | None = None) -> None:
        """Erase rightward from the cursor (§8.8.5.2).

        To the end of the line by default; a Version 6 game may
        instead give a width in pixels, clipped to stay inside the
        right margin.
        """

    def begin_input(self) -> None:
        """A timed line read is starting: remember the prompt.

        If the read's interrupt routine prints, the input line must
        be shown again afterwards (§15 read remarks), and the
        prompt as it stood is what there is to show.
        """

    def resume_input(self) -> None:
        """A timed read's interrupt printed; show the prompt again.

        The §15 remark: the interpreter should redisplay the input
        line after an interrupt routine that printed -- Jigsaw's
        chapter epigraphs arrive exactly this way, and without the
        redisplay the prompt strands above the quotation.
        """

    def abandon_input(self) -> None:
        """A timed read's interrupt terminated it: erase the input.

        §15 read: when the interrupt routine returns true, the read
        ends with all input erased -- off the glass as well as out
        of the buffers, so the half-typed line does not linger
        beside whatever the routine printed.
        """

    def click_position(self) -> tuple[int, int] | None:
        """Where the last mouse click landed, as (x, y) in units.

        The machine writes these into header extension words 1 and
        2 before delivering a click's input code (§10.3.2). None
        means no click has happened -- every frontend without a
        mouse, always.
        """

    def set_buffering(self, buffered: bool) -> None:
        """Turn word-wrap buffering on or off (§8.7)."""

    def split_window(self, lines: int) -> None:
        """Give the upper window this many lines; 0 unsplits (§8.7.2)."""

    def set_window(self, window: int) -> None:
        """Select the window that receives text (§8.7.2)."""

    def set_cursor(self, line: int, column: int) -> None:
        """Move the upper window's cursor (§8.7.2).

        On a stage, the selected window's cursor instead, in
        window-relative units (§8.8.3.5).
        """

    def place_window(
        self, window: int, line: int, column: int, height: int, width: int
    ) -> None:
        """Place a §8.8 window at a position and size, in units.

        Only frontends that claimed a stage hear the call; the
        rest render windows 0 and 1 as they always have.
        """

    def scroll_window(self, window: int, pixels: int) -> None:
        """Scroll a §8.8 window's own rectangle, in units (§15).

        Positive scrolls up, negative down. Only frontends that
        claimed a stage hear the call.
        """

    def set_margins(self, window: int, left: int, right: int) -> None:
        """Set a §8.8 window's margin sizes, in units (§8.8.3.2.1).

        Only frontends that claimed a stage hear the call.
        """

    def set_line_count(self, window: int, count: int) -> None:
        """Set a §8.8 window's [MORE] line count (§8.8.3.2.6).

        Games manipulate it freely, and -999 means never print
        [MORE]. Only frontends that claimed a stage hear the call.
        """

    def cursor_position(self) -> tuple[int, int]:
        """The cursor's row and column (§8.7.2.3.2).

        The upper window's cursor -- the one set_cursor can move
        -- which is what get_cursor reads back.
        """

    def picture_data(self, number: int) -> tuple[int, int] | None:
        """A picture's height and width in pixels, None for none.

        The order is picture_data's own: height first (§15). None
        is the answer for every number on a frontend that hangs
        no pictures.
        """

    def picture_census(self) -> tuple[int, int]:
        """How many pictures hang, and the art's release number.

        The picture_data number-0 census (§15): (0, 0) on a
        frontend without pictures.
        """

    def draw_picture(self, number: int, line: int, column: int) -> None:
        """Draw a picture, top left at a screen units position (§15).

        Only frontends that claimed pictures hear the call, with
        the cursor defaults and window origin already resolved.
        """

    def erase_picture(self, number: int, line: int, column: int) -> None:
        """Paint a picture's region to the background colour (§15).

        Only frontends that claimed pictures hear the call.
        """

    def bleep(self, number: int) -> None:
        """Sound a bleep: 1 is high, 2 is low (§9)."""

    def play_sound(self, number: int, volume: int, repeats: int | None) -> bool:
        """Start a sampled sound in the background (§9.4).

        The volume runs 1 to 8 (§9.3). Repeats count total plays,
        0 repeating until stopped (§9.4.3); None plays as the
        resource file's Loop chunk says -- the Version 3 case,
        where the opcode cannot say. Only frontends that claimed
        sound receive the call. Answers whether a sound actually
        started -- False for a number no resource holds, which
        decides if an end-of-sound routine is worth keeping.
        """

    def stop_sound(self, number: int | None) -> None:
        """Stop a sampled sound, or all of them when None (§9.4)."""

    def sound_playing(self) -> bool:
        """Whether a sampled sound is still sounding (§9 remarks)."""

    def sound_finished(self) -> bool:
        """Whether a sound just ended of its own accord (§9.4.4).

        True once per natural ending; a stopped or replaced sound
        never reports, so its end-of-sound routine never runs.
        """

    def wait_for_sound(self) -> None:
        """Block until the playing sound finishes a cycle.

        The §9 remarks' pacing rule for The Lurking Horror, which
        fires several sounds in one game round and assumes an
        interpreter as slow as Infocom's Amiga one.
        """


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
    # Timed input is real, if virtual: the machine fires read
    # interrupts on the patient typist's deterministic clock rather
    # than a wall clock, which is what seeded replay can honestly
    # offer (§15 read).
    has_timed_input = True
    # Sampled sounds live behind the painted frontend's speaker; a
    # transcript stream plays nothing and says so -- which is what
    # keeps recorded sessions deterministic (§9).
    has_sounds = False
    # Font 3's shapes would print as their Latin stand-ins here --
    # a map drawn in gibberish letters -- so the stream refuses the
    # font and games draw with plainer characters instead (§8.1.5.1).
    has_character_graphics = False
    # A transcript prints in ink it does not choose; the header says
    # so, and colour requests legally pass unanswered (§8.3.2).
    has_colours = False
    # A stream has no pixels to hang art on; the cleared header bit
    # says so, and picture_data answers with the census of an
    # interpreter that has none (§11.1.4, §15).
    has_pictures = False
    # No mouse can click a stream, and the request bit clears to
    # say so (§10.3.1.1).
    has_mouse = False
    # No stage either: Version 6 windows flow as text here, the
    # mimicry every recording replays in.
    has_stage = False
    screen_lines = 255
    screen_columns = 80
    # A stream measures in characters: one unit is one character,
    # so the font is 1 by 1 (§8.4.2).
    font_width = 1
    font_height = 1

    def __init__(self, write: Callable[[str], None] | None = None) -> None:
        """Bind the text stream, standard output when not given."""

        self._write = write if write is not None else sys.stdout.write
        self._window = LOWER_WINDOW
        self._split = 0
        self._upper_row = 1
        self._upper_column = 1

    def write(self, text: str) -> None:
        """Pass story text through to the stream, muting chrome.

        Lower-window text always flows. Upper-window text flows only
        when the split is tall enough to hold content -- a title
        card, a quotation -- and is muted when it is a one- or
        two-line status bar redrawn every turn. That distinction is
        what keeps a transcript the story and nothing else, without
        losing the parts of the story games put up top.
        """

        if self._window == LOWER_WINDOW:
            self._write(text)
        elif self._upper_holds_content():
            self._write(text)
            self._upper_column += len(text)

    def write_rectangle(self, rows: Sequence[str]) -> None:
        """Render the §15 rectangle as stacked lines.

        A stream has no cursor column to return to, so the rows
        become ordinary lines through the same muting rules as any
        other text -- exactly the transcript §15's remark expects
        of a plain screen model.
        """

        for index, row in enumerate(rows):
            if index:
                self.write("\n")

            self.write(row)

    def show_status(self, status: Status) -> None:
        """Drop the status: a plain stream has no line to keep it on."""

    def set_style(self, style: int) -> None:
        """Drop the style: none were claimed, and §8.7 permits that.

        The header declared no boldface and no italic, so a game
        asking for them is asking politely for something it was told
        does not exist.
        """

    def set_font(self, font: int) -> None:
        """Drop the change: fonts 1 and 4 are both this one stream.

        Character graphics were refused in the header, so only the
        normal and fixed-pitch fonts ever arrive -- and a plain
        stream is already fixed-pitch (§8.1).
        """

    def set_colour(self, foreground: int, background: int) -> None:
        """Drop the colours: none were claimed, and §8.3.2 permits that.

        The machine only forwards colours a frontend claimed, so
        nothing arrives here; the method stands for the protocol's
        sake.
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
            self._split = 0

    def erase_line(self, pixels: int | None = None) -> None:
        """Drop the erasure: a stream has no line to blank."""

    def begin_input(self) -> None:
        """Drop the notice: a stream shows input by echoing it.

        The typed line prints after any interrupt output anyway,
        so the transcript already reads in order -- and recordings
        must stay byte-identical, so the stream adds nothing.
        """

    def resume_input(self) -> None:
        """Drop the redisplay, for the same reason as the notice."""

    def abandon_input(self) -> None:
        """Drop the erasure: the stream never echoed a pending line."""

    def click_position(self) -> tuple[int, int] | None:
        """No mouse ever clicks a stream (§10.3)."""

        return None

    def set_buffering(self, buffered: bool) -> None:
        """Drop the toggle: an unwrapped stream needs no buffering."""

    def split_window(self, lines: int) -> None:
        """Remember the split height: it is the chrome-or-content tell."""

        self._split = lines

    def set_window(self, window: int) -> None:
        """Remember the selection, which is what routes write().

        Leaving a content-bearing upper window ends its last line,
        so upper text and the story never share one.
        """

        if (
            window == LOWER_WINDOW
            and self._window == UPPER_WINDOW
            and self._upper_holds_content()
        ):
            self._write("\n")

        self._window = window
        self._upper_row = 1
        self._upper_column = 1

    def set_cursor(self, line: int, column: int) -> None:
        """Reconstruct content-window layout in stream form.

        A row change becomes a new-line and a column beyond the pen
        becomes padding, which is how a centered title card stays
        centered in a transcript. Cursor moves in a status bar are
        dropped with the rest of the chrome.
        """

        if self._window != UPPER_WINDOW or not self._upper_holds_content():
            return

        if line != self._upper_row:
            self._write("\n")
            self._upper_row = line
            self._upper_column = 1

        if column > self._upper_column:
            self._write(" " * (column - self._upper_column))
            self._upper_column = column

    def cursor_position(self) -> tuple[int, int]:
        """The stream's upper-window bookkeeping, read back (§8.7.2.3.2).

        A stream has no real cursor, but it tracks where the upper
        window's pen would be to reconstruct layout; get_cursor
        reads the same ledger.
        """

        return (self._upper_row, self._upper_column)

    def _upper_holds_content(self) -> bool:
        """Whether the upper window is tall enough to be content."""

        return self._split > STATUS_CHROME_LINES

    def picture_data(self, number: int) -> tuple[int, int] | None:  # noqa: ARG002
        """No picture has a size here: a stream hangs none (§15)."""

        return None

    def picture_census(self) -> tuple[int, int]:
        """A census of zero pictures, release zero (§15 picture_data)."""

        return 0, 0

    def draw_picture(self, number: int, line: int, column: int) -> None:
        """Draw nothing: this frontend claimed no pictures (§11.1.4).

        The machine never sends a picture here -- has_pictures is
        False -- and a stray call changes nothing.
        """

    def erase_picture(self, number: int, line: int, column: int) -> None:
        """Erase nothing: this frontend claimed no pictures (§11.1.4)."""

    def place_window(
        self, window: int, line: int, column: int, height: int, width: int
    ) -> None:
        """Place nothing: this frontend claimed no stage.

        The machine never sends geometry here -- has_stage is
        False -- and a stray call changes nothing.
        """

    def scroll_window(self, window: int, pixels: int) -> None:
        """Scroll nothing: this frontend claimed no stage."""

    def set_margins(self, window: int, left: int, right: int) -> None:
        """Set nothing: this frontend claimed no stage."""

    def set_line_count(self, window: int, count: int) -> None:
        """Count nothing: this frontend claimed no stage."""

    def bleep(self, number: int) -> None:
        """Drop the bleep: a transcript is quieter than a terminal.

        A BEL character could ring a real bell here, but it would
        also embed control characters in every recorded session; the
        blessed frontend is where sound belongs.
        """

    def play_sound(self, number: int, volume: int, repeats: int | None) -> bool:
        """Play nothing: this frontend claimed no sound (§9).

        The machine never sends a sound here -- has_sounds is
        False -- and a stray call changes nothing, which is the
        silence every recording replays in.
        """

        del number, volume, repeats

        return False

    def stop_sound(self, number: int | None) -> None:
        """Stop nothing: nothing ever played."""

    def sound_playing(self) -> bool:
        """No sound is ever sounding here."""

        return False

    def sound_finished(self) -> bool:
        """No sound ever ends here, naturally or otherwise."""

        return False

    def wait_for_sound(self) -> None:
        """Return at once: there is never a cycle to wait out."""
