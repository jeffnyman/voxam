using System.Collections.Frozen;

namespace Voxam.Core.Glulx.Glk;

/// <summary>
/// The opaque class numbers, from gi_dispa.h. The prototype codes Qa
/// through Qd map onto these in order.
/// </summary>
public static class OpaqueClass
{
    /// <summary>A window.</summary>
    public const int Window = 0;

    /// <summary>A stream.</summary>
    public const int Stream = 1;

    /// <summary>A file reference.</summary>
    public const int FileRef = 2;

    /// <summary>A sound channel.</summary>
    public const int SoundChannel = 3;
}

/// <summary>
/// One item in a prototype: an argument, or the return value.
/// </summary>
public sealed record Item
{
    private static readonly Item[] NoFields = [];

    private static readonly FrozenDictionary<string, int> OpaqueCodes =
        new Dictionary<string, int>(StringComparer.Ordinal)
        {
            ["Qa"] = OpaqueClass.Window,
            ["Qb"] = OpaqueClass.Stream,
            ["Qc"] = OpaqueClass.FileRef,
            ["Qd"] = OpaqueClass.SoundChannel,
        }.ToFrozenDictionary(StringComparer.Ordinal);

    /// <summary>Declare an item of one type code.</summary>
    /// <param name="code">The type code, or empty for a struct.</param>
    public Item(string code) => Code = code;

    /// <summary>
    /// The type code: Iu, Cn, Qa and kin. Empty when the item is a
    /// struct.
    /// </summary>
    public string Code { get; init; }

    /// <summary>The field types, when this item is a struct.</summary>
    public IReadOnlyList<Item> Fields { get; init; } = NoFields;

    /// <summary>
    /// The reference direction: empty for a plain value, "&lt;" out,
    /// "&gt;" in, "&amp;" both, ":" for the return value.
    /// </summary>
    public string Ref { get; init; } = "";

    /// <summary>
    /// Whether the item is an array, consuming an address and a count.
    /// </summary>
    public bool IsArray { get; init; }

    /// <summary>Whether a null reference is forbidden.</summary>
    public bool NonNull { get; init; }

    /// <summary>Whether Glk keeps the array after the call.</summary>
    public bool Retained { get; init; }

    /// <summary>Whether this item is a struct of fields.</summary>
    public bool IsStruct => Fields.Count > 0;

    /// <summary>Whether this item is one of the four opaque classes.</summary>
    public bool IsOpaque => OpaqueCodes.ContainsKey(Code);

    /// <summary>The opaque class number, or null for a plain type.</summary>
    public int? ClassNumber => OpaqueCodes.TryGetValue(Code, out var found) ? found : null;

    /// <summary>Whether this item is a string object address.</summary>
    public bool IsString => Code is "S" or "U";

    /// <summary>
    /// Whether the word is read as a two's complement negative rather
    /// than as itself. The bridge hands the bits over either way; this
    /// is what the receiving function reads them by.
    /// </summary>
    public bool SignExtends => Code is "Is" or "Cs";

    /// <summary>Bytes per element: one for the char types, four otherwise.</summary>
    public int ElementSize => Code is "Cn" or "Cu" or "Cs" ? 1 : 4;

    /// <summary>Whether a value passes from the game into Glk.</summary>
    public bool PassesIn => Ref is ">" or "&";

    /// <summary>Whether a value passes from Glk back to the game.</summary>
    public bool PassesOut => Ref is "<" or "&" or ":";

    /// <summary>Whether the game passes an address rather than a value.</summary>
    public bool IsReference => Ref is "<" or ">" or "&";

    /// <summary>
    /// How many 32-bit Glulx arguments this item consumes.
    ///
    /// "An array argument, unlike a string argument, is always followed
    /// by an array length argument", so an array is two words where
    /// everything else is one (Glulx: Miscellaneous, under the glk
    /// opcode).
    /// </summary>
    public int WordCount => IsArray ? 2 : 1;

    /// <summary>This item rendered in gi_dispa.c's prototype grammar.</summary>
    public string Prototype
    {
        get
        {
            var body = IsStruct
                ? $"[{Fields.Count}{string.Concat(Fields.Select(piece => piece.Prototype))}]"
                : Code;

            var prefix = Ref;

            if (NonNull)
            {
                prefix += "+";
            }

            if (IsArray)
            {
                prefix += "#";
            }

            if (Retained)
            {
                prefix += "!";
            }

            return prefix + body;
        }
    }
}

/// <summary>One Glk function's dispatch signature.</summary>
public sealed record Signature
{
    /// <summary>Declare one function.</summary>
    /// <param name="number">The selector the glk opcode names it by.</param>
    /// <param name="name">The bare name, without the glk_ prefix.</param>
    /// <param name="args">The argument items, in call order.</param>
    /// <param name="result">The return item, or null for a void function.</param>
    public Signature(int number, string name, IReadOnlyList<Item> args, Item? result)
    {
        Number = number;
        Name = name;
        Args = args;
        Result = result;
    }

    /// <summary>The selector the glk opcode names the function by.</summary>
    public int Number { get; }

    /// <summary>The bare function name, without the glk_ prefix.</summary>
    public string Name { get; }

    /// <summary>The argument items, in call order.</summary>
    public IReadOnlyList<Item> Args { get; }

    /// <summary>The return item, or null for a void function.</summary>
    public Item? Result { get; }

    /// <summary>The function's full name, glk_ prefix included.</summary>
    public string GlkName => "glk_" + Name;

    /// <summary>Total 32-bit arguments the glk opcode must supply.</summary>
    public int WordCount => Args.Sum(arg => arg.WordCount);

    /// <summary>The whole signature in gi_dispa.c's prototype grammar.</summary>
    public string Prototype
    {
        get
        {
            var count = Args.Count + (Result is null ? 0 : 1);
            var body = string.Concat(Args.Select(arg => arg.Prototype));
            var tail = Result is null ? ":" : (Result with { Ref = ":" }).Prototype;

            return $"{count}{body}{tail}";
        }
    }
}

/// <summary>
/// The Glk dispatch layer: every function's signature.
///
/// The C world's gi_dispa.c, vendored with cheapglk, hand-writes a
/// thousand-line switch returning prototype strings like
/// "4&amp;#!CnIuIu:Qb". Voxam does the inverse: each function is
/// declared as a readable argument list, and the prototype string is
/// generated from it. The generated strings are then checked against
/// the ones parsed out of gi_dispa.c, for every function, in the tests,
/// which turns a transcription error into a test failure instead of a
/// runtime mystery.
///
/// The grammar, as gi_dispa.c defines it: a prototype is a count
/// followed by items, like "3Qa&lt;Iu:Qa" for glk_window_iterate. The
/// count includes the return value, which is the item carrying the ":"
/// prefix; a void function ends with a bare ":" that is not counted.
/// Prefixes appear in the order [ref][+][#][!] before the type code:
/// reference direction, nonnull, array, retained.
///
/// The table is named for what it holds rather than for the module,
/// because the machine's own opcode dispatch already owns the shorter
/// word one namespace out.
/// </summary>
public static class Signatures
{
    // The atoms the table is written in. A Unicode character argument
    // is U32 on purpose: it is a full word, where the Latin-1 char
    // types are bytes.
    private static readonly Item U32 = new("Iu");
    private static readonly Item I32 = new("Is");
    private static readonly Item Char = new("Cn");
    private static readonly Item UChar = new("Cu");
    private static readonly Item CString = new("S");
    private static readonly Item UString = new("U");

    private static readonly Item Window = new("Qa");
    private static readonly Item Stream = new("Qb");
    private static readonly Item FileRef = new("Qc");
    private static readonly Item SChannel = new("Qd");

    // The well-known structures, named in gi_dispa.h: event_t,
    // stream_result_t, glktimeval_t, glkdate_t.
    private static readonly Item Event = Struct(U32, Window, U32, U32);
    private static readonly Item StreamResult = Struct(U32, U32);
    private static readonly Item TimeVal = Struct(I32, U32, I32);
    private static readonly Item Date = Struct(I32, I32, I32, I32, I32, I32, I32, I32);

    private static readonly FrozenDictionary<int, Signature> Table = Built();

    /// <summary>Every declared signature, keyed by selector.</summary>
    public static IReadOnlyDictionary<int, Signature> All => Table;

    /// <summary>The signature for a Glk selector, or null if unknown.</summary>
    /// <param name="number">The selector to look up.</param>
    public static Signature? Lookup(int number) =>
        Table.TryGetValue(number, out var found) ? found : null;

    /// <summary>An output reference: Glk writes, the game reads.</summary>
    private static Item Out(Item item, bool nonnull = false) =>
        item with { Ref = "<", NonNull = nonnull };

    /// <summary>An input reference: the game writes, Glk reads.</summary>
    private static Item Into(Item item, bool nonnull = false) =>
        item with { Ref = ">", NonNull = nonnull };

    /// <summary>A struct of fields, passed as one reference.</summary>
    private static Item Struct(params Item[] fields) => new("") { Fields = fields };

    /// <summary>An array of items: an address and a count, two words.</summary>
    private static Item Array(Item item, string reference, bool nonnull = false, bool retained = false) =>
        item with { Ref = reference, IsArray = true, NonNull = nonnull, Retained = retained };

    // The table, ordered as in gi_dispa.c. glk_set_interrupt_handler
    // (0x0002) is absent on purpose: its prototype there is NULL,
    // meaning it cannot be invoked through the dispatch layer at all.
    private static FrozenDictionary<int, Signature> Built()
    {
        var table = new Dictionary<int, Signature>();

        void Declare(int number, string name, Item[] args, Item? result = null) =>
            table[number] = new Signature(number, name, args, result);

        // Core
        Declare(0x0001, "exit", []);
        Declare(0x0003, "tick", []);
        Declare(0x0004, "gestalt", [U32, U32], U32);
        Declare(0x0005, "gestalt_ext", [U32, U32, Array(U32, "&")], U32);

        // Windows
        Declare(0x0020, "window_iterate", [Window, Out(U32)], Window);
        Declare(0x0021, "window_get_rock", [Window], U32);
        Declare(0x0022, "window_get_root", [], Window);
        Declare(0x0023, "window_open", [Window, U32, U32, U32, U32], Window);
        Declare(0x0024, "window_close", [Window, Out(StreamResult)]);
        Declare(0x0025, "window_get_size", [Window, Out(U32), Out(U32)]);
        Declare(0x0026, "window_set_arrangement", [Window, U32, U32, Window]);
        Declare(0x0027, "window_get_arrangement", [Window, Out(U32), Out(U32), Out(Window)]);
        Declare(0x0028, "window_get_type", [Window], U32);
        Declare(0x0029, "window_get_parent", [Window], Window);
        Declare(0x002A, "window_clear", [Window]);
        Declare(0x002B, "window_move_cursor", [Window, U32, U32]);
        Declare(0x002C, "window_get_stream", [Window], Stream);
        Declare(0x002D, "window_set_echo_stream", [Window, Stream]);
        Declare(0x002E, "window_get_echo_stream", [Window], Stream);
        Declare(0x002F, "set_window", [Window]);
        Declare(0x0030, "window_get_sibling", [Window], Window);

        // Streams
        Declare(0x0040, "stream_iterate", [Stream, Out(U32)], Stream);
        Declare(0x0041, "stream_get_rock", [Stream], U32);
        Declare(0x0042, "stream_open_file", [FileRef, U32, U32], Stream);
        Declare(0x0043, "stream_open_memory", [Array(Char, "&", retained: true), U32, U32], Stream);
        Declare(0x0044, "stream_close", [Stream, Out(StreamResult)]);
        Declare(0x0045, "stream_set_position", [Stream, I32, U32]);
        Declare(0x0046, "stream_get_position", [Stream], U32);
        Declare(0x0047, "stream_set_current", [Stream]);
        Declare(0x0048, "stream_get_current", [], Stream);
        Declare(0x0049, "stream_open_resource", [U32, U32], Stream);

        // File references
        Declare(0x0060, "fileref_create_temp", [U32, U32], FileRef);
        Declare(0x0061, "fileref_create_by_name", [U32, CString, U32], FileRef);
        Declare(0x0062, "fileref_create_by_prompt", [U32, U32, U32], FileRef);
        Declare(0x0063, "fileref_destroy", [FileRef]);
        Declare(0x0064, "fileref_iterate", [FileRef, Out(U32)], FileRef);
        Declare(0x0065, "fileref_get_rock", [FileRef], U32);
        Declare(0x0066, "fileref_delete_file", [FileRef]);
        Declare(0x0067, "fileref_does_file_exist", [FileRef], U32);
        Declare(0x0068, "fileref_create_from_fileref", [U32, FileRef, U32], FileRef);

        // Character output
        Declare(0x0080, "put_char", [UChar]);
        Declare(0x0081, "put_char_stream", [Stream, UChar]);
        Declare(0x0082, "put_string", [CString]);
        Declare(0x0083, "put_string_stream", [Stream, CString]);
        Declare(0x0084, "put_buffer", [Array(Char, ">", nonnull: true)]);
        Declare(0x0085, "put_buffer_stream", [Stream, Array(Char, ">", nonnull: true)]);
        Declare(0x0086, "set_style", [U32]);
        Declare(0x0087, "set_style_stream", [Stream, U32]);

        // Character input
        Declare(0x0090, "get_char_stream", [Stream], I32);
        Declare(0x0091, "get_line_stream", [Stream, Array(Char, "<", nonnull: true)], U32);
        Declare(0x0092, "get_buffer_stream", [Stream, Array(Char, "<", nonnull: true)], U32);

        // Case mapping
        Declare(0x00A0, "char_to_lower", [UChar], UChar);
        Declare(0x00A1, "char_to_upper", [UChar], UChar);

        // Style hints
        Declare(0x00B0, "stylehint_set", [U32, U32, U32, I32]);
        Declare(0x00B1, "stylehint_clear", [U32, U32, U32]);
        Declare(0x00B2, "style_distinguish", [Window, U32, U32], U32);
        Declare(0x00B3, "style_measure", [Window, U32, U32, Out(U32)], U32);

        // Events
        Declare(0x00C0, "select", [Out(Event, nonnull: true)]);
        Declare(0x00C1, "select_poll", [Out(Event, nonnull: true)]);
        Declare(0x00D0, "request_line_event", [Window, Array(Char, "&", nonnull: true, retained: true), U32]);
        Declare(0x00D1, "cancel_line_event", [Window, Out(Event)]);
        Declare(0x00D2, "request_char_event", [Window]);
        Declare(0x00D3, "cancel_char_event", [Window]);
        Declare(0x00D4, "request_mouse_event", [Window]);
        Declare(0x00D5, "cancel_mouse_event", [Window]);
        Declare(0x00D6, "request_timer_events", [U32]);

        // Graphics
        Declare(0x00E0, "image_get_info", [U32, Out(U32), Out(U32)], U32);
        Declare(0x00E1, "image_draw", [Window, U32, I32, I32], U32);
        Declare(0x00E2, "image_draw_scaled", [Window, U32, I32, I32, U32, U32], U32);
        Declare(0x00E8, "window_flow_break", [Window]);
        Declare(0x00E9, "window_erase_rect", [Window, I32, I32, U32, U32]);
        Declare(0x00EA, "window_fill_rect", [Window, U32, I32, I32, U32, U32]);
        Declare(0x00EB, "window_set_background_color", [Window, U32]);
        Declare(0x00EC, "image_draw_scaled_ext", [Window, U32, I32, I32, U32, U32, U32, U32], U32);

        // Sound channels
        Declare(0x00F0, "schannel_iterate", [SChannel, Out(U32)], SChannel);
        Declare(0x00F1, "schannel_get_rock", [SChannel], U32);
        Declare(0x00F2, "schannel_create", [U32], SChannel);
        Declare(0x00F3, "schannel_destroy", [SChannel]);
        Declare(0x00F4, "schannel_create_ext", [U32, U32], SChannel);
        Declare(
            0x00F7,
            "schannel_play_multi",
            [Array(SChannel, ">", nonnull: true), Array(U32, ">", nonnull: true), U32],
            U32);
        Declare(0x00F8, "schannel_play", [SChannel, U32], U32);
        Declare(0x00F9, "schannel_play_ext", [SChannel, U32, U32, U32], U32);
        Declare(0x00FA, "schannel_stop", [SChannel]);
        Declare(0x00FB, "schannel_set_volume", [SChannel, U32]);
        Declare(0x00FC, "sound_load_hint", [U32, U32]);
        Declare(0x00FD, "schannel_set_volume_ext", [SChannel, U32, U32, U32]);
        Declare(0x00FE, "schannel_pause", [SChannel]);
        Declare(0x00FF, "schannel_unpause", [SChannel]);

        // Hyperlinks
        Declare(0x0100, "set_hyperlink", [U32]);
        Declare(0x0101, "set_hyperlink_stream", [Stream, U32]);
        Declare(0x0102, "request_hyperlink_event", [Window]);
        Declare(0x0103, "cancel_hyperlink_event", [Window]);

        // Unicode case mapping and normalization
        Declare(0x0120, "buffer_to_lower_case_uni", [Array(U32, "&", nonnull: true), U32], U32);
        Declare(0x0121, "buffer_to_upper_case_uni", [Array(U32, "&", nonnull: true), U32], U32);
        Declare(0x0122, "buffer_to_title_case_uni", [Array(U32, "&", nonnull: true), U32, U32], U32);
        Declare(0x0123, "buffer_canon_decompose_uni", [Array(U32, "&", nonnull: true), U32], U32);
        Declare(0x0124, "buffer_canon_normalize_uni", [Array(U32, "&", nonnull: true), U32], U32);

        // Unicode output
        Declare(0x0128, "put_char_uni", [U32]);
        Declare(0x0129, "put_string_uni", [UString]);
        Declare(0x012A, "put_buffer_uni", [Array(U32, ">", nonnull: true)]);
        Declare(0x012B, "put_char_stream_uni", [Stream, U32]);
        Declare(0x012C, "put_string_stream_uni", [Stream, UString]);
        Declare(0x012D, "put_buffer_stream_uni", [Stream, Array(U32, ">", nonnull: true)]);

        // Unicode input
        Declare(0x0130, "get_char_stream_uni", [Stream], I32);
        Declare(0x0131, "get_buffer_stream_uni", [Stream, Array(U32, "<", nonnull: true)], U32);
        Declare(0x0132, "get_line_stream_uni", [Stream, Array(U32, "<", nonnull: true)], U32);
        Declare(0x0138, "stream_open_file_uni", [FileRef, U32, U32], Stream);
        Declare(0x0139, "stream_open_memory_uni", [Array(U32, "&", retained: true), U32, U32], Stream);
        Declare(0x013A, "stream_open_resource_uni", [U32, U32], Stream);
        Declare(0x0140, "request_char_event_uni", [Window]);
        Declare(0x0141, "request_line_event_uni", [Window, Array(U32, "&", nonnull: true, retained: true), U32]);

        // Line input control
        Declare(0x0150, "set_echo_line_event", [Window, U32]);
        Declare(0x0151, "set_terminators_line_event", [Window, Array(U32, ">")]);

        // Date and time
        Declare(0x0160, "current_time", [Out(TimeVal, nonnull: true)]);
        Declare(0x0161, "current_simple_time", [U32], I32);
        Declare(0x0168, "time_to_date_utc", [Into(TimeVal, nonnull: true), Out(Date, nonnull: true)]);
        Declare(0x0169, "time_to_date_local", [Into(TimeVal, nonnull: true), Out(Date, nonnull: true)]);
        Declare(0x016A, "simple_time_to_date_utc", [I32, U32, Out(Date, nonnull: true)]);
        Declare(0x016B, "simple_time_to_date_local", [I32, U32, Out(Date, nonnull: true)]);
        Declare(0x016C, "date_to_time_utc", [Into(Date, nonnull: true), Out(TimeVal, nonnull: true)]);
        Declare(0x016D, "date_to_time_local", [Into(Date, nonnull: true), Out(TimeVal, nonnull: true)]);
        Declare(0x016E, "date_to_simple_time_utc", [Into(Date, nonnull: true), U32], I32);
        Declare(0x016F, "date_to_simple_time_local", [Into(Date, nonnull: true), U32], I32);

        return table.ToFrozenDictionary();
    }
}
