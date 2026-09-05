using Voxam.Core.Glulx.Glk;
using GlulxException = Voxam.Core.GlulxException;

namespace Voxam.Tests.Glulx.Glk;

/// <summary>
/// The holders Glk writes reference results into, and the characters
/// that reach a display through them.
/// </summary>
public sealed class RefsTests
{
    // A word hold is a plain value, and nothing about it names an
    // object.
    [Fact]
    public void AWordHoldCarriesItsValueAndNoObject()
    {
        var held = Held.OfWord(0xDEADBEEF);

        Assert.False(held.IsOpaque);
        Assert.Equal(0xDEADBEEFu, held.Word);
        Assert.Null(held.Opaque);
    }

    // An opaque hold names an object; the word stays zero, because
    // turning objects into ids is the bridge's translation, not this
    // layer's.
    [Fact]
    public void AnOpaqueHoldCarriesTheObjectItself()
    {
        var window = new BlankWindow();
        var held = Held.OfOpaque(window);

        Assert.True(held.IsOpaque);
        Assert.Equal(0u, held.Word);
        Assert.Same(window, held.Opaque);
    }

    // The null object is an opaque hold with nothing in it, which is a
    // different thing from the word zero.
    [Fact]
    public void TheNullObjectIsNotTheWordZero()
    {
        var nothing = Held.OfOpaque(null);
        var zero = Held.OfWord(0);

        Assert.True(nothing.IsOpaque);
        Assert.Null(nothing.Opaque);
        Assert.NotEqual(zero, nothing);
    }

    // Two holds of the same word are the same hold, and two of
    // different words are not.
    [Fact]
    public void HoldsCompareByWhatTheyHold()
    {
        Assert.Equal(Held.OfWord(7), Held.OfWord(7));
        Assert.NotEqual(Held.OfWord(7), Held.OfWord(8));
        Assert.Equal(Held.OfWord(7).GetHashCode(), Held.OfWord(7).GetHashCode());

        var window = new BlankWindow();

        Assert.Equal(Held.OfOpaque(window), Held.OfOpaque(window));
        Assert.NotEqual(Held.OfOpaque(window), Held.OfOpaque(new BlankWindow()));
    }

    // A reference opens at the word zero, which is what an unwritten
    // output value should read as.
    [Fact]
    public void AReferenceOpensAtZero()
    {
        var reference = new Ref();

        Assert.Equal(Held.OfWord(0), reference.Value);
        Assert.Equal(default, reference.Value);
    }

    // A reference can open at a value and be written afterwards.
    [Fact]
    public void AReferenceTakesAValueAndKeepsIt()
    {
        var reference = new Ref(Held.OfWord(3));

        Assert.Equal(Held.OfWord(3), reference.Value);

        reference.Value = Held.OfWord(4);

        Assert.Equal(Held.OfWord(4), reference.Value);
    }

    // A struct opens with a count of zeroed fields, each reachable on
    // its own.
    [Fact]
    public void AStructOpensZeroedAndTakesOneFieldAtATime()
    {
        var record = new RefStruct(3);

        Assert.Equal(3, record.Fields.Count);
        Assert.All(record.Fields, field => Assert.Equal(Held.OfWord(0), field));

        record[1] = Held.OfWord(9);

        Assert.Equal(Held.OfWord(9), record[1]);
        Assert.Equal(Held.OfWord(0), record[0]);
    }

    // Filling every field at once is how an event_t is answered.
    [Fact]
    public void AStructCanBeFilledWhole()
    {
        var window = new BlankWindow();
        var record = new RefStruct(4);

        record.SetAll(
            Held.OfWord(EventType.LineInput),
            Held.OfOpaque(window),
            Held.OfWord(5),
            Held.OfWord(0));

        Assert.Equal(Held.OfWord(EventType.LineInput), record[0]);
        Assert.Same(window, record[1].Opaque);
        Assert.Equal(Held.OfWord(5), record[2]);
    }

    // A struct has no optional members, so a fill of the wrong length
    // is refused rather than quietly padded.
    [Fact]
    public void AFillOfTheWrongLengthIsRefused()
    {
        var record = new RefStruct(2);

        var refusal = Assert.Throws<GlulxException>(
            () => record.SetAll(Held.OfWord(1)));

        Assert.Contains("expected 2 fields, got 1", refusal.Message, StringComparison.Ordinal);
    }

    // Nothing at all is not a fill either.
    [Fact]
    public void AFillOfNothingIsRefused() =>
        Assert.Throws<ArgumentNullException>(() => new RefStruct(1).SetAll(null!));

    // A character in the Unicode range travels as itself, and one above
    // the basic plane takes the two units C# spends on it.
    [Theory]
    [InlineData(0x41u, "A")]
    [InlineData(0x00E9u, "é")]
    [InlineData(0x1F600u, "😀")]
    public void ACharacterInRangeTravelsAsItself(uint value, string expected) =>
        Assert.Equal(expected, Characters.ToChar(value));

    // Anything outside Unicode, and the surrogate block, which is not
    // independently encodable, becomes the placeholder (Glk: Output).
    [Theory]
    [InlineData(0x110000u)]
    [InlineData(0xFFFFFFFFu)]
    [InlineData(0xD800u)]
    [InlineData(0xDC00u)]
    [InlineData(0xDFFFu)]
    public void ACharacterOutsideUnicodeBecomesThePlaceholder(uint value) =>
        Assert.Equal("?", Characters.ToChar(value));
}
