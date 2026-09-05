namespace Voxam.Core.Glulx.Glk;

/// <summary>
/// A Glk call standing down mid-session, waiting on something only the
/// host outside can supply.
///
/// A display that cannot block, one speaking a wire protocol to a
/// browser, never answers a read call. So the library records what it
/// waits for instead: the machine returns to its host, the host
/// collects the answer, and delivering it runs whatever the call left
/// parked here.
///
/// The one thing every wait parks is the bridge's writebacks. An empty
/// struct must not travel back into VM memory when the call returns, so
/// the bridge leaves the writes here and the delivery runs them once
/// the struct is filled.
/// </summary>
public abstract class Suspension
{
    /// <summary>The bridge's deferred writes into VM memory.</summary>
    public IReadOnlyList<Action> Writebacks { get; set; } = [];
}

/// <summary>
/// A suspended select: the seat the awaited event will land in.
/// </summary>
public sealed class Waiting : Suspension
{
    /// <summary>Open over the struct the game handed to glk_select.</summary>
    /// <param name="record">The event struct, filled on delivery.</param>
    public Waiting(RefStruct record) => Record = record;

    /// <summary>The event struct the game handed to glk_select.</summary>
    public RefStruct Record { get; }
}

/// <summary>
/// A suspended file prompt: a Glk call standing mid-flight.
///
/// Unlike a select, whose opcode completes and defers only its struct,
/// fileref_create_by_prompt cannot complete at all: its result is the
/// player's answer. So the wait parks the whole tail of the call. The
/// bridge leaves its result encoding here, the machine leaves the
/// opcode's store, and the delivery runs them once the name arrives
/// (Glk: File References).
/// </summary>
public sealed class Prompting : Suspension
{
    /// <summary>Open over the ask, the call's tail not yet parked.</summary>
    /// <param name="usage">What the file is for, suffix and all.</param>
    /// <param name="fmode">How the game means to open it.</param>
    /// <param name="rock">The rock the reference will wear.</param>
    public Prompting(uint usage, uint fmode, uint rock)
    {
        Usage = usage;
        FMode = fmode;
        Rock = rock;
    }

    /// <summary>What the file is for, suffix and all.</summary>
    public uint Usage { get; }

    /// <summary>How the game means to open it.</summary>
    public uint FMode { get; }

    /// <summary>The rock the reference will wear.</summary>
    public uint Rock { get; }

    /// <summary>The bridge's parked result encoding: the minted id.</summary>
    public Func<FileRef?, uint>? Encode { get; set; }

    /// <summary>The machine's parked opcode store.</summary>
    public Action<uint>? Store { get; set; }
}
