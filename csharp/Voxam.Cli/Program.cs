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

    // The terminal a session falls back to when nothing can be measured.
    private const int DefaultColumns = 80;
    private const int DefaultLines = 24;
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

    // A Glulx session over the plain stream, which is what a piped
    // session and the acceptance harness drive. The checksum verdict is
    // printed but does not gate the run: the verify opcode exists so a
    // story can judge itself.
    private static int Glulxed(
        string game,
        byte[] data,
        Blorb? blorb,
        int? seed,
        Action<string> emit,
        Func<string?> read,
        Action<string>? witness = null,
        Func<(int X, int Y)?>? clicks = null,
        Func<int?>? links = null)
    {
        Glulx.Story story;

        try
        {
            story = new Glulx.Story(data);
        }
        catch (VoxamException error)
        {
            emit($"voxam: {error.Message}\n");
            return ExitUnusable;
        }

        Greeting(emit);
        emit($"Running {Path.GetFileName(game)}: Glulx {story.Version}, {(story.Verify() ? "checksum verified" : "CHECKSUM MISMATCH")}\n\n");

        var display = new Glulx.Glk.StdioDisplay(emit, read, Room(), witness, clicks, links);
        // A story's own package is its resources: the pictures it draws,
        // the sounds it plays, and the data files it reads. What this
        // display can do with them is another matter, and its own.
        var library = new Glulx.Glk.Api(
            display, resources: new Glulx.Glk.GlkResources(blorb));

        try
        {
            new Glulx.Machine(story, seed, library: library).Run();
        }
        catch (Exception error) when (error is VoxamException or IOException)
        {
            emit($"\nvoxam: {error.Message}\n");
            return ExitUnusable;
        }

        // A story that ends with quit rather than glk_exit never asked
        // for a last flush; whatever its windows still hold is shown on
        // the way out.
        display.Flush(library.Root);
        emit("\n");

        return ExitOk;
    }

    // The room the windows lay out in, measured the way the reference
    // measures it: the environment first, since that is how a harness
    // pins a width; then the console itself, when there is one to ask;
    // and a conventional terminal when neither can say. A piped session
    // therefore lays out at eighty by twenty-four on both interpreters,
    // which is what makes their transcripts comparable.
    private static (int Width, int Height) Room()
    {
        var width = Declared("COLUMNS");
        var height = Declared("LINES");

        if (width > 0 && height > 0)
        {
            return (width, height);
        }

        var (columns, lines) = Console.IsOutputRedirected
            ? (DefaultColumns, DefaultLines)
            : (Console.WindowWidth, Console.WindowHeight);

        return (width > 0 ? width : columns, height > 0 ? height : lines);
    }

    // A dimension the environment names, or nothing it can be read as.
    private static int Declared(string name) =>
        int.TryParse(
            Environment.GetEnvironmentVariable(name),
            CultureInfo.InvariantCulture,
            out var value)
            ? value
            : 0;

    private static void Greeting(Action<string> emit) =>
        emit("\nVoxam Interpreter for Z-Machine and Glulx Stories\n\n");

    private static void Banner(string game, byte[] story, Blorb? blorb, Action<string> emit)
    {
        Greeting(emit);
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

        if (Glulx.Story.IsGlulx(story))
        {
            // The Glulx replay rides the plain display's own seams: the
            // source types, the witness listens for refusals, and a
            // script that carries clicks or links answers the events its
            // recording's game asked for, one per marker. A script that
            // carries neither wires neither source, so its replay keeps
            // those gestalts at zero, which is what a session recorded at
            // this display was told.
            var positions = script.Clicks.GetEnumerator();
            var selections = script.Links.GetEnumerator();
            var played = Glulxed(
                script.Game,
                story,
                blorb,
                seed,
                emit,
                Source,
                watch.Saw,
                script.Clicks.Count > 0 ? () => positions.MoveNext() ? positions.Current : null : null,
                script.Links.Count > 0 ? () => selections.MoveNext() ? selections.Current : null : null);

            watch.Finish();
            return played;
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
        }
        catch (Exception error) when (error is VoxamException or IOException)
        {
            emit($"voxam: {error.Message}\n");
            return ExitUnusable;
        }

        if (Glulx.Story.IsGlulx(story))
        {
            // The painted displays are their own roads; a Glulx story
            // plays over the plain stream whether one was asked for or
            // not. The prompt is pushed out before every read, since a
            // buffered writer would otherwise leave it unshown.
            return Glulxed(game, story, blorb, seed, emit, () =>
            {
                stdout.Flush();
                return Console.ReadLine();
            });
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
