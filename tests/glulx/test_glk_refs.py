"""The reference holders Glk writes results into."""

import pytest
from assertpy import assert_that

from voxam.glulx.glk.objects import TextBufferWindow
from voxam.glulx.glk.refs import Ref, RefStruct


# A ref holds one value -- a word by default, an opaque object
# when the answer is one, since turning objects into ids is the
# bridge's translation, not the library's.
def test_a_ref_holds_one_value() -> None:
    empty = Ref()
    window = TextBufferWindow()
    holding = Ref(7)

    holding.value = window

    assert_that(empty.value).is_equal_to(0)
    assert_that(holding.value).is_same_as(window)


# A struct is a fixed row: set_all fills every field at once, and
# a wrong count is refused -- a struct has no optional members.
def test_a_struct_fills_all_fields_or_none() -> None:
    struct = RefStruct(3)

    assert_that(struct.fields).is_equal_to([0, 0, 0])

    struct.set_all(1, 2, 3)

    assert_that(struct.fields).is_equal_to([1, 2, 3])

    with pytest.raises(ValueError, match="expected 3 fields, got 2"):
        struct.set_all(1, 2)
