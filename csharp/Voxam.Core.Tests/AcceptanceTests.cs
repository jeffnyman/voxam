namespace Voxam.Core.Tests;

public class AcceptanceTests
{
    private static readonly string Here = Path.GetFullPath(".");

    [Fact]
    public void TheGrammarReadsDirectivesCommentsFencesAndCommands()
    {
        var script = AcceptanceScript.Parse(
            [
                "! SEED=92",
                "! GAME=../games/zork1.z3",
                "",
                "# the opening",
                "  n. n. u  ",
                "```",
                "skipped",
                "```",
                "get egg",
            ],
            Here);
        Assert.Equal(92, script.Seed);
        Assert.Equal(Path.GetFullPath(Path.Combine(Here, "../games/zork1.z3")), script.Game);
        Assert.Equal(["n. n. u", "get egg"], script.Commands);
    }

    [Fact]
    public void AnUnclosedFenceTruncatesTheRest()
    {
        var script = AcceptanceScript.Parse(["! GAME=g.z3", "one", "```", "two", "three"], Here);
        Assert.Equal(["one"], script.Commands);
        Assert.Null(script.Seed);
    }

    [Theory]
    [InlineData("! SEED", "a directive is ! KEY=VALUE")]
    [InlineData("! SEED=abc", "the seed must be a non-negative integer")]
    [InlineData("! SEED=-1", "the seed must be a non-negative integer")]
    [InlineData("! COLOUR=blue", "unknown directive COLOUR")]
    public void MalformedDirectivesAreRefusedByLine(string line, string message)
    {
        var error = Assert.Throws<ZMachineException>(() => AcceptanceScript.Parse(["! GAME=g.z3", line], Here));
        Assert.Contains($"line 2: {message}", error.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void AScriptMustNameAGame()
    {
        var error = Assert.Throws<ZMachineException>(() => AcceptanceScript.Parse(["look"], Here));
        Assert.Contains("names no game", error.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void AFileIsReadRelativeToItself()
    {
        var directory = Directory.CreateTempSubdirectory("voxam-accept");

        try
        {
            var path = Path.Combine(directory.FullName, "walk.accept");
            File.WriteAllLines(path, ["! GAME=story.z5", "look"]);
            var script = AcceptanceScript.Parse(path);
            Assert.Equal(Path.Combine(directory.FullName, "story.z5"), script.Game);
            Assert.Equal(["look"], script.Commands);
        }
        finally
        {
            directory.Delete(recursive: true);
        }
    }
}
