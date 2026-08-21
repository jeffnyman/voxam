"""The opcode numbers: every one specification 3.1.3 defines.

The numbers come from (Glulx: Dictionary of Opcodes), checked
against the reference glulxe's own table (vendored). The whole
roster lives here even though the machine carries its eras one at
a time: a number the dispatch does not serve yet can then say what
it is and that it waits, instead of pretending to be unknown.

Names are never stored separately: name() derives them from the
member itself, so the two cannot drift apart.
"""

from enum import IntEnum


class Op(IntEnum):
    """Every opcode number defined by Glulx 3.1.3."""

    NOP = 0x00

    # Integer math
    ADD = 0x10
    SUB = 0x11
    MUL = 0x12
    DIV = 0x13
    MOD = 0x14
    NEG = 0x15
    BITAND = 0x18
    BITOR = 0x19
    BITXOR = 0x1A
    BITNOT = 0x1B
    SHIFTL = 0x1C
    SSHIFTR = 0x1D
    USHIFTR = 0x1E

    # Branches
    JUMP = 0x20
    JZ = 0x22
    JNZ = 0x23
    JEQ = 0x24
    JNE = 0x25
    JLT = 0x26
    JGE = 0x27
    JGT = 0x28
    JLE = 0x29
    JLTU = 0x2A
    JGEU = 0x2B
    JGTU = 0x2C
    JLEU = 0x2D
    JUMPABS = 0x104

    # Functions and continuations
    CALL = 0x30
    RETURN = 0x31
    CATCH = 0x32
    THROW = 0x33
    TAILCALL = 0x34
    CALLF = 0x160
    CALLFI = 0x161
    CALLFII = 0x162
    CALLFIII = 0x163

    # Moving data and array data
    COPY = 0x40
    COPYS = 0x41
    COPYB = 0x42
    SEXS = 0x44
    SEXB = 0x45
    ALOAD = 0x48
    ALOADS = 0x49
    ALOADB = 0x4A
    ALOADBIT = 0x4B
    ASTORE = 0x4C
    ASTORES = 0x4D
    ASTOREB = 0x4E
    ASTOREBIT = 0x4F

    # The stack
    STKCOUNT = 0x50
    STKPEEK = 0x51
    STKSWAP = 0x52
    STKROLL = 0x53
    STKCOPY = 0x54

    # Output
    STREAMCHAR = 0x70
    STREAMNUM = 0x71
    STREAMSTR = 0x72
    STREAMUNICHAR = 0x73
    GETSTRINGTBL = 0x140
    SETSTRINGTBL = 0x141
    GETIOSYS = 0x148
    SETIOSYS = 0x149

    # Miscellaneous
    GESTALT = 0x100
    DEBUGTRAP = 0x101
    GLK = 0x130

    # The memory map
    GETMEMSIZE = 0x102
    SETMEMSIZE = 0x103

    # The random number generator
    RANDOM = 0x110
    SETRANDOM = 0x111

    # Game state
    QUIT = 0x120
    VERIFY = 0x121
    RESTART = 0x122
    SAVE = 0x123
    RESTORE = 0x124
    SAVEUNDO = 0x125
    RESTOREUNDO = 0x126
    PROTECT = 0x127
    HASUNDO = 0x128
    DISCARDUNDO = 0x129

    # Searching
    LINEARSEARCH = 0x150
    BINARYSEARCH = 0x151
    LINKEDSEARCH = 0x152

    # Block copy and clear
    MZERO = 0x170
    MCOPY = 0x171

    # The memory allocation heap
    MALLOC = 0x178
    MFREE = 0x179

    # Accelerated functions
    ACCELFUNC = 0x180
    ACCELPARAM = 0x181

    # Floating-point math
    NUMTOF = 0x190
    FTONUMZ = 0x191
    FTONUMN = 0x192
    CEIL = 0x198
    FLOOR = 0x199
    FADD = 0x1A0
    FSUB = 0x1A1
    FMUL = 0x1A2
    FDIV = 0x1A3
    FMOD = 0x1A4
    SQRT = 0x1A8
    EXP = 0x1A9
    LOG = 0x1AA
    POW = 0x1AB
    SIN = 0x1B0
    COS = 0x1B1
    TAN = 0x1B2
    ASIN = 0x1B3
    ACOS = 0x1B4
    ATAN = 0x1B5
    ATAN2 = 0x1B6

    # Floating-point comparisons
    JFEQ = 0x1C0
    JFNE = 0x1C1
    JFLT = 0x1C2
    JFLE = 0x1C3
    JFGT = 0x1C4
    JFGE = 0x1C5
    JISNAN = 0x1C8
    JISINF = 0x1C9

    # Double-precision math
    NUMTOD = 0x200
    DTONUMZ = 0x201
    DTONUMN = 0x202
    FTOD = 0x203
    DTOF = 0x204
    DCEIL = 0x208
    DFLOOR = 0x209
    DADD = 0x210
    DSUB = 0x211
    DMUL = 0x212
    DDIV = 0x213
    DMODR = 0x214
    DMODQ = 0x215
    DSQRT = 0x218
    DEXP = 0x219
    DLOG = 0x21A
    DPOW = 0x21B
    DSIN = 0x220
    DCOS = 0x221
    DTAN = 0x222
    DASIN = 0x223
    DACOS = 0x224
    DATAN = 0x225
    DATAN2 = 0x226

    # Double-precision comparisons
    JDEQ = 0x230
    JDNE = 0x231
    JDLT = 0x232
    JDLE = 0x233
    JDGT = 0x234
    JDGE = 0x235
    JDISNAN = 0x238
    JDISINF = 0x239


def name(number: int) -> str:
    """An opcode number's lowercase name, or its hex for none."""

    try:
        return Op(number).name.lower()
    except ValueError:
        return f"${number:x}"
