using Avalonia.Media;

namespace Voxam.Desktop;

/// <summary>
/// The glass's default ink and paper: what §8.3.1's codes 0 and 1
/// resolve to, and, through the theme, the pair a game asking for
/// plain white on black is given (§8.3.3). Four dressings, the
/// reference's own: dark is the home look, gentle where pure white
/// on black glares; classic keeps the old pure values.
/// </summary>
public sealed record Theme(string Name, Color Ink, Color Paper)
{
    public static readonly Theme Dark = new("dark", Color.FromRgb(214, 214, 214), Color.FromRgb(28, 28, 28));
    public static readonly Theme Light = new("paper", Color.FromRgb(0, 0, 0), Color.FromRgb(255, 255, 255));
    public static readonly Theme Sepia = new("sepia", Color.FromRgb(67, 56, 42), Color.FromRgb(244, 236, 216));
    public static readonly Theme Classic = new("classic", Color.FromRgb(255, 255, 255), Color.FromRgb(0, 0, 0));

    /// <summary>Every theme, in the order the reference lists them.</summary>
    public static IReadOnlyList<Theme> All { get; } = [Dark, Light, Sepia, Classic];

    /// <summary>The theme of that name, or null for a name nobody dressed.</summary>
    public static Theme? Named(string name) => All.FirstOrDefault(theme => theme.Name == name);
}
