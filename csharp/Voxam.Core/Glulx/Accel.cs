namespace Voxam.Core.Glulx;

/// <summary>
/// Accelerated functions (Glulx: Accelerated Functions).
///
/// A game may ask that calls to one of its own functions be replaced
/// by a built-in equivalent. These are Inform library veneer
/// routines, property lookup and ofclass and their friends, which
/// dominate its running time. The specification calls the idea
/// "outrageously CISC"; it is what keeps an interpreter from walking
/// the same object table thousands of times a turn.
///
/// Functions 2 through 7 are deprecated: they assume NUM_ATTR_BYTES
/// has its default value of 7 and misbehave otherwise. Functions 8
/// through 13 are the same routines with that assumption removed.
/// Both sets are carried, because an older game file will ask for the
/// older ones.
///
/// On errors: the specification allows an accelerated function to
/// report them "by some convenient means", and notes that discarding
/// them is the safer choice when the I/O system is not Glk. Since
/// every error here means the game asked about an address that is not
/// what it claims to be, they are discarded and the answer is what
/// the Inform original would give; each discarded report is marked in
/// place.
/// </summary>
public sealed class Accelerator(Memory memory)
{
    // Inform's own layout constants, as the veneer compiles them: the
    // type bytes an address is classified by, the RAMSTART word in
    // the header, and the property-entry shape.
    private const uint HeaderEnd = 36;
    private const int RamStartAt = 8;
    private const int StringType = 0xE0;
    private const int FunctionType = 0xC0;
    private const int ObjectTypeLow = 0x70;
    private const int ObjectTypeHigh = 0x7F;
    private const uint PropertyEntry = 10;
    private const uint IndivRange = 8;
    private const uint Word = 4;

    // The classified regions Z__Region answers.
    private const uint IsObject = 1;
    private const uint IsRoutine = 2;
    private const uint IsString = 3;

    private const int ParamCount = 9;
    private const int Lowest = 1;
    private const int Highest = 13;

    private readonly Memory _memory = memory;
    private readonly uint[] _params = new uint[ParamCount];
    private readonly Dictionary<uint, int> _installed = [];

    /// <summary>The function numbers this interpreter implements.</summary>
    public static IReadOnlySet<uint> Available { get; } =
        new HashSet<uint>(Enumerable.Range(Lowest, Highest - Lowest + 1).Select(number => (uint)number));

    /// <summary>
    /// The accelfunc opcode's work. Index zero cancels, and asking
    /// for a function this interpreter does not implement is silently
    /// ignored, which is what lets a game request acceleration
    /// unconditionally and trust the gestalt (Glulx: Accelerated
    /// Functions).
    /// </summary>
    public void SetFunc(uint index, uint address)
    {
        _installed.Remove(address);

        if (index != 0 && Available.Contains(index))
        {
            _installed[address] = (int)index;
        }
    }

    /// <summary>The accelparam opcode's work; unknown numbers are ignored.</summary>
    public void SetParam(uint index, uint value)
    {
        if (index < ParamCount)
        {
            _params[index] = value;
        }
    }

    /// <summary>The replacement for a function address, if any.</summary>
    public Func<IReadOnlyList<uint>, uint>? Lookup(uint address) =>
        _installed.TryGetValue(address, out var index) ? args => Invoke(index, args) : null;

    private uint ClassesTable => _params[0];

    private uint IndivPropStart => _params[1];

    private uint ClassMetaclass => _params[2];

    private uint ObjectMetaclass => _params[3];

    private uint RoutineMetaclass => _params[4];

    private uint StringMetaclass => _params[5];

    private uint SelfAddr => _params[6];

    private uint NumAttrBytes => _params[7];

    private uint CpvStart => _params[8];

    // Every accelerated function takes its arguments from the call
    // and returns one value. Missing arguments read as zero, as they
    // would in a real call with unfilled locals.
    private static uint Arg(IReadOnlyList<uint> args, int index) => index < args.Count ? args[index] : 0;

    private uint Invoke(int index, IReadOnlyList<uint> args) => index switch
    {
        1 => ZRegion(Arg(args, 0)),
        2 => CpTab(Arg(args, 0), Arg(args, 1), wide: false),
        3 => RaPr(Arg(args, 0), Arg(args, 1), wide: false),
        4 => RlPr(Arg(args, 0), Arg(args, 1), wide: false),
        5 => OcCl(Arg(args, 0), Arg(args, 1), wide: false),
        6 => RvPr(Arg(args, 0), Arg(args, 1), wide: false),
        7 => OpPr(Arg(args, 0), Arg(args, 1), wide: false),
        8 => CpTab(Arg(args, 0), Arg(args, 1), wide: true),
        9 => RaPr(Arg(args, 0), Arg(args, 1), wide: true),
        10 => RlPr(Arg(args, 0), Arg(args, 1), wide: true),
        11 => OcCl(Arg(args, 0), Arg(args, 1), wide: true),
        12 => RvPr(Arg(args, 0), Arg(args, 1), wide: true),
        _ => OpPr(Arg(args, 0), Arg(args, 1), wide: true),
    };

    // Whether an object is a class: in Class, not of it.
    private bool ObjInClass(uint obj) =>
        _memory.ReadWord((int)(obj + 13 + NumAttrBytes)) == ClassMetaclass;

    // Function 1: an address as object, routine, or string.
    private uint ZRegion(uint address)
    {
        if (address < HeaderEnd || address >= (uint)_memory.EndMem)
        {
            return 0;
        }

        var kind = _memory.ReadByte((int)address);

        if (kind >= StringType)
        {
            return IsString;
        }

        if (kind >= FunctionType)
        {
            return IsRoutine;
        }

        // 0x70 through 0x7F is Inform's object type byte, but only in
        // RAM; the header word at address 8 is RAMSTART.
        return kind >= ObjectTypeLow && kind <= ObjectTypeHigh && address >= _memory.ReadWord(RamStartAt)
            ? IsObject
            : 0;
    }

    // Functions 2 and 8: a property entry in an object's table. The
    // two differ only in where the table pointer lives: the older
    // form hardcodes obj-->4, right only when NUM_ATTR_BYTES is 7;
    // the newer derives it.
    private uint CpTab(uint obj, uint propId, bool wide)
    {
        if (ZRegion(obj) != IsObject)
        {
            // ERROR, discarded: asked for the property table of a
            // non-object.
            return 0;
        }

        var offset = wide ? 4 * (3 + (NumAttrBytes / 4)) : 16;
        var table = _memory.ReadWord((int)(obj + offset));

        if (table == 0)
        {
            return 0;
        }

        var count = _memory.ReadWord((int)table);

        return Search.Binary(_memory, propId, 2, table + 4, PropertyEntry, count, 0, 0);
    }

    // The property-entry core RA__Pr, RL__Pr and OP__Pr share.
    private uint GetProp(uint obj, uint propId, bool wide)
    {
        var cla = 0u;

        if ((propId & 0xFFFF0000) != 0)
        {
            // A composite id: the low half indexes the classes table,
            // the high half is the property itself.
            cla = _memory.ReadWord((int)(ClassesTable + ((propId & 0xFFFF) * 4)));

            if (OcCl(obj, cla, wide) == 0)
            {
                return 0;
            }

            propId >>= 16;
            obj = cla;
        }

        var prop = CpTab(obj, propId, wide);

        if (prop == 0)
        {
            return 0;
        }

        if (ObjInClass(obj) && cla == 0)
        {
            // A class only shows its individual properties when asked
            // directly.
            var start = IndivPropStart;

            if (propId < start || propId >= start + IndivRange)
            {
                return 0;
            }
        }

        // A property flagged as protected is invisible unless the
        // global self is this object: the veneer's "@aloadbit prop
        // 72", which is bit 0 of the byte at prop + 9.
        return _memory.ReadWord((int)SelfAddr) != obj && (_memory.ReadByte((int)(prop + 9)) & 1) != 0
            ? 0
            : prop;
    }

    // Functions 3 and 9: a property's data address, or zero.
    private uint RaPr(uint obj, uint propId, bool wide)
    {
        var prop = GetProp(obj, propId, wide);

        return prop == 0 ? 0 : _memory.ReadWord((int)(prop + 4));
    }

    // Functions 4 and 10: a property's length in bytes, or zero.
    private uint RlPr(uint obj, uint propId, bool wide)
    {
        var prop = GetProp(obj, propId, wide);

        return prop == 0 ? 0 : Word * (uint)_memory.ReadShort((int)(prop + 2));
    }

    // Functions 5 and 11: Inform's ofclass.
    private uint OcCl(uint obj, uint cla, bool wide)
    {
        var region = ZRegion(obj);

        if (region == IsString)
        {
            return cla == StringMetaclass ? 1u : 0u;
        }

        if (region == IsRoutine)
        {
            return cla == RoutineMetaclass ? 1u : 0u;
        }

        if (region != IsObject)
        {
            return 0;
        }

        var metaclass = obj == ClassMetaclass || obj == StringMetaclass
            || obj == RoutineMetaclass || obj == ObjectMetaclass;

        if (cla == ClassMetaclass)
        {
            return ObjInClass(obj) || metaclass ? 1u : 0u;
        }

        if (cla == ObjectMetaclass)
        {
            return ObjInClass(obj) || metaclass ? 0u : 1u;
        }

        if (cla == StringMetaclass || cla == RoutineMetaclass)
        {
            return 0;
        }

        if (!ObjInClass(cla))
        {
            // ERROR, discarded: ofclass applied to a non-class.
            return 0;
        }

        var inlist = RaPr(obj, 2, wide);

        if (inlist == 0)
        {
            return 0;
        }

        var count = RlPr(obj, 2, wide) / Word;

        for (var index = 0u; index < count; index++)
        {
            if (_memory.ReadWord((int)(inlist + (4 * index))) == cla)
            {
                return 1;
            }
        }

        return 0;
    }

    // Functions 6 and 12: a property's value, or its default.
    private uint RvPr(uint obj, uint propId, bool wide)
    {
        var address = RaPr(obj, propId, wide);

        if (address != 0)
        {
            return _memory.ReadWord((int)address);
        }

        if (propId > 0 && propId < IndivPropStart)
        {
            return _memory.ReadWord((int)(CpvStart + (4 * propId)));
        }

        // ERROR, discarded: read of a property the object does not
        // have.
        return 0;
    }

    // Functions 7 and 13: Inform's provides.
    private uint OpPr(uint obj, uint propId, bool wide)
    {
        var region = ZRegion(obj);
        var start = IndivPropStart;

        if (region == IsString)
        {
            // A string provides print and print_to_array.
            return propId == start + 6 || propId == start + 7 ? 1u : 0u;
        }

        if (region == IsRoutine)
        {
            // A routine provides call.
            return propId == start + 5 ? 1u : 0u;
        }

        if (region != IsObject)
        {
            return 0;
        }

        return propId >= start && propId < start + IndivRange && ObjInClass(obj)
            ? 1u
            : RaPr(obj, propId, wide) != 0 ? 1u : 0u;
    }
}
