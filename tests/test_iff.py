import pytest
from assertpy import assert_that

from voxam.errors import IFFError
from voxam.iff import Chunk, chunk, parse_form, write_form


# A FORM round-trips: the type comes back, and every chunk returns
# in file order -- including ones no reader claims to know, because
# what a chunk means is the caller's business.
def test_a_form_round_trips_with_unknown_chunks() -> None:
    written = write_form(
        b"IFRS",
        (
            Chunk(b"RIdx", b"\x00\x00\x00\x01"),
            Chunk(b"AUTH", b"jeff"),
            Chunk(b"Myst", b"?"),
        ),
    )

    form_type, chunks = parse_form(written)

    assert_that(form_type).is_equal_to(b"IFRS")
    assert_that([piece.chunk_id for piece in chunks]).is_equal_to(
        [b"RIdx", b"AUTH", b"Myst"]
    )
    assert_that(chunks[2].payload).is_equal_to(b"?")


# Odd payloads gain a pad byte their length does not count
# (Quetzal §8.4.1), and the parse strides straight over it.
def test_odd_payloads_are_padded_and_unpadded() -> None:
    framed = chunk(b"ODDS", b"abc")

    assert_that(len(framed)).is_equal_to(12)
    assert_that(framed[8:11]).is_equal_to(b"abc")
    assert_that(framed[11:]).is_equal_to(b"\x00")

    _type, chunks = parse_form(write_form(b"TEST", (Chunk(b"ODDS", b"abc"),)))

    assert_that(chunks[0].payload).is_equal_to(b"abc")


# Bytes that do not open with a FORM chunk are not IFF at all
# (Quetzal §8.5).
def test_non_forms_are_refused() -> None:
    with pytest.raises(IFFError, match="no FORM chunk"):
        parse_form(b"GIF89a not even close")


# A FORM claiming more bytes than the file holds is truncated
# (Quetzal §8.3.5), as is a chunk overrunning the FORM (Quetzal
# §8.4) or one cut short mid-header (Quetzal §8.3.1).
def test_truncations_are_refused() -> None:
    whole = write_form(b"TEST", (Chunk(b"DATA", b"abcdef"),))

    with pytest.raises(IFFError, match="FORM chunk claims"):
        parse_form(whole[:-4])

    overrun = bytearray(whole)
    overrun[16] = 0xFF

    with pytest.raises(IFFError, match="chunk claims"):
        parse_form(bytes(overrun))

    stub = write_form(b"TEST", ())[: 8 + 4] + b"AB"
    stub = stub[:4] + (len(stub) - 8).to_bytes(4, "big") + stub[8:]

    with pytest.raises(IFFError, match="cut short mid-header"):
        parse_form(stub)
