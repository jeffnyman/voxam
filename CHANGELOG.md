## v0.1.0 (2026-08-11)

### Feat

- **zmachine**: search tables with scan_table (#33)
- **zmachine**: introduce the interpreter in version 4 headers (#32)
- **acceptance**: warn when a replayed command draws a refusal (#29)
- **zmachine**: assemble the status line behind a frontend seam (#27)
- **acceptance**: fence off script sections (#23)
- **cli**: replay a script then hand off to the prompt (#22)
- **cli**: replay recorded acceptance scripts (#21)
- **cli**: seed the dice for reproducible sessions (#20)
- **zmachine**: read and parse typed commands (#19)
- **zmachine**: read dictionaries and tokenize input (#18)
- **zmachine**: roll the two-state random generator (#17)
- **zscii**: expand abbreviations (#15)
- **zmachine**: read and reshape the object table (#14)
- **zmachine**: run branch, comparison, and bitwise opcodes (#13)
- **zmachine**: run arithmetic, memory, and variable opcodes (#12)
- **zmachine**: decode text and print across all versions (#11)
- **zmachine**: execute instructions through a machine loop (#10)
- **zmachine**: parse routines and model the call state (#9)
- **zmachine**: decode complete instructions via opcode tables (#8)
- **zmachine**: decode store, branch, and text riders (#7)
- **zmachine**: decode instruction forms and operands (#6)
- **zmachine**: model memory regions with access rules (#4)
- **zmachine**: parse header fields and verify checksums (#3)
- **zmachine**: load and validate story files (#2)

### Fix

- **zmachine**: halt runaway recursion at the stack ceiling (#25)
- **zmachine**: fetch high memory beyond the game-read cap (#16)

### Refactor

- **zmachine**: view headers through live memory (#5)

## v0.0.0 (2026-08-07)
