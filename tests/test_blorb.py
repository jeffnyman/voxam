import io
from pathlib import Path

import pytest
from assertpy import assert_that

from voxam.blorb import Blorb, Resource
from voxam.cli import main
from voxam.errors import BlorbError
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
