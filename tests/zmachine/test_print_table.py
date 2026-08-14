from collections.abc import Callable

from assertpy import assert_that

from voxam.zmachine.machine import Machine

# A scratch table in dynamic memory, clear of the globals table.
TABLE = 0x120


def printer(types: int, *operands: int) -> bytes:
    return bytes([0xFE, types, *operands, 0xBA])


def machine_with(
    code_machine: Callable[..., Machine], code: bytes, table: str
) -> tuple[Machine, list[str]]:
    output: list[str] = []
    machine = code_machine(code, version=5, output=output.append)

    for offset, character in enumerate(table):
        machine.memory.write_byte(TABLE + offset, ord(character))

    return machine, output


# With height omitted the rectangle is one row: width bytes of the
# table, printed where the cursor stands (§15 print_table).
def test_a_single_row_prints_the_width(
    code_machine: Callable[..., Machine],
) -> None:
    machine, output = machine_with(code_machine, printer(0x1F, 0x01, 0x20, 2), "HIDDEN")

    machine.run()

    assert_that("".join(output)).is_equal_to("HI")


# Height rows print in a stack, each row the next width bytes (§15
# print_table).
def test_rows_stack_down_the_screen(code_machine: Callable[..., Machine]) -> None:
    machine, output = machine_with(
        code_machine, printer(0x17, 0x01, 0x20, 2, 2), "ABCD"
    )

    machine.run()

    assert_that("".join(output)).is_equal_to("AB\nCD")


# A skip passes over table characters between rows: a small window
# onto a larger character map (§15 print_table).
def test_skip_carves_a_window_from_a_wider_map(
    code_machine: Callable[..., Machine],
) -> None:
    machine, output = machine_with(
        code_machine, printer(0x15, 0x01, 0x20, 2, 2, 3), "ABxxxCD"
    )

    machine.run()

    assert_that("".join(output)).is_equal_to("AB\nCD")


# Into a stream 3 table the rectangle travels as newline-separated
# rows: ZSCII 13 between them, exactly as the plain screen shows
# them (§7.1.2.2.1, §15 print_table).
def test_rectangles_redirect_into_stream_3_as_lines(
    code_machine: Callable[..., Machine],
) -> None:
    program = bytes(
        [
            *[0xF3, 0x4F, 0x03, 0x01, 0x40],  # output_stream 3 $140
            *[0xFE, 0x17, 0x01, 0x20, 0x02, 0x02],  # print_table $120 2 2
            *[0xF3, 0x3F, 0xFF, 0xFD],  # output_stream -3
            0xBA,
        ]
    )
    machine, output = machine_with(code_machine, program, "ABCD")

    machine.run()

    assert_that(output).is_empty()
    assert_that(machine.memory.read_word(0x140)).is_equal_to(5)
    assert_that(
        bytes(machine.memory.read_byte(0x142 + offset) for offset in range(5))
    ).is_equal_to(b"AB\rCD")


# With the screen deselected the rectangle vanishes as asked (§7).
def test_rectangles_respect_a_deselected_screen(
    code_machine: Callable[..., Machine],
) -> None:
    program = bytes(
        [
            *[0xF3, 0x3F, 0xFF, 0xFF],  # output_stream -1
            *[0xFE, 0x17, 0x01, 0x20, 0x02, 0x02],  # print_table $120 2 2
            *[0xF3, 0x7F, 0x01],  # output_stream 1
            0xBA,
        ]
    )
    machine, output = machine_with(code_machine, program, "ABCD")

    machine.run()

    assert_that("".join(output)).is_empty()
