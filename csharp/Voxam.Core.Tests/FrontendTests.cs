using System.Text;

namespace Voxam.Core.Tests;

public class FrontendTests
{
    private static (PlainFrontend Frontend, StringBuilder Output) Plain()
    {
        var output = new StringBuilder();
        return (new PlainFrontend(text => output.Append(text)), output);
    }

    [Fact]
    public void TheStreamClaimsWhatADumbTerminalHas()
    {
        var (frontend, _) = Plain();
        Assert.False(frontend.HasStatusLine);
        Assert.False(frontend.HasScreenSplitting);
        Assert.False(frontend.HasSounds);
        Assert.False(frontend.HasBold);
        Assert.False(frontend.HasItalic);
        Assert.True(frontend.HasFixedPitch);
        Assert.True(frontend.HasTimedInput);
        Assert.False(frontend.HasColours);
        Assert.Equal(255, frontend.ScreenLines);
        Assert.Equal(80, frontend.ScreenColumns);
    }

    [Fact]
    public void AStatusBarUpperWindowIsMuted()
    {
        var (frontend, output) = Plain();
        frontend.SetWindow(0);
        frontend.SplitWindow(1);
        frontend.SetWindow(1);
        frontend.SetCursor(1, 10);
        frontend.Write("Score: 0");
        frontend.SetWindow(0);
        frontend.Write("story");
        Assert.Equal("story", output.ToString());
        Assert.Equal((1, 1), frontend.CursorPosition());
    }

    [Fact]
    public void ATallUpperWindowFlowsWithItsLayout()
    {
        var (frontend, output) = Plain();
        frontend.SplitWindow(5);
        // A cursor move in the story window changes nothing.
        frontend.SetCursor(3, 3);
        frontend.SetWindow(1);
        frontend.SetCursor(1, 5);
        frontend.Write("Title");
        Assert.Equal((1, 10), frontend.CursorPosition());
        frontend.SetCursor(2, 3);
        frontend.Write("Sub");
        frontend.SetCursor(2, 2);
        frontend.SetWindow(0);
        frontend.Write("story");
        Assert.Equal("    Title\n  Substory".Replace("Substory", "Sub\nstory", StringComparison.Ordinal), output.ToString());
    }

    [Fact]
    public void ErasingEverythingUnsplitsAndReselectsTheStory()
    {
        var (frontend, output) = Plain();
        frontend.SplitWindow(5);
        frontend.SetWindow(1);
        frontend.EraseWindow(-1);
        frontend.Write("back");
        frontend.EraseWindow(0);
        Assert.Equal("back", output.ToString());
    }

    [Fact]
    public void PresentationRequestsAreTheConformingQuiet()
    {
        var (frontend, output) = Plain();
        frontend.ShowStatus(new Status("Room", 1, 2, false));
        frontend.SetStyle(ScreenModel.Bold);
        frontend.SetFont(3);
        frontend.SetColour(3, 4);
        frontend.SetBuffering(false);
        frontend.EraseLine();
        frontend.BeginInput();
        frontend.ResumeInput();
        frontend.AbandonInput();
        frontend.Write("only this");
        Assert.Equal("only this", output.ToString());
    }

    [Fact]
    public void RectanglesBecomeLines()
    {
        var (frontend, output) = Plain();
        frontend.WriteRectangle(["ab", "cd"]);
        Assert.Equal("ab\ncd", output.ToString());
    }
}
