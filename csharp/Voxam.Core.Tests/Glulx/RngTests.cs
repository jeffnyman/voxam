using Voxam.Core.Glulx;

namespace Voxam.Tests.Glulx;

/// <summary>
/// The stream the random and setrandom opcodes draw on: a xorshift32
/// owned here so that a seed produces the same session forever
/// (Glulx: The Random Number Generator).
/// </summary>
public sealed class RngTests
{
    // The one seed whose mixing lands on zero, which a xorshift state
    // may never be: the mixer is a bijection, so exactly one does.
    private const int SeedThatMixesToZero = 0x61C88647;

    // A seed produces the same stream forever, and two randomizers
    // given the same seed walk in step.
    [Fact]
    public void ASeedProducesTheSameStreamForever()
    {
        var one = new Randomizer(1234);
        var other = new Randomizer(1234);

        Assert.Equal(
            Enumerable.Range(0, 8).Select(_ => one.Word()),
            Enumerable.Range(0, 8).Select(_ => other.Word()));
    }

    [Fact]
    public void ADifferentSeedProducesADifferentStream()
    {
        Assert.NotEqual(new Randomizer(1).Word(), new Randomizer(2).Word());
    }

    // A range is folded from the stream by modulo.
    [Fact]
    public void ARangeIsFoldedFromTheStream()
    {
        var stream = new Randomizer(99);
        var rolled = new Randomizer(99);

        for (var roll = 0; roll < 8; roll++)
        {
            Assert.Equal(stream.Word() % 6, rolled.Below(6));
        }
    }

    [Fact]
    public void ANonZeroSeedResetsTheStreamWhereverItStood()
    {
        var stream = new Randomizer(1);
        stream.Word();
        stream.Seed(1234);

        Assert.Equal(new Randomizer(1234).Word(), stream.Word());
    }

    // A seed of zero asks for genuine unpredictability. In a session
    // the operator seeded it draws its new state off the seeded stream
    // instead, so the whole run stays a function of the one seed
    // given: successive reseeds still differ, and the run replays.
    [Fact]
    public void AZeroSeedDrawsOffTheSeededStreamWhenTheOperatorSeededIt()
    {
        var stream = new Randomizer(5);
        stream.Seed(0);
        var after = stream.Word();

        var again = new Randomizer(5);
        again.Seed(0);

        Assert.Equal(after, again.Word());

        var twice = new Randomizer(5);
        twice.Seed(0);
        twice.Seed(0);

        Assert.NotEqual(after, twice.Word());
    }

    // A session given no seed reaches the operating system's entropy,
    // at the start and at every reseed to zero.
    [Fact]
    public void AnUnseededSessionDrawsOnEntropy()
    {
        var stream = new Randomizer();
        var first = stream.Word();
        stream.Seed(0);

        Assert.NotEqual(0u, first);
        Assert.NotEqual(0u, stream.Word());
    }

    // A xorshift state of zero is a fixed point, so the one seed whose
    // mixing lands there is moved off it.
    [Fact]
    public void TheOneSeedThatWouldMixToZeroIsMovedOffIt()
    {
        var stream = new Randomizer(SeedThatMixesToZero);
        var moved = new Randomizer(1);
        moved.Seed(unchecked((uint)SeedThatMixesToZero));

        Assert.NotEqual(0u, stream.Word());
        Assert.Equal(new Randomizer(SeedThatMixesToZero).Word(), moved.Word());
    }
}
