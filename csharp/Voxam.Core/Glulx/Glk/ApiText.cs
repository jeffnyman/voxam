using System.Globalization;
using System.Text;

namespace Voxam.Core.Glulx.Glk;

/// <summary>
/// Case, normalization and the clock: the functions that work on text
/// and on time rather than on the display (Glk: Upper and Lower Case,
/// Unicode String Normalization, The System Clock).
/// </summary>
public sealed partial class Api
{
    private const int Microseconds = 1_000_000;

    /// <summary>
    /// The clock, as a moment. Its own seat so a test can pin it: every
    /// other answer here is a pure conversion, and this is the one thing
    /// that moves on its own.
    /// </summary>
    public Func<DateTimeOffset> Now { get; set; } = () => DateTimeOffset.UtcNow;

    private void ServeText()
    {
        // One character's case, where one character can hold it.
        Serve(0x00A0, args => Held.OfWord(MapCase(Word(args[0]), true)));
        Serve(0x00A1, args => Held.OfWord(MapCase(Word(args[0]), false)));

        Serve(0x0120, args => Held.OfWord(MapBuffer(Buf(args[0]), Signed(args[1]), true)));
        Serve(0x0121, args => Held.OfWord(MapBuffer(Buf(args[0]), Signed(args[1]), false)));
        Serve(0x0122, args =>
            Held.OfWord(TitleCase(Buf(args[0]), Signed(args[1]), Word(args[2]) != 0)));

        Serve(0x0123, args =>
            Held.OfWord(Normalize(Buf(args[0]), Signed(args[1]), NormalizationForm.FormD)));
        Serve(0x0124, args =>
            Held.OfWord(Normalize(Buf(args[0]), Signed(args[1]), NormalizationForm.FormC)));

        // Store the current Unix time as a glktimeval_t.
        Serve(0x0160, args =>
        {
            var now = Now();

            Record(args[0])!.SetAll(
                Held.OfWord((uint)(now.ToUnixTimeSeconds() >> 32)),
                Held.OfWord((uint)(now.ToUnixTimeSeconds() & 0xFFFFFFFF)),
                Held.OfWord((uint)(now.Microsecond + (now.Millisecond * 1000))));

            return default;
        });

        // The Unix time divided down, rounding toward the past.
        Serve(0x0161, args =>
        {
            var factor = Signed(args[0]);

            return Held.OfWord(factor == 0
                ? unchecked((uint)-1)
                : (uint)FloorDivide(Now().ToUnixTimeSeconds(), factor));
        });

        Serve(0x0168, args => TimeToDate(Record(args[0]), Record(args[1]), true));
        Serve(0x0169, args => TimeToDate(Record(args[0]), Record(args[1]), false));

        Serve(0x016A, args => SimpleToDate(Signed(args[0]), Signed(args[1]), Record(args[2]), true));
        Serve(0x016B, args => SimpleToDate(Signed(args[0]), Signed(args[1]), Record(args[2]), false));

        Serve(0x016C, args => DateToTime(Record(args[0]), Record(args[1]), true));
        Serve(0x016D, args => DateToTime(Record(args[0]), Record(args[1]), false));

        Serve(0x016E, args => Held.OfWord(DateToSimple(Record(args[0]), Signed(args[1]), true)));
        Serve(0x016F, args => Held.OfWord(DateToSimple(Record(args[0]), Signed(args[1]), false)));
    }

    /// <summary>
    /// One character's mapping, where one character can hold it.
    ///
    /// Only single-character mappings are representable; German sharp-s
    /// uppercasing to "SS" is the usual offender, and stays itself (Glk:
    /// Upper and Lower Case). This runtime's mapping is one to one, so
    /// that rule holds by construction: what comes back is always one
    /// code point, and the ones that would grow come back unchanged.
    /// </summary>
    private static uint MapCase(uint character, bool lower) =>
        character > Characters.MaxUnicode
            ? character
            : (uint)CodePoints(Mapped(Characters.ToChar(character), lower))[0];

    /// <summary>
    /// Case-map a buffer one character at a time.
    ///
    /// Per character, not on the joined string: a whole-string mapping
    /// applies context-sensitive rules, Greek sigma lowercasing
    /// differently at the end of a word, while the specification asks
    /// for "every character" mapped to its equivalent (Glk: Upper and
    /// Lower Case).
    /// </summary>
    private static uint MapBuffer(IBuffer? buf, int numchars, bool lower)
    {
        var chars = Chars(buf, numchars);

        return StoreChars(buf, string.Concat(chars.Select(each => Mapped(each, lower))));
    }

    /// <summary>
    /// Title-case the first character (Glk: Upper and Lower Case).
    ///
    /// Titlecase is a third Unicode case, not a synonym for uppercase:
    /// the ligature U+FB04 uppercases to "FFL" but title-cases to "Ffl",
    /// and U+01C4 has the distinct titlecase form U+01C5.
    /// </summary>
    private static uint TitleCase(IBuffer? buf, int numchars, bool lowerRest)
    {
        var chars = Chars(buf, numchars);

        if (chars.Count == 0)
        {
            return 0;
        }

        var head = CultureInfo.InvariantCulture.TextInfo.ToTitleCase(chars[0]);
        var rest = chars.Skip(1).Select(each => lowerRest ? Mapped(each, true) : each);

        return StoreChars(buf, head + string.Concat(rest));
    }

    /// <summary>Normalize a buffer in place to a Unicode normal form.</summary>
    private static uint Normalize(IBuffer? buf, int numchars, NormalizationForm form)
    {
        var joined = string.Concat(Chars(buf, numchars));

        return StoreChars(buf, joined.IsNormalized(form) ? joined : joined.Normalize(form));
    }

    /// <summary>One string's case, mapped the invariant way.</summary>
    private static string Mapped(string text, bool lower) =>
        lower ? text.ToLowerInvariant() : text.ToUpperInvariant();

    /// <summary>The first so-many characters of a buffer, as text.</summary>
    private static List<string> Chars(IBuffer? buf, int numchars)
    {
        if (numchars <= 0)
        {
            return [];
        }

        return [.. Enumerable
            .Range(0, Math.Min(numchars, buf!.Length))
            .Select(at => Characters.ToChar(buf[at]))];
    }

    /// <summary>
    /// Write text back, truncating at the buffer's capacity. The true
    /// converted length is answered even when it exceeds the buffer,
    /// whose contents past that point are undefined (Glk: Upper and
    /// Lower Case).
    /// </summary>
    private static uint StoreChars(IBuffer? buf, string text)
    {
        var points = CodePoints(text);

        Fill(buf, points.Select(point => (uint)point));

        return (uint)points.Count;
    }

    /// <summary>A string's code points, surrogate pairs joined.</summary>
    private static List<int> CodePoints(string text)
    {
        var found = new List<int>();

        for (var at = 0; at < text.Length; at++)
        {
            if (char.IsHighSurrogate(text[at]) && at + 1 < text.Length
                && char.IsLowSurrogate(text[at + 1]))
            {
                found.Add(char.ConvertToUtf32(text[at], text[at + 1]));
                at++;
            }
            else
            {
                found.Add(text[at]);
            }
        }

        return found;
    }

    /// <summary>
    /// Fill a date struct from a time struct. Both structs are declared
    /// nonnull in the dispatch table, so the bridge has already refused
    /// a null address and neither can be missing here.
    /// </summary>
    private static Held TimeToDate(RefStruct? timeref, RefStruct? dateref, bool utc)
    {
        var seconds = ((long)(int)timeref![0].Word << 32) | timeref[1].Word;

        dateref!.SetAll(BreakOut(seconds, timeref[2].Word, utc));

        return default;
    }

    /// <summary>Fill a date struct from a divided-down time.</summary>
    private static Held SimpleToDate(int time, int factor, RefStruct? dateref, bool utc)
    {
        // Resolution is whole seconds, so microseconds come back zero
        // (Glk: Time and Date Conversions).
        dateref!.SetAll(BreakOut((long)time * factor, 0, utc));

        return default;
    }

    /// <summary>Fill a time struct from a date struct.</summary>
    private static Held DateToTime(RefStruct? dateref, RefStruct? timeref, bool utc)
    {
        var seconds = ToSeconds(dateref!, utc);

        if (seconds is null)
        {
            // An unrepresentable time is -1 in both words (Glk: Time and
            // Date Conversions).
            timeref!.SetAll(
                Held.OfWord(0xFFFFFFFF), Held.OfWord(0xFFFFFFFF), Held.OfWord(0));

            return default;
        }

        timeref!.SetAll(
            Held.OfWord((uint)(seconds.Value >> 32)),
            Held.OfWord((uint)(seconds.Value & 0xFFFFFFFF)),
            Held.OfWord((uint)FloorRemainder((int)dateref![7].Word, Microseconds)));

        return default;
    }

    /// <summary>A date as a divided-down time, or -1 where impossible.</summary>
    private static uint DateToSimple(RefStruct? dateref, int factor, bool utc)
    {
        if (factor == 0)
        {
            return unchecked((uint)-1);
        }

        var seconds = ToSeconds(dateref!, utc);

        return seconds is null
            ? unchecked((uint)-1)
            : (uint)FloorDivide(seconds.Value, factor);
    }

    /// <summary>Explode a timestamp into the eight fields of a glkdate_t.</summary>
    private static Held[] BreakOut(long seconds, uint microsec, bool utc)
    {
        DateTime moment;

        try
        {
            var instant = DateTimeOffset.FromUnixTimeSeconds(seconds);

            moment = utc ? instant.UtcDateTime : instant.ToLocalTime().DateTime;
        }
        catch (ArgumentOutOfRangeException)
        {
            return [.. Enumerable.Repeat(Held.OfWord(0), 8)];
        }

        return
        [
            Held.OfWord((uint)moment.Year),
            Held.OfWord((uint)moment.Month),
            Held.OfWord((uint)moment.Day),
            // Glk counts weekdays from Sunday (Glk: The System Clock),
            // which is where this runtime counts from too.
            Held.OfWord((uint)moment.DayOfWeek),
            Held.OfWord((uint)moment.Hour),
            Held.OfWord((uint)moment.Minute),
            Held.OfWord((uint)moment.Second),
            Held.OfWord(microsec),
        ];
    }

    /// <summary>
    /// Turn glkdate_t fields into a timestamp, or null if impossible.
    ///
    /// The fields "need not be in their normal ranges; they will be
    /// normalized" (Glk: Time and Date Conversions). Months are
    /// normalized by hand because they have no fixed length; everything
    /// else is a plain span from the first of the month, which lets a
    /// day of 40 or an hour of -3 work.
    /// </summary>
    private static long? ToSeconds(RefStruct fields, bool utc)
    {
        var year = (int)fields[0].Word;
        var month = (int)fields[1].Word;

        year += (int)FloorDivide(month - 1, 12);
        month = (int)FloorRemainder(month - 1, 12) + 1;

        try
        {
            var kind = utc ? DateTimeKind.Utc : DateTimeKind.Local;
            var moment = new DateTime(year, month, 1, 0, 0, 0, kind)
                .AddDays((int)fields[2].Word - 1)
                .AddHours((int)fields[4].Word)
                .AddMinutes((int)fields[5].Word)
                .AddSeconds((int)fields[6].Word)
                .AddTicks((int)fields[7].Word * (TimeSpan.TicksPerSecond / Microseconds));

            var offset = utc
                ? TimeSpan.Zero
                : TimeZoneInfo.Local.GetUtcOffset(DateTime.SpecifyKind(moment, DateTimeKind.Unspecified));

            // Truncated toward zero, the way the reference's own read of
            // a floating-point timestamp is.
            return ((moment - DateTime.UnixEpoch).Ticks - offset.Ticks) / TimeSpan.TicksPerSecond;
        }
        catch (ArgumentOutOfRangeException)
        {
            return null;
        }
    }

    /// <summary>Division that rounds toward the past, as the reference's does.</summary>
    private static long FloorDivide(long value, long divisor)
    {
        var quotient = value / divisor;

        return quotient * divisor == value || (value < 0) == (divisor < 0) ? quotient : quotient - 1;
    }

    /// <summary>The remainder that goes with it, never negative.</summary>
    private static long FloorRemainder(long value, long divisor) =>
        value - (FloorDivide(value, divisor) * divisor);
}
