using Voxam.Core.Glulx;
namespace Voxam.Tests.Glulx;

/// <summary>
/// Assembles a tiny Glulx image from the numbers its header
/// declares: the boundaries land where a test asks for them, the
/// file comes out as long as the EXTSTART it names, and the checksum
/// is summed last, so a story built here verifies.
/// </summary>
public sealed class GlulxBuilder
{
    private const int MagicAt = 0;
    private const int ChecksumAt = 32;
    private const int WordSize = 4;

    private readonly List<(int At, byte[] Data)> _laid = [];

    /// <summary>The packed version word: 3.1.2 unless a test asks otherwise.</summary>
    public uint Version { get; set; } = 0x00030102;

    public uint RamStart { get; set; } = 256;
    public uint ExtStart { get; set; } = 512;
    public uint EndMem { get; set; } = 1024;
    public uint StackSize { get; set; } = 1024;
    public uint StartFunction { get; set; } = 256;
    public uint DecodingTable { get; set; }

    /// <summary>How long the built file is: the EXTSTART it declares unless a test says otherwise.</summary>
    public int? Length { get; set; }

    /// <summary>Lay bytes into the stored image at an address.</summary>
    public GlulxBuilder Lay(int at, params byte[] data)
    {
        _laid.Add((at, data));

        return this;
    }

    /// <summary>The image, header first and checksum last.</summary>
    public byte[] Build()
    {
        var image = new byte[Length ?? (int)ExtStart];
        "Glul"u8.CopyTo(image.AsSpan(MagicAt));
        Put(image, 4, Version);
        Put(image, 8, RamStart);
        Put(image, 12, ExtStart);
        Put(image, 16, EndMem);
        Put(image, 20, StackSize);
        Put(image, 24, StartFunction);
        Put(image, 28, DecodingTable);

        foreach (var (at, data) in _laid)
        {
            data.CopyTo(image, at);
        }

        Put(image, ChecksumAt, Summed(image));

        return image;
    }

    // The sum an interpreter computes: every word but the checksum's
    // own seat (Glulx: The Header).
    private static uint Summed(byte[] image)
    {
        var total = 0u;

        for (var at = 0; at + WordSize <= image.Length; at += WordSize)
        {
            if (at != ChecksumAt)
            {
                total += ((uint)image[at] << 24) | ((uint)image[at + 1] << 16) | ((uint)image[at + 2] << 8) | image[at + 3];
            }
        }

        return total;
    }

    private static void Put(byte[] image, int at, uint value)
    {
        image[at] = (byte)(value >> 24);
        image[at + 1] = (byte)(value >> 16);
        image[at + 2] = (byte)(value >> 8);
        image[at + 3] = (byte)value;
    }
}
