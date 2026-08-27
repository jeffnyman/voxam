"""The browser face: GlkOte served over HTTP, one turn per POST.

The same seams --glkote speaks over stdio, spoken over the wire
the display library itself was designed for: "the Game.accept call
is a single HTTP request -- and the data structure is a single
HTTP response" (GlkOte: The Application's Life Story). The server
is the standard library's, single-threaded on purpose -- one
story, one session, every request in its turn -- and the page it
serves carries the vendored GlkOte display, shipped inside the
package the way the window icons are.

A browser reload sends a fresh init, and a fresh init rebuilds
the whole session from the already-parsed story: reloading the
page restarts the game, which is exactly what a reload should
mean.
"""

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from importlib import resources as importlib_resources

from voxam.blorb import PNG_ID
from voxam.errors import VoxamError
from voxam.glkote import Stanza
from voxam.glulx.glk.api import Glk
from voxam.glulx.glk.glkote import GlkOteFrontend
from voxam.glulx.glk.resources import Resources
from voxam.glulx.machine import Machine
from voxam.glulx.story import Story
from voxam.zmachine.glkote import ADVANCE, STAND
from voxam.zmachine.glkote import GlkOteFrontend as ZGlkOteFrontend
from voxam.zmachine.glkote import fronted as z_fronted
from voxam.zmachine.machine import Machine as ZMachine
from voxam.zmachine.story import Story as ZStory

# What each shipped page file is, on the wire.
CONTENT_TYPES = {
    "index.html": "text/html; charset=utf-8",
    "glkote.css": "text/css",
    "glkote.js": "text/javascript",
    "voxam-audio.js": "text/javascript",
    "jquery-1.12.4.min.js": "text/javascript",
    "waiting.gif": "image/gif",
}

# The assets a browser may ask for by name; the license rides in
# the package but is nobody's fetch.
_SERVED = frozenset(CONTENT_TYPES) - {"index.html"}

_HTTP_OK = 200
_HTTP_NOT_FOUND = 404

_PICT_ROAD = "/pict/"


class Session:
    """One story's life behind the server, init to exit.

    Every init event -- the page's first breath, and every reload
    after -- builds a fresh frontend, library, and machine from
    the parsed story; the resources are kept, their image cache
    being pure memoization. A session whose machine faulted stays
    faulted, answering the same error until a reload starts over.
    """

    # The mark the browser tab wears: each machine's own window
    # icon, exactly as the pygame title bars wear them.
    icon: str

    def __init__(self, resources: Resources, *, seed: int | None = None) -> None:
        """Hold what every session shares; a subclass holds the story."""

        self._seed = seed
        self.resources = resources
        self._fault: Stanza | None = None

    def answer(self, stanza: Stanza) -> Stanza:
        """One event in, one stanza out: the burst model's turn.

        An init rebuilds the session; anything else lands on the
        machine standing suspended. A fault answers as the
        protocol's own error stanza and keeps answering so until
        the next init.
        """

        try:
            if stanza.get("type") == "init":
                self._fault = None

                return self._reborn(stanza)

            if self._fault is not None:
                return self._fault

            return self._delivered(stanza)
        except VoxamError as error:
            self._fault = {"type": "error", "message": f"voxam: {error}"}

            return self._fault

    def _reborn(self, stanza: Stanza) -> Stanza:
        """Start the story over, fresh objects from the kept story."""

        raise NotImplementedError  # pragma: no cover -- each machine's own

    def _delivered(self, stanza: Stanza) -> Stanza:
        """Deliver one event to the suspended machine and run on."""

        raise NotImplementedError  # pragma: no cover -- each machine's own

    @staticmethod
    def _unopened() -> Stanza:
        """The answer to an event before any init has spoken."""

        return {
            "type": "error",
            "message": "voxam: the conversation opens with an init event",
        }


class GlulxSession(Session):
    """A Glulx story behind the server, over the Glk library."""

    icon = "glulx.ico"

    def __init__(
        self, story: Story, resources: Resources, *, seed: int | None = None
    ) -> None:
        """Hold the story, ready to be born at the first init."""

        super().__init__(resources, seed=seed)

        self._story = story
        self._frontend: GlkOteFrontend | None = None
        self._glk: Glk | None = None
        self._machine: Machine | None = None

    def _reborn(self, stanza: Stanza) -> Stanza:
        self._frontend = GlkOteFrontend()
        self._glk = Glk(self._frontend, resources=self.resources)
        self._machine = Machine(self._story, seed=self._seed, glk=self._glk)

        self._frontend.begin(stanza)

        return self._turned()

    def _delivered(self, stanza: Stanza) -> Stanza:
        if self._frontend is None or self._glk is None or self._machine is None:
            return self._unopened()

        event = self._frontend.accept(stanza)

        if event is not None:
            self._glk.deliver_event(event)

            return self._turned()

        if self._glk.waiting is None:
            # The stanza itself completed the wait: a file answer
            # stores through the parked call.
            return self._turned()

        return {"type": "pass"}

    def _turned(self) -> Stanza:
        """Run the machine to its next wait and render the update."""

        if (
            self._machine is None or self._frontend is None
        ):  # pragma: no cover -- both callers just built or checked them
            raise AssertionError

        self._machine.run()

        return self._frontend.render(exit=not self._machine.running)


class ZSession(Session):
    """A Z-Machine story behind the server, over the screen model."""

    def __init__(
        self, story: ZStory, resources: Resources, *, seed: int | None = None
    ) -> None:
        """Hold the story, ready to be born at the first init."""

        super().__init__(resources, seed=seed)

        self.icon = f"z{story.header.version}.ico"
        self._story = story
        self._frontend: ZGlkOteFrontend | None = None
        self._machine: ZMachine | None = None

    def _reborn(self, stanza: Stanza) -> Stanza:
        self._frontend = z_fronted(self._story.header.version, self.resources)

        self._frontend.begin(stanza)

        self._machine = ZMachine(self._story, self._frontend, seed=self._seed)
        self._frontend.machine = self._machine

        return self._turned()

    def _delivered(self, stanza: Stanza) -> Stanza:
        if self._frontend is None or self._machine is None:
            return self._unopened()

        verdict = self._frontend.accept(stanza)

        if verdict == ADVANCE:
            return self._turned()

        if verdict == STAND:
            return self._frontend.render()

        return {"type": "pass"}

    def _turned(self) -> Stanza:
        """Run the machine to its next wait and render the update."""

        if (
            self._machine is None or self._frontend is None
        ):  # pragma: no cover -- both callers just built or checked them
            raise AssertionError

        self._machine.run()

        return self._frontend.render(exit=not self._machine.running)


class Face:
    """The request surface, socket-free and testable whole.

    Every route answers as (status, content type, payload); the
    handler shell below only carries those onto the wire.
    """

    def __init__(self, session: Session, caption: str | None) -> None:
        """Front one session, under the story's own name."""

        self.session = session
        self.caption = caption if caption is not None else "Voxam"

    def respond(self, method: str, path: str, body: bytes) -> tuple[int, str, bytes]:
        """Answer one request, whatever road it asks for."""

        if method == "POST" and path == "/event":
            return self._event(body)

        if method == "GET":
            if path == "/":
                return self._index()

            if path == "/favicon.ico":
                return (_HTTP_OK, "image/x-icon", _icon(self.session.icon))

            name = path.lstrip("/")

            if name in _SERVED:
                return (_HTTP_OK, CONTENT_TYPES[name], _page(name))

            if path.startswith(_PICT_ROAD):
                return self._pict(path[len(_PICT_ROAD) :])

        return (_HTTP_NOT_FOUND, "text/plain", b"voxam: no such road")

    def _index(self) -> tuple[int, str, bytes]:
        """The page itself, wearing the story's name."""

        page = _page("index.html").decode("utf-8")

        return (
            _HTTP_OK,
            CONTENT_TYPES["index.html"],
            page.replace("VOXAM_TITLE", self.caption).encode("utf-8"),
        )

    def _pict(self, tail: str) -> tuple[int, str, bytes]:
        """One Blorb picture by number; a placeholder is no picture."""

        found = self.session.resources.image(int(tail)) if tail.isdigit() else None

        if found is None:
            return (_HTTP_NOT_FOUND, "text/plain", b"voxam: no such picture")

        kind = "image/png" if found.kind == PNG_ID else "image/jpeg"

        return (_HTTP_OK, kind, found.data)

    def _event(self, body: bytes) -> tuple[int, str, bytes]:
        """One turn: the event in the body, the update in the answer.

        Even what is not JSON answers 200 with the protocol's
        error stanza -- the display renders that far better than a
        bare status ever would.
        """

        try:
            stanza = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            answered: Stanza = {
                "type": "error",
                "message": f"voxam: not JSON: {error}",
            }
        else:
            if isinstance(stanza, dict):
                answered = self.session.answer(stanza)
            else:
                answered = {
                    "type": "error",
                    "message": "voxam: a stanza is a JSON object",
                }

        return (
            _HTTP_OK,
            "application/json",
            json.dumps(answered, separators=(",", ":")).encode("utf-8"),
        )


class _Handler(BaseHTTPRequestHandler):
    """The thin shell between the socket and the Face."""

    face: Face

    def do_GET(self) -> None:
        self._answer(*self.face.respond("GET", self.path, b""))

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))

        self._answer(*self.face.respond("POST", self.path, self.rfile.read(length)))

    def _answer(self, status: int, kind: str, payload: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(payload)))
        # Without an explicit answer the browser caches assets
        # heuristically, and a tab can keep serving last week's
        # display against this week's server -- a mismatch that
        # reads as mystery breakage, never as staleness.
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        """Silence the stdlib's per-request stderr chatter."""


def webbed(face: Face, port: int) -> HTTPServer:
    """A server for one Face, bound to localhost and ready to run."""

    handler = type("_Bound", (_Handler,), {"face": face})

    return HTTPServer(("127.0.0.1", port), handler)


def serve_web(face: Face, port: int) -> int:
    """Serve one session until the player is done.

    Ctrl+C is how a server session ends on purpose; it comes back
    as a clean exit, the way quit ends a terminal session.
    """

    server = webbed(face, port)

    try:
        print(
            f"voxam: serving {face.caption} at "
            f"http://127.0.0.1:{server.server_port} (Ctrl+C to stop)"
        )

        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

    return 0


def _page(name: str) -> bytes:
    """One shipped page file, read from inside the package."""

    return (importlib_resources.files("voxam") / "pages" / name).read_bytes()


def _icon(name: str) -> bytes:
    """One shipped window icon, the same file the title bars wear."""

    return (importlib_resources.files("voxam") / "icons" / name).read_bytes()
