"""The Å-machine's table of resources, and the faces that show one.

A story may carry pictures of its own: URLS names them, FILE holds
the bytes, and EMBED_RES asks the display to set one into the flow
(Aa-machine: URLS). The stories built here carry a real two-pixel
PNG, so what a display is handed is a picture it could draw.
"""

import zlib

from assertpy import assert_that

from voxam.aamachine.glkote import GlkOteFrontend, WireVoice
from voxam.aamachine.story import SUMMED, Story
from voxam.iff import chunk as iff_chunk

# A minimal LANG: the four offsets and an empty extended table.
LANG = (
    b"\x00\x00"
    + (8).to_bytes(2, "big")
    + b"\x00\x00\x00\x00"
    + bytes([1, 0xE5, 0xC5])
    + (0xC5).to_bytes(3, "big")
)


def storied(*extra: bytes) -> Story:
    """A minimal story, with whatever extra chunks are handed in."""

    summed = {b"LANG": LANG, b"DICT": b"\x00\x00", b"LOOK": b"\x00\x00"}
    crc = 0

    for name in SUMMED:
        crc = zlib.crc32(summed.get(name, b""), crc)

    head = (
        bytes([0, 5, 2, 0])
        + (1).to_bytes(2, "big")
        + b"260902"
        + crc.to_bytes(4, "big")
        + (16).to_bytes(2, "big")
        + (8).to_bytes(2, "big")
        + (32).to_bytes(2, "big")
    )
    pieces = [iff_chunk(b"HEAD", head), *extra]

    for name in SUMMED:
        pieces.append(iff_chunk(name, summed.get(name, b"")))

    return Story(iff_chunk(b"FORM", b"AAVM" + b"".join(pieces)))


def urls(*descriptors: bytes) -> bytes:
    """A URLS chunk: the count, the offsets, then the descriptors."""

    head = len(descriptors).to_bytes(2, "big")
    at = len(head) + 2 * len(descriptors)
    offsets = b""

    for descriptor in descriptors:
        offsets += at.to_bytes(2, "big")
        at += len(descriptor)

    return iff_chunk(b"URLS", head + offsets + b"".join(descriptors))


def descriptor(url: str, alt: int = 0x000A16, options: str = "") -> bytes:
    """One URLS entry: the alt-text pointer, the URL, the options."""

    return (
        alt.to_bytes(3, "big")
        + url.encode("latin-1")
        + b"\x00"
        + options.encode("latin-1")
        + b"\x00"
    )


def filed(name: str, body: bytes) -> bytes:
    """A FILE chunk: the filename, then the contents."""

    return iff_chunk(b"FILE", name.encode("latin-1") + b"\x00" + body)


# The table reads as the specification lays it out, and a story
# without one simply has no resources rather than no table.
def test_the_resource_table_reads() -> None:
    story = storied(urls(descriptor("file:art.png"), descriptor("https://x/y.jpg")))

    assert_that(story.resources).is_length(2)
    assert_that(story.resources[0].url).is_equal_to("file:art.png")
    assert_that(story.resources[0].alt).is_equal_to(0x000A16)
    assert_that(story.resources[0].options).is_empty()
    assert_that(story.resources[1].url).is_equal_to("https://x/y.jpg")
    assert_that(storied().resources).is_empty()


# The options ride as written; the specification leaves reading
# them to the interpreter.
def test_a_descriptor_keeps_its_options() -> None:
    story = storied(urls(descriptor("file:art.png", options="width:80,center")))

    assert_that(story.resources[0].options).is_equal_to("width:80,center")


# A table that runs off its own chunk is read for the entries that
# do fit: the resources are a courtesy, and a story that can do
# without one can do without a refused parse.
def test_a_truncated_table_keeps_what_fits() -> None:
    whole = urls(descriptor("file:art.png"), descriptor("file:more.png"))
    payload = whole[8:]

    # Each cut lands in a different part of the walk: short of the
    # count itself, short of an offset, short of a descriptor's
    # alt pointer, and short of the null its URL ends with.
    for cut in (0, 1, 3, 5, 9, 14):
        story = storied(iff_chunk(b"URLS", payload[:cut]))

        assert_that(len(story.resources)).described_as(f"cut {cut}").is_less_than(2)


# A resource the story carries comes back with its filename and
# its bytes; one it does not, or one pointing at somebody's
# network, comes back as nothing.
def test_only_a_carried_resource_resolves(tiny_png: bytes) -> None:
    story = storied(
        urls(
            descriptor("file:art.png"),
            descriptor("https://example.invalid/art.png"),
            descriptor("file:absent.png"),
        ),
        filed("art.png", tiny_png),
    )

    found = story.embedded(0)

    assert_that(found).is_equal_to(("art.png", tiny_png))

    assert_that(story.embedded(1)).is_none()
    assert_that(story.embedded(2)).is_none()
    assert_that(story.embedded(-1)).is_none()
    assert_that(story.embedded(9)).is_none()


# A FILE chunk with no null after its filename names nothing, and
# is passed over rather than read as a name of its whole length.
def test_a_nameless_file_chunk_is_passed_over(tiny_png: bytes) -> None:
    story = storied(
        urls(descriptor("file:art.png")),
        iff_chunk(b"FILE", b"art.png"),
        filed("art.png", tiny_png),
    )

    assert_that(story.embedded(0)).is_not_none()

    bare = storied(urls(descriptor("file:art.png")), iff_chunk(b"FILE", b"art.png"))

    assert_that(bare.embedded(0)).is_none()


# The wire face claims a resource it can resolve and measure, and
# refuses one it cannot: a display told no shows whatever the
# story says instead (Aa-machine: CAN_EMBED_RES).
def test_the_wire_claims_only_what_it_can_draw(tiny_png: bytes) -> None:
    story = storied(
        urls(descriptor("file:art.png"), descriptor("file:broken.png")),
        filed("art.png", tiny_png),
        filed("broken.png", b"not a picture at all"),
    )
    voice = WireVoice(story)

    assert_that(voice.can_embed_res(0)).is_true()
    assert_that(voice.can_embed_res(1)).is_false()
    assert_that(voice.can_embed_res(7)).is_false()


# A claimed resource is marked where it was asked for, and the
# face sets the picture into the flow at that point, between the
# words it was told between.
def test_a_picture_lands_between_the_words_it_was_told_between(
    tiny_png: bytes,
) -> None:
    story = storied(urls(descriptor("file:art.png")), filed("art.png", tiny_png))
    face = GlkOteFrontend(story)

    face.voice.say("before")
    face.voice.embed_res(0)
    face.voice.say("after")
    face.voice.embed_res(4)

    runs = [
        run
        for window in face.render().get("content", [])
        for line in window.get("text", [])
        for run in line.get("content", []) or []
    ]
    pictures = [run for run in runs if isinstance(run, dict) and "special" in run]
    words = [run.get("text", "") for run in runs if isinstance(run, dict)]

    assert_that(pictures).is_length(1)
    assert_that(pictures[0]["special"]).is_equal_to("image")
    assert_that(pictures[0]["image"]).is_equal_to(0)
    assert_that(pictures[0]["width"]).is_equal_to(2)
    assert_that(pictures[0]["height"]).is_equal_to(2)
    assert_that(pictures[0]["url"]).starts_with("data:image/png;base64,")

    said = "".join(words)

    assert_that(said).contains("before")
    assert_that(said).contains("after")


# A JPEG is named by its own ending, so a display is told the type
# the bytes actually are.
def test_a_jpeg_resource_is_named_as_one() -> None:
    jpeg = (
        b"\xff\xd8"
        + b"\xff\xc0\x00\x08\x08"
        + (6).to_bytes(2, "big")
        + (9).to_bytes(2, "big")
    )
    story = storied(urls(descriptor("file:art.jpeg")), filed("art.jpeg", jpeg))
    voice = WireVoice(story)

    assert_that(voice.can_embed_res(0)).is_true()

    face = GlkOteFrontend(story)
    face.voice.embed_res(0)

    runs = [
        run
        for window in face.render().get("content", [])
        for line in window.get("text", [])
        for run in line.get("content", []) or []
    ]
    picture = next(run for run in runs if isinstance(run, dict) and "special" in run)

    assert_that(picture["url"]).starts_with("data:image/jpeg;base64,")
    assert_that((picture["width"], picture["height"])).is_equal_to((9, 6))
