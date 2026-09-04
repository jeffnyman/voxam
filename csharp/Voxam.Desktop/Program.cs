using System.Diagnostics.CodeAnalysis;
using Avalonia;

namespace Voxam.Desktop;

// The process door: the one piece the headless suite cannot walk
// through, since it starts the real platform. Everything behind it
// is covered.
[ExcludeFromCodeCoverage]
internal static class Program
{
    [STAThread]
    public static void Main(string[] args) => BuildAvaloniaApp().StartWithClassicDesktopLifetime(args);

    public static AppBuilder BuildAvaloniaApp() => AppBuilder.Configure<App>().UsePlatformDetect().LogToTrace();
}
