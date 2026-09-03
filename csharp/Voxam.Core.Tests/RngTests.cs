namespace Voxam.Core.Tests;

public class RngTests
{
    // The expected values come from the Python reference's Randomizer
    // with the same seeds; the two generators must agree forever, or
    // no recording could replay on both.
    [Fact]
    public void ASeededStreamMatchesTheReference()
    {
        var rng = new Randomizer(92);
        var rolls = Enumerable.Range(0, 8).Select(_ => rng.Roll(100)).ToArray();
        Assert.Equal([98, 27, 14, 54, 55, 58, 60, 30], rolls);
    }

    [Fact]
    public void ASmallSeedCyclesTheRisingSequence()
    {
        var rng = new Randomizer(92);
        rng.Seed(5);
        var rolls = Enumerable.Range(0, 7).Select(_ => rng.Roll(3)).ToArray();
        Assert.Equal([1, 2, 3, 1, 2, 1, 2], rolls);
    }

    [Fact]
    public void ALargeSeedReseedsTheStream()
    {
        var rng = new Randomizer(92);
        rng.Seed(5);
        rng.Seed(5000);
        var rolls = Enumerable.Range(0, 4).Select(_ => rng.Roll(6)).ToArray();
        Assert.Equal([2, 5, 2, 4], rolls);
    }

    // In a seeded session a return to the random state draws its new
    // state off the seeded stream, so the run stays a function of the
    // one seed; the reference gives these exact values.
    [Fact]
    public void RandomizeInASeededSessionStaysDeterministic()
    {
        var rng = new Randomizer(92);
        rng.Seed(5);
        rng.Seed(5000);

        foreach (var _ in Enumerable.Range(0, 4))
        {
            rng.Roll(6);
        }

        rng.Randomize();
        var rolls = Enumerable.Range(0, 3).Select(_ => rng.Roll(1000)).ToArray();
        Assert.Equal([501, 959, 976], rolls);

        var fresh = new Randomizer(92);
        fresh.Randomize();
        var again = Enumerable.Range(0, 3).Select(_ => fresh.Roll(1000)).ToArray();
        Assert.Equal([68, 686, 43], again);
    }

    [Fact]
    public void AnUnseededSessionRollsInRange()
    {
        var rng = new Randomizer(null);

        foreach (var _ in Enumerable.Range(0, 50))
        {
            Assert.InRange(rng.Roll(6), 1, 6);
        }

        rng.Randomize();
        Assert.InRange(rng.Roll(6), 1, 6);
    }

    [Fact]
    public void RandomizeLeavesTheRisingSequence()
    {
        var rng = new Randomizer(null);
        rng.Seed(2);
        Assert.Equal(1, rng.Roll(10));
        Assert.Equal(2, rng.Roll(10));
        rng.Randomize();
        Assert.InRange(rng.Roll(1000), 1, 1000);
    }
}
