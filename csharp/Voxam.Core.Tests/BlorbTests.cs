using System.Text;
using Voxam.Core.Tests.Support;

namespace Voxam.Core.Tests;

public class BlorbTests
{
    private static byte[] Chunk(string id, byte[] payload)
    {
        var bytes = new List<byte>(Encoding.ASCII.GetBytes(id));
        bytes.AddRange([(byte)(payload.Length >> 24), (byte)(payload.Length >> 16), (byte)(payload.Length >> 8), (byte)payload.Length]);
        bytes.AddRange(payload);

        if (payload.Length % 2 != 0)
        {
            bytes.Add(0);
        }

        return [.. bytes];
    }

    private static byte[] Form(params byte[][] chunks)
    {
        var body = new List<byte>(Encoding.ASCII.GetBytes("IFRS"));

        foreach (var chunk in chunks)
        {
            body.AddRange(chunk);
        }

        return Chunk("FORM", [.. body]);
    }

    private static byte[] Index(params string[] usages)
    {
        var bytes = new List<byte> { 0, 0, 0, (byte)usages.Length };

        foreach (var usage in usages)
        {
            bytes.AddRange(Encoding.ASCII.GetBytes(usage));
            bytes.AddRange(new byte[8]);
        }

        return Chunk("RIdx", [.. bytes]);
    }

    [Fact]
    public void TheCensusCountsPicturesSoundsAndAStory()
    {
        var blorb = Blorb.Load(Form(Index("Pict", "Pict", "Snd ", "Exec", "Data")));
        Assert.Equal(2, blorb.Pictures);
        Assert.Equal(1, blorb.Sounds);
        Assert.True(blorb.HasStory);
        Assert.Equal("2 pictures, 1 sound, a packaged story", blorb.Described());
        Assert.Equal("1 picture", Blorb.Load(Form(Index("Pict"))).Described());
        Assert.Equal("2 sounds", Blorb.Load(Form(Index("Snd ", "Snd "))).Described());
        Assert.Equal("no resources", Blorb.Load(Form(Index())).Described());
    }

    [Fact]
    public void AnythingElseIsNotABlorb()
    {
        Assert.Throws<ZMachineException>(() => Blorb.Load(new byte[4]));
        Assert.Throws<ZMachineException>(() => Blorb.Load(Chunk("FORM", Encoding.ASCII.GetBytes("AIFF"))));
        Assert.Throws<ZMachineException>(() => Blorb.Load(Chunk("RIFF", Encoding.ASCII.GetBytes("IFRS"))));
    }

    [Fact]
    public void TheIdentifierChunkNamesAStory()
    {
        var builder = new StoryBuilder();
        builder.Quit();
        var story = builder.Build();
        var identity = new byte[13];
        Array.Copy(story, Header.Release, identity, 0, 2);
        Array.Copy(story, Header.Serial, identity, 2, 6);
        Array.Copy(story, Header.Checksum, identity, 8, 2);
        Assert.True(Blorb.Load(Form(Index(), Chunk("IFhd", identity))).Matches(story));
        Assert.True(Blorb.Load(Form(Index())).Matches(story));
        Assert.True(Blorb.Load(Form(Index(), Chunk("IFhd", new byte[4]))).Matches(story));

        var wrongRelease = (byte[])identity.Clone();
        wrongRelease[1] ^= 1;
        Assert.False(Blorb.Load(Form(Index(), Chunk("IFhd", wrongRelease))).Matches(story));
        var wrongSerial = (byte[])identity.Clone();
        wrongSerial[5] = (byte)'x';
        Assert.False(Blorb.Load(Form(Index(), Chunk("IFhd", wrongSerial))).Matches(story));
        var wrongChecksum = (byte[])identity.Clone();
        wrongChecksum[9] ^= 1;
        Assert.False(Blorb.Load(Form(Index(), Chunk("IFhd", wrongChecksum))).Matches(story));
        var wrongChecksumHigh = (byte[])identity.Clone();
        wrongChecksumHigh[8] ^= 1;
        Assert.False(Blorb.Load(Form(Index(), Chunk("IFhd", wrongChecksumHigh))).Matches(story));
    }

    [Fact]
    public void OtherChunksArePassedOverWithTheirPadding()
    {
        var blorb = Blorb.Load(Form(Chunk("Fspc", [0, 0, 0, 1, 9]), Index("Pict")));
        Assert.Equal(1, blorb.Pictures);
    }
}
