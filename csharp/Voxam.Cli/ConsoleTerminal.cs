using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text;
using Voxam.Core;

namespace Voxam.Cli;

/// <summary>
/// The real console behind the painted terminal: its size, escape
/// sequences written straight through, and keys read raw with an
/// optional timeout. On Windows the console is asked to honour the
/// sequences, which Windows Terminal does unasked and the classic
/// console does not.
/// </summary>
internal sealed partial class ConsoleTerminal : ITerminal, IDisposable
{
    private const int StandardOutput = -11;
    private const uint VirtualTerminalProcessing = 0x0004;
    private readonly StreamWriter _out;

    public ConsoleTerminal()
    {
        if (OperatingSystem.IsWindows())
        {
            var handle = GetStdHandle(StandardOutput);

            if (GetConsoleMode(handle, out var mode) != 0)
            {
                _ = SetConsoleMode(handle, mode | VirtualTerminalProcessing);
            }
        }

        _out = new StreamWriter(Console.OpenStandardOutput(), new UTF8Encoding(false), 1 << 14) { AutoFlush = false };
    }

    public int Width => Measured(() => Console.WindowWidth);

    public int Height => Measured(() => Console.WindowHeight);

    public void Write(string text)
    {
        _out.Write(text);
        _out.Flush();
    }

    // Keys are read without echo. A timeout is served by polling, the
    // only way the console offers to wait a while for a key.
    public string? ReadKey(double? timeoutSeconds)
    {
        if (timeoutSeconds is { } seconds)
        {
            var started = Stopwatch.StartNew();

            while (!Console.KeyAvailable)
            {
                if (started.Elapsed.TotalSeconds >= seconds)
                {
                    return null;
                }

                Thread.Sleep(10);
            }
        }

        var key = Console.ReadKey(intercept: true);

        return key.Key switch
        {
            ConsoleKey.Enter => "\n",
            ConsoleKey.Backspace or ConsoleKey.Delete => "\u007f",
            ConsoleKey.Escape => "\u001b",
            ConsoleKey.UpArrow => "\u0081",
            ConsoleKey.DownArrow => "\u0082",
            ConsoleKey.LeftArrow => "\u0083",
            ConsoleKey.RightArrow => "\u0084",
            _ => key.KeyChar == '\0' ? null : key.KeyChar.ToString(),
        };
    }

    public void Dispose() => _out.Dispose();

    private static int Measured(Func<int> read)
    {
        try
        {
            return read();
        }
        catch (IOException)
        {
            return 0;
        }
    }

    [LibraryImport("kernel32.dll")]
    private static partial nint GetStdHandle(int handle);

    [LibraryImport("kernel32.dll")]
    private static partial int GetConsoleMode(nint handle, out uint mode);

    [LibraryImport("kernel32.dll")]
    private static partial int SetConsoleMode(nint handle, uint mode);
}
