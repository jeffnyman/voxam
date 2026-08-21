"""Floats and doubles: IEEE-754 through the machine (Glulx:
Floating-Point Math).
"""

import math
from collections.abc import Callable

from assertpy import assert_that

from voxam.glulx import floats
from voxam.glulx.floats import (
    DISPATCH,
    decode_double,
    decode_float,
    encode_double,
    encode_float,
)
from voxam.glulx.machine import Machine
from voxam.glulx.opcodes import Op
from voxam.glulx.operand import StoreTarget
from voxam.glulx.stack import DestType
from voxam.glulx.story import Story

IDLE = bytes([0xC0, 0x00, 0x00, 0x81, 0x20])
PLANT = 0x180
RESULT = 0x140
SECOND = 0x148

INT_MAX = 0x7FFFFFFF
INT_MIN = 0x80000000
F_INF = 0x7F800000
F_NEG_INF = 0xFF800000
F_NAN = 0x7FC00000
F_NEG_NAN = 0xFFC00123
D_NAN = (0x7FF80000, 0x00000000)

FLOAT_UNARY = (
    Op.CEIL,
    Op.FLOOR,
    Op.SQRT,
    Op.EXP,
    Op.LOG,
    Op.SIN,
    Op.COS,
    Op.TAN,
    Op.ASIN,
    Op.ACOS,
    Op.ATAN,
)
DOUBLE_UNARY = (
    Op.DCEIL,
    Op.DFLOOR,
    Op.DSQRT,
    Op.DEXP,
    Op.DLOG,
    Op.DSIN,
    Op.DCOS,
    Op.DTAN,
    Op.DASIN,
    Op.DACOS,
    Op.DATAN,
)


def booted(image: Callable[..., bytes]) -> Machine:
    return Machine(Story(image(code=IDLE)))


def mem(address: int) -> StoreTarget:
    return StoreTarget(DestType.MEMORY, address)


def stored(machine: Machine, op: Op, loads: list[int]) -> int:
    DISPATCH[op][1](machine, [*loads, mem(RESULT)])

    return machine.memory.read_word(RESULT)


def stored_double(machine: Machine, op: Op, loads: list[int]) -> tuple[int, int]:
    """Run a double-result op; (high, low) comes back.

    The stores arrive low word first -- the spec's own asymmetry
    -- so reading them back swapped is itself the assertion.
    """

    DISPATCH[op][1](machine, [*loads, mem(RESULT), mem(SECOND)])

    return machine.memory.read_word(SECOND), machine.memory.read_word(RESULT)


def jumped(machine: Machine, op: Op, loads: list[int]) -> bool:
    machine.pc = 0x1000

    DISPATCH[op][1](machine, [*loads, 0x10])

    return machine.pc == 0x1000 + 0x10 - 2


def f(value: float) -> int:
    return encode_float(value)


def d(value: float) -> list[int]:
    high, low = encode_double(value)

    return [high, low]


# The encodings round-trip exactly, and a value too large for
# single precision overflows to a signed infinity.
def test_encodings_round_trip() -> None:
    assert_that(encode_float(1.5)).is_equal_to(0x3FC00000)
    assert_that(decode_float(0x3FC00000)).is_equal_to(1.5)
    assert_that(encode_float(1e300)).is_equal_to(F_INF)
    assert_that(encode_float(-1e300)).is_equal_to(F_NEG_INF)

    high, low = encode_double(math.pi)

    assert_that(decode_double(high, low)).is_equal_to(math.pi)


# The conversions: integers to floats and back with truncation,
# rounding, and saturation; floats to doubles exactly; doubles to
# floats by rounding. Double results store low word first.
def test_conversions_saturate_and_round(image: Callable[..., bytes]) -> None:
    machine = booted(image)

    assert_that(stored(machine, Op.NUMTOF, [2])).is_equal_to(0x40000000)
    assert_that(stored(machine, Op.NUMTOF, [0xFFFFFFFE])).is_equal_to(0xC0000000)

    answers = [
        (Op.FTONUMZ, [f(2.7)], 2),
        (Op.FTONUMZ, [f(-2.7)], 0xFFFFFFFE),
        (Op.FTONUMN, [f(2.7)], 3),
        (Op.FTONUMN, [f(-2.7)], 0xFFFFFFFD),
        (Op.FTONUMZ, [F_INF], INT_MAX),
        (Op.FTONUMZ, [F_NEG_INF], INT_MIN),
        (Op.FTONUMZ, [F_NAN], INT_MAX),
        (Op.FTONUMZ, [F_NEG_NAN], INT_MIN),
        (Op.FTONUMZ, [f(3e9)], INT_MAX),
        (Op.FTONUMZ, [f(-3e9)], INT_MIN),
        (Op.DTONUMZ, [*d(-2.7)], 0xFFFFFFFE),
        (Op.DTONUMN, [*d(2.7)], 3),
        (Op.DTOF, [*d(1.1)], f(1.1)),
    ]

    for op, loads, expected in answers:
        assert_that(stored(machine, op, loads)).described_as(str(op)).is_equal_to(
            expected
        )

    assert_that(stored_double(machine, Op.NUMTOD, [0xFFFFFFFD])).is_equal_to(
        (0xC0080000, 0)
    )
    assert_that(stored_double(machine, Op.FTOD, [f(1.5)])).is_equal_to((0x3FF80000, 0))


# The arithmetic: computed in double, rounded to single on the way
# out, with IEEE answers where C would have them and Python would
# raise.
def test_float_arithmetic_is_ieee(image: Callable[..., bytes]) -> None:
    machine = booted(image)

    answers = [
        (Op.FADD, [f(1.5), f(2.25)], f(3.75)),
        (Op.FADD, [f(1.0), f(1e-10)], f(1.0)),
        (Op.FSUB, [f(5.0), f(1.5)], f(3.5)),
        (Op.FMUL, [f(3.0), f(0.5)], f(1.5)),
        (Op.FDIV, [f(1.0), f(0.0)], F_INF),
        (Op.FDIV, [f(-1.0), f(0.0)], F_NEG_INF),
        (Op.FDIV, [f(1.0), 0x80000000], F_NEG_INF),
        (Op.POW, [f(2.0), f(10.0)], f(1024.0)),
        (Op.POW, [f(1.0), F_NAN], f(1.0)),
        (Op.POW, [F_NAN, f(0.0)], f(1.0)),
        (Op.POW, [f(-1.0), F_INF], f(1.0)),
        (Op.POW, [f(0.0), f(-3.0)], F_INF),
        (Op.POW, [0x80000000, f(-3.0)], F_NEG_INF),
        (Op.POW, [0x80000000, f(-2.0)], F_INF),
        (Op.POW, [f(0.0), f(-2.5)], F_INF),
        (Op.POW, [f(-1e30), f(11.0)], F_NEG_INF),
        (Op.POW, [f(1e30), f(100.0)], F_INF),
        (Op.ATAN2, [f(1.0), f(1.0)], f(math.pi / 4)),
    ]

    for op, loads, expected in answers:
        assert_that(stored(machine, op, loads)).described_as(str(op)).is_equal_to(
            expected
        )

    # 0/0 and pow(-2, 0.5) are NaN; the payload is Python's, so
    # only NaN-ness is asserted.
    assert_that(
        math.isnan(decode_float(stored(machine, Op.FDIV, [f(0.0), f(0.0)])))
    ).is_true()
    assert_that(
        math.isnan(decode_float(stored(machine, Op.POW, [f(-2.0), f(0.5)])))
    ).is_true()


# fmod speaks remainder and quotient at once, and a quotient that
# underflows to zero takes its sign from the arguments.
def test_fmod_keeps_the_quotient_sign(image: Callable[..., bytes]) -> None:
    machine = booted(image)
    handler = DISPATCH[Op.FMOD][1]

    handler(machine, [f(7.5), f(2.0), mem(RESULT), mem(SECOND)])

    assert_that(machine.memory.read_word(RESULT)).is_equal_to(f(1.5))
    assert_that(machine.memory.read_word(SECOND)).is_equal_to(f(3.0))

    handler(machine, [f(1e-30), f(-1e30), mem(RESULT), mem(SECOND)])

    assert_that(machine.memory.read_word(SECOND)).is_equal_to(0x80000000)

    handler(machine, [f(1e-30), f(1e30), mem(RESULT), mem(SECOND)])

    assert_that(machine.memory.read_word(SECOND)).is_equal_to(0)

    # An infinite divisor leaves the value whole; a NaN dividend
    # poisons both answers.
    handler(machine, [f(3.0), F_INF, mem(RESULT), mem(SECOND)])

    assert_that(machine.memory.read_word(RESULT)).is_equal_to(f(3.0))

    handler(machine, [F_NAN, f(2.0), mem(RESULT), mem(SECOND)])

    assert_that(math.isnan(decode_float(machine.memory.read_word(RESULT)))).is_true()


# The unary family: rounding keeps the sign of zero, the roots and
# logs answer NaN and infinities where C would, and every function
# passes a NaN operand through bits-and-all -- acos included,
# where CPython alone would flip the sign.
def test_unary_functions_keep_ieee_shape(image: Callable[..., bytes]) -> None:
    machine = booted(image)

    answers = [
        (Op.CEIL, [f(-0.5)], 0x80000000),
        (Op.CEIL, [f(1.2)], f(2.0)),
        (Op.CEIL, [F_INF], F_INF),
        (Op.FLOOR, [f(0.5)], 0),
        (Op.FLOOR, [f(-1.2)], f(-2.0)),
        (Op.SQRT, [f(4.0)], f(2.0)),
        (Op.SQRT, [0x80000000], 0x80000000),
        (Op.EXP, [f(0.0)], f(1.0)),
        (Op.EXP, [f(1000.0)], F_INF),
        (Op.LOG, [f(0.0)], F_NEG_INF),
        (Op.LOG, [f(1.0)], 0),
        (Op.SIN, [f(0.0)], 0),
        (Op.COS, [f(0.0)], f(1.0)),
        (Op.TAN, [f(0.0)], 0),
        (Op.ASIN, [f(0.0)], 0),
        (Op.ACOS, [f(1.0)], 0),
        (Op.ATAN, [f(0.0)], 0),
    ]

    for op, loads, expected in answers:
        assert_that(stored(machine, op, loads)).described_as(str(op)).is_equal_to(
            expected
        )

    assert_that(math.isnan(decode_float(stored(machine, Op.SQRT, [f(-1.0)])))).is_true()
    assert_that(math.isnan(decode_float(stored(machine, Op.LOG, [f(-1.0)])))).is_true()
    assert_that(math.isnan(decode_float(stored(machine, Op.ASIN, [f(2.0)])))).is_true()

    for op in FLOAT_UNARY:
        assert_that(stored(machine, op, [F_NEG_NAN])).described_as(str(op)).is_equal_to(
            F_NEG_NAN
        )
        assert_that(stored(machine, op, [F_NAN])).described_as(str(op)).is_equal_to(
            F_NAN
        )


# The double family answers in full double precision -- 0.1 + 0.2
# is the famous sum, exactly -- and NaNs pass through both words
# unchanged.
def test_double_arithmetic_is_exact(image: Callable[..., bytes]) -> None:
    machine = booted(image)

    answers = [
        (Op.DADD, [*d(0.1), *d(0.2)], encode_double(0.30000000000000004)),
        (Op.DSUB, [*d(5.0), *d(1.5)], encode_double(3.5)),
        (Op.DMUL, [*d(3.0), *d(0.5)], encode_double(1.5)),
        (Op.DDIV, [*d(1.0), *d(0.0)], encode_double(math.inf)),
        (Op.DPOW, [*d(2.0), *d(0.5)], encode_double(math.sqrt(2.0))),
        (Op.DATAN2, [*d(1.0), *d(1.0)], encode_double(math.pi / 4)),
    ]

    for op, loads, expected in answers:
        assert_that(stored_double(machine, op, loads)).described_as(
            str(op)
        ).is_equal_to(expected)

    unary_answers = [
        (Op.DCEIL, [*d(-0.5)], encode_double(-0.0)),
        (Op.DFLOOR, [*d(1.7)], encode_double(1.0)),
        (Op.DSQRT, [*d(4.0)], encode_double(2.0)),
        (Op.DEXP, [*d(0.0)], encode_double(1.0)),
        (Op.DLOG, [*d(1.0)], encode_double(0.0)),
        (Op.DSIN, [*d(0.0)], encode_double(0.0)),
        (Op.DCOS, [*d(0.0)], encode_double(1.0)),
        (Op.DTAN, [*d(0.0)], encode_double(0.0)),
        (Op.DASIN, [*d(0.0)], encode_double(0.0)),
        (Op.DACOS, [*d(1.0)], encode_double(0.0)),
        (Op.DATAN, [*d(0.0)], encode_double(0.0)),
    ]

    for op, loads, expected in unary_answers:
        assert_that(stored_double(machine, op, loads)).described_as(
            str(op)
        ).is_equal_to(expected)

    for op in DOUBLE_UNARY:
        assert_that(stored_double(machine, op, [0xFFF80000, 0x123])).described_as(
            str(op)
        ).is_equal_to((0xFFF80000, 0x123))


# dmodr and dmodq split the modulo pair, and the quotient's
# underflowed zero takes its sign from the arguments here too.
def test_dmod_splits_the_pair(image: Callable[..., bytes]) -> None:
    machine = booted(image)

    assert_that(stored_double(machine, Op.DMODR, [*d(7.5), *d(2.0)])).is_equal_to(
        encode_double(1.5)
    )
    assert_that(stored_double(machine, Op.DMODQ, [*d(7.5), *d(2.0)])).is_equal_to(
        encode_double(3.0)
    )
    assert_that(stored_double(machine, Op.DMODQ, [*d(1e-200), *d(-1e200)])).is_equal_to(
        (0x80000000, 0)
    )
    assert_that(stored_double(machine, Op.DMODQ, [*d(1e-200), *d(1e200)])).is_equal_to(
        (0, 0)
    )


# The float comparisons: epsilon equality with its infinity
# rulings, the orderings, and the NaN and infinity tests.
def test_float_branches_decide(image: Callable[..., bytes]) -> None:
    machine = booted(image)

    answers = [
        (Op.JFEQ, [f(1.0), f(1.05), f(0.1)], True),
        (Op.JFEQ, [f(1.0), f(1.05), f(0.01)], False),
        (Op.JFEQ, [f(1.0), f(1.0), F_NAN], False),
        (Op.JFEQ, [F_INF, F_INF, f(0.0)], True),
        (Op.JFEQ, [F_INF, F_NEG_INF, F_INF], False),
        (Op.JFEQ, [f(2.0), f(9999.0), F_INF], True),
        (Op.JFNE, [f(1.0), f(1.0), F_NAN], True),
        (Op.JFNE, [f(1.0), f(1.0), f(0.0)], False),
        (Op.JFLT, [f(1.0), f(2.0)], True),
        (Op.JFLT, [f(2.0), f(1.0)], False),
        (Op.JFLE, [f(2.0), f(2.0)], True),
        (Op.JFLE, [f(3.0), f(2.0)], False),
        (Op.JFGT, [f(3.0), f(2.0)], True),
        (Op.JFGT, [F_NAN, f(2.0)], False),
        (Op.JFGE, [f(2.0), f(2.0)], True),
        (Op.JFGE, [f(1.0), f(2.0)], False),
        (Op.JISNAN, [F_NAN], True),
        (Op.JISNAN, [f(1.0)], False),
        (Op.JISINF, [F_NEG_INF], True),
        (Op.JISINF, [f(1.0)], False),
    ]

    for op, loads, taken in answers:
        assert_that(jumped(machine, op, loads)).described_as(str(op)).is_equal_to(taken)


# The double comparisons walk the same ladder over word pairs.
def test_double_branches_decide(image: Callable[..., bytes]) -> None:
    machine = booted(image)

    answers = [
        (Op.JDEQ, [*d(1.0), *d(1.05), *d(0.1)], True),
        (Op.JDEQ, [*d(1.0), *d(1.05), *d(0.01)], False),
        (Op.JDNE, [*d(1.0), *d(1.0), *D_NAN], True),
        (Op.JDNE, [*d(1.0), *d(1.0), *d(0.0)], False),
        (Op.JDLT, [*d(1.0), *d(2.0)], True),
        (Op.JDLT, [*d(2.0), *d(1.0)], False),
        (Op.JDLE, [*d(2.0), *d(2.0)], True),
        (Op.JDLE, [*d(3.0), *d(2.0)], False),
        (Op.JDGT, [*d(3.0), *d(2.0)], True),
        (Op.JDGT, [*d(1.0), *d(2.0)], False),
        (Op.JDGE, [*d(2.0), *d(2.0)], True),
        (Op.JDGE, [*d(1.0), *d(2.0)], False),
        (Op.JDISNAN, [*D_NAN], True),
        (Op.JDISNAN, [*d(1.0)], False),
        (Op.JDISINF, [*d(math.inf)], True),
        (Op.JDISINF, [*d(1.0)], False),
    ]

    for op, loads, taken in answers:
        assert_that(jumped(machine, op, loads)).described_as(str(op)).is_equal_to(taken)


# The family reaches the machine through the real dispatch: fadd
# and dadd by plant, and a taken jfeq branching over a store.
def test_the_dispatch_runs_the_family(image: Callable[..., bytes]) -> None:
    machine = booted(image)

    fadd = (
        bytes([0x81, 0xA0, 0x33, 0x07])
        + f(1.5).to_bytes(4, "big")
        + f(2.0).to_bytes(4, "big")
        + RESULT.to_bytes(4, "big")
    )
    dadd = (
        bytes([0x82, 0x10, 0x33, 0x33, 0x77])
        + b"".join(word.to_bytes(4, "big") for word in [*d(0.5), *d(0.25)])
        + SECOND.to_bytes(4, "big")
        + (SECOND + 4).to_bytes(4, "big")
    )
    # jfeq 1.0 1.0 0.0 -> skip the next instruction, a copy that
    # would scribble on a witness word: the copy is seven bytes,
    # plus the branch bias of two.
    witness = 0x150
    skip = (
        bytes([0x81, 0xC0, 0x33, 0x13])
        + f(1.0).to_bytes(4, "big")
        + f(1.0).to_bytes(4, "big")
        + f(0.0).to_bytes(4, "big")
        + bytes([0x09])
        + bytes([0x40, 0x71, 0x63])
        + witness.to_bytes(4, "big")
    )

    machine.memory.write_run(PLANT, fadd + dadd + skip + bytes([0x81, 0x20]))

    machine.pc = PLANT

    machine.run(limit=10)

    assert_that(machine.memory.read_word(RESULT)).is_equal_to(f(3.5))

    high, low = encode_double(0.75)

    assert_that(machine.memory.read_word(SECOND)).is_equal_to(low)
    assert_that(machine.memory.read_word(SECOND + 4)).is_equal_to(high)
    assert_that(machine.memory.read_word(witness)).is_equal_to(0)


# The module-level helpers the handlers lean on, at their edges.
def test_the_helper_edges() -> None:
    assert_that(floats._to_int(2.5, nearest=True)).is_equal_to(2)
    assert_that(floats._pow(0.0, -math.inf)).is_equal_to(math.inf)
    assert_that(floats._modulo(math.inf, 2.0)[0]).is_nan()
    assert_that(floats._divide(math.nan, 0.0)).is_nan()
    assert_that(floats._close(math.nan, 1.0, 1.0)).is_false()
