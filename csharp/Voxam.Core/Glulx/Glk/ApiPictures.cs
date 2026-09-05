namespace Voxam.Core.Glulx.Glk;

/// <summary>
/// Pictures, and the rectangles a graphics window is painted with (Glk:
/// Graphics).
/// </summary>
public sealed partial class Api
{
    private void ServePictures()
    {
        // Report a picture's size. Answered from the resource bytes, so
        // it works even where nothing can be drawn (Glk: Testing for
        // Graphics Capabilities).
        Serve(0x00E0, args =>
        {
            var info = Resources.Image((int)Word(args[0]));

            Store(Holder(args[1]), (uint)(info?.Width ?? 0));
            Store(Holder(args[2]), (uint)(info?.Height ?? 0));

            return Held.OfWord(info is not null ? 1u : 0u);
        });

        // Draw a picture at its own size (Glk: Graphics in Graphics
        // Windows).
        Serve(0x00E1, args => Held.OfWord(
            Draw(Win(args[0]), Word(args[1]), Signed(args[2]), Signed(args[3]), null, null)));

        // Draw a picture scaled to a size.
        Serve(0x00E2, args => Held.OfWord(
            Draw(Win(args[0]), Word(args[1]), Signed(args[2]), Signed(args[3]),
                Word(args[4]), Word(args[5]))));

        // The rules beyond plain scaling are aspect-ratio hints for the
        // display; the display era decides how far to honor them, so
        // they pass through untouched here.
        Serve(0x00EC, args => Held.OfWord(
            Draw(Win(args[0]), Word(args[1]), Signed(args[2]), Signed(args[3]),
                Word(args[4]), Word(args[5]))));

        // Break text past the margin images (Glk: Graphics in Text
        // Buffer Windows).
        Serve(0x00E8, args =>
        {
            if (Win(args[0]) is { } window)
            {
                Display.FlowBreak(window);
            }

            return default;
        });

        // Erase a rectangle to the background (Glk: Graphics in Graphics
        // Windows).
        Serve(0x00E9, args =>
        {
            if (Win(args[0]) is { } window)
            {
                Display.EraseRect(
                    window, Signed(args[1]), Signed(args[2]), Word(args[3]), Word(args[4]));
            }

            return default;
        });

        // Fill a rectangle with a color.
        Serve(0x00EA, args =>
        {
            if (Win(args[0]) is { } window)
            {
                Display.FillRect(
                    window, Word(args[1]), Signed(args[2]), Signed(args[3]),
                    Word(args[4]), Word(args[5]));
            }

            return default;
        });

        // Choose the color future clears fill with.
        Serve(0x00EB, args =>
        {
            if (Win(args[0]) is { } window)
            {
                Display.SetBackgroundColor(window, Word(args[1]));
            }

            return default;
        });
    }

    /// <summary>
    /// Hand a measured picture to the display, if there is one. A
    /// picture no resource answers, and a window that is not there, are
    /// both simply not drawn.
    /// </summary>
    private uint Draw(Window? window, uint image, int val1, int val2, uint? width, uint? height)
    {
        var info = Resources.Image((int)image);

        if (window is null || info is null)
        {
            return 0;
        }

        return Display.DrawImage(
            window, info, val1, val2, width ?? (uint)info.Width, height ?? (uint)info.Height)
            ? 1u
            : 0u;
    }
}
