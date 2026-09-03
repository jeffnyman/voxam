namespace Voxam.Core.Tests;

public class WindowLedgerTests
{
    private static WindowLedger Booted() => new(200, 320, 9, 2, fontWidth: 8, fontHeight: 16);

    [Fact]
    public void EveryWindowBootsToItsStandardState()
    {
        var ledger = Booted();
        Assert.Equal(0, ledger.Selected);
        Assert.Equal(200, ledger.Property(0, WindowLedger.YSize));
        Assert.Equal(320, ledger.Property(0, WindowLedger.XSize));
        Assert.Equal(WindowLedger.Wrapping | WindowLedger.Scrolling | WindowLedger.Transcripting | WindowLedger.Buffering, ledger.Property(0, WindowLedger.Attributes));
        Assert.Equal(0, ledger.Property(1, WindowLedger.YSize));
        Assert.Equal(320, ledger.Property(1, WindowLedger.XSize));
        Assert.Equal(WindowLedger.Buffering, ledger.Property(1, WindowLedger.Attributes));
        Assert.Equal(0, ledger.Property(7, WindowLedger.XSize));
        Assert.Equal(1, ledger.Property(5, WindowLedger.YCoordinate));
        Assert.Equal(1, ledger.Property(5, WindowLedger.XCursor));
        Assert.Equal(1, ledger.Property(5, WindowLedger.FontNumber));
        Assert.Equal((16 << 8) | 8, ledger.Property(5, WindowLedger.FontSize));
        Assert.Equal((2 << 8) | 9, ledger.Property(5, WindowLedger.ColourData));
    }

    [Fact]
    public void MinusThreeNamesTheSelectedWindowInBothSpellings()
    {
        var ledger = Booted();
        ledger.Selected = 4;
        Assert.Equal(4, ledger.Resolve(WindowLedger.CurrentWindow));
        Assert.Equal(4, ledger.Resolve(0xFFFD));
        Assert.Equal(7, ledger.Resolve(7));
        Assert.Contains("window 8 is not one of the eight", Assert.Throws<ZMachineException>(() => ledger.Resolve(8)).Message, StringComparison.Ordinal);
        Assert.Contains("window -1 is not one of the eight", Assert.Throws<ZMachineException>(() => ledger.Property(-1, 0)).Message, StringComparison.Ordinal);
    }

    [Fact]
    public void PropertiesAreReadAndWrittenWithinTheEighteen()
    {
        var ledger = Booted();
        ledger.WriteProperty(3, WindowLedger.LineCount, 7);
        Assert.Equal(7, ledger.Property(3, WindowLedger.LineCount));
        Assert.Contains("not one of §8.8.3.2's eighteen", Assert.Throws<ZMachineException>(() => ledger.Property(3, 18)).Message, StringComparison.Ordinal);
        Assert.Contains("not one of §8.8.3.2's eighteen", Assert.Throws<ZMachineException>(() => ledger.WriteProperty(3, -1, 0)).Message, StringComparison.Ordinal);
        Assert.Contains("is a true colour, which must not be written", Assert.Throws<ZMachineException>(() => ledger.WriteProperty(3, WindowLedger.TrueForeground, 0)).Message, StringComparison.Ordinal);
    }

    [Fact]
    public void GeometryAndMarginsLandWhereTheOpcodesPutThem()
    {
        var ledger = Booted();
        ledger.Move(2, 10, 20);
        ledger.Resize(2, 30, 40);
        ledger.SetMargins(2, 3, 4);
        Assert.Equal(10, ledger.Property(2, WindowLedger.YCoordinate));
        Assert.Equal(20, ledger.Property(2, WindowLedger.XCoordinate));
        Assert.Equal(30, ledger.Property(2, WindowLedger.YSize));
        Assert.Equal(40, ledger.Property(2, WindowLedger.XSize));
        Assert.Equal(3, ledger.Property(2, WindowLedger.LeftMargin));
        Assert.Equal(4, ledger.Property(2, WindowLedger.RightMargin));
    }

    [Fact]
    public void RestyleSetsTurnsOnTurnsOffAndReverses()
    {
        var ledger = Booted();
        ledger.Restyle(1, 6, 0);
        Assert.Equal(6, ledger.Property(1, WindowLedger.Attributes));
        ledger.Restyle(1, 1, 1);
        Assert.Equal(7, ledger.Property(1, WindowLedger.Attributes));
        ledger.Restyle(1, 2, 2);
        Assert.Equal(5, ledger.Property(1, WindowLedger.Attributes));
        ledger.Restyle(1, 4, 3);
        Assert.Equal(1, ledger.Property(1, WindowLedger.Attributes));
        Assert.Contains("operation 9 is not one of §15's four", Assert.Throws<ZMachineException>(() => ledger.Restyle(1, 1, 9)).Message, StringComparison.Ordinal);
    }
}
