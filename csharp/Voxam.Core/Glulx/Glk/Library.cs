namespace Voxam.Core.Glulx.Glk;

/// <summary>
/// The Glk library the bridge dispatches into.
///
/// The reference reaches its functions by name: the bridge asks the
/// library object for the attribute called glk_window_open and calls
/// whatever answers. Nothing here can work that way, because a port
/// that publishes ahead of time cannot look a method up by a string it
/// only learns at runtime. So the library declares what it serves
/// instead, selector by selector, and the table it builds is the same
/// promise the reference's method names are.
///
/// A selector nobody has served yet refuses by name. That is the same
/// discipline the opcode roster has kept since the first rung: an
/// absence is a frontier, spoken in the words of the thing that is
/// missing, never a wrong answer and never a silence.
/// </summary>
public class GlkLibrary
{
    private readonly Dictionary<int, Func<object?[], Held>> _served = [];

    /// <summary>
    /// Told when an object is destroyed, so the registry can stop
    /// resolving its id. The equivalent of the reference wiring itself
    /// in through gidispatch_set_object_registry.
    /// </summary>
    public Action<GlkObject>? OnDispose { get; set; }

    /// <summary>
    /// The call standing down, waiting on an answer from outside, or
    /// null while the machine runs.
    ///
    /// The seat carries this rather than the library alone, because the
    /// bridge above it must see a suspension without knowing which
    /// library it is talking to: it defers its writebacks onto whatever
    /// stands here, and refuses every further call while one does.
    /// </summary>
    public Suspension? Suspended { get; protected set; }

    /// <summary>
    /// Call one function, or refuse by name if it is not served yet.
    /// </summary>
    /// <param name="signature">The function's dispatch signature.</param>
    /// <param name="args">The marshalled arguments, in call order.</param>
    /// <exception cref="GlulxException">
    /// When the library does not serve this selector.
    /// </exception>
    public Held Call(Signature signature, object?[] args)
    {
        ArgumentNullException.ThrowIfNull(signature);

        if (!_served.TryGetValue(signature.Number, out var handler))
        {
            throw new GlulxException(
                $"called {signature.GlkName}, a Glk function this library does not serve yet");
        }

        return handler(args);
    }

    /// <summary>Declare that this library answers one selector.</summary>
    /// <param name="selector">The Glk function number.</param>
    /// <param name="handler">What answers it.</param>
    protected void Serve(int selector, Func<object?[], Held> handler) =>
        _served[selector] = handler;
}
