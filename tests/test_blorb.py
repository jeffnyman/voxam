import io
import struct
from pathlib import Path

import pytest
from assertpy import assert_that

from voxam.blorb import Blorb, Resource
from voxam.cli import main
from voxam.errors import AIFFError, BlorbError
from voxam.iff import Chunk, chunk, write_form


def story_bytes(version: int = 3) -> bytes:
    """A tiny valid story: boots and quits."""

    data = bytearray(96)
    data[0] = version
    data[0x04:0x06] = (0x0060).to_bytes(2, "big")
    data[0x06:0x08] = (0x0040).to_bytes(2, "big")
    data[0x0E:0x10] = (0x0060).to_bytes(2, "big")
    data[0x40] = 0xBA

    return bytes(data)


def build_blorb(entries: list[tuple[bytes, int, Chunk]], extra: bytes = b"") -> bytes:
    """Assemble a Blorb whose index points at real chunk offsets."""

    body = bytearray(b"IFRS")
    index_payload_size = 4 + len(entries) * 12
    index_chunk_size = 8 + index_payload_size
    position = 8 + 4 + index_chunk_size
    index = bytearray(len(entries).to_bytes(4, "big"))
    pieces = bytearray()

    for usage, number, piece in entries:
        framed = chunk(piece.chunk_id, piece.payload)
        index += usage + number.to_bytes(4, "big") + position.to_bytes(4, "big")
        pieces += framed
        position += len(framed)

    body += chunk(b"RIdx", bytes(index)) + pieces + extra

    return chunk(b"FORM", bytes(body))


# A Blorb round-trips through its index: usages, numbers, and the
# chunks their offsets point at (Blorb: Resource Index Chunk).
def test_the_index_resolves_resources() -> None:
    data = build_blorb(
        [
            (b"Pict", 1, Chunk(b"PNG ", b"picture-bytes")),
            (b"Snd ", 3, Chunk(b"FORM", b"AIFFsound-bytes")),
        ]
    )

    blorb = Blorb.parse(data)

    assert_that(blorb.resources).is_length(2)

    picture = blorb.resource(b"Pict", 1)

    assert_that(picture).is_instance_of(Resource)

    payloads = [
        piece.chunk.payload for piece in blorb.resources if piece.usage == b"Pict"
    ]

    assert_that(payloads).is_equal_to([b"picture-bytes"])
    assert_that(blorb.resource(b"Snd ", 9)).is_none()


# An Exec resource numbered 0 with a ZCOD chunk is a packaged
# story (Blorb: Code Resource Chunks); other executables are not
# ours to run.
def test_a_packaged_story_is_found_and_foreign_code_is_not() -> None:
    ours = Blorb.parse(build_blorb([(b"Exec", 0, Chunk(b"ZCOD", story_bytes()))]))

    assert_that(ours.story).is_equal_to(story_bytes())

    foreign = Blorb.parse(build_blorb([(b"Exec", 0, Chunk(b"GLUL", b"not-z-code"))]))

    assert_that(foreign.story).is_none()
    assert_that(Blorb.parse(build_blorb([])).story).is_none()


# The same Exec seat in the GLUL format is a packaged Glulx story
# -- the .gblorb of games that outgrew the Z-Machine -- and each
# format is invisible to the other's accessor.
def test_a_packaged_glulx_story_is_found_and_z_code_is_not() -> None:
    packaged = Blorb.parse(build_blorb([(b"Exec", 0, Chunk(b"GLUL", b"glulx-image"))]))

    assert_that(packaged.glulx).is_equal_to(b"glulx-image")

    zcode = Blorb.parse(build_blorb([(b"Exec", 0, Chunk(b"ZCOD", story_bytes()))]))

    assert_that(zcode.glulx).is_none()
    assert_that(Blorb.parse(build_blorb([])).glulx).is_none()


# The frontispiece names a cover picture; doubling it is refused
# (Blorb: Frontispiece Chunk).
def test_the_frontispiece_is_read_and_policed() -> None:
    data = build_blorb(
        [(b"Pict", 2, Chunk(b"PNG ", b"cover"))],
        extra=chunk(b"Fspc", (2).to_bytes(4, "big")),
    )

    assert_that(Blorb.parse(data).frontispiece).is_equal_to(2)

    doubled = build_blorb(
        [],
        extra=chunk(b"Fspc", (1).to_bytes(4, "big"))
        + chunk(b"Fspc", (2).to_bytes(4, "big")),
    )

    with pytest.raises(BlorbError, match="more than one"):
        Blorb.parse(doubled)

    stunted = build_blorb([], extra=chunk(b"Fspc", b"\x01"))

    with pytest.raises(BlorbError, match="four picture-number bytes"):
        Blorb.parse(stunted)


# The gallery hangs the drawable art: PNG bytes by number, Rect
# placeholders as placards -- width word then height word -- and a
# JPEG left out, since a picture Voxam cannot draw is not
# "available" in picture_data's sense (§15). The RelN release
# number rides along for the census.
def test_the_gallery_hangs_drawable_art() -> None:
    rect = (314).to_bytes(4, "big") + (84).to_bytes(4, "big")
    data = build_blorb(
        [
            (b"Pict", 1, Chunk(b"PNG ", b"png-bytes")),
            (b"Pict", 2, Chunk(b"Rect", rect)),
            (b"Pict", 3, Chunk(b"JPEG", b"jpeg-bytes")),
            (b"Snd ", 4, Chunk(b"FORM", b"AIFFnoise")),
        ],
        extra=chunk(b"RelN", (27).to_bytes(2, "big")),
    )
    blorb = Blorb.parse(data)

    assert_that(blorb.release).is_equal_to(27)

    gallery = blorb.gallery()

    assert_that(gallery.count).is_equal_to(2)
    assert_that(gallery.size(2)).is_equal_to((84, 314))
    assert_that(gallery.release).is_equal_to(27)


# A Blorb without a RelN releases 0; doubled or short RelN chunks
# are refused, as is a Rect without its eight width-and-height
# bytes (Blorb: Release Number Chunk, Picture Resource Chunks).
def test_release_and_rect_chunks_are_policed() -> None:
    assert_that(Blorb.parse(build_blorb([])).release).is_zero()

    release = chunk(b"RelN", (27).to_bytes(2, "big"))

    with pytest.raises(BlorbError, match="more than one"):
        Blorb.parse(build_blorb([], extra=release + release))

    with pytest.raises(BlorbError, match="two release-number bytes"):
        Blorb.parse(build_blorb([], extra=chunk(b"RelN", b"\x1b")))

    stubby = Blorb.parse(build_blorb([(b"Pict", 5, Chunk(b"Rect", b"\x00\x00"))]))

    with pytest.raises(BlorbError, match="Rect of 2 bytes"):
        stubby.gallery()


def reso_chunk(entries: bytes = b"", px: int = 320, py: int = 200) -> bytes:
    header = b"".join(n.to_bytes(4, "big") for n in (px, py, 0, 0, 0, 0))

    return chunk(b"Reso", header + entries)


def reso_entry(
    number: int,
    ratnum: int = 1,
    ratden: int = 1,
    minnum: int = 0,
    minden: int = 0,
    maxnum: int = 0,
    maxden: int = 0,
) -> bytes:
    return b"".join(
        n.to_bytes(4, "big")
        for n in (number, ratnum, ratden, minnum, minden, maxnum, maxden)
    )


# The Reso chunk's scaling instructions reach the gallery: on a
# 640-by-400 screen against a 320-by-200 standard window the Elbow
# Room Factor is 2, multiplied by each listed picture's standard
# ratio and clamped by its limits; unlisted pictures stay at 1
# (Blorb: The Resolution Chunk).
def test_the_resolution_chunk_reaches_the_gallery() -> None:
    entries = (
        reso_entry(1, ratnum=2)
        + reso_entry(2, minnum=3, minden=1)
        + reso_entry(3, ratnum=10, maxnum=3, maxden=1)
    )
    data = build_blorb(
        [(b"Pict", 1, Chunk(b"PNG ", b"png-bytes"))],
        extra=reso_chunk(entries),
    )
    gallery = Blorb.parse(data).gallery()

    assert_that(gallery.scale(1, 640, 400)).is_equal_to(4)
    assert_that(gallery.scale(2, 640, 400)).is_equal_to(3)
    assert_that(gallery.scale(3, 640, 400)).is_equal_to(3)
    assert_that(gallery.scale(9, 640, 400)).is_equal_to(1)


# The APal chunk names the adaptive pictures -- Infocom's chrome,
# which wears the palette of the scene plotted before it -- and is
# policed for doubling and ragged lengths (Blorb: The Adaptive
# Palette Chunk).
def test_the_adaptive_chunk_is_read_and_policed() -> None:
    numbers = (54).to_bytes(4, "big") + (170).to_bytes(4, "big")
    blorb = Blorb.parse(build_blorb([], extra=chunk(b"APal", numbers)))

    assert_that(blorb.adaptive).is_equal_to(frozenset({54, 170}))
    assert_that(Blorb.parse(build_blorb([])).adaptive).is_empty()

    with pytest.raises(BlorbError, match="more than one"):
        Blorb.parse(build_blorb([], extra=chunk(b"APal", numbers) * 2))

    with pytest.raises(BlorbError, match="four-byte picture numbers"):
        Blorb.parse(build_blorb([], extra=chunk(b"APal", b"\x00\x01")))


# The BPal chunk maps each (scene, adaptive) pair to the
# replacement picture the packager pre-dressed in that scene's
# palette, and is policed for doubling and ragged lengths (Bocfel:
# The Bocfel Adaptive Palette Chunk).
def test_the_baked_chunk_is_read_and_policed() -> None:
    def record(scene: int, adaptive: int, replacement: int) -> bytes:
        return b"".join(n.to_bytes(4, "big") for n in (scene, adaptive, replacement))

    records = record(1, 9, 1000) + record(2, 9, 1001)
    blorb = Blorb.parse(build_blorb([], extra=chunk(b"BPal", records)))

    assert_that(blorb.baked).is_equal_to({(1, 9): 1000, (2, 9): 1001})
    assert_that(Blorb.parse(build_blorb([])).baked).is_empty()

    with pytest.raises(BlorbError, match="more than one"):
        Blorb.parse(build_blorb([], extra=chunk(b"BPal", records) * 2))

    with pytest.raises(BlorbError, match="12-byte records"):
        Blorb.parse(build_blorb([], extra=chunk(b"BPal", b"\x00\x01")))


# Reso chunks are policed: doubled chunks, ragged lengths, a zero
# standard window, a zero standard denominator, and a half-zero
# limit fraction are each refused; a Blorb without one simply has
# no scaling (Blorb: The Resolution Chunk).
def test_resolution_chunks_are_policed() -> None:
    assert_that(Blorb.parse(build_blorb([])).resolution).is_none()

    with pytest.raises(BlorbError, match="more than one"):
        Blorb.parse(build_blorb([], extra=reso_chunk() + reso_chunk()))

    with pytest.raises(BlorbError, match="24-byte header"):
        Blorb.parse(build_blorb([], extra=chunk(b"Reso", b"\x00" * 10)))

    with pytest.raises(BlorbError, match="24-byte header"):
        Blorb.parse(build_blorb([], extra=chunk(b"Reso", b"\x00" * 30)))

    with pytest.raises(BlorbError, match="must be non-zero"):
        Blorb.parse(build_blorb([], extra=reso_chunk(px=0)))

    with pytest.raises(BlorbError, match="divides by zero"):
        Blorb.parse(build_blorb([], extra=reso_chunk(reso_entry(1, ratden=0))))

    with pytest.raises(BlorbError, match="half-zero"):
        Blorb.parse(build_blorb([], extra=reso_chunk(reso_entry(1, minnum=1))))


def _payload(resource: Resource | None) -> bytes:
    """The resource's chunk payload, empty when there is none."""

    return resource.chunk.payload if resource is not None else b""


# The cover is the Fspc picture when one is named; failing that, a
# resource file carrying exactly one picture offers that picture --
# Beyond Zork ships its splash so -- while bigger art sets offer
# nothing rather than a guess (Blorb: Frontispiece Chunk).
def test_the_cover_is_the_frontispiece_or_the_lone_picture() -> None:
    named = Blorb.parse(
        build_blorb(
            [
                (b"Pict", 1, Chunk(b"PNG ", b"one")),
                (b"Pict", 2, Chunk(b"PNG ", b"two")),
            ],
            extra=chunk(b"Fspc", (2).to_bytes(4, "big")),
        )
    )

    assert_that(_payload(named.cover)).is_equal_to(b"two")

    lone = Blorb.parse(build_blorb([(b"Pict", 5, Chunk(b"PNG ", b"solo"))]))

    assert_that(_payload(lone.cover)).is_equal_to(b"solo")

    crowd = Blorb.parse(
        build_blorb(
            [
                (b"Pict", 1, Chunk(b"PNG ", b"one")),
                (b"Pict", 2, Chunk(b"PNG ", b"two")),
            ]
        )
    )

    assert_that(crowd.cover).is_none()
    assert_that(Blorb.parse(build_blorb([])).cover).is_none()


# Only an IFRS FORM is a resource file, exactly one index must
# appear, and entries must point at real chunks.
def test_malformed_blorbs_are_refused() -> None:
    with pytest.raises(BlorbError, match="no FORM chunk"):
        Blorb.parse(b"not even close to an IFF file")

    with pytest.raises(BlorbError, match="not the IFRS"):
        Blorb.parse(write_form(b"IFZS", ()))

    with pytest.raises(BlorbError, match="exactly one RIdx"):
        Blorb.parse(write_form(b"IFRS", ()))

    stray = write_form(
        b"IFRS",
        (
            Chunk(
                b"RIdx",
                (1).to_bytes(4, "big")
                + b"Pict"
                + (1).to_bytes(4, "big")
                + (9999).to_bytes(4, "big"),
            ),
        ),
    )

    with pytest.raises(BlorbError, match="no chunk begins"):
        Blorb.parse(stray)

    short = write_form(b"IFRS", (Chunk(b"RIdx", (5).to_bytes(4, "big")),))

    with pytest.raises(BlorbError, match="needs"):
        Blorb.parse(short)

    stub = write_form(b"IFRS", (Chunk(b"RIdx", b"\x00"),))

    with pytest.raises(BlorbError, match="too short"):
        Blorb.parse(stub)


# The census reads like a banner line.
def test_the_census_counts_resources() -> None:
    full = Blorb.parse(
        build_blorb(
            [
                (b"Pict", 1, Chunk(b"PNG ", b"p")),
                (b"Snd ", 1, Chunk(b"FORM", b"AIFF")),
                (b"Snd ", 2, Chunk(b"FORM", b"AIFF")),
                (b"Exec", 0, Chunk(b"ZCOD", story_bytes())),
            ]
        )
    )

    assert_that(full.described()).is_equal_to("1 picture, 2 sounds, a packaged story")
    assert_that(Blorb.parse(build_blorb([])).described()).is_equal_to("no resources")


# A blorb's iFiction record answers --babel first: its IFID
# outranks the packaged story's, its bibliography rides along,
# and it round-trips off the IFmd chunk exactly as it arrived. A
# record with no IFID lends only its title; one that will not
# parse earns a loud note while the story answers instead.
def test_the_ifiction_record_answers_first(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    record = (
        b'<ifindex xmlns="http://babel.ifarchive.org/protocol/iFiction/">'
        b"<story><identification><ifid>1974A053-7DB0-4103-93A1-767C1382C0B7</ifid>"
        b"</identification><bibliographic><title>Savoir-Faire</title>"
        b"<author>Emily Short</author><headline>An Interactive Vivification"
        b"</headline></bibliographic></story></ifindex>"
    )
    packaged = tmp_path / "game.zblorb"
    packaged.write_bytes(
        build_blorb(
            [(b"Exec", 0, Chunk(b"ZCOD", story_bytes()))],
            extra=chunk(b"IFmd", record),
        )
    )

    assert_that(Blorb.load(packaged).ifiction).is_equal_to(record)
    assert_that(main(["--babel", str(packaged)])).is_equal_to(0)

    out = capsys.readouterr().out

    assert_that(out).contains("IFID: 1974A053-7DB0-4103-93A1-767C1382C0B7")
    assert_that(out).contains("Title: Savoir-Faire")
    assert_that(out).contains("Author: Emily Short")
    assert_that(out).contains("Headline: An Interactive Vivification")

    nameless = tmp_path / "nameless.zblorb"
    nameless.write_bytes(
        build_blorb(
            [(b"Exec", 0, Chunk(b"ZCOD", story_bytes()))],
            extra=chunk(
                b"IFmd",
                b"<ifindex><story><bibliographic><title>Nameless"
                b"</title></bibliographic></story></ifindex>",
            ),
        )
    )

    assert_that(main(["--babel", str(nameless)])).is_equal_to(0)

    out = capsys.readouterr().out

    assert_that(out).contains("IFID: ZCODE-")
    assert_that(out).contains("Title: Nameless")

    faceless = tmp_path / "faceless.zblorb"
    faceless.write_bytes(
        build_blorb(
            [(b"Exec", 0, Chunk(b"ZCOD", story_bytes()))],
            extra=chunk(
                b"IFmd",
                b"<ifindex><story><identification><ifid>DUMMY-9</ifid>"
                b"</identification></story></ifindex>",
            ),
        )
    )

    assert_that(main(["--babel", str(faceless)])).is_equal_to(0)

    out = capsys.readouterr().out

    assert_that(out).contains("IFID: DUMMY-9")
    assert_that(out).does_not_contain("Title:")

    broken = tmp_path / "broken.zblorb"
    broken.write_bytes(
        build_blorb(
            [(b"Exec", 0, Chunk(b"ZCOD", story_bytes()))],
            extra=chunk(b"IFmd", b"<not xml"),
        )
    )

    assert_that(main(["--babel", str(broken)])).is_equal_to(0)

    out = capsys.readouterr().out

    assert_that(out).contains("the iFiction record cannot be read")
    assert_that(out).contains("IFID: ZCODE-")


# --babel unwraps a blorb to the story it packages -- the
# treaty's rule until an iFiction record arrives to answer first
# -- and a blorb with no story inside "is not itself a work of
# IF and so does not have a IFID" (Babel: The IFID for a blorbed
# story file).
def test_babel_reports_the_packaged_story(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    packaged = tmp_path / "game.zblorb"
    packaged.write_bytes(build_blorb([(b"Exec", 0, Chunk(b"ZCOD", story_bytes()))]))

    assert_that(main(["--babel", str(packaged)])).is_equal_to(0)
    assert_that(capsys.readouterr().out).contains("IFID: ZCODE-")

    empty = tmp_path / "empty.blorb"
    empty.write_bytes(build_blorb([]))

    assert_that(main(["--babel", str(empty)])).is_equal_to(2)
    assert_that(capsys.readouterr().out).contains("packages no story")


# A Blorb suffix on the story argument boots the packaged story;
# one packaging nothing runnable reports and refuses.
def test_a_zblorb_story_boots_from_its_package(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    packaged = tmp_path / "game.zblorb"
    packaged.write_bytes(build_blorb([(b"Exec", 0, Chunk(b"ZCOD", story_bytes()))]))

    exit_code = main(["--plain", str(packaged)])

    out = capsys.readouterr().out

    assert_that(exit_code).is_equal_to(0)
    assert_that(out).contains("a packaged story")

    empty = tmp_path / "empty.blorb"
    empty.write_bytes(build_blorb([]))

    exit_code = main(["--plain", str(empty)])

    assert_that(exit_code).is_equal_to(2)
    assert_that(capsys.readouterr().out).contains("packages no Z-code story")


# A .gblorb carries a Glulx story in its Exec seat: it boots and
# runs, the checksum verdict spoken but not gating -- and a broken
# image still fails loudly, at its own fault rather than a
# version-70 riddle.
def test_a_gblorb_boots_its_glulx_story(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    image = bytearray(0x200)
    image[0:4] = b"Glul"
    image[4:8] = (0x00030101).to_bytes(4, "big")
    image[8:12] = (0x100).to_bytes(4, "big")
    image[12:16] = (0x200).to_bytes(4, "big")
    image[16:20] = (0x300).to_bytes(4, "big")
    image[20:24] = (0x100).to_bytes(4, "big")
    packaged = tmp_path / "game.gblorb"
    packaged.write_bytes(build_blorb([(b"Exec", 0, Chunk(b"GLUL", bytes(image)))]))

    exit_code = main([str(packaged)])
    out = capsys.readouterr().out

    assert_that(exit_code).is_equal_to(2)
    assert_that(out).contains("Glulx 3.1.1, CHECKSUM MISMATCH")
    assert_that(out).contains("not a function at all")


# A like-named Blorb beside the story is discovered on its own,
# and --resources points anywhere.
def test_sidecar_and_explicit_resources_are_found(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    story = tmp_path / "game.z3"
    story.write_bytes(story_bytes())
    sidecar = tmp_path / "game.blb"
    sidecar.write_bytes(build_blorb([(b"Snd ", 1, Chunk(b"FORM", b"AIFF"))]))

    exit_code = main(["--plain", str(story)])

    assert_that(exit_code).is_equal_to(0)
    assert_that(capsys.readouterr().out).contains("Resources: 1 sound")

    elsewhere = tmp_path / "shared.blorb"
    elsewhere.write_bytes(build_blorb([(b"Pict", 1, Chunk(b"PNG ", b"p"))]))

    exit_code = main(["--plain", "--resources", str(elsewhere), str(story)])

    assert_that(exit_code).is_equal_to(0)
    assert_that(capsys.readouterr().out).contains("Resources: 1 picture")


# A resource identity naming a different story draws the warning
# the Blorb spec asks for, without stopping play (Blorb: Game
# Identifier Chunk).
def test_a_mismatched_identity_warns_and_plays_on(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    story = tmp_path / "game.z3"
    story.write_bytes(story_bytes())
    stranger = tmp_path / "game.blb"
    stranger.write_bytes(build_blorb([], extra=chunk(b"IFhd", b"\xff" * 13)))

    exit_code = main(["--plain", str(story)])

    out = capsys.readouterr().out

    assert_that(exit_code).is_equal_to(0)
    assert_that(out).contains("names a different story")


def sound_form(samples: bytes) -> Chunk:
    """A minimal mono 8-bit AIFF FORM at 22050 Hz, as a Snd chunk."""

    common = Chunk(
        b"COMM",
        struct.pack(">hLh", 1, len(samples), 8)
        + struct.pack(">HQ", 16383 + 14, 22050 << 49),
    )
    sound_data = Chunk(b"SSND", bytes(8) + samples)

    return Chunk(b"FORM", write_form(b"AIFF", (common, sound_data))[8:])


# A Loop chunk marks which Version 3 sounds repeat until stopped:
# flag zero loops, anything else -- like an absent entry -- plays
# once (Blorb: The Looping Chunk).
def test_the_loop_chunk_names_the_repeating_sounds() -> None:
    entries = struct.pack(">LL", 4, 0) + struct.pack(">LL", 7, 1)
    blorb = Blorb.parse(build_blorb([], extra=chunk(b"Loop", entries)))

    assert_that(blorb.loops).is_equal_to(frozenset({4}))
    assert_that(Blorb.parse(build_blorb([])).loops).is_equal_to(frozenset())


# Doubled or ragged Loop chunks are refused.
def test_malformed_loop_chunks_are_refused() -> None:
    doubled = build_blorb([], extra=chunk(b"Loop", b"") + chunk(b"Loop", b""))

    with pytest.raises(BlorbError, match="Loop chunks appear"):
        Blorb.parse(doubled)

    ragged = build_blorb([], extra=chunk(b"Loop", bytes(7)))

    with pytest.raises(BlorbError, match="eight-byte entries"):
        Blorb.parse(ragged)


# sounds() decodes every Snd resource by number, reframing each
# chunk into the FORM file the AIFF decoder reads (Blorb: Sound
# Resource Chunks).
def test_sounds_decode_by_number() -> None:
    blorb = Blorb.parse(
        build_blorb(
            [
                (b"Snd ", 3, sound_form(b"\x01\x02")),
                (b"Snd ", 5, sound_form(b"\x03")),
                (b"Pict", 1, Chunk(b"PNG ", b"not-a-sound")),
            ]
        )
    )

    sounds = blorb.sounds()

    assert_that(sorted(sounds)).is_equal_to([3, 5])
    assert_that(sounds[3].samples).is_equal_to(b"\x01\x02")
    assert_that(sounds[5].sample_rate).is_equal_to(22050.0)


# A sound in a format other than AIFF is a loud AIFFError for the
# caller to soften into a courtesy.
def test_a_foreign_sound_format_is_loud() -> None:
    blorb = Blorb.parse(build_blorb([(b"Snd ", 3, Chunk(b"OGGV", b"ogg-bytes"))]))

    with pytest.raises(AIFFError):
        blorb.sounds()


# The parse helpers stay honest about padding: an odd chunk before
# a resource still leaves the index pointing at the right offsets.
def test_offsets_survive_padded_neighbours() -> None:
    data = build_blorb(
        [
            (b"Pict", 1, Chunk(b"PNG ", b"odd")),
            (b"Pict", 2, Chunk(b"PNG ", b"even")),
        ]
    )

    blorb = Blorb.parse(data)
    payloads = [piece.chunk.payload for piece in blorb.resources]

    assert_that(payloads).is_equal_to([b"odd", b"even"])
