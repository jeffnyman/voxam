using System.Text;
using Voxam.Core;

namespace Voxam.Cli;

internal static class Program
{
    private const int ExitOk = 0;
    private const int ExitUnusable = 2;
    private static readonly string[] BlorbSuffixes = [".blb", ".blorb", ".zblorb", ".gblorb"];

    private static int Main(string[] args)
    {
        string? script = null;
        int? seedOverride = null;

        for (var k = 0; k < args.Length; k++)
        {
            switch (args[k])
            {
                case "--accept" when k + 1 < args.Length:
                    script = args[++k];
                    break;
                case "--seed" when k + 1 < args.Length:
                    seedOverride = int.Parse(args[++k], System.Globalization.CultureInfo.InvariantCulture);
                    break;
                default:
                    Console.Error.WriteLine("usage: voxam --accept SCRIPT [--seed N]");
                    return ExitUnusable;
            }
        }

        if (script is null)
        {
            Console.Error.WriteLine("usage: voxam --accept SCRIPT [--seed N]");
            return ExitUnusable;
        }

        // The transcript is written as bytes, UTF-8 without a mark, with
        // the platform's line ending where the Python's text-mode stdout
        // would put one: the reference is byte-identical or nothing.
        using var stdout = new StreamWriter(Console.OpenStandardOutput(), new UTF8Encoding(false), 1 << 16);
        var newline = Environment.NewLine;

        void Emit(string text) => stdout.Write(newline == "\n" ? text : text.Replace("\n", newline, StringComparison.Ordinal));

        try
        {
            return Replay(script, seedOverride, Emit);
        }
        finally
        {
            stdout.Flush();
        }
    }

    private static int Replay(string scriptPath, int? seedOverride, Action<string> emit)
    {
        AcceptanceScript script;

        try
        {
            script = AcceptanceScript.Parse(scriptPath);
        }
        catch (Exception error) when (error is ZMachineException or IOException)
        {
            emit($"voxam: {error.Message}\n");
            return ExitUnusable;
        }

        var seed = seedOverride ?? script.Seed;
        byte[] story;
        Blorb? blorb = null;

        try
        {
            story = File.ReadAllBytes(script.Game);

            foreach (var suffix in BlorbSuffixes)
            {
                var sidecar = Path.ChangeExtension(script.Game, suffix);

                if (File.Exists(sidecar))
                {
                    blorb = Blorb.Load(File.ReadAllBytes(sidecar));
                    break;
                }
            }
        }
        catch (Exception error) when (error is ZMachineException or IOException)
        {
            emit($"voxam: {error.Message}\n");
            return ExitUnusable;
        }

        var commands = script.Commands.GetEnumerator();

        string? Source()
        {
            if (!commands.MoveNext())
            {
                return null;
            }

            emit(commands.Current + "\n");
            return commands.Current;
        }

        emit("\nVoxam Interpreter for Z-Machine and Glulx Stories\n\n");

        try
        {
            var release = (story[Header.Release] << 8) | story[Header.Release + 1];
            var serial = Encoding.ASCII.GetString(story, Header.Serial, 6);
            emit($"Running {Path.GetFileName(script.Game)}: release {release}, serial {serial} (z{story[0]})\n\n");

            if (blorb is not null)
            {
                emit($"Resources: {blorb.Described()}\n\n");

                if (!blorb.Matches(story))
                {
                    emit("voxam: the resource file names a different story\n\n");
                }
            }

            var machine = new Machine(story, new PlainFrontend(emit), Source, seed);
            machine.Run();
            emit("\n");
        }
        catch (EndOfInputException)
        {
            emit("\nvoxam: end of input\n");
            return ExitOk;
        }
        catch (ZMachineException error)
        {
            emit($"\nvoxam: {error.Message}\n");
            return ExitUnusable;
        }

        return ExitOk;
    }
}
