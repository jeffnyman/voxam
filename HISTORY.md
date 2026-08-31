# Voxam History

The road, told era by era: what each release meant, in the order
it was travelled. This is the narrative record -- the claims
themselves live in [STATUS.md](STATUS.md), organized by subject
and enforced in continuous integration, and the mechanical
release-by-release record is the [CHANGELOG](CHANGELOG.md).

The Z-Machine claim is `1.0`'s: every opcode §14 defines has a
handler, all eight story file versions play -- version 6
illustrated at a pygame window, painted at a terminal, spoken
aloud with the sound extra -- and everything is enforced in
continuous integration rather than promised: a test suite at
100% branch coverage, forty-four recorded playthroughs swept
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

The treaty and the declaration are `1.5`'s: Voxam claims Full
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

The protocol is `1.6`'s: Voxam speaks GlkOte -- the display
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
Voxam quietly.

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
browser tab wearing its own title, and the one refusal `1.8`
left honest -- the Version 6 stage at the painted glasses --
stood until `2.2` retired it.

The desktop shell is `1.9`'s: a
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
and the browser tab wears the machine's own icon.

And `2.0` completes the era. The Z-Machine's saves stand down
the way its reads do, so a Zork saved in the browser or the
shell is a real Quetzal on disk. The §10.5.2.1 terminating
characters and §10.3's mouse ride the wire -- a function key
ends a read, a click lands with real coordinates -- which makes
*Beyond Zork* playable in a browser tab. Text buffers claim
their pictures on the protocol faces, margins and flow breaks
whole, under the display's own graphics grant -- *Sensory Jam*'s
ornate drop cap renders in the shell, apology withdrawn -- and
the Blorb's cover stands at the top of the story's text, so
*Violet*'s writing-day art opens the session it belongs to.

And `2.1` sings what `2.0` declared. Sound joins the wire in
Voxam's own dialect -- AIFF re-wrapped as WAVE and played by the
page's own Web Audio, Glk channels with real fades, §9's
end-of-sound routines fired by the display's finish reports --
so *Sensory Jam*'s gong rings in a browser and *The Lurking
Horror*'s dream chant swells through its crescendo there, on the
Loop chunk's own say-so. The §8.3 colors ride as per-span ink
with the window's own paper, one palette shared with the pygame
glass, which is *Photopia* with its scenes bled to the edge; the
quote box stands at the turn's high water, so its question gets
asked; a display that lost its picture may ask for everything
back with the refresh event, and gets it. Beside the wire,
`--decompose` reads any resource file apart -- every chunk told
in Voxam's own measurements, every resource freed as the file
its bytes already are -- and the iFiction card greets the player
the way WinFrotz's little window does, in the browser, the
shell, and at the painted terminal's banner. It left one named
road standing: the Version 6 stage at the painted glasses.

New in `2.2`, the stage crosses the wire and brings a camera
home. The dialect grew the words a §8.8 screen needs -- scaled
canvases, placed text, sliding rectangles, an editor emplaced at
the game's own cursor -- and the same StageModel the pygame
glass paints from feeds them, pinned to the art's own coordinate
space, the adaptive palettes baked into the pictures themselves.
The repairs that followed ran deep: Enter had been silently dead
on every wire keystroke read since `1.8`, a misaimed event could
kill a session, and the model's text-flow scroll swept its own
margins -- Shogun's ship erased by its scrolling text at every
face, the pygame glass included -- each named, fixed, and
tested. And the filmstrip turned the hunt into an instrument:
driven walks photograph at the glass or through a headless
browser, strips compare frame by frame, and a seeded walk
reproduces to the pixel.

And `2.3` brings the third machine aboard whole. An `.aastory`
is verified at the door by its own checksum, its prose decoded
through LANG's bitstream tree, and its Prolog engine --
unification, twin heaps, choice points, the word-endings
decoder -- run instruction for instruction as the specification
writes it, runtime errors and all. The proof is the reference
implementation's own test suite: every battery it ships,
replayed under Voxam, matches the reference engine's transcript
byte for byte at the same seed -- the dice being the
reference's own. *Cloak of Darkness* plays at the terminal, on
the wire, and in a browser tab under its META bibliography's
card; the AASV savefile is written and revived with the story's
own header as its identity gate; and undo keeps the reference's
own depth at every face.

And `2.4` is the first release that builds for somebody else.
Dialog's own styling is worn at last, at the terminal and on
the wire from one shared wardrobe, which as far as we know no
other command-line Å-machine interpreter has done. The rest of
it is a seam rather than a feature: every update the wire sends
can carry a `voxam` block of plain session facts beside the
windows it draws, where the player stands, the command the
machine was actually handed, the score and the turns, and one
bit that says an undo or a restore just broke the causal
thread. Automappers and notebooks have always had to guess at
those facts by reading the transcript, and guessing is where
they break; an interpreter simply knows them. So the
interpreter says them, and stops there: no graph, no layout, no
compass-word parsing anywhere in the machines, because that
work belongs to whatever face wants to do it. Voxam's own
displays do not read the block yet. It is served before it is
consumed on purpose, so that a map, a notebook, or a "go to the
kitchen" that any game would obey can be written by anyone
against a feed that was designed to be honest rather than
clever.

And `2.5` is the release where the faces stop assuming. The
pixel window wears a theme, opening in a gentle dark instead of
1979's white on black, with paper, sepia, and the old classic a
flag away; the browser tab follows the reader's own system
preference until a picker says otherwise, and remembers the
answer. A theme is a whole dress rather than a background swap:
the ink and paper it names are what the §8.3 defaults resolve
to, so a game resetting to its own colours lands on the theme's
pair. Underneath the dress, three places where a face had been
trusting instead of reading: the painted terminal now follows
the window it is handed rather than the one it booted against;
the wire's screen model follows the display's font size, which
was pushing a status line's score off the edge of a narrowed
grid and, going the other way, ending the session outright; and
`--seed` keeps its word through a story's own reseed to entropy,
which is the one place Voxam knowingly answers a story with
something other than what its specification asks for, written
down with the argument that carried it. That last also made a
checker honest, since glulxercise's random battery reseeds
itself, and a pinned seed now runs it byte-identically. Small
release, and the first one shaped in part by a bug a player
filed.

And `2.6` is the release a player asked for without meaning
to. One opened a heavy Glulx story in a browser tab, pressed a
key, and watched nothing happen for a minute and a quarter --
which is indistinguishable, from the outside, from an
interpreter that has died. It had not. That story's opening
asks for thirty-one million instructions, and a pure-Python
machine was answering them at four hundred thousand a second
behind a page that showed no sign of life.

Both halves are answered now. The machine stopped repeating work
its own memory had already settled: an instruction below
RAMSTART cannot change, so its opcode, its handler, its
operands' modes and its ending address are read once and kept,
and so is a function's header; the stack stopped building bytes
only to discard them, and a local read stopped being four calls
deep. That is twice the pace `2.5` ran at, on identical
instruction counts, with every seeded session byte-identical
either side of it. And no face stays quiet while it works: a
light appears once a turn has taken long enough to be worth
mentioning, and then counts the seconds, because a number that
moves is proof of life where a still page is not.

The rest of the release is the same face learning to be read:
the line a player types wears the story's ink rather than the
browser's black, each ink names its own status bar instead of
deriving one by inverting twice, and the DOS Infocom blue that
WinFrotz still opens in joined the wardrobe. What the era did
not do is hide where it ends. Voxam is standard-library Python
on purpose, and that buys correctness which installs with
nothing; the price is a pace, and the pace is now written down
where it can be held to rather than discovered.

The story continues in [STATUS.md](STATUS.md), which always
opens with the current release and keeps the ledger of what
plays, what is certified, and what remains.
