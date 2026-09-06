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
  <a href="CONTRIBUTING.md"><img src="https://img.shields.io/badge/contributions-welcome-brightgreen.svg" alt="Contributions welcome"></a>
</p>

<p align="center">
  If you find any of this useful, consider leaving a ⭐️ for the repo.
</p>

<p align="center">
  <a href="SCREENSHOTS.md"><em>See what it looks like</em></a>
  &nbsp;&nbsp;·&nbsp;&nbsp;
  <a href="#-the-name"><em>What does Voxam mean?</em></a>
</p>

---

An interpreter for the Z-Machine, for Glulx, and for the
Å-machine, written in Python.

Three virtual machines, spanning the whole history of
interactive fiction:

- **The Z-Machine** is the virtual machine Infocom designed in
  1979 to run its text adventures, and which the community has
  used ever since. This is the home of everything from *Zork* to the
  modern Inform and PunyInform games. This is also the target of
  [Arcturus](https://github.com/8bitgames/arcturus), a modern
  programming language and compiler designed for writing
  interactive fiction that compiles down to efficient Infocom
  Z-Machine story files.
- **Glulx** is the Z-Machine's successor, built to shed the size
  limits of the Z-Machine, and the target of today's Inform.
- **The Å-machine** is a specialized virtual machine created by
  Linus Åkesson to run interactive fiction written in his
  [Dialog](https://linusakesson.net/dialog/) programming
  language, and which is now community maintained.

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
pure keystrokes. Forty-five recordings verify those sessions
end-to-end, their annotations doubling as an archaeology of where
the games' published walkthroughs go wrong. Glulx joins
them: *Adventure* answers at the terminal, and glulxercise says
"All tests passed." The Å-machine arrives certified harder still:
every test battery its reference implementation ships replays
under Voxam byte-identical to the reference engine's own
transcripts. *Miss Gosling's Last Case* walked three hundred
fifty-one commands to its finale.

The full ledger -- the current release, what plays, what's
certified, and what remains -- lives in [STATUS.md](STATUS.md);
the road here, told era by era, is [HISTORY.md](HISTORY.md);
the thinking underneath it all, principles and vocabulary alike,
is [DESIGN.md](DESIGN.md); and the setup for working on Voxam
itself is [CONTRIBUTING.md](CONTRIBUTING.md).

<p align="center">
  <img src="https://raw.githubusercontent.com/jeffnyman/voxam/main/assets/voxam-footer.png" alt="">
</p>

## How to Play

One command, several faces: every one of them speaks all three
machines, and a story file is all any of them needs:

- **At the terminal.** `voxam story.z5` runs with the `screen`
  extra installed, the painted display takes over: status line,
  windows, menus, real time. `--plain` keeps the classic text
  stream.
- **In a window.** `voxam --graphics story.ulx` shows a pygame
  window: the illustrated home of the Version 6 games, Glulx's
  canvases and mouse, and a fine roomy home for everything else.
- **In a browser.** `voxam --web story.gblorb` is a GlkOte tab
  on your own machine, in your system's own light or whichever
  you pick, art and covers inlined, saves written beside the
  story.
- **As a desktop app.** Grab the Voxam installer for your
  platform from the
  [latest release](https://github.com/jeffnyman/voxam/releases/latest)
  (Windows, macOS, Linux; unsigned, so expect the usual
  first-run nudges). The shell drives the `voxam` command, so
  install that first: `pipx install voxam` or
  `uv tool install voxam` puts it on the PATH.
- **On a wire.** `voxam --glkote story.z8` runs the whole session
  as JSON stanzas on stdin and stdout, the seam any
  GlkOte-speaking host drives down a pipe.

Installation of the app itself is one line (see
[Installation](#installation)), and the flags' full stories live
in [PLAYING.md](PLAYING.md).

## Installation

Voxam requires Python 3.12 or later, and it's an application
rather than a library, so it installs like one: in its own
environment, with only the `voxam` command placed on your PATH.
Nothing lands in your system Python.

```bash
pipx install voxam
```

If your Python is uv managed:

```bash
uv tool install voxam
```

Either way the story files, the saves, and the transcripts are
ordinary files in ordinary places, and uninstalling takes the
whole thing back out again.

To try it without installing anything at all, `uvx` fetches the
package to its cache, runs it, and leaves your PATH untouched:

```bash
uvx voxam story.z5
```

### The extras, and what they cost

Voxam's core has no dependencies whatsoever. The interpreter, the
story formats and the wire are standard-library Python: it
decodes its own PNGs, writes its own savefiles, and serves its
own pages. So an install of Voxam alone brings in Voxam alone.

Three optional extras buy presentation, never correctness:
`screen` for the painted terminal, `graphics` for the pygame
window, and `sound` for sampled audio. They do have dependencies
of their own -- blessed, pygame-ce, sounddevice -- and under
either installer above those land in Voxam's own environment
beside it, still nowhere near your system Python:

```bash
pipx install "voxam[screen,graphics,sound]"
```

```bash
uv tool install "voxam[screen,graphics,sound]"
```

`uvx` needs the extras named before the command:

```bash
uvx --from "voxam[screen]" voxam story.z5
```

The one genuinely system-level requirement anywhere is PortAudio,
which the sound extra needs on Linux (`apt install libportaudio2`
or the local equivalent) because it's a C library rather than a
Python package. On Windows and macOS the sound extra is
self-contained.

Without any of the extras Voxam plays as a plain text stream.
Every game still works; the status line simply stays imaginary,
and the sound games play in the conforming silence they were
shipped to accept.

Voxam ships no story files. Bring your own: the
[IF Archive](https://ifarchive.org/) hosts hundreds of freely
available games, and story files you own from commercial collections
work as-is.

## Playing stories

The faces above in full, and everything else a session can do:
[PLAYING.md](PLAYING.md). Which 1980s machine to tell a game it
is running on, and the games that genuinely play differently for
it; seeds and repeatable sessions; saves, transcripts, and the
streams; Blorb resources and cover art; and the flags that read a
story file apart rather than run it.

## Development

The contributor's setup lives in
[CONTRIBUTING.md](CONTRIBUTING.md): the environment and the task
table, the project conventions, the pre-commit hooks and the
commit message rules, the instruments Voxam is developed with
(acceptance recordings, RegTest suites, the benchmark, the probe,
and the filmstrip), and the optional reference material.

### The C# port

`csharp/` holds a second implementation of the Z-Machine, in C#,
built to ship as one native executable through NativeAOT. It
plays every Z-code story in the acceptance corpus identically to
the Python above, which stays the reference, and it plays at a
terminal: `voxam story.z5` from the native `voxam` is the painted
terminal, status line and all. Beside it is `Voxam`, a desktop
window on [Avalonia](https://avaloniaui.net/) that plays the same
stories on the same glass, opened from its menu or named on the
command line, with the bundled font, four themes and five sizes of
type it remembers between sessions, the §16 character graphics
drawn from their own pixels, and saved games going wherever the
platform's own file picker is told. A Version 6
story plays on a stage that places its windows in units, the way
Arthur and Shogun expect, with its Blorb's art measured, declared
and drawn. A Glulx story plays too, over a plain
stream: the machine, the whole of its Glk library, and a display the
acceptance harness can drive, which is enough for every acceptance
recording in the corpus to come back byte-identical to the
reference. At a real terminal it gets the
painted console, status line and wrapped text and a pause prompt,
the same shape the Z-Machine's own painter has, and in the desktop
window it plays on the same glass, drawing its pictures and hearing
the pointer.
It can also say what a
story is: `voxam --babel story.z5` reports the identity the Treaty
of Babel gives it, along with the title, author and headline where
the file carries an iFiction record, and the name Infocom's own
catalog gives the games that shipped before there was a treaty.
It ships as a beta from `2.8.0` on. Each
release attaches one archive per platform, named
`voxam-VERSION-windows-x64.zip`, `voxam-VERSION-macos-universal.zip`
and `voxam-VERSION-linux-x64.tar.gz`, holding the window, the console
beneath it, and a note about the first run: they are unsigned, like
the shell's installers. Nothing installs and nothing is required,
not even Python, so trying the port costs an unzip and undoing it
costs a delete.
Where it stands, and where it is going, is in
[STATUS.md](STATUS.md); how to build and certify it is in
[CONTRIBUTING.md](CONTRIBUTING.md).

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

**Note:** This license applies _only_ to Voxam's own code. Two other things travel with it, and neither is covered by it.

**The designs Voxam implements** belong to the people who made them. The Z-Machine is Infocom's, and the Standard documenting it is Graham Nelson's work with the community's; Glulx, Glk and Blorb are Andrew Plotkin's; the Å-machine and the Dialog language it serves are Linus Åkesson's; arc_image is Stefan Vogt's; the Treaty of Babel is the Interactive Fiction Technology Foundation's. Implementing a specification is not owning it, and none of these belong to this project.

**The code Voxam redistributes** keeps its own license. The browser face and the desktop shell both ship Andrew Plotkin's GlkOte display (`glkote.js`, `glkote.css`, `waiting.gif`) and jQuery. Both are MIT, and both licenses travel in the package beside the files they cover, as `LICENSE-glkote.txt` and `LICENSE-jquery.txt`. jQuery, the stylesheet, and the spinner ride unchanged; `glkote.js` is a modified copy, and every change to it is marked `VOXAM:` in place, so the additions are legible against the original: the sound and color dialects, the Version 6 stage with its scaled canvases and emplaced editor, and the support tokens that grant them. Two typefaces travel with them: Voxam Serif is Charis SIL under the SIL Open Font License, and Voxam Mono is Go Mono under the Go project's BSD license. Both are subset to the characters a story can print, and renamed as the OFL requires of a modified copy: their licenses ride beside them too, as `LICENSE-voxam-serif.txt` and `LICENSE-voxam-mono.txt`.

Story files belong to their authors. Voxam ships none, and reads yours without claiming anything about them.

✨ Long live the classics.
