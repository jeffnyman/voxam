"""The header glance: the story's own manifest, reported (§11.1)."""

from collections.abc import Callable
from pathlib import Path

import pytest
from assertpy import assert_that

from voxam.cli import main
from voxam.glance import report
from voxam.zmachine.story import Story

EXIT_OK = 0
EXIT_UNUSABLE = 2


def crafted(
    version: int = 3,
    flags_1: int = 0,
    flags_2: int = 0,
    words: dict[int, int] | None = None,
    checksum: int | None = None,
) -> Story:
    """Build a tiny story whose header says exactly what a test needs.

    The declared length covers the whole 128 bytes, so the checksum
    ranges over the 64 bytes past the header; None computes the true
    checksum so verification passes, while an explicit value plants
    disagreement.
    """

    data = bytearray(128)
    data[0] = version
    data[0x01] = flags_1
    data[0x04:0x06] = (0x0080).to_bytes(2, "big")
    data[0x06:0x08] = (0x0040).to_bytes(2, "big")
    data[0x0E:0x10] = (0x0060).to_bytes(2, "big")
    data[0x10:0x12] = flags_2.to_bytes(2, "big")
    data[0x12:0x18] = b"260101"
    data[0x1A:0x1C] = (
        128 // {1: 2, 2: 2, 3: 2, 4: 4, 5: 4, 6: 8, 7: 8, 8: 8}[version]
    ).to_bytes(2, "big")
    data[0x40] = 7  # one nonzero story byte, so a zero checksum cannot agree

    for offset, value in (words or {}).items():
        data[offset : offset + 2] = value.to_bytes(2, "big")

    stored = checksum if checksum is not None else sum(data[0x40:128]) % 0x10000
    data[0x1C:0x1E] = stored.to_bytes(2, "big")

    return Story(bytes(data))


# The report names the story's identity and, when the stored and
# computed checksums agree, says so in §15 verify's terms.
def test_reports_identity_and_verified_checksum(
    load_fixture: Callable[[int], Story],
) -> None:
    text = report(load_fixture(3))

    assert_that(text).contains("version")
    assert_that(text).contains("stored and computed agree")
    assert_that(text).contains("§15 verify")


# A corrupt story draws a loud MISMATCH with both sums shown. The
# corrupted byte sits just past the header: the file's tail may be
# padding beyond the declared length, which verification rightly
# ignores (§11.1.6).
def test_reports_checksum_mismatch(load_fixture: Callable[[int], Story]) -> None:
    data = bytearray(load_fixture(3).data)
    data[0x41] ^= 0xFF

    assert_that(report(Story(bytes(data)))).contains("MISMATCH")


# A stored zero earns the §11.1 caveat instead of an accusation:
# some early Version 3 files store no checksum at all.
def test_stored_zero_checksum_draws_the_caveat() -> None:
    text = report(crafted(checksum=0))

    assert_that(text).contains("some early")
    assert_that(text).does_not_contain("MISMATCH")


# Versions other than 6 report the initial program counter; 6 alone
# reports the packed main routine (§5.4, §5.5) and, with 7, the
# packed-address offsets (§1.2.3).
def test_reports_the_versions_own_start_and_offsets(
    load_fixture: Callable[[int], Story],
) -> None:
    five = report(load_fixture(5))
    six = report(load_fixture(6))
    seven = report(load_fixture(7))

    assert_that(five).contains("initial pc")
    assert_that(five).does_not_contain("routines offset")
    assert_that(six).contains("main routine")
    assert_that(six).contains("routines offset")
    assert_that(seven).contains("initial pc")
    assert_that(seven).contains("strings offset")


# A Version 3 story names its status line type, and the time bit
# flips the answer (§8.2.3).
def test_reports_the_status_line_type() -> None:
    assert_that(report(crafted())).contains("score and turns")
    assert_that(report(crafted(flags_1=0x02))).contains("time of day")


# A shipped Tandy bit is called out; Version 4 has no status line
# stanza at all (§8.2).
def test_reports_the_tandy_bit_and_drops_the_stanza_later() -> None:
    assert_that(report(crafted(flags_1=0x08))).contains("tandy bit")
    assert_that(report(crafted(version=4))).does_not_contain("status line")


# The Flags 2 request bits become a plain list of asks, and bit 3
# means the §16 font before Version 6 but pictures from it (§11.1).
def test_reports_the_games_requests() -> None:
    fonted = report(crafted(version=5, flags_2=0x00F8))
    pictured = report(crafted(version=6, flags_2=0x0108))

    assert_that(fonted).contains("character graphics font")
    assert_that(fonted).contains("undo")
    assert_that(fonted).contains("a mouse")
    assert_that(fonted).contains("colours")
    assert_that(fonted).contains("sound effects")
    assert_that(pictured).contains("pictures")
    assert_that(pictured).contains("menus")


# A story asking for nothing says so rather than printing an empty
# list.
def test_reports_no_requests_honestly() -> None:
    assert_that(report(crafted())).contains("no optional courtesies")


# A custom alphabet table and a custom Unicode table both surface
# with their addresses (§3.5.5, §3.8.5.2).
def test_reports_custom_tables() -> None:
    custom = crafted(
        version=5,
        words={0x34: 0x0050, 0x36: 0x0048, 0x48: 3, 0x4E: 0x0044},
    )
    text = report(custom)

    assert_that(text).contains("$0050")
    assert_that(text).contains("custom alphabets")
    assert_that(text).contains("$0044")
    assert_that(text).contains("custom translations")


# --header prints the report and exits cleanly.
def test_cli_header_glance(
    fixture_path: Callable[[int], Path], capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = main(["--header", str(fixture_path(3))])
    out = capsys.readouterr().out

    assert_that(exit_code).is_equal_to(EXIT_OK)
    assert_that(out).contains("Identity")
    assert_that(out).contains("Memory map")
    assert_that(out).contains("Flags, as shipped")


# --header needs a story, refuses session flags, and reports an
# unreadable file in the house voice.
def test_cli_header_refusals(
    fixture_path: Callable[[int], Path], capsys: pytest.CaptureFixture[str]
) -> None:
    assert_that(main(["--header"])).is_equal_to(EXIT_UNUSABLE)
    assert_that(capsys.readouterr().out).contains("needs a story")

    combined = main(["--header", "--accept", "x.accept", str(fixture_path(3))])

    assert_that(combined).is_equal_to(EXIT_UNUSABLE)
    assert_that(capsys.readouterr().out).contains("drop the session flags")

    missing = main(["--header", "no-such-story.z3"])

    assert_that(missing).is_equal_to(EXIT_UNUSABLE)
    assert_that(capsys.readouterr().out).contains("voxam:")
