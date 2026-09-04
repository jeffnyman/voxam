using System.Text;
using Voxam.Core.Tests.Support;

namespace Voxam.Core.Tests;

/// <summary>The machine's seams for a painted face: the raw keyboard, the wall clock, and the status line.</summary>
public class SeamTests
{
    private const int G0 = 0x10;

    private static void PrintGlobal(StoryBuilder b, int variable)
    {
        b.OpVar(0x06, Arg.Var(variable));
        b.NewLine();
    }

    private static (string Output, LoudFrontend Loud) Run(
        StoryBuilder b,
        IEnumerable<string>? input = null,
        Func<double?, string?>? keys = null,
        Func<double, string?>? timed = null)
    {
        var output = new StringBuilder();
        var loud = new LoudFrontend(text => output.Append(text));
        var lines = (input ?? []).GetEnumerator();
        new Machine(b.Build(), loud, () => lines.MoveNext() ? lines.Current : null, 1, keys, timed).Run();
        return (output.ToString(), loud);
    }

    private static Func<double?, string?> Keys(params string?[] keys)
    {
        var queue = new Queue<string?>(keys);
        return _ => queue.Dequeue();
    }

    [Fact]
    public void TheStatusLineIsDrawnAtEveryReadAndOnRequest()
    {
        var b = new StoryBuilder();
        b.Objects(new ObjectSpec("Cellar"));
        b.Dictionary("", "look");
        var text = b.Bytes(10, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0);
        var parse = b.Bytes(4, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0);
        b.Op2(0x0D, Arg.Small(16), Arg.Small(1));
        b.Op2(0x0D, Arg.Small(17), Arg.Large(0xFFFB));
        b.Op2(0x0D, Arg.Small(18), Arg.Small(7));
        b.OpVar(0x04, Arg.Large(text), Arg.Large(parse));
        b.Op0(0xC);
        b.Quit();
        var story = b.Build();
        var (_, loud) = Run(b, ["look"]);
        Assert.Equal(["status Cellar -5 7 False", "status Cellar -5 7 False"], loud.Told);

        story[Header.Flags1] |= 0x02;
        var output = new StringBuilder();
        var timed = new LoudFrontend(t => output.Append(t));
        var lines = new Queue<string>(["look"]);
        new Machine(story, timed, () => lines.Count > 0 ? lines.Dequeue() : null, 1).Run();
        Assert.Equal("status Cellar -5 7 True", timed.Told[0]);
    }

    [Fact]
    public void ARawKeyboardFeedsReadCharAndSkipsWhatZsciiCannotSpell()
    {
        var b = new StoryBuilder(5);
        b.OpVar(0x16, Arg.Small(1));
        b.Store(G0);
        PrintGlobal(b, G0);
        b.Quit();
        Assert.Equal("120\n", Run(b, keys: Keys(null, "↑", "x")).Output);
    }

    [Fact]
    public void ATimedKeyReadOnTheClockFiresItsInterruptWhenTheWaitExpires()
    {
        var b = new StoryBuilder(5);
        var declines = b.Routine(0);
        b.Print("tick");
        b.Op1(0xB, Arg.Small(0));
        var ends = b.Routine(0);
        b.Op1(0xB, Arg.Small(1));
        b.InitialPc = b.Here;
        b.OpVar(0x16, Arg.Small(1), Arg.Small(10), Arg.Large(b.Packed(declines)));
        b.Store(G0);
        PrintGlobal(b, G0);
        b.OpVar(0x16, Arg.Small(1), Arg.Small(10), Arg.Large(b.Packed(ends)));
        b.Store(G0);
        PrintGlobal(b, G0);
        b.Quit();
        var waits = new List<double?>();

        string? Source(double? timeout)
        {
            waits.Add(timeout);
            return waits.Count switch { 1 => null, 2 => "→", 3 => "y", _ => null };
        }

        Assert.Equal("tick121\n0\n", Run(b, keys: Source).Output);
        Assert.Equal([1.0, 1.0, 1.0, 1.0], waits);
    }

    [Fact]
    public void ATimedLineReadOnTheClockRedisplaysAfterAPrintingInterrupt()
    {
        var b = new StoryBuilder(5);
        var prints = b.Routine(0);
        b.Print("tock");
        b.Op1(0xB, Arg.Small(0));
        var quiet = b.Routine(0);
        b.Op1(0xB, Arg.Small(0));
        var ends = b.Routine(0);
        b.Op1(0xB, Arg.Small(1));
        b.Dictionary("", "look");
        var text = b.Bytes(10, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0);
        var parse = b.Bytes(4, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0);
        b.InitialPc = b.Here;

        foreach (var routine in new[] { prints, quiet, ends })
        {
            b.OpVar(0x04, Arg.Large(text), Arg.Large(parse), Arg.Small(20), Arg.Large(b.Packed(routine)));
            b.Store(G0);
            PrintGlobal(b, G0);
        }

        b.Quit();
        var calls = 0;

        string? Timed(double seconds)
        {
            Assert.Equal(2.0, seconds);
            calls++;
            return calls is 1 or 3 or 5 ? null : "look";
        }

        var (output, loud) = Run(b, timed: Timed);
        Assert.Equal("tock13\n13\n0\n", output);
        Assert.Equal(["begin", "resume", "begin", "begin", "abandon"], loud.Told);
    }

    [Fact]
    public void ThePatientTypistRedisplaysTooWhenItsInterruptPrinted()
    {
        var b = new StoryBuilder(5);
        var prints = b.Routine(0);
        b.Print("tock");
        b.Op1(0xB, Arg.Small(0));
        var quiet = b.Routine(0);
        b.Op1(0xB, Arg.Small(0));
        b.Dictionary("", "look");
        var text = b.Bytes(10, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0);
        var parse = b.Bytes(4, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0);
        b.InitialPc = b.Here;
        b.OpVar(0x04, Arg.Large(text), Arg.Large(parse), Arg.Small(20), Arg.Large(b.Packed(prints)));
        b.Store(G0);
        b.OpVar(0x04, Arg.Large(text), Arg.Large(parse), Arg.Small(20), Arg.Large(b.Packed(quiet)));
        b.Store(G0);
        b.Quit();
        var (output, loud) = Run(b, ["look", "look"]);
        Assert.Equal("tock", output);
        Assert.Equal(["begin", "resume", "begin"], loud.Told);
    }

    [Fact]
    public void ScreenFieldsFollowAResizeFromVersionFour()
    {
        var three = new StoryBuilder();
        three.Quit();
        var early = new Machine(three.Build(), new LoudFrontend(_ => { }), () => null, null);
        early.Run();
        early.RefreshScreenFields();
        Assert.Equal(0, early.Memory.ReadByte(Header.ScreenLines));

        var five = new StoryBuilder(5);
        five.Quit();
        var machine = new Machine(five.Build(), new LoudFrontend(_ => { }), () => null, null);
        machine.Run();
        machine.Memory.WriteByte(Header.ScreenLines, 0);
        machine.Memory.WriteWord(Header.ScreenWidthUnits, 0);
        machine.RefreshScreenFields();
        Assert.Equal(24, machine.Memory.ReadByte(Header.ScreenLines));
        Assert.Equal(80, machine.Memory.ReadByte(Header.ScreenColumns));
        // Only Version 6 measures in pixels; here a unit is a character.
        Assert.Equal(80, machine.Memory.ReadWord(Header.ScreenWidthUnits));
        Assert.Equal(24, machine.Memory.ReadWord(Header.ScreenHeightUnits));

        var four = new StoryBuilder(4);
        four.Quit();
        var mid = new Machine(four.Build(), new LoudFrontend(_ => { }), () => null, null);
        mid.Run();
        mid.Memory.WriteByte(Header.ScreenColumns, 0);
        mid.RefreshScreenFields();
        Assert.Equal(80, mid.Memory.ReadByte(Header.ScreenColumns));
    }

    [Fact]
    public void PresentationOpcodesReachAFrontendThatClaimsThem()
    {
        var b = new StoryBuilder(5);
        b.OpVar(0x11, Arg.Small(2));
        b.OpVar(0x12, Arg.Small(0));
        b.OpVar(0x0E, Arg.Small(1));
        b.OpVar(0x0E, Arg.Small(2));
        b.Op2(0x1B, Arg.Small(3), Arg.Large(0xFFFF));
        b.Ext(0x04, Arg.Small(3));
        b.Store(G0);
        PrintGlobal(b, G0);
        b.Quit();
        var (output, loud) = Run(b);
        Assert.Equal("1\n", output);
        Assert.Equal(["style 2", "buffer False", "erase line", "colour 3 -1", "font 3"], loud.Told);
    }
}
