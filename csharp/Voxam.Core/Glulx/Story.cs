namespace Voxam.Core.Glulx;

/// <summary>
/// A Glulx story file held in memory, its header promises kept.
///
/// The header is the first 36 bytes: nine big-endian 32-bit words,
/// opening with the magic 'Glul'. It lives in ROM, so everything in
/// it is fixed for the story's whole life, which is why loading is
/// the right moment to hold the file to all of the header's
/// promises: the version window, the 256-byte alignment of every
/// memory boundary, and the file's own declared length (Glulx: The
/// Header).
/// </summary>
public sealed class Story
{
    // Nine 32-bit words (Glulx: The Header).
    private const int HeaderSize = 36;
    private const int VersionAt = 4;
    private const int RamStartAt = 8;
    private const int ExtStartAt = 12;
    private const int EndMemAt = 16;
    private const int StackSizeAt = 20;
    private const int StartFunctionAt = 24;
    private const int DecodingTableAt = 28;
    private const int ChecksumAt = 32;
    private const int WordSize = 4;

    // An interpreter written to specification 3.1.3 accepts game
    // files from 2.0.0 through 3.1.*: minor versions are backwards
    // compatible, subminor versions do not matter, and 2.0 differs
    // from 3.0 only in lacking Unicode (Glulx: The Header).
    private const uint VersionFloor = 0x00020000;
    private const uint VersionCeiling = 0x000301FF;

    // The version word packs major.minor.subminor as 16, 8 and 8
    // bits (Glulx: The Header).
    private const int MajorShift = 16;
    private const int MinorShift = 8;
    private const uint ByteMask = 0xFF;

    // RAMSTART, EXTSTART, ENDMEM and the stack size all sit on
    // 256-byte boundaries, and ROM is at least that big so the
    // header fits inside it (Glulx: The Header, Glulx: The Stack).
    private const uint Boundary = 256;

    // The largest 256-byte boundary a map can reach here. The spec
    // sets no such limit, since addresses are 32 bits and the
    // reference glulxe simply fails to allocate; this machine says
    // so in words instead.
    private const uint Ceiling = 0x7FFFFF00;

    /// <summary>
    /// The raw bytes of the game file: the initial memory image from
    /// 0 to EXTSTART (Glulx: The Header).
    /// </summary>
    public byte[] Data { get; }

    /// <summary>The declared Glulx version, dotted: 3.1.2 and kin.</summary>
    public string Version { get; }

    /// <summary>The first address the program can write to.</summary>
    public int RamStart { get; }

    /// <summary>The end of stored initial memory: the game file's length.</summary>
    public int ExtStart { get; }

    /// <summary>The end of the memory map; above EXTSTART starts zeroed.</summary>
    public int EndMem { get; }

    /// <summary>The stack the program needs, in bytes.</summary>
    public int StackSize { get; }

    /// <summary>The function execution will commence by calling.</summary>
    public int StartFunction { get; }

    /// <summary>The string-decoding table's address; 0 means none.</summary>
    public int DecodingTable { get; }

    /// <summary>The checksum word the compiler stored.</summary>
    public uint StoredChecksum { get; }

    /// <summary>
    /// Hold a file to every promise its header makes.
    /// </summary>
    /// <exception cref="GlulxException">
    /// For a file too short for a header, the wrong magic, a version
    /// outside the accepted window, a misaligned memory boundary,
    /// boundaries out of order, or a file whose length is not the
    /// EXTSTART it declares.
    /// </exception>
    public Story(byte[] data)
    {
        if (data.Length < HeaderSize)
        {
            throw new GlulxException($"a Glulx story opens with a {HeaderSize}-byte header, but only {data.Length} bytes are present (Glulx: The Header)");
        }

        if (!IsGlulx(data))
        {
            throw new GlulxException("the file does not open with the magic number 'Glul' (Glulx: The Header)");
        }

        Data = data;
        var version = Word(VersionAt);

        if (version < VersionFloor || version > VersionCeiling)
        {
            throw new GlulxException($"the story declares Glulx version {Dotted(version)}, but an interpreter written to 3.1.3 accepts 2.0.0 through 3.1.* (Glulx: The Header)");
        }

        Version = Dotted(version);
        RamStart = Mapped("RAMSTART", RamStartAt);
        ExtStart = Mapped("EXTSTART", ExtStartAt);
        EndMem = Mapped("ENDMEM", EndMemAt);
        StackSize = Mapped("the stack size", StackSizeAt);

        if (RamStart < Boundary || RamStart > ExtStart || ExtStart > EndMem)
        {
            throw new GlulxException($"the memory map is out of order: ROM holds the header so RAMSTART is at least {Boundary}, and RAMSTART ({RamStart}) precedes EXTSTART ({ExtStart}) precedes ENDMEM ({EndMem}) (Glulx: The Header)");
        }

        if (data.Length != ExtStart)
        {
            throw new GlulxException($"the file is {data.Length} bytes, but its header declares EXTSTART {ExtStart}, the length of the stored initial memory (Glulx: The Header)");
        }

        StartFunction = (int)Word(StartFunctionAt);
        DecodingTable = (int)Word(DecodingTableAt);
        StoredChecksum = Word(ChecksumAt);
    }

    /// <summary>Whether a file's magic word says it is a Glulx story (Glulx: The Header).</summary>
    public static bool IsGlulx(byte[] data) => data.AsSpan().StartsWith("Glul"u8);

    /// <summary>
    /// The checksum as an interpreter computes it: a simple sum of
    /// the entire initial contents of memory as big-endian 32-bit
    /// words, with the checksum field itself counted as zero (Glulx:
    /// The Header). EXTSTART sits on a 256-byte boundary and the file
    /// is exactly that long, so no partial word can end the sum.
    /// </summary>
    public uint ComputedChecksum
    {
        get
        {
            var total = 0u;

            for (var at = 0; at < Data.Length; at += WordSize)
            {
                if (at != ChecksumAt)
                {
                    total += Word(at);
                }
            }

            return total;
        }
    }

    /// <summary>Whether the stored and computed checksums agree.</summary>
    public bool Verify() => StoredChecksum == ComputedChecksum;

    // A boundary the header names: on its 256-byte seat, and inside
    // what a map here can reach.
    private int Mapped(string name, int at)
    {
        var value = Word(at);

        if (value % Boundary != 0)
        {
            throw new GlulxException($"{name} is {value}, which is not a multiple of {Boundary} (Glulx: The Header)");
        }

        if (value > Ceiling)
        {
            throw new GlulxException($"{name} is {value}, larger than this machine can map (Glulx: The Header)");
        }

        return (int)value;
    }

    private uint Word(int at) => ((uint)Data[at] << 24) | ((uint)Data[at + 1] << 16) | ((uint)Data[at + 2] << 8) | Data[at + 3];

    private static string Dotted(uint version) => $"{version >> MajorShift}.{(version >> MinorShift) & ByteMask}.{version & ByteMask}";
}
