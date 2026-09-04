using System.Text;
using Voxam.Core.Tests.Support;

namespace Voxam.Core.Tests;

/// <summary>Loading a story from disk, packaged or accompanied (Blorb §2).</summary>
public class StoryFileTests
{
    private static byte[] Chunk(string id, byte[] payload)
    {
        var framed = new List<byte>(Encoding.ASCII.GetBytes(id));
        framed.AddRange([(byte)(payload.Length >> 24), (byte)(payload.Length >> 16), (byte)(payload.Length >> 8), (byte)payload.Length]);
        framed.AddRange(payload);

        if (payload.Length % 2 != 0)
        {
            framed.Add(0);
        }

        return [.. framed];
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

    // A Blorb whose one Exec entry names the story chunk that follows
    // the index: FORM header 12, RIdx header 8, index 16.
    private static byte[] Packaged(string kind, byte[] story)
    {
        var index = new List<byte> { 0, 0, 0, 1 };
        index.AddRange(Encoding.ASCII.GetBytes("Exec"));
        index.AddRange([0, 0, 0, 0, 0, 0, 0, 36]);
        return Form(Chunk("RIdx", [.. index]), Chunk(kind, story));
    }

    private static byte[] Story()
    {
        var b = new StoryBuilder(5);
        b.Quit();
        return b.Build();
    }

    [Fact]
    public void ABareStoryLoadsAloneAndASidecarBlorbJoinsIt()
    {
        var directory = Directory.CreateTempSubdirectory("voxam-story");

        try
        {
            var story = Story();
            var path = Path.Combine(directory.FullName, "tale.z5");
            File.WriteAllBytes(path, story);
            var (loaded, blorb) = StoryFile.Load(path);
            Assert.Equal(story, loaded);
            Assert.Null(blorb);

            File.WriteAllBytes(Path.Combine(directory.FullName, "tale.blorb"), Form(Chunk("RIdx", [0, 0, 0, 0])));
            (loaded, blorb) = StoryFile.Load(path);
            Assert.Equal(story, loaded);
            Assert.NotNull(blorb);
            Assert.Equal("no resources", blorb.Described());
        }
        finally
        {
            directory.Delete(recursive: true);
        }
    }

    [Fact]
    public void APackagedStoryComesOutOfItsBlorb()
    {
        var directory = Directory.CreateTempSubdirectory("voxam-story");

        try
        {
            var story = Story();
            var path = Path.Combine(directory.FullName, "tale.ZBLORB");
            File.WriteAllBytes(path, Packaged("ZCOD", story));
            var (loaded, blorb) = StoryFile.Load(path);
            Assert.Equal(story, loaded);
            Assert.NotNull(blorb);

            // A Glulx Blorb comes out of its wrapper the same way; what
            // arrived is the story's own first bytes to say.
            var glulx = Path.Combine(directory.FullName, "other.gblorb");
            File.WriteAllBytes(glulx, Packaged("GLUL", story));
            Assert.Equal(story, StoryFile.Load(glulx).Story);

            var adrift = Path.Combine(directory.FullName, "elsewhere.blorb");
            File.WriteAllBytes(adrift, Packaged("ADRI", story));
            var error = Assert.Throws<ZMachineException>(() => StoryFile.Load(adrift));
            Assert.Equal("elsewhere.blorb packages no story this interpreter can run", error.Message);
        }
        finally
        {
            directory.Delete(recursive: true);
        }
    }
}
