using Voxam.Core.Glulx;

namespace Voxam.Tests.Glulx;

/// <summary>
/// The accelerated functions (Glulx: Accelerated Functions): Inform's
/// veneer routines, replaced by built-in equivalents.
///
/// The world below is Inform-shaped rather than Inform-sized. An
/// object opens with a 0x70 type byte and seven attribute bytes; its
/// property table pointer sits at obj+16 and the metaclass word that
/// says whether it is a class at obj+20. A property table opens with
/// a count and then ten-byte entries, ordered by property number
/// because that is what the binary search inside wants.
/// </summary>
public sealed class AccelTests
{
    private const uint Obj = 384;
    private const uint Cls = 512;
    private const uint Str = 640;
    private const uint Rtn = 656;
    private const uint Junk = 672;
    private const uint ClassList = 704;
    private const uint Meta = 800;
    private const uint Other = 864;
    private const uint WideObj = 960;
    private const uint SelfGlobal = 300;
    private const uint ClassesTable = 320;
    private const uint CpvStart = 340;
    private const uint ClassMeta = 1024;
    private const uint RoutineMeta = 1056;
    private const uint StringMeta = 1088;
    private const uint Neither = 736;
    private const uint IndivStart = 100;

    // Function 1 classifies an address as object, routine or string,
    // and an object type byte outside RAM is none of them.
    [Theory]
    [InlineData(10u, 0u)]
    [InlineData(3000u, 0u)]
    [InlineData(100u, 0u)]
    [InlineData(Junk, 0u)]
    [InlineData(Neither, 0u)]
    [InlineData(Obj, 1u)]
    [InlineData(Rtn, 2u)]
    [InlineData(Str, 3u)]
    public void ZRegionClassifiesAnAddress(uint address, uint region)
    {
        Assert.Equal(region, Call(1, address));
    }

    // Function 2 hardcodes obj-->4; function 8 derives the offset from
    // the attribute width, so with eight attribute bytes they read
    // different tables.
    [Fact]
    public void TheTwoPropertyTablePointersDivergeOffTheDefaultWidth()
    {
        var accel = Standing();
        accel.SetParam(7, 8);

        Assert.Equal(462u, Call(accel, 2, WideObj, 5));
        Assert.Equal(580u, Call(accel, 8, WideObj, 5));
    }

    [Fact]
    public void APropertyTableIsFoundOrItIsNot()
    {
        // A non-object has none, and an object may carry none.
        Assert.Equal(0u, Call(2, Junk, 5));
        Assert.Equal(0u, Call(2, Meta, 5));
        Assert.Equal(462u, Call(2, Obj, 5));
        Assert.Equal(0u, Call(2, Obj, 99));
    }

    // Functions 3 and 4: where a property's data sits, and how long it
    // is in bytes.
    [Fact]
    public void APropertysAddressAndLengthComeOffItsEntry()
    {
        Assert.Equal(496u, Call(3, Obj, 5));
        Assert.Equal(4u, Call(4, Obj, 5));
        Assert.Equal(0u, Call(3, Obj, 99));
        Assert.Equal(0u, Call(4, Obj, 99));
    }

    // A composite property number indexes the classes table with its
    // low half and names the property with its high; the object has to
    // be of that class for it to answer.
    [Fact]
    public void ACompositePropertyNumberReachesThroughAClass()
    {
        Assert.Equal(630u, Call(3, Obj, (101u << 16) | 0));
        Assert.Equal(0u, Call(3, Meta, (101u << 16) | 0));
    }

    // A class only shows its individual properties when asked
    // directly, which is what the indiv range is for.
    [Fact]
    public void AClassShowsOnlyItsIndividualPropertiesWhenAskedDirectly()
    {
        Assert.Equal(630u, Call(3, Cls, IndivStart + 1));
        Assert.Equal(0u, Call(3, Cls, 5));
    }

    // A protected property is invisible unless the global self is this
    // very object.
    [Fact]
    public void AProtectedPropertyHidesFromEveryoneButItself()
    {
        var accel = Standing(out var memory);

        Assert.Equal(0u, Call(accel, 3, Obj, 7));

        memory.WriteWord((int)SelfGlobal, Obj);

        Assert.Equal(500u, Call(accel, 3, Obj, 7));
    }

    // Function 5 is Inform's ofclass, which answers for the two
    // metaclass regions before it looks at objects at all.
    [Theory]
    [InlineData(Str, StringMeta, 1u)]
    [InlineData(Str, ClassMeta, 0u)]
    [InlineData(Rtn, RoutineMeta, 1u)]
    [InlineData(Rtn, ClassMeta, 0u)]
    [InlineData(Junk, ClassMeta, 0u)]
    public void OfclassAnswersForStringsAndRoutinesFirst(uint obj, uint cla, uint answer)
    {
        Assert.Equal(answer, Call(5, obj, cla));
    }

    // Against the Class metaclass an object answers for whether it is
    // a class, or is itself one of the four metaclasses; against the
    // Object metaclass it answers the other way about.
    [Theory]
    [InlineData(Cls, true)]
    [InlineData(Meta, true)]
    [InlineData(ClassMeta, true)]
    [InlineData(RoutineMeta, true)]
    [InlineData(StringMeta, true)]
    [InlineData(Obj, false)]
    public void OfclassAgainstTheMetaclassesAnswersOppositely(uint obj, bool classy)
    {
        Assert.Equal(classy ? 1u : 0u, Call(5, obj, ClassMeta));
        Assert.Equal(classy ? 0u : 1u, Call(5, obj, Meta));
    }

    // An object is of a class when that class is in its own class
    // list, and of nothing at all when it has no list.
    [Fact]
    public void OfclassWalksTheObjectsOwnClassList()
    {
        Assert.Equal(1u, Call(5, Obj, Cls));
        Assert.Equal(0u, Call(5, Obj, Other));
        // Meta carries no property table, so no class list either.
        Assert.Equal(0u, Call(5, Meta, Cls));
        // A string or routine metaclass is never a class to be of.
        Assert.Equal(0u, Call(5, Obj, StringMeta));
        Assert.Equal(0u, Call(5, Obj, RoutineMeta));
        // And ofclass against a non-class is an error, discarded.
        Assert.Equal(0u, Call(5, Obj, Junk));
    }

    // Function 6 reads a property's value, falling back to the common
    // default for a property number below the individual range.
    [Fact]
    public void APropertysValueFallsBackToItsCommonDefault()
    {
        Assert.Equal(0xCAFEF00Du, Call(6, Obj, 5));
        Assert.Equal(0x1234u, Call(6, Obj, 6));
        Assert.Equal(0u, Call(6, Obj, 0));
        Assert.Equal(0u, Call(6, Obj, 200));
    }

    // Function 7 is Inform's provides: a string provides print and
    // print_to_array, a routine provides call, and an object provides
    // what it carries.
    [Theory]
    [InlineData(Str, IndivStart + 6, 1u)]
    [InlineData(Str, IndivStart + 7, 1u)]
    [InlineData(Str, 5u, 0u)]
    [InlineData(Rtn, IndivStart + 5, 1u)]
    [InlineData(Rtn, 5u, 0u)]
    [InlineData(Junk, 5u, 0u)]
    [InlineData(Cls, IndivStart + 1, 1u)]
    [InlineData(Obj, 5u, 1u)]
    [InlineData(Obj, 99u, 0u)]
    [InlineData(Obj, IndivStart + 1, 0u)]
    [InlineData(Obj, 200u, 0u)]
    public void ProvidesAnswersForEveryRegion(uint obj, uint propId, uint answer)
    {
        Assert.Equal(answer, Call(7, obj, propId));
    }

    // Functions 8 through 13 are the same routines with the attribute
    // width derived rather than assumed, and at the default width the
    // two sets agree.
    [Theory]
    [InlineData(2, 8)]
    [InlineData(3, 9)]
    [InlineData(4, 10)]
    [InlineData(5, 11)]
    [InlineData(6, 12)]
    [InlineData(7, 13)]
    public void TheWideFormsAgreeWithTheOldOnesAtTheDefaultWidth(uint old, uint wide)
    {
        Assert.Equal(Call(old, Obj, 5), Call(wide, Obj, 5));
        Assert.Equal(Call(old, Cls, IndivStart + 1), Call(wide, Cls, IndivStart + 1));
    }

    // Index zero cancels, and asking for a function this interpreter
    // does not implement is silently ignored, which is what lets a
    // game ask unconditionally and trust the gestalt.
    [Fact]
    public void InstallingAndCancellingAFunction()
    {
        var accel = Standing();

        Assert.Null(accel.Lookup(1000));

        accel.SetFunc(1, 1000);

        Assert.NotNull(accel.Lookup(1000));

        accel.SetFunc(0, 1000);

        Assert.Null(accel.Lookup(1000));

        accel.SetFunc(14, 1000);

        Assert.Null(accel.Lookup(1000));
    }

    // Unknown parameter numbers are ignored, and a missing argument
    // reads as zero, as it would in a real call with unfilled locals.
    [Fact]
    public void UnknownParametersAreIgnoredAndMissingArgumentsReadZero()
    {
        var accel = Standing();
        accel.SetParam(99, 5);
        accel.SetFunc(1, 1000);

        Assert.Equal(0u, accel.Lookup(1000)!([]));
    }

    // Every way of invoking a function lands in the same place, so an
    // accelerated one intercepts an ordinary call and its result comes
    // home through the stub the caller pushed.
    [Fact]
    public void AnAcceleratedFunctionInterceptsAnOrdinaryCall()
    {
        var callee = 160;
        var program = new GlulxProgram();
        program.Op(Op.Accelparam, Modes.Constant(7), Modes.Constant(7));
        program.Op(Op.Accelfunc, Modes.Constant(1), Modes.Constant((uint)callee));
        program.Op(Op.Callfi, Modes.Constant((uint)callee), Modes.Word(0x190), Modes.Memory(0x140));
        program.Op(Op.Quit);

        // The real function would answer 99; the replacement answers
        // what Z__Region does.
        var body = new GlulxProgram(callee, locals: 1);
        body.Op(Op.Return, Modes.Constant(99));
        program.Lay(callee, body.Assembled);
        program.Lay(0x190, [0xE0, 0]);

        var machine = program.Booted();
        machine.Run();

        Assert.Equal(3u, machine.Memory.ReadWord(0x140));
    }

    private static uint Call(uint index, uint first, uint second = 0) => Call(Standing(), index, first, second);

    private static uint Call(Accelerator accel, uint index, uint first, uint second)
    {
        accel.SetFunc(index, 1000);

        return accel.Lookup(1000)!([first, second]);
    }

    private static Accelerator Standing() => Standing(out _);

    private static Accelerator Standing(out Memory memory)
    {
        var builder = new GlulxBuilder { ExtStart = 1280, EndMem = 2048, StackSize = 1024 };

        // An object type byte in ROM, which is no object at all.
        builder.Lay(100, 0x70);
        builder.Lay((int)ClassesTable, Word(Cls));
        // The common default for property 6.
        builder.Lay((int)(CpvStart + (4 * 6)), Word(0x1234));

        // A plain object with a class list, a plain property, and a
        // protected one.
        builder.Lay((int)Obj, 0x70);
        builder.Lay((int)Obj + 16, Word(448));
        builder.Lay((int)Obj + 20, Word(0x111));
        builder.Lay(448, Word(3));
        builder.Lay(452, Entry(2, 1, ClassList, 0));
        builder.Lay(462, Entry(5, 1, 496, 0));
        builder.Lay(472, Entry(7, 2, 500, 1));
        builder.Lay(496, Word(0xCAFEF00D));
        builder.Lay((int)ClassList, Word(Cls));

        // A class, whose metaclass word says so, carrying one property
        // outside the individual range and one inside it.
        builder.Lay((int)Cls, 0x70);
        builder.Lay((int)Cls + 16, Word(576));
        builder.Lay((int)Cls + 20, Word(ClassMeta));
        builder.Lay(576, Word(2));
        builder.Lay(580, Entry(5, 1, 620, 0));
        builder.Lay(590, Entry(IndivStart + 1, 1, 630, 0));

        // A type byte between the object range and the routines, which
        // is nothing at all.
        builder.Lay((int)Neither, 0x90);

        // The three metaclasses that are objects in their own right,
        // so that an object can be one of them.
        foreach (var meta in (uint[])[ClassMeta, RoutineMeta, StringMeta])
        {
            builder.Lay((int)meta, 0x70);
            builder.Lay((int)meta + 20, Word(0x111));
        }

        builder.Lay((int)Str, 0xE0);
        builder.Lay((int)Rtn, 0xC0);
        builder.Lay((int)Junk, 0x42);

        // An object carrying no property table, which is also the
        // Object metaclass.
        builder.Lay((int)Meta, 0x70);
        builder.Lay((int)Meta + 20, Word(0x111));

        // A second class, of which nothing is.
        builder.Lay((int)Other, 0x70);
        builder.Lay((int)Other + 20, Word(ClassMeta));

        // An object whose two property-table pointers differ, so the
        // old and wide forms of CP__Tab part company.
        builder.Lay((int)WideObj, 0x70);
        builder.Lay((int)WideObj + 16, Word(448));
        builder.Lay((int)WideObj + 20, Word(576));

        memory = new Memory(new Story(builder.Build()));
        var accel = new Accelerator(memory);
        accel.SetParam(0, ClassesTable);
        accel.SetParam(1, IndivStart);
        accel.SetParam(2, ClassMeta);
        accel.SetParam(3, Meta);
        accel.SetParam(4, RoutineMeta);
        accel.SetParam(5, StringMeta);
        accel.SetParam(6, SelfGlobal);
        accel.SetParam(7, 7);
        accel.SetParam(8, CpvStart);

        return accel;
    }

    // One property-table entry: the number, the length in words, the
    // data address, and the flags whose low bit protects it.
    private static byte[] Entry(uint id, uint words, uint address, byte flags) =>
        [(byte)(id >> 8), (byte)id, (byte)(words >> 8), (byte)words, .. Word(address), 0, flags];

    private static byte[] Word(uint value) => [(byte)(value >> 24), (byte)(value >> 16), (byte)(value >> 8), (byte)value];
}
