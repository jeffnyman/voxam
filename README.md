<h1 align="center">
  <img src="https://raw.githubusercontent.com/jeffnyman/voxam/main/assets/voxam-title.png" alt="VΘXΔM">
</h1>

<p align="center">
  <em>A Specification-Accurate Z-Machine and Glulx Implementation</em><br />
  <em>Early and Late Infocom + Modern Inform</em><br />
  <em>(+ Dialog w/ Å-machine + Arcturus)</em>
</p>

<p align="center">
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/built%20with-Python-blue.svg" alt="Built with Python"></a>
  <a href="https://github.com/jeffnyman/voxam/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="Voxam is released under the MIT license."></a>
</p>

<p align="center">
  <strong>Works On</strong><br>
  <img src="https://raw.githubusercontent.com/jeffnyman/voxam/main/assets/os_windows.png" alt="Windows" align="middle">
  &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;
  <img src="https://raw.githubusercontent.com/jeffnyman/voxam/main/assets/os_mac.png" alt="macOS" align="middle">
  &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;
  <img src="https://raw.githubusercontent.com/jeffnyman/voxam/main/assets/os_linux.png" alt="Linux" align="middle">
</p>

<p align="center">
  <a href="https://pypi.org/project/voxam/"><img src="https://img.shields.io/pypi/v/voxam.svg" alt="PyPI package latest release"></a>
  <a href="https://pypi.org/project/voxam/"><img src="https://img.shields.io/pypi/pyversions/voxam.svg" alt="Supported Python versions"></a>
  <img src="https://img.shields.io/badge/coverage-100%25-brightgreen.svg" alt="Coverage: 100% branch, enforced in CI">
</p>

<p align="center">
  <a href="https://github.com/jeffnyman/voxam/actions/workflows/ci.yml"><img src="https://github.com/jeffnyman/voxam/actions/workflows/ci.yml/badge.svg" alt="CI status"></a>
  <a href="https://conventionalcommits.org"><img src="https://img.shields.io/badge/Conventional%20Commits-1.0.0-green.svg" alt="Conventional Commits: 1.0.0"></a>
</p>

<p align="center">
  <a href="https://vscode.dev/github/jeffnyman/voxam"><img alt="Open with vscode" src="https://img.shields.io/static/v1?logo=visualstudiocode&label=&message=Open%20in%20Visual%20Studio%20Code&labelColor=2c2c32&color=007acc&logoColor=007acc"></a>
  <br />
</p>

<p align="center">
  <a href="#development"><img src="https://img.shields.io/badge/contributions-welcome-brightgreen.svg" alt="Contributions welcome"></a>
</p>

<p align="center">
  If you find any of this useful, consider leaving a ⭐️ for the repo.
</p>

<p align="center">
  <a href="#-the-name"><em>What does Voxam mean?</em></a>
</p>

---

An interpreter for the Z-Machine, for Glulx, and for the
Å-machine, written in Python.

Three virtual machines, spanning the whole history of
interactive fiction:

- **The Z-Machine** is the virtual machine Infocom designed in
  1979 to run its text adventures, and which the community has
  used ever since -- the home of everything from *Zork* to the
  modern Inform and PunyInform games, and the target of
  [Arcturus](https://github.com/8bitgames/arcturus), a modern
  programming language and compiler designed for writing
  interactive fiction that compiles down to efficient Infocom
  Z-Machine story files.
- **Glulx** is the Z-Machine's successor, built to shed its
  size limits, and the target of today's Inform.
- **The Å-machine** is a specialized virtual machine created by
  Linus Åkesson to run interactive fiction written in his
  [Dialog](https://linusakesson.net/dialog/) programming
  language -- the newest of the three.

Voxam reads a compiled story file and executes it, with two
guiding commitments:

- Fidelity to the specifications: the
  [Z-Machine Standard](https://jeffnyman.github.io/z-machine-standard/),
  the [Glulx](https://www.eblong.com/zarf/glulx/) and
  [Glk](https://www.eblong.com/zarf/glk/) specifications, and the
  [Å-machine](https://github.com/Dialog-IF/aamachine/tree/main/docs),
  with every rule the interpreter enforces citing the section it
  came from.
- Reproducibility, so that a recorded play session replays identically,
  forever.

Voxam is developed against real games. The *Zork* trilogy,
*Trinity*, *A Mind Forever Voyaging*, *The Hitchhiker's Guide to
the Galaxy*, and -- filed in triplicate, blood pressure rising --
*Bureaucracy* have all been played to winning conclusions,
several to perfect scores. *Arthur* draws the sword from the
stone in what is, as far as I know, the first seeded, replayable
*Arthur* session anywhere; *The Lurking Horror* and *Sherlock*
reach perfect scores with their sounds heard aloud; *Arthur*,
*Shogun*, and *Zork Zero* render their art in a real graphics
window; and even *Journey* -- Infocom's finale, a game with no
command line at all -- replays through its opening chapter as
pure keystrokes. Forty-four recordings verify those sessions
end-to-end, their annotations doubling as an archaeology of where
the games' published walkthroughs go wrong. And now Glulx joins
them: *Adventure* answers at the terminal, and glulxercise says
"All tests passed." The Å-machine arrives certified harder still:
every test battery its reference implementation ships replays
under Voxam byte-identical to the reference engine's own
transcripts -- *Miss Gosling's Last Case* walked three hundred
fifty-one commands to its finale among them.

The full ledger -- the current release, what plays, what is
certified, and what remains -- lives in [STATUS.md](STATUS.md);
the road here, told era by era, is [HISTORY.md](HISTORY.md);
and the thinking underneath it all, principles and vocabulary
alike, is [DESIGN.md](DESIGN.md).

<p align="center">
  <img src="https://raw.githubusercontent.com/jeffnyman/voxam/main/assets/voxam-footer.png" alt="">
</p>

## How to Play

One command, several faces: every face speaks the Z-Machine and
Glulx, all but the pygame window speak the Å-machine too, and a
story file is all any of them needs:

- **At the terminal.** `voxam story.z5` -- with the `screen`
  extra installed, the painted display takes over: status line,
  windows, menus, real time. `--plain` keeps the classic text
  stream.
- **In a window.** `voxam --graphics story.ulx` -- the pygame
  window: the illustrated home of the Version 6 games, Glulx's
  canvases and mouse, and a fine roomy home for everything else.
- **In a browser.** `voxam --web story.gblorb` -- a GlkOte tab
  on your own machine, art and covers inlined, saves written
  beside the story.
- **As a desktop app.** Grab the Voxam installer for your
  platform from the
  [latest release](https://github.com/jeffnyman/voxam/releases/latest)
  (Windows, macOS, Linux; unsigned, so expect the usual
  first-run nudge). The shell drives the `voxam` command, so
  install that first -- `pipx install voxam` or
  `uv tool install voxam` puts it on the PATH.
- **On a wire.** `voxam --glkote story.z8` -- the whole session
  as JSON stanzas on stdin and stdout, the seam any
  GlkOte-speaking host drives down a pipe.

Installation of the command itself is one line -- see
[Installation](#installation) -- and the flags' full stories live
in [Playing stories](#playing-stories).

## Installation

Voxam requires Python 3.12 or later.

```bash
pip install voxam
```

or, as an isolated tool:

```bash
pipx install voxam
```

If you're using uv managed Python:

```bash
uv tool install voxam
```

And `uvx voxam story.z5` runs it without installing anything at
all -- uv fetches the package to its cache, runs the command, and
leaves your PATH untouched, which is the quickest possible way to
try Voxam on a story file.

The painted screen frontend rides in the `screen` extra, the
pygame window in the `graphics` extra, and sampled-sound playback
in the `sound` extra beside them:

```bash
pip install "voxam[screen,graphics,sound]"
```

Again, if you're using uv managed Python:

```bash
uv tool install "voxam[screen,graphics,sound]"
```

On Windows and macOS the sound extra is self-contained; on Linux,
PortAudio comes from the distribution (`apt install libportaudio2`
or the local equivalent). Without the extras, Voxam plays as a
plain text stream. Every game still works; the status line
simply stays imaginary, and the sound games play in the conforming
silence they were shipped to accept.

Voxam ships no story files. Bring your own: the
[IF Archive](https://ifarchive.org/) hosts hundreds of freely
available games, and story files you own from commercial collections
work as-is.

## Playing stories

Point Voxam at a story file and play at the terminal:

```bash
voxam path/to/story.z3
```

At a terminal with the `screen` extra installed, the painted
frontend takes over automatically: status line, windows, menus,
real-time input. Pass `--plain` to keep the classic stream
instead; pipes and scripted replays always use the stream, which
is what keeps recordings deterministic. And `--graphics` opens
the pygame window, which is the home of the Version 6 games, and
a fine roomy home for the earlier ones too. `--zoom` sets how much
of the desktop it takes (0.85 by default; `--zoom 0` keeps the
classic compact 80 by 24).

Glulx stories play the same way: a `.ulx` file or a packaged
`.gblorb` is recognized by its own magic, and at a real terminal
it earns the painted glass: the Glk window tree drawn across
the whole screen, status grids in place, buffer text wrapping
behind a `[MORE]` pause, styles in terminal dress, and the
gblorb's AIFF sounds playing when the sound extra is installed:

```bash
voxam path/to/story.ulx
```

`--plain` keeps the classic stream, buffer text flowing as prose
and grids drawn as blocks, and a piped session keeps it on its
own, which is exactly how the glulxercise certification drives
it. And `--graphics` opens the pygame window here too: the same
tree in a real window, the fitted faces carrying the styles, the
gblorb's sounds aboard, and a glulx badge on the fram, plus
everything only a window can offer: graphics canvases with the
gblorb's PNG art drawn on, mouse clicks in each window's own
units, and hyperlinks in the reader's blue, selected by click.

The newest face is the browser's. `--web` serves a Glulx story to
a browser tab over the GlkOte protocol, which is the display library
of Lectrote and the modern web interpreters, shipped inside the
package, nothing to install and no network beyond your own
machine:

```bash
voxam --web path/to/story.gblorb
```

The story's title rides on the tab, its art is served straight
from the gblorb, each turn is one HTTP exchange, and reloading
the page starts the story over; `--port` moves it off 8080.
Typing `save` in the tab asks for a name through the display's
own prompt and writes the Quetzal file beside the story, where
`restore` -- and every other interpreter -- can find it. And
`--glkote` speaks the same protocol as JSON lines on stdin and
stdout -- one update stanza out, one event stanza in -- which is
the seam any GlkOte-speaking host drives down a pipe. Both faces
speak the elder machines whole: a `.z3` through `.z8` plays
beside a `.ulx` or `.gblorb`, status line and split windows in
the protocol's own grid, and the Version 6 stage as one scaled
canvas in the art's own coordinates.

A display that asks for it by name gets one thing stock GlkOte
does not carry: a `voxam` block riding beside the windows, with
the plain facts of the session in it. Where the player stands
(the room's object and its printed name), the command the
machine was actually handed, the score and the turn count, and
one bit that says an undo, a restore, or a restart just broke
the causal thread. It is a feed for the features every display
has had to guess at by reading the transcript (a map, a
notebook, a "take me back to the kitchen"), and it does the
knowing, not the drawing: no graph, no layout, and no
compass-word parsing lives inside Voxam. A display that never
asks for the block never sees it, and no update is ever sent
into being for its sake.

Å-machine stories play the same way: an `.aastory` is
recognized by its own form and verified by its own checksum
before it runs:

```bash
voxam path/to/story.aastory
```

The terminal is the third machine's home face, wrapped at your
terminal's own width the way the reference frontends wrap;
typing `save` asks for a filename on the spot and writes an
AASV file any conforming interpreter can revive, `restore`
reads one back with the story's own header as the identity
gate, and undo is aboard without asking. `--web` and `--glkote`
carry the same story to a browser tab or down the wire -- the
desktop shell plays it through that same seam -- with the
story's META bibliography opening the page as its card and its
title riding the tab. The story also wears what its author
dressed it in: the LOOK sheet's bold, its italics (drawn as
underlines, the way Dialog's own debugger draws them), and its
colors as truecolor ink and paper, worn at a real terminal and,
under the display's own colors grant, on the wire as well. A
pipe still gets plain text, because a pipe is not a terminal
and Voxam answers the styling questions honestly per stream.
The dice are the reference
implementation's own, so a seeded Voxam session and a seeded
reference session agree forever.

Add `--seed` to make the dice reproducible: the same seed and the
same commands produce the same session, every time.

```bash
voxam --seed 1137 path/to/story.z3
```

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
does not. `--interpreter` claims any §11.1.3 platform by name or
number, and `--tandy` sets the bit that makes early Infocom games
mind their manners.

And before playing anything, `--header` reads a story's own
manifest (§11.1) and reports it:

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

And `--decompose` reads a resource file apart: a `.zblorb`,
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

### Best played with

`--interpreter` is not a costume. Infocom's Version 6 games carry
genuine per-machine code paths, chosen at startup from the
header's interpreter number, and the flag picks which 1989 machine
Voxam is pretending to be. Recommendations, earned from the games'
own source rather than folklore:

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

## Acceptance scripts

A live session can be written down as it is played, and replayed
later:

```bash
voxam --record my-session.accept path/to/story.z3
voxam --accept my-session.accept
```

`--record` captures every line typed and key pressed -- at the
plain stream or the painted terminal alike -- flushed input by
input, so even a session that ends in a death leaves a replayable
script up to its last keystroke. A recording needs a seed to
replay, so `--record` without `--seed` rolls one and writes it
down; the banner names it. An existing file is never overwritten,
and the rare input the script grammar cannot spell exactly draws a
warning rather than being silently mangled. A recorded session is
also the raw material for a curated one: scripts are just text, so
trim the wrong turns, add annotations, and keep the seed.

An acceptance script is a plain text file of typed commands plus a
few directives:

```text
! SEED=99
! GAME=path/to/story.z1

# Comments annotate the session; blank lines are ignored.

x me. x mailbox            # inline comments start at whitespace + #
> open mailbox             # the > prefix is optional transcript style
```

The rules, line by line:

- `! KEY=VALUE` is a directive: `GAME` names the story file to run,
  and `SEED` fixes the dice (a `--seed` argument overrides it). A
  relative `GAME` path counts from the script's own directory, and
  forward slashes work on every platform.
- `#` at the start of a line is a comment.
- An inline comment begins at whitespace followed by `#`.
- A leading `>` is optional and stripped; it also escapes the rare
  command that genuinely begins with `#` or `!`. A `>` alone types
  an empty line: the enter key.
- `<up>`, `<down>`, `<left>`, `<right>`, and `<escape>` press
  special keys, one line per press -- how a recording drives
  *Beyond Zork*'s menus and builds its characters. A token naming
  no known key fails loudly, and the `> <up>` prompt form stays a
  literal command for a game that really wants angle brackets.
- A line starting with three backticks is a fence: everything until
  the next fence is skipped entirely, directives included. Text
  after the backticks labels the fence, and an unclosed fence skips
  the rest of the file -- handy while working out a section that a
  seed change will invalidate, or to replay only the start of a
  longer script.
- Anything else is typed into the game exactly as written.
- When the commands run out, the session ends as if the player had
  reached end of input.

While curating a longer session, `--replay` types the script and
then leaves you at the prompt instead of ending, so a
work-in-progress script catches you up to where you left off:

```bash
voxam --replay some-session.accept
```

And when a session has to stop -- or a wrong turn needs cutting --
`--resume` is that whole expedition loop as one flag:

```bash
voxam --resume my-session.accept
```

It replays the script to its last line, hands you the prompt, and
appends everything you type to the same file. Trim the bad tail in
an editor, resume, and press on: a recording grows append-only,
under its own seed, across as many sittings as the game demands.

### RegTest scripts

Voxam also speaks [RegTest](https://eblong.com/zarf/plotex/regtest.html),
Andrew Plotkin's public-domain regression-test format for
interactive fiction -- and speaks it twice over. A RegTest script
of named tests, commands, and per-turn checks runs through the
built-in in-process runner on any platform:

```bash
voxam --regtest my-suite.regtest
```

or through Plotkin's own reference implementation driving
`voxam --plain` over pipes on POSIX systems, same file, same
verdict. The in-process runner boots a fresh machine per test at
in-process speed, reports failures in the reference's own voice,
and reaches further than the reference's dumb-terminal mode can:
keystroke input works, because a sent line lands on the same
input seam a recording uses. The `regtest/` directory holds
certified scripts that continuous integration runs under both
implementations and holds to the same verdict -- plus an *Arthur*
script only the built-in runner can follow, since v6's inline
keystroke prompts defeat pipe-based prompt framing. A seed on the
script's `** interpreter:` line makes the whole suite
deterministic under both runners, which is not a thing most
interpreters can offer RegTest at all.

### Refusal warnings

During a replay, Voxam listens for the parser's *refusal dialect* --
responses like "You can't see any statuette here!" or "You should
close it first" that mean a recorded command did not do what it
said. Each one is reported with the script line that drew it:

```text
voxam: line 31: 'lock door' looks refused: You should close it first.
```

Refusals scroll past a human reader without registering, and the
missing side effect may not surface until dozens of turns later.
The warning points at the moment it happened, which turns the most
common recording bug from an archaeology expedition into a one-line
fix.

### Probing a recording

When a recording goes wrong -- a death that survives every retry, a
walkthrough command the game will not speak -- the fix is empirical,
and `voxam.probe` is the instrument. A seeded script is a
deterministic timeline, so a probe can replay the recorded prefix
exactly and then ask "what would happen if...?", as many times as it
takes:

```python
from voxam.probe import Probe

probe = Probe.load("acceptance/advent.accept")
run = probe.attempt(["ne", "give eggs to troll", "ne"], drop_last=2)

for step in run.steps:
    line = step.response.strip().splitlines()[0] if step.response.strip() else ""
    flag = f"  <<< {step.refusal}" if step.refusal else ""
    print(f"[{step.command}] {line}{flag}")
```

Each step pairs a typed command with everything the story said
back, and flags any response spoken in the refusal dialect --
which turns a hundred-command stretch into a one-screen diagnosis.
`attempt` replays the script and tries a variant tail
(`drop_last` re-tries the ending without editing the file);
`run` takes the whole command list for surgery the prefix cannot
express, such as inserting turns mid-timeline; and the returned
`machine` is left standing for post-mortem reads of globals,
object parents, or the clock. Every run boots fresh from the seed,
so no experiment can contaminate another.

Probe scripts themselves are throwaways -- write one in a scratch
file, find the answer, record the fix in the `.accept` annotations,
and delete it. The harness is the part worth keeping.

### The filmstrip

Any recorded walk can be photographed. `--shots DIR` rides
`--accept`: the script replays at the real pygame glass --
driven, so no `[MORE]` waits on a player -- and every settled
turn saves a numbered frame, the boot screen first and the final
response last. Add `--browser` (a path, or bare to find one on
this machine) and the same walk shoots the web display instead:
the wire's own updates render through the shipped glkote.js in
your browser's headless mode, one launch per frame, both
machines welcome.

```console
voxam --accept bronze.accept --shots strips/before
voxam --accept bronze.accept --shots strips/after --browser
voxam --strip-diff strips/before strips/after
```

`--strip-diff` decodes every same-named frame with Voxam's own
PNG reader and compares pixel by pixel: differing frames each
get a line with a tally, frames only one strip holds are named,
and the verdict says where the strips part. The exit code speaks
RegTest's contract -- 0 identical, 1 parted -- so a regression
sweep can gate on it: photograph the corpus before a change,
photograph it after, and read only the frames that moved. A
driven, seeded walk reproduces to the pixel, and a glass strip
needs no screen at all: set `SDL_VIDEODRIVER=dummy` and the
window photographs in memory. One honest caveat rode home with
the feature: Version 6 games can read their presentation into
their own randomness, so a walk recorded at one face may
diverge at another -- the strip keeps every frame it earned and
says where it broke, and strips compare face-to-same-face.

## Development

Contributions are welcome -- an
[issue](https://github.com/jeffnyman/voxam/issues) is the front
door, whether it carries a bug, a question, or a pull request's
opening thought, and everything below is the contributor's
setup. The project's design principles, and the internal
vocabulary the documents and commit messages lean on (the wire,
the glass, the dress, and the rest), live in
[DESIGN.md](DESIGN.md). Working on Voxam itself needs
[uv](https://docs.astral.sh/uv/) for dependency and environment
management:

```bash
git clone https://github.com/jeffnyman/voxam.git
cd voxam
uv sync --all-groups
```

All commands below assume that environment.

| Task | Command |
| --- | --- |
| Run the test suite | `uv run pytest` |
| Run tests without coverage | `uv run pytest --no-cov` |
| Lint | `uv run ruff check .` |
| Lint and autofix | `uv run ruff check --fix .` |
| Format | `uv run ruff format .` |
| Check formatting only | `uv run ruff format --check .` |
| Type check | `uv run mypy` |
| Build distributions | `uv build` |

### The desktop shell

The `desktop/` directory holds Voxam's native shell: a
[Tauri](https://tauri.app/) webview wearing the same GlkOte
display the browser face wears, driving a spawned
`voxam --glkote` down a pipe. It is not part of the Python
package -- the wheel never carries it, and the Python toolchain
never sees it -- but it wears the same version: every release tag
builds its installers (Windows, macOS, Linux; unsigned) and
attaches them to the GitHub release beside the wheel. Building it
locally needs Rust (with the platform's native toolchain) and
Node:

```bash
cd desktop
npm install          # fetches the Tauri CLI
npx tauri dev        # run it; the first compile takes minutes
npx tauri build      # produce the platform installer
```

Two facts worth knowing when changing the shell's display. First,
part of `desktop/ui/` is vendored copies rather than originals:
`glkote.js`, `glkote.css`, `jquery-1.12.4.min.js`, `waiting.gif`,
`voxam-audio.js`, and `LICENSE-glkote.txt` are the same files the
Python package ships in `src/voxam/pages/`, copied in so the
shell needs no network and no build step -- when the originals
change, re-copy them (`index.html` and `shell.js` are the shell's
own and live only here). Second, a built shell *embeds* `ui/` at compile time:
`npx tauri dev` serves the directory live, so edits show on
reload, but an installer or a release binary keeps serving
whatever was embedded when it was built. After any `ui/` change,
rebuild (`npx tauri build`, or `cargo build --release` inside
`src-tauri/` for the bare executable) before trusting what an
installed shell shows -- a stale embed looks exactly like your
change not working.

The shell drives the `voxam` command -- `uv tool install voxam` or
`pipx install voxam` puts it in place. It looks on the PATH first,
then in the bin dirs those installers use (`~/.local/bin` and the
rest), then asks your login shell to resolve it, since an app
launched from the Dock or Finder never inherits a terminal's
PATH. Set `VOXAM_BIN` to an explicit path to skip the search. It
says so plainly when nothing turns up. Open a story from the landing page or the File menu --
the picker starts at the stories' own home, a pinned folder or
the last story's, so a save elsewhere never drags it away;
File > Restart Story starts it over, exactly as a reload does in
the browser face, and every story that can be named plays under
its Babel title on the title bar. The Story menu claims a §11.1.3
platform (the `--interpreter` flag's own roster) and sets the
legendary Tandy bit; a changed claim restarts the open story on
the spot, since the identity belongs to the booting machine --
and a Glulx story simply ignores it. The Display menu dresses the
page -- the story's type and size, the ink it is set in (paper,
sepia, or dark), and the measure of its column -- applied live,
remembered across sessions. The gblorb's art draws in the shell
exactly as in the browser, the pictures riding the updates
themselves. And a Glulx story's `save` opens a real save dialog
-- the desktop's own power, since the picker and the interpreter
share a filesystem -- the chosen path answering the protocol's
file prompt, so saves and restores work exactly as at the
painted glasses. And the Z-Machine saves there too: §15's save
and restore learned the same standing-down the reads learned,
asking for their files through the protocol's special input, so
a Zork saved in the shell is a real Quetzal on disk, restored
through the same picker.

### The Rust port

[voxam-rs](https://github.com/jeffnyman/voxam-rs) is a port of
this interpreter to Rust, kept in its own repository, and this
implementation is its reference: every seeded session recorded
here is expected to replay byte-identically there, and the
port's parity sweeps prove it rather than assert it. The port
carries `PORT.md`, its design document, which is also where
Voxam's own extensions to the GlkOte protocol are specified.
That is why a few citations in this codebase read
`PORT: What the sidecar carries` where the rest name a published
specification: the wire's extensions belong to no standard, so
they are written down once, in the one place both
implementations can be held to.

### Project conventions

- **Layout.** Source lives under `src/voxam`, tests under `tests/`. The `src`
  layout ensures tests exercise the installed package rather than the working
  directory.
- **Typing.** `mypy` runs in strict mode over both `src` and `tests`, and the
  package ships a `py.typed` marker so downstream consumers get its types.
- **Coverage.** The suite is gated at 100% branch coverage. This is deliberate
  for a project of this size; adjust `fail_under` in `pyproject.toml` if it
  stops being useful.
- **Spec citations.** The `§` references in code, docstrings, and output
  follow the HTML rendering of the Z-Machine Standard 1.1 vendored at
  `entharion/z-machine-standard/`. Other renderings of the same
  Standard, including the PDF beside it, number some paragraphs differently.
- **Line endings.** LF everywhere except Windows script files, enforced by both
  `.gitattributes` and `.editorconfig`.
- **Recordings.** Complete playthroughs live under `acceptance/` in the
  repository (they are not part of the installed package). They reference
  games under the optional `entharion` submodule, so they replay locally
  rather than in CI -- and they double as the project's archaeology notebook,
  annotating where the games' published walkthroughs go wrong.

### Pre-commit hooks

Install the hooks once, after which lint, format, and type checks run on every
commit, and commit messages are validated:

```bash
uv run pre-commit install
```

Every hook is a `repo: local` entry that runs its tool out of the project
environment via `uv run`, so pre-commit never clones hook repositories or
builds cached environments under `~/.cache/pre-commit`. Tool versions have a
single source of truth: `uv.lock`.

To run every hook against the whole tree:

```bash
uv run pre-commit run --all-files
```

### Commit messages

Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/),
enforced at commit time by [commitizen](https://commitizen-tools.github.io/commitizen/)
through the `commit-msg` hook installed above:

```text
feat: add object table parsing
fix(memory): reject story files shorter than the header
docs: explain the save file format
```

To check a message by hand, or to compose one interactively:

```bash
uv run cz check -m "feat: add object table parsing"
uv run cz commit
```

Because the history is machine-readable, commitizen derives the next
version, tags it, and updates the changelog:

```bash
uv run cz bump
```

### Reference Material (optional)

An `entharion` submodule holds the specifications and story files this
project is developed against. These are not required as part of building
and deploying Voxam, but they help during development. Voxam does not
depend on anything under `entharion/`. It is not needed to install the
project and CI does not fetch it. Git leaves submodules empty unless
asked, so a plain clone simply skips it.

If you want this reference material and if this is your first time checking
out the repo, run this command:

```sh
git submodule update --init --recursive
```

That will fetch the primary repository as well as its submodules:

- [frotz](https://gitlab.com/DavidGriffith/frotz)
- [ztools](https://github.com/jeffnyman/ztools)
- [reform6](https://github.com/jeffnyman/reform6)
- [ifarchive-if-specs](https://github.com/iftechfoundation/ifarchive-if-specs)
- [z-machine-standard](https://github.com/jeffnyman/z-machine-standard)

The latter is my own recomposed version of the Z-Machine Standard document,
made a little easier for me to read and consume. You can see this deployed
here:

- [Jeff's Z-Machine Standard Document](https://jeffnyman.github.io/z-machine-standard/)

To discard it again, freeing the disk space without affecting the project:

```bash
git submodule deinit --all
```

Dependabot tracks the pinned commit and opens a PR when upstream moves.
To move the pin by hand instead:

```bash
git submodule update --remote entharion
git submodule update --init --recursive entharion
git add entharion
git commit -m "chore(deps): update entharion submodule"
```

The second command carries no `--remote` on purpose: it aligns
entharion's own vendored submodules to the pointers the new pin
records. It is a no-op when the update only added files, and the
cure when a vendor pointer moved -- with `--remote` it would
instead drag those checkouts past their recorded pointers and
leave the submodule looking dirty.

#### Building the Reference Tools

Entharion includes several buildable C references, each a nested
submodule:

- `frotz` — the reference Z-Machine interpreter; its "dumb" build
  (`dfrotz`) runs in a plain terminal with no display dependencies.
- `glulxe` (with `cheapglk`) — the reference Glulx interpreter,
  spoken through the minimal Glk library beside it: plain stdio,
  dfrotz's twin for the other machine.
- `ztools` — inspection utilities such as `infodump` (header, objects,
  dictionary) and `txd` (disassembler).
- `reform6` — an Inform 6 based compiler for producing story files.

Building them is optional. They are useful for comparing Voxam's
behavior against known-good implementations. All three need only a C
compiler, `make`, and a Unix-like environment.

**Prerequisites**

**Windows.** The tools assume a Unix environment, so use WSL. From an
elevated PowerShell (rebooting if prompted, then creating a Unix user
when the Ubuntu shell first opens):

```powershell
wsl --install
```

Then, inside the Ubuntu shell, install the toolchain:

```sh
sudo apt update
sudo apt install build-essential groff
```

(`groff` is only needed to format the ztools man pages.)

Your Windows drives are visible in WSL under `/mnt`, so a checkout at
`F:\Projects\voxam` is reachable at `/mnt/f/Projects/voxam`.

**macOS.** Install the command line developer tools:

```sh
xcode-select --install
```

**Linux.** Install a compiler toolchain, e.g. on Debian/Ubuntu:

```sh
sudo apt update
sudo apt install build-essential groff
```

**Compiling.**

From the repository root (in WSL, macOS Terminal, or a Linux shell):

```sh
make -C entharion/vendor/ztools
make -C entharion/vendor/reform6
make -C entharion/vendor/frotz dumb
make -C entharion/vendor/cheapglk
make -C entharion/vendor/glulxe
```

(`cheapglk` must build before `glulxe`: its build generates the
`Make.cheapglk` snippet glulxe's Makefile includes, from the
side-by-side layout its defaults already expect.)

The binaries land in each tool's own directory, and each of those
repositories already ignores its build artifacts, so nothing shows up
as untracked in Git.

**Running.**

From a Unix shell:

```sh
./entharion/vendor/frotz/dfrotz entharion/zcode-infocom/ballyhoo-r97-s851218.z3
./entharion/vendor/ztools/infodump -i entharion/zcode-infocom/amfv-r77-s850814.z4
./entharion/vendor/glulxe/glulxe entharion/glulx-code/advent-r5-s961209.ulx
```

On Windows the binaries are Linux executables, but they can be invoked
directly from PowerShell by prefixing `wsl`:

```powershell
wsl ./entharion/vendor/frotz/dfrotz entharion/zcode-infocom/ballyhoo-r97-s851218.z3
```
---

## 🪄 The Name

<p align="center">
<img src="https://raw.githubusercontent.com/jeffnyman/voxam/main/assets/voxam-symbol.png" height="50" width="50" alt=""><br>
<img src="https://raw.githubusercontent.com/jeffnyman/voxam/main/assets/voxam-glow.png" alt="VΘXΔM">
</p>

The name Voxam draws from two sources of inspiration:

* From Latin, vox means "voice," evoking the idea of turning a player's command into action, like voice into magic.
* In _Zork: Grand Inquisitor_, voxam was a spell meaning "to separate the energies of different magics." That maps well to the process of parsing, breaking down a command into meaningful parts, isolating intent from raw text.

So whether seen as linguistic alchemy or parser sorcery, VΘXΔM stands at the intersection of command and consequence; of input and invocation.

<p align="center">
<img src="https://raw.githubusercontent.com/jeffnyman/voxam/main/assets/voxam-spell.png" alt="">
</p>

In terms of a few more historical details, the VOXAM spell has a hilarious relevance in _Zork: Grand Inquisitor_: it's a complete joke and serves absolutely no functional purpose in the main game. When you first receive your spellbook from Y'Gael at the bottom of the well, VOXAM is one of the three starting spells written inside (alongside REZROV and IGRAM). According to the in-game lore, it belongs to the class of High Magic and, as stated earlier, is defined as a spell to "separate the energies of different magics."

Its actual relevance breaks down into two categories:

* In the Main Game: Pure Flavor & Trolling. While you use REZROV to open the very first locked door and IGRAM to turn purple things invisible later on, VOXAM can't be cast successfully on anything.
* The Developer Joke: The developers included it purely as world-building flavor to pad out your initial spellbook and to trick players into trying it on various magical anomalies throughout the Great Underground Empire.

Also worth mentioning is the "Booznik" System. Later in the game, you discover that the Grand Inquisitor has "Boozniked" (reversed) all magic. If you were theoretically able to reverse VOXAM, it would mean "conjoin the energies of different magics," but the spell remains entirely useless to your inventory.

So: a spell defined as separating the energies of different magics, that generations of players cast hopefully at every anomaly in the Great Underground Empire, and that never once worked on anything -- until now. Point this one at a story file and it separates raw Z-code into opcodes, operands, and intent, exactly as advertised.

*Twenty-nine years later, the spell finally works on something.*

Chris McDonald, in [Techno History](https://technicshistory.com/2016/11/13/about-techno-history/), wrote:

> "Humans are ceaseless borrowers and copiers. Perhaps, contra *Ecclesiastes*,
> there is an occasional new thing under the sun, but certainly humans think no
> new thoughts *ex nihilo*. And yet we are also ceaseless inventors. We combine
> existing ideas in new ways or place them in new surroundings, and suddenly
> the old becomes new, in a wonderful alchemy of the mind."

A borrowed machine, a borrowed spell, a borrowed voice -- combined in new
surroundings until the old became new. VΘXΔM is that alchemy, practiced on
Z-code.

## 👨‍💻 Author

<p align="center">
  Made with 🤍 by <a href="https://github.com/jeffnyman">Jeff Nyman</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3178C6?style=for-the-badge&logo=python&logoColor=white">
</p>

<p align="center">
  <a href="https://testerstories.com" target="_blank" >
    <img src="https://img.shields.io/badge/Website-Jeff%20Nyman-000000?style=social&logo=wordpress" alt="Website - Jeff Nyman">
  </a>
</p>
<p align="center">
  <a href="https://www.linkedin.com/in/jeffnyman/" target="_blank" >
    <img src="https://img.shields.io/badge/LinkedIn-Jeff%20Nyman-0A66C2?style=social&logo=linkedin" alt="LinkedIn - Jeff Nyman">
  </a>
</p>

## ☦️ Doxazein (δοξάζειν)

<p align="center">
  חֶסֶד וֶאֱמֶת אַל־יַעַזְבֻךָ קָשְׁרֵם עַל־גַּרְגְּרֹתֶיךָ כָּתְבֵם עַל־לוּחַ לִבֶּךָ
</p>

<p align="center">
"Let not mercy and truth forsake thee:<br>
bind them about thy neck;<br>
write them upon the table of thine heart."<br>
<em>Proverbs 3:3</em>
</p>

## 🕹️ Acknowledgements

This project stands on the shoulders of the team at Infocom, the MIT-born company that invented the Z-Machine to let _Zork_, and everything that followed, run unmodified across nearly every computer of its era. Particular thanks go to Marc Blank and Joel Berez, who designed the Z-Machine's virtual architecture, and to Tim Anderson, Bruce Daniels, and Dave Lebling, whose work on _Zork_ at MIT gave the format a reason to exist. Thanks also to Graham Nelson, whose Inform language and Z-Machine Standards Document kept the format alive and well-documented long after Infocom itself was gone, making implementations like this one possible.

## ⚖️ License

The code used in this project is licensed under the [MIT license](https://github.com/jeffnyman/voxam/blob/main/LICENSE).

**Note:** This license applies _only_ to the code in this repository. The original Z-Machine concept, design, and any original assets belong to their respective copyright holders.

✨ Long live the classics.
