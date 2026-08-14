"""Exceptions raised by Voxam."""


class VoxamError(Exception):
    """Base class for every error Voxam raises."""


class AcceptanceError(VoxamError):
    """Raised when an acceptance script cannot be used."""


class IFFError(VoxamError):
    """Raised when bytes cannot be read as an IFF container."""


class ZMachineArithmeticError(VoxamError):
    """Raised for arithmetic a story may not perform (§2.3)."""


class ZMachineHeaderError(VoxamError):
    """Raised when a header field is absent or read inappropriately."""


class ZMachineInstructionError(VoxamError):
    """Raised when bytes cannot be decoded as an instruction."""


class ZMachineMemoryError(VoxamError):
    """Raised when a memory map is incoherent or an access breaks its rules."""


class ZMachineObjectError(VoxamError):
    """Raised when the object table is used against its rules (§12)."""


class ZMachineQuetzalError(VoxamError):
    """Raised when a Quetzal save file cannot be written or read."""


class ZMachineRoutineError(VoxamError):
    """Raised when bytes cannot be parsed as a routine."""


class ZMachineScreenError(VoxamError):
    """Raised when the screen model's §8 rules are broken."""


class ZMachineStackError(VoxamError):
    """Raised when the routine call state is used against its rules."""


class ZMachineStoryError(VoxamError):
    """Raised when a file cannot be loaded as a Z-Machine story."""


class ZMachineTextError(VoxamError):
    """Raised when encoded text cannot be decoded to characters."""


class ZMachineUnimplementedError(VoxamError):
    """Raised when execution reaches an opcode Voxam does not yet run.

    This is the frontier reporter: pointing Voxam at a story and
    reading this error's message is how the implementation backlog
    announces itself.

    Attributes:
        opcode_name: The name of the unimplemented opcode.
        address: The byte address execution reached it at.
    """

    def __init__(self, opcode_name: str, address: int) -> None:
        """Record which opcode was reached, and where.

        Args:
            opcode_name: The name of the unimplemented opcode.
            address: The byte address execution reached it at.
        """

        self.opcode_name = opcode_name
        self.address = address

        super().__init__(
            f"reached {opcode_name} at ${address:04x}, which is not yet implemented"
        )
