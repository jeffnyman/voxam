from collections.abc import Callable

import pytest
from assertpy import assert_that

from voxam.errors import ZMachineHeaderError
from voxam.zmachine.header import CHECKSUM_START, HEADER_SIZE, PACKED_PC_VERSION, Header
from voxam.zmachine.story import Story

# FIXTURES = Path(__file__).parent.parent / "fixtures"
ALL_VERSIONS = range(1, 9)


# def fixture_story(version: int) -> Story:
#     (path,) = FIXTURES.glob(f"simple-test-r*-s260727.z{version}")

#     return Story.load(path)


def synthetic_header(version: int = 3, words: dict[int, int] | None = None) -> bytes:
    data = bytearray(HEADER_SIZE)
    data[0] = version

    for offset, value in (words or {}).items():
        data[offset : offset + 2] = value.to_bytes(2, "big")

    return bytes(data)


# The expected releases record what Inform actually emits: 0 for its
# Version 1 and 2 targets, 1 for Version 3 and later. The fixture file
# names carry the same values.
@pytest.mark.parametrize(
    ("version", "release"),
    [(1, 0), (2, 0), (3, 1), (4, 1), (5, 1), (6, 1), (7, 1), (8, 1)],
)
def test_reads_identity_of_every_fixture(
    version: int, release: int, load_fixture: Callable[[int], Story]
) -> None:
    header = load_fixture(version).header

    assert_that(header.version).is_equal_to(version)
    assert_that(header.release).is_equal_to(release)
    assert_that(header.serial_number).is_equal_to("260727")


def test_rejects_content_too_short_for_a_header() -> None:
    with pytest.raises(ZMachineHeaderError, match="63"):
        Header(bytes(HEADER_SIZE - 1))


@pytest.mark.parametrize("version", ALL_VERSIONS)
def test_declared_length_never_exceeds_actual_size(
    version: int, load_fixture: Callable[[int], Story]
) -> None:
    story = load_fixture(version)

    assert_that(story.header.declared_file_length).is_less_than_or_equal_to(
        len(story.data)
    )


@pytest.mark.parametrize(
    ("version", "scaled_length"),
    [
        (1, 512),
        (2, 512),
        (3, 512),
        (4, 1024),
        (5, 1024),
        (6, 2048),
        (7, 2048),
        (8, 2048),
    ],
)
def test_scales_declared_length_by_version(version: int, scaled_length: int) -> None:
    header = Header(synthetic_header(version=version, words={0x1A: 0x0100}))

    assert_that(header.declared_file_length).is_equal_to(scaled_length)


# The declared length (576, stored as 288 under the Version 3 scale
# factor) covers the header plus 512 bytes of 0xFF, whose sum wraps
# modulo $10000: 512 * 0xFF = 0x1FE00 -> 0xFE00. The 0xAA bytes lie
# beyond the declared length, so they are padding, which §15 requires
# excluding from the sum.
def test_computes_checksum_by_the_spec_rule() -> None:
    story = synthetic_header(words={0x1A: 288, 0x1C: 0xFE00})
    story += bytes([0xFF]) * 512
    story += bytes([0xAA]) * 10
    header = Header(story)

    assert_that(header.computed_checksum).is_equal_to(0xFE00)
    assert_that(header.verify()).is_true()


@pytest.mark.parametrize("version", ALL_VERSIONS)
def test_every_fixture_passes_verification(
    version: int, load_fixture: Callable[[int], Story]
) -> None:
    header = load_fixture(version).header

    assert_that(header.verify()).is_true()


def test_detects_corruption_through_verification(
    load_fixture: Callable[[int], Story],
) -> None:
    data = bytearray(load_fixture(3).data)
    data[CHECKSUM_START] ^= 0xFF
    header = Header(bytes(data))

    assert_that(header.verify()).is_false()


@pytest.mark.parametrize("version", [v for v in ALL_VERSIONS if v != PACKED_PC_VERSION])
def test_initial_program_counter_lies_within_the_file(
    version: int, load_fixture: Callable[[int], Story]
) -> None:
    story = load_fixture(version)
    pc = story.header.initial_program_counter

    assert_that(pc).is_greater_than_or_equal_to(HEADER_SIZE)
    assert_that(pc).is_less_than(len(story.data))


def test_version_6_stores_a_packed_routine_address(
    load_fixture: Callable[[int], Story],
) -> None:
    header = load_fixture(6).header

    assert_that(header.main_routine_packed_address).is_greater_than(0)


def test_version_6_refuses_an_initial_program_counter(
    load_fixture: Callable[[int], Story],
) -> None:
    header = load_fixture(6).header

    with pytest.raises(ZMachineHeaderError, match="packed routine address"):
        _ = header.initial_program_counter


def test_other_versions_refuse_a_packed_routine_address(
    load_fixture: Callable[[int], Story],
) -> None:
    header = load_fixture(5).header

    with pytest.raises(ZMachineHeaderError, match="initial program counter"):
        _ = header.main_routine_packed_address


def flagged_header(version: int = 3, flags: int = 0) -> bytes:
    data = bytearray(synthetic_header(version=version))
    data[1] = flags

    return bytes(data)


# A Version 3 game claims an hours:minutes status line with bit 1 of
# Flags 1 (§8.2.3.2); without it, score and turns.
def test_version_3_reads_the_status_line_type() -> None:
    assert_that(Header(flagged_header(flags=0x02)).time_game).is_true()
    assert_that(Header(flagged_header()).time_game).is_false()


# Versions 1 and 2 predate the bit: score and turns, whatever Flags 1
# happens to hold.
def test_early_versions_always_show_score() -> None:
    assert_that(Header(flagged_header(version=1, flags=0x02)).time_game).is_false()


# From Version 4 there is no status line for the bit to describe
# (§8.2).
def test_later_versions_refuse_a_status_line_type() -> None:
    with pytest.raises(ZMachineHeaderError, match="no status line"):
        _ = Header(flagged_header(version=4)).time_game


# The header speaks in absences: bit 4 of Flags 1 set means no status
# line, while bit 5 set means the screen can split (§11.1).
def test_declarations_write_the_capability_bits() -> None:
    header = Header(bytearray(synthetic_header()))

    header.declare_status_line(available=False)
    header.declare_screen_splitting(available=True)

    assert_that(header.data[1]).is_equal_to(0x30)

    header.declare_status_line(available=True)
    header.declare_screen_splitting(available=False)

    assert_that(header.data[1]).is_equal_to(0x00)


def test_declarations_refuse_the_pristine_story() -> None:
    header = Header(synthetic_header())

    with pytest.raises(ZMachineHeaderError, match="pristine"):
        header.declare_status_line(available=False)


# Other versions' Flags 1 bits mean entirely different things
# (§11.1): boldface in Version 4, for one.
def test_declarations_refuse_other_versions() -> None:
    header = Header(bytearray(synthetic_header(version=4)))

    with pytest.raises(ZMachineHeaderError, match="only version 3"):
        header.declare_screen_splitting(available=True)


# From Version 4 the interpreter introduces itself: platform and
# revision at $1e/$1f, screen size at $20/$21, and Flags 1 reborn as
# typography and timing capabilities (§11.1, §11.1.3, §8.4).
def test_version_4_headers_take_the_interpreter_identity() -> None:
    header = Header(bytearray(synthetic_header(version=4)))

    header.introduce_interpreter(6, ord("V"))
    header.declare_screen_size(lines=255, columns=80)
    header.declare_presentation(
        bold=False, italic=False, fixed_pitch=True, timed_input=False
    )

    assert_that(header.data[0x1E]).is_equal_to(6)
    assert_that(header.data[0x1F]).is_equal_to(ord("V"))
    assert_that(header.data[0x20]).is_equal_to(255)
    assert_that(header.data[0x21]).is_equal_to(80)
    assert_that(header.data[1]).is_equal_to(0x10)


# The presentation bits are written both ways, and bits that mean
# other things -- colours, pictures -- are left exactly as found.
def test_presentation_bits_spare_their_neighbours() -> None:
    data = bytearray(synthetic_header(version=5))
    data[1] = 0xFF
    header = Header(data)

    header.declare_presentation(
        bold=False, italic=False, fixed_pitch=False, timed_input=False
    )

    assert_that(header.data[1]).is_equal_to(0xFF ^ 0x9C)


# Flags 2 bit 7 is the game asking for sound effects -- Sherlock in
# Version 5, The Lurking Horror as the one named Version 3 -- and a
# soundless interpreter clears the request so the game plays on in
# silence (§11.1). The neighbouring session bits are left alone.
def test_a_soundless_interpreter_clears_the_sound_request() -> None:
    data = bytearray(synthetic_header(version=3))
    data[0x11] = 0xFF
    header = Header(data)

    header.declare_sound(available=False)

    assert_that(header.data[0x11]).is_equal_to(0x7F)


# An interpreter that can oblige leaves the request standing.
def test_a_sound_interpreter_leaves_the_request_alone() -> None:
    data = bytearray(synthetic_header(version=5))
    data[0x11] = 0x80
    header = Header(data)

    header.declare_sound(available=True)

    assert_that(header.data[0x11]).is_equal_to(0x80)


# The Tandy bit belongs to Version 3's Flags 1 alone: from Version
# 4 the same bit means italics (§11.1.4).
def test_the_tandy_bit_ends_at_version_3() -> None:
    header = Header(bytearray(synthetic_header(version=4)))

    with pytest.raises(ZMachineHeaderError, match="only version 3"):
        header.declare_tandy(on=True)


def test_interpreter_fields_begin_at_version_4() -> None:
    header = Header(bytearray(synthetic_header(version=3)))

    with pytest.raises(ZMachineHeaderError, match="begin at version 4"):
        header.declare_screen_size(lines=255, columns=80)


def test_interpreter_fields_refuse_the_pristine_story() -> None:
    header = Header(synthetic_header(version=4))

    with pytest.raises(ZMachineHeaderError, match="pristine"):
        header.introduce_interpreter(6, ord("V"))


# Offsets here are written out raw, straight from the table in §11.1,
# so this test cannot inherit a mistake in the module's constants.
def test_reads_field_values_from_spec_offsets() -> None:
    header = Header(
        synthetic_header(
            words={
                0x02: 0x0102,
                0x04: 0x2030,
                0x06: 0x2233,
                0x08: 0x0400,
                0x0A: 0x0500,
                0x0C: 0x0600,
                0x0E: 0x0700,
                0x18: 0x0800,
                0x1C: 0xBEEF,
            }
        )
    )

    assert_that(header.release).is_equal_to(0x0102)
    assert_that(header.high_memory_base).is_equal_to(0x2030)
    assert_that(header.initial_program_counter).is_equal_to(0x2233)
    assert_that(header.dictionary_address).is_equal_to(0x0400)
    assert_that(header.object_table_address).is_equal_to(0x0500)
    assert_that(header.global_variables_address).is_equal_to(0x0600)
    assert_that(header.static_memory_base).is_equal_to(0x0700)
    assert_that(header.abbreviations_table_address).is_equal_to(0x0800)
    assert_that(header.stored_checksum).is_equal_to(0xBEEF)


# An interpreter obeying revision n.m writes n at $32 and m at $33
# (§11.1.5) -- on the working image only; the pristine story never
# changes.
def test_the_standard_revision_is_declared() -> None:
    data = bytearray(64)
    data[0] = 3
    header = Header(data)

    header.declare_standard_revision(1, 0)

    assert_that(data[0x32]).is_equal_to(1)
    assert_that(data[0x33]).is_equal_to(0)


def test_the_revision_cannot_be_declared_on_the_pristine_story() -> None:
    data = bytes(64)
    header = Header(bytes([3]) + data[1:])

    with pytest.raises(ZMachineHeaderError, match="pristine"):
        header.declare_standard_revision(1, 0)


# Word 3 of the header extension names a custom Unicode translation
# table; no extension, or one too short, means the default table
# (§3.8.5.2).
def test_the_unicode_table_is_found_through_the_extension() -> None:
    data = bytearray(0x100)
    data[0] = 5
    data[0x36:0x38] = (0x80).to_bytes(2, "big")
    data[0x80:0x82] = (3).to_bytes(2, "big")
    data[0x86:0x88] = (0xBEEF).to_bytes(2, "big")

    assert_that(Header(data).unicode_translation_address).is_equal_to(0xBEEF)


@pytest.mark.parametrize("words", [0, 2])
def test_a_short_or_absent_extension_means_the_default_table(words: int) -> None:
    data = bytearray(0x100)
    data[0] = 5

    if words:
        data[0x36:0x38] = (0x80).to_bytes(2, "big")
        data[0x80:0x82] = words.to_bytes(2, "big")

    assert_that(Header(data).unicode_translation_address).is_zero()
