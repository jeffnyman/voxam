using Voxam.Core.Tests.Support;

namespace Voxam.Core.Tests;

public class ObjectsTests
{
    // A room holding a box holding a coin, with a lamp beside the box.
    private static (Memory Memory, ObjectTable Objects) World(int version = 3)
    {
        var builder = new StoryBuilder(version);
        builder.Objects(
            new ObjectSpec("room", Child: 2, Attributes: [0, 7, 8], Properties: [(3, [0x12, 0x34]), (1, [9])]),
            new ObjectSpec("box", Parent: 1, Sibling: 3, Child: 4, Properties: [(5, [1, 2, 3, 4])]),
            new ObjectSpec("lamp", Parent: 1, Attributes: [31]),
            new ObjectSpec("coin", Parent: 2, Properties: [(2, [0xAB])]));
        builder.PropertyDefault(4, 0x0404);
        builder.Quit();
        var memory = new Memory(builder.Build());
        return (memory, new ObjectTable(memory));
    }

    [Theory]
    [InlineData(3)]
    [InlineData(5)]
    public void TheTreeReadsAsBuilt(int version)
    {
        var (_, objects) = World(version);
        Assert.Equal(0, objects.Parent(1));
        Assert.Equal(2, objects.Child(1));
        Assert.Equal(3, objects.Sibling(2));
        Assert.Equal(4, objects.Child(2));
        Assert.Equal(2, objects.Parent(4));
        Assert.Equal(0, objects.Sibling(4));
    }

    [Theory]
    [InlineData(3)]
    [InlineData(5)]
    public void AttributesReadAndWrite(int version)
    {
        var (_, objects) = World(version);
        Assert.True(objects.Attribute(1, 0));
        Assert.True(objects.Attribute(1, 7));
        Assert.True(objects.Attribute(1, 8));
        Assert.False(objects.Attribute(1, 9));
        Assert.True(objects.Attribute(3, 31));
        objects.SetAttribute(3, 31, false);
        Assert.False(objects.Attribute(3, 31));
        objects.SetAttribute(3, 9, true);
        Assert.True(objects.Attribute(3, 9));
        Assert.True(objects.AttributeExists(version == 3 ? 31 : 47));
        Assert.False(objects.AttributeExists(version == 3 ? 32 : 48));
        var error = Assert.Throws<ZMachineException>(() => objects.Attribute(1, 60));
        Assert.Contains("attribute 60 does not exist", error.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void RemovingTheFirstChildPromotesItsSibling()
    {
        var (_, objects) = World();
        objects.Remove(2);
        Assert.Equal(3, objects.Child(1));
        Assert.Equal(0, objects.Parent(2));
        Assert.Equal(0, objects.Sibling(2));
        Assert.Equal(4, objects.Child(2));
    }

    [Fact]
    public void RemovingALaterChildUnlinksItFromTheChain()
    {
        var (_, objects) = World();
        objects.Remove(3);
        Assert.Equal(2, objects.Child(1));
        Assert.Equal(0, objects.Sibling(2));
        Assert.Equal(0, objects.Parent(3));
        objects.Remove(3);
        Assert.Equal(0, objects.Parent(3));
    }

    [Fact]
    public void ABrokenChainIsReportedRatherThanWalkedForever()
    {
        var (memory, objects) = World();
        // The lamp claims the room as parent, but the room's chain no
        // longer reaches it.
        memory.WriteByte(memory.ReadWord(Header.ObjectTable) + 62 + 9 + 5, 0);
        var error = Assert.Throws<ZMachineException>(() => objects.Remove(3));
        Assert.Contains("does not list it among its children", error.Message, StringComparison.Ordinal);
    }

    [Theory]
    [InlineData(3)]
    [InlineData(5)]
    public void InsertingMakesAnObjectTheFirstChild(int version)
    {
        var (_, objects) = World(version);
        objects.Insert(4, 1);
        Assert.Equal(4, objects.Child(1));
        Assert.Equal(2, objects.Sibling(4));
        Assert.Equal(1, objects.Parent(4));
        Assert.Equal(0, objects.Child(2));
    }

    [Theory]
    [InlineData(3)]
    [InlineData(5)]
    public void PropertiesReadWriteAndDefault(int version)
    {
        var (memory, objects) = World(version);
        Assert.Equal(0x1234, objects.PropertyValue(1, 3));
        Assert.Equal(9, objects.PropertyValue(1, 1));
        Assert.Equal(0x0404, objects.PropertyValue(1, 4));
        Assert.Equal(0, objects.PropertyValue(1, 2));
        objects.PutProperty(1, 3, 0x5678);
        Assert.Equal(0x5678, objects.PropertyValue(1, 3));
        objects.PutProperty(1, 1, 0x1FF);
        Assert.Equal(0xFF, objects.PropertyValue(1, 1));
        var found = objects.FindProperty(2, 5);
        Assert.NotNull(found);
        Assert.Equal(4, found.Value.Length);
        Assert.Equal(1, memory.ReadByte(found.Value.Data));
        Assert.Equal(4, objects.PropertyLengthAt(found.Value.Data));
        Assert.Equal(2, objects.PropertyLengthAt(objects.FindProperty(1, 3)!.Value.Data));
        Assert.Equal(1, objects.PropertyLengthAt(objects.FindProperty(4, 2)!.Value.Data));
        Assert.Null(objects.FindProperty(2, 6));
        Assert.Null(objects.FindProperty(2, 1));
    }

    [Fact]
    public void LongPropertiesRefuseWordAccess()
    {
        var (_, objects) = World();
        Assert.Contains("4 bytes long", Assert.Throws<ZMachineException>(() => objects.PropertyValue(2, 5)).Message, StringComparison.Ordinal);
        Assert.Contains("4 bytes long", Assert.Throws<ZMachineException>(() => objects.PutProperty(2, 5, 1)).Message, StringComparison.Ordinal);
        Assert.Contains("no property 9 to write", Assert.Throws<ZMachineException>(() => objects.PutProperty(2, 9, 1)).Message, StringComparison.Ordinal);
        Assert.Contains("property 40 does not exist", Assert.Throws<ZMachineException>(() => objects.PropertyValue(2, 40)).Message, StringComparison.Ordinal);
        Assert.Contains("property 0 does not exist", Assert.Throws<ZMachineException>(() => objects.PropertyValue(2, 0)).Message, StringComparison.Ordinal);
    }

    [Fact]
    public void AVersionFiveLongPropertyCanReachSixtyFourBytes()
    {
        var builder = new StoryBuilder(5);
        builder.Objects(new ObjectSpec("thing", Properties: [(7, new byte[64])]));
        builder.Quit();
        var objects = new ObjectTable(new Memory(builder.Build()));
        var found = objects.FindProperty(1, 7);
        Assert.Equal(64, found!.Value.Length);
        Assert.Equal(64, objects.PropertyLengthAt(found.Value.Data));
    }

    [Theory]
    [InlineData(3)]
    [InlineData(5)]
    public void NextPropertyWalksDownwards(int version)
    {
        var (_, objects) = World(version);
        Assert.Equal(3, objects.NextProperty(1, 0));
        Assert.Equal(1, objects.NextProperty(1, 3));
        Assert.Equal(0, objects.NextProperty(1, 1));
        Assert.Equal(0, objects.NextProperty(3, 0));
        var error = Assert.Throws<ZMachineException>(() => objects.NextProperty(1, 2));
        Assert.Contains("no property 2 to step past", error.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void ShortNamesDecode()
    {
        var (memory, objects) = World();
        Assert.Equal("lamp", Zscii.Decode(memory, objects.ShortNameAddress(3)).Text);
    }
}
