namespace Voxam.Core.Glulx.Glk;

/// <summary>
/// A display over two text streams, in the manner of cheapglk.
///
/// Text buffer windows stream to the output as their contents
/// accumulate. Text grid windows are drawn as a block whenever they
/// change, which is what an Inform status line amounts to on a terminal
/// that cannot address the cursor. Input is a line off the input stream.
///
/// No cursor control, no styles, no partial redraw: this is the minimum
/// viable Glk, the display glulxercise needs and a piped session can
/// drive. Everything richer belongs to the painted displays.
///
/// The reference takes a stream and a replay callable separately,
/// because reading a stream at its end answers the empty string while a
/// spent script raises. One seam does for both here: a reader that
/// answers null has nothing more to give, which is what the console's
/// own line reader already says at end of input.
/// </summary>
public sealed class StdioDisplay : GlkDisplay
{
    // The status-line divider never grows past a sensible width, even
    // on a very wide terminal.
    private const int DividerLimit = 60;

    // The character a replayed click travels the command stream as: the
    // Z-Machine's own click code, the same marker that machine's replay
    // presses. The coordinates ride beside it on the click source.
    private const char Click = '\u00FE';

    // The marker a replayed link selection travels as; the value rides
    // beside it on the link source.
    private const char Link = '\u00FC';

    // The acceptance grammar's key tokens replay as the Z-Machine's
    // input characters: the cursor codes and the escape. Here those
    // characters become the Glk keycodes they mean (Glk: Character
    // Input), so one recorded <up> presses up on either machine.
    private static readonly Dictionary<char, uint> TokenKeycodes = new()
    {
        ['\u0081'] = KeyCode.Up,
        ['\u0082'] = KeyCode.Down,
        ['\u0083'] = KeyCode.Left,
        ['\u0084'] = KeyCode.Right,
        ['\u001B'] = KeyCode.Escape,
    };

    // Grids are redrawn only when they change, by window identity.
    private readonly Dictionary<Window, string[]> _grids = [];

    private readonly Action<string> _write;
    private readonly Func<string?> _read;
    private readonly Action<string>? _witness;
    private readonly Func<(int X, int Y)?>? _clicks;
    private readonly Func<int?>? _links;
    private readonly (int Width, int Height) _size;

    /// <summary>Stand over a writer and a reader.</summary>
    /// <param name="write">Where rendered text goes.</param>
    /// <param name="read">
    /// One line at a time; null means the input ran dry, and the
    /// session is over rather than broken.
    /// </param>
    /// <param name="size">The room to lay windows out in.</param>
    /// <param name="witness">
    /// Told every run of buffer text as it renders, which is where the
    /// acceptance harness's refusal watch listens.
    /// </param>
    /// <param name="clicks">
    /// A replayed script's click positions. The claim to mouse input is
    /// true exactly when this is aboard, because a live stream session
    /// has no pointer but a replay must answer the events its
    /// recording's game asked for.
    /// </param>
    /// <param name="links">The same, for selected link values.</param>
    public StdioDisplay(
        Action<string> write,
        Func<string?> read,
        (int Width, int Height)? size = null,
        Action<string>? witness = null,
        Func<(int X, int Y)?>? clicks = null,
        Func<int?>? links = null)
    {
        _write = write;
        _read = read;
        _size = size ?? (80, 24);
        _witness = witness;
        _clicks = clicks;
        _links = links;
    }

    /// <summary>
    /// A stream shows the player's own typing back already, so Glk
    /// echoing the line into the window would show it twice.
    /// </summary>
    public override bool EchoesInput => true;

    /// <inheritdoc/>
    public override bool MouseInput => _clicks is not null;

    /// <inheritdoc/>
    public override bool HyperlinkInput => _links is not null;

    /// <summary>The room chosen at construction.</summary>
    public override (int Width, int Height) Size() => _size;

    /// <summary>Render what changed.</summary>
    /// <param name="root">The root of the window tree, or null.</param>
    public override void Flush(Window? root)
    {
        if (root is not null)
        {
            Render(root);
        }
    }

    /// <summary>A line off the input, cut to what the buffer holds.</summary>
    /// <param name="window">The window waiting on the line.</param>
    /// <param name="maxlen">How many characters its buffer holds.</param>
    public override (string Text, uint Terminator)? ReadLine(Window window, int maxlen)
    {
        var line = ReadLine();

        return (line.Length > maxlen ? line[..maxlen] : line, 0);
    }

    /// <summary>
    /// One keystroke: the first character of a line.
    ///
    /// The input is line-buffered, so this is the same compromise
    /// cheapglk makes, and a bare Return reads as the Return keycode,
    /// which is what "press any key" prompts expect. A replayed key
    /// token arrives as its input character and leaves as the Glk
    /// keycode it means.
    /// </summary>
    /// <param name="window">The window waiting on the key.</param>
    public override uint? ReadChar(Window window)
    {
        var line = ReadLine();

        if (line.Length == 0)
        {
            return KeyCode.Return;
        }

        return TokenKeycodes.TryGetValue(line[0], out var keycode) ? keycode : line[0];
    }

    /// <summary>
    /// A scripted click, spent as the script says click.
    ///
    /// The command stream and the click positions travel in step: when
    /// the game waits for a click, the next command must be the
    /// grammar's click marker, and its coordinates come off the click
    /// source, the very coordinates the recording's game was told. A
    /// script that speaks anything else here has diverged from its
    /// game, and the session ends loudly rather than replaying wrong.
    /// </summary>
    /// <param name="window">The window waiting on a click.</param>
    /// <exception cref="SessionEndException">
    /// When the script and the game disagree about what comes next, or
    /// the clicks ran dry.
    /// </exception>
    public override (int X, int Y)? ReadMouse(Window window)
    {
        if (_clicks is null)
        {
            // No script aboard: the base answer, which sends glk_select
            // to its own loud refusal.
            return null;
        }

        var line = ReadLine();
        var position = line.Length > 0 && line[0] == Click ? _clicks() : null;

        if (position is null)
        {
            _write("\nvoxam: the game waits for a click the script does not spell\n");

            throw new SessionEndException();
        }

        return position;
    }

    /// <summary>
    /// A scripted selection, spent as the script says link. The same
    /// discipline the click keeps.
    /// </summary>
    /// <param name="window">The window waiting on a link.</param>
    /// <exception cref="SessionEndException">
    /// When the script and the game disagree about what comes next, or
    /// the links ran dry.
    /// </exception>
    public override uint? ReadHyperlink(Window window)
    {
        if (_links is null)
        {
            return null;
        }

        var line = ReadLine();
        var value = line.Length > 0 && line[0] == Link ? _links() : null;

        if (value is null)
        {
            _write("\nvoxam: the game waits for a link the script does not spell\n");

            throw new SessionEndException();
        }

        return (uint)value.Value;
    }

    /// <summary>Ask for a filename in the stream; empty cancels.</summary>
    /// <param name="usage">What the file is for, which the ask ignores.</param>
    /// <param name="fmode">How the game means to open it.</param>
    public override string? PromptFile(uint usage, uint fmode)
    {
        var verb = fmode == GlkFileMode.Read ? "Load from" : "Save to";

        _write($"{verb} which file? ");

        string name;

        try
        {
            name = ReadLine().Trim();
        }
        catch (SessionEndException)
        {
            // The input ran dry mid-prompt, which is a cancel rather
            // than a session ended in the middle of a Glk call.
            return null;
        }

        return name.Length == 0 ? null : name;
    }

    /// <summary>
    /// Walk the tree in visual order, drawing what shows. Visual order
    /// rather than tree order, so a status line split off above its
    /// buffer prints above it.
    /// </summary>
    private void Render(Window window)
    {
        switch (window)
        {
            case PairWindow pair:
                foreach (var child in new[] { pair.Child1, pair.Child2 }
                    .OrderBy(held => held.BBox.Top).ThenBy(held => held.BBox.Left))
                {
                    Render(child);
                }

                break;

            case TextGridWindow grid:
                RenderGrid(grid);

                break;

            case TextBufferWindow buffer:
                {
                    // TakeText drains the window, so each run of output
                    // prints exactly once however often we are flushed.
                    var text = buffer.TakeText();

                    if (text.Length > 0)
                    {
                        _write(text);
                        _witness?.Invoke(text);
                    }
                }

                break;

            default:
                // A blank window shows nothing, and a canvas needs a
                // display that can draw.
                break;
        }
    }

    /// <summary>Draw a grid as a block, only when its contents moved.</summary>
    private void RenderGrid(TextGridWindow window)
    {
        var rows = window.Rows().Select(row => row.TrimEnd()).ToArray();

        if (rows.All(row => row.Length == 0))
        {
            return;
        }

        if (_grids.TryGetValue(window, out var shown) && shown.SequenceEqual(rows))
        {
            return;
        }

        _grids[window] = rows;

        foreach (var row in rows)
        {
            _write(row + "\n");
        }

        _write(new string('-', Math.Min(Size().Width, DividerLimit)) + "\n");
    }

    /// <summary>One line; the end of the input ends the session.</summary>
    /// <exception cref="SessionEndException">
    /// At end of input: the session is over, not broken.
    /// </exception>
    private string ReadLine() =>
        _read() ?? throw new SessionEndException();
}
