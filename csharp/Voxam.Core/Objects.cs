namespace Voxam.Core;

/// <summary>The object table: tree, attributes, and properties (§12).</summary>
public sealed class ObjectTable
{
    private readonly Memory _m;
    private readonly bool _small;
    private readonly int _base;

    public ObjectTable(Memory m)
    {
        _m = m;
        _small = m.Version <= 3;
        _base = m.ReadWord(Header.ObjectTable);
    }

    private int MaxProperties => _small ? 31 : 63;
    private int EntrySize => _small ? 9 : 14;
    private int Entries => _base + 2 * MaxProperties;
    private int Entry(int obj) => Entries + (obj - 1) * EntrySize;

    public int Parent(int obj) => _small ? _m.ReadByte(Entry(obj) + 4) : _m.ReadWord(Entry(obj) + 6);
    public int Sibling(int obj) => _small ? _m.ReadByte(Entry(obj) + 5) : _m.ReadWord(Entry(obj) + 8);
    public int Child(int obj) => _small ? _m.ReadByte(Entry(obj) + 6) : _m.ReadWord(Entry(obj) + 10);

    private void SetParent(int obj, int value)
    {
        if (_small) _m.WriteByte(Entry(obj) + 4, value); else _m.WriteWord(Entry(obj) + 6, value);
    }

    private void SetSibling(int obj, int value)
    {
        if (_small) _m.WriteByte(Entry(obj) + 5, value); else _m.WriteWord(Entry(obj) + 8, value);
    }

    private void SetChild(int obj, int value)
    {
        if (_small) _m.WriteByte(Entry(obj) + 6, value); else _m.WriteWord(Entry(obj) + 10, value);
    }

    public int PropertyTableAddress(int obj) => _m.ReadWord(Entry(obj) + (_small ? 7 : 12));

    public int ShortNameAddress(int obj) => PropertyTableAddress(obj) + 1;

    public bool AttributeExists(int attribute) => attribute < (_small ? 32 : 48);

    public bool Attribute(int obj, int attribute)
    {
        if (!AttributeExists(attribute))
        {
            throw new ZMachineException($"attribute {attribute} does not exist in version {_m.Version} (§12.3.1)");
        }

        var value = _m.ReadByte(Entry(obj) + attribute / 8);
        return (value & (0x80 >> (attribute % 8))) != 0;
    }

    public void SetAttribute(int obj, int attribute, bool on)
    {
        var address = Entry(obj) + attribute / 8;
        var mask = 0x80 >> (attribute % 8);
        var value = _m.ReadByte(address);
        _m.WriteByte(address, on ? value | mask : value & ~mask);
    }

    public void Remove(int obj)
    {
        var parent = Parent(obj);

        if (parent == 0)
        {
            return;
        }

        if (Child(parent) == obj)
        {
            SetChild(parent, Sibling(obj));
        }
        else
        {
            var walker = Child(parent);

            while (walker != 0 && Sibling(walker) != obj)
            {
                walker = Sibling(walker);
            }

            if (walker == 0)
            {
                throw new ZMachineException($"object {obj} names parent {parent}, which does not list it among its children (§12)");
            }

            SetSibling(walker, Sibling(obj));
        }

        SetParent(obj, 0);
        SetSibling(obj, 0);
    }

    public void Insert(int obj, int destination)
    {
        Remove(obj);
        SetSibling(obj, Child(destination));
        SetChild(destination, obj);
        SetParent(obj, destination);
    }

    /// <summary>The first property's size byte address.</summary>
    private int FirstProperty(int obj)
    {
        var table = PropertyTableAddress(obj);
        return table + 1 + 2 * _m.ReadByte(table);
    }

    /// <summary>Read a property block: its number, data address, length, and the next block.</summary>
    private (int Number, int Data, int Length, int Next) Block(int address)
    {
        var first = _m.ReadByte(address);

        if (_small)
        {
            var length = (first >> 5) + 1;
            return (first & 0x1F, address + 1, length, address + 1 + length);
        }

        if ((first & 0x80) != 0)
        {
            var length = _m.ReadByte(address + 1) & 0x3F;

            if (length == 0)
            {
                length = 64;
            }

            return (first & 0x3F, address + 2, length, address + 2 + length);
        }

        var single = (first & 0x40) != 0 ? 2 : 1;
        return (first & 0x3F, address + 1, single, address + 1 + single);
    }

    public (int Data, int Length)? FindProperty(int obj, int number)
    {
        var address = FirstProperty(obj);

        while (_m.ReadByte(address) != 0)
        {
            var block = Block(address);

            if (block.Number == number)
            {
                return (block.Data, block.Length);
            }

            if (block.Number < number)
            {
                return null;
            }

            address = block.Next;
        }

        return null;
    }

    public int PropertyValue(int obj, int number)
    {
        var found = FindProperty(obj, number);

        if (found is null)
        {
            if (number < 1 || number > MaxProperties)
            {
                throw new ZMachineException($"property {number} does not exist in version {_m.Version} (§12.2)");
            }

            return _m.ReadWord(_base + 2 * (number - 1));
        }

        return found.Value.Length switch
        {
            1 => _m.ReadByte(found.Value.Data),
            2 => _m.ReadWord(found.Value.Data),
            _ => throw new ZMachineException(
                $"get_prop on property {number} of object {obj}, which is {found.Value.Length} bytes long (§15 get_prop)"),
        };
    }

    public void PutProperty(int obj, int number, int value)
    {
        var found = FindProperty(obj, number)
            ?? throw new ZMachineException($"object {obj} has no property {number} to write (§15 put_prop)");

        switch (found.Length)
        {
            case 1:
                _m.WriteByte(found.Data, value & 0xFF);
                break;
            case 2:
                _m.WriteWord(found.Data, value);
                break;
            default:
                throw new ZMachineException(
                    $"put_prop on property {number} of object {obj}, which is {found.Length} bytes long (§15 put_prop)");
        }
    }

    public int NextProperty(int obj, int number)
    {
        var address = FirstProperty(obj);

        if (number == 0)
        {
            return _m.ReadByte(address) == 0 ? 0 : Block(address).Number;
        }

        while (_m.ReadByte(address) != 0)
        {
            var block = Block(address);

            if (block.Number == number)
            {
                return _m.ReadByte(block.Next) == 0 ? 0 : Block(block.Next).Number;
            }

            address = block.Next;
        }

        throw new ZMachineException($"object {obj} has no property {number} to step past (§15 get_next_prop)");
    }

    public int PropertyLengthAt(int data)
    {
        var size = _m.ReadByte(data - 1);

        if (_small)
        {
            return (size >> 5) + 1;
        }

        if ((size & 0x80) != 0)
        {
            var length = size & 0x3F;
            return length == 0 ? 64 : length;
        }

        return (size & 0x40) != 0 ? 2 : 1;
    }
}
