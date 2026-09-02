# Playing stories

Point Voxam at a story file and it plays. Each machine is
recognized by the file's own contents rather than its name: a
`.z1` through `.z8` by its header, a `.ulx` or packaged `.gblorb`
by its magic, and an `.aastory` by its form and its own checksum,
verified before it runs.

```bash
voxam path/to/story.z3
voxam path/to/story.ulx
voxam path/to/story.aastory
```

Every face below speaks all three machines. What changes between
them is what the face can offer, and each one says honestly what
it cannot.

## At the terminal

The default. With the `screen` extra installed the painted
frontend takes over automatically: status line, windows, menus,
real-time input. Pass `--plain` to keep the classic stream
instead; pipes and scripted replays always use the stream, which
is what keeps recordings deterministic.

A Glulx story earns the painted glass too: the Glk window tree
drawn across the whole screen, status grids in place, buffer text
wrapping behind a `[MORE]` pause, styles in terminal dress, and
the gblorb's AIFF sounds playing when the sound extra is
installed. `--plain` keeps the classic stream, buffer text
flowing as prose and grids drawn as blocks, which is exactly how
the glulxercise certification drives it.

The terminal is the Å-machine's home face, wrapped at your
terminal's own width the way the reference frontends wrap. Typing
`save` asks for a filename on the spot and writes an AASV file
any conforming interpreter can revive, `restore` reads one back
with the story's own header as the identity gate, and undo is
aboard without asking. The story also wears what its author
dressed it in: the LOOK sheet's bold, its italics (drawn as
underlines, the way Dialog's own debugger draws them), and its
colors as truecolor ink and paper, worn at a real terminal and,
under the display's own colors grant, on the wire as well. A pipe
still gets plain text, because a pipe is not a terminal and Voxam
answers the styling questions honestly per stream.

## In a window

`--graphics` opens the pygame window, which is the home of the
Version 6 games and a fine roomy home for the earlier ones too.
`--zoom` sets how much of the desktop it takes (0.85 by default;
`--zoom 0` keeps the classic compact 80 by 24). `--theme` sets
its ink and paper: `dark` by default, or `paper`, `sepia`, or
`classic` for the old pure white on black.

A Glulx story gets the same window tree in real pixels, the
fitted faces carrying the styles, the gblorb's sounds aboard, and
a glulx badge on the frame, plus everything only a window can
offer: graphics canvases with the gblorb's PNG art drawn on,
mouse clicks in each window's own units, and hyperlinks in the
reader's blue, selected by click.

For the Å-machine this is the one face that knows how tall it is:
a story asking after the screen height gets a true answer there,
text that would scroll away pauses at a `[MORE]` first, and a
story that clears the screen really clears it.

Every story version wears its own badge on the window: `z1`
through `z8` by version, the Glulx mark for a Glulx story, and an
Å over a D for the Å-machine and the Dialog language that
compiles to it.

## In a browser

`--web` serves a story to a browser tab over the GlkOte protocol,
which is the display library of Lectrote and the modern web
interpreters, shipped inside the package: nothing to install and
no network beyond your own machine.

```bash
voxam --web path/to/story.gblorb
```

The story's title rides on the tab, its art is served straight
from the gblorb, each turn is one HTTP exchange, and reloading
the page starts the story over; `--port` moves it off 8080. A
turn that takes long enough to be worth mentioning raises a
working light that counts the seconds, so a page still thinking
is never mistaken for one that has died.

The page arrives in whichever light your system already prefers,
and the **Aa** button in the corner opens the preferences panel:
the ink, the type and its size, and the measure of the column.
The inks are System, Paper, Sepia, Dark, and Frotz, which is the
DOS Infocom look WinFrotz still opens in: white on deep blue,
with the status bar its exact inverse. Every choice is
remembered, and applied before the first paint, so a chosen ink
or size never flashes the other one on its way in. Each ink
names its own status bar rather than deriving one by inverting
the story, which is what keeps §8.2's line legible on a light
page instead of dissolving into the prose beneath it.

Typing `save` in the tab asks for a name through the display's
own prompt and writes the Quetzal file beside the story, where
`restore` -- and every other interpreter -- can find it. An
Å-machine story opens the page with its META bibliography as the
doorway card.

## On a wire

`--glkote` speaks the same protocol as JSON lines on stdin and
stdout -- one update stanza out, one event stanza in -- which is
the seam any GlkOte-speaking host drives down a pipe. It carries
all three machines whole: a `.z3` through `.z8` plays beside a
`.ulx` or `.gblorb`, status line and split windows in the
protocol's own grid, and the Version 6 stage as one scaled canvas
in the art's own coordinates.

A display that asks for it by name gets one thing stock GlkOte
does not carry: a `voxam` block riding beside the windows, with
the plain facts of the session in it. Where the player stands
(the room's object and its printed name), the command the machine
was actually handed, the score and the turn count, and one bit
that says an undo, a restore, or a restart just broke the causal
thread. It is a feed for the features every display has had to
guess at by reading the transcript (a map, a notebook, a "take me
back to the kitchen"), and it does the knowing, not the drawing:
no graph, no layout, and no compass-word parsing lives inside
Voxam. A display that never asks for the block never sees it, and
no update is ever sent into being for its sake.

## As a desktop app

Voxam's native shell is a [Tauri](https://tauri.app/) webview
wearing the same GlkOte display the browser face wears, driving
a spawned `voxam --glkote` down a pipe. Every release tag builds
its installers (Windows, macOS, Linux; unsigned) and attaches
them to the GitHub release beside the wheel.

The shell drives the `voxam` command -- `uv tool install voxam` or
`pipx install voxam` puts it in place. It looks on the PATH first,
then in the bin dirs those installers use (`~/.local/bin` and the
rest), then asks your login shell to resolve it, since an app
launched from the Dock or Finder never inherits a terminal's
PATH. Set `VOXAM_BIN` to an explicit path to skip the search. It
says so plainly when nothing turns up.

Open a story from the landing page or the File menu -- the
picker starts at the stories' own home, a pinned folder or
the last story's, so a save elsewhere never drags it away;
File > Restart Story starts it over, exactly as a reload does in
the browser face, and every story that can be named plays under
its Babel title on the title bar. The Story menu claims a §11.1.3
platform (the `--interpreter` flag's own roster) and sets the
legendary Tandy bit; a changed claim restarts the open story on
the spot, since the identity belongs to the booting machine --
and a Glulx story simply ignores it. Display > Preferences
(Ctrl+, or Cmd+,) opens the same panel the browser face carries,
dressing the page live: the story's type and size, the ink it is
set in, and the measure of its column, remembered across
sessions. The gblorb's art draws in the shell exactly as in the
browser, the pictures riding the updates themselves. And a
Glulx story's `save` opens a real save dialog
-- the desktop's own power, since the picker and the interpreter
share a filesystem -- the chosen path answering the protocol's
file prompt, so saves and restores work exactly as at the
painted glasses. And the Z-Machine saves there too: §15's save
and restore learned the same standing-down the reads learned,
asking for their files through the protocol's special input, so
a Zork saved in the shell is a real Quetzal on disk, restored
through the same picker.

Building the shell from source is in
[CONTRIBUTING.md](CONTRIBUTING.md).

## Best played with

A story file can ask what machine it is running on, and some of
Infocom's games change what they do with the answer. `--interpreter`
is how you answer: it claims any of the platforms §11.1.3 names,
by name or number, and `--tandy` sets the bit that makes early
Infocom games mind their manners.

Neither is a costume. Infocom's Version 6 games carry genuine
per-machine code paths, chosen at startup from the header's
interpreter number, so the flag picks which 1989 machine Voxam is
pretending to be, and the game takes a different branch because
of it. Recommendations, earned from the games' own source rather
than folklore:

- ***Shogun*: the default.** Its own `DISPLAY-BORDER` routine
  draws the right decorative rail only on the IBM machine path;
  claiming `--interpreter amiga` over the IBM picture set gives a
  left-rail-only screen -- Infocom's authentic Amiga behaviour,
  whose matching art this Blorb does not carry.
- ***Zork Zero*: either, with character.** The default plays the
  classic look; `--interpreter amiga` engages §8.3's shared
  color pair and the under-cursor color sampling for the
  grey-parchment look the Amiga release was famous for. Both
  render correctly -- the Amiga is arguably the prettier way in.
- ***Beyond Zork*: any -- the flag is a personality dial.** The
  game reshapes its whole screen model per machine (§11.1.3,
  §16), so each identity is a different-feeling session.
- **Early version 3 games: `--tandy` for the lore.** The
  legendary bit that makes them mind their manners -- *Zork I*
  literally prints a different licence line.

None of these are bugs routed around: they are the games' own
branches, preserved and selectable.

## Seeds and repeatable sessions

Add `--seed` to make the dice reproducible: the same seed and the
same commands produce the same session, every time.

```bash
voxam --seed 1137 path/to/story.z3
```

That promise holds even when the story reseeds itself. A game may
ask for genuine unpredictability mid-session (`random 0` in the
Z-Machine, `@setrandom 0` in Glulx), and in an ordinary session it
gets exactly that, from the operating system's own entropy. Under
an explicit `--seed`, the new dice are drawn off the seeded stream
instead, so the whole run stays a function of the one seed given.
It is the only place Voxam knowingly answers a story with
something other than what the specification asks for, and it is
narrow on purpose: `--seed` already overrides the same rule at
game start, a session without the flag is untouched, and without
it the flag would make a promise the interpreter quietly broke.

The Å-machine's dice are the reference implementation's own, so a
seeded Voxam session and a seeded reference session agree
forever.

## Saves, transcripts, and streams

Typing `save` in a game writes a Quetzal file beside the story --
`zork1.z3` saves to `zork1.sav` -- and `restore` reads it back.
Quetzal is the standard interchange format, so saves travel between
Voxam and other interpreters.

The session files live beside the story the same way. Typing
`script` in a game -- the command every Infocom manual documents
for keeping a paper log -- writes the transcript to `zork1.scr`,
opening with Infocom's own "Here begins a transcript" banner and
closing at `unscript`; the player's commands appear between the
game's text exactly as §7.1.1.1 asks, and 'Flags 2' bit 0 holds
the stream's status at every moment, however the game works it. This
is the §7.4 rule *A Mind Forever Voyaging* depends on. Output stream
4 records the player's commands to `zork1.cmd` as they finish,
and §10.2's input stream 1 plays such a file back, line by line
in the very format stream 4 writes, reverting to the keyboard
when the file runs dry. Nothing is created unless the game asks:
a session that never touches the streams leaves no files behind.

## Blorb resources and cover art

Blorb resources ride along automatically: a `.zblorb` story boots
from its package, and a like-named `.blb` beside a story file is
found on its own and, if the names differ, then `--resources` names
one explicitly. A packaged iFiction record greets the player as a
card before play -- title, headline, author, and the blurb, the
little window WinFrotz shows -- standing under the cover art in the
browser and the shell, and printed with the banner at a painted
terminal. The plain stream keeps its machine-readable quiet: a
record may quote anything, so no free-form bibliography reaches
a pipe.

At a painted terminal a packaged cover picture shows before play;
`--pixels` draws it in real pixels after asking whether the
terminal speaks sixel, falling back to half-blocks when it
does not.

## Reading a story file

Three flags read a story rather than run it.

`--header` reads a story's own manifest (§11.1) and reports it:

```bash
voxam --header path/to/story.z3
```

Release and serial answer "which version of this game is this?"
in one command -- the question the corpus's release-archaeology
keeps asking -- while the checksum is computed as §15's verify
opcode would and judged against the stored word, so a corrupt
download announces itself before it wastes an evening. Every
table address arrives with its Standard citation, and the
courtesies the game asks for -- pictures, sound, undo, a mouse,
menus -- are decoded from the flags as the compiler shipped them,
before any interpreter stamps in capabilities of its own. Packaged
`.zblorb` stories work as-is.

`--babel` names the story instead: its IFID, computed by the
Treaty of Babel's own per-format rules: the `UUID://` brand
where one is burned in, the human-readable legacy identities like
`ZCODE-88-840726` from the header numbers otherwise. And, when
a blorb carries an iFiction record, the record's IFID first with
its title, author, and headline beside it. Unlike the Z-Machine's
own reports, this one speaks all three machines: an `.aastory`'s
embedded IFID unwraps from the header where one is burned in:

```bash
voxam --babel path/to/story.gblorb
```

The same identities name the session itself: a game the iFiction
record or the Infocom catalog knows plays under its own title, in
the terminal's title bar and the pygame window's alike.

`--decompose` reads a resource file apart: a `.zblorb`,
`.gblorb`, `.blb`, or `.blorb`, packaged story or sidecar alike,
and an `.aastory` census in the same dress, its header's claims
and its dictionary's word count read from the chunks themselves:

```bash
voxam --decompose story.zblorb
```

Every chunk is listed in file order with whatever Voxam's own
decoders can say about it: the packaged story's version, release,
and serial read from its own header; each picture's pixel size
with the Fspc cover credited; each AIFF's shape and duration with
the Loop chunk's repeats credited; and the descriptive chunks in
their own words: the iFiction record, the release number, even
the wide-charactered story name and Infocom's own copyright
lines in the old `.blb` sets. Add `--extract` to free the
contents as ordinary files; either into the current directory, or
one named after the flag, created if need be:

```bash
voxam --decompose story.zblorb --extract art/
```

Each resource lands in the format its bytes already are, ready
for a viewer or a player: `pict-1.png`, `snd-4.aiff` (the FORM
re-framed whole, so it opens anywhere), `story.z8` or
`story.ulx` under the story's own version, and the iFiction
record as `ifiction.xml`. A file already standing is never
overwritten; it just earns a note and the rest proceed.

## Disassembly and traces

Deeper than the manifest, `--listing` disassembles the whole story
txd-style: every routine with its locals, every opcode with its
operands drawn for what they mean (call targets and jump
destinations as the $addresses they reach, variables by name,
inline text decoded), then the encoded strings that follow the
code:

```bash
voxam --listing path/to/story.z3
```

Nothing in a story file says where its routines are, so they are
found the way Mark Howell's txd found them: by decoding. A trial
decode accepts an address as a routine only when every instruction
holds together, the region grows through constant call operands to
a fixed point, and whatever refuses to decode is reported as data
rather than skipped. *Zork I* lists its full 440 routines, exactly
txd's own count. The listing is the excavation tool for games
whose source never shipped: when an expedition stalls, the routine
that decided can now be read.

The listing has a live sibling: `--trace` rides any session --
live play or a replayed recording -- and writes every instruction
the machine actually executes to a file, rendered exactly as the
listing renders it, interrupt routines included, closing with a
tally of instructions run and distinct addresses touched:

```bash
voxam --accept recording.accept --trace session.trace
```

A replayed recording makes the trace a *golden* one: when another
interpreter disagrees with Voxam about a story, the first
differing line of their traces is the bug. And when a session
halts, the trace's last line is the instruction that halted it.
The two halves agree with each other too: every address a session
executes appears in the static listing, which is also how you
learn that one full walkthrough of a game may touch barely a
third of its code.

---

The instruments Voxam is developed with -- acceptance recordings,
RegTest suites, the benchmark, the probe, and the filmstrip --
live in [CONTRIBUTING.md](CONTRIBUTING.md).
