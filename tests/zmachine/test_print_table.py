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
