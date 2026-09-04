using Avalonia.Threading;
using Voxam.Core;

namespace Voxam.Desktop;

/// <summary>
/// Saves the player names, through the platform's own file picker.
///
/// This is the one thing a window can do that a prompt cannot: the
/// picker and the machine share a filesystem, so a save goes wherever
/// the player says rather than to a fixed file beside the story. The
/// machine asks from its own thread and waits here while the window
/// puts the question, which is safe because the window never waits on
/// the machine.
///
/// Auxiliary files are not the player's to name: §7.6.1.1 has the game
/// supply those, so they stay beside the story where the game left
/// them.
/// </summary>
public sealed class PickedSaves(string story, Func<bool, Task<string?>> ask) : ISaveSlot
{
    private readonly FileSaveSlot _beside = new(Path.ChangeExtension(story, ".sav"));

    public bool Write(byte[] data)
    {
        if (Asked(saving: true) is not { } path)
        {
            return false;
        }

        try
        {
            File.WriteAllBytes(path, data);
            return true;
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException)
        {
            return false;
        }
    }

    public byte[]? Read()
    {
        if (Asked(saving: false) is not { } path)
        {
            return null;
        }

        try
        {
            return File.ReadAllBytes(path);
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException)
        {
            return null;
        }
    }

    public bool WriteAux(string name, byte[] data) => _beside.WriteAux(name, data);

    public byte[]? ReadAux(string name) => _beside.ReadAux(name);

    // Put the question on the window's thread and wait for its answer.
    // A picker that fails is a refusal, which is what a player who
    // cancels gives too.
    private string? Asked(bool saving)
    {
        var answered = new TaskCompletionSource<string?>();

        Dispatcher.UIThread.Post(async () =>
        {
            try
            {
                answered.SetResult(await ask(saving));
            }
            catch (Exception error) when (error is IOException or InvalidOperationException or NotSupportedException)
            {
                answered.SetResult(null);
            }
        });

        return answered.Task.GetAwaiter().GetResult();
    }
}
