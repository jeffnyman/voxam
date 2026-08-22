from assertpy import assert_that

from voxam.glulx.glk.wrap import SCROLLBACK, Wrapper, plain, wrap, wrap_segments


# One accumulated window, spoken to in plain text for brevity.
def wrapped(width: int, *texts: str) -> Wrapper:
    wrapper = Wrapper(width)
    wrapper.add((0, text) for text in texts)

    return wrapper


def shown(wrapper: Wrapper) -> list[str]:
    return [plain(line) for line in wrapper.lines]


# Lines break at spaces, and the space at the break costs nothing:
# it is dropped rather than carried to the next line.
def test_wrap_breaks_at_spaces() -> None:
    assert_that(wrap("the deep magic word", 9)).is_equal_to(
        ["the deep", "magic", "word"]
    )


# The break may fall on the character just past the line, since a
# space there is about to be dropped anyway.
def test_wrap_breaks_on_the_space_past_the_line() -> None:
    assert_that(wrap("xyzzy plugh", 5)).is_equal_to(["xyzzy", "plugh"])


# A word wider than the whole line is cut rather than left to
# overflow into a neighbouring window.
def test_wrap_cuts_a_word_wider_than_the_line() -> None:
    assert_that(wrap("overincredulous", 6)).is_equal_to(["overin", "credul", "ous"])


# Newlines are consumed as hard breaks, and a blank line in the
# text stays a blank line on the display.
def test_wrap_honours_newlines() -> None:
    assert_that(wrap("above\n\nbelow", 20)).is_equal_to(["above", "", "below"])


# A width below one is treated as one: no window is thin enough to
# hold no characters at all.
def test_wrap_clamps_the_width() -> None:
    assert_that(wrap("ab", 0)).is_equal_to(["a", "b"])


# Breaking a line cuts the segments that make it up, so each piece
# keeps the style it arrived wearing.
def test_wrap_segments_keeps_the_styles() -> None:
    lines = wrap_segments([(1, "bold text "), (2, "and italic")], 10)

    assert_that(lines).is_equal_to([[(1, "bold text")], [(2, "and italic")]])


# An empty paragraph is still one display line, or a blank line in
# the text would vanish from the layout.
def test_wrap_segments_of_nothing_is_one_empty_line() -> None:
    assert_that(wrap_segments([], 10)).is_equal_to([[]])


# A segment that straddles a blank line contributes nothing to it:
# the empty slice is skipped rather than kept as an empty piece.
def test_wrap_segments_leaves_blank_lines_empty() -> None:
    lines = wrap_segments([(0, "up\n\ndown")], 10)

    assert_that(lines).is_equal_to([[(0, "up")], [], [(0, "down")]])


# plain flattens a styled line back to its text.
def test_plain_strips_the_styling() -> None:
    assert_that(plain([(1, "xy"), (2, "zzy")])).is_equal_to("xyzzy")


# Output arriving in pieces continues the open paragraph, and
# same-styled pieces fuse into one segment.
def test_the_wrapper_folds_pieces_into_the_open_paragraph() -> None:
    wrapper = wrapped(20, "You are in a ", "maze", " of twisty passages")

    assert_that(shown(wrapper)).is_equal_to(["You are in a maze of", "twisty passages"])
    assert_that(wrapper.lines[0]).is_length(1)


# Differently styled pieces stay separate segments, and empty
# pieces vanish without starting anything.
def test_the_wrapper_keeps_styles_apart() -> None:
    wrapper = Wrapper(30)
    wrapper.add([(0, "a "), (0, ""), (1, "magic"), (0, " word\n"), (0, "")])

    assert_that(wrapper.lines[0]).is_equal_to([(0, "a "), (1, "magic"), (0, " word")])


# A newline completes the paragraph; what follows opens the next.
def test_a_newline_breaks_the_paragraph() -> None:
    wrapper = wrapped(20, "West of House\n", "You are standing")

    assert_that(shown(wrapper)).is_equal_to(["West of House", "You are standing"])


# The preview shows the display lines as if the runs had been
# added, without adding them: the typed line takes part in the
# layout before the game has accepted it.
def test_the_preview_does_not_commit() -> None:
    wrapper = wrapped(20, "What now?\n", "> ")

    preview = wrapper.preview([(8, "go north")])

    assert_that(plain(preview[-1])).is_equal_to("> go north")
    assert_that(shown(wrapper)).is_equal_to(["What now?", "> "])


# Previewing nothing is just the lines as they stand.
def test_an_empty_preview_is_the_lines() -> None:
    wrapper = wrapped(20, "steady")

    assert_that(wrapper.preview([])).is_equal_to(wrapper.lines)


# When everything unseen fits in the window, the view is the
# newest windowful and the player is considered to have read it.
def test_a_view_that_fits_advances_seen() -> None:
    wrapper = wrapped(20, "one\ntwo\nthree")

    view = wrapper.view(5)

    assert_that([plain(line) for line in view.lines]).is_equal_to(
        ["one", "two", "three"]
    )
    assert_that(view.start).is_equal_to(0)
    assert_that(view.more).is_false()
    assert_that(wrapper.seen).is_equal_to(3)


# More text than a windowful holds the view at the first page,
# repaint after repaint, until the player advances -- which is
# what makes the pause a pause.
def test_a_full_window_waits_to_be_read() -> None:
    wrapper = wrapped(10, "\n".join(str(index) for index in range(9)))

    first = wrapper.view(4)

    assert_that(first.more).is_true()
    assert_that([plain(line) for line in first.lines]).is_equal_to(["0", "1", "2"])
    assert_that(wrapper.view(4)).is_equal_to(first)

    wrapper.advance(4)
    second = wrapper.view(4)

    assert_that(second.more).is_true()
    assert_that(second.start).is_equal_to(2)

    wrapper.advance(4)
    last = wrapper.view(4)

    assert_that(last.more).is_false()
    assert_that([plain(line) for line in last.lines]).contains("8")


# The view of a window with no rows is nothing at all.
def test_a_flat_window_shows_nothing() -> None:
    wrapper = wrapped(10, "words")

    assert_that(wrapper.view(0).lines).is_empty()


# In a one-line window the page and the overlap are both a single
# line; the advance still moves, or the prompt would never clear.
def test_a_tiny_window_still_turns_its_page() -> None:
    wrapper = wrapped(10, "a\nb\nc")

    assert_that(wrapper.view(1).more).is_true()

    wrapper.advance(1)

    assert_that(wrapper.seen).is_equal_to(1)


# Catching up declares everything read, however much is waiting.
def test_catching_up_reads_everything() -> None:
    wrapper = wrapped(10, "\n".join("abcdefgh"))

    assert_that(wrapper.view(3).more).is_true()

    wrapper.catch_up()

    assert_that(wrapper.view(3).more).is_false()


# A resize recomputes the display lines from the original
# paragraphs, so no break point loses its space twice.
def test_a_resize_rewraps_from_the_paragraphs() -> None:
    wrapper = wrapped(20, "hello wide world")

    assert_that(shown(wrapper)).is_equal_to(["hello wide world"])

    wrapper.resize(10)

    assert_that(shown(wrapper)).is_equal_to(["hello wide", "world"])

    wrapper.resize(10)

    assert_that(shown(wrapper)).is_equal_to(["hello wide", "world"])


# A cleared window has no past.
def test_clearing_forgets_everything() -> None:
    wrapper = wrapped(10, "gone\n")
    wrapper.view(3)

    wrapper.clear()

    assert_that(shown(wrapper)).is_equal_to([""])
    assert_that(wrapper.seen).is_equal_to(0)


# Past the scrollback limit the oldest paragraphs are dropped in a
# batch, and the display lines are recomputed from what remains.
def test_the_scrollback_is_bounded() -> None:
    wrapper = Wrapper(20)

    for index in range(SCROLLBACK + 202):
        wrapper.add([(0, f"turn {index}\n")])

    lines = shown(wrapper)

    assert_that(len(lines)).is_less_than_or_equal_to(SCROLLBACK + 3)
    assert_that(lines[0]).is_equal_to("turn 200")
    assert_that(lines[-2]).is_equal_to(f"turn {SCROLLBACK + 201}")
