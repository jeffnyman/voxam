using System.Globalization;

namespace Voxam.Desktop;

/// <summary>
/// How the player likes the glass, remembered between sessions.
///
/// The file is two plain lines beside the application's own settings,
/// because a preference is not worth a serializer: an unreadable or
/// absent file is simply the defaults, and a line nobody wrote is
/// ignored rather than argued with.
/// </summary>
public sealed record Preferences(Theme Theme, double Size)
{
    /// <summary>The sizes the menu offers, in points.</summary>
    public static IReadOnlyList<double> Sizes { get; } = [14, 16, 18, 20, 24];

    /// <summary>What a player who has never chosen gets.</summary>
    public static Preferences Default { get; } = new(Theme.Dark, 18);

    /// <summary>Where the choices are kept.</summary>
    public static string Path =>
        System.IO.Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
            "Voxam",
            "preferences.txt");

    /// <summary>Read the choices, or the defaults when there are none to read.</summary>
    public static Preferences Load(string path)
    {
        var chosen = Default;

        try
        {
            foreach (var line in File.ReadAllLines(path))
            {
                var at = line.IndexOf('=', StringComparison.Ordinal);

                if (at < 0)
                {
                    continue;
                }

                var (name, value) = (line[..at].Trim(), line[(at + 1)..].Trim());

                if (name == "theme" && Theme.Named(value) is { } theme)
                {
                    chosen = chosen with { Theme = theme };
                }
                else if (name == "size" && double.TryParse(value, CultureInfo.InvariantCulture, out var size) && Sizes.Contains(size))
                {
                    chosen = chosen with { Size = size };
                }
            }
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException)
        {
            // Nothing readable is nothing chosen.
        }

        return chosen;
    }

    /// <summary>Write the choices down, quietly giving up if they cannot be kept.</summary>
    public void Save(string path)
    {
        try
        {
            Directory.CreateDirectory(System.IO.Path.GetDirectoryName(System.IO.Path.GetFullPath(path))!);
            File.WriteAllLines(path, [$"theme={Theme.Name}", string.Create(CultureInfo.InvariantCulture, $"size={Size}")]);
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException)
        {
            // A preference nobody can keep is not worth a complaint.
        }
    }
}
