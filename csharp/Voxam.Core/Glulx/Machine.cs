using System.Collections.Frozen;
using Voxam.Core.Glulx.Glk;

namespace Voxam.Core.Glulx;

/// <summary>
/// One opcode's operand signature beside its handler, so a step costs
/// a single lookup.
/// </summary>
public readonly record struct Dispatch(OperandList Oplist, Action<Machine, Operand[]> Handler);

/// <summary>
/// The Glulx machine: the fetch-decode-execute loop.
///
/// Each step reads an opcode number, inline because this runs once
/// per instruction, looks up its operand signature and handler in one
/// combined table, decodes the operands, and executes. The eras this
/// machine does not carry yet answer by name from the full opcode
/// roster and halt as the frontier they are, never as a mystery.
///
/// The handlers receive their operands as a plain array: unsigned
/// 32-bit values for loads, StoreTargets for stores, in exactly the
/// shapes the dispatch table's signatures promise. The 32-bit
/// discipline was enforced a layer down, so the arithmetic here is
/// ordinary unsigned arithmetic, masked only where a store leaves the
/// machine. Where an opcode reads its operand as a signed number, the
/// cast to int is that reading: the Python has to spell it out only
/// because its integers have no width of their own.
/// </summary>
public sealed class Machine
{
    private const uint SignBit = 0x8000_0000;
    private const int ShiftLimit = 32;
    private const int BitIndexMask = 0b111;
    private const int ByteWidth = 1;
    private const int ShortWidth = 2;
    private const int WordWidth = 4;
    private const int OneByteOpcodeLimit = 0x80;
    private const int TwoByteOpcodeLimit = 0xC0;
    private const int TwoByteOpcodeBase = 0x8000;
    private const uint FourByteOpcodeBase = 0xC000_0000;

    // A branch offset of 0 or 1 does not jump: it returns 0 or 1 from
    // the current function, and offsets otherwise count from just
    // past the instruction, less two (Glulx: Branches).
    private const uint ReturnZeroOffset = 0;
    private const uint ReturnOneOffset = 1;
    private const uint BranchAdjustment = 2;

    // What a popped save stub stores after a restore: "you have just
    // been restored and are continuing from this instruction" (Glulx:
    // Game State).
    private const uint Restored = 0xFFFFFFFF;

    private readonly Story _story;
    private readonly Randomizer _random;

    // One entry per instruction address below RAMSTART, holding
    // everything about that instruction that its bytes settle. The
    // story cannot write there, so nothing ever falls out of date
    // (Glulx: The Memory Map).
    private readonly Dictionary<int, Held> _shapes = [];

    // And one entry per function address below RAMSTART, for the same
    // reason and on the same terms.
    private readonly Dictionary<int, FunctionHeader> _headers = [];

    /// <summary>
    /// Boot the machine: memory laid, stack raised, start function
    /// called. A seed makes the dice reproducible; none means true
    /// entropy.
    /// </summary>
    public Machine(Story story, int? seed = null, IGlkOutput? glk = null, GlkLibrary? library = null)
    {
        _story = story;
        Glk = glk;
        Library = library;
        Memory = new Memory(story);
        Heap = new Heap(Memory);
        Accel = new Accelerator(Memory);
        Capabilities = new Capabilities { Glk = glk is not null };
        Stack = new StackMemory(story.StackSize);
        Bridge = library is null ? null : new Bridge(Memory, library, Stack);
        IoSys = new IoSystem();
        // The generator is deliberately not reseeded by a restart: it
        // is no part of saved state either (Glulx: The Random Number
        // Generator).
        _random = new Randomizer(seed);

        Restart();
    }

    /// <summary>
    /// Whether the roster carries a handler for an opcode. Every opcode
    /// Glulx 3.1.3 defines does; the answer is here so a test can hold
    /// the table to that promise.
    /// </summary>
    /// <param name="opcode">The opcode number to ask about.</param>
    public static bool Carries(int opcode) => Table.ContainsKey(opcode);

    /// <summary>
    /// The program counter. The string decoder moves it too, since a
    /// print that suspends into a function has to say where the
    /// machine picks back up.
    /// </summary>
    public int Pc { get; internal set; }

    /// <summary>The live memory map.</summary>
    public Memory Memory { get; }

    /// <summary>The value stack.</summary>
    public StackMemory Stack { get; }

    /// <summary>The dynamic allocation heap (Glulx: Memory Allocation Heap).</summary>
    public Heap Heap { get; }

    /// <summary>The acceleration table (Glulx: Accelerated Functions).</summary>
    public Accelerator Accel { get; }

    /// <summary>What this build of the machine can do (Glulx: Gestalt).</summary>
    public Capabilities Capabilities { get; }

    /// <summary>
    /// The states saveundo has put by, newest last. The chain is not
    /// part of saved state and does not survive a restart of the
    /// process, only of the story.
    /// </summary>
    public List<byte[]> UndoChain { get; } = [];

    /// <summary>Which output system is current (Glulx: Output).</summary>
    public IoSystem IoSys { get; }

    /// <summary>
    /// Where Glk output goes, or null with no library installed. What
    /// the machine can do follows from this: installing a library is
    /// what lets setiosys select the Glk system at all, so the
    /// fallback and the refusal tell the same truth.
    /// </summary>
    public IGlkOutput? Glk { get; }

    /// <summary>
    /// The Glk library the glk opcode dispatches into, or null with
    /// none installed. Separate from the output seat above for now: the
    /// output system was wired in the string era, when a library was
    /// still a frontier, and joining the two is the api era's to do.
    /// </summary>
    public GlkLibrary? Library { get; }

    /// <summary>
    /// The seam between this machine and its library, or null with no
    /// library installed.
    /// </summary>
    public Bridge? Bridge { get; }

    /// <summary>The string-decoding table's address; 0 means none.</summary>
    public uint StringTable { get; private set; }

    /// <summary>Whether execution has not yet been halted by quit.</summary>
    public bool Running { get; private set; }

    /// <summary>
    /// Instructions executed across the whole session, kept so an
    /// instrument can measure the machine's own pace.
    /// </summary>
    public long Instructions { get; private set; }

    /// <summary>
    /// An undo, restore, or restart broke the causal thread; a face
    /// that tracks continuity reads this once and rests it.
    /// </summary>
    public bool Discontinuity { get; set; }

    /// <summary>
    /// Return to the load state and call the start function. The
    /// protected range deliberately survives, memory's own reset
    /// honoring it, and execution begins by calling the header's start
    /// function with no arguments (Glulx: Game State, Glulx: The
    /// Header).
    /// </summary>
    public void Restart()
    {
        // The heap goes first, before the map is rebuilt: it does not
        // survive a restart (Glulx: Memory Allocation Heap).
        Heap.Clear();
        Memory.Reset();
        Stack.Reset();
        IoSys.Reset();
        StringTable = (uint)_story.DecodingTable;
        Running = true;
        Pc = Funcs.PushCallFrame(Memory, Stack, _story.StartFunction, [], _headers);
    }

    /// <summary>
    /// Fetch, decode, and execute a single instruction.
    ///
    /// An instruction below RAMSTART cannot change, so neither can its
    /// opcode, its handler, its operands' addressing modes, or the
    /// address it ends at (Glulx: The Memory Map). All of that is read
    /// once and kept, and every later visit does the one thing that is
    /// not fixed: fetching what the operands stand for. Code above
    /// RAMSTART is read afresh every time, since the story may write
    /// over it.
    /// </summary>
    /// <exception cref="GlulxException">
    /// For an opcode number the specification does not define, or one
    /// this machine does not carry yet, or any rule the instruction
    /// breaks.
    /// </exception>
    public void Step()
    {
        if (!_shapes.TryGetValue(Pc, out var held))
        {
            held = Shaped(Pc);
        }

        // Resolved before the program counter moves, so an operand
        // that refuses, an empty stack or a local outside the frame,
        // leaves the machine standing at the instruction that asked.
        var args = Operands.Resolve(Memory, Stack, held.Items, held.Width);
        Pc = held.After;

        held.Handler(this, args);
    }

    /// <summary>
    /// Execute until the story quits; the step count comes back. The
    /// limit is a test and debugging guard, not a specification
    /// feature: a runaway loop in a broken story should fail rather
    /// than hang.
    /// </summary>
    /// <exception cref="GlulxException">
    /// On exceeding the given limit, or any rule the story breaks.
    /// </exception>
    public long Run(long? limit = null)
    {
        var steps = 0L;

        // The tally is kept in a local and folded in once, from a
        // finally: a run that ends by raising must still say how far
        // the machine got.
        try
        {
            while (Running)
            {
                if (limit is not null && steps >= limit)
                {
                    throw new GlulxException($"execution exceeded {limit} instructions");
                }

                Step();
                steps++;
            }

            return steps;
        }
        finally
        {
            Instructions += steps;
        }
    }

    // Read one instruction's fixed half, keeping it if it can be.
    //
    // Kept only when the whole instruction lies below RAMSTART, which
    // is the memory the story can never write (Glulx: The Memory Map).
    // An instruction that reaches into RAM is shaped again on every
    // visit, so a story that writes its own code still runs the code
    // it wrote.
    private Held Shaped(int pc)
    {
        var memory = Memory;

        // Unsigned, so a program counter that wrapped past the top of
        // the map is caught here rather than indexing from the end.
        if ((uint)pc >= (uint)memory.EndMem)
        {
            throw new GlulxException($"execution ran off the memory map at ${pc:x} (Glulx: The Memory Map)");
        }

        int opcode;
        int at;
        var first = memory.Data[pc];

        if (first < OneByteOpcodeLimit)
        {
            opcode = first;
            at = pc + 1;
        }
        else if (first < TwoByteOpcodeLimit)
        {
            opcode = memory.ReadShort(pc) - TwoByteOpcodeBase;
            at = pc + 2;
        }
        else
        {
            opcode = (int)(memory.ReadWord(pc) - FourByteOpcodeBase);
            at = pc + 4;
        }

        if (!Table.TryGetValue(opcode, out var entry))
        {
            // The roster is whole: every opcode 3.1.3 defines has a
            // handler, which a test holds the table to. So a number
            // that misses the table is a number the specification does
            // not define, and there is no third case to speak for.
            throw new GlulxException(
                $"executed opcode {Opcode.Name(opcode)}, which Glulx 3.1.3 does not define (Glulx: Dictionary of Opcodes)");
        }

        var (items, after) = Operands.Shape(memory, at, entry.Oplist);
        var held = new Held(entry.Handler, items, entry.Oplist.ArgSize, after);

        if (after <= memory.RamStart)
        {
            _shapes[pc] = held;
        }

        return held;
    }

    internal void Store(StoreTarget target, uint value, int width = WordWidth) =>
        Operands.Store(Memory, Stack, target, value, width);

    // Branch by an offset, or return 0 or 1 (Glulx: Branches).
    internal void Jump(uint offset)
    {
        if (offset is ReturnZeroOffset or ReturnOneOffset)
        {
            Return(offset);
        }
        else
        {
            // The program counter already sits past the instruction,
            // hence the bias of two.
            Pc = (int)((uint)Pc + offset - BranchAdjustment);
        }
    }

    // Leave the current function; an empty stack ends the story.
    private void Return(uint value)
    {
        Stack.LeaveFrame();

        if (Stack.Sp == 0)
        {
            Running = false;

            return;
        }

        PopStub(value);
    }

    // Pop a call stub and act on it (Glulx: Call Stubs).
    private void PopStub(uint value)
    {
        var stub = Stack.PopStub();
        Pc = (int)stub.Pc;

        if (stub.DestType == DestType.ResumeFunction)
        {
            throw new GlulxException("a string-terminator call stub arrived where a function result belongs (Glulx: Call Stubs)");
        }

        if (stub.DestType is DestType.ResumeCompressed or DestType.ResumeNumber or DestType.ResumeCString or DestType.ResumeUnicode)
        {
            // A function called from inside a string has returned: its
            // value is discarded and the print picks up where it left
            // off (Glulx: Calling and Returning Within Strings).
            Strings.Resume(this, stub);

            return;
        }

        Store(new StoreTarget(stub.DestType, stub.DestAddr), value);
    }

    // Push the come-home stub, then enter the function.
    private void Call(uint addr, IReadOnlyList<uint> args, StoreTarget target)
    {
        Stack.PushStub(target.DestType, target.Addr, (uint)Pc);
        EnterFunction(addr, args);
    }

    /// <summary>
    /// Begin a call: every way of invoking a function lands here.
    ///
    /// This is what the specification means by a call including "any
    /// function invocation of that address", so the accelerated
    /// replacements intercept here, covering the call opcodes,
    /// tailcall, and the string-decoding table's function nodes alike
    /// (Glulx: Accelerated Functions). An accelerated function
    /// produces its result immediately, and the come-home stub the
    /// caller just pushed pops straight back off.
    /// </summary>
    internal void EnterFunction(uint addr, IReadOnlyList<uint> args)
    {
        if (Accel.Lookup(addr) is { } accelerated)
        {
            PopStub(accelerated(args));

            return;
        }

        Pc = Funcs.PushCallFrame(Memory, Stack, (int)addr, args, _headers);
    }

    // A bit number resolved to its byte address and the bit within.
    // Bits number sequentially in both directions from the least
    // significant bit of the base (Glulx: Array Data). An arithmetic
    // shift and a mask floor for negative operands, which is exactly
    // that rule; the reference glulxe needs an explicit negative
    // branch to get the same answer.
    private static (int Address, int Bit) BitAddress(uint start, uint index)
    {
        var offset = (int)index;

        return ((int)(start + (uint)(offset >> 3)), offset & BitIndexMask);
    }

    // Signed division truncating toward zero (Glulx: Integer Math).
    private static uint Divided(uint a, uint b)
    {
        var x = (int)a;
        var y = (int)b;

        if (y == 0)
        {
            throw new GlulxException("division by zero (Glulx: Integer Math)");
        }

        // The one dividend whose negation does not exist, which makes
        // the most negative value divided by -1 an overflow.
        if (y == -1 && x == int.MinValue)
        {
            throw new GlulxException("division overflow: the most negative value by -1");
        }

        return (uint)(x / y);
    }

    // Signed remainder, its sign the dividend's (Glulx: Integer Math).
    private static uint Remainder(uint a, uint b)
    {
        var x = (int)a;
        var y = (int)b;

        if (y == 0)
        {
            throw new GlulxException("division by zero taking a remainder (Glulx: Integer Math)");
        }

        if (y == -1 && x == int.MinValue)
        {
            throw new GlulxException("division overflow taking a remainder");
        }

        return (uint)(x % y);
    }

    private void OpAdd(Operand[] args) => Store(args[2].Target, args[0].Value + args[1].Value);

    private void OpSub(Operand[] args) => Store(args[2].Target, args[0].Value - args[1].Value);

    private void OpMul(Operand[] args) => Store(args[2].Target, args[0].Value * args[1].Value);

    private void OpDiv(Operand[] args) => Store(args[2].Target, Divided(args[0].Value, args[1].Value));

    private void OpMod(Operand[] args) => Store(args[2].Target, Remainder(args[0].Value, args[1].Value));

    private void OpNeg(Operand[] args) => Store(args[1].Target, 0u - args[0].Value);

    private void OpBitand(Operand[] args) => Store(args[2].Target, args[0].Value & args[1].Value);

    private void OpBitor(Operand[] args) => Store(args[2].Target, args[0].Value | args[1].Value);

    private void OpBitxor(Operand[] args) => Store(args[2].Target, args[0].Value ^ args[1].Value);

    private void OpBitnot(Operand[] args) => Store(args[1].Target, ~args[0].Value);

    // Shift left; 32 places or more leave nothing (Glulx: Integer Math).
    private void OpShiftl(Operand[] args)
    {
        var places = (int)args[1].Value;

        Store(args[2].Target, places >= 0 && places < ShiftLimit ? args[0].Value << places : 0);
    }

    // Shift right filling with zeros (Glulx: Integer Math).
    private void OpUshiftr(Operand[] args)
    {
        var places = (int)args[1].Value;

        Store(args[2].Target, places >= 0 && places < ShiftLimit ? args[0].Value >> places : 0);
    }

    // Shift right replicating the sign bit (Glulx: Integer Math).
    private void OpSshiftr(Operand[] args)
    {
        var places = (int)args[1].Value;
        var value = places >= 0 && places < ShiftLimit
            ? (uint)((int)args[0].Value >> places)
            : (args[0].Value & SignBit) != 0 ? uint.MaxValue : 0;

        Store(args[2].Target, value);
    }

    private void OpJump(Operand[] args) => Jump(args[0].Value);

    // Jump to an absolute address, no bias, no return codes.
    private void OpJumpabs(Operand[] args) => Pc = (int)args[0].Value;

    private void OpJz(Operand[] args)
    {
        if (args[0].Value == 0)
        {
            Jump(args[1].Value);
        }
    }

    private void OpJnz(Operand[] args)
    {
        if (args[0].Value != 0)
        {
            Jump(args[1].Value);
        }
    }

    private void OpJeq(Operand[] args)
    {
        if (args[0].Value == args[1].Value)
        {
            Jump(args[2].Value);
        }
    }

    private void OpJne(Operand[] args)
    {
        if (args[0].Value != args[1].Value)
        {
            Jump(args[2].Value);
        }
    }

    private void OpJlt(Operand[] args)
    {
        if ((int)args[0].Value < (int)args[1].Value)
        {
            Jump(args[2].Value);
        }
    }

    private void OpJge(Operand[] args)
    {
        if ((int)args[0].Value >= (int)args[1].Value)
        {
            Jump(args[2].Value);
        }
    }

    private void OpJgt(Operand[] args)
    {
        if ((int)args[0].Value > (int)args[1].Value)
        {
            Jump(args[2].Value);
        }
    }

    private void OpJle(Operand[] args)
    {
        if ((int)args[0].Value <= (int)args[1].Value)
        {
            Jump(args[2].Value);
        }
    }

    private void OpJltu(Operand[] args)
    {
        if (args[0].Value < args[1].Value)
        {
            Jump(args[2].Value);
        }
    }

    private void OpJgeu(Operand[] args)
    {
        if (args[0].Value >= args[1].Value)
        {
            Jump(args[2].Value);
        }
    }

    private void OpJgtu(Operand[] args)
    {
        if (args[0].Value > args[1].Value)
        {
            Jump(args[2].Value);
        }
    }

    private void OpJleu(Operand[] args)
    {
        if (args[0].Value <= args[1].Value)
        {
            Jump(args[2].Value);
        }
    }

    private void OpCall(Operand[] args) =>
        Call(args[0].Value, Funcs.PopArguments(Stack, args[1].Value, Memory), args[2].Target);

    private void OpCallf(Operand[] args) => Call(args[0].Value, [], args[1].Target);

    private void OpCallfi(Operand[] args) => Call(args[0].Value, [args[1].Value], args[2].Target);

    private void OpCallfii(Operand[] args) => Call(args[0].Value, [args[1].Value, args[2].Value], args[3].Target);

    private void OpCallfiii(Operand[] args) => Call(args[0].Value, [args[1].Value, args[2].Value, args[3].Value], args[4].Target);

    private void OpReturn(Operand[] args) => Return(args[0].Value);

    // Replace the frame without touching the stub below it.
    private void OpTailcall(Operand[] args)
    {
        var call = Funcs.PopArguments(Stack, args[1].Value, Memory);

        Stack.LeaveFrame();
        EnterFunction(args[0].Value, call);
    }

    // Push a stub, store its token, then branch. The order is the
    // specification's own: the offset was evaluated during operand
    // decoding, then the stub is pushed and the token, the resulting
    // stack pointer, computed, and only then is the token stored,
    // which matters when either lives on the stack (Glulx:
    // Continuations).
    private void OpCatch(Operand[] args)
    {
        var target = args[0].Target;

        Stack.PushStub(target.DestType, target.Addr, (uint)Pc);
        Store(target, (uint)Stack.Sp);
        Jump(args[1].Value);
    }

    // Unwind to a catch token and deliver a value there.
    private void OpThrow(Operand[] args)
    {
        var token = args[1].Value;

        if (token % WordWidth != 0 || token > (uint)Stack.Size)
        {
            throw new GlulxException($"a throw's catch token of {token} is not a place on this stack (Glulx: Continuations)");
        }

        Stack.Unwind((int)token);
        PopStub(args[0].Value);
    }

    private void OpCopy(Operand[] args) => Store(args[1].Target, args[0].Value);

    private void OpCopys(Operand[] args) => Store(args[1].Target, args[0].Value, ShortWidth);

    private void OpCopyb(Operand[] args) => Store(args[1].Target, args[0].Value, ByteWidth);

    private void OpSexs(Operand[] args) => Store(args[1].Target, Operands.SignExtend(args[0].Value, 16));

    private void OpSexb(Operand[] args) => Store(args[1].Target, Operands.SignExtend(args[0].Value, 8));

    private void OpAload(Operand[] args) =>
        Store(args[2].Target, Memory.ReadWord((int)(args[0].Value + (4 * args[1].Value))));

    private void OpAloads(Operand[] args) =>
        Store(args[2].Target, (uint)Memory.ReadShort((int)(args[0].Value + (2 * args[1].Value))));

    private void OpAloadb(Operand[] args) =>
        Store(args[2].Target, (uint)Memory.ReadByte((int)(args[0].Value + args[1].Value)));

    private void OpAloadbit(Operand[] args)
    {
        var (address, bit) = BitAddress(args[0].Value, args[1].Value);

        Store(args[2].Target, (Memory.ReadByte(address) & (1 << bit)) != 0 ? 1u : 0u);
    }

    private void OpAstore(Operand[] args) =>
        Memory.WriteWord((int)(args[0].Value + (4 * args[1].Value)), args[2].Value);

    private void OpAstores(Operand[] args) =>
        Memory.WriteShort((int)(args[0].Value + (2 * args[1].Value)), args[2].Value);

    private void OpAstoreb(Operand[] args) =>
        Memory.WriteByte((int)(args[0].Value + args[1].Value), args[2].Value);

    private void OpAstorebit(Operand[] args)
    {
        var (address, bit) = BitAddress(args[0].Value, args[1].Value);
        var value = (uint)Memory.ReadByte(address);

        value = args[2].Value != 0 ? value | (1u << bit) : value & ~(1u << bit);

        Memory.WriteByte(address, value);
    }

    private void OpStkcount(Operand[] args) => Store(args[0].Target, (uint)Stack.Count);

    // Peek by index; the index must name a value that exists.
    private void OpStkpeek(Operand[] args)
    {
        var index = (int)args[0].Value;

        if (index < 0 || index >= Stack.Count)
        {
            throw new GlulxException($"stkpeek at {index} reaches outside the current stack range (Glulx: The Stack)");
        }

        Store(args[1].Target, Stack.Peek(index));
    }

    private void OpStkswap(Operand[] args)
    {
        _ = args;

        if (Stack.Count < 2)
        {
            throw new GlulxException("stkswap with fewer than two values (Glulx: The Stack)");
        }

        var top = Stack.Pop();
        var below = Stack.Pop();

        Stack.Push(top);
        Stack.Push(below);
    }

    private void OpStkcopy(Operand[] args)
    {
        var count = (int)args[0].Value;

        if (count < 0)
        {
            throw new GlulxException("stkcopy with a negative count (Glulx: The Stack)");
        }

        if (count == 0)
        {
            return;
        }

        if (Stack.Count < count)
        {
            throw new GlulxException($"stkcopy of {count} exceeds the values above the frame");
        }

        var values = new uint[count];

        for (var at = 0; at < count; at++)
        {
            values[at] = Stack.Peek(count - 1 - at);
        }

        foreach (var value in values)
        {
            Stack.Push(value);
        }
    }

    // Rotate the top values by places, either direction. The reference
    // glulxe splits the rotation in two because C's remainder is
    // awkward for negative operands; the rotate-down distance is the
    // same for either sign once the remainder is floored (Glulx: The
    // Stack).
    private void OpStkroll(Operand[] args)
    {
        var count = (int)args[0].Value;
        var places = (int)args[1].Value;

        if (count < 0)
        {
            throw new GlulxException("stkroll with a negative count (Glulx: The Stack)");
        }

        if (Stack.Count < count)
        {
            throw new GlulxException($"stkroll of {count} exceeds the values above the frame");
        }

        if (count == 0)
        {
            return;
        }

        // Widened, because the most negative count of places has no
        // positive of its own to negate into.
        var shift = (int)(((-(long)places % count) + count) % count);

        if (shift == 0)
        {
            return;
        }

        var basement = Stack.Sp - (WordWidth * count);
        var values = new uint[count];

        for (var at = 0; at < count; at++)
        {
            values[at] = Stack.ReadWord(basement + (WordWidth * at));
        }

        for (var at = 0; at < count; at++)
        {
            Stack.WriteWord(basement + (WordWidth * at), values[(at + shift) % count]);
        }
    }

    // Save the state to a Glk stream (Glulx: Game State). The call
    // stub is pushed first, so it lands inside the save's own stack
    // chunk; popping it stores the spoken result and, after a later
    // restore, the same stub stores -1 and execution continues from
    // this very instruction (Glulx: Contents of the Stack).
    //
    // A stream is named by a Glk stream identifier, and with no
    // library installed there is no registry to name one in, so the
    // answer is the spoken failure a game learns to prompt again from.
    // The format such a stream would carry is already here, and
    // saveundo writes and reads it every turn.
    private void OpSave(Operand[] args)
    {
        var target = args[1].Target;

        Stack.PushStub(target.DestType, target.Addr, (uint)Pc);
        PopStub(Serial.Failed);
    }

    // Restore the state from a Glk stream. On success the restored
    // stack's own stub would pop with -1 and this instruction never
    // store at all; a failure speaks 1 in place, which is all there is
    // to speak until a stream can be named.
    private void OpRestore(Operand[] args) => Store(args[1].Target, Serial.Failed);

    // Call a Glk function by selector (Glulx: Miscellaneous). The
    // opcode always functions when a library is installed: Glk being
    // the current output system is not required (Glulx: Output).
    private void OpGlk(Operand[] args)
    {
        if (Bridge is null)
        {
            throw new GlulxException("the glk opcode needs a Glk library, and none is installed");
        }

        var call = Funcs.PopArguments(Stack, args[1].Value, Memory);

        Store(args[2].Target, Bridge.Perform((int)args[0].Value, call));
    }

    private void OpSaveUndo(Operand[] args)
    {
        var target = args[0].Target;

        Stack.PushStub(target.DestType, target.Addr, (uint)Pc);
        PopStub(Serial.SaveUndo(this));
    }

    private void OpRestoreUndo(Operand[] args)
    {
        if (Serial.RestoreUndo(this) == Serial.Succeeded)
        {
            Discontinuity = true;
            PopStub(Restored);

            return;
        }

        Store(args[0].Target, Serial.Failed);
    }

    private void OpGetstringtbl(Operand[] args) => Store(args[0].Target, StringTable);

    // Point the decoder at another table (Glulx: Output). The address
    // is taken on trust, exactly as the specification allows: a broken
    // table announces itself at the next compressed print, not here.
    private void OpSetstringtbl(Operand[] args) => StringTable = args[0].Value;

    private void OpGetiosys(Operand[] args)
    {
        Store(args[0].Target, IoSys.Mode);
        Store(args[1].Target, IoSys.Rock);
    }

    // Select the output system (Glulx: Output). Selecting an
    // unsupported system selects the null system, and Glk without a
    // library installed is exactly that, so the fallback here tells
    // the same truth the gestalt answer will once it exists.
    private void OpSetiosys(Operand[] args)
    {
        var mode = args[0].Value;
        var rock = args[1].Value;

        if (mode == (uint)IoMode.Glk && Glk is null)
        {
            mode = (uint)IoMode.Null;
            rock = 0;
        }

        IoSys.Select(mode, rock);
    }

    // Roll at three ranges (Glulx: The Random Number Generator). A
    // zero range asks for a full 32-bit value; a positive one for 0
    // through the range less one; a negative one for the mirror, the
    // range plus one through 0.
    private void OpRandom(Operand[] args)
    {
        var limit = (int)args[0].Value;
        var value = limit == 0
            ? _random.Word()
            : limit > 0 ? _random.Below((uint)limit) : 0u - _random.Below((uint)-(long)limit);

        Store(args[1].Target, value);
    }

    // Reseed the dice; zero asks for genuine unpredictability.
    private void OpSetrandom(Operand[] args) => _random.Seed(args[0].Value);

    private void OpGetmemsize(Operand[] args) => Store(args[0].Target, (uint)Memory.EndMem);

    // Resize the map; success stores 0 (Glulx: The Memory Map). The
    // opcode is illegal while the allocation heap is active, the heap
    // owning the map then (Glulx: Memory Allocation Heap).
    private void OpSetmemsize(Operand[] args)
    {
        if (Heap.Active)
        {
            throw new GlulxException("setmemsize is illegal while the allocation heap is active");
        }

        Memory.SetSize(args[0].Value);
        Store(args[1].Target, 0);
    }

    private void OpMzero(Operand[] args) => Memory.Fill((int)args[1].Value, args[0].Value);

    private void OpMcopy(Operand[] args) => Memory.Copy((int)args[2].Value, (int)args[1].Value, args[0].Value);

    private void OpProtect(Operand[] args) => Memory.SetProtection((int)args[0].Value, (int)args[1].Value);

    // Recompute the checksum: 0 for sound, 1 for not (Glulx: Game State).
    private void OpVerify(Operand[] args) => Store(args[0].Target, _story.Verify() ? 0u : 1u);

    private void OpQuit(Operand[] args)
    {
        _ = args;
        Running = false;
    }

    private void OpRestart(Operand[] args)
    {
        _ = args;
        Discontinuity = true;
        Restart();
    }

    // Halt loudly: this interpreter has no debugger to hand off to,
    // and the specification directs one with no debugging faculty to
    // treat the value as a fatal error and print it (Glulx:
    // Miscellaneous).
    private static void OpDebugtrap(Operand[] args) =>
        throw new GlulxException($"debugtrap with value {args[0].Value} (Glulx: Miscellaneous)");

    // One instruction's fixed half: the handler its opcode names, its
    // operands' shapes, the width the indirect modes move, and the
    // address the instruction ends at.
    private readonly record struct Held(Action<Machine, Operand[]> Handler, Shaped[] Items, int Width, int After);


    private static readonly OperandList None = new("");
    private static readonly OperandList L = new("L");
    private static readonly OperandList Ll = new("LL");
    private static readonly OperandList Lll = new("LLL");
    private static readonly OperandList S = new("S");
    private static readonly OperandList Ss = new("SS");
    private static readonly OperandList Ls = new("LS");
    private static readonly OperandList Sl = new("SL");
    private static readonly OperandList Lls = new("LLS");
    private static readonly OperandList Llls = new("LLLS");
    private static readonly OperandList Lllls = new("LLLLS");
    private static readonly OperandList Lllllls = new("LLLLLLS");
    private static readonly OperandList Llllllls = new("LLLLLLLS");

    private static readonly FrozenDictionary<int, Dispatch> Table = Built();

    // The machine's own opcodes, and then the float and double
    // families, which arrive as a prebuilt table of their own.
    private static FrozenDictionary<int, Dispatch> Built()
    {
        var table = new Dictionary<int, Dispatch>
        {
            // Do nothing, well (Glulx: Dictionary of Opcodes).
            [(int)Op.Nop] = new(None, static (_, _) => { }),
            [(int)Op.Add] = new(Lls, static (m, a) => m.OpAdd(a)),
            [(int)Op.Sub] = new(Lls, static (m, a) => m.OpSub(a)),
            [(int)Op.Mul] = new(Lls, static (m, a) => m.OpMul(a)),
            [(int)Op.Div] = new(Lls, static (m, a) => m.OpDiv(a)),
            [(int)Op.Mod] = new(Lls, static (m, a) => m.OpMod(a)),
            [(int)Op.Neg] = new(Ls, static (m, a) => m.OpNeg(a)),
            [(int)Op.Bitand] = new(Lls, static (m, a) => m.OpBitand(a)),
            [(int)Op.Bitor] = new(Lls, static (m, a) => m.OpBitor(a)),
            [(int)Op.Bitxor] = new(Lls, static (m, a) => m.OpBitxor(a)),
            [(int)Op.Bitnot] = new(Ls, static (m, a) => m.OpBitnot(a)),
            [(int)Op.Shiftl] = new(Lls, static (m, a) => m.OpShiftl(a)),
            [(int)Op.Sshiftr] = new(Lls, static (m, a) => m.OpSshiftr(a)),
            [(int)Op.Ushiftr] = new(Lls, static (m, a) => m.OpUshiftr(a)),
            [(int)Op.Jump] = new(L, static (m, a) => m.OpJump(a)),
            [(int)Op.Jumpabs] = new(L, static (m, a) => m.OpJumpabs(a)),
            [(int)Op.Jz] = new(Ll, static (m, a) => m.OpJz(a)),
            [(int)Op.Jnz] = new(Ll, static (m, a) => m.OpJnz(a)),
            [(int)Op.Jeq] = new(Lll, static (m, a) => m.OpJeq(a)),
            [(int)Op.Jne] = new(Lll, static (m, a) => m.OpJne(a)),
            [(int)Op.Jlt] = new(Lll, static (m, a) => m.OpJlt(a)),
            [(int)Op.Jge] = new(Lll, static (m, a) => m.OpJge(a)),
            [(int)Op.Jgt] = new(Lll, static (m, a) => m.OpJgt(a)),
            [(int)Op.Jle] = new(Lll, static (m, a) => m.OpJle(a)),
            [(int)Op.Jltu] = new(Lll, static (m, a) => m.OpJltu(a)),
            [(int)Op.Jgeu] = new(Lll, static (m, a) => m.OpJgeu(a)),
            [(int)Op.Jgtu] = new(Lll, static (m, a) => m.OpJgtu(a)),
            [(int)Op.Jleu] = new(Lll, static (m, a) => m.OpJleu(a)),
            [(int)Op.Call] = new(Lls, static (m, a) => m.OpCall(a)),
            [(int)Op.Callf] = new(Ls, static (m, a) => m.OpCallf(a)),
            [(int)Op.Callfi] = new(Lls, static (m, a) => m.OpCallfi(a)),
            [(int)Op.Callfii] = new(Llls, static (m, a) => m.OpCallfii(a)),
            [(int)Op.Callfiii] = new(Lllls, static (m, a) => m.OpCallfiii(a)),
            [(int)Op.Return] = new(L, static (m, a) => m.OpReturn(a)),
            [(int)Op.Tailcall] = new(Ll, static (m, a) => m.OpTailcall(a)),
            [(int)Op.Catch] = new(Sl, static (m, a) => m.OpCatch(a)),
            [(int)Op.Throw] = new(Ll, static (m, a) => m.OpThrow(a)),
            [(int)Op.Copy] = new(Ls, static (m, a) => m.OpCopy(a)),
            [(int)Op.Copys] = new(new OperandList("LS", ShortWidth), static (m, a) => m.OpCopys(a)),
            [(int)Op.Copyb] = new(new OperandList("LS", ByteWidth), static (m, a) => m.OpCopyb(a)),
            [(int)Op.Sexs] = new(Ls, static (m, a) => m.OpSexs(a)),
            [(int)Op.Sexb] = new(Ls, static (m, a) => m.OpSexb(a)),
            [(int)Op.Aload] = new(Lls, static (m, a) => m.OpAload(a)),
            [(int)Op.Aloads] = new(Lls, static (m, a) => m.OpAloads(a)),
            [(int)Op.Aloadb] = new(Lls, static (m, a) => m.OpAloadb(a)),
            [(int)Op.Aloadbit] = new(Lls, static (m, a) => m.OpAloadbit(a)),
            [(int)Op.Astore] = new(Lll, static (m, a) => m.OpAstore(a)),
            [(int)Op.Astores] = new(Lll, static (m, a) => m.OpAstores(a)),
            [(int)Op.Astoreb] = new(Lll, static (m, a) => m.OpAstoreb(a)),
            [(int)Op.Astorebit] = new(Lll, static (m, a) => m.OpAstorebit(a)),
            [(int)Op.Stkcount] = new(S, static (m, a) => m.OpStkcount(a)),
            [(int)Op.Stkpeek] = new(Ls, static (m, a) => m.OpStkpeek(a)),
            [(int)Op.Stkswap] = new(None, static (m, a) => m.OpStkswap(a)),
            [(int)Op.Stkroll] = new(Ll, static (m, a) => m.OpStkroll(a)),
            [(int)Op.Stkcopy] = new(L, static (m, a) => m.OpStkcopy(a)),
            // Print one character, its low byte, or the whole of it
            // (Glulx: Output).
            [(int)Op.Streamchar] = new(L, static (m, a) => Strings.PutChar(m, a[0].Value & 0xFF)),
            [(int)Op.Streamunichar] = new(L, static (m, a) => Strings.PutChar(m, a[0].Value)),
            [(int)Op.Streamnum] = new(L, static (m, a) => Strings.StreamNum(m, a[0].Value)),
            [(int)Op.Streamstr] = new(L, static (m, a) => Strings.StreamString(m, a[0].Value)),
            // Save and restore through a Glk stream (Glulx: Game State).
            // With no library installed there is no stream to name, so the
            // answer is the spoken failure a game learns to prompt again
            // from; the lookup arrives with the Glk era.
            [(int)Op.Save] = new(Ls, static (m, a) => m.OpSave(a)),
            [(int)Op.Restore] = new(Ls, static (m, a) => m.OpRestore(a)),
            [(int)Op.Saveundo] = new(S, static (m, a) => m.OpSaveUndo(a)),
            [(int)Op.Restoreundo] = new(S, static (m, a) => m.OpRestoreUndo(a)),
            [(int)Op.Hasundo] = new(S, static (m, a) => m.Store(a[0].Target, Serial.HasUndo(m))),
            [(int)Op.Discardundo] = new(None, static (m, _) => Serial.DiscardUndo(m)),

            // Call a Glk function by selector (Glulx: Miscellaneous).
            // The arguments come off the stack, first argument topmost,
            // just as the call opcodes leave them; any stack output
            // references push back before the result stores.
            [(int)Op.Glk] = new(Lls, static (m, a) => m.OpGlk(a)),

            // Claim and release heap memory (Glulx: Memory Allocation
            // Heap); the address stores, or zero for a refusal, since
            // allocation is never guaranteed.
            [(int)Op.Malloc] = new(Ls, static (m, a) => m.Store(a[1].Target, m.Heap.Alloc(a[0].Value))),
            [(int)Op.Mfree] = new(L, static (m, a) => m.Heap.Free(a[0].Value)),

            // Install or cancel a replacement, and set a veneer parameter
            // (Glulx: Accelerated Functions).
            [(int)Op.Accelfunc] = new(Ll, static (m, a) => m.Accel.SetFunc(a[0].Value, a[1].Value)),
            [(int)Op.Accelparam] = new(Ll, static (m, a) => m.Accel.SetParam(a[0].Value, a[1].Value)),

            // The three built-in searches (Glulx: Searching).
            [(int)Op.Linearsearch] = new(Llllllls, static (m, a) => m.Store(a[7].Target,
                Search.Linear(m.Memory, a[0].Value, a[1].Value, a[2].Value, a[3].Value, a[4].Value, a[5].Value, a[6].Value))),
            [(int)Op.Binarysearch] = new(Llllllls, static (m, a) => m.Store(a[7].Target,
                Search.Binary(m.Memory, a[0].Value, a[1].Value, a[2].Value, a[3].Value, a[4].Value, a[5].Value, a[6].Value))),
            [(int)Op.Linkedsearch] = new(Lllllls, static (m, a) => m.Store(a[6].Target,
                Search.Linked(m.Memory, a[0].Value, a[1].Value, a[2].Value, a[3].Value, a[4].Value, a[5].Value))),

            [(int)Op.Gestalt] = new(Lls, static (m, a) => m.Store(a[2].Target, Gestalt.Answer(m, a[0].Value, a[1].Value))),
            [(int)Op.Getstringtbl] = new(S, static (m, a) => m.OpGetstringtbl(a)),
            [(int)Op.Setstringtbl] = new(L, static (m, a) => m.OpSetstringtbl(a)),
            [(int)Op.Getiosys] = new(Ss, static (m, a) => m.OpGetiosys(a)),
            [(int)Op.Setiosys] = new(Ll, static (m, a) => m.OpSetiosys(a)),
            [(int)Op.Random] = new(Ls, static (m, a) => m.OpRandom(a)),
            [(int)Op.Setrandom] = new(L, static (m, a) => m.OpSetrandom(a)),
            [(int)Op.Getmemsize] = new(S, static (m, a) => m.OpGetmemsize(a)),
            [(int)Op.Setmemsize] = new(Ls, static (m, a) => m.OpSetmemsize(a)),
            [(int)Op.Mzero] = new(Ll, static (m, a) => m.OpMzero(a)),
            [(int)Op.Mcopy] = new(Lll, static (m, a) => m.OpMcopy(a)),
            [(int)Op.Protect] = new(Ll, static (m, a) => m.OpProtect(a)),
            [(int)Op.Verify] = new(S, static (m, a) => m.OpVerify(a)),
            [(int)Op.Quit] = new(None, static (m, a) => m.OpQuit(a)),
            [(int)Op.Restart] = new(None, static (m, a) => m.OpRestart(a)),
            [(int)Op.Debugtrap] = new(L, static (_, a) => OpDebugtrap(a)),
        };

        foreach (var (number, entry) in Floats.Entries())
        {
            table[number] = entry;
        }

        return table.ToFrozenDictionary();
    }
}
