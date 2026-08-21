"""Accelerated functions (Glulx: Accelerated Functions).

A game may ask that calls to one of its own functions be replaced
by a built-in equivalent. These are Inform library veneer routines
-- property lookup, ofclass, and friends -- which dominate its
running time. The spec calls the idea "outrageously CISC"; in
Python it is closer to essential, since the alternative is
interpreting the same object-table walk thousands of times per
turn.

Functions 2 through 7 are deprecated: they assume NUM_ATTR_BYTES
has its default value of 7 and misbehave otherwise. Functions 8
through 13 are the same routines with that assumption removed.
Both sets are carried, because an older game file will ask for the
older ones.

On errors: the spec allows an accelerated function to report them
"by some convenient means", and notes that discarding them is the
safer choice when the I/O system is not Glk. Since every error
here means the game asked about an address that is not what it
claims to be, Voxam discards them and answers what the Inform
original would -- each discarded report is marked in place.
"""

from collections.abc import Callable

from voxam.glulx.memory import Memory
from voxam.glulx.search import binary_search

_MASK = 0xFFFFFFFF
_WORD = 4

# Inform's own layout constants, as the veneer compiles them: the
# type bytes an address is classified by, the RAMSTART word in the
# header, and the property-entry shape.
_HEADER_END = 36
_RAMSTART_AT = 8
_STRING_TYPE = 0xE0
_FUNCTION_TYPE = 0xC0
_OBJECT_TYPE_LOW = 0x70
_OBJECT_TYPE_HIGH = 0x7F
_PROPERTY_ENTRY = 10
_INDIV_RANGE = 8

# The classified regions Z__Region answers.
_OBJECT = 1
_ROUTINE = 2
_STRING = 3

# The parameter table (Glulx: Accelerated Functions). Every entry
# starts at zero.
PARAM_NAMES = {
    0: "classes_table",
    1: "indiv_prop_start",
    2: "class_metaclass",
    3: "object_metaclass",
    4: "routine_metaclass",
    5: "string_metaclass",
    6: "self",
    7: "num_attr_bytes",
    8: "cpv__start",
}


class Accelerator:
    """The acceleration table for one machine.

    Neither the installed functions nor the parameter values are
    part of saved state (Glulx: Accelerated Functions), so nothing
    here is serialized -- and nothing survives into a save or out
    of a restore.

    Attributes:
        params: The parameter values, by number.
    """

    def __init__(self, memory: Memory) -> None:
        """Stand over a memory map with nothing installed."""

        self.memory = memory
        self.params: dict[int, int] = dict.fromkeys(PARAM_NAMES, 0)
        self._installed: dict[int, int] = {}

    @property
    def available(self) -> frozenset[int]:
        """The function numbers this interpreter implements."""

        return frozenset(_FUNCTIONS)

    def set_func(self, index: int, address: int) -> None:
        """The accelfunc opcode's work.

        Index zero cancels. Asking for a function Voxam does not
        implement is silently ignored, which is what lets a game
        request acceleration unconditionally and trust the gestalt
        (Glulx: Accelerated Functions).
        """

        self._installed.pop(address, None)

        if index != 0 and index in _FUNCTIONS:
            self._installed[address] = index

    def set_param(self, index: int, value: int) -> None:
        """The accelparam opcode's work; unknown numbers ignored."""

        if index in self.params:
            self.params[index] = value & _MASK

    def lookup(self, address: int) -> Callable[[list[int]], int] | None:
        """The replacement for a function address, if any."""

        index = self._installed.get(address)

        if index is None:
            return None

        method = _FUNCTIONS[index]

        return lambda args: method(self, args) & _MASK

    # -- the parameters, named ---------------------------------------------

    @property
    def classes_table(self) -> int:
        """The class-object array's address."""

        return self.params[0]

    @property
    def indiv_prop_start(self) -> int:
        """Where the individual property numbers begin."""

        return self.params[1]

    @property
    def class_metaclass(self) -> int:
        """The Class metaclass object."""

        return self.params[2]

    @property
    def object_metaclass(self) -> int:
        """The Object metaclass object."""

        return self.params[3]

    @property
    def routine_metaclass(self) -> int:
        """The Routine metaclass object."""

        return self.params[4]

    @property
    def string_metaclass(self) -> int:
        """The String metaclass object."""

        return self.params[5]

    @property
    def self_addr(self) -> int:
        """The address of the global holding the current self."""

        return self.params[6]

    @property
    def num_attr_bytes(self) -> int:
        """How many attribute bytes an object carries."""

        return self.params[7]

    @property
    def cpv_start(self) -> int:
        """The common property default values table."""

        return self.params[8]

    # -- shared machinery --------------------------------------------------

    def _obj_in_class(self, obj: int) -> bool:
        """Whether an object is a class -- in Class, not of it."""

        return (
            self.memory.read_word((obj + 13 + self.num_attr_bytes) & _MASK)
            == self.class_metaclass
        )

    def _z_region(self, address: int) -> int:
        """Function 1: an address as object, routine, or string."""

        if address < _HEADER_END or address >= self.memory.endmem:
            return 0

        kind = self.memory.read_byte(address)

        if kind >= _STRING_TYPE:
            return _STRING

        if kind >= _FUNCTION_TYPE:
            return _ROUTINE

        # 0x70..0x7F is Inform's object type byte, but only in
        # RAM; the header word at address 8 is RAMSTART.
        if (
            _OBJECT_TYPE_LOW <= kind <= _OBJECT_TYPE_HIGH
            and address >= self.memory.read_word(_RAMSTART_AT)
        ):
            return _OBJECT

        return 0

    def _cp_tab(self, obj: int, prop_id: int, *, new: bool) -> int:
        """Functions 2 and 8: a property entry in an object's table.

        The two differ only in where the table pointer lives: the
        older form hardcodes obj-->4, right only when
        NUM_ATTR_BYTES is 7; the newer derives it.
        """

        if self._z_region(obj) != _OBJECT:
            # ERROR, discarded: asked for the property table of a
            # non-object.
            return 0

        offset = 4 * (3 + self.num_attr_bytes // 4) if new else 16
        table = self.memory.read_word((obj + offset) & _MASK)

        if table == 0:
            return 0

        count = self.memory.read_word(table)

        return binary_search(
            self.memory, prop_id, 2, table + 4, _PROPERTY_ENTRY, count, 0, 0
        )

    def _get_prop(self, obj: int, prop_id: int, *, new: bool) -> int:
        """The property-entry core RA__Pr, RL__Pr, and OP__Pr share."""

        cla = 0

        if prop_id & 0xFFFF0000:
            # A composite id: the low half indexes the classes
            # table, the high half is the property itself.
            cla = self.memory.read_word(
                (self.classes_table + (prop_id & 0xFFFF) * 4) & _MASK
            )

            if not self._oc_cl(obj, cla, new=new):
                return 0

            prop_id >>= 16
            obj = cla

        prop = self._cp_tab(obj, prop_id, new=new)

        if prop == 0:
            return 0

        if self._obj_in_class(obj) and cla == 0:
            # A class only shows its individual properties when
            # asked directly.
            start = self.indiv_prop_start

            if not start <= prop_id < start + _INDIV_RANGE:
                return 0

        # A property flagged as protected is invisible unless the
        # global self is this object -- the veneer's "@aloadbit
        # prop 72", which is bit 0 of the byte at prop+9.
        if self.memory.read_word(self.self_addr) != obj and (
            self.memory.read_byte((prop + 9) & _MASK) & 1
        ):
            return 0

        return prop

    def _ra_pr(self, obj: int, prop_id: int, *, new: bool) -> int:
        """Functions 3 and 9: a property's data address, or 0."""

        prop = self._get_prop(obj, prop_id, new=new)

        return 0 if prop == 0 else self.memory.read_word((prop + 4) & _MASK)

    def _rl_pr(self, obj: int, prop_id: int, *, new: bool) -> int:
        """Functions 4 and 10: a property's length in bytes, or 0."""

        prop = self._get_prop(obj, prop_id, new=new)

        if prop == 0:
            return 0

        return _WORD * self.memory.read_short((prop + 2) & _MASK)

    def _oc_cl(  # noqa: PLR0911 -- one flat return per region and metaclass
        self, obj: int, cla: int, *, new: bool
    ) -> int:
        """Functions 5 and 11: Inform's ofclass."""

        region = self._z_region(obj)

        if region == _STRING:
            return int(cla == self.string_metaclass)

        if region == _ROUTINE:
            return int(cla == self.routine_metaclass)

        if region != _OBJECT:
            return 0

        metaclasses = (
            self.class_metaclass,
            self.string_metaclass,
            self.routine_metaclass,
            self.object_metaclass,
        )

        if cla == self.class_metaclass:
            return int(self._obj_in_class(obj) or obj in metaclasses)

        if cla == self.object_metaclass:
            return int(not (self._obj_in_class(obj) or obj in metaclasses))

        if cla in (self.string_metaclass, self.routine_metaclass):
            return 0

        if not self._obj_in_class(cla):
            # ERROR, discarded: ofclass applied to a non-class.
            return 0

        inlist = self._ra_pr(obj, 2, new=new)

        if inlist == 0:
            return 0

        count = self._rl_pr(obj, 2, new=new) // _WORD

        for index in range(count):
            if self.memory.read_word((inlist + 4 * index) & _MASK) == cla:
                return 1

        return 0

    def _rv_pr(self, obj: int, prop_id: int, *, new: bool) -> int:
        """Functions 6 and 12: a property's value, or its default."""

        address = self._ra_pr(obj, prop_id, new=new)

        if address == 0:
            if 0 < prop_id < self.indiv_prop_start:
                return self.memory.read_word((self.cpv_start + 4 * prop_id) & _MASK)

            # ERROR, discarded: read of a property the object does
            # not have.
            return 0

        return self.memory.read_word(address)

    def _op_pr(self, obj: int, prop_id: int, *, new: bool) -> int:
        """Functions 7 and 13: Inform's provides."""

        region = self._z_region(obj)
        start = self.indiv_prop_start

        if region == _STRING:
            # A string provides print and print_to_array.
            return int(prop_id in (start + 6, start + 7))

        if region == _ROUTINE:
            # A routine provides call.
            return int(prop_id == start + 5)

        if region != _OBJECT:
            return 0

        if start <= prop_id < start + _INDIV_RANGE and self._obj_in_class(obj):
            return 1

        return int(self._ra_pr(obj, prop_id, new=new) != 0)

    # -- the numbered entry points -----------------------------------------
    #
    # Every accelerated function takes its arguments from the call
    # and returns one value. Missing arguments read as zero, as
    # they would in a real call with unfilled locals.

    @staticmethod
    def _arg(args: list[int], index: int) -> int:
        """One call argument, zero where none arrived."""

        return args[index] if index < len(args) else 0

    def func_1_z_region(self, args: list[int]) -> int:
        """Z__Region: classify an address."""

        return self._z_region(self._arg(args, 0))

    def func_2_cp_tab(self, args: list[int]) -> int:
        """CP__Tab, assuming seven attribute bytes."""

        return self._cp_tab(self._arg(args, 0), self._arg(args, 1), new=False)

    def func_3_ra_pr(self, args: list[int]) -> int:
        """RA__Pr, assuming seven attribute bytes."""

        return self._ra_pr(self._arg(args, 0), self._arg(args, 1), new=False)

    def func_4_rl_pr(self, args: list[int]) -> int:
        """RL__Pr, assuming seven attribute bytes."""

        return self._rl_pr(self._arg(args, 0), self._arg(args, 1), new=False)

    def func_5_oc_cl(self, args: list[int]) -> int:
        """OC__Cl, assuming seven attribute bytes."""

        return self._oc_cl(self._arg(args, 0), self._arg(args, 1), new=False)

    def func_6_rv_pr(self, args: list[int]) -> int:
        """RV__Pr, assuming seven attribute bytes."""

        return self._rv_pr(self._arg(args, 0), self._arg(args, 1), new=False)

    def func_7_op_pr(self, args: list[int]) -> int:
        """OP__Pr, assuming seven attribute bytes."""

        return self._op_pr(self._arg(args, 0), self._arg(args, 1), new=False)

    def func_8_cp_tab(self, args: list[int]) -> int:
        """CP__Tab, at any attribute width."""

        return self._cp_tab(self._arg(args, 0), self._arg(args, 1), new=True)

    def func_9_ra_pr(self, args: list[int]) -> int:
        """RA__Pr, at any attribute width."""

        return self._ra_pr(self._arg(args, 0), self._arg(args, 1), new=True)

    def func_10_rl_pr(self, args: list[int]) -> int:
        """RL__Pr, at any attribute width."""

        return self._rl_pr(self._arg(args, 0), self._arg(args, 1), new=True)

    def func_11_oc_cl(self, args: list[int]) -> int:
        """OC__Cl, at any attribute width."""

        return self._oc_cl(self._arg(args, 0), self._arg(args, 1), new=True)

    def func_12_rv_pr(self, args: list[int]) -> int:
        """RV__Pr, at any attribute width."""

        return self._rv_pr(self._arg(args, 0), self._arg(args, 1), new=True)

    def func_13_op_pr(self, args: list[int]) -> int:
        """OP__Pr, at any attribute width."""

        return self._op_pr(self._arg(args, 0), self._arg(args, 1), new=True)


_FUNCTIONS: dict[int, Callable[[Accelerator, list[int]], int]] = {
    1: Accelerator.func_1_z_region,
    2: Accelerator.func_2_cp_tab,
    3: Accelerator.func_3_ra_pr,
    4: Accelerator.func_4_rl_pr,
    5: Accelerator.func_5_oc_cl,
    6: Accelerator.func_6_rv_pr,
    7: Accelerator.func_7_op_pr,
    8: Accelerator.func_8_cp_tab,
    9: Accelerator.func_9_ra_pr,
    10: Accelerator.func_10_rl_pr,
    11: Accelerator.func_11_oc_cl,
    12: Accelerator.func_12_rv_pr,
    13: Accelerator.func_13_op_pr,
}
