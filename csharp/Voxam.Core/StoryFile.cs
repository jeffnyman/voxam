namespace Voxam.Core;

/// <summary>A story on disk, with the Blorb that packages or accompanies it.</summary>
public static class StoryFile
{
    private static readonly string[] BlorbSuffixes = [".blb", ".blorb", ".zblorb", ".gblorb"];

    /// <summary>
    /// Whether a path names a package rather than a bare story. The
    /// suffix rules, not the bytes: a file named as a blorb that is not
    /// one is a broken blorb, and says so.
    /// </summary>
    public static bool IsBlorb(string game) =>
        BlorbSuffixes.Contains(Path.GetExtension(game).ToLowerInvariant());

    /// <summary>
    /// A path with a Blorb suffix must carry a packaged story; any
    /// other loads as a story file, with a like-named Blorb beside it
    /// as its resources when one exists.
    /// </summary>
    public static (byte[] Story, Blorb? Blorb) Load(string game)
    {
        if (IsBlorb(game))
        {
            var packaged = Blorb.Load(File.ReadAllBytes(game));
            var story = packaged.Story
                ?? throw new ZMachineException($"{Path.GetFileName(game)} packages no story this interpreter can run");
            return (story, packaged);
        }

        var bytes = File.ReadAllBytes(game);

        foreach (var suffix in BlorbSuffixes)
        {
            var sidecar = Path.ChangeExtension(game, suffix);

            if (File.Exists(sidecar))
            {
                return (bytes, Blorb.Load(File.ReadAllBytes(sidecar)));
            }
        }

        return (bytes, null);
    }
}
