"""The one Windows-only seam: whole characters off the console.

A console whose input code page is UTF-8 returns a byte-oriented
read only the FIRST byte of a multibyte character. A pasted
o-umlaut arrives as its lead byte alone and the continuation byte
is simply gone, so no decoder downstream can recover it and every
story leaning on §3.8.5's extra characters is untypable at the
painted terminal. The wide console read has no such defect.

This module exists to hold that platform test and nothing else.
The read it installs lives in `frontend.reading_wide`, where it is
ordinary code that every platform type-checks and every platform
tests. Here there is only the branch -- which is unreachable on
one platform or the other by construction, and cannot be covered
or checked on both at once.
"""

import sys

from voxam.frontend import reading_wide


def widened(terminal: object) -> object:  # pragma: no cover -- one arm per platform
    """On Windows, let the console hand over whole characters.

    Everywhere else the terminal comes back untouched: no other
    platform has the defect, and none should pay for the detour.
    """

    if sys.platform != "win32":
        return terminal

    import msvcrt  # noqa: PLC0415 -- Windows only, imported where used

    return reading_wide(terminal, msvcrt.getwch)
