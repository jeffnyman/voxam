"""Command-line interface for Voxam."""

import argparse
import secrets
import sys
from collections.abc import Callable, Sequence
from importlib import metadata
from pathlib import Path
from typing import TYPE_CHECKING

from voxam.aamachine.glkote import serve as serve_aamachine
from voxam.aamachine.story import FORM_ID as AAM_FORM
from voxam.aamachine.story import Story as AAMachineStory
from voxam.aamachine.terminal import played
from voxam.acceptance import (
    CLICK,
    DOUBLE_CLICK,
    AcceptanceScript,
    Recorder,
    RefusalWatch,
    replay,
)
from voxam.babel import IFiction, ifiction, ifid
from voxam.blorb import PNG_ID, Blorb
from voxam.decompose import decompose_report, extracted
from voxam.errors import (
    AIFFError,
    BlorbError,
    PNGError,
    VoxamError,
)
from voxam.filmstrip import browsed, paged, parted, shot, walked
from voxam.frontend import Frontend, PlainFrontend
from voxam.gallery import Gallery
from voxam.glance import report as glance_report
from voxam.glkote import carded
from voxam.glulx.glk.api import Glk
from voxam.glulx.glk.glkote import GlkOteFrontend, serve
from voxam.glulx.glk.objects import KeyCode
from voxam.glulx.glk.resources import Resources as GlkResources
from voxam.glulx.glk.stdio import StdioFrontend
from voxam.glulx.machine import Machine as GlulxMachine
from voxam.glulx.story import MAGIC as GLULX_MAGIC
from voxam.glulx.story import Story as GlulxStory
from voxam.iff import FORM_ID as IFF_FORM
from voxam.infocom import title as infocom_title
from voxam.listing import Tracer
from voxam.listing import report as listing_report
from voxam.png import decode
from voxam.regtest import parse_script, run_script
from voxam.saves import FileSaveSlot
from voxam.scribe import FileScribe
from voxam.speaker import Speaker, open_sounddevice_stream
from voxam.web import AAMachineSession, Face, GlulxSession, Session, ZSession, serve_web
from voxam.zmachine.glkote import fronted as z_fronted
from voxam.zmachine.glkote import serve as serve_z
from voxam.zmachine.instruction import Instruction
from voxam.zmachine.machine import Identity, Machine
from voxam.zmachine.memory import Memory
from voxam.zmachine.story import Story

if TYPE_CHECKING:
    from voxam.glass import GraphicsFrontend
    from voxam.glulx.glk.frontend import Frontend as GlkFrontend
    from voxam.glulx.glk.glass import GlassFrontend
    from voxam.glulx.glk.painted import PaintedFrontend
    from voxam.glulx.glk.terminal import TerminalFrontend
    from voxam.painter import ScreenFrontend

# Exit codes: 0 for a story that ran to quit, 2 for a file or session
# that could not run to its end. There is no longer a frontier exit:
# every §14 opcode has a handler, and the streams' session files ride
# along in every command-line session.
EXIT_OK = 0
EXIT_UNUSABLE = 2

# RegTest's own exit contract: 1 when any check failed.
EXIT_FAILED_CHECKS = 1

# A recording without a seed cannot replay, so --record without
# --seed rolls its own dice once and writes them down. The ceiling
# just keeps the number the size the corpus scripts use.
RECORDED_SEED_CEILING = 100_000

# Where the browser face listens unless --port says otherwise.
WEB_PORT = 8080


def main(argv: Sequence[str] | None = None) -> int:
    """Run the Voxam command line.

    Args:
        argv: Command-line arguments; None means the process's own.

    Returns:
        The process exit code.
    """

    # Voxam speaks UTF-8 on the stream it owns: a piped Windows
    # console otherwise defaults to a legacy code page that cannot
    # carry so much as an arrow, and a recording must replay
    # identically everywhere. Streams without the knob -- test
    # doubles -- are already unicode-clean.
    reconfigure = getattr(sys.stdout, "reconfigure", None)

    if reconfigure is not None:
        reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(
        prog="voxam",
        description="An interpreter for Z-Machine and Glulx stories.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {metadata.version('voxam')}",
        help="show Voxam's version and exit",
    )
    parser.add_argument(
        "story",
        nargs="?",
        type=Path,
        help="a story file to run; omit to just show the banner",
    )
    parser.add_argument(
        "--seed",
        type=int,
        help="seed the dice for a reproducible session",
    )
    parser.add_argument(
        "--accept",
        type=Path,
        help="replay an acceptance script instead of playing interactively",
    )
    parser.add_argument(
        "--replay",
        type=Path,
        help="replay an acceptance script, then keep playing at the prompt",
    )
    parser.add_argument(
        "--shots",
        type=Path,
        help="save a filmstrip of the replay, one screenshot per turn",
    )
    parser.add_argument(
        "--browser",
        nargs="?",
        const="",
        help="shoot the filmstrip at the web display, with this browser or a found one",
    )
    parser.add_argument(
        "--record",
        type=Path,
        help="write the session as an acceptance script at this path",
    )
    parser.add_argument(
        "--resume",
        type=Path,
        help="replay a recording, then record your continuation onto its end",
    )
    parser.add_argument(
        "--regtest",
        type=Path,
        help="run a RegTest script in-process (regtest.html's format)",
    )
    parser.add_argument(
        "--header",
        action="store_true",
        help="describe the story's header (§11.1) and exit",
    )
    parser.add_argument(
        "--listing",
        action="store_true",
        help="list the story's code txd-style (§4, §14) and exit",
    )
    parser.add_argument(
        "--babel",
        action="store_true",
        help="report the story's IFID (Treaty of Babel) and exit",
    )
    parser.add_argument(
        "--decompose",
        action="store_true",
        help="list a resource file's contents (Blorb) and exit",
    )
    parser.add_argument(
        "--strip-diff",
        nargs=2,
        type=Path,
        metavar=("LEFT", "RIGHT"),
        help="compare two filmstrips frame by frame and exit",
    )
    parser.add_argument(
        "--extract",
        type=Path,
        nargs="?",
        const=Path(),
        help="with --decompose: export the resources, right here or to a directory",
    )
    parser.add_argument(
        "--trace",
        type=Path,
        help="write every executed instruction to this file, listing-style",
    )
    parser.add_argument(
        "--plain",
        action="store_true",
        help="keep the plain stream frontend even at a terminal",
    )
    parser.add_argument(
        "--graphics",
        action="store_true",
        help="play in a pygame window (needs the graphics extra)",
    )
    parser.add_argument(
        "--glkote",
        action="store_true",
        help="speak the GlkOte protocol as JSON lines on stdin and stdout",
    )
    parser.add_argument(
        "--web",
        action="store_true",
        help="play in the browser: serve the GlkOte display over HTTP",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=WEB_PORT,
        help=f"the port --web listens on (default {WEB_PORT})",
    )
    parser.add_argument(
        "--interpreter",
        help="claim a §11.1.3 platform, by name (amiga, ibm-pc, ...) or number",
    )
    parser.add_argument(
        "--tandy",
        action="store_true",
        help="set the legendary Tandy bit for version 3 games (§11.1.4)",
    )
    parser.add_argument(
        "--resources",
        type=Path,
        help="a Blorb resource file; found beside the story by name when omitted",
    )
    parser.add_argument(
        "--pixels",
        action="store_true",
        help="draw cover art in real pixels (needs a sixel terminal)",
    )
    parser.add_argument(
        "--zoom",
        type=float,
        default=0.85,
        help="the desktop fraction the graphics window fills (0 keeps "
        "the classic compact size)",
    )
    arguments = parser.parse_args(argv)

    if not arguments.glkote:
        # The greeting stays off the wire: a GlkOte session's
        # stdout carries stanzas and nothing else.
        print("\nVoxam Interpreter for Z-Machine and Glulx Stories\n")

    reported = _static_report(arguments)

    if reported is not None:
        return reported

    try:
        identity = _identity(arguments.interpreter, tandy=arguments.tandy)
    except ValueError as error:
        print(f"voxam: {error}")

        return EXIT_UNUSABLE

    script_path = arguments.accept if arguments.accept is not None else arguments.replay
    refusal = _flag_refusal(arguments, script_path)

    if refusal is not None:
        print(f"voxam: {refusal}")

        return EXIT_UNUSABLE

    session = _scripted_session(arguments, identity, script_path)

    if session is not None:
        return session

    if arguments.story is None:
        return EXIT_OK

    return (
        _recorded_session(arguments, identity)
        if arguments.record is not None
        else _play(
            arguments.story,
            arguments.seed,
            None,
            screen=not arguments.plain,
            graphics=arguments.graphics,
            glkote=arguments.glkote,
            web=arguments.web,
            port=arguments.port,
            identity=identity,
            resources=arguments.resources,
            pixels=arguments.pixels,
            zoom=arguments.zoom or None,
            trace=arguments.trace,
        )
    )


def _static_report(  # noqa: PLR0911 -- one verdict per report
    arguments: argparse.Namespace,
) -> int | None:
    """Serve --header, --listing, --babel, or --decompose; None if unasked.

    The reports read the same pristine story, so they share their
    guards -- but each is its own document, and asking for more
    than one at once is refused rather than half-served.
    """

    chosen = [
        flag
        for flag, wanted in (
            ("--header", arguments.header),
            ("--listing", arguments.listing),
            ("--babel", arguments.babel),
            ("--decompose", arguments.decompose),
            ("--strip-diff", arguments.strip_diff is not None),
        )
        if wanted
    ]

    if len(chosen) > 1:
        print(f"voxam: {' and '.join(chosen)} are each their own report; pick one")

        return EXIT_UNUSABLE

    if arguments.extract is not None and not arguments.decompose:
        print("voxam: --extract rides --decompose; add it")

        return EXIT_UNUSABLE

    if arguments.header:
        return _story_report(arguments, "--header", glance_report)

    if arguments.listing:
        return _story_report(arguments, "--listing", listing_report)

    if arguments.babel:
        return _babel_report(arguments)

    if arguments.decompose:
        return _decompose_report(arguments)

    if arguments.strip_diff is not None:
        return _strip_diff_report(arguments)

    return None


def _strip_diff_report(arguments: argparse.Namespace) -> int:
    """Compare two filmstrips; the exit code is RegTest's contract.

    Zero for identical strips, one for strips that part -- the
    verdict a CI step can gate on -- and the unusable two when a
    strip cannot be read at all. The comparison needs no story:
    the strips already hold everything a game showed.
    """

    if arguments.story is not None:
        print("voxam: --strip-diff compares two strips; drop the story")

        return EXIT_UNUSABLE

    left, right = arguments.strip_diff

    try:
        lines, differs = parted(left, right)
    except VoxamError as error:
        print(f"voxam: {error}")

        return EXIT_UNUSABLE

    for line in lines:
        print(f"voxam: {line}")

    return EXIT_FAILED_CHECKS if differs else EXIT_OK


def _only_reads(arguments: argparse.Namespace, flag: str) -> int | None:
    """Refuse what a static report cannot use; None to proceed.

    A report reads the pristine file: no machine boots, no
    identity is claimed, so the session flags have nothing to do
    and are refused rather than silently ignored -- and a report
    with no story named has nothing to describe.
    """

    others = (
        arguments.accept,
        arguments.replay,
        arguments.record,
        arguments.resume,
        arguments.regtest,
        arguments.trace,
    )

    if any(value is not None for value in others):
        print(f"voxam: {flag} only reads the story; drop the session flags")

        return EXIT_UNUSABLE

    if arguments.story is None:
        print(f"voxam: {flag} needs a story file to describe")

        return EXIT_UNUSABLE

    return None


def _aamachine_story(story_path: Path) -> bool:
    """Whether the file opens as an Å-machine story's FORM AAVM."""

    with story_path.open("rb") as handle:
        opening = handle.read(12)

    return opening[:4] == IFF_FORM and opening[8:12] == AAM_FORM


def _run_aamachine(  # noqa: PLR0913 -- one knob per session seam
    story_path: Path,
    *,
    seed: int | None,
    recorder: "Recorder | None",
    trace: Path | None,
    input_source: Callable[[], str] | None,
    glkote: bool,
    web: bool,
    port: int,
    screen: bool = True,
) -> int:
    """Run one Å-machine story over a face.

    The terminal is the default face -- the reference frontends'
    own shape, certified against their transcripts -- with the
    GlkOte wire and the browser behind their usual flags. The
    session instruments the other machines carry are refused by
    name rather than half-working: the acceptance driver and the
    tracer are the third machine's later roads.
    """

    if recorder is not None or input_source is not None or trace is not None:
        if recorder is not None:
            recorder.close()

        print(
            "voxam: the Å-machine plays live for now -- the acceptance "
            "driver and the tracer are later roads"
        )

        return EXIT_UNUSABLE

    story = AAMachineStory(story_path.read_bytes())

    if web:
        caption = story.meta.get("title", story_path.stem)
        session = AAMachineSession(story, GlkResources(None), seed=seed)

        try:
            return serve_web(Face(session, caption), port)
        except OSError as error:
            # The port would not bind, most likely: say so plainly.
            print(f"voxam: {error}")

            return EXIT_UNUSABLE

    if glkote:
        try:
            served = serve_aamachine(story, sys.stdin, sys.stdout, seed=seed)
        except OSError:
            # The pipe itself failed: no stream is left to answer on.
            return EXIT_UNUSABLE

        return EXIT_OK if served else EXIT_UNUSABLE

    played(story, seed=seed, dressed=None if screen else False)

    return EXIT_OK


def _decompose_report(arguments: argparse.Namespace) -> int:
    """Print a resource file's census, and free its contents if asked.

    The file itself must be a Blorb -- packaged story or sidecar
    alike -- and a loose story earns the honest refusal that it
    has no chunks to list.
    """

    refused = _only_reads(arguments, "--decompose")

    if refused is not None:
        return refused

    try:
        data = arguments.story.read_bytes()

        print(decompose_report(arguments.story.name, data))

        if arguments.extract is not None and data[8:12] == AAM_FORM:
            print()
            print("voxam: an Å-machine story frees nothing yet; the census is whole")

            return EXIT_UNUSABLE

        if arguments.extract is not None:
            print()
            print(extracted(data, arguments.extract))
    except (OSError, VoxamError) as error:
        print(f"voxam: {error}")

        return EXIT_UNUSABLE

    return EXIT_OK


def _babel_report(arguments: argparse.Namespace) -> int:
    """Print the story's identity and finish.

    Unlike the Z-Machine's own reports, the treaty speaks both
    machines: a blorb's iFiction record answers first, then the
    packaged or loose story's own bytes (Babel: The IFID for a
    blorbed story file) -- and the record's bibliography rides
    along when it has any. A metadata-only blorb still refuses: a
    blorb with no story "is not itself a work of IF".
    """

    refused = _only_reads(arguments, "--babel")

    if refused is not None:
        return refused

    try:
        data = _story_bytes(arguments.story)
        record = _ifiction_record(arguments.story)
    except (OSError, VoxamError) as error:
        print(f"voxam: {error}")

        return EXIT_UNUSABLE

    if data is None:
        print(
            f"voxam: {arguments.story.name} packages no story, and a "
            "blorb without one is not itself a work of IF"
        )

        return EXIT_UNUSABLE

    identity = (
        record.ifid if record is not None and record.ifid is not None else ifid(data)
    )

    if identity is None:
        print(f"voxam: {arguments.story.name} is neither Z-code nor Glulx")

        return EXIT_UNUSABLE

    print(f"{arguments.story.name}\n")
    print(f"IFID: {identity}")

    named = (
        record.title
        if record is not None and record.title is not None
        else infocom_title(identity)
    )

    if named is not None:
        print(f"Title: {named}")

    if record is not None and record.author is not None:
        print(f"Author: {record.author}")

    if record is not None and record.headline is not None:
        print(f"Headline: {record.headline}")

    return EXIT_OK


def _ifiction_record(story_path: Path) -> "IFiction | None":
    """A blorb path's parsed iFiction record, or None.

    None covers every quiet case -- a loose story, a blorb with no
    metadata chunk -- while a chunk that will not parse earns a
    loud note before the story's own bytes answer instead.

    Raises:
        BlorbError: For an unusable resource file.
        OSError: For files that cannot be read.
    """

    if story_path.suffix.lower() not in BLORB_SUFFIXES:
        return None

    packaged = Blorb.load(story_path)

    if packaged.ifiction is None:
        return None

    record = ifiction(packaged.ifiction)

    if record is None:
        print("voxam: the iFiction record cannot be read; the story answers instead")

    return record


def _story_bytes(story_path: Path) -> bytes | None:
    """A story's own bytes, unwrapped from a Blorb when packaged.

    None only for a blorb that packages no story at all.
    """

    if story_path.suffix.lower() in BLORB_SUFFIXES:
        blorb = Blorb.load(story_path)

        return blorb.glulx if blorb.glulx is not None else blorb.story

    return story_path.read_bytes()


def _titled(story_path: Path, blorb: Blorb | None = None) -> str | None:
    """The caption a session deserves, when the game is known.

    A story names itself two ways -- its Blorb's iFiction record
    first, the Infocom catalog by IFID second -- and plays under
    that name: the treaty's first interpreter guideline, "to use
    basic bibliographic data ... to give windows sensible titles"
    (Babel: Guidelines for interpreters and browsers). Anything
    unknown, or unreadable at all, is quietly no caption: a title
    bar is a courtesy, never a gate.
    """

    if blorb is not None and blorb.ifiction is not None:
        record = ifiction(blorb.ifiction)

        if record is not None and record.title is not None:
            return f"{record.title} — Voxam"

    try:
        data = _story_bytes(story_path)
    except (OSError, VoxamError):
        return None

    named = infocom_title(ifid(data)) if data is not None else None

    if named is None:
        return None

    return f"{named} — Voxam"


def _entitle_terminal(caption: str | None) -> None:
    """Name the terminal's own title bar, where one is listening.

    OSC 0 is the xterm convention every modern terminal honors. A
    piped session gets no escape -- a transcript is not a title
    bar, and a recording must not carry one -- and no caption, an
    unknown game, names nothing.
    """

    if caption is not None and sys.stdout.isatty():
        sys.stdout.write(f"\x1b]0;{caption}\x07")
        sys.stdout.flush()


def _story_report(
    arguments: argparse.Namespace,
    flag: str,
    composer: Callable[[Story], str],
) -> int:
    """Print a static report of the Z-Machine story file and finish."""

    refused = _only_reads(arguments, flag)

    if refused is not None:
        return refused

    try:
        if _glulx_story(arguments.story) is not None:
            print(
                f"voxam: {flag} reads Z-Machine stories, and "
                f"{arguments.story.name} is Glulx"
            )

            return EXIT_UNUSABLE

        story, _blorb = _load_story(arguments.story, arguments.resources)
    except (OSError, VoxamError) as error:
        print(f"voxam: {error}")

        return EXIT_UNUSABLE

    print(f"{arguments.story.name}\n")
    print(composer(story))

    return EXIT_OK


def _scripted_session(
    arguments: argparse.Namespace,
    identity: Identity | None,
    script_path: Path | None,
) -> int | None:
    """Run whichever script-driven mode was asked for; None for none."""

    if arguments.regtest is not None:
        return _regtest_session(arguments.regtest)

    if arguments.resume is not None:
        return _resumed_session(arguments.resume, identity, arguments.trace)

    if script_path is not None:
        return _replay_script(
            script_path,
            arguments.story,
            arguments.seed,
            handoff=arguments.replay is not None,
            identity=identity,
            trace=arguments.trace,
            shots=arguments.shots,
            browser=arguments.browser,
        )

    return None


def _regtest_refusal(arguments: argparse.Namespace) -> str | None:
    """Why --regtest cannot proceed, or None when it can."""

    if arguments.regtest is None:
        return None

    others = (
        arguments.accept,
        arguments.replay,
        arguments.record,
        arguments.resume,
        arguments.trace,
    )

    if any(value is not None for value in others):
        return "--regtest runs a script of its own; drop the other flags"

    if arguments.story is not None:
        return "a RegTest script names its own game; drop the story"

    if arguments.seed is not None:
        return "a RegTest script carries its seed on its interpreter line"

    return None


def _regtest_session(script_path: Path) -> int:
    """Run a RegTest script in-process, in the reference's voice."""

    try:
        script = parse_script(script_path)
    except (OSError, VoxamError) as error:
        print(f"voxam: {error}")

        return EXIT_UNUSABLE

    errors = run_script(script, print)

    if errors:
        print(f"\nFAILED: {errors} errors")

        return EXIT_FAILED_CHECKS

    return EXIT_OK


def _flag_refusal(arguments: argparse.Namespace, script: Path | None) -> str | None:
    """Why this flag combination cannot proceed, or None when it can."""

    if arguments.accept is not None and arguments.replay is not None:
        return "--accept and --replay are one script apiece; pick one"

    if arguments.graphics and arguments.plain:
        return "--graphics and --plain name two different glasses; pick one"

    if not 0 <= arguments.zoom <= 1:
        return "--zoom takes a fraction of the desktop, 0 to 1"

    for gated in (
        _filmstrip_refusal,
        _glkote_refusal,
        _regtest_refusal,
        _resume_refusal,
    ):
        refused = gated(arguments)

        if refused is not None:
            return refused

    return _record_refusal(arguments.record, script, arguments.story)


def _filmstrip_refusal(arguments: argparse.Namespace) -> str | None:
    """Why the camera flags cannot proceed, or None when they can."""

    if arguments.shots is not None and arguments.accept is None:
        # The camera photographs a replayed walk; a live session
        # already has a player watching.
        return "--shots rides --accept; the filmstrip is a replay's camera"

    if arguments.browser is not None and arguments.shots is None:
        return "--browser rides --shots; it names the filmstrip's camera"

    return None


def _glkote_refusal(arguments: argparse.Namespace) -> str | None:
    """Why --glkote or --web cannot proceed, or None when either can.

    A GlkOte face owns the whole session: no other face, no
    recording or replay instrument, can share it -- and the two
    faces cannot share each other.
    """

    if arguments.glkote and arguments.web:
        return "--glkote and --web are two faces of one protocol; pick one"

    if arguments.port != WEB_PORT and not arguments.web:
        return "--port belongs to --web"

    face = "--glkote" if arguments.glkote else "--web"

    if not (arguments.glkote or arguments.web):
        return None

    for named, held in (
        ("--graphics", arguments.graphics),
        ("--plain", arguments.plain),
        ("--record", arguments.record is not None),
        ("--replay", arguments.replay is not None),
        ("--accept", arguments.accept is not None),
        ("--regtest", arguments.regtest is not None),
        ("--resume", arguments.resume is not None),
        ("--trace", arguments.trace is not None),
    ):
        if held:
            return f"{face} speaks for the whole session; {named} cannot join it"

    return None


def _resume_refusal(arguments: argparse.Namespace) -> str | None:
    """Why --resume cannot proceed, or None when it can."""

    if arguments.resume is None:
        return None

    others = (arguments.accept, arguments.replay, arguments.record)

    if any(value is not None for value in others):
        return "--resume is a replay and a recording in one; drop the other flags"

    if arguments.story is not None:
        return "a resumed recording names its own game; drop the story"

    if arguments.seed is not None:
        return "a resume keeps the recording's own dice; drop --seed"

    return None


def _record_refusal(
    record: Path | None, script: Path | None, story: Path | None
) -> str | None:
    """Why --record cannot proceed, or None when it can."""

    if record is None:
        return None

    if script is not None:
        return "--record captures live play; a script already is one"

    if story is None:
        return "--record needs a story to play"

    return None


def _resumed_session(
    script_path: Path, identity: Identity | None, trace: Path | None = None
) -> int:
    """Replay a recording, then record the player's continuation.

    The script replays to its last verified line, the terminal
    takes over, and everything typed from there on is appended to
    the same file -- the expedition loop of trim, resume, and
    press on, as one flag. The recording keeps its own game and
    its own dice.
    """

    try:
        recorder = Recorder.resumed(
            script_path, warn=lambda message: print(f"voxam: {message}")
        )
    except (OSError, VoxamError) as error:
        print(f"voxam: {error}")

        return EXIT_UNUSABLE

    try:
        return _replay_script(
            script_path,
            None,
            None,
            handoff=True,
            identity=identity,
            recorder=recorder,
            trace=trace,
        )
    finally:
        recorder.close()


def _recorded_session(arguments: argparse.Namespace, identity: Identity | None) -> int:
    """Open a recorder -- rolling a seed if none came -- and play.

    A recording without a seed cannot replay, so a bare --record
    rolls its own dice once and writes them down.
    """

    seed = arguments.seed

    if seed is None:
        seed = secrets.randbelow(RECORDED_SEED_CEILING - 1) + 1

    try:
        recorder = Recorder(
            arguments.record,
            game=arguments.story,
            seed=seed,
            warn=lambda message: print(f"voxam: {message}"),
        )
    except (OSError, VoxamError) as error:
        print(f"voxam: {error}")

        return EXIT_UNUSABLE

    print(f"Recording to {arguments.record} (seed {seed})\n")

    return _play(
        arguments.story,
        seed,
        None,
        screen=not arguments.plain,
        graphics=arguments.graphics,
        identity=identity,
        resources=arguments.resources,
        pixels=arguments.pixels,
        zoom=arguments.zoom or None,
        recorder=recorder,
        trace=arguments.trace,
    )


def _replay_script(  # noqa: PLR0913 -- one knob per replay seam
    script_path: Path,
    story: Path | None,
    seed_override: int | None,
    *,
    handoff: bool,
    identity: Identity | None = None,
    recorder: Recorder | None = None,
    trace: Path | None = None,
    shots: Path | None = None,
    browser: str | None = None,
) -> int:
    """Replay an acceptance script; --seed beats the script's seed.

    With handoff, the exhausted script yields to the interactive
    terminal instead of ending the session -- and with a recorder,
    every handed-off line is also appended to the recording, while
    the replayed prefix is not: it is already on the page. With
    shots, the walk replays at the real pygame glass instead of
    the plain stream, one screenshot saved per settled turn -- the
    filmstrip; the responses live in the frames rather than on
    stdout, so the refusal watch keeps quiet counsel there.
    """

    if story is not None:
        print("voxam: an acceptance script names its own game; drop the story")

        return EXIT_UNUSABLE

    try:
        script = AcceptanceScript.parse(script_path)
    except (OSError, VoxamError) as error:
        print(f"voxam: {error}")

        return EXIT_UNUSABLE

    seed = seed_override if seed_override is not None else script.seed
    watch = RefusalWatch(script, warn=lambda message: print(f"voxam: {message}"))

    def tee(text: str) -> None:
        sys.stdout.write(text)
        watch.saw(text)

    live = input if recorder is None else _recorded_lines(recorder, input)

    # At handoff the last scripted response is complete; the watch is
    # closed there so live typing is never blamed on the script.
    def handed_off() -> str:
        watch.finish()

        return live()

    try:
        glulx = _glulx_story(script.game)
    except (OSError, VoxamError) as error:
        print(f"voxam: {error}")

        return EXIT_UNUSABLE

    camera = None
    painted: GraphicsFrontend | None = None

    if shots is not None:
        aimed = _filmed(script, seed, shots, browser, glulx)

        if isinstance(aimed, int):
            return aimed

        camera, painted = aimed

    def noted(index: int) -> None:
        watch.typed(index)

        if camera is not None:
            camera.frame(index)

    source = replay(
        script.commands,
        sys.stdout.write,
        exhausted=handed_off if handoff else None,
        typed=noted,
    )

    if glulx is not None:
        # The Glulx replay rides the stdio display's own seams:
        # the source types, the witness listens for refusals, and
        # a script that carries clicks answers the mouse events
        # its recording's game asked for, one pair per click. A
        # clickless script wires no click source, so its replay
        # keeps the mouse gestalt at zero -- what a session
        # recorded at the stdio display was told.
        glulx_positions = iter(script.clicks)
        glulx_links = iter(script.links)
        code = _run_glulx(
            script.game,
            glulx,
            seed=seed,
            resources=None,
            recorder=None,
            trace=trace,
            input_source=source,
            witness=watch.saw,
            click_source=(
                (lambda: next(glulx_positions, None)) if script.clicks else None
            ),
            link_source=((lambda: next(glulx_links, None)) if script.links else None),
        )
        watch.finish()

        return code

    # The script's click positions are spent one pair per click
    # delivered, in order -- the machine asks at the very moment a
    # replayed <click x y> line presses its input code.
    positions = iter(script.clicks)

    code = _play(
        script.game,
        seed,
        source,
        painted if painted is not None else PlainFrontend(tee),
        identity=identity,
        trace=trace,
        click_source=lambda: next(positions, None),
    )
    watch.finish()

    if camera is not None:
        camera.finish(len(script.commands))

    return code


def _filmed(
    script: AcceptanceScript,
    seed: int | None,
    shots: Path,
    browser: str | None,
    glulx: "GlulxStory | None",
) -> "int | tuple[_Camera, GraphicsFrontend]":
    """The strip's camera, whichever display was asked for.

    A browser shoots the wire whole and answers an exit code; the
    glass answers its camera pair, or the code its refusal earned.
    """

    if browser is not None:
        return _web_filmstrip(script, seed, shots, browser, glulx)

    aimed = _walk_camera(script.game, shots, glulx=glulx is not None)

    return EXIT_UNUSABLE if aimed is None else aimed


def _web_filmstrip(
    script: AcceptanceScript,
    seed: int | None,
    shots: Path,
    browser: str,
    glulx: "GlulxStory | None",
) -> int:
    """Shoot the walk at the wire: the web Session, photographed.

    The strip covers both machines -- the session is the same
    object the web face serves -- while a walk that clicks or
    follows links waits for the camera to learn aiming.
    """

    if script.clicks or script.links:
        print("voxam: the web filmstrip cannot aim the walk's clicks yet")

        return EXIT_UNUSABLE

    camera = browsed(browser)

    if camera is None:
        print("voxam: no browser found to photograph with; name one with --browser")

        return EXIT_UNUSABLE

    try:
        if glulx is not None:
            sidecar = _glulx_resources(script.game, None)
            session: Session = GlulxSession(glulx, GlkResources(sidecar), seed=seed)
        else:
            told, sidecar = _load_story(script.game, None)
            session = ZSession(told, GlkResources(sidecar), seed=seed)

        updates, marks, note = walked(session, list(script.commands))

        if note is not None:
            print(f"voxam: {note}")

        page = paged(shots / "page", updates)
        frames = shot(page, shots, marks, camera)
    except (OSError, VoxamError) as error:
        print(f"voxam: {error}")

        return EXIT_UNUSABLE

    print(f"voxam: {frames} frames in {shots}")

    return EXIT_OK


def _walk_camera(
    game: Path, shots: Path, *, glulx: bool
) -> "tuple[_Camera, GraphicsFrontend] | None":
    """The filmstrip's driven glass and its camera, or None said loud.

    The camera photographs the Z glass; a Glulx walk is refused
    honestly until that glass joins -- a silent half-strip would
    be worse than the honest wait.
    """

    if glulx:
        print("voxam: the filmstrip covers the Z glass; the Glulx glass is a road")

        return None

    try:
        walked, sidecar = _load_story(game, None)
    except (OSError, VoxamError) as error:
        print(f"voxam: {error}")

        return None

    painted = _graphics_frontend(
        walked.header.version,
        sidecar,
        story_path=game,
        title=_titled(game, sidecar),
        driven=True,
    )

    if painted is None:
        print("voxam: the filmstrip needs the graphics window to photograph")

        return None

    return _Camera(painted, shots), painted


class _Camera:
    """One screenshot per settled turn, numbered for the strip.

    The replay's typed hook fires just before each command, which
    is the moment the previous response stands complete -- so
    frame N shows the screen after N commands were answered, and
    frame zero is the boot screen itself. The closing frame, taken
    after the session ends, carries the last response.
    """

    def __init__(self, frontend: "GraphicsFrontend", directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=True)

        self._frontend = frontend
        self._directory = directory

    def frame(self, index: int) -> None:
        """Photograph the screen as command `index` is about to type."""

        self._frontend.snapshot(str(self._directory / f"turn-{index:04d}.png"))

    def finish(self, total: int) -> None:
        """The closing frame, and a word on where the strip lies."""

        self.frame(total)
        print(f"voxam: {total + 1} frames in {self._directory}")


# The §11.1.3 interpreter numbers, by the names Infocom used.
INTERPRETER_NUMBERS = {
    "dec-20": 1,
    "apple-iie": 2,
    "macintosh": 3,
    "amiga": 4,
    "atari-st": 5,
    "ibm-pc": 6,
    "commodore-128": 7,
    "commodore-64": 8,
    "apple-iic": 9,
    "apple-iigs": 10,
    "tandy-color": 11,
}


def _identity(interpreter: str | None, *, tandy: bool) -> Identity | None:
    """Build the claimed identity from the command line.

    Args:
        interpreter: A §11.1.3 platform name or number, or None
            for Voxam's default introduction.
        tandy: Whether the legendary Tandy bit is requested.

    Returns:
        The identity to claim, or None when nothing was asked.

    Raises:
        ValueError: For an interpreter that is neither a known
            name nor a number.
    """

    if interpreter is None and not tandy:
        return None

    number: int | None = None

    if interpreter is not None:
        lowered = interpreter.lower()

        if lowered in INTERPRETER_NUMBERS:
            number = INTERPRETER_NUMBERS[lowered]
        elif interpreter.isdigit():
            number = int(interpreter)
        else:
            names = ", ".join(sorted(INTERPRETER_NUMBERS))
            msg = (
                f"unknown interpreter {interpreter!r}; use a number or one of: {names}"
            )

            raise ValueError(msg)

    return Identity(interpreter=number, tandy=tandy)


def _graphics_frontend(  # noqa: PLR0913 -- one seat per optional collaborator
    version: int,
    blorb: Blorb | None,
    zoom: float | None = None,
    story_path: Path | None = None,
    *,
    title: str | None = None,
    driven: bool = False,
) -> "GraphicsFrontend | None":
    """A pygame window, when the graphics extra allows.

    The flag was explicit, so a missing extra earns a note before
    the session falls back to the terminal painter or the stream.
    """

    try:
        # Imported here because the graphics extra is optional.
        from voxam.glass import GraphicsFrontend  # noqa: PLC0415

        # The Blorb's Reso chunk names the shape the art was laid
        # out for, and the spec offers it as a window-sizing hint
        # (Blorb: The Resolution Chunk); a window in the standard
        # proportions is what lets a game's own layout nest.
        standard = (
            (blorb.resolution.width, blorb.resolution.height)
            if blorb is not None and blorb.resolution is not None
            else None
        )
        art = _gallery(blorb)

        if art is None and story_path is not None:
            art = _picture_file_gallery(story_path)

        return GraphicsFrontend(
            version,
            speaker=_speaker(blorb),
            gallery=art,
            standard=standard,
            arc=GlkResources(blorb) if blorb is not None else None,
            zoom=zoom,
            title=title,
            driven=driven,
        )
    except ImportError:
        print(
            "voxam: the graphics window needs the pygame-ce extra "
            "(voxam[graphics]); staying with the terminal\n"
        )

        return None


# The pre-Blorb picture files, found beside the story by its own
# name -- the convention the DOS-era instructions describe when
# they say to rename zork0.eg1 to FMVPOKER.EG1 (pix2gif).
PICTURE_SUFFIXES = (".mg1", ".eg1", ".cg1")


def _picture_file_gallery(story_path: Path) -> "Gallery | None":
    """Art from a like-named MG1/EG1/CG1 file beside the story.

    The original Infocom convention, honoured only when no Blorb
    brought pictures: an unreadable file earns a note and the
    session plays on unillustrated -- art is a courtesy, never a
    gate.
    """

    for suffix in PICTURE_SUFFIXES:
        sidecar = story_path.with_suffix(suffix)

        if sidecar.exists():
            from voxam.picfile import gallery as picture_gallery  # noqa: PLC0415

            try:
                return picture_gallery(sidecar.read_bytes())
            except (OSError, VoxamError) as error:
                print(f"voxam: the picture file cannot be read: {error}\n")

                return None

    return None


def _gallery(blorb: Blorb | None) -> "Gallery | None":
    """The Blorb's art as a gallery, when it brought any.

    None -- no Blorb, or one with no drawable pictures -- keeps
    the frontend's picture claim honest (§11.1.4).
    """

    if blorb is None:
        return None

    gallery = blorb.gallery()

    return gallery if gallery.count else None


def _screen_frontend(
    version: int, blorb: Blorb | None = None
) -> "ScreenFrontend | None":
    """A painted frontend, when the glass and the extra allow.

    The screen frontend wants a real terminal to paint on and the
    blessed package the `screen` extra installs; missing either,
    the caller falls back to the plain stream, which is always
    there. A Blorb with sounds may also bring a speaker along --
    see _speaker for what that takes.
    """

    if not sys.stdout.isatty():
        return None

    try:
        # Imported here because the blessed extra is optional: the
        # plain stream must keep working without it.
        from voxam.painter import ScreenFrontend  # noqa: PLC0415
    except ImportError:
        return None

    return ScreenFrontend(version, speaker=_speaker(blorb))


def _recorded_sources(
    recorder: Recorder | None,
    input_source: Callable[[], str] | None,
    key_source: Callable[[float | None], str | None] | None,
    timed_input_source: Callable[[float], str | None] | None = None,
    clicks: Callable[[], tuple[int, int] | None] | None = None,
) -> tuple[
    Callable[[], str] | None,
    Callable[[float | None], str | None] | None,
    Callable[[float], str | None] | None,
]:
    """Tee every input seam through the recorder, when there is one.

    Without an input source of its own, a recorded session records
    the built-in prompt the machine would fall back to anyway. The
    clicks seam is the glass's own click_position, so a recorded
    click carries the coordinates the story was told.
    """

    if recorder is None:
        return input_source, key_source, timed_input_source

    lines = _recorded_lines(
        recorder, input_source if input_source is not None else input
    )
    keys = (
        key_source
        if key_source is None
        else _recorded_keys(recorder, key_source, clicks)
    )
    ticks = (
        timed_input_source
        if timed_input_source is None
        else _recorded_ticks(recorder, timed_input_source)
    )

    return lines, keys, ticks


def _recorded_lines(recorder: Recorder, source: Callable[[], str]) -> Callable[[], str]:
    """Tee typed lines into the recording on their way to the machine."""

    def _line() -> str:
        line = source()

        recorder.line(line)

        return line

    return _line


def _recorded_ticks(
    recorder: Recorder, source: Callable[[float], str | None]
) -> Callable[[float], str | None]:
    """Tee completed timed-read lines; an expiry is not a line."""

    def _tick(seconds: float) -> str | None:
        line = source(seconds)

        if line is not None:
            recorder.line(line)

        return line

    return _tick


def _recorded_keys(
    recorder: Recorder,
    source: Callable[[float | None], str | None],
    clicks: Callable[[], tuple[int, int] | None] | None = None,
) -> Callable[[float | None], str | None]:
    """Tee pressed keys; an expired timeout is nothing to record.

    A click records as its token -- single or double -- with the
    coordinates the glass reports, the same answer the machine is
    about to write into the header extension (§10.3.2). A click
    with no position is warned about loudly rather than handed to
    the key path, where its character would pass for printable
    Latin-1 text and record as a silently wrong command.
    """

    def _key(timeout: float | None) -> str | None:
        key = source(timeout)

        if key is None:
            return None

        if key in (CLICK, DOUBLE_CLICK):
            position = clicks() if clicks is not None else None

            if position is None:
                print("voxam: a click with no position; not recorded")
            elif key == DOUBLE_CLICK:
                recorder.double_click(*position)
            else:
                recorder.click(*position)
        else:
            recorder.key(key)

        return key

    return _key


def _speaker(blorb: Blorb | None) -> Speaker | None:
    """A speaker over the Blorb's sounds, when everything allows.

    Sound wants decodable AIFF resources, the sounddevice package
    the `sound` extra installs, and a real output device; missing
    any of them, play is silent -- a courtesy missed, never a gate
    closed (§9.1.2 lets the header say so honestly).
    """

    if blorb is None:
        return None

    try:
        sounds = blorb.sounds()
    except AIFFError as error:
        print(f"voxam: the sounds cannot be decoded: {error}\n")

        return None

    if not sounds:
        return None

    try:
        # Imported here because the sound extra is optional: the
        # screen must keep painting without it.
        import sounddevice  # noqa: PLC0415
    except ImportError:
        return None

    try:
        sounddevice.query_devices(kind="output")
    except (sounddevice.PortAudioError, ValueError):
        # No output device -- a headless box, a bare CI runner --
        # is silence, not failure.
        return None

    return Speaker(sounds, blorb.loops, open_sounddevice_stream)


# A Blorb may be the story itself (a packaged Exec resource) or a
# sidecar of pictures and sounds beside a plain story file. The
# .gblorb dress marks a packaged Glulx story, and .ulx a bare one.
BLORB_SUFFIXES = (".blb", ".blorb", ".zblorb", ".gblorb")


def _glulx_story(story_path: Path) -> GlulxStory | None:
    """The Glulx story a path holds; None when it holds none.

    A Blorb suffix answers by its GLUL Exec resource, any other
    file by its magic number -- so Z-code paths fall through to
    the Z-Machine loader untouched.

    Raises:
        GlulxStoryError: For a file that opens 'Glul' and then
            breaks the header's promises.
        OSError: For files that cannot be read.
    """

    if story_path.suffix.lower() in BLORB_SUFFIXES:
        packaged = Blorb.load(story_path).glulx

        return GlulxStory(packaged) if packaged is not None else None

    with story_path.open("rb") as handle:
        magic = handle.read(len(GLULX_MAGIC))

    if magic != GLULX_MAGIC:
        return None

    return GlulxStory.load(story_path)


def _glulx_resources(story_path: Path, resources: Path | None) -> Blorb | None:
    """The Blorb a Glulx session draws on, if any exists.

    A packaged story is its own resource file; a bare one takes
    the explicit path when given, or a like-named sidecar beside
    it -- the same convention the Z-Machine loader keeps.

    Raises:
        BlorbError: For an unusable resource file.
        OSError: For files that cannot be read.
    """

    if story_path.suffix.lower() in BLORB_SUFFIXES:
        return Blorb.load(story_path)

    if resources is not None:
        return Blorb.load(resources)

    for suffix in BLORB_SUFFIXES:
        sidecar = story_path.with_suffix(suffix)

        if sidecar.exists():
            return Blorb.load(sidecar)

    return None


def _serve_glkote(
    story_path: Path, story: GlulxStory, *, seed: int | None, resources: Path | None
) -> int:
    """Speak the GlkOte protocol for one story, both streams whole.

    The display at the far end sends init and events on stdin and
    reads update stanzas on stdout, so nothing else may print
    there -- no banner, no verdict, no title escape.
    """

    blorb = _glulx_resources(story_path, resources)
    frontend = GlkOteFrontend()
    library = Glk(frontend, resources=GlkResources(blorb))
    machine = GlulxMachine(story, seed=seed, glk=library)

    try:
        served = serve(machine, library, frontend, sys.stdin, sys.stdout)
    except OSError:
        # The pipe itself failed: no stream is left to answer on.
        return EXIT_UNUSABLE

    return EXIT_OK if served else EXIT_UNUSABLE


def _serve_web(
    story_path: Path,
    story: GlulxStory,
    *,
    seed: int | None,
    resources: Path | None,
    port: int,
) -> int:
    """Serve one story to the browser, under its own name.

    Unlike --glkote, stdout stays ours here: the banner has
    already spoken, and the serving line says where to point the
    browser.
    """

    blorb = _glulx_resources(story_path, resources)
    session = GlulxSession(story, GlkResources(blorb), seed=seed)
    caption = _titled(story_path, blorb)

    try:
        return serve_web(Face(session, caption), port)
    except OSError as error:
        # The port would not bind, most likely: say so plainly.
        print(f"voxam: {error}")

        return EXIT_UNUSABLE


def _serve_z_glkote(story: Story, blorb: Blorb | None, *, seed: int | None) -> int:
    """Speak the GlkOte protocol for one Z story, both streams whole."""

    frontend = z_fronted(story.header.version, GlkResources(blorb))

    try:
        served = serve_z(story, frontend, sys.stdin, sys.stdout, seed=seed)
    except OSError:
        # The pipe itself failed: no stream is left to answer on.
        return EXIT_UNUSABLE

    return EXIT_OK if served else EXIT_UNUSABLE


def _serve_z_web(
    story_path: Path, story: Story, blorb: Blorb | None, *, seed: int | None, port: int
) -> int:
    """Serve one Z story to the browser, under its own name.

    The catalog's courtesy holds here too: an Infocom story's tab
    wears its title, and a zblorb's record names it first.
    """

    session = ZSession(story, GlkResources(blorb), seed=seed)
    caption = _titled(story_path, blorb)

    try:
        return serve_web(Face(session, caption), port)
    except OSError as error:
        # The port would not bind, most likely: say so plainly.
        print(f"voxam: {error}")

        return EXIT_UNUSABLE


def _run_glulx(  # noqa: PLR0912, PLR0913 -- one knob per session seam
    story_path: Path,
    story: GlulxStory,
    *,
    seed: int | None,
    resources: Path | None,
    recorder: Recorder | None,
    trace: Path | None,
    input_source: Callable[[], str] | None = None,
    witness: Callable[[str], None] | None = None,
    click_source: Callable[[], tuple[int, int] | None] | None = None,
    link_source: Callable[[], int | None] | None = None,
    screen: bool = False,
    graphics: bool = False,
    glkote: bool = False,
    web: bool = False,
    port: int = WEB_PORT,
    zoom: float | None = None,
) -> int:
    """Run a Glulx story over a display.

    The checksum verdict is printed but does not gate the run: the
    verify opcode exists so a story can judge itself. An input
    source replaces the terminal -- the replay harness rides that
    seam -- and a recorder writes every live line as it is typed,
    the same acceptance grammar the Z-Machine records. Tracing is
    a Z-Machine session instrument still, declined by name rather
    than half-working.

    With graphics asked for, a live session gets the pygame
    window; with screen allowed, one at a real terminal gets the
    terminal glass -- a recording included either way, riding the
    painted display's own seams so real keystrokes land in the
    script as key tokens. A replay arrives as an input source and
    keeps the stdio display, whose lines are what the grammar
    speaks.
    """

    if trace is not None:
        if recorder is not None:
            recorder.close()

        print(
            "voxam: tracing is a Z-Machine session instrument for "
            "now; a Glulx session runs without it"
        )

        return EXIT_UNUSABLE

    if glkote:
        # No banner, no title escape: from here, stdout carries
        # stanzas and nothing else.
        return _serve_glkote(story_path, story, seed=seed, resources=resources)

    if web:
        return _serve_web(story_path, story, seed=seed, resources=resources, port=port)

    verdict = "checksum verified" if story.verify() else "CHECKSUM MISMATCH"

    print(f"Running {story_path.name}: Glulx {story.version}, {verdict}\n")

    blorb = _glulx_resources(story_path, resources)
    # The record's courtesy: a story whose gblorb names it plays
    # under its own name, in the terminal's title bar and the
    # window's alike.
    caption = _titled(story_path, blorb)

    _entitle_terminal(caption)

    # A replay arrives as an input source and keeps the stdio
    # display; a live session earns a glass, recorder and all --
    # the pygame window when asked for, the terminal otherwise.
    painted: PaintedFrontend | None = None

    if input_source is None:
        if graphics:
            painted = _glass_frontend(
                blorb, zoom=zoom, recorder=recorder, title=caption
            )

        if painted is None and screen:
            painted = _terminal_frontend(blorb, recorder=recorder)

    if painted is None and recorder is not None and input_source is None:
        # Recording at the stdio display: every typed line goes
        # onto the page as it is typed. A replayed prefix arrives
        # as an input source instead, and stays off the page -- it
        # is already there.
        input_source = _recorded_lines(recorder, input)
    frontend: GlkFrontend = (
        painted
        if painted is not None
        else StdioFrontend(
            input_source=input_source,
            witness=witness,
            click_source=click_source,
            link_source=link_source,
        )
    )

    if painted is not None:
        # The story deserves a clean glass: anything the shell left
        # on screen would otherwise show through every row the game
        # has not yet painted.
        painted.clear()

    library = Glk(frontend, resources=GlkResources(blorb))
    machine = GlulxMachine(story, seed=seed, glk=library)

    try:
        machine.run()
    except (OSError, VoxamError) as error:
        print(f"\nvoxam: {error}")

        return EXIT_UNUSABLE
    finally:
        if painted is not None:
            # A looping sound would otherwise play on past quit:
            # the session ends, the speaker falls silent with it.
            painted.hush()

        if recorder is not None:
            recorder.close()

    # A story that ends with quit rather than glk_exit never asked
    # for a last flush; whatever its windows still hold is shown on
    # the way out.
    library.frontend.flush(library.root)

    if painted is not None:
        # The shell's next prompt belongs under the story, not
        # somewhere mid-screen where the cursor was parked.
        painted.retire()

    print()

    return EXIT_OK


def _glass_frontend(
    blorb: Blorb | None = None,
    *,
    zoom: float | None = None,
    recorder: Recorder | None = None,
    title: str | None = None,
) -> "GlassFrontend | None":
    """A pygame-windowed Glk display, when the graphics extra allows.

    The flag was explicit, so a missing extra earns a note before
    the session falls back to the terminal glass or the stream.
    The Blorb's Reso chunk shapes the window as it does for the
    Z-Machine, a recorder rides the same seams the terminal glass
    offers, and a Blorb with sounds may bring a speaker along --
    see _speaker for what that takes.
    """

    try:
        # Imported here because the graphics extra is optional; the
        # ImportError itself rises from opening the window.
        from voxam.glulx.glk.glass import GlassFrontend  # noqa: PLC0415

        standard = (
            (blorb.resolution.width, blorb.resolution.height)
            if blorb is not None and blorb.resolution is not None
            else None
        )
        on_line = on_key = on_click = on_link = None

        if recorder is not None:
            on_line, on_key, on_click, on_link = _recorded_glk(recorder)

        return GlassFrontend(
            standard=standard,
            zoom=zoom,
            speaker=_speaker(blorb),
            title=title,
            on_line=on_line,
            on_key=on_key,
            on_click=on_click,
            on_link=on_link,
        )
    except ImportError:
        print(
            "voxam: the graphics window needs the pygame-ce extra "
            "(voxam[graphics]); staying with the terminal\n"
        )

        return None


def _terminal_frontend(
    blorb: Blorb | None = None, recorder: Recorder | None = None
) -> "TerminalFrontend | None":
    """A painted Glk display, when the glass and the extra allow.

    The painted display wants a real terminal to paint on and the
    blessed package the `screen` extra installs; missing either,
    the caller falls back to the stdio display, which is always
    there. A Blorb with sounds may also bring a speaker along --
    see _speaker for what that takes -- and a recorder rides the
    glass's input seams, hearing lines and keystrokes as the
    display accepts them.
    """

    if not sys.stdout.isatty():
        return None

    try:
        # Imported here because the blessed extra is optional: the
        # stdio display must keep working without it.
        from voxam.glulx.glk.terminal import TerminalFrontend  # noqa: PLC0415
    except ImportError:
        return None

    on_line = on_key = None

    if recorder is not None:
        # The terminal glass has no pointer, so the click and
        # link seams stay unwired here.
        on_line, on_key, _, _ = _recorded_glk(recorder)

    return TerminalFrontend(speaker=_speaker(blorb), on_line=on_line, on_key=on_key)


# The Glk keycodes the acceptance grammar can spell, as the input
# characters their tokens replay through -- the same §3.8.4 and
# §3.8.2.6 alphabet the Z-Machine's key seam records, so one
# recorded <up> presses up on either machine. Return maps to the
# newline the recorder turns into the grammar's bare prompt.
GLK_KEY_CHARACTERS = {
    KeyCode.UP: "\x81",
    KeyCode.DOWN: "\x82",
    KeyCode.LEFT: "\x83",
    KeyCode.RIGHT: "\x84",
    KeyCode.ESCAPE: "\x1b",
    KeyCode.RETURN: "\n",
}


def _recorded_glk(
    recorder: Recorder,
) -> tuple[
    Callable[[str, int], None],
    Callable[[int], None],
    Callable[[int, int], None],
    Callable[[int], None],
]:
    """The glass's recording seams, bridged onto the grammar.

    Lines record as lines. Keystrokes translate to the grammar's
    key alphabet where a token exists, pass as themselves where
    they are ordinary characters, and warn loudly where the
    grammar has no spelling -- the same rule the Z-Machine's key
    seam keeps. A terminator-ended line records plain, with a
    warning, because the grammar cannot spell the terminator.
    Clicks record as <click x y> and link selections as <link n>,
    each carrying exactly what the game itself was told -- what a
    replay must feed back.
    """

    def line(text: str, terminator: int) -> None:
        if terminator:
            print(
                "voxam: a terminator key ended the line; the "
                "grammar cannot spell it, so the line records plain"
            )

        recorder.line(text)

    def key(code: int) -> None:
        character = GLK_KEY_CHARACTERS.get(code)

        if character is not None:
            recorder.key(character)
        elif code <= sys.maxunicode:
            recorder.key(chr(code))
        else:
            print(f"voxam: key 0x{code:X} has no token in the grammar; not recorded")

    def click(x: int, y: int) -> None:
        recorder.click(x, y)

    def link(value: int) -> None:
        recorder.link(value)

    return line, key, click, link


def _load_story(story_path: Path, resources: Path | None) -> tuple[Story, Blorb | None]:
    """Load a story and whatever resources belong to it.

    A path with a Blorb suffix must carry a packaged story; any
    other path loads as a story file, with resources taken from
    the explicit path when given, or a like-named Blorb beside the
    story when one exists.

    Raises:
        BlorbError: For an unusable resource file, or a Blorb
            story path with no packaged story inside.
        VoxamError: For an unusable story file.
        OSError: For files that cannot be read.
    """

    if story_path.suffix.lower() in BLORB_SUFFIXES:
        blorb = Blorb.load(story_path)
        packaged = blorb.story

        if packaged is None:
            msg = f"{story_path.name} packages no Z-code story to run"

            raise BlorbError(msg)

        return Story(packaged), blorb

    story = Story.load(story_path)

    if resources is not None:
        return story, Blorb.load(resources)

    for suffix in BLORB_SUFFIXES:
        sidecar = story_path.with_suffix(suffix)

        if sidecar.exists():
            return story, Blorb.load(sidecar)

    return story, None


def _present_resources(
    blorb: Blorb | None,
    story: Story,
    painted: "ScreenFrontend | GraphicsFrontend | None",
    *,
    pixels: bool,
) -> None:
    """Announce a Blorb at the banner, and show its cover.

    The identity check warns and plays on -- the spec asks for an
    error but allows the user to press on (Blorb: Game Identifier
    Chunk), and a warning is both at once. The cover shows only at
    a painted terminal.
    """

    if blorb is None:
        return

    print(f"Resources: {blorb.described()}\n")

    if not blorb.matches(story):
        print("voxam: the resource file names a different story\n")

    if painted is not None:
        # The record's card, the bibliography WinFrotz shows in
        # its own little window -- at a painted terminal only,
        # the cover's own rule: a plain stream is the
        # machine-readable face, and a record may quote anything,
        # ">"-prefixed sample commands included, which would
        # desynchronize any harness that frames output by the
        # prompt (Babel: The iFiction format).
        record = ifiction(blorb.ifiction) if blorb.ifiction is not None else None

        if record is not None:
            for _, text in carded(record):
                print(text, end="")

        _show_cover(blorb, painted, pixels=pixels)


def _show_cover(
    blorb: Blorb,
    frontend: "ScreenFrontend | GraphicsFrontend",
    *,
    pixels: bool = False,
) -> None:
    """Show the Blorb's cover picture before play, when there is one.

    Cover art is a courtesy, never a gate: a cover Voxam cannot
    draw -- Zork 1's JPEG, an exotic PNG -- earns a note and the
    story plays on. Infocom's own interpreters opened this way:
    the art, a keypress, the story.
    """

    cover = blorb.cover

    if cover is None:
        return

    if cover.chunk.chunk_id != PNG_ID:
        kind = cover.chunk.chunk_id.decode("latin-1").strip()
        print(f"voxam: the cover picture is {kind}, which Voxam cannot draw\n")

        return

    try:
        picture = decode(cover.chunk.payload)
    except PNGError as error:
        print(f"voxam: the cover picture cannot be drawn: {error}\n")

        return

    frontend.show_frontispiece(picture, pixels=pixels)


def _tracing(
    trace: Path | None,
) -> tuple[Callable[[Memory, Instruction], None] | None, Callable[[], None]]:
    """Open the execution-trace seam; inert without --trace.

    Returns the machine's witness -- None when no trace was asked
    for -- and a closer that writes the tallies and shuts the file.

    Raises:
        OSError: If the trace file cannot be opened for writing.
    """

    if trace is None:
        return None, lambda: None

    sink = trace.open("w", encoding="utf-8", newline="\n")
    tracer = Tracer(sink.write)

    print(f"Tracing to {trace}")

    def close() -> None:
        tracer.close()
        sink.close()

    return tracer.see, close


def _play(  # noqa: PLR0911, PLR0912, PLR0913, PLR0915 -- one knob per session seam
    story_path: Path,
    seed: int | None,
    input_source: Callable[[], str] | None,
    frontend: Frontend | None = None,
    *,
    screen: bool = False,
    graphics: bool = False,
    glkote: bool = False,
    web: bool = False,
    port: int = WEB_PORT,
    identity: Identity | None = None,
    resources: Path | None = None,
    pixels: bool = False,
    zoom: float | None = None,
    recorder: Recorder | None = None,
    trace: Path | None = None,
    click_source: Callable[[], tuple[int, int] | None] | None = None,
) -> int:
    """Load and run one story, mapping outcomes to exit codes.

    With screen requested, a painted frontend is used when the
    terminal is real and the blessed extra is installed; otherwise
    play falls back to the plain stream. A story may arrive as a
    Blorb carrying an Exec resource, and a plain story may have a
    sidecar Blorb found beside it by name or given explicitly.
    With a recorder, every line and key on its way to the machine
    is also written to the script being recorded. With a trace,
    every instruction the machine executes is also written there,
    rendered as the listing renders it.
    """

    try:
        glulx = _glulx_story(story_path)

        if glulx is not None:
            return _run_glulx(
                story_path,
                glulx,
                seed=seed,
                resources=resources,
                recorder=recorder,
                trace=trace,
                input_source=input_source,
                screen=screen,
                graphics=graphics,
                glkote=glkote,
                web=web,
                port=port,
                zoom=zoom,
            )

        if _aamachine_story(story_path):
            return _run_aamachine(
                story_path,
                seed=seed,
                recorder=recorder,
                trace=trace,
                input_source=input_source,
                glkote=glkote,
                web=web,
                port=port,
                screen=screen,
            )

        story, blorb = _load_story(story_path, resources)
        witness, close_trace = _tracing(trace)
    except (OSError, VoxamError) as error:
        print(f"voxam: {error}")

        return EXIT_UNUSABLE

    header = story.header

    if glkote or web:
        if web:
            return _serve_z_web(story_path, story, blorb, seed=seed, port=port)

        return _serve_z_glkote(story, blorb, seed=seed)

    key_source: Callable[[float | None], str | None] | None = None
    timed_input_source: Callable[[float], str | None] | None = None
    painted: ScreenFrontend | GraphicsFrontend | None = None
    # The catalog's courtesy: an Infocom story plays under its own
    # name, in the terminal's title bar and the window's alike.
    caption = _titled(story_path)

    _entitle_terminal(caption)

    if frontend is None and graphics:
        painted = _graphics_frontend(
            header.version, blorb, zoom, story_path, title=caption
        )

    if frontend is None and painted is None and screen:
        painted = _screen_frontend(header.version, blorb)

    if frontend is None and painted is not None:
        frontend = painted
        input_source = painted.read_line
        key_source = painted.read_key
        # The live half of §15 timed line reads: the painted
        # frontends wait a read's own interval on the wall clock,
        # which is what lets Border Zone's clock tick between
        # keystrokes. Scripted sessions never set this, keeping
        # the patient typist and byte-identical replays.
        timed_input_source = painted.read_line_until

    input_source, key_source, timed_input_source = _recorded_sources(
        recorder,
        input_source,
        key_source,
        timed_input_source,
        clicks=painted.click_position if painted is not None else None,
    )

    print(
        f"Running {story_path.name}: release {header.release}, "
        f"serial {header.serial_number} (z{header.version})\n"
    )

    _present_resources(blorb, story, painted, pixels=pixels)

    if painted is not None:
        # The story deserves a clean glass: anything the shell left
        # on screen would otherwise show through every row the game
        # has not yet painted.
        painted.clear()

    # Saved games live beside the story: zork1.z3 saves to zork1.sav.
    saves = FileSaveSlot(story_path.with_suffix(".sav"))
    # So do the session files: the SCRIPT command's transcript in
    # zork1.scr, the command script and its playback in zork1.cmd
    # (§7.1.1, §7.1.2.3, §10.2). Nothing is created unless the game
    # asks.
    scribe = FileScribe(story_path.with_suffix(".scr"), story_path.with_suffix(".cmd"))

    try:
        machine = Machine(
            story,
            frontend,
            input_source=input_source,
            seed=seed,
            saves=saves,
            key_source=key_source,
            identity=identity,
            timed_input_source=timed_input_source,
            witness=witness,
            scribe=scribe,
            click_source=click_source,
        )

        if painted is not None:
            # While the player thinks at a prompt, the painter's
            # idle heartbeat lets an ended sound's routine fire
            # (§9.4.4) instead of waiting for the next keystroke.
            painted.idle = machine.poll_sound

        machine.run()
    except EOFError:
        print("\nvoxam: end of input")

        return EXIT_OK
    except VoxamError as error:
        print(f"\nvoxam: {error}")

        return EXIT_UNUSABLE
    finally:
        if painted is not None:
            # A looping sound would otherwise play on past quit:
            # the session ends, the speaker falls silent with it.
            painted.stop_sound(None)

        if recorder is not None:
            recorder.close()

        scribe.close()
        close_trace()

    print()

    return EXIT_OK
