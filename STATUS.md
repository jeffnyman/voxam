# Voxam Status

The claims ledger: what plays, what is certified, and what
remains. The short version lives in the [README](README.md), and
the road here, told era by era, is [HISTORY.md](HISTORY.md);
this is the long one, kept with the same rule the code keeps --
nothing below is promised, only enforced.

## The current release

Version `2.7`: the reader dresses the story. An interpreter has
no business deciding what a story is set in either, and for most
of Voxam's life the browser tab and the desktop shell decided
exactly that: one face, one size, one measure, black on the
browser's own white. Now the reader decides, through one
preferences panel that both faces wear.

The panel is written once and copied to both, which is the point
of it. It offers the type: two faces that travel with the package
so a story reads the same on every machine (Voxam Serif, which
is Charis SIL, and Voxam Mono, which is Go Mono, each subset to
what a story can print and renamed as the Open Font License asks
of a modified copy), three families from whatever the machine
happens to have, and any face on the system by name, checked
against the system before it is offered rather than falling back
in silence. It offers the measure in characters, which is what a
measure has always meant, the leading, and the letter and word
spacing. It offers the ink: five named palettes, including the
DOS Infocom blue WinFrotz still opens in, and eight surfaces a
reader can set to anything at all: the story's paper and ink,
the status bar and its text, reverse video's own pair, links, and
the surround. And it offers the way back, one Reset, because a
panel that can reach every corner needs a door out of them.

Under it, a divergence closed. The shell and the tab render the
same GlkOte display but had grown two colour models, and the
shell was still wearing GlkOte's own. Making them share one set
of custom properties fixed four defects that had been invisible
only because nobody had put the two faces side by side.

The third machine came to the glass. The Å-machine had played at
the terminal and down the wire since `2.3`; it plays in the
pygame window now, wearing the same voice ladder the other two
wear, and it carries its own mark in the window's title bar and
the browser's tab: an Å over a D, for the machine and for the
language that compiles to it. A story's embedded
pictures reach both faces: the URLS table names a resource, a FILE
chunk holds it, and the picture rides inside the update as its
own bytes, so nothing is fetched from anywhere. An Å-machine
resource naming somebody's network is declined rather than
reached for.

And the story's own card was put where it belongs. It had been
told as the page's opening text, which stood a publisher's blurb
among the game's first sentences where no reader asked for it,
and a parser bug made it worse by reading a record file's own
indentation as line breaks, so Zork I's bibliography arrived
double-spaced down the page. The parser was wrong and is fixed.
The placement was wrong too: the card now rides the sidecar as
plain facts, read once and rested, and the browser tab and the
desktop shell build the same little window over it from the same
shared script, behind a button beside the preferences opener. All
three machines answer it alike, because a story's bibliography
belongs to its file rather than to any machine's registers. This
is the sidecar's first consumer, an era after it was designed and
served.

The standing claims beneath it, each enforced in continuous
integration rather than promised: the Z-Machine is complete --
every opcode §14 defines, all eight story file versions, version
6 illustrated -- and held to the community's checkers at their
exact tallies; Full Glulx is declared, glulxercise entire, with
an exclusion ledger of exactly two spec-sanctioned refusals; the
Å-machine is certified the strongest way an implementation can
be, every test battery its reference implementation ships
replaying under Voxam byte-identical to the reference engine's
own transcripts, seeded dice included, from the opcode
stress-test to a 351-command walk through a real mystery; GlkOte
is spoken from the machine's side, so the stories play at the
terminal, the pygame window, the browser, the desktop shell, and
down a stdio wire, sound and art and the Version 6 stage
included; the Treaty of Babel names every story that can be
named; and a seeded session replays identically, forever. A test
suite at 100% branch coverage holds that in continuous
integration, and forty-five recorded playthroughs hold it across
releases.

Those forty-five were replayed whole against `2.6.1` before this
release was cut, and forty-three of the forty-four they share are
byte-identical. The one difference is a typed command a commit
deliberately edited; the forty-fifth is new. That is what an era
of face work is supposed to look like from the machine's side:
nothing.

The era's own residue, named. `--benchmark` reported a flat zero
for any session that ended by running out of input rather than by
the story quitting, which is an ordinary ending for a replayed
script and the ending several recordings have; the tally lived in
a local that an exception carried away, and it is folded in from
a finally now, at no cost to the loop. Two gaps are open rather
than fixed: the filmstrip photographs a replay page of its own
rather than the served page, so it sees the display but none of
the furniture around it, which is why a card that rendered wrong
in a tab could not be caught by a picture; and the forty-five
recordings still have no runner, which is [issue
365](https://github.com/jeffnyman/voxam/issues/365).

## The played-games ledger

Voxam is developed against real games. The *Zork* trilogy,
*Cutthroats*, *Deadline*, *Seastalker*, *Trinity*, *A Mind Forever
Voyaging*, *The Hitchhiker's Guide to the Galaxy*, and -- filed in
triplicate, blood pressure rising -- *Bureaucracy* have all been
played to winning conclusions under Voxam, several across multiple
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
Even *Journey* -- Infocom's menu-driven finale, a game with no
command line at all -- replays through its opening chapter as pure
keystrokes: letters press the commands they begin with, `<space>`
walks the highlight between the party column and the character
grid, and the arrows settle which Examine is whose. Two small
witnesses joined late: Magnus Olsson's *Zugzwang* -- the endgame
whose chessboard status line, nearly a thousand writes a turn,
taught the pygame glass to share its flips -- and Jeremy Freese's
*Violet*, whose one-room writing day plays in the browser under
its own cover-art tab. And the newest formats have their
witnesses too: Stefan Vogt's *Rabenstein* plays to its ending
illustrated, the arc_image band following the story scene by
scene, and Mathbrush's *The Impossible Stairs* -- compiled from
Dialog -- replays through its menu-driven dialogue, proving the
toolchain a new generation of story files is written in. And
the third machine has its witnesses in kind: *Cloak of
Darkness* -- Roger Firth's reference game in Linus Åkesson's
own Dialog port -- plays at the terminal, in the browser, and
over the wire, its savefile written and revived mid-hook; and
Daniel Stelzer's *Miss Gosling's Last Case* walks three hundred
fifty-one commands deep, the whole mystery to its finale, with
the transcript matching the reference engine's own byte for
byte at the same seed. And Zork speaks German: a rare translated
Infocom beta is walked from the mailbox into the house entirely
in its own language, umlauts and all, which is a §3.8.5 test in
disguise -- ZSCII is not ASCII, and a word like *öffne* only
reaches the parser if the interpreter encodes its extra
characters the way the story's own table says.
The oldest Zork on the record earns a footnote of its own:
Release 2's walk now calls the
coal-to-diamond machine by its true name, *pdp10*, after the DEC
machine Infocom's compiler ran on. That word only parses in an
interpreter that encodes dictionary words the way §3.7.1 says
Versions 1 and 2 must, locking the shift across a run rather
than shifting twice; Frotz and Bocfel both answer "I don't know
the word 'pdp10'". One word in a three-hundred-move walk, and it
holds a rule of the Standard upright.
Forty-five recordings verify those sessions end-to-end with the
acceptance harness the [README](README.md) describes, and their
annotations double as
an archaeology of where the games' published walkthroughs go wrong.

## The Z-Machine: 1.0


Full Z-Machine Support -- since `1.0`, no longer a goal but a
claim. Every opcode §14 defines has a handler, all eight story
file versions play, and everything below is enforced rather
than promised: a test suite at 100% branch coverage and the
community's own checkers held to their exact tallies, both in
continuous integration, and forty-five recorded playthroughs
replayed whole against the previous release, a sweep with a
runner of its own under `tools/`. The short list that remains is under **Not yet**.

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

At a real terminal, Voxam paints the screen: the blessed frontend
(an optional extra, named for both its temperament and the
[blessed](https://pypi.org/project/blessed/) package behind it)
renders the §8 screen model live -- a reverse-video status line
that holds the top of the screen, split windows, character-input
menus like Zork's InvisiClues browsed by single keypresses, bold,
italic, and the §8.3.1 colors, forwarded to games that ask for
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
the arrows through to the games that claim them. Pasting works at
the window too -- Ctrl+V, Cmd+V, or Shift+Insert empties the
clipboard through the same key seam, a multi-line paste submitting
line by line just as it would at a terminal. Timed
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

Voxam reads [Blorb](https://jeffnyman.github.io/z-machine-standard/blorb.html)
resource files as well: a `.zblorb` packaged story boots directly,
and a sidecar `.blb` found beside a story by name announces its
pictures and sounds at the banner. The era before Blorb is
honoured too: a like-named `.MG1`, `.EG1`, or `.CG1` file --
Infocom's original DOS picture format, decoded by the rules of
ztools' pix2gif -- hangs its art the same way. The decoder is
really aimed at Infocom's own Version 6 games from their original
DOS assets; it also lets the fan homebrew *Frobozz Magic
Videopoker* find and deal its cards from a renamed Zork Zero
graphics file, though that game hard-codes the DOS screen it was
written for and lays itself out oddly on any other.
A cover picture -- *Beyond
Zork* ships one -- is shown before play at a painted terminal,
scaled into half-block cells on any color terminal or drawn at
real resolution with `--pixels`, decoded by a pure-stdlib PNG
reader. The pixels path asks the terminal first: one that
declares sixel graphics also reports its cell size, so the art
magnifies to the glass as it actually measures, and one that
never learned sixel quietly gets the half-block painting instead
of escape garbage. Art is a courtesy, never a gate: a
cover Voxam cannot draw earns a note and the story plays on. And
Voxam can claim any classic machine identity (`--interpreter
amiga`, or the legendary Tandy bit via `--tandy`), which some
early games answer with altered text and *Beyond Zork* answers
with its whole screen-model personality (§11.1.3, §16).

And at a pygame window -- the `graphics` extra, opened with
`--graphics` -- the Version 6 era plays illustrated, and since
`2.2` the same stage plays in the browser too (below). The §8.8
screen is real there: eight placeable windows on one pixel grid,
text at true pixel positions, margins that wrap prose around scene
art, and a [MORE] that pauses a screenful in the window's own
colors and cleans up after itself. Blorb pictures draw at the
sizes the Reso chunk scales them to, transparency lets the chrome
layer over the scenes, and the adaptive palettes recolor that
chrome as scenes change -- both the Standard's live APal dance and
Bocfel's pre-baked BPal replacements, which is how *Zork Zero*'s
plaques keep their gold. Even §8.3.1's strangest color is
honoured: color -1 samples the pixel under the cursor, which is
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

Voxam is verified against the community's interpreter test suites:
CZECH (versions 3, 4, 5, and 8 -- the last certifying the modern
Inform format, held to its exact tallies in continuous
integration), Praxix -- its Standard 1.1 section included --
TerpEtude, and Strict Z Test all pass clean; Infocom's own ZIPTEST
opened the version 6 era and named its frontiers one opcode at a
time. Even Borg's UTF-16 surrogate-pair test renders all six of
its emoticons -- adjacent surrogate halves fuse into their astral
characters at the screen, a community extension the Standard's
16-bit unicode (§3.8.5) cannot express, honoured deliberately
rather than by accident of encoding. Every opcode §14 defines --
all one hundred and twenty of them, `encode_text` through
`buffer_screen` -- has a handler, and every remaining gap halts
loudly with a citation instead of guessing.

**Not yet:** *Zork Zero*'s Version 6 mouse minigames -- though
the mouse is real and the grammar hears it now: at the pygame
window a click arrives as §10.3's input code with its coordinates
in the header extension, which is how *Solitaire Poker*'s betting
buttons take a real click, and a recorded session spells it
`<click x y>` and replays it coordinates and all. And the Blorb music formats,
MOD and OGG (the entire vendored Infocom sound catalog is sampled
AIFF and needs neither). For recorded sessions, seeds
substitute for saves: a script replays a whole game in moments.

## Glulx: 1.1

The Glulx machine is carried whole. Every opcode the
[Glulx 3.1.3 specification](https://www.eblong.com/zarf/glulx/)
defines is dispatched: the 32-bit core with its call stubs and
big-endian stack discipline, the Huffman string decoder with
filter-mode suspension, and the full
[Glk 0.7.6](https://www.eblong.com/zarf/glk/) dispatch layer
behind the `glk` opcode -- all 123 functions, their prototype
strings generated from readable declarations and held, one by
one, to cheapglk's own `gi_dispa.c`. Saves and undo speak Glulx's
Quetzal dialect (the stack chunk a straight copy, because the
stack chose big-endian storage for exactly that moment), the
allocation heap grows and retires above the memory map, the three
search opcodes serve Inform's tables, the thirteen accelerated
veneer functions replace their interpreted originals
bit-for-bit, and IEEE-754 floats and doubles arrive with their
word-order asymmetry and NaN-propagation rulings carried
faithfully. As everywhere in Voxam, behavior argues by citation:
(Glulx: The Header) names a section of the specification the way
§1.1 names one of the Z-Machine Standard.

The certification is glulxercise, the community's Glulx
interpreter unit test. All seventy sections pass with zero
failures, and continuous integration holds the tally exact --
seventy `Passed.` verdicts counted, the closing "All tests
passed." demanded -- through the very stdio session a player
would use: `echo all | voxam glulxercise.ulx`.

At a real terminal, a `.ulx` or packaged `.gblorb` story plays on
painted glass: the window tree is drawn across the whole screen
by way of the same blessed sliver the Z-Machine's painter uses,
status grids sit in place at their boxes, buffer text wraps and
scrolls behind a `[MORE]` pause, the eleven Glk styles dress in
terminal attributes, timer events fire between keystrokes, and
`save` asks its filename on the bottom line. *Adventure* --
Crowther and Woods by way of Inform -- plays there the way
glkterm would show it. Piped sessions, `--plain` sessions, and
everything riding the acceptance grammar's line seam keep the
stdio display: buffer windows flowing as prose, grids drawn as
blocks when they change.

And the glass has ears: Glk sound channels play through the same
speaker the Z-Machine's painted frontends own, AIFF resources
from the gblorb decoded by the same census, completion events
posted between keystrokes the way timer events are. The speaker's
honest limit rides along -- one sampled sound at a time, the
newest play winning -- and the music gestalt answers zero because
no MOD decoder is aboard, whatever else can play. Plotkin's own
*Sensory Jam* rings its gong here.

And the acceptance harness speaks Glulx now: `--record` writes a
session in the same grammar the Z-Machine records, `--accept`
replays it with the refusal watch listening, and the corpus holds
its first Glulx recordings -- *Adventure*'s opening excursion,
provisions to grate to debris room and home on XYZZY, replaying
byte-identical beside the Z-code excursions of the same cave.
The harness hears keys, too: a live recording rides the painted
glass, where a real arrow press lands in the script as the same
`<up>` token Beyond Zork's menus have replayed through since the
Z-Machine's key era, and a replayed token presses the Glk key it
means. And it hears the mouse: a click at a mouse-bearing glass
records as `<click x y>` with the coordinates the story was told,
and a replayed click presses §10.3's input code -- or answers the
Glk mouse event -- with the script's own values, on either
machine's grammar and either machine's window. Hyperlink
selections spell as `<link n>` the same way, carrying the link
value the game itself heard. Double clicks spell too, as
`<double-click x y>` -- the pygame glass hears the fast pair and
presses §10.3.3's own code. What the grammar cannot spell -- a
function key, a terminator -- warns loudly and records nothing,
never silently wrong.

The third glass is open: `--graphics` plays a Glulx story in the
pygame window, no terminal needed. The display logic the terminal
glass proved -- the whole-tree repaint, the wrapped buffers and
their `[MORE]` pager, the line editor, the timer, the speaker --
was lifted into one painted spine both displays now ride, so the
window inherited sound and timers the day it opened. The window
itself supplies only what a window can: the fitted bold and
italic faces, reverse as an ink-and-paper swap, a block caret
where a terminal would park its hardware cursor, a glulx badge on
the frame, and a close button that ends the session the way an
exhausted input stream does. Replays keep the stdio display, as
the grammar requires.

And the window has its senses. Graphics windows open as true
pixel canvases: the tree is arranged over the glass's real
pixels, a text window still answers its size in characters by
way of the font-cell metrics, a canvas answers honestly in
pixels, fills and erases clip to its own box, its pixels persist
between repaints because they are the game's work -- and a moved
canvas is cleared to background with the redraw event the spec
demands posted to the game (Glk: Graphics Windows). The gblorb's
Picts draw onto the canvases scaled and clipped -- PNG through
the interpreter's own decoder with full transparency carried to
the surface, JPEG through the window's, whose pygame reads what
the interpreter does not; what neither can read is refused whole
rather than half-drawn. And transparency is claimed whole: a
translucent picture keeps its straight colors and opacities
through the decoder and blends on the blit, so the transparency
gestalt answers one and means it. The mouse is claimed: a click lands in whichever armed
grid or canvas it hit, delivered as the event glk_select expects
in that window's own units, cells or pixels. And hyperlinks are
claimed beside it: linked runs survive wrapping distinct, wear
the reader's blue on the glass, and a click on one delivers its
link value to a window that asked (Glk: Accepting Hyperlink
Events). Both inputs speak the grammar -- `<click x y>` and
`<link n>` -- so a session full of pointing records at the
window and replays at the stdio display, byte for byte. The
double click found its spelling too: the pygame glass hears the
fast pair, presses §10.3.3's own code on the Z-Machine, delivers
a second mouse event on Glulx -- Glk knows only clicks -- and
`<double-click x y>` replays it on either machine.

And the Treaty of Babel is aboard. Every story Voxam plays can
be asked its IFID -- `--babel` speaks every machine and the
blorbs besides -- computed by the treaty's own per-format rules: the
`UUID://` brand scanned out of byte-accessible memory where
modern Inform burned one in, gated by the treaty's own pre-2006
serial rule; the human-readable legacy identities otherwise,
`ZCODE-release-serial` with the checksum appended exactly where
the treaty says and withheld from Infocom's 8x serials and the
untrusted forms, `GLULX-` identities in both the Inform and the
alien flavors (Babel: The IFID unique identifier). A blorb's
iFiction record answers first, its title, author, and headline
reported beside the IFID; a record that will not parse earns a
loud note while the story's own bytes answer instead. And the
identities name the sessions: a modern game plays under its
record's title, and Infocom's games -- which predate the treaty
by two decades -- play under theirs by way of a table of all 246
known releases in Andrew Plotkin's Obsessively Complete Infocom
Catalog, keyed by the very IFIDs the headers compute. Trinity's
terminal tab says Trinity; Scroll Thief's window says Scroll
Thief.

### Full Glulx: the declaration

Voxam claims Full Glulx, in the manner 1.0 claimed the
Z-Machine. The machine claim is glulxercise's: all seventy
sections pass with zero failures, held to the exact tally in
continuous integration. The display claims are all true where
made and refused loudly where not, and after the last known
shapes were built -- JPEG through the window's own decoder,
partial alpha whole to the blit, character input in graphics
windows -- the exclusion ledger has exactly two entries, both
spec-sanctioned refusals with their reasons written down:

- **MOD music.** The music gestalt answers zero because the only
  audio decoder aboard is AIFF; a tracker player is an audio
  engine of its own, for a handful of games (Glk: Testing for
  Sound Capabilities).
- **Margin images in text buffers, at the glasses.** There,
  images draw in graphics windows alone, as the DrawImage gestalt
  says per window type -- "libraries may implement both, neither,
  or only one" is the spec's own sanction, and text flowed around
  margin art is the one display feature it explicitly permits
  declining (Glk: Testing for Graphics Capabilities). The 2.0 era
  narrowed this entry to the glasses: the protocol faces lay text
  around pictures for real, so they claim the whole buffer-image
  contract -- see the road to 2.0 below.

Everything else in the Glk 0.7.6 and Glulx 3.1.3 specifications
that a blocking display can express is expressed, and enforced
the way every Voxam claim is enforced: 100% branch coverage and
the checkers held to their tallies in continuous integration,
and forty-five recordings replayed whole against the previous
release.

### The road to 1.5, travelled

What remained after 1.1 was glass, not machine, and it mapped
onto the minor releases -- each shipped when its capability was
coherent, not on a calendar:

- **1.2, the complete harness.** Done in the making: the grammar
  spells raw keystrokes, so a session at the painted glass records
  and replays the way every line-driven session already does --
  and the Z-Machine's mouse clicks have their `<click x y>` token.
  The recording campaign runs through this era and keeps running.
- **1.3, the third glass.** Done in the making: the pygame
  frontend speaks the Glk window tree -- windows, text, styles,
  sound, and timers in a real window, one painted spine shared
  with the terminal glass.
- **1.4, the senses.** Done in the making: graphics windows and
  PNG image drawing from the gblorb, mouse input, hyperlink
  selection -- bundled because the pygame glass is where all
  three become honest claims -- and the grammar's `<click x y>`
  and `<link n>` spelling every one of them.
- **1.5, Full Glulx and the Treaty of Babel.** Done in the
  making: the last claims with known shapes -- JPEG art through
  the window's own decoder, partial transparency carried whole,
  character input in graphics windows -- then the treaty entire,
  IFIDs and iFiction and the Infocom catalog, and the
  declaration above with its two-entry exclusion ledger.

## The GlkOte protocol: 1.6 through 2.0

The 2.0 era opened exactly where the display contract said it
would: `glk_select` learned to suspend. A display that cannot
block raises one flag, and the select records what it waits for
and returns the machine to its host -- the opcode already whole,
the event delivered later through the library, execution stepping
on as though it never stopped. The exception that carries the
wait is named for no one machine, because the contract is not
Glulx's alone.

On that seam Voxam speaks GlkOte -- the JSON display protocol of
Lectrote and the modern web interpreters -- from the machine's
side, the role RemGlk plays for the C interpreters. The speaking
is machine-neutral by construction: a Page holds everything the
protocol remembers -- generation numbers, the windows already
shown, the grid rows already sent, the open paragraph, which
input fields stand at which generation -- and sends only what
changed, while a Glulx composer feeds it plain facts read from
the same tree the painted displays walk. The Z-Machine will feed
the same Page from its own screen model, and that is the point of
every seam in it.

Two faces wear the protocol. `--glkote` is the wire itself: JSON
lines on stdin and stdout, one update out, one event in, every
inbound stanza owed a response -- the transport a desktop shell
drives down a pipe. `--web` is the browser: a standard-library
HTTP server, the vendored GlkOte display shipped inside the wheel
beside the window icons, one POST per turn -- the burst model the
protocol's own documentation prescribes -- the story's Babel
title on the tab, the gblorb's art served at `/pict` by number,
and a page reload starting the story over, because that is what a
reload should mean. Adventure was the first game through the
wire, and the first in the tab.

And 1.7 made the protocol whole. The file prompt asked for a
second kind of standing down: a select suspends after its opcode
completes, but `fileref_create_by_prompt` cannot complete at all
-- its result is the player's answer -- so the call itself stands
mid-flight, the bridge's encoding and the opcode's store parked
on the wait, and the name that comes back as the protocol's
special input runs them in order. Typing `save` in a browser tab
writes a real Quetzal file beside the story; `restore` reads it
back; the cancel is honored as the always-legitimate answer it
is. And the player's half-typed command rides every event as the
protocol's partial input -- a field that must be remade because
the game printed mid-word is remade wearing exactly what was
typed, while a field the display carries keeps its editing state
untouched, so nothing churns and nothing is eaten.

And 1.8 kept the era's central promise: the Z-Machine joined.
The reads learned the same standing-down the selects learned --
with the file prompt's shape rather than the select's, because a
Z handler owns its own program counter and its operands pop the
stack, so the whole post-input tail parks on the wait: the
delivered line lands in the buffers and the lexer exactly as the
blocking tail lands it, a keystroke ZSCII cannot spell is refused
with the wait standing, and a timer's tick fires the §15
interrupt through the machine's own re-entrant loop -- the
interrupt's prints rendered while the read stands, a true return
erasing it the spec's way. Then the §8 screen model fed the same
Page the Glk tree feeds: the upper window and the Version 1 to 3
status line travel as the protocol's grid -- read out of the same
ScreenModel the painted terminal trusts, its splitting and cursor
rules and §8.2 formatting reused whole -- while the lower
window's text streams as styled runs the display wraps for
itself, the §8.7 dress mapped onto the protocol's names and
reverse video worn as the page's own inverse. Zork I's status bar
updates one changed row at a time; Bronze plays in a browser tab
wearing its own title.

The one named road the faces did not yet carry -- the Version 6
stage, "the stage stays at the painted glasses" -- stood as the
last refusal until `2.2` travelled it (below).

### The road to 2.0, travelled

Version 2.0 is an evolution rather than a completion: the GlkOte
interface whole -- both machines, browser and desktop. The
architectural change it asked for proved load-bearing the whole
way, and the road mapped onto the interim releases:

- **1.6, the protocol spoken.** Done in the making: the
  suspension seam, the machine-neutral update builder, the event
  half, and the two faces -- `--glkote` on the wire, `--web` in
  the browser.
- **1.7, the protocol whole.** Done in the making: the file
  prompt over the protocol's special input -- the era's second
  architectural moment, a suspension mid-Glk-call rather than at
  select -- and the player's partial input preserved when a timer
  interrupts their typing.
- **1.8, the Z-Machine joins.** Done in the making: reading
  learned the suspension contract the select learned, and the Z
  screen model -- upper window to grid, lower to buffer -- feeds
  the same Page. Bronze in the browser, beside Adventure.
- **1.9, the shell arrives.** Done in the making: the Lectrote analog,
  a Tauri webview wearing the same GlkOte display, driving a
  spawned `voxam --glkote` down a pipe -- a `desktop/` sibling
  the wheel never packages and the Python gate never sees. The
  shell finds `voxam` on the PATH, in the installers' bin dirs, or
  through the login shell -- a Dock launch carries no terminal
  PATH -- and says so plainly when it cannot; a session's events
  wear a minted id so a restart's
  fresh page ignores a dead session's last words; and the ends
  are honest -- the pipe's EOF is the machine's goodbye, the
  shell's own bar announces it (the vendored GlkOte ignores the
  update's exit flag), and a pre-wire refusal travels verbatim
  as the fault it is. The title bar speaks Babel: the shell asks
  `voxam --babel` for the story's name and the filename's stem
  stands in for the nameless. The Story menu claims the machine's
  identity -- a §11.1.3 platform and the Tandy bit, restarting
  the open story so the checkmark never outruns the header. The
  Display menu dresses the page in type, size, ink, and measure,
  applied live -- a poked resize re-measures the metrics and the
  machines take the new arrangement as they take any other -- and
  kept in the app's own config dir, so the checkmarks and the
  dress agree at every startup. The installers ride every release:
  a shared workflow builds Windows, macOS, and Linux bundles on
  each version tag -- dispatchable by hand for a dry run -- and
  the release attaches them beside the wheel, both streams wearing
  the one version `cz bump` stamps everywhere. And `1.9` carried
  the era's polish besides: the protocol grid wears its interior
  margins, so status rows draw whole in every face; the pygame
  glass presents on the frame's own cadence, so a chessboard of a
  thousand writes snaps into place instead of smearing; and the
  browser tab wears the machine's own icon beside the story's
  Babel title.
- **The band hangs.** Voxam speaks arc_image, the picture band of
  the Arcturus games (contract version 1.6, windowed profile): a
  conformant z5 or z8 with a sidecar of art plays illustrated --
  EXT:0x80 reaches a claiming display, Flags 1's picture bit
  answers honestly in Versions 5, 7, and 8, and the protocol
  faces hang the band as a graphics window above the whole
  screen, the picture inlined, the grid and buffer re-based
  below, the header's rows following. The pygame glass hangs it
  too, in the contract's own fixed-band profile -- the mode read
  from the art's aspect before the machine runs an instruction,
  whole rows reserved from boot, the model and the header born
  re-based, and the band standing empty rather than coming down.
  Every unclaiming face plays the same story as text, and the
  whole ignorable EXT range now passes unclaimed as Standard 1.1
  asks: the private band, 128 to 255, skips silently (§14.2),
  and the band reserved for future Standards, 30 to 127, skips
  with §14.2.1's own suggested warning sent off-screen to
  stderr, once per opcode -- never the story's stream, so every
  certified transcript holds. Below 30 an unknown number stays
  the loud error §14.2 asks for.
- **The saves stand down.** The Z machine's third wait: §15's
  save and restore suspend for their files the way the reads
  suspend for their lines, the ask travelling as the protocol's
  special input and the player's path -- or cancel -- running
  the parked rider. A restore that succeeds resumes at its
  save's own rider with 2, exactly as at the blocking glasses,
  so a Zork saved in the browser or the shell is a real Quetzal
  on disk. Both machines now save on every face that can ask.
- **The terminators ride the wire.** The §10.5.2.1 terminating
  characters table is read on the suspending faces: a Version 5
  or later read stands with the table's function keys in hand,
  the protocol request offers the twelve the wire can name, and
  the key that ends the line stores its own code where a plain
  return stores 13 -- with nothing echoed, since only a
  return-ended read prints its return, which is exactly the
  cursor-standing contract Beyond Zork's preloaded re-reads
  lean on. The cursor and keypad codes stay legal but unnameable
  in the protocol's vocabulary, an honest limit of the wire; the
  blocking editor keeps its own claim on the arrows for now.
- **The mouse rides the wire.** Clicks are core GlkOte, so the
  protocol faces claim §10.3 honestly: a keystroke read arms the
  grid -- the whole clickable surface, since buffer windows take
  no clicks -- and a click lands as input code 254 with its cell
  coordinates one step over in the header extension, which
  counts the screen from (1,1). A line read arms the grid only
  when its terminating table names the click code, and the click
  then ends the line, taking the half-typed command that rides
  the event as the protocol's partial input. The same branch
  settled the §15 preload contract on the wire: the story prints
  its own left-over characters, so the input field carries none
  and what comes back is the typed part alone, exactly what the
  machine appends after the preload it holds.
- **The pictures join the prose.** The protocol faces claim the
  whole buffer-image contract, because the display genuinely lays
  text around pictures: glk_image_draw into a text buffer places
  the picture in the flow -- inline alignments and the margin
  floats alike, the picture whole as a data: url, a link value
  riding so clickable art stays clickable -- and
  glk_window_flow_break moves the next paragraph below the
  margins. The claim is the display's own grant: GlkOte's init
  offers bare "graphics" for exactly this, distinct from the
  "graphicswin" that opens canvases, and the DrawImage gestalt
  answers per window type per display, so the glasses' ledger
  entry stays true where it was written. Sensory Jam's ornate
  initial letter -- a margin-left drop cap -- renders in the
  browser and the shell, apology withdrawn.
- **The cover stands at the door.** The frontispiece rides the
  wire: the Blorb's Fspc cover stands at the top of the story's
  text on both machines' protocol faces -- once, before anything
  the story prints, the picture whole as a data: url shrunk to
  the page by the display's own proportional cap -- under the
  same bare-graphics grant the buffer images ride, because a
  cover in the text is exactly a picture laid in text. The
  doorway courtesy the painted glasses have always offered, now
  in the browser tab and the shell: Violet's writing-day art
  opens the session it belongs to. Art is a courtesy, never a
  gate -- no cover, no grant, or an unmeasurable picture simply
  plays on.
- **2.0, the declaration.** The era is whole: both machines on
  every face, and every wait the machines know -- the selects,
  the reads, the file prompts, the saves -- standing down for the
  displays that cannot block. Pictures ride the pipe as `data:`
  urls, in canvases, in the prose, above the screen as the band,
  and at the door as the cover; the shell answers every file
  prompt with a real picker over the very filesystem the
  interpreter writes; the terminators and the mouse make Beyond
  Zork a browser game. What stays behind stays named: the
  Version 6 stage at the painted glasses, colors and sound over
  the protocol, the refresh event, the blocking editor's own
  claim on the arrow keys -- and signed installers, which are a
  certificate and an enrollment rather than a branch (macOS
  Gatekeeper and SmartScreen warn on the unsigned ones). None of
  it blocks a game the corpus plays, and forty-five recordings
  hold the whole claim to replay.

### Beyond the declaration: 2.1

The residue ledger is a menu, not a debt; what gets taken from it
is recorded here. The first helping shipped as `2.1` -- the whole
roster below -- leaving the Version 6 stage as the one named
road, which `2.2` then travelled.

- **The channels ring on the wire.** Sound joins the dialect:
  GlkOte never grew a sound vocabulary, but both ends of this
  wire are ours, so updates carry channel ops -- play, stop,
  volume -- and a finished play comes home as its own event. The
  sounds travel whole: AIFF re-wrapped as WAVE data: urls by a
  pure-stdlib writer, sample points intact, because a browser's
  decoder handles WAVE everywhere and AIFF almost nowhere; Ogg
  travels as itself; MOD keeps its refusal and the music gestalt
  its zero. The page's own module drives Web Audio -- one gain
  node per channel, counted repeats, forever as a native loop,
  and volume fades as real ramps, which is more than the
  speaker's next-play honesty ever offered. The claim is the
  display's grant ("sound" in the init's support), so every
  recorded session keeps its conforming silence. Sensory Jam's
  gong rings in the browser.
- **The Z-Machine sounds on the wire.** §9 joins the same
  dialect through the machine's untouched seam: the wire's one
  channel is §9.4.2's newest-play-wins made literal, the §9.3
  volume maps to eighths of unit gain, Version 3's silence on
  repeats is answered by the Blorb's Loop chunk -- how The
  Lurking Horror's dream chant loops through its 2-4-6-8
  crescendo in a browser tab, proved against the recording whose
  annotations were written as this very test plan -- and the
  display's finish reports drive §9.4.4's end-of-sound routines
  through the machine's own re-entrant loop, the seam Sherlock's
  chimes lean on. Even the interpreter's own bleeps travel, as
  oscillator notes: the wire's answer to a terminal's bell. The
  claim is honest twice over -- the display's word and a Blorb
  actually aboard -- and §9's pacing courtesy stays at the
  blocking glasses, where a synchronous answer exists; the wire's
  newest-wins is what that courtesy was approximating anyway.
- **The colors ride the wire.** §8.3 joins the dialect under
  its own word: text spans carry per-run ink -- fg and bg as CSS,
  drawn from the same palette the pygame glass mixes, promoted to
  a shared home so every face shows the same red -- and the
  window's paper travels on its declaration, so Photopia's scenes
  bleed to the window's edge rather than stopping under the
  letters. The grid's cells dress their spans through the same
  §8 model the painted terminal trusts, reverse video swaps ink
  and paper as every painted face swaps it, and the default
  color deliberately emits nothing: code 1 is each display's own
  theme, which is what §8.3's "default" has always meant. A
  display that never said the word leaves the header's color
  offer honestly unclaimed, and every recorded session replays
  untouched on the blocking seam it always used.
- **The refresh answers whole.** A display that lost its picture
  -- a reconnect, a confusion -- may ask with the protocol's
  refresh event, and the answer is an ordinary update complete in
  content: every window, the buffer's kept scrollback behind a
  clear (bounded at two hundred paragraphs, pictures and covers
  riding along since their data: urls were kept with the text),
  the grid's every row with the blank ones as bare line numbers,
  standing input fields stamped anew, a running timer renamed.
  The event is honored ahead of the generation gate, since a lost
  display is out of sync by definition; on Glulx the game also
  hears the spec's own redraw, because canvas pixels are the
  game's to repaint. The quote box stands beside it, from the
  color era's own bug hunt: the Z grid holds the turn's tallest
  split until the next input arrives -- the courtesy garglk and
  Parchment extend the same box -- so Photopia asks "Will you
  read me a story?" in the browser the way it always asked at
  the glasses.
- **The resource files read apart.** `--decompose` joins the
  archaeology instruments beside `--header`, `--babel`, and
  `--listing`: every chunk of a Blorb told in file order with the
  facts Voxam's own decoders can measure -- the story's version
  and serial from its own bytes, pictures sized with the cover
  credited, AIFFs shaped with their loops credited, the
  descriptive chunks each in their own voice, Infocom's copyright
  lines and wide-charactered story names included. `--extract`
  frees the contents as ordinary files in the formats their bytes
  already are -- AIFF FORMs re-framed whole so a player opens
  them, the story under its own version's name -- and a file
  already standing is never overwritten.
- **The card, and where it belongs.** The iFiction record's
  bibliography reaches the player the way WinFrotz's little
  window does: title, headline, author, and the description's
  paragraphs -- the record's <br/>-broken blurb parsed whole,
  mixed content walked rather than truncated at the first break,
  and the file's own indentation kept out of it, since a
  pretty-printed record is not a poem. At a painted terminal the
  card prints with the banner, under the cover's own rule: the
  plain stream is the machine-readable face, and a record may
  quote anything -- Zork I's blurb quotes a ">"-prefixed
  command, which would desynchronize any harness that frames
  output by the prompt.

  On the protocol faces it no longer opens the story's text at
  all. It rode there for one era and was wrong to: a publisher's
  blurb among the game's own first sentences is not something any
  reader asked for, and the story's opening belongs to its
  author. The card travels as facts in the sidecar instead, read
  once and rested, and the browser tab and the desktop shell each
  build the same little window over it from the same shared
  script, behind a button beside the preferences opener. A
  display that never says the sidecar's word never sees it, and a
  blorb with no record raises no button at all. Miss Gosling's
  Last Case still offers its own obituary, exactly as its author
  dressed it, to a reader who asks for it (Babel: The iFiction
  format; DESIGN: What the sidecar carries).

### The stage and the camera: 2.2

The second helping took the last named road and then built the
instrument that keeps such roads travelled.

- **The stage dialect.** The protocol grew the words a §8.8
  screen needs, both wire ends being ours: a graphics window may
  declare itself `scaled` -- its drawable size a logical space
  the display magnifies to fit, whole multiples for square
  pixels -- and its draw ops grew `text` (placed, dressed,
  stretched onto the cell grid) and `shift` (§8.8.3.6's scroll
  as a canvas self-copy), with line input emplaced at the game's
  own cursor, sized by its cell, written in its ink. A display
  that never learned the dialect is refused loudly at the door.
- **The stage face.** The same StageModel the pygame glass
  paints from feeds the wire: its unit-positioned paints become
  the dialect's ops on one canvas pinned to the art's own
  coordinate space -- the Reso standard window, or MCGA's 320 by
  200, the only default that draws no-Reso art true. A repaint
  journal answers redraws and refreshes; every §8.8 window op,
  the pictures, the clicks in units, the saves, and the timed
  reads ride the seams the two-window face already built.
- **The palettes bake.** A browser handed an adaptive stub's own
  bytes paints its placeholder palette, so the wire plots
  through the gallery's own APal-and-BPal dance and re-encodes
  the plotted pixels -- a pure-stdlib PNG writer joining the
  pure-stdlib reader -- with the standing chrome re-plotted when
  a scene changes the Current Palette. §8.3.1's color -1 samples
  the painted stage itself, walking the drawn ops newest-first,
  the found color minted past the named codes exactly as the
  glass mints its sampled pixels.
- **The seven repairs.** The stage's first live rounds named
  seven mechanisms, none of them in the stage: Enter had been
  silently dead on every wire keystroke read since `1.8` (spelled
  as a raw carriage return ZSCII refuses); a misaimed event --
  one keystroke landing across the roster's swap -- killed the
  whole session where a shrug was owed; focusing the canvas's
  input scrolled the stage sideways; GlkOte's reused input field
  kept the old duty's length cap and handlers; the model's
  text-flow scroll swept its own margins, erasing Shogun's ship
  at every face including the pygame glass, two eras unseen; the
  web server sent no cache headers, so stale displays masqueraded
  as unfixed bugs; and the editor wrote in the browser's default
  black -- invisible ink on a dark stage. Each is fixed at its
  proper layer, the model fix repairing the glass as well.
- **The filmstrip.** Any recorded walk photographs at a real
  face: `--shots` rides `--accept`, the glass runs driven -- no
  `[MORE]` waits on a player -- and saves its own surface each
  settled turn, headless under a dummy video driver if asked;
  `--browser` shoots the web display instead, the walk driving
  the very Session the browser face serves, both machines, the
  frames rendered through the shipped display files by the
  player's own browser in headless mode. A walk that breaks
  mid-stride keeps every frame it earned and says where it broke.
- **The strip diff.** `--strip-diff` compares two filmstrips
  frame by frame through Voxam's own decoder -- pixel truth, not
  file bytes -- naming each differing frame with its tally and
  the verdict with where the strips part, exit codes on
  RegTest's contract so a sweep can gate on it. A driven, seeded
  walk reproduces to the pixel, which is the property the whole
  instrument stands on.
- **The dice are seeded.** The CI glulxercise battery now runs
  under a pinned seed: its random section does statistical
  checks, and an honest unseeded stream fails them by pure
  chance every few dozen runs -- which twice read as a phantom
  regression on a green change before the cause was named.
- **A finding worth keeping.** Version 6 games can read their
  presentation into their own randomness, so a walk recorded at
  one face may diverge honestly at another -- Zork Zero's does,
  at the same seed. Filmstrips therefore compare face to same
  face, and the strips themselves are the per-face references a
  regression sweep needs.

What stays behind stays named, footpaths now rather than roads:
the Glulx games at the filmstrip's glass camera, the walk's
clicks at its web camera, `[MORE]` pacing on the wire's stage,
*Zork Zero*'s `read_mouse` minigames, the pre-Blorb picture
files on the wire, a period bitmap font for the stage's text,
the blocking editor's own claim on the arrow keys, and the
signed installers that remain a certificate rather than a
branch. None of it blocks a game the corpus plays, and
forty-five recordings hold the whole claim to replay.

## The Å-machine: 2.3, dressed in 2.4

The third machine. Dialog compiles to the Å-machine the way
Inform compiles to Glulx, and Voxam now carries the whole of it
-- the community fork's 1.0 specification, accepting every 0.x
story the compilers of the world actually emit -- certified the
strongest way an implementation can be: byte-identical against
the reference engine's own transcripts.

- **The story read at the door.** An `.aastory` is IFF -- form
  AAVM, HEAD first -- and the reader verifies the header's
  CRC-32 over the seven summed chunks before anything runs: a
  story that lies about its checksum is refused by the numbers.
  The optional IFID unwraps from its UUID dressing into
  `--babel`, the census reads every chunk in `--decompose`, and
  the META bibliography decodes through the story's own
  character table -- which is how an author's Å survives the
  trip.
- **The speech.** WRIT's strings are Huffman-inspired
  bitstreams walked by LANG's decoding tree, the escape in both
  its historical shapes -- seven fixed bits before format 0.4, a
  table-sized read after -- and the dictionary's words spell
  through the same charset. String pointers shift home tiny,
  short, and long.
- **The engine.** A Prolog heart: unification with a trail,
  choice and environment and stop frames on the main heap, the
  aux stack and long-term storage with their serialization
  formats, the input pipeline whole -- stop characters, the
  word-endings decoder, the wordmaps -- and every opcode of the
  instruction set dispatched, the runtime errors restarting at
  the entry point with their numbers in R00, exactly as
  specified.
- **The certification.** Every battery the reference ships runs
  in Voxam's own test suite and matches the reference engine's
  gold byte for byte at the same seed: aa-exercise (every
  opcode, saves declared and all), *Miss Gosling's Last Case*
  (a 351-command real-game walk), body_not_status (the 1.0
  SET_BODY fork), and codepoints (the character set, the
  keypress loop, the wrap buffer, the progress bars) -- with
  *The Impossible Stairs* certified against its gold as a live
  proof beside them. The dice are the reference's own linear
  congruence, so a seeded Voxam session and a seeded reference
  session roll the same numbers forever.
- **The faces.** The terminal is the default -- the certified
  document discipline streamed live, the reference frontend's
  own input drill -- and `--graphics` plays the same voice at
  the pygame window the other two machines paint on, which is
  the one face that knows how tall it is: a story asking after
  the screen height gets a true answer there rather than a
  shrug, a windowful of unread text pauses at a `[MORE]` before
  the scroll carries it away, and a story that clears the
  screen really clears it. The window keeps its own grid of
  dressed cells rather than borrowing the Z-Machine's screen
  model, because that model stores the eleven §8.3.1 color
  codes and the LOOK sheet's palette does not fit in them.
  The wire carries the same certified
  voice at width zero into one buffer window, the browser doing
  the wrapping: `--glkote` serves it down the pipe, `--web`
  puts it in a tab under the META title, and the desktop shell
  plays it for free. The META bibliography rides the sidecar to
  the same little window the treaty's own records get, and the
  window and the browser tab both wear the
  third machine's own mark now: an Å over a D, drawn in the same
  idiom the z badges are, for the machine and for the language
  that compiles to it. An Arcturus story wears no such thing on
  purpose, because it is a Z-Machine story file and the numbered
  badge it already gets is the true one.
- **The savefile.** AASV written and revived: the story's own
  HEAD copied byte for byte as the identity gate, the state
  run-length encoded against INIT, the open divs re-entered on
  revival. At the terminal and at the window alike a save asks
  for its name on the spot, which is the blocking faces' own
  privilege: the file-keeping is shared and only the asking
  differs. Undo is aboard at every face, pruned at the
  reference's own depth.
- **The dress.** At a real terminal the LOOK chunk's styles are
  worn: bold as bold, italics as underlines (the Dialog
  debugger's own rendering, drawn by every terminal), and the
  sheet's colors as truecolor ink and paper -- named, hex, and
  rgb() spellings alike, an insistent normal!important turning
  a dress off mid-span, and the deprecated SET_STYLE bits
  composing beside the classes. The honesty gate is the stream
  itself: a pipe stays plain, every certified transcript still
  matches byte for byte, and VM_INFO answers the styling and
  color questions truthfully per stream -- which makes Voxam,
  as far as we know, the first command-line Å-machine
  interpreter to clear the specification's styling bar. And the
  wire wears the same wardrobe: one face-neutral dress state
  feeds both renderings, the terminal's attributes and the
  protocol's runs -- bold as the display's subheader, italic as
  its emphasized, both at once as alert, exactly as the bar
  permits -- with the sheet's colors riding as per-span ink
  under the display's own colors grant, the same dialect word
  the Z-Machine's §8.3 colors travel by. A refresh returns the
  scrollback with its styles still on.

The third machine's own footpaths, named: savefiles over the
wire await the suspended file-wait the Z-Machine's saves ride;
the status areas stay honestly unclaimed on every face, and the
author's whole sheet -- fonts, sizes, and margins as real CSS
on the page -- is a richer wire road than the stock styles worn
today; links stay honestly refused at both painted faces, which
is where the window's next work is; and the acceptance driver,
the tracer, and the filmstrip do not speak `.aastory` yet.

## The sidecar: 2.4

Automapping, a notebook, a "go to the kitchen" that any game
would obey: every one of those features has been built before,
and every one of them has been built by a face reading the
transcript and guessing. Guessing is where they break. A face
cannot tell a real move from a printed flashback, cannot tell
that an undo just unwound the last three rooms, and cannot know
that the command the machine actually received was not the one
the player typed. But the interpreter knows all three without
guessing at anything, because they are simply facts about the
session it is running.

So the wire grew a sidecar: a `voxam` block riding beside the
windows in an ordinary update, carrying those facts and nothing
else. Every ounce of intelligence stays in the face. It was
designed and served an era before anything consumed it, so that
anyone's face could be written against it; the browser tab and
the desktop shell are its first customers, and they read one
field of it, the story's card. The schema it serves is specified
under **What the sidecar carries** in [DESIGN.md](DESIGN.md),
which is what the `DESIGN:` citations in the wire's own code
point at.

- **Granted, never assumed.** The block travels only to a
  display that names `voxam` in its own init support list,
  exactly as the sound, color, and stage words of the dialect
  travel. An ungranted session carries no block at all, and a
  granted one never has an update forced into being for its
  sake: a cycle where nothing changed is still the pass. The
  courtesy feed cannot become a gate.
- **Location, honestly or not at all.** The Z-Machine reads the
  §8.2 globals its status line reads: the first global's object
  and that object's short name, the score, and the turn count.
  A time game's globals are the clock, so its score and turns
  simply do not travel rather than travelling as nonsense, and
  a global naming no decodable object answers with no location
  rather than halting the session over a courtesy. Glulx and
  the Å-machine have no fixed globals to read at all, so
  theirs are the fields the wire itself owns.
- **The command as delivered.** The wire layer knows the exact
  line it handed the machine, scripted and replayed input
  included, which is better evidence than any face-side memory
  of what was typed into a box.
- **The discontinuity bit.** Undo, restore, and restart each
  raise it in the machine, and the face's composer reads it
  once and rests it. One honest bit spares every consumer the
  transcript-grepping heuristics the earlier automappers
  needed, and it is what keeps a mapper from drawing a phantom
  edge across time travel.
- **The card as facts.** The story's own bibliography rides the
  block too, read once and rested, since it cannot change while a
  story runs. All three machines answer it alike -- it belongs to
  the story file, not to any machine's registers -- the Z-Machine
  and Glulx from the treaty record a Blorb carries, the Å-machine
  from its own META chunk. This is the field the browser tab and
  the desktop shell build their **iFiction Card** button over,
  and it is the reason the block exists in the shape it does: a
  face given plain facts can put them where they belong.
- **The boundary, deliberately.** No direction parsing and no
  graph state anywhere in the machines. Reading a typed command
  for its compass word is an English-only, typed-input-only
  heuristic: a fine choice for a face, a poisonous assumption
  in a core. Rooms are identified by object number, not by
  printed name, which is the property that makes a maze
  mappable at all.

One more thing hardened underneath the release. The wire's own
pictures are re-encoded when an adaptive palette has to be baked
in, and `zlib.compress` does not promise the same bytes on every
build: madler zlib and zlib-ng disagree, so a filmstrip
photographed on one machine could differ from the same walk
photographed on another for no reason the story knew about.
The encoder now spells its own deflate stream by hand (RFC 1951)
beside the reader that was already hand-written, so the bytes
are the bytes, everywhere, forever.

The sidecar's own footpaths, named: only the card is consumed, so
the map, the notebook, and the verified fast travel that
motivated it remain designs rather than claims;
Glulx and the Å-machine carry no location, because neither
format has one an interpreter could honestly read, so a face
wanting rooms from them will have to earn them some other way;
and a persisted map, if one is ever kept, is meant to
key by IFID and live beside the story as an ordinary file, the
way the saves do.

## The faces dressed, and the seed kept: 2.5

An interpreter has no business deciding that a story must be
read in white on black, and for most of Voxam's life the pixel
window decided exactly that. Now it does not:

- **Four themes at the pixel window.** `--theme` picks `dark`
  (the new default), `paper`, `sepia`, or `classic`, which is
  the old white on black kept by name for anyone who wants it.
  A theme is a whole dress, not a background swap: the ink and
  paper it names are what §8.3's "default" colours resolve to,
  so a game that resets to its own defaults lands on the
  theme's pair rather than snapping back to a look the screen
  never otherwise shows.
- **A picker in the browser tab.** The page follows
  `prefers-color-scheme` until a reader chooses, so a dark
  desktop gets a dark story with nothing asked of anyone; the
  chip in the corner offers System, Paper, Sepia, Dark, and
  Frotz, and the choice is remembered and applied before the
  first paint, so a chosen ink never flashes the other one on
  the way in. The desktop shell's Display menu offers the same
  inks, in its own native list.
- **Frotz, the period piece.** The DOS Infocom look WinFrotz
  still opens in: white on a deep blue, with the status bar its
  exact inverse. The one ink here that is a piece of the
  format's history rather than a reading preference.
- **The status bar names its own pair.** On the protocol faces
  it had been derived by inversion, which looks right until the
  upper window is itself dressed as the story's inverse: §8.2's
  line is reverse video from end to end, so it inverted a second
  time and landed back on the story's own colours. In sepia the
  bar was pixel-for-pixel the prose beneath it; in paper its
  text was lighter than the story's own. Every ink now chooses
  its bar, the way WinFrotz chooses white on blue, and the grid
  itself wears the story's paper, because an upper window is
  part of the same screen. A test holds every ink's bar apart
  from its paper, so no future ink can quietly collapse again.
- **The named footpath.** `--theme` reaches the Z-Machine's
  pixel window; the Glulx Glk glass beside it wears the same
  default dark but does not read the flag yet. The pixel window
  never had the double inversion, since its reverse video swaps
  the theme's own ink and paper exactly once.

The rest of the release is faces that had been trusting instead
of reading, each caught by a real session:

- **The painted terminal follows its window.** It had been
  drawing against the size it booted with, so a terminal resized
  mid-story, or one too slow to answer at startup, was painted
  for a screen that was not there. It now re-measures and
  reshapes, and from Version 4 the §8.4 header fields are
  re-stamped with it.
- **The wire's screen model follows the display.** The Z face
  re-measured on an `arrange` but never told the model behind
  it, so the desktop shell's Display menu could push the §8.2
  status line's score past the right edge of a narrowed grid.
  Worse in the other direction: a smaller font widens the grid,
  and the renderer reached for cells the model did not have,
  which ended the session outright. Both were the one gap.
  Reported by a player, which is a first worth recording.
- **The `--seed` promise, kept to the end.** A story may ask to
  reseed itself from genuine entropy (`random 0` in the
  Z-Machine, `@setrandom 0` in Glulx) and in an ordinary session
  it gets exactly that. Under an explicit `--seed` the new dice
  are drawn off the seeded stream instead, so the whole run
  stays a function of the one seed given. This is the knowing
  deviation named above, and it is narrow by construction: the
  flag already overrides the same rule at game start, and
  without this the flag made a promise the interpreter quietly
  broke the moment a story asked. It also made a checker
  honest: glulxercise's random battery reseeds itself, and at a
  pinned seed the whole run is now byte-identical, so the retry
  loop that had been standing in for determinism in continuous
  integration is gone.

And the shell finds its interpreter. It looks on the PATH, then
in the bin directories the installers use, then asks the login
shell, since an app launched from the Dock or the Start menu
inherits no terminal's PATH; `VOXAM_BIN` names one outright, and
when nothing turns up it says so in words rather than failing
blank.

## The pace: 2.6

An interpreter written in pure Python has a speed, and it is
worth stating rather than leaving for a player to discover with a
story that takes a minute to open.

Voxam runs roughly **780,000 Glulx instructions a second**, twice
what `2.5` managed. `--benchmark` reports it for any session, and
because a seeded session executes exactly the same instructions
every time, two runs are comparable even when their seconds are
not:

```bash
voxam --accept acceptance/advent-r5-s961209-glulx.accept --benchmark
```

Four things bought that doubling, and all four are the same idea:
stop doing work whose answer was already settled.

- **The instruction shape is kept.** Below RAMSTART the story
  cannot write, so an instruction's opcode, its handler, its
  operands' addressing modes, and the address it ends at cannot
  change (Glulx: The Memory Map). They are read once. Every later
  visit does only the part that is not fixed: fetching what the
  operands stand for.
- **The function header is kept**, on the same terms and behind
  the same boundary.
- **The stack stopped building bytes to throw away.**
  `int.from_bytes` on a slice constructs an object per access
  purely to discard it; a prepared accessor does not, at about a
  third of the work.
- **A local read stopped being four calls deep.** It was a
  property, a check, and a dispatch on width before a byte was
  read.

Code above RAMSTART is read afresh every time, in both caches, so
a story that writes its own code runs the code it wrote. Nothing
is checked less than before, and every recording in the corpus
replays to the same tally it did in `2.5`.

**Where it stops.** After all four, no single thing dominates:
decoding operands is about 12% of a session and dispatching them
about 11%, and everything else is under 6%. Those top two are the
interpreter's own loop, which no amount of tidying removes. What
remains that is even thinkable is worth a few percent; a
different dispatch architecture would be a rewrite rather than a
repair. Neither turns a thirty-second opening into an instant
one, which would need roughly seven times.

That ceiling is not a defect. It is the price of the choice
[DESIGN.md](DESIGN.md) makes on purpose: the machines, the
formats, and the wire are standard-library Python, so what is
being paid for is correctness that installs with nothing and
runs anywhere. The price is the pace above, and a story whose
opening needs thirty-one million instructions takes half a
minute to arrive.

**The named footpath.** *Dead Cities* is by a wide margin the
heaviest thing Voxam plays, and would make a good permanent
guard against a performance regression; it stays out of the
corpus for now because it would add half a minute to every
sweep, and `--benchmark` catches the same regressions for less.

## The C# port: begun

Voxam has a second implementation now, under `csharp/`, and the
reason is the one
[#373](https://github.com/jeffnyman/voxam/issues/373) set out: a
native executable that installs with nothing, which Python cannot
produce, and a language whose coverage tools report branches,
which Go's does not. The exploration the issue asked for came
back with both answers it wanted. The Version 3 core replays the
whole of Zork I byte for byte against the Python, and it was
pleasant to write.

**What is in the directory.** `Voxam.Core`, the machine: memory,
the decoder and its opcode tables, the text, object and
dictionary rules, the seeded generator ported bit for bit, and a
plain frontend with the Python's muting rules. `Voxam.Cli`, a
console executable answering `--accept SCRIPT` exactly as the
Python does, down to the banner and the Blorb census. And
`Voxam.Desktop`, a window on Avalonia playing the same stories.
And the test projects, `Voxam.Core.Tests` at 309 tests and
`Voxam.Desktop.Tests` at 10, each at 100% line and branch
coverage enforced as a threshold the way the Python's suite is,
most of them driving tiny stories assembled by a builder in the
test project rather than fixtures on disk.

**Where it stands.** Every one of the 41 Z-code recordings in
the corpus replays identically, Versions 1 through 8, packaged
stories included, and Bronze among them in a second where the
Python takes eighteen. The port speaks the whole acceptance
grammar, keys, clicks, links and camera marks included, and
carries the refusal watch, so a replay warns of a silently
refused command exactly where the Python does. Its keystroke
queue and patient typist are the reference's: a scripted line
is spent one `read_char` at a time, and a timed read lets one
interval pass, firing its interrupt once. Version 6 keeps the
§8.8 window ledger as pure state, the eight windows' geometry,
cursors and properties, and answers the picture, mouse and menu
opcodes as a frontend without them does, which is exactly what
a plain transcript of Arthur or Shogun records. The saves are
Quetzal, below, and the window has opened. Glulx and the
Å-machine are refused at the door.
`tools/sweep-corpus.py record --voxam` is the certificate:
it records a sweep under the executable and compares it with the
Python's by digest, and CI replays Zork I under both on every
push, on all three platforms, from a NativeAOT publish.

**What it is not.** Not a replacement, and not a mirror. The
Python is the reference and keeps every face it has; the port is
certified against it, and a difference is the port's question
until the Python is shown wrong against the Standard. Where the
two part is the faces. The Python's browser tab and desktop shell
exist because a page was the one display it could give without an
install, and the sidecar and the GlkOte dialect belong to them.
The port has a native window instead, so it carries no wire face
at all: its glass is [Avalonia](https://avaloniaui.net/), one code
on Windows, macOS, Linux and the phones, and it is where the stage
gets drawn as a stage rather than flowing as text. Beside it
stands a console, the same `voxam` that answers `--accept` and the
tools, which also plays at a prompt the way the painted terminal
does, because a machine that installs with nothing should also
play with nothing. Two executables, one core: `voxam` at the
prompt, `Voxam` with an icon. The console keeps the Python's
name on purpose: it answers the same banner, the same transcript
and the same exit codes, which is what the sweep certifies, so a
different name would claim a difference the certificate denies.
The one place they should differ is `--version`, where the
native one names its runtime; the port versions with the repo.

**The console plays.** `voxam story.z5` at a real terminal is the
painted terminal, ported piece by piece: the §8 screen model as
pure state (two windows, one grid, the owed scroll, the [MORE]
pause), the line editor with its history and cursor keys, the
painter that redraws only damaged rows, the status line, styles,
colours and the font 3 shapes, a window that follows its
terminal's size, and the wall-clock half of timed reads, so a
Border Zone or a Bureaucracy form runs in real time. A piped
session, or `--plain`, is the transcript stream, answering as the
Python's does. `voxam --version` says `voxam 2.7.0 (native)`, and
the port versions with the repository. Not yet at this face:
sixel pictures, sound, and the terminal's title bar.

**The saves.** SAVE and RESTORE write and read Quetzal by the
rules the Python keeps: an IFhd naming the story by release,
serial and checksum, the checksum summed from the file when the
header holds none; a CMem that is the xor against the pristine
story, its zero runs counted and its unchanged tail dropped; a
Stks with the dummy frame first. The file conventions are the
Python's as well, `zork1.z3` saving to `zork1.sav` beside it, and
the table forms writing auxiliary files under the names the game
gives. A restore resumes at its save's own rider, with 2 from
Version 4 and the branch again in Version 3, and undo rides the
same capture. A malformed file is refused by the rule it breaks,
section cited, and a save of another game is turned away by its
IFhd. The certificate no recording can give was taken by hand:
a Zork I saved in the Python restores in the port, and one saved
in the port restores in the Python.

**The window.** `Voxam story.z5`, or Voxam alone and a story from
its menu, is the desktop: one window on Avalonia, published
through NativeAOT like the console, with the glass drawn straight
onto the control from the same screen model the painted terminal
keeps. The terminal and the window are two screens under one
frontend now: each is asked to paint a row, park the cursor, or
lay [MORE] over a line, and the terminal answers in ANSI where the
window answers in cells. The machine runs on its own thread and
blocks there for keys, so the window never waits on it; opening
another story retires the first mid-read. The suite drives the
window on Avalonia's headless platform with Skia drawing, so a
real frame renders to a bitmap at the 100% gate, which is the
measure the filmstrip takes of the Python's faces, taken inside
the tests. What the window does not yet do is the next branches'
business: the dress (a bundled face, the preferences, the title
from Babel), the stage for Version 6, and sound.

**The roads, in order.** The glass dressed, then the Version 6
stage on it, then sound. Then Glulx, its own era, with the
two recordings that certify it. The Å-machine waits on the
Python's own acceptance driver for it, and a browser face waits
on someone wanting one, at which point it is Avalonia in
WebAssembly and not a second renderer.
