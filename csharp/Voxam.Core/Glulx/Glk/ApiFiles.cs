namespace Voxam.Core.Glulx.Glk;

/// <summary>
/// File references and the streams opened over them (Glk: File
/// References, File Streams).
/// </summary>
public sealed partial class Api
{
    // Characters deleted from a game-supplied filename (Glk: File
    // References).
    private const string IllegalInName = "\"\\/><:|?*";

    private const string DefaultSuffix = ".glkdata";

    private void ServeFiles()
    {
        // A reference to a fresh temporary file.
        Serve(0x0060, args =>
        {
            var path = Path.Combine(
                Path.GetTempPath(), "voxam-glk-" + Path.GetRandomFileName());

            System.IO.File.WriteAllBytes(path, []);

            return Held.OfOpaque(NewFileRef(path, Word(args[0]), Word(args[1]), true));
        });

        // A reference to a file the game names itself.
        Serve(0x0061, args =>
        {
            var usage = Word(args[0]);

            return Held.OfOpaque(NewFileRef(PathFor(Text(args[1]), usage), usage, Word(args[2])));
        });

        Serve(0x0068, args =>
        {
            var fileref = File(args[1])
                ?? throw new GlulxException("fileref_create_from_fileref: invalid fileref");

            return Held.OfOpaque(NewFileRef(fileref.Filename, Word(args[0]), Word(args[2])));
        });

        // Drop a reference; a temporary file dies with it (Glk: File
        // References).
        Serve(0x0063, args =>
        {
            var fileref = File(args[0]);

            if (fileref is not null)
            {
                FileRefs.Remove(fileref);

                if (fileref.Temporary)
                {
                    Delete(fileref.Filename);
                }

                Dispose(fileref);
            }

            return default;
        });

        // Delete the file the reference names.
        Serve(0x0066, args =>
        {
            var fileref = File(args[0]);

            if (fileref is not null)
            {
                Delete(fileref.Filename);
            }

            return default;
        });

        // Whether the named file exists right now.
        Serve(0x0067, args =>
        {
            var fileref = File(args[0]);

            if (fileref is null)
            {
                return Held.OfWord(0);
            }

            return Held.OfWord(System.IO.File.Exists(fileref.Filename) ? 1u : 0u);
        });

        // Walk the live file references.
        Serve(0x0064, args => Held.OfOpaque(Iterate(FileRefs, File(args[0]), Holder(args[1]))));

        // The rock the reference was created with (Glk: Rocks).
        Serve(0x0065, args => Held.OfWord(File(args[0])?.Rock ?? 0));

        Serve(0x0042, args =>
            Held.OfOpaque(OpenFile(File(args[0]), Word(args[1]), Word(args[2]), false)));

        Serve(0x0138, args =>
            Held.OfOpaque(OpenFile(File(args[0]), Word(args[1]), Word(args[2]), true)));
    }

    /// <summary>Record a reference on the live list.</summary>
    private FileRef NewFileRef(string path, uint usage, uint rock, bool temporary = false)
    {
        var fileref = new FileRef(path, usage, rock, temporary);

        FileRefs.Insert(0, fileref);

        return fileref;
    }

    /// <summary>
    /// A game-supplied name, made a path inside the save directory.
    ///
    /// The recommended simplification, as cheapglk implements it: delete
    /// every character in the illegal set, truncate at the first period,
    /// use "null" if nothing is left, then append a suffix chosen by
    /// usage (Glk: File References). Not a requirement, but it is what
    /// lets Glk implementations exchange files, and it means a name
    /// arriving from game bytecode cannot reach outside the save
    /// directory by any route.
    /// </summary>
    private string PathFor(string name, uint usage)
    {
        var head = name.Split('.')[0];
        var stem = new string([.. head.Where(character => !IllegalInName.Contains(character))]);

        if (stem.Length == 0)
        {
            stem = "null";
        }

        var suffix = (usage & FileUsage.TypeMask) switch
        {
            FileUsage.SavedGame => ".glksave",
            FileUsage.Transcript => ".txt",
            FileUsage.InputRecord => ".txt",
            _ => DefaultSuffix,
        };

        return Path.Combine(SaveDir, stem + suffix);
    }

    /// <summary>
    /// Open a file stream, or nothing where it will not open (Glk: File
    /// Streams).
    /// </summary>
    /// <exception cref="GlulxException">
    /// For the null reference, or a mode that is not one of the four.
    /// </exception>
    private StreamOnFile? OpenFile(FileRef? fileref, uint fmode, uint rock, bool unicode)
    {
        if (fileref is null)
        {
            throw new GlulxException("stream_open_file: invalid fileref");
        }

        if (fmode is not (GlkFileMode.Read or GlkFileMode.Write
            or GlkFileMode.ReadWrite or GlkFileMode.WriteAppend))
        {
            throw new GlulxException("stream_open_file: illegal filemode");
        }

        Stream handle;

        try
        {
            handle = fmode switch
            {
                GlkFileMode.Read => new FileStream(
                    fileref.Filename, FileMode.Open, FileAccess.Read),
                GlkFileMode.Write => new FileStream(
                    fileref.Filename, FileMode.Create, FileAccess.Write),
                // Not an appending handle: an appending one forces every
                // write to the end of the file, but Glk only asks that
                // the mark start there, and a later seek must be honored
                // (Glk: Stream Positions).
                _ => new FileStream(
                    fileref.Filename, FileMode.OpenOrCreate, FileAccess.ReadWrite),
            };
        }
        catch (Exception thrown) when (thrown is IOException or UnauthorizedAccessException)
        {
            // Opening may simply fail, and yields the null stream (Glk:
            // File Streams). A missing file, a name that is really a
            // directory, and a file this session may not have all arrive
            // here, and which of them a given system raises which
            // exception for is that system's own business.
            return null;
        }

        if (fmode == GlkFileMode.WriteAppend)
        {
            handle.Seek(0, SeekOrigin.End);
        }

        var stream = new StreamOnFile(handle, fmode, rock, unicode, fileref.TextMode);

        Streams.Insert(0, stream);

        return stream;
    }

    /// <summary>
    /// Remove a file. One that was never there is no error, and a
    /// deletion that cannot happen at all faults rather than passing in
    /// silence: the reference deletes through a call with exactly those
    /// two properties, and the port has no business being braver than
    /// the thing it is a port of.
    ///
    /// Nothing is caught here on purpose. Which deletions a system
    /// refuses, and which exception it refuses with, is that system's
    /// own business, and a guess at it would put a path through this
    /// code that one machine could reach and another could not.
    /// </summary>
    private static void Delete(string filename) => System.IO.File.Delete(filename);
}
