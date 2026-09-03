using System.Buffers.Binary;
using System.Security.Cryptography;

namespace Voxam.Core;

/// <summary>
/// The two-state generator behind the random opcode (§2.4), ported
/// exactly from the Python reference: a xorshift32 the interpreter
/// owns, so that a seed produces the same session forever.
/// </summary>
public sealed class Randomizer
{
    private const int SequenceSeedLimit = 1000;
    private const uint MixIncrement = 0x9E3779B9;
    private const uint MixMultiplier1 = 0x85EBCA6B;
    private const uint MixMultiplier2 = 0xC2B2AE35;

    private readonly bool _seeded;
    private uint _state;
    private int _sequenceLimit;
    private int _sequenceAt;

    public Randomizer(int? seed)
    {
        _seeded = seed.HasValue;
        _state = seed.HasValue ? Mixed((uint)seed.Value) : Entropy();
    }

    /// <summary>A value from 1 to limit (§2.4.1).</summary>
    public int Roll(int limit)
    {
        if (_sequenceLimit != 0)
        {
            _sequenceAt = _sequenceAt % _sequenceLimit + 1;
            return (_sequenceAt - 1) % limit + 1;
        }

        return (int)(Next() % (uint)limit) + 1;
    }

    /// <summary>Switch to the predictable state with a seed (§2.4.2).</summary>
    public void Seed(int value)
    {
        if (value < SequenceSeedLimit)
        {
            _sequenceLimit = value;
            _sequenceAt = 0;
        }
        else
        {
            _sequenceLimit = 0;
            _state = Mixed((uint)value);
        }
    }

    /// <summary>
    /// Return to the random state. In a seeded session the new state
    /// comes off the seeded stream, so the whole run stays a function
    /// of the one seed the operator gave.
    /// </summary>
    public void Randomize()
    {
        _sequenceLimit = 0;
        _state = _seeded ? Mixed(Next()) : Entropy();
    }

    private uint Next()
    {
        var state = _state;
        state ^= state << 13;
        state ^= state >> 17;
        state ^= state << 5;
        _state = state;
        return state;
    }

    private static uint Mixed(uint value)
    {
        value += MixIncrement;
        value ^= value >> 16;
        value *= MixMultiplier1;
        value ^= value >> 13;
        value *= MixMultiplier2;
        value ^= value >> 16;
        return value != 0 ? value : MixIncrement;
    }

    private static uint Entropy() =>
        Mixed(BinaryPrimitives.ReadUInt32BigEndian(RandomNumberGenerator.GetBytes(4)));
}
