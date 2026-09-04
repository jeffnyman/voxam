using Voxam.Core.Glulx;
using GlulxException = Voxam.Core.GlulxException;

namespace Voxam.Tests.Glulx;

/// <summary>
/// Function entry: a type byte, a locals-format list, and the code
/// just past them (Glulx: Functions). The map here has ROM to 256 and
/// the stored image ending at 512.
/// </summary>
public sealed class FuncsTests
{
    private const int RamStart = 256;

    [Fact]
    public void AHeaderReadsItsTypeItsLocalsAndWhereItsCodeBegins()
    {
        var memory = Mapped((64, [0xC1, 4, 2, 1, 3, 0, 0]));
        var header = Funcs.ReadFunctionHeader(memory, 64);

        Assert.Equal(Funcs.LocalArguments, header.FuncType);
        Assert.Equal([new LocalsFormat(4, 2), new LocalsFormat(1, 3)], header.LocalsFormat);
        Assert.Equal(71, header.CodeAddr);
    }

    // C2 through DF are reserved for function types yet to be
    // defined, and the difference tells an author whether an address
    // is wrong or merely too new for the interpreter.
    [Theory]
    [InlineData(0x00, "the address $40 holds type $0, which is not a function at all (Glulx: Functions)")]
    [InlineData(0xE0, "the address $40 holds type $e0, which is not a function at all (Glulx: Functions)")]
    [InlineData(0xC2, "the address $40 holds type $c2, a function of a kind reserved for the future (Glulx: Functions)")]
    [InlineData(0xDF, "the address $40 holds type $df, a function of a kind reserved for the future (Glulx: Functions)")]
    public void AnAddressThatIsNoFunctionIsRefused(byte functype, string message)
    {
        var memory = Mapped((64, [functype, 0, 0]));

        Assert.Equal(message, Refusal(() => Funcs.ReadFunctionHeader(memory, 64)));
    }

    [Fact]
    public void ALocalTypeTheFormatBytesCannotMeanIsRefused()
    {
        var memory = Mapped((64, [0xC1, 3, 1, 0, 0]));

        Assert.Equal(
            "the function header at $41 declares a local type of 3, not 1, 2, or 4 (Glulx: Functions)",
            Refusal(() => Funcs.ReadFunctionHeader(memory, 64)));
    }

    // A header below RAMSTART cannot change, so it is kept and the
    // same one comes back; one reaching into RAM is read afresh, since
    // the story may have written over it.
    [Fact]
    public void AHeaderIsKeptOnlyWhereTheStoryCannotWriteIt()
    {
        var memory = Mapped((64, [0xC1, 0, 0]), (254, [0xC1, 4, 1, 0, 0]));
        var headers = new Dictionary<int, FunctionHeader>();

        var first = Funcs.ReadFunctionHeader(memory, 64, headers);
        Assert.Same(first, Funcs.ReadFunctionHeader(memory, 64, headers));

        var reaching = Funcs.ReadFunctionHeader(memory, 254, headers);
        Assert.Equal(259, reaching.CodeAddr);
        Assert.True(reaching.CodeAddr > RamStart);
        Assert.NotSame(reaching, Funcs.ReadFunctionHeader(memory, 254, headers));

        // And a caller that offers nowhere to keep one is answered
        // afresh every time.
        Assert.NotSame(Funcs.ReadFunctionHeader(memory, 64), Funcs.ReadFunctionHeader(memory, 64));
    }

    // A C0 function finds its arguments on its value stack, last
    // argument first with the count on top (Glulx: Functions).
    [Fact]
    public void AStackFunctionFindsItsArgumentsPushedBackwards()
    {
        var memory = Mapped((64, [0xC0, 0, 0]));
        var stack = new StackMemory(1024);
        var code = Funcs.PushCallFrame(memory, stack, 64, [10, 20, 30]);

        Assert.Equal(67, code);
        Assert.Equal(3u, stack.Pop());
        Assert.Equal(10u, stack.Pop());
        Assert.Equal(20u, stack.Pop());
        Assert.Equal(30u, stack.Pop());
    }

    // A C1 function finds them written into its locals in order, each
    // run starting at its own natural alignment.
    [Fact]
    public void ALocalFunctionFindsItsArgumentsSeatedInOrder()
    {
        var memory = Mapped((64, [0xC1, 1, 1, 4, 1, 0, 0]));
        var stack = new StackMemory(1024);
        Funcs.PushCallFrame(memory, stack, 64, [0xAA, 0x11223344]);

        Assert.Equal(0xAAu, stack.GetLocal(0, 1));
        Assert.Equal(0x11223344u, stack.GetLocal(4));
    }

    // Extra arguments drop silently and unfilled locals stay zero,
    // whether the arguments run out between runs or inside one.
    [Fact]
    public void ExtraArgumentsDropAndUnfilledLocalsStayZero()
    {
        var memory = Mapped((64, [0xC1, 4, 1, 4, 1, 0, 0]));
        var stack = new StackMemory(1024);
        Funcs.PushCallFrame(memory, stack, 64, [7]);

        Assert.Equal(7u, stack.GetLocal(0));
        Assert.Equal(0u, stack.GetLocal(4));

        var inside = new StackMemory(1024);
        Funcs.PushCallFrame(memory, inside, 64, [7, 8, 9, 10]);

        Assert.Equal(7u, inside.GetLocal(0));
        Assert.Equal(8u, inside.GetLocal(4));

        var partway = Mapped((64, [0xC1, 4, 3, 0, 0]));
        var stopped = new StackMemory(1024);
        Funcs.PushCallFrame(partway, stopped, 64, [7, 8]);

        Assert.Equal(8u, stopped.GetLocal(4));
        Assert.Equal(0u, stopped.GetLocal(8));
    }

    // With no address the arguments come off the stack, first argument
    // topmost; with one they read as a word array, which is what the
    // accelerated functions will need.
    [Fact]
    public void ArgumentsComeOffTheStackOrOutOfMemory()
    {
        var memory = Mapped((0x140, [0, 0, 0, 5, 0, 0, 0, 6]));
        var stack = new StackMemory(1024);
        stack.Push(30);
        stack.Push(20);
        stack.Push(10);

        Assert.Equal([10u, 20u], Funcs.PopArguments(stack, 2, memory));
        Assert.Equal([5u, 6u], Funcs.PopArguments(stack, 2, memory, 0x140));
        Assert.Equal([], Funcs.PopArguments(stack, 0, memory));
    }

    // A count with its sign bit set is a count gone wrong, not a big
    // one.
    [Fact]
    public void AnArgumentCountWithItsSignBitSetIsRefused()
    {
        var memory = Mapped((64, [0xC0, 0, 0]));
        var stack = new StackMemory(1024);

        Assert.Equal(
            "an argument count of 4294967295 has its sign bit set",
            Refusal(() => Funcs.PopArguments(stack, 0xFFFFFFFF, memory)));
    }

    private static Memory Mapped(params (int At, byte[] Data)[] laid)
    {
        var builder = new GlulxBuilder();

        foreach (var (at, data) in laid)
        {
            builder.Lay(at, data);
        }

        return new Memory(new Story(builder.Build()));
    }

    private static string Refusal(Action work) => Assert.Throws<GlulxException>(work).Message;
}
