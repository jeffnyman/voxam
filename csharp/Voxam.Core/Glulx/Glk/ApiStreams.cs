namespace Voxam.Core.Glulx.Glk;

/// <summary>
/// The stream half of the library: opening them over memory, choosing
/// which one prints, and reading them back (Glk: Streams).
/// </summary>
public sealed partial class Api
{
    private void ServeStreams()
    {
        // Walk the live streams.
        Serve(0x0040, args => Held.OfOpaque(Iterate(Streams, Str(args[0]), Holder(args[1]))));

        // The rock the stream was opened with (Glk: Rocks).
        Serve(0x0041, args => Held.OfWord(Str(args[0])?.Rock ?? 0));

        Serve(0x0043, args =>
            Held.OfOpaque(OpenMemory(Buf(args[0]), Word(args[1]), Word(args[2]), false)));

        Serve(0x0139, args =>
            Held.OfOpaque(OpenMemory(Buf(args[0]), Word(args[1]), Word(args[2]), true)));

        Serve(0x0044, args =>
        {
            StreamClose(Str(args[0]), Record(args[1]));

            return default;
        });

        // Choose where the printing functions send output.
        Serve(0x0047, args =>
        {
            CurrentStream = Str(args[0]);

            return default;
        });

        // The stream the printing functions write to, or nothing.
        Serve(0x0048, _ => Held.OfOpaque(CurrentStream));

        // Move a stream's mark (Glk: Stream Positions).
        Serve(0x0045, args =>
        {
            Str(args[0])?.SetPosition(Signed(args[1]), Word(args[2]));

            return default;
        });

        // A stream's mark (Glk: Stream Positions).
        Serve(0x0046, args => Held.OfWord((uint)(Str(args[0])?.GetPosition() ?? 0)));
    }

    /// <summary>
    /// Open a memory stream in one of the modes that fit it.
    /// </summary>
    /// <exception cref="GlulxException">
    /// For WriteAppend, which the specification forbids on a memory
    /// stream (Glk: Memory Streams).
    /// </exception>
    private StreamOnMemory OpenMemory(IBuffer? buf, uint fmode, uint rock, bool unicode)
    {
        if (fmode is not (GlkFileMode.Read or GlkFileMode.Write or GlkFileMode.ReadWrite))
        {
            throw new GlulxException("stream_open_memory: illegal filemode");
        }

        var stream = new StreamOnMemory(buf, fmode, rock, unicode);

        Streams.Insert(0, stream);

        return stream;
    }

    /// <summary>
    /// Close a stream, reporting its counts (Glk: Closing Streams).
    /// </summary>
    /// <exception cref="GlulxException">For the null stream.</exception>
    private void StreamClose(StreamObject? stream, RefStruct? result)
    {
        if (stream is null)
        {
            throw new GlulxException("stream_close: invalid stream");
        }

        var (read, written) = stream.Close();

        result?.SetAll(Held.OfWord(read), Held.OfWord(written));

        Streams.Remove(stream);

        if (ReferenceEquals(CurrentStream, stream))
        {
            CurrentStream = null;
        }

        Dispose(stream);
    }
}
