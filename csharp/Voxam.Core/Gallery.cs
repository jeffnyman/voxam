namespace Voxam.Core;

/// <summary>
/// An exact ratio, kept reduced. The Blorb's scaling arrives as
/// fractions and a picture's reported size must be its drawn size, so
/// the arithmetic never rounds until the last step (Blorb: The
/// Resolution Chunk).
/// </summary>
public readonly record struct Ratio
{
    public Ratio(long numerator, long denominator)
    {
        if (denominator == 0)
        {
            throw new ZMachineException("a ratio cannot divide by zero (Blorb: The Resolution Chunk)");
        }

        var divisor = GreatestCommon(Math.Abs(numerator), Math.Abs(denominator));
        Numerator = numerator / divisor;
        Denominator = denominator / divisor;
    }

    /// <summary>One to one: what an unscalable picture wears.</summary>
    public static Ratio One => new(1, 1);

    public long Numerator { get; }

    public long Denominator { get; }

    public static Ratio operator *(Ratio left, Ratio right) =>
        new(left.Numerator * right.Numerator, left.Denominator * right.Denominator);

    public static bool operator <(Ratio left, Ratio right) =>
        left.Numerator * right.Denominator < right.Numerator * left.Denominator;

    public static bool operator >(Ratio left, Ratio right) => right < left;

    public static bool operator <=(Ratio left, Ratio right) => !(right < left);

    public static bool operator >=(Ratio left, Ratio right) => !(left < right);

    /// <summary>The smaller of two ratios.</summary>
    public static Ratio Min(Ratio left, Ratio right) => left < right ? left : right;

    /// <summary>A length scaled and cut down to whole units, as §15 reports it.</summary>
    public int Times(int value) => (int)(value * Numerator / Denominator);

    private static long GreatestCommon(long left, long right)
    {
        while (right != 0)
        {
            (left, right) = (right, left % right);
        }

        return left;
    }
}

/// <summary>One scalable picture's ratios (Blorb: The Resolution Chunk).</summary>
public sealed record Scaling(Ratio Standard, Ratio? Minimum, Ratio? Maximum);

/// <summary>
/// The Reso chunk: the standard window its author drew for, and the
/// scalable art's ratios by number. A picture with no entry is not
/// scalable at all, one image pixel per screen pixel whatever the room.
/// </summary>
public sealed record Resolution(int Width, int Height, IReadOnlyDictionary<int, Scaling> Scalings);

/// <summary>A Rect placeholder: a picture-shaped size with no pixels.</summary>
public sealed record Placard(int Width, int Height);

/// <summary>
/// A Blorb's drawable art, by number: sizes eager, pixels lazy.
///
/// Sizes are what a Version 6 game lays its whole stage out from, so
/// they are answered from the picture's own header without decoding
/// anything, scaled by the Reso ratio the screen earns.
/// </summary>
public sealed class Gallery
{
    private const int SignatureEnd = 8;
    private const int IhdrNameAt = 12;
    private const int WidthAt = 16;
    private const int HeightAt = 20;
    private const int HeaderEnd = 24;

    private static readonly byte[] Signature = [0x89, (byte)'P', (byte)'N', (byte)'G', 0x0D, 0x0A, 0x1A, 0x0A];

    private readonly IReadOnlyDictionary<int, object> _art;
    private readonly Resolution? _resolution;

    /// <summary>An empty gallery: no art hangs, and no picture is available.</summary>
    public static Gallery Empty { get; } = new(new Dictionary<int, object>(), 0, null);

    public Gallery(IReadOnlyDictionary<int, object> art, int release, Resolution? resolution)
    {
        _art = art;
        _resolution = resolution;
        Release = release;
    }

    /// <summary>The resource file's release number, which the census reports (§15 picture_data).</summary>
    public int Release { get; }

    /// <summary>How many pictures hang here, placards included.</summary>
    public int Count => _art.Count;

    /// <summary>The picture's bytes, or null for a placard or a number nothing answers.</summary>
    public byte[]? Pixels(int number) => _art.TryGetValue(number, out var entry) ? entry as byte[] : null;

    /// <summary>
    /// A picture's height and width in pixels, height first as §15
    /// reports it, or null for a number nothing answers.
    /// </summary>
    public (int Height, int Width)? Size(int number)
    {
        if (!_art.TryGetValue(number, out var entry))
        {
            return null;
        }

        return entry is Placard placard ? (placard.Height, placard.Width) : Measured((byte[])entry);
    }

    /// <summary>
    /// A picture's scaling ratio on a screen of this size. The elbow
    /// room is how many times the standard window fits the screen, the
    /// tighter axis deciding; a listed picture's standard ratio
    /// multiplies it, clamped between its minimum and maximum.
    /// </summary>
    public Ratio Scale(int number, int screenWidth, int screenHeight)
    {
        if (_resolution is null || !_resolution.Scalings.TryGetValue(number, out var scaling))
        {
            return Ratio.One;
        }

        var room = Ratio.Min(new Ratio(screenWidth, _resolution.Width), new Ratio(screenHeight, _resolution.Height));
        var ratio = room * scaling.Standard;

        if (scaling.Minimum is { } minimum && ratio < minimum)
        {
            return minimum;
        }

        if (scaling.Maximum is { } maximum && ratio > maximum)
        {
            return maximum;
        }

        return ratio;
    }

    // A PNG's height and width, read straight off its IHDR.
    private static (int Height, int Width) Measured(byte[] data)
    {
        if (data.Length < HeaderEnd
            || !data.AsSpan(0, SignatureEnd).SequenceEqual(Signature)
            || Ascii(data, IhdrNameAt) != "IHDR")
        {
            throw new ZMachineException("a gallery picture does not open with a PNG signature and IHDR");
        }

        return (Word32(data, HeightAt), Word32(data, WidthAt));
    }

    private static string Ascii(byte[] data, int at) => System.Text.Encoding.ASCII.GetString(data, at, 4);

    private static int Word32(byte[] data, int at) => (data[at] << 24) | (data[at + 1] << 16) | (data[at + 2] << 8) | data[at + 3];
}
