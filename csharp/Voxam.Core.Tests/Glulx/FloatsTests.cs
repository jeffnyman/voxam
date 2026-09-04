using System.Security.Cryptography;
using Voxam.Core.Glulx;

namespace Voxam.Tests.Glulx;

/// <summary>
/// The floating-point and double-precision opcodes (Glulx:
/// Floating-Point Numbers, Glulx: Double-Precision Floating-Point
/// Numbers).
///
/// The breadth here is one probe rather than sixty-one tests: a
/// program that runs every opcode over seventeen values, twenty-seven
/// operand pairs and four epsilons.
///
/// Its results come back in two halves, and the reason is worth
/// knowing. IEEE 754 pins down addition, subtraction, multiplication,
/// division, remainder and the square root to the last bit, so those
/// answers are the same on every machine and a digest of them can be
/// written down; that digest was taken from the Python's own output,
/// running this program's own story file, which is what makes one
/// assertion worth more than sixty-one of mine. It does not pin down
/// sine, logarithm or power, so those answers belong to whichever
/// library the platform ships, and the Python is handed the same one.
/// The two implementations therefore agree machine for machine, and
/// no constant could be true on all three at once. What is portable
/// about them is checked instead: that each opcode reaches the
/// function it names, and that the cases the specification does fix,
/// the infinities and the NaNs, come out fixed.
/// </summary>
public sealed class FloatsTests
{
    // The results sit above the stored image, clear of the program
    // itself, which is tens of thousands of bytes of assembled
    // instructions.
    private const int Exact = 65536;
    private const int Library = 98304;

    private static readonly double[] Singles =
    [
        0.0, -0.0, 1.0, -1.0, 2.5, -2.5, 0.5, 3.0, 7.0, -7.0,
        double.PositiveInfinity, double.NegativeInfinity, double.NaN, 1e30, 1e-30, 1234.5678,
        // A NaN with its sign bit clear, which the runtime's own
        // constant does not have.
        BitConverter.UInt64BitsToDouble(0x7FF8000000000000UL),
    ];

    private static readonly (double A, double B)[] Pairs =
    [
        (1.0, 2.0), (-1.0, 2.0), (2.5, 0.5), (0.0, 0.0), (1.0, 0.0), (-1.0, 0.0),
        (0.0, -0.0), (double.PositiveInfinity, 1.0), (double.NaN, 1.0), (2.0, -0.5),
        (-8.0, 1.0 / 3.0), (7.0, 3.0), (-7.0, 3.0), (7.0, -3.0), (1.0, double.PositiveInfinity),
        (double.PositiveInfinity, double.PositiveInfinity), (1e30, 1e30), (-1.0, double.PositiveInfinity),
        // A quotient that comes out as negative zero, a NaN on the
        // right rather than the left, and the zero bases whose
        // negative powers pow has to answer for by hand.
        (1.0, -2.0), (1.0, double.NaN), (double.NaN, 0.0), (2.0, double.NaN),
        (0.0, -1.0), (-0.0, -1.0), (0.0, -2.0), (-0.0, -2.5), (0.0, -1e30),
    ];

    // The operations IEEE 754 fixes to the last bit.
    private static readonly Op[] ExactUnary = [Op.Ceil, Op.Floor, Op.Sqrt, Op.Ftonumz, Op.Ftonumn];

    private static readonly Op[] ExactBinary = [Op.Fadd, Op.Fsub, Op.Fmul, Op.Fdiv];

    private static readonly Op[] ExactWideUnary = [Op.Dceil, Op.Dfloor, Op.Dsqrt];

    private static readonly Op[] ExactWideBinary = [Op.Dadd, Op.Dsub, Op.Dmul, Op.Ddiv];

    // And the ones it leaves to the platform's own library.
    private static readonly Op[] LibraryUnary =
    [
        Op.Exp, Op.Log, Op.Sin, Op.Cos, Op.Tan, Op.Asin, Op.Acos, Op.Atan,
    ];

    private static readonly Op[] LibraryBinary = [Op.Pow, Op.Atan2];

    private static readonly Op[] LibraryWideUnary =
    [
        Op.Dexp, Op.Dlog, Op.Dsin, Op.Dcos, Op.Dtan, Op.Dasin, Op.Dacos, Op.Datan,
    ];

    private static readonly Op[] LibraryWideBinary = [Op.Dpow, Op.Datan2];

    private static readonly Op[] Comparisons = [Op.Jflt, Op.Jfle, Op.Jfgt, Op.Jfge];

    private static readonly Op[] WideComparisons = [Op.Jdlt, Op.Jdle, Op.Jdgt, Op.Jdge];

    // Everything the specification fixes, digested. Re-certify with
    // the scratchpad's floats_reference.py against the story this
    // writes.
    [Fact]
    public void EveryExactOpcodeAnswersAsTheReferenceDoes()
    {
        var (exact, widths, library) = Probe();

        Assert.Equal(1525, exact.Length);
        Assert.Equal(570, library.Length);
        Assert.Equal(
            "681a299d88228e2dd6681ca58ebdf3fc3a3c6564416f85aaf0a08dd39d5c0197",
            Convert.ToHexString(SHA256.HashData(
                Normalized(exact, widths).SelectMany(BitConverter.GetBytes).ToArray())).ToLowerInvariant());
    }

    // The sign of a NaN is the other thing no constant can carry, and
    // it is the processor's doing rather than the library's: an x86
    // makes its default NaN with the sign bit set and an ARM makes the
    // same NaN with it clear, so infinity less infinity comes out
    // differently on a Mac than on the machine this was written on.
    // The Python is handed the same processor, so the two still agree
    // there; what cannot travel is the constant. The payload does
    // travel, and stays in the digest.
    [Fact]
    public void TheDigestDoesNotDependOnWhichNaNTheProcessorMakes()
    {
        var (exact, widths, _) = Probe();
        var flipped = exact.ToArray();

        for (var at = 0; at < flipped.Length; at++)
        {
            if (IsNaNAt(flipped, widths, at))
            {
                flipped[at] ^= 0x80000000;
            }
        }

        Assert.NotEqual(exact, flipped);
        Assert.Equal(Normalized(exact, widths), Normalized(flipped, widths));
    }

    // What is portable about the library functions is that each
    // opcode reaches the one it names, at the width it names. The
    // values here sit inside every domain, so no special case fires
    // and the answer is simply the runtime's own.
    [Fact]
    public void EveryLibraryOpcodeReachesTheFunctionItNames()
    {
        (Op Single, Op Wide, Func<double, double> Function)[] family =
        [
            (Op.Exp, Op.Dexp, Math.Exp),
            (Op.Log, Op.Dlog, Math.Log),
            (Op.Sin, Op.Dsin, Math.Sin),
            (Op.Cos, Op.Dcos, Math.Cos),
            (Op.Tan, Op.Dtan, Math.Tan),
            (Op.Asin, Op.Dasin, Math.Asin),
            (Op.Acos, Op.Dacos, Math.Acos),
            (Op.Atan, Op.Datan, Math.Atan),
        ];

        foreach (var (single, wide, function) in family)
        {
            foreach (var value in (double[])[0.25, 0.5, 1.0])
            {
                var program = new GlulxProgram();
                var (high, low) = Floats.EncodeWide(value);
                program.Op(single, Modes.Word(Floats.Encode(value)), Modes.Memory(0x140));
                program.Op(wide, Modes.Word(high), Modes.Word(low), Modes.Memory(0x144), Modes.Memory(0x148));
                program.Op(Op.Quit);
                var machine = program.Booted();
                machine.Run();

                var (wantedHigh, wantedLow) = Floats.EncodeWide(function(value));

                Assert.Equal(Floats.Encode(function(Floats.Decode(Floats.Encode(value)))), machine.Memory.ReadWord(0x140));
                Assert.Equal(wantedLow, machine.Memory.ReadWord(0x144));
                Assert.Equal(wantedHigh, machine.Memory.ReadWord(0x148));
            }
        }
    }

    [Fact]
    public void ThePairedLibraryOpcodesReachTheirsToo()
    {
        var program = new GlulxProgram();
        var (twoHigh, twoLow) = Floats.EncodeWide(2.0);
        var (threeHigh, threeLow) = Floats.EncodeWide(3.0);
        program.Op(Op.Pow, Modes.Word(Floats.Encode(2.0)), Modes.Word(Floats.Encode(3.0)), Modes.Memory(0x140));
        program.Op(Op.Atan2, Modes.Word(Floats.Encode(2.0)), Modes.Word(Floats.Encode(3.0)), Modes.Memory(0x144));
        program.Op(Op.Dpow, Modes.Word(twoHigh), Modes.Word(twoLow), Modes.Word(threeHigh), Modes.Word(threeLow),
            Modes.Memory(0x148), Modes.Memory(0x14C));
        program.Op(Op.Datan2, Modes.Word(twoHigh), Modes.Word(twoLow), Modes.Word(threeHigh), Modes.Word(threeLow),
            Modes.Memory(0x150), Modes.Memory(0x154));
        program.Op(Op.Quit);
        var machine = program.Booted();
        machine.Run();

        var (powHigh, powLow) = Floats.EncodeWide(8.0);
        var (atanHigh, atanLow) = Floats.EncodeWide(Math.Atan2(2.0, 3.0));

        Assert.Equal(Floats.Encode(8.0), machine.Memory.ReadWord(0x140));
        Assert.Equal(Floats.Encode(Math.Atan2(2.0, 3.0)), machine.Memory.ReadWord(0x144));
        Assert.Equal(powLow, machine.Memory.ReadWord(0x148));
        Assert.Equal(powHigh, machine.Memory.ReadWord(0x14C));
        Assert.Equal(atanLow, machine.Memory.ReadWord(0x150));
        Assert.Equal(atanHigh, machine.Memory.ReadWord(0x154));
    }

    // The cases the specification does fix for the library functions:
    // the infinities and the NaNs, which every platform must agree on.
    [Theory]
    [InlineData(Op.Log, 0.0, 0xFF800000u)]
    [InlineData(Op.Log, -1.0, 0x7FC00000u)]
    [InlineData(Op.Exp, 1000.0, 0x7F800000u)]
    [InlineData(Op.Exp, double.NegativeInfinity, 0x00000000u)]
    [InlineData(Op.Sqrt, -1.0, 0x7FC00000u)]
    [InlineData(Op.Sqrt, -0.0, 0x80000000u)]
    [InlineData(Op.Asin, 2.0, 0x7FC00000u)]
    [InlineData(Op.Acos, 2.0, 0x7FC00000u)]
    [InlineData(Op.Sin, double.PositiveInfinity, 0x7FC00000u)]
    public void TheFixedCasesOfTheLibraryFunctionsComeOutFixed(Op opcode, double value, uint answer)
    {
        var program = new GlulxProgram();
        program.Op(opcode, Modes.Word(Floats.Encode(value)), Modes.Memory(0x140));
        program.Op(Op.Quit);
        var machine = program.Booted();
        machine.Run();

        Assert.Equal(answer, machine.Memory.ReadWord(0x140));
    }

    // One to any power and anything to the zeroth are one, and a zero
    // base to a negative power is infinite: three a strict library is
    // not required to answer for, which glulxe adds by hand.
    [Theory]
    [InlineData(1.0, double.NaN, 0x3F800000u)]
    [InlineData(double.NaN, 0.0, 0x3F800000u)]
    [InlineData(-1.0, double.PositiveInfinity, 0x3F800000u)]
    [InlineData(0.0, -1.0, 0x7F800000u)]
    [InlineData(-0.0, -1.0, 0xFF800000u)]
    [InlineData(-0.0, -2.0, 0x7F800000u)]
    [InlineData(-2.0, 0.5, 0x7FC00000u)]
    public void PowersOfTheAwkwardKindAreAnsweredByHand(double numeral, double exponent, uint answer)
    {
        var program = new GlulxProgram();
        program.Op(Op.Pow, Modes.Word(Floats.Encode(numeral)), Modes.Word(Floats.Encode(exponent)), Modes.Memory(0x140));
        program.Op(Op.Quit);
        var machine = program.Booted();
        machine.Run();

        Assert.Equal(answer, machine.Memory.ReadWord(0x140));
    }

    // A double argument is high word first, but a double result stores
    // low word first: the asymmetry the specification calls out, and
    // getting it backwards would swap every double a game computes.
    [Fact]
    public void ADoubleArrivesHighWordFirstAndLeavesLowWordFirst()
    {
        var program = new GlulxProgram();
        var (high, low) = Floats.EncodeWide(2.5);
        program.Op(Op.Dadd, Modes.Word(high), Modes.Word(low), Modes.Word(high), Modes.Word(low),
            Modes.Memory(0x140), Modes.Memory(0x144));
        program.Op(Op.Quit);
        var machine = program.Booted();
        machine.Run();

        var (wanted, wantedLow) = Floats.EncodeWide(5.0);

        Assert.Equal(wantedLow, machine.Memory.ReadWord(0x140));
        Assert.Equal(wanted, machine.Memory.ReadWord(0x144));
    }

    // A float too large for an integer saturates rather than wrapping,
    // and glulxe compares against 2147483647 in both directions.
    [Theory]
    [InlineData(3.7, 3u, 4u)]
    [InlineData(-3.7, 0xFFFFFFFDu, 0xFFFFFFFCu)]
    [InlineData(1e30, 0x7FFFFFFFu, 0x7FFFFFFFu)]
    [InlineData(-1e30, 0x80000000u, 0x80000000u)]
    [InlineData(double.PositiveInfinity, 0x7FFFFFFFu, 0x7FFFFFFFu)]
    [InlineData(double.NegativeInfinity, 0x80000000u, 0x80000000u)]
    public void AFloatBecomesAnIntegerBySaturating(double value, uint truncated, uint nearest)
    {
        var program = new GlulxProgram();
        program.Op(Op.Ftonumz, Modes.Word(Floats.Encode(value)), Modes.Memory(0x140));
        program.Op(Op.Ftonumn, Modes.Word(Floats.Encode(value)), Modes.Memory(0x144));
        program.Op(Op.Quit);
        var machine = program.Booted();
        machine.Run();

        Assert.Equal(truncated, machine.Memory.ReadWord(0x140));
        Assert.Equal(nearest, machine.Memory.ReadWord(0x144));
    }

    // A NaN passes through a unary operation whole, bits and all,
    // which is what IEEE 754 says of a quiet NaN and what keeps the
    // answer the same on every platform.
    [Fact]
    public void ANaNPassesThroughAUnaryOperationWhole()
    {
        var program = new GlulxProgram();
        program.Op(Op.Sqrt, Modes.Word(0xFFC00042), Modes.Memory(0x140));
        program.Op(Op.Sqrt, Modes.Word(Floats.Encode(-1.0)), Modes.Memory(0x144));
        program.Op(Op.Quit);
        var machine = program.Booted();
        machine.Run();

        Assert.Equal(0xFFC00042u, machine.Memory.ReadWord(0x140));
        // A NaN the operation made for itself is this machine's own,
        // with the sign bit clear.
        Assert.Equal(0x7FC00000u, machine.Memory.ReadWord(0x144));
    }

    // Two infinities are equal exactly when their signs match,
    // whatever epsilon says; only then does an infinite epsilon make
    // everything else equal.
    [Theory]
    [InlineData(1.0, 1.5, 1.0, true)]
    [InlineData(1.0, 1.5, 0.25, false)]
    [InlineData(double.PositiveInfinity, double.PositiveInfinity, 0.0, true)]
    [InlineData(double.PositiveInfinity, double.NegativeInfinity, double.PositiveInfinity, false)]
    [InlineData(1.0, 1000.0, double.PositiveInfinity, true)]
    [InlineData(1.0, 1.0, double.NaN, false)]
    public void EqualityIsWithinAnEpsilonAndInfinitiesSettleFirst(double a, double b, double epsilon, bool near)
    {
        var program = new GlulxProgram();
        program.Op(Op.Copy, Modes.Constant(0), Modes.Memory(0x140));
        program.Op(Op.Jfeq, Modes.Word(Floats.Encode(a)), Modes.Word(Floats.Encode(b)),
            Modes.Word(Floats.Encode(epsilon)), Modes.Word(0));
        var after = program.Here;
        program.Op(Op.Copy, Modes.Constant(1), Modes.Memory(0x140));
        program.Patch(after - 4, (uint)(program.Here - after + 2));
        program.Op(Op.Quit);
        var machine = program.Booted();
        machine.Run();

        Assert.Equal(near ? 0u : 1u, machine.Memory.ReadWord(0x140));
    }

    // A zero quotient has lost its sign in the arithmetic, so fmod and
    // dmodq recover it from the arguments.
    [Fact]
    public void AZeroQuotientTakesItsSignFromItsArguments()
    {
        var program = new GlulxProgram();
        program.Op(Op.Fmod, Modes.Word(Floats.Encode(1.0)), Modes.Word(Floats.Encode(-2.0)),
            Modes.Memory(0x140), Modes.Memory(0x144));
        program.Op(Op.Quit);
        var machine = program.Booted();
        machine.Run();

        Assert.Equal(Floats.Encode(1.0), machine.Memory.ReadWord(0x140));
        Assert.Equal(0x80000000u, machine.Memory.ReadWord(0x144));
    }

    // A NaN result with its sign bit cleared; everything else as it
    // stands. Which NaN an operation produces is not something the
    // specification fixes, so it is not something a digest may carry.
    private static uint[] Normalized(uint[] results, Width[] widths)
    {
        var normalized = results.ToArray();

        for (var at = 0; at < normalized.Length; at++)
        {
            if (IsNaNAt(normalized, widths, at))
            {
                normalized[at] &= 0x7FFFFFFF;
            }
        }

        return normalized;
    }

    // Whether the slot holds the sign-bearing word of a NaN: a single
    // in its own right, or the high word of a double. An integer or a
    // branch flag is left alone, since its bits mean something else.
    private static bool IsNaNAt(uint[] results, Width[] widths, int at) => widths[at] switch
    {
        Width.Single => float.IsNaN(BitConverter.UInt32BitsToSingle(results[at])),
        Width.High => double.IsNaN(Floats.DecodeWide(results[at], results[at - 1])),
        _ => false,
    };

    private static (uint[] Exact, Width[] Widths, uint[] Library) Probe()
    {
        var program = new GlulxProgram(at: 256) { ImageSize = 65536, EndMem = 262144, StackSize = 4096 };
        var exact = (uint)Exact;
        var library = (uint)Library;
        var widths = new List<Width>();

        uint NextExact(Width width)
        {
            var at = exact;
            exact += 4;
            widths.Add(width);

            return at;
        }

        uint NextLibrary()
        {
            var at = library;
            library += 4;

            return at;
        }

        void Skipping(Op opcode, Slot[] operands)
        {
            var mark = NextExact(Width.Opaque);
            program.Op(Op.Copy, Modes.Constant(0), Modes.Memory(mark));
            program.Op(opcode, [.. operands, Modes.Word(0)]);
            var after = program.Here;
            program.Op(Op.Copy, Modes.Constant(1), Modes.Memory(mark));
            program.Patch(after - 4, (uint)(program.Here - after + 2));
        }

        foreach (var opcode in ExactUnary)
        {
            foreach (var value in Singles)
            {
                program.Op(opcode, Modes.Word(Floats.Encode(value)),
                    Modes.Memory(NextExact(opcode is Op.Ftonumz or Op.Ftonumn ? Width.Opaque : Width.Single)));
            }
        }

        foreach (var opcode in LibraryUnary)
        {
            foreach (var value in Singles)
            {
                program.Op(opcode, Modes.Word(Floats.Encode(value)), Modes.Memory(NextLibrary()));
            }
        }

        foreach (var value in Singles)
        {
            program.Op(Op.Numtof, Modes.Word((uint)(int)value.ClampToInt()), Modes.Memory(NextExact(Width.Single)));
            program.Op(Op.Ftod, Modes.Word(Floats.Encode(value)), Modes.Memory(NextExact(Width.Low)), Modes.Memory(NextExact(Width.High)));
            program.Op(Op.Numtod, Modes.Word((uint)(int)value.ClampToInt()), Modes.Memory(NextExact(Width.Low)), Modes.Memory(NextExact(Width.High)));

            var (high, low) = Floats.EncodeWide(value);
            program.Op(Op.Dtof, Modes.Word(high), Modes.Word(low), Modes.Memory(NextExact(Width.Single)));
            program.Op(Op.Dtonumz, Modes.Word(high), Modes.Word(low), Modes.Memory(NextExact(Width.Opaque)));
            program.Op(Op.Dtonumn, Modes.Word(high), Modes.Word(low), Modes.Memory(NextExact(Width.Opaque)));
            program.Op(Op.Jisnan, Modes.Word(Floats.Encode(value)), Modes.Constant(2));
            program.Op(Op.Jisinf, Modes.Word(Floats.Encode(value)), Modes.Constant(2));
            Skipping(Op.Jisnan, [Modes.Word(Floats.Encode(value))]);
            Skipping(Op.Jisinf, [Modes.Word(Floats.Encode(value))]);
            Skipping(Op.Jdisnan, [Modes.Word(high), Modes.Word(low)]);
            Skipping(Op.Jdisinf, [Modes.Word(high), Modes.Word(low)]);
        }

        foreach (var opcode in ExactWideUnary)
        {
            foreach (var value in Singles)
            {
                var (high, low) = Floats.EncodeWide(value);
                program.Op(opcode, Modes.Word(high), Modes.Word(low), Modes.Memory(NextExact(Width.Low)), Modes.Memory(NextExact(Width.High)));
            }
        }

        foreach (var opcode in LibraryWideUnary)
        {
            foreach (var value in Singles)
            {
                var (high, low) = Floats.EncodeWide(value);
                program.Op(opcode, Modes.Word(high), Modes.Word(low), Modes.Memory(NextLibrary()), Modes.Memory(NextLibrary()));
            }
        }

        foreach (var (a, b) in Pairs)
        {
            var (ah, al) = Floats.EncodeWide(a);
            var (bh, bl) = Floats.EncodeWide(b);

            foreach (var opcode in ExactBinary)
            {
                program.Op(opcode, Modes.Word(Floats.Encode(a)), Modes.Word(Floats.Encode(b)), Modes.Memory(NextExact(Width.Single)));
            }

            foreach (var opcode in LibraryBinary)
            {
                program.Op(opcode, Modes.Word(Floats.Encode(a)), Modes.Word(Floats.Encode(b)), Modes.Memory(NextLibrary()));
            }

            program.Op(Op.Fmod, Modes.Word(Floats.Encode(a)), Modes.Word(Floats.Encode(b)), Modes.Memory(NextExact(Width.Single)), Modes.Memory(NextExact(Width.Single)));

            foreach (var opcode in ExactWideBinary)
            {
                program.Op(opcode, Modes.Word(ah), Modes.Word(al), Modes.Word(bh), Modes.Word(bl), Modes.Memory(NextExact(Width.Low)), Modes.Memory(NextExact(Width.High)));
            }

            foreach (var opcode in LibraryWideBinary)
            {
                program.Op(opcode, Modes.Word(ah), Modes.Word(al), Modes.Word(bh), Modes.Word(bl), Modes.Memory(NextLibrary()), Modes.Memory(NextLibrary()));
            }

            program.Op(Op.Dmodr, Modes.Word(ah), Modes.Word(al), Modes.Word(bh), Modes.Word(bl), Modes.Memory(NextExact(Width.Low)), Modes.Memory(NextExact(Width.High)));
            program.Op(Op.Dmodq, Modes.Word(ah), Modes.Word(al), Modes.Word(bh), Modes.Word(bl), Modes.Memory(NextExact(Width.Low)), Modes.Memory(NextExact(Width.High)));

            foreach (var opcode in Comparisons)
            {
                Skipping(opcode, [Modes.Word(Floats.Encode(a)), Modes.Word(Floats.Encode(b))]);
            }

            foreach (var opcode in WideComparisons)
            {
                Skipping(opcode, [Modes.Word(ah), Modes.Word(al), Modes.Word(bh), Modes.Word(bl)]);
            }

            foreach (var epsilon in (double[])[0.0, 0.5, double.PositiveInfinity, double.NaN])
            {
                Skipping(Op.Jfeq, [Modes.Word(Floats.Encode(a)), Modes.Word(Floats.Encode(b)), Modes.Word(Floats.Encode(epsilon))]);
                Skipping(Op.Jfne, [Modes.Word(Floats.Encode(a)), Modes.Word(Floats.Encode(b)), Modes.Word(Floats.Encode(epsilon))]);

                var (eh, el) = Floats.EncodeWide(epsilon);
                Skipping(Op.Jdeq, [Modes.Word(ah), Modes.Word(al), Modes.Word(bh), Modes.Word(bl), Modes.Word(eh), Modes.Word(el)]);
                Skipping(Op.Jdne, [Modes.Word(ah), Modes.Word(al), Modes.Word(bh), Modes.Word(bl), Modes.Word(eh), Modes.Word(el)]);
            }
        }

        program.Op(Op.Quit);

        var machine = new Machine(new Story(program.Build()), 777);
        machine.Run(50000);

        return (
            Read(machine, Exact, (int)((exact - Exact) / 4)),
            [.. widths],
            Read(machine, Library, (int)((library - Library) / 4)));
    }

    /// <summary>What a result slot holds, so a NaN in it can be recognized.</summary>
    private enum Width
    {
        /// <summary>An integer or a branch flag, whose bits mean something else.</summary>
        Opaque,

        /// <summary>A single-precision result.</summary>
        Single,

        /// <summary>A double's low word, which carries no sign of its own.</summary>
        Low,

        /// <summary>A double's high word, which does.</summary>
        High,
    }

    private static uint[] Read(Machine machine, int start, int count) =>
        [.. Enumerable.Range(0, count).Select(at => machine.Memory.ReadWord(start + (4 * at)))];
}

internal static class Clamping
{
    // A test value as the integer numtof and numtod will be handed.
    public static double ClampToInt(this double value) => double.IsNaN(value)
        ? 0
        : Math.Clamp(value, int.MinValue, int.MaxValue);
}
