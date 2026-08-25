<h1 align="center">
  <img src="https://raw.githubusercontent.com/jeffnyman/voxam/main/assets/voxam-title.png" alt="VΘXΔM">
</h1>

<p align="center">
  <em>A Specification-Accurate Z-Machine and Glulx Implementation</em><br />
  <em>Early and Late Infocom + Modern Inform</em>
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
</p>

<p align="center">
  If you find any of this useful, consider leaving a ⭐️ for the repo.
</p>

---

An interpreter for the Z-Machine and for Glulx, written in
Python.

The Z-Machine is the virtual machine Infocom designed in 1979 to run
its text adventures, and which the interactive fiction community has
used ever since. Voxam reads a compiled story file and executes it,
with two guiding commitments: fidelity to the specifications --
the [Z-Machine Standard](https://jeffnyman.github.io/z-machine-standard/)
and the [Glulx](https://www.eblong.com/zarf/glulx/) and
[Glk](https://www.eblong.com/zarf/glk/) specifications, every rule
the interpreter enforces citing the section it came from -- and
reproducibility, so that a recorded play session replays
identically, forever.

VΘXΔM is developed against real games. The *Zork* trilogy,
*Trinity*, *A Mind Forever Voyaging*, *The Hitchhiker's Guide to
the Galaxy*, and -- filed in triplicate, blood pressure rising --
*Bureaucracy* have all been played to winning conclusions,
several to perfect scores. *Arthur* draws the sword from the
stone in what is, as far as we know, the first seeded, replayable
*Arthur* session anywhere; *The Lurking Horror* and *Sherlock*
reach perfect scores with their sounds heard aloud; *Arthur*,
*Shogun*, and *Zork Zero* render their art in a real graphics
window; and even *Journey* -- Infocom's finale, a game with no
command line at all -- replays through its opening chapter as
pure keystrokes. Forty recordings verify those sessions
end-to-end, their annotations doubling as an archaeology of where
the games' published walkthroughs go wrong. And now Glulx joins
them: *Adventure* answers at the terminal, and glulxercise says
"All tests passed." The full ledger lives in
[STATUS.md](STATUS.md).

<p align="center">
  <img src="https://raw.githubusercontent.com/jeffnyman/voxam/main/assets/voxam-footer.png" alt="">
</p>

## Status

Version `1.9`: The desktop shell arrives -- installers on the
release, and the displays polished.

The Z-Machine claim is `1.0`'s: every opcode §14 defines has a
handler, all eight story file versions play -- version 6
illustrated at a pygame window, painted at a terminal, spoken
aloud with the sound extra -- and everything is enforced in
continuous integration rather than promised: a test suite at
100% branch coverage, forty recorded playthroughs swept
end-to-end, and the community's checkers held to their exact
tallies, CZECH at four versions among them.

The Glulx machine is `1.1`'s: every opcode the Glulx 3.1.3
roster defines is dispatched -- the full Glk 0.7.6 dispatch layer
behind the `glk` opcode, saves and undo in Quetzal, the
allocation heap, the accelerated Inform veneer, IEEE-754 floats
and doubles -- and the glulxercise checker certifies the whole of
it in continuous integration: seventy sections, zero failures,
"All tests passed." spoken through the same stdio session a
player can pipe.

The terminal glass and the grammar are `1.2`'s: a `.ulx` or
`.gblorb` story plays on painted terminal glass -- the Glk window
tree drawn whole, styles in terminal dress, timer events between
keystrokes, and Glk sound through the same speaker the Z-Machine
owns -- and the acceptance grammar spells every input any display
can produce: raw keystrokes as the tokens Beyond Zork's menus
always replayed through, and mouse clicks as `<click x y>`,
recorded with their coordinates and replayed with the same.

The third glass is `1.3`'s: `--graphics` opens a Glulx story in
the pygame window, the same window every Z-Machine version plays
in, one painted spine driving both Glk displays -- the window
tree, buffers wrapped behind `[MORE]`, styles in the fitted
faces, timers, and the Blorb's sound through the speaker.

The senses are `1.4`'s: graphics windows as true pixel canvases,
the gblorb's art drawn onto them scaled and clipped, the mouse
landing in whichever armed grid or canvas it hit, hyperlinks in
the reader's blue and selected by click -- and the acceptance
grammar spelling every one of those inputs, recorded at the
window and replayed anywhere.

The treaty and the declaration are `1.5`'s: VΘXΔM claims Full
Glulx, in the manner `1.0` claimed the Z-Machine -- glulxercise
entire, the displays' claims all true where made, and an
exclusion ledger of exactly two spec-sanctioned refusals with
their reasons written down. And the Treaty of Babel is aboard:
`--babel` reports any story's IFID by the treaty's own per-format
rules, a blorb's iFiction record answers first with its
bibliography beside it, and every game that can be named plays
under its own name in the title bar -- modern games through their
records, Infocom's whole catalog through a table of its 246 known
releases.

The protocol is `1.6`'s: VΘXΔM speaks GlkOte -- the display
protocol of Lectrote and the modern web interpreters -- from the
machine's side, the role RemGlk plays for the C interpreters. The
machine learned to stand and wait: `glk_select` suspends instead
of blocking, the host delivers the event, and execution steps on
as though it never stopped. On that seam the protocol goes both
ways: `--glkote` serves whole sessions as JSON lines on stdin and
stdout -- the wire the desktop shell drives -- and `--web` puts
the same conversation in a browser tab, the vendored GlkOte
display served from inside the package, one POST per turn, the
story's title on the tab and the machine's own icon beside it,
the gblorb's art inlined in the updates themselves as `data:`
urls -- any GlkOte display draws it with no Blorb of its own --
and a page reload starting the story over.

And the protocol faces speak
[arc_image](https://github.com/8bitgames/arcturus), the picture
band of Stefan Vogt's Arcturus games: a conformant z5 or z8 whose
sidecar Blorb carries art plays with the band hung above the whole
screen, the picture following the story scene by scene -- in the
browser and the desktop shell alike, while every other face plays
the same story honestly as text, exactly as the format promises.
The private-use opcode range it rides in now skips unclaimed
everywhere (§14.2), so any interpreter extension passes through
VΘXΔM quietly.

The protocol made whole is `1.7`'s: a game's ask for a save file
suspends the machine mid-Glk-call -- a second kind of standing
down, the call's own result parked for the player's answer -- and
travels as the protocol's special input, so `save` in a browser
tab writes a real Quetzal file beside the story; and the player's
half-typed command rides every event, so a timer printing
mid-word no longer eats it.

New in `1.8`, the Z-Machine joins: the reads learned the same
standing-down the selects learned -- the whole post-input tail
parked, lines and keystrokes and even the §15 timer's interrupts
delivered from outside -- and the §8 screen model feeds the same
machine-neutral serializer the Glk tree feeds: the upper window
and the status line travel as the protocol's grid, the lower
window as its flowing buffer, the styles in protocol dress. So
`--glkote` and `--web` now speak both machines: Zork I's inverse
status bar updates one changed row at a time, Bronze plays in a
browser tab wearing its own title, and the one refusal left is
honest -- the Version 6 stage stays at the painted glasses.

New in `1.9`, the desktop shell arrives: a
[Tauri](https://tauri.app/) webview wearing the same GlkOte
display, driving `voxam --glkote` down a pipe -- native menus for
opening and restarting, the Story menu claiming a §11.1.3
platform and the Tandy bit, the Display menu dressing the page in
type, size, ink, and measure, and every story that can be named
wearing its Babel title on the bar. Its installers ride the
GitHub release beside the wheel, three platforms, one version
stamped everywhere. And the displays kept their honesty: the
protocol grid wears its margins so status rows draw whole, the
pygame glass presents on the frame's own cadence -- Zugzwang's
chessboard, near a thousand writes a turn, snaps into place --
and the browser tab wears the machine's own icon. The road to
`2.0` runs through pictures and saves in the shell.

The full ledger -- what plays, what is certified, what remains --
lives in [STATUS.md](STATUS.md).

## Installation

VΘXΔM requires Python 3.12 or later.

```bash
pip install voxam
```

or, as an isolated tool:

```bash
pipx install voxam        # or: uv tool install voxam
```

The painted screen frontend rides in the `screen` extra, the
pygame window in the `graphics` extra, and sampled-sound playback
in the `sound` extra beside them:

```bash
pip install "voxam[screen,graphics,sound]"    # or: uv tool install "voxam[screen,graphics,sound]"
```

On Windows and macOS the sound extra is self-contained; on Linux,
PortAudio comes from the distribution (`apt install libportaudio2`
or the local equivalent). Without the extras, VΘXΔM plays as a
plain text stream -- every game still works; the status line
simply stays imaginary, and the sound games play in the conforming
silence they were shipped to accept.

VΘXΔM ships no story files. Bring your own: the
[IF Archive](https://ifarchive.org/) hosts thousands of freely
available games, and story files you own from commercial collections
work as-is.

## Playing stories

Point VΘXΔM at a story file and play at the terminal:

```bash
voxam path/to/story.z3
```

At a terminal with the `screen` extra installed, the painted
frontend takes over automatically -- status line, windows, menus,
real-time input. Pass `--plain` to keep the classic stream
instead; pipes and scripted replays always use the stream, which
is what keeps recordings deterministic. And `--graphics` opens
the pygame window -- the home of the Version 6 games, and a fine
roomy home for the earlier ones too. `--zoom` sets how much of
the desktop it takes (0.85 by default; `--zoom 0` keeps the
classic compact 80 by 24).

Glulx stories play the same way: a `.ulx` file or a packaged
`.gblorb` is recognized by its own magic, and at a real terminal
it earns the painted glass -- the Glk window tree drawn across
the whole screen, status grids in place, buffer text wrapping
behind a `[MORE]` pause, styles in terminal dress, and the
gblorb's AIFF sounds playing when the sound extra is installed:

```bash
voxam path/to/story.ulx
```

`--plain` keeps the classic stream, buffer text flowing as prose
and grids drawn as blocks -- and a piped session keeps it on its
own, which is exactly how the glulxercise certification drives
it. And `--graphics` opens the pygame window here too: the same
tree in a real window, the fitted faces carrying the styles, the
gblorb's sounds aboard, and a glulx badge on the frame -- plus
everything only a window can offer: graphics canvases with the
gblorb's PNG art drawn on, mouse clicks in each window's own
units, and hyperlinks in the reader's blue, selected by click.

The newest face is the browser's. `--web` serves a Glulx story to
a browser tab over the GlkOte protocol -- the display library of
Lectrote and the modern web interpreters, shipped inside the
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
speak both machines: a `.z3` through `.z8` plays beside a `.ulx`
or `.gblorb`, status line and split windows in the protocol's own
grid -- only the Version 6 stage stays at the painted glasses.

Add `--seed` to make the dice reproducible: the same seed and the
same commands produce the same session, every time.

```bash
voxam --seed 1137 path/to/story.z3
```

Blorb resources ride along automatically: a `.zblorb` story boots
from its package, and a like-named `.blb` beside a story file is
found on its own -- `--resources` names one explicitly. At a
painted terminal a packaged cover picture shows before play;
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
Treaty of Babel's own per-format rules -- the `UUID://` brand
where one is burned in, the human-readable legacy identities like
`ZCODE-88-840726` from the header numbers otherwise -- and, when
a blorb carries an iFiction record, the record's IFID first with
its title, author, and headline beside it. Unlike the Z-Machine's
own reports, this one speaks both machines:

```bash
voxam --babel path/to/story.gblorb
```

The same identities name the session itself: a game the iFiction
record or the Infocom catalog knows plays under its own title, in
the terminal's title bar and the pygame window's alike.

Deeper than the manifest, `--listing` disassembles the whole story
txd-style -- every routine with its locals, every opcode with its
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
rather than skipped -- Zork I lists its full 440 routines, exactly
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
interpreter disagrees with VΘXΔM about a story, the first
differing line of their traces is the bug -- and when a session
halts, the trace's last line is the instruction that halted it.
The two halves agree with each other too: every address a session
executes appears in the static listing, which is also how you
learn that one full walkthrough of a game may touch barely a
third of its code.

Typing `save` in a game writes a Quetzal file beside the story --
`zork1.z3` saves to `zork1.sav` -- and `restore` reads it back.
Quetzal is the standard interchange format, so saves travel between
VΘXΔM and other interpreters.

The session files live beside the story the same way. Typing
`script` in a game -- the command every Infocom manual documents
for keeping a paper log -- writes the transcript to `zork1.scr`,
opening with Infocom's own "Here begins a transcript" banner and
closing at `unscript`; the player's commands appear between the
game's text exactly as §7.1.1.1 asks, and 'Flags 2' bit 0 holds
the stream's status at every moment, however the game works it --
the §7.4 rule *A Mind Forever Voyaging* depends on. Output stream
4 records the player's commands to `zork1.cmd` as they finish,
and §10.2's input stream 1 plays such a file back, line by line
in the very format stream 4 writes, reverting to the keyboard
when the file runs dry. Nothing is created unless the game asks:
a session that never touches the streams leaves no files behind.

### Best played with

`--interpreter` is not a costume. Infocom's Version 6 games carry
genuine per-machine code paths, chosen at startup from the
header's interpreter number, and the flag picks which 1989 machine
VΘXΔM is pretending to be. Recommendations, earned from the games'
own source rather than folklore:

- ***Shogun*: the default.** Its own `DISPLAY-BORDER` routine
  draws the right decorative rail only on the IBM machine path;
  claiming `--interpreter amiga` over the IBM picture set gives a
  left-rail-only screen -- Infocom's authentic Amiga behaviour,
  whose matching art this Blorb does not carry.
- ***Zork Zero*: either, with character.** The default plays the
  classic look; `--interpreter amiga` engages §8.3's shared
  colour pair and the under-cursor colour sampling for the
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

VΘXΔM also speaks [RegTest](https://eblong.com/zarf/plotex/regtest.html),
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

During a replay, VΘXΔM listens for the parser's *refusal dialect* --
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

## Development

Working on VΘXΔM itself needs
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

The `desktop/` directory holds VΘXΔM's native shell: a
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

The shell finds `voxam` on the PATH -- `uv tool install voxam` or
`pipx install voxam` puts it there -- and says so plainly when it
cannot. Open a story from the landing page or the File menu --
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
painted glasses. (A Z-Machine story's save over the protocol
still answers honestly that it cannot: the Z machine saves
without suspending, and teaching it to wait is its own named
road.)

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
and deploying VΘXΔM, but they help during development. VΘXΔM does not
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

Building them is optional. They are useful for comparing VΘXΔM's
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

The name VΘXΔM draws from two sources of inspiration:

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
