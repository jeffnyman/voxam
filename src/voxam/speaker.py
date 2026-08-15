"""Playing sampled sounds through a real audio device.

A started sound effect takes place in the background, while normal
operation of the Z-machine goes on (§9.4). This module is where
that background lives: a Speaker holds a game's decoded sounds and
feeds the current one to an output stream a buffer-full at a time,
on the stream's own callback thread, at the sound's own sample
rate -- Lurking Horror's rates are values like 9676.2, and the
audio host resamples, not us.

The device arrives through the `sounddevice` package, the `sound`
optional extra -- but only through the sliver the Stream protocol
names, so the whole machinery can be driven by a stub in tests and
the module imports without the extra installed.
"""

import threading
from collections.abc import Callable, Mapping
from typing import Protocol, cast

from voxam.aiff import Sound

# Sound effects play at volumes 1 to 8, 8 the loudest (§9.3); at 8
# the sample points pass untouched.
FULL_VOLUME = 8

# 8-bit sample points are signed two's complement: bytes past the
# sign boundary are the negative half of the wave.
SIGN_BOUNDARY = 127
BYTE_SPAN = 256
BYTE_MASK = 0xFF

# A pacing wait blocks for at most one cycle of the playing sound;
# the grace beyond that covers buffering, then calls the stream
# gone rather than hang the machine.
WAIT_GRACE = 1.0


class Stream(Protocol):
    """The sliver of an output stream the speaker drives."""

    def start(self) -> None:
        """Begin pulling buffers through the callback."""

    def abort(self) -> None:
        """Stop at once, without draining pending buffers."""

    def close(self) -> None:
        """Release the stream's device resources."""


# A fill callback loads the next buffer-full of sample bytes and
# answers whether the sound is over; a finished callback hears
# that the stream has actually stopped, however it stopped.
Fill = Callable[[bytearray], bool]
Finished = Callable[[], None]
OpenStream = Callable[[float, Fill, Finished], Stream]


class Speaker:
    """One game's sounds, played one at a time (§9.4.2).

    Only one sampled sound plays at any given time: starting a new
    one stops the current one. The machine polls playing() for the
    §9 remarks' pacing rule and finished() for the end-of-sound
    routine; both answers come from flags the stream's callback
    thread sets, never from the audio data itself.
    """

    def __init__(
        self,
        sounds: Mapping[int, Sound],
        loops: frozenset[int],
        open_stream: OpenStream,
    ) -> None:
        """Hold the decoded sounds and the way to a device.

        Args:
            sounds: Every decoded sound, by resource number.
            loops: The numbers the Blorb's Loop chunk repeats
                until stopped -- the Version 3 default.
            open_stream: The doorway to an output stream; tests
                pass a stub, play passes the sounddevice one.
        """

        self._sounds = dict(sounds)
        self._loops = loops
        self._open_stream = open_stream
        self._stream: Stream | None = None
        self._number: int | None = None
        self._data = b""
        self._position = 0
        self._remaining: int | None = 1
        self._duration = 0.0
        self._playing = False
        self._ended_naturally = False
        self._generation = 0
        self._cycle = threading.Event()

    def play(self, number: int, volume: int, repeats: int | None) -> bool:
        """Start a sound, stopping any current one (§9.4.2).

        Args:
            number: The sound to play. An unknown number quietly
                plays nothing -- and stops nothing, since nothing
                new started: The Lurking Horror's own bug asks for
                sound 4095, and the §9 remarks name it.
            volume: The §9.3 volume, 1 to 8.
            repeats: The total number of plays; 0 repeats until
                stopped (§9.4.3), and None plays as the Blorb's
                Loop chunk says -- the Version 3 case.

        Returns:
            Whether a sound actually started -- the answer that
            decides if an end-of-sound routine is worth keeping.
        """

        sound = self._sounds.get(number)

        if sound is None:
            return False

        self.stop()

        if repeats is None:
            repeats = 0 if number in self._loops else 1

        self._number = number
        self._data = _scaled(sound.samples, volume)
        self._position = 0
        self._remaining = None if repeats == 0 else repeats
        self._duration = sound.duration
        self._ended_naturally = False
        self._cycle = threading.Event()

        if not self._data:
            # A frameless sound has already played all its plays.
            self._ended_naturally = True

            return True

        generation = self._generation
        self._stream = self._open_stream(
            sound.sample_rate,
            lambda buffer: self._fill(generation, buffer),
            lambda: self._finished(generation),
        )
        self._playing = True
        self._stream.start()

        return True

    def stop(self, number: int | None = None) -> None:
        """Stop a sound, or whatever is playing (§9.4).

        Args:
            number: Stop only this sound, leaving another playing
                sound alone; None stops unconditionally, the
                sound_effect 0 form.
        """

        if number is not None and number != self._number:
            return

        self._generation += 1
        stream, self._stream = self._stream, None
        self._playing = False
        self._cycle.set()

        if stream is not None:
            stream.abort()
            stream.close()

    def playing(self) -> bool:
        """Whether a sound is still sounding."""

        return self._playing

    def finished(self) -> bool:
        """Whether the current sound just ended of its own accord.

        True once per natural ending -- the answer the end-of-sound
        routine waits on. A sound stopped by stop() or replaced by
        play() never ended naturally, so its routine is rightly
        never called (§9.4.4).
        """

        if self._ended_naturally and not self._playing:
            self._ended_naturally = False

            return True

        return False

    def wait(self) -> None:
        """Block until the playing sound finishes a cycle.

        The Lurking Horror fires several sounds in one game round,
        assuming an interpreter as slow as Infocom's Amiga one; the
        §9 remarks ask that a new sound wait for the current one to
        finish a cycle before replacing it. Returns at once when
        nothing plays.
        """

        if not self._playing:
            return

        self._cycle.clear()
        self._cycle.wait(self._duration + WAIT_GRACE)

    def _fill(self, generation: int, buffer: bytearray) -> bool:
        """Load the next buffer-full; True when the sound is over.

        Runs on the stream's callback thread. A stale generation
        means stop() or a new play() has moved on while this
        stream's last callbacks were still in flight: fall silent.
        """

        if generation != self._generation:
            return True

        size = len(buffer)
        filled = bytearray()

        while len(filled) < size:
            piece = self._data[self._position : self._position + size - len(filled)]
            filled += piece
            self._position += len(piece)

            if self._position >= len(self._data):
                self._position = 0
                self._cycle.set()

                if self._remaining is not None:
                    self._remaining -= 1

                    if self._remaining < 1:
                        filled += bytes(size - len(filled))
                        buffer[:] = bytes(filled)
                        self._ended_naturally = True

                        return True

        buffer[:] = bytes(filled)

        return False

    def _finished(self, generation: int) -> None:
        """Hear that the stream stopped; wake any pacing waiter.

        Runs on the stream's callback thread, after the last
        buffer drains -- naturally or not.
        """

        if generation != self._generation:
            return

        self._playing = False
        self._cycle.set()


def open_sounddevice_stream(rate: float, fill: Fill, finished: Finished) -> Stream:
    """Open a real output stream for mono signed 8-bit frames.

    The sounddevice package is imported here, not at module top,
    because the `sound` extra is optional: everything else in this
    module works without it.
    """

    import sounddevice  # noqa: PLC0415

    def callback(
        outdata: bytearray, _frames: int, _time: object, _status: object
    ) -> None:
        if fill(outdata):
            raise sounddevice.CallbackStop

    return cast(
        "Stream",
        sounddevice.RawOutputStream(
            samplerate=rate,
            channels=1,
            dtype="int8",
            callback=callback,
            finished_callback=finished,
        ),
    )


def _scaled(samples: bytes, volume: int) -> bytes:
    """Sample points at a §9.3 volume, 8 passing untouched.

    The points are signed bytes, so the scale is a 256-entry
    translation table -- one signed multiply per possible value,
    then bytes.translate does the samples in C.
    """

    if volume >= FULL_VOLUME:
        return samples

    table = bytes(
        (_signed(value) * volume // FULL_VOLUME) & BYTE_MASK
        for value in range(BYTE_SPAN)
    )

    return samples.translate(table)


def _signed(value: int) -> int:
    """The two's-complement reading of one sample byte."""

    return value - BYTE_SPAN if value > SIGN_BOUNDARY else value
