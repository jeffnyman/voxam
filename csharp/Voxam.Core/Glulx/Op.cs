namespace Voxam.Core.Glulx;

/// <summary>
/// Every opcode number specification 3.1.3 defines.
///
/// The numbers come from (Glulx: Dictionary of Opcodes), checked
/// against the reference glulxe's own table. The whole roster lives
/// here even though the machine carries its eras one at a time: a
/// number the dispatch does not serve yet can then say what it is
/// and that it waits, instead of pretending to be unknown.
/// </summary>
public enum Op
{
    Nop = 0x00,

    // Integer math
    Add = 0x10,
    Sub = 0x11,
    Mul = 0x12,
    Div = 0x13,
    Mod = 0x14,
    Neg = 0x15,
    Bitand = 0x18,
    Bitor = 0x19,
    Bitxor = 0x1A,
    Bitnot = 0x1B,
    Shiftl = 0x1C,
    Sshiftr = 0x1D,
    Ushiftr = 0x1E,

    // Branches
    Jump = 0x20,
    Jz = 0x22,
    Jnz = 0x23,
    Jeq = 0x24,
    Jne = 0x25,
    Jlt = 0x26,
    Jge = 0x27,
    Jgt = 0x28,
    Jle = 0x29,
    Jltu = 0x2A,
    Jgeu = 0x2B,
    Jgtu = 0x2C,
    Jleu = 0x2D,
    Jumpabs = 0x104,

    // Functions and continuations
    Call = 0x30,
    Return = 0x31,
    Catch = 0x32,
    Throw = 0x33,
    Tailcall = 0x34,
    Callf = 0x160,
    Callfi = 0x161,
    Callfii = 0x162,
    Callfiii = 0x163,

    // Moving data and array data
    Copy = 0x40,
    Copys = 0x41,
    Copyb = 0x42,
    Sexs = 0x44,
    Sexb = 0x45,
    Aload = 0x48,
    Aloads = 0x49,
    Aloadb = 0x4A,
    Aloadbit = 0x4B,
    Astore = 0x4C,
    Astores = 0x4D,
    Astoreb = 0x4E,
    Astorebit = 0x4F,

    // The stack
    Stkcount = 0x50,
    Stkpeek = 0x51,
    Stkswap = 0x52,
    Stkroll = 0x53,
    Stkcopy = 0x54,

    // Output
    Streamchar = 0x70,
    Streamnum = 0x71,
    Streamstr = 0x72,
    Streamunichar = 0x73,
    Getstringtbl = 0x140,
    Setstringtbl = 0x141,
    Getiosys = 0x148,
    Setiosys = 0x149,

    // Miscellaneous
    Gestalt = 0x100,
    Debugtrap = 0x101,
    Glk = 0x130,

    // The memory map
    Getmemsize = 0x102,
    Setmemsize = 0x103,

    // The random number generator
    Random = 0x110,
    Setrandom = 0x111,

    // Game state
    Quit = 0x120,
    Verify = 0x121,
    Restart = 0x122,
    Save = 0x123,
    Restore = 0x124,
    Saveundo = 0x125,
    Restoreundo = 0x126,
    Protect = 0x127,
    Hasundo = 0x128,
    Discardundo = 0x129,

    // Searching
    Linearsearch = 0x150,
    Binarysearch = 0x151,
    Linkedsearch = 0x152,

    // Block copy and clear
    Mzero = 0x170,
    Mcopy = 0x171,

    // The memory allocation heap
    Malloc = 0x178,
    Mfree = 0x179,

    // Accelerated functions
    Accelfunc = 0x180,
    Accelparam = 0x181,

    // Floating-point math
    Numtof = 0x190,
    Ftonumz = 0x191,
    Ftonumn = 0x192,
    Ceil = 0x198,
    Floor = 0x199,
    Fadd = 0x1A0,
    Fsub = 0x1A1,
    Fmul = 0x1A2,
    Fdiv = 0x1A3,
    Fmod = 0x1A4,
    Sqrt = 0x1A8,
    Exp = 0x1A9,
    Log = 0x1AA,
    Pow = 0x1AB,
    Sin = 0x1B0,
    Cos = 0x1B1,
    Tan = 0x1B2,
    Asin = 0x1B3,
    Acos = 0x1B4,
    Atan = 0x1B5,
    Atan2 = 0x1B6,

    // Floating-point comparisons
    Jfeq = 0x1C0,
    Jfne = 0x1C1,
    Jflt = 0x1C2,
    Jfle = 0x1C3,
    Jfgt = 0x1C4,
    Jfge = 0x1C5,
    Jisnan = 0x1C8,
    Jisinf = 0x1C9,

    // Double-precision math
    Numtod = 0x200,
    Dtonumz = 0x201,
    Dtonumn = 0x202,
    Ftod = 0x203,
    Dtof = 0x204,
    Dceil = 0x208,
    Dfloor = 0x209,
    Dadd = 0x210,
    Dsub = 0x211,
    Dmul = 0x212,
    Ddiv = 0x213,
    Dmodr = 0x214,
    Dmodq = 0x215,
    Dsqrt = 0x218,
    Dexp = 0x219,
    Dlog = 0x21A,
    Dpow = 0x21B,
    Dsin = 0x220,
    Dcos = 0x221,
    Dtan = 0x222,
    Dasin = 0x223,
    Dacos = 0x224,
    Datan = 0x225,
    Datan2 = 0x226,

    // Double-precision comparisons
    Jdeq = 0x230,
    Jdne = 0x231,
    Jdlt = 0x232,
    Jdle = 0x233,
    Jdgt = 0x234,
    Jdge = 0x235,
    Jdisnan = 0x238,
    Jdisinf = 0x239,
}

/// <summary>How an opcode number says its own name.</summary>
public static class Opcode
{
    /// <summary>
    /// An opcode number's lowercase name, or its hex for a number
    /// the specification does not define. Names are never stored
    /// beside the numbers: they are derived from the member itself,
    /// so the two cannot drift apart.
    /// </summary>
    public static string Name(int number) => Enum.IsDefined((Op)number)
        ? ((Op)number).ToString().ToLowerInvariant()
        : $"${number:x}";
}
