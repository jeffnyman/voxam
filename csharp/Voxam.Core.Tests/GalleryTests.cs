using System.Text;

namespace Voxam.Core.Tests;

/// <summary>A Blorb's art: its sizes, its release, and the room a screen earns it (Blorb: The Resolution Chunk).</summary>
public class GalleryTests
{
    private static byte[] Png(int width, int height)
    {
        var bytes = new List<byte> { 0x89, (byte)'P', (byte)'N', (byte)'G', 0x0D, 0x0A, 0x1A, 0x0A };
        bytes.AddRange([0, 0, 0, 13]);
        bytes.AddRange(Encoding.ASCII.GetBytes("IHDR"));
        bytes.AddRange([(byte)(width >> 24), (byte)(width >> 16), (byte)(width >> 8), (byte)width]);
        bytes.AddRange([(byte)(height >> 24), (byte)(height >> 16), (byte)(height >> 8), (byte)height]);
        return [.. bytes];
    }

    private static Gallery Hung(Resolution? resolution = null, int release = 0)
    {
        var art = new Dictionary<int, object>
        {
            [1] = Png(320, 200),
            [2] = new Placard(40, 20),
        };
        return new Gallery(art, release, resolution);
    }

    // A ratio stays exact and reduced, so a reported size and a drawn
    // one can never drift apart.
    [Fact]
    public void ARatioIsExactAndReduced()
    {
        var half = new Ratio(2, 4);
        Assert.Equal((1L, 2L), (half.Numerator, half.Denominator));
        Assert.Equal(new Ratio(1, 3), new Ratio(2, 4) * new Ratio(2, 3));
        Assert.True(new Ratio(1, 3) < new Ratio(1, 2));
        Assert.True(new Ratio(1, 2) > new Ratio(1, 3));
        Assert.True(new Ratio(1, 2) <= new Ratio(1, 2));
        Assert.True(new Ratio(1, 2) >= new Ratio(1, 2));
        Assert.Equal(new Ratio(1, 3), Ratio.Min(new Ratio(1, 2), new Ratio(1, 3)));
        Assert.Equal(new Ratio(1, 3), Ratio.Min(new Ratio(1, 3), new Ratio(1, 2)));
        Assert.Equal((0L, 1L), (new Ratio(0, 5).Numerator, new Ratio(0, 5).Denominator));
        Assert.Equal(Ratio.One, new Ratio(7, 7));
        // The scaling cuts down to whole units, as §15 reports them.
        Assert.Equal(66, new Ratio(2, 3).Times(100));
        Assert.Equal(0, new Ratio(0, 5).Times(100));
        Assert.Equal("a ratio cannot divide by zero (Blorb: The Resolution Chunk)", Assert.Throws<ZMachineException>(() => new Ratio(1, 0)).Message);
    }

    [Fact]
    public void APicturesSizeIsReadOffItsOwnHeader()
    {
        var gallery = Hung(release: 7);
        Assert.Equal(2, gallery.Count);
        Assert.Equal(7, gallery.Release);
        Assert.Equal((200, 320), gallery.Size(1));
        Assert.Equal((20, 40), gallery.Size(2));
        Assert.Null(gallery.Size(3));
        Assert.NotNull(gallery.Pixels(1));
        Assert.Null(gallery.Pixels(2));
        Assert.Null(gallery.Pixels(3));
        Assert.Equal(0, Gallery.Empty.Count);
    }

    [Fact]
    public void ArtThatIsNotAPngIsRefused()
    {
        var gallery = new Gallery(new Dictionary<int, object> { [1] = new byte[] { 1, 2, 3 } }, 0, null);
        Assert.Equal("a gallery picture does not open with a PNG signature and IHDR", Assert.Throws<ZMachineException>(() => gallery.Size(1)).Message);
        var headerless = new Gallery(new Dictionary<int, object> { [1] = Png(1, 1)[..12] }, 0, null);
        Assert.Throws<ZMachineException>(() => headerless.Size(1));
        var stub = new Gallery(new Dictionary<int, object> { [1] = new byte[4] }, 0, null);
        Assert.Throws<ZMachineException>(() => stub.Size(1));
        var unsigned = new Gallery(new Dictionary<int, object> { [1] = new byte[32] }, 0, null);
        Assert.Throws<ZMachineException>(() => unsigned.Size(1));
        var mislabelled = Png(1, 1);
        mislabelled[13] = (byte)'X';
        Assert.Throws<ZMachineException>(() => new Gallery(new Dictionary<int, object> { [1] = mislabelled }, 0, null).Size(1));
    }

    // The elbow room is how many times the standard window fits the
    // screen, the tighter axis deciding, and the picture's own ratio
    // multiplies it between its limits.
    [Fact]
    public void TheScreenEarnsAPictureItsRoom()
    {
        var scalings = new Dictionary<int, Scaling>
        {
            [1] = new(new Ratio(1, 1), null, null),
            [2] = new(new Ratio(1, 1), new Ratio(2, 1), null),
            [3] = new(new Ratio(1, 1), null, new Ratio(3, 2)),
        };
        var gallery = Hung(new Resolution(320, 200, scalings));
        // Twice the standard window each way: the room is 2.
        Assert.Equal(new Ratio(2, 1), gallery.Scale(1, 640, 400));
        // Wider than it is tall: the tighter axis decides.
        Assert.Equal(new Ratio(2, 1), gallery.Scale(1, 1600, 400));
        Assert.Equal(new Ratio(2, 1), gallery.Scale(2, 320, 200));
        Assert.Equal(new Ratio(3, 2), gallery.Scale(3, 640, 400));
        // A picture with no entry, or a Blorb with no Reso, is not
        // scalable at all.
        Assert.Equal(Ratio.One, gallery.Scale(9, 640, 400));
        Assert.Equal(Ratio.One, Hung().Scale(1, 640, 400));
    }
}
