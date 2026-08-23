import pytest
from assertpy import assert_that

from voxam.babel import glulx_ifid, ifiction, ifid, zcode_ifid

IFICTION = b"""<?xml version="1.0" encoding="UTF-8"?>
<ifindex version="1.0" xmlns="http://babel.ifarchive.org/protocol/iFiction/">
 <story>
  <identification>
   <ifid>1974A053-7DB0-4103-93A1-767C1382C0B7</ifid>
   <ifid>ZCODE-8-040205-6630</ifid>
   <format>zcode</format>
  </identification>
  <bibliographic>
   <title>Savoir-Faire</title>
   <author>Emily Short</author>
   <headline>An Interactive Vivification</headline>
  </bibliographic>
 </story>
</ifindex>"""


def z_header(
    release: int, serial: bytes, checksum: int = 0, version: int = 5, tail: bytes = b""
) -> bytes:
    data = bytearray(0x40)
    data[0] = version
    data[0x02:0x04] = release.to_bytes(2, "big")
    data[0x12:0x18] = serial
    data[0x1C:0x1E] = checksum.to_bytes(2, "big")

    return bytes(data) + tail


def glulx_image(
    checksum: int = 0,
    compiler: bytes = b"\x00\x00\x00\x00",
    release: int = 0,
    serial: bytes = b"\x00" * 6,
    extent: int = 0x100,
    tail: bytes = b"",
) -> bytes:
    data = bytearray(0x40)
    data[0:4] = b"Glul"
    data[12:16] = extent.to_bytes(4, "big")
    data[32:36] = checksum.to_bytes(4, "big")
    data[36:40] = compiler
    data[52:54] = release.to_bytes(2, "big")
    data[54:60] = serial

    return bytes(data) + tail


# The treaty's own worked example: Savoir-Faire release 8, serial
# 040205, checksum 0x6630 -- an Inform-era serial, so the checksum
# rides as four hexadecimal digits (Babel: The IFID for a legacy
# Z-code story file).
def test_the_treatys_worked_example() -> None:
    assert_that(zcode_ifid(z_header(8, b"040205", 0x6630))).is_equal_to(
        "ZCODE-8-040205-6630"
    )


# Infocom's 8x serials stay bare -- Trinity's first release is the
# treaty's example -- and the named early oddities come through
# exactly, non-date serials and all.
def test_infocom_identities_stay_bare() -> None:
    assert_that(zcode_ifid(z_header(11, b"860509", 0xF00D))).is_equal_to(
        "ZCODE-11-860509"
    )
    assert_that(zcode_ifid(z_header(2, b"AS000C", 0xF00D, version=1))).is_equal_to(
        "ZCODE-2-AS000C"
    )
    assert_that(zcode_ifid(z_header(15, b"UG3AU5", 0xF00D, version=2))).is_equal_to(
        "ZCODE-15-UG3AU5"
    )


# Untrusted serials never earn the checksum -- nulls clean to
# hyphens, 999999 marks a test or modified copy -- while an
# ordinary serial's stray non-ASCII byte cleans to a hyphen and
# keeps the rest of its identity.
def test_serials_clean_and_untrusted_forms_stay_bare() -> None:
    assert_that(zcode_ifid(z_header(5, b"\x00" * 6, 0xF00D, version=1))).is_equal_to(
        "ZCODE-5-------"
    )
    assert_that(zcode_ifid(z_header(15, b"999999", 0xF00D))).is_equal_to(
        "ZCODE-15-999999"
    )
    assert_that(zcode_ifid(z_header(1, b"9\xb50101", 0xBEEF))).is_equal_to(
        "ZCODE-1-9-0101-BEEF"
    )


# A modern serial invites the brand scan and the brand wins,
# lowercase spellings uppercased as Alan writes them; without a
# brand the header answers with its checksum. A pre-2006 serial
# is never scanned at all, brand or no brand.
def test_the_brand_wins_where_it_may_exist() -> None:
    brand = b"...UUID://1974a053-7db0-4103-93a1-767c1382c0b7//..."

    assert_that(zcode_ifid(z_header(1, b"060601", 0xBEEF, tail=brand))).is_equal_to(
        "1974A053-7DB0-4103-93A1-767C1382C0B7"
    )
    assert_that(zcode_ifid(z_header(1, b"060601", 0xBEEF))).is_equal_to(
        "ZCODE-1-060601-BEEF"
    )
    assert_that(zcode_ifid(z_header(11, b"860509", 1, tail=brand))).is_equal_to(
        "ZCODE-11-860509"
    )


# Glulx identities: the brand wherever it sits, else Inform's
# release-serial-checksum when "Info" announces the compiler, else
# the stated memory extent and the checksum alone.
def test_glulx_identities() -> None:
    brand = b"UUID://448E73DF-2D2F-47E7-A494-A46B40D4CFB3//"

    assert_that(glulx_ifid(glulx_image(tail=brand))).is_equal_to(
        "448E73DF-2D2F-47E7-A494-A46B40D4CFB3"
    )
    assert_that(
        glulx_ifid(glulx_image(0xDEADBEEF, b"Info", 83, b"890706"))
    ).is_equal_to("GLULX-83-890706-DEADBEEF")
    assert_that(glulx_ifid(glulx_image(0x1234, extent=0x40000))).is_equal_to(
        "GLULX-00040000-00001234"
    )


# An iFiction record answers its first IFID -- the treaty puts
# the newest foremost when a work carries several -- and its
# bibliography whole. Local names alone are matched, so a record
# missing the treaty's namespace answers all the same.
def test_ifiction_records_read_whole() -> None:
    record = ifiction(IFICTION)

    if record is None:
        pytest.fail("the record did not parse")

    assert_that(record.ifid).is_equal_to("1974A053-7DB0-4103-93A1-767C1382C0B7")
    assert_that(record.title).is_equal_to("Savoir-Faire")
    assert_that(record.author).is_equal_to("Emily Short")
    assert_that(record.headline).is_equal_to("An Interactive Vivification")

    bare = ifiction(
        b"<ifindex><story><identification><ifid>DUMMY-1</ifid>"
        b"</identification></story></ifindex>"
    )

    if bare is None:
        pytest.fail("the bare record did not parse")

    assert_that(bare.ifid).is_equal_to("DUMMY-1")
    assert_that(bare.title).is_none()


# What cannot be read answers None -- broken XML, an index with no
# story record -- and absent fields stay None, whitespace-only
# text included.
def test_unreadable_records_answer_none() -> None:
    assert_that(ifiction(b"<not xml")).is_none()
    assert_that(ifiction(b"<ifindex></ifindex>")).is_none()

    blank = ifiction(
        b"<ifindex><story><bibliographic><title>  </title>"
        b"</bibliographic></story></ifindex>"
    )

    if blank is None:
        pytest.fail("the blank record did not parse")

    assert_that(blank.title).is_none()
    assert_that(blank.ifid).is_none()


# The front door routes by what the bytes claim to be: the Glulx
# magic word, a plausible Z-code version byte, or nothing at all
# -- and a fragment too short for a header has no identity either.
def test_ifid_routes_by_format() -> None:
    assert_that(ifid(glulx_image(7))).is_equal_to("GLULX-00000100-00000007")
    assert_that(ifid(z_header(8, b"040205", 0x6630))).is_equal_to("ZCODE-8-040205-6630")
    assert_that(ifid(b"\x00" * 64)).is_none()
    assert_that(ifid(b"MZ" + b"\x00" * 62)).is_none()
    assert_that(ifid(b"\x05")).is_none()
