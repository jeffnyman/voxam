"""Floating-point and double-precision opcodes.

Floats are IEEE-754 singles held in one 32-bit value (Glulx:
Floating-Point Numbers); doubles are IEEE-754 doubles split across
two (Glulx: Double-Precision Floating-Point Numbers). Python
computes in double precision throughout, so the single-precision
opcodes round on the way back out -- which is what gives fadd its
single-precision result even though the addition happened in
double.

Word order: a double argument is L1:L2, high word first. A double
*result* stores as S2:S1 -- the low word goes to the first store
operand. The spec is explicit about the asymmetry (Glulx:
Double-Precision Math), and getting it backwards would swap every
double a game ever computes.

Python's exceptions: C's math library returns NaN or infinity
where Python raises. log(0), sqrt(-1), fmod(inf, 2), and asin(2)
are all errors here and values there, so every entry point that
can raise is wrapped to produce the IEEE answer the spec asks for.
"""

import math
import struct
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from voxam.glulx.opcodes import Op
from voxam.glulx.operand import OperandList, operands

if TYPE_CHECKING:
    from voxam.glulx.machine import Machine

_MASK = 0xFFFFFFFF
_SIGN = 0x80000000
_FLOAT_INFINITY = 0x7F800000
_INT_MAX = 0x7FFFFFFF
_INT_MIN = 0x80000000

# glulxe compares against 2147483647.0 in both directions rather
# than -2147483648.0; matched so the boundary behaves identically.
_SATURATION = 2147483647.0

type _Handler = Callable[["Machine", list[Any]], None]


def encode_float(value: float) -> int:
    """Pack a Python float into an IEEE-754 single.

    Values too large for single precision become infinity rather
    than an error, which is what the arithmetic opcodes promise on
    overflow (Glulx: Floating-Point Math).
    """

    try:
        return int(struct.unpack(">I", struct.pack(">f", value))[0])
    except OverflowError:
        return _FLOAT_INFINITY | (_SIGN if value < 0 else 0)


def decode_float(bits: int) -> float:
    """Read a 32-bit value as an IEEE-754 single."""

    return float(struct.unpack(">f", (bits & _MASK).to_bytes(4, "big"))[0])


def encode_double(value: float) -> tuple[int, int]:
    """Pack a Python float into an IEEE-754 double, as (high, low)."""

    packed = struct.pack(">d", value)

    return (
        int(struct.unpack(">I", packed[0:4])[0]),
        int(struct.unpack(">I", packed[4:8])[0]),
    )


def decode_double(high: int, low: int) -> float:
    """Read a high and low word pair as an IEEE-754 double."""

    return float(
        struct.unpack(
            ">d",
            (high & _MASK).to_bytes(4, "big") + (low & _MASK).to_bytes(4, "big"),
        )[0]
    )


def _negative(value: float) -> bool:
    """The IEEE sign bit, set for -0.0 and for a negative NaN."""

    return math.copysign(1.0, value) < 0


def _to_int(value: float, *, nearest: bool) -> int:
    """A float as a 32-bit integer, saturated (Glulx: Floating-Point Math)."""

    if _negative(value):
        if math.isnan(value) or math.isinf(value) or value < -_SATURATION:
            return _INT_MIN
    elif math.isnan(value) or math.isinf(value) or value > _SATURATION:
        return _INT_MAX

    rounded = round(value) if nearest else math.trunc(value)

    return int(rounded) & _MASK


def _round_toward(function: Callable[[float], int]) -> Callable[[float], float]:
    """Wrap math.floor and math.ceil for float-shaped rounding.

    Both return Python *integers*, which loses two things the spec
    asks for: the sign of a zero result -- ceil(-0.5) is -0 -- and
    infinities, which they refuse to convert at all.
    """

    def wrapped(value: float) -> float:
        if math.isnan(value) or math.isinf(value) or value == 0.0:
            return value

        result = float(function(value))

        return math.copysign(result, value) if result == 0.0 else result

    return wrapped


_floor = _round_toward(math.floor)
_ceil = _round_toward(math.ceil)


def _sqrt(value: float) -> float:
    """The root: sqrt(-0) stays -0, and a negative answers NaN."""

    if value == 0.0:
        return value

    try:
        return math.sqrt(value)
    except ValueError:
        return math.nan


def _exp(value: float) -> float:
    """The exponential, overflowing to infinity."""

    try:
        return math.exp(value)
    except OverflowError:
        return math.inf


def _log(value: float) -> float:
    """The logarithm: both zeroes give -Inf, negatives give NaN."""

    if value == 0.0:
        return -math.inf

    try:
        return math.log(value)
    except ValueError:
        return math.nan


def _trig(function: Callable[[float], float]) -> Callable[[float], float]:
    """Wrap a trigonometric call to answer NaN where C would."""

    def wrapped(value: float) -> float:
        try:
            return function(value)
        except (ValueError, OverflowError):
            return math.nan

    return wrapped


def _pow(base: float, exponent: float) -> float:
    """Power, with the special cases C's own pow does not guarantee.

    The reference glulxe adds three by hand in glulx_powf, because
    a strict C library is not required to answer 1 for them: one
    to any power, anything to the zeroth, and minus one to an
    infinite power.
    """

    if base == 1.0 or exponent == 0.0:
        return 1.0

    if base == -1.0 and math.isinf(exponent):
        return 1.0

    if base == 0.0 and exponent < 0:
        # pow(+-0, y) for negative y is infinite -- negative only
        # when the base is -0 and the exponent an odd integer.
        # Python raises here.
        odd_integer = (
            not math.isinf(exponent)
            and exponent == int(exponent)
            and int(exponent) % 2 != 0
        )

        return -math.inf if (_negative(base) and odd_integer) else math.inf

    try:
        return math.pow(base, exponent)
    except OverflowError:
        negative = base < 0 and exponent == int(exponent) and bool(int(exponent) % 2)

        return -math.inf if negative else math.inf
    except ValueError:
        return math.nan


def _divide(a: float, b: float) -> float:
    """IEEE division: a zero denominator gives infinity or NaN."""

    try:
        return a / b
    except ZeroDivisionError:
        if a == 0.0 or math.isnan(a):
            return math.nan

        return math.copysign(math.inf, a) * math.copysign(1.0, b)


def _modulo(a: float, b: float) -> tuple[float, float]:
    """The (remainder, quotient) pair fmod and dmod speak.

    An infinite divisor leaves the value alone with a zero
    quotient; an infinite dividend or a zero divisor gives NaN for
    both (Glulx: Floating-Point Math).
    """

    if math.isnan(a) or math.isnan(b) or math.isinf(a) or b == 0.0:
        return math.nan, math.nan

    if math.isinf(b):
        return a, 0.0

    remainder = math.fmod(a, b)

    return remainder, _divide(a - remainder, b)


def _close(a: float, b: float, epsilon: float) -> bool:
    """The jfeq and jdeq test (Glulx: Floating-Point Comparisons).

    Infinities are settled before epsilon is consulted: two
    infinities are equal exactly when their signs match, whatever
    epsilon says. Only then does an infinite epsilon make
    everything else equal.
    """

    if math.isnan(a) or math.isnan(b) or math.isnan(epsilon):
        return False

    if math.isinf(a) and math.isinf(b):
        return _negative(a) == _negative(b)

    if math.isinf(epsilon):
        return True

    return abs(a - b) <= abs(epsilon)


# -- the handlers -----------------------------------------------------------
#
# Each takes the machine and the decoded operands; doubles arrive
# high word first and store low word first (module docstring).
#
# A NaN operand passes straight through the unary operations, bits
# and all, which is what IEEE 754 says of a quiet NaN. The rule is
# applied before the function is called, because CPython's math
# module does not follow it: math.acos of a positive NaN answers a
# NaN with the sign bit set, alone among the functions used here.
# The sign of a NaN is observable in Glulx -- a +NaN is
# 7F800001..7FFFFFFF, a -NaN FF800001..FFFFFFFF -- but nothing
# says which one an operation must produce, and the C libraries
# disagree with each other and with themselves. Copying one libm's
# inconsistencies would just be wrong on the next platform, so
# Voxam is uniform instead: propagate, in both precisions,
# everywhere.


def _float_unary(function: Callable[[float], float]) -> _Handler:
    """One float in, one float out, NaN passing through whole."""

    def handler(machine: "Machine", args: list[Any]) -> None:
        value = decode_float(args[0])

        if math.isnan(value):
            machine._store(args[1], args[0] & _MASK)

            return

        machine._store(args[1], encode_float(function(value)))

    return handler


def _float_binary(function: Callable[[float, float], float]) -> _Handler:
    """Two floats in, one float out."""

    def handler(machine: "Machine", args: list[Any]) -> None:
        result = function(decode_float(args[0]), decode_float(args[1]))

        machine._store(args[2], encode_float(result))

    return handler


def _double_unary(function: Callable[[float], float]) -> _Handler:
    """One double in, one double out, NaN passing through whole."""

    def handler(machine: "Machine", args: list[Any]) -> None:
        value = decode_double(args[0], args[1])

        if math.isnan(value):
            high, low = args[0] & _MASK, args[1] & _MASK
        else:
            high, low = encode_double(function(value))

        machine._store(args[2], low)
        machine._store(args[3], high)

    return handler


def _double_binary(function: Callable[[float, float], float]) -> _Handler:
    """Two doubles in, one double out."""

    def handler(machine: "Machine", args: list[Any]) -> None:
        result = function(
            decode_double(args[0], args[1]), decode_double(args[2], args[3])
        )

        high, low = encode_double(result)

        machine._store(args[4], low)
        machine._store(args[5], high)

    return handler


def _float_compare(test: Callable[[float, float], bool]) -> _Handler:
    """Two floats compared; the branch taken when the test holds."""

    def handler(machine: "Machine", args: list[Any]) -> None:
        if test(decode_float(args[0]), decode_float(args[1])):
            machine._jump(args[2])

    return handler


def _double_compare(test: Callable[[float, float], bool]) -> _Handler:
    """Two doubles compared; the branch taken when the test holds."""

    def handler(machine: "Machine", args: list[Any]) -> None:
        left = decode_double(args[0], args[1])
        right = decode_double(args[2], args[3])

        if test(left, right):
            machine._jump(args[4])

    return handler


def _float_test(test: Callable[[float], bool]) -> _Handler:
    """One float tested; the branch taken when the test holds."""

    def handler(machine: "Machine", args: list[Any]) -> None:
        if test(decode_float(args[0])):
            machine._jump(args[1])

    return handler


def _double_test(test: Callable[[float], bool]) -> _Handler:
    """One double tested; the branch taken when the test holds."""

    def handler(machine: "Machine", args: list[Any]) -> None:
        if test(decode_double(args[0], args[1])):
            machine._jump(args[2])

    return handler


def _op_numtof(machine: "Machine", args: list[Any]) -> None:
    """numtof: a signed integer becomes the nearest single."""

    value = args[0] - 0x1_0000_0000 if args[0] & _SIGN else args[0]

    machine._store(args[1], encode_float(float(value)))


def _op_ftonum(*, nearest: bool) -> _Handler:
    """The engine of ftonumz and ftonumn: a saturated integer."""

    def handler(machine: "Machine", args: list[Any]) -> None:
        machine._store(args[1], _to_int(decode_float(args[0]), nearest=nearest))

    return handler


def _op_fmod(machine: "Machine", args: list[Any]) -> None:
    """fmod: remainder and quotient at once."""

    remainder, quotient = _modulo(decode_float(args[0]), decode_float(args[1]))
    encoded = encode_float(quotient)

    if encoded in (0x0, _SIGN):
        # A zero quotient has lost its sign in the arithmetic; the
        # reference recovers it from the arguments' signs.
        encoded = (args[0] ^ args[1]) & _SIGN

    machine._store(args[2], encode_float(remainder))
    machine._store(args[3], encoded)


def _op_numtod(machine: "Machine", args: list[Any]) -> None:
    """numtod: a signed integer becomes a double, exactly."""

    value = args[0] - 0x1_0000_0000 if args[0] & _SIGN else args[0]
    high, low = encode_double(float(value))

    machine._store(args[1], low)
    machine._store(args[2], high)


def _op_ftod(machine: "Machine", args: list[Any]) -> None:
    """ftod: every single widens exactly."""

    high, low = encode_double(decode_float(args[0]))

    machine._store(args[1], low)
    machine._store(args[2], high)


def _op_dtof(machine: "Machine", args: list[Any]) -> None:
    """dtof: a double narrows, rounding to the nearest single."""

    machine._store(args[2], encode_float(decode_double(args[0], args[1])))


def _op_dtonum(*, nearest: bool) -> _Handler:
    """The engine of dtonumz and dtonumn: a saturated integer."""

    def handler(machine: "Machine", args: list[Any]) -> None:
        machine._store(
            args[2], _to_int(decode_double(args[0], args[1]), nearest=nearest)
        )

    return handler


def _op_dmod(*, quotient_wanted: bool) -> _Handler:
    """The engine of dmodr and dmodq: remainder or quotient."""

    def handler(machine: "Machine", args: list[Any]) -> None:
        remainder, quotient = _modulo(
            decode_double(args[0], args[1]), decode_double(args[2], args[3])
        )
        high, low = encode_double(quotient if quotient_wanted else remainder)

        if quotient_wanted and low == 0 and high in (0x0, _SIGN):
            # As in fmod: a zero quotient takes its sign from the
            # arguments.
            high = (args[0] ^ args[2]) & _SIGN

        machine._store(args[4], low)
        machine._store(args[5], high)

    return handler


def _op_jfeq(machine: "Machine", args: list[Any]) -> None:
    """Branch when equal within epsilon -- jfeq's own test."""

    if _close(decode_float(args[0]), decode_float(args[1]), decode_float(args[2])):
        machine._jump(args[3])


def _op_jfne(machine: "Machine", args: list[Any]) -> None:
    """jfne: the reverse of jfeq, so any NaN branches."""

    if not _close(decode_float(args[0]), decode_float(args[1]), decode_float(args[2])):
        machine._jump(args[3])


def _op_jdeq(machine: "Machine", args: list[Any]) -> None:
    """jdeq: doubles equal within a double epsilon."""

    if _close(
        decode_double(args[0], args[1]),
        decode_double(args[2], args[3]),
        decode_double(args[4], args[5]),
    ):
        machine._jump(args[6])


def _op_jdne(machine: "Machine", args: list[Any]) -> None:
    """jdne: the reverse of jdeq, so any NaN branches."""

    if not _close(
        decode_double(args[0], args[1]),
        decode_double(args[2], args[3]),
        decode_double(args[4], args[5]),
    ):
        machine._jump(args[6])


def _entries() -> dict[int, tuple[OperandList, _Handler]]:
    """The whole family's dispatch table, signatures included."""

    ls = operands("LS")
    lls = operands("LLS")
    llss = operands("LLSS")
    lss = operands("LSS")
    llllss = operands("LLLLSS")
    ll = operands("LL")
    lll = operands("LLL")
    llll = operands("LLLL")
    lllll = operands("LLLLL")
    lllllll = operands("LLLLLLL")

    return {
        # Conversions and arithmetic (Glulx: Floating-Point Math).
        Op.NUMTOF: (ls, _op_numtof),
        Op.FTONUMZ: (ls, _op_ftonum(nearest=False)),
        Op.FTONUMN: (ls, _op_ftonum(nearest=True)),
        Op.CEIL: (ls, _float_unary(_ceil)),
        Op.FLOOR: (ls, _float_unary(_floor)),
        Op.FADD: (lls, _float_binary(lambda a, b: a + b)),
        Op.FSUB: (lls, _float_binary(lambda a, b: a - b)),
        Op.FMUL: (lls, _float_binary(lambda a, b: a * b)),
        Op.FDIV: (lls, _float_binary(_divide)),
        Op.FMOD: (llss, _op_fmod),
        Op.SQRT: (ls, _float_unary(_sqrt)),
        Op.EXP: (ls, _float_unary(_exp)),
        Op.LOG: (ls, _float_unary(_log)),
        Op.POW: (lls, _float_binary(_pow)),
        Op.SIN: (ls, _float_unary(_trig(math.sin))),
        Op.COS: (ls, _float_unary(_trig(math.cos))),
        Op.TAN: (ls, _float_unary(_trig(math.tan))),
        Op.ASIN: (ls, _float_unary(_trig(math.asin))),
        Op.ACOS: (ls, _float_unary(_trig(math.acos))),
        Op.ATAN: (ls, _float_unary(_trig(math.atan))),
        Op.ATAN2: (lls, _float_binary(math.atan2)),
        # Comparisons (Glulx: Floating-Point Comparisons).
        Op.JFEQ: (llll, _op_jfeq),
        Op.JFNE: (llll, _op_jfne),
        Op.JFLT: (lll, _float_compare(lambda a, b: a < b)),
        Op.JFLE: (lll, _float_compare(lambda a, b: a <= b)),
        Op.JFGT: (lll, _float_compare(lambda a, b: a > b)),
        Op.JFGE: (lll, _float_compare(lambda a, b: a >= b)),
        Op.JISNAN: (ll, _float_test(math.isnan)),
        Op.JISINF: (ll, _float_test(math.isinf)),
        # Double conversions and arithmetic (Glulx: Double-
        # Precision Math).
        Op.NUMTOD: (lss, _op_numtod),
        Op.DTONUMZ: (lls, _op_dtonum(nearest=False)),
        Op.DTONUMN: (lls, _op_dtonum(nearest=True)),
        Op.FTOD: (lss, _op_ftod),
        Op.DTOF: (lls, _op_dtof),
        Op.DCEIL: (llss, _double_unary(_ceil)),
        Op.DFLOOR: (llss, _double_unary(_floor)),
        Op.DADD: (llllss, _double_binary(lambda a, b: a + b)),
        Op.DSUB: (llllss, _double_binary(lambda a, b: a - b)),
        Op.DMUL: (llllss, _double_binary(lambda a, b: a * b)),
        Op.DDIV: (llllss, _double_binary(_divide)),
        Op.DMODR: (llllss, _op_dmod(quotient_wanted=False)),
        Op.DMODQ: (llllss, _op_dmod(quotient_wanted=True)),
        Op.DSQRT: (llss, _double_unary(_sqrt)),
        Op.DEXP: (llss, _double_unary(_exp)),
        Op.DLOG: (llss, _double_unary(_log)),
        Op.DPOW: (llllss, _double_binary(_pow)),
        Op.DSIN: (llss, _double_unary(_trig(math.sin))),
        Op.DCOS: (llss, _double_unary(_trig(math.cos))),
        Op.DTAN: (llss, _double_unary(_trig(math.tan))),
        Op.DASIN: (llss, _double_unary(_trig(math.asin))),
        Op.DACOS: (llss, _double_unary(_trig(math.acos))),
        Op.DATAN: (llss, _double_unary(_trig(math.atan))),
        Op.DATAN2: (llllss, _double_binary(math.atan2)),
        # Double comparisons (Glulx: Double-Precision Comparisons).
        Op.JDEQ: (lllllll, _op_jdeq),
        Op.JDNE: (lllllll, _op_jdne),
        Op.JDLT: (lllll, _double_compare(lambda a, b: a < b)),
        Op.JDLE: (lllll, _double_compare(lambda a, b: a <= b)),
        Op.JDGT: (lllll, _double_compare(lambda a, b: a > b)),
        Op.JDGE: (lllll, _double_compare(lambda a, b: a >= b)),
        Op.JDISNAN: (lll, _double_test(math.isnan)),
        Op.JDISINF: (lll, _double_test(math.isinf)),
    }


# The table the machine merges into its own dispatch.
DISPATCH = _entries()
