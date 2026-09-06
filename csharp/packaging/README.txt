Voxam, the native port
======================

This is Voxam's C# port, built as one native program with nothing
to install beside it: no runtime, no interpreter, no packages. It
plays Z-Machine and Glulx stories, which is to say .z1 through
.z8, .ulx, and the .zblorb, .gblorb and .blorb packages around
them.

It is a beta. The Voxam on PyPI is the reference implementation
and stays the one that carries every face; this is a second
implementation certified against it, and where the two differ the
difference is this one's to answer for.

What is in here:

  Voxam           the window. Open a story from its File menu,
                  or name one on the command line.
  console/voxam   the same interpreter at a prompt, with the
                  status line painted where the terminal allows
                  it and --plain where it does not.

These binaries are unsigned, so your platform will want a word
about it the first time:

  Windows   SmartScreen offers "More info", then "Run anyway".
  macOS     Right click Voxam.app, choose Open, then Open again
            in the box that asks. If it still refuses:
              xattr -dr com.apple.quarantine Voxam.app
  Linux     If the archive lost the execute bit, put it back:
              chmod +x Voxam console/voxam

Anything that misbehaves is worth reporting, and the story it
happened in is the first thing to say:

  https://github.com/jeffnyman/voxam/issues
