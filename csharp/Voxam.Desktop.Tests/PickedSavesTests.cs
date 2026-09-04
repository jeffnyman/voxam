using Avalonia.Headless.XUnit;
using Voxam.Core;
using Voxam.Core.Tests.Support;
using static Voxam.Desktop.Tests.Rig;

namespace Voxam.Desktop.Tests;

/// <summary>Saves the player names, through the platform's own picker (§15 save).</summary>
public sealed class PickedSavesTests : IDisposable
{
    private const int G0 = 0x10;
    private readonly DirectoryInfo _directory = Directory.CreateTempSubdirectory("voxam-saves");

    public void Dispose() => _directory.Delete(recursive: true);

    private string Beside(string name) => Path.Combine(_directory.FullName, name);

    // A story that saves, bumps a global, restores, and prints what
    // each answered: 1 for the save, 2 for the resumed restore, and 0
    // where the slot refused.
    private string RoundTrip()
    {
        var b = new StoryBuilder(5);
        var routine = b.Routine(0);
        b.Ext(0x00);
        b.Store(G0);
        b.OpVar(0x06, Arg.Var(G0));
        b.NewLine();
        b.Ext(0x01);
        b.Store(G0);
        b.OpVar(0x06, Arg.Var(G0));
        b.NewLine();
        b.OpVar(0x16, Arg.Small(1));
        b.Store(G0);
        b.Op0(0x1);
        b.InitialPc = b.Here;
        b.Call(routine, G0 + 1);
        b.Quit();
        var path = Beside("tale.z5");
        File.WriteAllBytes(path, b.Build());
        return path;
    }

    // The picker names the file, and what the machine wrote is a real
    // saved game the machine can read back.
    [AvaloniaFact]
    public void APickedFileIsWhereTheSaveGoes()
    {
        var chosen = Beside("elsewhere.sav");
        var window = Shown(null);
        window.Files = _ => Task.FromResult<string?>(chosen);
        window.Open(RoundTrip());
        Until(window, () => window.Glass.Waiting);
        Assert.True(File.Exists(chosen));
        Assert.Equal("IFZS", System.Text.Encoding.ASCII.GetString(File.ReadAllBytes(chosen), 8, 4));
        // The save answered 1 and the restore resumed with 2.
        Assert.StartsWith("1\n2\n", window.Glass.Text, StringComparison.Ordinal);
    }

    // A player who changes their mind refuses the save, and the story
    // is told so rather than stopped.
    [AvaloniaFact]
    public void APlayerWhoChangesTheirMindRefusesTheSave()
    {
        var window = Shown(null);
        window.Files = _ => Task.FromResult<string?>(null);
        window.Open(RoundTrip());
        Until(window, () => window.Glass.Waiting);
        Assert.StartsWith("0\n0\n", window.Glass.Text, StringComparison.Ordinal);
    }

    [AvaloniaFact]
    public void WhatCannotBeWrittenOrReadIsARefusal()
    {
        var blocked = Path.Combine(_directory.FullName, "missing", "deeper", "one.sav");
        var slot = new PickedSaves(Beside("tale.z5"), _ => Task.FromResult<string?>(blocked));
        Assert.False(Offstage(() => slot.Write([1, 2, 3])));
        Assert.Null(Offstage(slot.Read));
    }

    // Auxiliary files are not the player's to name: the game supplies
    // those, and they stay beside the story (§7.6.1.1).
    [Fact]
    public void AuxiliaryFilesStayBesideTheStory()
    {
        var asked = 0;
        var slot = new PickedSaves(Beside("tale.z5"), _ =>
        {
            asked++;
            return Task.FromResult<string?>(null);
        });
        Assert.True(slot.WriteAux("map", [7]));
        Assert.Equal([7], slot.ReadAux("map"));
        Assert.True(File.Exists(Beside("map.aux")));
        Assert.Equal(0, asked);
    }

    // A picker that fails is a refusal, the same answer a player who
    // cancels gives.
    [AvaloniaFact]
    public void APickerThatFailsIsARefusal()
    {
        var slot = new PickedSaves(Beside("tale.z5"), _ => throw new InvalidOperationException("no picker here"));
        Assert.False(Offstage(() => slot.Write([1])));
        Assert.Null(Offstage(slot.Read));
    }
}
