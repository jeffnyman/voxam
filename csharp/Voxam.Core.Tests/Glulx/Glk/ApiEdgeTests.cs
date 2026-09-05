using Voxam.Core.Glulx;
using Voxam.Core.Glulx.Glk;

namespace Voxam.Tests.Glulx.Glk;

/// <summary>
/// The corners: the Unicode twins of the printing functions, a tree
/// three deep, and the answers at the edges of what a calendar and a
/// file system can do.
/// </summary>
public sealed class ApiEdgeTests : IDisposable
{
    private const uint Buf = 0x500;
    private const uint Ref = 0x600;
    private const uint Time = 0x780;

    private readonly string _saveDir =
        Path.Combine(Path.GetTempPath(), "voxam-glk-edge-" + Path.GetRandomFileName());

    public ApiEdgeTests() => Directory.CreateDirectory(_saveDir);

    public void Dispose() => Directory.Delete(_saveDir, true);

    // Every printing function has a Unicode twin, and the pair differ
    // only in what the bridge read on the way in. Both reach the same
    // stream.
    [Fact]
    public void EveryPrintingFunctionHasAUnicodeTwin()
    {
        var (bridge, glk) = Seam();

        var window = bridge.Perform(0x0023, [0, 0, 0, WindowType.TextBuffer, 0]);
        var stream = bridge.Perform(0x002C, [window]);

        bridge.Perform(0x002F, [window]);

        bridge.Perform(0x0128, [0x41]);
        bridge.Perform(0x012B, [stream, 0x42]);
        bridge.Perform(0x0129, [UniStringAt(bridge, "cd")]);
        bridge.Perform(0x012C, [stream, UniStringAt(bridge, "ef")]);

        bridge.Memory.WriteWord((int)Buf, 0x67);
        bridge.Memory.WriteWord((int)Buf + 4, 0x68);

        bridge.Perform(0x012A, [Buf, 2]);
        bridge.Perform(0x012D, [stream, Buf, 2]);

        Assert.Equal("ABcdefghgh", ((TextBufferWindow)glk.Windows[0]).Text());
    }

    // The byte-wide printing functions take the low byte and no more,
    // where the Unicode ones take the whole word.
    [Fact]
    public void TheByteWideFunctionsTakeTheLowByte()
    {
        var (bridge, glk) = Seam();

        var window = bridge.Perform(0x0023, [0, 0, 0, WindowType.TextBuffer, 0]);

        bridge.Perform(0x002F, [window]);
        bridge.Perform(0x0080, [0x141]);
        bridge.Perform(0x0128, [0x141]);

        Assert.Equal("AŁ", ((TextBufferWindow)glk.Windows[0]).Text());
    }

    // Reading a stream has the same twins, and they answer alike.
    [Fact]
    public void ReadingHasTheSameTwins()
    {
        var (bridge, _) = Seam();

        bridge.Memory.WriteWord((int)Buf, 0x41);
        bridge.Memory.WriteWord((int)Buf + 4, 0x42);

        var stream = bridge.Perform(0x0139, [Buf, 2, GlkFileMode.Read, 0]);

        Assert.Equal(0x41u, bridge.Perform(0x0130, [stream]));
        Assert.Equal(1u, bridge.Perform(0x0131, [stream, Ref, 4]));
        Assert.Equal(0u, bridge.Perform(0x0131, [0, Ref, 4]));
        Assert.Equal(0x42u, bridge.Memory.ReadWord((int)Ref));
        Assert.Equal(0u, bridge.Perform(0x0091, [0, Ref, 4]));
    }

    // Splitting a window that already hangs under a pair puts the new
    // pair where the old window stood, on whichever side it was.
    [Fact]
    public void ATreeCanGrowThreeDeepOnEitherSide()
    {
        var (bridge, glk) = Seam();

        var first = bridge.Perform(0x0023, [0, 0, 0, WindowType.TextBuffer, 1]);
        var second = bridge.Perform(
            0x0023, [first, WindowMethod.Above | WindowMethod.Fixed, 3, WindowType.TextGrid, 2]);

        // The first window is now child1 of the root pair.
        bridge.Perform(
            0x0023, [first, WindowMethod.Below | WindowMethod.Fixed, 2, WindowType.TextGrid, 3]);

        // And the second is child2 of it.
        bridge.Perform(
            0x0023, [second, WindowMethod.Left | WindowMethod.Fixed, 4, WindowType.TextGrid, 4]);

        Assert.Equal(7, glk.Windows.Count);
        Assert.Equal(4, glk.Windows.Count(each => each is not PairWindow));

        // Every window still reaches the root through its parents.
        foreach (var window in glk.Windows)
        {
            var walk = window;

            while (walk.Parent is not null)
            {
                walk = walk.Parent;
            }

            Assert.Same(glk.Root, walk);
        }
    }

    // Closing a window deep in the tree promotes its sibling into the
    // grandparent, on whichever side the parent stood.
    [Fact]
    public void ClosingDeepInTheTreePromotesIntoTheGrandparent()
    {
        var (bridge, glk) = Seam();

        var first = bridge.Perform(0x0023, [0, 0, 0, WindowType.TextBuffer, 1]);
        var second = bridge.Perform(
            0x0023, [first, WindowMethod.Above | WindowMethod.Fixed, 3, WindowType.TextGrid, 2]);
        var third = bridge.Perform(
            0x0023, [second, WindowMethod.Left | WindowMethod.Fixed, 4, WindowType.TextGrid, 3]);

        bridge.Perform(0x0024, [third, 0]);

        Assert.Equal(3, glk.Windows.Count);
        Assert.Equal(second, bridge.Registry.Register(((PairWindow)glk.Root!).Child2, 0));

        var fourth = bridge.Perform(
            0x0023, [first, WindowMethod.Below | WindowMethod.Fixed, 2, WindowType.TextGrid, 4]);

        bridge.Perform(0x0024, [fourth, 0]);

        Assert.Equal(3, glk.Windows.Count);
        Assert.Equal(first, bridge.Registry.Register(((PairWindow)glk.Root!).Child1, 0));
    }

    // A walk over a list with nothing on it ends where it began.
    [Fact]
    public void AWalkOverNothingEndsAtOnce()
    {
        var (bridge, _) = Seam();

        Assert.Equal(0u, bridge.Perform(0x0064, [0, Ref]));
        Assert.Equal(0u, bridge.Memory.ReadWord((int)Ref));
        Assert.Equal(0u, bridge.Perform(0x0020, [0, Ref]));
        Assert.Equal(0u, bridge.Perform(0x0040, [0, Ref]));
    }

    // With no bridge beneath it the library still buries what it
    // closes; there is simply nobody to tell about it.
    [Fact]
    public void ALibraryWithNoBridgeStillBuriesWhatItCloses()
    {
        var glk = new Api();
        var window = new BlankWindow();

        glk.Windows.Add(window);
        glk.Streams.Add(window.Stream);

        Assert.Null(glk.OnDispose);

        glk.Call(Signatures.Lookup(0x0024)!, [Held.OfOpaque(window), null]);

        Assert.True(window.Disposed);
        Assert.True(window.Stream.Disposed);
        Assert.Empty(glk.Windows);
    }

    // A blank window shows nothing and is the plainest thing the tree
    // can hold (Glk: Blank Windows).
    [Fact]
    public void ABlankWindowOpensAndShowsNothing()
    {
        var (bridge, glk) = Seam();

        var ident = bridge.Perform(0x0023, [0, 0, 0, WindowType.Blank, 0]);

        Assert.NotEqual(0u, ident);
        Assert.IsType<BlankWindow>(glk.Root);
        Assert.Equal(WindowType.Blank, bridge.Perform(0x0028, [ident]));

        bridge.Perform(0x0025, [ident, Ref, Ref + 4]);

        Assert.Equal(0u, bridge.Memory.ReadWord((int)Ref));
    }

    // A string with a character above the basic plane travels through
    // the case functions as one character, not the two units it is held
    // in.
    [Fact]
    public void AnAstralCharacterIsOneCharacterThrough()
    {
        var (bridge, _) = Seam();

        bridge.Memory.WriteWord((int)Buf, 0x1F600);
        bridge.Memory.WriteWord((int)Buf + 4, 0x61);

        Assert.Equal(2u, bridge.Perform(0x0121, [Buf, 8, 2]));
        Assert.Equal(0x1F600u, bridge.Memory.ReadWord((int)Buf));
        Assert.Equal(0x41u, bridge.Memory.ReadWord((int)Buf + 4));
    }

    // Text already in the form asked for is left exactly as it is.
    [Fact]
    public void TextAlreadyNormalizedIsLeftAlone()
    {
        var (bridge, _) = Seam();

        bridge.Memory.WriteWord((int)Buf, 0x41);
        bridge.Memory.WriteWord((int)Buf + 4, 0x42);

        Assert.Equal(2u, bridge.Perform(0x0124, [Buf, 8, 2]));
        Assert.Equal(0x41u, bridge.Memory.ReadWord((int)Buf));
    }

    // A second beyond what any calendar can hold explodes into nothing
    // at all rather than faulting.
    [Fact]
    public void ASecondBeyondEveryCalendarIsZeroed()
    {
        var (bridge, _) = Seam();

        bridge.Memory.WriteWord((int)Time, 0x7FFFFFFF);
        bridge.Memory.WriteWord((int)Time + 4, 0xFFFFFFFF);
        bridge.Memory.WriteWord((int)Time + 8, 0);

        bridge.Perform(0x0168, [Time, Ref]);

        for (var field = 0; field < 8; field++)
        {
            Assert.Equal(0u, bridge.Memory.ReadWord((int)Ref + (field * 4)));
        }
    }

    // A file the system will not let go of stays where it is, and
    // deleting it is quiet about that.
    [Fact]
    public void AFileTheSystemHoldsOntoStaysWhereItIs()
    {
        var (bridge, glk) = Seam();

        var fileref = bridge.Perform(0x0061, [FileUsage.Data, StringAt(bridge, "held"), 0]);
        var path = glk.FileRefs[0].Filename;

        File.WriteAllText(path, "x");

        using (var held = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.None))
        {
            bridge.Perform(0x0066, [fileref]);
        }

        Assert.True(File.Exists(path));
    }

    // A game can name a file that turns out to be a directory. Opening
    // it cannot work, and that answers the null stream rather than
    // faulting (Glk: File Streams).
    [Fact]
    public void ANameThatIsReallyADirectoryOpensNothing()
    {
        var (bridge, glk) = Seam();

        var fileref = bridge.Perform(0x0061, [FileUsage.Data, StringAt(bridge, "folder"), 0]);

        Directory.CreateDirectory(glk.FileRefs[0].Filename);

        Assert.Equal(0u, bridge.Perform(0x0042, [fileref, GlkFileMode.Read, 0]));
        Assert.Equal(0u, bridge.Perform(0x0042, [fileref, GlkFileMode.Write, 0]));

        // And deleting it is quiet about being unable to.
        bridge.Perform(0x0066, [fileref]);

        Assert.True(Directory.Exists(glk.FileRefs[0].Filename));
    }

    private static uint StringAt(Bridge bridge, string text)
    {
        const int At = 0x800;

        bridge.Memory.WriteByte(At, 0xE0);

        for (var index = 0; index < text.Length; index++)
        {
            bridge.Memory.WriteByte(At + 1 + index, text[index]);
        }

        bridge.Memory.WriteByte(At + 1 + text.Length, 0);

        return At;
    }

    private static uint UniStringAt(Bridge bridge, string text)
    {
        const int At = 0x900;

        bridge.Memory.WriteWord(At, 0xE2000000);

        for (var index = 0; index < text.Length; index++)
        {
            bridge.Memory.WriteWord(At + 4 + (index * 4), text[index]);
        }

        bridge.Memory.WriteWord(At + 4 + (text.Length * 4), 0);

        return At;
    }

    private (Bridge Bridge, Api Glk) Seam()
    {
        var story = new Story(new GlulxBuilder
        {
            RamStart = 0x100,
            ExtStart = 0x200,
            EndMem = 0x2000,
            StackSize = 0x400,
        }.Build());

        var glk = new Api(saveDir: _saveDir);

        return (new Bridge(new Memory(story), glk, new StackMemory(0x400)), glk);
    }
}
