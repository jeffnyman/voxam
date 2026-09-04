using System.Diagnostics.CodeAnalysis;
using Avalonia;
using Avalonia.Controls.ApplicationLifetimes;
using Avalonia.Markup.Xaml;

namespace Voxam.Desktop;

public partial class App : Application
{
    public override void Initialize() => AvaloniaXamlLoader.Load(this);

    // The other half of the process door: only a real desktop
    // lifetime reaches here with arguments, so the headless suite
    // opens its windows itself.
    [ExcludeFromCodeCoverage]
    public override void OnFrameworkInitializationCompleted()
    {
        if (ApplicationLifetime is IClassicDesktopStyleApplicationLifetime desktop)
        {
            desktop.MainWindow = new MainWindow(desktop.Args is { Length: > 0 } ? desktop.Args[0] : null);
        }

        base.OnFrameworkInitializationCompleted();
    }
}
