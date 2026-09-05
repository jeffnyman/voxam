using Voxam.Core.Glulx.Glk;

namespace Voxam.Tests.Glulx.Glk;

/// <summary>
/// The opaque base and the two simplest classes standing on it, plus
/// the four fields an event answers with.
/// </summary>
public sealed class ObjectsTests
{
    // The rock is the game's own filing, kept exactly as handed over.
    [Fact]
    public void AnObjectKeepsTheRockItWasFiledUnder()
    {
        Assert.Equal(0xCAFEF00Du, new NamelessObject(0xCAFEF00D).Rock);
        Assert.Equal(0u, new NamelessObject().Rock);
    }

    // The base answers with a class number no real class uses, so a
    // registry asked about something outside the four gets an answer it
    // cannot mistake for one of them.
    [Fact]
    public void TheBaseNamesNoClassOfItsOwn() =>
        Assert.Equal(-1, new NamelessObject().GlkClass);

    // The four opaque classes number themselves the way the dispatch
    // layer counts them (Glk: Opaque Objects).
    [Fact]
    public void TheFourClassesNumberThemselvesAsDispatchDoes()
    {
        var window = new BlankWindow();

        Assert.Equal(0, window.GlkClass);
        Assert.Equal(1, window.Stream.GlkClass);
        Assert.Equal(2, new FileRef("save.glksave", FileUsage.SavedGame).GlkClass);
        Assert.Equal(3, new SoundChannel().GlkClass);
    }

    // An object stands until something buries it; the flag is what lets
    // a stale reference fault loudly rather than operate on a corpse.
    [Fact]
    public void AnObjectStandsUntilItIsBuried()
    {
        var held = new NamelessObject();

        Assert.False(held.Disposed);

        held.Bury();

        Assert.True(held.Disposed);
    }

    // The usage word carries both what the file is for and how it
    // opens, and the reference keeps them apart.
    [Fact]
    public void AFileReferenceSplitsItsUsageWord()
    {
        var reference = new FileRef(
            "notes.txt", FileUsage.Transcript | FileUsage.TextMode, rock: 12);

        Assert.Equal("notes.txt", reference.Filename);
        Assert.Equal(FileUsage.Transcript, reference.Usage);
        Assert.True(reference.TextMode);
        Assert.False(reference.Temporary);
        Assert.Equal(12u, reference.Rock);
    }

    // Binary mode shares the value zero with data, so a plain usage
    // leaves the text flag down.
    [Fact]
    public void APlainUsageOpensBinary()
    {
        var reference = new FileRef("blob", FileUsage.Data, temporary: true);

        Assert.Equal(FileUsage.Data, reference.Usage);
        Assert.False(reference.TextMode);
        Assert.True(reference.Temporary);
    }

    // A channel opens silent at full volume, which is what a game that
    // never sets one should hear (Glk: Sound).
    [Fact]
    public void ASoundChannelOpensSilentAtFullVolume()
    {
        var channel = new SoundChannel();

        Assert.Equal(SoundChannel.FullVolume, channel.Volume);
        Assert.Equal(0u, channel.Sound);
        Assert.Equal(0u, channel.Repeats);
        Assert.Equal(0u, channel.Notify);
        Assert.False(channel.Paused);
    }

    // Everything a play sets is the channel's to carry.
    [Fact]
    public void ASoundChannelCarriesWhatAPlaySets()
    {
        var channel = new SoundChannel(volume: 0x8000, rock: 4)
        {
            Sound = 17,
            Repeats = 2,
            Notify = 99,
            Paused = true,
        };

        Assert.Equal(0x8000u, channel.Volume);
        Assert.Equal(4u, channel.Rock);
        Assert.Equal(17u, channel.Sound);
        Assert.Equal(2u, channel.Repeats);
        Assert.Equal(99u, channel.Notify);
        Assert.True(channel.Paused);
    }

    // An event with nothing set is "nothing happened", which is what a
    // poll usually finds.
    [Fact]
    public void AnEventDefaultsToNothingHavingHappened()
    {
        var nothing = new GlkEvent();

        Assert.Equal(EventType.None, nothing.Kind);
        Assert.Null(nothing.Window);
        Assert.Equal(0u, nothing.Val1);
        Assert.Equal(0u, nothing.Val2);
    }

    // The four fields come back in event_t order, the window still an
    // object rather than an id.
    [Fact]
    public void AnEventAnswersItsFourFieldsInOrder()
    {
        var window = new TextBufferWindow();
        var arrived = new GlkEvent(EventType.LineInput, window, 5, 0);

        var (kind, named, val1, val2) = arrived.AsFields();

        Assert.Equal(EventType.LineInput, kind);
        Assert.Same(window, named);
        Assert.Equal(5u, val1);
        Assert.Equal(0u, val2);
    }
}
