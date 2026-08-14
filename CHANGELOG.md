## v0.6.0 (2026-08-14)

### Feat

- **accept**: press the arrows — key tokens in the recording grammar (#103)
- **blorb**: show cover art before play, in half-blocks or real sixel pixels (#99)
- **zmachine**: offer the §8.3 colours and stamp the palette honestly (#98)
- **screen**: the painter owns the keyboard — raw input, rubout, and arrow keys (#97)
- **zmachine**: grant the §16 font, stamp the v5 unit fields, and print rectangles true (#96)
- **blorb**: read resource files and boot packaged stories (#93)
- **cli**: claim interpreter platforms and the legendary Tandy bit (#92)

### Fix

- **screen**: clear the glass before play begins (#102)

### Refactor

- **iff**: lift the IFF container out of quetzal (#91)

## v0.5.0 (2026-08-14)

### Feat

- **painter**: run timed reads on the wall clock (#88)
- **painter**: read raw keystrokes through the frontend (#87)
- **painter**: paint the screen model through blessed (#86)
- **screen**: model the §8 windows as a pure cell grid (#85)

## v0.4.0 (2026-08-13)

### Feat

- **zmachine**: let sampled sounds pass in conforming silence (#83)
- **zmachine**: spend read_char lines as queued keystrokes (#81)
- **zmachine**: fire timed-input interrupts on a virtual clock (#78)
- **zmachine**: claim Standard 1.1 with the unicode cluster (#76)
- **zmachine**: save memory regions to named auxiliary files (#75)

## v0.3.0 (2026-08-13)

### Feat

- **zmachine**: append typed input after a preloaded line (#72)
- **zscii**: speak the extra characters of the default table (#70)
- **zmachine**: stack undo snapshots sixteen turns deep (#69)
- **zmachine**: unwind the call stack with throw and catch (#68)
- **zmachine**: declare Standard 1.0 in header (#65)
- **zmachine**: discard the stack top with pop (#63)
- **zmachine**: complete timed reads under the instant typist (#61)
- **zmachine**: print rectangles of table text with print_table (#56)
- **zmachine**: copy, smear, and zero tables with copy_table (#55)
- **zmachine**: honor custom alphabet tables in text and lookups (#54)
- **zmachine**: shift words logically and arithmetically (#53)
- **zmachine**: lex the buffer on demand with tokenise (#52)
- **zmachine**: hold and replay an undo snapshot (#51)
- **zmachine**: read version 5's counted text buffer with aread (#50)

### Fix

- **zmachine**: answer the object-zero family with nothing (#73)
- **zmachine**: accept a read with the parse buffer omitted (#71)
- **zmachine**: read table indices as signed on a 16-bit bus (#67)
- **zmachine**: settle overshifts instead of halting (#66)
- **zscii**: print the null as nothing, as §3.8.2.1 defines (#64)
- **zmachine**: answer test_attr on object 0 with false (#59)
- **zmachine**: answer object-tree reads about object 0 with nothing (#58)

## v0.2.0 (2026-08-12)

### Feat

- **probe**: add a probe harness for interrogating recordings (#48)
- **acceptance**: teach the refusal guard Inform's dialect (#46)
- **zmachine**: wire save, restore, and restart opcodes (#45)
- **zmachine**: encode and decode Quetzal saved games (#44)
- **zmachine**: capture and restore the state of play (#43)
- **zmachine**: dispatch call_vs2 and call_vn2 through the shared call handler (#41)
- **frontend**: sound bleeps and render upper-window content (#39)
- **zmachine**: redirect output through the §7 stream machinery (#38)
- **zmachine**: read single keystrokes with read_char (#37)
- **zmachine**: route window operations and mute the upper window (#36)
- **zmachine**: route screen operations through the frontend (#35)

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
