"""The opcode tables: names, version spans, and rider flags (§14).

Each entry records only what full decoding needs to know about an
opcode: its name, which versions define it, and whether a store byte,
branch data, or literal text follows its operands. Semantics arrive
with execution, not here.

The table data below was machine-extracted from the §14 tables in the
project's recomposed Standard and then hand-checked against the known
version forks. Versions 7 and 8 are Version 5 variants (§1.1), so a
span that opens at 5 runs to 8 unless the table says otherwise.
"""

from dataclasses import dataclass
from enum import Enum

from voxam.errors import ZMachineInstructionError

FIRST_VERSION = 1
LAST_VERSION = 8


class OpcodeKind(Enum):
    """Which of the five §14 tables an opcode number is looked up in."""

    ZERO_OP = "0OP"
    ONE_OP = "1OP"
    TWO_OP = "2OP"
    VAR = "VAR"
    EXT = "EXT"


@dataclass(frozen=True)
class Opcode:
    """What decoding must know about one opcode (§14).

    Attributes:
        name: The Inform name of the opcode.
        stores: Whether a store byte follows the operands (§4.6).
        branches: Whether branch data follows (§4.7).
        has_text: Whether an encoded string follows (§3.2); true only
            for print and print_ret.
    """

    name: str
    stores: bool = False
    branches: bool = False
    has_text: bool = False


# A table entry: the first and last version defining the opcode, and
# the opcode itself. A number maps to a tuple of entries because some
# opcodes fork across versions (save, pop/catch, not/call_1n, pull).
_Entry = tuple[int, int, Opcode]


def _op(
    name: str,
    *,
    first: int = FIRST_VERSION,
    last: int = LAST_VERSION,
    stores: bool = False,
    branches: bool = False,
) -> _Entry:
    """Build a table entry, defaulting to all versions and no riders.

    The two text-carrying opcodes are written as explicit entries in
    the 0OP table rather than adding a parameter here.
    """

    return (first, last, Opcode(name, stores, branches))


_TWO_OP: dict[int, tuple[_Entry, ...]] = {
    0x01: (_op("je", branches=True),),
    0x02: (_op("jl", branches=True),),
    0x03: (_op("jg", branches=True),),
    0x04: (_op("dec_chk", branches=True),),
    0x05: (_op("inc_chk", branches=True),),
    0x06: (_op("jin", branches=True),),
    0x07: (_op("test", branches=True),),
    0x08: (_op("or", stores=True),),
    0x09: (_op("and", stores=True),),
    0x0A: (_op("test_attr", branches=True),),
    0x0B: (_op("set_attr"),),
    0x0C: (_op("clear_attr"),),
    0x0D: (_op("store"),),
    0x0E: (_op("insert_obj"),),
    0x0F: (_op("loadw", stores=True),),
    0x10: (_op("loadb", stores=True),),
    0x11: (_op("get_prop", stores=True),),
    0x12: (_op("get_prop_addr", stores=True),),
    0x13: (_op("get_next_prop", stores=True),),
    0x14: (_op("add", stores=True),),
    0x15: (_op("sub", stores=True),),
    0x16: (_op("mul", stores=True),),
    0x17: (_op("div", stores=True),),
    0x18: (_op("mod", stores=True),),
    0x19: (_op("call_2s", first=4, stores=True),),
    0x1A: (_op("call_2n", first=5),),
    0x1B: (_op("set_colour", first=5),),
    0x1C: (_op("throw", first=5),),
}

_ONE_OP: dict[int, tuple[_Entry, ...]] = {
    0x0: (_op("jz", branches=True),),
    0x1: (_op("get_sibling", stores=True, branches=True),),
    0x2: (_op("get_child", stores=True, branches=True),),
    0x3: (_op("get_parent", stores=True),),
    0x4: (_op("get_prop_len", stores=True),),
    0x5: (_op("inc"),),
    0x6: (_op("dec"),),
    0x7: (_op("print_addr"),),
    0x8: (_op("call_1s", first=4, stores=True),),
    0x9: (_op("remove_obj"),),
    0xA: (_op("print_obj"),),
    0xB: (_op("ret"),),
    # jump's destination is an ordinary operand, not branch data, so
    # despite the "?(label)" syntax it carries no branch rider (§14).
    0xC: (_op("jump"),),
    0xD: (_op("print_paddr"),),
    0xE: (_op("load", stores=True),),
    0xF: (
        _op("not", last=4, stores=True),
        _op("call_1n", first=5),
    ),
}

_ZERO_OP: dict[int, tuple[_Entry, ...]] = {
    0x0: (_op("rtrue"),),
    0x1: (_op("rfalse"),),
    0x2: ((FIRST_VERSION, LAST_VERSION, Opcode("print", has_text=True)),),
    0x3: ((FIRST_VERSION, LAST_VERSION, Opcode("print_ret", has_text=True)),),
    0x4: (_op("nop"),),
    # save and restore branch in Versions 1 to 3, store in Version 4,
    # and leave the 0OP table entirely in Version 5 (§14).
    0x5: (
        _op("save", last=3, branches=True),
        _op("save", first=4, last=4, stores=True),
    ),
    0x6: (
        _op("restore", last=3, branches=True),
        _op("restore", first=4, last=4, stores=True),
    ),
    0x7: (_op("restart"),),
    0x8: (_op("ret_popped"),),
    0x9: (
        _op("pop", last=4),
        _op("catch", first=5, stores=True),
    ),
    0xA: (_op("quit"),),
    0xB: (_op("new_line"),),
    0xC: (_op("show_status", first=3, last=3),),
    0xD: (_op("verify", first=3, branches=True),),
    # 0OP:14 is deliberately absent: byte 0xBE marks an extended-form
    # instruction from Version 5 (§4.3), and is not an opcode earlier.
    0xF: (_op("piracy", first=5, branches=True),),
}

_VAR: dict[int, tuple[_Entry, ...]] = {
    0x00: (
        _op("call", last=3, stores=True),
        _op("call_vs", first=4, stores=True),
    ),
    0x01: (_op("storew"),),
    0x02: (_op("storeb"),),
    0x03: (_op("put_prop"),),
    0x04: (
        _op("sread", last=4),
        _op("aread", first=5, stores=True),
    ),
    0x05: (_op("print_char"),),
    0x06: (_op("print_num"),),
    0x07: (_op("random", stores=True),),
    0x08: (_op("push"),),
    # pull stores only in Version 6; Versions 7 and 8 revert to the
    # Version 5 behaviour, making the spans non-contiguous (§14).
    0x09: (
        _op("pull", last=5),
        _op("pull", first=6, last=6, stores=True),
        _op("pull", first=7),
    ),
    0x0A: (_op("split_window", first=3),),
    0x0B: (_op("set_window", first=3),),
    0x0C: (_op("call_vs2", first=4, stores=True),),
    0x0D: (_op("erase_window", first=4),),
    0x0E: (_op("erase_line", first=4),),
    0x0F: (_op("set_cursor", first=4),),
    0x10: (_op("get_cursor", first=4),),
    0x11: (_op("set_text_style", first=4),),
    0x12: (_op("buffer_mode", first=4),),
    0x13: (_op("output_stream", first=3),),
    0x14: (_op("input_stream", first=3),),
    # Officially Version 5, but The Lurking Horror uses it in 3 and
    # the §14 table records that reality.
    0x15: (_op("sound_effect", first=3),),
    0x16: (_op("read_char", first=4, stores=True),),
    0x17: (_op("scan_table", first=4, stores=True, branches=True),),
    0x18: (_op("not", first=5, stores=True),),
    0x19: (_op("call_vn", first=5),),
    0x1A: (_op("call_vn2", first=5),),
    0x1B: (_op("tokenise", first=5),),
    0x1C: (_op("encode_text", first=5),),
    0x1D: (_op("copy_table", first=5),),
    0x1E: (_op("print_table", first=5),),
    0x1F: (_op("check_arg_count", first=5, branches=True),),
}

_EXT: dict[int, tuple[_Entry, ...]] = {
    0x00: (_op("save", first=5, stores=True),),
    0x01: (_op("restore", first=5, stores=True),),
    0x02: (_op("log_shift", first=5, stores=True),),
    0x03: (_op("art_shift", first=5, stores=True),),
    0x04: (_op("set_font", first=5, stores=True),),
    0x05: (_op("draw_picture", first=6),),
    0x06: (_op("picture_data", first=6, branches=True),),
    0x07: (_op("erase_picture", first=6),),
    0x08: (_op("set_margins", first=6),),
    0x09: (_op("save_undo", first=5, stores=True),),
    0x0A: (_op("restore_undo", first=5, stores=True),),
    0x0B: (_op("print_unicode", first=5),),
    0x0C: (_op("check_unicode", first=5, stores=True),),
    0x0D: (_op("set_true_colour", first=5),),
    0x10: (_op("move_window", first=6),),
    0x11: (_op("window_size", first=6),),
    0x12: (_op("window_style", first=6),),
    0x13: (_op("get_wind_prop", first=6, stores=True),),
    0x14: (_op("scroll_window", first=6),),
    0x15: (_op("pop_stack", first=6),),
    0x16: (_op("read_mouse", first=6),),
    0x17: (_op("mouse_window", first=6),),
    0x18: (_op("push_stack", first=6, branches=True),),
    0x19: (_op("put_wind_prop", first=6),),
    0x1A: (_op("print_form", first=6),),
    0x1B: (_op("make_menu", first=6, branches=True),),
    0x1C: (_op("picture_table", first=6),),
    0x1D: (_op("buffer_screen", first=6, stores=True),),
}

_TABLES: dict[OpcodeKind, dict[int, tuple[_Entry, ...]]] = {
    OpcodeKind.ZERO_OP: _ZERO_OP,
    OpcodeKind.ONE_OP: _ONE_OP,
    OpcodeKind.TWO_OP: _TWO_OP,
    OpcodeKind.VAR: _VAR,
    OpcodeKind.EXT: _EXT,
}


def lookup(kind: OpcodeKind, number: int, version: int) -> Opcode:
    """Find the opcode a number means in a given version (§14).

    Args:
        kind: Which of the five tables to consult.
        number: The opcode number within that table.
        version: The story file's version.

    Returns:
        The opcode's decoding knowledge.

    Raises:
        ZMachineInstructionError: If no opcode is defined for that
            number in that version.
    """

    for first, last, opcode in _TABLES[kind].get(number, ()):
        if first <= version <= last:
            return opcode

    msg = f"{kind.value}:{number} is not an opcode in version {version} (§14)"

    raise ZMachineInstructionError(msg)
