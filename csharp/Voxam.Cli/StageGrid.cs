using Voxam.Core;

namespace Voxam.Cli;

/// <summary>
/// The stage's own grid for an acceptance walk, printed as text.
///
/// The corpus sweep certifies the port against the reference through
/// the character faces, which say nothing about §8.8's stage. This
/// says it: the same walk, the same geometry, and the grid the stage
/// holds at the end. The reference prints the same block through
/// tools/stage-grid.py, and the two are compared row for row.
/// </summary>
internal static class StageGrid
{
    // The certification geometry, which both sides spell the same and
    // print in the header, so a drift shows up as a difference rather
    // than as a puzzle.
    private const int Columns = 80;
    private const int Lines = 24;
    private const int UnitWidth = 11;
    private const int UnitHeight = 21;

    /// <summary>A glass that measures but never draws: the grid is the model's.</summary>
    private sealed class Headless : IStageScreen
    {
        public int Columns => StageGrid.Columns;

        public int Lines => StageGrid.Lines;

        public int FontWidth => UnitWidth;

        public int FontHeight => UnitHeight;

        public string? ReadKey(double? timeoutSeconds) => null;

        public void Settle(IReadOnlyList<Paint> paints)
        {
        }
    }

    public static int Dump(string scriptPath, int? seedOverride, Action<string> emit)
    {
        AcceptanceScript script;
        byte[] story;
        Blorb? blorb;

        try
        {
            script = AcceptanceScript.Parse(scriptPath);
            (story, blorb) = StoryFile.Load(script.Game);
        }
        catch (Exception error) when (error is ZMachineException or IOException)
        {
            emit($"voxam: {error.Message}\n");
            return 2;
        }

        var face = new StageFrontend(new Headless(), driven: true, gallery: blorb?.Gallery);
        var at = 0;

        string? Source()
        {
            if (at >= script.Commands.Count)
            {
                return null;
            }

            var command = script.Commands[at++];
            // The typed line is echoed into the stage the way the
            // editor would echo it, so both sides show the same walk.
            face.Write(AcceptanceScript.Shown(command) + "\n");
            return command;
        }

        emit($"# stage {Columns}x{Lines} units {UnitWidth}x{UnitHeight}\n");

        try
        {
            new Machine(story, face, Source, seedOverride ?? script.Seed).Run();
        }
        catch (EndOfInputException)
        {
            // The walk ends where its commands do, which is ordinary.
        }
        catch (ZMachineException error)
        {
            // How a walk ends is worth saying, but it is each
            // interpreter's own voice and no part of the grid, so it
            // keeps off the output being compared.
            Console.Error.WriteLine($"# ended: {error.Message}");
        }

        emit(face.Model.Rendered() + "\n");
        return 0;
    }
}
