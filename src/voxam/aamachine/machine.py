"""The Å-machine engine: registers, twin heaps, and the Prolog heart.

The machine is a register machine with a main heap that carries
terms, environment frames, and choice frames, and an auxiliary
heap that carries a scratch stack from one end and the trail from
the other (Aa-machine: Runtime data). Failure unwinds to the
newest choice frame, undoing trailed bindings on the way; a
runtime error restarts the machine at the shared entry point with
the error's number in R00 (Aa-machine: Opcode semantics).

run() executes until the story quits or asks for input, answering
"quit", "line", or "key"; deliver_line and deliver_key parse the
player's answer into the machine's own values and resume. The
whole instruction set is dispatched from _OPS by full opcode
byte, each handler holding its own spec citation.

The dice are the reference implementation's own multiplier
carried deliberately -- state times $015a4e35 plus one, the top
bits told -- so a seeded Voxam run is comparable word for word
with a seeded run of the community fork's engine.
"""

import time
from collections.abc import Callable

from voxam.aamachine import saves
from voxam.aamachine.output import PlainVoice, Voice
from voxam.aamachine.story import Story
from voxam.aamachine.text import Speech
from voxam.errors import AAMachineError, VoxamError

# The unused-word stamp, handy for measuring peak memory
# (Aa-machine: Runtime data).
UNUSED = 0x3F3F

# The empty list literal (Aa-machine: Runtime data).
EMPTY = 0x3F00

# The runtime error numbers, already dressed as tagged integers
# (Aa-machine: Runtime data).
HEAP_FULL = 0x4001
AUX_FULL = 0x4002
EXPECTED_OBJECT = 0x4003
EXPECTED_BOUND = 0x4004
LONGTERM_FULL = 0x4006
BAD_OUTPUT_STATE = 0x4007

# The whitespace states, in their ordering (Aa-machine: Runtime
# data).
_AUTO = 0
_NOSPACE = 1
_NBSP = 2
_PENDING = 3
_SPACE = 4
_LINE = 5
_PAR = 6

# How many undo states the machine keeps before pruning, the
# reference engine's own allowance.
_UNDO_KEPT = 50

# The biggest boxed integer (Aa-machine: Runtime data).
_NUMBER_TOP = 0x3FFF

# A word is sixteen flags, numbered from the most significant bit
# (Aa-machine: Runtime data).
_BITS_PER_WORD = 16

# The reference random stream: a 32-bit linear congruence whose
# top bits are told.
_DICE_STEP = 0x015A4E35

# Operand encoding markers (Aa-machine: Story file): an operand's
# first byte says where the rest of it lives.
_FROM_ENV = 0xC0
_FROM_REGISTER = 0x80
_CLOSE_TOP = 0x40
_RELATIVE_TOP = 0x80
_UNIFY_DEST = 0x80
_ENV_DEST = 0x40

# The opcode bytes a shared handler tells apart by name.
_PAIR_OF_DESTS = 0x12
_PAIR_OF_WORD = 0x13
_RAW_ZERO = 0x94
_RAW_WORD = 0x15
_OLD_LEAVE_STATUS = 0xE7

# A SIM at or above this is no simple cut at all: choice frames
# never naturally dip below it (Aa-machine: PROCEED).
_NO_CUT = 0x8000

# The serialized stream's markers (Aa-machine: Runtime data).
_UNBOUND_MARK = 0x8000
_EXTDICT_MARK = 0x8100
_LIST_MARK = 0xC000

# The character set's landmarks (Aa-machine: Text).
_SPACE_CODE = 0x20
_PRINTABLE_START = 0x20
_PRINTABLE_TOP = 0x7F
_UPPER_A = 0x41
_UPPER_Z = 0x5A
_EXTENDED_START = 0x80

# The endings decoder keeps at least this many characters in the
# stem (Aa-machine: GET_INPUT).
_STEM_KEPT = 2

# A wordmap payload byte at or above this opens a two-byte object
# id (Aa-machine: MAPS).
_WIDE_SEAT = 0xE0

# VM_INFO's frame: the peak-memory areas, and the last defined
# selector (Aa-machine: VM_INFO).
_PEAK_AREAS = 3
_SELECTOR_TOP = 0x7F

# The LANG special characters come in three null-terminated sets
# from format 0.4 (Aa-machine: LANG).
_SPECIAL_SETS = 3

# The live-value tags: a variable number of upper bits, the value
# in the rest (Aa-machine: Runtime data).
_TAG_MASK = 0xE000
_REFERENCE_TAG = 0x8000
_PAIR_TAG = 0xC000
_EXTDICT_TAG = 0xE000
_NUMBER_TAG = 0x4000
_WORD_TAG = 0x2000
_CHAR_TAG = 0x3E00
_CHAR_MASK = 0xFF00
_VALUE_MASK = 0x1FFF
_DIGIT_LOW = 0x30
_DIGIT_HIGH = 0x39


def _referenced(value: int) -> bool:
    """Whether a value is an indirect reference (Aa-machine tag 100)."""

    return (value & _TAG_MASK) == _REFERENCE_TAG


def _paired(value: int) -> bool:
    """Whether a value is a pair (Aa-machine tag 110)."""

    return (value & _TAG_MASK) == _PAIR_TAG


def _extdicted(value: int) -> bool:
    """Whether a value is an extended dict word (Aa-machine tag 111)."""

    return value >= _EXTDICT_TAG


def _numbered(value: int) -> bool:
    """Whether a value is a boxed integer (Aa-machine tag 01)."""

    return _NUMBER_TAG <= value < _REFERENCE_TAG


def _chared(value: int) -> bool:
    """Whether a value is a character literal (Aa-machine: Words)."""

    return (value & _CHAR_MASK) == _CHAR_TAG


def _dicted(value: int) -> bool:
    """Whether a value is a dictionary word literal (Aa-machine: Words)."""

    return _WORD_TAG <= value < _CHAR_TAG


def _objected(value: int) -> bool:
    """Whether a value is an object literal (Aa-machine: Words)."""

    return 1 <= value <= _VALUE_MASK


def _digited(code: int) -> bool:
    """Whether a charset code is a decimal digit."""

    return _DIGIT_LOW <= code <= _DIGIT_HIGH


def _wordish(value: int) -> bool:
    """Whether IF_WORD counts the value: dict, char, or extdict."""

    return _WORD_TAG <= value < EMPTY or _extdicted(value)


def _linkable(value: int) -> bool:
    """Whether ENTER_LINK spells the value into its click words."""

    return _WORD_TAG <= value < _REFERENCE_TAG or _extdicted(value)


class _Missed(Exception):  # noqa: N818 -- not an error: failure is how Prolog says no
    """Raised when execution fails to the newest choice frame."""


class _Fault(Exception):  # noqa: N818 -- carries a tagged error code, not a Python error
    """Raised for a runtime error, carrying its tagged number."""

    def __init__(self, code: int) -> None:
        self.code = code

        super().__init__(f"runtime error {code - 0x4000}")


class Machine:
    """One running Å-machine, speaking through a Voice.

    Attributes:
        running: False once the story has quit.
    """

    _regs: list[int]
    _inst: int
    _cont: int
    _top: int
    _env: int
    _cho: int
    _sim: int
    _auxp: int
    _trl: int
    _sta: int
    _stc: int
    _cwl: int
    _spc: int
    _tmp: int
    _nob: int
    _ltb: int
    _ltt: int
    _divs: list[int]
    _upper: bool
    _trace: bool
    _in_status: int
    _n_span: int
    _n_link: int
    _dice: int
    _undo: list[saves.State]
    _pruned: bool

    def __init__(self, story: Story, voice: Voice, seed: int | None = None) -> None:
        """Ready a story for its first run.

        Raises:
            AAMachineError: For a LANG chunk whose decoder or
                special-character offsets lie outside it.
        """

        self._story = story
        self._voice = voice
        self._seed = seed
        # Instructions executed across the whole session, kept
        # so an instrument can measure the machine's own pace.
        # Counted in run()'s loop rather than per dispatch, so the
        # hot path pays one local add and nothing more.
        self.instructions = 0
        self._speech = Speech(story)
        self._major = story.version[0]
        self._code = story.summed(b"CODE").payload
        self._init = story.summed(b"INIT").payload
        self._maps = story.summed(b"MAPS").payload
        self._dict = story.summed(b"DICT").payload
        self._lang = story.summed(b"LANG").payload
        self._tags = story.chunk(b"TAGS")
        self._heap: list[int] = [UNUSED] * story.heap_size
        self._aux: list[int] = [UNUSED] * story.aux_size
        self._ram: list[int] = [UNUSED] * story.ram_size
        self._endings_at = int.from_bytes(self._lang[4:6], "big")
        self._cased = _cased(self._lang, story.extended)
        self._upcased = _upcased(self._lang, story.extended)
        self._stops, self._unspaced_before, self._unspaced_after = _stopped(
            self._lang, story.version
        )
        self._sought = _sought(self._dict)
        self.running = True

        # The sidecar's one honest bit: an undo, restore, or
        # restart broke the causal thread; the wire face reads it
        # once and rests it (DESIGN: What the sidecar carries).
        self.discontinuity = False

        self._reinit()
        self._reset(0, clear_undo=True)
        self._held = self._captured(1)

    def run(self, delivered: int | None = None) -> str:
        """Execute until the story quits or waits.

        Returns "quit", "line", or "key"; a delivered value is
        stored through the pending input instruction's destination
        first (Aa-machine: Opcode semantics).

        Raises:
            AAMachineError: For an instruction the engine does not
                carry, or a failure with no choice frame standing.
        """

        steps = 0

        while True:
            try:
                if delivered is not None:
                    answered, delivered = delivered, None
                    self._store(self._fetched(), answered)

                steps += 1
                op = self._fetched()
                handler = _OPS.get(op)

                if handler is None:
                    msg = (
                        f"reached opcode {op:#04x} at ${self._inst - 1:06x}, "
                        f"which this engine does not carry (Aa-machine: Story file)"
                    )

                    raise AAMachineError(msg)

                told = handler(self, op)

                if told is not None:
                    self.instructions += steps

                    return told
            except _Missed:
                delivered = None
                self._fallen()
            except _Fault as fault:
                delivered = None
                self._faulted(fault.code)

    def deliver_line(self, text: str) -> str:
        """Answer a waiting GET_INPUT with the player's line.

        The line is lowercased through the story's own case table,
        split at whitespace and stop characters, and parsed word
        by word into machine values (Aa-machine: GET_INPUT).
        """

        codes = [self._encased(piece) for piece in text]
        pieces: list[list[int]] = []
        start = 0

        for at, code in enumerate(codes):
            if code == _SPACE_CODE:
                if at != start:
                    pieces.append(codes[start:at])

                start = at + 1
            elif code in self._stops:
                if at != start:
                    pieces.append(codes[start:at])

                pieces.append([code])
                start = at + 1

        if start != len(codes):
            pieces.append(codes[start:])

        try:
            told = EMPTY

            for piece in reversed(pieces):
                told = self._pair(self._parsed(piece), told)
        except _Fault as fault:
            self._faulted(fault.code)

            self._spc = _LINE

            return self.run()

        self._spc = _LINE

        return self.run(delivered=told)

    def deliver_key(self, code: int) -> str:
        """Answer a waiting GET_KEY with one keypress.

        The code is a Unicode codepoint, or one of the reserved
        keypress codes -- $08, $0d, $10 to $13 (Aa-machine: Text).
        A key the story's character set cannot spell leaves the
        wait standing.
        """

        told = 0

        if _PRINTABLE_START <= code < _PRINTABLE_TOP:
            told = code ^ 0x20 if _UPPER_A <= code <= _UPPER_Z else code
        elif code in (0x08, 0x0D, 0x10, 0x11, 0x12, 0x13):
            told = code
        else:
            told = self._cased.get(chr(code), 0)

        if not told:
            return "key"

        self._spc = _SPACE

        if _digited(told):
            return self.run(delivered=0x4000 + told - 0x30)

        return self.run(delivered=0x3E00 | told)

    # -- the fetch stage -------------------------------------------------

    def _fetched(self) -> int:
        """The next code byte, the instruction pointer advanced."""

        told = self._code[self._inst]
        self._inst += 1

        return told

    def _value(self) -> int:
        """A VALUE or RAW operand (Aa-machine: Story file)."""

        told = self._fetched()

        if told >= _FROM_ENV:
            return self._heap[self._env + 4 + (told & 0x3F)]

        if told >= _FROM_REGISTER:
            return self._regs[told & 0x3F]

        return (told << 8) | self._fetched()

    def _index(self) -> int:
        """An INDEX operand (Aa-machine: Story file)."""

        told = self._fetched()

        if told >= _FROM_ENV:
            return ((told & 0x3F) << 8) | self._fetched()

        return told

    def _target(self) -> int:
        """A CODE operand, relative forms already resolved."""

        told = self._fetched()

        if told == 0:
            return 0

        if told < _CLOSE_TOP:
            return self._inst + told

        if told < _RELATIVE_TOP:
            told = ((told & 0x3F) << 8) | self._fetched()

            return self._inst + told - (0x4000 if told & 0x2000 else 0)

        told = ((told & 0x7F) << 16) | (self._fetched() << 8)

        return told | self._fetched()

    def _string(self) -> int:
        """A STRING operand: a shifted byte address into WRIT."""

        told = self._fetched()

        if told >= _FROM_ENV:
            told = ((told & 0x3F) << 16) | (self._fetched() << 8)
            told |= self._fetched()

            return told << self._story.shift

        if told >= _FROM_REGISTER:
            told = ((told & 0x3F) << 8) | self._fetched()

            return told << self._story.shift

        return told << 1

    def _word(self) -> int:
        """A WORD or VWORD operand: two plain bytes."""

        return (self._fetched() << 8) | self._fetched()

    # -- the store stage -------------------------------------------------

    def _slotted(self, dest: int) -> int:
        """The current value behind a destination byte's seat."""

        if dest & 0x40:
            return self._heap[self._env + 4 + (dest & 0x3F)]

        return self._regs[dest & 0x3F]

    def _store(self, dest: int, value: int) -> None:
        """Store or unify through a DEST byte (Aa-machine: Story file).

        Raises:
            _Missed: When the unify variants cannot agree.
        """

        if dest >= _UNIFY_DEST:
            self._unify(self._slotted(dest), value)
        elif dest >= _ENV_DEST:
            self._heap[self._env + 4 + (dest & 0x3F)] = value
        else:
            self._regs[dest] = value

    # -- terms: deref, unify, allocation ---------------------------------

    def _deref(self, value: int) -> int:
        """Chase references to the value they hold (Aa-machine: ASSIGN)."""

        while _referenced(value):
            told = self._heap[value & 0x1FFF]

            if not told:
                return value

            value = told

        return value

    def _bound(self, address: int) -> None:
        """Bind the variable at a heap address, the trail told.

        Raises:
            _Fault: When the trail meets the aux stack.
        """

        if self._trl <= self._auxp:
            raise _Fault(AUX_FULL)

        self._trl -= 1
        self._aux[self._trl] = address

    def _unify(self, a: int, b: int) -> None:
        """Make two values the same or fail (Aa-machine: ASSIGN).

        Raises:
            _Missed: When the terms cannot agree.
            _Fault: When the trail meets the aux stack.
        """

        while True:
            a = self._deref(a)
            b = self._deref(b)

            if _referenced(a) and _referenced(b):
                if a != b:
                    older, newer = (a, b) if a < b else (b, a)
                    self._bound(newer & 0x1FFF)
                    self._heap[newer & 0x1FFF] = older

                return

            if _referenced(a) or _referenced(b):
                ref, told = (a, b) if _referenced(a) else (b, a)
                self._bound(ref & 0x1FFF)
                self._heap[ref & 0x1FFF] = told

                return

            if _extdicted(a) or _extdicted(b):
                if _extdicted(a):
                    a = self._heap[a & 0x1FFF]

                if _extdicted(b):
                    b = self._heap[b & 0x1FFF]
            elif a == b:
                return
            elif _paired(a) and _paired(b):
                self._unify(0x8000 | (a & 0x1FFF), 0x8000 | (b & 0x1FFF))
                a = 0x8000 | ((a & 0x1FFF) + 1)
                b = 0x8000 | ((b & 0x1FFF) + 1)
            else:
                raise _Missed

    def _agreeable(self, a: int, b: int) -> bool:
        """Whether two values could unify, nothing bound (Aa-machine: IF_UNIFY)."""

        while True:
            a = self._deref(a)
            b = self._deref(b)

            if _referenced(a) or _referenced(b):
                return True

            if _extdicted(a) or _extdicted(b):
                if _extdicted(a):
                    a = self._heap[a & 0x1FFF]

                if _extdicted(b):
                    b = self._heap[b & 0x1FFF]
            elif a == b:
                return True
            elif _paired(a) and _paired(b):
                if not self._agreeable(0x8000 | (a & 0x1FFF), 0x8000 | (b & 0x1FFF)):
                    return False

                a = 0x8000 | ((a & 0x1FFF) + 1)
                b = 0x8000 | ((b & 0x1FFF) + 1)
            else:
                return False

    def _claimed(self, count: int) -> int:
        """Claim words at the heap's top; the old top comes back.

        Raises:
            _Fault: When the heap meets the frames.
        """

        told = self._top
        self._top += count

        if self._top > min(self._env, self._cho):
            raise _Fault(HEAP_FULL)

        return told

    def _pair(self, head: int, tail: int) -> int:
        """A fresh pair cell holding head and tail (Aa-machine: Runtime data)."""

        at = self._claimed(2)
        self._heap[at] = head
        self._heap[at + 1] = tail

        return 0xC000 | at

    def _variable(self) -> int:
        """A fresh unbound variable on the heap."""

        at = self._claimed(1)
        self._heap[at] = 0

        return 0x8000 | at

    # -- frames ----------------------------------------------------------

    def _pushed_choice(self, kept: int, handler: int) -> None:
        """Push a choice frame keeping the first registers (Aa-machine: PUSH_CHOICE)."""

        at = min(self._env, self._cho) - 9 - kept

        if at < self._top:
            raise _Fault(HEAP_FULL)

        self._heap[at + 0] = self._env
        self._heap[at + 1] = self._sim
        self._heap[at + 2] = self._cont >> 16
        self._heap[at + 3] = self._cont & 0xFFFF
        self._heap[at + 4] = handler >> 16
        self._heap[at + 5] = handler & 0xFFFF
        self._heap[at + 6] = self._cho
        self._heap[at + 7] = self._top
        self._heap[at + 8] = self._trl

        for seat in range(kept):
            self._heap[at + 9 + seat] = self._regs[seat]

        self._cho = at

    def _popped_choice(self, kept: int) -> None:
        """Restore from the newest choice frame (Aa-machine: POP_CHOICE).

        The trail unwinds on the way, unbinding what was bound
        past the frame's mark.
        """

        for seat in range(kept):
            self._regs[seat] = self._heap[self._cho + 9 + seat]

        while self._trl < self._heap[self._cho + 8]:
            self._heap[self._aux[self._trl]] = 0
            self._trl += 1

        self._top = self._heap[self._cho + 7]
        self._cont = (self._heap[self._cho + 2] << 16) | self._heap[self._cho + 3]
        self._sim = self._heap[self._cho + 1]
        self._env = self._heap[self._cho + 0]

    def _fallen(self) -> None:
        """Land a failure at the newest choice frame's handler.

        Raises:
            AAMachineError: When no choice frame stands at all.
        """

        if self._cho + 6 > len(self._heap):
            msg = "the story failed with no choice frame standing (Aa-machine: FAIL)"

            raise AAMachineError(msg)

        self._inst = (self._heap[self._cho + 4] << 16) | self._heap[self._cho + 5]

    def _faulted(self, code: int) -> None:
        """Restart at the entry point with the error told in R00.

        The line is broken if one stands open, the div stack and
        status state are cleared, and only the registers restart --
        the random access area keeps its state (Aa-machine:
        Runtime data).
        """

        if self._spc < _LINE:
            self._voice.line()

        self._cleared_divs()
        self._reset(code, clear_undo=False)

    # -- the random access area ------------------------------------------

    def _field_at(self, field: int, obj: int) -> int:
        """The RAM address of an object's field (Aa-machine: Runtime data).

        Raises:
            _Fault: For a non-object past the object count.
        """

        obj = self._deref(obj)

        if obj > self._nob:
            raise _Fault(EXPECTED_OBJECT)

        return self._ram[obj] + field

    def _field(self, field: int, obj: int) -> int:
        """An object's field read; non-objects politely read zero."""

        obj = self._deref(obj)

        if obj > self._nob:
            return 0

        return self._ram[self._ram[obj] + field]

    def _unlinked(self, root: int, field: int, key: int) -> None:
        """Remove a key object from a RAM-linked chain (Aa-machine: UNLINK)."""

        key = self._deref(key)

        if not _objected(key):
            return

        tail = self._ram[self._field_at(field, key)]
        at = root

        while self._ram[at] != 0:
            if self._ram[at] == key:
                self._ram[at] = tail

                return

            at = self._field_at(field, self._ram[at])

    # -- long-term storage -----------------------------------------------

    def _lifted(self, value: int) -> int:
        """A stored value fetched, long-term data revived (Aa-machine: LOAD_VAL)."""

        if value & 0x8000:
            self._tmp = value & 0x7FFF
            self._tmp += self._ram[self._tmp]
            value = self._popped_longterm()

        return value

    def _popped_longterm(self) -> int:
        """One value deserialized backward out of long-term storage."""

        self._tmp -= 1
        value = self._ram[self._tmp]

        if value == _UNBOUND_MARK:
            return self._variable()

        if value == _EXTDICT_MARK:
            at = self._claimed(2)
            self._heap[at + 0] = self._popped_longterm()
            self._heap[at + 1] = self._popped_longterm()

            return 0xE000 | at

        if (value & _LIST_MARK) == _LIST_MARK:
            count = value & 0x1FFF
            value = self._popped_longterm() if value & 0x2000 else EMPTY

            for _ in range(count):
                value = self._pair(self._popped_longterm(), value)

        return value

    def _kept_longterm(self, address: int, value: int) -> None:
        """Store at a RAM address, live data serialized (Aa-machine: STORE_VAL)."""

        self._cleared_longterm(address)
        value = self._deref(value)

        if (value & 0xE000) in (0xC000, 0xE000) or _referenced(value):
            self._tmp = self._ltt + 2

            if self._tmp > len(self._ram):
                raise _Fault(LONGTERM_FULL)

            self._pushed_longterm(value)
            self._ram[address] = 0x8000 + self._ltt
            self._ram[self._ltt + 0] = self._tmp - self._ltt
            self._ram[self._ltt + 1] = address
            self._ltt = self._tmp
        else:
            self._ram[address] = value

    def _pushed_longterm(self, value: int) -> None:
        """One value serialized into long-term storage.

        Raises:
            _Fault: For an unbound value, or storage exhausted.
        """

        value = self._deref(value)

        if _paired(value):
            count = 0

            while True:
                self._pushed_longterm(self._heap[value & 0x1FFF])
                count += 1
                value = self._deref(self._heap[(value & 0x1FFF) + 1])

                if value == EMPTY:
                    value = 0xC000 | count

                    break

                if not _paired(value):
                    self._pushed_longterm(value)
                    value = 0xE000 | count

                    break
        elif _extdicted(value):
            self._pushed_longterm(self._heap[(value & 0x1FFF) + 1])
            self._pushed_longterm(self._heap[(value & 0x1FFF) + 0])
            value = 0x8100
        elif _referenced(value):
            raise _Fault(EXPECTED_BOUND)

        if self._tmp >= len(self._ram):
            raise _Fault(LONGTERM_FULL)

        self._ram[self._tmp] = value
        self._tmp += 1

    def _cleared_longterm(self, address: int) -> None:
        """Free a long-term chunk (Aa-machine: STORE_VAL).

        The surviving chunks slide down and their owners are
        repointed through their back-references.
        """

        value = self._ram[address]

        if not value & 0x8000:
            return

        self._ram[address] = 0
        value &= 0x7FFF
        size = self._ram[value]

        for at in range(value, self._ltt - size):
            self._ram[at] = self._ram[at + size]

        self._ltt -= size

        while value < self._ltt:
            self._ram[self._ram[value + 1]] -= size
            value += self._ram[value]

    # -- the aux stack ---------------------------------------------------

    def _pushed_aux(self, value: int) -> None:
        """One raw word onto the aux stack.

        Raises:
            _Fault: When the aux stack meets the trail.
        """

        if self._auxp >= self._trl:
            raise _Fault(AUX_FULL)

        self._aux[self._auxp] = value
        self._auxp += 1

    def _popped_aux(self) -> int:
        """One raw word off the aux stack, underflow loud.

        Raises:
            AAMachineError: When the stack is empty.
        """

        if self._auxp == 0:
            msg = "the aux stack popped past its own bottom (Aa-machine: Runtime data)"

            raise AAMachineError(msg)

        self._auxp -= 1

        return self._aux[self._auxp]

    def _serialized(self, value: int) -> None:
        """One value serialized onto the aux stack (Aa-machine: AUX_PUSH_VAL)."""

        value = self._deref(value)

        if _paired(value):
            count = 0

            while True:
                self._serialized(self._heap[value & 0x1FFF])
                count += 1
                value = self._deref(self._heap[(value & 0x1FFF) + 1])

                if value == EMPTY:
                    value = 0xC000 + count

                    break

                if not _paired(value):
                    self._serialized(value)
                    value = 0xE000 + count

                    break
        elif _extdicted(value):
            self._serialized(self._heap[(value & 0x1FFF) + 1])
            self._serialized(self._heap[(value & 0x1FFF) + 0])
            value = 0x8100
        elif _referenced(value):
            value = 0x8000

        self._pushed_aux(value)

    def _deserialized(self) -> int:
        """One value deserialized off the aux stack (Aa-machine: AUX_POP_VAL)."""

        value = self._popped_aux()

        if value == _UNBOUND_MARK:
            return self._variable()

        if value == _EXTDICT_MARK:
            at = self._claimed(2)
            self._heap[at + 0] = self._deserialized()
            self._heap[at + 1] = self._deserialized()

            return 0xE000 | at

        if (value & _LIST_MARK) == _LIST_MARK:
            count = value & 0x1FFF
            value = self._deserialized() if value & 0x2000 else EMPTY

            for _ in range(count):
                value = self._pair(self._deserialized(), value)

        return value

    def _deserialized_list(self) -> int:
        """Values deserialized to the end marker (Aa-machine: AUX_POP_LIST)."""

        told = EMPTY

        while value := self._deserialized():
            told = self._pair(value, told)

        return told

    # -- the dice --------------------------------------------------------

    def _rolled(self) -> int:
        """The next roll of the reference dice: fifteen fair bits."""

        self._dice = (self._dice * _DICE_STEP + 1) & 0xFFFFFFFF

        return (self._dice >> 16) & 0x7FFF

    # -- numbers ---------------------------------------------------------

    def _unboxed(self, value: int) -> int:
        """A tagged number's value, anything else failing (Aa-machine: ADD_NUM)."""

        value = self._deref(value)

        if not _numbered(value):
            raise _Missed

        return value & _NUMBER_TOP

    def _boxed(self, value: int) -> int:
        """A number boxed into its tag, the range enforced by failure."""

        if not 0 <= value <= _NUMBER_TOP:
            raise _Missed

        return 0x4000 | value

    # -- lifecycle -------------------------------------------------------

    def _reinit(self) -> None:
        """Fill the memory areas from INIT, the rest left unused (Aa-machine: INIT)."""

        self._nob = int.from_bytes(self._init[0:2], "big")
        self._ltb = int.from_bytes(self._init[2:4], "big")
        self._ltt = int.from_bytes(self._init[4:6], "big")

        for at in range(len(self._heap)):
            self._heap[at] = UNUSED

        for at in range(len(self._aux)):
            self._aux[at] = UNUSED

        held = (len(self._init) - 6) // 2

        for at in range(len(self._ram)):
            self._ram[at] = (
                int.from_bytes(self._init[6 + at * 2 : 8 + at * 2], "big")
                if at < held
                else UNUSED
            )

    def _reset(self, first: int, *, clear_undo: bool) -> None:
        """Reinitialize the registers, R00 excepted (Aa-machine: Runtime data)."""

        self._regs = [0] * 64
        self._regs[0] = first
        self._inst = 1
        self._cont = 0
        self._top = 0
        self._env = len(self._heap)
        self._cho = len(self._heap)
        self._sim = 0xFFFF
        self._auxp = 0
        self._trl = len(self._aux)
        self._sta = 0
        self._stc = 0
        self._cwl = 0
        self._spc = _LINE
        self._tmp = 0
        self._divs = []
        self._upper = False
        self._trace = False
        self._in_status = 0
        self._n_span = 0
        self._n_link = 0
        self._dice = (
            self._seed if self._seed is not None else time.time_ns() & 0xFFFFFFFF
        )

        if clear_undo:
            self._undo = []
            self._pruned = False

    def _captured(self, landing: int) -> saves.State:
        """The whole game state, unallocated regions masked unused.

        The landing is the instruction address a restore will
        resume at (Aa-machine: Savefile).
        """

        return (
            (self._nob, self._ltb, self._ltt),
            tuple(
                value if at < self._ltt else UNUSED
                for at, value in enumerate(self._ram)
            ),
            tuple(
                value if at < self._auxp or at >= self._trl else UNUSED
                for at, value in enumerate(self._aux)
            ),
            tuple(
                value
                if at < self._top or at >= self._env or at >= self._cho
                else UNUSED
                for at, value in enumerate(self._heap)
            ),
            tuple(self._regs),
            (landing, self._cont, self._top, self._env, self._cho, self._sim),
            (self._auxp, self._trl, self._sta, self._stc, self._cwl, self._spc),
            tuple(self._divs),
        )

    def _restored(self, state: saves.State) -> None:
        """The whole game state put back from a capture."""

        counted, ram, aux, heap, regs, flow, stacks, divs = state
        self._nob, self._ltb, self._ltt = counted
        self._ram[:] = ram
        self._aux[:] = aux
        self._heap[:] = heap
        self._regs = list(regs)
        self._inst, self._cont, self._top, self._env, self._cho, self._sim = flow
        self._auxp, self._trl, self._sta, self._stc, self._cwl, self._spc = stacks
        self._divs = list(divs)

    def _cleared_divs(self) -> None:
        """Return the output to its initial state, the counters too."""

        self._voice.leave_all()
        self._in_status = 0
        self._n_span = 0
        self._n_link = 0
        self._divs = []

    # -- speaking --------------------------------------------------------

    def _said(self, text: str) -> None:
        """Say text through the voice, an armed UPPERCASE applied."""

        if self._upper and text:
            text = self._upcased.get(text[0], text[0].upper()) + text[1:]
            self._upper = False

        self._voice.say(text)

    def _spaced_auto(self) -> None:
        """The usual gap before printing: auto and pending say space."""

        if self._spc in (_AUTO, _PENDING):
            self._voice.space()

    def _character(self, code: int) -> str:
        """One charset code as text, the extended table ruling."""

        if code < _EXTENDED_START:
            return chr(code)

        return self._story.extended[code - _EXTENDED_START]

    def _encased(self, piece: str) -> int:
        """One input character as its lowercase charset code.

        Unspellable characters become question marks, the
        reference engine's own shrug.
        """

        code = ord(piece)

        if _UPPER_A <= code <= _UPPER_Z:
            return code ^ 0x20

        if code < _EXTENDED_START:
            return code

        return self._cased.get(piece, 0x3F)

    def _valued_text(self, value: int) -> str:  # noqa: PLR0911 -- one seat per value tag
        """A value spelled the way PRINT_VAL spells it (Aa-machine: PRINT_VAL)."""

        if _chared(value):
            return self._character(value & 0xFF)

        if _extdicted(value) or _dicted(value):
            return self._worded_text(value)

        if _paired(value):
            return self._listed_text(value)

        if _referenced(value):
            return "$"

        if _numbered(value):
            return str(value & _NUMBER_TOP)

        if value == EMPTY:
            return "[]"

        return self._object_text(value)

    def _worded_text(self, value: int) -> str:
        """A dict word or extdict spelled out (Aa-machine: PRINT_VAL)."""

        if _dicted(value):
            return self._speech.words[value & 0x1FFF]

        first = self._heap[value & 0x1FFF]

        if (first & 0xE000) in (0x8000, 0xC000):
            return self._tail_text(first)

        return self._worded_text(first) + self._tail_text(
            self._heap[(value & 0x1FFF) + 1]
        )

    def _tail_text(self, listed: int) -> str:
        """A character list spelled out plainly."""

        pieces = []

        while _paired(listed):
            pieces.append(self._valued_text(self._heap[listed & 0x1FFF]))
            listed = self._heap[(listed & 0x1FFF) + 1]

        return "".join(pieces)

    def _listed_text(self, value: int) -> str:
        """A list spelled in brackets, an improper tail barred."""

        pieces = []

        while _paired(value):
            pieces.append(self._valued_text(self._deref(self._heap[value & 0x1FFF])))
            value = self._deref(self._heap[(value & 0x1FFF) + 1])

        told = " ".join(pieces)

        if value != EMPTY:
            told += " | " + self._valued_text(value)

        return "[" + told + "]"

    def _object_text(self, value: int) -> str:
        """An object spelled as its hashmark and TAGS name."""

        told = "#"

        if self._tags is not None:
            payload = self._tags.payload
            at = int.from_bytes(payload[value * 2 : value * 2 + 2], "big")
            ended = payload.find(b"\x00", at)
            told += "".join(self._character(code) for code in payload[at:ended])

        return told

    # -- input parsing ---------------------------------------------------

    def _parsed(self, codes: list[int]) -> int:
        """One input word as a machine value (Aa-machine: GET_INPUT)."""

        if len(codes) > 1:
            seat = self._sought.get(bytes(codes))

            if seat is not None:
                return 0x2000 | seat

        number = 0

        for code in codes:
            if not _digited(code):
                break

            number = number * 10 + code - 0x30

            if number > _NUMBER_TOP:
                break
        else:
            return 0x4000 | number

        if len(codes) == 1:
            return 0x3E00 | codes[0]

        return self._suffixed(codes)

    def _suffixed(self, codes: list[int]) -> int:
        """A word run through the endings decoder (Aa-machine: LANG)."""

        state = self._endings_at
        ending: list[int] = []
        held = len(codes)

        while True:
            told = self._lang[state]
            state += 1

            if told == 0:
                ending.extend(reversed(codes[:held]))

                return self._pair(self._charlist(ending), EMPTY) | 0xE000

            if told == 1:
                seat = self._sought.get(bytes(codes[:held]))

                if seat is not None:
                    return self._pair(0x2000 | seat, self._charlist(ending)) | 0xE000
            else:
                landing = self._lang[state]
                state += 1

                if held > _STEM_KEPT and told == codes[held - 1]:
                    ending.append(told)
                    held -= 1
                    state = self._endings_at + landing

    def _charlist(self, reversed_codes: list[int]) -> int:
        """Reversed charset codes as a list, digits told as numbers."""

        told = EMPTY

        for code in reversed_codes:
            if _digited(code):
                told = self._pair(0x4000 + code - 0x30, told)
            else:
                told = self._pair(0x3E00 | code, told)

        return told

    def _joined_codes(self, listed: int) -> "list[int] | None":
        """A word list as charset codes; None asks the caller to fail.

        (Aa-machine: JOIN_WORDS).
        """

        codes: list[int] = []

        while True:
            value = self._deref(self._heap[listed & 0x1FFF])

            if _extdicted(value):
                first = self._heap[value & 0x1FFF]
                inner = self._joined_codes(first if first >= _UNBOUND_MARK else value)

                if inner is None:
                    return None

                codes.extend(inner)
            elif _numbered(value):
                codes.extend(ord(piece) for piece in str(value & _NUMBER_TOP))
            elif _chared(value):
                code = value & 0xFF

                if code <= _SPACE_CODE or code in self._stops:
                    return None

                codes.append(code)
            elif _dicted(value):
                codes.extend(self._worded_codes(value & 0x1FFF))
            else:
                return None

            listed = self._deref(self._heap[(listed & 0x1FFF) + 1])

            if not _paired(listed):
                break

        if listed != EMPTY:
            return None

        return codes

    def _worded_codes(self, seat: int) -> bytes:
        """One dictionary word's raw charset bytes."""

        length = self._dict[2 + seat * 3]
        at = int.from_bytes(self._dict[3 + seat * 3 : 5 + seat * 3], "big")

        return self._dict[at : at + length]

    def _prepended(self, seat: int, tail: int) -> int:
        """A dictionary word's characters prepended to a list."""

        told = tail

        for code in reversed(self._worded_codes(seat)):
            if _digited(code):
                told = self._pair(0x4000 + code - 0x30, told)
            else:
                told = self._pair(0x3E00 | code, told)

        return told

    # -- the wordmaps ----------------------------------------------------

    def _mapped(self, seat: int) -> bool:
        """Search a wordmap for IDX; True asks for the jump (Aa-machine: MAPS)."""

        table = int.from_bytes(self._maps[2 + seat * 2 : 4 + seat * 2], "big")
        low = 0
        high = int.from_bytes(self._maps[table : table + 2], "big")
        wanted = self._regs[0x3F]

        while low < high:
            mid = (low + high) // 2
            at = table + 2 + mid * 4
            told = int.from_bytes(self._maps[at : at + 2], "big")

            if told == wanted:
                return self._map_told(
                    int.from_bytes(self._maps[at + 2 : at + 4], "big")
                )

            if told > wanted:
                high = mid
            else:
                low = mid + 1

        return True

    def _map_told(self, entry: int) -> bool:
        """Act on one wordmap entry: wildcard, one object, or many."""

        if not entry:
            return False

        if entry & 0xE000:
            self._pushed_aux(entry & 0x1FFF)

            return True

        while code := self._maps[entry]:
            entry += 1

            if code >= _WIDE_SEAT:
                code = ((code & 0x1F) << 8) | self._maps[entry]
                entry += 1

            self._pushed_aux(code)

        return True

    # -- execution flow opcodes ------------------------------------------

    def _op_nop(self, _op: int) -> None:
        """NOP: do nothing (Aa-machine: NOP)."""

    def _op_fail(self, _op: int) -> None:
        """FAIL: fail to the newest choice frame (Aa-machine: FAIL).

        Raises:
            _Missed: Always.
        """

        raise _Missed

    def _op_set_cont(self, _op: int) -> None:
        """SET_CONT: aim the continuation (Aa-machine: SET_CONT)."""

        self._cont = self._target()

    def _op_proceed(self, _op: int) -> None:
        """PROCEED: resume at the continuation, a simple cut landing."""

        if self._sim < _NO_CUT:
            self._cho = self._sim

        self._inst = self._cont

    def _op_jmp(self, _op: int) -> None:
        """JMP: a straightforward jump (Aa-machine: JMP)."""

        self._inst = self._target()

    def _op_jmp_multi(self, op: int) -> None:
        """JMP_MULTI and JMPL_MULTI: a multi-call, SIM invalidated."""

        landing = self._target()

        if op & 0x80:
            self._cont = self._inst

        self._sim = 0xFFFF
        self._inst = landing

    def _op_jmp_simple(self, op: int) -> None:
        """JMP_SIMPLE and JMPL_SIMPLE: a simple call, SIM caught."""

        landing = self._target()

        if op & 0x80:
            self._cont = self._inst

        self._sim = self._cho
        self._inst = landing

    def _op_jmp_tail(self, _op: int) -> None:
        """JMP_TAIL: a tail call, SIM caught if not already (Aa-machine: JMP_TAIL)."""

        if self._sim >= _NO_CUT:
            self._sim = self._cho

        self._inst = self._target()

    def _op_tail(self, _op: int) -> None:
        """TAIL: catch SIM without jumping (Aa-machine: TAIL)."""

        if self._sim >= _NO_CUT:
            self._sim = self._cho

    def _op_push_env(self, op: int) -> None:
        """PUSH_ENV: an environment frame with local slots (Aa-machine: PUSH_ENV)."""

        slots = 0 if op & 0x80 else self._fetched()
        at = min(self._env, self._cho) - 4 - slots

        if at < self._top:
            raise _Fault(HEAP_FULL)

        self._heap[at + 0] = self._env
        self._heap[at + 1] = self._sim
        self._heap[at + 2] = self._cont >> 16
        self._heap[at + 3] = self._cont & 0xFFFF
        self._env = at

    def _op_pop_env(self, _op: int) -> None:
        """POP_ENV: leave the environment frame (Aa-machine: POP_ENV)."""

        self._cont = (self._heap[self._env + 2] << 16) | self._heap[self._env + 3]
        self._sim = self._heap[self._env + 1]
        self._env = self._heap[self._env + 0]

    def _op_pop_env_proceed(self, _op: int) -> None:
        """POP_ENV_PROCEED: leave the frame straight into its continuation."""

        self._inst = (self._heap[self._env + 2] << 16) | self._heap[self._env + 3]

        if self._heap[self._env + 1] < _NO_CUT:
            self._cho = self._heap[self._env + 1]

        self._env = self._heap[self._env + 0]

    def _op_push_choice(self, op: int) -> None:
        """PUSH_CHOICE: a choice frame keeping the first registers."""

        kept = 0 if op & 0x80 else self._fetched()
        self._pushed_choice(kept, self._target())

    def _op_pop_choice(self, op: int) -> None:
        """POP_CHOICE: restore and discard the newest choice frame."""

        kept = 0 if op & 0x80 else self._fetched()
        self._popped_choice(kept)
        self._cho = self._heap[self._cho + 6]

    def _op_pop_push_choice(self, op: int) -> None:
        """POP_PUSH_CHOICE: restore the frame and re-aim its handler."""

        kept = 0 if op & 0x80 else self._fetched()
        landing = self._target()
        self._heap[self._cho + 4] = landing >> 16
        self._heap[self._cho + 5] = landing & 0xFFFF
        self._popped_choice(kept)

    def _op_cut_choice(self, _op: int) -> None:
        """CUT_CHOICE: discard the newest choice frame (Aa-machine: CUT_CHOICE)."""

        self._cho = self._heap[self._cho + 6]

    def _op_get_cho(self, _op: int) -> None:
        """GET_CHO: tell the choice pointer (Aa-machine: GET_CHO)."""

        self._store(self._fetched(), self._cho)

    def _op_set_cho(self, _op: int) -> None:
        """SET_CHO: aim the choice pointer (Aa-machine: SET_CHO)."""

        self._cho = self._value()

    # -- live data opcodes -----------------------------------------------

    def _op_assign(self, op: int) -> None:
        """ASSIGN: store or unify a value (Aa-machine: ASSIGN)."""

        value = self._fetched() if op & 0x80 else self._value()
        self._store(self._fetched(), value)

    def _op_make_var(self, _op: int) -> None:
        """MAKE_VAR: a fresh unbound variable (Aa-machine: MAKE_VAR)."""

        self._store(self._fetched(), self._variable())

    def _op_make_pair(self, op: int) -> None:
        """MAKE_PAIR: build or take apart a pair (Aa-machine: MAKE_PAIR)."""

        if op == _PAIR_OF_DESTS:
            literal = None
            first = self._fetched()
        elif op == _PAIR_OF_WORD:
            literal = self._word()
            first = 0
        else:
            literal = self._fetched()
            first = 0

        second = self._fetched()
        third = self._fetched()

        if third & 0x80:
            self._made_against(literal, first, second, third)
        else:
            at = self._built(literal, first, second)
            self._store(third, 0xC000 | at)

    def _built(self, literal: "int | None", first: int, second: int) -> int:
        """A fresh pair cell filled per MAKE_PAIR's argument shapes."""

        at = self._claimed(2)
        self._filled(literal, first, at)
        self._filled(None, second, at + 1)

        return at

    def _filled(self, literal: "int | None", dest: int, at: int) -> None:
        """One cell word: a literal lands, a destination is served."""

        if literal is not None:
            self._heap[at] = literal
        elif dest & 0x80:
            self._heap[at] = self._slotted(dest)
        else:
            self._heap[at] = 0
            self._store(dest, 0x8000 | at)

    def _made_against(
        self, literal: "int | None", first: int, second: int, third: int
    ) -> None:
        """MAKE_PAIR's unify shape: match an existing value."""

        value = self._deref(self._slotted(third))

        if _paired(value):
            if literal is not None:
                self._unify(literal, 0x8000 | (value & 0x1FFF))
            else:
                self._store(first, 0x8000 | (value & 0x1FFF))

            self._store(second, 0x8000 | ((value & 0x1FFF) + 1))
        elif _referenced(value):
            at = self._built(literal, first, second)
            self._unify(value, 0xC000 | at)
        else:
            raise _Missed

    def _op_aux_push_val(self, _op: int) -> None:
        """AUX_PUSH_VAL: serialize a value onto the aux stack."""

        self._serialized(self._value())

    def _op_aux_push_raw(self, op: int) -> None:
        """AUX_PUSH_RAW: one raw word onto the aux stack (Aa-machine: AUX_PUSH_RAW)."""

        if op == _RAW_ZERO:
            self._pushed_aux(0)
        elif op == _RAW_WORD:
            self._pushed_aux(self._word())
        else:
            self._pushed_aux(self._fetched())

    def _op_aux_pop_val(self, _op: int) -> None:
        """AUX_POP_VAL: deserialize one value, the pre-1.0 opcode carried."""

        self._store(self._fetched(), self._deserialized())

    def _op_aux_pop_list(self, _op: int) -> None:
        """AUX_POP_LIST: deserialize down to the marker as a list."""

        self._store(self._fetched(), self._deserialized_list())

    def _op_aux_pop_list_chk(self, _op: int) -> None:
        """AUX_POP_LIST_CHK: drain the stack, failing unless the key appears."""

        key = self._deref(self._value())
        found = False

        while value := self._popped_aux():
            if value == key:
                found = True

        if not found:
            raise _Missed

    def _op_aux_pop_list_match(self, _op: int) -> None:
        """AUX_POP_LIST_MATCH: every key element must match the stack.

        Each element of the key list must unify with some element
        of the stacked list, or the whole instruction fails.
        """

        kept = self._top
        key = self._deref(self._value())
        listed = self._deserialized_list()

        while _paired(key):
            probe = listed
            matched = False

            while _paired(probe) and not matched:
                if self._agreeable(0x8000 | (probe & 0x1FFF), 0x8000 | (key & 0x1FFF)):
                    matched = True

                probe = self._heap[(probe & 0x1FFF) + 1]

            if not matched:
                raise _Missed

            key = self._heap[(key & 0x1FFF) + 1]

        self._top = kept

    def _op_split_list(self, _op: int) -> None:
        """SPLIT_LIST: copy a list up to a given tail (Aa-machine: SPLIT_LIST)."""

        listed = self._deref(self._value())
        ended = self._deref(self._value())
        dest = self._fetched()

        if listed == ended or not _paired(listed):
            self._store(dest, EMPTY)

            return

        first = current = self._claimed(2)

        while True:
            self._heap[current + 0] = self._heap[listed & 0x1FFF]
            listed = self._deref(self._heap[(listed & 0x1FFF) + 1])

            if listed == ended or not _paired(listed):
                break

            following = self._claimed(2)
            self._heap[current + 1] = 0xC000 | following
            current = following

        self._heap[current + 1] = EMPTY
        self._store(dest, 0xC000 | first)

    def _op_stop(self, _op: int) -> None:
        """STOP: fail out to the stoppable choice point (Aa-machine: STOP).

        Raises:
            _Missed: Always, from the stop frame's choice point.
        """

        self._cho = self._stc

        raise _Missed

    def _op_push_stop(self, _op: int) -> None:
        """PUSH_STOP: a stop frame and its catching choice point."""

        if self._auxp + 2 > self._trl:
            raise _Fault(AUX_FULL)

        self._pushed_aux(self._stc)
        self._pushed_aux(self._sta)
        self._sta = self._auxp
        self._pushed_choice(0, self._target())
        self._stc = self._cho

    def _op_pop_stop(self, _op: int) -> None:
        """POP_STOP: leave the stop frame (Aa-machine: POP_STOP)."""

        self._auxp = self._sta
        self._sta = self._popped_aux()
        self._stc = self._popped_aux()

    def _op_split_word(self, _op: int) -> None:
        """SPLIT_WORD: a word as its list of characters (Aa-machine: SPLIT_WORD)."""

        value = self._deref(self._value())

        if _dicted(value):
            told = self._prepended(value & 0x1FFF, EMPTY)
        elif _chared(value):
            told = self._pair(value, EMPTY)
        elif _numbered(value):
            number = value & _NUMBER_TOP
            told = EMPTY

            while True:
                told = self._pair(0x4000 | (number % 10), told)
                number //= 10

                if not number:
                    break
        elif _extdicted(value):
            first = self._heap[value & 0x1FFF]

            if first >= _UNBOUND_MARK:
                told = first
            else:
                told = self._prepended(first & 0x1FFF, self._heap[(value & 0x1FFF) + 1])
        else:
            raise _Missed

        self._store(self._fetched(), told)

    def _op_join_words(self, _op: int) -> None:
        """JOIN_WORDS: parse a character list back into a word."""

        value = self._deref(self._value())

        if not _paired(value):
            raise _Missed

        first = self._deref(self._heap[value & 0x1FFF])

        if _chared(first):
            tail = self._deref(self._heap[(value & 0x1FFF) + 1])

            if tail == EMPTY:
                self._store(self._fetched(), first)

                return

        codes = self._joined_codes(value)

        if codes is None:
            raise _Missed

        self._store(self._fetched(), self._parsed(codes))

    # -- random access opcodes -------------------------------------------

    def _op_load_word(self, op: int) -> None:
        """LOAD_WORD: read an object's field (Aa-machine: LOAD_WORD)."""

        obj = 0 if op & 0x80 else self._value()
        field = self._index()
        self._store(self._fetched(), self._field(field, obj))

    def _op_load_byte(self, op: int) -> None:
        """LOAD_BYTE: read half an object's field (Aa-machine: LOAD_BYTE)."""

        obj = 0 if op & 0x80 else self._value()
        field = self._index()
        told = self._field(field >> 1, obj)
        self._store(self._fetched(), told & 0xFF if field & 1 else told >> 8)

    def _op_load_val(self, op: int) -> None:
        """LOAD_VAL: read a stored value, long-term data revived."""

        obj = 0 if op & 0x80 else self._value()
        field = self._index()
        told = self._lifted(self._field(field, obj))

        if not told:
            raise _Missed

        self._store(self._fetched(), told)

    def _op_store_word(self, op: int) -> None:
        """STORE_WORD: write an object's field (Aa-machine: STORE_WORD)."""

        obj = 0 if op & 0x80 else self._value()
        field = self._index()
        self._ram[self._field_at(field, obj)] = self._value()

    def _op_store_byte(self, op: int) -> None:
        """STORE_BYTE: write half an object's field (Aa-machine: STORE_BYTE)."""

        obj = 0 if op & 0x80 else self._value()
        field = self._index()
        value = self._value()
        at = self._field_at(field >> 1, obj)

        if field & 1:
            self._ram[at] = (self._ram[at] & 0xFF00) | (value & 0xFF)
        else:
            self._ram[at] = (self._ram[at] & 0x00FF) | ((value & 0xFF) << 8)

    def _op_store_val(self, op: int) -> None:
        """STORE_VAL: keep a value in an object's field.

        Live heap data is serialized into long-term storage so it
        survives the heap's unwinding.
        """

        obj = 0 if op & 0x80 else self._deref(self._value())
        field = self._index()
        value = self._value()

        if obj <= self._nob or value:
            self._kept_longterm(self._field_at(field, obj), value)

    def _op_set_flag(self, op: int) -> None:
        """SET_FLAG: raise one of an object's flags (Aa-machine: SET_FLAG)."""

        obj = 0 if op & 0x80 else self._value()
        flag = self._index()
        at = self._field_at(flag // _BITS_PER_WORD, obj)
        self._ram[at] |= 0x8000 >> (flag % _BITS_PER_WORD)

    def _op_reset_flag(self, op: int) -> None:
        """RESET_FLAG: lower one of an object's flags (Aa-machine: RESET_FLAG)."""

        obj = 0 if op & 0x80 else self._deref(self._value())
        flag = self._index()

        if obj <= self._nob:
            at = self._field_at(flag // _BITS_PER_WORD, obj)
            self._ram[at] &= ~(0x8000 >> (flag % _BITS_PER_WORD)) & 0xFFFF

    def _op_unlink(self, op: int) -> None:
        """UNLINK: remove an object from a linked field chain (Aa-machine: UNLINK)."""

        obj = 0 if op & 0x80 else self._value()
        root = self._index()
        field = self._index()
        self._unlinked(self._field_at(root, obj), field, self._deref(self._value()))

    def _op_set_parent(self, op: int) -> None:
        """SET_PARENT: move an object in the tree (Aa-machine: SET_PARENT)."""

        first = self._fetched() if op & 0x80 else self._deref(self._value())
        second = self._fetched() if op & 0x01 else self._deref(self._value())

        if second and (not _objected(first) or not _objected(second)):
            raise _Fault(EXPECTED_OBJECT)

        if _objected(first):
            parent = self._ram[self._field_at(0, first)]

            if parent:
                self._unlinked(self._field_at(1, parent), 2, first)

            self._ram[self._field_at(0, first)] = second

            if second:
                self._ram[self._field_at(2, first)] = self._ram[
                    self._field_at(1, second)
                ]
                self._ram[self._field_at(1, second)] = first

    # -- conditional branches --------------------------------------------

    def _jumped(self, op: int, told: bool) -> None:
        """Take the CODE operand's jump when the test says to.

        The negated opcodes carry bit 6: IF jumps on true, IFN on
        false (Aa-machine: Opcode semantics).
        """

        landing = self._target()

        if told != bool(op & 0x40):
            self._inst = landing

    def _op_if_raw_eq(self, op: int) -> None:
        """IF_RAW_EQ and IFN_RAW_EQ (Aa-machine: IF_RAW_EQ)."""

        first = 0 if op & 0x80 else self._word()
        self._jumped(op, first == self._value())

    def _op_if_bound(self, op: int) -> None:
        """IF_BOUND and IFN_BOUND (Aa-machine: IF_BOUND)."""

        self._jumped(op, not _referenced(self._deref(self._value())))

    def _op_if_empty(self, op: int) -> None:
        """IF_EMPTY and IFN_EMPTY (Aa-machine: IF_EMPTY)."""

        self._jumped(op, self._deref(self._value()) == EMPTY)

    def _op_if_num(self, op: int) -> None:
        """IF_NUM and IFN_NUM (Aa-machine: IF_NUM)."""

        told = self._deref(self._value())
        self._jumped(op, _numbered(told))

    def _op_if_pair(self, op: int) -> None:
        """IF_PAIR and IFN_PAIR (Aa-machine: IF_PAIR)."""

        self._jumped(op, _paired(self._deref(self._value())))

    def _op_if_obj(self, op: int) -> None:
        """IF_OBJ and IFN_OBJ (Aa-machine: IF_OBJ)."""

        self._jumped(op, _objected(self._deref(self._value())))

    def _op_if_word(self, op: int) -> None:
        """IF_WORD and IFN_WORD (Aa-machine: IF_WORD)."""

        told = self._deref(self._value())
        wordish = _wordish(told)
        self._jumped(op, wordish)

    def _op_if_uword(self, op: int) -> None:
        """IF_UWORD and IFN_UWORD: an unrecognized dictionary word."""

        told = self._deref(self._value())
        unknown = _extdicted(told) and _paired(self._heap[told & 0x1FFF])
        self._jumped(op, unknown)

    def _op_if_unify(self, op: int) -> None:
        """IF_UNIFY and IFN_UNIFY (Aa-machine: IF_UNIFY)."""

        first = self._value()
        self._jumped(op, self._agreeable(first, self._value()))

    def _op_if_gt(self, op: int) -> None:
        """IF_GT and IFN_GT (Aa-machine: IF_GT)."""

        first = self._deref(self._value())
        second = self._deref(self._value())
        told = _numbered(first) and _numbered(second) and first > second
        self._jumped(op, told)

    def _op_if_eq(self, op: int) -> None:
        """IF_EQ and IFN_EQ (Aa-machine: IF_EQ)."""

        first = self._fetched() if op & 0x80 else self._word()
        self._jumped(op, first == self._deref(self._value()))

    def _op_if_mem_eq(self, op: int) -> None:
        """IF_MEM_EQ and IFN_MEM_EQ, the RAW-shaped pair (Aa-machine: IF_MEM_EQ)."""

        obj = 0 if op & 0x80 else self._value()
        field = self._index()
        self._jumped(op, self._field(field, obj) == self._value())

    def _op_if_mem_eq_byte(self, op: int) -> None:
        """IF_MEM_EQ and IFN_MEM_EQ, the VBYTE-shaped pair (Aa-machine: IF_MEM_EQ)."""

        obj = 0 if op & 0x80 else self._value()
        field = self._index()
        self._jumped(op, self._field(field, obj) == self._fetched())

    def _op_if_flag(self, op: int) -> None:
        """IF_FLAG and IFN_FLAG (Aa-machine: IF_FLAG)."""

        obj = 0 if op & 0x80 else self._value()
        flag = self._index()
        told = self._field(flag // _BITS_PER_WORD, obj)
        mask = 0x8000 >> (flag % _BITS_PER_WORD)
        self._jumped(op, bool(told & mask))

    def _op_if_cwl(self, op: int) -> None:
        """IF_CWL and IFN_CWL (Aa-machine: IF_CWL)."""

        self._jumped(op, self._cwl != 0)

    # -- arithmetic ------------------------------------------------------

    def _op_add_raw(self, _op: int) -> None:
        """ADD_RAW (Aa-machine: ADD_RAW)."""

        first = self._value()
        second = self._value()
        self._store(self._fetched(), (first + second) & 0xFFFF)

    def _op_sub_raw(self, _op: int) -> None:
        """SUB_RAW (Aa-machine: SUB_RAW)."""

        first = self._value()
        second = self._value()
        self._store(self._fetched(), (first - second) & 0xFFFF)

    def _op_inc_raw(self, _op: int) -> None:
        """INC_RAW (Aa-machine: INC_RAW)."""

        told = self._value()
        self._store(self._fetched(), (told + 1) & 0xFFFF)

    def _op_dec_raw(self, _op: int) -> None:
        """DEC_RAW (Aa-machine: DEC_RAW)."""

        told = self._value()
        self._store(self._fetched(), (told - 1) & 0xFFFF)

    def _op_rand_raw(self, _op: int) -> None:
        """RAND_RAW: a raw roll up to the byte told (Aa-machine: RAND_RAW)."""

        ceiling = self._fetched()
        self._store(self._fetched(), self._rolled() % (ceiling + 1))

    def _op_add_num(self, _op: int) -> None:
        """ADD_NUM (Aa-machine: ADD_NUM)."""

        first = self._unboxed(self._value())
        second = self._unboxed(self._value())
        self._store(self._fetched(), self._boxed(first + second))

    def _op_sub_num(self, _op: int) -> None:
        """SUB_NUM (Aa-machine: SUB_NUM)."""

        first = self._unboxed(self._value())
        second = self._unboxed(self._value())
        self._store(self._fetched(), self._boxed(first - second))

    def _op_mul_num(self, _op: int) -> None:
        """MUL_NUM: the product kept to fourteen bits (Aa-machine: MUL_NUM)."""

        first = self._unboxed(self._value())
        second = self._unboxed(self._value())
        self._store(self._fetched(), self._boxed((first * second) & _NUMBER_TOP))

    def _op_div_num(self, _op: int) -> None:
        """DIV_NUM: division by zero fails (Aa-machine: DIV_NUM)."""

        first = self._unboxed(self._value())
        second = self._unboxed(self._value())

        if not second:
            raise _Missed

        self._store(self._fetched(), self._boxed(first // second))

    def _op_mod_num(self, _op: int) -> None:
        """MOD_NUM: the remainder, division by zero failing (Aa-machine: MOD_NUM)."""

        first = self._unboxed(self._value())
        second = self._unboxed(self._value())

        if not second:
            raise _Missed

        self._store(self._fetched(), self._boxed(first % second))

    def _op_rand_num(self, _op: int) -> None:
        """RAND_NUM: a roll within an inclusive range (Aa-machine: RAND_NUM)."""

        start = self._unboxed(self._value())
        span = self._unboxed(self._value()) - start + 1

        if span < 1:
            raise _Missed

        self._store(self._fetched(), self._boxed(start + self._rolled() % span))

    def _op_inc_num(self, _op: int) -> None:
        """INC_NUM (Aa-machine: INC_NUM)."""

        told = self._unboxed(self._value())
        self._store(self._fetched(), self._boxed(told + 1))

    def _op_dec_num(self, _op: int) -> None:
        """DEC_NUM (Aa-machine: DEC_NUM)."""

        told = self._unboxed(self._value())
        self._store(self._fetched(), self._boxed(told - 1))

    # -- output ----------------------------------------------------------

    def _op_print_str(self, op: int) -> None:
        """The four PRINT_*_STR_* opcodes (Aa-machine: PRINT_A_STR_A).

        A WRIT string lands with its whitespace discipline: the A
        and N halves of the name say whether a space may lead and
        whether one may follow.
        """

        address = self._string()

        if self._spc == _PENDING or (self._spc == _AUTO and not op & 0x80):
            self._voice.space()
        elif self._spc == _NBSP:
            self._voice.nbsp()

        self._said(self._speech.spelled(address))
        self._spc = _NOSPACE if op & 0x01 else _AUTO

    def _op_nospace(self, _op: int) -> None:
        """NOSPACE (Aa-machine: NOSPACE)."""

        if not self._cwl:
            self._spc = max(self._spc, _NOSPACE)

    def _op_space(self, _op: int) -> None:
        """SPACE (Aa-machine: SPACE)."""

        if not self._cwl:
            self._spc = max(self._spc, _PENDING)

    def _op_line(self, _op: int) -> None:
        """LINE (Aa-machine: LINE)."""

        if not self._cwl and self._spc < _LINE:
            self._voice.line()
            self._spc = _LINE

    def _op_par(self, _op: int) -> None:
        """PAR (Aa-machine: PAR)."""

        if not self._cwl and self._spc < _PAR:
            self._voice.par()
            self._spc = _PAR

    def _op_space_n(self, _op: int) -> None:
        """SPACE_N: a counted run of spaces (Aa-machine: SPACE_N)."""

        value = self._deref(self._value())

        if not self._cwl and _numbered(value):
            self._voice.spaces(value & _NUMBER_TOP)
            self._spc = _SPACE

    def _op_print_val(self, _op: int) -> None:
        """PRINT_VAL: spell a value out (Aa-machine: PRINT_VAL).

        While words are being collected, the value is serialized
        onto the aux stack instead of spoken.
        """

        value = self._deref(self._value())

        if self._cwl:
            self._serialized(value)
        elif _chared(value):
            self._printed_char(value & 0xFF)
        else:
            self._spaced_auto()

            if not (_dicted(value) or _extdicted(value)):
                self._upper = False

            self._said(self._valued_text(value))
            self._spc = _AUTO

    def _printed_char(self, code: int) -> None:
        """One character with the LANG chunk's spacing manners."""

        if self._spc == _PENDING or (
            self._spc == _AUTO and code not in self._unspaced_before
        ):
            self._voice.space()

        self._said(self._character(code))
        self._spc = _NOSPACE if code in self._unspaced_after else _AUTO

    def _op_enter_div(self, _op: int) -> None:
        """ENTER_DIV (Aa-machine: ENTER_DIV)."""

        style = self._index()

        if not self._cwl:
            if self._n_span:
                raise _Fault(BAD_OUTPUT_STATE)

            self._voice.enter_div(style)
            self._divs.append(style)
            self._spc = _PAR

    def _op_leave_div(self, _op: int) -> None:
        """LEAVE_DIV (Aa-machine: LEAVE_DIV)."""

        if not self._cwl:
            self._voice.leave_div(self._divs.pop())
            self._spc = _LINE

    def _op_enter_span(self, _op: int) -> None:
        """ENTER_SPAN (Aa-machine: ENTER_SPAN)."""

        style = self._index()

        if not self._cwl:
            self._spaced_auto()
            self._voice.enter_span(style)
            self._spc = _NOSPACE
            self._n_span += 1

    def _op_leave_span(self, _op: int) -> None:
        """LEAVE_SPAN (Aa-machine: LEAVE_SPAN)."""

        if not self._cwl:
            self._voice.leave_span()
            self._spc = _AUTO
            self._n_span -= 1

    def _op_status_or_body(self, _op: int) -> None:
        """Opcode $67: ENTER_STATUS before 1.0, SET_BODY from it.

        (Aa-machine: ENTER_STATUS; SET_BODY).
        """

        if self._major < 1:
            self._entered_status(0, self._index())
        else:
            style = self._index()

            if self._in_status or self._n_span:
                raise _Fault(BAD_OUTPUT_STATE)

            self._voice.set_body(style)

    def _op_enter_status(self, _op: int) -> None:
        """ENTER_STATUS, the 0.5 shape with its area byte (Aa-machine: ENTER_STATUS)."""

        area = self._fetched()
        self._entered_status(area, self._index())

    def _entered_status(self, area: int, style: int) -> None:
        """Enter a status area, the illegal states loud."""

        if self._in_status or self._n_span:
            raise _Fault(BAD_OUTPUT_STATE)

        if not self._cwl:
            self._voice.enter_status(area, style)
            self._in_status = area + 1
            self._spc = _PAR

    def _op_leave_status(self, op: int) -> None:
        """LEAVE_STATUS, at either of its two historical seats."""

        if (op == _OLD_LEAVE_STATUS) == (self._major >= 1):
            msg = (
                f"opcode {op:#04x} is not LEAVE_STATUS in a format "
                f"{self._major}.x story (Aa-machine: LEAVE_STATUS)"
            )

            raise AAMachineError(msg)

        if not self._cwl:
            self._voice.leave_status()
            self._in_status = 0
            self._spc = _PAR

    def _op_enter_link_res(self, _op: int) -> None:
        """ENTER_LINK_RES (Aa-machine: ENTER_LINK_RES)."""

        resource = self._deref(self._value())

        if not self._cwl:
            if not self._n_link:
                self._spaced_auto()
                self._voice.enter_link_res(resource)
                self._spc = _NOSPACE

            self._n_link += 1
            self._n_span += 1

    def _op_leave_link_res(self, _op: int) -> None:
        """LEAVE_LINK_RES (Aa-machine: LEAVE_LINK_RES)."""

        if not self._cwl:
            self._n_link -= 1
            self._n_span -= 1

            if not self._n_link:
                self._voice.leave_link_res()

    def _op_enter_link(self, _op: int) -> None:
        """ENTER_LINK: a link whose click types its word list."""

        listed = self._deref(self._value())

        if not self._cwl:
            if not self._n_link:
                self._spaced_auto()
                held, self._upper = self._upper, False
                pieces = []

                while _paired(listed):
                    value = self._deref(self._heap[listed & 0x1FFF])

                    if _linkable(value):
                        pieces.append(self._valued_text(value))

                    listed = self._deref(self._heap[(listed & 0x1FFF) + 1])

                self._voice.enter_link(" ".join(pieces))
                self._upper = held
                self._spc = _NOSPACE

            self._n_link += 1
            self._n_span += 1

    def _op_leave_link(self, _op: int) -> None:
        """LEAVE_LINK (Aa-machine: LEAVE_LINK)."""

        if not self._cwl:
            self._n_link -= 1
            self._n_span -= 1

            if not self._n_link:
                self._voice.leave_link()

    def _op_enter_self_link(self, _op: int) -> None:
        """ENTER_SELF_LINK (Aa-machine: ENTER_SELF_LINK)."""

        if not self._cwl:
            if not self._n_link:
                self._spaced_auto()
                self._voice.enter_self_link()
                self._spc = _SPACE

            self._n_link += 1
            self._n_span += 1

    def _op_leave_self_link(self, _op: int) -> None:
        """LEAVE_SELF_LINK (Aa-machine: LEAVE_SELF_LINK)."""

        if not self._cwl:
            self._n_link -= 1
            self._n_span -= 1

            if not self._n_link:
                self._voice.leave_self_link()

    def _op_set_style(self, op: int) -> None:
        """SET_STYLE and RESET_STYLE, deprecated but carried (Aa-machine: SET_STYLE)."""

        bits = self._fetched()

        if not self._cwl:
            if op & 0x80:
                self._voice.reset_style(bits)
            else:
                self._spaced_auto()
                self._voice.set_style(bits)
                self._spc = _SPACE

    def _op_embed_res(self, _op: int) -> None:
        """EMBED_RES (Aa-machine: EMBED_RES).

        The operand arrives tagged, as every value does; the voice
        is handed the URLS index it carries, counted from zero the
        way the reference engine counts it.
        """

        resource = self._deref(self._value()) & _VALUE_MASK

        if not self._cwl:
            self._voice.embed_res(resource)

    def _op_can_embed_res(self, _op: int) -> None:
        """CAN_EMBED_RES (Aa-machine: CAN_EMBED_RES)."""

        resource = self._deref(self._value()) & _VALUE_MASK
        told = 1 if self._voice.can_embed_res(resource) else 0
        self._store(self._fetched(), told)

    def _op_progress(self, _op: int) -> None:
        """PROGRESS (Aa-machine: PROGRESS)."""

        amount = self._deref(self._value())
        total = self._deref(self._value())

        if not self._cwl and _numbered(amount) and _numbered(total):
            self._voice.progress(amount & _NUMBER_TOP, total & _NUMBER_TOP)

    # -- system control --------------------------------------------------

    def _op_ext0(self, _op: int) -> "str | None":
        """EXT0: the single-byte system operations (Aa-machine: Opcode semantics)."""

        selector = self._fetched()
        handler = _EXTS.get(selector)

        if handler is None:
            msg = (
                f"reached EXT0 {selector:#04x} at ${self._inst - 2:06x}, "
                f"which this engine does not carry (Aa-machine: Story file)"
            )

            raise AAMachineError(msg)

        return handler(self)

    def _ext_quit(self) -> str:
        """QUIT (Aa-machine: QUIT)."""

        self._voice.sync()
        self.running = False

        return "quit"

    def _ext_restart(self) -> None:
        """RESTART: the whole game state reborn (Aa-machine: RESTART)."""

        self.discontinuity = True

        self._cleared_divs()
        self._reset(0, clear_undo=True)
        self._restored(self._held)
        self._voice.reset()

    def _ext_restore(self) -> None:
        """RESTORE: revive a kept savefile (Aa-machine: RESTORE).

        A voice with no file, or a file that does not belong to
        this story, is a failed restore: execution simply
        continues, the spec's own shape. A revived state resumes
        at the address its SAVE named, the output returned to its
        base and the saved divs re-entered.
        """

        if not self._voice.has_saves:
            return

        told = self._voice.restore()

        if told is None:
            return

        try:
            state = saves.revived(self._story, told)
        except VoxamError:
            return

        self.discontinuity = True

        self._restored(state)
        self._voice.leave_all()
        self._in_status = 0
        self._n_span = 0
        self._n_link = 0

        for style in self._divs:
            self._voice.enter_div(style)

    def _ext_undo(self) -> None:
        """UNDO: step back to the last kept moment (Aa-machine: UNDO)."""

        if self._undo:
            self.discontinuity = True

            self._cleared_divs()
            self._restored(self._undo.pop())
        elif not self._pruned:
            raise _Missed

    def _ext_unstyle(self) -> None:
        """UNSTYLE (Aa-machine: UNSTYLE)."""

        if not self._cwl:
            self._voice.unstyle()

    def _ext_print_serial(self) -> None:
        """PRINT_SERIAL (Aa-machine: PRINT_SERIAL)."""

        if not self._cwl:
            self._spaced_auto()
            self._voice.say(self._story.serial)
            self._spc = _AUTO

    def _ext_clear(self) -> None:
        """CLEAR and CLEAR_ALL share the div-restating dance (Aa-machine: CLEAR)."""

        self._cleared(self._voice.clear)

    def _ext_clear_all(self) -> None:
        """CLEAR_ALL (Aa-machine: CLEAR_ALL)."""

        self._cleared(self._voice.clear_all)

    def _cleared(self, call: Callable[[], None]) -> None:
        """Clear through the voice, the open divs re-entered."""

        if not self._cwl:
            if self._in_status or self._n_span:
                raise _Fault(BAD_OUTPUT_STATE)

            kept = self._divs
            self._cleared_divs()
            call()

            for style in kept:
                self._voice.enter_div(style)

            self._divs = kept

    def _ext_script_on(self) -> None:
        """SCRIPT_ON: failure reports the transcript refused (Aa-machine: SCRIPT_ON)."""

        if not self._voice.script_on():
            raise _Missed

    def _ext_script_off(self) -> None:
        """SCRIPT_OFF (Aa-machine: SCRIPT_OFF)."""

        self._voice.script_off()

    def _ext_trace_on(self) -> None:
        """TRACE_ON (Aa-machine: TRACE_ON)."""

        self._trace = True

    def _ext_trace_off(self) -> None:
        """TRACE_OFF (Aa-machine: TRACE_OFF)."""

        self._trace = False

    def _ext_inc_cwl(self) -> None:
        """INC_CWL (Aa-machine: INC_CWL)."""

        self._cwl += 1

    def _ext_dec_cwl(self) -> None:
        """DEC_CWL (Aa-machine: DEC_CWL)."""

        self._cwl -= 1

    def _ext_uppercase(self) -> None:
        """UPPERCASE: arm the next character (Aa-machine: UPPERCASE)."""

        if not self._cwl:
            self._upper = True

    def _ext_clear_links(self) -> None:
        """CLEAR_LINKS (Aa-machine: CLEAR_LINKS)."""

        self._voice.clear_links()

    def _ext_clear_old(self) -> None:
        """CLEAR_OLD (Aa-machine: CLEAR_OLD)."""

        if self._n_span:
            raise _Fault(BAD_OUTPUT_STATE)

        self._voice.clear_old()

    def _ext_clear_div(self) -> None:
        """CLEAR_DIV (Aa-machine: CLEAR_DIV)."""

        self._voice.clear_div()

    def _ext_clear_status(self) -> None:
        """CLEAR_STATUS (Aa-machine: CLEAR_STATUS)."""

        if self._in_status:
            raise _Fault(BAD_OUTPUT_STATE)

        self._voice.clear_status()

    def _ext_nbsp(self) -> None:
        """NBSP (Aa-machine: NBSP)."""

        if not self._cwl:
            self._spc = max(self._spc, _NBSP)

    def _op_save(self, _op: int) -> None:
        """SAVE: keep the whole state through the voice (Aa-machine: SAVE).

        A voice that keeps no files, or one whose keeping is
        refused or cancelled, fails the instruction; success
        continues past it, and a later restore lands at the CODE
        operand (Aa-machine: Savefile).

        Raises:
            _Fault: For a save from inside a span or status area.
            _Missed: When no savefile is kept.
        """

        landing = self._target()

        if self._in_status or self._n_span:
            raise _Fault(BAD_OUTPUT_STATE)

        if not self._voice.has_saves:
            raise _Missed

        told = saves.kept(self._story, self._captured(landing))

        if not self._voice.save(told):
            raise _Missed

    def _op_save_undo(self, _op: int) -> None:
        """SAVE_UNDO: keep this moment in memory (Aa-machine: SAVE_UNDO)."""

        landing = self._target()

        if self._in_status or self._n_span:
            raise _Fault(BAD_OUTPUT_STATE)

        if len(self._undo) > _UNDO_KEPT:
            self._undo.pop(0)
            self._pruned = True

        self._undo.append(self._captured(landing))

    def _op_get_input(self, _op: int) -> str:
        """GET_INPUT: wait for the player's line (Aa-machine: GET_INPUT)."""

        self._spaced_input()

        return "line"

    def _op_get_key(self, _op: int) -> str:
        """GET_KEY: wait for one keypress (Aa-machine: GET_KEY)."""

        self._spaced_input()

        return "key"

    def _spaced_input(self) -> None:
        """Settle the whitespace and the display before a wait."""

        if self._spc in (_AUTO, _PENDING):
            self._voice.space()
        elif self._spc == _NBSP:
            self._voice.nbsp()

        self._voice.sync()

    def _op_vm_info(self, _op: int) -> None:
        """VM_INFO: the interpreter examined (Aa-machine: VM_INFO)."""

        selector = self._fetched()

        if selector > _SELECTOR_TOP:
            msg = f"VM_INFO selector {selector:#04x} is undefined (Aa-machine: VM_INFO)"

            raise AAMachineError(msg)

        if selector & 0x40:
            told = 1 if self._featured(selector & 0x3F) else 0
        elif selector & 0x20:
            told = 0x4000 | self._voice.measured(selector & 0x1F)
        elif selector < _PEAK_AREAS:
            areas = (self._heap, self._aux, self._ram[self._ltb :])
            told = 0x4000 + sum(1 for value in areas[selector] if value != UNUSED)
        else:
            told = 0x4000

        self._store(self._fetched(), told)

    def _featured(self, feature: int) -> bool:
        """One interpreter-feature answer (Aa-machine: VM_INFO)."""

        told = {
            0x00: True,
            0x01: self._voice.has_saves,
            0x02: self._voice.has_links,
            0x03: True,
            0x04: self._voice.has_styles,
            0x05: self._voice.has_color,
            0x06: self._voice.has_alignment,
            0x10: self._voice.script_active(),
            0x20: self._voice.has_top_status,
            0x21: self._voice.has_inline_status,
        }

        return told.get(feature, False)

    def _op_set_idx(self, _op: int) -> None:
        """SET_IDX: load the index register (Aa-machine: SET_IDX)."""

        value = self._deref(self._value())

        if _extdicted(value):
            value = self._heap[value & 0x1FFF]

        self._regs[0x3F] = value

    def _op_check_eq(self, op: int) -> None:
        """CHECK_EQ: jump when IDX matches (Aa-machine: CHECK_EQ)."""

        first = self._fetched() if op & 0x80 else self._word()
        landing = self._target()

        if self._regs[0x3F] == first:
            self._inst = landing

    def _op_check_gt_eq(self, op: int) -> None:
        """CHECK_GT_EQ: a two-way split on IDX (Aa-machine: CHECK_GT_EQ)."""

        first = self._fetched() if op & 0x80 else self._word()
        above = self._target()
        equal = self._target()

        if self._regs[0x3F] > first:
            self._inst = above
        elif self._regs[0x3F] == first:
            self._inst = equal

    def _op_check_gt(self, op: int) -> None:
        """CHECK_GT: jump when IDX exceeds (Aa-machine: CHECK_GT)."""

        first = self._fetched() if op & 0x80 else self._value()
        landing = self._target()

        if self._regs[0x3F] > first:
            self._inst = landing

    def _op_check_wordmap(self, _op: int) -> None:
        """CHECK_WORDMAP: consult a word-to-object map (Aa-machine: CHECK_WORDMAP)."""

        seat = self._index()
        landing = self._target()

        if self._mapped(seat):
            self._inst = landing

    def _op_check_eq_2(self, op: int) -> None:
        """CHECK_EQ_2: jump when IDX matches either (Aa-machine: CHECK_EQ_2)."""

        if op & 0x80:
            first, second = self._fetched(), self._fetched()
        else:
            first, second = self._word(), self._word()

        landing = self._target()

        if self._regs[0x3F] in (first, second):
            self._inst = landing

    def _op_tracepoint(self, _op: int) -> None:
        """TRACEPOINT: a debug mark, told only while tracing."""

        event = self._string()
        shape = self._string()
        source = self._string()
        line = self._word()

        if self._trace:
            pieces = []
            seat = 0

            for piece in self._speech.spelled(shape):
                if piece == "$":
                    pieces.append(self._valued_text(self._deref(self._regs[seat])))
                    seat += 1
                else:
                    pieces.append(piece)

            self._voice.trace(
                f"{self._speech.spelled(event)}({''.join(pieces)}) "
                f"{self._speech.spelled(source)}:{line}"
            )


def walked(story: Story, script: str, seed: int | None = None) -> str:
    """Play a story through a plain voice; the whole telling comes back.

    The drill is the reference Node frontend's own: each script
    line is echoed raw into the telling with the line ending it
    arrived with, a line wait takes the line whole, a key wait
    takes it a keypress at a time with a return to finish, and
    the telling closes on a broken line -- which is what makes
    the result diff clean against the reference engine's
    transcripts.
    """

    voice = PlainVoice(story)
    machine = Machine(story, voice, seed=seed)
    feed = iter(script.splitlines(keepends=True))
    waiting = machine.run()

    while waiting != "quit":
        told = next(feed, None)

        if told is None:
            break

        line = told.rstrip("\r\n")
        voice.echoed(line + ("\n" if told != line else ""))

        if waiting == "line":
            voice.prompted()
            waiting = machine.deliver_line(line)
        else:
            at = 0

            while waiting == "key" and at < len(line):
                waiting = machine.deliver_key(ord(line[at]))
                at += 1

            if waiting == "key":
                waiting = machine.deliver_key(0x0D)

    voice.line()

    return voice.told()


def _cased(lang: bytes, extended: tuple[str, ...]) -> dict[str, int]:
    """Each extended character to its lowercase charset code (Aa-machine: LANG)."""

    at = int.from_bytes(lang[2:4], "big")

    return {extended[seat]: lang[at + 1 + seat * 5] for seat in range(lang[at])}


def _upcased(lang: bytes, extended: tuple[str, ...]) -> dict[str, str]:
    """Each extended character to its uppercase self (Aa-machine: LANG)."""

    at = int.from_bytes(lang[2:4], "big")
    told = {}

    for seat in range(lang[at]):
        upper = lang[at + 1 + seat * 5 + 1]
        told[extended[seat]] = (
            chr(upper) if upper < _EXTENDED_START else extended[upper & 0x7F]
        )

    return told


def _stopped(
    lang: bytes, version: tuple[int, int]
) -> tuple[frozenset[int], frozenset[int], frozenset[int]]:
    """The special characters: stops and the whitespace inhibitors (Aa-machine: LANG).

    Raises:
        AAMachineError: For a set running past the chunk.
    """

    at = int.from_bytes(lang[6:8], "big")
    sets: list[frozenset[int]] = []
    wanted = 3 if version >= (0, 4) else 1

    for _ in range(wanted):
        ended = lang.find(b"\x00", at)

        if ended < 0:
            msg = (
                "a LANG special-character set is missing its null "
                "ending (Aa-machine: LANG)"
            )

            raise AAMachineError(msg)

        sets.append(frozenset(lang[at:ended]))
        at = ended + 1

    while len(sets) < _SPECIAL_SETS:
        sets.append(frozenset())

    return sets[0], sets[1], sets[2]


def _sought(dictionary: bytes) -> dict[bytes, int]:
    """Each dictionary word's raw bytes to its seat (Aa-machine: DICT)."""

    count = int.from_bytes(dictionary[0:2], "big")
    told = {}

    for seat in range(count):
        length = dictionary[2 + seat * 3]
        at = int.from_bytes(dictionary[3 + seat * 3 : 5 + seat * 3], "big")
        told[dictionary[at : at + length]] = seat

    return told


# The dispatch table: every opcode byte to its handler
# (Aa-machine: Story file).
_OPS: dict[int, Callable[[Machine, int], "str | None"]] = {
    0x00: Machine._op_nop,
    0x01: Machine._op_fail,
    0x02: Machine._op_set_cont,
    0x03: Machine._op_proceed,
    0x04: Machine._op_jmp,
    0x05: Machine._op_jmp_multi,
    0x85: Machine._op_jmp_multi,
    0x06: Machine._op_jmp_simple,
    0x86: Machine._op_jmp_simple,
    0x07: Machine._op_jmp_tail,
    0x87: Machine._op_tail,
    0x08: Machine._op_push_env,
    0x88: Machine._op_push_env,
    0x09: Machine._op_pop_env,
    0x89: Machine._op_pop_env_proceed,
    0x0A: Machine._op_push_choice,
    0x8A: Machine._op_push_choice,
    0x0B: Machine._op_pop_choice,
    0x8B: Machine._op_pop_choice,
    0x0C: Machine._op_pop_push_choice,
    0x8C: Machine._op_pop_push_choice,
    0x0D: Machine._op_cut_choice,
    0x0E: Machine._op_get_cho,
    0x0F: Machine._op_set_cho,
    0x10: Machine._op_assign,
    0x90: Machine._op_assign,
    0x11: Machine._op_make_var,
    0x12: Machine._op_make_pair,
    0x13: Machine._op_make_pair,
    0x93: Machine._op_make_pair,
    0x14: Machine._op_aux_push_val,
    0x94: Machine._op_aux_push_raw,
    0x15: Machine._op_aux_push_raw,
    0x95: Machine._op_aux_push_raw,
    0x16: Machine._op_aux_pop_val,
    0x17: Machine._op_aux_pop_list,
    0x18: Machine._op_aux_pop_list_chk,
    0x19: Machine._op_aux_pop_list_match,
    0x1B: Machine._op_split_list,
    0x1C: Machine._op_stop,
    0x1D: Machine._op_push_stop,
    0x1E: Machine._op_pop_stop,
    0x1F: Machine._op_split_word,
    0x9F: Machine._op_join_words,
    0x20: Machine._op_load_word,
    0xA0: Machine._op_load_word,
    0x21: Machine._op_load_byte,
    0xA1: Machine._op_load_byte,
    0x22: Machine._op_load_val,
    0xA2: Machine._op_load_val,
    0x24: Machine._op_store_word,
    0xA4: Machine._op_store_word,
    0x25: Machine._op_store_byte,
    0xA5: Machine._op_store_byte,
    0x26: Machine._op_store_val,
    0xA6: Machine._op_store_val,
    0x28: Machine._op_set_flag,
    0xA8: Machine._op_set_flag,
    0x29: Machine._op_reset_flag,
    0xA9: Machine._op_reset_flag,
    0x2D: Machine._op_unlink,
    0xAD: Machine._op_unlink,
    0x2E: Machine._op_set_parent,
    0xAE: Machine._op_set_parent,
    0x2F: Machine._op_set_parent,
    0xAF: Machine._op_set_parent,
    0x30: Machine._op_if_raw_eq,
    0xB0: Machine._op_if_raw_eq,
    0x40: Machine._op_if_raw_eq,
    0xC0: Machine._op_if_raw_eq,
    0x31: Machine._op_if_bound,
    0x41: Machine._op_if_bound,
    0x32: Machine._op_if_empty,
    0x42: Machine._op_if_empty,
    0x33: Machine._op_if_num,
    0x43: Machine._op_if_num,
    0x34: Machine._op_if_pair,
    0x44: Machine._op_if_pair,
    0x35: Machine._op_if_obj,
    0x45: Machine._op_if_obj,
    0x36: Machine._op_if_word,
    0x46: Machine._op_if_word,
    0xB6: Machine._op_if_uword,
    0xC6: Machine._op_if_uword,
    0x37: Machine._op_if_unify,
    0x47: Machine._op_if_unify,
    0x38: Machine._op_if_gt,
    0x48: Machine._op_if_gt,
    0x39: Machine._op_if_eq,
    0xB9: Machine._op_if_eq,
    0x49: Machine._op_if_eq,
    0xC9: Machine._op_if_eq,
    0x3A: Machine._op_if_mem_eq,
    0xBA: Machine._op_if_mem_eq,
    0x4A: Machine._op_if_mem_eq,
    0xCA: Machine._op_if_mem_eq,
    0x3B: Machine._op_if_flag,
    0xBB: Machine._op_if_flag,
    0x4B: Machine._op_if_flag,
    0xCB: Machine._op_if_flag,
    0x3C: Machine._op_if_cwl,
    0x4C: Machine._op_if_cwl,
    0x3D: Machine._op_if_mem_eq_byte,
    0xBD: Machine._op_if_mem_eq_byte,
    0x4D: Machine._op_if_mem_eq_byte,
    0xCD: Machine._op_if_mem_eq_byte,
    0x50: Machine._op_add_raw,
    0xD0: Machine._op_inc_raw,
    0x51: Machine._op_sub_raw,
    0xD1: Machine._op_dec_raw,
    0x52: Machine._op_rand_raw,
    0x58: Machine._op_add_num,
    0xD8: Machine._op_inc_num,
    0x59: Machine._op_sub_num,
    0xD9: Machine._op_dec_num,
    0x5A: Machine._op_rand_num,
    0x5B: Machine._op_mul_num,
    0x5C: Machine._op_div_num,
    0x5D: Machine._op_mod_num,
    0x60: Machine._op_print_str,
    0xE0: Machine._op_print_str,
    0x61: Machine._op_print_str,
    0xE1: Machine._op_print_str,
    0x62: Machine._op_nospace,
    0xE2: Machine._op_space,
    0x63: Machine._op_line,
    0xE3: Machine._op_par,
    0x64: Machine._op_space_n,
    0x65: Machine._op_print_val,
    0x66: Machine._op_enter_div,
    0xE6: Machine._op_leave_div,
    0x67: Machine._op_status_or_body,
    0xE7: Machine._op_leave_status,
    0x68: Machine._op_enter_link_res,
    0xE8: Machine._op_leave_link_res,
    0x69: Machine._op_enter_link,
    0xE9: Machine._op_leave_link,
    0x6A: Machine._op_enter_self_link,
    0xEA: Machine._op_leave_self_link,
    0x6B: Machine._op_set_style,
    0xEB: Machine._op_set_style,
    0x6C: Machine._op_embed_res,
    0xEC: Machine._op_can_embed_res,
    0x6D: Machine._op_progress,
    0x6E: Machine._op_enter_span,
    0xEE: Machine._op_leave_span,
    0x6F: Machine._op_enter_status,
    0xEF: Machine._op_leave_status,
    0x70: Machine._op_ext0,
    0x72: Machine._op_save,
    0xF2: Machine._op_save_undo,
    0x73: Machine._op_get_input,
    0xF3: Machine._op_get_key,
    0x74: Machine._op_vm_info,
    0x78: Machine._op_set_idx,
    0x79: Machine._op_check_eq,
    0xF9: Machine._op_check_eq,
    0x7A: Machine._op_check_gt_eq,
    0xFA: Machine._op_check_gt_eq,
    0x7B: Machine._op_check_gt,
    0xFB: Machine._op_check_gt,
    0x7C: Machine._op_check_wordmap,
    0x7D: Machine._op_check_eq_2,
    0xFD: Machine._op_check_eq_2,
    0x7F: Machine._op_tracepoint,
}

# The EXT0 selectors (Aa-machine: Opcode semantics).
_EXTS: dict[int, Callable[[Machine], "str | None"]] = {
    0x00: Machine._ext_quit,
    0x01: Machine._ext_restart,
    0x02: Machine._ext_restore,
    0x03: Machine._ext_undo,
    0x04: Machine._ext_unstyle,
    0x05: Machine._ext_print_serial,
    0x06: Machine._ext_clear,
    0x07: Machine._ext_clear_all,
    0x08: Machine._ext_script_on,
    0x09: Machine._ext_script_off,
    0x0A: Machine._ext_trace_on,
    0x0B: Machine._ext_trace_off,
    0x0C: Machine._ext_inc_cwl,
    0x0D: Machine._ext_dec_cwl,
    0x0E: Machine._ext_uppercase,
    0x0F: Machine._ext_clear_links,
    0x10: Machine._ext_clear_old,
    0x11: Machine._ext_clear_div,
    0x12: Machine._ext_clear_status,
    0x13: Machine._ext_nbsp,
}
