namespace Voxam.Core.Glulx.Glk;

/// <summary>
/// What a reference can hold: a word, or an opaque object.
///
/// A held value may be an opaque object rather than a word, an event
/// names its window and an arrangement names its key, because turning
/// objects into the 32-bit ids Glulx sees is the bridge's translation,
/// not the library's. The null object is an opaque hold with nothing
/// in it, which is not the same as the word zero.
/// </summary>
public readonly record struct Held
{
    private Held(bool isOpaque, uint word, GlkObject? opaque)
    {
        IsOpaque = isOpaque;
        Word = word;
        Opaque = opaque;
    }

    /// <summary>Whether the hold names an object rather than a word.</summary>
    public bool IsOpaque { get; }

    /// <summary>The word held, or zero for an opaque hold.</summary>
    public uint Word { get; }

    /// <summary>The object held, or null for a word or the null object.</summary>
    public GlkObject? Opaque { get; }

    /// <summary>Hold a plain 32-bit value.</summary>
    /// <param name="value">The word to hold.</param>
    public static Held OfWord(uint value) => new(false, value, null);

    /// <summary>Hold an opaque object, or the null object.</summary>
    /// <param name="opaque">The object to hold, or null.</param>
    public static Held OfOpaque(GlkObject? opaque) => new(true, 0, opaque);
}

/// <summary>
/// A single call-by-reference output value.
///
/// A Glk function returning through a pointer, a window size, an
/// event_t, a stream_result_t, needs somewhere to put the values. In C
/// that is the caller's pointer; here it is one of these holders, the
/// shape glkote's glkapi.js calls RefBox and RefStruct. The library
/// fills them; the bridge era is what copies their contents back into
/// VM memory or onto the stack.
/// </summary>
public sealed class Ref
{
    /// <summary>Start at a value, the word zero by default.</summary>
    /// <param name="value">What the reference opens holding.</param>
    public Ref(Held value = default) => Value = value;

    /// <summary>The held value.</summary>
    public Held Value { get; set; }
}

/// <summary>A struct passed by reference: a fixed row of fields.</summary>
public sealed class RefStruct
{
    private readonly Held[] _fields;

    /// <summary>Open with a count of zeroed fields.</summary>
    /// <param name="count">How many fields the struct has.</param>
    public RefStruct(int count) => _fields = new Held[count];

    /// <summary>The field values, in the struct's declared order.</summary>
    public IReadOnlyList<Held> Fields => _fields;

    /// <summary>One field, by position.</summary>
    /// <param name="index">Which field to reach.</param>
    public Held this[int index]
    {
        get => _fields[index];
        set => _fields[index] = value;
    }

    /// <summary>Fill every field at once.</summary>
    /// <param name="values">One value per field, in order.</param>
    /// <exception cref="GlulxException">
    /// If the count of values is not the count of fields: a struct has
    /// no optional members.
    /// </exception>
    public void SetAll(params Held[] values)
    {
        ArgumentNullException.ThrowIfNull(values);

        if (values.Length != _fields.Length)
        {
            throw new GlulxException(
                $"expected {_fields.Length} fields, got {values.Length}");
        }

        values.CopyTo(_fields, 0);
    }
}
