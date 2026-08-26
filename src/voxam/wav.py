"""Writing WAVE sounds with nothing but the standard library.

The wire's own sound container: a browser's audio engine decodes
WAVE everywhere, where AIFF is a gamble -- so a Blorb's sampled
sounds travel the protocol re-wrapped, their sample points intact.
The writing follows the canonical PCM WAVE layout (RIFF: WAVE
Audio File Format): one fmt chunk, one data chunk, nothing else.
"""

import struct

from voxam.aiff import Sound

BITS_PER_BYTE = 8

# The canonical PCM header: RIFF size counts everything after its
# own eight bytes, and the fmt chunk is the fixed sixteen of
# uncompressed PCM (format tag 1).
PCM_FORMAT = 1
FMT_SIZE = 16
RIFF_TAIL = 36

# WAVE stores 8-bit sample points unsigned, midpoint 0x80; wider
# points stay two's complement and turn little-endian.
UNSIGNED_OFFSET = 0x80


def riff(sound: Sound) -> bytes:
    """An AIFF-decoded sound re-wrapped as a complete WAVE file.

    Sample points keep their values: 8-bit points move to WAVE's
    unsigned convention, wider ones swap byte order, and both
    formats left-justify a point in its whole bytes, so nothing
    is rescaled. A fractional sample rate -- Lurking Horror plays
    at values like 9676.2 -- rounds to the whole hertz the format
    stores, and the listener's audio host resamples, exactly as
    the speaker's does (§9 remarks; AIFF: Common Chunk).
    """

    width = (sound.sample_size + BITS_PER_BYTE - 1) // BITS_PER_BYTE
    data = _little(sound.samples, width)
    rate = max(1, round(sound.sample_rate))
    block = sound.channels * width
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        RIFF_TAIL + len(data),
        b"WAVE",
        b"fmt ",
        FMT_SIZE,
        PCM_FORMAT,
        sound.channels,
        rate,
        rate * block,
        block,
        width * BITS_PER_BYTE,
        b"data",
        len(data),
    )

    return header + data


def _little(samples: bytes, width: int) -> bytes:
    """Big-endian signed sample points as WAVE stores them."""

    if width == 1:
        return bytes(point ^ UNSIGNED_OFFSET for point in samples)

    turned = bytearray(len(samples))

    for start in range(0, len(samples) - width + 1, width):
        turned[start : start + width] = samples[start : start + width][::-1]

    return bytes(turned)
