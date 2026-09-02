# Voxam Design

How Voxam is built, why it is built that way, and what its words
mean. The [README](README.md) says what Voxam does,
[STATUS.md](STATUS.md) says what is enforced,
[HISTORY.md](HISTORY.md) tells the road, and
[CONTRIBUTING.md](CONTRIBUTING.md) is how to work on it. This
document explains the thinking that runs underneath all of them,
and the internal vocabulary those documents use without any sort
of apology, but also without any sort of explanation.

## The principles

**Fidelity, with citations.** Voxam implements specifications,
not folklore. Every rule the interpreter enforces cites the
section it came from, in the code itself: a Z-Machine behavior
names its section of the Standard, a Glk call names its chapter,
an Å-machine opcode names its heading in the reference
specification. When Voxam and another interpreter disagree, the
citation is where the argument starts, and usually where it
ends. The one family of citations that names no published
specification is the wire's own extensions, which no
specification covers; the last section here is where those are
written down instead.

**Loud beats wrong.** When Voxam can't do something correctly,
it says so, by name, and stops. It doesn't guess, half-work, or
silently degrade. A story format it can't run is refused with
the reason spelled out; a capability a display lacks is declared
honestly to the game (in the header bits, the Glk gestalts, or
the Å-machine's VM_INFO answers), so the game can adapt rather
than be lied to. The corollary is the earned relaxation: a rule
is loosened only when a real, named precedent shows the strict
reading breaks legitimate stories, and the relaxation is written
down with its precedent.

**Reproducibility, forever.** A seeded session given the same
commands produces the same session, every time, on every
machine. This is not a testing convenience that happens to be
exposed; it's a commitment the whole architecture serves. The
dice are seedable in every machine (the Å-machine's are the
reference implementation's own stream, so even cross-interpreter
comparisons hold), and every recorded playthrough is expected to
replay byte for byte until the end of time. This is the one
principle allowed to outrank fidelity, and it outranks it exactly
once: a story asking to reseed itself from entropy is answered
off the seeded stream when, and only when, the operator passed
`--seed`. The flag already overrides that same rule at game
start, so the alternative is not a purer reading of the
specification but a flag that lies.

**Certification over promise.** Claims are enforced in continuous
integration or they are not made. The community's own checkers
are held to their exact tallies (CZECH, ZIPTEST, glulxercise,
Praxix), the Å-machine replays its reference implementation's
whole test suite byte-identical to the reference engine's
transcripts, RegTest scripts run under both Voxam's runner and
the reference runner to the same verdict, and the test suite
holds 100% statement and branch coverage as a gate, not a goal.

**Machines stand and wait.** A machine never blocks on input.
When a story asks for a line, a keystroke, or a file, the machine
suspends: it parks its state mid-instruction, returns to whoever
runs it, and resumes when the answer is delivered from outside.
This one contract is what lets the same machine play at a
blocking terminal, in a browser tab, and down a pipe, because
input becomes something a host delivers rather than something
the machine demands.

**One machine, many faces.** The machines know nothing about
displays; the faces know nothing about opcodes. Between them sit
narrow, machine-neutral seams, so a new face serves every
machine at once, and a new machine appears on every face at
once. The seams are also where the tests live: anything a player
can do, a test can do through the same opening.

**The player's data is ordinary files.** Saves are real Quetzal
and AASV files written beside the story, readable by any
conforming interpreter. Nothing of the player's is held in a
browser silo, a proprietary format, or an internal database, and
anything Voxam grows in the future (notes, maps) is expected to
keep this rule.

**Own both ends of the wire, extend it honestly.** Voxam speaks
GlkOte from the machine's side and ships the display it serves,
so when the stock protocol lacks a word (sound, per-span color,
the Version 6 stage), Voxam's dialect adds one, always behind
the display's own declaration of support. A display that never
learned the dialect gets an honest, undegraded session; one that
speaks it gets everything.

**The core is dependency-free.** The machines, the formats, and
the wire are pure standard-library Python: Voxam decodes its own
PNGs, writes its own savefiles, and serves its own pages. The
extras (`screen`, `graphics`, `sound`) buy presentation, never
correctness, and everything works without them.

That choice has a price, and it is a speed. An interpreter in
Python runs a few hundred thousand virtual instructions a second
where one in C runs a hundred million, so a story whose opening
asks for tens of millions of them takes a noticeable while to
arrive. The work worth doing against that is the work of not
repeating oneself -- what a story's own read-only memory settles
is read once and kept -- and that has been done. What is left is
the interpreter's own decode and dispatch loop, which is the
floor this choice sets. [STATUS.md](STATUS.md) states the pace
as a number, because a price named is a decision and a price
unnamed looks like an oversight.

## The lexicon

Voxam's documents and commit messages use my house vocabulary.
It's not whimsy for its own sake; each word marks a boundary
the architecture actually has.

### The machines and their stories

- **machine**: one virtual machine implementation. There are
  three: the Z-Machine, Glulx, and the Å-machine.
- **story**: a compiled game file, whatever the format. Stories
  are read at the door, verified (checksums, headers), and
  refused loudly if they lie about themselves.
- **suspend / stand and wait**: the no-blocking contract. A
  machine that needs input parks itself and returns; the host
  delivers the answer and the machine steps on as though it
  never stopped.

### The faces

- **face**: one complete way to play, end to end. The painted
  terminal, the plain stream, the pygame window, the browser
  tab, the desktop shell, and the stdio wire are faces.
- **glass**: a blocking, locally drawn display surface. The
  terminal glass paints with terminal cells; the pygame glass
  paints with pixels. "At the glasses" means "on the blocking
  local displays," as opposed to on the wire.
- **painted**: rendered live onto a screen model at a real
  terminal, as opposed to **plain**, the classic scrolling text
  stream (which is also what pipes and replays always get,
  because it's deterministic).
- **the shell**: the desktop application, a native window
  wearing the same display the browser face serves, driving
  `voxam --glkote` down a pipe.

### The wire

- **the wire**: the GlkOte protocol seam. One session as
  structured messages: over stdio with `--glkote`, over HTTP
  with `--web`.
- **stanza**: one JSON message on the wire, either direction.
- **the burst model**: the wire's rhythm. One event arrives, the
  machine runs to its next wait, one update goes back.
- **the dialect**: Voxam's own extensions to stock GlkOte,
  spoken only to displays that declare support for them: sound
  channels, per-span ink, and the stage's words.
- **the sidecar**: the `voxam` block riding beside the windows
  in an update: plain facts about the session (where the player
  stands, the command the machine was handed, the score and
  turns, and whether an undo or a restore just broke the causal
  thread) offered to a display that asks for them by name. A
  dumb factual feed, never a picture: everything clever a face
  might build on it is the face's own work.
- **the stage**: Version 6's §8.8 screen crossing the wire as a
  single scaled canvas in the art's own coordinates, with placed
  text, sliding rectangles, and an input editor emplaced at the
  game's cursor.
- **the card**: the bibliography that greets the player at the
  door of a session: title, author, headline, blurb, drawn from
  the iFiction record or the Å-machine's own metadata.
- **the band**: the arc_image picture strip hung above the
  screen, following an Arcturus game scene by scene.

### The dress

- **dress / dressed**: styling worn by output. A dressed face
  renders bold, italics, and color; an undressed stream is plain
  text. Dressing is gated by honesty: a pipe is never dressed,
  and the game is told the truth either way.
- **wardrobe / outfit**: the Å-machine's styling state. The
  wardrobe holds one dress per LOOK style class; the outfit is
  what is currently worn once the body, the open divisions, and
  the deprecated style bits are folded together. One wardrobe
  feeds every face; only the rendering differs.
- **ink and paper**: foreground and background color, the
  Z-Machine Standard's own words for them, used across all three
  machines.
- **theme**: the ink and paper a face opens in, and what a
  story's own "default" colors resolve to while it is worn. A
  theme is chosen by the reader, never by the story: the pixel
  window takes one from `--theme`, the browser tab from the
  system's preference or its own picker. It dresses what the
  story left unsaid, and never overrides a color the story
  actually asked for.
- **voice**: the Å-machine's output subsystem, and **the
  telling** is what a voice has said so far. The plain voice is
  certified word for word against the reference implementation's
  transcripts, which is why every other voice is built on it.

### The instruments

- **recording / walk**: a play session captured as an acceptance
  script, in a grammar that can spell every input any display
  can produce, keystrokes and mouse clicks included. The
  **corpus** is the collection of games these walks run against,
  and the **sweep** replays all of them, counting warnings
  against a known baseline.
- **the refusal dialect**: the vocabulary of a game parser
  saying no ("You can't go that way"), which the replay harness
  listens for so a broken walk is caught at the turn it breaks.
- **the filmstrip**: a recorded walk photographed at a real
  face, one frame per settled turn, at the pygame glass or
  through a headless browser. A **strip diff** compares two
  filmstrips pixel by pixel with Voxam's own decoder.
- **the benchmark**: a session asked to report its own pace,
  through `--benchmark`. The instruction count leads, because a
  seeded session executes exactly the same instructions every
  time and is therefore comparable run to run; the seconds and
  the rate follow, and are the machine's, not the story's. A
  recording makes the fixed workload, so the corpus doubles as
  the bench.
- **the probe**: replaying a recording up to a chosen turn and
  examining the machine's state there, the instrument for
  answering "what was true when it broke."
- **the gate**: the local quality chain that must pass before
  any branch is done: formatting, lint, types, and the full test
  suite at 100% branch coverage, run as one command so nothing
  passes on a technicality.

### The process

- **era**: one release's arc of work, a set of branches with a
  shared theme, told afterward as a paragraph in
  [HISTORY.md](HISTORY.md).
- **road**: named future work. Roads are written down in
  [STATUS.md](STATUS.md) so that what Voxam does not do is as
  documented as what it does.
- **footpath**: a small deliberate not-yet, named so that it's
  remembered, blocking nothing the corpus plays.
- **the ledger**: STATUS.md itself, and the habit it enforces:
  claims organized by subject, each one enforced rather than
  promised, including the **exclusion ledger** of the few
  spec-sanctioned refusals and their reasons.
- **refusal**: Voxam declining to do something, loudly and by
  name, with the reason and usually the road. The opposite of a
  silent failure, and treated in this project as a feature.

## The wire's own extensions

Citations in the code normally name a public specification
(`§8.2`, `Glulx: The Random Number Generator`, `Blorb: The
Adaptive Palette Chunk`). One family cannot, because it names
something no specification covers: Voxam's own additions to the
GlkOte protocol. Those read `DESIGN: What the sidecar carries`,
and this is the section they mean. Where the citation convention
normally says "this behavior is not mine to invent," one of these
says "this behavior is ours, and here is where it is written down
so it cannot drift."

### What the sidecar carries

The sidecar is a `voxam` block riding beside the windows in an
ordinary update stanza: plain facts about the session, offered so
that a face can build a map, a notebook, or a "take me to the
kitchen" on knowledge instead of on guesswork. Everything clever
belongs to the face. The block itself is dumb on purpose.

**The grant.** It travels only to a display that names `voxam` in
its own init support list. A display that never asks never sees
it, and one that asks gets it on every real update.

**Never a cause.** The block rides updates; it does not summon
them. A cycle in which nothing changed stays the pass stanza it
would have been.

**The fields**, each present only when the machine can say it
honestly, and absent otherwise rather than guessed:

- `location`: `{"object": <number>, "name": <string>}` -- where
  the player stands, identified by object number, with the
  printed name beside it. The number is the identity; the name is
  a courtesy, since two rooms may print alike.
- `score`: the current score.
- `turns`: the turn count.
- `command`: the line the wire actually delivered to the machine,
  which is not always the line the player typed.
- `discontinuity`: `true` when an undo, a restore, or a restart
  has intervened since the last update, so this state of play does
  not follow from the last command. Read once and rested: it
  appears in exactly one update and is cleared as it goes.
- `card`: the story's own bibliography, as `title`, `headline`,
  `author` and `description`, each present only when the story
  says it. Read once and rested, like the discontinuity bit: it
  rides the first real update and never comes again, because it
  cannot change while a story is running. A painted face shows
  this at the door, in the story's own text, because a terminal
  has nowhere else to put it. A display that speaks the sidecar
  is given it as facts instead, and can keep it behind a button
  where the reader asks for it rather than reading it in the
  middle of the story's opening words.

**What each machine can honestly answer.** The Z-Machine reads
its §8.2 bearings, so it offers all five of the play fields --
except that a time game has no score or turns to give, and omits
them. Glulx and the Å-machine have no fixed globals an
interpreter could read for location, score, or turns, so they
carry only `command` and `discontinuity`. An absent field means
the machine could not say, never that the answer was zero.

The card is the exception that proves the shape: it belongs to
the story file rather than to any machine's registers, so all
three answer it alike. The Z-Machine and Glulx read the treaty
record a Blorb carries; the Å-machine reads its own META chunk,
which says the same things in its own words and has no headline
to give.

**The boundary, deliberately.** No direction parsing and no graph
state live in the machines. Compass words are an English-only,
typed-input-only heuristic: a fine thing for a face to do and a
poisonous assumption in a core. Rooms are identified by object
number rather than printed name, which is the property that makes
a maze mappable at all.
