"""Reading resource files apart: the census told, the contents freed."""

import struct
from pathlib import Path

from assertpy import assert_that

from voxam.decompose import decompose_report, extracted
from voxam.iff import chunk


def blorbed(
    entries: list[tuple[bytes, int, bytes, bytes]], extras: bytes = b""
) -> bytes:
    """Assemble Blorb bytes from (usage, number, id, payload) rows."""

    ridx_payload_len = 4 + 12 * len(entries)
    offset = 12 + 8 + ridx_payload_len + len(extras)
    index = len(entries).to_bytes(4, "big")
    body = b""

    for usage, number, chunk_id, payload in entries:
        index += usage + number.to_bytes(4, "big") + offset.to_bytes(4, "big")
        framed = chunk(chunk_id, payload)
        body += framed
        offset += len(framed)

    return chunk(b"FORM", b"IFRS" + chunk(b"RIdx", index) + extras + body)


def zcode() -> bytes:
    """A minimal Z-code header: version 5, release 11, serial 250101."""

    header = bytearray(0x20)
    header[0] = 5
    header[2:4] = (11).to_bytes(2, "big")
    header[0x12:0x18] = b"250101"

    return bytes(header)


def png(width: int, height: int) -> bytes:
    return (
        b"\x89PNG\r\n\x1a\n"
        + (13).to_bytes(4, "big")
        + b"IHDR"
        + width.to_bytes(4, "big")
        + height.to_bytes(4, "big")
    )


def jpeg(width: int, height: int) -> bytes:
    return (
        b"\xff\xd8"
        + b"\xff\xc0\x00\x08\x08"
        + height.to_bytes(2, "big")
        + width.to_bytes(2, "big")
    )


def tiny_aiff() -> bytes:
    """An AIFF FORM's contents: mono 8-bit, two points at 16384Hz."""

    return (
        b"AIFF"
        + chunk(
            b"COMM",
            struct.pack(">hLh", 1, 2, 8) + struct.pack(">HQ", 16397, 1 << 63),
        )
        + chunk(b"SSND", struct.pack(">LL", 0, 0) + b"\x01\xfe")
    )


def full_blorb() -> bytes:
    """One of everything: the census's whole vocabulary."""

    extras = (
        chunk(b"Fspc", (1).to_bytes(4, "big"))
        + chunk(b"RelN", (7).to_bytes(2, "big"))
        + chunk(b"Loop", struct.pack(">LL", 3, 0))
        + chunk(b"IFhd", (11).to_bytes(2, "big") + b"250101" + bytes(5))
        + chunk(b"IFmd", b"<ifiction/>")
        + chunk(b"SNam", "Tiny".encode("utf-16-be"))
        + chunk(b"AUTH", b"Me")
        + chunk(b"ANNO", b"")
        + chunk(b"XyZw", b"??")
    )

    return blorbed(
        [
            (b"Exec", 0, b"ZCOD", zcode()),
            (b"Pict", 1, b"PNG ", png(2, 3)),
            (b"Pict", 2, b"JPEG", jpeg(4, 5)),
            (b"Pict", 3, b"Rect", struct.pack(">LL", 6, 7)),
            (b"Pict", 4, b"Rect", bytes(4)),
            (b"Pict", 8, b"PNG ", b"\x89PNG\r\n\x1a\nIH"),
            (b"Snd ", 3, b"FORM", tiny_aiff()),
            (b"Snd ", 8, b"FORM", tiny_aiff()),
            (b"Snd ", 5, b"OGGV", b"OggS-ish"),
            (b"Snd ", 6, b"MOD ", b"\x00"),
            (b"Snd ", 7, b"FORM", b"AIFFjunk"),
            (b"Data", 1, b"TEXT", b"hello"),
            (b"Data", 2, b"BINA", b"\x00\x01"),
            (b"Data", 4, b"FORM", b"WRAP" + chunk(b"DATA", b"x")),
        ],
        extras,
    )


# The census speaks every chunk in file order: the story's own
# header facts, pictures measured with the cover credited, sounds
# shaped with their loops credited, placeholders and broken AIFFs
# named honestly, and the descriptive chunks each in their own
# voice -- the wide-charactered story name included.
def test_the_census_tells_every_chunk() -> None:
    report = decompose_report("tiny.zblorb", full_blorb())

    assert_that(report).contains("tiny.zblorb: FORM IFRS, 24 chunks")
    assert_that(report).contains("z5 story, release 11, serial 250101")
    assert_that(report).contains("2 x 3 (the cover)")
    assert_that(report).contains("4 x 5")
    assert_that(report).contains("placeholder, 6 x 7")
    assert_that(report).contains("unmeasurable")
    assert_that(report).contains("AIFF, 1-channel 8-bit, 0.0s (loops until stopped)")
    assert_that(report).contains("FORM, not a readable AIFF")
    assert_that(report).contains("Ogg Vorbis")
    assert_that(report).contains("MOD music")
    assert_that(report).contains("resource index, 14 entries")
    assert_that(report).contains("names Pict 1 the cover")
    assert_that(report).contains("resource release 7")
    assert_that(report).contains("looping: Snd 3")
    assert_that(report).contains("story identity: release 11, serial 250101")
    assert_that(report).contains("iFiction record")
    assert_that(report).contains("SNam Tiny")
    assert_that(report).contains("AUTH Me")
    assert_that(report).contains("XyZw --")

    glulx = blorbed(
        [(b"Exec", 0, b"GLUL", b"Glul\x00\x03\x01\x02" + bytes(8))],
        chunk(b"IFhd", b"\x00") + chunk(b"SONG", b"\x00"),
    )

    told = decompose_report("tiny.gblorb", glulx)

    assert_that(told).contains("Glulx 3.1.2 story")
    assert_that(told).contains("MOD song")


# Extraction frees each resource in the format its bytes already
# are: the story under its own version's name, AIFF FORMs reframed
# whole so a player opens them, a data FORM as plain IFF, and the
# iFiction record as XML. A placeholder carries nothing to export,
# and a file already standing is never overwritten.
def test_extraction_frees_the_resources(tmp_path: Path) -> None:
    freed = tmp_path / "freed"
    log = extracted(full_blorb(), freed)

    assert_that((freed / "story.z5").read_bytes()).is_equal_to(zcode())
    assert_that((freed / "pict-1.png").read_bytes()).is_equal_to(png(2, 3))
    assert_that((freed / "pict-2.jpg").exists()).is_true()
    assert_that((freed / "snd-3.aiff").read_bytes()).is_equal_to(
        chunk(b"FORM", tiny_aiff())
    )
    assert_that((freed / "snd-5.ogg").read_bytes()).is_equal_to(b"OggS-ish")
    assert_that((freed / "snd-6.mod").exists()).is_true()
    assert_that((freed / "data-1.txt").read_bytes()).is_equal_to(b"hello")
    assert_that((freed / "data-2.bin").exists()).is_true()
    assert_that((freed / "data-4.iff").read_bytes()).is_equal_to(
        chunk(b"FORM", b"WRAP" + chunk(b"DATA", b"x"))
    )
    assert_that((freed / "ifiction.xml").read_bytes()).is_equal_to(b"<ifiction/>")
    assert_that(log).contains("pict-3: a Rect carries nothing to export")
    assert_that(log).contains("story.z5 -- ")

    again = extracted(full_blorb(), freed)

    assert_that(again).contains("story.z5: already here, left alone")

    oddities = tmp_path / "odd"
    told = extracted(
        blorbed(
            [
                (b"Exec", 0, b"GLUL", b"Glul\x00\x03\x01\x02" + bytes(8)),
                (b"Exec", 1, b"Rect", bytes(8)),
                (b"Exec", 2, b"ABCD", b"?"),
                (b"Pict", 9, b"WEIR", b"x"),
            ]
        ),
        oddities,
    )

    assert_that((oddities / "story.ulx").exists()).is_true()
    assert_that((oddities / "story.rect").exists()).is_true()
    assert_that((oddities / "story.abcd").exists()).is_true()
    assert_that((oddities / "pict-9.bin").exists()).is_true()
    assert_that(told).contains("story.abcd -- ")
