using System.Text;
using Voxam.Core.Tests.Support;

namespace Voxam.Core.Tests;

/// <summary>Save and restore through a slot, and the auxiliary files beside them (§15 save, §6.1).</summary>
public class SaveTests
{
    private const int G0 = 0x10;

    /// <summary>A slot that keeps everything in memory and can be told to refuse.</summary>
    private sealed class MemorySlot : ISaveSlot
    {
        public byte[]? Kept { get; set; }

        public Dictionary<string, byte[]> Aux { get; } = new(StringComparer.Ordinal);

        public bool Refusing { get; set; }

        /// <summary>Whether a write replaces what is kept: false leaves a planted file in place.</summary>
        public bool Keeps { get; set; } = true;

        public Action<byte[]>? Written { get; set; }

        public bool Write(byte[] data)
        {
            if (Refusing)
            {
                return false;
            }

            if (Keeps)
            {
                Kept = data;
            }

            Written?.Invoke(data);
            return true;
        }

        public byte[]? Read()
        {
            var data = Kept;
            Kept = null;
            return data;
        }

        public bool WriteAux(string name, byte[] data)
        {
            if (Refusing)
            {
                return false;
            }

            Aux[name] = data;
            return true;
        }

        public byte[]? ReadAux(string name) => Aux.TryGetValue(name, out var data) ? data : null;
    }

    private static void PrintGlobal(StoryBuilder b, int variable)
    {
        b.OpVar(0x06, Arg.Var(variable));
        b.NewLine();
    }

    private static string Run(StoryBuilder b, ISaveSlot? slot, IEnumerable<string>? input = null)
    {
        var output = new StringBuilder();
        var lines = (input ?? []).GetEnumerator();
        new Machine(b.Build(), new PlainFrontend(t => output.Append(t)), () => lines.MoveNext() ? lines.Current : null, 1, saves: slot).Run();
        return output.ToString();
    }

    private static void SaveOp(StoryBuilder b, int version, int which)
    {
        if (version == 4)
        {
            b.Op0(0x5 + which);
        }
        else
        {
            b.Ext(which);
        }

        b.Store(G0);
    }

    // Save inside a routine with a local and a pushed value, then ask
    // for a restore at once. The restore resumes at the save's rider
    // with the second answer (2 from Version 4, the branch again in 3),
    // the slot is spent by then, so the next restore fails and play
    // goes on with the routine's local and stack intact (a Version 5
    // local starts at zero, §5.2.1, so its 41 is only Versions 1 to 4).
    private static StoryBuilder RoundTrip(int version)
    {
        var b = new StoryBuilder(version);
        var routine = b.Routine(1, 41);
        b.OpVar(0x08, Arg.Small(9));

        if (version <= 3)
        {
            b.Op0(0x5);
            b.Branch(true, 5);
            b.Print("F");
            b.Print("S");
            b.Op0(0x6);
            b.Branch(true, 5);
            b.Print("G");
        }
        else
        {
            SaveOp(b, version, 0);
            PrintGlobal(b, G0);
            SaveOp(b, version, 1);
            PrintGlobal(b, G0);
        }

        b.OpVar(0x06, Arg.Var(1));
        b.OpVar(0x06, Arg.Stack);
        b.Op0(0x0);
        b.InitialPc = b.Here;
        b.Call(routine, G0 + 3);
        b.Quit();
        return b;
    }

    [Theory]
    [InlineData(3, "SSG419")]
    [InlineData(4, "1\n2\n0\n419")]
    [InlineData(5, "1\n2\n0\n09")]
    public void ASaveRestoresToItsOwnRider(int version, string expected)
    {
        var slot = new MemorySlot();
        var seen = new List<byte[]>();
        slot.Written = data => seen.Add(data);
        Assert.Equal(expected, Run(RoundTrip(version), slot));
        Assert.Single(seen);
        Assert.Equal("IFZS", Encoding.ASCII.GetString(seen[0], 8, 4));
    }

    // A Version 3 save whose rider is rtrue or rfalse returns from its
    // routine on saving, and again when the restore resumes there.
    [Theory]
    [InlineData(1, "1\n1\nX")]
    [InlineData(0, "0\n0\nX")]
    public void ARestoreResumesARiderThatReturns(int rider, string expected)
    {
        var b = new StoryBuilder(3);
        var routine = b.Routine(0);
        b.Op0(0x5);
        b.Branch(true, rider);
        b.Print("F");
        b.Op0(0x1);
        b.InitialPc = b.Here;
        b.Call(routine, G0);
        PrintGlobal(b, G0);
        b.Op0(0x6);
        b.Branch(true, 5);
        b.Print("X");
        b.Quit();
        Assert.Equal(expected, Run(b, new MemorySlot()));
    }

    [Fact]
    public void ARefusedOrMissingSaveAnswersFailure()
    {
        foreach (var version in new[] { 3, 5 })
        {
            var b = new StoryBuilder(version);

            if (version == 3)
            {
                b.Op0(0x5);
                b.Branch(true, 5);
                b.Print("F");
                b.Op0(0x6);
                b.Branch(true, 5);
                b.Print("G");
            }
            else
            {
                b.Ext(0x00);
                b.Store(G0);
                PrintGlobal(b, G0);
                b.Ext(0x01);
                b.Store(G0);
                PrintGlobal(b, G0);
            }

            b.Quit();
            Assert.Equal(version == 3 ? "FG" : "0\n0\n", Run(b, null));
            Assert.Equal(version == 3 ? "FG" : "0\n0\n", Run(b, new MemorySlot { Refusing = true }));
            Assert.Equal(version == 3 ? "G" : "1\n0\n", Run(b, new MemorySlot { Kept = [1, 2, 3], Keeps = false }));
        }
    }

    [Fact]
    public void ASaveOfAnotherGameIsRefusedOnRestore()
    {
        var first = new StoryBuilder(5);
        first.Ext(0x00);
        first.Store(G0);
        first.Quit();
        var slot = new MemorySlot();
        Run(first, slot);
        var other = new StoryBuilder(5);
        other.Alloc(2);
        other.Ext(0x01);
        other.Store(G0);
        PrintGlobal(other, G0);
        other.Quit();
        Assert.Equal("0\n", Run(other, slot));
    }

    [Fact]
    public void TheTableFormsKeepGameNamedFiles()
    {
        var b = new StoryBuilder(5);
        var table = b.Bytes(1, 2, 3, 4);
        var name = b.Bytes(4, (byte)'m', (byte)'a', (byte)'p', (byte)'!');
        var absent = b.Bytes(3, (byte)'a', (byte)'b', (byte)'c');
        var target = b.Alloc(4);
        b.Ext(0x00, Arg.Large(table), Arg.Small(3), Arg.Large(name));
        b.Store(G0);
        PrintGlobal(b, G0);
        b.Ext(0x01, Arg.Large(target), Arg.Small(2), Arg.Large(name));
        b.Store(G0);
        PrintGlobal(b, G0);
        b.Op2(0x10, Arg.Large(target), Arg.Small(1));
        b.Store(G0);
        PrintGlobal(b, G0);
        b.Ext(0x01, Arg.Large(target), Arg.Small(2), Arg.Large(absent));
        b.Store(G0);
        PrintGlobal(b, G0);
        b.Quit();
        var slot = new MemorySlot();
        Assert.Equal("1\n2\n2\n0\n", Run(b, slot));
        Assert.Equal([1, 2, 3], slot.Aux["map!"]);
        Assert.Equal("0\n0\n0\n0\n", Run(b, null));
        var refusing = new MemorySlot { Refusing = true };
        Assert.Equal("0\n0\n0\n0\n", Run(b, refusing));

        var few = new StoryBuilder(5);
        few.Ext(0x00, Arg.Small(1), Arg.Small(2));
        few.Store(G0);
        Assert.Contains("the table form takes a table, a length, and a name", Session.Fails<ZMachineException>(few).Message, StringComparison.Ordinal);
    }

    [Fact]
    public void AFileSlotKeepsSavesAndAuxiliariesBesideTheStory()
    {
        var directory = Directory.CreateTempSubdirectory("voxam-saves");

        try
        {
            var slot = new FileSaveSlot(Path.Combine(directory.FullName, "story.sav"));
            Assert.Null(slot.Read());
            Assert.True(slot.Write([1, 2, 3]));
            Assert.Equal([1, 2, 3], slot.Read());
            Assert.True(slot.WriteAux("my map/1!", [9]));
            Assert.Equal([9], slot.ReadAux("my map/1!"));
            Assert.True(File.Exists(Path.Combine(directory.FullName, "mymap1.aux")));
            Assert.True(slot.WriteAux("!!!", [8]));
            Assert.True(File.Exists(Path.Combine(directory.FullName, "aux.aux")));
            Assert.True(slot.WriteAux("a-b_c", [7]));
            Assert.True(File.Exists(Path.Combine(directory.FullName, "a-b_c.aux")));
            // A save named by a bare root has no directory to keep
            // auxiliaries in, so they fall beside the working one.
            Assert.Null(new FileSaveSlot(Path.GetPathRoot(directory.FullName)!).ReadAux("absent"));
            Assert.Null(slot.ReadAux("absent"));
            var blocked = new FileSaveSlot(Path.Combine(directory.FullName, "missing", "deeper", "story.sav"));
            Assert.False(blocked.Write([1]));
            Assert.False(blocked.WriteAux("x", [1]));
            Assert.Equal(slot.Path, Path.Combine(directory.FullName, "story.sav"));
        }
        finally
        {
            directory.Delete(recursive: true);
        }
    }
}
