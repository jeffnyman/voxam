using System.Buffers.Binary;
using System.Security.Cryptography;

namespace Voxam.Core.Glulx;

/// <summary>
/// The random number generator behind the random opcode.
///
/// The stream is a xorshift32 owned here rather than the platform's
/// own, for the same reason as the Z-machine's dice: a seed must
/// produce the same session forever, because recorded playthroughs
/// must never be invalidated by an interpreter upgrade. Glulx asks
/// less of its generator than the Z-machine does, there being no
/// rising-sequence testing mode, so this is the plain stream: full
/// words, and ranges folded from them (Glulx: The Random Number
/// Generator).
///
/// The generator is deliberately not part of saved state, and a
/// restart leaves it alone (Glulx: Game State).
/// </summary>
public sealed class Randomizer
{
    private const int ShiftA = 13;
    private const int ShiftB = 17;
    private const int ShiftC = 5;
    private const uint MixIncrement = 0x9E3779B9;
    private const uint MixMultiplier1 = 0x85EBCA6B;
    private const uint MixMultiplier2 = 0xC2B2AE35;

    // Whether the operator asked for a reproducible session, which
    // is what decides where a later reseed-to-entropy draws its
    // state from. See Seed.
    private readonly bool _seeded;
    private uint _state;

    /// <summary>Start seeded for a session, or from true entropy where no seed is given.</summary>
    public Randomizer(int? seed = null)
    {
        _seeded = seed is not null;
        _state = seed is null ? Entropy() : Mixed((uint)seed.Value);
    }

    /// <summary>The next full 32-bit value off the stream.</summary>
    public uint Word()
    {
        var state = _state;
        state ^= state << ShiftA;
        state ^= state >> ShiftB;
        state ^= state << ShiftC;
        _state = state;

        return state;
    }

    /// <summary>
    /// A value in 0 through limit - 1, folded from the stream.
    /// Folding by modulo skews the distribution by well under one
    /// part in a million for any range a game's dice could ask, far
    /// below anything observable.
    /// </summary>
    public uint Below(uint limit) => Word() % limit;

    /// <summary>
    /// Reseed the stream: setrandom's work. A seed of zero asks for
    /// genuine unpredictability (Glulx: The Random Number Generator),
    /// and gets it in an ordinary session.
    ///
    /// In a session the operator seeded, it draws its new state off
    /// the seeded stream instead. This is a deliberate deviation, and
    /// a narrow one: the seed flag already overrides the same rule at
    /// game start, where the generator is likewise meant to be
    /// unpredictable, so honoring it here only makes it mean at turn
    /// five hundred what it meant at turn one. Without it a story that
    /// reseeds silently breaks the flag's whole promise, and no
    /// recording that reaches such a story could ever replay.
    /// </summary>
    public void Seed(uint value)
    {
        if (value != 0)
        {
            _state = Mixed(value);
        }
        else if (_seeded)
        {
            // Off the stream itself: no counter to keep, successive
            // reseeds still differ, and the whole run stays a
            // function of the one seed the operator gave.
            _state = Mixed(Word());
        }
        else
        {
            _state = Entropy();
        }
    }

    // Spread a seed over the state space, never yielding zero: a
    // xorshift state of zero is a fixed point, and small seeds used
    // raw would start the stream in a correlated corner.
    private static uint Mixed(uint value)
    {
        value += MixIncrement;
        value ^= value >> 16;
        value *= MixMultiplier1;
        value ^= value >> 13;
        value *= MixMultiplier2;
        value ^= value >> 16;

        return value == 0 ? MixIncrement : value;
    }

    // A fresh state from the operating system's entropy.
    private static uint Entropy() => Mixed(BinaryPrimitives.ReadUInt32BigEndian(RandomNumberGenerator.GetBytes(4)));
}
