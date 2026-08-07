"""Exceptions raised by Voxam."""


class VoxamError(Exception):
    """Base class for every error Voxam raises."""


class ZMachineStoryError(VoxamError):
    """Raised when a file cannot be loaded as a Z-Machine story."""


class ZMachineHeaderError(VoxamError):
    """Raised when a header field is absent or read inappropriately."""
