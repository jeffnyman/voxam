using System.Text;
using Voxam.Core.Glulx;
using GlulxException = Voxam.Core.GlulxException;

namespace Voxam.Tests.Glulx;

/// <summary>
/// String decoding and the output opcodes (Glulx: Strings). Three
/// string types share one entry point, and only the compressed kind
/// is interesting: its tree can print other strings and call
/// functions, so a print is a coroutine that suspends into the machine
/// and resumes off a call stub.
///
/// The filter function here writes every character it is handed into a
/// word buffer, so a test can read back exactly what was printed.
/// </summary>
public sealed class StringsTests
{
    private const int Filter = 150;
    private const int Printer = 208;
    private const int TableAt = 256;
    private const int Root = 272;
    private const int Left = 288;
    private const int Right = 304;
    private const int Text = 320;
    private const int Extra = 352;
    private const int Cell = 384;
    private const int Buffer = 0x200;
    private const int Cursor = 0x300;

    // A compressed string is a type byte and then a bit stream, read
    // low bit first: left, left, right down a tree whose left leaf
    // prints an A and whose right leaf ends the string.
    [Fact]
    public void ACompressedStringWalksItsTreeBitByBit()
    {
        Assert.Equal("AA", Filtered([0xE1, 0b100], Alphabet()));
    }

    // The null system decodes and discards, which is not the same as
    // not decoding at all.
    [Fact]
    public void TheNullSystemDecodesAndDiscards()
    {
        var machine = Printing([0xE1, 0b100], 0, null, Alphabet());
        machine.Run(200);

        Assert.Equal(0u, machine.Memory.ReadWord(Cursor));
        Assert.False(machine.Running);
    }

    // Glk output is a direct call, so it never suspends.
    [Fact]
    public void GlkOutputGoesStraightToTheLibrary()
    {
        var glk = new Recorder();
        var machine = Printing([0xE1, 0b100], 2, glk, Alphabet());
        machine.Run(200);

        Assert.Equal("AA", glk.Text);
        Assert.Equal(0, glk.Wide);
    }

    // A plain E0 string runs to its zero terminator; an E2 string pads
    // to a four-byte boundary first and then runs in words.
    [Theory]
    [InlineData(0u)]
    [InlineData(1u)]
    [InlineData(2u)]
    public void ThePlainStringsRunToTheirTerminators(uint mode)
    {
        var glk = new Recorder();
        var plain = Printing([0xE0, (byte)'H', (byte)'i', 0], mode, glk);
        plain.Run(200);

        Assert.Equal(mode == 0 ? "" : "Hi", mode == 1 ? Captured(plain) : glk.Text);

        var wide = new Recorder();
        var machine = Printing([0xE2, 0, 0, 0, .. Word('H'), .. Word('i'), .. Word(0)], mode, wide);
        machine.Run(200);

        Assert.Equal(mode == 0 ? "" : "Hi", mode == 1 ? Captured(machine) : wide.Text);
    }

    // A byte stream would flatten a wide character to a question mark,
    // so anything above a byte takes the Unicode call instead.
    [Fact]
    public void AWideCharacterTakesTheUnicodeCall()
    {
        var glk = new Recorder();
        var machine = Printing([0xE2, 0, 0, 0, .. Word(0x1F600), .. Word('A'), .. Word(0)], 2, glk);
        machine.Run(200);

        Assert.Equal([0x1F600u, 'A'], glk.Chars);
        Assert.Equal(1, glk.Wide);
    }

    // The tree may hold a wide character of its own, which a filter
    // sees whole.
    [Fact]
    public void TheTreeHoldsAWideCharacter()
    {
        var glk = new Recorder();
        var machine = Printing([0xE1, 0b10], 2, glk, Tree([0x04, .. Word(0x2603)]));
        machine.Run(200);

        Assert.Equal([0x2603u], glk.Chars);
        Assert.Equal("☃", Filtered([0xE1, 0b10], Tree([0x04, .. Word(0x2603)])));
    }

    // A bit stream longer than a byte carries on into the next one,
    // which is the one place the walk touches memory again.
    [Fact]
    public void ABitStreamRunsOnIntoTheNextByte()
    {
        Assert.Equal("AAAAAAAA", Filtered([0xE1, 0b0000_0000, 0b0000_0001], Alphabet()));
    }

    // The null system walks a whole-string node and prints nothing.
    [Fact]
    public void AWholeStringNodeIsWalkedAndDiscardedInTheNullSystem()
    {
        var machine = Printing([0xE1, 0b10], 0, null, Tree([0x03, (byte)'h', (byte)'i', 0]));
        machine.Run(200);

        Assert.Equal(0u, machine.Memory.ReadWord(Cursor));
        Assert.False(machine.Running);
    }

    // A character printed into the null system goes nowhere, and goes
    // there without calling anything.
    [Fact]
    public void ACharacterPrintsNowhereInTheNullSystem()
    {
        var program = new GlulxProgram();
        program.Op(Op.Streamchar, Modes.Constant(65));
        program.Op(Op.Quit);

        Assert.Equal(2, program.Booted().Run());
    }

    // An 0x03 node holds a C string and an 0x05 node a wide one, both
    // handed back to the top-level loop when a filter is printing.
    [Fact]
    public void TheTreeHoldsWholeStringsOfEitherWidth()
    {
        Assert.Equal("hi", Filtered([0xE1, 0b10], Tree([0x03, (byte)'h', (byte)'i', 0])));
        Assert.Equal("hi", Filtered([0xE1, 0b10], Tree([0x05, .. Word('h'), .. Word('i'), .. Word(0)])));

        var glk = new Recorder();
        var machine = Printing([0xE1, 0b10], 2, glk, Tree([0x03, (byte)'h', (byte)'i', 0]));
        machine.Run(200);

        var wide = new Recorder();
        var words = Printing([0xE1, 0b10], 2, wide, Tree([0x05, .. Word('h'), .. Word('i'), .. Word(0)]));
        words.Run(200);

        Assert.Equal("hi", glk.Text);
        Assert.Equal("hi", wide.Text);
    }

    // An indirect node reaches a string somewhere else; a double
    // indirect one reaches an address that holds the address.
    [Theory]
    [InlineData(0x08, Extra)]
    [InlineData(0x09, Cell)]
    public void AnIndirectNodeReachesAStringElsewhere(byte nodetype, int target)
    {
        Assert.Equal("hi", Filtered([0xE1, 0b10],
        [
            .. Tree([nodetype, .. Word((uint)target)]),
            (Extra, [0xE0, (byte)'h', (byte)'i', 0]),
            (Cell, Word(Extra)),
        ]));
    }

    // An indirect node may reach a function instead, which the print
    // suspends into and comes back from; the argument-bearing kinds
    // read their arguments out of the node itself.
    [Theory]
    [InlineData(0x08, false)]
    [InlineData(0x09, false)]
    [InlineData(0x0A, true)]
    [InlineData(0x0B, true)]
    public void AnIndirectNodeMayReachAFunctionInstead(byte nodetype, bool carriesArguments)
    {
        // A function that prints the character it is handed, so the
        // filter sees it the ordinary way.
        var printer = new GlulxProgram(Printer, locals: 1);
        printer.Op(Op.Streamchar, Modes.Local(0));
        printer.Op(Op.Return, Modes.Constant(0));

        byte[] node = nodetype switch
        {
            0x08 => [nodetype, .. Word(Printer)],
            0x09 => [nodetype, .. Word(Cell)],
            0x0A => [nodetype, .. Word(Printer), .. Word(1), .. Word('Z')],
            _ => [nodetype, .. Word(Cell), .. Word(1), .. Word('Z')],
        };

        var text = Filtered([0xE1, 0b10],
        [
            .. Tree(node),
            (Cell, Word(Printer)),
            (Printer, printer.Assembled),
        ]);

        // With no arguments the function's local stays zero, which the
        // filter still sees as a character.
        Assert.Equal(carriesArguments ? "Z" : "\0", text);
    }

    // streamchar carries only the low byte of its operand, and
    // streamunichar the whole of it.
    [Fact]
    public void TheCharacterOpcodesCarryAByteAndAWholeWord()
    {
        var glk = new Recorder();
        var program = new GlulxProgram();
        program.Op(Op.Setiosys, Modes.Constant(2), Modes.Constant(0));
        program.Op(Op.Streamchar, Modes.Word(0x1F641));
        program.Op(Op.Streamunichar, Modes.Word(0x1F600));
        program.Op(Op.Quit);
        var machine = program.Booted(glk: glk);
        machine.Run(200);

        Assert.Equal([0x41u, 0x1F600u], glk.Chars);
        Assert.Equal(1, glk.Wide);
    }

    // A number prints as a signed decimal, one character at a time
    // through a filter, the resume stub carrying the number itself.
    [Theory]
    [InlineData(42u, "42")]
    [InlineData(0xFFFFFFD6u, "-42")]
    [InlineData(0x80000000u, "-2147483648")]
    [InlineData(0u, "0")]
    public void ANumberPrintsAsASignedDecimal(uint value, string shown)
    {
        var program = new GlulxProgram();
        program.Op(Op.Setiosys, Modes.Constant(1), Modes.Constant(Filter));
        program.Op(Op.Streamnum, Modes.Word(value));
        program.Op(Op.Quit);
        program.Lay(Filter, FilterBody());
        var machine = program.Booted();
        machine.Run(500);

        Assert.Equal(shown, Captured(machine));

        var glk = new Recorder();
        var direct = new GlulxProgram();
        direct.Op(Op.Setiosys, Modes.Constant(2), Modes.Constant(0));
        direct.Op(Op.Streamnum, Modes.Word(value));
        direct.Op(Op.Quit);
        direct.Booted(glk: glk).Run(200);

        Assert.Equal(shown, glk.Text);
    }

    [Fact]
    public void ANumberPrintsNowhereInTheNullSystem()
    {
        var program = new GlulxProgram();
        program.Op(Op.Streamnum, Modes.Constant(42));
        program.Op(Op.Quit);

        Assert.Equal(2, program.Booted().Run());
    }

    [Theory]
    [InlineData(new byte[] { 0xE3 }, "the type byte $e3 names a kind of string reserved for the future (Glulx: Strings)")]
    [InlineData(new byte[] { 0x42 }, "the type byte $42 is not a string at all (Glulx: Strings)")]
    public void AStringTheWalkCannotFollowIsRefused(byte[] bytes, string message)
    {
        var program = new GlulxProgram();
        program.Op(Op.Streamstr, Modes.Constant(Text));
        program.Op(Op.Quit);
        program.Lay(Text, bytes);

        Assert.Equal(message, Refusal(() => program.Booted().Run(200)));
    }

    [Fact]
    public void ACompressedStringWithNoTableIsRefused()
    {
        var program = new GlulxProgram();
        program.Op(Op.Streamstr, Modes.Constant(Text));
        program.Op(Op.Quit);
        program.Lay(Text, [0xE1, 0]);

        Assert.Equal(
            "a compressed string cannot print with no decoding table set (Glulx: The String-Decoding Table)",
            Refusal(() => program.Booted().Run(200)));
    }

    [Fact]
    public void AStringAtNoAddressIsRefused()
    {
        var program = new GlulxProgram();
        program.Op(Op.Streamstr, Modes.Constant(0));

        Assert.Equal("streamstr with a null address (Glulx: Output)", Refusal(() => program.Booted().Run(200)));
    }

    [Fact]
    public void ANodeTypeTheTableMayNotHoldIsRefused()
    {
        Assert.Equal(
            "node type $7 is not one the decoding table may hold (Glulx: The String-Decoding Table)",
            Refusal(() => Printing([0xE1, 0], 1, null, Tree([0x07])).Run(200)));
    }

    [Fact]
    public void AnIndirectNodeReachingNeitherAStringNorAFunctionIsRefused()
    {
        Assert.Equal(
            "an indirect node reaches $160, which holds neither a string nor a function (Glulx: The String-Decoding Table)",
            Refusal(() => Printing([0xE1, 0], 1, null,
            [
                .. Tree([0x08, .. Word(Extra)]),
                (Extra, [0x42]),
            ]).Run(200)));
    }

    // Only forcing the output system can arrange Glk output with no
    // library installed: setiosys falls back to the null system.
    [Fact]
    public void GlkOutputWithNoLibraryIsRefused()
    {
        var program = new GlulxProgram();
        program.Op(Op.Streamchar, Modes.Constant(65));
        program.Op(Op.Quit);
        var machine = program.Booted();
        machine.IoSys.Select(2, 0);

        Assert.Equal("Glk output selected, but no Glk library is installed", Refusal(() => machine.Run(200)));
    }

    // The stubs a print leaves behind say what they are, and one that
    // says the wrong thing is caught rather than followed.
    [Fact]
    public void AStubOfTheWrongKindEndsAPrintLoudly()
    {
        var counting = Printing([0xE0, 0], 1);
        counting.Stack.PushStub(DestType.ResumeCompressed, 0, 0);

        Assert.Equal(
            "a string-on-string call stub arrived while printing a number (Glulx: Calling and Returning Within Strings)",
            Refusal(() => Strings.StreamNum(counting, 5, inMiddle: true, charnum: 5)));

        var printing = Printing([0xE0, (byte)'h', 0], 0);
        printing.Stack.PushStub(DestType.ResumeNumber, 0, 0);

        Assert.Equal(
            "a function-terminator call stub arrived at the end of a string (Glulx: Calling and Returning Within Strings)",
            Refusal(() => Strings.StreamString(printing, Text + 1, inMiddle: 0xE0)));
    }

    // A tree whose left leaf prints an A and whose right leaf ends the
    // string.
    private static (int At, byte[] Data)[] Alphabet() => Tree([0x02, (byte)'A']);

    // A tree with one leaf a test chooses and the other a terminator.
    private static (int At, byte[] Data)[] Tree(byte[] left) =>
    [
        (Root, [0x00, .. Word(Left), .. Word(Right)]),
        (Left, left),
        (Right, [0x01]),
    ];

    private static byte[] Word(uint value) => [(byte)(value >> 24), (byte)(value >> 16), (byte)(value >> 8), (byte)value];

    // A machine set to print one string, with a decoding table and
    // whatever nodes a test lays out.
    private static Machine Printing(byte[] text, uint mode = 1, Recorder? glk = null, params (int At, byte[] Data)[] nodes)
    {
        var program = new GlulxProgram();
        program.Op(Op.Setstringtbl, Modes.Constant(TableAt));
        program.Op(Op.Setiosys, Modes.Constant(mode), Modes.Constant(mode == 1 ? (uint)Filter : 0));
        program.Op(Op.Streamstr, Modes.Constant(Text));
        program.Op(Op.Quit);
        program.Lay(Filter, FilterBody());
        program.Lay(Text, text);
        program.Lay(TableAt, [.. Word(64), .. Word(1), .. Word(Root)]);

        foreach (var (at, data) in nodes)
        {
            program.Lay(at, data);
        }

        return program.Booted(glk: glk);
    }

    // What a compressed string printed through the filter.
    private static string Filtered(byte[] text, params (int At, byte[] Data)[] nodes)
    {
        var machine = Printing(text, 1, null, nodes);
        machine.Run(500);

        return Captured(machine);
    }

    // A filter that writes every character it is handed into a word
    // buffer, so a test can read back what was printed.
    private static byte[] FilterBody()
    {
        var filter = new GlulxProgram(Filter, locals: 2);
        filter.Op(Op.Aload, Modes.Constant(Cursor), Modes.Constant(0), Modes.Local(4));
        filter.Op(Op.Astore, Modes.Constant(Buffer), Modes.Local(4), Modes.Local(0));
        filter.Op(Op.Add, Modes.Local(4), Modes.Constant(1), Modes.Local(4));
        filter.Op(Op.Astore, Modes.Constant(Cursor), Modes.Constant(0), Modes.Local(4));
        filter.Op(Op.Return, Modes.Constant(0));

        return filter.Assembled;
    }

    private static string Captured(Machine machine)
    {
        var count = (int)machine.Memory.ReadWord(Cursor);
        var text = new StringBuilder();

        for (var at = 0; at < count; at++)
        {
            text.Append((char)machine.Memory.ReadWord(Buffer + (4 * at)));
        }

        return text.ToString();
    }

    private static string Refusal(Action work) => Assert.Throws<GlulxException>(work).Message;

    // A Glk library that only remembers what it was told to print.
    private sealed class Recorder : IGlkOutput
    {
        public List<uint> Chars { get; } = [];

        public int Wide { get; private set; }

        public string Text => new([.. Chars.Select(character => (char)character)]);

        public void PutChar(uint character) => Chars.Add(character);

        public void PutCharUni(uint character)
        {
            Chars.Add(character);
            Wide++;
        }
    }
}
