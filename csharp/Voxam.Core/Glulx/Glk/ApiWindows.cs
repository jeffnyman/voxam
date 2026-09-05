namespace Voxam.Core.Glulx.Glk;

/// <summary>
/// The window half of the library: opening, closing, splitting and
/// measuring (Glk: Window Opening, Closing, and Constraints).
/// </summary>
public sealed partial class Api
{
    private void ServeWindows()
    {
        // Walk the live windows (Glk: Iterating Through Opaque Objects).
        Serve(0x0020, args => Held.OfOpaque(Iterate(Windows, Win(args[0]), Holder(args[1]))));

        // The rock the window was opened with (Glk: Rocks).
        Serve(0x0021, args => Held.OfWord(Win(args[0])?.Rock ?? 0));

        // The root of the window tree, or nothing with none open.
        Serve(0x0022, _ => Held.OfOpaque(Root));

        Serve(0x0023, args => Held.OfOpaque(
            WindowOpen(Win(args[0]), Word(args[1]), Signed(args[2]), Word(args[3]), Word(args[4]))));

        Serve(0x0024, args =>
        {
            WindowClose(Win(args[0]), Record(args[1]));

            return default;
        });

        // The window's size in its own units (Glk: Changing Window
        // Constraints).
        Serve(0x0025, args =>
        {
            var window = Win(args[0]);

            Store(Holder(args[1]), (uint)(window?.Width ?? 0));
            Store(Holder(args[2]), (uint)(window?.Height ?? 0));

            return default;
        });

        Serve(0x0026, args =>
        {
            SetArrangement(Win(args[0]), Word(args[1]), Signed(args[2]), Win(args[3]));

            return default;
        });

        Serve(0x0027, args =>
        {
            GetArrangement(Win(args[0]), Holder(args[1]), Holder(args[2]), Holder(args[3]));

            return default;
        });

        // The window's type number (Glk: The Types of Windows).
        Serve(0x0028, args => Held.OfWord(Win(args[0])?.WinType ?? 0));

        // The pair above the window, or nothing at the root.
        Serve(0x0029, args => Held.OfOpaque(Win(args[0])?.Parent));

        // The window on the other side of the parent pair.
        Serve(0x0030, args => Held.OfOpaque(Sibling(Win(args[0]))));

        // Erase the window (Glk: Other Window Functions).
        Serve(0x002A, args =>
        {
            Win(args[0])?.Clear();

            return default;
        });

        Serve(0x002B, args =>
        {
            MoveCursor(Win(args[0]), Signed(args[1]), Signed(args[2]));

            return default;
        });

        // The window's own output stream (Glk: Window Streams).
        Serve(0x002C, args => Held.OfOpaque(Win(args[0])?.Stream));

        // Copy the window's output to a stream too (Glk: Echo Streams).
        Serve(0x002D, args =>
        {
            var window = Win(args[0]);

            if (window is not null)
            {
                window.EchoStream = Str(args[1]);
            }

            return default;
        });

        // The window's echo stream, or nothing without one.
        Serve(0x002E, args => Held.OfOpaque(Win(args[0])?.EchoStream));

        // Send the printing functions to this window (Glk: How To Print).
        Serve(0x002F, args =>
        {
            CurrentStream = Win(args[0])?.Stream;

            return default;
        });
    }

    /// <summary>
    /// Open a window, splitting an existing one after the first.
    ///
    /// An unsupported window type answers nothing rather than faulting,
    /// so a game can probe for graphics support by trying (Glk: Window
    /// Opening, Closing, and Constraints).
    /// </summary>
    /// <exception cref="GlulxException">
    /// For a split that contradicts the tree: a first window with a
    /// split, a later one without, or a method that is not a direction
    /// plus a division.
    /// </exception>
    private Window? WindowOpen(Window? split, uint method, int size, uint wtype, uint rock)
    {
        if (Root is null)
        {
            if (split is not null)
            {
                throw new GlulxException("window_open: splitwin must be null for the first window");
            }
        }
        else if (split is null)
        {
            throw new GlulxException("window_open: splitwin must not be null");
        }
        else
        {
            var division = method & WindowMethod.DivisionMask;

            if (division is not (WindowMethod.Fixed or WindowMethod.Proportional))
            {
                throw new GlulxException("window_open: the method is neither fixed nor proportional");
            }

            if ((method & WindowMethod.DirMask) is not (WindowMethod.Left or WindowMethod.Right
                or WindowMethod.Above or WindowMethod.Below))
            {
                throw new GlulxException("window_open: the method names no direction");
            }
        }

        var window = MakeWindow(wtype, rock, Display.Graphics);

        if (window is null)
        {
            return null;
        }

        Windows.Insert(0, window);
        Streams.Insert(0, window.Stream);

        if (split is null)
        {
            Root = window;
        }
        else
        {
            var parent = split.Parent;
            var pair = new PairWindow(split, window, window, method, size);

            Windows.Insert(0, pair);

            split.Parent = pair;
            window.Parent = pair;
            pair.Parent = parent;

            if (parent is null)
            {
                Root = pair;
            }
            else if (ReferenceEquals(parent.Child1, split))
            {
                parent.Child1 = pair;
            }
            else
            {
                parent.Child2 = pair;
            }
        }

        Rearrange();

        return window;
    }

    /// <summary>
    /// Close a window and its whole subtree. The sibling is promoted
    /// into the parent pair's place (Glk: Window Opening, Closing, and
    /// Constraints).
    /// </summary>
    /// <exception cref="GlulxException">For the null window.</exception>
    private void WindowClose(Window? window, RefStruct? result)
    {
        if (window is null)
        {
            throw new GlulxException("window_close: invalid window");
        }

        var (read, written) = window.Stream.Close();

        result?.SetAll(Held.OfWord(read), Held.OfWord(written));

        foreach (var descendant in Subtree(window))
        {
            ForgetWindow(descendant);
        }

        var parent = window.Parent;

        if (parent is null)
        {
            Root = null;
        }
        else
        {
            var sibling = ReferenceEquals(parent.Child1, window) ? parent.Child2 : parent.Child1;
            var grandparent = parent.Parent;

            ForgetWindow(parent);

            sibling.Parent = grandparent;

            if (grandparent is null)
            {
                Root = sibling;
            }
            else if (ReferenceEquals(grandparent.Child1, parent))
            {
                grandparent.Child1 = sibling;
            }
            else
            {
                grandparent.Child2 = sibling;
            }
        }

        Rearrange();
    }

    /// <summary>Drop one window and its stream from the live lists.</summary>
    private void ForgetWindow(Window window)
    {
        Windows.Remove(window);
        Streams.Remove(window.Stream);

        if (ReferenceEquals(CurrentStream, window.Stream))
        {
            CurrentStream = null;
        }

        Dispose(window.Stream);
        Dispose(window);
    }

    /// <summary>
    /// Change a pair's split (Glk: Changing Window Constraints).
    ///
    /// The windows never flip or rotate: changing the direction within
    /// its axis moves the constraint to the other child while the glass
    /// stays where it is, which the model carries by swapping the
    /// children, as the reference does.
    /// </summary>
    /// <exception cref="GlulxException">
    /// When the window is not a pair, the method changes the split's
    /// axis, or the key is a pair or lives outside this pair's subtree.
    /// </exception>
    private void SetArrangement(Window? window, uint method, int size, Window? key)
    {
        if (window is not PairWindow pair)
        {
            throw new GlulxException("window_set_arrangement: not a pair window");
        }

        var direction = method & WindowMethod.DirMask;
        var vertical = direction is WindowMethod.Left or WindowMethod.Right;
        var backward = direction is WindowMethod.Left or WindowMethod.Above;

        if (vertical != pair.Vertical)
        {
            // "You can't flip or rotate them" (Glk: Changing Window
            // Constraints).
            throw new GlulxException("window_set_arrangement: a split cannot change its axis");
        }

        if (key is not null)
        {
            if (key is PairWindow)
            {
                throw new GlulxException("window_set_arrangement: the key cannot be a pair window");
            }

            if (!Subtree(pair).Contains(key))
            {
                throw new GlulxException("window_set_arrangement: the key must live under the pair");
            }
        }

        if (backward != pair.Backward)
        {
            (pair.Child1, pair.Child2) = (pair.Child2, pair.Child1);
        }

        pair.SetMethod(method);
        pair.Size = size;

        if (key is not null)
        {
            pair.Key = key;
        }

        Rearrange();
    }

    /// <summary>Report a pair's split (Glk: Changing Window Constraints).</summary>
    /// <exception cref="GlulxException">When the window is not a pair.</exception>
    private static void GetArrangement(
        Window? window, Ref? methodref, Ref? sizeref, Ref? keyref)
    {
        if (window is not PairWindow pair)
        {
            throw new GlulxException("window_get_arrangement: not a pair window");
        }

        Store(methodref, pair.Method);
        Store(sizeref, (uint)pair.Size);

        if (keyref is not null)
        {
            keyref.Value = Held.OfOpaque(pair.Key);
        }
    }

    /// <summary>Place a grid's cursor (Glk: Text Grid Windows).</summary>
    /// <exception cref="GlulxException">When the window is not a text grid.</exception>
    private static void MoveCursor(Window? window, int xpos, int ypos)
    {
        if (window is not TextGridWindow grid)
        {
            throw new GlulxException("window_move_cursor: not a text grid window");
        }

        grid.MoveCursor(xpos, ypos);
    }

    /// <summary>The window on the other side of the parent pair.</summary>
    private static Window? Sibling(Window? window)
    {
        if (window?.Parent is not { } parent)
        {
            return null;
        }

        return ReferenceEquals(parent.Child1, window) ? parent.Child2 : parent.Child1;
    }

    /// <summary>
    /// Build a window of a type, or nothing for a type not on offer.
    /// </summary>
    /// <exception cref="GlulxException">
    /// For the pair type, which only splitting creates (Glk: Pair
    /// Windows).
    /// </exception>
    private static Window? MakeWindow(uint wtype, uint rock, bool graphics)
    {
        if (wtype == WindowType.Pair)
        {
            throw new GlulxException("window_open: cannot open a pair window directly");
        }

        return wtype switch
        {
            WindowType.Blank => new BlankWindow(rock),
            WindowType.TextBuffer => new TextBufferWindow(rock),
            WindowType.TextGrid => new TextGridWindow(rock),
            // Null rather than a fault, so a game can probe for graphics
            // by trying to open a window (Glk: Graphics Windows).
            WindowType.Graphics => graphics ? new GraphicsWindow(rock) : null,
            _ => null,
        };
    }

    /// <summary>Put a word in a holder, where one came in.</summary>
    private static void Store(Ref? holder, uint value)
    {
        if (holder is not null)
        {
            holder.Value = Held.OfWord(value);
        }
    }
}
