"""The Glk object model: streams, windows, and their kin."""

from io import BytesIO

from assertpy import assert_that

from voxam.glulx.glk.objects import (
    BlankWindow,
    Event,
    EventType,
    FileMode,
    FileRef,
    FileStream,
    FileUsage,
    GraphicsWindow,
    LineRequest,
    MemoryStream,
    Metrics,
    PairWindow,
    Run,
    SeekMode,
    SoundChannel,
    Stream,
    Style,
    TextBufferWindow,
    TextGridWindow,
    WindowMethod,
    WindowType,
    to_char,
)


def grid(width: int, height: int) -> TextGridWindow:
    window = TextGridWindow()

    window.rearrange((0, 0, width, height))

    return window


# A Glulx character is an arbitrary 32-bit value, so a game can
# print something that is not a code point at all -- glulxercise
# does. Anything past the Unicode range, and the surrogate block,
# renders as '?' (Glk: Output).
def test_unprintable_values_render_as_question_marks() -> None:
    assert_that(to_char(0x41)).is_equal_to("A")
    assert_that(to_char(0x110000)).is_equal_to("?")
    assert_that(to_char(0xD800)).is_equal_to("?")


# The rock is a 32-bit value (Glk: Rocks), whatever Python integer
# the caller hands over.
def test_rocks_are_reduced_to_32_bits() -> None:
    channel = SoundChannel(rock=0x1_2345_6789)

    assert_that(channel.rock).is_equal_to(0x2345_6789)
    assert_that(channel.disposed).is_false()


# A stream only moves characters in its declared directions: a
# write to an unwritable stream is not even counted, and a read
# from an unreadable one is end-of-stream.
def test_streams_enforce_their_directions() -> None:
    silent = Stream(readable=True)
    deaf = Stream(writable=True)

    silent.put_char(0x41)
    deaf.put_char(0x41)

    assert_that(silent.writecount).is_equal_to(0)
    assert_that(deaf.writecount).is_equal_to(1)
    assert_that(deaf.get_char()).is_equal_to(-1)

    # The base stream is also where reads land when a subclass has
    # nothing: end-of-stream, and the read count holds at zero.
    assert_that(silent.get_char()).is_equal_to(-1)
    assert_that(silent.readcount).is_equal_to(0)

    # Seeking is meaningless on the base; the mark just answers 0.
    silent.set_position(5, SeekMode.START)

    assert_that(silent.get_position()).is_equal_to(0)
    assert_that(deaf.close()).is_equal_to((0, 1))
    assert_that(deaf.disposed).is_true()


# A byte stream substitutes '?' for anything it cannot hold; a
# Unicode stream holds the full word (Glk: Output).
def test_byte_streams_substitute_what_they_cannot_hold() -> None:
    narrow = MemoryStream([0, 0], FileMode.WRITE)
    wide = MemoryStream([0, 0], FileMode.WRITE, unicode=True)

    narrow.put_buffer([0x41, 0x2603])
    wide.put_buffer([0x41, 0x2603])

    assert_that(narrow.buf).is_equal_to([0x41, 0x3F])
    assert_that(wide.buf).is_equal_to([0x41, 0x2603])


# "It will count the number of characters written into the stream,
# not the number that fit in the buffer" (Glk: Memory Streams) --
# and a null buffer is the legal extreme, discarding everything
# while counting it, which is how a game measures output length.
def test_write_counts_include_what_overflowed() -> None:
    short = MemoryStream([0], FileMode.WRITE)
    null = MemoryStream(None, FileMode.WRITE)

    short.put_string("abc")
    null.put_string("abc")

    assert_that(short.buf).is_equal_to([0x61])
    assert_that(short.writecount).is_equal_to(3)
    assert_that(short.get_position()).is_equal_to(3)
    assert_that(null.capacity).is_equal_to(0)
    assert_that(null.writecount).is_equal_to(3)

    # And a null buffer reads as instant end-of-stream.
    assert_that(MemoryStream(None, FileMode.READ).get_char()).is_equal_to(-1)


# get_buffer fills until the buffer or the stream runs out, no
# terminal null placed (Glk: How To Read).
def test_get_buffer_fills_until_something_runs_out() -> None:
    source = MemoryStream([0x61, 0x62, 0x63], FileMode.READ)
    room = [0, 0, 0, 0, 0]

    assert_that(source.get_buffer(room)).is_equal_to(3)
    assert_that(room).is_equal_to([0x61, 0x62, 0x63, 0, 0])
    assert_that(source.readcount).is_equal_to(3)

    refill = MemoryStream([0x64, 0x65], FileMode.READ)
    snug = [0, 0]

    assert_that(refill.get_buffer(snug)).is_equal_to(2)
    assert_that(snug).is_equal_to([0x64, 0x65])


# get_line reads until len-1 characters or a newline, keeps the
# newline, and always null-terminates, the null not counted (Glk:
# How To Read).
def test_get_line_keeps_the_newline_and_terminates() -> None:
    source = MemoryStream([0x61, 0x62, 0x0A, 0x63], FileMode.READ)
    room = [9, 9, 9, 9]

    assert_that(source.get_line(room)).is_equal_to(3)
    assert_that(room).is_equal_to([0x61, 0x62, 0x0A, 0])

    # The stream ending mid-line terminates what was read.
    tail = [9, 9, 9, 9]

    assert_that(source.get_line(tail)).is_equal_to(1)
    assert_that(tail).is_equal_to([0x63, 0, 9, 9])

    # A full buffer stops one short to leave room for the null.
    cramped = [9, 9]

    long = MemoryStream([0x64, 0x65, 0x66], FileMode.READ)

    assert_that(long.get_line(cramped)).is_equal_to(1)
    assert_that(cramped).is_equal_to([0x64, 0])

    # A zero-capacity buffer reads nothing at all.
    assert_that(long.get_line([])).is_equal_to(0)


# The mark seeks from the start, the current position, or the end,
# and clamps to the buffer either way (Glk: Stream Positions).
def test_memory_streams_seek_and_clamp() -> None:
    stream = MemoryStream([0x61, 0x62, 0x63, 0x64], FileMode.READ_WRITE)

    stream.set_position(2, SeekMode.START)

    assert_that(stream.get_char()).is_equal_to(0x63)

    stream.set_position(-2, SeekMode.CURRENT)

    assert_that(stream.get_char()).is_equal_to(0x62)

    stream.set_position(-1, SeekMode.END)

    assert_that(stream.get_char()).is_equal_to(0x64)
    assert_that(stream.get_char()).is_equal_to(-1)

    stream.set_position(-10, SeekMode.START)

    assert_that(stream.get_position()).is_equal_to(0)

    stream.set_position(10, SeekMode.START)

    assert_that(stream.get_position()).is_equal_to(4)

    # WriteAppend is a writable mode for the stream flags, even
    # though opening a memory stream with it is the api's to refuse.
    appender = MemoryStream([0], FileMode.WRITE_APPEND)

    assert_that(appender.writable).is_true()
    assert_that(appender.readable).is_false()


# A window's stream is never readable, and what it is handed lands
# in the window (Glk: Window Streams).
def test_window_streams_hand_characters_to_their_window() -> None:
    window = TextBufferWindow()

    window.stream.put_string("ab")

    assert_that(window.stream.readable).is_false()
    assert_that(window.stream.unicode).is_true()
    assert_that(window.text()).is_equal_to("ab")


# An echo stream receives a copy of everything the window shows
# (Glk: Echo Streams) -- and a window without one just shows.
def test_echo_streams_receive_a_copy() -> None:
    window = TextBufferWindow()
    copy = MemoryStream([0, 0, 0], FileMode.WRITE)

    window.put_char(0x61)

    window.echo_stream = copy

    window.put_char(0x62)

    assert_that(copy.buf).is_equal_to([0x62, 0, 0])
    assert_that(window.text()).is_equal_to("ab")


# A line request records what was asked; the null buffer has no
# capacity.
def test_line_requests_hold_what_was_asked() -> None:
    request = LineRequest([0, 0, 0], 1, unicode=True, echo=False)
    hollow = LineRequest(None)

    assert_that(request.capacity).is_equal_to(3)
    assert_that(request.initlen).is_equal_to(1)
    assert_that(request.unicode).is_true()
    assert_that(request.echo).is_false()
    assert_that(request.terminators).is_equal_to(())
    assert_that(hollow.capacity).is_equal_to(0)
    assert_that(hollow.echo).is_true()


# A text window's size is its box divided by the display's cell,
# margins off the top, rounded down -- claiming a column that does
# not fit would spill over the window's own edge.
def test_text_windows_measure_in_cells() -> None:
    window = TextBufferWindow()

    window.metrics = Metrics(10, 16, 4, 2)

    window.rearrange((0, 0, 104, 66))

    assert_that(window.width).is_equal_to(10)
    assert_that(window.height).is_equal_to(4)

    # A zero cell -- a display that has not measured -- answers no
    # room at all rather than dividing by it.
    window.metrics = Metrics(0, 0)

    assert_that(window.width).is_equal_to(0)

    # A box smaller than the margin clamps to zero, not negative.
    window.metrics = Metrics(10, 16, 200, 2)

    assert_that(window.width).is_equal_to(0)


# The reverse conversion rounds up: a fixed split a fraction of a
# pixel short would push its last line past its own border. The
# base window's units are already display units, so it converts by
# doing nothing.
def test_extents_round_up_for_the_split() -> None:
    window = TextGridWindow()

    window.metrics = Metrics(10.4, 16, 4, 2)

    assert_that(window.extent(3, vertical=True)).is_equal_to(36)
    assert_that(window.extent(2, vertical=False)).is_equal_to(34)

    pixels = GraphicsWindow()

    pixels.rearrange((10, 10, 74, 58))

    assert_that(pixels.extent(50, vertical=True)).is_equal_to(50)
    assert_that(pixels.width).is_equal_to(64)
    assert_that(pixels.height).is_equal_to(48)


# A degenerate box never reports a negative size.
def test_boxes_clamp_at_nothing() -> None:
    window = GraphicsWindow()

    window.rearrange((10, 10, 4, 4))

    assert_that(window.width).is_equal_to(0)
    assert_that(window.height).is_equal_to(0)


# "A blank window has no size; glk_window_get_size() will return
# (0,0)" (Glk: Blank Windows) -- and a pair window is a split, not
# a place. The box stays, because a display draws borders from it;
# zero is only what the game is told.
def test_sizeless_windows_answer_zero_with_a_real_box() -> None:
    blank = BlankWindow()

    blank.rearrange((0, 0, 80, 24))

    assert_that(blank.width).is_equal_to(0)
    assert_that(blank.height).is_equal_to(0)
    assert_that(blank.bbox).is_equal_to((0, 0, 80, 24))
    assert_that(blank.wintype).is_equal_to(WindowType.BLANK)

    # The base clear has nothing to erase; it can only raise the
    # flag for a display to act on.
    blank.clear()

    assert_that(blank.pending_clear).is_true()


# Buffer text accumulates as runs: a run continues only while both
# the style and the link value hold (Glk: Creating Hyperlinks).
def test_buffer_runs_split_on_style_and_link() -> None:
    window = TextBufferWindow()

    window.stream.put_string("ab")

    window.style = Style.EMPHASIZED

    window.stream.put_char(0x63)

    window.style = Style.NORMAL
    window.stream.hyperlink = 7

    window.stream.put_char(0x64)

    assert_that(window.content).is_equal_to(
        [
            Run(Style.NORMAL, 0, "ab"),
            Run(Style.EMPHASIZED, 0, "c"),
            Run(Style.NORMAL, 7, "d"),
        ]
    )
    assert_that(window.text()).is_equal_to("abcd")

    # The drains hand everything over exactly once.
    assert_that(window.take_content()).is_length(3)
    assert_that(window.content).is_empty()

    window.stream.put_char(0x65)

    assert_that(window.take_text()).is_equal_to("e")
    assert_that(window.text()).is_equal_to("")

    window.stream.put_char(0x66)

    window.clear()

    assert_that(window.content).is_empty()
    assert_that(window.pending_clear).is_true()


# The grid writes at the cursor and advances, wraps at the right
# edge, treats newline as a cursor drop that prints nothing, and
# drops what lands outside entirely (Glk: Text Grid Windows).
def test_grids_write_wrap_and_drop() -> None:
    window = grid(3, 2)

    window.stream.put_string("abcd")

    assert_that(window.rows()).is_equal_to(["abc", "d  "])

    window.move_cursor(0, 1)
    window.stream.put_char(0x0A)

    window.stream.put_string("lost")

    assert_that(window.rows()).is_equal_to(["abc", "d  "])

    # A negative cursor is equally out of the grid.
    window.move_cursor(-2, 0)
    window.stream.put_char(0x7A)

    assert_that(window.rows()).is_equal_to(["abc", "d  "])


# Each grid cell keeps the style and link it was written under.
def test_grids_keep_styles_and_links_per_cell() -> None:
    window = grid(2, 1)

    window.style = Style.HEADER
    window.stream.hyperlink = 5

    window.stream.put_char(0x61)

    assert_that(window.styles[0]).is_equal_to([Style.HEADER, Style.NORMAL])
    assert_that(window.links[0]).is_equal_to([5, 0])


# Rearranging a grid keeps what still fits; the cursor is clamped
# into the new bounds.
def test_grids_resize_keeping_what_fits() -> None:
    window = grid(4, 2)

    window.stream.put_string("abcdef")

    window.rearrange((0, 0, 6, 3))

    assert_that(window.rows()).is_equal_to(["abcd  ", "ef    ", "      "])

    window.move_cursor(5, 2)

    window.rearrange((0, 0, 2, 1))

    assert_that(window.rows()).is_equal_to(["ab"])
    assert_that((window.cursor_x, window.cursor_y)).is_equal_to((2, 1))

    window.clear()

    assert_that(window.rows()).is_equal_to(["  "])
    assert_that((window.cursor_x, window.cursor_y)).is_equal_to((0, 0))


# A pair window unpacks its method word and can recompose it.
def test_pair_methods_unpack_and_recompose() -> None:
    left = TextBufferWindow()
    right = TextBufferWindow()
    pair = PairWindow(left, right, right, WindowMethod.LEFT | WindowMethod.FIXED, 10)

    assert_that(pair.vertical).is_true()
    assert_that(pair.backward).is_true()
    assert_that(pair.has_border).is_true()
    assert_that(pair.method).is_equal_to(WindowMethod.LEFT | WindowMethod.FIXED)
    assert_that(pair.wintype).is_equal_to(WindowType.PAIR)

    pair.set_method(
        WindowMethod.BELOW | WindowMethod.PROPORTIONAL | WindowMethod.NO_BORDER
    )

    assert_that(pair.vertical).is_false()
    assert_that(pair.backward).is_false()
    assert_that(pair.has_border).is_false()
    assert_that(pair.method).is_equal_to(
        WindowMethod.BELOW | WindowMethod.PROPORTIONAL | WindowMethod.NO_BORDER
    )


# A proportional split takes its percentage of the extent; the
# split-off child sits on the named side, the original takes the
# rest.
def test_proportional_splits_divide_by_percentage() -> None:
    original = TextBufferWindow()
    status = TextGridWindow()
    pair = PairWindow(
        original, status, status, WindowMethod.ABOVE | WindowMethod.PROPORTIONAL, 25
    )

    pair.rearrange((0, 0, 80, 24))

    assert_that(status.bbox).is_equal_to((0, 0, 80, 6))
    assert_that(original.bbox).is_equal_to((0, 6, 80, 24))
    assert_that(pair.sized_box).is_equal_to((0, 0, 80, 6))
    assert_that(pair.width).is_equal_to(0)


# A fixed split is expressed in the key window's measurement
# system (Glk: Window Opening, Closing, and Constraints): the key
# converts characters to display units, and the split lands below
# when the direction says so.
def test_fixed_splits_measure_by_the_key_window() -> None:
    original = TextBufferWindow()
    status = TextGridWindow()
    pair = PairWindow(
        original, status, status, WindowMethod.BELOW | WindowMethod.FIXED, 3
    )

    pair.rearrange((0, 0, 80, 24))

    assert_that(status.bbox).is_equal_to((0, 21, 80, 24))
    assert_that(original.bbox).is_equal_to((0, 0, 80, 21))

    # A split larger than the box clamps to the box.
    pair.size = 100

    pair.rearrange((0, 0, 80, 24))

    assert_that(status.bbox).is_equal_to((0, 0, 80, 24))
    assert_that(original.bbox).is_equal_to((0, 0, 80, 0))


# The key window only supplies the measurement system: the sized
# side is always the one the direction names -- child2's side --
# even when the key lives on the other side, which the spec's own
# worked example does on purpose (Glk: Changing Window
# Constraints).
def test_the_key_only_measures() -> None:
    original = TextGridWindow()
    added = TextBufferWindow()
    pair = PairWindow(
        original, added, original, WindowMethod.LEFT | WindowMethod.FIXED, 5
    )

    pair.rearrange((0, 0, 80, 24))

    assert_that(added.bbox).is_equal_to((0, 0, 5, 24))
    assert_that(original.bbox).is_equal_to((5, 0, 80, 24))


# A fileref records what the file is for, keeping only the type
# bits of the usage word (Glk: The Types of File References).
def test_filerefs_split_usage_from_mode() -> None:
    saved = FileRef("story.glksave", FileUsage.SAVED_GAME | FileUsage.TEXT_MODE)
    scratch = FileRef("notes.glkdata", FileUsage.DATA, temporary=True)

    assert_that(saved.usage).is_equal_to(FileUsage.SAVED_GAME)
    assert_that(saved.text_mode).is_true()
    assert_that(saved.temporary).is_false()
    assert_that(scratch.text_mode).is_false()
    assert_that(scratch.temporary).is_true()


# A byte file stream holds one Latin-1 byte per character in
# either mode (Glk: File Streams); what a byte cannot hold was
# already substituted upstream.
def test_byte_file_streams_hold_latin_1() -> None:
    handle = BytesIO()
    stream = FileStream(handle, FileMode.READ_WRITE)

    stream.put_string("ab")
    stream.put_char(0x2603)

    assert_that(handle.getvalue()).is_equal_to(b"ab?")

    stream.set_position(0, SeekMode.START)

    assert_that(stream.get_char()).is_equal_to(0x61)

    stream.set_position(-1, SeekMode.END)

    assert_that(stream.get_char()).is_equal_to(0x3F)
    assert_that(stream.get_char()).is_equal_to(-1)

    stream.set_position(1, SeekMode.START)
    stream.set_position(1, SeekMode.CURRENT)

    assert_that(stream.get_position()).is_equal_to(2)

    # An unknown seek mode measures from the start.
    stream.set_position(0, 9)

    assert_that(stream.get_position()).is_equal_to(0)

    stream.close()

    assert_that(handle.closed).is_true()


# A Unicode file stream in binary mode is four-byte big-endian
# words (Glk: File Streams).
def test_unicode_binary_file_streams_hold_words() -> None:
    handle = BytesIO()
    stream = FileStream(handle, FileMode.READ_WRITE, unicode=True)

    stream.put_char(0x1F600)

    assert_that(handle.getvalue()).is_equal_to(b"\x00\x01\xf6\x00")

    stream.set_position(0, SeekMode.START)

    assert_that(stream.get_char()).is_equal_to(0x1F600)
    assert_that(stream.get_char()).is_equal_to(-1)


# A Unicode file stream in text mode is UTF-8 with no byte-order
# mark (Glk: File Streams) -- which is what makes an ASCII file
# byte-identical to one written through the byte functions.
def test_unicode_text_file_streams_hold_utf8() -> None:
    handle = BytesIO()
    stream = FileStream(handle, FileMode.READ_WRITE, unicode=True, text_mode=True)

    stream.put_buffer([0x41, 0xE9, 0x2603, 0x1F600])

    assert_that(handle.getvalue()).is_equal_to(b"A\xc3\xa9\xe2\x98\x83\xf0\x9f\x98\x80")

    stream.set_position(0, SeekMode.START)

    assert_that(stream.get_char()).is_equal_to(0x41)
    assert_that(stream.get_char()).is_equal_to(0xE9)
    assert_that(stream.get_char()).is_equal_to(0x2603)
    assert_that(stream.get_char()).is_equal_to(0x1F600)
    assert_that(stream.get_char()).is_equal_to(-1)


# Damaged UTF-8 -- a stray continuation byte, or a sequence the
# file ends in the middle of -- reads as '?' rather than faulting:
# a position is anywhere a game seeks, so a mid-sequence start
# must be survivable.
def test_damaged_utf8_reads_as_question_marks() -> None:
    stray = FileStream(BytesIO(b"\x83A"), FileMode.READ, unicode=True, text_mode=True)

    assert_that(stray.get_char()).is_equal_to(0x3F)
    assert_that(stray.get_char()).is_equal_to(0x41)

    cut = FileStream(BytesIO(b"\xe2\x98"), FileMode.READ, unicode=True, text_mode=True)

    assert_that(cut.get_char()).is_equal_to(0x3F)


# A sound channel opens silent, at the volume asked for.
def test_sound_channels_open_silent() -> None:
    channel = SoundChannel()

    assert_that(channel.volume).is_equal_to(0x10000)
    assert_that(channel.sound).is_equal_to(0)
    assert_that(channel.repeats).is_equal_to(0)
    assert_that(channel.notify).is_equal_to(0)
    assert_that(channel.paused).is_false()


# An event defaults to "nothing happened" and hands its fields
# over in event_t order (Glk: Events).
def test_events_default_to_nothing_happened() -> None:
    quiet = Event()
    window = TextBufferWindow()
    typed = Event(EventType.CHAR_INPUT, window, 0x61, 0)

    assert_that(quiet.as_fields()).is_equal_to((EventType.NONE, None, 0, 0))
    assert_that(typed.as_fields()).is_equal_to((EventType.CHAR_INPUT, window, 0x61, 0))
