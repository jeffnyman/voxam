using Voxam.Core.Glulx;
using Voxam.Core.Tests.Support;

namespace Voxam.Core.Tests;

/// <summary>
/// The Glulx memory map: ROM below RAMSTART held sacred, RAM above
/// it writable to ENDMEM, and everything past EXTSTART born zeroed
/// (Glulx: The Memory Map). The default map here has ROM to 256, the
/// stored image ending at 512, and the map ending at 1024.
/// </summary>
public sealed class GlulxMemoryTests
{
    private const int Rom = 100;
    private const int Ram = 300;
    private const int Above = 600;
    private const int EndMem = 1024;

    // Memory has no alignment rule: a four-byte read at an odd
    // address is legal Glulx.
    [Fact]
    public void ReadsComeInEveryWidthAtAnyAlignment()
    {
        var memory = Mapped(new GlulxBuilder().Lay(Ram, 0x12, 0x34, 0x56, 0x78));

        Assert.Equal(0x12, memory.ReadByte(Ram));
        Assert.Equal(0x3456, memory.ReadShort(Ram + 1));
        Assert.Equal(0x12345678u, memory.ReadWord(Ram));
        Assert.Equal(0x34567800u, memory.ReadWord(Ram + 1));
    }

    // The width an operand came in picks the accessor.
    [Fact]
    public void AReadTakesTheWidthItsOperandAsksFor()
    {
        var memory = Mapped(new GlulxBuilder().Lay(Ram, 0x12, 0x34, 0x56, 0x78));

        Assert.Equal(0x12345678u, memory.Read(Ram, 4));
        Assert.Equal(0x12u, memory.Read(Ram, 1));
        Assert.Equal(0x1234u, memory.Read(Ram, 2));
    }

    // The address a refusal names is the 32-bit one the story asked
    // for, which is why an address the machine holds as negative
    // comes back as the high word it really is.
    [Fact]
    public void AReadOutsideTheMapIsRefused()
    {
        var memory = Mapped();

        Assert.Equal("the address $ffffffff is outside the memory map (Glulx: The Memory Map)", Refusal(() => memory.ReadByte(-1)));
        Assert.Equal("the address $400 is outside the memory map (Glulx: The Memory Map)", Refusal(() => memory.ReadByte(EndMem)));
        Assert.Equal("the address $ffffffff is outside the memory map (Glulx: The Memory Map)", Refusal(() => memory.ReadShort(-1)));
        Assert.Equal("the address $3ff is outside the memory map (Glulx: The Memory Map)", Refusal(() => memory.ReadShort(EndMem - 1)));
        Assert.Equal("the address $ffffffff is outside the memory map (Glulx: The Memory Map)", Refusal(() => memory.ReadWord(-1)));
        Assert.Equal("the address $3fd is outside the memory map (Glulx: The Memory Map)", Refusal(() => memory.ReadWord(EndMem - 3)));
    }

    // The last short and the last word both end exactly at ENDMEM.
    [Fact]
    public void AReadEndingAtTheMapsEndIsAllowed()
    {
        var memory = Mapped();

        Assert.Equal(0, memory.ReadShort(EndMem - 2));
        Assert.Equal(0u, memory.ReadWord(EndMem - 4));
    }

    // An empty run needs no address at all, so nothing is checked
    // for it.
    [Fact]
    public void ARunReadsWhatItCoversAndNothingWhenItIsEmpty()
    {
        var memory = Mapped(new GlulxBuilder().Lay(Ram, 1, 2, 3));

        Assert.Equal([1, 2, 3], memory.ReadRun(Ram, 3));
        Assert.Equal([], memory.ReadRun(-5, 0));
        Assert.Equal("the address $ffffffff is outside the memory map (Glulx: The Memory Map)", Refusal(() => memory.ReadRun(-1, 2)));
        Assert.Equal("the address $3ff is outside the memory map (Glulx: The Memory Map)", Refusal(() => memory.ReadRun(EndMem - 1, 2)));
    }

    // The decoder reads straight from the backing store rather than
    // through an accessor, so memory hands the store over whole; a
    // resize replaces it, which is why nothing may hold on to it.
    [Fact]
    public void TheBackingStoreIsHandedOverWholeAndReplacedByAResize()
    {
        var memory = Mapped(new GlulxBuilder().Lay(Ram, 5));
        var before = memory.Data;

        Assert.Equal(5, before[Ram]);
        Assert.Equal(EndMem, before.Length);

        memory.SetSize(2048);

        Assert.NotSame(before, memory.Data);
        Assert.Equal(2048, memory.Data.Length);
    }

    [Fact]
    public void WritesComeInEveryWidthAndAreMaskedToIt()
    {
        var memory = Mapped();
        memory.WriteByte(Ram, 0x1234);
        memory.WriteShort(Ram + 1, 0x123456);
        memory.WriteWord(Ram + 4, 0xDEADBEEF);

        Assert.Equal(0x34, memory.ReadByte(Ram));
        Assert.Equal(0x3456, memory.ReadShort(Ram + 1));
        Assert.Equal(0xDEADBEEFu, memory.ReadWord(Ram + 4));
    }

    [Fact]
    public void AWriteTakesTheWidthItsOperandAsksFor()
    {
        var memory = Mapped();
        memory.Write(Ram, 4, 0x11223344);
        memory.Write(Ram + 4, 1, 0x55);
        memory.Write(Ram + 6, 2, 0x6677);

        Assert.Equal(0x11223344u, memory.ReadWord(Ram));
        Assert.Equal(0x55, memory.ReadByte(Ram + 4));
        Assert.Equal(0x6677, memory.ReadShort(Ram + 6));
    }

    // ROM says why it refused; past the end says only that it is
    // past the end.
    [Fact]
    public void AWriteIntoRomOrOffTheMapIsRefused()
    {
        var memory = Mapped();
        const string InRom = "the address $64 is in ROM, which ends at $100: it is illegal to write there (Glulx: The Memory Map)";

        Assert.Equal(InRom, Refusal(() => memory.WriteByte(Rom, 1)));
        Assert.Equal(InRom, Refusal(() => memory.WriteShort(Rom, 1)));
        Assert.Equal(InRom, Refusal(() => memory.WriteWord(Rom, 1)));
        Assert.Equal("the address $400 is outside the memory map (Glulx: The Memory Map)", Refusal(() => memory.WriteByte(EndMem, 1)));
        Assert.Equal("the address $3ff is outside the memory map (Glulx: The Memory Map)", Refusal(() => memory.WriteShort(EndMem - 1, 1)));
        Assert.Equal("the address $3fd is outside the memory map (Glulx: The Memory Map)", Refusal(() => memory.WriteWord(EndMem - 3, 1)));
    }

    // An empty run writes nowhere, so not even ROM minds it.
    [Fact]
    public void ARunWritesWhatItCoversAndAnEmptyOneWritesNowhere()
    {
        var memory = Mapped();
        memory.WriteRun(Ram, [1, 2, 3]);
        memory.WriteRun(Rom, []);

        Assert.Equal([1, 2, 3], memory.ReadRun(Ram, 3));
        Assert.Equal(0, memory.ReadByte(Rom));
        Assert.Equal("the address $64 is in ROM, which ends at $100: it is illegal to write there (Glulx: The Memory Map)", Refusal(() => memory.WriteRun(Rom, [1])));
    }

    // mzero's work: a run of RAM set to one value.
    [Fact]
    public void AFillSetsARunAndAnEmptyOneSetsNothing()
    {
        var memory = Mapped();
        memory.Fill(Ram, 4, 0xFF);
        memory.Fill(Rom, 0);

        Assert.Equal(0xFFFFFFFFu, memory.ReadWord(Ram));
        Assert.Equal("the address $3ff is outside the memory map (Glulx: The Memory Map)", Refusal(() => memory.Fill(EndMem - 1, 2)));
    }

    // mcopy's work, and the overlap it must survive: the source is
    // read whole before a byte of it lands.
    [Fact]
    public void ACopyMovesARunEvenWhereItOverlapsItself()
    {
        var memory = Mapped();
        memory.WriteRun(Ram, [1, 2, 3, 4]);
        memory.Copy(Ram + 8, Ram, 4);
        memory.Copy(Ram + 2, Ram, 4);
        memory.Copy(Ram, Ram, 0);

        Assert.Equal([1, 2, 3, 4], memory.ReadRun(Ram + 8, 4));
        Assert.Equal([1, 2, 1, 2, 3, 4], memory.ReadRun(Ram, 6));
    }

    [Fact]
    public void ACopyLeavingTheMapOrTouchingRomIsRefused()
    {
        var memory = Mapped();

        Assert.Equal("the address $3ff is outside the memory map (Glulx: The Memory Map)", Refusal(() => memory.Copy(Ram, EndMem - 1, 4)));
        Assert.Equal("the address $64 is in ROM, which ends at $100: it is illegal to write there (Glulx: The Memory Map)", Refusal(() => memory.Copy(Rom, Ram, 4)));
    }

    // setmemsize's work: growth is zero-filled, and the map never
    // shrinks below the ENDMEM it booted with.
    [Fact]
    public void TheMapGrowsAndShrinksBetweenItsBootSizeAndWhatever()
    {
        var memory = Mapped();
        memory.WriteByte(Ram, 7);
        memory.SetSize(2048);

        Assert.Equal(2048, memory.EndMem);
        Assert.Equal(7, memory.ReadByte(Ram));
        Assert.Equal(0, memory.ReadByte(1500));

        memory.WriteByte(1500, 9);
        memory.SetSize(EndMem);

        Assert.Equal(EndMem, memory.EndMem);
        Assert.Equal("the address $5dc is outside the memory map (Glulx: The Memory Map)", Refusal(() => memory.ReadByte(1500)));
    }

    [Fact]
    public void AResizeOffItsBoundaryOrBelowTheBootSizeIsRefused()
    {
        var memory = Mapped();

        Assert.Equal("a memory size of 1000 is not a multiple of 256 (Glulx: Game State)", Refusal(() => memory.SetSize(1000)));
        Assert.Equal("memory cannot shrink to 768, below the 1024 it booted with (Glulx: Game State)", Refusal(() => memory.SetSize(768)));
    }

    // restart's work: the boot image whole again, and the boot size
    // with it, so a grown map does not survive.
    [Fact]
    public void AResetLaysTheBootImageBackAndTheBootSizeWithIt()
    {
        var memory = Mapped(new GlulxBuilder().Lay(Ram, 5));
        memory.WriteByte(Ram, 6);
        memory.SetSize(2048);
        memory.Reset();

        Assert.Equal(5, memory.ReadByte(Ram));
        Assert.Equal(EndMem, memory.EndMem);
    }

    // The protected range is silently unaffected by a restart, with
    // no qualification about where it lies, so it survives even above
    // EXTSTART.
    [Fact]
    public void AProtectedRangeSurvivesAReset()
    {
        var memory = Mapped(new GlulxBuilder().Lay(Ram, 5));
        memory.SetProtection(Ram, 1);
        memory.WriteByte(Ram, 6);
        memory.WriteByte(Above, 8);
        memory.Reset();

        Assert.Equal(6, memory.ReadByte(Ram));
        Assert.Equal(0, memory.ReadByte(Above));
    }

    // A range running past the end of the map is kept only as far as
    // the map goes.
    [Fact]
    public void AProtectedRangeIsClippedToTheMapItComesBackInto()
    {
        var memory = Mapped();
        memory.SetSize(2048);
        memory.WriteRun(EndMem - 2, [1, 2, 3, 4]);
        memory.SetProtection(EndMem - 2, 4);
        memory.Reset();

        Assert.Equal([1, 2], memory.ReadRun(EndMem - 2, 2));
    }

    // A range that has come to lie entirely above the map has
    // nowhere to be laid back.
    [Fact]
    public void AProtectedRangeAboveTheMapIsSimplyLost()
    {
        var memory = Mapped();
        memory.SetSize(2048);
        memory.WriteByte(1536, 3);
        memory.SetProtection(1536, 256);
        memory.Reset();

        Assert.Equal(EndMem, memory.EndMem);
        Assert.Equal("the address $600 is outside the memory map (Glulx: The Memory Map)", Refusal(() => memory.ReadByte(1536)));
    }

    // One range exists at a time, and a zero length turns protection
    // off.
    [Fact]
    public void AZeroLengthTurnsProtectionOff()
    {
        var memory = Mapped(new GlulxBuilder().Lay(Ram, 5));
        memory.SetProtection(Ram, 1);
        memory.SetProtection(Ram, 0);
        memory.WriteByte(Ram, 6);
        memory.Reset();

        Assert.Equal(5, memory.ReadByte(Ram));
    }

    // The compressed save format XORs live RAM against the original
    // image, as if the game file were extended with as many zeroes as
    // necessary above EXTSTART.
    [Fact]
    public void TheOriginalImageAnswersInZeroesAboveWhereItEnds()
    {
        var memory = Mapped(new GlulxBuilder().Lay(508, 1, 2, 3, 4));

        Assert.Equal([1, 2, 3, 4], memory.OriginalRun(508, 4));
        Assert.Equal([3, 4, 0, 0], memory.OriginalRun(510, 4));
        Assert.Equal([0, 0], memory.OriginalRun(Above, 2));
    }

    // A restore lays RAM back from RAMSTART, and where no range is
    // protected that is the whole of it.
    [Fact]
    public void ARestoreLaysRamBackFromRamstart()
    {
        var memory = Mapped();
        memory.OverwriteRam(Run(768, 9));

        Assert.Equal(9, memory.ReadByte(256));
        Assert.Equal(9, memory.ReadByte(EndMem - 1));
    }

    // The protected range is silently unaffected by a restore,
    // wherever in the restored span it falls.
    [Theory]
    [InlineData(300, 100, 300, 400)]
    [InlineData(256, 100, 256, 356)]
    [InlineData(900, 124, 900, EndMem)]
    [InlineData(256, 768, 256, EndMem)]
    public void ARestoreSparesWhateverRangeIsProtected(int start, int length, int keptFrom, int keptTo)
    {
        var memory = Mapped();
        memory.Fill(256, 768, 4);
        memory.SetProtection(start, length);
        memory.OverwriteRam(Run(768, 9));

        for (var at = 256; at < EndMem; at++)
        {
            Assert.Equal(at >= keptFrom && at < keptTo ? 4 : 9, memory.ReadByte(at));
        }
    }

    // A run of one value, as a restore's contents.
    private static byte[] Run(int length, byte value)
    {
        var run = new byte[length];
        Array.Fill(run, value);

        return run;
    }

    // The message a refusal carried, so a test can read it plainly.
    private static string Refusal(Action work) => Assert.Throws<GlulxException>(work).Message;

    // The one place the Glulx map is named, the Z-machine having a
    // Memory of its own.
    private static Voxam.Core.Glulx.Memory Mapped(GlulxBuilder? builder = null) =>
        new(new Story((builder ?? new GlulxBuilder()).Build()));
}
