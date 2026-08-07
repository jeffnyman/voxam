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
