### What to download

Three things ship on one release, and `VERSION` below stands in
for this one's number.

**`voxam-standalone-VERSION-*`** is the C# port: one native
program with nothing to install beside it, no runtime and no
Python. Unzip it and run `Voxam` for the window or
`console/voxam` for the terminal. Windows, macOS (Intel and
Apple silicon in the one archive) and Linux. It is a beta, and
the note inside says what each platform asks the first time it
meets an unsigned binary.

**`Voxam_VERSION_*`** are the desktop shell's installers: the
`.exe` for Windows, the `.dmg` for macOS, the `.deb` and the
`.AppImage` for Linux. The shell is a window over the Python
interpreter rather than an interpreter itself, so it wants
`voxam` already on the PATH.

**`voxam-VERSION-py3-none-any.whl`** and
**`voxam-VERSION.tar.gz`** are the Python package: the same
files published to PyPI, where `pip install voxam` and
`uv tool install voxam` find them without coming here.

---
