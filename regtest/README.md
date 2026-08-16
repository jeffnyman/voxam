# RegTest scripts

[RegTest](https://eblong.com/zarf/plotex/regtest.html) is Andrew
Plotkin's regression tester for interactive fiction. Every script
here runs two ways, from the repository root:

    voxam --regtest regtest/zork1.regtest

runs it through Voxam's built-in in-process runner, on any
platform; and

    python regtest/reference/regtest.py regtest/zork1.regtest

runs it through the vendored reference implementation (public
domain, unmodified), which drives `voxam --plain` through POSIX
pipes -- Linux, macOS, or WSL. The certified scripts --
`fixtures.regtest` and `zork1.regtest` -- must pass under both,
with the same verdict, and continuous integration holds them to
it. `arthur.regtest` runs under the built-in runner alone: the
reference's cheap mode frames output on a newline-prompt pair
that Arthur's inline keystroke prompts never print.
