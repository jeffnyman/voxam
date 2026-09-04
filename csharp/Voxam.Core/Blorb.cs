using System.Text;

namespace Voxam.Core;

/// <summary>Enough of a Blorb to take the session banner's census and check identity.</summary>
public sealed class Blorb
{
    public int Pictures { get; private init; }
    public int Sounds { get; private init; }
    public bool HasStory { get; private init; }
    private byte[]? _identity;

    /// <summary>
    /// The packaged Z-code story, or null: an Exec resource is
    /// numbered 0, and only the ZCOD executable format belongs to
    /// this machine.
    /// </summary>
    public byte[]? Story { get; private init; }

    public static Blorb Load(byte[] data)
    {
        if (data.Length < 12 || Ascii(data, 0) != "FORM" || Ascii(data, 8) != "IFRS")
        {
            throw new ZMachineException("the resource file is not a Blorb: no FORM IFRS header");
        }

        var pictures = 0;
        var sounds = 0;
        var story = false;
        byte[]? packaged = null;
        byte[]? identity = null;
        var pos = 12;

        while (pos + 8 <= data.Length)
        {
            var id = Ascii(data, pos);
            var length = Word32(data, pos + 4);
            var payload = pos + 8;

            if (payload + length > data.Length)
            {
                throw new ZMachineException($"the {id} chunk claims {length} bytes, but the file ends before them (Blorb: IFF)");
            }

            if (id == "RIdx")
            {
                if (length < 4)
                {
                    throw new ZMachineException("the RIdx chunk is too short to hold its own count");
                }

                var count = Word32(data, payload);

                if (length != 4 + 12 * count)
                {
                    throw new ZMachineException($"the RIdx count of {count} needs {4 + 12 * count} bytes, but the chunk holds {length} (Blorb: Resource Index Chunk)");
                }

                for (var k = 0; k < count; k++)
                {
                    var entry = payload + 4 + 12 * k;
                    var usage = Ascii(data, entry);

                    if (usage == "Pict")
                    {
                        pictures++;
                    }
                    else if (usage == "Snd ")
                    {
                        sounds++;
                    }
                    else if (usage == "Exec")
                    {
                        story = true;

                        if (Word32(data, entry + 4) == 0)
                        {
                            packaged = Executable(data, Word32(data, entry + 8));
                        }
                    }
                }
            }
            else if (id == "IFhd")
            {
                identity = data[payload..(payload + length)];
            }

            pos = payload + length + (length & 1);
        }

        return new Blorb { Pictures = pictures, Sounds = sounds, HasStory = story, Story = packaged, _identity = identity };
    }

    // The chunk an Exec entry points at, when it is Z-code.
    private static byte[]? Executable(byte[] data, int offset)
    {
        if (offset + 8 > data.Length || Ascii(data, offset) != "ZCOD")
        {
            return null;
        }

        var length = Word32(data, offset + 4);
        return data[(offset + 8)..(offset + 8 + length)];
    }

    private static int Word32(byte[] data, int at) => (data[at] << 24) | (data[at + 1] << 16) | (data[at + 2] << 8) | data[at + 3];

    /// <summary>A one-line census for the session banner.</summary>
    public string Described()
    {
        var parts = new List<string>();

        if (Pictures > 0) parts.Add($"{Pictures} picture{(Pictures != 1 ? "s" : "")}");
        if (Sounds > 0) parts.Add($"{Sounds} sound{(Sounds != 1 ? "s" : "")}");
        if (HasStory) parts.Add("a packaged story");

        return parts.Count > 0 ? string.Join(", ", parts) : "no resources";
    }

    /// <summary>Whether the identifier chunk names this story; absence matches anything.</summary>
    public bool Matches(byte[] story)
    {
        if (_identity is null || _identity.Length < 10)
        {
            return true;
        }

        for (var k = 0; k < 2; k++)
        {
            if (_identity[k] != story[Header.Release + k]) return false;
        }

        for (var k = 0; k < 6; k++)
        {
            if (_identity[2 + k] != story[Header.Serial + k]) return false;
        }

        return _identity[8] == story[Header.Checksum] && _identity[9] == story[Header.Checksum + 1];
    }

    private static string Ascii(byte[] data, int at) => Encoding.ASCII.GetString(data, at, 4);
}
