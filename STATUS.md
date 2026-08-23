# VΘXΔM Status

The claims ledger: what plays, what is certified, and what
remains. The short version lives in the [README](README.md);
this is the long one, kept with the same rule the code keeps --
nothing below is promised, only enforced.

## The played-games ledger

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
Even *Journey* -- Infocom's menu-driven finale, a game with no
command line at all -- replays through its opening chapter as pure
keystrokes: letters press the commands they begin with, `<space>`
walks the highlight between the party column and the character
grid, and the arrows settle which Examine is whose.
Forty recordings verify those sessions end-to-end with the
acceptance harness the [README](README.md) describes, and their
annotations double as
an archaeology of where the games' published walkthroughs go wrong.

## The Z-Machine: 1.0


Full Z-Machine Support -- since `1.0`, no longer a goal but a
claim. Every opcode §14 defines has a handler, all eight story
file versions play, and everything below is enforced in
continuous integration rather than promised: a test suite at
100% branch coverage, forty recorded playthroughs swept
end-to-end, and the community's own checkers held to their exact
tallies. The short list that remains is under **Not yet**.

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

VΘXΔM reads [Blorb](https://jeffnyman.github.io/z-machine-standard/blorb.html)
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
faithfully. As everywhere in VΘXΔM, behavior argues by citation:
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
value the game itself heard. What the grammar cannot spell -- a
function key, a terminator, a double click -- warns loudly and
records nothing, never silently wrong.

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
PNG Picts draw onto the canvases scaled and clipped, full
transparency carried through to the surface; a JPEG Pict is
refused whole rather than half-drawn, and the transparency
gestalt underclaims at zero because partial alpha is composed
over black -- both honest refusals with their reasons written
down. The mouse is claimed: a click lands in whichever armed
grid or canvas it hit, delivered as the event glk_select expects
in that window's own units, cells or pixels. And hyperlinks are
claimed beside it: linked runs survive wrapping distinct, wear
the reader's blue on the glass, and a click on one delivers its
link value to a window that asked (Glk: Accepting Hyperlink
Events). Both inputs speak the grammar -- `<click x y>` and
`<link n>` -- so a session full of pointing records at the
window and replays at the stdio display, byte for byte.

### The road to 1.5

What remains is glass, not machine, and it maps onto the minor
releases ahead -- each shipping when its capability is coherent,
not on a calendar:

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
- **1.5, Full Glulx and the Treaty of Babel.** The declaration
  release, in the manner of 1.0. First the last claims with
  known shapes: JPEG art through the window's own decoder,
  partial transparency carried honestly, character input in
  graphics windows. Then the Treaty of Babel: IFIDs computed by
  the treaty's per-format rules and the Blorb's iFiction record
  read, so Voxam can name what it plays. Then the declaration
  itself -- the parity sweep, the certifications, and a ledger
  whose exclusion list is short and spec-sanctioned: MOD music
  and margin images, refusals with their reasons written down.

### And then 2.0

Version 2.0 is reserved for an evolution rather than a
completion: a Lectrote-like interface speaking the GlkOte
protocol, where the display no longer blocks for input but is
handed events as they happen. That asks for the one architectural
change the display contract was designed to permit -- glk_select
suspending rather than calling read_line -- and the machine has
been single-steppable since the frontier days for exactly that
reason. The reference material is already vendored: GlkOte
itself, and Quixe beside it.
