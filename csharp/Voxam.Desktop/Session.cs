using Voxam.Core;
using Voxam.Core.Glulx.Glk;
using Glulx = Voxam.Core.Glulx;

namespace Voxam.Desktop;

/// <summary>
/// One story playing on the glass: the machine runs on its own
/// thread and blocks there for keys, so the window never waits on
/// it. Retiring the session ends the read the machine is parked in,
/// and the thread leaves quietly.
/// </summary>
public sealed class Session
{
    private readonly Glass _glass;
    private readonly Thread _thread;

    private Session(Glass glass, Thread thread)
    {
        _glass = glass;
        _thread = thread;
    }

    /// <summary>The cell face playing this story, or null when a Version 6 stage has the glass.</summary>
    public ScreenFrontend? Face { get; private set; }

    /// <summary>The Version 6 face playing this story, or null for every other version.</summary>
    public StageFrontend? Stage { get; private set; }

    /// <summary>The Glk display playing this story, or null for a Z-Machine one.</summary>
    public GlassDisplay? Glk { get; private set; }

    /// <summary>
    /// Load the story and start it playing; the loader's refusals come
    /// straight back. Version 6 places its own windows in units, so it
    /// gets the stage; every other version gets the cell screen the
    /// painted terminal keeps. Where a save goes is the caller's to
    /// say, since a window and a prompt answer that differently.
    /// </summary>
    public static Session Start(string game, Glass glass, Action<string> notice, ISaveSlot saves, int? seed = null)
    {
        var (story, blorb) = StoryFile.Load(game);

        if (Glulx.Story.IsGlulx(story))
        {
            // Held to its header's promises here as everywhere, so a
            // Glulx file with something wrong inside it says what that
            // is rather than only that it will not play.
            var glulx = new Glulx.Story(story);

            // The window tree is laid out over real pixels, so the glass
            // keeps a retained surface the way a Version 6 stage does,
            // and it hears the pointer, which only Glk asks it for.
            glass.Pin(glass.Columns, glass.Lines);
            glass.Clicks = true;

            var display = new GlassDisplay(glass);
            var library = new Api(
                display,
                Path.GetDirectoryName(Path.GetFullPath(game)),
                new GlkResources(blorb));
            var glulxed = new Glulx.Machine(glulx, seed, library: library);

            return Started(
                glass,
                null,
                () =>
                {
                    display.Clear();
                    glulxed.Run();

                    // A story that ends with quit rather than glk_exit
                    // never asked for a last flush; whatever its windows
                    // still hold is shown on the way out.
                    display.Flush(library.Root);
                },
                notice,
                session => session.Glk = display);
        }

        if (story[0] == 6)
        {
            // The art hangs behind the stage, so a game lays its
            // windows out for the room its pictures take, even while
            // the drawing of them is still a road.
            var stage = new StageFrontend(glass, gallery: blorb?.Gallery);
            glass.Pin(stage.ScreenColumns, stage.ScreenLines);
            var staged = new Machine(story, stage, stage.ReadLine, seed, stage.ReadKey, stage.ReadLineUntil, saves);
            return Started(glass, stage, () => staged.Run(), notice, session => session.Stage = stage);
        }

        var face = new ScreenFrontend(story[0], glass);
        var machine = new Machine(story, face, face.ReadLine, seed, face.ReadKey, face.ReadLineUntil, saves);
        face.OnResize = machine.RefreshScreenFields;
        return Started(glass, null, () => { face.Clear(); machine.Run(); }, notice, session => session.Face = face);
    }

    private static Session Started(Glass glass, StageFrontend? stage, Action run, Action<string> notice, Action<Session> dressed)
    {
        var thread = new Thread(() => Play(run, notice)) { IsBackground = true, Name = "voxam machine" };
        var session = new Session(glass, thread);
        dressed(session);
        thread.Start();
        return session;
    }

    /// <summary>End the reads this story waits in and give the thread a moment to leave.</summary>
    public void Retire()
    {
        _glass.Retire();
        _thread.Join(TimeSpan.FromSeconds(1));
        _glass.Strike();
    }

    private static void Play(Action run, Action<string> notice)
    {
        try
        {
            run();
            notice("The story has ended.");
        }
        catch (OperationCanceledException)
        {
            // Retired: another story has the glass now.
        }
        catch (VoxamException error)
        {
            notice($"voxam: {error.Message}");
        }
    }
}
