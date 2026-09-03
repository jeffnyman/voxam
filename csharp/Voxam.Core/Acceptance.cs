using System.Globalization;
using System.Text;
using System.Text.RegularExpressions;

namespace Voxam.Core;

/// <summary>
/// An acceptance script, read under the Python acceptance grammar: a
/// game, a seed, and the lines to type. Fences skip sections,
/// comments and blank lines are ignored, directives are ! KEY=VALUE,
/// and the angle-bracket tokens press keys, click, follow links, or
/// mark the camera. Each command remembers its line in the file, so
/// the refusal watch can name it.
/// </summary>
public sealed partial record AcceptanceScript(
    string Game,
    int? Seed,
    IReadOnlyList<string> Commands,
    IReadOnlyList<int> Lines,
    IReadOnlyList<(int X, int Y)> Clicks,
    IReadOnlyList<int> Links)
{
    /// <summary>A click travels the command stream as the §10.3.3 input code for one.</summary>
    public const string Click = "\u00fe";

    /// <summary>The second click of a fast pair, §10.3.3's 253.</summary>
    public const string DoubleClick = "\u00fd";

    /// <summary>A link selection's own marker, outside the key alphabet.</summary>
    public const string Link = "\u00fc";

    private const int CoordinateCeiling = 0xFFFF;
    private const long LinkCeiling = 0xFFFFFFFF;

    // The special keys a recording can press: the §3.8.4 cursor codes,
    // the §3.8.2.6 escape, and the space bar, which stripping would
    // otherwise erase.
    private static readonly Dictionary<string, string> KeyTokens = new()
    {
        ["<up>"] = "\u0081",
        ["<down>"] = "\u0082",
        ["<left>"] = "\u0083",
        ["<right>"] = "\u0084",
        ["<escape>"] = "\u001b",
        ["<space>"] = " ",
    };

    private static readonly Dictionary<string, string> KeyEchoes =
        KeyTokens.ToDictionary(pair => pair.Value, pair => pair.Key, StringComparer.Ordinal);

    [GeneratedRegex(@"^<click (\d+) (\d+)>$")]
    private static partial Regex ClickToken();

    [GeneratedRegex(@"^<double-click (\d+) (\d+)>$")]
    private static partial Regex DoubleClickToken();

    [GeneratedRegex(@"^<link (\d+)>$")]
    private static partial Regex LinkToken();

    [GeneratedRegex(@"^<shot(?: ([a-z0-9][a-z0-9-]*))?>$")]
    private static partial Regex ShotToken();

    [GeneratedRegex(@"\s+#")]
    private static partial Regex InlineComment();

    /// <summary>What the transcript shows for a command: a key's token, a click's or link's marker, or the command itself.</summary>
    public static string Shown(string command)
    {
        if (command == Click)
        {
            return "<click>";
        }

        if (command == DoubleClick)
        {
            return "<double-click>";
        }

        if (command == Link)
        {
            return "<link>";
        }

        return KeyEchoes.TryGetValue(command, out var token) ? token : command;
    }

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
        var numbers = new List<int>();
        var clicks = new List<(int, int)>();
        var links = new List<int>();
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

            if (line.StartsWith('!'))
            {
                var (key, value) = Directive(line, number);

                switch (key)
                {
                    case "SEED":
                        seed = SeedValue(value, number);
                        break;
                    case "GAME":
                        game = Path.IsPathRooted(value) ? value : Path.GetFullPath(Path.Combine(scriptDirectory, value));
                        break;
                    default:
                        throw new ZMachineException($"line {number}: unknown directive {key}");
                }

                continue;
            }

            var lowered = line.ToLowerInvariant();

            if (ShotToken().IsMatch(lowered))
            {
                continue;
            }

            var pointer = PointerToken(line, lowered, number);

            if (pointer is not null)
            {
                commands.Add(pointer.Value.Marker);
                clicks.Add(pointer.Value.Position);
            }
            else if (LinkValue(line, lowered, number) is { } link)
            {
                commands.Add(Link);
                links.Add(link);
            }
            else
            {
                commands.Add(KeyToken(line, lowered, number) ?? Command(line));
            }

            numbers.Add(number);
        }

        if (game is null)
        {
            throw new ZMachineException("the script names no game: add a ! GAME=path line");
        }

        return new AcceptanceScript(game, seed, commands, numbers, clicks, links);
    }

    private static (string Key, string Value) Directive(string line, int number)
    {
        var body = line[1..].Trim();
        var split = body.IndexOf('=');

        if (split < 0 || body[..split].Trim().Length == 0)
        {
            throw new ZMachineException($"line {number}: a directive is '! KEY=VALUE', not '{line}'");
        }

        return (body[..split].Trim().ToUpperInvariant(), body[(split + 1)..].Trim());
    }

    private static int SeedValue(string value, int number)
    {
        if (!int.TryParse(value, NumberStyles.Integer, CultureInfo.InvariantCulture, out var seed))
        {
            throw new ZMachineException($"line {number}: the seed '{value}' is not a number");
        }

        return seed;
    }

    // A click line of either kind: its marker and its (x, y). A line
    // that starts a click but garbles it fails loudly, like any
    // typoed token, and a coordinate must fit a header word (§10.3.2).
    private static (string Marker, (int X, int Y) Position)? PointerToken(string line, string lowered, int number)
    {
        if (lowered.StartsWith("<click", StringComparison.Ordinal))
        {
            return (Click, Coordinates(ClickToken().Match(lowered), line, number, "a click is '<click x y>'"));
        }

        if (lowered.StartsWith("<double", StringComparison.Ordinal))
        {
            return (DoubleClick, Coordinates(DoubleClickToken().Match(lowered), line, number, "a double click is '<double-click x y>'"));
        }

        return null;
    }

    private static (int X, int Y) Coordinates(Match matched, string line, int number, string shape)
    {
        if (!matched.Success)
        {
            throw new ZMachineException($"line {number}: {shape}, not '{line}'");
        }

        var x = int.Parse(matched.Groups[1].Value, CultureInfo.InvariantCulture);
        var y = int.Parse(matched.Groups[2].Value, CultureInfo.InvariantCulture);

        if (x > CoordinateCeiling || y > CoordinateCeiling)
        {
            throw new ZMachineException($"line {number}: a click coordinate must fit a word (§10.3.2)");
        }

        return (x, y);
    }

    // A link value is 32-bit and never zero: zero is Glk's own "not a
    // link", which no display could deliver.
    private static int? LinkValue(string line, string lowered, int number)
    {
        if (!lowered.StartsWith("<link", StringComparison.Ordinal))
        {
            return null;
        }

        var matched = LinkToken().Match(lowered);

        if (!matched.Success)
        {
            throw new ZMachineException($"line {number}: a link is '<link n>', not '{line}'");
        }

        if (!long.TryParse(matched.Groups[1].Value, NumberStyles.Integer, CultureInfo.InvariantCulture, out var value)
            || value <= 0 || value > LinkCeiling)
        {
            throw new ZMachineException($"line {number}: a link value is 32-bit and never zero");
        }

        return unchecked((int)value);
    }

    // A key token presses its character; a bracketed line naming no
    // key fails loudly, so a typo never types its letters into the
    // game. The "> <key>" prompt form stays a literal command.
    private static string? KeyToken(string line, string lowered, int number)
    {
        if (!(line.StartsWith('<') && line.EndsWith('>')))
        {
            return null;
        }

        if (KeyTokens.TryGetValue(lowered, out var pressed))
        {
            return pressed;
        }

        var known = string.Join(", ", KeyTokens.Keys.Order(StringComparer.Ordinal));
        throw new ZMachineException(
            $"line {number}: unknown key '{line}'; the keys are: {known}, <click x y>, <double-click x y>, <link n>, and <shot> for the camera");
    }

    // The optional > prefix is dropped; a command starting with #
    // after the prefix is taken verbatim, the escape for the rare
    // command that begins with a marker character.
    private static string Command(string line)
    {
        if (line.StartsWith('>'))
        {
            var rest = line[1..].TrimStart();
            return rest.StartsWith('#') ? rest : Uncommented(rest);
        }

        return Uncommented(line);
    }

    private static string Uncommented(string line)
    {
        var comment = InlineComment().Match(line);
        return (comment.Success ? line[..comment.Index] : line).TrimEnd();
    }
}

/// <summary>
/// Reads a replayed conversation for silently refused commands. The
/// response to a command is everything the story prints before the
/// next command is typed; when it speaks the parser's refusal
/// dialect, the watch warns with the command and its line.
/// </summary>
public sealed class RefusalWatch(AcceptanceScript script, Action<string> warn)
{
    // The refusal dialect: responses meaning a typed command did not
    // do what it said, curated from the Infocom house parser and the
    // Inform library, matched case-insensitively at the start of a
    // line. "That's not a verb I recogni" is truncated on purpose:
    // Inform spells the rest -ise or -ize by dialect.
    private static readonly string[] Openings =
    [
        "I beg your pardon",
        "I didn't understand that sentence",
        "I don't know the word",
        "I only understood you as far as",
        "It's not clear what you're referring to",
        "Nice try",
        "That sentence isn't one I recognize",
        "That's not a verb I recogni",
        "There was no verb in that sentence",
        "What do you want",
        "You are not holding",
        "You aren't holding that",
        "You can't be serious",
        "You can't do that",
        "You can't go that way",
        "You can't quite reach",
        "You can't see any",
        "You must use a verb",
        "You should close it first",
        "You should open it first",
        "You're holding too many",
        "Your load is too heavy",
    ];

    // Disambiguation questions bury their tell mid-line.
    private static readonly string[] Tells = ["do you mean"];

    private readonly StringBuilder _response = new();
    private int _awaiting = -1;

    /// <summary>Collect story output as the response in progress.</summary>
    public void Saw(string text) => _response.Append(text);

    /// <summary>Judge the previous response; start collecting the next.</summary>
    public void Typed(int index)
    {
        Judge();
        _awaiting = index;
        _response.Clear();
    }

    /// <summary>Judge the final command's response, ending the watch.</summary>
    public void Finish()
    {
        Judge();
        _awaiting = -1;
        _response.Clear();
    }

    /// <summary>The first line of a response spoken in the refusal dialect, or null.</summary>
    public static string? RefusalIn(string response)
    {
        foreach (var line in response.Split('\n'))
        {
            var candidate = line.Trim();
            // AMFV brackets its parser messages, so the anchor looks
            // past a leading bracket.
            var lowered = candidate.ToLowerInvariant();

            if (lowered.StartsWith('['))
            {
                lowered = lowered[1..];
            }

            var opens = Openings.Any(opening => lowered.StartsWith(opening.ToLowerInvariant(), StringComparison.Ordinal));
            var tells = Tells.Any(tell => lowered.Contains(tell, StringComparison.Ordinal));

            if (opens || tells)
            {
                return candidate;
            }
        }

        return null;
    }

    private void Judge()
    {
        if (_awaiting < 0)
        {
            return;
        }

        var offense = RefusalIn(_response.ToString());

        if (offense is not null)
        {
            var quoted = Quoted(script.Commands[_awaiting]);
            warn($"line {script.Lines[_awaiting]}: {quoted} looks refused: {offense.Trim()}");
        }
    }

    // Python's repr of a str: single quotes unless the text holds a
    // single quote and no double quote.
    private static string Quoted(string text)
    {
        var quote = text.Contains('\'') && !text.Contains('"') ? '"' : '\'';
        var escaped = text.Replace("\\", "\\\\", StringComparison.Ordinal);

        if (quote == '\'')
        {
            escaped = escaped.Replace("'", "\\'", StringComparison.Ordinal);
        }

        return $"{quote}{escaped}{quote}";
    }
}
