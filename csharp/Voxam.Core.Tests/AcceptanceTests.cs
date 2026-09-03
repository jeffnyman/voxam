namespace Voxam.Core.Tests;

public class AcceptanceTests
{
    private static readonly string Here = Path.GetFullPath(".");

    private static AcceptanceScript Parsed(params string[] lines) =>
        AcceptanceScript.Parse(["! GAME=g.z3", .. lines], Here);

    [Fact]
    public void TheGrammarReadsDirectivesCommentsFencesAndCommands()
    {
        var script = AcceptanceScript.Parse(
            [
                "! seed = 92",
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
        Assert.Equal([5, 9], script.Lines);
        Assert.Empty(script.Clicks);
        Assert.Empty(script.Links);
    }

    [Fact]
    public void AnUnclosedFenceTruncatesTheRest()
    {
        var script = Parsed("one", "```", "two", "three");
        Assert.Equal(["one"], script.Commands);
        Assert.Null(script.Seed);
    }

    [Fact]
    public void AnAbsoluteGamePathPassesThrough()
    {
        var rooted = Path.GetFullPath(Path.Combine(Here, "elsewhere", "g.z5"));
        var script = AcceptanceScript.Parse([$"! GAME={rooted}"], Here);
        Assert.Equal(rooted, script.Game);
    }

    [Fact]
    public void CommandsDropThePromptAndInlineComments()
    {
        var script = Parsed(
            "> look",
            "wait         # the seed means we need only one wait",
            "> #literal",
            "say hi#there");
        Assert.Equal(["look", "wait", "#literal", "say hi#there"], script.Commands);
    }

    [Fact]
    public void KeyTokensPressTheirCharacters()
    {
        var script = Parsed("<UP>", "<down>", "<left>", "<right>", "<escape>", "<space>");
        Assert.Equal(["\u0081", "\u0082", "\u0083", "\u0084", "\u001b", " "], script.Commands);
        Assert.Equal("<up>", AcceptanceScript.Shown("\u0081"));
        Assert.Equal("<space>", AcceptanceScript.Shown(" "));
        Assert.Equal("look", AcceptanceScript.Shown("look"));
    }

    [Fact]
    public void ClicksAndLinksTravelBesideTheCommands()
    {
        var script = Parsed("<click 10 20>", "look", "<Double-Click 3 4>", "<link 7>", "<shot>", "<shot end-game>");
        Assert.Equal([AcceptanceScript.Click, "look", AcceptanceScript.DoubleClick, AcceptanceScript.Link], script.Commands);
        Assert.Equal([(10, 20), (3, 4)], script.Clicks);
        Assert.Equal([7], script.Links);
        Assert.Equal([2, 3, 4, 5], script.Lines);
        Assert.Equal("<click>", AcceptanceScript.Shown(AcceptanceScript.Click));
        Assert.Equal("<double-click>", AcceptanceScript.Shown(AcceptanceScript.DoubleClick));
        Assert.Equal("<link>", AcceptanceScript.Shown(AcceptanceScript.Link));
    }

    [Theory]
    [InlineData("! SEED", "a directive is '! KEY=VALUE'")]
    [InlineData("! =3", "a directive is '! KEY=VALUE'")]
    [InlineData("! SEED=abc", "the seed 'abc' is not a number")]
    [InlineData("! COLOUR=blue", "unknown directive COLOUR")]
    [InlineData("<click 1>", "a click is '<click x y>'")]
    [InlineData("<click 70000 1>", "a click coordinate must fit a word")]
    [InlineData("<double-click x>", "a double click is '<double-click x y>'")]
    [InlineData("<double-click 1 70000>", "a click coordinate must fit a word")]
    [InlineData("<link>", "a link is '<link n>'")]
    [InlineData("<link 0>", "a link value is 32-bit and never zero")]
    [InlineData("<link 4294967296>", "a link value is 32-bit and never zero")]
    [InlineData("<link 99999999999999999999>", "a link value is 32-bit and never zero")]
    [InlineData("<jump>", "unknown key '<jump>'; the keys are: <down>, <escape>, <left>, <right>, <space>, <up>, <click x y>, <double-click x y>, <link n>, and <shot> for the camera")]
    public void MalformedLinesAreRefusedByLine(string line, string message)
    {
        var error = Assert.Throws<ZMachineException>(() => Parsed(line));
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

    [Fact]
    public void TheWatchWarnsWhenAResponseRefuses()
    {
        var script = Parsed("open mailbox", "get statuette", "s. e", "what's this", "say \"it's\"");
        var warnings = new List<string>();
        var watch = new RefusalWatch(script, warnings.Add);
        watch.Saw("Opening the mailbox reveals a leaflet.\n>");
        watch.Typed(0);
        watch.Saw("Opening the mailbox reveals a leaflet.\n>");
        watch.Typed(1);
        watch.Saw("You can't see any statuette here!\n>");
        watch.Typed(2);
        watch.Saw("Forest.\n[Which way do you mean, north or south?]\n>");
        watch.Typed(3);
        watch.Saw("[I don't know the word \"this\".]\n>");
        watch.Typed(4);
        watch.Saw("You must use a verb.\n");
        watch.Finish();
        watch.Finish();
        // The command is quoted as Python's repr would: double quotes
        // around a lone apostrophe, single quotes with it escaped when
        // both kinds appear.
        Assert.Equal(
            [
                "line 3: 'get statuette' looks refused: You can't see any statuette here!",
                "line 4: 's. e' looks refused: [Which way do you mean, north or south?]",
                "line 5: \"what's this\" looks refused: [I don't know the word \"this\".]",
                "line 6: 'say \"it\\'s\"' looks refused: You must use a verb.",
            ],
            warnings);
    }

    [Fact]
    public void ProseThatMerelyContainsTheWordsIsNotARefusal()
    {
        Assert.Null(RefusalWatch.RefusalIn("Okay, Jeff, what do you want to do now?"));
        Assert.Equal("What do you want to do?", RefusalWatch.RefusalIn("  What do you want to do?  "));
        Assert.Equal("that's not a verb I recognise.", RefusalWatch.RefusalIn("that's not a verb I recognise."));
    }
}
