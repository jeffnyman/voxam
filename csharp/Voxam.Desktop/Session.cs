using Voxam.Core;

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

    /// <summary>The frontend playing this story, for anyone measuring the model behind the glass.</summary>
    public ScreenFrontend? Face { get; private set; }

    /// <summary>Load the story and start it playing; the loader's refusals come straight back.</summary>
    public static Session Start(string game, Glass glass, Action<string> notice, int? seed = null)
    {
        var (story, _) = StoryFile.Load(game);
        var face = new ScreenFrontend(story[0], glass);
        var saves = new FileSaveSlot(Path.ChangeExtension(game, ".sav"));
        var machine = new Machine(story, face, face.ReadLine, seed, face.ReadKey, face.ReadLineUntil, saves);
        face.OnResize = machine.RefreshScreenFields;
        var thread = new Thread(() => Play(face, machine, notice)) { IsBackground = true, Name = "voxam machine" };
        var session = new Session(glass, thread) { Face = face };
        thread.Start();
        return session;
    }

    /// <summary>End the reads this story waits in and give the thread a moment to leave.</summary>
    public void Retire()
    {
        _glass.Retire();
        _thread.Join(TimeSpan.FromSeconds(1));
    }

    private static void Play(ScreenFrontend face, Machine machine, Action<string> notice)
    {
        try
        {
            face.Clear();
            machine.Run();
            notice("The story has ended.");
        }
        catch (OperationCanceledException)
        {
            // Retired: another story has the glass now.
        }
        catch (ZMachineException error)
        {
            notice($"voxam: {error.Message}");
        }
    }
}
