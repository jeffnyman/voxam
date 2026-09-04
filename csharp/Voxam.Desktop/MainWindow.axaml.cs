using System.Diagnostics.CodeAnalysis;
using Avalonia.Controls;
using Avalonia.Interactivity;
using Avalonia.Media;
using Avalonia.Platform.Storage;
using Avalonia.Threading;
using Voxam.Core;

namespace Voxam.Desktop;

/// <summary>The one window: a menu, the glass, and a line of notices under it.</summary>
public partial class MainWindow : Window
{
    private static readonly string[] StoryPatterns =
        ["*.z1", "*.z2", "*.z3", "*.z4", "*.z5", "*.z6", "*.z7", "*.z8", "*.zblorb", "*.zlb", "*.blorb", "*.blb"];

    private Session? _session;

    public MainWindow()
        : this(Launch.Parse([]))
    {
    }

    public MainWindow(Launch launch)
    {
        InitializeComponent();
        Picker = PickStory;
        Screen.Look = launch.Theme;
        Background = new SolidColorBrush(launch.Theme.Paper);

        Opened += (_, _) =>
        {
            Screen.Focus();

            if (launch.Game is not null)
            {
                Open(launch.Game);
            }
            else
            {
                Tell(launch.Complaint ?? "Open a story to begin.");
            }
        };
    }

    /// <summary>How a story is chosen: the platform's picker, or whatever a test hands over.</summary>
    public Func<Task<string?>> Picker { get; set; }

    /// <summary>The glass the story plays on.</summary>
    public Glass Glass => Screen;

    /// <summary>The story playing, or null before the first opens.</summary>
    public Session? Session => _session;

    /// <summary>Start a story on the glass, retiring whichever was playing.</summary>
    public void Open(string game)
    {
        _session?.Retire();
        _session = null;
        // The notice clears before the story starts, never after: a
        // story that faults at once has its word on the line first.
        Tell("");

        try
        {
            _session = Session.Start(game, Screen, Tell);
            Title = $"{Path.GetFileNameWithoutExtension(game)}: Voxam";
        }
        catch (Exception error) when (error is ZMachineException or IOException)
        {
            Tell($"voxam: {error.Message}");
        }
    }

    private void Tell(string text) => Dispatcher.UIThread.Post(() => Notice.Text = text);

    private async void OpenClicked(object? sender, RoutedEventArgs e)
    {
        var game = await Picker();

        if (game is not null)
        {
            Open(game);
        }
    }

    private void QuitClicked(object? sender, RoutedEventArgs e) => Close();

    // The platform's own file dialog: the headless suite has none to
    // open, so it hands a path through Picker instead.
    [ExcludeFromCodeCoverage]
    private async Task<string?> PickStory()
    {
        var chosen = await StorageProvider.OpenFilePickerAsync(new FilePickerOpenOptions
        {
            Title = "Open a story",
            AllowMultiple = false,
            FileTypeFilter =
            [
                new FilePickerFileType("Stories") { Patterns = StoryPatterns },
                FilePickerFileTypes.All,
            ],
        });

        return chosen.Count > 0 ? chosen[0].TryGetLocalPath() : null;
    }
}
