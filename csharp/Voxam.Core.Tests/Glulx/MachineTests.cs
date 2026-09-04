using Voxam.Core.Glulx;
using GlulxException = Voxam.Core.GlulxException;

namespace Voxam.Tests.Glulx;

/// <summary>
/// The fetch-decode-execute loop and the opcodes this machine
/// carries: integer math, branches, calls, array data, the stack, and
/// the game state (Glulx: Dictionary of Opcodes). Programs are
/// assembled into ROM at 64, where an instruction's shape can be kept,
/// unless a test asks for RAM.
/// </summary>
public sealed class MachineTests
{
    private const uint Slot0 = 0x140;
    private const uint Slot1 = 0x144;

    // A story that adds and stops; the loop reports how far it got.
    [Fact]
    public void TheLoopRunsUntilTheStoryQuits()
    {
        var program = new GlulxProgram();
        program.Op(Op.Add, Modes.Constant(2), Modes.Constant(3), Modes.Memory(Slot0));
        program.Op(Op.Quit);
        var machine = program.Booted();

        Assert.True(machine.Running);
        Assert.Equal(2, machine.Run());
        Assert.False(machine.Running);
        Assert.Equal(5u, machine.Memory.ReadWord((int)Slot0));
        Assert.Equal(2, machine.Instructions);
    }

    // The limit is a debugging guard, not a specification feature: a
    // runaway loop should fail rather than hang, and the tally still
    // says how far the machine got.
    [Fact]
    public void ARunawayLoopMeetsTheLimitItWasGiven()
    {
        var program = new GlulxProgram();
        var at = program.Here;
        program.Op(Op.Jump, Modes.Word(0));
        program.Patch(program.Here - 4, (uint)(at - program.Here + 2));
        var machine = program.Booted();

        Assert.Equal("execution exceeded 20 instructions", Refusal(() => machine.Run(20)));
        Assert.Equal(20, machine.Instructions);
    }

    [Theory]
    [InlineData(Op.Add, 2u, 3u, 5u)]
    [InlineData(Op.Add, 0xFFFFFFFFu, 2u, 1u)]
    [InlineData(Op.Sub, 3u, 5u, 0xFFFFFFFEu)]
    [InlineData(Op.Mul, 0x10000u, 0x10000u, 0u)]
    [InlineData(Op.Mul, 7u, 6u, 42u)]
    [InlineData(Op.Div, 7u, 2u, 3u)]
    [InlineData(Op.Div, 0xFFFFFFF9u, 2u, 0xFFFFFFFDu)]
    [InlineData(Op.Div, 7u, 0xFFFFFFFEu, 0xFFFFFFFDu)]
    [InlineData(Op.Mod, 7u, 2u, 1u)]
    [InlineData(Op.Mod, 0xFFFFFFF9u, 2u, 0xFFFFFFFFu)]
    [InlineData(Op.Bitand, 0xF0F0u, 0xFF00u, 0xF000u)]
    [InlineData(Op.Bitor, 0xF0F0u, 0x0F0Fu, 0xFFFFu)]
    [InlineData(Op.Bitxor, 0xFFFFu, 0x0F0Fu, 0xF0F0u)]
    [InlineData(Op.Shiftl, 1u, 4u, 0x10u)]
    [InlineData(Op.Shiftl, 1u, 32u, 0u)]
    [InlineData(Op.Shiftl, 1u, 0xFFFFFFFFu, 0u)]
    [InlineData(Op.Ushiftr, 0x80000000u, 4u, 0x08000000u)]
    [InlineData(Op.Ushiftr, 0x80000000u, 32u, 0u)]
    [InlineData(Op.Sshiftr, 0x80000000u, 4u, 0xF8000000u)]
    [InlineData(Op.Sshiftr, 0x80000000u, 32u, 0xFFFFFFFFu)]
    [InlineData(Op.Sshiftr, 0x40000000u, 32u, 0u)]
    [InlineData(Op.Sshiftr, 0x40000000u, 0xFFFFFFFFu, 0u)]
    public void TheIntegerOpcodesComputeWhatTheSpecificationSays(Op opcode, uint a, uint b, uint answer)
    {
        Assert.Equal(answer, Computed(opcode, a, b));
    }

    [Theory]
    [InlineData(Op.Neg, 5u, 0xFFFFFFFBu)]
    [InlineData(Op.Neg, 0u, 0u)]
    [InlineData(Op.Bitnot, 0x0000FFFFu, 0xFFFF0000u)]
    [InlineData(Op.Copy, 0x12345678u, 0x12345678u)]
    [InlineData(Op.Sexs, 0x00008000u, 0xFFFF8000u)]
    [InlineData(Op.Sexs, 0x00001234u, 0x00001234u)]
    [InlineData(Op.Sexb, 0x000000FFu, 0xFFFFFFFFu)]
    [InlineData(Op.Sexb, 0x0000007Fu, 0x0000007Fu)]
    public void TheOneOperandOpcodesComputeWhatTheSpecificationSays(Op opcode, uint a, uint answer)
    {
        var program = new GlulxProgram();
        program.Op(opcode, Modes.Constant(a), Modes.Memory(Slot0));
        program.Op(Op.Quit);
        var machine = program.Booted();
        machine.Run();

        Assert.Equal(answer, machine.Memory.ReadWord((int)Slot0));
    }

    // The most negative value has no positive of its own, so dividing
    // it by -1 is the one overflow integer math has.
    [Theory]
    [InlineData(Op.Div, 7u, 0u, "division by zero (Glulx: Integer Math)")]
    [InlineData(Op.Div, 0x80000000u, 0xFFFFFFFFu, "division overflow: the most negative value by -1")]
    [InlineData(Op.Mod, 7u, 0u, "division by zero taking a remainder (Glulx: Integer Math)")]
    [InlineData(Op.Mod, 0x80000000u, 0xFFFFFFFFu, "division overflow taking a remainder")]
    public void DivisionByZeroAndItsOneOverflowAreRefused(Op opcode, uint a, uint b, string message)
    {
        Assert.Equal(message, Refusal(() => Computed(opcode, a, b)));
    }

    // copys and copyb narrow what they store, and a narrowed value
    // pushed to the stack still lands as a full word.
    [Fact]
    public void TheNarrowCopiesStoreOnlyTheirOwnWidth()
    {
        var program = new GlulxProgram();
        program.Op(Op.Astore, Modes.Constant(Slot0), Modes.Constant(0), Modes.Constant(0xFFFFFFFF));
        program.Op(Op.Copys, Modes.Word(0x11223344), Modes.Memory(Slot0));
        program.Op(Op.Copyb, Modes.Word(0x55667788), Modes.Memory(Slot1));
        program.Op(Op.Quit);
        var machine = program.Booted();
        machine.Run();

        Assert.Equal(0x3344FFFFu, machine.Memory.ReadWord((int)Slot0));
        Assert.Equal(0x88, machine.Memory.ReadByte((int)Slot1));
    }

    // A branch offset of 1 returns 1 from the current function, which
    // in the outermost function ends the story: the shortest way to
    // ask whether a comparison held.
    [Theory]
    [InlineData(Op.Jeq, 5u, 5u, true)]
    [InlineData(Op.Jeq, 5u, 6u, false)]
    [InlineData(Op.Jne, 5u, 6u, true)]
    [InlineData(Op.Jne, 5u, 5u, false)]
    [InlineData(Op.Jlt, 0xFFFFFFFFu, 1u, true)]
    [InlineData(Op.Jlt, 1u, 0xFFFFFFFFu, false)]
    [InlineData(Op.Jge, 1u, 0xFFFFFFFFu, true)]
    [InlineData(Op.Jge, 0xFFFFFFFFu, 1u, false)]
    [InlineData(Op.Jgt, 1u, 0xFFFFFFFFu, true)]
    [InlineData(Op.Jgt, 0xFFFFFFFFu, 1u, false)]
    [InlineData(Op.Jle, 0xFFFFFFFFu, 1u, true)]
    [InlineData(Op.Jle, 1u, 0xFFFFFFFFu, false)]
    [InlineData(Op.Jltu, 1u, 0xFFFFFFFFu, true)]
    [InlineData(Op.Jltu, 0xFFFFFFFFu, 1u, false)]
    [InlineData(Op.Jgeu, 0xFFFFFFFFu, 1u, true)]
    [InlineData(Op.Jgeu, 1u, 0xFFFFFFFFu, false)]
    [InlineData(Op.Jgtu, 0xFFFFFFFFu, 1u, true)]
    [InlineData(Op.Jgtu, 1u, 0xFFFFFFFFu, false)]
    [InlineData(Op.Jleu, 1u, 0xFFFFFFFFu, true)]
    [InlineData(Op.Jleu, 0xFFFFFFFFu, 1u, false)]
    public void TheComparisonsBranchWhenTheirTestHolds(Op opcode, uint a, uint b, bool taken)
    {
        var program = new GlulxProgram();
        program.Op(opcode, Modes.Constant(a), Modes.Constant(b), Modes.Constant(1));
        program.Op(Op.Add, Modes.Constant(7), Modes.Constant(0), Modes.Memory(Slot0));
        program.Op(Op.Quit);
        var machine = program.Booted();
        machine.Run();

        Assert.Equal(taken ? 0u : 7u, machine.Memory.ReadWord((int)Slot0));
    }

    [Theory]
    [InlineData(Op.Jz, 0u, true)]
    [InlineData(Op.Jz, 1u, false)]
    [InlineData(Op.Jnz, 1u, true)]
    [InlineData(Op.Jnz, 0u, false)]
    public void TheZeroTestsBranchWhenTheirTestHolds(Op opcode, uint a, bool taken)
    {
        var program = new GlulxProgram();
        program.Op(opcode, Modes.Constant(a), Modes.Constant(1));
        program.Op(Op.Add, Modes.Constant(7), Modes.Constant(0), Modes.Memory(Slot0));
        program.Op(Op.Quit);
        var machine = program.Booted();
        machine.Run();

        Assert.Equal(taken ? 0u : 7u, machine.Memory.ReadWord((int)Slot0));
    }

    // A real branch counts from just past the instruction, less two.
    [Fact]
    public void AJumpLandsWhereItsOffsetCounts()
    {
        var program = new GlulxProgram();
        program.Op(Op.Jump, Modes.Word(0));
        var after = program.Here;
        program.Op(Op.Add, Modes.Constant(7), Modes.Constant(0), Modes.Memory(Slot0));
        var target = program.Here;
        program.Op(Op.Add, Modes.Constant(9), Modes.Constant(0), Modes.Memory(Slot1));
        program.Op(Op.Quit);
        program.Patch(after - 4, (uint)(target - after + 2));
        var machine = program.Booted();
        machine.Run();

        Assert.Equal(0u, machine.Memory.ReadWord((int)Slot0));
        Assert.Equal(9u, machine.Memory.ReadWord((int)Slot1));
    }

    // jumpabs takes the address whole: no bias, and no return codes.
    [Fact]
    public void AnAbsoluteJumpTakesTheAddressWhole()
    {
        var program = new GlulxProgram();
        program.Op(Op.Jumpabs, Modes.Word(0));
        var after = program.Here;
        program.Op(Op.Add, Modes.Constant(7), Modes.Constant(0), Modes.Memory(Slot0));
        var target = program.Here;
        program.Op(Op.Quit);
        program.Patch(after - 4, (uint)target);
        var machine = program.Booted();
        machine.Run();

        Assert.Equal(0u, machine.Memory.ReadWord((int)Slot0));
    }

    // A branch offset of zero returns zero, which the outermost
    // function has nowhere to return to.
    [Fact]
    public void ABranchOfZeroReturnsZero()
    {
        var program = new GlulxProgram();
        program.Op(Op.Jump, Modes.Constant(0));
        program.Op(Op.Add, Modes.Constant(7), Modes.Constant(0), Modes.Memory(Slot0));
        var machine = program.Booted();

        Assert.Equal(1, machine.Run());
        Assert.False(machine.Running);
        Assert.Equal(0u, machine.Memory.ReadWord((int)Slot0));
    }

    // A called function's result comes home to the store its caller
    // named, and the arguments seat as the function's type directs.
    [Theory]
    [InlineData(Funcs.LocalArguments)]
    [InlineData(Funcs.StackArguments)]
    public void ACallReturnsThroughTheStubItLeft(int functype)
    {
        var callee = 160;
        var program = new GlulxProgram();
        program.Op(Op.Callfii, Modes.Constant((uint)callee), Modes.Constant(20), Modes.Constant(22), Modes.Memory(Slot0));
        program.Op(Op.Quit);

        // A function that adds its two arguments and returns the sum.
        var body = new GlulxProgram(callee, locals: 2, funcType: functype);

        if (functype == Funcs.StackArguments)
        {
            // The count arrives on top, then the arguments themselves.
            body.Op(Op.Copy, Modes.Stack, Modes.Discard);
            body.Op(Op.Add, Modes.Stack, Modes.Stack, Modes.Local(0));
        }
        else
        {
            body.Op(Op.Add, Modes.Local(0), Modes.Local(4), Modes.Local(0));
        }

        body.Op(Op.Return, Modes.Local(0));
        program.Lay(callee, body.Assembled);
        var machine = program.Booted();
        machine.Run();

        Assert.Equal(42u, machine.Memory.ReadWord((int)Slot0));
    }

    // call takes its arguments off the stack, first argument topmost.
    [Fact]
    public void CallTakesItsArgumentsOffTheStack()
    {
        var callee = 160;
        var program = new GlulxProgram();
        program.Op(Op.Copy, Modes.Constant(22), Modes.Stack);
        program.Op(Op.Copy, Modes.Constant(20), Modes.Stack);
        program.Op(Op.Call, Modes.Constant((uint)callee), Modes.Constant(2), Modes.Memory(Slot0));
        program.Op(Op.Quit);

        var body = new GlulxProgram(callee, locals: 2);
        body.Op(Op.Add, Modes.Local(0), Modes.Local(4), Modes.Local(0));
        body.Op(Op.Return, Modes.Local(0));
        program.Lay(callee, body.Assembled);
        var machine = program.Booted();
        machine.Run();

        Assert.Equal(42u, machine.Memory.ReadWord((int)Slot0));
    }

    [Theory]
    [InlineData(Op.Callf, 0u)]
    [InlineData(Op.Callfi, 1u)]
    [InlineData(Op.Callfii, 2u)]
    [InlineData(Op.Callfiii, 3u)]
    public void TheImmediateCallsSeatAsManyArgumentsAsTheyName(Op opcode, uint count)
    {
        var callee = 160;
        var program = new GlulxProgram();
        Slot[] args = [Modes.Constant((uint)callee), Modes.Constant(10), Modes.Constant(20), Modes.Constant(30)];
        program.Op(opcode, [.. args[..(int)(count + 1)], Modes.Memory(Slot0)]);
        program.Op(Op.Quit);

        // The count of arguments a C0 function was handed is the word
        // its own stack opens with.
        var body = new GlulxProgram(callee, funcType: Funcs.StackArguments);
        body.Op(Op.Return, Modes.Stack);
        program.Lay(callee, body.Assembled);
        var machine = program.Booted();
        machine.Run();

        Assert.Equal(count, machine.Memory.ReadWord((int)Slot0));
    }

    // A tailcall replaces the frame without touching the stub beneath
    // it, so the replacement returns to the original caller.
    [Fact]
    public void ATailcallReturnsToItsCallersCaller()
    {
        var middle = 160;
        var last = 200;
        var program = new GlulxProgram();
        program.Op(Op.Callfi, Modes.Constant((uint)middle), Modes.Constant(5), Modes.Memory(Slot0));
        program.Op(Op.Quit);

        var body = new GlulxProgram(middle, locals: 1);
        body.Op(Op.Copy, Modes.Local(0), Modes.Stack);
        body.Op(Op.Tailcall, Modes.Constant((uint)last), Modes.Constant(1));
        program.Lay(middle, body.Assembled);

        var tail = new GlulxProgram(last, locals: 1);
        tail.Op(Op.Mul, Modes.Local(0), Modes.Constant(3), Modes.Local(0));
        tail.Op(Op.Return, Modes.Local(0));
        program.Lay(last, tail.Assembled);

        var machine = program.Booted();
        machine.Run();

        Assert.Equal(15u, machine.Memory.ReadWord((int)Slot0));
    }

    // catch stores a token and branches; throw unwinds to that token
    // and delivers a value where the catch said.
    [Fact]
    public void ACatchTokenIsWhereAThrowLands()
    {
        var callee = 160;
        var program = new GlulxProgram();
        program.Op(Op.Catch, Modes.Memory(Slot0), Modes.Word(0));
        // A throw comes home to the instruction just past the catch,
        // so the handler lives here and the protected code is what the
        // catch branches to.
        var after = program.Here;
        program.Op(Op.Add, Modes.Constant(7), Modes.Constant(0), Modes.Memory(Slot1));
        program.Op(Op.Quit);
        var guarded = program.Here;
        program.Op(Op.Callf, Modes.Constant((uint)callee), Modes.Discard);
        program.Op(Op.Add, Modes.Constant(9), Modes.Constant(0), Modes.Memory(Slot1));
        program.Op(Op.Quit);
        program.Patch(after - 4, (uint)(guarded - after + 2));

        var body = new GlulxProgram(callee);
        body.Op(Op.Throw, Modes.Constant(99), Modes.Memory(Slot0));
        program.Lay(callee, body.Assembled);

        var machine = program.Booted();
        machine.Run();

        // The throw unwound past the call and never reached the 9, and
        // it delivered 99 where the catch's own store points.
        Assert.Equal(7u, machine.Memory.ReadWord((int)Slot1));
        Assert.Equal(99u, machine.Memory.ReadWord((int)Slot0));
    }

    [Fact]
    public void AThrowToSomewhereThatIsNoTokenIsRefused()
    {
        var program = new GlulxProgram();
        program.Op(Op.Throw, Modes.Constant(1), Modes.Constant(6));
        var machine = program.Booted();

        Assert.Equal("a throw's catch token of 6 is not a place on this stack (Glulx: Continuations)", Refusal(() => machine.Run()));

        var beyond = new GlulxProgram();
        beyond.Op(Op.Throw, Modes.Constant(1), Modes.Word(0x10000));

        Assert.Equal("a throw's catch token of 65536 is not a place on this stack (Glulx: Continuations)", Refusal(() => beyond.Booted().Run()));
    }

    // Array data is addressed by index at the width the opcode names.
    [Fact]
    public void TheArrayOpcodesIndexAtTheirOwnWidth()
    {
        var program = new GlulxProgram();
        program.Op(Op.Astore, Modes.Constant(Slot0), Modes.Constant(1), Modes.Word(0x11223344));
        program.Op(Op.Astores, Modes.Constant(Slot0), Modes.Constant(1), Modes.Word(0xAABB));
        program.Op(Op.Astoreb, Modes.Constant(Slot0), Modes.Constant(1), Modes.Constant(0xCC));
        program.Op(Op.Aload, Modes.Constant(Slot0), Modes.Constant(1), Modes.Memory(0x150));
        program.Op(Op.Aloads, Modes.Constant(Slot0), Modes.Constant(1), Modes.Memory(0x154));
        program.Op(Op.Aloadb, Modes.Constant(Slot0), Modes.Constant(1), Modes.Memory(0x158));
        program.Op(Op.Quit);
        var machine = program.Booted();
        machine.Run();

        Assert.Equal(0x11223344u, machine.Memory.ReadWord(0x150));
        Assert.Equal(0xAABBu, machine.Memory.ReadWord(0x154));
        Assert.Equal(0xCCu, machine.Memory.ReadWord(0x158));
    }

    // Bits number sequentially in both directions from the least
    // significant bit of the base address (Glulx: Array Data).
    [Fact]
    public void BitsNumberInBothDirectionsFromTheirBase()
    {
        var program = new GlulxProgram();
        program.Op(Op.Astorebit, Modes.Constant(Slot0), Modes.Constant(9), Modes.Constant(1));
        program.Op(Op.Astorebit, Modes.Constant(Slot0), Modes.Constant(0xFFFFFFFF), Modes.Constant(1));
        program.Op(Op.Aloadbit, Modes.Constant(Slot0), Modes.Constant(9), Modes.Memory(0x150));
        program.Op(Op.Aloadbit, Modes.Constant(Slot0), Modes.Constant(0xFFFFFFFF), Modes.Memory(0x154));
        program.Op(Op.Aloadbit, Modes.Constant(Slot0), Modes.Constant(8), Modes.Memory(0x158));
        program.Op(Op.Astorebit, Modes.Constant(Slot0), Modes.Constant(9), Modes.Constant(0));
        program.Op(Op.Aloadbit, Modes.Constant(Slot0), Modes.Constant(9), Modes.Memory(0x15C));
        program.Op(Op.Quit);
        var machine = program.Booted();
        machine.Run();

        Assert.Equal(1u, machine.Memory.ReadWord(0x150));
        Assert.Equal(1u, machine.Memory.ReadWord(0x154));
        Assert.Equal(0u, machine.Memory.ReadWord(0x158));
        Assert.Equal(0u, machine.Memory.ReadWord(0x15C));
        // Bit 9 sat in the byte after the base, cleared again by the
        // last store, and bit -1 in the byte before it.
        Assert.Equal(0x00, machine.Memory.ReadByte((int)Slot0 + 1));
        Assert.Equal(0x80, machine.Memory.ReadByte((int)Slot0 - 1));
    }

    [Fact]
    public void TheStackOpcodesCountPeekSwapCopyAndRoll()
    {
        var program = new GlulxProgram();

        foreach (var value in (uint[])[10, 20, 30])
        {
            program.Op(Op.Copy, Modes.Constant(value), Modes.Stack);
        }

        program.Op(Op.Stkcount, Modes.Memory(Slot0));
        program.Op(Op.Stkpeek, Modes.Constant(2), Modes.Memory(Slot1));
        program.Op(Op.Stkswap);
        program.Op(Op.Copy, Modes.Stack, Modes.Memory(0x150));
        program.Op(Op.Stkcopy, Modes.Constant(2));
        program.Op(Op.Stkcount, Modes.Memory(0x154));
        program.Op(Op.Quit);
        var machine = program.Booted();
        machine.Run();

        Assert.Equal(3u, machine.Memory.ReadWord((int)Slot0));
        Assert.Equal(10u, machine.Memory.ReadWord((int)Slot1));
        // The swap put 20 on top, and taking it leaves 30 and 10.
        Assert.Equal(20u, machine.Memory.ReadWord(0x150));
        Assert.Equal(4u, machine.Memory.ReadWord(0x154));
    }

    // stkroll rotates the top values either way, and the rotation is
    // the same distance whichever sign the places came in.
    [Theory]
    [InlineData(1u, 30u, 10u, 20u)]
    [InlineData(0xFFFFFFFFu, 20u, 30u, 10u)]
    [InlineData(3u, 10u, 20u, 30u)]
    [InlineData(0u, 10u, 20u, 30u)]
    [InlineData(0x80000000u, 30u, 10u, 20u)]
    public void StkrollRotatesTheTopValuesEitherWay(uint places, uint bottom, uint middle, uint top)
    {
        var program = new GlulxProgram();

        foreach (var value in (uint[])[10, 20, 30])
        {
            program.Op(Op.Copy, Modes.Constant(value), Modes.Stack);
        }

        program.Op(Op.Stkroll, Modes.Constant(3), Modes.Constant(places));
        program.Op(Op.Copy, Modes.Stack, Modes.Memory(0x150));
        program.Op(Op.Copy, Modes.Stack, Modes.Memory(0x154));
        program.Op(Op.Copy, Modes.Stack, Modes.Memory(0x158));
        program.Op(Op.Quit);
        var machine = program.Booted();
        machine.Run();

        Assert.Equal(top, machine.Memory.ReadWord(0x150));
        Assert.Equal(middle, machine.Memory.ReadWord(0x154));
        Assert.Equal(bottom, machine.Memory.ReadWord(0x158));
    }

    [Fact]
    public void AStackOpcodeReachingPastTheFrameIsRefused()
    {
        Assert.Equal("stkpeek at 0 reaches outside the current stack range (Glulx: The Stack)", Refusal(Op.Stkpeek, Modes.Constant(0), Modes.Discard));
        Assert.Equal("stkpeek at -1 reaches outside the current stack range (Glulx: The Stack)", Refusal(Op.Stkpeek, Modes.Constant(0xFFFFFFFF), Modes.Discard));
        Assert.Equal("stkswap with fewer than two values (Glulx: The Stack)", Refusal(Op.Stkswap));
        Assert.Equal("stkcopy with a negative count (Glulx: The Stack)", Refusal(Op.Stkcopy, Modes.Constant(0xFFFFFFFF)));
        Assert.Equal("stkcopy of 2 exceeds the values above the frame", Refusal(Op.Stkcopy, Modes.Constant(2)));
        Assert.Equal("stkroll with a negative count (Glulx: The Stack)", Refusal(Op.Stkroll, Modes.Constant(0xFFFFFFFF), Modes.Constant(1)));
        Assert.Equal("stkroll of 2 exceeds the values above the frame", Refusal(Op.Stkroll, Modes.Constant(2), Modes.Constant(1)));
    }

    // A copy of nothing is not an error, and neither is a roll of it.
    [Fact]
    public void CopyingAndRollingNothingIsAllowed()
    {
        var program = new GlulxProgram();
        program.Op(Op.Stkcopy, Modes.Constant(0));
        program.Op(Op.Stkroll, Modes.Constant(0), Modes.Constant(1));
        program.Op(Op.Stkcount, Modes.Memory(Slot0));
        program.Op(Op.Quit);
        var machine = program.Booted();
        machine.Run();

        Assert.Equal(0u, machine.Memory.ReadWord((int)Slot0));
    }

    [Fact]
    public void TheStringTableIsSetAndReadBack()
    {
        var program = new GlulxProgram();
        program.Op(Op.Getstringtbl, Modes.Memory(Slot0));
        program.Op(Op.Setstringtbl, Modes.Word(0x300));
        program.Op(Op.Getstringtbl, Modes.Memory(Slot1));
        program.Op(Op.Quit);
        var machine = program.Booted();
        machine.Run();

        Assert.Equal(0u, machine.Memory.ReadWord((int)Slot0));
        Assert.Equal(0x300u, machine.Memory.ReadWord((int)Slot1));
        Assert.Equal(0x300u, machine.StringTable);
    }

    // Selecting an unsupported system selects the null system, and
    // Glk without a library installed is exactly that.
    [Theory]
    [InlineData(0u, 0u, 0u, 0u)]
    [InlineData(1u, 0x500u, 1u, 0x500u)]
    [InlineData(2u, 0x500u, 0u, 0u)]
    [InlineData(9u, 0x500u, 0u, 0u)]
    public void TheOutputSystemIsSelectedAndReadBack(uint mode, uint rock, uint chosen, uint kept)
    {
        var program = new GlulxProgram();
        program.Op(Op.Setiosys, Modes.Constant(mode), Modes.Word(rock));
        program.Op(Op.Getiosys, Modes.Memory(Slot0), Modes.Memory(Slot1));
        program.Op(Op.Quit);
        var machine = program.Booted();
        machine.Run();

        Assert.Equal(chosen, machine.Memory.ReadWord((int)Slot0));
        Assert.Equal(kept, machine.Memory.ReadWord((int)Slot1));
    }

    // A zero range asks for a full word, a positive one for 0 through
    // the range less one, and a negative one for the mirror.
    [Fact]
    public void TheDiceRollAtThreeRanges()
    {
        var program = new GlulxProgram();
        program.Op(Op.Setrandom, Modes.Constant(11));
        program.Op(Op.Random, Modes.Constant(0), Modes.Memory(Slot0));
        program.Op(Op.Random, Modes.Constant(6), Modes.Memory(Slot1));
        program.Op(Op.Random, Modes.Constant(0xFFFFFFFA), Modes.Memory(0x150));
        program.Op(Op.Quit);
        var machine = program.Booted();
        machine.Run();

        var expected = new Randomizer(11);

        Assert.Equal(expected.Word(), machine.Memory.ReadWord((int)Slot0));
        Assert.Equal(expected.Below(6), machine.Memory.ReadWord((int)Slot1));
        Assert.Equal(0u - expected.Below(6), machine.Memory.ReadWord(0x150));
    }

    [Fact]
    public void TheMapIsMeasuredAndResized()
    {
        var program = new GlulxProgram();
        program.Op(Op.Getmemsize, Modes.Memory(Slot0));
        program.Op(Op.Setmemsize, Modes.Word(2048), Modes.Memory(Slot1));
        program.Op(Op.Getmemsize, Modes.Memory(0x150));
        program.Op(Op.Quit);
        var machine = program.Booted();
        machine.Run();

        Assert.Equal(1024u, machine.Memory.ReadWord((int)Slot0));
        Assert.Equal(0u, machine.Memory.ReadWord((int)Slot1));
        Assert.Equal(2048u, machine.Memory.ReadWord(0x150));
        Assert.Equal(2048, machine.Memory.EndMem);
    }

    [Fact]
    public void RunsOfMemoryAreCopiedAndCleared()
    {
        var program = new GlulxProgram();
        program.Op(Op.Astore, Modes.Constant(Slot0), Modes.Constant(0), Modes.Word(0x11223344));
        program.Op(Op.Mcopy, Modes.Constant(4), Modes.Constant(Slot0), Modes.Constant(0x150));
        program.Op(Op.Mzero, Modes.Constant(4), Modes.Constant(Slot0));
        program.Op(Op.Quit);
        var machine = program.Booted();
        machine.Run();

        Assert.Equal(0x11223344u, machine.Memory.ReadWord(0x150));
        Assert.Equal(0u, machine.Memory.ReadWord((int)Slot0));
    }

    // verify recomputes the checksum: 0 for sound, 1 for not.
    [Fact]
    public void VerifyAnswersForTheChecksumTheStoryCarries()
    {
        var program = new GlulxProgram();
        program.Op(Op.Verify, Modes.Memory(Slot0));
        program.Op(Op.Quit);
        var machine = program.Booted();
        machine.Run();

        Assert.Equal(0u, machine.Memory.ReadWord((int)Slot0));

        var image = program.Build();
        image[500] ^= 1;
        var broken = new Machine(new Story(image));
        broken.Run();

        Assert.Equal(1u, broken.Memory.ReadWord((int)Slot0));
    }

    // A restart returns to the load state and calls the start function
    // again, so the only way round the loop is a protected range: that
    // is silently unaffected, wherever it lies (Glulx: Game State).
    [Fact]
    public void ARestartReturnsToTheLoadStateAndSparesWhatIsProtected()
    {
        var program = new GlulxProgram();
        program.Op(Op.Protect, Modes.Constant(0x150), Modes.Constant(4));
        program.Op(Op.Jnz, Modes.Memory(0x150), Modes.Constant(1));
        program.Op(Op.Astore, Modes.Constant(0x150), Modes.Constant(0), Modes.Constant(1));
        program.Op(Op.Astore, Modes.Constant(Slot0), Modes.Constant(0), Modes.Constant(9));
        program.Op(Op.Restart);
        var machine = program.Booted();

        Assert.Equal(7, machine.Run());
        Assert.False(machine.Running);
        Assert.True(machine.Discontinuity);
        Assert.Equal(1u, machine.Memory.ReadWord(0x150));
        // What was not protected went back to the load state.
        Assert.Equal(0u, machine.Memory.ReadWord((int)Slot0));
    }

    // This interpreter has no debugger to hand off to, so the
    // specification directs it to treat the value as fatal.
    [Fact]
    public void ADebugTrapHaltsLoudlyCarryingItsValue()
    {
        Assert.Equal("debugtrap with value 42 (Glulx: Miscellaneous)", Refusal(Op.Debugtrap, Modes.Constant(42)));
    }

    // The whole roster is known even where it is not yet carried, so a
    // number the dispatch does not serve says what it is rather than
    // pretending to be a mystery.
    [Fact]
    public void AnOpcodeNotCarriedYetSaysSoAndOneNotDefinedSaysThat()
    {
        var program = new GlulxProgram();
        program.Op(Op.Malloc, Modes.Constant(16), Modes.Discard);

        Assert.Equal("executed malloc, an opcode this machine does not carry yet", Refusal(() => program.Booted().Run()));

        var unknown = new GlulxProgram();
        unknown.Op((Op)0x99, Modes.Constant(0));

        Assert.Equal("executed opcode $99, which Glulx 3.1.3 does not define (Glulx: Dictionary of Opcodes)", Refusal(() => unknown.Booted().Run()));
    }

    // An opcode number spells its own length, so the same opcode
    // reached through a longer encoding runs the same way.
    [Fact]
    public void AnOpcodeReadsAtEveryEncodedLength()
    {
        var program = new GlulxProgram();

        // Room for the instruction, which is then laid over the nops:
        // add, spelled in two bytes rather than one.
        for (var pad = 0; pad < 8; pad++)
        {
            program.Op(Op.Nop);
        }

        program.Op(Op.Quit);
        program.Lay(program.Start + 3, 0x80, 0x10, 0x11, 0x06, 2, 3, (byte)(Slot0 >> 8), (byte)(Slot0 & 0xFF));
        var machine = program.Booted();
        machine.Run();

        Assert.Equal(5u, machine.Memory.ReadWord((int)Slot0));
    }

    // The longest encoding names the same opcode as the shortest, and
    // nop does nothing, well.
    [Fact]
    public void TheLongestEncodingNamesTheSameOpcode()
    {
        var program = new GlulxProgram();
        program.Op(Op.Nop);

        for (var pad = 0; pad < 10; pad++)
        {
            program.Op(Op.Nop);
        }

        program.Op(Op.Quit);
        // add, spelled in four bytes rather than one.
        program.Lay(program.Start + 4, 0xC0, 0x00, 0x00, 0x10, 0x11, 0x06, 2, 3, (byte)(Slot0 >> 8), (byte)(Slot0 & 0xFF));
        var machine = program.Booted();

        Assert.Equal(3, machine.Run());
        Assert.Equal(5u, machine.Memory.ReadWord((int)Slot0));
    }

    // Execution that leaves the map says where it went.
    [Fact]
    public void ExecutionOffTheMapIsRefused()
    {
        var program = new GlulxProgram();
        program.Op(Op.Jumpabs, Modes.Word(0x1000));
        var machine = program.Booted();

        Assert.Equal("execution ran off the memory map at $1000 (Glulx: The Memory Map)", Refusal(() => machine.Run()));

        var wrapped = new GlulxProgram();
        wrapped.Op(Op.Jumpabs, Modes.Word(0xFFFFFFF0));

        Assert.Equal("execution ran off the memory map at $fffffff0 (Glulx: The Memory Map)", Refusal(() => wrapped.Booted().Run()));
    }

    // Code in RAM is shaped afresh on every visit, so a story that
    // writes its own code runs the code it wrote.
    [Fact]
    public void CodeInRamIsReadAgainEveryTime()
    {
        // The code itself lives in RAM here, so the flag it turns has
        // to sit clear of it.
        const uint Flag = 0x180;
        const uint Seen = 0x184;
        var program = new GlulxProgram(at: 300);
        var loop = program.Here;
        program.Op(Op.Aload, Modes.Constant(Flag), Modes.Constant(0), Modes.Memory(Seen));
        program.Op(Op.Astore, Modes.Constant(Flag), Modes.Constant(0), Modes.Constant(1));
        program.Op(Op.Jnz, Modes.Memory(Seen), Modes.Constant(1));
        program.Op(Op.Jump, Modes.Word(0));
        program.Patch(program.Here - 4, (uint)(loop - program.Here + 2));
        var machine = program.Booted();

        Assert.Equal(7, machine.Run());
        Assert.Equal(1u, machine.Memory.ReadWord((int)Flag));
    }

    // The four resume stubs are the string decoder's now, but a
    // string terminator where a function result belongs is nobody's.
    [Fact]
    public void AStringTerminatorIsRefusedWhereAResultBelongs()
    {
        var callee = 160;
        var program = new GlulxProgram();
        program.Op(Op.Callf, Modes.Constant((uint)callee), Modes.Discard);
        program.Op(Op.Quit);

        var body = new GlulxProgram(callee);
        body.Op(Op.Return, Modes.Constant(0));
        program.Lay(callee, body.Assembled);

        var machine = program.Booted();
        machine.Step();
        // Rewrite the stub the call just left, which sits four words
        // below the new frame.
        machine.Stack.WriteWord(machine.Stack.FramePtr - StackMemory.StubSize, (uint)DestType.ResumeFunction);

        Assert.Equal(
            "a string-terminator call stub arrived where a function result belongs (Glulx: Call Stubs)",
            Refusal(() => machine.Run()));
    }

    private static uint Computed(Op opcode, uint a, uint b)
    {
        var program = new GlulxProgram();
        program.Op(opcode, Modes.Constant(a), Modes.Constant(b), Modes.Memory(Slot0));
        program.Op(Op.Quit);
        var machine = program.Booted();
        machine.Run();

        return machine.Memory.ReadWord((int)Slot0);
    }

    // What one instruction refused, run on its own.
    private static string Refusal(Op opcode, params Slot[] args)
    {
        var program = new GlulxProgram();
        program.Op(opcode, args);
        program.Op(Op.Quit);

        return Refusal(() => program.Booted().Run());
    }

    private static string Refusal(Action work) => Assert.Throws<GlulxException>(work).Message;
}
