# Voxam

An emulator and interpreter for the Z-Machine and Glulx, written in Python.

The Z-Machine is the virtual machine that Infocom designed in 1979 to run its
text adventures, and which the interactive fiction community has used ever
since. While the Z-Machine remains active for retro-style games, Glulx was
introduced in 1999 as the standard for modern, heavy-duty interactive fiction.
The goal for Voxam is to read a compiled story file for either platform and
execute it.

## Requirements

- Python 3.12 or later
- [uv](https://docs.astral.sh/uv/) for dependency and environment management

## Installation

```bash
git clone https://github.com/jeffnyman/voxam.git
cd voxam
uv sync --all-groups
```

## Development

All commands assume the environment created by `uv sync --all-groups`.

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

Because the history is machine-readable, commitizen can also derive the next
version, tag it, and update the changelog once releases begin:

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
git add entharion
git commit -m "chore(deps): update entharion submodule"
```

## License

Released under the [MIT License](LICENSE).
