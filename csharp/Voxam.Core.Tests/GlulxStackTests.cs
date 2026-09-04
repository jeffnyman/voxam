using Voxam.Core.Glulx;

namespace Voxam.Core.Tests;

/// <summary>
/// The Glulx stack: byte-addressed, growing upward from zero, big
/// endian, and strictly aligned where main memory is not (Glulx: The
/// Stack, Glulx: The Call Frame, Glulx: Call Stubs).
/// </summary>
public sealed class GlulxStackTests
{
    private const int Size = 1024;

    [Fact]
    public void AStackOffItsBoundaryOrBelowItIsRefused()
    {
        Assert.Equal("a stack of 128 bytes is not a multiple of 256 at least 256 tall (Glulx: The Stack)", Refusal(() => _ = new StackMemory(128)));
        Assert.Equal("a stack of 300 bytes is not a multiple of 256 at least 256 tall (Glulx: The Stack)", Refusal(() => _ = new StackMemory(300)));
        Assert.Equal(256, new StackMemory(256).Size);
    }

    // Values go on and come off in the order they were pushed, and
    // the stack knows how many stand above the current frame.
    [Fact]
    public void ValuesPushAndPopAndAreCounted()
    {
        var stack = new StackMemory(Size);
        stack.Push(1);
        stack.Push(0xDEADBEEF);

        Assert.Equal(2, stack.Count);
        Assert.Equal(0xDEADBEEFu, stack.Pop());
        Assert.Equal(1u, stack.Pop());
        Assert.Equal(0, stack.Count);
    }

    // A pop may not eat the call frame beneath the value stack, and
    // a push may not leave the stack's own top.
    [Fact]
    public void APushOffTheTopOrAPopIntoTheFrameIsRefused()
    {
        var stack = new StackMemory(256);

        for (var at = 0; at < 64; at++)
        {
            stack.Push((uint)at);
        }

        Assert.Equal("the 256-byte stack overflowed (Glulx: The Stack)", Refusal(() => stack.Push(0)));

        var empty = new StackMemory(256);
        Assert.Equal("the stack underflowed: popping past the value stack would eat the call frame (Glulx: The Call Frame)", Refusal(() => empty.Pop()));
    }

    // stkpeek reads without popping, and cannot reach past the value
    // stack either.
    [Fact]
    public void APeekReadsWithoutPoppingAndStopsAtTheValueStack()
    {
        var stack = new StackMemory(Size);
        stack.Push(10);
        stack.Push(20);
        stack.Push(30);

        Assert.Equal(30u, stack.Peek());
        Assert.Equal(10u, stack.Peek(2));
        Assert.Equal(3, stack.Count);
        Assert.Equal("a peek 3 deep reaches past the value stack (Glulx: The Call Frame)", Refusal(() => stack.Peek(3)));
    }

    // Shorts sit at even positions and words at multiples of four; a
    // program that breaks that has undefined behavior, and undefined
    // behavior is caught here.
    [Fact]
    public void EveryWidthReadsAndWritesOnItsOwnAlignment()
    {
        var stack = new StackMemory(Size);
        stack.WriteByte(0, 0x1234);
        stack.WriteShort(2, 0x123456);
        stack.WriteWord(4, 0xDEADBEEF);

        Assert.Equal(0x34u, stack.ReadByte(0));
        Assert.Equal(0x3456u, stack.ReadShort(2));
        Assert.Equal(0xDEADBEEFu, stack.ReadWord(4));
        Assert.Equal(0xDEADBEEFu, stack.Read(4, 4));
        Assert.Equal(0xDEu, stack.Read(4, 1));
        Assert.Equal(0xDEADu, stack.Read(4, 2));
    }

    [Fact]
    public void AWriteTakesTheWidthItIsGiven()
    {
        var stack = new StackMemory(Size);
        stack.Write(0, 4, 0x11223344);
        stack.Write(4, 1, 0x55);
        stack.Write(6, 2, 0x6677);

        Assert.Equal(0x11223344u, stack.ReadWord(0));
        Assert.Equal(0x55u, stack.ReadByte(4));
        Assert.Equal(0x6677u, stack.ReadShort(6));
    }

    // Off the stack says so; on the stack but off its alignment says
    // that instead.
    [Fact]
    public void AnAccessOffTheStackOrOffItsAlignmentIsRefused()
    {
        var stack = new StackMemory(Size);

        Assert.Equal("a 1-byte access at -1 is off the 1024-byte stack (Glulx: The Stack)", Refusal(() => stack.ReadByte(-1)));
        Assert.Equal("a 1-byte access at 1024 is off the 1024-byte stack (Glulx: The Stack)", Refusal(() => stack.ReadByte(Size)));
        Assert.Equal("a 2-byte access at 1023 is off the 1024-byte stack (Glulx: The Stack)", Refusal(() => stack.ReadShort(Size - 1)));
        Assert.Equal("a 2-byte access at -2 is off the 1024-byte stack (Glulx: The Stack)", Refusal(() => stack.ReadShort(-2)));
        Assert.Equal("a 2-byte stack access at 1 is off its natural alignment (Glulx: The Call Frame)", Refusal(() => stack.ReadShort(1)));
        Assert.Equal("a 4-byte access at 1021 is off the 1024-byte stack (Glulx: The Stack)", Refusal(() => stack.ReadWord(Size - 3)));
        Assert.Equal("a 4-byte access at -4 is off the 1024-byte stack (Glulx: The Stack)", Refusal(() => stack.ReadWord(-4)));
        Assert.Equal("a 4-byte stack access at 2 is off its natural alignment (Glulx: The Call Frame)", Refusal(() => stack.ReadWord(2)));

        Assert.Equal("a 1-byte access at -1 is off the 1024-byte stack (Glulx: The Stack)", Refusal(() => stack.WriteByte(-1, 0)));
        Assert.Equal("a 1-byte access at 1024 is off the 1024-byte stack (Glulx: The Stack)", Refusal(() => stack.WriteByte(Size, 0)));
        Assert.Equal("a 2-byte access at -2 is off the 1024-byte stack (Glulx: The Stack)", Refusal(() => stack.WriteShort(-2, 0)));
        Assert.Equal("a 2-byte access at 1023 is off the 1024-byte stack (Glulx: The Stack)", Refusal(() => stack.WriteShort(Size - 1, 0)));
        Assert.Equal("a 2-byte stack access at 1 is off its natural alignment (Glulx: The Call Frame)", Refusal(() => stack.WriteShort(1, 0)));
        Assert.Equal("a 4-byte access at -4 is off the 1024-byte stack (Glulx: The Stack)", Refusal(() => stack.WriteWord(-4, 0)));
        Assert.Equal("a 4-byte access at 1021 is off the 1024-byte stack (Glulx: The Stack)", Refusal(() => stack.WriteWord(Size - 3, 0)));
        Assert.Equal("a 4-byte stack access at 2 is off its natural alignment (Glulx: The Call Frame)", Refusal(() => stack.WriteWord(2, 0)));
    }

    // A frame is a header, a locals-format list ending in a zero
    // pair, and the zeroed locals themselves; the format list pads to
    // a word, which is why an odd list gets a second terminator.
    [Theory]
    [InlineData(4, 1, 4, 16, 12)]
    [InlineData(1, 3, 4, 16, 12)]
    [InlineData(2, 2, 4, 16, 12)]
    public void AFrameIsBuiltFromItsLocalsFormat(int size, int count, int localsLength, int frameLen, int localsPos)
    {
        var stack = new StackMemory(Size);
        stack.PushFrame([new LocalsFormat(size, count)]);

        Assert.Equal(0, stack.FramePtr);
        Assert.Equal(localsPos, stack.LocalsBase);
        Assert.Equal(localsLength, stack.LocalsLength);
        Assert.Equal((uint)frameLen, stack.FrameLen);
        Assert.Equal((uint)localsPos, stack.LocalsPos);
        Assert.Equal(frameLen, stack.Sp);
        Assert.Equal(0, stack.Count);
        Assert.Equal([new LocalsFormat(size, count)], stack.ReadLocalsFormat());
    }

    // Each run of locals pads up to its own alignment before it
    // starts: a byte then a word puts the word at offset 4, not 1.
    [Fact]
    public void EachRunOfLocalsPadsUpToItsOwnAlignment()
    {
        var stack = new StackMemory(Size);
        stack.PushFrame([new LocalsFormat(1, 1), new LocalsFormat(4, 1)]);

        Assert.Equal(8, stack.LocalsLength);
        // An odd list of entries takes a second zero pair to stay
        // word-aligned, so the locals start eight bytes past the
        // header rather than four.
        Assert.Equal(16, stack.LocalsBase);
        Assert.Equal([new LocalsFormat(1, 1), new LocalsFormat(4, 1)], stack.ReadLocalsFormat());

        stack.SetLocal(0, 0xFF, 1);
        stack.SetLocal(4, 0xCAFEF00D);

        Assert.Equal(0xFFu, stack.GetLocal(0, 1));
        Assert.Equal(0xCAFEF00Du, stack.GetLocal(4));
    }

    [Fact]
    public void ALocalsFormatOutsideItsTypesOrItsByteIsRefused()
    {
        var stack = new StackMemory(Size);

        Assert.Equal("a locals-format list may hold types 1, 2, and 4, not 3 (Glulx: The Call Frame)", Refusal(() => stack.PushFrame([new LocalsFormat(3, 1)])));
        Assert.Equal("a locals-format count of 256 does not fit its byte (Glulx: The Call Frame)", Refusal(() => stack.PushFrame([new LocalsFormat(4, 256)])));
        Assert.Equal("a locals-format count of -1 does not fit its byte (Glulx: The Call Frame)", Refusal(() => stack.PushFrame([new LocalsFormat(4, -1)])));
    }

    [Fact]
    public void AFrameTallerThanTheStackIsRefused()
    {
        var stack = new StackMemory(256);

        Assert.Equal("the 256-byte stack overflowed building a call frame (Glulx: The Call Frame)", Refusal(() => stack.PushFrame([new LocalsFormat(4, 255)])));
    }

    // A stack with no frame on it has no locals format to read, and
    // the reader stops at the locals rather than running on.
    [Fact]
    public void AStackWithNoFrameHasNoLocalsFormat()
    {
        Assert.Empty(new StackMemory(Size).ReadLocalsFormat());
    }

    // The specification is explicit that a local reference must not
    // point outside the current function's locals segment, a check
    // glulxe skips and this one makes.
    [Fact]
    public void ALocalReferenceOutsideTheSegmentIsRefused()
    {
        var stack = new StackMemory(Size);
        stack.PushFrame([new LocalsFormat(4, 2)]);
        const string Outside = "a local reference at offset {0} points outside the current function's locals segment (Glulx: The Call Frame)";

        Assert.Equal(string.Format(null, Outside, -1), Refusal(() => stack.GetLocal(-1)));
        Assert.Equal(string.Format(null, Outside, 8), Refusal(() => stack.GetLocal(8)));
        Assert.Equal(string.Format(null, Outside, -1), Refusal(() => stack.SetLocal(-1, 0)));
        Assert.Equal(string.Format(null, Outside, 8), Refusal(() => stack.SetLocal(8, 0)));
    }

    [Fact]
    public void LocalsComeUpZeroedAndReadBackAtEveryWidth()
    {
        var stack = new StackMemory(Size);
        stack.PushFrame([new LocalsFormat(2, 2)]);

        Assert.Equal(0u, stack.GetLocal(0, 2));

        stack.SetLocal(0, 0x1234, 2);
        stack.SetLocal(2, 0x5678, 2);

        Assert.Equal(0x1234u, stack.GetLocal(0, 2));
        Assert.Equal(0x12345678u, stack.GetLocal(0));
    }

    // A call leaves four words saying how to come home, and popping
    // them puts the caller's frame back with its derived bases.
    [Fact]
    public void ACallStubSaysHowToComeHome()
    {
        var stack = new StackMemory(Size);
        stack.PushFrame([new LocalsFormat(4, 2)]);
        stack.Push(7);
        stack.PushStub(DestType.Memory, 0x100, 0x200);
        var outer = stack.LocalsBase;
        stack.PushFrame([new LocalsFormat(4, 1)]);

        Assert.NotEqual(0, stack.FramePtr);

        stack.LeaveFrame();
        var stub = stack.PopStub();

        Assert.Equal(new CallStub(DestType.Memory, 0x100, 0x200, 0), stub);
        Assert.Equal(0, stack.FramePtr);
        Assert.Equal(outer, stack.LocalsBase);
        Assert.Equal(7u, stack.Pop());
    }

    [Fact]
    public void AStubOffTheTopOrPoppedFromNothingIsRefused()
    {
        var stack = new StackMemory(256);

        for (var at = 0; at < 61; at++)
        {
            stack.Push((uint)at);
        }

        Assert.Equal("the 256-byte stack overflowed pushing a call stub (Glulx: Call Stubs)", Refusal(() => stack.PushStub(DestType.Discard, 0, 0)));
        Assert.Equal("the stack underflowed popping a call stub (Glulx: Call Stubs)", Refusal(() => new StackMemory(256).PopStub()));
    }

    // restart's share of the work: the stack comes back empty and
    // frameless.
    [Fact]
    public void AResetClearsTheStackWhole()
    {
        var stack = new StackMemory(Size);
        stack.PushFrame([new LocalsFormat(4, 1)]);
        stack.Push(9);
        stack.Reset();

        Assert.Equal(0, stack.Sp);
        Assert.Equal(0, stack.FramePtr);
        Assert.Equal(0, stack.LocalsBase);
        Assert.Equal(0, stack.ValStackBase);
        Assert.Equal(0u, stack.ReadWord(0));
    }

    // The save format wants the stack big-endian, which is already
    // how it is stored, so a snapshot is a straight copy.
    [Fact]
    public void ASnapshotIsTheLiveBytesAndRestoresFromThem()
    {
        var stack = new StackMemory(Size);
        stack.Push(0x01020304);
        stack.Push(0x05060708);
        var saved = stack.Snapshot();

        Assert.Equal([1, 2, 3, 4, 5, 6, 7, 8], saved);

        var other = new StackMemory(Size);
        other.Push(99);
        other.Restore(saved);

        Assert.Equal(8, other.Sp);
        Assert.Equal(0, other.FramePtr);
        Assert.Equal(0x05060708u, other.Pop());
    }

    [Fact]
    public void ASnapshotThatCannotBeTheStackIsRefused()
    {
        var stack = new StackMemory(256);

        Assert.Equal("a saved stack of 512 bytes cannot fit this interpreter's 256-byte stack (Glulx: Contents of the Stack)", Refusal(() => stack.Restore(new byte[512])));
        Assert.Equal("a saved stack of 6 bytes is not a whole number of words (Glulx: Contents of the Stack)", Refusal(() => stack.Restore(new byte[6])));
    }

    // The message a refusal carried, so a test can read it plainly.
    private static string Refusal(Action work) => Assert.Throws<GlulxException>(work).Message;
}
