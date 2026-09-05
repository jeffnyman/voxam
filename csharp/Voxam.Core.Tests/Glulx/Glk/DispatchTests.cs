using Voxam.Core.Glulx.Glk;

namespace Voxam.Tests.Glulx.Glk;

/// <summary>
/// The Glk dispatch table, held to gi_dispa.c's own strings.
/// </summary>
public sealed class DispatchTests
{
    // Parsed verbatim out of gidispatch_prototype() in cheapglk's
    // gi_dispa.c, vendored at entharion/vendor/cheapglk. Embedded here
    // rather than read live because the suite must run from a plain
    // checkout, submodules present or not, and the vendored reference is
    // pinned, so these strings are constants and not a moving target.
    // glk_set_interrupt_handler (0x0002) returns NULL there, "cannot be
    // invoked through dispatch layer", and is deliberately absent from
    // both sides of the comparison.
    private static readonly Dictionary<int, (string Name, string Prototype)> GiDispa = new()
    {
        [0x0001] = ("exit", "0:"),
        [0x0003] = ("tick", "0:"),
        [0x0004] = ("gestalt", "3IuIu:Iu"),
        [0x0005] = ("gestalt_ext", "4IuIu&#Iu:Iu"),
        [0x0020] = ("window_iterate", "3Qa<Iu:Qa"),
        [0x0021] = ("window_get_rock", "2Qa:Iu"),
        [0x0022] = ("window_get_root", "1:Qa"),
        [0x0023] = ("window_open", "6QaIuIuIuIu:Qa"),
        [0x0024] = ("window_close", "2Qa<[2IuIu]:"),
        [0x0025] = ("window_get_size", "3Qa<Iu<Iu:"),
        [0x0026] = ("window_set_arrangement", "4QaIuIuQa:"),
        [0x0027] = ("window_get_arrangement", "4Qa<Iu<Iu<Qa:"),
        [0x0028] = ("window_get_type", "2Qa:Iu"),
        [0x0029] = ("window_get_parent", "2Qa:Qa"),
        [0x002A] = ("window_clear", "1Qa:"),
        [0x002B] = ("window_move_cursor", "3QaIuIu:"),
        [0x002C] = ("window_get_stream", "2Qa:Qb"),
        [0x002D] = ("window_set_echo_stream", "2QaQb:"),
        [0x002E] = ("window_get_echo_stream", "2Qa:Qb"),
        [0x002F] = ("set_window", "1Qa:"),
        [0x0030] = ("window_get_sibling", "2Qa:Qa"),
        [0x0040] = ("stream_iterate", "3Qb<Iu:Qb"),
        [0x0041] = ("stream_get_rock", "2Qb:Iu"),
        [0x0042] = ("stream_open_file", "4QcIuIu:Qb"),
        [0x0043] = ("stream_open_memory", "4&#!CnIuIu:Qb"),
        [0x0044] = ("stream_close", "2Qb<[2IuIu]:"),
        [0x0045] = ("stream_set_position", "3QbIsIu:"),
        [0x0046] = ("stream_get_position", "2Qb:Iu"),
        [0x0047] = ("stream_set_current", "1Qb:"),
        [0x0048] = ("stream_get_current", "1:Qb"),
        [0x0049] = ("stream_open_resource", "3IuIu:Qb"),
        [0x0060] = ("fileref_create_temp", "3IuIu:Qc"),
        [0x0061] = ("fileref_create_by_name", "4IuSIu:Qc"),
        [0x0062] = ("fileref_create_by_prompt", "4IuIuIu:Qc"),
        [0x0063] = ("fileref_destroy", "1Qc:"),
        [0x0064] = ("fileref_iterate", "3Qc<Iu:Qc"),
        [0x0065] = ("fileref_get_rock", "2Qc:Iu"),
        [0x0066] = ("fileref_delete_file", "1Qc:"),
        [0x0067] = ("fileref_does_file_exist", "2Qc:Iu"),
        [0x0068] = ("fileref_create_from_fileref", "4IuQcIu:Qc"),
        [0x0080] = ("put_char", "1Cu:"),
        [0x0081] = ("put_char_stream", "2QbCu:"),
        [0x0082] = ("put_string", "1S:"),
        [0x0083] = ("put_string_stream", "2QbS:"),
        [0x0084] = ("put_buffer", "1>+#Cn:"),
        [0x0085] = ("put_buffer_stream", "2Qb>+#Cn:"),
        [0x0086] = ("set_style", "1Iu:"),
        [0x0087] = ("set_style_stream", "2QbIu:"),
        [0x0090] = ("get_char_stream", "2Qb:Is"),
        [0x0091] = ("get_line_stream", "3Qb<+#Cn:Iu"),
        [0x0092] = ("get_buffer_stream", "3Qb<+#Cn:Iu"),
        [0x00A0] = ("char_to_lower", "2Cu:Cu"),
        [0x00A1] = ("char_to_upper", "2Cu:Cu"),
        [0x00B0] = ("stylehint_set", "4IuIuIuIs:"),
        [0x00B1] = ("stylehint_clear", "3IuIuIu:"),
        [0x00B2] = ("style_distinguish", "4QaIuIu:Iu"),
        [0x00B3] = ("style_measure", "5QaIuIu<Iu:Iu"),
        [0x00C0] = ("select", "1<+[4IuQaIuIu]:"),
        [0x00C1] = ("select_poll", "1<+[4IuQaIuIu]:"),
        [0x00D0] = ("request_line_event", "3Qa&+#!CnIu:"),
        [0x00D1] = ("cancel_line_event", "2Qa<[4IuQaIuIu]:"),
        [0x00D2] = ("request_char_event", "1Qa:"),
        [0x00D3] = ("cancel_char_event", "1Qa:"),
        [0x00D4] = ("request_mouse_event", "1Qa:"),
        [0x00D5] = ("cancel_mouse_event", "1Qa:"),
        [0x00D6] = ("request_timer_events", "1Iu:"),
        [0x00E0] = ("image_get_info", "4Iu<Iu<Iu:Iu"),
        [0x00E1] = ("image_draw", "5QaIuIsIs:Iu"),
        [0x00E2] = ("image_draw_scaled", "7QaIuIsIsIuIu:Iu"),
        [0x00E8] = ("window_flow_break", "1Qa:"),
        [0x00E9] = ("window_erase_rect", "5QaIsIsIuIu:"),
        [0x00EA] = ("window_fill_rect", "6QaIuIsIsIuIu:"),
        [0x00EB] = ("window_set_background_color", "2QaIu:"),
        [0x00EC] = ("image_draw_scaled_ext", "9QaIuIsIsIuIuIuIu:Iu"),
        [0x00F0] = ("schannel_iterate", "3Qd<Iu:Qd"),
        [0x00F1] = ("schannel_get_rock", "2Qd:Iu"),
        [0x00F2] = ("schannel_create", "2Iu:Qd"),
        [0x00F3] = ("schannel_destroy", "1Qd:"),
        [0x00F4] = ("schannel_create_ext", "3IuIu:Qd"),
        [0x00F7] = ("schannel_play_multi", "4>+#Qd>+#IuIu:Iu"),
        [0x00F8] = ("schannel_play", "3QdIu:Iu"),
        [0x00F9] = ("schannel_play_ext", "5QdIuIuIu:Iu"),
        [0x00FA] = ("schannel_stop", "1Qd:"),
        [0x00FB] = ("schannel_set_volume", "2QdIu:"),
        [0x00FC] = ("sound_load_hint", "2IuIu:"),
        [0x00FD] = ("schannel_set_volume_ext", "4QdIuIuIu:"),
        [0x00FE] = ("schannel_pause", "1Qd:"),
        [0x00FF] = ("schannel_unpause", "1Qd:"),
        [0x0100] = ("set_hyperlink", "1Iu:"),
        [0x0101] = ("set_hyperlink_stream", "2QbIu:"),
        [0x0102] = ("request_hyperlink_event", "1Qa:"),
        [0x0103] = ("cancel_hyperlink_event", "1Qa:"),
        [0x0120] = ("buffer_to_lower_case_uni", "3&+#IuIu:Iu"),
        [0x0121] = ("buffer_to_upper_case_uni", "3&+#IuIu:Iu"),
        [0x0122] = ("buffer_to_title_case_uni", "4&+#IuIuIu:Iu"),
        [0x0123] = ("buffer_canon_decompose_uni", "3&+#IuIu:Iu"),
        [0x0124] = ("buffer_canon_normalize_uni", "3&+#IuIu:Iu"),
        [0x0128] = ("put_char_uni", "1Iu:"),
        [0x0129] = ("put_string_uni", "1U:"),
        [0x012A] = ("put_buffer_uni", "1>+#Iu:"),
        [0x012B] = ("put_char_stream_uni", "2QbIu:"),
        [0x012C] = ("put_string_stream_uni", "2QbU:"),
        [0x012D] = ("put_buffer_stream_uni", "2Qb>+#Iu:"),
        [0x0130] = ("get_char_stream_uni", "2Qb:Is"),
        [0x0131] = ("get_buffer_stream_uni", "3Qb<+#Iu:Iu"),
        [0x0132] = ("get_line_stream_uni", "3Qb<+#Iu:Iu"),
        [0x0138] = ("stream_open_file_uni", "4QcIuIu:Qb"),
        [0x0139] = ("stream_open_memory_uni", "4&#!IuIuIu:Qb"),
        [0x013A] = ("stream_open_resource_uni", "3IuIu:Qb"),
        [0x0140] = ("request_char_event_uni", "1Qa:"),
        [0x0141] = ("request_line_event_uni", "3Qa&+#!IuIu:"),
        [0x0150] = ("set_echo_line_event", "2QaIu:"),
        [0x0151] = ("set_terminators_line_event", "2Qa>#Iu:"),
        [0x0160] = ("current_time", "1<+[3IsIuIs]:"),
        [0x0161] = ("current_simple_time", "2Iu:Is"),
        [0x0168] = ("time_to_date_utc", "2>+[3IsIuIs]<+[8IsIsIsIsIsIsIsIs]:"),
        [0x0169] = ("time_to_date_local", "2>+[3IsIuIs]<+[8IsIsIsIsIsIsIsIs]:"),
        [0x016A] = ("simple_time_to_date_utc", "3IsIu<+[8IsIsIsIsIsIsIsIs]:"),
        [0x016B] = ("simple_time_to_date_local", "3IsIu<+[8IsIsIsIsIsIsIsIs]:"),
        [0x016C] = ("date_to_time_utc", "2>+[8IsIsIsIsIsIsIsIs]<+[3IsIuIs]:"),
        [0x016D] = ("date_to_time_local", "2>+[8IsIsIsIsIsIsIsIs]<+[3IsIuIs]:"),
        [0x016E] = ("date_to_simple_time_utc", "3>+[8IsIsIsIsIsIsIsIs]Iu:Is"),
        [0x016F] = ("date_to_simple_time_local", "3>+[8IsIsIsIsIsIsIsIs]Iu:Is"),
    };

    // The whole point of generating prototype strings instead of
    // transcribing them: every declared signature must render to exactly
    // the string gi_dispa.c hand-writes. Same selectors, same names,
    // same prototypes, nothing missing and nothing extra. A
    // transcription error anywhere in the table fails here by name.
    [Fact]
    public void EverySignatureRendersGiDispaExactly()
    {
        Assert.Equal(123, GiDispa.Count);
        Assert.Equal([.. GiDispa.Keys.Order()], [.. Signatures.All.Keys.Order()]);

        foreach (var (number, (name, prototype)) in GiDispa)
        {
            var signature = Signatures.Lookup(number)!;

            Assert.Equal((number, name), (number, signature.Name));
            Assert.Equal((name, prototype), (name, signature.Prototype));
            Assert.Equal("glk_" + name, signature.GlkName);
        }
    }

    // Lookup answers by selector; an unknown number, and 0x0002 which
    // gi_dispa.c declares uninvokable, answer nothing at all.
    [Theory]
    [InlineData(0x0002)]
    [InlineData(0x0000)]
    [InlineData(0x9999)]
    public void OnlyDeclaredSelectorsAnswer(int number) => Assert.Null(Signatures.Lookup(number));

    // The items answer what the marshalling asks of them: which of the
    // four classes an opaque item names, which items are addresses
    // rather than values, and which way a value travels.
    [Fact]
    public void ItemsAnswerWhatMarshallingAsks()
    {
        var iterate = Signatures.Lookup(0x0020)!;
        var window = iterate.Args[0];
        var rock = iterate.Args[1];

        Assert.True(window.IsOpaque);
        Assert.Equal(OpaqueClass.Window, window.ClassNumber);
        Assert.False(window.IsReference);
        Assert.False(window.PassesIn);
        Assert.False(window.PassesOut);

        Assert.True(rock.IsReference);
        Assert.False(rock.PassesIn);
        Assert.True(rock.PassesOut);
        Assert.Null(rock.ClassNumber);

        // A plain item names no class and is no address.
        var gestalt = Signatures.Lookup(0x0004)!.Args[0];

        Assert.False(gestalt.IsOpaque);
        Assert.False(gestalt.IsString);
        Assert.False(gestalt.SignExtends);
        Assert.Equal(4, gestalt.ElementSize);
    }

    // The four opaque codes map onto the class numbers gi_dispa.h gives
    // them, in order.
    [Theory]
    [InlineData(0x0020, OpaqueClass.Window)]
    [InlineData(0x0040, OpaqueClass.Stream)]
    [InlineData(0x0064, OpaqueClass.FileRef)]
    [InlineData(0x00F0, OpaqueClass.SoundChannel)]
    public void TheFourOpaqueCodesNameTheirClasses(int selector, int expected) =>
        Assert.Equal(expected, Signatures.Lookup(selector)!.Args[0].ClassNumber);

    // A string argument is an address the bridge reads a string object
    // from, and the two widths are told apart by their codes.
    [Fact]
    public void StringItemsAreKnownByTheirCodes()
    {
        Assert.True(Signatures.Lookup(0x0082)!.Args[0].IsString);
        Assert.Equal("S", Signatures.Lookup(0x0082)!.Args[0].Code);
        Assert.Equal("U", Signatures.Lookup(0x0129)!.Args[0].Code);
    }

    // A signed item is read as a two's complement negative by whatever
    // receives it, and the char types are the only ones a byte wide.
    [Fact]
    public void SignAndWidthComeOffTheCode()
    {
        Assert.True(Signatures.Lookup(0x0045)!.Args[1].SignExtends);
        Assert.Equal(4, Signatures.Lookup(0x0045)!.Args[1].ElementSize);
        Assert.Equal(1, Signatures.Lookup(0x0084)!.Args[0].ElementSize);
        Assert.Equal(1, Signatures.Lookup(0x0080)!.Args[0].ElementSize);
        Assert.Equal(4, Signatures.Lookup(0x012A)!.Args[0].ElementSize);
    }

    // "An array argument, unlike a string argument, is always followed
    // by an array length argument", so an array costs two words where
    // everything else costs one.
    [Fact]
    public void WordCountsIncludeArrayLengths()
    {
        // glk_put_buffer takes one array, which is itself two words: an
        // address and a count.
        Assert.Equal(2, Signatures.Lookup(0x0084)!.WordCount);
        Assert.Equal(2, Signatures.Lookup(0x0084)!.Args[0].WordCount);

        // Where a plain item is one.
        Assert.Equal(1, Signatures.Lookup(0x0086)!.Args[0].WordCount);

        // glk_window_open takes five plain words.
        Assert.Equal(5, Signatures.Lookup(0x0023)!.WordCount);

        // glk_schannel_play_multi takes two arrays and a word.
        Assert.Equal(5, Signatures.Lookup(0x00F7)!.WordCount);

        // And a function with no arguments takes none.
        Assert.Equal(0, Signatures.Lookup(0x0001)!.WordCount);
    }

    // A struct is one reference carrying its fields, and the fields are
    // items in their own right: an event names a window in its second.
    [Fact]
    public void AStructCarriesItsFieldsAsItems()
    {
        var evt = Signatures.Lookup(0x00C0)!.Args[0];

        Assert.True(evt.IsStruct);
        Assert.True(evt.NonNull);
        Assert.Equal(4, evt.Fields.Count);
        Assert.Equal(OpaqueClass.Window, evt.Fields[1].ClassNumber);
        Assert.Equal(1, evt.WordCount);
    }

    // An array Glk keeps after the call says so, which is what tells the
    // bridge a live view has to outlive the call.
    [Fact]
    public void ARetainedArraySaysSo()
    {
        var buffer = Signatures.Lookup(0x00D0)!.Args[1];

        Assert.True(buffer.IsArray);
        Assert.True(buffer.Retained);
        Assert.True(buffer.NonNull);
        Assert.True(buffer.PassesIn);
        Assert.True(buffer.PassesOut);
    }

    // Every scalar reference in the whole table travels outward:
    // nothing in Glk 0.7.6 passes a bare word in by address, and only
    // structs travel inward. The bridge leans on that, so it is held
    // here rather than left as a thing someone once noticed.
    [Fact]
    public void EveryScalarReferenceTravelsOutward()
    {
        var inward = Signatures.All.Values
            .SelectMany(signature => signature.Args.Select(arg => (signature.GlkName, arg)))
            .Where(pair => pair.arg.IsReference && !pair.arg.IsArray && !pair.arg.IsStruct)
            .Where(pair => pair.arg.PassesIn)
            .Select(pair => pair.GlkName)
            .ToArray();

        Assert.Empty(inward);
    }

    // The model answers for shapes the table happens not to use as well,
    // because the grammar has them and a later Glk may.
    [Fact]
    public void TheGrammarAnswersForShapesTheTableDoesNotUse()
    {
        // A signed char is a byte, and read as a negative.
        var signedChar = new Item("Cs");

        Assert.True(signedChar.SignExtends);
        Assert.Equal(1, signedChar.ElementSize);

        // The return value carries the ":" direction, and travels out.
        var result = new Item("Iu") with { Ref = ":" };

        Assert.True(result.PassesOut);
        Assert.False(result.PassesIn);
        Assert.False(result.IsReference);

        // A scalar passing both ways is an address, and travels each way.
        var both = new Item("Iu") with { Ref = "&" };

        Assert.True(both.IsReference);
        Assert.True(both.PassesIn);
        Assert.True(both.PassesOut);
    }

    // Items are values: two written the same way are the same item.
    [Fact]
    public void ItemsCompareByWhatTheyDeclare()
    {
        var word = new Item("Iu");

        Assert.Equal(word, new Item("Iu"));
        Assert.Equal(word.GetHashCode(), new Item("Iu").GetHashCode());
        Assert.NotEqual(word, new Item("Is"));
        Assert.NotEqual(word, word with { IsArray = true });
    }
}
