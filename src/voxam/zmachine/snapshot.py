"""A captured state of play (§6.1).

The state of play is four things: the contents of dynamic memory, the
contents of the stack, the program counter, and the routine call
state -- the chain of routines that have called each other, with
their local variables (§6.1). A Snapshot holds all four as immutable
values in the interpreter's private memory, exactly where §6.1 says
the stack and call state must live.

A Snapshot is the common currency of every state-travel feature:
save writes one out, restore plays one back, undo keeps one in hand,
and Quetzal will one day be a Snapshot in a file.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class FrameSnapshot:
    """One frozen link of the routine call chain (§6.1).

    A Frame's fields, made immutable: what the call state remembers
    about one routine invocation, without the ability to mutate a
    live machine through it.

    Attributes:
        return_address: Where execution resumes when the routine
            returns (§6.4).
        store_variable: The caller's variable for the result, or None
            when the result is thrown away (§6.4.1).
        locals: The routine's local variable values, in order.
        argument_count: How many arguments the caller supplied
            (§6.4.4.1).
        stack: The routine's private portion of the stack (§6.3.2).
    """

    return_address: int
    store_variable: int | None
    locals: tuple[int, ...]
    argument_count: int
    stack: tuple[int, ...]


@dataclass(frozen=True)
class Snapshot:
    """The entire state of play, captured whole (§6.1, §6.1.1).

    Attributes:
        dynamic_memory: Every byte below the static memory base,
            header included (§1.1.1).
        pc: The byte address of the next instruction to execute.
        frames: The routine call chain from the base frame up, each
            with its locals and its portion of the stack (§6.1).
    """

    dynamic_memory: bytes
    pc: int
    frames: tuple[FrameSnapshot, ...]
