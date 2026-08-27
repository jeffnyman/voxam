"""Tests for the Å-machine's plain voice and the LOOK styles."""

import zlib

import pytest
from assertpy import assert_that

from voxam.aamachine.output import PlainVoice, styled
from voxam.aamachine.story import SUMMED, Story
from voxam.errors import AAMachineError
from voxam.iff import chunk as iff_chunk

# A minimal LANG: the four offsets and an empty extended table.
LANG = (
    (8).to_bytes(2, "big")
    + (8).to_bytes(2, "big")
    + (9).to_bytes(2, "big")
    + (10).to_bytes(2, "big")
    + b"\x00\x00\x00\x00\x00"
)


def dressed(look: bytes = b"\x00\x00") -> Story:
    """A minimal story wearing the given LOOK chunk."""

    summed = {b"LANG": LANG, b"DICT": b"\x00\x00", b"LOOK": look}
    crc = 0

    for name in SUMMED:
        crc = zlib.crc32(summed.get(name, b""), crc)

    head = (
        bytes([0, 5, 2, 0])
        + (1).to_bytes(2, "big")
        + b"260827"
        + crc.to_bytes(4, "big")
        + bytes(6)
    )
    pieces = [iff_chunk(b"HEAD", head)]

    for name in SUMMED:
        pieces.append(iff_chunk(name, summed.get(name, b"")))

    return Story(iff_chunk(b"FORM", b"AAVM" + b"".join(pieces)))


def styled_story(*entries: bytes) -> Story:
    """A story whose LOOK holds one style built from the entries."""

    definition = b"".join(piece + b"\x00" for piece in entries) + b"\x00"
    look = (1).to_bytes(2, "big") + (4).to_bytes(2, "big") + definition

    return dressed(look)


# A LOOK too short for its own count is refused at the door.
def test_a_short_look_is_refused() -> None:
    with pytest.raises(AAMachineError, match=r"too short for its own count"):
        styled(dressed(b"\x00"))


# A count claiming styles past the chunk is refused whole.
def test_an_overclaiming_look_is_refused() -> None:
    with pytest.raises(AAMachineError, match=r"claims 9 styles"):
        styled(dressed((9).to_bytes(2, "big")))


# A style definition missing its null ending is refused by seat.
def test_an_unterminated_style_is_refused() -> None:
    look = (1).to_bytes(2, "big") + (4).to_bytes(2, "big") + b"width: 1em"

    with pytest.raises(AAMachineError, match=r"style 0 is missing"):
        styled(dressed(look))


# Key-value pairs land trimmed; an entry without a colon is
# passed over, the way the spec asks readers to be charitable.
def test_styles_read_their_pairs_charitably() -> None:
    story = styled_story(b"margin-top:  2em ", b"nonsense", b"font-weight: bold")

    assert_that(styled(story)).is_equal_to(
        ({"margin-top": "2em", "font-weight": "bold"},)
    )


# The em-sized margins parse; anything else answers zero.
def test_margins_parse_only_whole_ems() -> None:
    voice = PlainVoice(styled_story(b"margin-top: 2em", b"margin-bottom: 12px"))

    assert_that(voice._margined(0, "margin-top")).is_equal_to(2)
    assert_that(voice._margined(0, "margin-bottom")).is_equal_to(0)
    assert_that(voice._margined(0, "margin-left")).is_equal_to(0)
    assert_that(voice._margined(9, "margin-top")).is_equal_to(0)
    assert_that(voice._margined(-1, "margin-top")).is_equal_to(0)


# Inside a status area the plain voice swallows everything: text,
# breaks, forced spaces, bars, and traces alike.
def test_a_status_area_swallows_everything() -> None:
    voice = PlainVoice(dressed())
    voice.say("before ")
    voice.enter_status(0, 0)
    voice.say("hidden")
    voice.nbsp()
    voice.space()
    voice.spaces(4)
    voice.line()
    voice.par()
    voice.enter_div(0)
    voice.leave_div(0)
    voice.progress(1, 2)
    voice.trace("hidden too")
    voice.leave_status()
    voice.say("after")

    assert_that(voice.told()).is_equal_to("before \nafter")


# A trace lands raw on its own line, wrapped by nothing.
def test_a_trace_lands_on_its_own_line() -> None:
    voice = PlainVoice(dressed())
    voice.say("text")
    voice.trace("query(x) file:9")
    voice.say("more")

    assert_that(voice.told()).is_equal_to("text\nquery(x) file:9\nmore")


# The plain voice's flat answers: no files, no transcript, no
# height, and a width that clamps at zero.
def test_the_flat_answers() -> None:
    voice = PlainVoice(dressed())

    assert_that(voice.save(b"data")).is_false()
    assert_that(voice.restore()).is_none()
    assert_that(voice.script_on()).is_false()
    assert_that(voice.script_active()).is_false()
    assert_that(voice.measured(0)).is_equal_to(80)
    assert_that(voice.measured(1)).is_equal_to(0)
    assert_that(PlainVoice(dressed(), width=-1).measured(0)).is_equal_to(0)

    voice.script_off()


# An echo lands past the wrapper even with a word pending, and
# prompted resets the wrap state for the output that follows.
def test_echoes_land_raw_and_prompted_resets() -> None:
    voice = PlainVoice(dressed(), width=10)
    voice.say("pending")
    voice.echoed("typed\n")
    voice.prompted()
    voice.say("next")

    assert_that(voice.told()).is_equal_to("pendingtyped\nnext")


# A word past the width wraps to a fresh line; forced spaces
# clamp to the room that remains.
def test_the_wrap_and_the_clamp() -> None:
    voice = PlainVoice(dressed(), width=10)
    voice.say("first overlong")
    voice.spaces(99)
    voice.say("x")

    assert_that(voice.told()).is_equal_to("first\noverlong  \nx")


# A progress bar with a zero total draws empty rather than
# dividing by nothing.
def test_a_zero_total_progress_bar_draws_empty() -> None:
    voice = PlainVoice(dressed(), width=13)
    voice.progress(0, 0)

    assert_that(voice.told()).contains("[          ]")


# At width zero -- the wire's shape -- forced spaces go out whole,
# unclamped: the display owns the wrapping.
def test_width_zero_never_clamps_spaces() -> None:
    voice = PlainVoice(dressed(), width=0)
    voice.say("x")
    voice.spaces(5)

    assert_that(voice.told()).is_equal_to("x     ")
