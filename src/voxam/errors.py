"""Exceptions raised by Voxam."""


class VoxamError(Exception):
    """Base class for every error Voxam raises."""


class ZMachineStoryError(VoxamError):
    """Raised when a file cannot be loaded as a Z-Machine story."""
