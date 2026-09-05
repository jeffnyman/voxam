using Voxam.Core.Glulx.Glk;

namespace Voxam.Tests.Glulx.Glk;

/// <summary>
/// A character array standing in for the live view onto VM memory the
/// bridge era will hand the library.
/// </summary>
internal sealed class WordBuffer : IBuffer
{
    private readonly uint[] _values;

    public WordBuffer(int length) => _values = new uint[length];

    public WordBuffer(params uint[] values) => _values = values;

    public int Length => _values.Length;

    public uint this[int index]
    {
        get => _values[index];
        set => _values[index] = value;
    }

    public uint[] Snapshot() => [.. _values];
}

/// <summary>
/// A stream that overrides nothing, so the base's own placing and
/// fetching are what answer. Glk has no such stream; the base exists to
/// hold the counting rules the four real kinds share, and this is how
/// those rules are reached on their own.
/// </summary>
internal sealed class BareStream : StreamObject
{
    public BareStream(bool readable = true, bool writable = true, bool unicode = true)
        : base(0, readable, writable, unicode)
    {
    }
}

/// <summary>
/// An opaque object of no particular class, for the base's own answers.
/// </summary>
internal sealed class NamelessObject : GlkObject
{
    public NamelessObject(uint rock = 0)
        : base(rock)
    {
    }

    public void Bury() => Disposed = true;
}
