"""The Glulx stack: call frames, locals, and call stubs.

Byte-addressed and growing upward from zero (Glulx: The Stack),
the stack is where every function call builds its frame -- a
header, a locals-format list, the zeroed locals themselves -- and
where every call leaves a four-word stub saying how to come home
(Glulx: The Call Frame, Glulx: Call Stubs). Unlike main memory,
stack access is strictly aligned: shorts at even offsets, words at
multiples of four. A program that breaks that has undefined
behavior, and undefined behavior gets caught here, not tolerated.

Two settled rulings ride along from the prior art. The byte order
is big-endian even though the spec leaves it to the interpreter
and the reference glulxe (vendored) uses native order: the save
format stores the stack big-endian (Glulx: Contents of the Stack),
so storing it that way in the first place makes saving a straight
copy and deletes the byte-swapping machinery -- and the class of
bug the spec itself warns "will fail, if nothing else" for locals
written out of format. And local references are bounds-checked:
the spec is explicit that a local reference "must not point
outside the range of the current function's locals segment", a
check glulxe skips with a note that a strict interpreter probably
should make. Voxam is that strict interpreter.
"""

import struct
from collections.abc import Callable
from dataclasses import dataclass
from enum import IntEnum
from typing import NamedTuple

from voxam.errors import GlulxStackError
from voxam.glulx.memory import (
    BYTE_MASK,
    BYTE_WIDTH,
    SHORT_MASK,
    SHORT_WIDTH,
    WORD_MASK,
    WORD_WIDTH,
)
from voxam.glulx.story import BOUNDARY

# A call stub is four 32-bit words: DestType, DestAddr, PC, and
# FramePtr (Glulx: Call Stubs).
STUB_SIZE = 16

# A frame opens with FrameLen and LocalsPos, four bytes each
# (Glulx: The Call Frame).
FRAME_HEADER_SIZE = 8

# A locals-format entry is a LocalType byte and a LocalCount byte;
# the legal types are 1, 2, and 4 (Glulx: The Call Frame).
FORMAT_ENTRY_SIZE = 2
LOCAL_TYPES = (BYTE_WIDTH, SHORT_WIDTH, WORD_WIDTH)
LOCAL_COUNT_LIMIT = 255

# Big-endian access, prepared once. int.from_bytes on a slice,
# and to_bytes into one, each build a throwaway bytes object per
# access; these do not. On the reads this stack does tens of
# millions of times in a session that is measured at roughly a
# third of the work for the same answer.
_WORD = struct.Struct(">I")
_SHORT = struct.Struct(">H")
# Typed here rather than at each call: unpack_from is Any-returning
# in the stubs, and a cast at every read would cost what this saves.
_read_word: Callable[[bytearray, int], tuple[int]] = _WORD.unpack_from
_write_word: Callable[[bytearray, int, int], None] = _WORD.pack_into
_read_short: Callable[[bytearray, int], tuple[int]] = _SHORT.unpack_from
_write_short: Callable[[bytearray, int, int], None] = _SHORT.pack_into

SHORT_ALIGN_MASK = 0b1
WORD_ALIGN_MASK = 0b11


class DestType(IntEnum):
    """Where a call stub's result lands (Glulx: Call Stubs).

    The spec prints the string-resume values as "10" through "14"
    with no radix marker, in a document that writes hex bare
    everywhere else. Both reference implementations read them as
    hexadecimal -- glulxe's pop_callstub switches on 0x10 through
    0x14, and quixe does the same -- so they are 16 through 20,
    not 10 through 14.
    """

    DISCARD = 0
    MEMORY = 1
    LOCAL = 2
    STACK = 3

    # Resuming an E1 compressed string; DestAddr holds the bit
    # number within the byte.
    RESUME_COMPRESSED = 0x10
    # Resuming function code after a string finishes.
    RESUME_FUNCTION = 0x11
    # Resuming a signed decimal print; PC holds the number itself.
    RESUME_NUMBER = 0x12
    # Resuming an E0 C-string.
    RESUME_CSTRING = 0x13
    # Resuming an E2 Unicode string.
    RESUME_UNICODE = 0x14


class CallStub(NamedTuple):
    """The four words a call, catch, or string print leaves behind.

    Attributes:
        desttype: Where the result goes, a DestType value.
        destaddr: The address or offset that destination reads.
        pc: Where execution resumes.
        frameptr: The frame to come home to.
    """

    desttype: int
    destaddr: int
    pc: int
    frameptr: int


@dataclass(frozen=True)
class LocalsFormat:
    """One LocalType/LocalCount pair from a locals-format list.

    A dataclass rather than a named tuple only because the spec's
    own field name, count, is a name every tuple already claims.

    Attributes:
        size: The type: a width of 1, 2, or 4 bytes.
        count: How many locals of that width, 0 through 255.
    """

    size: int
    count: int


class Stack:
    """The Glulx value stack, its registers public for the machine.

    Attributes:
        sp: The stack pointer, counting bytes from zero.
        frameptr: Where the current call frame begins.
        localsbase: Where its locals segment begins -- what the
            locals addressing modes and DestType 2 offset from.
        valstackbase: Where its value stack begins -- the floor
            pops may not pass.
    """

    def __init__(self, size: int) -> None:
        """Raise an empty stack of the header's declared size.

        Args:
            size: The stack size in bytes, a multiple of 256 at
                least 256 tall (Glulx: The Stack).

        Raises:
            GlulxStackError: For a size below or off the 256-byte
                convenience the spec demands.
        """

        if size < BOUNDARY or size % BOUNDARY:
            msg = (
                f"a stack of {size} bytes is not a multiple of {BOUNDARY} "
                f"at least {BOUNDARY} tall (Glulx: The Stack)"
            )

            raise GlulxStackError(msg)

        self._size = size
        self._data = bytearray(size)
        self.sp = 0
        self.frameptr = 0
        self.localsbase = 0
        self.valstackbase = 0

    @property
    def size(self) -> int:
        """The stack's full height in bytes."""

        return self._size

    def reset(self) -> None:
        """Clear the stack whole -- restart's share of the work."""

        self._data = bytearray(self._size)
        self.sp = 0
        self.frameptr = 0
        self.localsbase = 0
        self.valstackbase = 0

    def snapshot(self) -> bytes:
        """The live bytes, ready for a save file's stack chunk.

        A straight copy: the save format wants big-endian values
        (Glulx: Contents of the Stack) and that is already how the
        stack stores them -- the whole point of the byte-order
        ruling in the module docstring.
        """

        return bytes(self._data[: self.sp])

    def restore(self, data: bytes) -> None:
        """Replace the stack from a snapshot.

        The frame registers stay zeroed: a restore is completed by
        popping the call stub the saver pushed, and until then the
        bases mean nothing.

        Raises:
            GlulxStackError: For a snapshot taller than this stack
                or not a whole number of words long.
        """

        if len(data) > self._size:
            msg = (
                f"a saved stack of {len(data)} bytes cannot fit this "
                f"interpreter's {self._size}-byte stack "
                f"(Glulx: Contents of the Stack)"
            )

            raise GlulxStackError(msg)

        if len(data) % WORD_WIDTH:
            msg = (
                f"a saved stack of {len(data)} bytes is not a whole "
                f"number of words (Glulx: Contents of the Stack)"
            )

            raise GlulxStackError(msg)

        self._data = bytearray(self._size)
        self._data[: len(data)] = data
        self.sp = len(data)
        self.frameptr = 0
        self.localsbase = 0
        self.valstackbase = 0

    def read_byte(self, position: int) -> int:
        """Read one byte of the stack.

        Raises:
            GlulxStackError: For a position off the stack.
        """

        if position < 0 or position >= self._size:
            raise GlulxStackError(_refused(position, BYTE_WIDTH, self._size))

        return self._data[position]

    def read_short(self, position: int) -> int:
        """Read a big-endian short at an even position.

        Raises:
            GlulxStackError: For a position off the stack or off
                its natural alignment (Glulx: The Call Frame).
        """

        if (
            position < 0
            or position > self._size - SHORT_WIDTH
            or position & SHORT_ALIGN_MASK
        ):
            raise GlulxStackError(_refused(position, SHORT_WIDTH, self._size))

        return _read_short(self._data, position)[0]

    def read_word(self, position: int) -> int:
        """Read a big-endian word at a multiple of four.

        Raises:
            GlulxStackError: For a position off the stack or off
                its natural alignment (Glulx: The Call Frame).
        """

        if (
            position < 0
            or position > self._size - WORD_WIDTH
            or position & WORD_ALIGN_MASK
        ):
            raise GlulxStackError(_refused(position, WORD_WIDTH, self._size))

        return _read_word(self._data, position)[0]

    def read(self, position: int, width: int) -> int:
        """Read at a local's width: 1, 2, or 4 bytes.

        Raises:
            GlulxStackError: For a position off the stack or off
                the width's alignment.
        """

        if width == WORD_WIDTH:
            return self.read_word(position)

        if width == BYTE_WIDTH:
            return self.read_byte(position)

        return self.read_short(position)

    def write_byte(self, position: int, value: int) -> None:
        """Write one byte of the stack, masked to 8 bits.

        Raises:
            GlulxStackError: For a position off the stack.
        """

        if position < 0 or position >= self._size:
            raise GlulxStackError(_refused(position, BYTE_WIDTH, self._size))

        self._data[position] = value & BYTE_MASK

    def write_short(self, position: int, value: int) -> None:
        """Write a big-endian short at an even position, masked.

        Raises:
            GlulxStackError: For a position off the stack or off
                its natural alignment (Glulx: The Call Frame).
        """

        if (
            position < 0
            or position > self._size - SHORT_WIDTH
            or position & SHORT_ALIGN_MASK
        ):
            raise GlulxStackError(_refused(position, SHORT_WIDTH, self._size))

        _write_short(self._data, position, value & SHORT_MASK)

    def write_word(self, position: int, value: int) -> None:
        """Write a big-endian word at a multiple of four, masked.

        Raises:
            GlulxStackError: For a position off the stack or off
                its natural alignment (Glulx: The Call Frame).
        """

        if (
            position < 0
            or position > self._size - WORD_WIDTH
            or position & WORD_ALIGN_MASK
        ):
            raise GlulxStackError(_refused(position, WORD_WIDTH, self._size))

        _write_word(self._data, position, value & WORD_MASK)

    def write(self, position: int, width: int, value: int) -> None:
        """Write at a local's width: 1, 2, or 4 bytes.

        Raises:
            GlulxStackError: For a position off the stack or off
                the width's alignment.
        """

        if width == WORD_WIDTH:
            self.write_word(position, value)
        elif width == BYTE_WIDTH:
            self.write_byte(position, value)
        else:
            self.write_short(position, value)

    def push(self, value: int) -> None:
        """Push one word, masked to 32 bits.

        Raises:
            GlulxStackError: On overflow (Glulx: The Stack).
        """

        if self.sp + WORD_WIDTH > self._size:
            msg = f"the {self._size}-byte stack overflowed (Glulx: The Stack)"

            raise GlulxStackError(msg)

        _write_word(self._data, self.sp, value & WORD_MASK)
        self.sp += WORD_WIDTH

    def pop(self) -> int:
        """Pop one word.

        Raises:
            GlulxStackError: On popping past the frame's value
                stack into the call frame itself (Glulx: The Call
                Frame).
        """

        if self.sp < self.valstackbase + WORD_WIDTH:
            msg = (
                "the stack underflowed: popping past the value stack "
                "would eat the call frame (Glulx: The Call Frame)"
            )

            raise GlulxStackError(msg)

        self.sp -= WORD_WIDTH

        return _read_word(self._data, self.sp)[0]

    def peek(self, depth: int = 0) -> int:
        """Read a value without popping; depth 0 is the topmost.

        Raises:
            GlulxStackError: For a depth reaching past the frame's
                value stack -- stkpeek's own error case.
        """

        position = self.sp - WORD_WIDTH * (depth + 1)

        if position < self.valstackbase:
            msg = (
                f"a peek {depth} deep reaches past the value stack "
                f"(Glulx: The Call Frame)"
            )

            raise GlulxStackError(msg)

        return _read_word(self._data, position)[0]

    @property
    def count(self) -> int:
        """Words above the current frame -- stkcount's answer."""

        return (self.sp - self.valstackbase) // WORD_WIDTH

    def push_stub(self, desttype: int, destaddr: int, pc: int) -> None:
        """Push DestType, DestAddr, PC, and FramePtr (Glulx: Call Stubs).

        Raises:
            GlulxStackError: On overflow.
        """

        if self.sp + STUB_SIZE > self._size:
            msg = (
                f"the {self._size}-byte stack overflowed pushing a call "
                f"stub (Glulx: Call Stubs)"
            )

            raise GlulxStackError(msg)

        self.write_word(self.sp, desttype)
        self.write_word(self.sp + 4, destaddr)
        self.write_word(self.sp + 8, pc)
        self.write_word(self.sp + 12, self.frameptr)
        self.sp += STUB_SIZE

    def pop_stub(self) -> CallStub:
        """Pop a call stub, restoring frameptr and the derived bases.

        The program counter and the storing of any result stay the
        caller's business: what those mean depends on the DestType
        (Glulx: Call Stubs).

        Raises:
            GlulxStackError: On underflow.
        """

        if self.sp < STUB_SIZE:
            msg = "the stack underflowed popping a call stub (Glulx: Call Stubs)"

            raise GlulxStackError(msg)

        self.sp -= STUB_SIZE
        stub = CallStub(
            desttype=self.read_word(self.sp),
            destaddr=self.read_word(self.sp + 4),
            pc=self.read_word(self.sp + 8),
            frameptr=self.read_word(self.sp + 12),
        )
        self.frameptr = stub.frameptr
        self.valstackbase = self.frameptr + self.read_word(self.frameptr)
        self.localsbase = self.frameptr + self.read_word(self.frameptr + 4)

        return stub

    def push_frame(self, locals_format: tuple[LocalsFormat, ...]) -> None:
        """Build a call frame at sp and make it current.

        The locals arrive zeroed; placing arguments is the caller's
        business, since that depends on whether the function is the
        stack-argument or local-argument kind. Each run of locals
        pads up to its own natural alignment before it starts, the
        segment pads to a word, and the written format list ends
        with a zero pair -- twice when needed to stay word-aligned
        (Glulx: The Call Frame).

        Raises:
            GlulxStackError: For a local type other than 1, 2, or
                4, a count outside a byte, or a frame that would
                overflow the stack.
        """

        for entry in locals_format:
            if entry.size not in LOCAL_TYPES:
                msg = (
                    f"a locals-format list may hold types 1, 2, and 4, "
                    f"not {entry.size} (Glulx: The Call Frame)"
                )

                raise GlulxStackError(msg)

            if not 0 <= entry.count <= LOCAL_COUNT_LIMIT:
                msg = (
                    f"a locals-format count of {entry.count} does not fit "
                    f"its byte (Glulx: The Call Frame)"
                )

                raise GlulxStackError(msg)

        locals_length = 0

        for entry in locals_format:
            locals_length = (
                _aligned(locals_length, entry.size) + entry.size * entry.count
            )

        locals_length = _aligned(locals_length, WORD_WIDTH)

        written = [*locals_format, LocalsFormat(0, 0)]

        if len(written) % 2:
            written.append(LocalsFormat(0, 0))

        format_length = FORMAT_ENTRY_SIZE * len(written)
        frameptr = self.sp
        localsbase = frameptr + FRAME_HEADER_SIZE + format_length
        valstackbase = localsbase + locals_length

        if valstackbase >= self._size:
            msg = (
                f"the {self._size}-byte stack overflowed building a call "
                f"frame (Glulx: The Call Frame)"
            )

            raise GlulxStackError(msg)

        self.frameptr = frameptr
        self.localsbase = localsbase
        self.valstackbase = valstackbase

        self.write_word(frameptr, FRAME_HEADER_SIZE + format_length + locals_length)
        self.write_word(frameptr + 4, FRAME_HEADER_SIZE + format_length)

        position = frameptr + FRAME_HEADER_SIZE

        for entry in written:
            self._data[position] = entry.size
            self._data[position + 1] = entry.count
            position += FORMAT_ENTRY_SIZE

        self._data[localsbase:valstackbase] = bytes(locals_length)
        self.sp = valstackbase

    def leave_frame(self) -> None:
        """Discard the current frame and everything pushed above it."""

        self.sp = self.frameptr

    @property
    def frame_len(self) -> int:
        """The current frame's whole length, off its own header."""

        return self.read_word(self.frameptr)

    @property
    def locals_pos(self) -> int:
        """Where the locals sit within the frame, off its header."""

        return self.read_word(self.frameptr + 4)

    @property
    def locals_length(self) -> int:
        """The locals segment's length in bytes, padding included."""

        return self.valstackbase - self.localsbase

    def locals_format(self) -> tuple[LocalsFormat, ...]:
        """Read the current frame's format list back off the stack."""

        entries: list[LocalsFormat] = []
        position = self.frameptr + FRAME_HEADER_SIZE

        while position + FORMAT_ENTRY_SIZE <= self.localsbase:
            size = self._data[position]
            count = self._data[position + 1]

            if size == 0:
                break

            entries.append(LocalsFormat(size, count))
            position += FORMAT_ENTRY_SIZE

        return tuple(entries)

    def get_local(self, offset: int, width: int = WORD_WIDTH) -> int:
        """Read a local by its offset from localsbase.

        The offset is what the locals addressing modes and a call
        stub's DestType 2 both carry.

        The segment test is spelled out here, and the word case
        goes straight to its accessor, because this is among the
        machine's most-run lines: the roundabout way was a property
        call, a checking call, and a dispatch on width before any
        byte was read. A reference that fails the test hands off to
        _refuse_local, which owns the wording of the refusal.

        Raises:
            GlulxStackError: For a reference outside the locals
                segment -- the spec's "must not point outside"
                made a real check -- or off its alignment.
        """

        if offset < 0 or offset > self.valstackbase - self.localsbase - width:
            self._refuse_local(offset)

        position = self.localsbase + offset

        if width == WORD_WIDTH:
            return self.read_word(position)

        return self.read(position, width)

    def set_local(self, offset: int, value: int, width: int = WORD_WIDTH) -> None:
        """Write a local by its offset from localsbase, masked.

        Raises:
            GlulxStackError: For a reference outside the locals
                segment or off its alignment.
        """

        if offset < 0 or offset > self.valstackbase - self.localsbase - width:
            self._refuse_local(offset)

        position = self.localsbase + offset

        if width == WORD_WIDTH:
            self.write_word(position, value)
        else:
            self.write(position, width, value)

    def _refuse_local(self, offset: int) -> None:
        """Refuse a local reference outside the locals segment.

        The reference glulxe skips this check, noting that "a
        strict mode interpreter probably should" make it; the spec
        says a local reference "must not point outside the range of
        the current function's locals segment", and an unchecked
        one reads the frame header or a neighbouring frame --
        silent corruption instead of a diagnosable fault.

        The test itself is at the two call sites, where it is run
        tens of millions of times a session and cannot afford a
        call. This owns the wording, and is reached only once the
        test has already failed.

        Raises:
            GlulxStackError: Always; that is what it is for.
        """

        msg = (
            f"a local reference at offset {offset} points outside "
            f"the current function's locals segment "
            f"(Glulx: The Call Frame)"
        )

        raise GlulxStackError(msg)


def _aligned(value: int, alignment: int) -> int:
    """The value rounded up to its width's natural alignment."""

    remainder = value % alignment

    return value if remainder == 0 else value + alignment - remainder


def _refused(position: int, width: int, size: int) -> str:
    """Why a stack access was refused: off the stack, or unaligned."""

    if position < 0 or position > size - width:
        return (
            f"a {width}-byte access at {position} is off the "
            f"{size}-byte stack (Glulx: The Stack)"
        )

    return (
        f"a {width}-byte stack access at {position} is off its natural "
        f"alignment (Glulx: The Call Frame)"
    )
