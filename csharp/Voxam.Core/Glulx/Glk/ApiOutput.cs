namespace Voxam.Core.Glulx.Glk;

/// <summary>
/// Printing, reading a stream back, and the dress output wears (Glk:
/// How To Print, How To Read, Styles).
/// </summary>
public sealed partial class Api
{
    /// <summary>
    /// Print one Latin-1 character to the current stream. The machine's
    /// own output system reaches the library here rather than through a
    /// selector, which is how a story printing with streamchar and a
    /// story calling glk_put_char land in the same place.
    /// </summary>
    /// <param name="character">The character to print.</param>
    public void PutChar(uint character) => CurrentStream?.PutChar(character & 0xFF);

    /// <summary>Print one Unicode character to the current stream.</summary>
    /// <param name="character">The character to print.</param>
    public void PutCharUni(uint character) => CurrentStream?.PutChar(character);

    private void ServeOutput()
    {
        // Print one character, Latin-1 or full width, to the current
        // stream or to a named one.
        Serve(0x0080, args =>
        {
            PutChar(Word(args[0]));

            return default;
        });

        Serve(0x0128, args =>
        {
            PutCharUni(Word(args[0]));

            return default;
        });

        Serve(0x0081, args =>
        {
            Str(args[0])?.PutChar(Word(args[1]) & 0xFF);

            return default;
        });

        Serve(0x012B, args =>
        {
            Str(args[0])?.PutChar(Word(args[1]));

            return default;
        });

        // Print a string. The Unicode forms differ only in which string
        // object the bridge read on the way in.
        Serve(0x0082, args =>
        {
            CurrentStream?.PutString(Text(args[0]));

            return default;
        });

        Serve(0x0129, args =>
        {
            CurrentStream?.PutString(Text(args[0]));

            return default;
        });

        Serve(0x0083, args =>
        {
            Str(args[0])?.PutString(Text(args[1]));

            return default;
        });

        Serve(0x012C, args =>
        {
            Str(args[0])?.PutString(Text(args[1]));

            return default;
        });

        // Print an array of characters.
        Serve(0x0084, args =>
        {
            PutBuffer(CurrentStream, Buf(args[0]));

            return default;
        });

        Serve(0x012A, args =>
        {
            PutBuffer(CurrentStream, Buf(args[0]));

            return default;
        });

        Serve(0x0085, args =>
        {
            PutBuffer(Str(args[0]), Buf(args[1]));

            return default;
        });

        Serve(0x012D, args =>
        {
            PutBuffer(Str(args[0]), Buf(args[1]));

            return default;
        });

        // Choose the style of coming output (Glk: Styles). Only a window
        // stream shows one.
        Serve(0x0086, args =>
        {
            SetStyle(CurrentStream, Word(args[0]));

            return default;
        });

        Serve(0x0087, args =>
        {
            SetStyle(Str(args[0]), Word(args[1]));

            return default;
        });

        // Mark coming output as a link (Glk: Creating Hyperlinks).
        Serve(0x0100, args =>
        {
            SetHyperlink(CurrentStream, Word(args[0]));

            return default;
        });

        Serve(0x0101, args =>
        {
            SetHyperlink(Str(args[0]), Word(args[1]));

            return default;
        });

        // Read one character, or -1 at the end.
        Serve(0x0090, args => Held.OfWord(GetChar(Str(args[0]))));
        Serve(0x0130, args => Held.OfWord(GetChar(Str(args[0]))));

        // Fill a buffer from a stream; answer the count read.
        Serve(0x0091, args => Held.OfWord(GetLine(Str(args[0]), Buf(args[1]))));
        Serve(0x0132, args => Held.OfWord(GetLine(Str(args[0]), Buf(args[1]))));
        Serve(0x0092, args => Held.OfWord(GetBuffer(Str(args[0]), Buf(args[1]))));
        Serve(0x0131, args => Held.OfWord(GetBuffer(Str(args[0]), Buf(args[1]))));

        // Record a styling suggestion for a display to honor, or
        // withdraw one.
        Serve(0x00B0, args =>
        {
            StyleHints[(Word(args[0]), Word(args[1]), Word(args[2]))] = Signed(args[3]);

            return default;
        });

        Serve(0x00B1, args =>
        {
            StyleHints.Remove((Word(args[0]), Word(args[1]), Word(args[2])));

            return default;
        });

        Serve(0x00B2, args => Held.OfWord(Distinguish(Win(args[0]), Word(args[1]), Word(args[2]))));
        Serve(0x00B3, args =>
            Held.OfWord(Measure(Win(args[0]), Word(args[1]), Word(args[2]), Holder(args[3]))));
    }

    /// <summary>
    /// Print an array of characters to a named stream. Every array the
    /// printing and reading functions take is declared nonnull, so the
    /// bridge has already refused a null one and only the stream can be
    /// missing here.
    /// </summary>
    private static void PutBuffer(StreamObject? stream, IBuffer? buf)
    {
        if (stream is null)
        {
            return;
        }

        for (var at = 0; at < buf!.Length; at++)
        {
            stream.PutChar(buf[at]);
        }
    }

    /// <summary>Choose a stream's style; only window streams show one.</summary>
    private static void SetStyle(StreamObject? stream, uint value)
    {
        if (stream is StreamOnWindow window)
        {
            window.Window.Style = value;
        }
    }

    /// <summary>Everything written from here on belongs to this link.</summary>
    private static void SetHyperlink(StreamObject? stream, uint linkval)
    {
        if (stream is not null)
        {
            stream.Hyperlink = linkval;
        }
    }

    /// <summary>
    /// Read one character, or -1 at the end. The word carries the
    /// two's complement, which the signature says to read as signed.
    /// </summary>
    private static uint GetChar(StreamObject? stream) =>
        stream is null ? unchecked((uint)-1) : unchecked((uint)stream.GetChar());

    /// <summary>Fill a buffer from a stream; answer the count read.</summary>
    private static uint GetBuffer(StreamObject? stream, IBuffer? buf) =>
        stream is null ? 0 : (uint)stream.GetBuffer(buf!);

    /// <summary>Read a line from a stream; answer the count read.</summary>
    private static uint GetLine(StreamObject? stream, IBuffer? buf) =>
        stream is null ? 0 : (uint)stream.GetLine(buf!);

    /// <summary>
    /// Whether two styles look different (Glk: Testing the Appearance of
    /// Styles). Only the display knows; one that cannot say answers no.
    /// </summary>
    private uint Distinguish(Window? window, uint first, uint second) =>
        window is null || first == second ? 0u
            : Display.StyleDistinguish(window, first, second) ? 1u : 0u;

    /// <summary>Measure one attribute of a style, if the display can.</summary>
    private uint Measure(Window? window, uint style, uint hint, Ref? resultref)
    {
        if (window is null || Display.StyleMeasure(window, style, hint) is not { } measured)
        {
            return 0;
        }

        Store(resultref, measured);

        return 1;
    }
}
