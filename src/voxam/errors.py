"""Exceptions raised by Voxam."""


class VoxamError(Exception):
    """Base class for every error Voxam raises."""


class ZMachineHeaderError(VoxamError):
    """Raised when a header field is absent or read inappropriately."""


class ZMachineMemoryError(VoxamError):
    """Raised when a memory map is incoherent or an access breaks its rules."""


class ZMachineStoryError(VoxamError):
    """Raised when a file cannot be loaded as a Z-Machine story."""
