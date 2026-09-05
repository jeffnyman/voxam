using System.Globalization;
using System.Text;
using System.Xml;
using System.Xml.Linq;

namespace Voxam.Core;

/// <summary>
/// The bibliographic heart of an iFiction record.
///
/// The blurb the reference also reads is not here: the port has no
/// card and no page to set one on, and what it does not show it does
/// not parse.
/// </summary>
/// <param name="Ifid">
/// The record's primary IFID, the first listed, which the treaty puts
/// foremost when a work carries several (Babel: The iFiction format).
/// </param>
/// <param name="Title">The work's title, or null unrecorded.</param>
/// <param name="Author">The author, or null unrecorded.</param>
/// <param name="Headline">The subtitle-like headline, or null unrecorded.</param>
public sealed record IFiction(
    string? Ifid = null,
    string? Title = null,
    string? Author = null,
    string? Headline = null);

/// <summary>
/// The Treaty of Babel: computing a story's IFID.
///
/// The treaty gives every work of interactive fiction an IFID,
/// "analogous to the ISBN code assigned to every published book"
/// (Babel: The IFID unique identifier), and lays down per-format rules
/// for computing one where none is embedded. This carries the rules
/// for the two formats the port plays: Z-code and Glulx. The
/// Å-machine's rule belongs to the reference alone, which is the only
/// one of the two that runs Dialog.
///
/// Modern design systems brand both formats with a UUID://...// string
/// in byte-accessible memory, and the brand wins wherever it is found.
/// Legacy files earn their IFIDs from their header numbers instead:
/// human-readable identities like ZCODE-88-840726, which the treaty
/// prefers to hashes because Infocom's files "sometimes crop up with
/// spurious tails" (Babel: The IFID for a legacy Z-code story file).
/// </summary>
public static class Babel
{
    // A story too short to hold the identifying header words can hold
    // no identity either.
    private const int HeaderExtent = 0x40;

    // The Z-Machine's eight story file versions (§11.1): a plausible
    // version byte is what marks loose bytes as Z-code.
    private const int LastZVersion = 8;

    // The Z-code header's identifying words (§11.1): release, serial,
    // checksum, the treaty's three elements.
    private const int ZRelease = 0x02;
    private const int ZSerial = 0x12;
    private const int ZSerialLength = 6;
    private const int ZChecksum = 0x1C;

    // The Glulx header's identifying words (Glulx: The Header), plus
    // the Inform-compiled fields past its end (Babel: The IFID for a
    // legacy Glulx story file).
    private const int GlulxExtent = 12;
    private const int GlulxChecksum = 32;
    private const int GlulxCompiler = 36;
    private const int GlulxRelease = 52;
    private const int GlulxSerial = 54;
    private const int GlulxSerialLength = 6;

    // The brand modern design systems burn into byte-accessible
    // memory. The treaty spells an IFID with digits, capitals and
    // hyphens, but Alan writes lowercase hexadecimal, "converted to
    // upper case when reading" (Babel: Game formats that embed an
    // IFID), so the scan accepts both cases and the answer wears
    // capitals.
    private static readonly byte[] BrandOpen = "UUID://"u8.ToArray();

    // Serial codes that never earn a checksum suffix: the test and
    // user-modified forms the treaty names (Babel: The IFID for a
    // legacy Z-code story file).
    private static readonly string[] UntrustedSerials = ["000000", "999999", "------"];

    // Inform announces itself past the Glulx header proper.
    private static readonly byte[] Inform = "Info"u8.ToArray();

    /// <summary>
    /// The IFID for a story file's bytes; null for neither format.
    ///
    /// A Glulx file answers by its magic word, anything else with a
    /// plausible version byte as Z-code. The caller unwraps blorbs
    /// first: a blorbed story's IFID is its packaged story's, until an
    /// iFiction record says otherwise (Babel: The IFID for a blorbed
    /// story file).
    /// </summary>
    public static string? Ifid(byte[] data)
    {
        if (data.Length < HeaderExtent)
        {
            return null;
        }

        if (Glulx.Story.IsGlulx(data))
        {
            return GlulxIfid(data);
        }

        return data[0] >= 1 && data[0] <= LastZVersion ? ZcodeIfid(data) : null;
    }

    /// <summary>
    /// A Z-code story's IFID from its brand or its header.
    ///
    /// The serial gates the brand scan: a file whose serial dates it
    /// before 2006, the 1980s, the 1990s, 2000 through 2005, cannot
    /// carry the UUID brand, so "searching for this is unnecessary"
    /// and only the rest are scanned (Babel: The IFID for a legacy
    /// Z-code story file).
    /// </summary>
    public static string ZcodeIfid(byte[] data)
    {
        var serial = Cleaned(data, ZSerial, ZSerialLength);

        if (!Dated(serial))
        {
            var branded = Branded(data);

            if (branded is not null)
            {
                return branded;
            }
        }

        var release = (data[ZRelease] << 8) | data[ZRelease + 1];
        var head = string.Create(
            CultureInfo.InvariantCulture, $"ZCODE-{release}-{serial}");

        // The post-1990 form: Inform-era serials carry the checksum as
        // four hexadecimal digits, while Infocom's 8x serials, and the
        // untrusted forms, stay bare (Babel: The IFID for a legacy
        // Z-code story file).
        if (!"012345679".Contains(serial[0], StringComparison.Ordinal)
            || UntrustedSerials.Contains(serial))
        {
            return head;
        }

        var checksum = (data[ZChecksum] << 8) | data[ZChecksum + 1];

        return string.Create(CultureInfo.InvariantCulture, $"{head}-{checksum:X4}");
    }

    /// <summary>
    /// A Glulx story's IFID from its brand or its header.
    ///
    /// An Inform-compiled file identifies like Z-code, release, serial
    /// and checksum, and announces itself with "Info" past the header
    /// proper; a file from any other tool has only its checksum,
    /// supplemented by the stated size of the initial memory map
    /// (Babel: The IFID for a legacy Glulx story file).
    /// </summary>
    public static string GlulxIfid(byte[] data)
    {
        var branded = Branded(data);

        if (branded is not null)
        {
            return branded;
        }

        var checksum = Word32(data, GlulxChecksum);

        if (data.AsSpan(GlulxCompiler, Inform.Length).SequenceEqual(Inform))
        {
            var release = (data[GlulxRelease] << 8) | data[GlulxRelease + 1];
            var serial = Cleaned(data, GlulxSerial, GlulxSerialLength);

            return string.Create(
                CultureInfo.InvariantCulture,
                $"GLULX-{release}-{serial}-{checksum:X8}");
        }

        var extent = Word32(data, GlulxExtent);

        return string.Create(
            CultureInfo.InvariantCulture, $"GLULX-{extent:X8}-{checksum:X8}");
    }

    /// <summary>
    /// The first story record in iFiction XML; null for unreadable.
    ///
    /// Elements are matched by local name alone: the treaty namespaces
    /// &lt;ifindex&gt;, but records in the wild are not always so
    /// careful, and bibliography is a courtesy that should survive a
    /// missing xmlns. Records the treaty itself warns about, the
    /// pre-1.0 versions still circulating, answer whatever of the
    /// record they can (Babel: The iFiction format).
    /// </summary>
    public static IFiction? Ifiction(byte[] xml)
    {
        XDocument document;

        try
        {
            // A stream rather than a string, so the record's own
            // encoding declaration is the one that is honoured.
            using var bytes = new MemoryStream(xml);

            document = XDocument.Load(bytes);
        }
        catch (XmlException)
        {
            return null;
        }

        var story = Child(document.Root, "story");

        if (story is null)
        {
            return null;
        }

        var identification = Child(story, "identification");
        var bibliographic = Child(story, "bibliographic");

        return new IFiction(
            Ifid: Field(identification, "ifid"),
            Title: Field(bibliographic, "title"),
            Author: Field(bibliographic, "author"),
            Headline: Field(bibliographic, "headline"));
    }

    // Whether the serial dates the file before the brand existed: the
    // 1980s, the 1990s, and 2000 through 2005. The comparison is
    // ordinal, as the reference's own string comparison is, so a
    // serial that is not a date at all falls outside it.
    private static bool Dated(string serial) =>
        serial[0] is '8' or '9'
        || (string.CompareOrdinal(serial[..2], "00") >= 0
            && string.CompareOrdinal(serial[..2], "05") <= 0);

    /// <summary>
    /// The embedded UUID://...// brand, uppercased, or null.
    ///
    /// "Its location cannot be guaranteed, so the whole of
    /// byte-accessible memory must be scanned" (Babel: Game formats
    /// that embed an IFID), and the file is the practical superset of
    /// byte-accessible memory.
    /// </summary>
    private static string? Branded(byte[] data)
    {
        var from = 0;

        while (true)
        {
            var opened = Found(data, from);

            if (opened < 0)
            {
                return null;
            }

            var start = opened + BrandOpen.Length;
            var end = start;

            while (end < data.Length && Allowed(data[end]))
            {
                end++;
            }

            // The run must be non-empty and closed by the second pair
            // of slashes; a brand that is neither is not one, and the
            // scan carries on past it as a search would.
            if (end > start && end + 1 < data.Length && data[end] == '/' && data[end + 1] == '/')
            {
                return Encoding.ASCII.GetString(data, start, end - start).ToUpperInvariant();
            }

            from = opened + 1;
        }
    }

    // Where the brand's opening stands next, or -1 past the last one.
    private static int Found(byte[] data, int from)
    {
        var span = data.AsSpan(from).IndexOf(BrandOpen);

        return span < 0 ? -1 : from + span;
    }

    // The characters the treaty spells an IFID with, plus the
    // lowercase Alan writes.
    private static bool Allowed(byte value) =>
        Alphanumeric(value) || value == (byte)'-';

    private static bool Alphanumeric(byte value) =>
        value is (>= (byte)'0' and <= (byte)'9')
            or (>= (byte)'A' and <= (byte)'Z')
            or (>= (byte)'a' and <= (byte)'z');

    /// <summary>
    /// Serial bytes as text, non-alphanumerics turned to hyphens.
    ///
    /// Only ASCII alphanumerics survive: "converting any
    /// non-alphanumeric characters (in particular, nulls) to hyphens"
    /// (Babel: The IFID for a legacy Z-code story file).
    /// </summary>
    private static string Cleaned(byte[] data, int offset, int length)
    {
        var built = new StringBuilder(length);

        for (var k = 0; k < length; k++)
        {
            var value = data[offset + k];

            built.Append(Alphanumeric(value) ? (char)value : '-');
        }

        return built.ToString();
    }

    // The first child element whose local name matches, namespace-blind.
    private static XElement? Child(XElement? element, string name)
    {
        if (element is null)
        {
            return null;
        }

        foreach (var child in element.Elements())
        {
            if (child.Name.LocalName == name)
            {
                return child;
            }
        }

        return null;
    }

    // A section's first named child's text, stripped, or null. The
    // text is the piece before any child element, which is what the
    // reference reads and all a bibliographic field ever holds.
    private static string? Field(XElement? section, string name)
    {
        if (Child(section, name) is not { } found)
        {
            return null;
        }

        if (found.Nodes().FirstOrDefault() is not XText text)
        {
            return null;
        }

        var trimmed = text.Value.Trim();

        return trimmed.Length == 0 ? null : trimmed;
    }

    private static uint Word32(byte[] data, int offset) =>
        ((uint)data[offset] << 24)
        | ((uint)data[offset + 1] << 16)
        | ((uint)data[offset + 2] << 8)
        | data[offset + 3];
}
