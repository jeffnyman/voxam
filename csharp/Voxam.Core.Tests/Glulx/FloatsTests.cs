using System.Security.Cryptography;
using Voxam.Core.Glulx;

namespace Voxam.Tests.Glulx;

/// <summary>
/// The floating-point and double-precision opcodes (Glulx:
/// Floating-Point Numbers, Glulx: Double-Precision Floating-Point
/// Numbers).
///
/// The breadth here is one probe rather than sixty-one tests: a
/// program that runs every opcode over sixteen values, eighteen
/// operand pairs and four epsilons, and a digest of all 1,616 results.
/// That digest was certified against the Python by running this
/// program's own story file under both machines, which is what makes
/// one assertion worth more than sixty-one of mine. The named tests
/// below it are the rules a reader should be able to find.
/// </summary>
public sealed class FloatsTests
{
    // The results sit above the stored image, clear of the program
    // itself, which is tens of thousands of bytes of assembled
    // instructions.
    private const int Slots = 65536;

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

    private static readonly Op[] Unary =
    [
        Op.Ceil, Op.Floor, Op.Sqrt, Op.Exp, Op.Log, Op.Sin, Op.Cos, Op.Tan,
        Op.Asin, Op.Acos, Op.Atan, Op.Ftonumz, Op.Ftonumn,
    ];

    private static readonly Op[] Binary = [Op.Fadd, Op.Fsub, Op.Fmul, Op.Fdiv, Op.Pow, Op.Atan2];

    private static readonly Op[] WideUnary =
    [
        Op.Dceil, Op.Dfloor, Op.Dsqrt, Op.Dexp, Op.Dlog, Op.Dsin, Op.Dcos, Op.Dtan,
        Op.Dasin, Op.Dacos, Op.Datan,
    ];

    private static readonly Op[] WideBinary = [Op.Dadd, Op.Dsub, Op.Dmul, Op.Ddiv, Op.Dpow, Op.Datan2];

    private static readonly Op[] Compare = [Op.Jflt, Op.Jfle, Op.Jfgt, Op.Jfge];

    private static readonly Op[] WideCompare = [Op.Jdlt, Op.Jdle, Op.Jdgt, Op.Jdge];

    // Every opcode, over every value and pair, digested. Re-certify
    // with the scratchpad's floats_reference.py against the story this
    // writes.
    [Fact]
    public void EveryOpcodeAnswersAsTheReferenceDoes()
    {
        var results = Probe();

        Assert.Equal(2095, results.Length);
        Assert.Equal(
            "fd2c4c3e6f6d349d76821747ab22dd9a91491284d1097681506081e887d80acc",
            Convert.ToHexString(SHA256.HashData(results.SelectMany(BitConverter.GetBytes).ToArray())).ToLowerInvariant());
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

    private static uint[] Probe()
    {
        var program = new GlulxProgram(at: 256) { ImageSize = 65536, EndMem = 131072, StackSize = 4096 };
        var slot = (uint)Slots;

        uint Next()
        {
            var at = slot;
            slot += 4;

            return at;
        }

        void Skipping(Op opcode, Slot[] operands)
        {
            var mark = Next();
            program.Op(Op.Copy, Modes.Constant(0), Modes.Memory(mark));
            program.Op(opcode, [.. operands, Modes.Word(0)]);
            var after = program.Here;
            program.Op(Op.Copy, Modes.Constant(1), Modes.Memory(mark));
            program.Patch(after - 4, (uint)(program.Here - after + 2));
        }

        foreach (var opcode in Unary)
        {
            foreach (var value in Singles)
            {
                program.Op(opcode, Modes.Word(Floats.Encode(value)), Modes.Memory(Next()));
            }
        }

        foreach (var value in Singles)
        {
            program.Op(Op.Numtof, Modes.Word((uint)(int)value.ClampToInt()), Modes.Memory(Next()));
            program.Op(Op.Ftod, Modes.Word(Floats.Encode(value)), Modes.Memory(Next()), Modes.Memory(Next()));
            program.Op(Op.Numtod, Modes.Word((uint)(int)value.ClampToInt()), Modes.Memory(Next()), Modes.Memory(Next()));

            var (high, low) = Floats.EncodeWide(value);
            program.Op(Op.Dtof, Modes.Word(high), Modes.Word(low), Modes.Memory(Next()));
            program.Op(Op.Dtonumz, Modes.Word(high), Modes.Word(low), Modes.Memory(Next()));
            program.Op(Op.Dtonumn, Modes.Word(high), Modes.Word(low), Modes.Memory(Next()));
            program.Op(Op.Jisnan, Modes.Word(Floats.Encode(value)), Modes.Constant(2));
            program.Op(Op.Jisinf, Modes.Word(Floats.Encode(value)), Modes.Constant(2));
            Skipping(Op.Jisnan, [Modes.Word(Floats.Encode(value))]);
            Skipping(Op.Jisinf, [Modes.Word(Floats.Encode(value))]);
            Skipping(Op.Jdisnan, [Modes.Word(high), Modes.Word(low)]);
            Skipping(Op.Jdisinf, [Modes.Word(high), Modes.Word(low)]);
        }

        foreach (var opcode in WideUnary)
        {
            foreach (var value in Singles)
            {
                var (high, low) = Floats.EncodeWide(value);
                program.Op(opcode, Modes.Word(high), Modes.Word(low), Modes.Memory(Next()), Modes.Memory(Next()));
            }
        }

        foreach (var (a, b) in Pairs)
        {
            foreach (var opcode in Binary)
            {
                program.Op(opcode, Modes.Word(Floats.Encode(a)), Modes.Word(Floats.Encode(b)), Modes.Memory(Next()));
            }

            program.Op(Op.Fmod, Modes.Word(Floats.Encode(a)), Modes.Word(Floats.Encode(b)), Modes.Memory(Next()), Modes.Memory(Next()));

            var (ah, al) = Floats.EncodeWide(a);
            var (bh, bl) = Floats.EncodeWide(b);

            foreach (var opcode in WideBinary)
            {
                program.Op(opcode, Modes.Word(ah), Modes.Word(al), Modes.Word(bh), Modes.Word(bl), Modes.Memory(Next()), Modes.Memory(Next()));
            }

            program.Op(Op.Dmodr, Modes.Word(ah), Modes.Word(al), Modes.Word(bh), Modes.Word(bl), Modes.Memory(Next()), Modes.Memory(Next()));
            program.Op(Op.Dmodq, Modes.Word(ah), Modes.Word(al), Modes.Word(bh), Modes.Word(bl), Modes.Memory(Next()), Modes.Memory(Next()));

            foreach (var opcode in Compare)
            {
                Skipping(opcode, [Modes.Word(Floats.Encode(a)), Modes.Word(Floats.Encode(b))]);
            }

            foreach (var opcode in WideCompare)
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

        var count = (int)((slot - Slots) / 4);

        return [.. Enumerable.Range(0, count).Select(at => machine.Memory.ReadWord(Slots + (4 * at)))];
    }
}

internal static class Clamping
{
    // A test value as the integer numtof and numtod will be handed.
    public static double ClampToInt(this double value) => double.IsNaN(value)
        ? 0
        : Math.Clamp(value, int.MinValue, int.MaxValue);
}
