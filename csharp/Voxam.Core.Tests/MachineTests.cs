using System.Text;
using Voxam.Core.Tests.Support;

namespace Voxam.Core.Tests;

public class MachineTests
{
    private const int G0 = 0x10;
    private const int G1 = 0x11;

    private static void PrintNum(StoryBuilder b, Arg value) => b.OpVar(0x06, value);

    private static void PrintGlobal(StoryBuilder b, int variable)
    {
        PrintNum(b, Arg.Var(variable));
        b.NewLine();
    }

    [Fact]
    public void TextReachesTheStreamThroughEveryPrintOpcode()
    {
        var b = new StoryBuilder();
        var name = b.Bytes(StoryBuilder.ZString("dynamic"));
        b.Objects(new ObjectSpec("lamp"));
        b.Print("Hi");
        b.NewLine();
        PrintNum(b, Arg.Large(0xFFFB));
        b.OpVar(0x05, Arg.Small(65));
        b.Op1(0x7, Arg.Large(name));
        b.Op1(0xA, Arg.Small(1));
        // The call is five bytes, quit one, and "packed" four.
        var routine = b.Align(b.Here + 5 + 1 + 4);
        b.Call(routine, 0);
        b.Quit();
        // A string in high memory, printable by packed address.
        var packedString = b.Here;
        b.Raw(StoryBuilder.ZString("packed"));
        Assert.Equal(routine, b.Routine(0));
        b.Op1(0xD, Arg.Large(b.Packed(packedString)));
        b.PrintRet("done");

        var (output, machine) = Session.Run(b);
        Assert.Equal("Hi\n-5Adynamiclamppackeddone\n", output);
        Assert.Equal(10, machine.Instructions);
    }

    [Fact]
    public void ArithmeticIsSignedAndWraps()
    {
        var b = new StoryBuilder();
        b.Op2(0x14, Arg.Large(32767), Arg.Small(1));
        b.Store(G0);
        PrintGlobal(b, G0);
        b.Op2(0x15, Arg.Small(3), Arg.Small(10));
        b.Store(G0);
        PrintGlobal(b, G0);
        b.Op2(0x16, Arg.Large(0xFFFE), Arg.Small(3));
        b.Store(G0);
        PrintGlobal(b, G0);
        b.Op2(0x17, Arg.Large(0xFFF9), Arg.Small(2));
        b.Store(G0);
        PrintGlobal(b, G0);
        b.Op2(0x18, Arg.Large(0xFFF9), Arg.Small(2));
        b.Store(G0);
        PrintGlobal(b, G0);
        b.Op2(0x18, Arg.Small(7), Arg.Large(0xFFFE));
        b.Store(G0);
        PrintGlobal(b, G0);
        b.Op2(0x17, Arg.Large(0xFFF9), Arg.Large(0xFFFE));
        b.Store(G0);
        PrintGlobal(b, G0);
        b.Quit();
        var (output, _) = Session.Run(b);
        Assert.Equal("-32768\n-7\n-6\n-3\n-1\n1\n3\n", output);
    }

    [Fact]
    public void DivisionByZeroHalts()
    {
        var b = new StoryBuilder();
        b.Op2(0x17, Arg.Small(1), Arg.Small(0));
        b.Store(G0);
        b.Quit();
        Assert.Contains("division by zero at $1000", Session.Fails<ZMachineException>(b).Message, StringComparison.Ordinal);
    }

    [Fact]
    public void BitwiseOpcodesAreUnsigned()
    {
        var b = new StoryBuilder(5);
        b.Op2(0x08, Arg.Small(0x0F), Arg.Large(0xF0F0));
        b.Store(G0);
        PrintGlobal(b, G0);
        b.Op2(0x09, Arg.Large(0xF0FF), Arg.Large(0x0FF0));
        b.Store(G0);
        PrintGlobal(b, G0);
        b.OpVar(0x18, Arg.Small(1));
        b.Store(G0);
        PrintGlobal(b, G0);
        b.Ext(0x02, Arg.Small(3), Arg.Small(2));
        b.Store(G0);
        PrintGlobal(b, G0);
        b.Ext(0x02, Arg.Large(0x8000), Arg.Large(0xFFFF));
        b.Store(G0);
        PrintGlobal(b, G0);
        b.Ext(0x03, Arg.Large(0x8000), Arg.Large(0xFFFF));
        b.Store(G0);
        PrintGlobal(b, G0);
        b.Ext(0x03, Arg.Small(3), Arg.Small(1));
        b.Store(G0);
        PrintGlobal(b, G0);
        b.Quit();
        var (output, _) = Session.Run(b);
        Assert.Equal("-3841\n240\n-2\n12\n16384\n-16384\n6\n", output);
    }

    [Fact]
    public void VersionFourNotIsAOneOperandOpcode()
    {
        var b = new StoryBuilder(4);
        b.Op1(0xF, Arg.Small(0));
        b.Store(G0);
        PrintGlobal(b, G0);
        b.Quit();
        Assert.Equal("-1\n", Session.Run(b).Output);
    }

    [Fact]
    public void BranchesFollowTheirSenseAndTheirOffsets()
    {
        var b = new StoryBuilder();
        b.Objects(new ObjectSpec("room", Child: 2, Attributes: [3]), new ObjectSpec("thing", Parent: 1));
        // je with several operands: 5 is among 3, 5.
        b.Op2Var(0x01, Arg.Small(5), Arg.Small(3), Arg.Small(5));
        b.Branch(true, 5);
        b.Print("A");
        // jl false branch taken when the condition is false.
        b.Op2(0x02, Arg.Small(9), Arg.Small(2));
        b.Branch(false, 5);
        b.Print("B");
        // jg signed: -1 > 1 is false, so the true branch is not taken.
        b.Op2(0x03, Arg.Large(0xFFFF), Arg.Small(1));
        b.Branch(true, 5);
        b.Print("C");
        // jz, test, jin, test_attr.
        b.Op1(0x0, Arg.Small(0));
        b.Branch(true, 5);
        b.Print("D");
        b.Op2(0x07, Arg.Small(0b1011), Arg.Small(0b1001));
        b.Branch(true, 5);
        b.Print("E");
        b.Op2(0x06, Arg.Small(2), Arg.Small(1));
        b.Branch(true, 5);
        b.Print("F");
        b.Op2(0x06, Arg.Small(0), Arg.Small(0));
        b.Branch(true, 5);
        b.Print("G");
        b.Op2(0x0A, Arg.Small(1), Arg.Small(3));
        b.Branch(true, 5);
        b.Print("H");
        b.Op2(0x0A, Arg.Small(0), Arg.Small(3));
        b.Branch(false, 5);
        b.Print("I");
        // A long, backward-reaching offset that still lands forward.
        b.Op1(0x0, Arg.Small(0));
        b.Branch(true, 70);
        var skipped = b.Here;

        while (b.Here < skipped + 66)
        {
            b.Print("J");
        }

        b.Op0(0x4);
        b.Op0(0x4);
        b.Print("K");
        b.Quit();
        Assert.Equal("CK", Session.Run(b).Output);
    }

    [Fact]
    public void JeNeedsAtLeastTwoOperands()
    {
        var b = new StoryBuilder();
        b.Op2Var(0x01, Arg.Small(5));
        b.Branch(true, 5);
        b.Quit();
        Assert.Contains("je at $1000 has 1 operand(s)", Session.Fails<ZMachineException>(b).Message, StringComparison.Ordinal);
    }

    [Fact]
    public void ABranchOffsetOfZeroOrOneReturnsFromTheRoutine()
    {
        var b = new StoryBuilder();
        var routine = b.Align(b.Here + 5 + 4 + 6 + 4 + 1);
        b.Call(routine, G0);
        PrintGlobal(b, G0);
        b.Call(routine, G0, Arg.Small(1));
        PrintGlobal(b, G0);
        b.Quit();
        Assert.Equal(routine, b.Routine(1));
        b.Op1(0x0, Arg.Var(1));
        b.Branch(true, 1);
        b.Op1(0x0, Arg.Var(1));
        b.Branch(false, 0);
        b.Print("never");
        b.Quit();
        Assert.Equal("1\n0\n", Session.Run(b).Output);
    }

    [Fact]
    public void JumpMovesByASignedOffset()
    {
        var b = new StoryBuilder();
        // Forward past the quit and "A" onto "B", then back onto the quit.
        b.Op1(0xC, Arg.Large(6));
        b.Quit();
        b.Print("A");
        b.Print("B");
        b.Op1(0xC, Arg.Large(0x10000 - 8));
        Assert.Equal("B", Session.Run(b).Output);
    }

    [Fact]
    public void VariablesReadAndWriteThroughStackLocalsAndGlobals()
    {
        var b = new StoryBuilder();
        b.OpVar(0x08, Arg.Small(7));
        b.OpVar(0x08, Arg.Small(9));
        // store into variable 0 overwrites the top in place; load reads it without popping.
        b.Op2(0x0D, Arg.Small(0), Arg.Small(11));
        b.Op1(0xE, Arg.Small(0));
        b.Store(G0);
        PrintGlobal(b, G0);
        b.Op1(0x5, Arg.Small(0));
        b.Op1(0x6, Arg.Small(G0));
        PrintGlobal(b, G0);
        b.OpVar(0x09, Arg.Small(G1));
        PrintGlobal(b, G1);
        b.Op2(0x05, Arg.Small(G1), Arg.Small(11));
        b.Branch(true, 5);
        b.Print("X");
        b.Op2(0x04, Arg.Small(G1), Arg.Small(13));
        b.Branch(true, 5);
        b.Print("Y");
        PrintGlobal(b, G1);
        // Pulling into variable 0 pops, then overwrites the new top in place.
        b.OpVar(0x08, Arg.Small(3));
        b.OpVar(0x09, Arg.Small(0));
        b.Op1(0xE, Arg.Small(0));
        b.Store(G0);
        PrintGlobal(b, G0);
        b.Op0(0x9);
        b.Quit();
        Assert.Equal("11\n10\n12\n12\n3\n", Session.Run(b).Output);
    }

    [Fact]
    public void TheStackCannotBePoppedBelowItsFrame()
    {
        var b = new StoryBuilder();
        b.Op0(0x9);
        b.Quit();
        Assert.Contains("stack underflow", Session.Fails<ZMachineException>(b).Message, StringComparison.Ordinal);

        var peek = new StoryBuilder();
        peek.Op1(0xE, Arg.Small(0));
        peek.Store(G0);
        peek.Quit();
        Assert.Contains("stack underflow", Session.Fails<ZMachineException>(peek).Message, StringComparison.Ordinal);

        var replace = new StoryBuilder();
        replace.Op2(0x0D, Arg.Small(0), Arg.Small(1));
        replace.Quit();
        Assert.Contains("stack underflow", Session.Fails<ZMachineException>(replace).Message, StringComparison.Ordinal);
    }

    [Fact]
    public void LocalsOutsideTheRoutineAreRefused()
    {
        var read = new StoryBuilder();
        read.Op1(0xE, Arg.Small(3));
        read.Store(G0);
        read.Quit();
        Assert.Contains("local variable 3 does not exist", Session.Fails<ZMachineException>(read).Message, StringComparison.Ordinal);

        var write = new StoryBuilder();
        write.Op2(0x0D, Arg.Small(3), Arg.Small(1));
        write.Quit();
        Assert.Contains("local variable 3 does not exist", Session.Fails<ZMachineException>(write).Message, StringComparison.Ordinal);
    }

    [Fact]
    public void CallsPassArgumentsOverInitialLocalsAndReturnValues()
    {
        var b = new StoryBuilder();
        var routine = b.Align(b.Here + 8 + 4 + 4 + 4 + 1);
        b.Call(routine, G0, Arg.Small(5), Arg.Small(6), Arg.Small(7));
        PrintGlobal(b, G0);
        b.OpVar(0x00, Arg.Small(0));
        b.Store(G0);
        PrintGlobal(b, G0);
        b.Quit();
        Assert.Equal(routine, b.Routine(2, 100, 200));
        b.Op2(0x14, Arg.Var(1), Arg.Var(2));
        b.Store(0);
        b.Op0(0x8);
        Assert.Equal("11\n0\n", Session.Run(b).Output);
    }

    [Fact]
    public void VersionFiveRoutinesStartWithZeroedLocals()
    {
        var b = new StoryBuilder(5);
        var routine = b.Align(b.Here + 6 + 4 + 1);
        b.Call(routine, G0, Arg.Small(4));
        PrintGlobal(b, G0);
        b.Quit();
        Assert.Equal(routine, b.Routine(3));
        b.OpVar(0x1F, Arg.Small(1));
        b.Branch(false, 0);
        b.OpVar(0x1F, Arg.Small(2));
        b.Branch(true, 0);
        b.Op2(0x14, Arg.Var(1), Arg.Var(3));
        b.Store(0);
        b.Op0(0x8);
        Assert.Equal("4\n", Session.Run(b).Output);
    }

    [Fact]
    public void TheCallFamilyStoresOrDiscards()
    {
        var b = new StoryBuilder(5);
        var routine = StoryBuilder.CodeStart + 60;
        b.Op1(0x8, Arg.Large(b.Packed(routine)));
        b.Store(G0);
        PrintGlobal(b, G0);
        b.Op1(0xF, Arg.Large(b.Packed(routine)));
        b.Op2(0x19, Arg.Large(b.Packed(routine)), Arg.Small(2));
        b.Store(G0);
        PrintGlobal(b, G0);
        b.Op2(0x1A, Arg.Large(b.Packed(routine)), Arg.Small(3));
        b.OpVar(0x19, Arg.Large(b.Packed(routine)), Arg.Small(4));
        b.OpVar(0x1A, Arg.Large(b.Packed(routine)), Arg.Small(5), Arg.Small(6), Arg.Small(7), Arg.Small(8));
        b.OpVar(0x0C, Arg.Large(b.Packed(routine)), Arg.Small(5), Arg.Small(6), Arg.Small(7), Arg.Small(8));
        b.Store(G0);
        PrintGlobal(b, G0);
        b.Quit();

        while (b.Here < routine)
        {
            b.Op0(0x4);
        }

        Assert.Equal(routine, b.Routine(1));
        b.Print("r");
        b.Op1(0xB, Arg.Var(1));
        Assert.Equal("r0\nrr2\nrrrr5\n", Session.Run(b).Output);
    }

    [Fact]
    public void ARoutineHeaderClaimingTooManyLocalsIsNotARoutine()
    {
        var b = new StoryBuilder();
        var bogus = b.Here + 6;
        b.Call(bogus, G0);
        b.Quit();
        b.Raw(16);
        Assert.Contains("claims 16 locals", Session.Fails<ZMachineException>(b).Message, StringComparison.Ordinal);
    }

    [Fact]
    public void ReturningFromTheMainRoutineIsRefused()
    {
        var b = new StoryBuilder();
        b.Op0(0x0);
        Assert.Contains("return from the main routine", Session.Fails<ZMachineException>(b).Message, StringComparison.Ordinal);
    }

    [Fact]
    public void CatchAndThrowUnwindToAFrame()
    {
        var b = new StoryBuilder(5);
        var inner = StoryBuilder.CodeStart + 40;
        var outer = StoryBuilder.CodeStart + 60;
        b.Op1(0x8, Arg.Large(b.Packed(outer)));
        b.Store(G0);
        PrintGlobal(b, G0);
        b.Quit();

        while (b.Here < inner)
        {
            b.Op0(0x4);
        }

        Assert.Equal(inner, b.Routine(0));
        b.Op2(0x1C, Arg.Small(42), Arg.Var(G1));
        b.Print("never");
        b.Op0(0x0);

        while (b.Here < outer)
        {
            b.Op0(0x4);
        }

        Assert.Equal(outer, b.Routine(0));
        b.Op0(0x9);
        b.Store(G1);
        b.Op1(0x8, Arg.Large(b.Packed(inner)));
        b.Store(0);
        b.Print("never");
        b.Op0(0x0);
        var (output, _) = Session.Run(b);
        Assert.Equal("42\n", output);
        var b2 = new StoryBuilder(5);
        b2.Op2(0x1C, Arg.Small(1), Arg.Small(9));
        Assert.Contains("cannot throw to stack frame 9", Session.Fails<ZMachineException>(b2).Message, StringComparison.Ordinal);
    }

    [Fact]
    public void ObjectOpcodesReadAndReshapeTheTree()
    {
        var b = new StoryBuilder();
        b.Objects(
            new ObjectSpec("room", Child: 2, Properties: [(3, [0x12, 0x34]), (1, [9])]),
            new ObjectSpec("box", Parent: 1, Sibling: 3, Attributes: [5]),
            new ObjectSpec("lamp", Parent: 1));
        b.PropertyDefault(4, 0x0404);
        b.Op1(0x3, Arg.Small(2));
        b.Store(G0);
        PrintGlobal(b, G0);
        b.Op1(0x3, Arg.Small(0));
        b.Store(G0);
        PrintGlobal(b, G0);
        b.Op1(0x1, Arg.Small(2));
        b.Store(G0);
        b.Branch(true, 5);
        b.Print("X");
        PrintGlobal(b, G0);
        b.Op1(0x1, Arg.Small(0));
        b.Store(G0);
        b.Branch(false, 5);
        b.Print("Y");
        b.Op1(0x2, Arg.Small(1));
        b.Store(G0);
        b.Branch(true, 5);
        b.Print("Z");
        PrintGlobal(b, G0);
        b.Op1(0x2, Arg.Small(0));
        b.Store(G0);
        b.Branch(false, 5);
        b.Print("W");
        // Move the lamp to be the room's first child, then remove the box.
        b.Op2(0x0E, Arg.Small(3), Arg.Small(1));
        b.Op2(0x0E, Arg.Small(0), Arg.Small(1));
        b.Op2(0x0E, Arg.Small(3), Arg.Small(0));
        b.Op1(0x9, Arg.Small(2));
        b.Op1(0x9, Arg.Small(0));
        b.Op1(0x2, Arg.Small(1));
        b.Store(G0);
        b.Branch(true, 5);
        b.Print("V");
        PrintGlobal(b, G0);
        b.Op1(0x1, Arg.Small(3));
        b.Store(G0);
        b.Branch(false, 5);
        b.Print("U");
        // Attributes: set, test, clear, and the quiet out-of-range writes.
        b.Op2(0x0B, Arg.Small(3), Arg.Small(7));
        b.Op2(0x0B, Arg.Small(3), Arg.Small(40));
        b.Op2(0x0B, Arg.Small(0), Arg.Small(7));
        b.Op2(0x0A, Arg.Small(3), Arg.Small(7));
        b.Branch(true, 5);
        b.Print("T");
        b.Op2(0x0C, Arg.Small(3), Arg.Small(7));
        b.Op2(0x0C, Arg.Small(2), Arg.Small(40));
        b.Op2(0x0C, Arg.Small(0), Arg.Small(7));
        b.Op2(0x0A, Arg.Small(3), Arg.Small(7));
        b.Branch(false, 5);
        b.Print("S");
        // Properties.
        b.Op2(0x11, Arg.Small(1), Arg.Small(3));
        b.Store(G0);
        PrintGlobal(b, G0);
        b.Op2(0x11, Arg.Small(1), Arg.Small(4));
        b.Store(G0);
        PrintGlobal(b, G0);
        b.Op2(0x11, Arg.Small(0), Arg.Small(4));
        b.Store(G0);
        PrintGlobal(b, G0);
        b.OpVar(0x03, Arg.Small(1), Arg.Small(3), Arg.Large(0x0102));
        b.Op2(0x12, Arg.Small(1), Arg.Small(3));
        b.Store(G0);
        b.Op1(0x4, Arg.Var(G0));
        b.Store(G1);
        PrintGlobal(b, G1);
        b.Op2(0x0F, Arg.Var(G0), Arg.Small(0));
        b.Store(G1);
        PrintGlobal(b, G1);
        b.Op2(0x12, Arg.Small(1), Arg.Small(9));
        b.Store(G0);
        PrintGlobal(b, G0);
        b.Op2(0x12, Arg.Small(0), Arg.Small(9));
        b.Store(G0);
        PrintGlobal(b, G0);
        b.Op1(0x4, Arg.Small(0));
        b.Store(G0);
        PrintGlobal(b, G0);
        b.Op2(0x13, Arg.Small(1), Arg.Small(0));
        b.Store(G0);
        PrintGlobal(b, G0);
        b.Op2(0x13, Arg.Small(0), Arg.Small(0));
        b.Store(G0);
        PrintGlobal(b, G0);
        b.Quit();
        var (output, _) = Session.Run(b);
        Assert.Equal("1\n0\n3\n2\n3\n4660\n1028\n0\n2\n258\n0\n0\n0\n3\n0\n", output);
    }

    [Fact]
    public void TablesAreAddressedWithSignedIndices()
    {
        var b = new StoryBuilder();
        var table = b.Words(0x1111, 0x2222, 0x3333);
        b.OpVar(0x01, Arg.Large(table), Arg.Small(1), Arg.Large(0xABCD));
        b.OpVar(0x02, Arg.Large(table + 4), Arg.Large(0xFFFF), Arg.Large(0x1FF));
        b.Op2(0x0F, Arg.Large(table), Arg.Small(1));
        b.Store(G0);
        PrintGlobal(b, G0);
        b.Op2(0x10, Arg.Large(table + 4), Arg.Large(0xFFFF));
        b.Store(G0);
        PrintGlobal(b, G0);
        b.Op2(0x0F, Arg.Large(table + 4), Arg.Large(0xFFFF));
        b.Store(G0);
        PrintGlobal(b, G0);
        b.Quit();
        Assert.Equal("-21505\n255\n-21505\n", Session.Run(b).Output);
    }

    [Fact]
    public void ScanTableFindsWordsAndBytes()
    {
        var b = new StoryBuilder(5);
        var table = b.Words(0x0001, 0x0002, 0x0003);
        b.OpVar(0x17, Arg.Small(2), Arg.Large(table), Arg.Small(3));
        b.Store(G0);
        b.Branch(true, 5);
        b.Print("X");
        b.Op2(0x15, Arg.Var(G0), Arg.Large(table));
        b.Store(G0);
        PrintGlobal(b, G0);
        b.OpVar(0x17, Arg.Small(3), Arg.Large(table + 1), Arg.Small(3), Arg.Small(0x02));
        b.Store(G0);
        b.Branch(true, 5);
        b.Print("Y");
        b.Op2(0x15, Arg.Var(G0), Arg.Large(table));
        b.Store(G0);
        PrintGlobal(b, G0);
        b.OpVar(0x17, Arg.Small(9), Arg.Large(table), Arg.Small(3));
        b.Store(G0);
        b.Branch(false, 5);
        b.Print("Z");
        PrintGlobal(b, G0);
        b.Quit();
        Assert.Equal("2\n5\n0\n", Session.Run(b).Output);
    }

    [Fact]
    public void CopyTableZeroesMovesAndOverlaps()
    {
        var b = new StoryBuilder(5);
        var table = b.Bytes(1, 2, 3, 4, 5, 6);
        // Forward overlap copies backward so the source survives.
        b.OpVar(0x1D, Arg.Large(table), Arg.Large(table + 1), Arg.Small(3));
        b.OpVar(0x1D, Arg.Large(table + 4), Arg.Large(table + 5), Arg.Large(0xFFFF));
        b.OpVar(0x1D, Arg.Large(table + 3), Arg.Large(table), Arg.Small(1));
        b.OpVar(0x1D, Arg.Large(table + 5), Arg.Small(0), Arg.Small(1));

        for (var k = 0; k < 6; k++)
        {
            b.Op2(0x10, Arg.Large(table), Arg.Small(k));
            b.Store(G0);
            PrintNum(b, Arg.Var(G0));
        }

        b.Quit();
        Assert.Equal("312350", Session.Run(b).Output);
    }

    [Fact]
    public void PrintTableWritesRowsToTheScreenOrATable()
    {
        var b = new StoryBuilder(5);
        var table = b.Bytes((byte)'a', (byte)'b', (byte)'x', (byte)'c', (byte)'d', (byte)'x');
        var target = b.Alloc(20);
        b.OpVar(0x1E, Arg.Large(table), Arg.Small(2), Arg.Small(2), Arg.Small(1));
        b.NewLine();
        b.OpVar(0x1E, Arg.Large(table), Arg.Small(2));
        b.NewLine();
        b.OpVar(0x13, Arg.Small(3), Arg.Large(target));
        b.OpVar(0x1E, Arg.Large(table), Arg.Small(2), Arg.Small(2), Arg.Small(1));
        b.OpVar(0x13, Arg.Large(0xFFFD));
        b.Op2(0x0F, Arg.Large(target), Arg.Small(0));
        b.Store(G0);
        PrintGlobal(b, G0);
        b.Quit();
        Assert.Equal("ab\ncd\nab\n5\n", Session.Run(b).Output);
    }

    [Fact]
    public void ReadLowercasesTruncatesAndParses()
    {
        var b = new StoryBuilder();
        b.Dictionary(",", "open", "mailbox");
        var text = b.Bytes(8, 0, 0, 0, 0, 0, 0, 0, 0);
        var parse = b.Bytes(4, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0);
        b.Print(">");
        b.OpVar(0x04, Arg.Large(text), Arg.Large(parse));
        b.Quit();
        var (output, machine) = Session.Run(b, ["Open,MAILBOX now"]);
        Assert.Equal(">", output);
        var memory = machine.Memory;
        var typed = new StringBuilder();

        for (var at = text + 1; memory.ReadByte(at) != 0; at++)
        {
            typed.Append((char)memory.ReadByte(at));
        }

        // Seven letters fit an eight-byte buffer with its terminator;
        // the lexer sees "open" "," "ma": three words, the first in the
        // dictionary, four letters long, starting at byte 1.
        Assert.Equal("open,ma", typed.ToString());
        Assert.Equal(3, memory.ReadByte(parse + 1));
        Assert.NotEqual(0, memory.ReadWord(parse + 2));
        Assert.Equal(4, memory.ReadByte(parse + 4));
        Assert.Equal(1, memory.ReadByte(parse + 5));
        Assert.Equal(0, memory.ReadWord(parse + 10));
        Assert.Equal(2, memory.ReadByte(parse + 12));
        Assert.Equal(6, memory.ReadByte(parse + 13));
    }

    [Fact]
    public void ReadBeforeVersionFiveNeedsAParseBuffer()
    {
        var b = new StoryBuilder();
        var text = b.Bytes(8, 0, 0, 0, 0, 0, 0, 0, 0);
        b.OpVar(0x04, Arg.Large(text));
        b.Quit();
        Assert.Contains("names no parse buffer", Session.Fails<ZMachineException>(b, ["x"]).Message, StringComparison.Ordinal);
    }

    [Fact]
    public void ReadRefusesOverrunBuffers()
    {
        var b = new StoryBuilder();
        var text = b.Bytes(1, 0, 0);
        var parse = b.Bytes(1, 0, 0, 0, 0, 0);
        b.OpVar(0x04, Arg.Large(text), Arg.Large(parse));
        b.Quit();
        Assert.Contains("claims a capacity of 1", Session.Fails<ZMachineException>(b, ["x"]).Message, StringComparison.Ordinal);

        var c = new StoryBuilder();
        var text2 = c.Bytes(8, 0, 0, 0, 0, 0, 0, 0, 0);
        var parse2 = c.Bytes(0, 0, 0, 0, 0, 0);
        c.OpVar(0x04, Arg.Large(text2), Arg.Large(parse2));
        c.Quit();
        Assert.Contains("claims room for 0 words", Session.Fails<ZMachineException>(c, ["x"]).Message, StringComparison.Ordinal);
    }

    [Fact]
    public void ReadEndsTheSessionWhenInputRunsOut()
    {
        var b = new StoryBuilder();
        var text = b.Bytes(8, 0, 0, 0, 0, 0, 0, 0, 0);
        var parse = b.Bytes(4, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0);
        b.OpVar(0x04, Arg.Large(text), Arg.Large(parse));
        b.Quit();
        Session.Fails<EndOfInputException>(b);
    }

    [Fact]
    public void VersionFiveReadCountsAndKeepsPreloadedText()
    {
        var b = new StoryBuilder(5);
        b.Dictionary("", "go", "north");
        var text = b.Bytes(10, 3, (byte)'g', (byte)'o', (byte)' ', 0, 0, 0, 0, 0, 0, 0);
        var parse = b.Bytes(4, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0);
        b.OpVar(0x04, Arg.Large(text), Arg.Large(parse), Arg.Small(0), Arg.Small(0));
        b.Store(G0);
        PrintGlobal(b, G0);
        b.Op2(0x10, Arg.Large(text), Arg.Small(1));
        b.Store(G0);
        PrintGlobal(b, G0);
        b.Op2(0x10, Arg.Large(parse), Arg.Small(1));
        b.Store(G0);
        PrintGlobal(b, G0);
        b.Op2(0x10, Arg.Large(parse), Arg.Small(9));
        b.Store(G0);
        PrintGlobal(b, G0);
        // A read with no parse buffer lexes nothing.
        b.OpVar(0x04, Arg.Large(text), Arg.Small(0));
        b.Store(G0);
        b.Op2(0x10, Arg.Large(text), Arg.Small(1));
        b.Store(G0);
        PrintGlobal(b, G0);
        b.Quit();
        Assert.Equal("13\n8\n2\n5\n10\n", Session.Run(b, ["NORTH", "and more"]).Output);
    }

    [Fact]
    public void TokeniseUsesAnotherDictionaryAndKeepsRecognizedWords()
    {
        var b = new StoryBuilder(5);
        var other = b.Dictionary("", "close");
        b.Dictionary("", "open");
        var text = b.Bytes(20, 10, (byte)'o', (byte)'p', (byte)'e', (byte)'n', (byte)' ', (byte)'c', (byte)'l', (byte)'o', (byte)'s', (byte)'e', 0, 0, 0, 0, 0, 0, 0, 0, 0, 0);
        var parse = b.Bytes(4, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0);
        b.OpVar(0x1B, Arg.Large(text), Arg.Large(parse));
        b.Op2(0x0F, Arg.Large(parse), Arg.Small(1));
        b.Store(G0);
        b.Op2(0x0F, Arg.Large(parse), Arg.Small(3));
        b.Store(G1);
        b.Op1(0x0, Arg.Var(G0));
        b.Branch(true, 5);
        b.Print("A");
        b.Op1(0x0, Arg.Var(G1));
        b.Branch(false, 5);
        b.Print("B");
        b.OpVar(0x1B, Arg.Large(text), Arg.Large(parse), Arg.Small(0));
        b.OpVar(0x1B, Arg.Large(text), Arg.Large(parse), Arg.Large(other), Arg.Small(1));
        b.Op2(0x0F, Arg.Large(parse), Arg.Small(1));
        b.Store(G0);
        b.Op2(0x0F, Arg.Large(parse), Arg.Small(3));
        b.Store(G1);
        b.Op1(0x0, Arg.Var(G0));
        b.Branch(true, 5);
        b.Print("C");
        b.Op1(0x0, Arg.Var(G1));
        b.Branch(true, 5);
        b.Print("D");
        b.Quit();
        Assert.Equal("ABCD", Session.Run(b).Output);
    }

    [Fact]
    public void EncodeTextWritesDictionaryForm()
    {
        var b = new StoryBuilder(5);
        var text = b.Bytes((byte)'x', (byte)'o', (byte)'p', (byte)'e', (byte)'n');
        var target = b.Alloc(6);
        b.OpVar(0x1C, Arg.Large(text), Arg.Small(4), Arg.Small(1), Arg.Large(target));

        for (var k = 0; k < 3; k++)
        {
            b.Op2(0x0F, Arg.Large(target), Arg.Small(k));
            b.Store(G0);
            PrintGlobal(b, G0);
        }

        b.Quit();
        Assert.Equal("21162\n19621\n-27483\n", Session.Run(b).Output);
    }

    [Fact]
    public void ReadCharSpendsLinesAsKeystrokes()
    {
        var b = new StoryBuilder(5);

        for (var k = 0; k < 3; k++)
        {
            b.OpVar(0x16, Arg.Small(1));
            b.Store(G0);
            PrintGlobal(b, G0);
        }

        b.Quit();
        Assert.Equal("97\n98\n99\n", Session.Run(b, ["ab", "c"]).Output);
    }

    [Fact]
    public void RandomRollsSeedsAndRerandomizes()
    {
        var b = new StoryBuilder();
        b.OpVar(0x07, Arg.Small(100));
        b.Store(G0);
        PrintGlobal(b, G0);
        b.OpVar(0x07, Arg.Large(0x10000 - 3));
        b.Store(G0);
        PrintGlobal(b, G0);
        b.OpVar(0x07, Arg.Small(10));
        b.Store(G0);
        PrintGlobal(b, G0);
        b.OpVar(0x07, Arg.Small(0));
        b.Store(G0);
        PrintGlobal(b, G0);
        b.OpVar(0x07, Arg.Small(1));
        b.Store(G0);
        PrintGlobal(b, G0);
        b.Quit();
        Assert.Equal("98\n0\n1\n0\n1\n", Session.Run(b, seed: 92).Output);
    }

    [Fact]
    public void OutputStreamsSelectTheScreenAndRedirectToTables()
    {
        var b = new StoryBuilder();
        var table = b.Alloc(20);
        var inner = b.Alloc(20);
        b.OpVar(0x13, Arg.Large(0xFFFF));
        b.Print("hidden");
        b.OpVar(0x13, Arg.Small(1));
        b.OpVar(0x13, Arg.Small(3), Arg.Large(table));
        b.Print("ab");
        b.OpVar(0x13, Arg.Small(3), Arg.Large(inner));
        b.Print("c");
        b.NewLine();
        b.OpVar(0x13, Arg.Large(0xFFFD));
        b.Print("d");
        b.OpVar(0x13, Arg.Large(0xFFFD));
        b.OpVar(0x13, Arg.Small(4));
        b.OpVar(0x13, Arg.Large(0xFFFC));
        b.OpVar(0x13, Arg.Small(0));
        b.OpVar(0x13, Arg.Large(0xFFFE));
        b.Op2(0x0F, Arg.Large(table), Arg.Small(0));
        b.Store(G0);
        PrintGlobal(b, G0);
        b.Op2(0x10, Arg.Large(table), Arg.Small(4));
        b.Store(G0);
        PrintGlobal(b, G0);
        b.Op2(0x0F, Arg.Large(inner), Arg.Small(0));
        b.Store(G0);
        PrintGlobal(b, G0);
        b.Op2(0x10, Arg.Large(inner), Arg.Small(3));
        b.Store(G0);
        PrintGlobal(b, G0);
        b.Quit();
        Assert.Equal("3\n100\n2\n13\n", Session.Run(b).Output);
    }

    [Fact]
    public void TheTranscriptStreamIsALoudFrontier()
    {
        var select = new StoryBuilder();
        select.OpVar(0x13, Arg.Small(2));
        select.Quit();
        Assert.Contains("output_stream at $1000 is not yet ported", Session.Fails<ZMachineException>(select).Message, StringComparison.Ordinal);

        var flagged = new StoryBuilder();
        flagged.OpVar(0x01, Arg.Small(0), Arg.Small(Header.Flags2 / 2), Arg.Small(1));
        flagged.Print("x");
        Assert.Contains("output stream 2 at", Session.Fails<ZMachineException>(flagged).Message, StringComparison.Ordinal);

        var unknown = new StoryBuilder();
        unknown.OpVar(0x13, Arg.Small(5));
        Assert.Contains("names stream 5, but §7.1 defines only 1 to 4", Session.Fails<ZMachineException>(unknown).Message, StringComparison.Ordinal);

        var unselected = new StoryBuilder();
        unselected.OpVar(0x13, Arg.Large(0xFFFD));
        Assert.Contains("stream 3 is not selected", Session.Fails<ZMachineException>(unselected).Message, StringComparison.Ordinal);

        var tableless = new StoryBuilder();
        tableless.OpVar(0x13, Arg.Small(3));
        Assert.Contains("names no table to redirect into", Session.Fails<ZMachineException>(tableless).Message, StringComparison.Ordinal);

        var deep = new StoryBuilder();
        var table = deep.Alloc(4);

        for (var k = 0; k < 17; k++)
        {
            deep.OpVar(0x13, Arg.Small(3), Arg.Large(table));
        }

        Assert.Contains("would nest 17 deep; §7.1.2.1.1 allows 16 at most", Session.Fails<ZMachineException>(deep).Message, StringComparison.Ordinal);
    }

    [Fact]
    public void WindowOpcodesReachThePlainFrontend()
    {
        var b = new StoryBuilder(5);
        var cursor = b.Alloc(4);
        b.OpVar(0x0A, Arg.Small(5));
        b.OpVar(0x0B, Arg.Small(1));
        b.OpVar(0x0F, Arg.Small(2), Arg.Small(3));
        b.Print("up");
        b.OpVar(0x10, Arg.Large(cursor));
        b.OpVar(0x0B, Arg.Small(0));
        b.Print("story");
        b.OpVar(0x0B, Arg.Small(1));
        b.OpVar(0x0D, Arg.Large(0xFFFF));
        b.Print("cleared");
        b.OpVar(0x11, Arg.Small(2));
        b.OpVar(0x12, Arg.Small(1));
        b.OpVar(0x0E, Arg.Small(1));
        b.Op2(0x1B, Arg.Small(1), Arg.Small(2));
        b.Ext(0x0D, Arg.Small(1), Arg.Small(2));
        b.OpVar(0x14, Arg.Small(0));
        b.OpVar(0x15, Arg.Small(1));
        b.Op0(0x4);
        b.OpVar(0x0D, Arg.Small(0));
        b.NewLine();
        b.Op2(0x0F, Arg.Large(cursor), Arg.Small(0));
        b.Store(G0);
        PrintGlobal(b, G0);
        b.Op2(0x0F, Arg.Large(cursor), Arg.Small(1));
        b.Store(G0);
        PrintGlobal(b, G0);
        b.Quit();
        Assert.Equal("\n  up\nstorycleared\n2\n5\n", Session.Run(b).Output);
    }

    [Fact]
    public void ShowStatusAndSoundAreQuietOnAStream()
    {
        var b = new StoryBuilder();
        b.Op0(0xC);
        b.OpVar(0x15, Arg.Small(2));
        b.Print("ok");
        b.Quit();
        Assert.Equal("ok", Session.Run(b).Output);
    }

    [Fact]
    public void TheHeaderIsStampedWithTheFrontendsCapabilities()
    {
        var v3 = new StoryBuilder();
        v3.Op2(0x10, Arg.Small(0), Arg.Small(Header.Flags1));
        v3.Store(G0);
        PrintGlobal(v3, G0);
        v3.Op2(0x0F, Arg.Small(0), Arg.Small(Header.Flags2 / 2));
        v3.Store(G0);
        PrintGlobal(v3, G0);
        v3.Op2(0x10, Arg.Small(0), Arg.Small(Header.StandardMajor));
        v3.Store(G0);
        PrintGlobal(v3, G0);
        v3.Op2(0x10, Arg.Small(0), Arg.Small(Header.StandardMinor));
        v3.Store(G0);
        PrintGlobal(v3, G0);
        v3.Quit();
        var story = v3.Build();
        // Every bit set but the transcript bit, which would make the
        // first print a loud frontier.
        story[Header.Flags1] = 0xFF;
        StoryBuilder.Word(story, Header.Flags2, 0xFFFE);
        var output = new StringBuilder();
        new Machine(story, new PlainFrontend(t => output.Append(t)), () => null, null).Run();
        Assert.Equal("215\n-130\n1\n1\n", output.ToString());

        var v5 = new StoryBuilder(5);

        foreach (var field in new[] { Header.Flags1, Header.Interpreter, Header.InterpreterVersion, Header.ScreenLines, Header.ScreenColumns, Header.FontWidth, Header.FontHeight })
        {
            v5.Op2(0x10, Arg.Small(0), Arg.Small(field));
            v5.Store(G0);
            PrintGlobal(v5, G0);
        }

        foreach (var field in new[] { Header.Flags2, Header.ScreenWidthUnits, Header.ScreenHeightUnits })
        {
            v5.Op2(0x0F, Arg.Small(0), Arg.Small(field / 2));
            v5.Store(G0);
            PrintGlobal(v5, G0);
        }

        v5.Quit();
        var story5 = v5.Build();
        story5[Header.Flags1] = 0xFF;
        StoryBuilder.Word(story5, Header.Flags2, 0xFFFE);
        output.Clear();
        new Machine(story5, new PlainFrontend(t => output.Append(t)), () => null, null).Run();
        Assert.Equal("240\n6\n86\n255\n80\n1\n1\n-170\n80\n255\n", output.ToString());
    }

    [Fact]
    public void RestartReloadsDynamicMemoryButKeepsTheTranscriptBits()
    {
        var b = new StoryBuilder();
        // The first run sets a global and the fixed-pitch bit, then
        // restarts; the second finds the global reset and the bit kept,
        // and quits.
        PrintGlobal(b, G0);
        b.Op2(0x0F, Arg.Small(0), Arg.Small(Header.Flags2 / 2));
        b.Store(G1);
        b.Op2(0x09, Arg.Var(G1), Arg.Small(0x02));
        b.Store(G1);
        b.Op1(0x0, Arg.Var(G1));
        b.Branch(false, 11);
        b.Op2(0x0D, Arg.Small(G0), Arg.Small(1));
        b.OpVar(0x01, Arg.Small(0), Arg.Small(Header.Flags2 / 2), Arg.Small(0x02));
        b.Op0(0x7);
        b.Quit();
        var (output, _) = Session.Run(b);
        Assert.Equal("0\n0\n", output);
    }

    [Fact]
    public void VerifyChecksThePristineStory()
    {
        var b = new StoryBuilder();
        b.Op0(0xD);
        b.Branch(true, 5);
        b.Print("bad");
        b.Print("ok");
        b.Quit();
        Assert.Equal("ok", Session.Run(b).Output);
        var story = b.Build();
        story[^1] ^= 0xFF;
        var output = new StringBuilder();
        new Machine(story, new PlainFrontend(t => output.Append(t)), () => null, null).Run();
        Assert.Equal("badok", output.ToString());
        StoryBuilder.Word(story, Header.FileLength, 0);
        output.Clear();
        new Machine(story, new PlainFrontend(t => output.Append(t)), () => null, null).Run();
        Assert.Equal("badok", output.ToString());
    }

    [Fact]
    public void PiracyIsGullible()
    {
        var b = new StoryBuilder(5);
        b.Op0(0xF);
        b.Branch(true, 7);
        b.Print("pirate");
        b.Print("genuine");
        b.Quit();
        Assert.Equal("genuine", Session.Run(b).Output);
    }

    [Fact]
    public void UndoRestoresTheMomentOfTheSave()
    {
        var b = new StoryBuilder(5);
        b.Ext(0x0A);
        b.Store(G1);
        PrintGlobal(b, G1);
        b.Ext(0x09);
        b.Store(G0);
        PrintGlobal(b, G0);
        // je G0 2 skips the store, the restore and "gone": 3 + 4 + 5 bytes.
        b.Op2(0x01, Arg.Var(G0), Arg.Small(2));
        b.Branch(true, 14);
        b.Op2(0x0D, Arg.Small(G0), Arg.Small(7));
        b.Ext(0x0A);
        b.Store(G1);
        b.Print("gone");
        b.Print("back");
        b.Quit();
        Assert.Equal("0\n1\n2\nback", Session.Run(b).Output);
    }

    [Fact]
    public void SetFontAnswersWithThePreviousFontOrZero()
    {
        var b = new StoryBuilder(5);
        b.Ext(0x04, Arg.Small(4));
        b.Store(G0);
        PrintGlobal(b, G0);
        b.Ext(0x04, Arg.Small(0));
        b.Store(G0);
        PrintGlobal(b, G0);
        b.Ext(0x04, Arg.Small(3));
        b.Store(G0);
        PrintGlobal(b, G0);
        b.Ext(0x04, Arg.Small(1));
        b.Store(G0);
        PrintGlobal(b, G0);
        b.Quit();
        Assert.Equal("1\n4\n0\n4\n", Session.Run(b).Output);
    }

    [Fact]
    public void UnicodeOpcodesPrintAndCheck()
    {
        var b = new StoryBuilder(5);
        b.Ext(0x0B, Arg.Large(0x2191));
        b.Ext(0x0C, Arg.Large(0x2191));
        b.Store(G0);
        PrintGlobal(b, G0);
        b.Ext(0x0C, Arg.Small(9));
        b.Store(G0);
        PrintGlobal(b, G0);
        b.Ext(0x0C, Arg.Large(0xD800));
        b.Store(G0);
        PrintGlobal(b, G0);
        b.Ext(0x0C, Arg.Large(0xE000));
        b.Store(G0);
        PrintGlobal(b, G0);
        b.Quit();
        Assert.Equal("↑3\n0\n0\n3\n", Session.Run(b).Output);
    }

    [Fact]
    public void CodeInDynamicMemoryIsNeverCached()
    {
        var b = new StoryBuilder();
        var routine = b.Bytes(0, 0xB2, 0xA0, 0xA5, 0xB0);
        b.Call(routine, G0);
        b.Call(routine, G0);
        b.Quit();
        Assert.Equal("cc", Session.Run(b).Output);
    }
}
