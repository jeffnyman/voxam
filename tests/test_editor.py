"""The line editor: pure transitions, and the shared read loop."""

from assertpy import assert_that

from voxam.editor import EXPIRED, HISTORY_LIMIT, LineEditor, read_line_edited


def composed(*lines: str) -> LineEditor:
    editor = LineEditor()

    for line in lines:
        for character in line:
            editor.insert(character)

        editor.submit()

    return editor


class FakeCanvas:
    """Records the echo operations the loop performs."""

    def __init__(self) -> None:
        self.operations: list[tuple[str, object]] = []

    def write(self, text: str) -> None:
        self.operations.append(("write", text))

    def retreat(self, cells: int) -> int:
        self.operations.append(("retreat", cells))

        return cells


def run(
    editor: LineEditor, keys: list[str | None]
) -> tuple[str | None, FakeCanvas, int]:
    canvas = FakeCanvas()
    remaining = list(keys)
    repaints = 0

    def repaint() -> None:
        nonlocal repaints
        repaints += 1

    line = read_line_edited(editor, canvas, lambda: remaining.pop(0), repaint)

    return line, canvas, repaints


# Typing builds the line at the insertion point, and submit hands
# it over and resets for the next.
def test_typing_and_submitting() -> None:
    editor = LineEditor()

    for character in "go":
        editor.insert(character)

    assert_that(editor.text).is_equal_to("go")
    assert_that(editor.cursor).is_equal_to(2)
    assert_that(editor.submit()).is_equal_to("go")
    assert_that(editor.text).is_empty()


# Rub-out deletes the character before the insertion point; at the
# line's start there is nothing left of the line to rub.
def test_rub_out_deletes_before_the_cursor() -> None:
    editor = LineEditor()

    for character in "cat":
        editor.insert(character)

    editor.left()

    assert_that(editor.rub_out()).is_true()
    assert_that(editor.text).is_equal_to("ct")
    assert_that(editor.left()).is_true()
    assert_that(editor.rub_out()).is_false()


# The cursor moves within the line and stops honestly at both ends.
def test_cursor_motion_stops_at_the_ends() -> None:
    editor = LineEditor()
    editor.insert("x")

    assert_that(editor.right()).is_false()
    assert_that(editor.left()).is_true()
    assert_that(editor.left()).is_false()
    assert_that(editor.right()).is_true()


# An insertion mid-line lands at the cursor, not the end.
def test_insertion_lands_at_the_cursor() -> None:
    editor = LineEditor()

    for character in "gt":
        editor.insert(character)

    editor.left()
    editor.insert("e")

    assert_that(editor.text).is_equal_to("get")
    assert_that(editor.cursor).is_equal_to(2)


# Cursor-up walks back through the session's history, oldest last,
# and stops there; with no history at all it is quietly nothing.
def test_earlier_walks_back_through_history() -> None:
    assert_that(LineEditor().earlier()).is_false()

    editor = composed("north", "south")

    assert_that(editor.earlier()).is_true()
    assert_that(editor.text).is_equal_to("south")
    assert_that(editor.earlier()).is_true()
    assert_that(editor.text).is_equal_to("north")
    assert_that(editor.earlier()).is_false()


# Cursor-down walks forward again and, past the newest history
# line, restores the draft that recall interrupted.
def test_later_returns_to_the_draft() -> None:
    editor = composed("north")

    for character in "dr":
        editor.insert(character)

    editor.earlier()

    assert_that(editor.text).is_equal_to("north")
    assert_that(editor.later()).is_true()
    assert_that(editor.text).is_equal_to("dr")
    assert_that(editor.later()).is_false()


# Walking down through the middle of history recalls each line on
# the way back to the draft.
def test_later_recalls_intermediate_lines() -> None:
    editor = composed("north", "south")

    editor.earlier()
    editor.earlier()
    editor.later()

    assert_that(editor.text).is_equal_to("south")


# An empty line never joins the history, and repeating a command
# records it once -- recall should not walk through repetitions.
def test_history_skips_empties_and_repeats() -> None:
    editor = composed("look", "look")

    editor.submit()
    editor.earlier()

    assert_that(editor.text).is_equal_to("look")
    assert_that(editor.earlier()).is_false()


# The history is bounded: the oldest line falls off past the limit.
def test_history_is_bounded() -> None:
    editor = composed(*(f"go {index}" for index in range(HISTORY_LIMIT + 1)))

    while editor.earlier():
        pass

    assert_that(editor.text).is_equal_to("go 1")


# The loop types a line through the canvas and submits on enter,
# with the fast path writing each appended character as itself.
def test_loop_types_and_submits() -> None:
    line, canvas, _repaints = run(LineEditor(), ["h", "i", "\n"])

    assert_that(line).is_equal_to("hi")
    assert_that(canvas.operations).is_equal_to(
        [("write", "h"), ("write", "i"), ("write", "\n")]
    )


# Idle heartbeats (None) and escape are waited out, as are the
# §3.8.4 input-only codes beyond the editing keys.
def test_loop_waits_out_unusable_keys() -> None:
    line, _canvas, repaints = run(LineEditor(), [None, "\x1b", "\x85", "y", "\n"])

    assert_that(line).is_equal_to("y")
    assert_that(repaints).is_equal_to(2)


# An editing key that changes nothing repaints nothing: rub-out at
# the line's start is quiet.
def test_loop_skips_redraws_that_change_nothing() -> None:
    _line, canvas, repaints = run(LineEditor(), ["\x7f", "\n"])

    assert_that(canvas.operations).is_equal_to([("write", "\n")])
    assert_that(repaints).is_equal_to(1)


# A mid-line edit redraws the whole line from its start: retreat to
# the beginning, the new text, and the cursor walked back to its
# place.
def test_loop_redraws_mid_line_edits() -> None:
    line, canvas, _repaints = run(LineEditor(), ["g", "t", "\x83", "e", "\n"])

    assert_that(line).is_equal_to("get")
    assert_that(canvas.operations).contains(("retreat", 2), ("write", "gt"))
    assert_that(canvas.operations).contains(("write", "get"), ("retreat", 1))


# Recalling a shorter line blanks the longer draft's remnant with
# spaces, then retreats over them.
def test_loop_blanks_recall_remnants() -> None:
    editor = composed("in")

    line, canvas, _repaints = run(editor, ["l", "o", "o", "k", "\x81", "\n"])

    assert_that(line).is_equal_to("in")
    assert_that(canvas.operations).contains(("write", "in"), ("write", "  "))


# Cursor-down walks recall forward again inside the loop.
def test_loop_walks_history_both_ways() -> None:
    editor = composed("north", "south")

    line, _canvas, _repaints = run(editor, ["\x81", "\x81", "\x82", "\n"])

    assert_that(line).is_equal_to("south")


# The right cursor key moves back over a line the left key walked
# into, restoring the append fast path at the end.
def test_loop_moves_right_after_left() -> None:
    line, _canvas, _repaints = run(LineEditor(), ["a", "\x83", "\x84", "b", "\n"])

    assert_that(line).is_equal_to("ab")


# An EXPIRED answer pauses the read: the loop hands back None with
# the composed line intact, and a fresh=False call resumes it to
# completion -- how a timed read survives its interrupts.
def test_expiry_pauses_and_resume_completes() -> None:
    editor = LineEditor()
    line, _canvas, _repaints = run(editor, ["g", "o", EXPIRED])

    assert_that(line).is_none()
    assert_that(editor.text).is_equal_to("go")

    canvas = FakeCanvas()
    keys = iter([" ", "n", "\n"])
    resumed = read_line_edited(
        editor, canvas, lambda: next(keys), lambda: None, fresh=False
    )

    assert_that(resumed).is_equal_to("go n")
