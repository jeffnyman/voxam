using System.Text;
using Voxam.Core;
using Voxam.Core.Glulx.Glk;

namespace Voxam.Tests.Glulx.Glk;

/// <summary>
/// A display that claims to draw and to play, and remembers what it was
/// asked, but overrides none of the doing: the seat's own answers are
/// what a game gets.
/// </summary>
internal class ArtlessDisplay : ScriptedDisplay
{
    public List<string> Asks { get; } = [];

    public override bool Graphics => true;

    public override bool Sound => true;
}

/// <summary>A display that actually draws and plays, and says so.</summary>
internal sealed class DrawingDisplay : ArtlessDisplay
{
    public bool Draws { get; set; } = true;

    public bool Plays { get; set; } = true;

    public override bool DrawImage(
        Window window, ImageInfo image, int val1, int val2, uint width, uint height)
    {
        Asks.Add($"draw {image.Number} at {val1},{val2} {width}x{height}");

        return Draws;
    }

    public override void EraseRect(Window window, int left, int top, uint width, uint height) =>
        Asks.Add($"erase {left},{top} {width}x{height}");

    public override void FillRect(
        Window window, uint color, int left, int top, uint width, uint height) =>
        Asks.Add($"fill {color:x6} {left},{top} {width}x{height}");

    public override void SetBackgroundColor(Window window, uint color) =>
        Asks.Add($"paper {color:x6}");

    public override void FlowBreak(Window window) => Asks.Add("break");

    public override bool PlaySound(SoundChannel channel, uint sound, uint repeats, uint notify)
    {
        Asks.Add($"play {sound} x{repeats} notify {notify}");

        return Plays;
    }

    public override void StopSound(SoundChannel channel) => Asks.Add("stop");

    public override void PauseSound(SoundChannel channel, bool paused) =>
        Asks.Add(paused ? "pause" : "unpause");

    public override void SetVolume(SoundChannel channel, uint volume, uint duration) =>
        Asks.Add($"volume {volume} over {duration}");
}

/// <summary>
/// A display that can start a sound but has nothing to do to stop one,
/// which is an honest shape: the seat answers for the rest.
/// </summary>
internal sealed class EagerDisplay : ArtlessDisplay
{
    public override bool PlaySound(SoundChannel channel, uint sound, uint repeats, uint notify) =>
        true;
}

/// <summary>
/// Pictures and sound: what a game asks for, what reaches the display,
/// and what a display that cannot do either answers instead.
/// </summary>
public sealed class ApiArtTests
{
    private const uint Ref = 0x600;

    // A picture's size is answered from the resource bytes, so a game
    // can lay a window out before discovering it cannot draw.
    [Fact]
    public void APicturesSizeIsAnsweredWhetherOrNotItCanBeDrawn()
    {
        var glk = Seam(new NullDisplay());
        var width = new Ref();
        var height = new Ref();

        Assert.Equal(1u, Call(glk, 0x00E0, Held.OfWord(1), width, height).Word);
        Assert.Equal(640u, width.Value.Word);
        Assert.Equal(400u, height.Value.Word);

        // A number no picture answers reports zeros, and says so.
        Assert.Equal(0u, Call(glk, 0x00E0, Held.OfWord(9), width, height).Word);
        Assert.Equal(0u, width.Value.Word);
        Assert.Equal(0u, height.Value.Word);

        // And the holders are optional.
        Assert.Equal(1u, Call(glk, 0x00E0, Held.OfWord(1), null, null).Word);
    }

    // A picture is drawn at its own size unless a size is named, and
    // the extended call's aspect hints pass through untouched.
    [Fact]
    public void APictureIsDrawnAtItsOwnSizeUnlessOneIsNamed()
    {
        var face = new DrawingDisplay();
        var glk = Seam(face);
        var window = Open(glk, WindowType.Graphics);

        Assert.Equal(1u, Call(glk, 0x00E1,
            Held.OfOpaque(window), Held.OfWord(1), Held.OfWord(3), Held.OfWord(4)).Word);
        Assert.Equal(1u, Call(glk, 0x00E2,
            Held.OfOpaque(window), Held.OfWord(1), Held.OfWord(3), Held.OfWord(4),
            Held.OfWord(64), Held.OfWord(32)).Word);
        Assert.Equal(1u, Call(glk, 0x00EC,
            Held.OfOpaque(window), Held.OfWord(1), Held.OfWord(3), Held.OfWord(4),
            Held.OfWord(64), Held.OfWord(32), Held.OfWord(7), Held.OfWord(99)).Word);

        Assert.Equal(
            [
                "draw 1 at 3,4 640x400",
                "draw 1 at 3,4 64x32",
                "draw 1 at 3,4 64x32",
            ],
            face.Asks);
    }

    // Nothing is drawn without a window to draw in, without a picture
    // to draw, or at a display that will not draw it.
    [Fact]
    public void ThereAreThreeWaysAPictureIsNotDrawn()
    {
        var face = new DrawingDisplay();
        var glk = Seam(face);
        var window = Open(glk, WindowType.Graphics);

        Assert.Equal(0u, Call(glk, 0x00E1,
            Held.OfOpaque(null), Held.OfWord(1), Held.OfWord(0), Held.OfWord(0)).Word);
        Assert.Equal(0u, Call(glk, 0x00E1,
            Held.OfOpaque(window), Held.OfWord(9), Held.OfWord(0), Held.OfWord(0)).Word);

        face.Draws = false;

        Assert.Equal(0u, Call(glk, 0x00E1,
            Held.OfOpaque(window), Held.OfWord(1), Held.OfWord(0), Held.OfWord(0)).Word);
    }

    // The rectangles and the flow break reach the display, and the null
    // window is nothing to ask any of them about.
    [Fact]
    public void TheRectanglesAndTheBreakReachTheDisplay()
    {
        var face = new DrawingDisplay();
        var glk = Seam(face);
        var window = Open(glk, WindowType.Graphics);

        Call(glk, 0x00E8, Held.OfOpaque(window));
        Call(glk, 0x00E9, Held.OfOpaque(window),
            Held.OfWord(1), Held.OfWord(2), Held.OfWord(3), Held.OfWord(4));
        Call(glk, 0x00EA, Held.OfOpaque(window), Held.OfWord(0xFF0000),
            Held.OfWord(1), Held.OfWord(2), Held.OfWord(3), Held.OfWord(4));
        Call(glk, 0x00EB, Held.OfOpaque(window), Held.OfWord(0x00FF00));

        Assert.Equal(["break", "erase 1,2 3x4", "fill ff0000 1,2 3x4", "paper 00ff00"], face.Asks);

        face.Asks.Clear();

        Call(glk, 0x00E8, Held.OfOpaque(null));
        Call(glk, 0x00E9, Held.OfOpaque(null),
            Held.OfWord(1), Held.OfWord(2), Held.OfWord(3), Held.OfWord(4));
        Call(glk, 0x00EA, Held.OfOpaque(null), Held.OfWord(0),
            Held.OfWord(1), Held.OfWord(2), Held.OfWord(3), Held.OfWord(4));
        Call(glk, 0x00EB, Held.OfOpaque(null), Held.OfWord(0));

        Assert.Empty(face.Asks);
    }

    // A display that claims to draw and to play but overrides nothing
    // gets the seat's own answers: no picture drawn, no sound started,
    // and everything else quietly nothing.
    [Fact]
    public void TheSeatAnswersForADisplayThatOverridesNothing()
    {
        var glk = Seam(new ArtlessDisplay());
        var window = Open(glk, WindowType.Graphics);
        var channel = Call(glk, 0x00F2, Held.OfWord(0)).Opaque;

        Assert.Equal(0u, Call(glk, 0x00E1,
            Held.OfOpaque(window), Held.OfWord(1), Held.OfWord(0), Held.OfWord(0)).Word);
        Assert.Equal(0u, Call(glk, 0x00F8, Held.OfOpaque(channel), Held.OfWord(1)).Word);

        // The four that answer nothing at all still take the asking.
        Call(glk, 0x00E8, Held.OfOpaque(window));
        Call(glk, 0x00E9, Held.OfOpaque(window),
            Held.OfWord(0), Held.OfWord(0), Held.OfWord(1), Held.OfWord(1));
        Call(glk, 0x00EA, Held.OfOpaque(window), Held.OfWord(0),
            Held.OfWord(0), Held.OfWord(0), Held.OfWord(1), Held.OfWord(1));
        Call(glk, 0x00EB, Held.OfOpaque(window), Held.OfWord(0));

        // A channel that never sounded is stopped, paused and turned
        // down without the seat doing anything about it.
        Call(glk, 0x00FA, Held.OfOpaque(channel));
        Call(glk, 0x00FE, Held.OfOpaque(channel));
        Call(glk, 0x00FF, Held.OfOpaque(channel));
        Call(glk, 0x00FB, Held.OfOpaque(channel), Held.OfWord(0x8000));

        Assert.Equal(0x8000u, ((SoundChannel)channel!).Volume);
    }

    // A channel opens only where sound can play, at full volume or at
    // the volume asked for, and walks with the other opaque objects.
    [Fact]
    public void AChannelOpensOnlyWhereSoundCanPlay()
    {
        Assert.Null(Call(Seam(new NullDisplay()), 0x00F2, Held.OfWord(0)).Opaque);

        var glk = Seam(new DrawingDisplay());
        var plain = (SoundChannel)Call(glk, 0x00F2, Held.OfWord(7)).Opaque!;
        var quiet = (SoundChannel)Call(glk, 0x00F4, Held.OfWord(8), Held.OfWord(0x100)).Opaque!;

        Assert.Equal(SoundChannel.FullVolume, plain.Volume);
        Assert.Equal(7u, plain.Rock);
        Assert.Equal(0x100u, quiet.Volume);
        Assert.Equal(8u, quiet.Rock);
        Assert.Equal([quiet, plain], glk.Channels);

        // The walk, newest first, and the rock beside it.
        var rock = new Ref();

        Assert.Same(quiet, Call(glk, 0x00F0, Held.OfOpaque(null), rock).Opaque);
        Assert.Equal(8u, rock.Value.Word);
        Assert.Same(plain, Call(glk, 0x00F0, Held.OfOpaque(quiet), rock).Opaque);
        Assert.Null(Call(glk, 0x00F0, Held.OfOpaque(plain), rock).Opaque);
        Assert.Equal(7u, Call(glk, 0x00F1, Held.OfOpaque(plain)).Word);
        Assert.Equal(0u, Call(glk, 0x00F1, Held.OfOpaque(null)).Word);
    }

    // A sound plays once, or as many times as asked, and the channel
    // remembers what it is playing.
    [Fact]
    public void ASoundPlaysAndTheChannelRemembersIt()
    {
        var face = new DrawingDisplay();
        var glk = Seam(face);
        var channel = (SoundChannel)Call(glk, 0x00F2, Held.OfWord(0)).Opaque!;

        Assert.Equal(1u, Call(glk, 0x00F8, Held.OfOpaque(channel), Held.OfWord(1)).Word);
        Assert.Equal(1u, channel.Sound);
        Assert.Equal(1u, channel.Repeats);

        Assert.Equal(1u, Call(glk, 0x00F9, Held.OfOpaque(channel),
            Held.OfWord(1), Held.OfWord(3), Held.OfWord(42)).Word);
        Assert.Equal(3u, channel.Repeats);
        Assert.Equal(42u, channel.Notify);

        // The second play stopped the first: a channel sounds one thing.
        Assert.Equal(
            ["play 1 x1 notify 0", "stop", "play 1 x3 notify 42"], face.Asks);
    }

    // There are four ways a sound does not play: no channel, no
    // repeats, no such sound, and a display that will not start it.
    [Fact]
    public void ThereAreFourWaysASoundDoesNotPlay()
    {
        var face = new DrawingDisplay();
        var glk = Seam(face);
        var channel = (SoundChannel)Call(glk, 0x00F2, Held.OfWord(0)).Opaque!;

        Assert.Equal(0u, Call(glk, 0x00F8, Held.OfOpaque(null), Held.OfWord(1)).Word);
        Assert.Equal(0u, Call(glk, 0x00F9, Held.OfOpaque(channel),
            Held.OfWord(1), Held.OfWord(0), Held.OfWord(0)).Word);
        Assert.Equal(0u, Call(glk, 0x00F8, Held.OfOpaque(channel), Held.OfWord(9)).Word);

        face.Plays = false;
        face.Asks.Clear();

        // The display is asked, and declines; the channel is left as
        // silent as it was.
        Assert.Equal(0u, Call(glk, 0x00F8, Held.OfOpaque(channel), Held.OfWord(1)).Word);
        Assert.Equal(0u, channel.Sound);
        Assert.Equal(["play 1 x1 notify 0"], face.Asks);
    }

    // Several channels start together, and the count that comes back is
    // how many took. The two arrays are spent in step, so the shorter
    // one decides.
    [Fact]
    public void ChannelsStartTogetherAndTheShorterArrayDecides()
    {
        var glk = Seam(new DrawingDisplay());
        var first = Call(glk, 0x00F2, Held.OfWord(0)).Opaque;
        var second = Call(glk, 0x00F2, Held.OfWord(0)).Opaque;

        Assert.Equal(2u, Call(glk, 0x00F7,
            new[] { first, second }, new WordBuffer(1, 1), Held.OfWord(5)).Word);

        // One sound for two channels starts one of them.
        Assert.Equal(1u, Call(glk, 0x00F7,
            new[] { first, second }, new WordBuffer([1u]), Held.OfWord(0)).Word);

        // And nothing at all starts nothing.
        Assert.Equal(0u, Call(glk, 0x00F7, null, null, Held.OfWord(0)).Word);
    }

    // A sounding channel stops; a silent one was never sounding, and
    // the display is not told twice.
    [Fact]
    public void OnlyASoundingChannelIsStopped()
    {
        var face = new DrawingDisplay();
        var glk = Seam(face);
        var channel = Call(glk, 0x00F2, Held.OfWord(0)).Opaque;

        Call(glk, 0x00FA, Held.OfOpaque(channel));
        Call(glk, 0x00FA, Held.OfOpaque(null));

        Assert.Empty(face.Asks);

        Call(glk, 0x00F8, Held.OfOpaque(channel), Held.OfWord(1));
        face.Asks.Clear();
        Call(glk, 0x00FA, Held.OfOpaque(channel));
        Call(glk, 0x00FA, Held.OfOpaque(channel));

        Assert.Equal(["stop"], face.Asks);
    }

    // Pausing is a state, not an instruction: a channel already held is
    // not held again, and one already running is not resumed.
    [Fact]
    public void PausingIsAStateAndNotAnInstruction()
    {
        var face = new DrawingDisplay();
        var glk = Seam(face);
        var channel = (SoundChannel)Call(glk, 0x00F2, Held.OfWord(0)).Opaque!;

        Call(glk, 0x00FF, Held.OfOpaque(channel));
        Call(glk, 0x00FE, Held.OfOpaque(channel));
        Call(glk, 0x00FE, Held.OfOpaque(channel));
        Call(glk, 0x00FF, Held.OfOpaque(channel));
        Call(glk, 0x00FE, Held.OfOpaque(null));

        Assert.Equal(["pause", "unpause"], face.Asks);
        Assert.False(channel.Paused);
    }

    // The volume is set at once or faded to, and the extended form can
    // ask to be told when the fade is done.
    [Fact]
    public void TheVolumeIsSetOrFadedAndMaySaySoWhenItIsDone()
    {
        var face = new DrawingDisplay();
        var glk = Seam(face);
        var channel = (SoundChannel)Call(glk, 0x00F2, Held.OfWord(0)).Opaque!;

        Call(glk, 0x00FB, Held.OfOpaque(channel), Held.OfWord(0x8000));

        Assert.Equal(0x8000u, channel.Volume);
        Assert.Empty(glk.PendingEvents);

        Call(glk, 0x00FD, Held.OfOpaque(channel),
            Held.OfWord(0x4000), Held.OfWord(500), Held.OfWord(0));

        Assert.Empty(glk.PendingEvents);

        Call(glk, 0x00FD, Held.OfOpaque(channel),
            Held.OfWord(0x2000), Held.OfWord(500), Held.OfWord(9));

        var told = Assert.Single(glk.PendingEvents);

        Assert.Equal(EventType.VolumeNotify, told.Kind);
        Assert.Equal(9u, told.Val2);
        Assert.Equal(["volume 32768 over 0", "volume 16384 over 500", "volume 8192 over 500"], face.Asks);

        // The null channel is nothing to turn up.
        Call(glk, 0x00FB, Held.OfOpaque(null), Held.OfWord(0));
    }

    // Destroying a channel silences it, drops it from the live list and
    // buries it; the null channel is nothing to destroy.
    [Fact]
    public void DestroyingAChannelSilencesAndBuriesIt()
    {
        var face = new DrawingDisplay();
        var glk = Seam(face);
        var channel = (SoundChannel)Call(glk, 0x00F2, Held.OfWord(0)).Opaque!;

        Call(glk, 0x00F8, Held.OfOpaque(channel), Held.OfWord(1));
        face.Asks.Clear();
        Call(glk, 0x00F3, Held.OfOpaque(channel));

        Assert.Equal(["stop"], face.Asks);
        Assert.Empty(glk.Channels);
        Assert.True(channel.Disposed);

        Call(glk, 0x00F3, Held.OfOpaque(null));
    }

    // A display that starts a sound but has nothing to do to stop one
    // is answered for by the seat, and the channel falls silent all the
    // same.
    [Fact]
    public void ADisplayThatOnlyStartsSoundsIsAnsweredForByTheSeat()
    {
        var glk = Seam(new EagerDisplay());
        var channel = (SoundChannel)Call(glk, 0x00F2, Held.OfWord(0)).Opaque!;

        Assert.Equal(1u, Call(glk, 0x00F8, Held.OfOpaque(channel), Held.OfWord(1)).Word);
        Assert.Equal(1u, channel.Sound);

        Call(glk, 0x00FA, Held.OfOpaque(channel));

        Assert.Equal(0u, channel.Sound);
    }

    // The load hint is advisory, and advising is all it does.
    [Fact]
    public void TheLoadHintIsAdvisoryOnly()
    {
        var glk = Seam(new DrawingDisplay());

        Assert.Equal(default, Call(glk, 0x00FC, Held.OfWord(1), Held.OfWord(1)));
    }

    // A resource stream reads a data chunk: as bytes, as UTF-8 where
    // the chunk is text, and as four-byte words where it is not.
    [Fact]
    public void AResourceStreamReadsADataChunkThreeWays()
    {
        var glk = Seam(new NullDisplay());

        // Latin-1 bytes, one character at a time.
        var bytes = (StreamObject)Call(glk, 0x0049, Held.OfWord(1), Held.OfWord(0)).Opaque!;

        Assert.Equal((uint)'h', bytes.GetChar());
        Assert.Same(bytes, glk.Streams[0]);

        // The same chunk as Unicode: text means UTF-8.
        var text = (StreamObject)Call(glk, 0x013A, Held.OfWord(1), Held.OfWord(0)).Opaque!;

        Assert.Equal((uint)'h', text.GetChar());

        // A binary chunk as Unicode is four-byte words.
        var words = (StreamObject)Call(glk, 0x013A, Held.OfWord(2), Held.OfWord(0)).Opaque!;

        Assert.Equal(0x41u, words.GetChar());

        // And a number no resource answers opens nothing.
        Assert.Null(Call(glk, 0x0049, Held.OfWord(9), Held.OfWord(0)).Opaque);
        Assert.Null(Call(glk, 0x013A, Held.OfWord(9), Held.OfWord(0)).Opaque);
    }

    /// <summary>Open a window of a type as the root of the tree.</summary>
    private static Window Open(Api glk, uint wtype) => (Window)Call(
        glk, 0x0023, Held.OfOpaque(null), Held.OfWord(0), Held.OfWord(0),
        Held.OfWord(wtype), Held.OfWord(0)).Opaque!;

    /// <summary>Reach one function the way the bridge would.</summary>
    private static Held Call(Api glk, int selector, params object?[] args) =>
        glk.Call(Signatures.Lookup(selector)!, args);

    /// <summary>
    /// A library over a Blorb carrying one picture, one sound, and two
    /// data chunks: one text, one binary.
    /// </summary>
    private static Api Seam(GlkDisplay display)
    {
        var index = new List<byte>(Word(4));
        var body = new List<byte>();
        var at = 12 + 8 + 4 + (12 * 4);

        foreach (var (usage, number, id, payload) in Pieces())
        {
            index.AddRange(Encoding.ASCII.GetBytes(usage));
            index.AddRange(Word(number));
            index.AddRange(Word(at));

            var chunk = Chunk(id, payload);

            body.AddRange(chunk);
            at += chunk.Length;
        }

        var whole = new List<byte>(Encoding.ASCII.GetBytes("IFRS"));

        whole.AddRange(Chunk("RIdx", [.. index]));
        whole.AddRange(body);

        return new Api(display, resources: new GlkResources(Blorb.Load(Chunk("FORM", [.. whole]))));
    }

    private static (string Usage, int Number, string Id, byte[] Payload)[] Pieces()
    {
        var png = new List<byte> { 0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A };

        png.AddRange([0, 0, 0, 13]);
        png.AddRange(Encoding.ASCII.GetBytes("IHDR"));
        png.AddRange(Word(640));
        png.AddRange(Word(400));

        return
        [
            ("Pict", 1, "PNG ", [.. png]),
            ("Snd ", 1, "OGGV", Encoding.ASCII.GetBytes("ogg")),
            ("Data", 1, "TEXT", Encoding.ASCII.GetBytes("hello")),
            ("Data", 2, "BINA", [0, 0, 0, 0x41]),
        ];
    }

    private static byte[] Word(int value) =>
        [(byte)(value >> 24), (byte)(value >> 16), (byte)(value >> 8), (byte)value];

    private static byte[] Chunk(string id, byte[] payload)
    {
        var bytes = new List<byte>(Encoding.ASCII.GetBytes(id));

        bytes.AddRange(Word(payload.Length));
        bytes.AddRange(payload);

        if (payload.Length % 2 != 0)
        {
            bytes.Add(0);
        }

        return [.. bytes];
    }
}
