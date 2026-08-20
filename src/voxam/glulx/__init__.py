"""The Glulx machine: the road to 2.0.

Glulx is the 32-bit virtual machine modern Inform games compile to
when they outgrow the Z-Machine, and Glk is the I/O layer they
speak through. The specifications are vendored with the reference
material -- Glulx 3.1.3 and Glk 0.7.6 -- and, as everywhere in
Voxam, behavior argues by citation: (Glulx: The Header) names a
section of the Glulx specification the way §1.1 names one of the
Z-Machine Standard.

This package opens with the honest boot: a Glulx story is
recognized, its header read and verified, and execution reported
as the frontier it still is. The machine follows, era by era.
"""
