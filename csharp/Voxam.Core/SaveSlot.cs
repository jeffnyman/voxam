namespace Voxam.Core;

/// <summary>
/// Where a saved game's bytes go, kept apart from the machine: the
/// machine asks the slot to keep or produce bytes, and failure is an
/// answer, not an accident, because save and restore report failure
/// to the story as an ordinary result (§15).
/// </summary>
public interface ISaveSlot
{
    bool Write(byte[] data);

    byte[]? Read();

    /// <summary>Keep a game-named auxiliary file (§7.6).</summary>
    bool WriteAux(string name, byte[] data);

    byte[]? ReadAux(string name);
}

/// <summary>A save that lives beside the story on disk: story.sav, and story-named .aux files beside it.</summary>
public sealed class FileSaveSlot(string path) : ISaveSlot
{
    public string Path { get; } = path;

    public bool Write(byte[] data) => Kept(Path, data);

    public byte[]? Read() => Found(Path);

    public bool WriteAux(string name, byte[] data) => Kept(AuxPath(name), data);

    public byte[]? ReadAux(string name) => Found(AuxPath(name));

    // A refused disk is a failed save, not a crash.
    private static bool Kept(string path, byte[] data)
    {
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

    private static byte[]? Found(string path)
    {
        try
        {
            return File.ReadAllBytes(path);
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException)
        {
            return null;
        }
    }

    // A game-supplied name is stripped to letters, digits, dashes and
    // underscores, and takes the .aux extension §7.6.1.1 suggests.
    private string AuxPath(string name)
    {
        var stem = string.Concat(name.Where(c => char.IsLetterOrDigit(c) || c is '-' or '_'));
        var directory = System.IO.Path.GetDirectoryName(Path) ?? "";
        return System.IO.Path.Combine(directory, $"{(stem.Length > 0 ? stem : "aux")}.aux");
    }
}
