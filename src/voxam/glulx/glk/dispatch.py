"""The Glk dispatch layer: every function's signature.

The C world's gi_dispa.c (vendored with cheapglk) hand-writes a
thousand-line switch returning prototype strings like
``"4&#!CnIuIu:Qb"``. Voxam does the inverse: each function is
declared as a readable argument list, and the prototype string is
*generated* from it. The generated strings are then checked against
the ones parsed out of gi_dispa.c -- for every function -- in the
tests, which turns a transcription error into a test failure
instead of a runtime mystery.

The grammar, as gi_dispa.c defines it: a prototype is a count
followed by items, like ``"3Qa<Iu:Qa"`` for glk_window_iterate. The
count includes the return value, which is the item carrying the
``:`` prefix; a void function ends with a bare ``:`` that is not
counted. Prefixes appear in the order ``[ref][+][#][!]`` before the
type code -- reference direction, nonnull, array, retained.
"""

from dataclasses import dataclass, replace

# The opaque class numbers, from gi_dispa.h. The prototype codes
# Qa through Qd map onto these in order.
CLASS_WINDOW = 0
CLASS_STREAM = 1
CLASS_FILEREF = 2
CLASS_SCHANNEL = 3

_OPAQUE_CODES = {
    "Qa": CLASS_WINDOW,
    "Qb": CLASS_STREAM,
    "Qc": CLASS_FILEREF,
    "Qd": CLASS_SCHANNEL,
}
_SIGNED_CODES = frozenset({"Is", "Cs"})
_BYTE_CODES = frozenset({"Cn", "Cu", "Cs"})
_STRING_CODES = frozenset({"S", "U"})


@dataclass(frozen=True)
class Item:
    """One item in a prototype: an argument, or the return value.

    Attributes:
        code: The type code -- ``Iu``, ``Cn``, ``Qa``, and kin.
            Empty when the item is a struct.
        fields: The field types, when this item is a struct.
        ref: The reference direction: ``""`` for a plain value,
            ``"<"`` out, ``">"`` in, ``"&"`` both, ``":"`` for the
            return value.
        array: Whether the item is an array, consuming an address
            and a count.
        nonnull: Whether a null reference is forbidden.
        retained: Whether Glk keeps the array after the call.
    """

    code: str
    fields: tuple["Item", ...] = ()
    ref: str = ""
    array: bool = False
    nonnull: bool = False
    retained: bool = False

    @property
    def is_struct(self) -> bool:
        """Whether this item is a struct of fields."""

        return bool(self.fields)

    @property
    def is_opaque(self) -> bool:
        """Whether this item is one of the four opaque classes."""

        return self.code in _OPAQUE_CODES

    @property
    def opaque_class(self) -> int | None:
        """The opaque class number, or None for a plain type."""

        return _OPAQUE_CODES.get(self.code)

    @property
    def is_string(self) -> bool:
        """Whether this item is a string object address."""

        return self.code in _STRING_CODES

    @property
    def signed(self) -> bool:
        """Whether this item's value is signed."""

        return self.code in _SIGNED_CODES

    @property
    def element_size(self) -> int:
        """Bytes per element: 1 for the char types, 4 otherwise."""

        return 1 if self.code in _BYTE_CODES else 4

    @property
    def passes_in(self) -> bool:
        """Whether a value passes from the game into Glk."""

        return self.ref in (">", "&")

    @property
    def passes_out(self) -> bool:
        """Whether a value passes from Glk back to the game."""

        return self.ref in ("<", "&", ":")

    @property
    def is_reference(self) -> bool:
        """Whether the game passes an address rather than a value."""

        return self.ref in ("<", ">", "&")

    @property
    def word_count(self) -> int:
        """How many 32-bit Glulx arguments this item consumes.

        "An array argument, unlike a string argument, is always
        followed by an array length argument" -- so an array is two
        words where everything else is one (Glulx: Miscellaneous,
        under the glk opcode).
        """

        return 2 if self.array else 1

    @property
    def prototype(self) -> str:
        """This item rendered in gi_dispa.c's prototype grammar."""

        body = (
            f"[{len(self.fields)}{''.join(f.prototype for f in self.fields)}]"
            if self.is_struct
            else self.code
        )

        prefix = self.ref

        if self.nonnull:
            prefix += "+"

        if self.array:
            prefix += "#"

        if self.retained:
            prefix += "!"

        return prefix + body


@dataclass(frozen=True)
class Signature:
    """One Glk function's dispatch signature.

    Attributes:
        number: The selector the glk opcode names the function by.
        name: The bare function name, without the glk_ prefix.
        args: The argument items, in call order.
        result: The return item, or None for a void function.
    """

    number: int
    name: str
    args: tuple[Item, ...] = ()
    result: Item | None = None

    @property
    def glk_name(self) -> str:
        """The function's full name, glk_ prefix included."""

        return f"glk_{self.name}"

    @property
    def word_count(self) -> int:
        """Total 32-bit arguments the glk opcode must supply."""

        return sum(arg.word_count for arg in self.args)

    @property
    def prototype(self) -> str:
        """The whole signature in gi_dispa.c's prototype grammar."""

        count = len(self.args) + (1 if self.result is not None else 0)
        body = "".join(arg.prototype for arg in self.args)
        tail = replace(self.result, ref=":").prototype if self.result else ":"

        return f"{count}{body}{tail}"


# The atoms the table is written in. UNICHAR is U32 on purpose: a
# Unicode character argument is a full word, where the Latin-1 char
# types are bytes.
U32 = Item("Iu")
I32 = Item("Is")
CHAR = Item("Cn")
UCHAR = Item("Cu")
CSTRING = Item("S")
USTRING = Item("U")

WINDOW = Item("Qa")
STREAM = Item("Qb")
FILEREF = Item("Qc")
SCHANNEL = Item("Qd")


def out(item: Item, *, nonnull: bool = False) -> Item:
    """An output reference: Glk writes, the game reads."""

    return replace(item, ref="<", nonnull=nonnull)


def into(item: Item, *, nonnull: bool = False) -> Item:
    """An input reference: the game writes, Glk reads."""

    return replace(item, ref=">", nonnull=nonnull)


def inout(item: Item, *, nonnull: bool = False) -> Item:
    """A reference passing both ways."""

    return replace(item, ref="&", nonnull=nonnull)


def struct(*fields: Item) -> Item:
    """A struct of fields, passed as one reference."""

    return Item("", fields=fields)


def array(
    item: Item,
    ref: str,
    *,
    nonnull: bool = False,
    retained: bool = False,
) -> Item:
    """An array of items: an address and a count, two words."""

    return replace(item, ref=ref, array=True, nonnull=nonnull, retained=retained)


# The well-known structures, named in gi_dispa.h: event_t,
# stream_result_t, glktimeval_t, glkdate_t.
EVENT = struct(U32, WINDOW, U32, U32)
STREAM_RESULT = struct(U32, U32)
TIMEVAL = struct(I32, U32, I32)
DATE = struct(I32, I32, I32, I32, I32, I32, I32, I32)


_SIGNATURES: dict[int, Signature] = {}


def _declare(
    number: int, name: str, args: list[Item], result: Item | None = None
) -> None:
    _SIGNATURES[number] = Signature(number, name, tuple(args), result)


# The table, ordered as in gi_dispa.c. glk_set_interrupt_handler
# (0x0002) is absent on purpose: its prototype there is NULL,
# meaning it cannot be invoked through the dispatch layer at all.

# Core
_declare(0x0001, "exit", [])
_declare(0x0003, "tick", [])
_declare(0x0004, "gestalt", [U32, U32], U32)
_declare(0x0005, "gestalt_ext", [U32, U32, array(U32, "&")], U32)

# Windows
_declare(0x0020, "window_iterate", [WINDOW, out(U32)], WINDOW)
_declare(0x0021, "window_get_rock", [WINDOW], U32)
_declare(0x0022, "window_get_root", [], WINDOW)
_declare(0x0023, "window_open", [WINDOW, U32, U32, U32, U32], WINDOW)
_declare(0x0024, "window_close", [WINDOW, out(STREAM_RESULT)])
_declare(0x0025, "window_get_size", [WINDOW, out(U32), out(U32)])
_declare(0x0026, "window_set_arrangement", [WINDOW, U32, U32, WINDOW])
_declare(0x0027, "window_get_arrangement", [WINDOW, out(U32), out(U32), out(WINDOW)])
_declare(0x0028, "window_get_type", [WINDOW], U32)
_declare(0x0029, "window_get_parent", [WINDOW], WINDOW)
_declare(0x002A, "window_clear", [WINDOW])
_declare(0x002B, "window_move_cursor", [WINDOW, U32, U32])
_declare(0x002C, "window_get_stream", [WINDOW], STREAM)
_declare(0x002D, "window_set_echo_stream", [WINDOW, STREAM])
_declare(0x002E, "window_get_echo_stream", [WINDOW], STREAM)
_declare(0x002F, "set_window", [WINDOW])
_declare(0x0030, "window_get_sibling", [WINDOW], WINDOW)

# Streams
_declare(0x0040, "stream_iterate", [STREAM, out(U32)], STREAM)
_declare(0x0041, "stream_get_rock", [STREAM], U32)
_declare(0x0042, "stream_open_file", [FILEREF, U32, U32], STREAM)
_declare(
    0x0043, "stream_open_memory", [array(CHAR, "&", retained=True), U32, U32], STREAM
)
_declare(0x0044, "stream_close", [STREAM, out(STREAM_RESULT)])
_declare(0x0045, "stream_set_position", [STREAM, I32, U32])
_declare(0x0046, "stream_get_position", [STREAM], U32)
_declare(0x0047, "stream_set_current", [STREAM])
_declare(0x0048, "stream_get_current", [], STREAM)
_declare(0x0049, "stream_open_resource", [U32, U32], STREAM)

# File references
_declare(0x0060, "fileref_create_temp", [U32, U32], FILEREF)
_declare(0x0061, "fileref_create_by_name", [U32, CSTRING, U32], FILEREF)
_declare(0x0062, "fileref_create_by_prompt", [U32, U32, U32], FILEREF)
_declare(0x0063, "fileref_destroy", [FILEREF])
_declare(0x0064, "fileref_iterate", [FILEREF, out(U32)], FILEREF)
_declare(0x0065, "fileref_get_rock", [FILEREF], U32)
_declare(0x0066, "fileref_delete_file", [FILEREF])
_declare(0x0067, "fileref_does_file_exist", [FILEREF], U32)
_declare(0x0068, "fileref_create_from_fileref", [U32, FILEREF, U32], FILEREF)

# Character output
_declare(0x0080, "put_char", [UCHAR])
_declare(0x0081, "put_char_stream", [STREAM, UCHAR])
_declare(0x0082, "put_string", [CSTRING])
_declare(0x0083, "put_string_stream", [STREAM, CSTRING])
_declare(0x0084, "put_buffer", [array(CHAR, ">", nonnull=True)])
_declare(0x0085, "put_buffer_stream", [STREAM, array(CHAR, ">", nonnull=True)])
_declare(0x0086, "set_style", [U32])
_declare(0x0087, "set_style_stream", [STREAM, U32])

# Character input
_declare(0x0090, "get_char_stream", [STREAM], I32)
_declare(0x0091, "get_line_stream", [STREAM, array(CHAR, "<", nonnull=True)], U32)
_declare(0x0092, "get_buffer_stream", [STREAM, array(CHAR, "<", nonnull=True)], U32)

# Case mapping
_declare(0x00A0, "char_to_lower", [UCHAR], UCHAR)
_declare(0x00A1, "char_to_upper", [UCHAR], UCHAR)

# Style hints
_declare(0x00B0, "stylehint_set", [U32, U32, U32, I32])
_declare(0x00B1, "stylehint_clear", [U32, U32, U32])
_declare(0x00B2, "style_distinguish", [WINDOW, U32, U32], U32)
_declare(0x00B3, "style_measure", [WINDOW, U32, U32, out(U32)], U32)

# Events
_declare(0x00C0, "select", [out(EVENT, nonnull=True)])
_declare(0x00C1, "select_poll", [out(EVENT, nonnull=True)])
_declare(
    0x00D0,
    "request_line_event",
    [WINDOW, array(CHAR, "&", nonnull=True, retained=True), U32],
)
_declare(0x00D1, "cancel_line_event", [WINDOW, out(EVENT)])
_declare(0x00D2, "request_char_event", [WINDOW])
_declare(0x00D3, "cancel_char_event", [WINDOW])
_declare(0x00D4, "request_mouse_event", [WINDOW])
_declare(0x00D5, "cancel_mouse_event", [WINDOW])
_declare(0x00D6, "request_timer_events", [U32])

# Graphics
_declare(0x00E0, "image_get_info", [U32, out(U32), out(U32)], U32)
_declare(0x00E1, "image_draw", [WINDOW, U32, I32, I32], U32)
_declare(0x00E2, "image_draw_scaled", [WINDOW, U32, I32, I32, U32, U32], U32)
_declare(0x00E8, "window_flow_break", [WINDOW])
_declare(0x00E9, "window_erase_rect", [WINDOW, I32, I32, U32, U32])
_declare(0x00EA, "window_fill_rect", [WINDOW, U32, I32, I32, U32, U32])
_declare(0x00EB, "window_set_background_color", [WINDOW, U32])
_declare(
    0x00EC, "image_draw_scaled_ext", [WINDOW, U32, I32, I32, U32, U32, U32, U32], U32
)

# Sound channels
_declare(0x00F0, "schannel_iterate", [SCHANNEL, out(U32)], SCHANNEL)
_declare(0x00F1, "schannel_get_rock", [SCHANNEL], U32)
_declare(0x00F2, "schannel_create", [U32], SCHANNEL)
_declare(0x00F3, "schannel_destroy", [SCHANNEL])
_declare(0x00F4, "schannel_create_ext", [U32, U32], SCHANNEL)
_declare(
    0x00F7,
    "schannel_play_multi",
    [array(SCHANNEL, ">", nonnull=True), array(U32, ">", nonnull=True), U32],
    U32,
)
_declare(0x00F8, "schannel_play", [SCHANNEL, U32], U32)
_declare(0x00F9, "schannel_play_ext", [SCHANNEL, U32, U32, U32], U32)
_declare(0x00FA, "schannel_stop", [SCHANNEL])
_declare(0x00FB, "schannel_set_volume", [SCHANNEL, U32])
_declare(0x00FC, "sound_load_hint", [U32, U32])
_declare(0x00FD, "schannel_set_volume_ext", [SCHANNEL, U32, U32, U32])
_declare(0x00FE, "schannel_pause", [SCHANNEL])
_declare(0x00FF, "schannel_unpause", [SCHANNEL])

# Hyperlinks
_declare(0x0100, "set_hyperlink", [U32])
_declare(0x0101, "set_hyperlink_stream", [STREAM, U32])
_declare(0x0102, "request_hyperlink_event", [WINDOW])
_declare(0x0103, "cancel_hyperlink_event", [WINDOW])

# Unicode case mapping and normalization
_declare(0x0120, "buffer_to_lower_case_uni", [array(U32, "&", nonnull=True), U32], U32)
_declare(0x0121, "buffer_to_upper_case_uni", [array(U32, "&", nonnull=True), U32], U32)
_declare(
    0x0122, "buffer_to_title_case_uni", [array(U32, "&", nonnull=True), U32, U32], U32
)
_declare(
    0x0123, "buffer_canon_decompose_uni", [array(U32, "&", nonnull=True), U32], U32
)
_declare(
    0x0124, "buffer_canon_normalize_uni", [array(U32, "&", nonnull=True), U32], U32
)

# Unicode output
_declare(0x0128, "put_char_uni", [U32])
_declare(0x0129, "put_string_uni", [USTRING])
_declare(0x012A, "put_buffer_uni", [array(U32, ">", nonnull=True)])
_declare(0x012B, "put_char_stream_uni", [STREAM, U32])
_declare(0x012C, "put_string_stream_uni", [STREAM, USTRING])
_declare(0x012D, "put_buffer_stream_uni", [STREAM, array(U32, ">", nonnull=True)])

# Unicode input
_declare(0x0130, "get_char_stream_uni", [STREAM], I32)
_declare(0x0131, "get_buffer_stream_uni", [STREAM, array(U32, "<", nonnull=True)], U32)
_declare(0x0132, "get_line_stream_uni", [STREAM, array(U32, "<", nonnull=True)], U32)
_declare(0x0138, "stream_open_file_uni", [FILEREF, U32, U32], STREAM)
_declare(
    0x0139, "stream_open_memory_uni", [array(U32, "&", retained=True), U32, U32], STREAM
)
_declare(0x013A, "stream_open_resource_uni", [U32, U32], STREAM)
_declare(0x0140, "request_char_event_uni", [WINDOW])
_declare(
    0x0141,
    "request_line_event_uni",
    [WINDOW, array(U32, "&", nonnull=True, retained=True), U32],
)

# Line input control
_declare(0x0150, "set_echo_line_event", [WINDOW, U32])
_declare(0x0151, "set_terminators_line_event", [WINDOW, array(U32, ">")])

# Date and time
_declare(0x0160, "current_time", [out(TIMEVAL, nonnull=True)])
_declare(0x0161, "current_simple_time", [U32], I32)
_declare(
    0x0168, "time_to_date_utc", [into(TIMEVAL, nonnull=True), out(DATE, nonnull=True)]
)
_declare(
    0x0169, "time_to_date_local", [into(TIMEVAL, nonnull=True), out(DATE, nonnull=True)]
)
_declare(0x016A, "simple_time_to_date_utc", [I32, U32, out(DATE, nonnull=True)])
_declare(0x016B, "simple_time_to_date_local", [I32, U32, out(DATE, nonnull=True)])
_declare(
    0x016C, "date_to_time_utc", [into(DATE, nonnull=True), out(TIMEVAL, nonnull=True)]
)
_declare(
    0x016D, "date_to_time_local", [into(DATE, nonnull=True), out(TIMEVAL, nonnull=True)]
)
_declare(0x016E, "date_to_simple_time_utc", [into(DATE, nonnull=True), U32], I32)
_declare(0x016F, "date_to_simple_time_local", [into(DATE, nonnull=True), U32], I32)


def lookup(number: int) -> Signature | None:
    """Return the signature for a Glk selector, or None if unknown."""

    return _SIGNATURES.get(number)


def all_signatures() -> dict[int, Signature]:
    """Every declared signature, keyed by selector."""

    return dict(_SIGNATURES)
