## v1.0.0 (2026-08-20)

Full Z-Machine Support: every §14 opcode handled, all eight versions played, all four graphical games in the corpus.

### Feat

- **scribe**: the session files -- SCRIPT's transcript, stream 4's command script, input stream 1's playback (§7, §10.2) (#186)
- **machine**: the last three opcodes -- encode_text, buffer_screen, input_stream; all 120 of §14 now handled (#185)
- **trace**: --trace writes every executed instruction, listing-style -- the golden trace, interrupts included (#184)
- **listing**: --listing disassembles the story txd-style -- code found by decoding it, Zork I's 440 routines exact (#183)
- **glass**: the clipboard pastes at the window -- Ctrl+V, Cmd+V, Shift+Insert through the key seam (#182)
- **picfile**: Infocom's original MG1/EG1/CG1 picture files hang their art -- pix2gif's rules, FMV Poker's cards (#181)
- **machine**: mouse clicks arrive as §10.3 input codes -- Solitaire Poker's buttons take a real click (#180)
- **zscii**: surrogate halves fuse at the screen -- the smileys checker's six emoticons render (#177)
- **machine**: timed line reads run live on the wall clock -- Border Zone's espionage engine ticks (#175)
- **screen**: [MORE] paging for the two-window screen -- no speech outruns its reader (#172)
- **glass**: an input caret at the pygame window -- the form's hopping cursor made visible (#171)
- **cli**: --header glances at a story's manifest -- identity, memory map, and flags, cited (#170)

### Fix

- **screen**: the upper cursor tolerates overreach to the screen's edge -- Frotz's silence, bounded (#179)
- **editor**: control characters wait out instead of crashing the session -- tab chief among them (#178)
- **machine**: redisplay only when the story window printed -- no picket fence of prompts (#176)
- **painter**: bold spaces shed their bold -- no glyph, no brightness patchwork (#174)

## v0.10.0 (2026-08-19)

### Feat

- **frontend**: the line editor -- cursor editing and command history at every painted prompt (#164)
- **frontend**: the prompt returns after a printing interrupt (§15) (#156)
- **accept**: the recorder notices another writer at its file (#155)

### Fix

- **zmachine**: the patient typist grows nimble fingers (§15 read_char) (#153)

### Perf

- **zmachine**: static code decodes once (§1.1) -- 19x for Inform 7 (#160)

## v0.9.0 (2026-08-18)

### Feat

- **glass**: zoom grows the grid, never the type (#149)
- **glass**: the window takes its share of the desktop (--zoom) (#147)
- **zmachine**: erase_line lands, pixel reach and all (§8.8.5.2) (#143)
- **gallery**: plaques wear their pre-baked palettes (Bocfel BPal) (#142)
- **glass**: colour -1 samples the pixel under the cursor (§8.3.1) (#141)
- **stage**: a screenful earns its [MORE] (§8.8.3.2.6) (#140)
- **glass**: the window wears its story's version badge (#139)
- **stage**: the cursor tells the truth, proven by Inform's own v6 (#138)
- **glass**: text lands in pixels, and the window takes the art's shape (#137)
- **gallery**: adaptive chrome wears the scene's palette (APal) (#136)
- **stage**: margins bound the flow (§8.8.3.2.1) (#135)
- **png**: clear pixels stay clear, and the banner frames its scene (#134)
- **stage**: eight §8.8 windows take their places on the glass (#133)
- **reso**: grow the art by the Blorb's own elbow room (#132)
- **pictures**: hang the Blorb gallery and let the glass draw it (#131)
- **units**: the measuring glass retires the 1-by-1 font for v6 (#130)
- **glass**: draw font 3 from §16's own bitmaps, retiring the tofu (#129)
- **glass**: the third frontend — the corpus plays in a pygame window (#128)
- **regtest**: cross-certified — same scripts, both runners, held to one verdict in CI (#127)
- **regtest**: the community's tester, in-process — same script, same verdict, any platform (#126)

### Fix

- **stage**: an erase refills the [MORE] budget (§8.8.3.2.6) (#148)
- **glass**: the [MORE] prompt cleans up after itself (§8.8.3.2.6) (#146)
- **zmachine**: cursor properties answer the flowed cursor (§8.8.3.5) (#145)
- **zscii**: alphabet slots hold their expansions (§3.5.5, §3.8.2.1) (#144)

## v0.8.0 (2026-08-16)

### Feat

- **v6**: print_form and the width-bearing stream 3 — Arthur's parser answers back (#123)
- **v6**: scroll_window's conforming quiet — and Arthur takes commands (#121)
- **v6**: the cursor learns its v6 forms — and Arthur's prologue plays (#120)
- **v6**: mouse courtesies — an arrow that never appears, honestly reported (#119)
- **v6**: the window ledger — eight windows of §8.8 state, and six opcodes to drive it (#118)
- **v6**: picture courtesies — honest answers for art the header already declined (#117)
- **v6**: user stacks — push_stack, pop_stack, and the turned-around pull (#116)
- **v6**: get_cursor reads the cursor back — two ZIPTEST categories unblocked (#115)
- **v6**: ZIPTEST boots and names the frontier — header honesty, §3.8 typography, and nop (#114)

### Fix

- **v6**: erase_window learns which windows the glass renders — Arthur past the prologue, painted (#122)

## v0.7.0 (2026-08-15)

### Feat

- **painter**: ask the glass — sixel capability and cell size come from the terminal itself (#111)
- **painter**: attentive waits — idle heartbeats fire end-of-sound routines at the prompt (#110)
- **accept**: --record writes live play as a script — the grammar learns to listen (#109)
- **accept**: pay the refusal-dialect debts — five earned phrases, one withdrawn guess (#108)
- **sound**: the machine finds its voice — §9 playback through a sounddevice speaker (#107)
- **aiff**: read the sounds — a pure-stdlib AIFF decoder over the IFF walker (#106)

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
