namespace Voxam.Core.Glulx;

/// <summary>The output systems setiosys accepts (Glulx: Output).</summary>
public enum IoMode : uint
{
    /// <summary>Output is discarded: the mode the machine starts in.</summary>
    Null = 0,

    /// <summary>Each character passes to the Glulx function the rock names.</summary>
    Filter = 1,

    /// <summary>Output goes to the current Glk stream.</summary>
    Glk = 2,
}

/// <summary>
/// Which output system is current, and its rock (Glulx: Output).
///
/// Only the selection lives here. Actually emitting a character is
/// the machine's business, because filter mode calls back into the
/// machine and Glk mode goes out through the dispatch layer, neither
/// of which this should know about.
/// </summary>
public sealed class IoSystem
{
    /// <summary>The current mode, as the story set it.</summary>
    public uint Mode { get; private set; }

    /// <summary>Filter mode's function address; otherwise decoration.</summary>
    public uint Rock { get; private set; }

    /// <summary>
    /// Select an output system. An unrecognized mode is not an error:
    /// the specification says setting an unsupported system selects
    /// the null system instead, which is exactly what a program
    /// probing with an unknown mode should find (Glulx: Output).
    /// </summary>
    public void Select(uint mode, uint rock)
    {
        if (mode is not ((uint)IoMode.Null or (uint)IoMode.Filter or (uint)IoMode.Glk))
        {
            mode = (uint)IoMode.Null;
            rock = 0;
        }

        Mode = mode;
        Rock = rock;
    }

    /// <summary>Return to the null system: restart's share.</summary>
    public void Reset()
    {
        Mode = (uint)IoMode.Null;
        Rock = 0;
    }
}
