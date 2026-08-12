from collections.abc import Callable

from assertpy import assert_that

from voxam.zmachine.machine import Machine
from voxam.zmachine.memory import Memory

# Two scratch regions in dynamic memory, clear of the globals table.
FIRST = 0x120
SECOND = 0x140


def copier(first: int, second: int, size: int) -> bytes:
    return bytes(
        [
            0xFD,
            0x03,
            *first.to_bytes(2, "big"),
            *second.to_bytes(2, "big"),
            *(size & 0xFFFF).to_bytes(2, "big"),
            0xBA,
        ]
    )


def plant(memory: Memory, address: int, values: list[int]) -> None:
    for offset, value in enumerate(values):
        memory.write_byte(address + offset, value)


def bytes_at(memory: Memory, address: int, count: int) -> list[int]:
    return [memory.read_byte(address + offset) for offset in range(count)]


def test_copies_between_separate_tables(code_machine: Callable[..., Machine]) -> None:
    machine = code_machine(copier(FIRST, SECOND, 4), version=5)
    plant(machine.memory, FIRST, [1, 2, 3, 4])

    machine.run()

    assert_that(bytes_at(machine.memory, SECOND, 4)).is_equal_to([1, 2, 3, 4])


# A zero second table means "zero size bytes of first" (§15
# copy_table) -- and a negative size zeroes its magnitude.
def test_a_zero_second_table_zeroes_the_first(
    code_machine: Callable[..., Machine],
) -> None:
    machine = code_machine(copier(FIRST, 0, 3), version=5)
    plant(machine.memory, FIRST, [7, 7, 7, 7])

    machine.run()

    assert_that(bytes_at(machine.memory, FIRST, 4)).is_equal_to([0, 0, 0, 7])


def test_zeroing_reads_a_negative_size_as_its_magnitude(
    code_machine: Callable[..., Machine],
) -> None:
    machine = code_machine(copier(FIRST, 0, -3), version=5)
    plant(machine.memory, FIRST, [7, 7, 7, 7])

    machine.run()

    assert_that(bytes_at(machine.memory, FIRST, 4)).is_equal_to([0, 0, 0, 7])


# With a positive size the copy must not corrupt an overlap: every
# original byte of first arrives in second intact (§15 copy_table).
def test_a_positive_size_survives_an_overlap(
    code_machine: Callable[..., Machine],
) -> None:
    machine = code_machine(copier(FIRST, FIRST + 2, 4), version=5)
    plant(machine.memory, FIRST, [1, 2, 3, 4])

    machine.run()

    assert_that(bytes_at(machine.memory, FIRST + 2, 4)).is_equal_to([1, 2, 3, 4])


# A negative size forces the forward copy even through an overlap:
# aimed one byte along, it smears the first byte across the run,
# which is exactly how Beyond Zork fills an array with spaces (§15
# copy_table).
def test_a_negative_size_smears_forward(
    code_machine: Callable[..., Machine],
) -> None:
    machine = code_machine(copier(FIRST, FIRST + 1, -4), version=5)
    plant(machine.memory, FIRST, [7, 1, 2, 3, 4])

    machine.run()

    assert_that(bytes_at(machine.memory, FIRST, 5)).is_equal_to([7, 7, 7, 7, 7])
