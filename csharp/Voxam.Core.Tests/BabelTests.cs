using System.Text;

namespace Voxam.Core.Tests;

public class BabelTests
{
    // A Z-code story file: a version byte, a release, a serial, and a
    // checksum, padded out to the header extent the treaty needs.
    private static byte[] Zcode(
        int version, int release, string serial, int checksum, byte[]? tail = null)
    {
        var data = new byte[0x40 + (tail?.Length ?? 0)];
        data[0] = (byte)version;
        data[0x02] = (byte)(release >> 8);
        data[0x03] = (byte)release;
        Encoding.ASCII.GetBytes(serial).CopyTo(data, 0x12);
        data[0x1C] = (byte)(checksum >> 8);
        data[0x1D] = (byte)checksum;
        tail?.CopyTo(data, 0x40);

        return data;
    }

    // A Glulx story file: the magic word, the stated extent of the
    // initial memory map, the checksum, and the compiler's own mark.
    private static byte[] Glulxed(
        uint extent, uint checksum, string compiler, int release = 0, string serial = "000000")
    {
        var data = new byte[0x40];
        Encoding.ASCII.GetBytes("Glul").CopyTo(data, 0);
        Word32(data, 12, extent);
        Word32(data, 32, checksum);
        Encoding.ASCII.GetBytes(compiler).CopyTo(data, 36);
        data[52] = (byte)(release >> 8);
        data[53] = (byte)release;
        Encoding.ASCII.GetBytes(serial).CopyTo(data, 54);

        return data;
    }

    private static void Word32(byte[] data, int offset, uint value)
    {
        data[offset] = (byte)(value >> 24);
        data[offset + 1] = (byte)(value >> 16);
        data[offset + 2] = (byte)(value >> 8);
        data[offset + 3] = (byte)value;
    }

    private static byte[] Ascii(string text) => Encoding.ASCII.GetBytes(text);

    // A file too short to hold the identifying words holds no identity,
    // Glulx answers by its magic, and anything with a plausible version
    // byte is read as Z-code. Anything else is neither.
    [Fact]
    public void TheFormatDecidesWhichRuleAnswers()
    {
        Assert.Null(Babel.Ifid(new byte[0x3F]));
        Assert.Equal(
            "GLULX-00000100-DEADBEEF",
            Babel.Ifid(Glulxed(0x100, 0xDEADBEEF, "\0\0\0\0")));
        Assert.Equal("ZCODE-88-840726", Babel.Ifid(Zcode(3, 88, "840726", 0x1234)));
        Assert.Equal("ZCODE-1-010101-1234", Babel.Ifid(Zcode(8, 1, "010101", 0x1234)));
        Assert.Null(Babel.Ifid(Zcode(0, 1, "010101", 0)));
        Assert.Null(Babel.Ifid(Zcode(9, 1, "010101", 0)));
    }

    // Infocom's 8x serials stay bare; an Inform-era serial carries the
    // checksum as four hexadecimal digits; and the test and
    // user-modified serials the treaty names earn no suffix either.
    [Fact]
    public void TheSerialDecidesWhetherAChecksumRides()
    {
        Assert.Equal("ZCODE-88-840726", Babel.ZcodeIfid(Zcode(3, 88, "840726", 0xABCD)));
        Assert.Equal("ZCODE-16-951024-0FED", Babel.ZcodeIfid(Zcode(5, 16, "951024", 0x0FED)));
        Assert.Equal("ZCODE-1-000000", Babel.ZcodeIfid(Zcode(5, 1, "000000", 0x1111)));
        Assert.Equal("ZCODE-1-999999", Babel.ZcodeIfid(Zcode(5, 1, "999999", 0x1111)));
        Assert.Equal("ZCODE-1-------", Babel.ZcodeIfid(Zcode(5, 1, "------", 0x1111)));
    }

    // Non-alphanumerics in a serial become hyphens, nulls included,
    // which is what the treaty asks for.
    [Fact]
    public void ASerialKeepsOnlyItsAlphanumerics()
    {
        var data = Zcode(5, 7, "06\0.aZ", 0x2222);

        Assert.Equal("ZCODE-7-06--aZ-2222", Babel.ZcodeIfid(data));
    }

    // A file whose serial dates it before the brand existed is not
    // scanned for one, even when it carries something that looks like a
    // brand; a later file is, and the brand wins when it is there.
    [Fact]
    public void TheSerialGatesTheBrandScan()
    {
        var brand = Ascii("UUID://9E2B-0001//");

        Assert.Equal(
            "ZCODE-3-851218", Babel.ZcodeIfid(Zcode(3, 3, "851218", 0, brand)));
        Assert.Equal(
            "ZCODE-3-991218-0000", Babel.ZcodeIfid(Zcode(3, 3, "991218", 0, brand)));
        Assert.Equal(
            "ZCODE-3-050101-0000", Babel.ZcodeIfid(Zcode(3, 3, "050101", 0, brand)));
        Assert.Equal(
            "9E2B-0001", Babel.ZcodeIfid(Zcode(3, 3, "060101", 0, brand)));
        Assert.Equal(
            "9E2B-0001", Babel.ZcodeIfid(Zcode(3, 3, "1x0101", 0, brand)));
    }

    // Alan writes the brand in lowercase, "converted to upper case when
    // reading"; a file with no brand at all falls back to its header.
    [Fact]
    public void TheBrandIsReadInEitherCaseAndAnsweredInCapitals()
    {
        Assert.Equal(
            "9E2B-000A",
            Babel.ZcodeIfid(Zcode(5, 3, "060101", 0, Ascii("UUID://9e2b-000a//"))));
        Assert.Equal(
            "ZCODE-3-060101-0000", Babel.ZcodeIfid(Zcode(5, 3, "060101", 0)));
    }

    // What looks like a brand but is not one is stepped over, and the
    // scan carries on to whatever stands after it: an empty run, a run
    // the file ends inside, a run closed by the wrong character, and a
    // run closed by only one slash are all refused.
    [Fact]
    public void AMalformedBrandIsNotOne()
    {
        Assert.Equal(
            "ZCODE-3-060101-0000",
            Babel.ZcodeIfid(Zcode(5, 3, "060101", 0, Ascii("UUID:////"))));
        Assert.Equal(
            "ZCODE-3-060101-0000",
            Babel.ZcodeIfid(Zcode(5, 3, "060101", 0, Ascii("UUID://ABC"))));
        Assert.Equal(
            "ZCODE-3-060101-0000",
            Babel.ZcodeIfid(Zcode(5, 3, "060101", 0, Ascii("UUID://ABC!!"))));
        Assert.Equal(
            "ZCODE-3-060101-0000",
            Babel.ZcodeIfid(Zcode(5, 3, "060101", 0, Ascii("UUID://ABC/X"))));
        Assert.Equal(
            "REAL-01",
            Babel.ZcodeIfid(Zcode(5, 3, "060101", 0, Ascii("UUID://ABC/XUUID://real-01//"))));
    }

    // An Inform-compiled Glulx file identifies like Z-code, release,
    // serial and checksum; a file from any other tool has only its
    // checksum and the stated size of its memory map; and a brand beats
    // both.
    [Fact]
    public void GlulxIdentifiesByItsCompiler()
    {
        Assert.Equal(
            "GLULX-9-060503-0BADF00D",
            Babel.GlulxIfid(Glulxed(0x100, 0x0BADF00D, "Info", 9, "060503")));
        Assert.Equal(
            "GLULX-00000100-0BADF00D",
            Babel.GlulxIfid(Glulxed(0x100, 0x0BADF00D, "____")));

        var branded = Glulxed(0x100, 0x0BADF00D, "Info", 9, "060503");
        var whole = new byte[branded.Length + 20];
        branded.CopyTo(whole, 0);
        Ascii("UUID://ABCD-0001//").CopyTo(whole, branded.Length);

        Assert.Equal("ABCD-0001", Babel.GlulxIfid(whole));
    }

    // A whole record answers every field it has.
    [Fact]
    public void ARecordAnswersItsBibliography()
    {
        var record = Babel.Ifiction(
            Ascii(
                """
                <?xml version="1.0" encoding="UTF-8"?>
                <ifindex version="1.0" xmlns="http://babel.ifarchive.org/protocol/iFiction/">
                  <story>
                    <identification>
                      <ifid>ZCODE-11-060503-1234</ifid>
                      <format>zcode</format>
                    </identification>
                    <bibliographic>
                      <title>Bronze</title>
                      <author>Emily Short</author>
                      <headline>A fractured fairy tale</headline>
                    </bibliographic>
                  </story>
                </ifindex>
                """));

        Assert.NotNull(record);
        Assert.Equal("ZCODE-11-060503-1234", record.Ifid);
        Assert.Equal("Bronze", record.Title);
        Assert.Equal("Emily Short", record.Author);
        Assert.Equal("A fractured fairy tale", record.Headline);
    }

    // Bibliography is a courtesy that survives what the wild does to
    // it: XML that will not parse, a file with no story record, a story
    // with neither section, an empty field, and a field that opens with
    // markup rather than words all answer quietly rather than loudly.
    [Fact]
    public void AnUnreadableRecordIsQuietlyNothing()
    {
        Assert.Null(Babel.Ifiction(Ascii("<ifindex>")));
        Assert.Null(Babel.Ifiction([]));
        Assert.Null(Babel.Ifiction(Ascii("<ifindex><other/></ifindex>")));

        var bare = Babel.Ifiction(Ascii("<ifindex><story/></ifindex>"));

        Assert.NotNull(bare);
        Assert.Null(bare.Ifid);
        Assert.Null(bare.Title);
        Assert.Null(bare.Author);
        Assert.Null(bare.Headline);

        // The title here is a single non-breaking space. Ordinary
        // whitespace never survives the reader, which drops a
        // whitespace-only node before anyone can look at it, but a
        // record written by hand can still hold a field that is
        // blank in substance rather than in bytes.
        var thin = Babel.Ifiction(
            Ascii(
                "<ifindex><story><bibliographic><title>&#160;</title>"
                + "<author><b>x</b></author><headline/>"
                + "</bibliographic></story></ifindex>"));

        Assert.NotNull(thin);
        Assert.Null(thin.Title);
        Assert.Null(thin.Author);
        Assert.Null(thin.Headline);
    }

    // The catalog names the games that shipped before there were
    // records to name them, and nothing else.
    [Fact]
    public void TheCatalogNamesTheGamesThatPredateTheTreaty()
    {
        Assert.Equal("Zork 1", Infocom.Title("ZCODE-88-840726"));
        Assert.Equal("Zork Zero", Infocom.Title("ZCODE-393-890714"));
        Assert.Null(Infocom.Title("ZCODE-11-060503-1234"));
        Assert.Null(Infocom.Title(null));
    }
}
