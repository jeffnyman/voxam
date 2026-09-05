namespace Voxam.Core.Glulx.Glk;

/// <summary>
/// Sound channels: creating them, playing on them, and turning them
/// down (Glk: Sound).
/// </summary>
public sealed partial class Api
{
    /// <summary>Every live sound channel, newest first.</summary>
    public List<SoundChannel> Channels { get; } = [];

    private void ServeSound()
    {
        // Walk the live sound channels (Glk: Iterating Through Opaque
        // Objects).
        Serve(0x00F0, args => Held.OfOpaque(Iterate(Channels, Chan(args[0]), Holder(args[1]))));

        // The rock the channel was created with (Glk: Rocks).
        Serve(0x00F1, args => Held.OfWord(Chan(args[0])?.Rock ?? 0));

        // Create a channel at full volume, or at the volume asked for.
        Serve(0x00F2, args => Held.OfOpaque(Create(SoundChannel.FullVolume, Word(args[0]))));
        Serve(0x00F4, args => Held.OfOpaque(Create(Word(args[1]), Word(args[0]))));

        // Stop and drop a channel.
        Serve(0x00F3, args =>
        {
            var channel = Chan(args[0]);

            if (channel is not null)
            {
                Stop(channel);
                Channels.Remove(channel);
                Dispose(channel);
            }

            return default;
        });

        // Play a sound once, or repeatedly (Glk: Playing Sounds).
        Serve(0x00F8, args => Held.OfWord(Play(Chan(args[0]), Word(args[1]), 1, 0)));
        Serve(0x00F9, args =>
            Held.OfWord(Play(Chan(args[0]), Word(args[1]), Word(args[2]), Word(args[3]))));

        // Start channels together; answer how many took.
        Serve(0x00F7, args =>
        {
            var channels = (GlkObject?[]?)args[0] ?? [];
            var sounds = Buf(args[1]);
            var notify = Word(args[2]);
            var started = 0u;
            var count = Math.Min(channels.Length, sounds?.Length ?? 0);

            for (var at = 0; at < count; at++)
            {
                started += Play(channels[at] as SoundChannel, sounds![at], 1, notify);
            }

            return Held.OfWord(started);
        });

        // Silence a channel (Glk: Playing Sounds).
        Serve(0x00FA, args =>
        {
            if (Chan(args[0]) is { } channel)
            {
                Stop(channel);
            }

            return default;
        });

        // Hold a channel where it is, and let a held one continue.
        Serve(0x00FE, args => Paused(Chan(args[0]), true));
        Serve(0x00FF, args => Paused(Chan(args[0]), false));

        // Set a channel's volume, at once or over a fade (Glk: Other
        // Sound Channel Functions).
        Serve(0x00FB, args => Volume(Chan(args[0]), Word(args[1]), 0, 0));
        Serve(0x00FD, args =>
            Volume(Chan(args[0]), Word(args[1]), Word(args[2]), Word(args[3])));

        // Advisory only: a sound is, or is not, about to be used.
        Serve(0x00FC, _ => default);
    }

    /// <summary>
    /// Create a channel, or nothing where sound cannot play (Glk:
    /// Creating and Destroying Sound Channels).
    /// </summary>
    private SoundChannel? Create(uint volume, uint rock)
    {
        if (!Display.Sound)
        {
            return null;
        }

        var channel = new SoundChannel(volume, rock);

        Channels.Insert(0, channel);

        return channel;
    }

    /// <summary>
    /// Play a sound repeatedly; answer whether it took (Glk: Playing
    /// Sounds).
    /// </summary>
    private uint Play(SoundChannel? channel, uint sound, uint repeats, uint notify)
    {
        if (channel is null)
        {
            return 0;
        }

        Stop(channel);

        // Zero repeats is a legal way to say "stop and play nothing"
        // (Glk: Playing Sounds).
        if (repeats == 0 || Resources.Audio((int)sound) is null)
        {
            return 0;
        }

        if (!Display.PlaySound(channel, sound, repeats, notify))
        {
            return 0;
        }

        channel.Sound = sound;
        channel.Repeats = repeats;
        channel.Notify = notify;
        channel.Paused = false;

        return 1;
    }

    /// <summary>Silence a channel that is sounding.</summary>
    private void Stop(SoundChannel channel)
    {
        if (channel.Sound == 0)
        {
            return;
        }

        Display.StopSound(channel);

        channel.Sound = 0;
        channel.Paused = false;
    }

    /// <summary>Hold a channel, or let a held one continue.</summary>
    private Held Paused(SoundChannel? channel, bool paused)
    {
        if (channel is not null && channel.Paused != paused)
        {
            channel.Paused = paused;

            Display.PauseSound(channel, paused);
        }

        return default;
    }

    /// <summary>
    /// Set a channel's volume, with an optional fade and a completion
    /// event (Glk: Other Sound Channel Functions).
    /// </summary>
    private Held Volume(SoundChannel? channel, uint volume, uint duration, uint notify)
    {
        if (channel is null)
        {
            return default;
        }

        channel.Volume = volume;

        Display.SetVolume(channel, volume, duration);

        if (notify != 0)
        {
            PostEvent(new GlkEvent(EventType.VolumeNotify, null, 0, notify));
        }

        return default;
    }

    private static SoundChannel? Chan(object? arg) => ((Held)arg!).Opaque as SoundChannel;
}
