# Contributing

Contributions are welcome! An
[issue](https://github.com/jeffnyman/voxam/issues) is the front
door, whether it carries a bug, a question, or a pull request's
opening thought, and everything below is the contributor's
setup. The project's design principles, and the internal
vocabulary the documents and commit messages lean on (the wire,
the glass, the dress, and the rest), live in
[DESIGN.md](DESIGN.md); what Voxam does is the
[README](README.md), what is enforced is
[STATUS.md](STATUS.md), and the road it took is
[HISTORY.md](HISTORY.md). Working on Voxam itself needs
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
| Type check as another platform | `uv run mypy --platform linux` |
| Build distributions | `uv build` |

## The C# port

The `csharp/` directory holds the C# port of the Z-Machine: a
class library, a console executable answering `--accept` the way
the Python does, and a test project. It needs the .NET SDK named
in `csharp/global.json` and nothing else; the Python toolchain
never sees it and the wheel never carries it. Its gate is the
Python's, translated: warnings are errors, formatting is checked,
and the tests enforce 100% line and branch coverage through
coverlet's threshold.

| Task | Command |
| --- | --- |
| Build | `dotnet build csharp -c Release` |
| Run the tests at the coverage threshold | `dotnet test csharp -c Release` |
| Format | `dotnet format csharp` |
| Check formatting only | `dotnet format csharp --verify-no-changes` |
| Publish a native executable | `dotnet publish csharp/Voxam.Cli -c Release -o csharp/publish` |
| Certify against the reference | `uv run python tools/sweep-corpus.py record port --voxam csharp/publish/voxam` |
| Play at the terminal | `csharp/publish/voxam story.z5` (`--plain` for the transcript stream) |

The port's version lives in `csharp/Directory.Build.props`, which
`cz bump` moves with the rest, so `voxam --version` names the same
release as the Python and adds `(native)` after it.

The port is certified the way a release is: a sweep of the corpus
under the Python, a sweep under the native executable, and a
comparison of the two by transcript digest. CI does the smallest
version of that on every push, replaying Zork I under both and
requiring the bytes to agree. The Python is the reference and
stays so: a difference between the two is a question for the
port, not the Python, unless the Python is shown wrong against
the Standard.

## The desktop shell

The `desktop/` directory holds Voxam's native shell, a
[Tauri](https://tauri.app/) webview driving a spawned
`voxam --glkote` down a pipe; what it does for a player is in
the [README](README.md). It's not part of the Python package:
the wheel never carries it, and the Python toolchain never sees
it, but it wears the same version, and every release tag builds
its installers (Windows, macOS, Linux; unsigned) and attaches
them to the GitHub release beside the wheel. Building it locally
needs Rust (with the platform's native toolchain) and Node:

```bash
cd desktop
npm install          # fetches the Tauri CLI
npx tauri dev        # run it; the first compile takes minutes
npx tauri build      # produce the platform installer
```

Two facts worth knowing when changing the shell's display. First,
part of `desktop/ui/` is vendored copies rather than originals:
`glkote.js`, `glkote.css`, `jquery-1.12.4.min.js`, `waiting.gif`,
`voxam-audio.js`, `voxam-prefs.js`, `voxam-card.js`, the bundled
`.woff2` faces, and `LICENSE-glkote.txt` are the same files the
Python package ships in `src/voxam/pages/`, copied in so the
shell needs no network and no build step. A test holds them
byte-identical, so a copy that drifts fails the gate rather than
diverging quietly. When the originals
change, re-copy them (`index.html` and `shell.js` are the shell's
own and live only here). Second, a built shell *embeds* `ui/` at compile time:
`npx tauri dev` serves the directory live, so edits show on
reload, but an installer or a release binary keeps serving
whatever was embedded when it was built. After any `ui/` change,
rebuild (`npx tauri build`, or `cargo build --release` inside
`src-tauri/` for the bare executable) before trusting what an
installed shell shows; a stale embed looks exactly like your
change not working.

## Project conventions

- **Layout.** Source lives under `src/voxam`, tests under `tests/`. The `src`
  layout ensures tests exercise the installed package rather than the working
  directory. Developer scripts live under `tools/`: they import `voxam` and
  are held to the same lint and typing bar, but they never ship, and the
  release audit fails the build if one ever reaches an artifact.
- **Typing.** `mypy` runs in strict mode over `src`, `tests`, and `tools`, and
  the package ships a `py.typed` marker so downstream consumers get its types.
  One caution if you touch a platform branch: `mypy` narrows `sys.platform`
  to the machine it's running on, so the other platform's arm reads as
  dead code and the local gate can't see the error CI will. Check it with
  `uv run mypy --platform linux` before pushing. The project keeps its one
  such branch isolated in `src/voxam/winkeys.py`, which holds the platform
  test and nothing else, for exactly this reason.
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
  rather than in CI, and they double as the project's archaeology notebook,
  annotating where the games' published walkthroughs go wrong.

  They are also the project's widest regression net, and
  `tools/sweep-corpus.py` is what runs them. A sweep replays every
  recording into transcripts with a manifest of timings; two sweeps
  compare, on RegTest's exit codes, so a release can be held against the
  one before it:

  ```bash
  uv run python tools/sweep-corpus.py record before --root ../voxam-2.6.1
  uv run python tools/sweep-corpus.py record after
  uv run python tools/sweep-corpus.py compare before after
  ```

  `--root` sweeps another checkout using that checkout's own source, so
  the tool need exist in only one of the two. A recording that times out
  keeps what it earned and is marked incomplete: a truncated transcript
  is excluded from the verdict rather than counted as a difference.
  Bronze is the one recording that needs `--timeout` raised on purpose.

## Pre-commit hooks

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

## Commit messages

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

## The instruments

Voxam is developed against real games, and these are the tools it
is developed with. None of them is needed to play a story;
[PLAYING.md](PLAYING.md) covers that.

### Acceptance scripts

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
and the rare input the script grammar can't spell exactly draws a
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
  special keys, one line per press, which is how a recording drives
  *Beyond Zork*'s menus and builds its characters. A token naming
  no known key fails loudly, and the `> <up>` prompt form stays a
  literal command for a game that really wants angle brackets.
- A line starting with three backticks is a fence: everything until
  the next fence is skipped entirely, directives included. Text
  after the backticks labels the fence, and an unclosed fence skips
  the rest of the file. This is handy while working out a section that
  a seed change will invalidate, or to replay only the start of a
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
interactive fiction, and speaks it twice over. A RegTest script
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
implementations and holds to the same verdict. Plus an *Arthur*
script only the built-in runner can follow, since v6's inline
keystroke prompts defeat pipe-based prompt framing. A seed on the
script's `** interpreter:` line makes the whole suite
deterministic under both runners, which is not a thing most
interpreters can offer RegTest at all.

### Refusal warnings

During a replay, Voxam listens for the parser's *refusal dialect*:
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

### Measuring the machine

`--benchmark` rides any session and reports the machine's own pace
when it ends:

```bash
voxam --accept acceptance/zork1-r88-s840726.accept --benchmark
```

```text
voxam: 312,349 instructions in 0.5s (585,872 per second)
```

The instruction count comes first because it's the honest half: a
seeded session executes exactly the same instructions every time,
on every machine, so two runs are comparable even when the seconds
are not. The seconds and the rate are what an optimization has to
move. A recording makes the fixed workload the measurement needs,
so the corpus doubles as the bench.

It rides the Z-Machine and Glulx at the blocking faces. The
Å-machine refuses it by name, alongside the acceptance driver and
the tracer, and the wire faces are a later road.

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
back, and flags any response spoken in the refusal dialect,
which turns a hundred-command stretch into a one-screen diagnosis.
`attempt` replays the script and tries a variant tail
(`drop_last` re-tries the ending without editing the file);
`run` takes the whole command list for surgery the prefix can't
express, such as inserting turns mid-timeline; and the returned
`machine` is left standing for post-mortem reads of globals,
object parents, or the clock. Every run boots fresh from the seed,
so no experiment can contaminate another.

Probe scripts themselves are throwaways: write one in a scratch
file, find the answer, record the fix in the `.accept` annotations,
and delete it. The harness is the part worth keeping.

### The filmstrip

Any recorded walk can be photographed. `--shots DIR` rides
`--accept`: the script replays at the real pygame glass --
driven, so no `[MORE]` waits on a player -- and every settled
turn saves a numbered frame, the boot screen first and the final
response last. Add `--browser` (a path, or bare to find one on
your machine) and the same walk shoots the web display instead:
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
diverge at another. The strip keeps every frame it earned and
says where it broke, and strips compare face-to-same-face.

## Reference Material (optional)

An `entharion` submodule holds the specifications and story files this
project is developed against. These are not required as part of building
and deploying Voxam, but they help during development. Voxam does not
depend on anything under `entharion/`. It's not needed to install the
project and CI doesn't fetch it. Git leaves submodules empty unless
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
git submodule update --init --recursive entharion
git commit -m "chore(deps): update entharion submodule"
```

The `git add` comes second on purpose, not last. A plain
`git submodule update` checks out whatever commit the superproject's
index records, so with the new pointer still unstaged the third
command would quietly put entharion back where it started and the
pin would never move at all.

The third command carries no `--remote` on purpose either: it aligns
entharion's own vendored submodules to the pointers the new pin
records. It's a no-op when the update only added files, and the
cure when a vendor pointer moved: with `--remote` it would instead
drag those checkouts past their recorded pointers and leave the
submodule looking dirty.

### Building the Reference Tools

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
