"""The txd-style listing: code found by decoding it (§4, §14)."""

from collections.abc import Callable
from pathlib import Path

from assertpy import assert_that

from voxam.cli import main
from voxam.frontend import PlainFrontend
from voxam.listing import Tracer, report
from voxam.zmachine.machine import Machine
from voxam.zmachine.story import Story

EXIT_OK = 0
EXIT_UNUSABLE = 2


def crafted(
    cells: dict[int, bytes],
    version: int = 3,
    *,
    size: int = 256,
    high_base: int = 0x40,
    initial_pc: int = 0x41,
) -> Story:
    """Build a story whose code region says exactly what a test needs.

    Static memory opens at $40 so code can follow the header
    immediately; the initial program counter defaults to $41, one
    past an entry routine header at $40. In Version 6 the word at
    $06 is the packed address of the main routine instead.
    """

    data = bytearray(size)
    data[0] = version
    data[0x04:0x06] = high_base.to_bytes(2, "big")
    data[0x06:0x08] = initial_pc.to_bytes(2, "big")
    data[0x0E:0x10] = (0x40).to_bytes(2, "big")

    for at, blob in cells.items():
        data[at : at + len(blob)] = blob

    return Story(bytes(data))


# The word 0xB5C5 is the encoded string "hi": z-chars 13, 14, and a
# padding 5, with the terminator bit set (§3.2, §3.5.3).
HI = bytes([0xB5, 0xC5])


# The whole shape of a listing: the main routine titled as such, a
# call operand unpacked to its $address, a store rider's arrow, a
# Version 3 routine wearing its initial local values, a branch note,
# inline print text, and the strings region closing the file over
# the compiler's zero padding.
def test_a_story_lists_end_to_end() -> None:
    story = crafted(
        {
            0x40: bytes([0x00]),
            # call $0048 -> sp; quit
            0x41: bytes([0xE0, 0x3F, 0x00, 0x24, 0x00, 0xBA]),
            # 2 locals (000a, 0000); je L01, #05 ?rtrue; print "hi";
            # ret_popped
            0x48: bytes([0x02, 0x00, 0x0A, 0x00, 0x00])
            + bytes([0x41, 0x02, 0x05, 0xC1])
            + bytes([0xB2, *HI])
            + bytes([0xB8]),
            0x56: HI,
        }
    )
    text = report(story)

    assert_that(text).contains("[start of code at $0040]")
    assert_that(text).contains("Main routine $0040, 0 locals")
    assert_that(text).contains("  $0041: call            $0048 -> sp")
    assert_that(text).contains("  $0046: quit")
    assert_that(text).contains("Routine $0048, 2 locals (000a, 0000)")
    assert_that(text).contains("  $004d: je              L01, #05 ?rtrue")
    assert_that(text).contains('  $0051: print           "hi"')
    assert_that(text).contains("  $0054: ret_popped")
    assert_that(text).contains("[end of code at $0054]")
    assert_that(text).contains("[start of text at $0056]")
    assert_that(text).contains('  $0056: "hi"')
    assert_that(text).contains("[padding from $0058]")
    assert_that(text).contains("[end of file]")


# The horizon rule: a routine does not end at a return while an
# earlier branch points past it. Here a jz branches over an rtrue
# and a backward jump, so all four instructions belong to one
# routine that only ends at the rfalse the branch reaches -- and a
# jump through a variable ends the next routine on its own, since
# nowhere further is promised.
def test_the_end_of_a_routine_waits_for_its_branches() -> None:
    story = crafted(
        {
            0x40: bytes([0x00]),
            # jz #00 ?$0048; rtrue; jump $0041; rfalse
            0x41: bytes([0x90, 0x00, 0xC6])
            + bytes([0xB0])
            + bytes([0x8C, 0xFF, 0xFB])
            + bytes([0xB1]),
            # je #01, #02 ?~rfalse; jump sp
            0x4A: bytes([0x00, 0x01, 0x01, 0x02, 0x40, 0xAC, 0x00]),
            # jump $0058 forward over two rtrues to the rfalse
            0x52: bytes([0x00, 0x8C, 0x00, 0x04, 0xB0, 0xB0, 0xB1]),
        }
    )
    text = report(story)

    assert_that(text).contains("  $0041: jz              #00 ?$0048")
    assert_that(text).contains("  $0044: rtrue")
    assert_that(text).contains("  $0045: jump            $0041")
    assert_that(text).contains("  $0048: rfalse")
    assert_that(text).contains("  $004b: je              #01, #02 ?~rfalse")
    assert_that(text).contains("  $004f: jump            sp")
    assert_that(text).contains("  $0053: jump            $0058")
    assert_that(text).contains("  $0058: rfalse")
    assert_that(text).contains("[end of code at $0058]")


# Every rejection txd knows turns a stretch into data: a store into
# a local the routine does not have, a branch back past the
# routine's own start, and a jump below the code region. The sweep
# hunts past all three poisoned candidates and lands on the real
# routine beyond them -- and a call whose target could not be a
# routine header still lists, but grows the region nowhere.
def test_rejected_candidates_become_data() -> None:
    story = crafted(
        {
            0x40: bytes([0x00]),
            # call $0068 -> sp; call $0070 -> sp; quit
            0x41: bytes([0xE0, 0x3F, 0x00, 0x34, 0x00])
            + bytes([0xE0, 0x3F, 0x00, 0x38, 0x00])
            + bytes([0xBA]),
            # add #01, #02 -> L05 under a 1-local header
            0x50: bytes([0x01, 0x00, 0x00, 0x14, 0x01, 0x02, 0x06]),
            # jz #00 branching 20 bytes backward, before its start
            0x58: bytes([0x00, 0x90, 0x00, 0xBF, 0xEC]),
            # jump to $0027, below the code region
            0x60: bytes([0x00, 0x8C, 0xFF, 0xC5]),
            0x68: bytes([0x00, 0xB0]),
            0x70: bytes([0xFF]),
        }
    )
    text = report(story)

    assert_that(text).contains("  $0046: call            $0070 -> sp")
    assert_that(text).contains("[data from $004c to $0067]")
    assert_that(text).contains("Routine $0068, 0 locals")
    assert_that(text).does_not_contain("Routine $0070")
    assert_that(text).does_not_contain("$0050,")


# The low scan: routines nobody calls, sitting below the entry
# point, are found when enough of them decode back-to-back -- and
# when nothing below decodes, the code region simply starts at the
# entry (txd).
def test_the_low_scan_finds_uncalled_routines() -> None:
    populated = crafted(
        {
            0x44: bytes([0x00, 0xB0]),
            0x46: bytes([0x00, 0xB0]),
            0x48: bytes([0x00, 0xB0]),
            0x4A: bytes([0x00, 0xBA]),
        },
        high_base=0x44,
        initial_pc=0x4B,
    )
    text = report(populated)

    assert_that(text).contains("[start of code at $0044]")
    assert_that(text).contains("Routine $0044, 0 locals")
    assert_that(text).contains("Main routine $004a, 0 locals")

    # One lone routine below is not enough consecutive evidence,
    # and the junk after it is no routine at all.
    lone = crafted(
        {
            0x40: bytes([0x00, 0xB0]),
            0x42: bytes([0xFF] * 14),
            0x50: bytes([0x00, 0xBA]),
        },
        initial_pc=0x51,
    )

    assert_that(report(lone)).contains("[start of code at $0050]")


# A constant call operand reaching below the known region widens
# it: the sweep restarts from the called routine, and the code
# region opens there.
def test_calls_widen_the_region_downward() -> None:
    story = crafted(
        {
            0x44: bytes([0x00, 0xB0]),
            # call $0044 -> sp; quit
            0x50: bytes([0x00, 0xE0, 0x3F, 0x00, 0x22, 0x00, 0xBA]),
        },
        high_base=0x50,
        initial_pc=0x51,
    )
    text = report(story)

    assert_that(text).contains("[start of code at $0044]")
    assert_that(text).contains("Routine $0044, 0 locals")
    assert_that(text).contains("Main routine $0050, 0 locals")


# Code that decodes without a routine header is an orphan code
# fragment, exactly txd's phrase for it -- and a call inside one
# still leads the sweep onward to the routine it names.
def test_headerless_code_is_an_orphan_fragment() -> None:
    story = crafted(
        {
            0x40: bytes([0x00, 0xBA]),
            # call $004e -> sp; call $0054 -> sp; rtrue -- headerless
            0x42: bytes([0xE0, 0x3F, 0x00, 0x27, 0x00])
            + bytes([0xE0, 0x3F, 0x00, 0x2A, 0x00])
            + bytes([0xB0]),
            0x4E: bytes([0x00, 0xB0]),
            # $0054 could never hold a routine header
            0x54: bytes([0xFF]),
        }
    )
    text = report(story)

    assert_that(text).contains("orphan code fragment:")
    assert_that(text).contains("  $0042: call            $004e -> sp")
    assert_that(text).contains("  $0047: call            $0054 -> sp")
    assert_that(text).contains("  $004c: rtrue")
    assert_that(text).contains("Routine $004e, 0 locals")
    assert_that(text).does_not_contain("Routine $0054")


# Version 5 dresses the richer operands: an aread's interrupt
# routine and a call_vn's target unpack to $addresses, indirect
# variable references wear brackets, print_paddr names the string
# the text section then lists, and a routine header past Version 4
# carries no initial values.
def test_version_5_operands_dress_for_what_they_mean() -> None:
    story = crafted(
        {
            0x40: bytes([0x00]),
            # aread #0100, #00, #0a, $0058 -> sp
            0x41: bytes([0xE4, 0x14, 0x01, 0x00, 0x00, 0x0A, 0x00, 0x16, 0x00]),
            # inc [L00]; store [G00], #05; print_paddr $005c
            0x4A: bytes([0x95, 0x01])
            + bytes([0x0D, 0x10, 0x05])
            + bytes([0x8D, 0x00, 0x17]),
            # call_vn $0058 (#03); quit
            0x52: bytes([0xF9, 0x1F, 0x00, 0x16, 0x03, 0xBA]),
            0x58: bytes([0x01, 0xB0]),
            0x5C: HI,
        },
        version=5,
    )
    text = report(story)

    assert_that(text).contains("  $0041: aread           #0100, #00, #0a, $0058 -> sp")
    assert_that(text).contains("  $004a: inc             [L00]")
    assert_that(text).contains("  $004c: store           [G00], #05")
    assert_that(text).contains("  $004f: print_paddr     $005c")
    assert_that(text).contains("  $0052: call_vn         $0058 (#03)")
    assert_that(text).contains("Routine $0058, 1 local")
    assert_that(text).contains('  $005c: "hi"')


# Code running to the file's very edge leaves no strings region and
# no room for another routine -- the listing simply ends; and a
# tail that is garbage rather than padding is reported unreadable.
def test_the_files_edge_and_unreadable_tails_stay_loud() -> None:
    flush = crafted(
        {0x40: bytes([0x00, 0xBA])},
        size=0x42,
    )

    assert_that(report(flush)).contains("[end of code at $0041]")
    assert_that(report(flush)).does_not_contain("[start of text")

    garbled = crafted(
        {
            0x40: bytes([0x00, 0xBA]),
            0x44: bytes([0x12, 0x34] * 4),
        },
        size=0x4C,
    )

    assert_that(report(garbled)).contains("[unreadable text from $0042]")

    # A string ending exactly at the file's edge closes the report
    # with no marker at all: there was nothing after it to explain.
    flush_text = crafted(
        {0x40: bytes([0x00, 0xBA]), 0x42: HI},
        size=0x44,
    )
    tail = report(flush_text)

    assert_that(tail).contains('  $0042: "hi"')
    assert_that(tail).contains("[end of file]")
    assert_that(tail).does_not_contain("padding")
    assert_that(tail).does_not_contain("unreadable")


# The trace is the listing's live sibling: a machine wearing the
# witness writes every executed instruction in execution order,
# rendered exactly as the listing renders it, and the closing line
# tallies instructions and distinct addresses -- the golden trace
# another interpreter can diff against.
def test_a_traced_machine_writes_its_golden_trace() -> None:
    story = crafted(
        {
            0x40: bytes([0x00]),
            0x41: bytes([0xB2, *HI, 0xBA]),
        }
    )
    lines: list[str] = []
    printed: list[str] = []
    tracer = Tracer(lines.append)
    machine = Machine(story, PlainFrontend(printed.append), witness=tracer.see)

    machine.run()
    tracer.close()

    assert_that(printed).contains("hi")
    assert_that(lines).is_equal_to(
        [
            '  $0041: print           "hi"\n',
            "  $0044: quit\n",
            "\n[end of trace: 2 instructions at 2 distinct addresses]\n",
        ]
    )


# The real compiled fixtures list whole in every version family:
# the packed Version 6 main routine included, each report opening
# and closing its regions.
def test_the_fixture_stories_list_whole(
    load_fixture: Callable[[int], Story],
) -> None:
    for version in (1, 3, 4, 6, 8):
        text = report(load_fixture(version))

        assert_that(text).contains("Main routine")
        assert_that(text).contains("[end of code")
        assert_that(text).contains("[start of text")
        assert_that(text).contains("[end of file]")


# --listing prints the report and exits cleanly; it needs a story,
# refuses the session flags, and will not share the stage with
# --header.
def test_the_listing_flag_reports_and_refuses(
    fixture_path: Callable[[int], Path],
    capsys: object,
) -> None:
    exit_code = main(["--listing", str(fixture_path(3))])
    out = capsys.readouterr().out  # type: ignore[attr-defined]

    assert_that(exit_code).is_equal_to(EXIT_OK)
    assert_that(out).contains("[start of code")

    assert_that(main(["--listing"])).is_equal_to(EXIT_UNUSABLE)
    assert_that(capsys.readouterr().out).contains(  # type: ignore[attr-defined]
        "needs a story"
    )

    combined = main(["--listing", "--accept", "x.accept", str(fixture_path(3))])

    assert_that(combined).is_equal_to(EXIT_UNUSABLE)
    assert_that(capsys.readouterr().out).contains(  # type: ignore[attr-defined]
        "drop the session flags"
    )

    both = main(["--listing", "--header", str(fixture_path(3))])

    assert_that(both).is_equal_to(EXIT_UNUSABLE)
    assert_that(capsys.readouterr().out).contains(  # type: ignore[attr-defined]
        "pick one"
    )
