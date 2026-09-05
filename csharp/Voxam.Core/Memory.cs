namespace Voxam.Core;

/// <summary>
/// Anything a story or the machine running it did that the rules
/// refuse (the Python VoxamError). The two machines raise their own
/// kinds; what catches a session's refusals catches this.
/// </summary>
public class VoxamException(string message) : Exception(message);

/// <summary>A rule a Z-code story or the machine running it broke.</summary>
public class ZMachineException(string message) : VoxamException(message);

/// <summary>A rule a Glulx story or the machine running it broke.</summary>
public class GlulxException(string message) : VoxamException(message);

/// <summary>The input source ran dry: the session ends there, as at end of input.</summary>
public sealed class EndOfInputException() : Exception("end of input");

/// <summary>
/// The session is over, thrown by glk_exit: a game that calls exit is
/// finished, and the throw is how the news travels up out of a Glk call
/// that may be nested deep inside the machine (Glk: Your Program's Main
/// Function).
///
/// The reference deliberately declines to name this one as an error,
/// because it is not one. Here it wears the suffix anyway, the
/// analyzers holding every throwable to the same ending.
/// </summary>
public sealed class SessionEndException() : Exception("the session has ended");

/// <summary>Header field offsets (§11.1).</summary>
public static class Header
{
    public const int Version = 0x00;
    public const int Flags1 = 0x01;
    public const int Release = 0x02;
    public const int HighBase = 0x04;
    public const int InitialPc = 0x06;
    public const int Dictionary = 0x08;
    public const int ObjectTable = 0x0A;
    public const int Globals = 0x0C;
    public const int StaticBase = 0x0E;
    public const int Flags2 = 0x10;
    public const int Serial = 0x12;
    public const int Abbreviations = 0x18;
    public const int FileLength = 0x1A;
    public const int Checksum = 0x1C;
    public const int Interpreter = 0x1E;
    public const int InterpreterVersion = 0x1F;
    public const int ScreenLines = 0x20;
    public const int ScreenColumns = 0x21;
    public const int ScreenWidthUnits = 0x22;
    public const int ScreenHeightUnits = 0x24;
    public const int FontWidth = 0x26;
    public const int FontHeight = 0x27;
    public const int RoutinesOffset = 0x28;
    public const int StringsOffset = 0x2A;
    public const int DefaultBackground = 0x2C;
    public const int DefaultForeground = 0x2D;
    public const int TotalWidth = 0x30;
    public const int StandardMajor = 0x32;
    public const int StandardMinor = 0x33;
    public const int AlphabetTable = 0x34;
    public const int Extension = 0x36;
    public const int Size = 64;
}

/// <summary>
/// The mutable working image of a story, with the §1.1 access rules.
/// The pristine file is kept beside it for restart and verify.
/// </summary>
public sealed class Memory
{
    private readonly byte[] _data;
    private readonly int _readLimit;

    public byte[] Pristine { get; }
    public int Version { get; }
    public int StaticBase { get; }
    public int Length => _data.Length;

    public Memory(byte[] story)
    {
        if (story.Length < Header.Size)
        {
            throw new ZMachineException(
                $"story file is {story.Length} bytes, but the header alone requires {Header.Size} (§1.1.1.1)");
        }

        Version = story[0];

        if (Version is < 1 or > 8)
        {
            throw new ZMachineException(
                $"story file declares version {Version}, but only versions 1 to 8 exist (§11.1)");
        }

        Pristine = story;
        _data = (byte[])story.Clone();
        StaticBase = (story[Header.StaticBase] << 8) | story[Header.StaticBase + 1];
        var highBase = (story[Header.HighBase] << 8) | story[Header.HighBase + 1];
        var maximum = Version switch { <= 3 => 128 * 1024, <= 5 => 256 * 1024, _ => 512 * 1024 };

        if (story.Length > maximum)
        {
            throw new ZMachineException(
                $"story file is {story.Length} bytes, but version {Version} allows at most {maximum} (§1.1.4)");
        }

        if (StaticBase < Header.Size)
        {
            throw new ZMachineException(
                $"static memory begins at ${StaticBase:x4}, which would leave dynamic memory smaller than the {Header.Size}-byte header (§1.1.1)");
        }

        if (StaticBase > story.Length)
        {
            throw new ZMachineException(
                $"static memory begins at ${StaticBase:x4}, beyond the end of the {story.Length}-byte file (§1.1)");
        }

        if (highBase < StaticBase)
        {
            throw new ZMachineException(
                $"high memory begins at ${highBase:x4}, inside dynamic memory, which runs up to ${StaticBase:x4} (§1.1.3)");
        }

        _readLimit = Math.Min(story.Length, 0x10000);
    }

    public int ReadByte(int address)
    {
        RequireReadable(address);
        return _data[address];
    }

    public int ReadWord(int address)
    {
        RequireReadable(address);
        RequireReadable(address + 1);
        return (_data[address] << 8) | _data[address + 1];
    }

    public int FetchByte(int address)
    {
        RequireFetchable(address);
        return _data[address];
    }

    public int FetchWord(int address)
    {
        RequireFetchable(address);
        RequireFetchable(address + 1);
        return (_data[address] << 8) | _data[address + 1];
    }

    public void WriteByte(int address, int value)
    {
        RequireWritable(address);

        if (value is < 0 or > 0xFF)
        {
            throw new ZMachineException($"value {value} does not fit in a byte");
        }

        _data[address] = (byte)value;
    }

    public void WriteWord(int address, int value)
    {
        RequireWritable(address);
        RequireWritable(address + 1);

        if (value is < 0 or > 0xFFFF)
        {
            throw new ZMachineException($"value {value} does not fit in a word");
        }

        _data[address] = (byte)(value >> 8);
        _data[address + 1] = (byte)value;
    }

    /// <summary>Every byte below the static memory base, copied (§6.1).</summary>
    public byte[] DynamicSnapshot() => _data[..StaticBase];

    /// <summary>Write a captured dynamic image back whole (§6.1.2).</summary>
    public void RestoreDynamic(ReadOnlySpan<byte> image)
    {
        if (image.Length != StaticBase)
        {
            throw new ZMachineException(
                $"cannot restore a {image.Length}-byte dynamic memory image over the {StaticBase} bytes this story defines: it was captured from a different game (§6.1.2.1)");
        }

        image.CopyTo(_data);
    }

    private void RequireFetchable(int address)
    {
        if (address < 0 || address >= _data.Length)
        {
            throw new ZMachineException(
                $"cannot fetch ${address:x4}: the story file ends at ${_data.Length - 1:x4} (§1.1)");
        }
    }

    private void RequireReadable(int address)
    {
        if (address < 0 || address >= _readLimit)
        {
            throw new ZMachineException(
                $"cannot read ${address:x4}: game-readable memory runs from $0000 up to ${_readLimit - 1:x4} (§1.1.2)");
        }
    }

    private void RequireWritable(int address)
    {
        if (address < 0 || address >= StaticBase)
        {
            throw new ZMachineException(
                $"cannot write ${address:x4}: only dynamic memory, below ${StaticBase:x4}, is writable (§1.1.2)");
        }
    }
}
