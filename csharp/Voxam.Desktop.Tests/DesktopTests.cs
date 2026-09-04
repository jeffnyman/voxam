using Avalonia;
using Avalonia.Controls;
using Avalonia.Headless;
using Avalonia.Headless.XUnit;
using Avalonia.Input;
using Avalonia.Interactivity;
using Avalonia.Threading;
using Voxam.Core.Tests.Support;

namespace Voxam.Desktop.Tests;

/// <summary>The window, the glass and the session, driven on the headless platform.</summary>
public sealed class DesktopTests : IDisposable
{
    private const int G0 = 0x10;
    private readonly DirectoryInfo _directory = Directory.CreateTempSubdirectory("voxam-desktop");

    public void Dispose() => _directory.Delete(recursive: true);

    private string Story(string name, Action<StoryBuilder> body, int version = 5)
    {
        var b = new StoryBuilder(version);
        body(b);
        b.Quit();
        var path = Path.Combine(_directory.FullName, name);
        File.WriteAllBytes(path, b.Build());
        return path;
    }

    private static void ReadKey(StoryBuilder b)
    {
        b.OpVar(0x16, Arg.Small(1));
        b.Store(G0);
    }

    // Print a greeting and wait for a key, then echo it and end.
    private string Greeting() => Story("greeting.z5", b =>
    {
        b.Print("Hello");
        ReadKey(b);
        b.OpVar(0x05, Arg.Var(G0));
        b.NewLine();
        b.Print("Bye");
    });

    // Wait for a key and hold it: a story that never ends on its own.
    private string Waiting(string name = "waiting.z5") => Story(name, b =>
    {
        b.Print(Path.GetFileNameWithoutExtension(name));
        ReadKey(b);
    });

    private static MainWindow Shown(string? game)
    {
        var window = game is null ? new MainWindow() : new MainWindow(game);
        window.Show();
        Dispatcher.UIThread.RunJobs();
        return window;
    }

    private static string Notice(MainWindow window) => window.FindControl<TextBlock>("Notice")!.Text ?? "";

    // Pump the UI thread until the story's thread has done what the
    // test waits for, or a patient five seconds have passed.
    private static void Until(MainWindow window, Func<bool> condition)
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

    [AvaloniaFact]
    public static void TheWindowAsksForAStoryWhenGivenNone()
    {
        var window = Shown(null);
        Assert.Equal("Open a story to begin.", Notice(window));
        Assert.Equal("Voxam", window.Title);
        Assert.NotNull(window.CaptureRenderedFrame());
    }

    [AvaloniaFact]
    public void AStoryPlaysOnTheGlassAndTypedKeysReachIt()
    {
        var window = Shown(Greeting());
        var glass = window.Glass;
        Until(window, () => glass.Text.Contains("Hello", StringComparison.Ordinal));
        Assert.Equal("greeting: Voxam", window.Title);
        Assert.True(glass.Columns >= 40 && glass.Lines >= 10);
        window.KeyTextInput("x");
        Until(window, () => Notice(window) == "The story has ended.");
        Assert.Contains("Hellox\nBye", glass.Text, StringComparison.Ordinal);
        var frame = window.CaptureRenderedFrame();
        Assert.NotNull(frame);
        Assert.True(frame.PixelSize.Width > 0 && frame.PixelSize.Height > 0);
    }

    // Each special key arrives at the machine as the §3.8 code the
    // terminal would send; keys the glass has no name for pass by.
    [AvaloniaFact]
    public void TheKeyboardSpeaksTheStandardsCodes()
    {
        var path = Story("keys.z5", b =>
        {
            for (var k = 0; k < 8; k++)
            {
                ReadKey(b);
                b.OpVar(0x06, Arg.Var(G0));
                b.Print(" ");
            }
        });
        var window = Shown(path);
        var glass = window.Glass;
        Until(window, () => glass.Columns > 0);
        window.KeyPress(Key.F1, RawInputModifiers.None, PhysicalKey.F1, null);
        window.KeyPress(Key.Enter, RawInputModifiers.None, PhysicalKey.Enter, null);
        window.KeyPress(Key.Back, RawInputModifiers.None, PhysicalKey.Backspace, null);
        window.KeyPress(Key.Escape, RawInputModifiers.None, PhysicalKey.Escape, null);
        window.KeyPress(Key.Up, RawInputModifiers.None, PhysicalKey.ArrowUp, null);
        window.KeyPress(Key.Down, RawInputModifiers.None, PhysicalKey.ArrowDown, null);
        window.KeyPress(Key.Left, RawInputModifiers.None, PhysicalKey.ArrowLeft, null);
        window.KeyPress(Key.Right, RawInputModifiers.None, PhysicalKey.ArrowRight, null);
        window.KeyTextInput("a");
        Until(window, () => Notice(window) == "The story has ended.");
        Assert.Contains("13 8 27 129 130 131 132 97", glass.Text, StringComparison.Ordinal);
    }

    // Styles, colours and font 3 all reach the frame, and a screenful
    // waits behind [MORE] until a key lets it go.
    [AvaloniaFact]
    public void TheFrameWearsTheModelsDressAndPausesAtMore()
    {
        var path = Story("dressed.z5", b =>
        {
            b.OpVar(0x11, Arg.Small(1));
            b.Print("R");
            b.OpVar(0x11, Arg.Small(2));
            b.Print("B");
            b.OpVar(0x11, Arg.Small(4));
            b.Print("I");
            b.OpVar(0x11, Arg.Small(6));
            b.Print("X ");
            b.OpVar(0x11, Arg.Small(0));
            b.Op2(0x1B, Arg.Small(3), Arg.Small(4));
            b.Print("C");
            b.Op2(0x1B, Arg.Small(3), Arg.Small(5));
            b.Print("D");
            b.Op2(0x1B, Arg.Small(1), Arg.Small(1));
            b.Ext(0x04, Arg.Small(3));
            b.Store(G0);
            b.Print("!");
            b.Ext(0x04, Arg.Small(1));
            b.Store(G0);

            for (var k = 0; k < 80; k++)
            {
                b.NewLine();
                b.Print("L");
            }

            ReadKey(b);
        });
        var window = Shown(path);
        var glass = window.Glass;
        Until(window, () => glass.Prompt == "[MORE]");
        Assert.NotNull(window.CaptureRenderedFrame());
        glass.Press(" ");
        Until(window, () => glass.Prompt is null && glass.Text.Contains("L\nL", StringComparison.Ordinal));
        Assert.NotNull(window.CaptureRenderedFrame());
    }

    // A timed read ends on the clock when nothing is typed, and on
    // the key when something is; a click on the glass takes the focus.
    [AvaloniaFact]
    public void ATimedReadKeepsTheClockAndAClickTakesFocus()
    {
        var path = Story("timed.z5", b =>
        {
            var ends = b.Routine(0);
            b.Op1(0x0B, Arg.Small(1));
            b.InitialPc = b.Here;
            b.OpVar(0x16, Arg.Small(1), Arg.Small(3), Arg.Large(b.Packed(ends)));
            b.Store(G0);
            b.OpVar(0x06, Arg.Var(G0));
            b.Print(" ");
            b.OpVar(0x16, Arg.Small(1), Arg.Small(50), Arg.Large(b.Packed(ends)));
            b.Store(G0);
            b.OpVar(0x06, Arg.Var(G0));
        });
        var window = Shown(path);
        var glass = window.Glass;
        Until(window, () => glass.Text.StartsWith("0\n", StringComparison.Ordinal));
        window.MouseDown(new Point(120, 120), MouseButton.Left);
        Assert.True(glass.IsFocused);
        window.KeyTextInput("k");
        Until(window, () => Notice(window) == "The story has ended.");
        Assert.Contains("0 107", glass.Text, StringComparison.Ordinal);
    }

    [AvaloniaFact]
    public void AStoryThatFaultsSaysSoOnTheNoticeLine()
    {
        var window = Shown(Story("faulty.z5", b => b.Op2(0x00, Arg.Small(1), Arg.Small(2))));
        Until(window, () => Notice(window).StartsWith("voxam: 2OP:0 is not an opcode", StringComparison.Ordinal));
    }

    [AvaloniaFact]
    public void OpeningAnotherStoryRetiresTheFirst()
    {
        var window = Shown(Waiting("first.z5"));
        var glass = window.Glass;
        Until(window, () => glass.Text.Contains("first", StringComparison.Ordinal));
        window.Open(Waiting("second.z5"));
        Until(window, () => glass.Text.Contains("second", StringComparison.Ordinal));
        Assert.DoesNotContain("first", glass.Text, StringComparison.Ordinal);
        Assert.Equal("second: Voxam", window.Title);
    }

    [AvaloniaFact]
    public void AStoryThatCannotBeLoadedIsSaidSo()
    {
        var window = Shown(Path.Combine(_directory.FullName, "missing.z5"));
        Until(window, () => Notice(window).StartsWith("voxam: ", StringComparison.Ordinal));
        var blorb = Path.Combine(_directory.FullName, "empty.zblorb");
        File.WriteAllBytes(blorb, [.. "FORM"u8, 0, 0, 0, 16, .. "IFRSRIdx"u8, 0, 0, 0, 4, 0, 0, 0, 0]);
        window.Open(blorb);
        Until(window, () => Notice(window) == "voxam: empty.zblorb packages no Z-code story to run");
    }

    [AvaloniaFact]
    public void TheMenuOpensWhatThePickerChoosesAndQuits()
    {
        var window = Shown(null);
        var open = window.FindControl<MenuItem>("OpenItem")!;
        window.Picker = () => Task.FromResult<string?>(null);
        open.RaiseEvent(new RoutedEventArgs(MenuItem.ClickEvent));
        Dispatcher.UIThread.RunJobs();
        Assert.Equal("Open a story to begin.", Notice(window));
        window.Picker = () => Task.FromResult<string?>(Greeting());
        open.RaiseEvent(new RoutedEventArgs(MenuItem.ClickEvent));
        Until(window, () => window.Glass.Text.Contains("Hello", StringComparison.Ordinal));
        var closed = false;
        window.Closed += (_, _) => closed = true;
        window.FindControl<MenuItem>("QuitItem")!.RaiseEvent(new RoutedEventArgs(MenuItem.ClickEvent));
        Dispatcher.UIThread.RunJobs();
        Assert.True(closed);
    }

    // The model follows the glass's size at its next paint, as it
    // follows a terminal's: the story's next output lands on the new
    // grid, and the header's §8.4 fields with it.
    [AvaloniaFact]
    public void TheGlassFollowsTheWindowItIsGiven()
    {
        var path = Story("sized.z5", b =>
        {
            b.Print("before");
            ReadKey(b);
            b.NewLine();
            b.Print("after");
            ReadKey(b);
        });
        var window = Shown(path);
        var glass = window.Glass;
        Until(window, () => glass.Text.Contains("before", StringComparison.Ordinal));
        var (columns, lines) = (glass.Columns, glass.Lines);
        window.Width = 1400;
        window.Height = 900;
        Until(window, () => glass.Columns > columns && glass.Lines > lines);
        glass.Press(" ");
        Until(window, () => glass.Text.Contains("after", StringComparison.Ordinal));
        var model = window.Session!.Face!.Model;
        Assert.Equal((glass.Columns, glass.Lines), (model.Columns, model.Lines));
        Assert.Equal(glass.Lines, glass.Text.Count(c => c == '\n'));
    }
}
