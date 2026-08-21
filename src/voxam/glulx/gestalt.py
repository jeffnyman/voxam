"""Gestalt selectors: what this interpreter can do (Glulx: Gestalt).

The reference glulxe answers most of these from compile-time
switches. Voxam answers them from Capabilities, a runtime value --
partly because Python has no compile step, and partly because it
lets the capability set track which eras exist yet. Every False in
the defaults is not a design decision but a statement that the
supporting era has not arrived, with the era named beside it; the
branch that builds an era flips its flag.
"""

from dataclasses import dataclass
from enum import IntEnum
from importlib.metadata import version
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from voxam.glulx.machine import Machine

# The Glulx specification version implemented: 3.1.3, packed as the
# header packs it (Glulx: The Header).
GLULX_VERSION = 0x00030103

MAJOR_SHIFT = 16
MINOR_SHIFT = 8


class Gestalt(IntEnum):
    """The selector numbers the gestalt opcode answers."""

    GLULX_VERSION = 0
    TERP_VERSION = 1
    RESIZE_MEM = 2
    UNDO = 3
    IO_SYSTEM = 4
    UNICODE = 5
    MEM_COPY = 6
    MALLOC = 7
    MALLOC_HEAP = 8
    ACCELERATION = 9
    ACCEL_FUNC = 10
    FLOAT = 11
    EXT_UNDO = 12
    DOUBLE = 13


# The io systems the IO_SYSTEM selector is asked about.
IOSYS_NULL = 0
IOSYS_FILTER = 1
IOSYS_GLK = 2


@dataclass(frozen=True)
class Capabilities:
    """What this build of the machine can currently do.

    Attributes:
        resize_mem: setmemsize works; the memory era built it.
        mem_copy: mzero and mcopy work; the exec-loop era.
        unicode: E2 strings, the wide nodes, streamunichar, and
            the type-14 stubs; the strings era.
        undo: saveundo and restoreundo; the save era carried them.
        ext_undo: hasundo and discardundo; the same era.
        malloc: malloc and mfree; the heap era carried them.
        acceleration: The accel era.
        floats: The float era.
        doubles: The double era.
        glk: A Glk library is installed on this machine; the
            bridge answers the glk opcode and iosys mode 2 works.
    """

    resize_mem: bool = True
    mem_copy: bool = True
    unicode: bool = True
    undo: bool = True
    ext_undo: bool = True
    malloc: bool = True
    acceleration: bool = False
    floats: bool = False
    doubles: bool = False
    glk: bool = False


def terp_version() -> int:
    """Voxam's own version, packed the way the header packs one.

    Read from the installed package so the answer can never drift
    from pyproject: release 1.2.3 answers 0x00010203.
    """

    major, minor, patch = (int(part) for part in version("voxam").split("."))

    return (major << MAJOR_SHIFT) | (minor << MINOR_SHIFT) | patch


def answer(  # noqa: PLR0911, PLR0912 -- one flat return per selector
    machine: "Machine", selector: int, argument: int
) -> int:
    """One gestalt query, answered honestly.

    Unknown selectors answer zero rather than erring: that is how
    a program written against a future spec probes an older
    interpreter (Glulx: Gestalt).
    """

    caps = machine.capabilities

    if selector == Gestalt.GLULX_VERSION:
        return GLULX_VERSION

    if selector == Gestalt.TERP_VERSION:
        return terp_version()

    if selector == Gestalt.RESIZE_MEM:
        return int(caps.resize_mem)

    if selector == Gestalt.UNDO:
        return int(caps.undo)

    if selector == Gestalt.IO_SYSTEM:
        # The null and filter systems always work; Glk is its own
        # era's promise to keep.
        if argument in (IOSYS_NULL, IOSYS_FILTER):
            return 1

        if argument == IOSYS_GLK:
            return int(caps.glk)

        return 0

    if selector == Gestalt.UNICODE:
        return int(caps.unicode)

    if selector == Gestalt.MEM_COPY:
        return int(caps.mem_copy)

    if selector == Gestalt.MALLOC:
        return int(caps.malloc)

    if selector == Gestalt.MALLOC_HEAP:
        # The heap's start address, or zero with no blocks extant
        # (Glulx: Gestalt).
        return machine.heap.start

    if selector == Gestalt.ACCELERATION:
        return int(caps.acceleration)

    if selector == Gestalt.ACCEL_FUNC:
        # No accelerated function is available until that era.
        return 0

    if selector == Gestalt.FLOAT:
        return int(caps.floats)

    if selector == Gestalt.EXT_UNDO:
        return int(caps.ext_undo)

    if selector == Gestalt.DOUBLE:
        return int(caps.doubles)

    return 0
