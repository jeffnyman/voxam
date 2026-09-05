using System.Text;

namespace Voxam.Core.Glulx.Glk;

/// <summary>
/// What a run of text is dressed in: the Glk style it was written in,
/// and the hyperlink value it belongs to, zero for none.
///
/// The two travel together so a linked run stays distinct from its
/// plain neighbours all the way to the display (Glk: Hyperlinks).
/// </summary>
/// <param name="Style">The Glk style number.</param>
/// <param name="Link">The link value, or zero.</param>
public readonly record struct Dress(uint Style, uint Link);

/// <summary>A run of text sharing one appearance.</summary>
/// <param name="Key">What the display distinguishes runs by.</param>
/// <param name="Text">The characters themselves.</param>
public readonly record struct Segment(Dress Key, string Text);

/// <summary>What a window should be showing at this moment.</summary>
/// <param name="Lines">The display lines to show, oldest first.</param>
/// <param name="Start">
/// The index in the wrapper's lines that these begin at, for anything
/// anchored to a line number.
/// </param>
/// <param name="More">
/// Whether text is waiting that this view could not fit: what a pause
/// prompt announces.
/// </param>
public readonly record struct View(
    IReadOnlyList<IReadOnlyList<Segment>> Lines, int Start, bool More);

/// <summary>
/// Accumulates one window's styled output and wraps it to a width.
///
/// Buffer windows wrap: the game emits a stream of styled characters
/// and the display decides where the lines break (Glk: Text Buffer
/// Windows). Only a display knows its width, so wrapping belongs on the
/// display side, but every painted display needs the same thing, so it
/// lives here rather than being written twice.
///
/// Two things make this more than a call to a line breaker. Text
/// arrives in pieces: a window hands over whatever accumulated since
/// the last flush, which may stop mid-word, so the wrapper keeps the
/// unfinished paragraph and folds the next piece into it. And text is
/// styled: breaking a line has to cut the segments that make it up, not
/// a flat string, or the emphasis moves, so the breaks are found in the
/// plain text and the segments sliced to match.
///
/// The wrapper also keeps the paragraphs it has been given, which is
/// what makes a resize exact: display lines are recomputed from the
/// original text rather than re-broken from lines that already lost
/// their spaces at the break points.
/// </summary>
public sealed class Wrapper
{
    // How many completed paragraphs to remember. Past this the oldest
    // are dropped: a terminal cannot scroll back to them anyway, and a
    // long game would otherwise accumulate its entire transcript.
    private const int Scrollback = 2000;
    private const int Trim = 200;

    // Completed paragraphs, and the one still being written.
    private readonly List<List<Segment>> _history = [];

    private List<Segment> _current = [];

    // Wrapped forms of each, recomputed only when they change.
    private List<List<Segment>>? _done = [];
    private List<List<Segment>>? _tail;

    /// <summary>Start empty, wrapping to the given width.</summary>
    /// <param name="width">The width lines are wrapped to.</param>
    public Wrapper(int width = 80) => Width = Math.Max(1, width);

    /// <summary>The width lines are currently wrapped to.</summary>
    public int Width { get; private set; }

    /// <summary>
    /// How many display lines the player has been shown. Everything
    /// before this has had its turn on screen; text past it that will
    /// not fit in one windowful is what a pause prompt is for.
    /// </summary>
    public int Seen { get; private set; }

    /// <summary>Every display line, oldest first.</summary>
    public IReadOnlyList<IReadOnlyList<Segment>> Lines => Wrapped();

    /// <summary>The text of a display line, without its styling.</summary>
    /// <param name="line">The line to read.</param>
    public static string Plain(IEnumerable<Segment> line)
    {
        ArgumentNullException.ThrowIfNull(line);

        var text = new StringBuilder();

        foreach (var segment in line)
        {
            text.Append(segment.Text);
        }

        return text.ToString();
    }

    /// <summary>Break one styled paragraph into styled display lines.</summary>
    /// <param name="segments">The paragraph, in order.</param>
    /// <param name="width">The width to break it to.</param>
    public static List<List<Segment>> WrapSegments(IReadOnlyList<Segment> segments, int width)
    {
        ArgumentNullException.ThrowIfNull(segments);

        if (segments.Count == 0)
        {
            return [[]];
        }

        // Every paragraph is measured in code points, so a character
        // above the basic plane counts once toward a line's width
        // however many units hold it.
        var points = new int[segments.Count][];
        var starts = new int[segments.Count];
        var length = 0;

        for (var at = 0; at < segments.Count; at++)
        {
            points[at] = Points(segments[at].Text);
            starts[at] = length;
            length += points[at].Length;
        }

        var whole = new int[length];

        for (var at = 0; at < segments.Count; at++)
        {
            points[at].CopyTo(whole, starts[at]);
        }

        var lines = new List<List<Segment>>();

        foreach (var (begin, finish) in Spans(whole, width))
        {
            var line = new List<Segment>();

            for (var at = 0; at < segments.Count; at++)
            {
                var from = starts[at];
                var to = from + points[at].Length;

                if (to <= begin || from >= finish)
                {
                    continue;
                }

                var piece = Joined(
                    points[at], Math.Max(begin, from) - from, Math.Min(finish, to) - from);

                if (piece.Length > 0)
                {
                    line.Add(new Segment(segments[at].Key, piece));
                }
            }

            lines.Add(line);
        }

        return lines;
    }

    /// <summary>Fold more styled output in, continuing the open paragraph.</summary>
    /// <param name="runs">The runs to add, in order.</param>
    public void Add(IEnumerable<Segment> runs)
    {
        ArgumentNullException.ThrowIfNull(runs);

        foreach (var (key, text) in runs)
        {
            if (text.Length == 0)
            {
                continue;
            }

            var pieces = text.Split('\n');

            Extend(key, pieces[0]);

            for (var at = 1; at < pieces.Length; at++)
            {
                BreakParagraph();
                Extend(key, pieces[at]);
            }
        }

        _tail = null;
    }

    /// <summary>
    /// The display lines as if runs had been added, without adding.
    ///
    /// A display draws the line the player is typing this way: it is
    /// part of the layout, but it is not part of the window's contents
    /// until the game accepts it.
    /// </summary>
    /// <param name="runs">The runs to imagine at the end.</param>
    public IReadOnlyList<IReadOnlyList<Segment>> Preview(IReadOnlyList<Segment> runs)
    {
        ArgumentNullException.ThrowIfNull(runs);

        var lines = Wrapped();

        if (runs.Count == 0)
        {
            return lines;
        }

        // Reading the lines settled the open paragraph, and wrapping one
        // always yields at least the empty line, so there is always a
        // tail here to set aside.
        var kept = lines.Take(lines.Count - _tail!.Count).ToList();

        kept.AddRange(WrapSegments([.. _current, .. runs], Width));

        return kept;
    }

    // A window shows a windowful. If the game prints more than that
    // between two chances for the player to read, the excess would
    // scroll past unread, so the display stops and waits. The model is
    // glkterm's lastseenline: Seen is the high-water mark of what has
    // been shown, and text beyond it that will not fit is what holds
    // things up.

    /// <summary>
    /// What to show now, where it starts, and whether more waits.
    ///
    /// Calling this is the display showing them, so it advances Seen,
    /// but only when there is nothing left waiting. While there is, the
    /// view stays put until Advance is called, which is what makes the
    /// pause a pause.
    /// </summary>
    /// <param name="height">How many lines the window can show.</param>
    public View Show(int height)
    {
        var lines = Wrapped();

        if (height <= 0)
        {
            return new View([], 0, false);
        }

        if (lines.Count - Seen <= height)
        {
            // Everything unseen fits: show the newest windowful, and
            // the player has now had the lot. Idempotent, which matters:
            // a repaint happens on every keystroke.
            Seen = lines.Count;

            var newest = Math.Max(0, lines.Count - height);

            return new View(lines.GetRange(newest, lines.Count - newest), newest, false);
        }

        var start = PageStart();
        var page = Math.Min(Page(height), lines.Count - start);

        return new View(lines.GetRange(start, page), start, true);
    }

    /// <summary>
    /// The player has read a page; move on to the next.
    ///
    /// Always at least one line further on. In a window one or two
    /// lines tall the page and the overlap are both a single line, and
    /// without this the pair cancel out and the prompt never clears.
    /// </summary>
    /// <param name="height">How many lines the window can show.</param>
    public void Advance(int height) =>
        Seen = Math.Min(Wrapped().Count, Math.Max(Seen + 1, PageStart() + Page(height)));

    /// <summary>
    /// Treat everything as read, however much of it there is. For the
    /// moments when pausing would be wrong: a file prompt, or a window
    /// the game has just cleared.
    /// </summary>
    public void CatchUp() => Seen = Wrapped().Count;

    /// <summary>Re-wrap everything for a new width.</summary>
    /// <param name="width">The width to wrap to.</param>
    public void Resize(int width)
    {
        width = Math.Max(1, width);

        if (width == Width)
        {
            return;
        }

        Width = width;
        _done = null;
        _tail = null;
    }

    /// <summary>Forget everything, as a cleared window has.</summary>
    public void Clear()
    {
        _history.Clear();
        _current = [];
        _done = [];
        _tail = null;
        Seen = 0;
    }

    /// <summary>
    /// Index ranges of a paragraph, one per display line. Newlines are
    /// consumed, as is the space at each break. A word wider than the
    /// line is cut rather than left to overflow.
    /// </summary>
    private static List<(int Begin, int End)> Spans(int[] text, int width)
    {
        width = Math.Max(width, 1);

        var spans = new List<(int, int)>();
        var position = 0;

        while (true)
        {
            var newline = IndexOf(text, '\n', position);
            var end = newline < 0 ? text.Length : newline;
            var start = position;

            while (end - start > width)
            {
                var limit = start + width;
                // The break may fall on the character just past the
                // line, since a space there costs nothing to drop.
                var point = LastIndexOf(text, ' ', start, Math.Min(limit + 1, text.Length));

                if (point <= start)
                {
                    spans.Add((start, limit));
                    start = limit;
                }
                else
                {
                    spans.Add((start, point));
                    start = point + 1;
                }
            }

            spans.Add((start, end));

            if (newline < 0)
            {
                return spans;
            }

            position = newline + 1;
        }
    }

    private static int IndexOf(int[] text, int wanted, int from)
    {
        for (var at = from; at < text.Length; at++)
        {
            if (text[at] == wanted)
            {
                return at;
            }
        }

        return -1;
    }

    private static int LastIndexOf(int[] text, int wanted, int from, int before)
    {
        for (var at = before - 1; at >= from; at--)
        {
            if (text[at] == wanted)
            {
                return at;
            }
        }

        return -1;
    }

    private static int[] Points(string text)
    {
        var points = new List<int>(text.Length);

        foreach (var rune in text.EnumerateRunes())
        {
            points.Add(rune.Value);
        }

        return [.. points];
    }

    private static string Joined(int[] points, int from, int to)
    {
        var text = new StringBuilder();

        for (var at = from; at < to; at++)
        {
            text.Append(new Rune(points[at]));
        }

        return text.ToString();
    }

    /// <summary>Lines of text per page: the window, less the prompt's line.</summary>
    private static int Page(int height) => Math.Max(1, height - 1);

    // One line of overlap, so the page break does not read as a gap.
    private int PageStart() => Math.Max(0, Seen - 1);

    private List<List<Segment>> Wrapped()
    {
        if (_done is null)
        {
            _done = [];

            foreach (var paragraph in _history)
            {
                _done.AddRange(WrapSegments(paragraph, Width));
            }
        }

        _tail ??= WrapSegments(_current, Width);

        return [.. _done, .. _tail];
    }

    private void Extend(Dress key, string text)
    {
        if (text.Length == 0)
        {
            return;
        }

        if (_current.Count > 0 && _current[^1].Key == key)
        {
            _current[^1] = new Segment(key, _current[^1].Text + text);
        }
        else
        {
            _current.Add(new Segment(key, text));
        }
    }

    private void BreakParagraph()
    {
        _history.Add(_current);
        _done?.AddRange(WrapSegments(_current, Width));
        _current = [];

        if (_history.Count > Scrollback + Trim)
        {
            // Trimmed in batches, so this is not paid on every line.
            _history.RemoveRange(0, Trim);
            _done = null;
        }
    }
}
