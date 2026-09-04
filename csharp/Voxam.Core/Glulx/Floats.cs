namespace Voxam.Core.Glulx;

/// <summary>
/// Floating-point and double-precision opcodes.
///
/// Floats are IEEE-754 singles held in one 32-bit value (Glulx:
/// Floating-Point Numbers); doubles are IEEE-754 doubles split across
/// two (Glulx: Double-Precision Floating-Point Numbers). Everything
/// computes in double precision throughout, so the single-precision
/// opcodes round on the way back out, which is what gives fadd its
/// single-precision result even though the addition happened in
/// double.
///
/// Word order: a double argument is L1:L2, high word first. A double
/// result stores as S2:S1, the low word going to the first store
/// operand. The specification is explicit about the asymmetry (Glulx:
/// Double-Precision Math), and getting it backwards would swap every
/// double a game ever computes.
///
/// The Python wraps its own math library because it raises for
/// log(0), sqrt(-1) and asin(2) where C answers with an IEEE value.
/// The runtime here already answers the IEEE way, but the wrappers
/// stay for a second reason that is easy to miss: they also settle
/// the sign of a manufactured NaN. This runtime's NaN constant has
/// its sign bit set and the Python's does not, and the sign is
/// observable in Glulx even though nothing says which one an
/// operation must produce, so every NaN this module makes for itself
/// is made positive, and only a NaN that came out of the hardware is
/// left as the hardware made it.
/// </summary>
public static class Floats
{
    private const uint Sign = 0x80000000;
    private const uint IntMax = 0x7FFFFFFF;
    private const uint IntMin = 0x80000000;

    // glulxe compares against 2147483647.0 in both directions rather
    // than -2147483648.0; matched so the boundary behaves identically.
    private const double Saturation = 2147483647.0;

    // Above this every double is an even integer, so nothing larger
    // needs its oddness asked about.
    private const double ExactIntegers = 9007199254740992.0;

    // A NaN with its sign bit clear, which the runtime's own constant
    // does not have. See the note above.
    private static readonly double Nan = BitConverter.UInt64BitsToDouble(0x7FF8000000000000UL);

    /// <summary>
    /// The whole family's dispatch table, signatures included: sixty
    /// one opcodes of one shape, kept apart from the machine's own.
    /// </summary>
    public static Dictionary<int, Dispatch> Entries()
    {
        var ls = new OperandList("LS");
        var lls = new OperandList("LLS");
        var llss = new OperandList("LLSS");
        var lss = new OperandList("LSS");
        var llllss = new OperandList("LLLLSS");
        var ll = new OperandList("LL");
        var lll = new OperandList("LLL");
        var llll = new OperandList("LLLL");
        var lllll = new OperandList("LLLLL");
        var lllllll = new OperandList("LLLLLLL");

        return new Dictionary<int, Dispatch>
        {
            // Conversions and arithmetic (Glulx: Floating-Point Math).
            [(int)Op.Numtof] = new(ls, static (m, a) => m.Store(a[1].Target, Encode((int)a[0].Value))),
            [(int)Op.Ftonumz] = new(ls, ToNumber(nearest: false)),
            [(int)Op.Ftonumn] = new(ls, ToNumber(nearest: true)),
            [(int)Op.Ceil] = new(ls, Unary(Math.Ceiling)),
            [(int)Op.Floor] = new(ls, Unary(Math.Floor)),
            [(int)Op.Fadd] = new(lls, Binary(static (a, b) => a + b)),
            [(int)Op.Fsub] = new(lls, Binary(static (a, b) => a - b)),
            [(int)Op.Fmul] = new(lls, Binary(static (a, b) => a * b)),
            [(int)Op.Fdiv] = new(lls, Binary(Divide)),
            [(int)Op.Fmod] = new(llss, Fmod),
            [(int)Op.Sqrt] = new(ls, Unary(Root)),
            [(int)Op.Exp] = new(ls, Unary(Math.Exp)),
            [(int)Op.Log] = new(ls, Unary(Logarithm)),
            [(int)Op.Pow] = new(lls, Binary(Power)),
            [(int)Op.Sin] = new(ls, Unary(Trig(Math.Sin))),
            [(int)Op.Cos] = new(ls, Unary(Trig(Math.Cos))),
            [(int)Op.Tan] = new(ls, Unary(Trig(Math.Tan))),
            [(int)Op.Asin] = new(ls, Unary(Trig(Math.Asin))),
            [(int)Op.Acos] = new(ls, Unary(Trig(Math.Acos))),
            [(int)Op.Atan] = new(ls, Unary(Trig(Math.Atan))),
            [(int)Op.Atan2] = new(lls, Binary(Math.Atan2)),

            // Comparisons (Glulx: Floating-Point Comparisons).
            [(int)Op.Jfeq] = new(llll, Near(wanted: true)),
            [(int)Op.Jfne] = new(llll, Near(wanted: false)),
            [(int)Op.Jflt] = new(lll, Compare(static (a, b) => a < b)),
            [(int)Op.Jfle] = new(lll, Compare(static (a, b) => a <= b)),
            [(int)Op.Jfgt] = new(lll, Compare(static (a, b) => a > b)),
            [(int)Op.Jfge] = new(lll, Compare(static (a, b) => a >= b)),
            [(int)Op.Jisnan] = new(ll, Test(double.IsNaN)),
            [(int)Op.Jisinf] = new(ll, Test(double.IsInfinity)),

            // Double conversions and arithmetic (Glulx: Double-
            // Precision Math).
            [(int)Op.Numtod] = new(lss, static (m, a) => StoreWide(m, a, 1, (int)a[0].Value)),
            [(int)Op.Dtonumz] = new(lls, ToNumberWide(nearest: false)),
            [(int)Op.Dtonumn] = new(lls, ToNumberWide(nearest: true)),
            [(int)Op.Ftod] = new(lss, static (m, a) => StoreWide(m, a, 1, Decode(a[0].Value))),
            [(int)Op.Dtof] = new(lls, static (m, a) => m.Store(a[2].Target, Encode(DecodeWide(a[0].Value, a[1].Value)))),
            [(int)Op.Dceil] = new(llss, UnaryWide(Math.Ceiling)),
            [(int)Op.Dfloor] = new(llss, UnaryWide(Math.Floor)),
            [(int)Op.Dadd] = new(llllss, BinaryWide(static (a, b) => a + b)),
            [(int)Op.Dsub] = new(llllss, BinaryWide(static (a, b) => a - b)),
            [(int)Op.Dmul] = new(llllss, BinaryWide(static (a, b) => a * b)),
            [(int)Op.Ddiv] = new(llllss, BinaryWide(Divide)),
            [(int)Op.Dmodr] = new(llllss, Dmod(quotientWanted: false)),
            [(int)Op.Dmodq] = new(llllss, Dmod(quotientWanted: true)),
            [(int)Op.Dsqrt] = new(llss, UnaryWide(Root)),
            [(int)Op.Dexp] = new(llss, UnaryWide(Math.Exp)),
            [(int)Op.Dlog] = new(llss, UnaryWide(Logarithm)),
            [(int)Op.Dpow] = new(llllss, BinaryWide(Power)),
            [(int)Op.Dsin] = new(llss, UnaryWide(Trig(Math.Sin))),
            [(int)Op.Dcos] = new(llss, UnaryWide(Trig(Math.Cos))),
            [(int)Op.Dtan] = new(llss, UnaryWide(Trig(Math.Tan))),
            [(int)Op.Dasin] = new(llss, UnaryWide(Trig(Math.Asin))),
            [(int)Op.Dacos] = new(llss, UnaryWide(Trig(Math.Acos))),
            [(int)Op.Datan] = new(llss, UnaryWide(Trig(Math.Atan))),
            [(int)Op.Datan2] = new(llllss, BinaryWide(Math.Atan2)),

            // Double comparisons (Glulx: Double-Precision Comparisons).
            [(int)Op.Jdeq] = new(lllllll, NearWide(wanted: true)),
            [(int)Op.Jdne] = new(lllllll, NearWide(wanted: false)),
            [(int)Op.Jdlt] = new(lllll, CompareWide(static (a, b) => a < b)),
            [(int)Op.Jdle] = new(lllll, CompareWide(static (a, b) => a <= b)),
            [(int)Op.Jdgt] = new(lllll, CompareWide(static (a, b) => a > b)),
            [(int)Op.Jdge] = new(lllll, CompareWide(static (a, b) => a >= b)),
            [(int)Op.Jdisnan] = new(lll, TestWide(double.IsNaN)),
            [(int)Op.Jdisinf] = new(lll, TestWide(double.IsInfinity)),
        };
    }

    /// <summary>
    /// Pack a value into an IEEE-754 single. One too large for single
    /// precision becomes infinity rather than an error, which is what
    /// the arithmetic opcodes promise on overflow (Glulx:
    /// Floating-Point Math).
    /// </summary>
    public static uint Encode(double value) => BitConverter.SingleToUInt32Bits((float)value);

    /// <summary>Read a 32-bit value as an IEEE-754 single.</summary>
    public static double Decode(uint bits) => BitConverter.UInt32BitsToSingle(bits);

    /// <summary>Pack a value into an IEEE-754 double, as its high and low words.</summary>
    public static (uint High, uint Low) EncodeWide(double value)
    {
        var bits = BitConverter.DoubleToUInt64Bits(value);

        return ((uint)(bits >> 32), (uint)bits);
    }

    /// <summary>Read a high and low word pair as an IEEE-754 double.</summary>
    public static double DecodeWide(uint high, uint low) =>
        BitConverter.UInt64BitsToDouble(((ulong)high << 32) | low);

    // A NaN operand passes straight through the unary operations,
    // bits and all, which is what IEEE 754 says of a quiet NaN. The
    // sign of a NaN is observable in Glulx, but nothing says which one
    // an operation must produce, and the C libraries disagree with
    // each other and with themselves; propagating is uniform instead.
    private static Action<Machine, Operand[]> Unary(Func<double, double> function) =>
        (machine, args) =>
        {
            var value = Decode(args[0].Value);

            machine.Store(args[1].Target, double.IsNaN(value) ? args[0].Value : Encode(function(value)));
        };

    private static Action<Machine, Operand[]> Binary(Func<double, double, double> function) =>
        (machine, args) => machine.Store(args[2].Target, Encode(function(Decode(args[0].Value), Decode(args[1].Value))));

    private static Action<Machine, Operand[]> UnaryWide(Func<double, double> function) =>
        (machine, args) =>
        {
            var value = DecodeWide(args[0].Value, args[1].Value);
            var (high, low) = double.IsNaN(value)
                ? (args[0].Value, args[1].Value)
                : EncodeWide(function(value));

            machine.Store(args[2].Target, low);
            machine.Store(args[3].Target, high);
        };

    private static Action<Machine, Operand[]> BinaryWide(Func<double, double, double> function) =>
        (machine, args) =>
        {
            var (high, low) = EncodeWide(function(
                DecodeWide(args[0].Value, args[1].Value),
                DecodeWide(args[2].Value, args[3].Value)));

            machine.Store(args[4].Target, low);
            machine.Store(args[5].Target, high);
        };

    private static Action<Machine, Operand[]> Compare(Func<double, double, bool> test) =>
        (machine, args) =>
        {
            if (test(Decode(args[0].Value), Decode(args[1].Value)))
            {
                machine.Jump(args[2].Value);
            }
        };

    private static Action<Machine, Operand[]> CompareWide(Func<double, double, bool> test) =>
        (machine, args) =>
        {
            if (test(DecodeWide(args[0].Value, args[1].Value), DecodeWide(args[2].Value, args[3].Value)))
            {
                machine.Jump(args[4].Value);
            }
        };

    private static Action<Machine, Operand[]> Test(Func<double, bool> test) =>
        (machine, args) =>
        {
            if (test(Decode(args[0].Value)))
            {
                machine.Jump(args[1].Value);
            }
        };

    private static Action<Machine, Operand[]> TestWide(Func<double, bool> test) =>
        (machine, args) =>
        {
            if (test(DecodeWide(args[0].Value, args[1].Value)))
            {
                machine.Jump(args[2].Value);
            }
        };

    // jfeq and its reverse, so that any NaN branches on jfne.
    private static Action<Machine, Operand[]> Near(bool wanted) =>
        (machine, args) =>
        {
            if (Close(Decode(args[0].Value), Decode(args[1].Value), Decode(args[2].Value)) == wanted)
            {
                machine.Jump(args[3].Value);
            }
        };

    private static Action<Machine, Operand[]> NearWide(bool wanted) =>
        (machine, args) =>
        {
            var close = Close(
                DecodeWide(args[0].Value, args[1].Value),
                DecodeWide(args[2].Value, args[3].Value),
                DecodeWide(args[4].Value, args[5].Value));

            if (close == wanted)
            {
                machine.Jump(args[6].Value);
            }
        };

    private static Action<Machine, Operand[]> ToNumber(bool nearest) =>
        (machine, args) => machine.Store(args[1].Target, ToInt(Decode(args[0].Value), nearest));

    private static Action<Machine, Operand[]> ToNumberWide(bool nearest) =>
        (machine, args) => machine.Store(args[2].Target, ToInt(DecodeWide(args[0].Value, args[1].Value), nearest));

    // fmod: remainder and quotient at once.
    private static void Fmod(Machine machine, Operand[] args)
    {
        var (remainder, quotient) = Modulo(Decode(args[0].Value), Decode(args[1].Value));
        var encoded = Encode(quotient);

        if (encoded is 0 or Sign)
        {
            // A zero quotient has lost its sign in the arithmetic; the
            // reference recovers it from the arguments' signs.
            encoded = (args[0].Value ^ args[1].Value) & Sign;
        }

        machine.Store(args[2].Target, Encode(remainder));
        machine.Store(args[3].Target, encoded);
    }

    // The engine of dmodr and dmodq: remainder or quotient.
    private static Action<Machine, Operand[]> Dmod(bool quotientWanted) =>
        (machine, args) =>
        {
            var (remainder, quotient) = Modulo(
                DecodeWide(args[0].Value, args[1].Value),
                DecodeWide(args[2].Value, args[3].Value));
            var (high, low) = EncodeWide(quotientWanted ? quotient : remainder);

            if (quotientWanted && low == 0 && high is 0 or Sign)
            {
                // As in fmod: a zero quotient takes its sign from the
                // arguments.
                high = (args[0].Value ^ args[2].Value) & Sign;
            }

            machine.Store(args[4].Target, low);
            machine.Store(args[5].Target, high);
        };

    // A double result stores low word first, which is the asymmetry
    // the specification calls out.
    private static void StoreWide(Machine machine, Operand[] args, int first, double value)
    {
        var (high, low) = EncodeWide(value);

        machine.Store(args[first].Target, low);
        machine.Store(args[first + 1].Target, high);
    }

    // A float as a 32-bit integer, saturated (Glulx: Floating-Point
    // Math).
    private static uint ToInt(double value, bool nearest)
    {
        if (double.IsNegative(value))
        {
            if (double.IsNaN(value) || double.IsInfinity(value) || value < -Saturation)
            {
                return IntMin;
            }
        }
        else if (double.IsNaN(value) || double.IsInfinity(value) || value > Saturation)
        {
            return IntMax;
        }

        return (uint)(int)(nearest ? Math.Round(value) : Math.Truncate(value));
    }

    // The root: a negative answers NaN, and minus zero stays itself.
    private static double Root(double value) => value == 0.0 ? value : value < 0 ? Nan : Math.Sqrt(value);

    // The logarithm: both zeroes give negative infinity, and a
    // negative gives NaN.
    private static double Logarithm(double value) => value == 0.0
        ? double.NegativeInfinity
        : value < 0 ? Nan : Math.Log(value);

    // A trigonometric call, its NaN made this module's own: the
    // Python's library raises where C answers, and its wrapper
    // answers with a positive NaN.
    private static Func<double, double> Trig(Func<double, double> function) => value =>
    {
        var answer = function(value);

        return double.IsNaN(answer) ? Nan : answer;
    };

    // IEEE division: a zero denominator gives infinity, or NaN where
    // the numerator cannot say which infinity.
    private static double Divide(double a, double b)
    {
        if (b != 0.0)
        {
            return a / b;
        }

        return a == 0.0 || double.IsNaN(a)
            ? Nan
            : Math.CopySign(double.PositiveInfinity, a) * Math.CopySign(1.0, b);
    }

    // The (remainder, quotient) pair fmod and dmod speak. An infinite
    // divisor leaves the value alone with a zero quotient; an infinite
    // dividend or a zero divisor gives NaN for both (Glulx:
    // Floating-Point Math).
    private static (double Remainder, double Quotient) Modulo(double a, double b)
    {
        if (double.IsNaN(a) || double.IsNaN(b) || double.IsInfinity(a) || b == 0.0)
        {
            return (Nan, Nan);
        }

        if (double.IsInfinity(b))
        {
            return (a, 0.0);
        }

        var remainder = a % b;

        return (remainder, Divide(a - remainder, b));
    }

    // Power, with the special cases a strict library is not required
    // to answer 1 for: one to any power, anything to the zeroth, and
    // minus one to an infinite power.
    private static double Power(double numeral, double exponent)
    {
        // A NaN operand passes through, which is what the Python's own
        // library does before anything else.
        if (double.IsNaN(numeral))
        {
            return exponent == 0.0 ? 1.0 : numeral;
        }

        if (double.IsNaN(exponent))
        {
            return numeral == 1.0 ? 1.0 : exponent;
        }

        if (numeral == 1.0 || exponent == 0.0)
        {
            return 1.0;
        }

        if (numeral == -1.0 && double.IsInfinity(exponent))
        {
            return 1.0;
        }

        if (numeral == 0.0 && exponent < 0)
        {
            // A zero to a negative power is infinite, negative only
            // when the zero is negative and the exponent an odd
            // integer.
            var odd = Math.Abs(exponent) < ExactIntegers
                && exponent == Math.Truncate(exponent)
                && (long)exponent % 2 != 0;

            return double.IsNegative(numeral) && odd ? double.NegativeInfinity : double.PositiveInfinity;
        }

        var answer = Math.Pow(numeral, exponent);

        return double.IsNaN(answer) ? Nan : answer;
    }

    // The jfeq and jdeq test (Glulx: Floating-Point Comparisons).
    // Infinities are settled before epsilon is consulted: two
    // infinities are equal exactly when their signs match, whatever
    // epsilon says. Only then does an infinite epsilon make everything
    // else equal.
    private static bool Close(double a, double b, double epsilon)
    {
        if (double.IsNaN(a) || double.IsNaN(b) || double.IsNaN(epsilon))
        {
            return false;
        }

        if (double.IsInfinity(a) && double.IsInfinity(b))
        {
            return double.IsNegative(a) == double.IsNegative(b);
        }

        return double.IsInfinity(epsilon) || Math.Abs(a - b) <= Math.Abs(epsilon);
    }
}
