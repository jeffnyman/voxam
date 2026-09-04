namespace Voxam.Core;

public enum OperandKind
{
    Large = 0,
    Small = 1,
    Variable = 2,
    Omitted = 3,
}

public readonly record struct Operand(OperandKind Kind, int Value);

/// <summary>A branch rider (§4.7): offsets 0 and 1 mean return false and return true.</summary>
public readonly record struct Branch(bool OnTrue, int Offset)
{
    public bool ReturnsFalse => Offset == 0;
    public bool ReturnsTrue => Offset == 1;
    public int Target(int after) => after + Offset - 2;
}

public enum Op
{
    Je, Jl, Jg, DecChk, IncChk, Jin, Test, Or, And, TestAttr, SetAttr, ClearAttr, Store,
    InsertObj, Loadw, Loadb, GetProp, GetPropAddr, GetNextProp, Add, Sub, Mul, Div, Mod,
    Call2s, Call2n, SetColour, Throw,
    Jz, GetSibling, GetChild, GetParent, GetPropLen, Inc, Dec, PrintAddr, Call1s, RemoveObj,
    PrintObj, Ret, Jump, PrintPaddr, Load, Not, Call1n,
    Rtrue, Rfalse, Print, PrintRet, Nop, Save, Restore, Restart, RetPopped, Pop, Catch, Quit,
    NewLine, ShowStatus, Verify, Piracy,
    Call, Storew, Storeb, PutProp, Sread, Aread, PrintChar, PrintNum, Random, Push, Pull,
    SplitWindow, SetWindow, CallVs2, EraseWindow, EraseLine, SetCursor, GetCursor,
    SetTextStyle, BufferMode, OutputStream, InputStream, SoundEffect, ReadChar, ScanTable,
    CallVn, CallVn2, Tokenise, EncodeText, CopyTable, PrintTable, CheckArgCount,
    LogShift, ArtShift, SetFont, DrawPicture, PictureData, ErasePicture, SetMargins,
    SaveUndo, RestoreUndo, PrintUnicode, CheckUnicode, SetTrueColour, MoveWindow, WindowSize,
    WindowStyle, GetWindProp, ScrollWindow, PopStack, ReadMouse, MouseWindow, PushStack,
    PutWindProp, PrintForm, MakeMenu, PictureTable, BufferScreen, DrawImage,
    ExtPrivate, ExtReserved,
}

public readonly record struct OpInfo(Op Op, string Name, bool Stores = false, bool Branches = false, bool HasText = false);

/// <summary>The opcode tables: names, version spans, and rider flags (§14).</summary>
public static class Opcodes
{
    private readonly record struct Entry(int First, int Last, OpInfo Info);

    private static Entry E(Op op, string name, int first = 1, int last = 8, bool stores = false, bool branches = false, bool text = false) =>
        new(first, last, new OpInfo(op, name, stores, branches, text));

    private static readonly Dictionary<int, Entry[]> TwoOp = new()
    {
        [0x01] = [E(Op.Je, "je", branches: true)],
        [0x02] = [E(Op.Jl, "jl", branches: true)],
        [0x03] = [E(Op.Jg, "jg", branches: true)],
        [0x04] = [E(Op.DecChk, "dec_chk", branches: true)],
        [0x05] = [E(Op.IncChk, "inc_chk", branches: true)],
        [0x06] = [E(Op.Jin, "jin", branches: true)],
        [0x07] = [E(Op.Test, "test", branches: true)],
        [0x08] = [E(Op.Or, "or", stores: true)],
        [0x09] = [E(Op.And, "and", stores: true)],
        [0x0A] = [E(Op.TestAttr, "test_attr", branches: true)],
        [0x0B] = [E(Op.SetAttr, "set_attr")],
        [0x0C] = [E(Op.ClearAttr, "clear_attr")],
        [0x0D] = [E(Op.Store, "store")],
        [0x0E] = [E(Op.InsertObj, "insert_obj")],
        [0x0F] = [E(Op.Loadw, "loadw", stores: true)],
        [0x10] = [E(Op.Loadb, "loadb", stores: true)],
        [0x11] = [E(Op.GetProp, "get_prop", stores: true)],
        [0x12] = [E(Op.GetPropAddr, "get_prop_addr", stores: true)],
        [0x13] = [E(Op.GetNextProp, "get_next_prop", stores: true)],
        [0x14] = [E(Op.Add, "add", stores: true)],
        [0x15] = [E(Op.Sub, "sub", stores: true)],
        [0x16] = [E(Op.Mul, "mul", stores: true)],
        [0x17] = [E(Op.Div, "div", stores: true)],
        [0x18] = [E(Op.Mod, "mod", stores: true)],
        [0x19] = [E(Op.Call2s, "call_2s", first: 4, stores: true)],
        [0x1A] = [E(Op.Call2n, "call_2n", first: 5)],
        [0x1B] = [E(Op.SetColour, "set_colour", first: 5)],
        [0x1C] = [E(Op.Throw, "throw", first: 5)],
    };

    private static readonly Dictionary<int, Entry[]> OneOp = new()
    {
        [0x0] = [E(Op.Jz, "jz", branches: true)],
        [0x1] = [E(Op.GetSibling, "get_sibling", stores: true, branches: true)],
        [0x2] = [E(Op.GetChild, "get_child", stores: true, branches: true)],
        [0x3] = [E(Op.GetParent, "get_parent", stores: true)],
        [0x4] = [E(Op.GetPropLen, "get_prop_len", stores: true)],
        [0x5] = [E(Op.Inc, "inc")],
        [0x6] = [E(Op.Dec, "dec")],
        [0x7] = [E(Op.PrintAddr, "print_addr")],
        [0x8] = [E(Op.Call1s, "call_1s", first: 4, stores: true)],
        [0x9] = [E(Op.RemoveObj, "remove_obj")],
        [0xA] = [E(Op.PrintObj, "print_obj")],
        [0xB] = [E(Op.Ret, "ret")],
        [0xC] = [E(Op.Jump, "jump")],
        [0xD] = [E(Op.PrintPaddr, "print_paddr")],
        [0xE] = [E(Op.Load, "load", stores: true)],
        [0xF] = [E(Op.Not, "not", last: 4, stores: true), E(Op.Call1n, "call_1n", first: 5)],
    };

    private static readonly Dictionary<int, Entry[]> ZeroOp = new()
    {
        [0x0] = [E(Op.Rtrue, "rtrue")],
        [0x1] = [E(Op.Rfalse, "rfalse")],
        [0x2] = [E(Op.Print, "print", text: true)],
        [0x3] = [E(Op.PrintRet, "print_ret", text: true)],
        [0x4] = [E(Op.Nop, "nop")],
        [0x5] = [E(Op.Save, "save", last: 3, branches: true), E(Op.Save, "save", first: 4, last: 4, stores: true)],
        [0x6] = [E(Op.Restore, "restore", last: 3, branches: true), E(Op.Restore, "restore", first: 4, last: 4, stores: true)],
        [0x7] = [E(Op.Restart, "restart")],
        [0x8] = [E(Op.RetPopped, "ret_popped")],
        [0x9] = [E(Op.Pop, "pop", last: 4), E(Op.Catch, "catch", first: 5, stores: true)],
        [0xA] = [E(Op.Quit, "quit")],
        [0xB] = [E(Op.NewLine, "new_line")],
        [0xC] = [E(Op.ShowStatus, "show_status", first: 3, last: 3)],
        [0xD] = [E(Op.Verify, "verify", first: 3, branches: true)],
        [0xF] = [E(Op.Piracy, "piracy", first: 5, branches: true)],
    };

    private static readonly Dictionary<int, Entry[]> Var = new()
    {
        [0x00] = [E(Op.Call, "call", last: 3, stores: true), E(Op.Call, "call_vs", first: 4, stores: true)],
        [0x01] = [E(Op.Storew, "storew")],
        [0x02] = [E(Op.Storeb, "storeb")],
        [0x03] = [E(Op.PutProp, "put_prop")],
        [0x04] = [E(Op.Sread, "sread", last: 4), E(Op.Aread, "aread", first: 5, stores: true)],
        [0x05] = [E(Op.PrintChar, "print_char")],
        [0x06] = [E(Op.PrintNum, "print_num")],
        [0x07] = [E(Op.Random, "random", stores: true)],
        [0x08] = [E(Op.Push, "push")],
        [0x09] = [E(Op.Pull, "pull", last: 5), E(Op.Pull, "pull", first: 6, last: 6, stores: true), E(Op.Pull, "pull", first: 7)],
        [0x0A] = [E(Op.SplitWindow, "split_window", first: 3)],
        [0x0B] = [E(Op.SetWindow, "set_window", first: 3)],
        [0x0C] = [E(Op.CallVs2, "call_vs2", first: 4, stores: true)],
        [0x0D] = [E(Op.EraseWindow, "erase_window", first: 4)],
        [0x0E] = [E(Op.EraseLine, "erase_line", first: 4)],
        [0x0F] = [E(Op.SetCursor, "set_cursor", first: 4)],
        [0x10] = [E(Op.GetCursor, "get_cursor", first: 4)],
        [0x11] = [E(Op.SetTextStyle, "set_text_style", first: 4)],
        [0x12] = [E(Op.BufferMode, "buffer_mode", first: 4)],
        [0x13] = [E(Op.OutputStream, "output_stream", first: 3)],
        [0x14] = [E(Op.InputStream, "input_stream", first: 3)],
        [0x15] = [E(Op.SoundEffect, "sound_effect", first: 3)],
        [0x16] = [E(Op.ReadChar, "read_char", first: 4, stores: true)],
        [0x17] = [E(Op.ScanTable, "scan_table", first: 4, stores: true, branches: true)],
        [0x18] = [E(Op.Not, "not", first: 5, stores: true)],
        [0x19] = [E(Op.CallVn, "call_vn", first: 5)],
        [0x1A] = [E(Op.CallVn2, "call_vn2", first: 5)],
        [0x1B] = [E(Op.Tokenise, "tokenise", first: 5)],
        [0x1C] = [E(Op.EncodeText, "encode_text", first: 5)],
        [0x1D] = [E(Op.CopyTable, "copy_table", first: 5)],
        [0x1E] = [E(Op.PrintTable, "print_table", first: 5)],
        [0x1F] = [E(Op.CheckArgCount, "check_arg_count", first: 5, branches: true)],
    };

    private static readonly Dictionary<int, Entry[]> Ext = new()
    {
        [0x00] = [E(Op.Save, "save", first: 5, stores: true)],
        [0x01] = [E(Op.Restore, "restore", first: 5, stores: true)],
        [0x02] = [E(Op.LogShift, "log_shift", first: 5, stores: true)],
        [0x03] = [E(Op.ArtShift, "art_shift", first: 5, stores: true)],
        [0x04] = [E(Op.SetFont, "set_font", first: 5, stores: true)],
        [0x05] = [E(Op.DrawPicture, "draw_picture", first: 6)],
        [0x06] = [E(Op.PictureData, "picture_data", first: 6, branches: true)],
        [0x07] = [E(Op.ErasePicture, "erase_picture", first: 6)],
        [0x08] = [E(Op.SetMargins, "set_margins", first: 6)],
        [0x09] = [E(Op.SaveUndo, "save_undo", first: 5, stores: true)],
        [0x0A] = [E(Op.RestoreUndo, "restore_undo", first: 5, stores: true)],
        [0x0B] = [E(Op.PrintUnicode, "print_unicode", first: 5)],
        [0x0C] = [E(Op.CheckUnicode, "check_unicode", first: 5, stores: true)],
        [0x0D] = [E(Op.SetTrueColour, "set_true_colour", first: 5)],
        [0x10] = [E(Op.MoveWindow, "move_window", first: 6)],
        [0x11] = [E(Op.WindowSize, "window_size", first: 6)],
        [0x12] = [E(Op.WindowStyle, "window_style", first: 6)],
        [0x13] = [E(Op.GetWindProp, "get_wind_prop", first: 6, stores: true)],
        [0x14] = [E(Op.ScrollWindow, "scroll_window", first: 6)],
        [0x15] = [E(Op.PopStack, "pop_stack", first: 6)],
        [0x16] = [E(Op.ReadMouse, "read_mouse", first: 6)],
        [0x17] = [E(Op.MouseWindow, "mouse_window", first: 6)],
        [0x18] = [E(Op.PushStack, "push_stack", first: 6, branches: true)],
        [0x19] = [E(Op.PutWindProp, "put_wind_prop", first: 6)],
        [0x1A] = [E(Op.PrintForm, "print_form", first: 6)],
        [0x1B] = [E(Op.MakeMenu, "make_menu", first: 6, branches: true)],
        [0x1C] = [E(Op.PictureTable, "picture_table", first: 6)],
        [0x1D] = [E(Op.BufferScreen, "buffer_screen", first: 6, stores: true)],
        [0x80] = [E(Op.DrawImage, "draw_image", first: 5, last: 5), E(Op.DrawImage, "draw_image", first: 7, last: 8)],
    };

    public enum Kind { ZeroOp, OneOp, TwoOp, Var, Ext }

    public static OpInfo Lookup(Kind kind, int number, int version)
    {
        var table = kind switch
        {
            Kind.ZeroOp => ZeroOp,
            Kind.OneOp => OneOp,
            Kind.TwoOp => TwoOp,
            Kind.Var => Var,
            _ => Ext,
        };

        if (table.TryGetValue(number, out var entries))
        {
            foreach (var entry in entries)
            {
                if (entry.First <= version && version <= entry.Last)
                {
                    return entry.Info;
                }
            }
        }

        if (kind == Kind.Ext && number >= 0x80)
        {
            return new OpInfo(Op.ExtPrivate, "ext_private");
        }

        if (kind == Kind.Ext && number >= 0x1E)
        {
            return new OpInfo(Op.ExtReserved, "ext_reserved");
        }

        var label = kind switch
        {
            Kind.ZeroOp => "0OP",
            Kind.OneOp => "1OP",
            Kind.TwoOp => "2OP",
            Kind.Var => "VAR",
            _ => "EXT",
        };

        throw new ZMachineException($"{label}:{number} is not an opcode in version {version} (§14)");
    }
}

/// <summary>A single fully decoded instruction (§4.1).</summary>
public sealed class Instruction
{
    public required int Address { get; init; }
    public required OpInfo Info { get; init; }

    /// <summary>The opcode number within its table, for the reserved-opcode warning.</summary>
    public required int Number { get; init; }
    public required Operand[] Operands { get; init; }
    public required int OperandsEnd { get; init; }

    /// <summary>The store variable, or -1 when the opcode stores nothing.</summary>
    public required int StoreVariable { get; init; }

    public required Branch? Branch { get; init; }
    public required int NextAddress { get; init; }

    public Op Op => Info.Op;

    public static Instruction Decode(Memory m, int address)
    {
        var opcodeByte = m.FetchByte(address);
        var version = m.Version;
        var pos = address + 1;
        Opcodes.Kind kind;
        int number;
        OperandKind[] kinds;

        if (opcodeByte == 0xBE && version >= 5)
        {
            kind = Opcodes.Kind.Ext;
            number = m.FetchByte(pos);
            kinds = FieldTypes(m.FetchByte(pos + 1));
            pos += 2;
        }
        else if ((opcodeByte & 0xC0) == 0xC0)
        {
            var isVar = (opcodeByte & 0x20) != 0;
            kind = isVar ? Opcodes.Kind.Var : Opcodes.Kind.TwoOp;
            number = opcodeByte & 0x1F;

            if (isVar && number is 0x0C or 0x1A)
            {
                kinds = FieldTypes(m.FetchByte(pos), m.FetchByte(pos + 1));
                pos += 2;
            }
            else
            {
                kinds = FieldTypes(m.FetchByte(pos));
                pos += 1;
            }
        }
        else if ((opcodeByte & 0xC0) == 0x80)
        {
            var single = (OperandKind)((opcodeByte >> 4) & 0x3);
            var omitted = single == OperandKind.Omitted;
            kind = omitted ? Opcodes.Kind.ZeroOp : Opcodes.Kind.OneOp;
            number = opcodeByte & 0x0F;
            kinds = omitted ? [] : [single];
        }
        else
        {
            kind = Opcodes.Kind.TwoOp;
            number = opcodeByte & 0x1F;
            kinds =
            [
                (opcodeByte & 0x40) != 0 ? OperandKind.Variable : OperandKind.Small,
                (opcodeByte & 0x20) != 0 ? OperandKind.Variable : OperandKind.Small,
            ];
        }

        var operands = new Operand[kinds.Length];

        for (var i = 0; i < kinds.Length; i++)
        {
            if (kinds[i] == OperandKind.Large)
            {
                operands[i] = new Operand(kinds[i], m.FetchWord(pos));
                pos += 2;
            }
            else
            {
                operands[i] = new Operand(kinds[i], m.FetchByte(pos));
                pos += 1;
            }
        }

        var operandsEnd = pos;
        var info = Opcodes.Lookup(kind, number, version);
        var store = -1;
        Branch? branch = null;

        if (info.Stores)
        {
            store = m.FetchByte(pos);
            pos += 1;
        }

        if (info.Branches)
        {
            (branch, pos) = ReadBranch(m, pos);
        }

        if (info.HasText)
        {
            while ((m.FetchWord(pos) & 0x8000) == 0)
            {
                pos += 2;
            }

            pos += 2;
        }

        return new Instruction
        {
            Address = address,
            Info = info,
            Number = number,
            Operands = operands,
            OperandsEnd = operandsEnd,
            StoreVariable = store,
            Branch = branch,
            NextAddress = pos,
        };
    }

    /// <summary>Read a branch rider at an address (§4.7): the branch and the address past it.</summary>
    public static (Branch Branch, int After) ReadBranch(Memory m, int address)
    {
        var first = m.FetchByte(address);
        var onTrue = (first & 0x80) != 0;

        if ((first & 0x40) != 0)
        {
            return (new Branch(onTrue, first & 0x3F), address + 1);
        }

        var offset = ((first & 0x3F) << 8) | m.FetchByte(address + 1);

        if ((offset & 0x2000) != 0)
        {
            offset -= 0x4000;
        }

        return (new Branch(onTrue, offset), address + 2);
    }

    private static OperandKind[] FieldTypes(params int[] typeBytes)
    {
        var fields = new List<OperandKind>();

        foreach (var typeByte in typeBytes)
        {
            for (var shift = 6; shift >= 0; shift -= 2)
            {
                fields.Add((OperandKind)((typeByte >> shift) & 0x3));
            }
        }

        var omittedFrom = -1;

        for (var i = 0; i < fields.Count; i++)
        {
            if (fields[i] == OperandKind.Omitted)
            {
                if (omittedFrom < 0)
                {
                    omittedFrom = i;
                }
            }
            else if (omittedFrom >= 0)
            {
                var shown = string.Join(" ", typeBytes.Select(b => $"${b:x2}"));
                throw new ZMachineException($"type bytes {shown} specify an operand after an omitted one (§4.4.3)");
            }
        }

        return omittedFrom < 0 ? [.. fields] : [.. fields.Take(omittedFrom)];
    }
}
