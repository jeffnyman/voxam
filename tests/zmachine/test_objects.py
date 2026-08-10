from dataclasses import dataclass, field

import pytest
from assertpy import assert_that

from voxam.errors import (
    ZMachineObjectError,
    ZMachineStackError,
    ZMachineUnimplementedError,
)
from voxam.frontend import PlainFrontend
from voxam.zmachine.header import PACKED_PC_VERSION
from voxam.zmachine.machine import Machine
from voxam.zmachine.memory import Memory
from voxam.zmachine.objects import V3_LAST_VERSION, WORD_LENGTH, ObjectTable
from voxam.zmachine.story import Story
from voxam.zmachine.zscii import decode_string

TABLE_BASE = 0x400

RESULT_VARIABLE = 0x10
RESULT_ADDRESS = 0x100
SECOND_VARIABLE = 0x11
SECOND_ADDRESS = 0x102

NOT_TAKEN = 1
TAKEN = 2
ARMS = bytes(
    [0x0D, RESULT_VARIABLE, NOT_TAKEN, 0xBA, 0x0D, RESULT_VARIABLE, TAKEN, 0xBA]
)
BRANCH_TAKEN = 0xC6

# 'h' and 'i' in one terminated word (§3.5.3).
HI = bytes([0xB5, 0xC5])


@dataclass
class Obj:
    attributes: tuple[int, ...] = ()
    parent: int = 0
    sibling: int = 0
    child: int = 0
    name: bytes = b""
    properties: dict[int, bytes] = field(default_factory=dict)


def build_table(objects: list[Obj], version: int, defaults: dict[int, int]) -> bytes:
    v3 = version <= V3_LAST_VERSION
    default_count = 31 if v3 else 63
    entry_size = 9 if v3 else 14
    attribute_bytes = 4 if v3 else 6

    data = bytearray()

    for number in range(1, default_count + 1):
        data += defaults.get(number, 0).to_bytes(2, "big")

    entries_start = len(data)
    data += bytes(entry_size * len(objects))

    property_tables = []

    for obj in objects:
        property_tables.append(TABLE_BASE + len(data))
        data += bytes([len(obj.name) // 2]) + obj.name

        for number in sorted(obj.properties, reverse=True):
            payload = obj.properties[number]

            if v3:
                data += bytes([32 * (len(payload) - 1) + number])
            elif len(payload) == 1:
                data += bytes([number])
            elif len(payload) == WORD_LENGTH:
                data += bytes([0x40 | number])
            else:
                data += bytes([0x80 | number, 0x80 | (len(payload) & 0x3F)])

            data += payload

        data += b"\x00"

    for index, obj in enumerate(objects):
        offset = entries_start + index * entry_size
        flags = bytearray(attribute_bytes)

        for attribute in obj.attributes:
            flags[attribute // 8] |= 0x80 >> (attribute % 8)

        if v3:
            relations = bytes([obj.parent, obj.sibling, obj.child])
        else:
            relations = b"".join(
                relation.to_bytes(2, "big")
                for relation in (obj.parent, obj.sibling, obj.child)
            )

        entry = bytes(flags) + relations + property_tables[index].to_bytes(2, "big")
        data[offset : offset + entry_size] = entry

    return bytes(data)


def scene_story(
    objects: list[Obj],
    version: int = 3,
    defaults: dict[int, int] | None = None,
    code: bytes = b"",
) -> Story:
    data = bytearray(2048)
    data[0] = version
    data[0x04:0x06] = (0x0700).to_bytes(2, "big")

    # Version 6 reads $06 as the packed address of a main routine
    # (§5.4): packed 0x10 unpacks to byte address $40, so the code
    # there must begin with a routine's local-count byte.
    initial = 0x0010 if version == PACKED_PC_VERSION else 0x0040
    data[0x06:0x08] = initial.to_bytes(2, "big")
    data[0x0A:0x0C] = TABLE_BASE.to_bytes(2, "big")
    data[0x0C:0x0E] = (0x0100).to_bytes(2, "big")
    data[0x0E:0x10] = (0x0700).to_bytes(2, "big")
    data[0x40 : 0x40 + len(code)] = code

    table = build_table(objects, version, defaults or {})
    data[TABLE_BASE : TABLE_BASE + len(table)] = table

    return Story(bytes(data))


# The standing scene: a box holding a coin then a key. The box's
# properties are 5 (a word) and 3 (a byte); property 7 exists only
# as a table default.
def scene(code: bytes = b"", version: int = 3) -> Story:
    return scene_story(
        [
            Obj(
                attributes=(3, 12),
                child=2,
                name=HI,
                properties={5: b"\x12\x34", 3: b"\x42"},
            ),
            Obj(parent=1, sibling=3),
            Obj(parent=1),
        ],
        version=version,
        defaults={7: 0x0777},
        code=code,
    )


def table_of(story: Story) -> tuple[ObjectTable, Memory]:
    memory = Memory(story)

    return ObjectTable(memory), memory


def run(code: bytes, version: int = 3) -> Machine:
    machine = Machine(scene(code, version))
    machine.run()

    return machine


def result_of(machine: Machine) -> int:
    return machine.memory.read_word(RESULT_ADDRESS)


def test_reads_and_writes_attributes() -> None:
    table, _ = table_of(scene())

    assert_that(table.attribute(1, 3)).is_true()
    assert_that(table.attribute(1, 4)).is_false()

    table.set_attribute(1, 4, on=True)
    table.set_attribute(1, 3, on=False)

    assert_that(table.attribute(1, 4)).is_true()
    assert_that(table.attribute(1, 3)).is_false()


# Version 4 grows the attribute range to 48 (§12.3.2); 32 is out of
# range only through Version 3.
def test_attribute_ranges_fork_at_version_4() -> None:
    v3_table, _ = table_of(scene())

    with pytest.raises(ZMachineObjectError, match="attribute 32"):
        v3_table.attribute(1, 32)

    v4_table, _ = table_of(scene_story([Obj(attributes=(40,))], version=5))

    assert_that(v4_table.attribute(1, 40)).is_true()
    assert_that(v4_table.attribute(1, 47)).is_false()


def test_object_numbers_are_policed() -> None:
    table, _ = table_of(scene())

    with pytest.raises(ZMachineObjectError, match="object 0 does not exist"):
        table.parent(0)

    with pytest.raises(ZMachineObjectError, match="object 256"):
        table.parent(256)


def test_reads_the_family_relations() -> None:
    table, _ = table_of(scene())

    assert_that(table.child(1)).is_equal_to(2)
    assert_that(table.sibling(2)).is_equal_to(3)
    assert_that(table.parent(3)).is_equal_to(1)
    assert_that(table.sibling(3)).is_equal_to(0)


# Version 4 relations are words, so an object number above 255 can
# be a parent (§12.3.2).
def test_version_4_relations_are_words() -> None:
    table, _ = table_of(scene_story([Obj(parent=300)], version=5))

    assert_that(table.parent(1)).is_equal_to(300)


def test_removing_the_first_child_promotes_its_sibling() -> None:
    table, _ = table_of(scene())
    table.remove(2)

    assert_that(table.child(1)).is_equal_to(3)
    assert_that(table.parent(2)).is_equal_to(0)
    assert_that(table.sibling(2)).is_equal_to(0)


def test_removing_a_later_child_relinks_the_chain() -> None:
    table, _ = table_of(scene())
    table.remove(3)

    assert_that(table.child(1)).is_equal_to(2)
    assert_that(table.sibling(2)).is_equal_to(0)
    assert_that(table.parent(3)).is_equal_to(0)


# With three siblings, removing the last one exercises the walk down
# the chain past a non-matching sibling.
def test_removing_the_last_of_three_siblings() -> None:
    story = scene_story(
        [
            Obj(child=2),
            Obj(parent=1, sibling=3),
            Obj(parent=1, sibling=4),
            Obj(parent=1),
        ]
    )
    table, _ = table_of(story)
    table.remove(4)

    assert_that(table.sibling(3)).is_equal_to(0)
    assert_that(table.parent(4)).is_equal_to(0)


# Version 4 relations are words, so tree surgery writes words too.
def test_version_4_tree_surgery_writes_words() -> None:
    table, _ = table_of(scene_story([Obj(), Obj()], version=5))
    table.insert(2, 1)

    assert_that(table.parent(2)).is_equal_to(1)
    assert_that(table.child(1)).is_equal_to(2)


def test_removing_a_parentless_object_changes_nothing() -> None:
    table, _ = table_of(scene())
    table.remove(1)

    assert_that(table.child(1)).is_equal_to(2)


def test_insertion_makes_the_first_child() -> None:
    table, _ = table_of(scene())
    table.insert(3, 2)

    assert_that(table.parent(3)).is_equal_to(2)
    assert_that(table.child(2)).is_equal_to(3)
    assert_that(table.sibling(2)).is_equal_to(0)
    assert_that(table.child(1)).is_equal_to(2)


def test_reads_properties_and_defaults() -> None:
    table, _ = table_of(scene())

    assert_that(table.property_value(1, 5)).is_equal_to(0x1234)
    assert_that(table.property_value(1, 3)).is_equal_to(0x42)
    assert_that(table.property_value(1, 7)).is_equal_to(0x0777)
    assert_that(table.property_value(1, 9)).is_equal_to(0)


def test_writes_properties() -> None:
    table, _ = table_of(scene())
    table.put_property(1, 5, 0xBEEF)

    assert_that(table.property_value(1, 5)).is_equal_to(0xBEEF)

    # A length-1 property takes only the least significant byte (§15).
    table.put_property(1, 3, 0xABCD)

    assert_that(table.property_value(1, 3)).is_equal_to(0xCD)


def test_writing_an_absent_property_halts() -> None:
    table, _ = table_of(scene())

    with pytest.raises(ZMachineObjectError, match="put_prop must halt"):
        table.put_property(2, 5, 1)


# get_prop and put_prop may only touch properties of length 1 or 2
# (§15); a three-byte property refuses both.
def test_long_properties_refuse_word_access() -> None:
    story = scene_story([Obj(properties={4: b"\x01\x02\x03"})])
    table, _ = table_of(story)

    with pytest.raises(ZMachineObjectError, match="get_prop may not"):
        table.property_value(1, 4)

    with pytest.raises(ZMachineObjectError, match="put_prop may not"):
        table.put_property(1, 4, 1)


def found_property(table: ObjectTable, obj: int, number: int) -> tuple[int, int]:
    found = table.find_property(obj, number)

    if found is None:
        pytest.fail(f"object {obj} unexpectedly lacks property {number}")

    return found


def test_property_lengths_recover_from_data_addresses() -> None:
    table, _ = table_of(scene())

    for number, expected in [(5, 2), (3, 1)]:
        data, _ = found_property(table, 1, number)

        assert_that(table.property_length_at(data)).is_equal_to(expected)


# Version 4 property blocks: one byte for lengths 1 and 2, two bytes
# beyond -- where a stored length of 0 means 64 (§12.4.2).
def test_version_4_property_formats() -> None:
    story = scene_story(
        [
            Obj(
                properties={
                    9: b"\x11",
                    8: b"\x22\x33",
                    7: b"\x01\x02\x03",
                    6: bytes(64),
                }
            )
        ],
        version=5,
    )
    table, _ = table_of(story)

    for number, expected in [(9, 1), (8, 2), (7, 3), (6, 64)]:
        data, length = found_property(table, 1, number)

        assert_that(length).is_equal_to(expected)
        assert_that(table.property_length_at(data)).is_equal_to(expected)


def test_walks_the_property_list() -> None:
    table, _ = table_of(scene())

    assert_that(table.next_property(1, 0)).is_equal_to(5)
    assert_that(table.next_property(1, 5)).is_equal_to(3)
    assert_that(table.next_property(1, 3)).is_equal_to(0)
    assert_that(table.next_property(2, 0)).is_equal_to(0)

    with pytest.raises(ZMachineObjectError, match="get_next_prop must halt"):
        table.next_property(2, 5)


def test_defaults_are_policed() -> None:
    table, _ = table_of(scene())

    with pytest.raises(ZMachineObjectError, match="property 40 has no default"):
        table.default(40)


def test_short_names_decode() -> None:
    table, memory = table_of(scene())

    text, _ = decode_string(memory, table.short_name_address(1))

    assert_that(text).is_equal_to("hi")


# --- The opcodes, run as programs over the same scene. ---


def test_jin_branches_on_parenthood() -> None:
    machine = run(bytes([0x06, 2, 1, BRANCH_TAKEN]) + ARMS)

    assert_that(result_of(machine)).is_equal_to(TAKEN)

    machine = run(bytes([0x06, 2, 3, BRANCH_TAKEN]) + ARMS)

    assert_that(result_of(machine)).is_equal_to(NOT_TAKEN)


def test_test_attr_set_attr_and_clear_attr() -> None:
    machine = run(bytes([0x0A, 1, 3, BRANCH_TAKEN]) + ARMS)

    assert_that(result_of(machine)).is_equal_to(TAKEN)

    machine = run(bytes([0x0B, 1, 4, 0x0A, 1, 4, BRANCH_TAKEN]) + ARMS)

    assert_that(result_of(machine)).is_equal_to(TAKEN)

    machine = run(bytes([0x0C, 1, 3, 0x0A, 1, 3, BRANCH_TAKEN]) + ARMS)

    assert_that(result_of(machine)).is_equal_to(NOT_TAKEN)


def test_get_parent_stores_without_branching() -> None:
    machine = run(bytes([0x93, 2, RESULT_VARIABLE, 0xBA]))

    assert_that(result_of(machine)).is_equal_to(1)


# get_sibling and get_child store their result and branch only when
# it is not zero (§15).
def test_get_sibling_and_get_child_store_and_branch() -> None:
    machine = run(bytes([0x91, 2, SECOND_VARIABLE, BRANCH_TAKEN]) + ARMS)

    assert_that(result_of(machine)).is_equal_to(TAKEN)
    assert_that(machine.memory.read_word(SECOND_ADDRESS)).is_equal_to(3)

    machine = run(bytes([0x92, 2, SECOND_VARIABLE, BRANCH_TAKEN]) + ARMS)

    assert_that(result_of(machine)).is_equal_to(NOT_TAKEN)
    assert_that(machine.memory.read_word(SECOND_ADDRESS)).is_equal_to(0)


def test_insert_obj_and_remove_obj_reshape_the_tree() -> None:
    machine = run(bytes([0x0E, 3, 2, 0xBA]))
    table = ObjectTable(machine.memory)

    assert_that(table.parent(3)).is_equal_to(2)
    assert_that(table.child(2)).is_equal_to(3)

    machine = run(bytes([0x99, 2, 0xBA]))
    table = ObjectTable(machine.memory)

    assert_that(table.parent(2)).is_equal_to(0)
    assert_that(table.child(1)).is_equal_to(3)


def test_print_obj_prints_the_short_name() -> None:
    output: list[str] = []
    machine = Machine(scene(bytes([0x9A, 1, 0xBA])), PlainFrontend(output.append))

    machine.run()

    assert_that("".join(output)).is_equal_to("hi")


def test_put_prop_and_get_prop_round_trip() -> None:
    program = bytes(
        [
            0xE3,
            0x53,
            1,
            5,
            0xBE,
            0xEF,  # put_prop box 5 0xBEEF
            0x11,
            1,
            5,
            RESULT_VARIABLE,  # get_prop box 5
            0xBA,
        ]
    )
    machine = run(program)

    assert_that(result_of(machine)).is_equal_to(0xBEEF)


def test_get_prop_falls_back_to_the_default() -> None:
    machine = run(bytes([0x11, 2, 7, RESULT_VARIABLE, 0xBA]))

    assert_that(result_of(machine)).is_equal_to(0x0777)


# get_prop_addr chains into get_prop_len through a variable; an
# absent property gives address 0, and get_prop_len of 0 gives 0
# (§15).
def test_the_property_address_and_length_pair() -> None:
    program = bytes(
        [
            0x12,
            1,
            5,
            RESULT_VARIABLE,  # get_prop_addr box 5
            0xA4,
            RESULT_VARIABLE,
            SECOND_VARIABLE,  # get_prop_len [that]
            0xBA,
        ]
    )
    machine = run(program)

    assert_that(result_of(machine)).is_greater_than(0)
    assert_that(machine.memory.read_word(SECOND_ADDRESS)).is_equal_to(2)

    program = bytes(
        [
            0x12,
            2,
            5,
            RESULT_VARIABLE,  # get_prop_addr coin 5: absent
            0xA4,
            RESULT_VARIABLE,
            SECOND_VARIABLE,
            0xBA,
        ]
    )
    machine = run(program)

    assert_that(result_of(machine)).is_equal_to(0)
    assert_that(machine.memory.read_word(SECOND_ADDRESS)).is_equal_to(0)


def test_get_next_prop_walks_in_a_program() -> None:
    machine = run(bytes([0x13, 1, 0, RESULT_VARIABLE, 0xBA]))

    assert_that(result_of(machine)).is_equal_to(5)


def test_pull_writes_the_referenced_variable() -> None:
    program = bytes(
        [
            0xE8,
            0x7F,
            0x2A,  # push 42
            0xE9,
            0x7F,
            RESULT_VARIABLE,  # pull g10
            0xBA,
        ]
    )
    machine = run(program)

    assert_that(result_of(machine)).is_equal_to(42)


# Pulling into variable $00 pops, then overwrites the new stack top
# in place (§6.3.4): from a stack of 1, 2 the pull leaves just 2.
def test_pull_into_the_stack_is_in_place() -> None:
    program = bytes(
        [
            0xE8,
            0x7F,
            0x01,  # push 1
            0xE8,
            0x7F,
            0x02,  # push 2
            0xE9,
            0x7F,
            0x00,  # pull [sp]
            0x2D,
            RESULT_VARIABLE,
            0x00,  # store g10 <- sp: pops
            0xBA,
        ]
    )
    machine = run(program)

    assert_that(result_of(machine)).is_equal_to(2)


def test_pull_from_an_empty_stack_halts() -> None:
    machine = Machine(scene(bytes([0xE9, 0x7F, RESULT_VARIABLE, 0xBA])))

    with pytest.raises(ZMachineStackError, match="empty stack"):
        machine.run()


# Version 6's storing pull works on user stacks, which do not exist
# yet; the frontier reporter says so rather than misbehaving (§14).
def test_version_6_pull_is_a_reported_frontier() -> None:
    code = bytes([0x00, 0xE9, 0x7F, RESULT_VARIABLE, 0x00])
    machine = Machine(scene_story([Obj()], version=6, code=code))

    with pytest.raises(ZMachineUnimplementedError, match="pull"):
        machine.run()
