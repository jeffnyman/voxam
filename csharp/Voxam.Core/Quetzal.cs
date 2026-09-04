using System.Text;

namespace Voxam.Core;

/// <summary>One routine invocation as a save remembers it (§6.1); a store variable of -1 discards the result.</summary>
public sealed record SavedFrame(int ReturnAddress, int StoreVariable, int[] Locals, int ArgumentCount, int[] Stack);

/// <summary>The state of play: dynamic memory, the pc, and the call chain from the base frame up.</summary>
public sealed record SavedState(byte[] Dynamic, int Pc, IReadOnlyList<SavedFrame> Frames);

/// <summary>
/// Quetzal, the common format for saved games (Quetzal 1.4): an IFF
/// FORM of type IFZS carrying IFhd, CMem or UMem, and Stks. A pure
/// codec, ported from the reference: state in, bytes out, and back.
/// Writing always compresses; reading accepts both memory forms.
/// </summary>
public static class Quetzal
{
    private const int IfhdLength = 13;
    private const int IdentitySize = 10;
    private const int AddressLimit = 0xFFFFFF;
    private const int DiscardFlag = 0x10;
    private const int LocalsMask = 0x0F;
    private const int FlagsReserved = 0xE0;
    private const int ArgumentsLimit = 7;
    private const int FrameHeaderSize = 8;
    private const int LongestRun = 256;

    /// <summary>Serialize a state of play as an IFZS FORM: IFhd, then CMem, then Stks.</summary>
    public static byte[] Write(SavedState state, byte[] pristine)
    {
        var staticBase = (pristine[Header.StaticBase] << 8) | pristine[Header.StaticBase + 1];

        if (state.Dynamic.Length != staticBase)
        {
            throw new ZMachineException(
                $"cannot save a {state.Dynamic.Length}-byte dynamic memory image for a story whose dynamic memory is {staticBase} bytes: the snapshot belongs to a different game (Quetzal §5.3)");
        }

        var body = new List<byte>(Encoding.ASCII.GetBytes("IFZS"));
        body.AddRange(Chunk("IFhd", [.. Identity(pristine), .. Address(state.Pc)]));
        body.AddRange(Chunk("CMem", Compress(state.Dynamic, pristine)));
        body.AddRange(Chunk("Stks", EncodeFrames(state.Frames)));
        return Chunk("FORM", [.. body]);
    }

    /// <summary>Parse an IFZS FORM back into a state of play, refusing a save of another game.</summary>
    public static SavedState Read(byte[] data, byte[] pristine)
    {
        var found = Walk(data);

        if (!found.TryGetValue("IFhd", out var ifhd))
        {
            throw new ZMachineException("the required IFhd chunk is missing (Quetzal §7.18)");
        }

        if (!found.TryGetValue("Stks", out var stks))
        {
            throw new ZMachineException("the required Stks chunk is missing (Quetzal §7.18)");
        }

        var compressed = found.TryGetValue("CMem", out var cmem);
        var whole = found.TryGetValue("UMem", out var umem);

        if (compressed && whole)
        {
            throw new ZMachineException("CMem and UMem both appear: a save carries one or the other (Quetzal §7.18)");
        }

        if (!compressed && !whole)
        {
            throw new ZMachineException("the required CMem or UMem chunk is missing (Quetzal §7.18)");
        }

        var pc = CheckIdentity(ifhd, pristine);
        var staticBase = (pristine[Header.StaticBase] << 8) | pristine[Header.StaticBase + 1];
        var dynamic = whole ? WholeMemory(umem!, staticBase) : Decompress(cmem!, pristine, staticBase);
        return new SavedState(dynamic, pc, DecodeFrames(stks));
    }

    /// <summary>The ten bytes naming a story: release, serial, checksum (Quetzal §5.3), computed when the header holds none.</summary>
    public static byte[] Identity(byte[] pristine)
    {
        var checksum = (pristine[Header.Checksum] << 8) | pristine[Header.Checksum + 1];

        if (checksum == 0)
        {
            var scale = pristine[0] switch { <= 3 => 2, <= 5 => 4, _ => 8 };
            var length = Math.Min(((pristine[Header.FileLength] << 8) | pristine[Header.FileLength + 1]) * scale, pristine.Length);

            for (var k = 0x40; k < length; k++)
            {
                checksum = (checksum + pristine[k]) & 0xFFFF;
            }
        }

        return
        [
            pristine[Header.Release], pristine[Header.Release + 1],
            .. pristine[Header.Serial..(Header.Serial + 6)],
            (byte)(checksum >> 8), (byte)checksum,
        ];
    }

    private static byte[] Address(int value)
    {
        if (value > AddressLimit)
        {
            throw new ZMachineException($"address ${value:x} does not fit in the three bytes Quetzal stores (Quetzal §4.3.1)");
        }

        return [(byte)(value >> 16), (byte)(value >> 8), (byte)value];
    }

    // Exclusive-or against the pristine story, zero runs collapsed to a
    // zero byte and a count of n+1, trailing zeros dropped (§3.2, §3.4).
    private static byte[] Compress(byte[] dynamic, byte[] pristine)
    {
        var changed = new byte[dynamic.Length];

        for (var k = 0; k < dynamic.Length; k++)
        {
            changed[k] = (byte)(dynamic[k] ^ pristine[k]);
        }

        var end = changed.Length;

        while (end > 0 && changed[end - 1] == 0)
        {
            end--;
        }

        var encoded = new List<byte>();
        var position = 0;

        while (position < end)
        {
            if (changed[position] != 0)
            {
                encoded.Add(changed[position]);
                position++;
                continue;
            }

            // The trimmed tail ends on a changed byte, so a run of
            // zeros always stops at one before it can reach the edge.
            var run = position;

            while (changed[run] == 0)
            {
                run++;
            }

            for (var length = position; length < run; length += LongestRun)
            {
                encoded.Add(0);
                encoded.Add((byte)(Math.Min(run - length, LongestRun) - 1));
            }

            position = run;
        }

        return [.. encoded];
    }

    private static byte[] Decompress(byte[] encoded, byte[] pristine, int size)
    {
        var changed = new List<byte>();
        var position = 0;

        while (position < encoded.Length)
        {
            var value = encoded[position];

            if (value != 0)
            {
                changed.Add(value);
                position++;
                continue;
            }

            if (position + 1 == encoded.Length)
            {
                throw new ZMachineException("compressed memory ends with a zero byte and no run length (Quetzal §3.5)");
            }

            changed.AddRange(new byte[encoded[position + 1] + 1]);
            position += 2;
        }

        if (changed.Count > size)
        {
            throw new ZMachineException($"compressed memory decodes to {changed.Count} bytes, but dynamic memory holds only {size} (Quetzal §3.5)");
        }

        var dynamic = new byte[size];

        for (var k = 0; k < size; k++)
        {
            dynamic[k] = (byte)((k < changed.Count ? changed[k] : 0) ^ pristine[k]);
        }

        return dynamic;
    }

    private static byte[] WholeMemory(byte[] dump, int size)
    {
        if (dump.Length != size)
        {
            throw new ZMachineException($"a UMem dump must be exactly dynamic memory: {size} bytes, not {dump.Length} (Quetzal §3.6)");
        }

        return dump;
    }

    // The call chain as Stks data, oldest first; the base frame is the
    // dummy frame of Quetzal §4.11, every field zero but its stack count.
    private static byte[] EncodeFrames(IReadOnlyList<SavedFrame> frames)
    {
        var encoded = new List<byte>();

        for (var index = 0; index < frames.Count; index++)
        {
            var frame = frames[index];

            if (index == 0)
            {
                encoded.AddRange([0, 0, 0, 0, 0, 0]);
            }
            else
            {
                if (frame.ArgumentCount > ArgumentsLimit)
                {
                    throw new ZMachineException($"a frame holding {frame.ArgumentCount} arguments does not fit the seven argument bits (Quetzal §4.3.4)");
                }

                var flags = frame.Locals.Length;
                var store = frame.StoreVariable;

                if (store < 0)
                {
                    flags |= DiscardFlag;
                    store = 0;
                }

                encoded.AddRange(Address(frame.ReturnAddress));
                encoded.AddRange([(byte)flags, (byte)store, (byte)((1 << frame.ArgumentCount) - 1)]);
            }

            encoded.Add((byte)(frame.Stack.Length >> 8));
            encoded.Add((byte)frame.Stack.Length);

            foreach (var word in frame.Locals.Concat(frame.Stack))
            {
                encoded.Add((byte)(word >> 8));
                encoded.Add((byte)word);
            }
        }

        return [.. encoded];
    }

    private static List<SavedFrame> DecodeFrames(byte[] data)
    {
        var frames = new List<SavedFrame>();
        var position = 0;

        while (position < data.Length)
        {
            if (position + FrameHeaderSize > data.Length)
            {
                throw new ZMachineException("a stack frame is cut short mid-header (Quetzal §4.3)");
            }

            var returnAddress = (data[position] << 16) | (data[position + 1] << 8) | data[position + 2];
            var flags = data[position + 3];
            var store = data[position + 4];
            var mask = data[position + 5];
            var stackCount = (data[position + 6] << 8) | data[position + 7];
            position += FrameHeaderSize;

            if ((flags & FlagsReserved) != 0)
            {
                throw new ZMachineException($"a frame's flags byte ${flags:x2} uses reserved bits: only 000pvvvv is defined (Quetzal §4.3.2)");
            }

            if ((mask & (mask + 1)) != 0)
            {
                throw new ZMachineException($"a frame's argument mask ${mask:x2} has gaps: arguments are supplied in order (Quetzal §4.3.4)");
            }

            var localCount = flags & LocalsMask;
            var wordsSize = (localCount + stackCount) * 2;

            if (position + wordsSize > data.Length)
            {
                throw new ZMachineException("a stack frame is cut short mid-words (Quetzal §4.3)");
            }

            var words = new int[localCount + stackCount];

            for (var k = 0; k < words.Length; k++)
            {
                words[k] = (data[position + 2 * k] << 8) | data[position + 2 * k + 1];
            }

            position += wordsSize;
            int storeVariable;

            if (frames.Count == 0)
            {
                if (returnAddress != 0 || flags != 0 || store != 0 || mask != 0)
                {
                    throw new ZMachineException("the first frame must be the dummy: every field zero but its stack count (Quetzal §4.11.1)");
                }

                storeVariable = -1;
            }
            else
            {
                storeVariable = (flags & DiscardFlag) != 0 ? -1 : store;
            }

            frames.Add(new SavedFrame(returnAddress, storeVariable, words[..localCount], System.Numerics.BitOperations.PopCount((uint)mask), words[localCount..]));
        }

        if (frames.Count == 0)
        {
            throw new ZMachineException("the Stks chunk is empty: the dummy frame is always present (Quetzal §4.11.2)");
        }

        return frames;
    }

    // The known chunks out of the IFF container: only an IFZS FORM
    // will do, the known chunks may not double, IFhd must come first,
    // and unknown chunks are skipped unread (Quetzal §7.17, §8.6).
    private static Dictionary<string, byte[]> Walk(byte[] data)
    {
        if (data.Length < 12 || Encoding.ASCII.GetString(data, 0, 4) != "FORM")
        {
            throw new ZMachineException("not an IFF file: no FORM chunk to open it (Quetzal §8.5)");
        }

        var length = (data[4] << 24) | (data[5] << 16) | (data[6] << 8) | data[7];

        if (8 + length > data.Length)
        {
            throw new ZMachineException($"the FORM chunk claims {length} bytes, but the file has only {data.Length - 8} after its header (Quetzal §8.3.5)");
        }

        if (Encoding.ASCII.GetString(data, 8, 4) != "IFZS")
        {
            throw new ZMachineException($"the FORM type is {Encoding.ASCII.GetString(data, 8, 4)}, not the IFZS of a saved game (Quetzal §2.1)");
        }

        var found = new Dictionary<string, byte[]>(StringComparer.Ordinal);
        var position = 12;
        var end = 8 + length;

        while (position < end)
        {
            if (position + 8 > end)
            {
                throw new ZMachineException("a chunk is cut short mid-header (Quetzal §8.3.1)");
            }

            var id = Encoding.ASCII.GetString(data, position, 4);
            var size = (data[position + 4] << 24) | (data[position + 5] << 16) | (data[position + 6] << 8) | data[position + 7];
            position += 8;

            if (position + size > end)
            {
                throw new ZMachineException($"the {id} chunk claims {size} bytes, but the FORM ends before them (Quetzal §8.4)");
            }

            if (id is "IFhd" or "CMem" or "UMem" or "Stks")
            {
                if (found.ContainsKey(id))
                {
                    throw new ZMachineException($"the {id} chunk appears twice (Quetzal §7.18)");
                }

                if (id != "IFhd" && !found.ContainsKey("IFhd"))
                {
                    throw new ZMachineException($"the {id} chunk arrives before IFhd, which must come first (Quetzal §5.4)");
                }

                found[id] = data[position..(position + size)];
            }

            position += size + (size & 1);
        }

        return found;
    }

    private static int CheckIdentity(byte[] ifhd, byte[] pristine)
    {
        if (ifhd.Length < IfhdLength)
        {
            throw new ZMachineException($"the IFhd chunk holds {ifhd.Length} bytes, fewer than the {IfhdLength} its first bytes always contain (Quetzal §5.5)");
        }

        if (!ifhd.AsSpan(0, IdentitySize).SequenceEqual(Identity(pristine)))
        {
            throw new ZMachineException("this save names a different game: its release, serial, and checksum do not match the story being played (Quetzal §5.3, §6.1.2.1)");
        }

        return (ifhd[10] << 16) | (ifhd[11] << 8) | ifhd[12];
    }

    // A framed chunk: ID, big-endian length, data, and a pad byte after odd data.
    private static byte[] Chunk(string id, byte[] payload)
    {
        var framed = new List<byte>(Encoding.ASCII.GetBytes(id));
        framed.AddRange([(byte)(payload.Length >> 24), (byte)(payload.Length >> 16), (byte)(payload.Length >> 8), (byte)payload.Length]);
        framed.AddRange(payload);

        if (payload.Length % 2 != 0)
        {
            framed.Add(0);
        }

        return [.. framed];
    }
}
