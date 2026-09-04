using System.Runtime.InteropServices;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Media;
using Avalonia.Media.Imaging;
using Avalonia.Platform;
using Avalonia.Threading;
using Voxam.Core.Tests.Support;

namespace Voxam.Desktop.Tests;

/// <summary>What the desktop tests share: stories on disk, windows shown, a patient wait, and a look at the pixels.</summary>
internal static class Rig
{
    public const int G0 = 0x10;

    /// <summary>Assemble a Version 5 story with the builder and write it beside the others.</summary>
    public static string Story(DirectoryInfo directory, string name, Action<StoryBuilder> body, int version = 5)
    {
        var b = new StoryBuilder(version);
        body(b);
        b.Quit();
        var path = Path.Combine(directory.FullName, name);
        File.WriteAllBytes(path, b.Build());
        return path;
    }

    /// <summary>read_char with no clock, its key stored in the first global.</summary>
    public static void ReadKey(StoryBuilder b)
    {
        b.OpVar(0x16, Arg.Small(1));
        b.Store(G0);
    }

    public static MainWindow Shown(string? game, Theme? theme = null)
    {
        var window = game is null && theme is null ? new MainWindow() : new MainWindow(new Launch(game, theme ?? Theme.Dark, null));
        window.Show();
        Dispatcher.UIThread.RunJobs();
        return window;
    }

    public static string Notice(MainWindow window) => window.FindControl<TextBlock>("Notice")!.Text ?? "";

    /// <summary>Pump the UI thread until the story's thread has done what the test waits for, or five seconds pass.</summary>
    public static void Until(MainWindow window, Func<bool> condition)
    {
        var deadline = DateTime.UtcNow.AddSeconds(5);

        while (!condition())
        {
            Assert.True(DateTime.UtcNow < deadline, $"the story never got there; notice: {Notice(window)}; glass:\n{window.Glass.Text}");
            Dispatcher.UIThread.RunJobs();
            Thread.Sleep(10);
        }

        Dispatcher.UIThread.RunJobs();
    }

    /// <summary>Where a cell's top left corner falls in the window's own pixels.</summary>
    public static Point CellOrigin(MainWindow window, int row, int column)
    {
        var glass = window.Glass;
        var origin = glass.TranslatePoint(new Point(0, 0), window)!.Value;
        var cell = glass.CellSize;
        return new Point(origin.X + (column - 1) * cell.Width, origin.Y + (row - 1) * cell.Height);
    }

    /// <summary>The colour of one pixel of a rendered frame.</summary>
    public static Color Pixel(WriteableBitmap frame, double x, double y)
    {
        using var buffer = frame.Lock();
        var word = Marshal.ReadInt32(buffer.Address, (int)y * buffer.RowBytes + (int)x * 4);
        var (low, mid, high) = ((byte)word, (byte)(word >> 8), (byte)(word >> 16));
        return buffer.Format == PixelFormat.Rgba8888 ? Color.FromRgb(low, mid, high) : Color.FromRgb(high, mid, low);
    }
}
