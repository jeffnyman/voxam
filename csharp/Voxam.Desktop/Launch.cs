namespace Voxam.Desktop;

/// <summary>
/// The command line as the window reads it: a story to open, the
/// theme to wear, and a complaint when the line made no sense. A
/// complaint stands in for the story, the way the console's usage
/// message does, so a mistyped switch never half-launches.
/// </summary>
public sealed record Launch(string? Game, Theme? Theme, string? Complaint)
{
    private const string Usage = "usage: Voxam [--theme NAME] [STORY]";

    public static Launch Parse(IReadOnlyList<string> args)
    {
        string? game = null;
        Theme? theme = null;

        for (var k = 0; k < args.Count; k++)
        {
            if (args[k] == "--theme" && k + 1 < args.Count)
            {
                var name = args[++k];
                var named = Theme.Named(name);

                if (named is null)
                {
                    var themes = string.Join(", ", Theme.All.Select(t => t.Name));
                    return new Launch(null, null, $"voxam: no theme named {name}; the themes are {themes}");
                }

                theme = named;
            }
            else if (args[k].StartsWith('-') || game is not null)
            {
                return new Launch(null, null, $"voxam: {Usage}");
            }
            else
            {
                game = args[k];
            }
        }

        return new Launch(game, theme, null);
    }
}
