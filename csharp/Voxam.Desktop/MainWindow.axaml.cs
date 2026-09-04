using System.Globalization;
using System.Diagnostics.CodeAnalysis;
using Avalonia.Controls;
using Avalonia.Interactivity;
using Avalonia.Media;
using Avalonia.Platform.Storage;
using Avalonia.Styling;
using Avalonia.Threading;
using Voxam.Core;

namespace Voxam.Desktop;

/// <summary>The one window: a menu, the glass, and a line of notices under it.</summary>
public partial class MainWindow : Window
{
    private static readonly string[] StoryPatterns =
        ["*.z1", "*.z2", "*.z3", "*.z4", "*.z5", "*.z6", "*.z7", "*.z8", "*.zblorb", "*.zlb", "*.blorb", "*.blb"];

    private Session? _session;
    private string? _playing;
    private Preferences _chosen = Preferences.Default;

    [ExcludeFromCodeCoverage]
    public MainWindow()
        : this(Launch.Parse([]))
    {
    }

    /// <summary>The window a launch opens, keeping the player's own choices.</summary>
    [ExcludeFromCodeCoverage]
    public MainWindow(Launch launch)
        : this(launch, Preferences.Path)
    {
    }

    public MainWindow(Launch launch, string preferences)
    {
        InitializeComponent();
        Picker = PickStory;
        Files = PickSave;
        Kept = preferences;
        // A theme named on the command line dresses this launch; what
        // the player chose otherwise is remembered from the last one.
        _chosen = Preferences.Load(preferences);

        if (launch.Theme is { } dressed)
        {
            _chosen = _chosen with { Theme = dressed };
        }

        Dress();
        Offer();

        Closed += (_, _) => Screen.Dispose();

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

    /// <summary>
    /// How a saved game is named, given whether one is being saved
    /// rather than restored: the platform's picker, or whatever a test
    /// hands over. Null is a player who changed their mind.
    /// </summary>
    public Func<bool, Task<string?>> Files { get; set; }

    /// <summary>Where the player's choices are kept.</summary>
    public string Kept { get; }

    /// <summary>What the player has chosen: the glass's dress and its type.</summary>
    public Preferences Chosen => _chosen;

    /// <summary>The glass the story plays on.</summary>
    public Glass Glass => Screen;

    /// <summary>The story playing, or null before the first opens.</summary>
    public Session? Session => _session;

    /// <summary>Start a story on the glass, retiring whichever was playing.</summary>
    public void Open(string game)
    {
        // The notice clears before the story starts, never after: a
        // story that faults at once has its word on the line first.
        Tell("");
        // A Version 6 story is born knowing the screen's size, and it
        // lays out its whole stage from that, so it waits for the
        // layout to settle rather than asking a glass mid-arrangement.
        Dispatcher.UIThread.Post(() => Begin(game), DispatcherPriority.Loaded);
    }

    private void Begin(string game)
    {
        _session?.Retire();
        _session = null;
        _playing = game;

        try
        {
            _session = Session.Start(game, Screen, Tell, new PickedSaves(game, Files));
            Title = $"{Path.GetFileNameWithoutExtension(game)}: Voxam";
        }
        catch (Exception error) when (error is VoxamException or IOException)
        {
            Tell($"voxam: {error.Message}");
        }
    }

    private void Tell(string text) => Dispatcher.UIThread.Post(() => Notice.Text = text);

    // The Look menu: the four dressings, then the sizes. A choice
    // takes at once and is remembered for the next session.
    private void Offer()
    {
        foreach (var theme in Voxam.Desktop.Theme.All)
        {
            LookMenu.Items.Add(new MenuItem
            {
                Header = char.ToUpperInvariant(theme.Name[0]) + theme.Name[1..],
                ToggleType = MenuItemToggleType.Radio,
                GroupName = "theme",
                IsChecked = theme == _chosen.Theme,
                Tag = theme,
            });
        }

        LookMenu.Items.Add(new Separator());

        foreach (var size in Preferences.Sizes)
        {
            LookMenu.Items.Add(new MenuItem
            {
                Header = string.Create(CultureInfo.InvariantCulture, $"{size} point"),
                ToggleType = MenuItemToggleType.Radio,
                GroupName = "size",
                IsChecked = size == _chosen.Size,
                Tag = size,
            });
        }

        foreach (var item in LookMenu.Items.OfType<MenuItem>())
        {
            item.Click += item.Tag is double ? ChoseSize : ChoseTheme;
        }
    }

    private void ChoseTheme(object? sender, RoutedEventArgs e) =>
        Keep(_chosen with { Theme = (Voxam.Desktop.Theme)((MenuItem)sender!).Tag! });

    private void ChoseSize(object? sender, RoutedEventArgs e) =>
        Keep(_chosen with { Size = (double)((MenuItem)sender!).Tag! });

    private void Keep(Preferences chosen)
    {
        _chosen = chosen;
        Dress();
        _chosen.Save(Kept);
    }

    private void Dress()
    {
        Screen.Look = _chosen.Theme;
        Screen.Size = _chosen.Size;
        Background = new SolidColorBrush(_chosen.Theme.Paper);
        // The window's own chrome follows the paper: a menu dressed
        // for a dark window is barely there on a pale one.
        RequestedThemeVariant = Lit(_chosen.Theme.Paper) ? ThemeVariant.Light : ThemeVariant.Dark;
    }

    /// <summary>Whether a colour is light enough to want dark chrome over it.</summary>
    private static bool Lit(Color paper) => (0.299 * paper.R) + (0.587 * paper.G) + (0.114 * paper.B) > 128;

    private async void OpenClicked(object? sender, RoutedEventArgs e)
    {
        var game = await Picker();

        if (game is not null)
        {
            Open(game);
        }
    }

    private void QuitClicked(object? sender, RoutedEventArgs e) => Close();

    // The platform's own save and restore dialogs, which the headless
    // suite has none of, so it answers through Files instead.
    [ExcludeFromCodeCoverage]
    private async Task<string?> PickSave(bool saving)
    {
        var named = Path.GetFileNameWithoutExtension(_playing ?? "story") + ".sav";
        var kind = new FilePickerFileType("Saved games") { Patterns = ["*.sav", "*.qut"] };

        if (!saving)
        {
            var chosen = await StorageProvider.OpenFilePickerAsync(new FilePickerOpenOptions
            {
                Title = "Restore a saved game",
                AllowMultiple = false,
                FileTypeFilter = [kind, FilePickerFileTypes.All],
            });

            return chosen.Count > 0 ? chosen[0].TryGetLocalPath() : null;
        }

        var file = await StorageProvider.SaveFilePickerAsync(new FilePickerSaveOptions
        {
            Title = "Save this story",
            SuggestedFileName = named,
            DefaultExtension = "sav",
            FileTypeChoices = [kind],
        });

        return file?.TryGetLocalPath();
    }

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
