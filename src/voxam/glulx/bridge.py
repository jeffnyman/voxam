"""The VM/Glk seam: argument marshalling and the object registry.

This is the only module that reads both sides: Glulx sees opaque
Glk objects as 32-bit ids and passes references as addresses, while
the library sees Python objects and writes into holders. The glk
opcode hands over a selector and a list of raw words; everything
here is about turning those into a Python call and writing the
answers back into VM memory or onto the stack, by the rules the
spec spells out under the glk opcode (Glulx: Miscellaneous).
"""

from collections.abc import Callable, Iterator
from typing import cast

from voxam.errors import GlulxGlkError
from voxam.glulx.glk import dispatch
from voxam.glulx.glk.api import Glk
from voxam.glulx.glk.dispatch import Item, Signature
from voxam.glulx.glk.objects import GlkObject
from voxam.glulx.glk.refs import Held, Ref, RefStruct
from voxam.glulx.memory import Memory
from voxam.glulx.stack import Stack

# A reference argument of -1 means "read from or write to the
# stack" -- a feature of the Glk invocation mechanism alone, not of
# Glulx addressing (Glulx: Miscellaneous).
STACK_REF = 0xFFFFFFFF

_MASK = 0xFFFFFFFF
_WORD = 4
_SIGN_BIT = 0x8000_0000
_NUM_CLASSES = 4

# The type bytes of the string objects a Glk call may name: the
# unencoded forms, and only those (Glulx: Miscellaneous).
_UNENCODED = 0xE0
_UNENCODED_UNICODE = 0xE2

# What a Glulx word that is not a code point renders as.
_UNPRINTABLE = "?"
_MAX_UNICODE = 0x10FFFF

# The deferred work a reference argument leaves behind: writing
# the held answer back after the call returns.
type _Writeback = Callable[[], None]


class Registry:
    """Two-way mapping between Glk objects and the ids Glulx sees.

    The reference glkop.c keeps a hash table per class and seeds
    each with a randomized offset, so that games cannot come to
    depend on particular id values. Voxam assigns ids sequentially
    instead: reproducible ids make transcript-diffing against a
    reference interpreter possible, which is the best correctness
    test available, and nothing in the spec requires randomness.

    Ids are unique across classes and never reused, but lookups
    are still class-checked, so passing a stream id where a window
    is expected reads as the null object rather than as the wrong
    object.
    """

    def __init__(self) -> None:
        """Open empty, with the id counter at one."""

        self._by_id: list[dict[int, GlkObject]] = [{} for _ in range(_NUM_CLASSES)]
        self._by_object: dict[int, int] = {}
        self._next = 1

    def register(self, obj: GlkObject | None, glk_class: int) -> int:
        """The object's id, minted if it is new; the null object is 0."""

        if obj is None:
            return 0

        existing = self._by_object.get(id(obj))

        if existing is not None:
            return existing

        ident = self._next
        self._next += 1
        self._by_object[id(obj)] = ident
        self._by_id[glk_class][ident] = obj

        return ident

    def lookup(self, glk_class: int, ident: int) -> GlkObject | None:
        """The object an id names within a class, or None."""

        if ident == 0:
            return None

        return self._by_id[glk_class].get(ident)

    def forget(self, obj: GlkObject) -> None:
        """Drop a destroyed object, so its id stops resolving.

        The library reports every disposal through its on_dispose
        seat -- the equivalent of glkop.c wiring itself in through
        gidispatch_set_object_registry.
        """

        ident = self._by_object.pop(id(obj), None)

        if ident is not None:
            self._by_id[obj.glk_class].pop(ident, None)


class MemArray:
    """A live view onto an array in VM memory.

    Deliberately not a copy and not a memoryview. Holding
    coordinates and indexing lazily means a retained array -- one
    Glk keeps after the call returns, such as a pending line
    request's buffer -- stays valid across a setmemsize that would
    invalidate a snapshot. It also handles four-byte elements,
    which a byte-oriented view does not.

    Satisfies the objects module's Buffer protocol, which is the
    whole point: the library reads and writes it without knowing a
    VM exists.
    """

    def __init__(
        self,
        memory: Memory,
        address: int,
        count: int,
        element_size: int = 1,
        *,
        signed: bool = False,
    ) -> None:
        """Frame a span of memory as elements of a size."""

        self._memory = memory
        self._address = address
        self._count = count
        self._size = element_size
        self._signed = signed

    def __len__(self) -> int:
        """The element count the call named."""

        return self._count

    def _offset(self, index: int) -> int:
        """The address of one element, bounds enforced.

        Raises:
            IndexError: For an index outside the array.
        """

        if not 0 <= index < self._count:
            msg = f"array index {index} is outside the {self._count} elements"

            raise IndexError(msg)

        return (self._address + index * self._size) & _MASK

    def __getitem__(self, index: int) -> int:
        """Read one element, sign-read when the type is signed."""

        value = self._memory.read(self._offset(index), self._size)

        if self._signed and value & (1 << (8 * self._size - 1)):
            value -= 1 << (8 * self._size)

        return value

    def __setitem__(self, index: int, value: int) -> None:
        """Write one element; the memory layer masks to width."""

        self._memory.write(self._offset(index), self._size, value)

    def __iter__(self) -> Iterator[int]:
        """The elements in order."""

        return (self[index] for index in range(self._count))


class Bridge:
    """Dispatches glk opcode calls into the Glk library.

    Attributes:
        memory: The VM memory reference arguments live in.
        stack: The VM stack the -1 references reach.
        library: The Glk library the calls land on.
        registry: The id mapping for the opaque classes.
    """

    def __init__(self, memory: Memory, library: Glk, stack: Stack) -> None:
        """Join a machine's memory and stack to a library.

        The library's disposal reports are wired straight into the
        registry, so a closed object's id stops resolving.
        """

        self.memory = memory
        self.stack = stack
        self.library = library
        self.registry = Registry()

        library.on_dispose = self.registry.forget

    def perform(self, selector: int, args: list[int]) -> int:
        """Run one Glk call; return the value the opcode stores.

        Stack output references push here, after the call but
        before the opcode's own store -- the order the spec fixes
        (Glulx: Miscellaneous).

        Raises:
            GlulxGlkError: For a selector the dispatch table does
                not carry, an argument count that contradicts its
                signature, or any call while a select stands
                suspended -- the machine should be standing still.
        """

        signature = dispatch.lookup(selector)

        if signature is None:
            # A game asking for a selector this Glk lacks expects
            # a library from the future; that should be loud.
            msg = f"the glk opcode asked for unknown function {selector:#06x}"

            raise GlulxGlkError(msg)

        self._refuse_while_suspended(signature.glk_name)

        if len(args) != signature.word_count:
            msg = (
                f"{signature.glk_name} takes {signature.word_count} "
                f"argument words, but {len(args)} arrived"
            )

            raise GlulxGlkError(msg)

        # Every declared signature has a function: the api's own
        # completeness test holds the two tables together.
        function = getattr(self.library, signature.glk_name)

        call_args, writebacks = self._unmarshal(signature, args)
        result = function(*call_args)

        if self.library.waiting is not None:
            # The call was a select that suspended: its struct is
            # empty until the event arrives, so its travel back
            # into memory waits with it, run by deliver_event.
            self.library.waiting.writebacks = writebacks
        else:
            for writeback in writebacks:
                writeback()

        return self._encode_result(signature.result, result)

    def _refuse_while_suspended(self, glk_name: str) -> None:
        """Refuse any call while a select stands suspended.

        A suspended machine executes nothing until its event is
        delivered; a call arriving anyway means a host ran on past
        the suspension. Refused before any argument pops, so the
        stack stays whole.

        Raises:
            GlulxGlkError: When the library stands suspended.
        """

        if self.library.waiting is not None:
            msg = f"{glk_name} called while the machine stands suspended"

            raise GlulxGlkError(msg)

    def _unmarshal(
        self, signature: Signature, args: list[int]
    ) -> tuple[list[object], list[_Writeback]]:
        """Turn raw words into Python arguments, left to right."""

        call_args: list[object] = []
        writebacks: list[_Writeback] = []
        position = 0

        for item in signature.args:
            value, writeback, position = self._unmarshal_item(item, args, position)

            call_args.append(value)

            if writeback is not None:
                writebacks.append(writeback)

        return call_args, writebacks

    def _unmarshal_item(  # noqa: PLR0911 -- one return per argument shape
        self, item: Item, args: list[int], position: int
    ) -> tuple[object, _Writeback | None, int]:
        """One prototype item into one Python argument.

        Returns the argument, an optional write-back to run after
        the call, and the new position in the raw words.

        Raises:
            GlulxGlkError: For a null address where the signature
                forbids one.
        """

        if item.array:
            address, count = args[position], args[position + 1]
            position += 2

            if address == 0:
                self._require_nullable(item)

                return None, None, position

            if item.is_opaque:
                # An array of object ids -- only ever passed in,
                # so a snapshot is equivalent to a live view.
                found = [
                    self.registry.lookup(
                        item.opaque_class or 0,
                        self.memory.read_word((address + _WORD * index) & _MASK),
                    )
                    for index in range(count)
                ]

                return found, None, position

            # Writes through a live view land straight in memory,
            # so even an out-array needs no write-back step.
            array = MemArray(
                self.memory, address, count, item.element_size, signed=item.signed
            )

            return array, None, position

        if item.is_reference:
            address = args[position]
            position += 1

            if address == 0:
                self._require_nullable(item)

                return None, None, position

            if address == STACK_REF:
                return *self._stack_reference(item), position

            return *self._memory_reference(item, address), position

        raw = args[position]
        position += 1

        return self._decode(item, raw), None, position

    def _require_nullable(self, item: Item) -> None:
        """Refuse a null address the signature marked nonnull.

        Raises:
            GlulxGlkError: When null is forbidden here.
        """

        if item.nonnull:
            msg = "a null address arrived where the Glk call requires one"

            raise GlulxGlkError(msg)

    def _memory_reference(
        self, item: Item, address: int
    ) -> tuple[Ref | RefStruct, _Writeback | None]:
        """A reference argument held in main memory.

        The value need not be aligned, but is big-endian -- which
        the memory layer's word accessors already are (Glulx:
        Miscellaneous).
        """

        if item.is_struct:
            struct = RefStruct(len(item.fields))

            if item.passes_in:
                struct.fields[:] = [
                    self._decode_value(
                        field,
                        self.memory.read_word((address + _WORD * index) & _MASK),
                    )
                    for index, field in enumerate(item.fields)
                ]

            if not item.passes_out:
                return struct, None

            def write_struct() -> None:
                for index, field in enumerate(item.fields):
                    self.memory.write_word(
                        (address + _WORD * index) & _MASK,
                        self._encode(field, struct.fields[index]),
                    )

            return struct, write_struct

        ref = Ref()

        if item.passes_in:
            ref.value = self._decode_value(item, self.memory.read_word(address))

        if not item.passes_out:
            return ref, None

        def write_scalar() -> None:
            self.memory.write_word(address, self._encode(item, ref.value))

        return ref, write_scalar

    def _stack_reference(self, item: Item) -> tuple[Ref | RefStruct, _Writeback | None]:
        """A reference argument of -1: the value lives on the stack.

        The spec spells out the ordering: an input reference is
        popped first-topmost, so a struct's first field is the
        topmost value, and an output reference is pushed
        last-topmost, so pushing the fields in order leaves the
        last one on top (Glulx: Miscellaneous). The pops happen
        here, after the Glk argument list has already come off the
        stack, which is also the order the spec requires.
        """

        if item.is_struct:
            struct = RefStruct(len(item.fields))

            if item.passes_in:
                struct.fields[:] = [
                    self._decode_value(field, self.stack.pop()) for field in item.fields
                ]

            if not item.passes_out:
                return struct, None

            def push_struct() -> None:
                for index, field in enumerate(item.fields):
                    self.stack.push(self._encode(field, struct.fields[index]))

            return struct, push_struct

        ref = Ref()

        if item.passes_in:
            ref.value = self._decode_value(item, self.stack.pop())

        if not item.passes_out:
            return ref, None

        def push_scalar() -> None:
            self.stack.push(self._encode(item, ref.value))

        return ref, push_scalar

    def _decode(self, item: Item, raw: int) -> Held | str:
        """A plain argument word into what Glk should receive."""

        if item.is_string:
            return (
                self._read_unicode_string(raw)
                if item.code == "U"
                else self._read_string(raw)
            )

        return self._decode_value(item, raw)

    def _decode_value(self, item: Item, raw: int) -> Held:
        """A word into an object, a signed value, or itself."""

        if item.is_opaque:
            return self.registry.lookup(item.opaque_class or 0, raw)

        if item.signed and raw & _SIGN_BIT:
            return raw - (1 << 32)

        return raw

    def _encode(self, item: Item, value: Held) -> int:
        """A Python value back into a 32-bit word."""

        if item.is_opaque:
            obj = value if isinstance(value, GlkObject) else None

            return self.registry.register(obj, item.opaque_class or 0)

        # Only words reach here: strings never pass back out, and
        # objects took the opaque branch above.
        return cast("int", value) & _MASK

    def _encode_result(self, item: Item | None, value: Held) -> int:
        """The result as a word; a void call stores zero (Glulx: Miscellaneous)."""

        if item is None:
            return 0

        return self._encode(item, value)

    def _read_string(self, address: int) -> str:
        """Read an unencoded (E0) string object.

        A string argument is the address of a *string object*, not
        of a bare byte array -- the type byte comes first and the
        text ends at a zero byte (Glulx: Miscellaneous).

        Raises:
            GlulxGlkError: When the address holds no E0 object.
        """

        kind = self.memory.read_byte(address)

        if kind != _UNENCODED:
            msg = (
                f"the Glk string argument at {address:#x} is not an E0 "
                f"string object (found {kind:#04x})"
            )

            raise GlulxGlkError(msg)

        address += 1
        out = bytearray()

        while True:
            char = self.memory.read_byte(address)

            if char == 0:
                return out.decode("latin-1")

            out.append(char)
            address = (address + 1) & _MASK

    def _read_unicode_string(self, address: int) -> str:
        """Read an unencoded Unicode (E2) string object.

        An E2 object is a type byte and three padding bytes, so
        the characters start four bytes in (Glulx: String
        Encoding).

        Raises:
            GlulxGlkError: When the address holds no E2 object.
        """

        kind = self.memory.read_byte(address)

        if kind != _UNENCODED_UNICODE:
            msg = (
                f"the Glk Unicode string argument at {address:#x} is not "
                f"an E2 string object (found {kind:#04x})"
            )

            raise GlulxGlkError(msg)

        address += _WORD
        out: list[str] = []

        while True:
            char = self.memory.read_word(address)

            if char == 0:
                return "".join(out)

            # A Glulx string may hold values that are not code
            # points at all; they render as the placeholder.
            out.append(chr(char) if char <= _MAX_UNICODE else _UNPRINTABLE)
            address = (address + _WORD) & _MASK
