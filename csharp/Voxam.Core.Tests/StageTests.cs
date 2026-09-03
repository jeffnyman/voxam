using System.Text;
using Voxam.Core.Tests.Support;

namespace Voxam.Core.Tests;

/// <summary>Version 6: the main routine, the window ledger, and the opcodes a plain stream answers quietly (§8.8).</summary>
public class StageTests
{
    private const int G0 = 0x10;
    private const int G1 = 0x11;

    private static void PrintGlobal(StoryBuilder b, int variable)
    {
        b.OpVar(0x06, Arg.Var(variable));
        b.NewLine();
    }

    // A Version 6 story is entered through its main routine (§5.4).
    private static (StoryBuilder Builder, int Main) Six()
    {
        var b = new StoryBuilder(6);
        return (b, b.Routine(0));
    }

    private static string Run(StoryBuilder b, int main, IEnumerable<string>? input = null)
    {
        b.Quit();
        b.InitialPc = main;
        return Session.Run(b, input).Output;
    }

    private static void PrintWindProp(StoryBuilder b, int window, int property)
    {
        b.Ext(0x13, Arg.Small(window), Arg.Small(property));
        b.Store(G0);
        PrintGlobal(b, G0);
    }

    [Fact]
    public void ExecutionBeginsAtTheMainRoutine()
    {
        var (b, main) = Six();
        b.Print("six");
        Assert.Equal("six", Run(b, main));
    }

    [Fact]
    public void AnyOfTheEightWindowsMayBeSelectedAndTheStreamHearsOfTwo()
    {
        var (b, main) = Six();
        b.OpVar(0x0A, Arg.Small(5));
        b.OpVar(0x0B, Arg.Small(1));
        b.Print("top");
        b.OpVar(0x0B, Arg.Small(0));
        b.Print("story");
        b.OpVar(0x0B, Arg.Small(5));
        b.Print("five");
        b.OpVar(0x0B, Arg.Large(0xFFFD));
        b.Ext(0x13, Arg.Large(0xFFFD), Arg.Small(0));
        b.Store(G0);
        PrintGlobal(b, G0);
        Assert.Equal("top\nstoryfive1\n", Run(b, main));

        var (bad, badMain) = Six();
        bad.OpVar(0x0B, Arg.Small(9));
        bad.Quit();
        bad.InitialPc = badMain;
        Assert.Contains("window 9 is not one of the eight", Session.Fails<ZMachineException>(bad).Message, StringComparison.Ordinal);
    }

    [Fact]
    public void EraseWindowNamesTheEightAndUnsplitsOnMinusOne()
    {
        var (b, main) = Six();
        b.OpVar(0x0A, Arg.Small(5));
        b.OpVar(0x0B, Arg.Small(1));
        b.Print("up");
        // Erasing a window the stream never painted changes nothing.
        b.OpVar(0x0D, Arg.Small(7));
        b.Print("still");
        b.OpVar(0x0D, Arg.Large(0xFFFF));
        b.Print("back");
        b.OpVar(0x0D, Arg.Large(0xFFFD));
        b.OpVar(0x0D, Arg.Large(0xFFFE));
        b.Print("end");
        Assert.Equal("upstillbackend", Run(b, main));
    }

    [Fact]
    public void SplitTilesTheLedgerVertically()
    {
        var (b, main) = Six();
        b.OpVar(0x0A, Arg.Small(40));
        PrintWindProp(b, 1, WindowLedger.YCoordinate);
        PrintWindProp(b, 1, WindowLedger.YSize);
        PrintWindProp(b, 0, WindowLedger.YCoordinate);
        PrintWindProp(b, 0, WindowLedger.YSize);
        b.OpVar(0x0A, Arg.Large(300));
        PrintWindProp(b, 0, WindowLedger.YSize);
        Assert.Equal("1\n40\n41\n215\n0\n", Run(b, main));
    }

    [Fact]
    public void CursorMovesLandInTheLedger()
    {
        var (b, main) = Six();
        var array = b.Alloc(4);
        b.OpVar(0x0F, Arg.Small(5), Arg.Small(7));
        b.OpVar(0x10, Arg.Large(array));
        b.Op2(0x0F, Arg.Large(array), Arg.Small(0));
        b.Store(G0);
        PrintGlobal(b, G0);
        b.Op2(0x0F, Arg.Large(array), Arg.Small(1));
        b.Store(G0);
        PrintGlobal(b, G0);
        b.OpVar(0x0F, Arg.Small(3), Arg.Small(4), Arg.Small(2));
        PrintWindProp(b, 2, WindowLedger.YCursor);
        PrintWindProp(b, 2, WindowLedger.XCursor);
        // -1 and -2 are cursor chrome and move nothing.
        b.OpVar(0x0F, Arg.Large(0xFFFF));
        b.OpVar(0x0F, Arg.Large(0xFFFE), Arg.Small(0));
        PrintWindProp(b, 0, WindowLedger.YCursor);
        Assert.Equal("5\n7\n3\n4\n5\n", Run(b, main));
    }

    [Fact]
    public void WindowPropertiesFollowTheOpcodes()
    {
        var (b, main) = Six();
        PrintWindProp(b, 0, WindowLedger.XSize);
        PrintWindProp(b, 1, WindowLedger.Attributes);
        b.Ext(0x10, Arg.Small(3), Arg.Small(10), Arg.Small(20));
        b.Ext(0x11, Arg.Small(3), Arg.Small(30), Arg.Small(40));
        PrintWindProp(b, 3, WindowLedger.YCoordinate);
        PrintWindProp(b, 3, WindowLedger.XCoordinate);
        PrintWindProp(b, 3, WindowLedger.YSize);
        PrintWindProp(b, 3, WindowLedger.XSize);
        b.Ext(0x12, Arg.Small(3), Arg.Small(6));
        b.Ext(0x12, Arg.Small(3), Arg.Small(1), Arg.Small(1));
        PrintWindProp(b, 3, WindowLedger.Attributes);
        b.Ext(0x19, Arg.Small(3), Arg.Small(WindowLedger.LineCount), Arg.Small(77));
        PrintWindProp(b, 3, WindowLedger.LineCount);
        b.Ext(0x08, Arg.Small(4), Arg.Small(6));
        PrintWindProp(b, 0, WindowLedger.LeftMargin);
        PrintWindProp(b, 0, WindowLedger.RightMargin);
        b.Ext(0x08, Arg.Small(1), Arg.Small(2), Arg.Small(5));
        PrintWindProp(b, 5, WindowLedger.LeftMargin);
        Assert.Equal("80\n8\n10\n20\n30\n40\n7\n77\n4\n6\n1\n", Run(b, main));
    }

    [Fact]
    public void AWidthBearingRedirectionWritesPrintFormsLineShape()
    {
        var (b, main) = Six();
        var table = b.Alloc(120);
        var boxed = b.Alloc(40);
        var flat = b.Alloc(40);
        b.OpVar(0x13, Arg.Small(3), Arg.Large(table), Arg.Large(0x10000 - 20));
        b.Print("the quick brown fox jumps over the lazy dog");
        b.NewLine();
        b.Print("abcdefghijklmnopqrstuvwxyz");
        b.OpVar(0x13, Arg.Large(0xFFFD));
        b.Ext(0x1A, Arg.Large(table));
        b.Op2(0x0F, Arg.Small(0), Arg.Small(Header.TotalWidth / 2));
        b.Store(G0);
        PrintGlobal(b, G0);
        // A window's width is the limit when the operand names one.
        b.OpVar(0x13, Arg.Small(3), Arg.Large(boxed), Arg.Small(1));
        b.Print("ab");
        b.OpVar(0x13, Arg.Large(0xFFFD));
        b.Ext(0x1A, Arg.Large(boxed));
        // Without a width the table is flat, and the widest line still lands at $30.
        b.OpVar(0x13, Arg.Small(3), Arg.Large(flat));
        b.Print("ab\ncde");
        b.OpVar(0x13, Arg.Large(0xFFFD));
        b.Op2(0x0F, Arg.Small(0), Arg.Small(Header.TotalWidth / 2));
        b.Store(G0);
        PrintGlobal(b, G0);
        Assert.Equal("the quick brown fox\njumps over the lazy\ndog\nabcdefghijklmnopqrst\nuvwxyz\n20\nab\n3\n", Run(b, main));
    }

    // Before Version 6 a third operand means nothing: the table stays flat.
    [Fact]
    public void AThirdOperandIsIgnoredBeforeVersionSix()
    {
        var b = new StoryBuilder(5);
        var table = b.Alloc(40);
        b.OpVar(0x13, Arg.Small(3), Arg.Large(table), Arg.Large(0x10000 - 2));
        b.Print("abcd");
        b.OpVar(0x13, Arg.Large(0xFFFD));
        b.Op2(0x0F, Arg.Large(table), Arg.Small(0));
        b.Store(G0);
        PrintGlobal(b, G0);
        b.Quit();
        Assert.Equal("4\n", Session.Run(b).Output);
    }

    [Fact]
    public void AColourClaimingFrontendReadsTheColourPair()
    {
        var b = new StoryBuilder(5);
        b.OpVar(0x08, Arg.Small(7));
        b.OpVar(0x08, Arg.Small(1));
        b.OpVar(0x08, Arg.Small(2));
        b.Op2(0x1B, Arg.Stack, Arg.Stack);
        b.OpVar(0x06, Arg.Stack);
        b.Quit();
        var output = new StringBuilder();
        new Machine(b.Build(), new LoudFrontend(t => output.Append(t)), () => null, null).Run();
        Assert.Equal("7", output.ToString());
    }

    [Fact]
    public void ABlankLineTravelsAsASpace()
    {
        var (b, main) = Six();
        var table = b.Alloc(40);
        b.OpVar(0x13, Arg.Small(3), Arg.Large(table), Arg.Large(0x10000 - 10));
        b.Print("a\n\nb");
        b.OpVar(0x13, Arg.Large(0xFFFD));
        b.Ext(0x1A, Arg.Large(table));
        Assert.Equal("a\n \nb\n", Run(b, main));
    }

    [Fact]
    public void PicturesAndTheMouseAnswerAsAFrontendWithoutThem()
    {
        var (b, main) = Six();
        var array = b.Words(0x1111, 0x2222, 0x3333, 0x4444);
        b.Ext(0x06, Arg.Small(0), Arg.Large(array));
        b.Branch(true, 5);
        b.Print("A");
        b.Op2(0x0F, Arg.Large(array), Arg.Small(0));
        b.Store(G0);
        PrintGlobal(b, G0);
        b.Ext(0x06, Arg.Small(5), Arg.Large(array));
        b.Branch(true, 5);
        b.Print("B");
        b.Ext(0x05, Arg.Small(1), Arg.Small(2), Arg.Small(3));
        b.Ext(0x07, Arg.Small(1));
        b.Ext(0x1C, Arg.Large(array));
        b.Ext(0x14, Arg.Small(0), Arg.Small(8));
        b.Ext(0x17, Arg.Small(1));
        b.Ext(0x16, Arg.Large(array));
        b.Op2(0x0F, Arg.Large(array), Arg.Small(3));
        b.Store(G0);
        PrintGlobal(b, G0);
        b.Ext(0x1B, Arg.Small(1), Arg.Large(array));
        b.Branch(true, 5);
        b.Print("C");
        b.Ext(0x1D, Arg.Small(1));
        b.Store(G0);
        PrintGlobal(b, G0);
        b.Ext(0x1D, Arg.Large(0xFFFF));
        b.Store(G0);
        PrintGlobal(b, G0);
        b.Ext(0x1D, Arg.Small(0));
        b.Store(G0);
        PrintGlobal(b, G0);
        Assert.Equal("A0\nB0\nC0\n1\n1\n", Run(b, main));

        var (bad, badMain) = Six();
        bad.Ext(0x1D, Arg.Small(2));
        bad.Store(G0);
        bad.Quit();
        bad.InitialPc = badMain;
        Assert.Contains("asks for mode 2", Session.Fails<ZMachineException>(bad).Message, StringComparison.Ordinal);
    }

    [Fact]
    public void UserStacksPushPullAndPop()
    {
        var (b, main) = Six();
        var stack = b.Words(2, 0, 0);
        b.Ext(0x18, Arg.Small(7), Arg.Large(stack));
        b.Branch(true, 5);
        b.Print("A");
        b.Ext(0x18, Arg.Small(8), Arg.Large(stack));
        b.Branch(true, 5);
        b.Print("B");
        b.Ext(0x18, Arg.Small(9), Arg.Large(stack));
        b.Branch(true, 5);
        b.Print("C");
        b.OpVar(0x09, Arg.Large(stack));
        b.Store(G0);
        PrintGlobal(b, G0);
        b.Ext(0x15, Arg.Small(1), Arg.Large(stack));
        b.Op2(0x0F, Arg.Large(stack), Arg.Small(0));
        b.Store(G0);
        PrintGlobal(b, G0);
        // Without a user stack, pull pops the game stack and pop_stack discards.
        b.OpVar(0x08, Arg.Small(4));
        b.OpVar(0x08, Arg.Small(5));
        b.OpVar(0x09);
        b.Store(G0);
        PrintGlobal(b, G0);
        b.Ext(0x15, Arg.Small(1));
        Assert.Equal("C8\n2\n5\n", Run(b, main));
    }

    [Fact]
    public void SetColourReadsNoOperandsOnAStreamWithoutColours()
    {
        var (b, main) = Six();
        b.OpVar(0x08, Arg.Small(5));
        b.Op2(0x1B, Arg.Stack, Arg.Stack);
        b.OpVar(0x06, Arg.Stack);
        Assert.Equal("5", Run(b, main));
    }

    [Fact]
    public void InputStreamsAreTheKeyboardOrNothingYet()
    {
        var (b, main) = Six();
        b.OpVar(0x14, Arg.Small(0));
        b.Print("kb");
        Assert.Equal("kb", Run(b, main));

        var file = new StoryBuilder(5);
        file.OpVar(0x14, Arg.Small(1));
        Assert.Contains("input_stream at $1000 is not yet ported", Session.Fails<ZMachineException>(file).Message, StringComparison.Ordinal);

        var unknown = new StoryBuilder(5);
        unknown.OpVar(0x14, Arg.Small(2));
        Assert.Contains("names stream 2, but §10.2 defines only 0 and 1", Session.Fails<ZMachineException>(unknown).Message, StringComparison.Ordinal);
    }

    [Fact]
    public void TheHeaderIsStampedForVersionSix()
    {
        var (b, main) = Six();

        foreach (var field in new[] { Header.Flags1, Header.FontWidth, Header.FontHeight, Header.DefaultBackground, Header.DefaultForeground })
        {
            b.Op2(0x10, Arg.Small(0), Arg.Small(field));
            b.Store(G0);
            PrintGlobal(b, G0);
        }

        foreach (var field in new[] { Header.Flags2, Header.ScreenWidthUnits, Header.ScreenHeightUnits })
        {
            b.Op2(0x0F, Arg.Small(0), Arg.Small(field / 2));
            b.Store(G0);
            PrintGlobal(b, G0);
        }

        b.Quit();
        b.InitialPc = main;
        var story = b.Build();
        story[Header.Flags1] = 0xFF;
        StoryBuilder.Word(story, Header.Flags2, 0xFFFE);
        var output = new StringBuilder();
        new Machine(story, new LoudFrontend(t => output.Append(t)), () => null, null).Run();
        // Bold, italic, colours and sound presence stand; fixed pitch,
        // timed input and pictures clear. The font bytes are swapped in
        // Version 6, and the units are the loud frontend's 8 by 16.
        Assert.Equal("109\n16\n8\n2\n9\n-298\n640\n384\n", output.ToString());
    }
}
