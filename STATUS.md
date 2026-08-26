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
toolchain a new generation of story files is written in.
Forty-four recordings verify those sessions end-to-end with the
acceptance harness the [README](README.md) describes, and their
annotations double as
an archaeology of where the games' published walkthroughs go wrong.

## The Z-Machine: 1.0


Full Z-Machine Support -- since `1.0`, no longer a goal but a
claim. Every opcode §14 defines has a handler, all eight story
file versions play, and everything below is enforced in
continuous integration rather than promised: a test suite at
100% branch coverage, forty-four recorded playthroughs swept
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
be asked its IFID -- `--babel` speaks both machines and their
blorbs -- computed by the treaty's own per-format rules: the
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

VΘXΔM claims Full Glulx, in the manner 1.0 claimed the
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
the way every Voxam claim is enforced: 100% branch coverage,
forty-four recordings swept end-to-end, the checkers held to
their
tallies.

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

On that seam VΘXΔM speaks GlkOte -- the JSON display protocol of
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

What the faces do not yet carry, each a named road: the Version 6
stage ("the stage stays at the painted glasses" -- the one
refusal left), colours over the protocol, the Z-Machine's half of
the sound dialect (the Glk channels already ring in the browser),
and the refresh event. None blocks a game the corpus plays.

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
  shell finds `voxam` on the PATH and says so plainly when it
  cannot; a session's events wear a minted id so a restart's
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
- **The band hangs.** VΘXΔM speaks arc_image, the picture band of
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
  whole private EXT range now skips unclaimed (§14.2), as
  Standard 1.1 asks.
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
  Version 6 stage at the painted glasses, colours and sound over
  the protocol, the refresh event, the blocking editor's own
  claim on the arrow keys -- and signed installers, which are a
  certificate and an enrollment rather than a branch (macOS
  Gatekeeper and SmartScreen warn on the unsigned ones). None of
  it blocks a game the corpus plays, and forty-four recordings
  hold the whole claim to replay.

### Beyond the declaration

The residue ledger is a menu, not a debt; what gets taken from it
is recorded here.

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
  gong rings in the browser; the Z-Machine's own sound seam --
  The Lurking Horror's rats, Sherlock's chimes -- is the named
  next road.
