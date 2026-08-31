"""Function entry: headers read, frames built, arguments seated.

A function opens with a type byte -- C0 for stack arguments, C1
for local arguments -- and a locals-format list, and its code
begins just past that (Glulx: Functions). Entering one builds a
call frame and seats the arguments as the type directs: a C0
function finds them pushed on its value stack, last argument
first with the count on top, while a C1 function finds them
written into its locals in order, extras dropped silently and
unfilled locals left zero (Glulx: Calling and Returning).

The call stub is deliberately *not* pushed here. Whether one is
needed, and what its DestType says, depends on the opcode -- call
pushes one, tailcall pointedly does not -- so the stub stays the
caller's business.
"""

from typing import NamedTuple

from voxam.errors import GlulxFunctionError
from voxam.glulx.memory import WORD_MASK, WORD_WIDTH, Memory
from voxam.glulx.stack import LOCAL_TYPES, LocalsFormat, Stack

# The two function types (Glulx: Functions): C0 takes its
# arguments on the stack, C1 in its locals.
STACK_ARGUMENTS = 0xC0
LOCAL_ARGUMENTS = 0xC1

# C2 through DF are reserved for function types yet to be defined
# (Glulx: Functions). The spec distinguishes them from plain
# non-functions, and so does the reference glulxe, because the
# difference tells an author whether an address is wrong or merely
# too new for the interpreter.
RESERVED_FIRST = 0xC2
RESERVED_LAST = 0xDF

# The sign bit of an unsigned 32-bit argument count: a "negative"
# count is a count gone wrong, not a big one.
COUNT_SIGN_BIT = 0x8000_0000


class FunctionHeader(NamedTuple):
    """A decoded function header (Glulx: Functions).

    Attributes:
        functype: STACK_ARGUMENTS or LOCAL_ARGUMENTS.
        locals_format: The declared locals, in order.
        code_addr: The first instruction, just past the header.
    """

    functype: int
    locals_format: tuple[LocalsFormat, ...]
    code_addr: int


def read_function_header(
    memory: Memory, addr: int, headers: "dict[int, FunctionHeader] | None" = None
) -> FunctionHeader:
    """Read the type byte and locals-format list at an address.

    A header below RAMSTART cannot change, so a caller that offers
    somewhere to keep one gets the same object back on every later
    call to the same function (Glulx: The Memory Map). A header
    reaching into RAM is read afresh every time, since the story
    may have written over it.

    Raises:
        GlulxFunctionError: For a type byte that is no function --
            or one reserved for a future kind of function, named
            as such -- or a local type the format bytes cannot
            mean (Glulx: Functions).
        GlulxMemoryError: For a header running off the map.
    """

    if headers is not None:
        held = headers.get(addr)

        if held is not None:
            return held

    funcaddr = addr
    functype = memory.read_byte(addr)

    if functype not in (STACK_ARGUMENTS, LOCAL_ARGUMENTS):
        if RESERVED_FIRST <= functype <= RESERVED_LAST:
            msg = (
                f"the address ${addr:x} holds type ${functype:x}, a "
                f"function of a kind reserved for the future "
                f"(Glulx: Functions)"
            )
        else:
            msg = (
                f"the address ${addr:x} holds type ${functype:x}, "
                f"which is not a function at all (Glulx: Functions)"
            )

        raise GlulxFunctionError(msg)

    addr += 1
    entries: list[LocalsFormat] = []

    while True:
        size = memory.read_byte(addr)
        count = memory.read_byte(addr + 1)
        addr += 2

        if size == 0:
            break

        if size not in LOCAL_TYPES:
            msg = (
                f"the function header at ${addr - 2:x} declares a local "
                f"type of {size}, not 1, 2, or 4 (Glulx: Functions)"
            )

            raise GlulxFunctionError(msg)

        entries.append(LocalsFormat(size, count))

    header = FunctionHeader(functype, tuple(entries), addr)

    # The header runs from funcaddr up to the code it names, so
    # that is the span which has to sit in memory the story cannot
    # write before it is worth keeping.
    if headers is not None and addr <= memory.ramstart:
        headers[funcaddr] = header

    return header


def push_call_frame(
    memory: Memory,
    stack: Stack,
    funcaddr: int,
    args: list[int],
    headers: "dict[int, FunctionHeader] | None" = None,
) -> int:
    """Enter the function at an address; the new PC comes back.

    The arguments arrive in call order -- args[0] first -- and are
    seated as the function's type directs (Glulx: Calling and
    Returning). Headers, when offered, are kept; see
    read_function_header.

    Raises:
        GlulxFunctionError: For an address that is no function.
        GlulxStackError: For a frame the stack cannot hold.
    """

    header = read_function_header(memory, funcaddr, headers)

    stack.push_frame(header.locals_format)

    if header.functype == STACK_ARGUMENTS:
        _push_stack_arguments(stack, args)
    else:
        _write_local_arguments(stack, header.locals_format, args)

    return header.code_addr


def pop_arguments(stack: Stack, count: int, memory: Memory, addr: int = 0) -> list[int]:
    """Collect a call's arguments, from the stack or from memory.

    With addr zero the arguments come off the stack, first
    argument topmost -- how callf's kin leave them. Otherwise they
    read as a word array at addr, which is what the accelerated
    functions will need, the address arithmetic wrapping at 32
    bits like all address arithmetic.

    Raises:
        GlulxStackError: For a stack with fewer values than asked.
        GlulxFunctionError: For a count with its sign bit set -- a
            count gone wrong, not a big one.
    """

    if count & COUNT_SIGN_BIT:
        msg = f"an argument count of {count} has its sign bit set"

        raise GlulxFunctionError(msg)

    if addr == 0:
        return [stack.pop() for _ in range(count)]

    return [
        memory.read_word((addr + WORD_WIDTH * index) & WORD_MASK)
        for index in range(count)
    ]


def _push_stack_arguments(stack: Stack, args: list[int]) -> None:
    """Seat a C0 function's arguments: backwards, then the count.

    The last argument pushes first, so the first ends up topmost
    with the count above it (Glulx: Functions).
    """

    for value in reversed(args):
        stack.push(value)

    stack.push(len(args))


def _write_local_arguments(
    stack: Stack, locals_format: tuple[LocalsFormat, ...], args: list[int]
) -> None:
    """Seat a C1 function's arguments into its locals, in order.

    Extra arguments drop silently and unfilled locals stay zero,
    both per (Glulx: Functions). A value written into an 8- or
    16-bit local truncates -- a deprecated arrangement, but still
    a legal one.
    """

    index = 0
    offset = 0

    for entry in locals_format:
        if index >= len(args):
            break

        # Each run starts at its own natural alignment, exactly as
        # the frame laid it down.
        offset += -offset % entry.size

        for _ in range(entry.count):
            if index >= len(args):
                return

            stack.set_local(offset, args[index], entry.size)
            offset += entry.size
            index += 1
