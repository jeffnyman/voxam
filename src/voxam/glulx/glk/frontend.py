"""What Glk needs from a display.

The contract is deliberately narrow. Windows keep their own
contents, so a display renders the tree on flush and is asked for
input synchronously -- enough for a terminal, and the arrangement
cheapglk and glkterm use. A display that cannot block, one speaking
the GlkOte protocol, would need glk_select to suspend rather than
call read_line; that is a change to this contract and to the api,
not to the VM, which is single-steppable for exactly that reason.

Every capability defaults to "cannot": a display claims what it
can do by flipping a flag and overriding the methods behind it,
and the gestalt answers follow the flags, so a game never asks for
what the display never promised.
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from voxam.errors import GlulxSessionEnd
from voxam.glulx.glk.objects import (
    CHARACTER_CELL,
    Event,
    Metrics,
    SoundChannel,
    Window,
)
from voxam.glulx.glk.resources import ImageInfo

if TYPE_CHECKING:
    from voxam.glulx.glk.api import Glk


class Frontend(ABC):
    """A display Glk can render into and read from.

    Attributes:
        glk: The library, once attach has been called.
        timer_input: Whether timer events can fire here (Glk:
            Timer Events).
        mouse_input: Whether the player can click in a grid or
            graphics window (Glk: Mouse Input Events).
        hyperlink_input: Whether the player can select a hyperlink
            (Glk: Accepting Hyperlink Events). Writing link values
            works everywhere regardless -- that is the separate
            Hyperlinks selector.
        graphics: Whether images and rectangles can be drawn
            (Glk: Graphics).
        sound: Whether sound resources can be played (Glk: Sound).
        echoes_input: Whether typed input is already visible
            without Glk reprinting it. A terminal echoes as the
            player types, so Glk echoing the line into the window
            as well would show it twice; a display that draws
            everything itself leaves this False and lets Glk echo.
        metrics: The size of one character cell in the units size
            reports. A terminal measures in characters already, so
            the default 1x1 makes every conversion a no-op; a
            graphical display measures in pixels and answers its
            font's cell.
    """

    glk: "Glk | None" = None
    timer_input: bool = False
    mouse_input: bool = False
    hyperlink_input: bool = False
    graphics: bool = False
    sound: bool = False
    echoes_input: bool = False
    metrics: Metrics = CHARACTER_CELL

    def metrics_for(self, window: Window) -> Metrics:
        """The metrics for one window; by default, the same for all.

        A display may spend different amounts on different window
        types -- GlkOte measures a grid's padding separately from a
        buffer's -- so the tree asks per window rather than once. A
        display with one answer need not override this.
        """

        del window

        return self.metrics

    def attach(self, glk: "Glk") -> None:
        """Note the library this display belongs to.

        Needed by any display that raises events of its own: a
        timer coming round, a sound finishing, a window resized.
        """

        self.glk = glk

    def post(self, event: Event) -> None:
        """Queue an event the display raised, for the next select.

        A blocking display has no other way to report something
        that is not the input it was asked for. It returns None
        from the input call as well, so that glk_select comes back
        round and finds what was queued here.
        """

        if self.glk is not None:
            self.glk.post_event(event)

    @abstractmethod
    def size(self) -> tuple[int, int]:
        """The whole display as (width, height), in display units.

        A terminal's unit is the character cell; a graphical
        display's is the pixel. The metrics say which, by giving
        the size of one cell in those units.
        """

    @abstractmethod
    def flush(self, root: Window | None) -> None:
        """Render the window tree. Called before every input ask."""

    @abstractmethod
    def read_line(self, window: Window, maxlen: int) -> tuple[str, int] | None:
        """Read a line; return (text, terminator).

        The terminator is 0 for an ordinary Return, or the keycode
        of whichever terminator key ended the line (Glk: Line
        Input Events).

        Returning None means "nothing yet, but something else
        happened" -- a timer firing, most likely. The request
        stays pending and glk_select looks again, which is what
        lets a timer event arrive without cancelling line input.
        """

    @abstractmethod
    def read_char(self, window: Window) -> int | None:
        """Read one keystroke, as a Glk character code.

        None means the same as it does for read_line.
        """

    def set_timer(self, millisecs: int) -> None:  # noqa: B027 -- optional override
        """Ask for timer events every so often; zero stops them."""

    def style_distinguish(self, window: Window, first: int, second: int) -> bool:
        """Whether two styles are visibly different in this window."""

        del window, first, second

        return False

    def style_measure(self, window: Window, style: int, hint: int) -> int | None:
        """Measure a style hint, or None if it cannot be measured."""

        del window, style, hint

        return None

    # The graphics contract is inert by default. A display that
    # sets the graphics flag overrides these; one that does not is
    # never asked, because the Graphics gestalt reports zero and
    # graphics windows refuse to open.

    def draw_image(  # noqa: PLR0913, PLR0917 -- the six values of image_draw_scaled
        self,
        window: Window,
        image: ImageInfo,
        val1: int,
        val2: int,
        width: int,
        height: int,
    ) -> bool:
        """Draw a picture; return whether it was drawn."""

        del window, image, val1, val2, width, height

        return False

    def erase_rect(  # noqa: B027 -- optional, inert by default
        self, window: Window, left: int, top: int, width: int, height: int
    ) -> None:
        """Erase a rectangle to the background (Glk: Graphics in Graphics Windows)."""

    def fill_rect(  # noqa: PLR0913, PLR0917, B027 -- optional, inert by default
        self, window: Window, color: int, left: int, top: int, width: int, height: int
    ) -> None:
        """Fill a rectangle with a color."""

    def set_background_color(  # noqa: B027 -- optional, inert by default
        self, window: Window, color: int
    ) -> None:
        """Set the color future clears fill with."""

    def flow_break(self, window: Window) -> None:  # noqa: B027 -- optional override
        """Break text below margin images (Glk: Graphics in Text Buffer Windows)."""

    # The sound contract, equally inert without the sound flag.

    def play_sound(
        self, channel: SoundChannel, sound: int, repeats: int, notify: int
    ) -> bool:
        """Begin playing; return whether it started.

        A display that supports notification posts a SoundNotify
        event through post when the sound ends -- a blocking
        display has no other way to raise one.
        """

        del channel, sound, repeats, notify

        return False

    def stop_sound(  # noqa: B027 -- optional, inert by default
        self, channel: SoundChannel
    ) -> None:
        """Stop whatever the channel is playing."""

    def pause_sound(  # noqa: B027 -- optional, inert by default
        self, channel: SoundChannel, paused: bool
    ) -> None:
        """Pause or resume the channel."""

    def set_volume(  # noqa: B027 -- optional, inert by default
        self, channel: SoundChannel, volume: int, duration: int
    ) -> None:
        """Change the channel's volume, over a duration if asked."""

    def read_mouse(self, window: Window) -> tuple[int, int] | None:
        """Return a clicked position, or None if none can be."""

        del window

        return None

    def read_hyperlink(self, window: Window) -> int | None:
        """Return a selected link value, or None if none can be."""

        del window

        return None

    def prompt_file(self, usage: int, fmode: int) -> str | None:
        """Ask the player for a filename; None cancels.

        Cancelling is always a legitimate answer (Glk: File
        References), so a display with no way to ask can simply
        inherit this.
        """

        del usage, fmode

        return None


class NullFrontend(Frontend):
    """A display that shows nothing and has no input.

    Output is discarded; an input request ends the session, since a
    game waiting for input that can never arrive would otherwise
    hang forever.
    """

    def size(self) -> tuple[int, int]:
        """A classic 80x24, so layout arithmetic stays sensible."""

        return (80, 24)

    def flush(self, root: Window | None) -> None:
        """Discard the rendering."""

    def read_line(self, window: Window, maxlen: int) -> tuple[str, int]:
        """End the session: no line can ever arrive."""

        del window, maxlen

        raise GlulxSessionEnd

    def read_char(self, window: Window) -> int:
        """End the session: no keystroke can ever arrive."""

        del window

        raise GlulxSessionEnd
