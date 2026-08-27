"""Synthetic tests for the Å-machine's opcodes and refusals.

Each story here is a tiny hand-assembled program built around one
seam: the code bytes are spelled out operand by operand, and the
outcome is read back out of the plain voice's telling. The guard
pattern leans on the machine's own error contract -- a runtime
fault restarts execution at address 1 with the error's number in
R00, so a guarded program simply prints R00 when it comes back
nonzero (Aa-machine: Runtime data).
"""

import zlib

import pytest
from assertpy import assert_that

from voxam.aamachine.machine import Machine, walked
from voxam.aamachine.output import PlainVoice
from voxam.aamachine.story import SUMMED, Story
from voxam.errors import AAMachineError
from voxam.iff import chunk as iff_chunk

# A two-entry decoding table: entry 0 spells $ or jumps on; entry
# 1 spells the letter a or ends the string.
TABLE = bytes([0x04, 0x81, 0x41, 0x80])

# WRIT built on that table: "$" at byte 0, "a" at byte 2 -- both
# on even addresses, where tiny string pointers can reach.
WRIT = bytes([0b01100000, 0x00, 0b10110000])

QUIT = bytes([0x70, 0x00])


def immediate(value: int) -> bytes:
    """A VALUE, RAW, VWORD, or WORD immediate operand."""

    return bytes([value >> 8, value & 0xFF])


def absolute(at: int) -> bytes:
    """An absolute CODE operand."""

    return bytes([0x80 | (at >> 16), (at >> 8) & 0xFF, at & 0xFF])


def printed(reg: int) -> bytes:
    """PRINT_VAL of a register."""

    return bytes([0x65, 0x80 | reg])


def shown(value: int) -> bytes:
    """PRINT_VAL of an immediate."""

    return bytes([0x65]) + immediate(value)


def guarded(main: bytes) -> bytes:
    """A program whose entry reports a nonzero R00 and quits.

    The engine restarts at address 1 with the error in R00 after
    a runtime fault; the guard prints it and stops, so a test can
    read the error number straight out of the telling.
    """

    err_at = 1 + 7 + len(main)

    return bytes([0x40, 0x00, 0x00, 0x80]) + absolute(err_at) + main + printed(0) + QUIT


def caught(main: bytes, told: int = 0x4009) -> bytes:
    """A program whose failures land at a printing choice point."""

    handler_at = 1 + 5 + len(main) + len(QUIT)

    return bytes([0x0A, 0x00]) + absolute(handler_at) + main + QUIT + shown(told) + QUIT


def langed(
    table: bytes = TABLE,
    extended: tuple[tuple[int, int, int], ...] = (),
    endings: bytes = b"\x00",
    stops: bytes = b"",
    before: bytes = b"",
    after: bytes = b"",
) -> bytes:
    """A LANG payload with all four decoder regions present.

    Extended entries are (lower, upper, codepoint) triples, the
    chunk's own shape.
    """

    charactered = bytes([len(extended)]) + b"".join(
        bytes([lower, upper]) + point.to_bytes(3, "big")
        for lower, upper, point in extended
    )
    table_at = 8
    ext_at = table_at + len(table)
    endings_at = ext_at + len(charactered)
    special_at = endings_at + len(endings)

    return (
        table_at.to_bytes(2, "big")
        + ext_at.to_bytes(2, "big")
        + endings_at.to_bytes(2, "big")
        + special_at.to_bytes(2, "big")
        + table
        + charactered
        + endings
        + stops
        + b"\x00"
        + before
        + b"\x00"
        + after
        + b"\x00"
    )


def worded(*words: bytes) -> bytes:
    """A DICT payload holding the given words."""

    table_end = 2 + 3 * len(words)
    entries = []
    arrays = []
    at = table_end

    for word in words:
        entries.append(bytes([len(word)]) + at.to_bytes(2, "big"))
        arrays.append(word)
        at += len(word)

    return len(words).to_bytes(2, "big") + b"".join(entries) + b"".join(arrays)


def roomy(
    nob: int = 0, fields: int = 8, top: int = 8, longterm: int = 16
) -> tuple[bytes, int]:
    """An INIT payload with an object table, and the ram size to fit.

    The global data sits after the offsets, each object's fields
    after that, and the long-term area stands empty at the tail.
    """

    offsets = [nob + 1] + [nob + 1 + top + seat * fields for seat in range(nob)]
    data = [0] * (top + nob * fields)
    ltb = len(offsets) + len(data)
    payload = (
        nob.to_bytes(2, "big")
        + ltb.to_bytes(2, "big")
        + ltb.to_bytes(2, "big")
        + b"".join(word.to_bytes(2, "big") for word in offsets + data)
    )

    return payload, ltb + longterm


def crafted(
    code: bytes,
    *,
    version: tuple[int, int] = (0, 5),
    heap: int = 64,
    aux: int = 32,
    init: "bytes | None" = None,
    ram: "int | None" = None,
    lang: "bytes | None" = None,
    dictionary: bytes = b"\x00\x00",
    maps: bytes = b"\x00\x00",
    look: bytes = b"\x00\x00",
    writ: bytes = WRIT,
    tags: "bytes | None" = None,
) -> Story:
    """A story around a code body; address 0 gains its FAIL."""

    if init is None:
        init, sized = roomy()
        ram = sized if ram is None else ram

    summed = {
        b"LANG": langed() if lang is None else lang,
        b"DICT": dictionary,
        b"MAPS": maps,
        b"LOOK": look,
        b"WRIT": writ,
        b"INIT": init,
        b"CODE": b"\x01" + code,
    }
    crc = 0

    for name in SUMMED:
        crc = zlib.crc32(summed.get(name, b""), crc)

    head = (
        bytes([*version, 2, 0])
        + (1).to_bytes(2, "big")
        + b"260827"
        + crc.to_bytes(4, "big")
        + heap.to_bytes(2, "big")
        + aux.to_bytes(2, "big")
        + (ram or 64).to_bytes(2, "big")
    )
    pieces = [iff_chunk(b"HEAD", head)]

    for name in SUMMED:
        pieces.append(iff_chunk(name, summed.get(name, b"")))

    if tags is not None:
        pieces.append(iff_chunk(b"TAGS", tags))

    return Story(iff_chunk(b"FORM", b"AAVM" + b"".join(pieces)))


def spoken(story: Story, *lines: str) -> str:
    """Run a crafted story, feeding lines; the telling comes back."""

    voice = PlainVoice(story)
    machine = Machine(story, voice, seed=7)
    waiting = machine.run()

    for line in lines:
        if waiting == "line":
            waiting = machine.deliver_line(line)
        else:
            waiting = machine.deliver_key(ord(line))

    return voice.told()


class RecordingVoice(PlainVoice):
    """A plain voice that also notes the machine's structural calls."""

    def __init__(self, story: Story) -> None:
        super().__init__(story)
        self.noted: list[tuple[object, ...]] = []

    def enter_span(self, style: int) -> None:
        self.noted.append(("enter_span", style))

    def leave_span(self) -> None:
        self.noted.append(("leave_span",))

    def set_body(self, style: int) -> None:
        self.noted.append(("set_body", style))

    def enter_link(self, words: str) -> None:
        self.noted.append(("enter_link", words))

    def leave_link(self) -> None:
        self.noted.append(("leave_link",))

    def enter_link_res(self, resource: int) -> None:
        self.noted.append(("enter_link_res", resource))

    def leave_link_res(self) -> None:
        self.noted.append(("leave_link_res",))

    def enter_self_link(self) -> None:
        self.noted.append(("enter_self_link",))

    def leave_self_link(self) -> None:
        self.noted.append(("leave_self_link",))

    def set_style(self, bits: int) -> None:
        self.noted.append(("set_style", bits))

    def reset_style(self, bits: int) -> None:
        self.noted.append(("reset_style", bits))

    def unstyle(self) -> None:
        self.noted.append(("unstyle",))

    def embed_res(self, resource: int) -> None:
        self.noted.append(("embed_res", resource))

    def progress(self, amount: int, total: int) -> None:
        self.noted.append(("progress", amount, total))

    def clear_links(self) -> None:
        self.noted.append(("clear_links",))

    def clear_old(self) -> None:
        self.noted.append(("clear_old",))

    def clear_div(self) -> None:
        self.noted.append(("clear_div",))

    def clear_status(self) -> None:
        self.noted.append(("clear_status",))

    def enter_div(self, style: int) -> None:
        self.noted.append(("enter_div", style))
        super().enter_div(style)

    def clear(self) -> None:
        self.noted.append(("clear",))
        super().clear()

    def clear_all(self) -> None:
        self.noted.append(("clear_all",))
        super().clear_all()

    def trace(self, text: str) -> None:
        self.noted.append(("trace", text))


def recorded(story: Story) -> RecordingVoice:
    """Run a crafted story against a recording voice."""

    voice = RecordingVoice(story)
    Machine(story, voice, seed=7).run()

    return voice


# -- refusals ----------------------------------------------------------


# An opcode the engine does not carry is a loud frontier report,
# named by address, not a silent skip.
def test_an_unknown_opcode_is_refused() -> None:
    story = crafted(bytes([0x71]))
    machine = Machine(story, PlainVoice(story))

    with pytest.raises(AAMachineError, match=r"opcode 0x71 at \$000001"):
        machine.run()


# An EXT0 selector the engine does not carry is equally loud.
def test_an_unknown_ext0_is_refused() -> None:
    story = crafted(bytes([0x70, 0x7E]))
    machine = Machine(story, PlainVoice(story))

    with pytest.raises(AAMachineError, match=r"EXT0 0x7e"):
        machine.run()


# A failure with no choice frame anywhere has no handler to name;
# the engine refuses rather than reading past the heap.
def test_a_failure_with_no_choice_frame_is_refused() -> None:
    story = crafted(bytes([0x01]))
    machine = Machine(story, PlainVoice(story))

    with pytest.raises(AAMachineError, match=r"no choice frame"):
        machine.run()


# A VM_INFO selector past $7f is undefined by the spec's own word.
def test_an_undefined_vm_info_selector_is_refused() -> None:
    story = crafted(bytes([0x74, 0x80, 0x00]))
    machine = Machine(story, PlainVoice(story))

    with pytest.raises(AAMachineError, match=r"selector 0x80"):
        machine.run()


# Popping the aux stack past its own bottom is a wiring fault the
# engine names rather than wrapping around.
def test_an_aux_underflow_is_refused() -> None:
    story = crafted(bytes([0x16, 0x00]))
    machine = Machine(story, PlainVoice(story))

    with pytest.raises(AAMachineError, match=r"past its own bottom"):
        machine.run()


# LEAVE_STATUS moved seats at 1.0: the old byte in a new story --
# and the new byte in an old story -- are both refused by era.
def test_leave_status_is_era_checked() -> None:
    old_in_new = crafted(bytes([0xE7]), version=(1, 0))

    with pytest.raises(AAMachineError, match=r"not LEAVE_STATUS in a format 1"):
        Machine(old_in_new, PlainVoice(old_in_new)).run()

    new_in_old = crafted(bytes([0xEF]))

    with pytest.raises(AAMachineError, match=r"not LEAVE_STATUS in a format 0"):
        Machine(new_in_old, PlainVoice(new_in_old)).run()


# A LANG special-character set without its null ending is refused
# at the machine's door.
def test_an_unterminated_special_set_is_refused() -> None:
    story = crafted(QUIT, lang=langed()[:-1])

    with pytest.raises(AAMachineError, match=r"missing its null"):
        Machine(story, PlainVoice(story))


# Before format 0.4 the LANG chunk carries only the stop set; the
# whitespace inhibitors stand empty and the story still runs.
def test_an_old_story_has_one_special_set() -> None:
    story = crafted(QUIT, version=(0, 3), lang=langed()[:-2])
    machine = Machine(story, PlainVoice(story))

    assert_that(machine.run()).is_equal_to("quit")


# -- the runtime error reports -----------------------------------------


# A heap too small for an environment frame restarts the machine
# with error 1 in R00, which the guard program prints.
def test_a_full_heap_env_reports_error_one() -> None:
    story = crafted(guarded(bytes([0x08, 0x3F])), heap=8)

    assert_that(spoken(story)).contains("1")


# A choice frame past the heap reports the same exhaustion.
def test_a_full_heap_choice_reports_error_one() -> None:
    story = crafted(guarded(bytes([0x0A, 0x3F]) + absolute(0)), heap=8)

    assert_that(spoken(story)).contains("1")


# A stop frame with no aux room reports exhaustion 2.
def test_a_full_aux_stop_reports_error_two() -> None:
    story = crafted(guarded(bytes([0x1D]) + absolute(0)), aux=0)

    assert_that(spoken(story)).contains("2")


# Binding a variable with the trail already against the stack
# reports exhaustion 2 as well.
def test_a_full_trail_reports_error_two() -> None:
    main = bytes([0x11, 0x01, 0x11, 0x02, 0x10, 0x81, 0x82])
    story = crafted(guarded(main), aux=0)

    assert_that(spoken(story)).contains("2")


# SET_PARENT of a number reports a type error 3.
def test_set_parent_of_a_number_reports_error_three() -> None:
    init, ram = roomy(nob=2)
    main = bytes([0x2E]) + immediate(0x4001) + immediate(0x0001)
    story = crafted(guarded(main), init=init, ram=ram)

    assert_that(spoken(story)).contains("3")


# Writing a field of an object past the count reports error 3.
def test_a_field_of_a_missing_object_reports_error_three() -> None:
    init, ram = roomy(nob=1)
    main = bytes([0x24]) + immediate(0x0005) + bytes([0x00]) + immediate(1)
    story = crafted(guarded(main), init=init, ram=ram)

    assert_that(spoken(story)).contains("3")


# Storing a value that still holds an unbound variable long-term
# reports error 4: only bound data survives the heap.
def test_storing_an_unbound_value_reports_error_four() -> None:
    init, ram = roomy(nob=1)
    main = (
        bytes([0x11, 0x01])
        + bytes([0x12, 0x81, 0x02, 0x03])
        + bytes([0xA6, 0x00, 0x83])
    )
    story = crafted(guarded(main), init=init, ram=ram)

    assert_that(spoken(story)).contains("4")


# A long-term area too small for a serialized list reports 6.
def test_a_full_longterm_area_reports_error_six() -> None:
    init, ram = roomy(longterm=1)
    main = (
        bytes([0x13, 0x40, 0x01, 0x02, 0x03])
        + bytes([0x10])
        + immediate(0x3F00)
        + bytes([0x82])
        + bytes([0xA6, 0x00, 0x83])
    )
    story = crafted(guarded(main), init=init, ram=ram)

    assert_that(spoken(story)).contains("6")


# ENTER_DIV inside a span is an invalid output state, error 7.
def test_a_div_inside_a_span_reports_error_seven() -> None:
    story = crafted(guarded(bytes([0x6E, 0x00, 0x66, 0x00])))

    assert_that(spoken(story)).contains("7")


# ENTER_STATUS inside a span reports the same error 7.
def test_a_status_inside_a_span_reports_error_seven() -> None:
    story = crafted(guarded(bytes([0x6E, 0x00, 0x6F, 0x00, 0x00])))

    assert_that(spoken(story)).contains("7")


# SET_BODY inside a span, the 1.0 shape of $67, reports error 7.
def test_set_body_inside_a_span_reports_error_seven() -> None:
    story = crafted(guarded(bytes([0x6E, 0x00, 0x67, 0x00])), version=(1, 0))

    assert_that(spoken(story)).contains("7")


# SAVE inside a span reports error 7 before any file is asked for.
def test_save_inside_a_span_reports_error_seven() -> None:
    main = bytes([0x6E, 0x00, 0x72]) + absolute(0)
    story = crafted(guarded(main))

    assert_that(spoken(story)).contains("7")


# SAVE_UNDO inside a span reports error 7 as well.
def test_save_undo_inside_a_span_reports_error_seven() -> None:
    main = bytes([0x6E, 0x00, 0xF2]) + absolute(0)
    story = crafted(guarded(main))

    assert_that(spoken(story)).contains("7")


# CLEAR_OLD inside a span reports error 7.
def test_clear_old_inside_a_span_reports_error_seven() -> None:
    story = crafted(guarded(bytes([0x6E, 0x00, 0x70, 0x10])))

    assert_that(spoken(story)).contains("7")


# CLEAR_STATUS from inside a status area reports error 7.
def test_clear_status_inside_a_status_reports_error_seven() -> None:
    story = crafted(guarded(bytes([0x6F, 0x00, 0x00, 0x70, 0x12])))

    assert_that(spoken(story)).contains("7")


# CLEAR from inside a span reports error 7.
def test_clear_inside_a_span_reports_error_seven() -> None:
    story = crafted(guarded(bytes([0x6E, 0x00, 0x70, 0x06])))

    assert_that(spoken(story)).contains("7")


# -- arithmetic --------------------------------------------------------


# ADD_RAW and SUB_RAW work on raw sixteen-bit words: adding 3 to
# the tagged number 5 lands on the tagged number 8.
def test_raw_arithmetic_carries_whole_words() -> None:
    main = (
        bytes([0x50])
        + immediate(0x4005)
        + immediate(3)
        + bytes([0x01])
        + printed(1)
        + bytes([0x51, 0x81])
        + immediate(3)
        + bytes([0x02])
        + printed(2)
    )
    story = crafted(main + QUIT)

    assert_that(spoken(story)).contains("8").contains("5")


# RAND_RAW with a zero bound can only roll zero.
def test_rand_raw_with_a_zero_bound_rolls_zero() -> None:
    main = (
        bytes([0x52, 0x00, 0x01])
        + bytes([0x50, 0x81])
        + immediate(0x4000)
        + bytes([0x01])
        + printed(1)
    )
    story = crafted(main + QUIT)

    assert_that(spoken(story)).contains("0")


# DIV_NUM by zero fails to the choice point rather than crashing.
def test_division_by_zero_fails() -> None:
    main = bytes([0x5C]) + immediate(0x4006) + immediate(0x4000) + bytes([0x01])
    story = crafted(caught(main))

    assert_that(spoken(story)).contains("9")


# MOD_NUM by zero fails the same way.
def test_remainder_by_zero_fails() -> None:
    main = bytes([0x5D]) + immediate(0x4006) + immediate(0x4000) + bytes([0x01])
    story = crafted(caught(main))

    assert_that(spoken(story)).contains("9")


# RAND_NUM with an empty range fails.
def test_a_backward_random_range_fails() -> None:
    main = bytes([0x5A]) + immediate(0x4005) + immediate(0x4002) + bytes([0x01])
    story = crafted(caught(main))

    assert_that(spoken(story)).contains("9")


# ADD_NUM of a non-number fails through the unboxing.
def test_adding_an_object_fails() -> None:
    main = bytes([0x58]) + immediate(0x0001) + immediate(0x4001) + bytes([0x01])
    story = crafted(caught(main))

    assert_that(spoken(story)).contains("9")


# -- values spelled out ------------------------------------------------


# The empty list, an unbound variable, and an improper list all
# have PRINT_VAL spellings of their own.
def test_odd_values_spell_themselves() -> None:
    main = (
        shown(0x3F00)
        + bytes([0x11, 0x01])
        + printed(1)
        + bytes([0x13, 0x40, 0x01, 0x02, 0x03])
        + bytes([0x10])
        + immediate(0x4002)
        + bytes([0x82])
        + printed(3)
    )
    story = crafted(main + QUIT)

    assert_that(spoken(story)).contains("[]").contains("$").contains("[1 | 2]")


# An object prints its TAGS name after the hashmark when the
# chunk is aboard, and the bare hashmark when it is not.
def test_objects_print_their_tags_names() -> None:
    init, ram = roomy(nob=1)
    tagged = crafted(
        shown(0x0001) + QUIT,
        init=init,
        ram=ram,
        tags=(1).to_bytes(2, "big") + (4).to_bytes(2, "big") + b"lamp\x00",
    )

    assert_that(spoken(tagged)).contains("#lamp")

    bare = crafted(shown(0x0001) + QUIT, init=init, ram=ram)

    assert_that(spoken(bare)).contains("#")


# An extended character prints through the story's own table.
def test_an_extended_character_prints() -> None:
    story = crafted(shown(0x3E80) + QUIT, lang=langed(extended=((0x80, 0x80, 0xC5),)))

    assert_that(spoken(story)).contains("Å")


# UPPERCASE arms exactly one character: an ASCII letter rises,
# and an extended letter rises through the table's upper seat.
def test_uppercase_arms_one_character() -> None:
    lang = langed(extended=((0x80, 0x81, 0xE5), (0x81, 0x81, 0xC5)))
    main = (
        bytes([0x70, 0x0E])
        + shown(0x3E61)
        + bytes([0x70, 0x0E])
        + shown(0x3E80)
        + shown(0x3E61)
    )
    story = crafted(main + QUIT, lang=lang)

    assert_that(spoken(story)).contains("A").contains("Å").contains("a")


# -- lists and words ---------------------------------------------------


# SPLIT_WORD spells a dictionary word, a character, and a number
# into their lists; digits inside a word arrive as numbers.
def test_split_word_spells_lists() -> None:
    main = (
        bytes([0x1F])
        + immediate(0x2001)
        + bytes([0x01])
        + printed(1)
        + bytes([0x1F])
        + immediate(0x3E62)
        + bytes([0x02])
        + printed(2)
        + bytes([0x1F])
        + immediate(0x4159)
        + bytes([0x03])
        + printed(3)
    )
    story = crafted(main + QUIT, dictionary=worded(b"go", b"a1"))

    assert_that(spoken(story)).contains("[a 1]").contains("[b]").contains("[3 4 5]")


# SPLIT_WORD of something wordless fails.
def test_split_word_of_a_number_pair_fails() -> None:
    main = (
        bytes([0x13, 0x40, 0x01, 0x02, 0x03])
        + bytes([0x10])
        + immediate(0x3F00)
        + bytes([0x82])
        + bytes([0x1F, 0x83, 0x04])
    )
    story = crafted(caught(main))

    assert_that(spoken(story)).contains("9")


# SPLIT_LIST copies a list up to a tail; with the empty list as
# the end, the whole list is copied cell by cell.
def test_split_list_copies_the_whole_list() -> None:
    main = (
        bytes([0x73, 0x00])
        + bytes([0x1B, 0x80])
        + immediate(0x3F00)
        + bytes([0x01])
        + printed(1)
    )
    story = crafted(main + QUIT)

    assert_that(spoken(story, "a b c")).contains("[a b c]")


# JOIN_WORDS glues a word list back into one word: letters,
# numbers, and dictionary words all flatten.
def test_join_words_glues_a_word() -> None:
    main = bytes([0x73, 0x00]) + bytes([0x9F, 0x80, 0x01]) + printed(1)
    story = crafted(main + QUIT, dictionary=worded(b"go"))

    assert_that(spoken(story, "go 12")).contains("go12")


# JOIN_WORDS of a lone character is that character, even one the
# story treats as a stop.
def test_join_words_keeps_a_lone_character() -> None:
    main = bytes([0x73, 0x00, 0x9F, 0x80, 0x01]) + printed(1)
    story = crafted(main + QUIT, lang=langed(stops=b"."))

    assert_that(spoken(story, ".")).contains(".")


# JOIN_WORDS fails on a stop character inside a longer list.
def test_join_words_refuses_an_inner_stop() -> None:
    main = bytes([0x73, 0x00, 0x9F, 0x80, 0x01])
    story = crafted(caught(main), lang=langed(stops=b"."), dictionary=worded(b"go"))

    assert_that(spoken(story, ". go")).contains("9")


# JOIN_WORDS fails on anything but a pair.
def test_join_words_refuses_a_bare_number() -> None:
    main = bytes([0x9F]) + immediate(0x4001) + bytes([0x01])
    story = crafted(caught(main))

    assert_that(spoken(story)).contains("9")


# JOIN_WORDS fails on an improper list.
def test_join_words_refuses_an_improper_list() -> None:
    main = (
        bytes([0x13, 0x3E, 0x61, 0x02, 0x03])
        + bytes([0x10])
        + immediate(0x4002)
        + bytes([0x82])
        + bytes([0x9F, 0x83, 0x04])
    )
    story = crafted(caught(main))

    assert_that(spoken(story)).contains("9")


# The aux stack serializes an unbound variable to a marker and
# revives it as a fresh variable.
def test_aux_serialization_carries_the_unbound() -> None:
    main = (
        bytes([0x94])
        + bytes([0x11, 0x01])
        + bytes([0x14, 0x81])
        + bytes([0x16, 0x02])
        + printed(2)
    )
    story = crafted(main + QUIT)

    assert_that(spoken(story)).contains("$")


# The aux stack serializes an improper list and revives it whole.
def test_aux_serialization_carries_the_improper() -> None:
    main = (
        bytes([0x13, 0x40, 0x01, 0x02, 0x03])
        + bytes([0x10])
        + immediate(0x4002)
        + bytes([0x82])
        + bytes([0x14, 0x83])
        + bytes([0x16, 0x04])
        + printed(4)
    )
    story = crafted(main + QUIT)

    assert_that(spoken(story)).contains("[1 | 2]")


# -- long-term storage -------------------------------------------------


# A stored list survives a rearrangement: freeing an earlier chunk
# slides the later one down and repoints its owner.
def test_longterm_storage_survives_a_slide() -> None:
    init, ram = roomy(nob=1, longterm=32)
    main = (
        bytes([0x73, 0x00])
        + bytes([0xA6, 0x00, 0x80])
        + bytes([0xA6, 0x01, 0x80])
        + bytes([0xA6, 0x00])
        + immediate(0x4001)
        + bytes([0xA2, 0x01, 0x01])
        + printed(1)
    )
    story = crafted(main + QUIT, init=init, ram=ram)

    assert_that(spoken(story, "a zz")).contains("[a zz]")


# An improper list survives long-term storage too.
def test_longterm_storage_carries_the_improper() -> None:
    init, ram = roomy(nob=1)
    main = (
        bytes([0x13, 0x40, 0x01, 0x02, 0x03])
        + bytes([0x10])
        + immediate(0x4002)
        + bytes([0x82])
        + bytes([0xA6, 0x00, 0x83])
        + bytes([0xA2, 0x00, 0x04])
        + printed(4)
    )
    story = crafted(main + QUIT, init=init, ram=ram)

    assert_that(spoken(story)).contains("[1 | 2]")


# LOAD_VAL of a never-written field fails.
def test_loading_an_empty_field_fails() -> None:
    init, ram = roomy(nob=1)
    main = bytes([0xA2, 0x02, 0x01])
    story = crafted(caught(main), init=init, ram=ram)

    assert_that(spoken(story)).contains("9")


# -- the object tree ---------------------------------------------------


# UNLINK removes an object from a chain rooted in another field,
# and quietly ignores a non-object key.
def test_unlink_removes_from_a_chain() -> None:
    init, ram = roomy(nob=2)
    main = (
        bytes([0xA4, 0x04])
        + immediate(0x0001)
        + bytes([0x24])
        + immediate(0x0001)
        + bytes([0x04])
        + immediate(0x0002)
        + bytes([0xAD, 0x04, 0x04])
        + immediate(0x0002)
        + bytes([0x20])
        + immediate(0x0001)
        + bytes([0x04, 0x01])
        + bytes([0x50, 0x81])
        + immediate(0x4000)
        + bytes([0x01])
        + printed(1)
        + bytes([0x2D])
        + immediate(0)
        + bytes([0x04, 0x04])
        + immediate(0x4001)
    )
    story = crafted(main + QUIT, init=init, ram=ram)

    assert_that(spoken(story)).contains("0")


# -- branches and checks -----------------------------------------------


# IF_MEM_EQ jumps when the field matches its raw operand.
def test_if_mem_eq_jumps_on_a_match() -> None:
    init, ram = roomy(nob=1)
    main = (
        bytes([0xA4, 0x00])
        + immediate(5)
        + bytes([0x3A])
        + immediate(0)
        + bytes([0x00])
        + immediate(5)
        + absolute(0x20)
    )
    landing = shown(0x4002) + QUIT
    at = 1 + len(main) + len(shown(0x4001) + QUIT)
    main = (
        bytes([0xA4, 0x00])
        + immediate(5)
        + bytes([0x3A])
        + immediate(0)
        + bytes([0x00])
        + immediate(5)
        + absolute(at)
    )
    story = crafted(main + shown(0x4001) + QUIT + landing, init=init, ram=ram)

    assert_that(spoken(story)).contains("2")


# CHECK_GT_EQ splits three ways on IDX.
def test_check_gt_eq_splits_three_ways() -> None:
    def program(idx: int) -> Story:
        head = bytes([0x78]) + immediate(idx) + bytes([0x7A]) + immediate(0x4004)
        above_at = 1 + len(head) + 6 + len(shown(0x4003) + QUIT)
        equal_at = above_at + len(shown(0x4001) + QUIT)
        body = (
            head
            + absolute(above_at)
            + absolute(equal_at)
            + shown(0x4003)
            + QUIT
            + shown(0x4001)
            + QUIT
            + shown(0x4002)
            + QUIT
        )

        return crafted(body)

    assert_that(spoken(program(0x4005))).contains("1")
    assert_that(spoken(program(0x4004))).contains("2")
    assert_that(spoken(program(0x4003))).contains("3")


# CHECK_GT jumps in both its RAW and BYTE shapes.
def test_check_gt_jumps_in_both_shapes() -> None:
    head = bytes([0x78]) + immediate(0x4005) + bytes([0x7B]) + immediate(0x4001)
    at = 1 + len(head) + 3 + len(shown(0x4001) + QUIT)
    body = head + absolute(at) + shown(0x4001) + QUIT + shown(0x4002) + QUIT

    assert_that(spoken(crafted(body))).contains("2")

    head = bytes([0x78]) + immediate(0x0005) + bytes([0xFB, 0x01])
    at = 1 + len(head) + 3 + len(shown(0x4001) + QUIT)
    body = head + absolute(at) + shown(0x4001) + QUIT + shown(0x4002) + QUIT

    assert_that(spoken(crafted(body))).contains("2")


# IF_UNIFY sees two separately-typed unknown words as one.
def test_if_unify_matches_twin_unknown_words() -> None:
    head = (
        bytes([0x73, 0x00])
        + bytes([0x12, 0x01, 0x02, 0x80])
        + bytes([0x12, 0x03, 0x04, 0x82])
        + bytes([0x37, 0x81, 0x83])
    )
    at = 1 + len(head) + 3 + len(shown(0x4001) + QUIT)
    body = head + absolute(at) + shown(0x4001) + QUIT + shown(0x4002) + QUIT
    story = crafted(body)

    assert_that(spoken(story, "qq qq")).contains("2")


# -- the wordmaps ------------------------------------------------------


def mapped_story(idx: int) -> Story:
    """A story consulting a three-entry wordmap for the given IDX.

    The map knows 'go' as a wildcard, dict word 1 as one object,
    and the period as a payload of two -- one of them wide.
    """

    entries = (
        immediate(0x2000)
        + immediate(0)
        + immediate(0x2001)
        + immediate(0xE000 | 2)
        + immediate(0x3E2E)
        + immediate(18)
    )
    table = immediate(3) + entries + bytes([0x01, 0xE0, 0x02, 0x00])
    maps = immediate(1) + immediate(4) + table
    head = bytes([0x94]) + bytes([0x78]) + immediate(idx) + bytes([0x7C, 0x00])
    at = 1 + len(head) + 3 + len(shown(0x4001) + QUIT)
    landing = bytes([0x17, 0x01]) + printed(1) + QUIT
    body = head + absolute(at) + shown(0x4001) + QUIT + landing
    init, ram = roomy(nob=2)

    return crafted(body, maps=maps, init=init, ram=ram, dictionary=worded(b"go", b"at"))


# A wildcard word matches everything: no jump, nothing pushed.
def test_a_wildcard_word_stays_on_the_path() -> None:
    assert_that(spoken(mapped_story(0x2000))).contains("1")


# A single-object word pushes its object and jumps.
def test_a_single_object_word_jumps_with_its_object() -> None:
    assert_that(spoken(mapped_story(0x2001))).contains("[#]")


# A payload word pushes its whole list, wide ids included.
def test_a_payload_word_jumps_with_its_objects() -> None:
    assert_that(spoken(mapped_story(0x3E2E))).contains("[# #]")


# A word missing from the map jumps with nothing pushed.
def test_a_missing_word_jumps_empty() -> None:
    assert_that(spoken(mapped_story(0x3E2F))).contains("[]")


# -- the output tour ---------------------------------------------------


# Spans, styles, and resources travel to the voice with their
# operands; a two-byte INDEX reaches its full range.
def test_the_output_tour_reaches_the_voice() -> None:
    main = (
        bytes([0x6E, 0xC1, 0x05])
        + bytes([0xEE])
        + bytes([0x6B, 0x02])
        + bytes([0xEB, 0x02])
        + bytes([0x70, 0x04])
        + bytes([0x6C])
        + immediate(0x4001)
        + bytes([0xEC])
        + immediate(0x4001)
        + bytes([0x01])
        + bytes([0x6D])
        + immediate(0x4001)
        + immediate(0x4004)
        + bytes([0x64])
        + immediate(0x4003)
        + bytes([0x70, 0x0F])
        + bytes([0x70, 0x11])
    )
    voice = recorded(crafted(main + QUIT))

    assert_that(voice.noted).contains(("enter_span", 0x105))
    assert_that(voice.noted).contains(("leave_span",))
    assert_that(voice.noted).contains(("set_style", 2))
    assert_that(voice.noted).contains(("reset_style", 2))
    assert_that(voice.noted).contains(("unstyle",))
    assert_that(voice.noted).contains(("embed_res", 0x4001))
    assert_that(voice.noted).contains(("progress", 1, 4))
    assert_that(voice.noted).contains(("clear_links",))
    assert_that(voice.noted).contains(("clear_div",))


# A link built from a word list reaches the voice with its click
# words spelled; a nested link stays silent inside the outer one.
def test_links_reach_the_voice_once() -> None:
    main = (
        bytes([0x13, 0x20, 0x00, 0x02, 0x03])
        + bytes([0x10])
        + immediate(0x3F00)
        + bytes([0x82])
        + bytes([0x69, 0x83])
        + bytes([0x69, 0x83])
        + bytes([0xE9])
        + bytes([0xE9])
        + bytes([0x68])
        + immediate(0x4005)
        + bytes([0x68])
        + immediate(0x4005)
        + bytes([0xE8, 0xE8])
        + bytes([0x6A, 0x6A, 0xEA, 0xEA])
    )
    voice = recorded(crafted(main + QUIT, dictionary=worded(b"go")))
    links = [note for note in voice.noted if str(note[0]).endswith("link")]

    assert_that(voice.noted).contains(("enter_link", "go"))
    assert_that(voice.noted).contains(("enter_link_res", 0x4005))
    assert_that(voice.noted).contains(("enter_self_link",))
    assert_that(len(links)).is_equal_to(4)


# CLEAR keeps the div stack: the voice sees the clear, then every
# open div entered again.
def test_clear_restates_the_open_divs() -> None:
    main = bytes([0x66, 0x03, 0x70, 0x06, 0x70, 0x07])
    voice = recorded(crafted(main + QUIT))
    told = [
        note for note in voice.noted if note[0] in ("enter_div", "clear", "clear_all")
    ]

    assert_that(told).is_equal_to(
        [
            ("enter_div", 3),
            ("clear",),
            ("enter_div", 3),
            ("clear_all",),
            ("enter_div", 3),
        ]
    )


# SET_BODY, the 1.0 shape of $67, reaches the voice.
def test_set_body_reaches_the_voice() -> None:
    voice = recorded(crafted(bytes([0x67, 0x04]) + QUIT, version=(1, 0)))

    assert_that(voice.noted).contains(("set_body", 4))


# TRACEPOINT speaks only while tracing, with the registers
# substituted into the shape's dollar signs.
def test_tracepoint_speaks_only_while_tracing() -> None:
    main = (
        bytes([0x10])
        + immediate(0x4007)
        + bytes([0x00])
        + bytes([0x70, 0x0A])
        + bytes([0x7F, 0x01, 0x00, 0x01])
        + immediate(42)
        + bytes([0x70, 0x0B])
        + bytes([0x7F, 0x01, 0x00, 0x01])
        + immediate(42)
    )
    voice = recorded(crafted(main + QUIT))
    traces = [note for note in voice.noted if note[0] == "trace"]

    assert_that(traces).is_equal_to([("trace", "a(7) a:42")])


# SCRIPT_ON fails when the voice refuses a transcript; SCRIPT_OFF
# passes quietly.
def test_script_on_fails_without_a_transcript() -> None:
    main = bytes([0x70, 0x09, 0x70, 0x08])
    story = crafted(caught(main))

    assert_that(spoken(story)).contains("9")


# -- VM_INFO -----------------------------------------------------------


# The div width comes back as a boxed number; unknown numeric
# selectors politely answer zero; feature answers land raw.
def test_vm_info_answers_by_selector() -> None:
    main = (
        bytes([0x74, 0x20, 0x01])
        + printed(1)
        + bytes([0x74, 0x3E, 0x02])
        + printed(2)
        + bytes([0x74, 0x40, 0x03])
        + bytes([0x50, 0x83])
        + immediate(0x4000)
        + bytes([0x03])
        + printed(3)
        + bytes([0x74, 0x42, 0x04])
        + bytes([0x50, 0x84])
        + immediate(0x4000)
        + bytes([0x04])
        + printed(4)
        + bytes([0x74, 0x00, 0x05])
        + printed(5)
    )
    told = spoken(crafted(main + QUIT))

    assert_that(told).contains("80")
    assert_that(told).contains("1")
    assert_that(told).contains("0")


# -- save, undo, restart, restore --------------------------------------


# SAVE fails politely when the voice keeps no files.
def test_save_fails_without_a_file_keeper() -> None:
    main = bytes([0x72]) + absolute(0)
    story = crafted(caught(main))

    assert_that(spoken(story)).contains("9")


# A voice that claims saves reaches the frontier report instead:
# the savefile is a later rung, loudly.
class KeepingVoice(PlainVoice):
    """A voice keeping one savefile in memory, or refusing to."""

    has_saves = True

    def __init__(self, story: Story, *, granting: bool = True) -> None:
        super().__init__(story)

        self.kept: bytes | None = None
        self._granting = granting

    def save(self, data: bytes) -> bool:
        if not self._granting:
            return False

        self.kept = data

        return True

    def restore(self) -> bytes | None:
        return self.kept


def saving_story() -> Story:
    """A story that saves, restores, and reports which path ran.

    The save continues to print 1, a later restore lands at the
    saved address to print 2, and a failed restore falls through
    to print 3.
    """

    head = bytes([0x72])
    landing = 1 + 1 + 3 + len(shown(0x4001)) + len(shown(0x4003)) + len(QUIT) + 2
    body = (
        head
        + absolute(landing)
        + shown(0x4001)
        + bytes([0x70, 0x02])
        + shown(0x4003)
        + QUIT
        + shown(0x4002)
        + QUIT
    )

    return crafted(body)


# A granted save continues, and the restore that follows revives
# the kept file, landing at the address the save named.
def test_a_kept_savefile_revives_at_its_landing() -> None:
    story = saving_story()
    voice = KeepingVoice(story)
    machine = Machine(story, voice, seed=7)
    machine.run()

    assert_that(voice.told()).contains("1").contains("2").does_not_contain("3")


# A refused save fails to the choice point.
def test_a_refused_save_fails() -> None:
    story = crafted(caught(bytes([0x72]) + absolute(0)))
    voice = KeepingVoice(story, granting=False)
    machine = Machine(story, voice, seed=7)
    machine.run()

    assert_that(voice.told()).contains("9")


# RESTORE with no saves continues as a failed restore.
def test_restore_without_saves_continues() -> None:
    story = crafted(bytes([0x70, 0x02]) + shown(0x4005) + QUIT)

    assert_that(spoken(story)).contains("5")


# A restore with nothing kept, and one handed unreadable bytes,
# both continue as failed restores.
def test_an_empty_or_unreadable_restore_continues() -> None:
    class HollowVoice(KeepingVoice):
        def restore(self) -> bytes | None:
            return None

    class CorruptVoice(KeepingVoice):
        def restore(self) -> bytes | None:
            return b"junk"

    for shape in (HollowVoice, CorruptVoice):
        story = saving_story()
        voice = shape(story)
        machine = Machine(story, voice, seed=7)
        machine.run()

        assert_that(voice.told()).contains("1").contains("3")


# UNDO with nothing kept and nothing pruned fails.
def test_undo_with_nothing_kept_fails() -> None:
    story = crafted(caught(bytes([0x70, 0x03])))

    assert_that(spoken(story)).contains("9")


# A long chain of SAVE_UNDOs prunes its oldest moments; draining
# the stack then lands on the pruned answer: a quiet continue.
def test_undo_prunes_and_then_continues() -> None:
    saves = 54
    landing = 1 + saves * 4
    main = (bytes([0xF2]) + absolute(landing)) * saves
    body = main + bytes([0x70, 0x03]) + shown(0x4008) + QUIT
    story = crafted(body)

    assert_that(spoken(story)).contains("8")


# RESTART rewinds the whole machine to its opening state; the
# story asks again, and a different key ends it.
def test_restart_rewinds_to_the_opening() -> None:
    head = bytes([0xF3, 0x00]) + shown(0x3E2A) + bytes([0x39]) + immediate(0x3E72)
    at = 1 + len(head) + 1 + 3 + len(QUIT)
    body = head + bytes([0x80]) + absolute(at) + QUIT + bytes([0x70, 0x01])
    story = crafted(body)

    assert_that(spoken(story, "r", "q")).contains("*\n*")


# -- input delivery ----------------------------------------------------


# GET_KEY takes special keys by their reserved codes, extended
# characters through the table, and digits as numbers.
def test_keys_arrive_by_kind() -> None:
    story = crafted(
        bytes([0xF3, 0x00]) + printed(0) + QUIT,
        lang=langed(extended=((0x80, 0x80, 0x2192),)),
    )

    voice = PlainVoice(story)
    machine = Machine(story, voice, seed=7)
    machine.run()
    machine.deliver_key(0x2192)

    assert_that(voice.told()).contains("→")

    told = spoken(crafted(bytes([0xF3, 0x00]) + printed(0) + QUIT), "7")

    assert_that(told).contains("7")


# A key the story cannot spell leaves the wait standing.
def test_an_unspellable_key_leaves_the_wait() -> None:
    story = crafted(bytes([0xF3, 0x00]) + printed(0) + QUIT)
    machine = Machine(story, PlainVoice(story), seed=7)
    machine.run()

    assert_that(machine.deliver_key(0x3A9)).is_equal_to("key")
    assert_that(machine.deliver_key(0x10)).is_equal_to("quit")


# An unspellable character in a line becomes the question mark,
# the reference engine's own shrug.
def test_an_unspellable_line_character_shrugs() -> None:
    main = bytes([0x73, 0x00]) + bytes([0x12, 0x01, 0x02, 0x80]) + printed(1)
    story = crafted(main + QUIT)

    assert_that(spoken(story, "ω")).contains("?")


# A heap too small to hold the parsed input reports exhaustion
# through the usual restart, and the wait is answered by the
# error entry instead.
def test_input_past_the_heap_reports_error_one() -> None:
    story = crafted(guarded(bytes([0x73, 0x00]) + QUIT), heap=6)

    assert_that(spoken(story, "a b c d e f g h")).contains("1")


# The endings decoder takes a suffix off and finds the stem; an
# unknown word keeps every letter, digits told as numbers.
def test_the_endings_decoder_finds_stems() -> None:
    endings = bytes([ord("s"), 3, 0x00, 0x01, 0x00])
    lang = langed(endings=endings)
    main = (
        bytes([0x73, 0x00])
        + bytes([0x12, 0x01, 0x02, 0x80])
        + printed(1)
        + bytes([0x1F, 0x81, 0x03])
        + printed(3)
    )
    story = crafted(main + QUIT, lang=lang, dictionary=worded(b"look"))

    assert_that(spoken(story, "looks")).contains("looks").contains("[l o o k s]")

    unknown = crafted(main + QUIT, lang=lang, dictionary=worded(b"look"))

    assert_that(spoken(unknown, "zz9")).contains("zz9").contains("[z z 9]")


# walked() closes the telling on a script that runs dry.
def test_a_dry_script_closes_the_walk() -> None:
    story = crafted(bytes([0x73, 0x00]) + QUIT)

    assert_that(walked(story, "", seed=7)).is_equal_to("")


# -- output whitespace -------------------------------------------------


# The NBSP state survives to the next print, and a pending space
# before a key read lands through the voice.
def test_nbsp_rides_to_the_next_print() -> None:
    main = (
        bytes([0x60, 0x01])
        + bytes([0x70, 0x13])
        + bytes([0x60, 0x00])
        + bytes([0xE2])
        + bytes([0xF3, 0x00])
    )
    story = crafted(main + QUIT)
    told = spoken(story, "q")

    assert_that(told).contains("a $")


# -- the collect-words level -------------------------------------------


# With the collect-words level raised, every output opcode holds
# its tongue: nothing reaches the voice until the level drops.
def test_a_raised_collect_level_silences_output() -> None:
    main = (
        bytes([0x70, 0x0C])
        + bytes([0x62, 0xE2, 0x63, 0xE3])
        + bytes([0x64])
        + immediate(0x4003)
        + bytes([0x66, 0x00, 0xE6])
        + bytes([0x6E, 0x00, 0xEE])
        + bytes([0x6F, 0x00, 0x00, 0xE7])
        + bytes([0x69])
        + immediate(0x4001)
        + bytes([0xE9])
        + bytes([0x68])
        + immediate(0x4001)
        + bytes([0xE8])
        + bytes([0x6A, 0xEA])
        + bytes([0x6B, 0x02, 0xEB, 0x02])
        + bytes([0x70, 0x04])
        + bytes([0x6C])
        + immediate(0x4001)
        + bytes([0x6D])
        + immediate(0x4001)
        + immediate(0x4004)
        + bytes([0x70, 0x05])
        + bytes([0x70, 0x0E])
        + bytes([0x70, 0x13])
        + bytes([0x70, 0x06])
        + bytes([0x70, 0x0D])
        + shown(0x4008)
    )
    voice = recorded(crafted(main + QUIT))

    assert_that(voice.told()).is_equal_to("8")
    assert_that(voice.noted).is_empty()


# PRINT_VAL under a raised level collects the value onto the aux
# stack instead of speaking it.
def test_print_val_under_the_level_collects() -> None:
    main = (
        bytes([0x94])
        + bytes([0x70, 0x0C])
        + shown(0x4005)
        + bytes([0x70, 0x0D])
        + bytes([0x17, 0x01])
        + printed(1)
    )
    story = crafted(main + QUIT)

    assert_that(spoken(story)).is_equal_to("[5]")


# -- serialization corners ---------------------------------------------


# An extended dict word rides the aux stack whole, both ways.
def test_aux_serialization_carries_the_extdict() -> None:
    endings = bytes([ord("s"), 3, 0x00, 0x01, 0x00])
    main = (
        bytes([0x73, 0x00])
        + bytes([0x12, 0x01, 0x02, 0x80])
        + bytes([0x94])
        + bytes([0x14, 0x81])
        + bytes([0x16, 0x03])
        + printed(3)
    )
    story = crafted(
        main + QUIT, lang=langed(endings=endings), dictionary=worded(b"look")
    )

    assert_that(spoken(story, "looks")).contains("looks")


# A raw aux push with no room reports exhaustion 2.
def test_a_full_aux_raw_push_reports_error_two() -> None:
    story = crafted(guarded(bytes([0x95, 0x05])), aux=0)

    assert_that(spoken(story)).contains("2")


# A long-term push past the area's end mid-list reports 6.
def test_a_longterm_push_past_the_end_reports_error_six() -> None:
    init, ram = roomy(longterm=3)
    main = bytes([0x73, 0x00]) + bytes([0xA6, 0x00, 0x80])
    story = crafted(guarded(main + QUIT), init=init, ram=ram)

    assert_that(spoken(story, "a b c")).contains("6")


# A number too long for the tag parses as an unknown word, every
# digit kept.
def test_an_oversized_number_stays_a_word() -> None:
    main = bytes([0x73, 0x00]) + bytes([0x12, 0x01, 0x02, 0x80]) + printed(1)
    story = crafted(main + QUIT)

    assert_that(spoken(story, "99999")).contains("99999")


# JOIN_WORDS flattens an extended dict word -- stem and ending --
# back into its spelled characters.
def test_join_words_flattens_an_extdict() -> None:
    endings = bytes([ord("s"), 3, 0x00, 0x01, 0x00])
    main = bytes([0x73, 0x00, 0x9F, 0x80, 0x01]) + printed(1)
    story = crafted(
        main + QUIT, lang=langed(endings=endings), dictionary=worded(b"look")
    )

    assert_that(spoken(story, "looks zz")).contains("lookszz")


# -- unification corners -----------------------------------------------


# Unifying a variable with itself binds nothing and succeeds.
def test_a_variable_unifies_with_itself() -> None:
    main = bytes([0x11, 0x01, 0x10, 0x81, 0x81]) + shown(0x4006)
    story = crafted(main + QUIT)

    assert_that(spoken(story)).contains("6")


# An extended dict word unifies with its own stem word under
# IF_UNIFY's would-unify walk.
def test_an_extdict_unifies_with_its_stem() -> None:
    endings = bytes([ord("s"), 3, 0x00, 0x01, 0x00])
    head = (
        bytes([0x73, 0x00])
        + bytes([0x12, 0x01, 0x02, 0x80])
        + bytes([0x37, 0x81])
        + immediate(0x2000)
    )
    at = 1 + len(head) + 3 + len(shown(0x4001) + QUIT)
    body = head + absolute(at) + shown(0x4001) + QUIT + shown(0x4002) + QUIT
    story = crafted(body, lang=langed(endings=endings), dictionary=worded(b"look"))

    assert_that(spoken(story, "looks")).contains("2")


# ASSIGN's unify variant accepts an extdict against its stem too.
def test_assign_unifies_an_extdict_with_its_stem() -> None:
    endings = bytes([ord("s"), 3, 0x00, 0x01, 0x00])
    main = (
        bytes([0x73, 0x00])
        + bytes([0x12, 0x01, 0x02, 0x80])
        + bytes([0x10])
        + immediate(0x2000)
        + bytes([0x81])
        + shown(0x4006)
    )
    story = crafted(
        main + QUIT, lang=langed(endings=endings), dictionary=worded(b"look")
    )

    assert_that(spoken(story, "looks")).contains("6")


# UNLINK walks a chain to its end without finding the key, and
# leaves it standing.
def test_unlink_passes_a_missing_key() -> None:
    init, ram = roomy(nob=2)
    main = (
        bytes([0xA4, 0x04])
        + immediate(0x0001)
        + bytes([0xAD, 0x04, 0x04])
        + immediate(0x0002)
        + shown(0x4006)
    )
    story = crafted(main + QUIT, init=init, ram=ram)

    assert_that(spoken(story)).contains("6")


# -- half-word and flag variants ---------------------------------------


# LOAD_BYTE and STORE_BYTE reach both halves of a word, and a
# raised flag answers IF_FLAG on a named object.
def test_bytes_and_flags_reach_their_halves() -> None:
    init, ram = roomy(nob=1)
    main = (
        bytes([0x25])
        + immediate(0x0001)
        + bytes([0x00])
        + immediate(0xAB)
        + bytes([0x25])
        + immediate(0x0001)
        + bytes([0x01])
        + immediate(0xCD)
        + bytes([0x21])
        + immediate(0x0001)
        + bytes([0x00, 0x01])
        + bytes([0x50, 0x81])
        + immediate(0x4000)
        + bytes([0x01])
        + printed(1)
        + bytes([0x21])
        + immediate(0x0001)
        + bytes([0x01, 0x02])
        + bytes([0x50, 0x82])
        + immediate(0x4000)
        + bytes([0x02])
        + printed(2)
        + bytes([0x28])
        + immediate(0x0001)
        + bytes([0x21])
        + bytes([0x4B])
        + immediate(0x0001)
        + bytes([0x21])
        + absolute(0)
    )
    story = crafted(main + QUIT, init=init, ram=ram)
    told = spoken(story)

    assert_that(told).contains(str(0xAB)).contains(str(0xCD))


# -- the trace and info tails ------------------------------------------


# A tracepoint shape without dollar signs passes through plain.
def test_a_plain_tracepoint_shape_passes_through() -> None:
    main = bytes([0x70, 0x0A]) + bytes([0x7F, 0x01, 0x01, 0x01]) + immediate(9)
    voice = recorded(crafted(main + QUIT))

    assert_that(voice.noted).contains(("trace", "a(a) a:9"))


# The peak-memory selectors count every non-unused word, and the
# height and transcript selectors answer their zeros.
def test_vm_info_counts_the_peaks() -> None:
    main = (
        bytes([0x74, 0x01, 0x01])
        + printed(1)
        + bytes([0x74, 0x02, 0x02])
        + printed(2)
        + bytes([0x74, 0x21, 0x03])
        + printed(3)
        + bytes([0x74, 0x50, 0x04])
        + bytes([0x50, 0x84])
        + immediate(0x4000)
        + bytes([0x04])
        + printed(4)
    )
    story = crafted(main + QUIT)

    assert_that(spoken(story)).contains("0")


# CLEAR_OLD and CLEAR_STATUS pass to the voice outside a span.
def test_clear_old_and_status_reach_the_voice() -> None:
    voice = recorded(crafted(bytes([0x70, 0x10, 0x70, 0x12]) + QUIT))

    assert_that(voice.noted).contains(("clear_old",))
    assert_that(voice.noted).contains(("clear_status",))


# -- the last corners --------------------------------------------------


# A long-term chunk holding the unbound marker revives as a fresh
# variable -- reachable only by a story writing its own long-term
# words, which STORE_WORD's reach across RAM permits.
def test_a_handwritten_longterm_variable_revives() -> None:
    init, ram = roomy()
    main = (
        bytes([0x50])
        + immediate(0x7FFF)
        + immediate(0x0A)
        + bytes([0x01])
        + bytes([0xA4, 0x00, 0x81])
        + bytes([0xA4, 0x08])
        + immediate(3)
        + bytes([0x50])
        + immediate(0x7FFF)
        + immediate(1)
        + bytes([0x02])
        + bytes([0xA4, 0x0A, 0x82])
        + bytes([0xA2, 0x00, 0x03])
        + printed(3)
    )
    story = crafted(main + QUIT, init=init, ram=ram)

    assert_that(spoken(story)).contains("$")


# JOIN_WORDS fails on a nested word list that itself refuses --
# here an unknown word hand-built around a stop character.
def test_join_words_refuses_a_nested_stop() -> None:
    main = (
        bytes([0x15])
        + immediate(0x3F00)
        + bytes([0x15])
        + immediate(0x3E2E)
        + bytes([0x15, 0xC0, 0x01])
        + bytes([0x15, 0x81, 0x00])
        + bytes([0x16, 0x01])
        + bytes([0x12, 0x81, 0x02, 0x03])
        + bytes([0x10])
        + immediate(0x3F00)
        + bytes([0x82])
        + bytes([0x9F, 0x83, 0x04])
    )
    story = crafted(caught(main), lang=langed(stops=b"."))

    assert_that(spoken(story)).contains("9")


# JOIN_WORDS fails on a list element no word could ever hold.
def test_join_words_refuses_a_wordless_element() -> None:
    main = (
        bytes([0x13, 0x00, 0x01, 0x02, 0x03])
        + bytes([0x10])
        + immediate(0x3F00)
        + bytes([0x82])
        + bytes([0x9F, 0x83, 0x04])
    )
    story = crafted(caught(main))

    assert_that(spoken(story)).contains("9")


# The polite skips: STORE_VAL of null to a non-object, RESET_FLAG
# of a non-object, and SET_PARENT of a non-object all pass over.
def test_non_objects_are_politely_skipped() -> None:
    init, ram = roomy(nob=1)
    main = (
        bytes([0x26])
        + immediate(0x4005)
        + bytes([0x00])
        + immediate(0)
        + bytes([0x29])
        + immediate(0x4005)
        + bytes([0x00])
        + bytes([0x2E])
        + immediate(0x4005)
        + immediate(0)
        + shown(0x4006)
    )
    story = crafted(main + QUIT, init=init, ram=ram)

    assert_that(spoken(story)).contains("6")


# ENTER_LINK passes over list elements that spell nothing.
def test_a_link_skips_the_unspellable() -> None:
    main = (
        bytes([0x12, 0x01, 0x02, 0x03])
        + bytes([0x10])
        + immediate(0x3F00)
        + bytes([0x82])
        + bytes([0x69, 0x83])
        + bytes([0xE9])
    )
    voice = recorded(crafted(main + QUIT))

    assert_that(voice.noted).contains(("enter_link", ""))


# SCRIPT_ON continues when the voice grants a transcript.
def test_script_on_continues_when_granted() -> None:
    class ScriptingVoice(PlainVoice):
        def script_on(self) -> bool:
            return True

    story = crafted(bytes([0x70, 0x08]) + shown(0x4006) + QUIT)
    voice = ScriptingVoice(story)
    machine = Machine(story, voice, seed=7)
    machine.run()

    assert_that(voice.told()).contains("6")


# The numeric VM_INFO selectors between the peaks and the div
# measures answer a boxed zero.
def test_vm_info_middle_selectors_answer_zero() -> None:
    main = bytes([0x74, 0x1F, 0x01]) + printed(1)
    story = crafted(main + QUIT)

    assert_that(spoken(story)).contains("0")


# A restore revives the divs that were open at the save, entering
# them again on the voice in order.
def test_a_restore_reenters_the_open_divs() -> None:
    head = bytes([0x66, 0x05, 0x72])
    landing = 1 + len(head) + 3 + 1 + len(shown(0x4001)) + len(shown(0x4003)) + 4
    body = (
        head
        + absolute(landing)
        + bytes([0xE6])
        + shown(0x4001)
        + bytes([0x70, 0x02])
        + shown(0x4003)
        + QUIT
        + shown(0x4002)
        + QUIT
    )
    story = crafted(body)
    voice = KeepingVoice(story)
    machine = Machine(story, voice, seed=7)
    machine.run()

    assert_that(voice.told()).contains("1").contains("2").does_not_contain("3")
