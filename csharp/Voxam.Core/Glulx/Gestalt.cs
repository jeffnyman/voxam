using System.Reflection;

namespace Voxam.Core.Glulx;

/// <summary>The selector numbers the gestalt opcode answers (Glulx: Gestalt).</summary>
public enum Selector : uint
{
    GlulxVersion = 0,
    TerpVersion = 1,
    ResizeMem = 2,
    Undo = 3,
    IoSystem = 4,
    Unicode = 5,
    MemCopy = 6,
    Malloc = 7,
    MallocHeap = 8,
    Acceleration = 9,
    AccelFunc = 10,
    Floats = 11,
    ExtUndo = 12,
    Doubles = 13,
}

/// <summary>
/// What this build of the machine can currently do.
///
/// Every false below is not a design decision but a statement that
/// the supporting era has not arrived, with the era named beside it;
/// the branch that builds an era flips its flag.
/// </summary>
public sealed record Capabilities
{
    /// <summary>setmemsize works; the memory era built it.</summary>
    public bool ResizeMem { get; init; } = true;

    /// <summary>mzero and mcopy work; the execution-loop era.</summary>
    public bool MemCopy { get; init; } = true;

    /// <summary>E2 strings, the wide nodes and streamunichar; the strings era.</summary>
    public bool Unicode { get; init; } = true;

    /// <summary>malloc and mfree; the heap era carried them.</summary>
    public bool Malloc { get; init; } = true;

    /// <summary>accelfunc and accelparam; the acceleration era carried them.</summary>
    public bool Acceleration { get; init; } = true;

    /// <summary>saveundo and restoreundo; the save era carried them.</summary>
    public bool Undo { get; init; } = true;

    /// <summary>hasundo and discardundo; the same era carried them.</summary>
    public bool ExtUndo { get; init; } = true;

    /// <summary>The single-precision opcodes; the float era carried them.</summary>
    public bool Floats { get; init; } = true;

    /// <summary>The double-precision opcodes; the same era carried them.</summary>
    public bool Doubles { get; init; } = true;

    /// <summary>A Glk library is installed, so the Glk output system works.</summary>
    public bool Glk { get; init; }
}

/// <summary>
/// Gestalt selectors: what this interpreter can do (Glulx: Gestalt).
///
/// The reference glulxe answers most of these from compile-time
/// switches; these are answered from a runtime value instead, which
/// lets the capability set track which eras exist yet.
/// </summary>
public static class Gestalt
{
    /// <summary>
    /// The Glulx specification version implemented: 3.1.3, packed as
    /// the header packs it (Glulx: The Header).
    /// </summary>
    public const uint GlulxVersion = 0x00030103;

    private const int MajorShift = 16;
    private const int MinorShift = 8;

    // The io systems the IoSystem selector is asked about.
    private const uint IoSysNull = 0;
    private const uint IoSysFilter = 1;
    private const uint IoSysGlk = 2;

    /// <summary>
    /// This interpreter's own version, packed the way the header packs
    /// one: release 1.2.3 answers 0x00010203. Read off the assembly,
    /// so the answer can never drift from what the port versions at.
    /// </summary>
    public static uint TerpVersion
    {
        get
        {
            // The build stamps a version on every assembly, so there
            // is always one here to read.
            var version = typeof(Gestalt).Assembly.GetName().Version!;

            return ((uint)version.Major << MajorShift) | ((uint)version.Minor << MinorShift) | (uint)version.Build;
        }
    }

    /// <summary>
    /// One gestalt query, answered honestly. Unknown selectors answer
    /// zero rather than erring: that is how a program written against
    /// a future specification probes an older interpreter (Glulx:
    /// Gestalt).
    /// </summary>
    public static uint Answer(Machine machine, uint selector, uint argument) => (Selector)selector switch
    {
        Selector.GlulxVersion => GlulxVersion,
        Selector.TerpVersion => TerpVersion,
        Selector.ResizeMem => Flag(machine.Capabilities.ResizeMem),
        Selector.Undo => Flag(machine.Capabilities.Undo),
        Selector.IoSystem => IoSystem(machine, argument),
        Selector.Unicode => Flag(machine.Capabilities.Unicode),
        Selector.MemCopy => Flag(machine.Capabilities.MemCopy),
        Selector.Malloc => Flag(machine.Capabilities.Malloc),
        // The heap's start address, or zero with no blocks extant.
        Selector.MallocHeap => (uint)machine.Heap.Start,
        Selector.Acceleration => Flag(machine.Capabilities.Acceleration),
        // Per function: which numbers this interpreter can replace.
        Selector.AccelFunc => Flag(Accelerator.Available.Contains(argument)),
        Selector.Floats => Flag(machine.Capabilities.Floats),
        Selector.ExtUndo => Flag(machine.Capabilities.ExtUndo),
        Selector.Doubles => Flag(machine.Capabilities.Doubles),
        _ => 0,
    };

    // The null and filter systems always work; Glk is its own era's
    // promise to keep.
    private static uint IoSystem(Machine machine, uint argument) => argument switch
    {
        IoSysNull or IoSysFilter => 1,
        IoSysGlk => Flag(machine.Capabilities.Glk),
        _ => 0,
    };

    private static uint Flag(bool answer) => answer ? 1u : 0u;
}
