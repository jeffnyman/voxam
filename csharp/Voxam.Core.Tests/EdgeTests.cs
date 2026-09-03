using System.Text;
using Voxam.Core.Tests.Support;

namespace Voxam.Core.Tests;

/// <summary>A frontend claiming everything, so the header stamping's other halves run.</summary>
internal sealed class LoudFrontend(Action<string> write) : IFrontend
{
    private readonly PlainFrontend _plain = new(write);

    public bool HasStatusLine => true;
    public bool HasScreenSplitting => true;
    public bool HasSounds => true;
    public bool HasBold => true;
    public bool HasItalic => true;
    public bool HasFixedPitch => false;
    public bool HasTimedInput => false;
    public bool HasColours => true;
    public int ScreenLines => 24;
    public int ScreenColumns => 80;
    public int FontWidth => 8;
    public int FontHeight => 16;

    public void Write(string text) => _plain.Write(text);
    public void WriteRectangle(IReadOnlyList<string> rows) => _plain.WriteRectangle(rows);
    public void SplitWindow(int lines) => _plain.SplitWindow(lines);
    public void SetWindow(int window) => _plain.SetWindow(window);
    public void EraseWindow(int window) => _plain.EraseWindow(window);
    public void SetCursor(int line, int column) => _plain.SetCursor(line, column);
    public (int Line, int Column) CursorPosition() => _plain.CursorPosition();
}

public class EdgeTests
{
    private const int G0 = 0x10;

    private static void PrintGlobal(StoryBuilder b, int variable)
    {
        b.OpVar(0x06, Arg.Var(variable));
        b.NewLine();
    }

    // A story whose routine and string come first, with the entry
    // point after them, so packed addresses of every scale are exercised.
    private static string ScaledStory(int version, string word, int routinesOffset = 0, int stringsOffset = 0)
    {
        var b = new StoryBuilder(version) { RoutinesOffset = routinesOffset, StringsOffset = stringsOffset };
        var routine = b.Routine(0);
        b.Op1(0xB, Arg.Small(version));
        b.AlignCode();
        var text = b.Here;
        b.Raw(StoryBuilder.ZString(word));
        b.AlignCode();
        b.InitialPc = b.Here;
        b.Call(routine, G0);
        PrintGlobal(b, G0);
        b.Op1(0xD, Arg.Large(b.PackedString(text)));
        b.Op0(0xD);
        b.Branch(true, 5);
        b.Print("bad");
        b.Print("ok");
        b.Quit();
        return Session.Run(b).Output;
    }

    [Fact]
    public void VersionOneStoriesRunWithoutTheLaterHeaderFields()
    {
        var b = new StoryBuilder(1);
        b.Print("hi");
        b.Quit();
        var (output, machine) = Session.Run(b);
        Assert.Equal("hi", output);
        Assert.Equal(0, machine.Memory.ReadByte(Header.Flags1));
        Assert.Equal(1, machine.Memory.ReadByte(Header.StandardMajor));
    }

    [Fact]
    public void VersionFiveScalesByFour()
    {
        Assert.Equal("5\nfiveok", ScaledStory(5, "five"));
    }

    [Fact]
    public void VersionSevenAddsTheHeaderOffsets()
    {
        Assert.Equal("7\nsevenok", ScaledStory(7, "seven", routinesOffset: 0x40, stringsOffset: 0x80));
    }

    [Fact]
    public void VersionEightScalesByEight()
    {
        Assert.Equal("8\neightok", ScaledStory(8, "eight"));
    }

    [Fact]
    public void StoresReachLocalVariables()
    {
        var b = new StoryBuilder();
        var routine = b.Routine(1);
        b.Op2(0x14, Arg.Small(1), Arg.Small(2));
        b.Store(1);
        b.Op1(0xB, Arg.Var(1));
        b.InitialPc = b.Here;
        b.Call(routine, G0);
        PrintGlobal(b, G0);
        b.Quit();
        Assert.Equal("3\n", Session.Run(b).Output);
    }

    [Fact]
    public void AVariableZeroOperandPopsTheStack()
    {
        var b = new StoryBuilder();
        b.OpVar(0x08, Arg.Small(5));
        b.OpVar(0x06, Arg.Stack);
        b.Quit();
        Assert.Equal("5", Session.Run(b).Output);
    }

    [Fact]
    public void ANonStoringCallOfZeroStoresNothing()
    {
        var b = new StoryBuilder(5);
        b.Op1(0xF, Arg.Small(0));
        b.Print("on");
        b.Quit();
        Assert.Equal("on", Session.Run(b).Output);
    }

    [Fact]
    public void TheDictionaryIsReadOnceAndTheParseBufferBounded()
    {
        var b = new StoryBuilder();
        b.Dictionary("", "look");
        var text = b.Bytes(20, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0);
        var parse = b.Bytes(1, 0, 0, 0, 0, 0);

        for (var k = 0; k < 2; k++)
        {
            b.OpVar(0x04, Arg.Large(text), Arg.Large(parse));
            b.Op2(0x10, Arg.Large(parse), Arg.Small(1));
            b.Store(G0);
            PrintGlobal(b, G0);
        }

        b.Quit();
        Assert.Equal("1\n1\n", Session.Run(b, ["look around now", "look"]).Output);
    }

    [Fact]
    public void UndoKeepsTheLastTenSnapshots()
    {
        var b = new StoryBuilder(5);

        for (var k = 0; k < 11; k++)
        {
            b.Ext(0x09);
            b.Store(G0);
        }

        PrintGlobal(b, G0);
        b.Quit();
        Assert.Equal("1\n", Session.Run(b).Output);
    }

    [Fact]
    public void RfalseReturnsZero()
    {
        var b = new StoryBuilder();
        var routine = b.Routine(0);
        b.Op0(0x1);
        b.InitialPc = b.Here;
        b.Call(routine, G0);
        PrintGlobal(b, G0);
        b.Quit();
        Assert.Equal("0\n", Session.Run(b).Output);
    }

    [Fact]
    public void RestoreAndPrivateOpcodesAreNotYetPorted()
    {
        var restore = new StoryBuilder();
        restore.Op0(0x6);
        restore.Branch(true, 5);
        Assert.Contains("restore at $1000 is not yet ported", Session.Fails<ZMachineException>(restore).Message, StringComparison.Ordinal);
        // Private and reserved extended opcodes pass unclaimed (§14.2).
        var extension = new StoryBuilder(5);
        extension.Ext(0x90, Arg.Small(1));
        extension.Ext(0x1F);
        extension.Ext(0x1F);
        // The arc_image band is presentation a stream never claimed.
        extension.Ext(0x80, Arg.Small(1), Arg.Small(2));
        extension.Print("on");
        extension.Quit();
        Assert.Equal("on", Session.Run(extension).Output);
    }

    // The one seed whose mixing lands on zero, a fixed point of the
    // xorshift, is nudged to the mixing constant instead.
    [Fact]
    public void ASeedThatMixesToZeroStillRolls()
    {
        var rng = new Randomizer(1640531527);
        var rolls = Enumerable.Range(0, 20).Select(_ => rng.Roll(6)).ToArray();
        Assert.Contains(rolls, roll => roll != 1);
        Assert.All(rolls, roll => Assert.InRange(roll, 1, 6));
    }

    [Fact]
    public void ALoudFrontendStampsTheOtherHalvesOfTheHeader()
    {
        foreach (var version in new[] { 3, 5 })
        {
            var b = new StoryBuilder(version);
            b.Op2(0x10, Arg.Small(0), Arg.Small(Header.Flags1));
            b.Store(G0);
            PrintGlobal(b, G0);
            b.Op2(0x0F, Arg.Small(0), Arg.Small(Header.Flags2 / 2));
            b.Store(G0);
            PrintGlobal(b, G0);
            b.Op2(0x10, Arg.Small(0), Arg.Small(Header.ScreenLines));
            b.Store(G0);
            PrintGlobal(b, G0);
            b.Quit();
            var output = new StringBuilder();
            new Machine(b.Build(), new LoudFrontend(t => output.Append(t)), () => null, null).Run();
            Assert.Equal(version == 3 ? "32\n128\n0\n" : "13\n128\n24\n", output.ToString());
        }
    }
}
