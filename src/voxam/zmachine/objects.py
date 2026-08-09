"""The object table: attributes, family relations, properties (§12).

Objects live in a table in dynamic memory whose address the header
word at $0a gives (§12.1). Each has attribute flags, a parent, a
sibling, and a child, plus its own property table. The geometry
forks at Version 4: entry sizes, attribute counts, object limits,
and the property size-byte format all change.
"""

from voxam.errors import ZMachineObjectError
from voxam.zmachine.memory import Memory

V3_LAST_VERSION = 3

# The property defaults table opens the object table: 31 words
# through Version 3, 63 after (§12.2).
V3_DEFAULTS = 31
V4_DEFAULTS = 63

# Entries are 9 bytes with 32 attribute flags and byte-sized family
# relations through Version 3; 14 bytes, 48 flags, and word-sized
# relations after (§12.3.1, §12.3.2).
V3_ENTRY_SIZE = 9
V4_ENTRY_SIZE = 14
V3_ATTRIBUTE_BYTES = 4
V4_ATTRIBUTE_BYTES = 6
V3_MAX_OBJECT = 255
V4_MAX_OBJECT = 65535

# Version 1 to 3 property size bytes: 32 * (length - 1) + number
# (§12.4.1). A zero size byte terminates the list.
V3_PROPERTY_NUMBER_MASK = 0x1F
V3_SIZE_FACTOR = 32
TERMINATOR = 0

# Version 4 and later size bytes: the number is the bottom 6 bits;
# bit 7 set means a second byte carries the length in its bottom 6
# bits, with 0 meaning 64; bit 7 clear means bit 6 selects a length
# of 2 over 1 (§12.4.2).
V4_PROPERTY_NUMBER_MASK = 0x3F
TWO_BYTE_SIZE_BIT = 0x80
ONE_BYTE_LENGTH_BIT = 0x40
V4_LENGTH_MASK = 0x3F
ZERO_MEANS_64 = 64

# get_prop and put_prop only handle lengths 1 and 2 (§15).
WORD_LENGTH = 2

WORD_SIZE = 2
RELATION_COUNT = 3


class ObjectTable:
    """A live view of the object table within a memory image (§12)."""

    def __init__(self, memory: Memory) -> None:
        """Fix the version-dependent geometry over an image.

        Args:
            memory: The memory image whose object table this reads
                and writes.
        """

        self._memory = memory
        self._base = memory.header.object_table_address

        v3 = memory.header.version <= V3_LAST_VERSION

        self._attribute_count = 8 * (V3_ATTRIBUTE_BYTES if v3 else V4_ATTRIBUTE_BYTES)
        self._attribute_bytes = V3_ATTRIBUTE_BYTES if v3 else V4_ATTRIBUTE_BYTES
        self._entry_size = V3_ENTRY_SIZE if v3 else V4_ENTRY_SIZE
        self._defaults = V3_DEFAULTS if v3 else V4_DEFAULTS
        self._max_object = V3_MAX_OBJECT if v3 else V4_MAX_OBJECT
        self._v3 = v3
        self._entries = self._base + WORD_SIZE * self._defaults

    def default(self, number: int) -> int:
        """Read a property's default value (§12.2).

        Args:
            number: The property number, 1 up to the table size.

        Returns:
            The default word for that property.

        Raises:
            ZMachineObjectError: If no such default exists.
        """

        if not 1 <= number <= self._defaults:
            msg = (
                f"property {number} has no default; the table holds "
                f"{self._defaults} (§12.2)"
            )

            raise ZMachineObjectError(msg)

        return self._memory.read_word(self._base + WORD_SIZE * (number - 1))

    def attribute(self, obj: int, attribute: int) -> bool:
        """Test an attribute flag (§12.3.1).

        Args:
            obj: The object number.
            attribute: The attribute number, 0 upward.

        Returns:
            Whether the flag is set.
        """

        address, bit = self._attribute_location(obj, attribute)

        return bool(self._memory.read_byte(address) & bit)

    def set_attribute(self, obj: int, attribute: int, on: bool) -> None:
        """Set or clear an attribute flag (§12.3.1).

        Args:
            obj: The object number.
            attribute: The attribute number, 0 upward.
            on: Whether the flag should end up set.
        """

        address, bit = self._attribute_location(obj, attribute)
        flags = self._memory.read_byte(address)
        flags = flags | bit if on else flags & ~bit & 0xFF

        self._memory.write_byte(address, flags)

    def parent(self, obj: int) -> int:
        """The object's parent, 0 for none (§12.3)."""

        return self._relation(obj, 0)

    def sibling(self, obj: int) -> int:
        """The object's next sibling, 0 for none (§12.3)."""

        return self._relation(obj, 1)

    def child(self, obj: int) -> int:
        """The object's first child, 0 for none (§12.3)."""

        return self._relation(obj, 2)

    def remove(self, obj: int) -> None:
        """Detach an object from its parent (§15 remove_obj).

        Its children stay with it; it keeps no stale sibling link.
        """

        parent = self.parent(obj)

        if parent == 0:
            return

        following = self.sibling(obj)

        if self.child(parent) == obj:
            self._set_relation(parent, 2, following)
        else:
            previous = self.child(parent)

            while self.sibling(previous) != obj:
                previous = self.sibling(previous)

            self._set_relation(previous, 1, following)

        self._set_relation(obj, 0, 0)
        self._set_relation(obj, 1, 0)

    def insert(self, obj: int, destination: int) -> None:
        """Move an object to be a destination's first child (§15 insert_obj)."""

        self.remove(obj)
        self._set_relation(obj, 1, self.child(destination))
        self._set_relation(obj, 0, destination)
        self._set_relation(destination, 2, obj)

    def short_name_address(self, obj: int) -> int:
        """The byte address of the object's encoded short name (§12.4)."""

        return self._properties_address(obj) + 1

    def find_property(self, obj: int, number: int) -> tuple[int, int] | None:
        """Find a property the object itself provides (§12.4).

        Args:
            obj: The object number.
            number: The property number sought.

        Returns:
            The property data's address and length, or None when the
            object does not provide the property.
        """

        address = self._first_property(obj)

        while True:
            found = self._property_at(address)

            if found is None:
                return None

            found_number, length, data = found

            if found_number == number:
                return data, length

            address = data + length

    def property_value(self, obj: int, number: int) -> int:
        """Read a property, falling back to its default (§15 get_prop).

        Raises:
            ZMachineObjectError: If the property is longer than a
                word, which get_prop may not read (§15).
        """

        found = self.find_property(obj, number)

        if found is None:
            return self.default(number)

        data, length = found

        if length == 1:
            return self._memory.read_byte(data)

        if length == WORD_LENGTH:
            return self._memory.read_word(data)

        msg = (
            f"get_prop may not read property {number} of object {obj}: "
            f"its length is {length}, not 1 or 2 (§15)"
        )

        raise ZMachineObjectError(msg)

    def put_property(self, obj: int, number: int, value: int) -> None:
        """Write a property the object must provide (§15 put_prop).

        A length-1 property takes the least significant byte.

        Raises:
            ZMachineObjectError: If the object does not provide the
                property, or it is longer than a word.
        """

        found = self.find_property(obj, number)

        if found is None:
            msg = (
                f"object {obj} does not provide property {number}, so "
                f"put_prop must halt (§15)"
            )

            raise ZMachineObjectError(msg)

        data, length = found

        if length == 1:
            self._memory.write_byte(data, value & 0xFF)
        elif length == WORD_LENGTH:
            self._memory.write_word(data, value)
        else:
            msg = (
                f"put_prop may not write property {number} of object "
                f"{obj}: its length is {length}, not 1 or 2 (§15)"
            )

            raise ZMachineObjectError(msg)

    def property_length_at(self, data_address: int) -> int:
        """Recover a property's length from its data address (§12.4).

        The size information sits just before the data: a lone size
        byte through Version 3; afterward, a byte whose top bit tells
        whether it is the second of two (carrying a length) or alone
        (bit 6 selecting 2 over 1).
        """

        size_byte = self._memory.read_byte(data_address - 1)

        if self._v3:
            return size_byte // V3_SIZE_FACTOR + 1

        if size_byte & TWO_BYTE_SIZE_BIT:
            return (size_byte & V4_LENGTH_MASK) or ZERO_MEANS_64

        return 2 if size_byte & ONE_BYTE_LENGTH_BIT else 1

    def next_property(self, obj: int, number: int) -> int:
        """Walk the property list (§15 get_next_prop).

        Number 0 asks for the first property; otherwise the property
        after the given one. The result 0 means the list ended.

        Raises:
            ZMachineObjectError: If the given property is absent.
        """

        if number == 0:
            found = self._property_at(self._first_property(obj))

            return 0 if found is None else found[0]

        current = self.find_property(obj, number)

        if current is None:
            msg = (
                f"object {obj} does not provide property {number}, so "
                f"get_next_prop must halt (§15)"
            )

            raise ZMachineObjectError(msg)

        data, length = current
        following = self._property_at(data + length)

        return 0 if following is None else following[0]

    def _entry(self, obj: int) -> int:
        """Locate an object's entry, policing the number (§12.3)."""

        if not 1 <= obj <= self._max_object:
            msg = (
                f"object {obj} does not exist: object numbers run from "
                f"1 to {self._max_object}, with 0 meaning nothing (§12.3)"
            )

            raise ZMachineObjectError(msg)

        return self._entries + (obj - 1) * self._entry_size

    def _attribute_location(self, obj: int, attribute: int) -> tuple[int, int]:
        """Locate the byte and bit of an attribute flag (§12.3.1)."""

        if not 0 <= attribute < self._attribute_count:
            msg = (
                f"attribute {attribute} does not exist: attributes run "
                f"from 0 to {self._attribute_count - 1} (§12.3)"
            )

            raise ZMachineObjectError(msg)

        address = self._entry(obj) + attribute // 8
        bit = 0x80 >> attribute % 8

        return address, bit

    def _relation(self, obj: int, index: int) -> int:
        """Read parent (0), sibling (1), or child (2) (§12.3)."""

        base = self._entry(obj) + self._attribute_bytes

        if self._v3:
            return self._memory.read_byte(base + index)

        return self._memory.read_word(base + WORD_SIZE * index)

    def _set_relation(self, obj: int, index: int, value: int) -> None:
        """Write parent (0), sibling (1), or child (2) (§12.3)."""

        base = self._entry(obj) + self._attribute_bytes

        if self._v3:
            self._memory.write_byte(base + index, value)
        else:
            self._memory.write_word(base + WORD_SIZE * index, value)

    def _properties_address(self, obj: int) -> int:
        """The byte address of the object's property table (§12.3)."""

        return self._memory.read_word(
            self._entry(obj) + self._attribute_bytes + self._relation_bytes()
        )

    def _relation_bytes(self) -> int:
        """How many bytes the three family relations occupy (§12.3)."""

        return RELATION_COUNT * (1 if self._v3 else WORD_SIZE)

    def _first_property(self, obj: int) -> int:
        """The address of the first property block, past the name (§12.4)."""

        table = self._properties_address(obj)
        name_words = self._memory.read_byte(table)

        return table + 1 + WORD_SIZE * name_words

    def _property_at(self, address: int) -> tuple[int, int, int] | None:
        """Read a property block header (§12.4.1, §12.4.2).

        Returns:
            The property number, data length, and data address, or
            None at the list terminator.
        """

        first = self._memory.read_byte(address)

        if first == TERMINATOR:
            return None

        if self._v3:
            number = first & V3_PROPERTY_NUMBER_MASK
            length = first // V3_SIZE_FACTOR + 1

            return number, length, address + 1

        number = first & V4_PROPERTY_NUMBER_MASK

        if first & TWO_BYTE_SIZE_BIT:
            length = self._memory.read_byte(address + 1) & V4_LENGTH_MASK

            return number, length or ZERO_MEANS_64, address + 2

        return number, 2 if first & ONE_BYTE_LENGTH_BIT else 1, address + 1
