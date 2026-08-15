"""Reading AIFF sounds with nothing but the standard library.

Blorb resource files carry their sampled sounds as AIFF FORMs
(Blorb: Sound Resource Chunks), and playing them starts with
reading them -- but Voxam's core stays pure stdlib, and Python
retired its aifc module, so the reading is done here by hand on
top of the shared IFF walker, following the Audio Interchange File
Format 1.3 specification (Apple, 1989).

The scope is the census of every sound in the vendored resource
files: 32 AIFF FORMs, all mono 8-bit samples, holding a COMM
chunk and an SSND chunk -- three of them with MARK and INST
sampler loops alongside, which are skipped the way AIFF tells
readers to skip chunks they have no use for (a Blorb sound's
looping comes from the sound_effect operand, not the instrument).
Compressed AIFF-C never appears there and is refused with its
name given.
"""

import math
import struct
from dataclasses import dataclass

from voxam.errors import AIFFError, IFFError
from voxam.iff import Chunk, parse_form

# The FORM types: plain AIFF is the one Blorb sounds use, and
# AIFF-C adds compression codecs no vendored sound needs.
SOUND_FORM = b"AIFF"
COMPRESSED_FORM = b"AIFC"

# The Common Chunk: channels, sample frames, sample size in bits,
# and the sample rate as an 80-bit extended float -- exactly 18
# bytes, appearing exactly once (AIFF: Common Chunk).
COMMON_ID = b"COMM"
COMMON_SIZE = 18
FIELDS_SIZE = 8
MIN_SAMPLE_SIZE = 1
MAX_SAMPLE_SIZE = 32

# The Sound Data Chunk: an offset, a block size the offset already
# accounts for, then the sample frames (AIFF: Sound Data Chunk).
# It may only be omitted when there are no sample frames at all.
SOUND_DATA_ID = b"SSND"
SOUND_DATA_HEADER_SIZE = 8

# The 80-bit extended float holding the sample rate: a sign bit,
# a 15-bit biased exponent, and a 64-bit mantissa whose integer
# bit is explicit (AIFF: Common Chunk).
SIGN_BIT = 0x8000
EXPONENT_MASK = 0x7FFF
EXTENDED_BIAS = 16383
MANTISSA_SHIFT = 63

BITS_PER_BYTE = 8


@dataclass(frozen=True)
class Sound:
    """A decoded sound: its shape and its raw sample frames.

    Attributes:
        channels: How many interleaved channels each frame holds.
        sample_size: Bits per sample point, 1 to 32.
        sample_rate: Sample frames per second.
        frames: How many sample frames the sound holds.
        samples: The frames as stored: signed two's-complement
            sample points, each left-justified in as many whole
            bytes as its bits need (AIFF: Sound Data Chunk).
    """

    channels: int
    sample_size: int
    sample_rate: float
    frames: int
    samples: bytes

    @property
    def duration(self) -> float:
        """The playing time in seconds."""

        return self.frames / self.sample_rate


def decode(data: bytes) -> Sound:
    """Decode AIFF bytes into a sound.

    Args:
        data: The complete FORM AIFF bytes.

    Raises:
        AIFFError: If the bytes are not an AIFF FORM, are
            compressed AIFF-C, or are internally inconsistent.
    """

    try:
        form_type, chunks = parse_form(data)
    except IFFError as error:
        raise AIFFError(str(error)) from error

    if form_type == COMPRESSED_FORM:
        msg = (
            "this sound is compressed AIFF-C, whose codecs are "
            "outside the plain AIFF every Blorb sound uses"
        )

        raise AIFFError(msg)

    if form_type != SOUND_FORM:
        msg = f"the FORM type is {form_type!r}, not the AIFF of a sound"

        raise AIFFError(msg)

    common = [piece for piece in chunks if piece.chunk_id == COMMON_ID]

    if len(common) != 1:
        msg = (
            f"an AIFF holds exactly one COMM chunk; this one has "
            f"{len(common)} (AIFF: Common Chunk)"
        )

        raise AIFFError(msg)

    channels, frames, sample_size, sample_rate = _common(common[0].payload)
    samples = _samples(chunks, frames, channels, sample_size)

    return Sound(channels, sample_size, sample_rate, frames, samples)


def _common(payload: bytes) -> tuple[int, int, int, float]:
    """Decode the COMM chunk's four fields.

    Raises:
        AIFFError: If the chunk is not its fixed 18 bytes, or a
            field's value is outside what AIFF allows.
    """

    if len(payload) != COMMON_SIZE:
        msg = (
            f"a COMM chunk is exactly {COMMON_SIZE} bytes, but this "
            f"one holds {len(payload)} (AIFF: Common Chunk)"
        )

        raise AIFFError(msg)

    channels, frames, sample_size = struct.unpack(">hLh", payload[:FIELDS_SIZE])

    if channels < 1:
        msg = f"a sound needs at least one channel, not {channels}"

        raise AIFFError(msg)

    if not MIN_SAMPLE_SIZE <= sample_size <= MAX_SAMPLE_SIZE:
        msg = (
            f"a sample point is {MIN_SAMPLE_SIZE} to {MAX_SAMPLE_SIZE} "
            f"bits, not {sample_size} (AIFF: Common Chunk)"
        )

        raise AIFFError(msg)

    return channels, frames, sample_size, _rate(payload[FIELDS_SIZE:])


def _rate(raw: bytes) -> float:
    """Decode the sample rate's 80-bit extended float.

    Raises:
        AIFFError: If the value is not a positive finite number a
            sound could play at.
    """

    sign_exponent, mantissa = struct.unpack(">HQ", raw)
    exponent = sign_exponent & EXPONENT_MASK
    complaint = "the sample rate must be a positive finite number"

    if sign_exponent & SIGN_BIT or exponent == EXPONENT_MASK:
        raise AIFFError(complaint)

    try:
        rate = math.ldexp(mantissa, exponent - EXTENDED_BIAS - MANTISSA_SHIFT)
    except OverflowError as error:
        raise AIFFError(complaint) from error

    if rate <= 0:
        raise AIFFError(complaint)

    return rate


def _samples(
    chunks: tuple[Chunk, ...], frames: int, channels: int, sample_size: int
) -> bytes:
    """Extract the sample frames from at most one SSND chunk.

    Raises:
        AIFFError: For a doubled SSND, one missing while frames
            remain to store, one shorter than its own header, or
            one holding fewer bytes than the frames need.
    """

    sound_data = [piece for piece in chunks if piece.chunk_id == SOUND_DATA_ID]

    if len(sound_data) > 1:
        msg = (
            f"an AIFF holds at most one SSND chunk; this one has "
            f"{len(sound_data)} (AIFF: Sound Data Chunk)"
        )

        raise AIFFError(msg)

    if not sound_data:
        if frames:
            msg = (
                f"{frames} sample frames are promised, but no SSND "
                f"chunk holds them (AIFF: Sound Data Chunk)"
            )

            raise AIFFError(msg)

        return b""

    payload = sound_data[0].payload

    if len(payload) < SOUND_DATA_HEADER_SIZE:
        msg = (
            f"an SSND chunk starts with {SOUND_DATA_HEADER_SIZE} bytes "
            f"of offset and block size, but this one holds only "
            f"{len(payload)} (AIFF: Sound Data Chunk)"
        )

        raise AIFFError(msg)

    offset = int.from_bytes(payload[:4], "big")
    width = (sample_size + BITS_PER_BYTE - 1) // BITS_PER_BYTE
    needed = frames * channels * width
    region = payload[SOUND_DATA_HEADER_SIZE + offset :]

    if len(region) < needed:
        msg = (
            f"{frames} frames of {channels} channel(s) at {width} "
            f"byte(s) each need {needed} bytes, but the SSND chunk "
            f"offers {len(region)} (AIFF: Sound Data Chunk)"
        )

        raise AIFFError(msg)

    return region[:needed]
