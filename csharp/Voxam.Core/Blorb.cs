using System.Text;

namespace Voxam.Core;

/// <summary>Enough of a Blorb to take the session banner's census and check identity.</summary>
public sealed class Blorb
{
    public int Pictures { get; private init; }
    public int Sounds { get; private init; }
    public bool HasStory { get; private init; }
    private byte[]? _identity;

    public static Blorb Load(byte[] data)
    {
        if (data.Length < 12 || Ascii(data, 0) != "FORM" || Ascii(data, 8) != "IFRS")
        {
            throw new ZMachineException("the resource file is not a Blorb: no FORM IFRS header");
        }

        var pictures = 0;
        var sounds = 0;
        var story = false;
        byte[]? identity = null;
        var pos = 12;

        while (pos + 8 <= data.Length)
        {
            var id = Ascii(data, pos);
            var length = (data[pos + 4] << 24) | (data[pos + 5] << 16) | (data[pos + 6] << 8) | data[pos + 7];
            var payload = pos + 8;

            if (id == "RIdx")
            {
                var count = (data[payload] << 24) | (data[payload + 1] << 16) | (data[payload + 2] << 8) | data[payload + 3];

                for (var k = 0; k < count; k++)
                {
                    var usage = Ascii(data, payload + 4 + 12 * k);

                    if (usage == "Pict") pictures++;
                    else if (usage == "Snd ") sounds++;
                    else if (usage == "Exec") story = true;
                }
            }
            else if (id == "IFhd")
            {
                identity = data[payload..(payload + length)];
            }

            pos = payload + length + (length & 1);
        }

        return new Blorb { Pictures = pictures, Sounds = sounds, HasStory = story, _identity = identity };
    }

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
