import math
import struct

import pytest
from assertpy import assert_that

from voxam.aiff import decode
from voxam.errors import AIFFError
from voxam.iff import Chunk, write_form


def extended(value: float) -> bytes:
    mantissa, exponent = math.frexp(value)

    return struct.pack(">HQ", exponent - 1 + 16383, int(mantissa * (1 << 64)))


def comm(
    channels: int = 1,
    frames: int = 0,
    bits: int = 8,
    rate: float = 22050.0,
    rate_bytes: bytes = b"",
) -> Chunk:
    fields = struct.pack(">hLh", channels, frames, bits)

    return Chunk(b"COMM", fields + (rate_bytes or extended(rate)))


def ssnd(samples: bytes, offset: int = 0) -> Chunk:
    header = struct.pack(">LL", offset, 0)

    return Chunk(b"SSND", header + b"\xee" * offset + samples)


def sound_bytes(*chunks: Chunk, form_type: bytes = b"AIFF") -> bytes:
    return write_form(form_type, chunks)


# The Infocom shape -- mono 8-bit COMM and SSND, nothing else --
# decodes to its frames exactly, and a whole second of frames at
# the sample rate is a duration of one.
def test_the_infocom_shape_decodes() -> None:
    raw = bytes(range(150)) * 147
    sound = decode(sound_bytes(comm(frames=22050), ssnd(raw)))

    assert_that(sound.channels).is_equal_to(1)
    assert_that(sound.sample_size).is_equal_to(8)
    assert_that(sound.sample_rate).is_equal_to(22050.0)
    assert_that(sound.frames).is_equal_to(22050)
    assert_that(sound.samples).is_equal_to(raw)
    assert_that(sound.duration).is_equal_to(1.0)


# The 80-bit extended float carries fractional rates whole -- the
# Lurking Horror sounds play at rates like 9676.2, not round
# numbers (AIFF: Common Chunk).
def test_a_fractional_sample_rate_survives() -> None:
    sound = decode(sound_bytes(comm(frames=2, rate=11025.5), ssnd(b"\x01\x02")))

    assert_that(sound.sample_rate).is_equal_to(11025.5)


# MARK and INST sampler loops ride along in some sounds; a reader
# skips chunks it has no use for, as AIFF instructs.
def test_sampler_loop_chunks_are_skipped() -> None:
    sound = decode(
        sound_bytes(
            comm(frames=3),
            Chunk(b"MARK", struct.pack(">H", 0)),
            Chunk(b"INST", bytes(20)),
            ssnd(b"\x01\x02\x03"),
        )
    )

    assert_that(sound.samples).is_equal_to(b"\x01\x02\x03")


# The SSND offset pushes the first frame past alignment padding,
# and block padding after the last frame is not sample data
# (AIFF: Sound Data Chunk).
def test_the_ssnd_offset_and_block_padding_are_stepped_around() -> None:
    sound = decode(sound_bytes(comm(frames=2), ssnd(b"\x0a\x0b\xee\xee\xee", offset=4)))

    assert_that(sound.samples).is_equal_to(b"\x0a\x0b")


# A sound promising no frames may omit its SSND chunk entirely
# (AIFF: Sound Data Chunk).
def test_a_frameless_sound_needs_no_ssnd() -> None:
    sound = decode(sound_bytes(comm(frames=0)))

    assert_that(sound.samples).is_equal_to(b"")
    assert_that(sound.duration).is_equal_to(0.0)


# A sample point takes as many whole bytes as its bits need: 16
# bits is two, and so is 12 (AIFF: Sound Data Chunk).
def test_wide_and_packed_sample_points_take_whole_bytes() -> None:
    stereo = decode(sound_bytes(comm(channels=2, frames=2, bits=16), ssnd(bytes(8))))
    packed = decode(sound_bytes(comm(frames=3, bits=12), ssnd(bytes(6))))

    assert_that(stereo.samples).is_length(8)
    assert_that(packed.samples).is_length(6)


@pytest.mark.parametrize(
    ("data", "complaint"),
    [
        (b"RIFF but not a FORM", "not an IFF file"),
        (sound_bytes(comm(), form_type=b"AIFC"), "AIFF-C"),
        (sound_bytes(comm(), form_type=b"IFZS"), "not the AIFF"),
        (sound_bytes(ssnd(b"")), "exactly one COMM"),
        (sound_bytes(comm(), comm()), "exactly one COMM"),
        (sound_bytes(Chunk(b"COMM", bytes(17))), "exactly 18 bytes"),
        (sound_bytes(comm(channels=0)), "at least one channel"),
        (sound_bytes(comm(bits=0)), "1 to 32"),
        (sound_bytes(comm(bits=33)), "1 to 32"),
        (
            sound_bytes(comm(rate_bytes=struct.pack(">HQ", 0x8000 | 16397, 1 << 63))),
            "positive finite",
        ),
        (
            sound_bytes(comm(rate_bytes=struct.pack(">HQ", 0x7FFF, 0))),
            "positive finite",
        ),
        (sound_bytes(comm(rate_bytes=bytes(10))), "positive finite"),
        (
            sound_bytes(comm(rate_bytes=struct.pack(">HQ", 0x7FFE, 1 << 63))),
            "positive finite",
        ),
        (sound_bytes(comm(), ssnd(b""), ssnd(b"")), "at most one SSND"),
        (sound_bytes(comm(frames=5)), "no SSND chunk holds them"),
        (sound_bytes(comm(), Chunk(b"SSND", bytes(4))), "offset and block size"),
        (sound_bytes(comm(frames=4), ssnd(b"\x01\x02")), "offers 2"),
    ],
)
def test_unusable_sounds_are_refused(data: bytes, complaint: str) -> None:
    with pytest.raises(AIFFError, match=complaint):
        decode(data)
