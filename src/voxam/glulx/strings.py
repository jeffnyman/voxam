"""String decoding and the output opcodes (Glulx: Strings).

Three string types share one entry point: E0, plain bytes; E2,
32-bit characters; and E1, Huffman-compressed against the
string-decoding table (Glulx: The String-Decoding Table). Only E1
is interesting: its tree can hold nodes that print other strings
or call functions, so decoding is not a loop that runs to
completion but a coroutine that may suspend into the machine and
resume later (Glulx: Calling and Returning Within Strings).

In filter mode every character is a function call, and a
compressed string may call a function at any node. Either way the
decoder stops, records where it was as a call stub -- the resume
types the stack module names -- and lets the machine run; resume()
is the other half, called when one of those stubs comes back off
the stack. Glk mode never suspends, since output there is a direct
call: that is the path real games take, and it stays a plain loop
-- one this machine reports as a frontier until the Glk era
arrives. The null mode decodes and discards.
"""

from typing import TYPE_CHECKING

from voxam.errors import GlulxFrontierError, GlulxStringError
from voxam.glulx import funcs
from voxam.glulx.iosys import IOMode
from voxam.glulx.memory import WORD_MASK
from voxam.glulx.stack import CallStub, DestType

if TYPE_CHECKING:
    from voxam.glulx.machine import Machine

# The three string types; E3 through FF are reserved for future
# kinds of string (Glulx: Strings).
CSTRING = 0xE0
COMPRESSED = 0xE1
UNICODE_STRING = 0xE2
STRING_FIRST = 0xE0
STRING_LAST = 0xFF

FUNCTION_FIRST = 0xC0
FUNCTION_LAST = 0xDF

# The node types a decoding table may hold (Glulx: The
# String-Decoding Table).
NODE_BRANCH = 0x00
NODE_TERMINATOR = 0x01
NODE_CHAR = 0x02
NODE_CSTR = 0x03
NODE_UNICHAR = 0x04
NODE_UNISTR = 0x05
NODE_INDIRECT = 0x08
NODE_DOUBLE_INDIRECT = 0x09
NODE_INDIRECT_ARGS = 0x0A
NODE_DOUBLE_INDIRECT_ARGS = 0x0B

INDIRECT_NODES = frozenset(
    {
        NODE_INDIRECT,
        NODE_DOUBLE_INDIRECT,
        NODE_INDIRECT_ARGS,
        NODE_DOUBLE_INDIRECT_ARGS,
    }
)

# The root node's address sits at the table's ninth byte, after
# the length and node-count words (Glulx: The String-Decoding
# Table).
ROOT_AT = 8

LAST_BIT = 7


def put_char(machine: "Machine", character: int) -> None:
    """The engine of streamchar and streamunichar.

    In filter mode this enters the filter function and returns;
    the machine carries on from there, and the ordinary
    function-return path brings it back -- the stub discards the
    filter's result, exactly as the reference glulxe arranges it.
    """

    mode = machine.iosys.mode

    if mode == IOMode.NULL:
        return

    if mode == IOMode.FILTER:
        machine.stack.push_stub(DestType.DISCARD, 0, machine.pc)
        machine.enter_function(machine.iosys.rock, [character])

        return

    _put_glk(machine, character)


def stream_num(
    machine: "Machine",
    value: int,
    *,
    in_middle: bool = False,
    charnum: int = 0,
) -> None:
    """The engine of streamnum: print a signed decimal.

    charnum counts the characters already printed, nonzero only
    when resuming a filter-mode print. The resume stub's PC field
    carries the number itself, so resuming needs it stored nowhere
    else (Glulx: Calling and Returning Within Strings).
    """

    text = str(_signed(value))
    mode = machine.iosys.mode

    if mode == IOMode.GLK:
        for character in text[charnum:]:
            _put_glk(machine, ord(character))
    elif mode == IOMode.FILTER:
        if not in_middle:
            machine.stack.push_stub(DestType.RESUME_FUNCTION, 0, machine.pc)

            in_middle = True

        if charnum < len(text):
            machine.stack.push_stub(
                DestType.RESUME_NUMBER, charnum + 1, value & WORD_MASK
            )
            machine.enter_function(machine.iosys.rock, [ord(text[charnum])])

            return

    if in_middle:
        stub = machine.stack.pop_stub()
        machine.pc = stub.pc

        if stub.desttype != DestType.RESUME_FUNCTION:
            msg = (
                "a string-on-string call stub arrived while printing a "
                "number (Glulx: Calling and Returning Within Strings)"
            )

            raise GlulxStringError(msg)


def stream_string(
    machine: "Machine",
    addr: int,
    *,
    in_middle: int = 0,
    bitnum: int = 0,
) -> None:
    """The engine of streamstr, and the landing for resumed strings.

    Raises:
        GlulxStringError: For a null address, a type byte that is
            no string, or a table the walk cannot follow.
    """

    if addr == 0:
        msg = "streamstr with a null address (Glulx: Output)"

        raise GlulxStringError(msg)

    _Printer(machine, addr, in_middle, bitnum).run()


def resume(machine: "Machine", stub: CallStub) -> None:
    """Continue a suspended print from its popped stub.

    The machine's stub-popping filtered the types already, so the
    four resume kinds are exhaustive here (Glulx: Calling and
    Returning Within Strings).
    """

    machine.pc = stub.pc

    if stub.desttype == DestType.RESUME_COMPRESSED:
        stream_string(machine, stub.pc, in_middle=COMPRESSED, bitnum=stub.destaddr)
    elif stub.desttype == DestType.RESUME_CSTRING:
        stream_string(machine, stub.pc, in_middle=CSTRING)
    elif stub.desttype == DestType.RESUME_UNICODE:
        stream_string(machine, stub.pc, in_middle=UNICODE_STRING)
    else:
        stream_num(machine, stub.pc, in_middle=True, charnum=stub.destaddr)


def _signed(value: int) -> int:
    """The signed reading of an unsigned 32-bit value."""

    return value - (1 << 32) if value & 0x8000_0000 else value


def _put_glk(_machine: "Machine", character: int) -> None:
    """The Glk emission seat -- a frontier until the Glk era.

    Raises:
        GlulxFrontierError: Always, for now: Glk output awaits the
            Glk era, and the character it would have printed is
            named so the frontier is diagnosable.
    """

    msg = f"Glk output of character {character} awaits the Glk era"

    raise GlulxFrontierError(msg)


class _Printer:
    """One streamstr in progress.

    The mutable state the reference glulxe keeps in the locals of
    a three-hundred-line function: where the walk stands, which
    bit, whether the terminator stub is down yet, and whether
    control was handed back to the machine.
    """

    def __init__(
        self, machine: "Machine", addr: int, in_middle: int, bitnum: int
    ) -> None:
        self.machine = machine
        self.addr = addr
        self.in_middle = in_middle
        self.bitnum = bitnum
        # Entering mid-string means the terminator stub is already
        # on the stack.
        self.substring = in_middle != 0
        self.suspended = False

    def run(self) -> None:
        """Print until the string ends or the machine must run.

        Raises:
            GlulxStringError: For a type byte that is no string,
                or a reserved future kind of string.
        """

        memory = self.machine.memory

        while True:
            if self.in_middle == 0:
                kind = memory.read_byte(self.addr)
                # E2 strings pad to a four-byte boundary; the
                # others start right after their type byte.
                self.addr += 4 if kind == UNICODE_STRING else 1
                self.bitnum = 0
            else:
                kind = self.in_middle
                self.in_middle = 0

            if kind == COMPRESSED:
                restart = self._compressed()
            elif kind == CSTRING:
                restart = self._cstring()
            elif kind == UNICODE_STRING:
                restart = self._unicode_string()
            elif STRING_FIRST <= kind <= STRING_LAST:
                msg = (
                    f"the type byte ${kind:x} names a kind of string "
                    f"reserved for the future (Glulx: Strings)"
                )

                raise GlulxStringError(msg)
            else:
                msg = f"the type byte ${kind:x} is not a string at all (Glulx: Strings)"

                raise GlulxStringError(msg)

            if self.suspended:
                return

            if restart:
                continue

            if not self.substring:
                return

            if not self._pop_string_stub():
                return

            self.in_middle = COMPRESSED

    def _cstring(self) -> bool:
        """An E0 string: bytes to a zero terminator."""

        memory = self.machine.memory
        mode = self.machine.iosys.mode

        if mode == IOMode.FILTER:
            self._begin_substring()

            character = memory.read_byte(self.addr)
            self.addr += 1

            if character != 0:
                self._call_filter(character, DestType.RESUME_CSTRING, 0, self.addr)

            return False

        while True:
            character = memory.read_byte(self.addr)
            self.addr += 1

            if character == 0:
                return False

            if mode == IOMode.GLK:
                _put_glk(self.machine, character)

    def _unicode_string(self) -> bool:
        """An E2 string: 32-bit characters to a zero terminator."""

        memory = self.machine.memory
        mode = self.machine.iosys.mode

        if mode == IOMode.FILTER:
            self._begin_substring()

            character = memory.read_word(self.addr)
            self.addr += 4

            if character != 0:
                self._call_filter(character, DestType.RESUME_UNICODE, 0, self.addr)

            return False

        while True:
            character = memory.read_word(self.addr)
            self.addr += 4

            if character == 0:
                return False

            if mode == IOMode.GLK:
                # pragma: no cover -- the fallthrough lives when
                # the Glk era makes _put_glk return.
                _put_glk(self.machine, character)  # pragma: no cover

    def _compressed(self) -> bool:  # noqa: PLR0912 -- the tree walk stays whole
        """Walk the Huffman tree until the string ends or we suspend.

        True means a sub-object was set up and the outer loop
        should start again on it. The reference glulxe keeps a
        multi-bit cache of the tree; this is the plain walk it
        falls back on -- one memory read per bit. The cache is a
        worthwhile optimization later, but it must cope with a
        table in RAM the game can rewrite, so correctness first.

        Raises:
            GlulxStringError: With no table set, or for a node
                type the spec does not define.
        """

        machine = self.machine
        memory = machine.memory
        table = machine.string_table

        if not table:
            msg = (
                "a compressed string cannot print with no decoding "
                "table set (Glulx: The String-Decoding Table)"
            )

            raise GlulxStringError(msg)

        root = memory.read_word(table + ROOT_AT)
        byte = memory.read_byte(self.addr)

        if self.bitnum:
            byte >>= self.bitnum

        node = root

        while True:
            nodetype = memory.read_byte(node)
            node += 1

            if nodetype == NODE_BRANCH:
                # Bits read low bit first (Glulx: Strings).
                node = (
                    memory.read_word(node + 4) if byte & 1 else memory.read_word(node)
                )

                if self.bitnum == LAST_BIT:
                    self.bitnum = 0
                    self.addr += 1
                    byte = memory.read_byte(self.addr)
                else:
                    self.bitnum += 1
                    byte >>= 1
            elif nodetype == NODE_TERMINATOR:
                return False
            elif nodetype == NODE_CHAR:
                if not self._emit(memory.read_byte(node)):
                    return False

                node = root
            elif nodetype == NODE_UNICHAR:
                if not self._emit(memory.read_word(node)):
                    return False

                node = root
            elif nodetype == NODE_CSTR:
                if self._emit_substring(node, CSTRING):
                    return True

                node = root
            elif nodetype == NODE_UNISTR:
                if self._emit_substring(node, UNICODE_STRING):
                    return True

                node = root
            elif nodetype in INDIRECT_NODES:
                # Either restarts on a referenced string or
                # suspends into a referenced function; both end
                # this walk.
                return self._indirect(nodetype, node)
            else:
                msg = (
                    f"node type ${nodetype:x} is not one the decoding "
                    f"table may hold (Glulx: The String-Decoding Table)"
                )

                raise GlulxStringError(msg)

    def _emit(self, character: int) -> bool:
        """Print one character; False means we suspended into a filter."""

        mode = self.machine.iosys.mode

        if mode == IOMode.GLK:
            _put_glk(self.machine, character)

            # Reached only when the Glk era makes _put_glk return.
            return True  # pragma: no cover

        if mode == IOMode.FILTER:
            self._begin_substring()
            self._call_filter(
                character, DestType.RESUME_COMPRESSED, self.bitnum, self.addr
            )

            return False

        # The null mode: decoded and discarded.
        return True

    def _emit_substring(self, node: int, kind: int) -> bool:
        """A node holding a whole string; True restarts on it."""

        machine = self.machine
        mode = machine.iosys.mode
        memory = machine.memory

        if mode == IOMode.FILTER:
            # Hand the sub-string to the top-level loop, with a
            # stub remembering where the compressed stream picks
            # back up.
            self._begin_substring()

            machine.pc = self.addr

            machine.stack.push_stub(DestType.RESUME_COMPRESSED, self.bitnum, self.addr)

            self.in_middle = kind
            self.addr = node

            return True

        if mode == IOMode.GLK:
            if kind == CSTRING:
                while (character := memory.read_byte(node)) != 0:
                    _put_glk(machine, character)

                    # Walked only once the Glk era arrives.
                    node += 1  # pragma: no cover
            else:
                while (character := memory.read_word(node)) != 0:
                    _put_glk(machine, character)

                    # Walked only once the Glk era arrives.
                    node += 4  # pragma: no cover

        return False

    def _indirect(self, nodetype: int, node: int) -> bool:
        """Follow an indirect reference to a string or a function.

        True restarts the outer loop on a referenced string; a
        referenced function suspends instead.

        Raises:
            GlulxStringError: For a target that is neither.
        """

        machine = self.machine
        memory = machine.memory
        target = memory.read_word(node)

        if nodetype in (NODE_DOUBLE_INDIRECT, NODE_DOUBLE_INDIRECT_ARGS):
            target = memory.read_word(target)

        target_type = memory.read_byte(target)

        self._begin_substring()

        if STRING_FIRST <= target_type <= STRING_LAST:
            machine.pc = self.addr

            machine.stack.push_stub(DestType.RESUME_COMPRESSED, self.bitnum, self.addr)

            self.in_middle = 0
            self.addr = target

            return True

        if FUNCTION_FIRST <= target_type <= FUNCTION_LAST:
            if nodetype in (NODE_INDIRECT_ARGS, NODE_DOUBLE_INDIRECT_ARGS):
                count = memory.read_word(node + 4)
                args = funcs.pop_arguments(machine.stack, count, memory, node + 8)
            else:
                args = []

            machine.stack.push_stub(DestType.RESUME_COMPRESSED, self.bitnum, self.addr)
            machine.enter_function(target, args)

            self.suspended = True

            return False

        msg = (
            f"an indirect node reaches ${target:x}, which holds neither "
            f"a string nor a function (Glulx: The String-Decoding Table)"
        )

        raise GlulxStringError(msg)

    def _begin_substring(self) -> None:
        """Lay the terminator stub that marks where this print began."""

        if not self.substring:
            self.machine.stack.push_stub(DestType.RESUME_FUNCTION, 0, self.machine.pc)

            self.substring = True

    def _call_filter(
        self, character: int, desttype: int, destaddr: int, pc: int
    ) -> None:
        """Suspend into the filter function with one character."""

        machine = self.machine

        machine.stack.push_stub(desttype, destaddr, pc)
        machine.enter_function(machine.iosys.rock, [character])

        self.suspended = True

    def _pop_string_stub(self) -> bool:
        """Pop a resume or terminator stub; False ends the print.

        Raises:
            GlulxStringError: For a stub that belongs to neither.
        """

        stub = self.machine.stack.pop_stub()
        self.machine.pc = stub.pc

        if stub.desttype == DestType.RESUME_FUNCTION:
            return False

        if stub.desttype == DestType.RESUME_COMPRESSED:
            self.addr = stub.pc
            self.bitnum = stub.destaddr

            return True

        msg = (
            "a function-terminator call stub arrived at the end of a "
            "string (Glulx: Calling and Returning Within Strings)"
        )

        raise GlulxStringError(msg)
