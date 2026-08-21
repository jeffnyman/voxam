"""The Glulx machine, carried whole.

Glulx is the 32-bit virtual machine modern Inform games compile to
when they outgrow the Z-Machine, and Glk is the I/O layer they
speak through. The specifications are vendored with the reference
material -- Glulx 3.1.3 and Glk 0.7.6 -- and, as everywhere in
Voxam, behavior argues by citation: (Glulx: The Header) names a
section of the Glulx specification the way §1.1 names one of the
Z-Machine Standard.

Every opcode the 3.1.3 roster defines is dispatched, and the
glulxercise checker certifies the whole -- seventy sections,
spoken through the same stdio session a player uses. What remains
is glass, not machine: richer displays, and the courtesies that
ride with them.
"""
