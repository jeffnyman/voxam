namespace Voxam.Core;

/// <summary>
/// The Version 6 window ledger: §8.8's eight windows as pure state.
/// Each has a position and size in units, a cursor, attribute flags,
/// and eighteen numbered properties (§8.8.3), kept faithfully with no
/// glass in sight: get_wind_prop reads them, and the character
/// frontends go on rendering windows 0 and 1 as they always have.
/// </summary>
public sealed class WindowLedger
{
    public const int WindowCount = 8;
    public const int CurrentWindow = -3;
    private const int UnsignedCurrent = 0xFFFD;

    public const int YCoordinate = 0;
    public const int XCoordinate = 1;
    public const int YSize = 2;
    public const int XSize = 3;
    public const int YCursor = 4;
    public const int XCursor = 5;
    public const int LeftMargin = 6;
    public const int RightMargin = 7;
    public const int TextStyle = 10;
    public const int ColourData = 11;
    public const int FontNumber = 12;
    public const int FontSize = 13;
    public const int Attributes = 14;
    public const int LineCount = 15;
    public const int TrueForeground = 16;
    public const int PropertyCount = 18;
    private const int LastWritable = 15;

    public const int Wrapping = 1;
    public const int Scrolling = 2;
    public const int Transcripting = 4;
    public const int Buffering = 8;

    private readonly int[][] _windows = new int[WindowCount][];

    /// <summary>The currently selected window, which the code -3 resolves to (§8.8.3).</summary>
    public int Selected { get; set; }

    public WindowLedger(int height, int width, int foreground, int background, int fontWidth = 1, int fontHeight = 1)
    {
        for (var number = 0; number < WindowCount; number++)
        {
            var window = new int[PropertyCount];
            window[YCoordinate] = 1;
            window[XCoordinate] = 1;
            window[YCursor] = 1;
            window[XCursor] = 1;
            window[FontNumber] = 1;
            window[FontSize] = (fontHeight << 8) | fontWidth;
            window[ColourData] = (background << 8) | foreground;
            window[Attributes] = Buffering;

            if (number == 0)
            {
                window[YSize] = height;
                window[XSize] = width;
                window[Attributes] = Wrapping | Scrolling | Transcripting | Buffering;
            }
            else if (number == 1)
            {
                window[XSize] = width;
            }

            _windows[number] = window;
        }
    }

    /// <summary>The window a number names, -3 meaning the selected one.</summary>
    public int Resolve(int window)
    {
        if (window is CurrentWindow or UnsignedCurrent)
        {
            return Selected;
        }

        if (window is >= 0 and < WindowCount)
        {
            return window;
        }

        throw new ZMachineException($"window {window} is not one of the eight (§8.8.3)");
    }

    /// <summary>Read one §8.8.3.2 property, as get_wind_prop does.</summary>
    public int Property(int window, int number) => _windows[Resolve(window)][Known(number)];

    /// <summary>Write one property, as put_wind_prop does; the true colours must not be written.</summary>
    public void WriteProperty(int window, int number, int value)
    {
        if (Known(number) > LastWritable)
        {
            throw new ZMachineException($"window property {number} is a true colour, which must not be written (§8.8.3.2)");
        }

        _windows[Resolve(window)][number] = value;
    }

    /// <summary>Place a window's top left at (y, x) in units (§15 move_window).</summary>
    public void Move(int window, int y, int x)
    {
        var target = _windows[Resolve(window)];
        target[YCoordinate] = y;
        target[XCoordinate] = x;
    }

    /// <summary>Set a window's size in units (§15 window_size).</summary>
    public void Resize(int window, int height, int width)
    {
        var target = _windows[Resolve(window)];
        target[YSize] = height;
        target[XSize] = width;
    }

    /// <summary>Change a window's attribute flags: set, on, off, or reverse (§15 window_style).</summary>
    public void Restyle(int window, int flags, int operation)
    {
        var target = _windows[Resolve(window)];

        switch (operation)
        {
            case 0:
                target[Attributes] = flags;
                break;
            case 1:
                target[Attributes] |= flags;
                break;
            case 2:
                target[Attributes] &= ~flags & 0xFFFF;
                break;
            case 3:
                target[Attributes] ^= flags;
                break;
            default:
                throw new ZMachineException($"window_style operation {operation} is not one of §15's four (set, on, off, reverse)");
        }
    }

    /// <summary>Set a window's margin sizes, in units (§8.8.3.2.1).</summary>
    public void SetMargins(int window, int left, int right)
    {
        var target = _windows[Resolve(window)];
        target[LeftMargin] = left;
        target[RightMargin] = right;
    }

    private static int Known(int number)
    {
        if (number is < 0 or >= PropertyCount)
        {
            throw new ZMachineException($"window property {number} is not one of §8.8.3.2's eighteen");
        }

        return number;
    }
}
