using Voxam.Core.Tests.Support;

namespace Voxam.Core.Tests;

/// <summary>The keystroke queue and the patient typist behind timed reads (§15).</summary>
public class TypistTests
{
    private const int G0 = 0x10;

    private static void PrintGlobal(StoryBuilder b, int variable)
    {
        b.OpVar(0x06, Arg.Var(variable));
        b.NewLine();
    }

    // A routine returning its first argument, for the interrupt's
    // verdict: 1 ends the read, 0 lets it proceed.
    private static int Verdict(StoryBuilder b, int returned)
    {
        var routine = b.Routine(0);
        b.Op1(0xB, Arg.Small(returned));
        return routine;
    }

    [Fact]
    public void AnEmptyLineIsTheReturnKeyAndALineIsSpentByCharacter()
    {
        var b = new StoryBuilder(5);

        for (var k = 0; k < 5; k++)
        {
            b.OpVar(0x16, Arg.Small(1));
            b.Store(G0);
            PrintGlobal(b, G0);
        }

        b.Quit();
        Assert.Equal("97\n98\n13\n99\n13\n", Session.Run(b, ["ab", "", "c", ""]).Output);
    }

    [Fact]
    public void OnlyTheKeyboardIsAnInputDevice()
    {
        var b = new StoryBuilder(5);
        b.OpVar(0x16, Arg.Small(2));
        b.Store(G0);
        Assert.Contains("asks for input device 2", Session.Fails<ZMachineException>(b, ["x"]).Message, StringComparison.Ordinal);
    }

    [Fact]
    public void TheNimbleTypistAnswersTheRetryOfATerminatedRead()
    {
        var b = new StoryBuilder(5);
        var ends = Verdict(b, 1);
        b.InitialPc = b.Here;
        // read_char with a time and a terminating routine: the first
        // asking is terminated with 0, and jumping back to the very
        // same instruction finds the key ready.
        var read = b.Here;
        b.OpVar(0x16, Arg.Small(1), Arg.Small(10), Arg.Large(b.Packed(ends)));
        b.Store(G0);
        PrintGlobal(b, G0);
        b.Op1(0x0, Arg.Var(G0));
        // jz G0 ?back: the jz is emitted, and two bytes of long negative
        // branch follow, so "after" is two past here.
        var after = b.Here + 2;
        b.Branch(true, read - after + 2);
        b.Quit();
        Assert.Equal("0\n120\n", Session.Run(b, ["x"]).Output);
    }

    [Fact]
    public void AnInterruptThatDeclinesLetsTheKeyLand()
    {
        var b = new StoryBuilder(5);
        var declines = Verdict(b, 0);
        b.InitialPc = b.Here;
        b.OpVar(0x16, Arg.Small(1), Arg.Small(10), Arg.Large(b.Packed(declines)));
        b.Store(G0);
        PrintGlobal(b, G0);
        b.Quit();
        Assert.Equal("120\n", Session.Run(b, ["x"]).Output);
    }

    [Fact]
    public void KeysAlreadyQueuedBeatTheClock()
    {
        var b = new StoryBuilder(5);
        var ends = Verdict(b, 1);
        b.InitialPc = b.Here;
        b.OpVar(0x16, Arg.Small(1));
        b.Store(G0);
        PrintGlobal(b, G0);
        b.OpVar(0x16, Arg.Small(1), Arg.Small(10), Arg.Large(b.Packed(ends)));
        b.Store(G0);
        PrintGlobal(b, G0);
        b.Quit();
        Assert.Equal("120\n121\n", Session.Run(b, ["xy"]).Output);
    }

    [Fact]
    public void AnInterruptThatQuitsEndsEverything()
    {
        var b = new StoryBuilder(5);
        var quits = b.Routine(0);
        b.Print("bye");
        b.Quit();
        b.InitialPc = b.Here;
        b.OpVar(0x16, Arg.Small(1), Arg.Small(10), Arg.Large(b.Packed(quits)));
        b.Store(G0);
        b.Print("never");
        Assert.Equal("bye", Session.Run(b, ["x"]).Output);
    }

    [Fact]
    public void ATimedLineReadEndedByItsInterruptIsEmptied()
    {
        var b = new StoryBuilder(5);
        var ends = Verdict(b, 1);
        b.Dictionary("", "look");
        var text = b.Bytes(10, 4, (byte)'l', (byte)'o', (byte)'o', (byte)'k', 0, 0, 0, 0, 0, 0);
        var parse = b.Bytes(4, 9, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0);
        b.InitialPc = b.Here;
        b.OpVar(0x04, Arg.Large(text), Arg.Large(parse), Arg.Small(10), Arg.Large(b.Packed(ends)));
        b.Store(G0);
        PrintGlobal(b, G0);
        b.Op2(0x10, Arg.Large(text), Arg.Small(1));
        b.Store(G0);
        PrintGlobal(b, G0);
        b.Op2(0x10, Arg.Large(parse), Arg.Small(1));
        b.Store(G0);
        PrintGlobal(b, G0);
        // The next read is untimed and takes the line the first never consumed.
        b.OpVar(0x04, Arg.Large(text), Arg.Large(parse));
        b.Store(G0);
        b.Op2(0x10, Arg.Large(text), Arg.Small(1));
        b.Store(G0);
        PrintGlobal(b, G0);
        b.Quit();
        Assert.Equal("0\n0\n0\n4\n", Session.Run(b, ["wait"]).Output);
    }

    [Fact]
    public void ATimedLineReadWithoutAParseBufferLexesNothing()
    {
        var b = new StoryBuilder(5);
        var ends = Verdict(b, 1);
        var text = b.Bytes(10, 2, (byte)'g', (byte)'o', 0, 0, 0, 0, 0, 0, 0, 0);
        b.InitialPc = b.Here;
        b.OpVar(0x04, Arg.Large(text), Arg.Small(0), Arg.Small(10), Arg.Large(b.Packed(ends)));
        b.Store(G0);
        PrintGlobal(b, G0);
        b.Op2(0x10, Arg.Large(text), Arg.Small(1));
        b.Store(G0);
        PrintGlobal(b, G0);
        b.Quit();
        Assert.Equal("0\n0\n", Session.Run(b).Output);
    }

    [Fact]
    public void AVersionFourTimedLineReadEndsWithATerminatedEmptyString()
    {
        var b = new StoryBuilder(4);
        var ends = Verdict(b, 1);
        var text = b.Bytes(10, (byte)'x', (byte)'y', 0, 0, 0, 0, 0, 0, 0, 0);
        var parse = b.Bytes(4, 9, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0);
        b.InitialPc = b.Here;
        b.OpVar(0x04, Arg.Large(text), Arg.Large(parse), Arg.Small(10), Arg.Large(b.Packed(ends)));
        b.Op2(0x10, Arg.Large(text), Arg.Small(1));
        b.Store(G0);
        PrintGlobal(b, G0);
        b.Op2(0x10, Arg.Large(parse), Arg.Small(1));
        b.Store(G0);
        PrintGlobal(b, G0);
        b.Quit();
        Assert.Equal("0\n0\n", Session.Run(b).Output);
    }

    [Fact]
    public void ATimeWithoutARoutineOrBeforeVersionFourNeverFires()
    {
        var v5 = new StoryBuilder(5);
        v5.OpVar(0x16, Arg.Small(1), Arg.Small(10), Arg.Small(0));
        v5.Store(G0);
        PrintGlobal(v5, G0);
        v5.OpVar(0x16, Arg.Small(1), Arg.Small(0), Arg.Small(1));
        v5.Store(G0);
        PrintGlobal(v5, G0);
        v5.Quit();
        Assert.Equal("120\n121\n", Session.Run(v5, ["xy"]).Output);

        var v3 = new StoryBuilder();
        v3.Dictionary("", "look");
        var text = v3.Bytes(10, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0);
        var parse = v3.Bytes(4, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0);
        v3.OpVar(0x04, Arg.Large(text), Arg.Large(parse), Arg.Small(10), Arg.Small(1));
        v3.Op2(0x10, Arg.Large(parse), Arg.Small(1));
        v3.Store(G0);
        PrintGlobal(v3, G0);
        v3.Quit();
        Assert.Equal("1\n", Session.Run(v3, ["look"]).Output);
    }
}
