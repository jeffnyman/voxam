using System.Text;
using Voxam.Core.Glulx;
using GlulxException = Voxam.Core.GlulxException;

namespace Voxam.Tests.Glulx;

/// <summary>
/// Saving and restoring the machine state (Glulx: The Save-Game
/// Format): a Quetzal container holding IFhd to name the story, CMem
/// for dynamic memory XOR-compressed against the game file, MAll for
/// the allocation heap, and Stks for the stack whole.
///
/// The undo opcodes are the way in, since they write the same format
/// and read it back; a Glk stream cannot be named until the Glk era,
/// so save and restore themselves answer the spoken failure.
/// </summary>
public sealed class SerialTests
{
    private const uint Flag = 0x140;
    private const uint Mark = 0x144;

    // A state put by and taken back: the memory a story wrote after
    // saving is gone again, and the opcode that saved speaks -1 the
    // second time through, which is how a story knows it has been
    // restored rather than saved.
    [Fact]
    public void AnUndoStatePutsBackTheMemoryWrittenAfterIt()
    {
        var program = new GlulxProgram();
        program.Op(Op.Saveundo, Modes.Memory(Mark));
        // Only the pass that has not been restored writes the flag.
        program.Op(Op.Jnz, Modes.Memory(Mark), Modes.Constant(1));
        program.Op(Op.Astore, Modes.Constant(Flag), Modes.Constant(0), Modes.Constant(9));
        program.Op(Op.Restoreundo, Modes.Discard);
        program.Op(Op.Quit);
        var machine = program.Booted();
        machine.Run(200);

        // The store landed, the undo took it away, and the second
        // pass through the saveundo instruction spoke -1.
        Assert.Equal(0u, machine.Memory.ReadWord((int)Flag));
        Assert.Equal(0xFFFFFFFFu, machine.Memory.ReadWord((int)Mark));
        Assert.True(machine.Discontinuity);
    }

    // hasundo promises what restoreundo will do, and discardundo
    // takes the promise back.
    [Fact]
    public void TheChainAnswersForWhatItHolds()
    {
        var program = new GlulxProgram();
        program.Op(Op.Hasundo, Modes.Memory(0x150));
        program.Op(Op.Saveundo, Modes.Discard);
        program.Op(Op.Hasundo, Modes.Memory(0x154));
        program.Op(Op.Discardundo);
        // And once more with nothing left to let go of.
        program.Op(Op.Discardundo);
        program.Op(Op.Hasundo, Modes.Memory(0x158));
        program.Op(Op.Restoreundo, Modes.Memory(0x15C));
        program.Op(Op.Quit);
        var machine = program.Booted();
        machine.Run(200);

        Assert.Equal(1u, machine.Memory.ReadWord(0x150));
        Assert.Equal(0u, machine.Memory.ReadWord(0x154));
        Assert.Equal(1u, machine.Memory.ReadWord(0x158));
        // Nothing left to restore, so the opcode speaks its failure.
        Assert.Equal(1u, machine.Memory.ReadWord(0x15C));
        Assert.Empty(machine.UndoChain);
    }

    // The chain keeps the newest handful and lets the oldest go.
    [Fact]
    public void TheChainKeepsOnlyTheNewestHandful()
    {
        var machine = Booted();

        for (var at = 0; at < 12; at++)
        {
            machine.Memory.WriteWord((int)Flag, (uint)at);
            Serial.SaveUndo(machine);
        }

        Assert.Equal(8, machine.UndoChain.Count);

        machine.Memory.WriteWord((int)Flag, 99);
        Serial.RestoreUndo(machine);

        // The newest state came back, which is the eleventh.
        Assert.Equal(11u, machine.Memory.ReadWord((int)Flag));
    }

    // Everything the format carries, put by and taken back: the map's
    // own size, the memory in it, the heap above it, and the stack.
    [Fact]
    public void TheWholeStateSurvivesTheRoundTrip()
    {
        var machine = Booted();
        machine.Memory.WriteWord((int)Flag, 0x11223344);
        machine.Memory.SetSize(2048);
        machine.Memory.WriteWord(1500, 0xCAFEF00D);
        var block = machine.Heap.Alloc(64);
        machine.Memory.WriteWord((int)block, 0xDEADBEEF);
        machine.Stack.Push(0x55667788);
        machine.Stack.PushStub(DestType.Discard, 0, 0);

        var saved = Serial.Serialize(machine);

        machine.Memory.WriteWord((int)Flag, 0);
        machine.Memory.WriteWord(1500, 0);
        machine.Heap.Clear();
        machine.Memory.SetSize(1024);

        Serial.Deserialize(machine, saved);

        Assert.Equal(0x11223344u, machine.Memory.ReadWord((int)Flag));
        Assert.Equal(0xCAFEF00Du, machine.Memory.ReadWord(1500));
        Assert.Equal((uint)block, (uint)machine.Heap.Start);
        Assert.Equal(1, machine.Heap.AllocCount);
        Assert.Equal(0xDEADBEEFu, machine.Memory.ReadWord((int)block));
        Assert.Equal(DestType.Discard, machine.Stack.PopStub().DestType);
        Assert.Equal(0x55667788u, machine.Stack.Pop());
    }

    // A run of zeroes packs into two bytes however long it is, and a
    // trailing run is left out entirely, the decoder treating
    // anything past the chunk as unchanged.
    [Fact]
    public void UnchangedMemoryCostsAlmostNothingToSave()
    {
        var machine = Booted();
        var bare = Serial.Serialize(machine);

        machine.Memory.WriteByte(1000, 0xFF);
        var marked = Serial.Serialize(machine);

        // A whole untouched map is a handful of bytes, and one changed
        // byte costs only the runs on either side of it.
        Assert.True(bare.Length < 200, $"an untouched save took {bare.Length} bytes");
        Assert.True(marked.Length < bare.Length + 16, $"one byte cost {marked.Length - bare.Length} bytes");
    }

    // A map grown since the save comes back the size it was, and one
    // shrunk comes back grown again.
    [Theory]
    [InlineData(1024)]
    [InlineData(4096)]
    public void TheMapComesBackTheSizeItWasSaved(int size)
    {
        var machine = Booted();
        machine.Memory.SetSize(size);
        machine.Memory.WriteWord(600, 0xABCDEF01);
        var saved = Serial.Serialize(machine);

        machine.Memory.SetSize(8192);
        machine.Memory.WriteWord(600, 0);

        Serial.Deserialize(machine, saved);

        Assert.Equal(size, machine.Memory.EndMem);
        Assert.Equal(0xABCDEF01u, machine.Memory.ReadWord(600));
    }

    // The protected range is silently unaffected by a restore, and it
    // is no part of what a save file carries.
    [Fact]
    public void AProtectedRangeIsUntouchedByARestore()
    {
        var machine = Booted();
        var saved = Serial.Serialize(machine);

        machine.Memory.SetProtection(0x150, 4);
        machine.Memory.WriteWord(0x150, 0x12345678);

        Serial.Deserialize(machine, saved);

        Assert.Equal(0x12345678u, machine.Memory.ReadWord(0x150));
    }

    // A UMem chunk says the size and then the memory raw, which a
    // save file is allowed to carry instead of the packed kind.
    [Fact]
    public void APlainMemoryChunkIsReadTheSameWay()
    {
        var machine = Booted();
        var identity = machine.Memory.ReadRun(0, 128);
        var ram = new byte[machine.Memory.EndMem - machine.Memory.RamStart];
        ram[0] = 0x42;

        Serial.Deserialize(machine, Form(
            Chunk("IFhd", identity),
            Chunk("UMem", [.. Word(1024), .. ram]),
            Chunk("Stks", [])));

        Assert.Equal(0x42, machine.Memory.ReadByte(machine.Memory.RamStart));
    }

    [Theory]
    [InlineData("not an iff file at all", "the save file is not an IFF container: no FORM chunk to open it (Quetzal 8.5)")]
    [InlineData("tiny", "the save file is not an IFF container: no FORM chunk to open it (Quetzal 8.5)")]
    public void BytesThatAreNoSaveFileAreRefused(string text, string message)
    {
        var machine = Booted();

        Assert.Equal(message, Refusal(() => Serial.Deserialize(machine, Encoding.ASCII.GetBytes(text))));
    }

    [Fact]
    public void AContainerThatIsNotQuetzalsIsRefused()
    {
        var machine = Booted();

        Assert.Equal(
            "the save file is a IFRS FORM, not Quetzal's IFZS",
            Refusal(() => Serial.Deserialize(machine, [.. Ascii("FORM"), .. Word(4), .. Ascii("IFRS")])));
        Assert.Equal(
            "the FORM chunk claims 400 bytes, but the file has only 4 after its header (Quetzal 8.3.5)",
            Refusal(() => Serial.Deserialize(machine, [.. Ascii("FORM"), .. Word(400), .. Ascii("IFZS")])));
    }

    [Fact]
    public void AChunkThatOverrunsTheFormIsRefused()
    {
        var machine = Booted();

        Assert.Equal(
            "a chunk is cut short mid-header (Quetzal 8.3.1)",
            Refusal(() => Serial.Deserialize(machine, [.. Ascii("FORM"), .. Word(8), .. Ascii("IFZS"), 1, 2, 3, 4])));
        Assert.Equal(
            "the IFhd chunk claims 400 bytes, but the FORM ends before them (Quetzal 8.4)",
            Refusal(() => Serial.Deserialize(machine, [.. Ascii("FORM"), .. Word(12), .. Ascii("IFZS"), .. Ascii("IFhd"), .. Word(400)])));
    }

    [Fact]
    public void ASaveFileMissingWhatItNeedsIsRefused()
    {
        var machine = Booted();
        var identity = machine.Memory.ReadRun(0, 128);

        Assert.Equal(
            "the save file has no IFhd chunk to name its story",
            Refusal(() => Serial.Deserialize(machine, Form(Chunk("Stks", [])))));
        Assert.Equal(
            "the save file belongs to a different story",
            Refusal(() => Serial.Deserialize(machine, Form(Chunk("IFhd", new byte[128])))));
        Assert.Equal(
            "the save file has no memory chunk",
            Refusal(() => Serial.Deserialize(machine, Form(Chunk("IFhd", identity)))));
        Assert.Equal(
            "the save file has no Stks chunk",
            Refusal(() => Serial.Deserialize(machine, Form(Chunk("IFhd", identity), Chunk("CMem", Word(1024))))));
        Assert.Equal(
            "the save file's memory chunk cannot hold its own size",
            Refusal(() => Serial.Deserialize(machine, Form(Chunk("IFhd", identity), Chunk("CMem", [1, 2])))));
        Assert.Equal(
            "a zero byte ends the memory chunk with no run length",
            Refusal(() => Serial.Deserialize(machine, Form(Chunk("IFhd", identity), Chunk("CMem", [.. Word(1024), 0])))));
    }

    // The heap summary is start, count, then an address and a length
    // for each block that is still claimed.
    [Fact]
    public void AHeapSummaryNamesEveryBlockStillClaimed()
    {
        var machine = Booted();

        Assert.Empty(machine.Heap.Summary());

        var first = machine.Heap.Alloc(16);
        var second = machine.Heap.Alloc(32);
        machine.Heap.Free(first);

        Assert.Equal([(uint)machine.Heap.Start, 1u, second, 32u], machine.Heap.Summary());
    }

    [Fact]
    public void AHeapSummaryThatContradictsItselfIsRefused()
    {
        var machine = Booted();

        Assert.Equal(
            "the save file's heap summary is cut short mid-block",
            Refusal(() => machine.Heap.ApplySummary([1024, 1, 1024])));
        Assert.Equal(
            "the save file's heap blocks are out of address order",
            Refusal(() => machine.Heap.ApplySummary([1024, 2, 1100, 16, 1050, 16])));

        machine.Heap.Alloc(16);

        Assert.Equal(
            "a heap summary cannot land on an active heap",
            Refusal(() => machine.Heap.ApplySummary([1024, 1, 1024, 16])));
    }

    // The free blocks are rebuilt from the gaps between the extant
    // ones, and from whatever is left over out to the end of the map.
    [Fact]
    public void AHeapSummaryRebuildsTheGapsBetweenItsBlocks()
    {
        var machine = Booted();
        machine.Memory.SetSize(2048);
        machine.Heap.ApplySummary([1024, 2, 1040, 16, 1080, 32]);

        Assert.True(machine.Heap.Active);
        Assert.Equal(1024, machine.Heap.Start);
        Assert.Equal(2, machine.Heap.AllocCount);
        Assert.Equal(
            [(1024, 16L, true), (1040, 16L, false), (1056, 24L, true), (1080, 32L, false), (1112, 936L, true)],
            machine.Heap.Blocks.Select(block => (block.Address, block.Length, block.Free)));
    }

    // A block that runs to the end of the map leaves no free space
    // behind it at all.
    [Fact]
    public void AHeapFilledToItsEndHasNoFreeSpaceLeft()
    {
        var machine = Booted();
        machine.Memory.SetSize(2048);
        machine.Heap.ApplySummary([1024, 1, 1024, 1024]);

        Assert.Equal([(1024, 1024L, false)], machine.Heap.Blocks.Select(block => (block.Address, block.Length, block.Free)));
    }

    // A summary saying nothing, and one saying the heap was inactive,
    // both leave the heap alone.
    [Fact]
    public void ASummaryOfNothingLeavesTheHeapAlone()
    {
        var machine = Booted();
        machine.Heap.ApplySummary([]);
        machine.Heap.ApplySummary([0, 0]);

        Assert.False(machine.Heap.Active);
    }

    // A stream is named by a Glk stream identifier, and there is no
    // registry to name one in yet, so both opcodes speak the failure
    // a game learns to prompt again from.
    [Fact]
    public void SaveAndRestoreSpeakTheirFailureUntilAStreamCanBeNamed()
    {
        var program = new GlulxProgram();
        program.Op(Op.Save, Modes.Constant(0), Modes.Memory(0x150));
        program.Op(Op.Restore, Modes.Constant(0), Modes.Memory(0x154));
        program.Op(Op.Quit);
        var machine = program.Booted();
        machine.Run(200);

        Assert.Equal(1u, machine.Memory.ReadWord(0x150));
        Assert.Equal(1u, machine.Memory.ReadWord(0x154));
    }

    private static Machine Booted() => new(new Story(new GlulxProgram().Build()), 7);

    private static byte[] Form(params byte[][] chunks) =>
        [.. Ascii("FORM"), .. Word((uint)(4 + chunks.Sum(chunk => chunk.Length))), .. Ascii("IFZS"), .. chunks.SelectMany(chunk => chunk)];

    private static byte[] Chunk(string id, byte[] payload) => payload.Length % 2 == 0
        ? [.. Ascii(id), .. Word((uint)payload.Length), .. payload]
        : [.. Ascii(id), .. Word((uint)payload.Length), .. payload, 0];

    private static byte[] Ascii(string text) => Encoding.ASCII.GetBytes(text);

    private static byte[] Word(uint value) => [(byte)(value >> 24), (byte)(value >> 16), (byte)(value >> 8), (byte)value];

    private static string Refusal(Action work) => Assert.Throws<GlulxException>(work).Message;
}
