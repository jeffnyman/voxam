import sys
import threading
import time
import types
from collections.abc import Callable
from typing import cast

import pytest
from assertpy import assert_that

from voxam.aiff import Sound
from voxam.speaker import Fill, Finished, Speaker, Stream, open_sounddevice_stream


def sound(data: bytes, rate: float = 1000.0) -> Sound:
    return Sound(1, 8, rate, len(data), data)


class StubStream:
    """Records lifecycle calls and hands the callbacks to the test."""

    def __init__(self, rate: float, fill: Fill, finished: Finished) -> None:
        self.rate = rate
        self.fill = fill
        self.finished = finished
        self.started = False
        self.aborted = False
        self.closed = False

    def start(self) -> None:
        self.started = True

    def abort(self) -> None:
        self.aborted = True

    def close(self) -> None:
        self.closed = True


class Opener:
    """An OpenStream that keeps every stream it opened."""

    def __init__(self) -> None:
        self.streams: list[StubStream] = []

    def __call__(self, rate: float, fill: Fill, finished: Finished) -> Stream:
        stream = StubStream(rate, fill, finished)
        self.streams.append(stream)

        return stream


def fill_once(stream: StubStream, size: int) -> tuple[bytes, bool]:
    buffer = bytearray(size)
    over = stream.fill(buffer)

    return bytes(buffer), over


# A played sound opens a stream at its own sample rate, drains its
# bytes with a silence tail, and ends naturally exactly once --
# the answer the end-of-sound routine waits on (§9.4.4).
def test_a_sound_plays_through_and_finishes_once() -> None:
    opener = Opener()
    speaker = Speaker({3: sound(b"\x01\x02\x03\x04", rate=8000.0)}, frozenset(), opener)

    speaker.play(3, 8, 1)
    stream = opener.streams[0]

    assert_that(stream.rate).is_equal_to(8000.0)
    assert_that(stream.started).is_true()
    assert_that(speaker.playing()).is_true()
    assert_that(speaker.finished()).is_false()

    heard, over = fill_once(stream, 6)

    assert_that(heard).is_equal_to(b"\x01\x02\x03\x04\x00\x00")
    assert_that(over).is_true()

    stream.finished()

    assert_that(speaker.playing()).is_false()
    assert_that(speaker.finished()).is_true()
    assert_that(speaker.finished()).is_false()


# Repeats count total plays: two plays of three bytes fill seven
# slots and end mid-second-buffer (§9.4.3).
def test_repeats_cycle_the_samples() -> None:
    opener = Opener()
    speaker = Speaker({3: sound(b"\x0a\x0b\x0c")}, frozenset(), opener)

    speaker.play(3, 8, 2)
    stream = opener.streams[0]

    first, over = fill_once(stream, 4)

    assert_that(first).is_equal_to(b"\x0a\x0b\x0c\x0a")
    assert_that(over).is_false()

    second, over = fill_once(stream, 4)

    assert_that(second).is_equal_to(b"\x0b\x0c\x00\x00")
    assert_that(over).is_true()


# Zero repeats means play until stopped (§9.4.3); the Blorb's Loop
# chunk supplies the same forever for a Version 3 sound, and once
# for a sound the chunk does not name (Blorb: The Looping Chunk).
def test_forever_and_the_blorb_defaults() -> None:
    opener = Opener()
    speaker = Speaker({3: sound(b"\x01"), 4: sound(b"\x02")}, frozenset({3}), opener)

    speaker.play(3, 8, 0)

    for _ in range(3):
        _, over = fill_once(opener.streams[0], 5)

        assert_that(over).is_false()

    speaker.play(3, 8, None)

    _, over = fill_once(opener.streams[1], 5)

    assert_that(over).is_false()

    speaker.play(4, 8, None)

    _, over = fill_once(opener.streams[2], 5)

    assert_that(over).is_true()


# The Lurking Horror asks for sound 4095, a bug the §9 remarks
# name; an unknown number quietly plays nothing -- and stops
# nothing, since no new sound started to do the stopping (§9.4.2).
def test_an_unknown_number_plays_nothing() -> None:
    opener = Opener()
    speaker = Speaker({3: sound(b"\x01")}, frozenset(), opener)

    assert_that(speaker.play(4095, 8, 1)).is_false()
    assert_that(opener.streams).is_empty()
    assert_that(speaker.playing()).is_false()
    assert_that(speaker.finished()).is_false()

    assert_that(speaker.play(3, 8, 0)).is_true()
    assert_that(speaker.play(4095, 8, 1)).is_false()
    assert_that(speaker.playing()).is_true()
    assert_that(opener.streams[0].aborted).is_false()


# Volume scales the signed sample points: half volume halves both
# sides of the wave, full volume passes untouched (§9.3).
def test_volume_scales_signed_samples() -> None:
    opener = Opener()
    quiet = bytes([100, 0x9C])
    speaker = Speaker({3: sound(quiet)}, frozenset(), opener)

    speaker.play(3, 4, 1)

    heard, _ = fill_once(opener.streams[0], 2)

    assert_that(heard).is_equal_to(bytes([50, 0xCE]))

    speaker.play(3, 8, 1)

    heard, _ = fill_once(opener.streams[1], 2)

    assert_that(heard).is_equal_to(quiet)


# Starting a new sound stops the current one (§9.4.2); the old
# stream is aborted, its late callbacks fall silent, and its
# routine never fires because it never ended naturally.
def test_a_new_sound_replaces_the_old_one() -> None:
    opener = Opener()
    speaker = Speaker({3: sound(b"\x01"), 4: sound(b"\x02")}, frozenset(), opener)

    speaker.play(3, 8, 1)
    speaker.play(4, 8, 1)

    old, new = opener.streams

    assert_that(old.aborted).is_true()
    assert_that(old.closed).is_true()

    stale, over = fill_once(old, 2)

    assert_that(over).is_true()
    assert_that(stale).is_equal_to(b"\x00\x00")

    old.finished()

    assert_that(speaker.playing()).is_true()
    assert_that(speaker.finished()).is_false()

    heard, _ = fill_once(new, 2)

    assert_that(heard).is_equal_to(b"\x02\x00")


# Stopping by number leaves a different playing sound alone;
# stopping without a number is unconditional, and a manually
# stopped sound's routine is never called (§9.4.4).
def test_stopping_is_selective_and_silences_the_routine() -> None:
    opener = Opener()
    speaker = Speaker({3: sound(b"\x01")}, frozenset(), opener)

    speaker.play(3, 8, 1)
    speaker.stop(7)

    assert_that(speaker.playing()).is_true()

    speaker.stop(3)

    assert_that(speaker.playing()).is_false()
    assert_that(opener.streams[0].aborted).is_true()
    assert_that(speaker.finished()).is_false()

    speaker.play(3, 8, 1)
    speaker.stop()

    assert_that(speaker.playing()).is_false()
    assert_that(speaker.finished()).is_false()


# A frameless sound has already played all its plays: no stream,
# but a natural ending for the routine to hear.
def test_a_frameless_sound_finishes_at_once() -> None:
    opener = Opener()
    speaker = Speaker({3: sound(b"")}, frozenset(), opener)

    speaker.play(3, 8, 1)

    assert_that(opener.streams).is_empty()
    assert_that(speaker.playing()).is_false()
    assert_that(speaker.finished()).is_true()
    assert_that(speaker.finished()).is_false()


# The pacing wait returns at once when nothing plays, wakes when
# the playing sound wraps a cycle, and gives up after one cycle
# plus grace when the stream has gone quiet (§9 remarks on The
# Lurking Horror).
def test_the_pacing_wait_watches_the_cycle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("voxam.speaker.WAIT_GRACE", 0.05)
    opener = Opener()
    speaker = Speaker({3: sound(b"\x01\x02", rate=1000.0)}, frozenset(), opener)

    speaker.wait()

    assert_that(speaker.playing()).is_false()

    speaker.play(3, 8, 0)
    stream = opener.streams[0]
    wrapper = threading.Timer(0.01, lambda: fill_once(stream, 4))

    started = time.monotonic()

    wrapper.start()
    speaker.wait()
    wrapper.join()

    assert_that(time.monotonic() - started).is_less_than(1.0)

    started = time.monotonic()

    speaker.wait()

    assert_that(time.monotonic() - started).is_less_than(1.0)
    assert_that(speaker.playing()).is_true()


# The sounddevice doorway builds a raw mono 8-bit stream whose
# callback raises CallbackStop when the fill says the sound is
# over.
def test_the_sounddevice_doorway_builds_a_callback_stream(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeStopError(Exception):
        pass

    captured: dict[str, object] = {}

    class FakeRaw:
        def __init__(self, **arguments: object) -> None:
            captured.update(arguments)

    fake = types.SimpleNamespace(CallbackStop=FakeStopError, RawOutputStream=FakeRaw)

    monkeypatch.setitem(sys.modules, "sounddevice", fake)

    answers = iter([False, True])
    stream = open_sounddevice_stream(8000.0, lambda _buffer: next(answers), print)

    assert_that(stream).is_instance_of(FakeRaw)
    assert_that(captured["samplerate"]).is_equal_to(8000.0)
    assert_that(captured["channels"]).is_equal_to(1)
    assert_that(captured["dtype"]).is_equal_to("int8")
    assert_that(captured["finished_callback"]).is_equal_to(print)

    callback = cast(
        "Callable[[bytearray, int, object, object], None]", captured["callback"]
    )

    callback(bytearray(2), 2, None, None)

    with pytest.raises(FakeStopError):
        callback(bytearray(2), 2, None, None)
