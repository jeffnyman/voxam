using Avalonia.Controls;
using Avalonia.Headless.XUnit;
using Avalonia.Interactivity;
using Avalonia.Threading;
using static Voxam.Desktop.Tests.Rig;

namespace Voxam.Desktop.Tests;

/// <summary>What the player chose about the glass, and its keeping.</summary>
public sealed class PreferencesTests : IDisposable
{
    private readonly DirectoryInfo _directory = Directory.CreateTempSubdirectory("voxam-prefs");

    public void Dispose() => _directory.Delete(recursive: true);

    private string Kept => Path.Combine(_directory.FullName, "preferences.txt");

    [Fact]
    public void ChoicesSurviveBeingWrittenDown()
    {
        Assert.Equal(Preferences.Default, Preferences.Load(Kept));
        new Preferences(Theme.Sepia, 24).Save(Kept);
        Assert.Equal(new Preferences(Theme.Sepia, 24), Preferences.Load(Kept));
        Assert.Equal("theme=sepia\nsize=24", string.Join("\n", File.ReadAllLines(Kept)));
    }

    // A file nobody wrote, a line nobody meant, and a value nothing
    // offers are all simply not choices.
    [Theory]
    [InlineData("")]
    [InlineData("nonsense")]
    [InlineData("theme=neon\nsize=99")]
    [InlineData("theme\nsize")]
    public void WhatCannotBeReadIsNotAChoice(string written)
    {
        File.WriteAllText(Kept, written);
        Assert.Equal(Preferences.Default, Preferences.Load(Kept));
    }

    // A place nothing can be kept is not worth a complaint.
    [Fact]
    public void ChoicesThatCannotBeKeptAreGivenUpQuietly()
    {
        var blocked = Path.Combine(_directory.FullName, "story.txt", "deeper", "preferences.txt");
        File.WriteAllText(Path.Combine(_directory.FullName, "story.txt"), "not a directory");
        new Preferences(Theme.Sepia, 24).Save(blocked);
        Assert.Equal(Preferences.Default, Preferences.Load(blocked));
    }

    [Fact]
    public void TheChoicesAreKeptBesideTheApplicationsOwnSettings()
    {
        Assert.EndsWith(Path.Combine("Voxam", "preferences.txt"), Preferences.Path, StringComparison.Ordinal);
    }

    private static MenuItem Item(MainWindow window, string header) =>
        window.FindControl<MenuItem>("LookMenu")!.Items.OfType<MenuItem>().First(item => (string)item.Header! == header);

    // The Look menu dresses the glass at once and remembers the choice
    // for the next session.
    [AvaloniaFact]
    public void ChoosingALookDressesTheGlassAndIsRemembered()
    {
        var window = new MainWindow(Launch.Parse([]), Kept);
        window.Show();
        Dispatcher.UIThread.RunJobs();
        Assert.Equal(Theme.Dark, window.Glass.Look);
        Assert.Equal(18, window.Glass.Size);

        Item(window, "Sepia").RaiseEvent(new RoutedEventArgs(MenuItem.ClickEvent));
        Item(window, "24 point").RaiseEvent(new RoutedEventArgs(MenuItem.ClickEvent));
        Dispatcher.UIThread.RunJobs();
        Assert.Equal(Theme.Sepia, window.Glass.Look);
        Assert.Equal(24, window.Glass.Size);
        Assert.Equal(new Preferences(Theme.Sepia, 24), window.Chosen);
        // The chrome follows the paper, so a menu stays readable.
        Assert.Equal(Avalonia.Styling.ThemeVariant.Light, window.RequestedThemeVariant);
        Item(window, "Dark").RaiseEvent(new RoutedEventArgs(MenuItem.ClickEvent));
        Dispatcher.UIThread.RunJobs();
        Assert.Equal(Avalonia.Styling.ThemeVariant.Dark, window.RequestedThemeVariant);
        Item(window, "Sepia").RaiseEvent(new RoutedEventArgs(MenuItem.ClickEvent));
        Dispatcher.UIThread.RunJobs();

        // The next session opens wearing them.
        var next = new MainWindow(Launch.Parse([]), Kept);
        next.Show();
        Dispatcher.UIThread.RunJobs();
        Assert.Equal(Theme.Sepia, next.Glass.Look);
        Assert.Equal(24, next.Glass.Size);
    }

    // Bigger type means fewer cells, and the story hears the new size.
    [AvaloniaFact]
    public void BiggerTypeMeansFewerCells()
    {
        var window = new MainWindow(Launch.Parse([]), Kept);
        window.Show();
        Dispatcher.UIThread.RunJobs();
        var (columns, lines) = (window.Glass.Columns, window.Glass.Lines);
        Item(window, "24 point").RaiseEvent(new RoutedEventArgs(MenuItem.ClickEvent));
        Dispatcher.UIThread.RunJobs();
        window.Measure(new Avalonia.Size(double.PositiveInfinity, double.PositiveInfinity));
        window.Arrange(new Avalonia.Rect(window.DesiredSize));
        Dispatcher.UIThread.RunJobs();
        Assert.True(window.Glass.CellSize.Height > 0);
        Assert.True(window.Glass.Columns <= columns);
        Assert.True(window.Glass.Lines <= lines);
    }

    // The command line dresses the launch it was given, whatever was
    // chosen last time.
    [AvaloniaFact]
    public void TheCommandLineDressesItsOwnLaunch()
    {
        new Preferences(Theme.Sepia, 16).Save(Kept);
        var window = new MainWindow(Launch.Parse(["--theme", "classic"]), Kept);
        window.Show();
        Dispatcher.UIThread.RunJobs();
        Assert.Equal(Theme.Classic, window.Glass.Look);
        Assert.Equal(16, window.Glass.Size);
    }
}
