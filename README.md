<h1 align="center">
  <img src="https://raw.githubusercontent.com/jeffnyman/voxam/main/assets/voxam-title.png" alt="VΘXΔM">
</h1>

<p align="center">
  <em>A Specification-Accurate Z-Machine Implementation</em><br />
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
  <a href="https://github.com/jeffnyman/voxam/actions/workflows/ci.yml"><img src="https://github.com/jeffnyman/voxam/actions/workflows/ci.yml/badge.svg" alt="CI status"></a>
  <a href="https://conventionalcommits.org"><img src="https://img.shields.io/badge/Conventional%20Commits-1.0.0-green.svg" alt="Conventional Commits: 1.0.0"></a>
</p>

<p align="center">
  <a href="https://vscode.dev/github/jeffnyman/voxam"><img alt="Open with vscode" src="https://img.shields.io/static/v1?logo=visualstudiocode&label=&message=Open%20in%20Visual%20Studio%20Code&labelColor=2c2c32&color=007acc&logoColor=007acc"></a>
</p>

An interpreter for the Z-Machine, written in Python, with Glulx to
follow.

The Z-Machine is the virtual machine Infocom designed in 1979 to run
its text adventures, and which the interactive fiction community has
used ever since. Voxam reads a compiled story file and executes it,
with two guiding commitments: fidelity to the
[Z-Machine Standard](https://jeffnyman.github.io/z-machine-standard/)
-- every rule the interpreter enforces cites the section it came from
-- and reproducibility, so that a recorded play session replays
identically, forever.

VΘXΔM is developed against real games. The *Zork* trilogy,
*Cutthroats*, *Deadline*, *Seastalker*, *Trinity*, *A Mind Forever
Voyaging*, *The Hitchhiker's Guide to the Galaxy*, and -- filed in
triplicate, blood pressure rising -- *Bureaucracy* have all been
played to winning conclusions under VΘXΔM, several across multiple
releases and several to perfect scores, alongside modern classics
from *Colossal Cave* to the IF Comp winner *All Roads*. The
Version 6 era has opened: *Arthur: The Quest for Excalibur* plays
to its ending -- the sword drawn from the stone at the rank of
king, every chivalry point earned -- in what is as far as we know
the first seeded, replayable *Arthur* session anywhere. The sound
era is certified too: *The Lurking Horror* and *Sherlock: The
Riddle of the Crown Jewels* both play to perfect scores -- recorded
in the conforming quiet, and now heard aloud at a painted terminal
with the sound extra installed -- and *Beyond
Zork*'s first act is on the record, its hero built point by point
on the arrow-driven character screen, in what is as far as we know
the first seeded, replayable *Beyond Zork* session anywhere. And
the era plays illustrated now: *Arthur*, *Shogun*, and *Zork
Zero* render their pictures, palettes, and window layouts in a
real graphics window, held to the Standard's §8.8 screen model.
The late formats have opened as well: version 8 is held to CZECH's
exact tallies in continuous integration, *Jigsaw* -- Graham
Nelson's epic of the twentieth century -- is recorded through its
first two chapters, from the Sarajevo assassination to the
Titanic's rescue summoned in real Morse code, and Emily Short's
*Bronze* plays to its winning ending -- the King restored, his
servants freed -- in a session adapted command by command from a
surviving Release 12 transcript to the canonical Release 11 story
file, its annotations recording every place the two releases
disagree. Even version 7, the format Infocom never shipped, has a
seeded recording, as far as we know the first anywhere. *Ballyhoo*
joins the perfect scores -- 200 of 200, the circus saved, and
three of its cruellest hidden state-gates excavated from Infocom's
own source and annotated where every published walkthrough omits
them. And Jon Ingold's *The Mulldoon Legacy* -- a game that
teases players who act on knowledge their character hasn't earned
("Playing a restored game are we?") -- is recorded deep into its
museum, the first of the fortune teller's visions complete: a
verified route through a game built to resist secondhand play.
Thirty-four recordings verify those sessions end-to-end with the
acceptance harness described below, and their annotations double as
an archaeology of where the games' published walkthroughs go wrong.

<p align="center">
  <img src="https://raw.githubusercontent.com/jeffnyman/voxam/main/assets/voxam-footer.png" alt="">
</p>

## Status

Version `0.x`: early, honest, and playable.

**Works today:** story file versions 1 through 8 -- Infocom's
whole catalog, the modern Inform and PunyInform games built on
versions 5 and 8, and the rarely-sighted version 7 besides --
including version 6, run against Infocom's own ZIPTEST
checker and played through *Arthur*: the eight-window §8.8 ledger
with its eighteen properties per window, user stacks, the
formatted-text stream behind print_form, and the v6 cursor forms.
At the pygame window the whole era renders illustrated -- the
pictures, the palettes, and all eight windows for real -- while on
a character glass a version 6 game still plays as flowing text,
its graphical courtesies declared unavailable in the header and
answered honestly when it asks anyway. Underneath all of it:
the full parser and object machinery -- with code above the
static-memory line decoded once and cached (§1.1), which is what
lets an Inform 7 game spend three hundred thousand instructions on
a single turn without the player noticing -- a seeded random number
generator for reproducible sessions, the
screen model (split windows, single-keystroke input), custom
alphabet tables, the accented extra characters, and the Standard
1.1 Unicode extras -- custom translation tables and print_unicode
-- so the interpreter declares revision 1.1 in every header it
touches. SAVE, RESTORE, and RESTART speak the standard
[Quetzal](https://jeffnyman.github.io/z-machine-standard/quetzal.html)
format, auxiliary files cover the games that save fragments of
themselves, UNDO is multi-level, and an acceptance-script harness
records, replays, and probes whole playthroughs.

At a real terminal, VΘXΔM paints the screen: the blessed frontend
(an optional extra, named for both its temperament and the
[blessed](https://pypi.org/project/blessed/) package behind it)
renders the §8 screen model live -- a reverse-video status line
that holds the top of the screen, split windows, character-input
menus like Zork's InvisiClues browsed by single keypresses, bold,
italic, and the §8.3.1 colours, forwarded to games that ask for
them with the header declaring the offer honestly. Font 3 -- §16's
character graphics -- paints as Unicode: box-drawing and blocks
for *Beyond Zork*'s on-screen map, its stat gauges as
eighth-blocks, and the rune alphabet as genuine futhorc runes,
each glyph derived from the Standard's own bitmaps. The painter
owns the keyboard too: line input is read raw and echoed through
the screen model, so nothing but the painter ever writes to the
glass, and the cursor keys reach the games that listen for them
(§3.8.4) -- which is how *Beyond Zork*'s menus are driven. At a
prompt those same keys are a full line editor: left and right move
within the line, edits land at the cursor, and up and down walk
the session's command history, shell-style -- at the terminal and
the pygame window alike, with single-keystroke reads still passing
the arrows through to the games that claim them. Timed
input runs on the real wall clock there, so a game like Z-Tornado
plays in genuine real time -- and so do timed line reads: while
you think at *Border Zone*'s prompt, its espionage clock ticks on
without you, the read's interrupt fired every interval exactly as
§15 asks, with your half-typed command surviving each tick.
And a screenful of unread text waits
behind a reverse-video [MORE] until a key arrives -- at the
terminal and the pygame window alike, for every story version --
so a game's longest speech never outruns its reader.
The architecture keeps a strict split
between a pure screen model -- a grid of attributed cells held to
§8 by golden-grid tests -- and a thin painter that only repaints
what changed, so the screen is as testable as the machine beneath
it.

VΘXΔM reads [Blorb](https://jeffnyman.github.io/z-machine-standard/blorb.html)
resource files as well: a `.zblorb` packaged story boots directly,
and a sidecar `.blb` found beside a story by name announces its
pictures and sounds at the banner. A cover picture -- *Beyond
Zork* ships one -- is shown before play at a painted terminal,
scaled into half-block cells on any colour terminal or drawn at
real resolution with `--pixels`, decoded by a pure-stdlib PNG
reader. The pixels path asks the terminal first: one that
declares sixel graphics also reports its cell size, so the art
magnifies to the glass as it actually measures, and one that
never learned sixel quietly gets the half-block painting instead
of escape garbage. Art is a courtesy, never a gate: a
cover VΘXΔM cannot draw earns a note and the story plays on. And
VΘXΔM can claim any classic machine identity (`--interpreter
amiga`, or the legendary Tandy bit via `--tandy`), which some
early games answer with altered text and *Beyond Zork* answers
with its whole screen-model personality (§11.1.3, §16).

And at a pygame window -- the `graphics` extra, opened with
`--graphics` -- the Version 6 era plays illustrated. The §8.8
screen is real there: eight placeable windows on one pixel grid,
text at true pixel positions, margins that wrap prose around scene
art, and a [MORE] that pauses a screenful in the window's own
colours and cleans up after itself. Blorb pictures draw at the
sizes the Reso chunk scales them to, transparency lets the chrome
layer over the scenes, and the adaptive palettes recolour that
chrome as scenes change -- both the Standard's live APal dance and
Bocfel's pre-baked BPal replacements, which is how *Zork Zero*'s
plaques keep their gold. Even §8.3.1's strangest colour is
honoured: colour -1 samples the pixel under the cursor, which is
how *Zork Zero* prints readable text over its parchment under the
Amiga identity. The window takes its share of the desktop --
`--zoom`, 85% by default -- by growing the grid rather than the
type: more rows and columns of the same modest cell, the way
Infocom's own interpreters used a big monitor, with `--zoom 0`
keeping the classic 80 by 24. It even wears its story's version as
its icon, z1 through z8. *Arthur*, *Shogun*, and *Zork Zero* all
play illustrated, and the modern Inform- and PunyInform-compiled
version 6 games render clean beside them. For the curious: point
the `VOXAM_SNAPSHOT` environment variable at a file path and every
presented frame is also saved there -- the diagnostic witness this
whole era was debugged with.

And the machine has a voice. With the `sound` extra installed, a
painted session plays the sampled sounds its Blorb carries, in the
background while play goes on (§9.4): volumes and repeat counts
decoded from the opcode, a Version 3 game's looping taken from the
Blorb's own Loop chunk -- which is how *The Lurking Horror*'s rats
hum until the valve stops them -- and the end-of-sound routines
*Sherlock* leans on called when a sound truly finishes, never for
one stopped or replaced. Even the Standard's §9 war stories are
honoured: *The Lurking Horror* fires several sounds in one game
round, trusting the interpreter to be as slow as Infocom's Amiga
was, so a new sound waits for the current one to finish a cycle,
exactly as the Standard's remarks prescribe -- and its famously
bugged sound requests are pardoned by name. Sound is a courtesy on
the same terms as art: a missing package, a missing PortAudio
library, or a missing audio device each mean a quieter game, never
a broken one, with the header honestly saying so.

Input runs deeper than lines. A scripted line reaches
single-keystroke reads one character at a time, which is how
cursor-driven forms -- up to and including Bureaucracy's Software
Licence Application -- fill in correctly from a recording. In
recorded sessions timed input runs on a virtual clock instead: the
"patient typist" lets one interrupt interval elapse before each
input arrives, which keeps timed games replayable while recordings
stay deterministic. Sampled sounds in recorded sessions likewise
still pass in the conforming silence of an interpreter that
declares none -- *The Lurking Horror* and *Sherlock* were both
shipped to accept exactly that -- because a replay must land on
the same bytes everywhere, speakers or no speakers.

VΘXΔM is verified against the community's interpreter test suites:
CZECH (versions 3, 4, 5, and 8 -- the last certifying the modern
Inform format, held to its exact tallies in continuous
integration), Praxix -- its Standard 1.1 section included --
TerpEtude, and Strict Z Test all pass clean; Infocom's own ZIPTEST
opened the version 6 era and named its frontiers one opcode at a
time. Every remaining gap halts loudly with a citation instead of
guessing.

**Not yet:** mouse input -- *Zork Zero*'s mouse minigames want
real clicks, and a planned `<click y x>` recording token will keep
those sessions replayable when they come; *Journey*, the last of
the graphical four, not yet certified; the Blorb music formats,
MOD and OGG (the entire vendored Infocom sound catalog is sampled
AIFF and needs neither); and Glulx. For recorded sessions, seeds
substitute for saves: a script replays a whole game in moments.

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

Typing `save` in a game writes a Quetzal file beside the story --
`zork1.z3` saves to `zork1.sav` -- and `restore` reads it back.
Quetzal is the standard interchange format, so saves travel between
VΘXΔM and other interpreters.

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
git add entharion
git commit -m "chore(deps): update entharion submodule"
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
