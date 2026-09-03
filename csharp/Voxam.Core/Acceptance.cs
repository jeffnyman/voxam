using System.Text;

namespace Voxam.Core;

/// <summary>
/// An acceptance script (the Python acceptance grammar): its game,
/// its seed, and the lines to type. Fences skip sections, comments
/// and blank lines are ignored, and directives are ! KEY=VALUE.
/// </summary>
public sealed record AcceptanceScript(string Game, int? Seed, IReadOnlyList<string> Commands)
{
    public static AcceptanceScript Parse(string path)
    {
        var scriptDirectory = Path.GetDirectoryName(Path.GetFullPath(path))!;
        return Parse(File.ReadAllLines(path, Encoding.UTF8), scriptDirectory);
    }

    public static AcceptanceScript Parse(IEnumerable<string> lines, string scriptDirectory)
    {
        string? game = null;
        int? seed = null;
        var commands = new List<string>();
        var fenced = false;
        var number = 0;

        foreach (var raw in lines)
        {
            number++;
            var line = raw.Trim();

            if (line.StartsWith("```", StringComparison.Ordinal))
            {
                fenced = !fenced;
                continue;
            }

            if (fenced || line.Length == 0 || line.StartsWith('#'))
            {
                continue;
            }

            if (!line.StartsWith('!'))
            {
                commands.Add(line);
                continue;
            }

            var directive = line[1..].Trim();
            var split = directive.IndexOf('=');

            if (split < 0)
            {
                throw new ZMachineException($"line {number}: a directive is ! KEY=VALUE");
            }

            var key = directive[..split].Trim();
            var value = directive[(split + 1)..].Trim();

            switch (key)
            {
                case "SEED":
                    if (!int.TryParse(value, out var parsed) || parsed < 0)
                    {
                        throw new ZMachineException($"line {number}: the seed must be a non-negative integer");
                    }

                    seed = parsed;
                    break;
                case "GAME":
                    game = Path.GetFullPath(Path.Combine(scriptDirectory, value));
                    break;
                default:
                    throw new ZMachineException($"line {number}: unknown directive {key}");
            }
        }

        if (game is null)
        {
            throw new ZMachineException("the script names no game: add a ! GAME=path line");
        }

        return new AcceptanceScript(game, seed, commands);
    }
}
