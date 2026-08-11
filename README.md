<h1 align="center">
  <img src="https://raw.githubusercontent.com/jeffnyman/voxam/main/assets/voxam-title.png" alt="Voxam">
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

Voxam is developed against the real Infocom catalog. The *Zork*
trilogy, *Cutthroats*, *Deadline*, and *Seastalker* have all been played to
winning conclusions under Voxam, several of them across multiple
releases, each verified end-to-end by the acceptance harness
described below.

<p align="center">
  <img src="https://raw.githubusercontent.com/jeffnyman/voxam/main/assets/voxam-footer.png" alt="">
</p>

## Status

Version `0.x`: early, honest, and playable.

**Works today:** story file versions 1 through 3, which cover
Infocom's 1980--1985 catalog and many modern retro-style games. That
includes the full parser and object machinery, a seeded random
number generator for reproducible sessions, status line semantics,
and an acceptance-script harness for recording and replaying whole
playthroughs.

**Under construction:** version 4 support is being built
"frontier-driven" -- games are run until they name the next missing
piece. Version 4 stories boot and identify the interpreter; the
screen model (split windows, text styles) is in progress.

**Not yet:** SAVE and RESTORE, sound, timed input, versions 5 and
up, and Glulx. For recorded sessions, seeds substitute for saves:
a script replays a whole game in moments.

## Installation

Voxam requires Python 3.12 or later.

```bash
pip install voxam
```

or, as an isolated tool:

```bash
pipx install voxam        # or: uv tool install voxam
```

Voxam ships no story files. Bring your own: the
[IF Archive](https://ifarchive.org/) hosts thousands of freely
available games, and story files you own from commercial collections
work as-is.

## Playing stories

Point Voxam at a story file and play at the terminal:

```bash
voxam path/to/story.z3
```

Add `--seed` to make the dice reproducible: the same seed and the
same commands produce the same session, every time.

```bash
voxam --seed 1137 path/to/story.z3
```

## Acceptance scripts

A play session can be saved as an acceptance script and replayed:

```bash
voxam --accept some-session.accept
```

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
  an empty line.
- A line starting with three backticks is a fence: everything until
  the next fence is skipped entirely, directives included. Text
  after the backticks labels the fence, and an unclosed fence skips
  the rest of the file -- handy while working out a section that a
  seed change will invalidate, or to replay only the start of a
  longer script.
- Anything else is typed into the game exactly as written.
- When the commands run out, the session ends as if the player had
  reached end of input.

While recording a longer session, `--replay` types the script and
then leaves you at the prompt instead of ending, so a
work-in-progress script catches you up to where you left off:

```bash
voxam --replay some-session.accept
```

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

## Development

Working on Voxam itself needs
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

The code used in this project is licensed under the [MIT license](https://github.com/jeffnyman/quendor/blob/main/LICENSE).

**Note:** This license applies _only_ to the code in this repository. The original Z-Machine concept, design, and any original assets belong to their respective copyright holders.

✨ Long live the classics.
