"""The WAVE writer: AIFF sample points re-wrapped for the wire."""

import struct

from assertpy import assert_that

from voxam.aiff import Sound
from voxam.wav import riff


# An 8-bit mono sound wraps into the canonical 44-byte header --
# PCM format, sizes counted, block align one byte -- with its
# sample points moved to WAVE's unsigned convention, values
# intact, and its fractional sample rate rounded to the whole
# hertz the format stores.
def test_eight_bit_points_turn_unsigned() -> None:
    sound = Sound(1, 8, 9676.2, 4, bytes([0x00, 0x7F, 0x80, 0xFF]))

    held = riff(sound)

    assert_that(held[:4]).is_equal_to(b"RIFF")
    assert_that(struct.unpack("<I", held[4:8])[0]).is_equal_to(40)
    assert_that(held[8:16]).is_equal_to(b"WAVEfmt ")
    assert_that(struct.unpack("<HHIIHH", held[20:36])).is_equal_to(
        (1, 1, 9676, 9676, 1, 8)
    )
    assert_that(held[36:40]).is_equal_to(b"data")
    assert_that(struct.unpack("<I", held[40:44])[0]).is_equal_to(4)
    assert_that(held[44:]).is_equal_to(bytes([0x80, 0xFF, 0x00, 0x7F]))


# Wider sample points keep two's complement and swap byte order,
# point by point, with the block align counting every interleaved
# channel and the byte rate following from it.
def test_wider_points_swap_to_little_endian() -> None:
    sound = Sound(2, 16, 8000.0, 1, bytes([0x12, 0x34, 0xAB, 0xCD]))

    held = riff(sound)

    assert_that(struct.unpack("<HHIIHH", held[20:36])).is_equal_to(
        (1, 2, 8000, 32000, 4, 16)
    )
    assert_that(held[44:]).is_equal_to(bytes([0x34, 0x12, 0xCD, 0xAB]))
