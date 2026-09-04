using Voxam.Core.Glulx;
using GlulxException = Voxam.Core.GlulxException;

namespace Voxam.Tests.Glulx;

/// <summary>
/// The dynamic allocation heap (Glulx: Memory Allocation Heap).
/// Blocks live above ENDMEM, which starts at 1024 here; the first
/// malloc activates the heap and the last free hands the memory back.
/// </summary>
public sealed class HeapTests
{
    private const int BootEndMem = 1024;

    // The first allocation activates the heap: the end of memory
    // becomes its start, and the map grows from there.
    [Fact]
    public void TheFirstAllocationActivatesTheHeap()
    {
        var (memory, heap) = Standing();

        Assert.False(heap.Active);
        Assert.Equal(0, heap.Start);

        var block = heap.Alloc(16);

        Assert.True(heap.Active);
        Assert.Equal((uint)BootEndMem, block);
        Assert.Equal(BootEndMem, heap.Start);
        Assert.Equal(1, heap.AllocCount);
        // The map grew by one boundary, and the remainder is free.
        Assert.Equal(BootEndMem + 256, memory.EndMem);
        Assert.Equal(2, heap.Blocks.Count);
        Assert.Equal(16, heap.Blocks[0].Length);
        Assert.Equal(240, heap.Blocks[1].Length);
    }

    // Freeing the last block deactivates the heap and shrinks memory
    // back to where it began.
    [Fact]
    public void FreeingTheLastBlockHandsTheMemoryBack()
    {
        var (memory, heap) = Standing();
        var block = heap.Alloc(16);
        heap.Free(block);

        Assert.False(heap.Active);
        Assert.Equal(0, heap.AllocCount);
        Assert.Empty(heap.Blocks);
        Assert.Equal(BootEndMem, memory.EndMem);
    }

    // A block splits so the remainder stays free, and the list stays
    // in address order.
    [Fact]
    public void AllocationsSplitTheFreeSpaceInAddressOrder()
    {
        var (_, heap) = Standing();
        var first = heap.Alloc(16);
        var second = heap.Alloc(32);
        var third = heap.Alloc(8);

        Assert.Equal([first, second, third], (uint[])[(uint)BootEndMem, (uint)BootEndMem + 16, (uint)BootEndMem + 48]);
        Assert.Equal(3, heap.AllocCount);
        Assert.Equal([16L, 32L, 8L, 200L], heap.Blocks.Select(block => block.Length));
        Assert.Equal([false, false, false, true], heap.Blocks.Select(block => block.Free));
    }

    // Free neighbors merge only when something needs the space, as
    // the reference glulxe has it.
    [Fact]
    public void FreeNeighborsMergeWhenTheSpaceIsWanted()
    {
        var (_, heap) = Standing();
        var first = heap.Alloc(16);
        var second = heap.Alloc(16);
        var third = heap.Alloc(16);
        heap.Free(first);
        heap.Free(second);

        // Two free spans of sixteen sit side by side, and neither
        // alone can hold a twenty-four byte block.
        Assert.Equal([16L, 16L, 16L, 208L], heap.Blocks.Select(block => block.Length));

        var wanted = heap.Alloc(24);

        Assert.Equal(first, wanted);
        Assert.Equal([24L, 8L, 16L, 208L], heap.Blocks.Select(block => block.Length));
        Assert.Equal(2, heap.AllocCount);
        Assert.NotEqual(0u, third);
    }

    // The heap doubles, or grows by what was asked, or by one
    // boundary, whichever is largest.
    [Fact]
    public void TheHeapGrowsByWhicheverIsLargest()
    {
        var (memory, heap) = Standing();
        heap.Alloc(200);

        Assert.Equal(BootEndMem + 256, memory.EndMem);

        // A request the free remainder cannot hold grows the map
        // again, this time by the heap's whole extent.
        heap.Alloc(200);

        Assert.Equal(BootEndMem + 512, memory.EndMem);

        // And one larger than either doubling grows by its own size,
        // rounded up to the boundary.
        heap.Alloc(2000);

        Assert.Equal(BootEndMem + 512 + 2048, memory.EndMem);
    }

    // Allocation is never guaranteed: a refusal is an answer, not an
    // error.
    [Fact]
    public void AnAllocationTooLargeToMapIsRefusedWithZero()
    {
        var (_, heap) = Standing();

        Assert.Equal(0u, heap.Alloc(0x7FFFFFFF));
        Assert.False(heap.Active);
    }

    // A request that exactly fills the free space leaves nothing to
    // split off.
    [Fact]
    public void AnExactFitLeavesNoRemainder()
    {
        var (_, heap) = Standing();
        heap.Alloc(256);

        Assert.Equal([256L], heap.Blocks.Select(block => block.Length));
        Assert.Single(heap.Blocks);
    }

    // The opcodes ask the same things of the heap, and setmemsize is
    // illegal while it is active, the heap owning the map then.
    [Fact]
    public void TheOpcodesClaimAndReleaseAndLockTheMap()
    {
        var program = new GlulxProgram();
        program.Op(Op.Malloc, Modes.Constant(16), Modes.Memory(0x140));
        program.Op(Op.Getmemsize, Modes.Memory(0x144));
        program.Op(Op.Mfree, Modes.Memory(0x140));
        program.Op(Op.Getmemsize, Modes.Memory(0x148));
        program.Op(Op.Quit);
        var machine = program.Booted();
        machine.Run();

        Assert.Equal(1024u, machine.Memory.ReadWord(0x140));
        Assert.Equal(1280u, machine.Memory.ReadWord(0x144));
        Assert.Equal(1024u, machine.Memory.ReadWord(0x148));

        var locked = new GlulxProgram();
        locked.Op(Op.Malloc, Modes.Constant(16), Modes.Discard);
        locked.Op(Op.Setmemsize, Modes.Word(4096), Modes.Discard);
        locked.Op(Op.Quit);

        Assert.Equal(
            "setmemsize is illegal while the allocation heap is active",
            Assert.Throws<GlulxException>(() => locked.Booted().Run()).Message);
    }

    [Fact]
    public void AZeroLengthAllocationIsRefused()
    {
        var (_, heap) = Standing();

        Assert.Equal(
            "a heap allocation must ask for at least one byte",
            Assert.Throws<GlulxException>(() => heap.Alloc(0)).Message);
    }

    [Fact]
    public void FreeingWhatWasNeverAllocatedIsRefused()
    {
        var (_, heap) = Standing();
        var block = heap.Alloc(16);
        heap.Alloc(16);
        heap.Free(block);

        Assert.Equal(
            "no allocated heap block begins at 0x400",
            Assert.Throws<GlulxException>(() => heap.Free(block)).Message);
        Assert.Equal(
            "no allocated heap block begins at 0x999",
            Assert.Throws<GlulxException>(() => heap.Free(0x999)).Message);
    }

    // A restart clears the heap, which does not survive one.
    [Fact]
    public void AClearedHeapGivesItsMemoryBackAndAnInactiveOneHasNoneToGive()
    {
        var (memory, heap) = Standing();
        heap.Alloc(16);
        heap.Clear();

        Assert.False(heap.Active);
        Assert.Equal(BootEndMem, memory.EndMem);

        heap.Clear();

        Assert.Equal(BootEndMem, memory.EndMem);
    }

    private static (Memory Memory, Heap Heap) Standing()
    {
        var memory = new Memory(new Story(new GlulxBuilder().Build()));

        return (memory, new Heap(memory));
    }
}
