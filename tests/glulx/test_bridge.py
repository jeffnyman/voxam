"""The VM/Glk seam: ids minted, words marshalled, answers written."""

from collections.abc import Callable
from pathlib import Path

import pytest
from assertpy import assert_that

from voxam.errors import GlulxGlkError, GlulxSessionEnd
from voxam.glulx import gestalt
from voxam.glulx.bridge import STACK_REF, Bridge, MemArray, Registry
from voxam.glulx.glk.api import GLK_VERSION, Glk
from voxam.glulx.glk.dispatch import CLASS_STREAM, CLASS_WINDOW, U32, into
from voxam.glulx.glk.frontend import Frontend
from voxam.glulx.glk.objects import (
    EventType,
    FileMode,
    FileUsage,
    SeekMode,
    TextBufferWindow,
    Window,
    WindowType,
)
from voxam.glulx.machine import Machine
from voxam.glulx.story import Story

IDLE = bytes([0xC0, 0x00, 0x00, 0x81, 0x20])
PLANT = 0x180
RESULT = 0x140
SCRATCH = 0x2C0
TEXT = 0x250

GESTALT = 0x0004
WINDOW_OPEN = 0x0023
WINDOW_CLOSE = 0x0024
WINDOW_GET_ROCK = 0x0021
WINDOW_ITERATE = 0x0020
STREAM_GET_ROCK = 0x0041
STREAM_OPEN_MEMORY = 0x0043
STREAM_CLOSE = 0x0044
STREAM_SET_POSITION = 0x0045
STREAM_GET_POSITION = 0x0046
GET_BUFFER_STREAM = 0x0092
PUT_STRING = 0x0082
PUT_STRING_UNI = 0x0129
PUT_BUFFER = 0x0084
SELECT = 0x00C0
PLAY_MULTI = 0x00F7
FILEREF_CREATE_BY_NAME = 0x0061
TIME_TO_DATE_UTC = 0x0168
DATE_TO_TIME_UTC = 0x016C


class Suspending(Frontend):
    """A display that cannot block: never asked, only delivered to."""

    suspends = True

    def size(self) -> tuple[int, int]:
        return (80, 24)

    def flush(self, root: Window | None) -> None:
        pass

    def read_line(self, _window: Window, _maxlen: int) -> tuple[str, int] | None:
        pytest.fail("a suspending display is never asked for a line")

    def read_char(self, _window: Window) -> int | None:
        pytest.fail("a suspending display is never asked for a key")


def bridged(
    image: Callable[..., bytes], library: Glk | None = None
) -> tuple[Machine, Bridge, Glk]:
    """A machine with a Glk library installed, its bridge in hand."""

    glk = library if library is not None else Glk()
    machine = Machine(Story(image(code=IDLE)), glk=glk)

    if machine.bridge is None:
        pytest.fail("the bridge is installed with the library")

    return machine, machine.bridge, glk


# The registry mints sequential ids -- reproducible sessions beat
# glkop.c's randomized offsets -- and lookups are class-checked, so
# a stream id in a window seat reads as the null object.
def test_the_registry_minted_ids_are_class_checked() -> None:
    registry = Registry()
    window = TextBufferWindow()

    first = registry.register(window, CLASS_WINDOW)

    assert_that(first).is_equal_to(1)
    assert_that(registry.register(window, CLASS_WINDOW)).is_equal_to(1)
    assert_that(registry.register(None, CLASS_WINDOW)).is_equal_to(0)
    assert_that(registry.lookup(CLASS_WINDOW, first)).is_same_as(window)
    assert_that(registry.lookup(CLASS_STREAM, first)).is_none()
    assert_that(registry.lookup(CLASS_WINDOW, 0)).is_none()

    registry.forget(window)
    registry.forget(window)

    assert_that(registry.lookup(CLASS_WINDOW, first)).is_none()
    assert_that(registry.register(TextBufferWindow(), CLASS_WINDOW)).is_equal_to(2)


# A MemArray is a live view: reads and writes land in VM memory at
# the element width, sign-read where the type is signed, and the
# bounds are enforced.
def test_mem_arrays_are_live_views(image: Callable[..., bytes]) -> None:
    machine, _, _ = bridged(image)
    bytes_view = MemArray(machine.memory, SCRATCH, 3)
    words_view = MemArray(machine.memory, SCRATCH, 2, 4, signed=True)

    bytes_view[0] = 0x41
    bytes_view[1] = 0x142

    assert_that(machine.memory.read_byte(SCRATCH)).is_equal_to(0x41)
    assert_that(bytes_view[1]).is_equal_to(0x42)
    assert_that(list(bytes_view)).is_equal_to([0x41, 0x42, 0])
    assert_that(len(words_view)).is_equal_to(2)

    words_view[1] = 0xFFFFFFFF

    assert_that(words_view[1]).is_equal_to(-1)

    with pytest.raises(IndexError, match="outside the 3 elements"):
        bytes_view[3] = 0


# A plain call passes words in and a word back; the unknown and
# the malformed are refused by name.
def test_plain_calls_pass_words(image: Callable[..., bytes]) -> None:
    _, bridge, _ = bridged(image)

    assert_that(bridge.perform(GESTALT, [0, 0])).is_equal_to(GLK_VERSION)

    with pytest.raises(GlulxGlkError, match="unknown function 0x9999"):
        bridge.perform(0x9999, [])

    with pytest.raises(GlulxGlkError, match="takes 2 argument words, but 1"):
        bridge.perform(GESTALT, [0])


# Opaque objects cross as ids: a window opens and its id answers
# for it, a wrong-class id reads as null, and a closed window's id
# stops resolving because disposal reaches the registry.
def test_opaque_ids_mint_and_expire(image: Callable[..., bytes]) -> None:
    machine, bridge, _ = bridged(image)

    ident = bridge.perform(WINDOW_OPEN, [0, 0, 0, WindowType.TEXT_BUFFER, 7])

    assert_that(ident).is_equal_to(1)
    assert_that(bridge.perform(WINDOW_GET_ROCK, [ident])).is_equal_to(7)
    assert_that(bridge.perform(STREAM_GET_ROCK, [ident])).is_equal_to(0)

    bridge.perform(WINDOW_CLOSE, [ident, RESULT])

    assert_that(bridge.perform(WINDOW_GET_ROCK, [ident])).is_equal_to(0)
    assert_that(machine.memory.read_word(RESULT)).is_equal_to(0)
    assert_that(machine.memory.read_word(RESULT + 4)).is_equal_to(0)


# Scalar output references write to memory when given an address,
# skip quietly when given null, and push when given -1.
def test_scalar_references_answer_everywhere(
    image: Callable[..., bytes],
) -> None:
    machine, bridge, _ = bridged(image)

    first = bridge.perform(WINDOW_OPEN, [0, 0, 0, WindowType.TEXT_BUFFER, 9])

    assert_that(bridge.perform(WINDOW_ITERATE, [0, SCRATCH])).is_equal_to(first)
    assert_that(machine.memory.read_word(SCRATCH)).is_equal_to(9)
    assert_that(bridge.perform(WINDOW_ITERATE, [first, 0])).is_equal_to(0)

    depth = machine.stack.count

    bridge.perform(WINDOW_ITERATE, [0, STACK_REF])

    assert_that(machine.stack.count).is_equal_to(depth + 1)
    assert_that(machine.stack.pop()).is_equal_to(9)


# A struct written to the stack pushes its fields in order, last
# on top -- which is why a game closing a stream pops the write
# count before the read count (Glulx: Miscellaneous).
def test_stack_structs_push_last_on_top(image: Callable[..., bytes]) -> None:
    machine, bridge, library = bridged(image)

    stream = bridge.perform(STREAM_OPEN_MEMORY, [0, 0, FileMode.WRITE, 0])

    library.glk_put_char_stream(library.streams[0], 0x41)

    bridge.perform(STREAM_CLOSE, [stream, STACK_REF])

    assert_that(machine.stack.pop()).is_equal_to(1)
    assert_that(machine.stack.pop()).is_equal_to(0)


# A struct read from the stack pops its fields first-topmost, and
# the date comes back through memory: 2023-11-14, a Tuesday
# counted from Sunday.
def test_stack_structs_pop_first_topmost(image: Callable[..., bytes]) -> None:
    machine, bridge, _ = bridged(image)

    machine.stack.push(250)
    machine.stack.push(1_700_000_000)
    machine.stack.push(0)

    bridge.perform(TIME_TO_DATE_UTC, [STACK_REF, SCRATCH])

    held = [machine.memory.read_word(SCRATCH + 4 * index) for index in range(8)]

    assert_that(held).is_equal_to([2023, 11, 14, 2, 22, 13, 20, 250])


# A struct read from memory decodes its signed fields: an hour of
# -3 is legal and normalizes away (Glk: Time and Date
# Conversions).
def test_memory_structs_decode_signed_fields(
    image: Callable[..., bytes],
) -> None:
    machine, bridge, _ = bridged(image)

    fields = [2023, 11, 14, 0, -3, 0, 0, 0]

    for index, value in enumerate(fields):
        machine.memory.write_word(SCRATCH + 4 * index, value & 0xFFFFFFFF)

    bridge.perform(DATE_TO_TIME_UTC, [SCRATCH, RESULT])

    low = machine.memory.read_word(RESULT + 4)

    assert_that(low).is_equal_to(1_700_000_000 - 22 * 3600 - 13 * 60 - 20 - 3 * 3600)


# Null is refused where the signature forbids it: select's event
# struct, and put_buffer's character array.
def test_nonnull_seats_refuse_null(image: Callable[..., bytes]) -> None:
    _, bridge, _ = bridged(image)

    with pytest.raises(GlulxGlkError, match="requires one"):
        bridge.perform(SELECT, [0])

    with pytest.raises(GlulxGlkError, match="requires one"):
        bridge.perform(PUT_BUFFER, [0, 3])


# A signed plain argument sign-extends: seeking -1 from the end
# leaves the mark one short of it.
def test_signed_arguments_sign_extend(image: Callable[..., bytes]) -> None:
    machine, bridge, _ = bridged(image)

    machine.memory.write_run(SCRATCH, b"abcd")

    stream = bridge.perform(STREAM_OPEN_MEMORY, [SCRATCH, 4, FileMode.READ_WRITE, 0])

    bridge.perform(STREAM_SET_POSITION, [stream, 0xFFFFFFFF, SeekMode.END])

    assert_that(bridge.perform(STREAM_GET_POSITION, [stream])).is_equal_to(3)


# A memory stream opened over VM memory is retained by Glk and
# stays live: characters put through the library land in the
# machine's own RAM, and reads come back out of it.
def test_retained_arrays_stay_live(image: Callable[..., bytes]) -> None:
    machine, bridge, library = bridged(image)

    stream = bridge.perform(STREAM_OPEN_MEMORY, [SCRATCH, 8, FileMode.READ_WRITE, 0])

    library.glk_stream_set_current(library.streams[0])
    library.glk_put_string("hey")

    assert_that(machine.memory.read_run(SCRATCH, 3)).is_equal_to(b"hey")

    bridge.perform(STREAM_SET_POSITION, [stream, 0, SeekMode.START])

    count = bridge.perform(GET_BUFFER_STREAM, [stream, SCRATCH + 8, 3])

    assert_that(count).is_equal_to(3)
    assert_that(machine.memory.read_run(SCRATCH + 8, 3)).is_equal_to(b"hey")


# String arguments are unencoded string objects, type byte and
# all: E0 for Latin-1, E2 for Unicode with values that are no code
# point rendering as '?'. A bare byte array in a string seat is
# refused by name.
def test_string_arguments_are_objects(
    image: Callable[..., bytes], tmp_path: Path
) -> None:
    machine, bridge, library = bridged(image, Glk(save_dir=tmp_path))

    machine.memory.write_run(TEXT, bytes([0xE0]) + b"tale" + bytes([0x00]))

    ident = bridge.perform(FILEREF_CREATE_BY_NAME, [FileUsage.DATA, TEXT, 0])

    assert_that(ident).is_greater_than(0)
    assert_that(library.filerefs[0].filename).is_equal_to(
        str(tmp_path / "tale.glkdata")
    )

    held = [0] * 4

    library.glk_stream_set_current(
        library.glk_stream_open_memory_uni(held, FileMode.WRITE, 0)
    )

    machine.memory.write_run(
        TEXT,
        bytes([0xE2, 0x00, 0x00, 0x00])
        + (0x2603).to_bytes(4, "big")
        + (0x110000).to_bytes(4, "big")
        + bytes(4),
    )

    bridge.perform(PUT_STRING_UNI, [TEXT])

    assert_that(held).is_equal_to([0x2603, ord("?"), 0, 0])

    machine.memory.write_run(TEXT, bytes([0x41, 0x00]))

    with pytest.raises(GlulxGlkError, match="not an E0"):
        bridge.perform(PUT_STRING, [TEXT])

    with pytest.raises(GlulxGlkError, match="not an E2"):
        bridge.perform(PUT_STRING_UNI, [TEXT])


# An opaque array crosses as a snapshot of looked-up objects; ids
# of zero are the null channel, and nothing plays where no sound
# can.
def test_opaque_arrays_cross_as_objects(image: Callable[..., bytes]) -> None:
    machine, bridge, _ = bridged(image)

    machine.memory.write_word(SCRATCH, 0)
    machine.memory.write_word(SCRATCH + 4, 0)
    machine.memory.write_word(SCRATCH + 8, 3)
    machine.memory.write_word(SCRATCH + 12, 4)

    started = bridge.perform(PLAY_MULTI, [SCRATCH, 2, SCRATCH + 8, 2, 0])

    assert_that(started).is_equal_to(0)


# The marshaller's full grammar includes input scalars, which the
# current Glk API never uses -- they are held to the same rules
# via synthetic items so the grammar stays whole.
def test_input_scalars_read_memory_and_stack(
    image: Callable[..., bytes],
) -> None:
    machine, bridge, _ = bridged(image)
    item = into(U32)

    machine.memory.write_word(SCRATCH, 99)

    value, writeback, position = bridge._unmarshal_item(item, [SCRATCH], 0)

    assert_that(getattr(value, "value", None)).is_equal_to(99)
    assert_that(writeback).is_none()
    assert_that(position).is_equal_to(1)

    machine.stack.push(41)

    value, writeback, _ = bridge._unmarshal_item(item, [STACK_REF], 0)

    assert_that(getattr(value, "value", None)).is_equal_to(41)
    assert_that(writeback).is_none()


# The glk opcode itself: selector and count as operands, arguments
# off the stack first-topmost, the answer stored -- and glk_exit
# ends the run the way quit does.
def test_the_glk_opcode_calls_and_exits(image: Callable[..., bytes]) -> None:
    machine, _, _ = bridged(image)

    machine.stack.push(0)
    machine.stack.push(0)
    machine.memory.write_run(
        PLANT,
        bytes([0x81, 0x30, 0x11, 0x07, GESTALT, 0x02])
        + (RESULT).to_bytes(4, "big")
        + bytes([0x81, 0x30, 0x11, 0x00, 0x01, 0x00]),
    )

    machine.pc = PLANT

    machine.run(limit=10)

    assert_that(machine.memory.read_word(RESULT)).is_equal_to(GLK_VERSION)
    assert_that(machine.running).is_false()


# Without a library the glk opcode is refused by name, and
# selecting the Glk output system falls back to null -- the same
# truth the gestalt answers.
def test_no_library_means_no_glk(image: Callable[..., bytes]) -> None:
    machine = Machine(Story(image(code=IDLE)))

    machine.memory.write_run(
        PLANT, bytes([0x81, 0x49, 0x11, 0x02, 0x07]) + bytes([0x81, 0x20])
    )

    machine.pc = PLANT

    machine.run(limit=10)

    assert_that(machine.iosys.mode).is_equal_to(0)
    assert_that(machine.iosys.rock).is_equal_to(0)
    assert_that(gestalt.answer(machine, 4, 2)).is_equal_to(0)

    machine.memory.write_run(
        PLANT, bytes([0x81, 0x30, 0x11, 0x00, 0x01, 0x00]) + bytes([0x81, 0x20])
    )

    machine.pc = PLANT

    with pytest.raises(GlulxGlkError, match="none is installed"):
        machine.step()


# With a library installed the capability flips, iosys mode 2
# holds, and a streamchar lands in the Glk window -- the machine
# speaks through Glk for the first time.
def test_the_machine_speaks_through_glk(image: Callable[..., bytes]) -> None:
    machine, _, library = bridged(image)
    window = library.glk_window_open(None, 0, 0, WindowType.TEXT_BUFFER, 0)

    if not isinstance(window, TextBufferWindow):
        pytest.fail("the root window opened")

    library.glk_set_window(window)

    assert_that(gestalt.answer(machine, 4, 2)).is_equal_to(1)

    machine.memory.write_run(
        PLANT,
        bytes([0x81, 0x49, 0x11, 0x02, 0x00])
        + bytes([0x70, 0x01, 0x41])
        + bytes([0x81, 0x20]),
    )

    machine.pc = PLANT

    machine.run(limit=10)

    assert_that(machine.iosys.mode).is_equal_to(2)
    assert_that(window.text()).is_equal_to("A")


# A session that raises GlulxSessionEnd from a select -- the null
# display's answer to input -- stops the machine cleanly too.
def test_an_unanswerable_session_ends_cleanly(
    image: Callable[..., bytes],
) -> None:
    _, bridge, library = bridged(image)

    window = library.glk_window_open(None, 0, 0, WindowType.TEXT_BUFFER, 0)

    library.glk_request_char_event(window)

    with pytest.raises(GlulxSessionEnd):
        bridge.perform(SELECT, [SCRATCH])


# A select over a suspending display completes its opcode -- zero
# stored, stack whole -- but the struct's travel back into memory
# is deferred: the sentinel survives until the host delivers the
# event, and every call in between is refused, because a suspended
# machine should be standing still.
def test_a_suspended_select_defers_its_writeback(image: Callable[..., bytes]) -> None:
    machine, bridge, library = bridged(image, Glk(Suspending()))
    window = library.glk_window_open(None, 0, 0, WindowType.TEXT_BUFFER, 0)

    if window is None:
        pytest.fail("the window opened")

    library.glk_request_char_event(window)

    for index in range(4):
        machine.memory.write_word(SCRATCH + 4 * index, 0xDEADBEEF)

    assert_that(bridge.perform(SELECT, [SCRATCH])).is_equal_to(0)
    assert_that(machine.memory.read_word(SCRATCH)).is_equal_to(0xDEADBEEF)

    with pytest.raises(GlulxGlkError, match="stands suspended"):
        bridge.perform(GESTALT, [0, 0])

    library.deliver_event(library.deliver_char(window, 0x41))

    assert_that(machine.memory.read_word(SCRATCH)).is_equal_to(EventType.CHAR_INPUT)
    assert_that(machine.memory.read_word(SCRATCH + 4)).is_equal_to(1)
    assert_that(machine.memory.read_word(SCRATCH + 8)).is_equal_to(0x41)
    assert_that(machine.memory.read_word(SCRATCH + 12)).is_equal_to(0)
