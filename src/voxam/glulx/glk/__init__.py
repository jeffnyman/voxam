"""Glk: the I/O layer Glulx games speak through.

Glk is a portable API, not a wire protocol: a game calls named
functions like glk_put_char and glk_window_open, and Glulx reaches
them through the glk opcode by number. This package carries that
world in layers -- the dispatch table that knows every function's
signature, the object model the functions operate on, and, in eras
to come, the function surface itself and the display that makes a
session visible.

Citations name sections of the vendored Glk 0.7.6 specification:
(Glk: Text Grid Windows) works the way (Glulx: The Header) and
Z-Machine §1.1 citations do elsewhere in Voxam.
"""
