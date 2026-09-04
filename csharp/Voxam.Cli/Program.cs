using System.Globalization;
using System.Reflection;
using System.Text;
using Voxam.Core;
using Glulx = Voxam.Core.Glulx;

namespace Voxam.Cli;

internal static class Program
{
    private const int ExitOk = 0;
    private const int ExitUnusable = 2;
    private const string Usage = "usage: voxam STORY [--plain] [--seed N]\n       voxam --accept SCRIPT [--seed N]\n       voxam --stage-grid SCRIPT [--seed N]\n       voxam --version";

    private static int Main(string[] args)
    {
        string? script = null;
        string? grid = null;
        string? story = null;
        int? seedOverride = null;
        var plain = false;

        for (var k = 0; k < args.Length; k++)
        {
            switch (args[k])
            {
                case "--accept" when k + 1 < args.Length:
                    script = args[++k];
                    break;
                case "--stage-grid" when k + 1 < args.Length:
                    grid = args[++k];
                    break;
                case "--seed" when k + 1 < args.Length:
                    seedOverride = int.Parse(args[++k], CultureInfo.InvariantCulture);
                    break;
                case "--plain":
                    plain = true;
                    break;
                case "--version":
                    Console.WriteLine($"voxam {Version()} (native)");
                    return ExitOk;
                default:
                    if (args[k].StartsWith('-') || story is not null)
                    {
                        Console.Error.WriteLine(Usage);
                        return ExitUnusable;
                    }

                    story = args[k];
                    break;
            }
        }

        if (script is null && grid is null && story is null)
        {
            Console.Error.WriteLine(Usage);
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
            if (grid is not null)
            {
                return StageGrid.Dump(grid, seedOverride, Emit);
            }

            return script is not null ? Replay(script, seedOverride, Emit) : Play(story!, seedOverride, plain, Emit, stdout);
        }
        finally
        {
            stdout.Flush();
        }
    }

    // The port versions with the repository; the runtime is the tell.
    private static string Version()
    {
        var version = Assembly.GetEntryAssembly()?.GetName().Version;
        return version is null ? "0.0.0" : $"{version.Major}.{version.Minor}.{version.Build}";
    }

    // A Glulx story loads and is held to every promise its header
    // makes, and then says what it is: the machine that runs one is a
    // road this port has not walked yet, and a session that stops
    // should name what stopped it.
    private static bool Frontier(string game, byte[] data, Action<string> emit)
    {
        if (!Glulx.Story.IsGlulx(data))
        {
            return false;
        }

        var story = new Glulx.Story(data);
        var checksum = story.Verify() ? "checksum verified" : "checksum wrong";
        emit($"voxam: {Path.GetFileName(game)} is a Glulx story (version {story.Version}, {checksum}), and the Glulx machine is not here yet\n");

        return true;
    }

    private static void Banner(string game, byte[] story, Blorb? blorb, Action<string> emit)
    {
        emit("\nVoxam Interpreter for Z-Machine and Glulx Stories\n\n");
        var release = (story[Header.Release] << 8) | story[Header.Release + 1];
        var serial = Encoding.ASCII.GetString(story, Header.Serial, 6);
        emit($"Running {Path.GetFileName(game)}: release {release}, serial {serial} (z{story[0]})\n\n");

        if (blorb is not null)
        {
            emit($"Resources: {blorb.Described()}\n\n");

            if (!blorb.Matches(story))
            {
                emit("voxam: the resource file names a different story\n\n");
            }
        }
    }

    private static int Replay(string scriptPath, int? seedOverride, Action<string> emit)
    {
        AcceptanceScript script;
        byte[] story;
        Blorb? blorb;

        try
        {
            script = AcceptanceScript.Parse(scriptPath);
            (story, blorb) = StoryFile.Load(script.Game);

            if (Frontier(script.Game, story, emit))
            {
                return ExitUnusable;
            }
        }
        catch (Exception error) when (error is VoxamException or IOException)
        {
            emit($"voxam: {error.Message}\n");
            return ExitUnusable;
        }

        var seed = seedOverride ?? script.Seed;

        // The watch reads the story's output, never the typed echoes,
        // and judges each response the moment the next command is
        // typed: a warning lands between the prompt and the echo, as
        // in the reference.
        var watch = new RefusalWatch(script, message => emit($"voxam: {message}\n"));
        var at = 0;

        string? Source()
        {
            if (at >= script.Commands.Count)
            {
                return null;
            }

            var command = script.Commands[at];
            watch.Typed(at);
            at++;
            emit(AcceptanceScript.Shown(command) + "\n");
            return command;
        }

        void Tee(string text)
        {
            emit(text);
            watch.Saw(text);
        }

        var saves = new FileSaveSlot(Path.ChangeExtension(script.Game, ".sav"));
        var code = Session(() => new Machine(story, new PlainFrontend(Tee), Source, seed, saves: saves), emit, () => Banner(script.Game, story, blorb, emit), null);
        watch.Finish();
        return code;
    }

    // An interactive session: the painted terminal when standard
    // output and input are a real console and --plain was not asked
    // for, the plain stream otherwise.
    private static int Play(string game, int? seed, bool plain, Action<string> emit, StreamWriter stdout)
    {
        byte[] story;
        Blorb? blorb;

        try
        {
            (story, blorb) = StoryFile.Load(game);

            if (Frontier(game, story, emit))
            {
                return ExitUnusable;
            }
        }
        catch (Exception error) when (error is VoxamException or IOException)
        {
            emit($"voxam: {error.Message}\n");
            return ExitUnusable;
        }

        var painted = !plain && !Console.IsOutputRedirected && !Console.IsInputRedirected;
        // Saved games live beside the story: zork1.z3 saves to zork1.sav.
        var saves = new FileSaveSlot(Path.ChangeExtension(game, ".sav"));

        if (!painted)
        {
            return Session(() => new Machine(story, new PlainFrontend(emit), Console.ReadLine, seed, saves: saves), emit, () => Banner(game, story, blorb, emit), null);
        }

        using var terminal = new ConsoleTerminal();
        var face = new TerminalFrontend(story[0], terminal);
        Console.CancelKeyPress += (_, _) => terminal.Write("\u001b[0m\n");

        return Session(
            () =>
            {
                var machine = new Machine(story, face, face.ReadLine, seed, face.ReadKey, face.ReadLineUntil, saves);
                face.OnResize = machine.RefreshScreenFields;
                return machine;
            },
            emit,
            () =>
            {
                stdout.Flush();
                Banner(game, story, blorb, emit);
                stdout.Flush();
                face.Clear();
            },
            () => terminal.Write("\u001b[0m\n"));
    }

    private static int Session(Func<Machine> boot, Action<string> emit, Action banner, Action? closing)
    {
        try
        {
            banner();
            boot().Run();
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
        finally
        {
            closing?.Invoke();
        }

        return ExitOk;
    }
}
