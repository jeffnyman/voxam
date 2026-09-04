using Voxam.Core.Glulx;

namespace Voxam.Tests.Glulx;

/// <summary>Which output system is current, and its rock (Glulx: Output).</summary>
public sealed class IoSystemTests
{
    // The machine starts in the null system, and returns to it on a
    // restart.
    [Fact]
    public void TheNullSystemIsWhereEverythingStartsAndReturns()
    {
        var iosys = new IoSystem();

        Assert.Equal((uint)IoMode.Null, iosys.Mode);
        Assert.Equal(0u, iosys.Rock);

        iosys.Select((uint)IoMode.Filter, 0x500);
        iosys.Reset();

        Assert.Equal((uint)IoMode.Null, iosys.Mode);
        Assert.Equal(0u, iosys.Rock);
    }

    // An unrecognized mode is not an error: the specification says
    // setting an unsupported system selects the null system instead,
    // which is what a program probing with an unknown mode finds.
    [Theory]
    [InlineData(0u, 0x500u, 0u, 0x500u)]
    [InlineData(1u, 0x500u, 1u, 0x500u)]
    [InlineData(2u, 0x500u, 2u, 0x500u)]
    [InlineData(3u, 0x500u, 0u, 0u)]
    [InlineData(0xFFFFFFFFu, 0x500u, 0u, 0u)]
    public void AnUnsupportedSystemSelectsTheNullSystem(uint mode, uint rock, uint chosen, uint kept)
    {
        var iosys = new IoSystem();
        iosys.Select(mode, rock);

        Assert.Equal(chosen, iosys.Mode);
        Assert.Equal(kept, iosys.Rock);
    }
}
