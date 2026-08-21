"""The holders Glk writes reference results into.

A Glk function returning through a pointer -- a window size, an
event_t, a stream_result_t -- needs somewhere to put the values.
In C that is the caller's pointer; here it is one of these holders,
the shape glkote's glkapi.js calls RefBox and RefStruct. The
library fills them; the bridge era is what copies their contents
back into VM memory or onto the stack.

A held value may be an opaque object rather than a word -- an
event names its window, an arrangement names its key -- because
turning objects into the 32-bit ids Glulx sees is the bridge's
translation, not the library's.
"""

from voxam.glulx.glk.objects import GlkObject

# What a reference can hold: a word, an opaque object, or the null
# object.
Held = int | GlkObject | None


class Ref:
    """A single call-by-reference output value.

    Attributes:
        value: The held value.
    """

    def __init__(self, value: Held = 0) -> None:
        """Start at a value, zero by default."""

        self.value = value


class RefStruct:
    """A struct passed by reference: a fixed row of fields.

    Attributes:
        fields: The field values, in the struct's declared order.
    """

    def __init__(self, count: int) -> None:
        """Open with a count of zeroed fields."""

        self.fields: list[Held] = [0] * count

    def set_all(self, *values: Held) -> None:
        """Fill every field at once.

        Raises:
            ValueError: If the count of values is not the count of
                fields -- a struct has no optional members.
        """

        if len(values) != len(self.fields):
            msg = f"expected {len(self.fields)} fields, got {len(values)}"

            raise ValueError(msg)

        self.fields[:] = values
