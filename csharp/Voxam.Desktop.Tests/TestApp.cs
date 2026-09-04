using Avalonia;
using Avalonia.Headless;
using Voxam.Desktop;
using Voxam.Desktop.Tests;

[assembly: AvaloniaTestApplication(typeof(TestApp))]

namespace Voxam.Desktop.Tests;

/// <summary>The app under test: the real App on the headless platform, drawing through Skia so frames are real.</summary>
public static class TestApp
{
    public static AppBuilder BuildAvaloniaApp() =>
        AppBuilder.Configure<App>()
            .UseSkia()
            .UseHeadless(new AvaloniaHeadlessPlatformOptions { UseHeadlessDrawing = false });
}
