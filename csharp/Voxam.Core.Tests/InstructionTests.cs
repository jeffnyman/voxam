using Voxam.Core.Tests.Support;

namespace Voxam.Core.Tests;

public class InstructionTests
{
    private static Instruction Decoded(int version, Action<StoryBuilder> emit)
    {
        var builder = new StoryBuilder(version);
        emit(builder);
        builder.Quit();
        // Padding, so a rider that reads past the quit still finds bytes.
        builder.Raw(0, 0, 0);
        return Instruction.Decode(new Memory(builder.Build()), StoryBuilder.CodeStart);
    }

    [Fact]
    public void LongFormCarriesTwoSmallOrVariableOperands()
    {
        var i = Decoded(3, b => b.Op2(0x0D, Arg.Small(7), Arg.Var(0x10)));
        Assert.Equal(Op.Store, i.Op);
        Assert.Equal("store", i.Info.Name);
        Assert.Equal([new Operand(OperandKind.Small, 7), new Operand(OperandKind.Variable, 0x10)], i.Operands);
        Assert.Equal(StoryBuilder.CodeStart + 3, i.OperandsEnd);
        Assert.Equal(-1, i.StoreVariable);
        Assert.Null(i.Branch);
    }

    [Fact]
    public void ShortFormDecodesOneOperandOrNone()
    {
        var one = Decoded(3, b => b.Op1(0x0, Arg.Large(0x1234)));
        Assert.Equal(Op.Jz, one.Op);
        Assert.Equal(new Operand(OperandKind.Large, 0x1234), one.Operands[0]);
        var none = Decoded(3, b => b.Op0(0xB));
        Assert.Equal(Op.NewLine, none.Op);
        Assert.Empty(none.Operands);
        Assert.Equal(StoryBuilder.CodeStart + 1, none.NextAddress);
    }

    [Fact]
    public void VariableFormReadsATypeByte()
    {
        var two = Decoded(3, b => b.Op2Var(0x14, Arg.Large(300), Arg.Small(2)));
        Assert.Equal(Op.Add, two.Op);
        Assert.Equal(300, two.Operands[0].Value);
        var many = Decoded(3, b => b.OpVar(0x00, Arg.Large(0x800), Arg.Small(1), Arg.Var(2)));
        Assert.Equal(Op.Call, many.Op);
        Assert.Equal(3, many.Operands.Length);
        Assert.True(many.Info.Stores);
    }

    [Fact]
    public void TheDoubleTypeOpcodesReadEightFields()
    {
        var i = Decoded(5, b => b.OpVar(0x0C, Arg.Large(0x800), Arg.Small(1), Arg.Small(2), Arg.Small(3), Arg.Small(4), Arg.Small(5)));
        Assert.Equal(Op.CallVs2, i.Op);
        Assert.Equal(6, i.Operands.Length);
        Assert.Equal(5, i.Operands[5].Value);
    }

    [Fact]
    public void ExtendedFormExistsFromVersionFive()
    {
        var i = Decoded(5, b => b.Ext(0x02, Arg.Small(1), Arg.Small(2)));
        Assert.Equal(Op.LogShift, i.Op);
        Assert.True(i.Info.Stores);
        var earlier = Assert.Throws<ZMachineException>(() => Decoded(4, b => b.Raw(0xBE, 0x02)));
        Assert.Contains("0OP:14 is not an opcode in version 4", earlier.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void StoreAndBranchRidersFollowTheOperands()
    {
        var shortBranch = Decoded(3, b =>
        {
            b.Op1(0x1, Arg.Small(1));
            b.Store(0x05);
            b.Branch(true, 9);
        });
        Assert.Equal(Op.GetSibling, shortBranch.Op);
        Assert.Equal(5, shortBranch.StoreVariable);
        Assert.Equal(new Branch(true, 9), shortBranch.Branch);
        Assert.Equal(StoryBuilder.CodeStart + 4, shortBranch.NextAddress);

        var longBranch = Decoded(3, b =>
        {
            b.Op1(0x0, Arg.Small(1));
            b.Branch(false, -20);
        });
        Assert.Equal(new Branch(false, -20), longBranch.Branch);
        Assert.Equal(StoryBuilder.CodeStart + 4, longBranch.NextAddress);

        var forward = Decoded(3, b =>
        {
            b.Op1(0x0, Arg.Small(1));
            b.Branch(true, 300);
        });
        Assert.Equal(300, forward.Branch!.Value.Offset);
        Assert.Equal(StoryBuilder.CodeStart + 4 + 300 - 2, forward.Branch.Value.Target(forward.NextAddress));
    }

    [Fact]
    public void ABranchOffsetOfZeroOrOneMeansAReturn()
    {
        Assert.True(new Branch(true, 0).ReturnsFalse);
        Assert.True(new Branch(true, 1).ReturnsTrue);
        Assert.False(new Branch(true, 2).ReturnsFalse);
    }

    [Fact]
    public void TextRidersRunToTheTerminatingWord()
    {
        var i = Decoded(3, b => b.Print("hello there"));
        Assert.Equal(Op.Print, i.Op);
        Assert.Equal(StoryBuilder.CodeStart + 1, i.OperandsEnd);
        Assert.Equal(StoryBuilder.CodeStart + 1 + 8, i.NextAddress);
    }

    [Fact]
    public void AnOperandAfterAnOmittedOneIsRefused()
    {
        var error = Assert.Throws<ZMachineException>(() => Decoded(3, b => b.Raw(0xE0, 0b11_01_11_11, 1)));
        Assert.Contains("after an omitted one", error.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void OpcodesAreLookedUpByVersion()
    {
        Assert.Equal(Op.Call, Decoded(3, b => b.Raw(0xE0, 0xFF)).Op);
        Assert.Equal("call_vs", Decoded(4, b => b.Raw(0xE0, 0xFF)).Info.Name);
        Assert.Equal(Op.Pop, Decoded(4, b => b.Op0(0x9)).Op);
        Assert.Equal(Op.Catch, Decoded(5, b => b.Op0(0x9)).Op);
        Assert.Equal(Op.Not, Decoded(4, b => b.Op1(0xF, Arg.Small(1))).Op);
        Assert.Equal(Op.Call1n, Decoded(5, b => b.Op1(0xF, Arg.Small(1))).Op);
        Assert.Equal(Op.Sread, Decoded(4, b => b.OpVar(0x04, Arg.Small(1), Arg.Small(2))).Op);
        Assert.Equal(Op.Aread, Decoded(5, b => b.OpVar(0x04, Arg.Small(1), Arg.Small(2))).Op);
        Assert.True(Decoded(3, b => b.Op0(0x5)).Info.Branches);
        Assert.True(Decoded(4, b => b.Op0(0x5)).Info.Stores);
        Assert.Equal(Op.Pull, Decoded(6, b => b.OpVar(0x09)).Op);
        Assert.Equal(Op.Pull, Decoded(8, b => b.OpVar(0x09, Arg.Small(1))).Op);
        Assert.Equal(Op.DrawImage, Decoded(5, b => b.Ext(0x80)).Op);
        Assert.Equal(Op.DrawImage, Decoded(8, b => b.Ext(0x80)).Op);
    }

    [Fact]
    public void UnknownOpcodesAreRefusedByName()
    {
        var ext = Assert.Throws<ZMachineException>(() => Decoded(3, b => b.Op0(0xF)));
        Assert.Contains("0OP:15 is not an opcode in version 3", ext.Message, StringComparison.Ordinal);
        Assert.Contains("1OP:8 is not an opcode in version 3", Assert.Throws<ZMachineException>(() => Decoded(3, b => b.Op1(0x8, Arg.Small(1)))).Message, StringComparison.Ordinal);
        Assert.Contains("2OP:29 is not an opcode", Assert.Throws<ZMachineException>(() => Decoded(3, b => b.Op2(0x1D, Arg.Small(1), Arg.Small(1)))).Message, StringComparison.Ordinal);
        Assert.Contains("VAR:12 is not an opcode in version 3", Assert.Throws<ZMachineException>(() => Decoded(3, b => b.OpVar(0x0C))).Message, StringComparison.Ordinal);
        Assert.Contains("EXT:14 is not an opcode", Assert.Throws<ZMachineException>(() => Decoded(5, b => b.Ext(0x0E))).Message, StringComparison.Ordinal);
    }

    [Fact]
    public void PrivateAndReservedExtendedOpcodesDecode()
    {
        Assert.Equal(Op.ExtPrivate, Decoded(5, b => b.Ext(0x90)).Op);
        Assert.Equal(Op.ExtReserved, Decoded(5, b => b.Ext(0x1F)).Op);
        Assert.Equal(Op.ExtReserved, Decoded(5, b => b.Ext(0x80 - 1)).Op);
    }
}
