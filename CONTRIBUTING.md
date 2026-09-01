# Contributing

Contributions are welcome -- an
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

## The desktop shell

The `desktop/` directory holds Voxam's native shell, a
[Tauri](https://tauri.app/) webview driving a spawned
`voxam --glkote` down a pipe; what it does for a player is in
the [README](README.md). It is not part of the Python package:
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

## Project conventions

- **Layout.** Source lives under `src/voxam`, tests under `tests/`. The `src`
  layout ensures tests exercise the installed package rather than the working
  directory.
- **Typing.** `mypy` runs in strict mode over both `src` and `tests`, and the
  package ships a `py.typed` marker so downstream consumers get its types.
  One caution if you touch a platform branch: `mypy` narrows `sys.platform`
  to the machine it is running on, so the other platform's arm reads as
  dead code and the local gate cannot see the error CI will. Check it with
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
  rather than in CI -- and they double as the project's archaeology notebook,
  annotating where the games' published walkthroughs go wrong.

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

## Reference Material (optional)

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
records. It is a no-op when the update only added files, and the
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
