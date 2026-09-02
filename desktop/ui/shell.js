/* The desktop bridge: GlkOte in a Tauri webview, the machine on
   the far side of a pipe. The Rust core owns the child process;
   this file owns the ordering -- listeners before spawn, spawn
   before init -- and the page's own furniture (landing, ended
   bar, the story picker).

   Reload is restart: the chosen story lives in the Rust core and
   survives the page, exactly the web face's semantics. */

"use strict";

var invoke = window.__TAURI__.core.invoke;
var listen = window.__TAURI__.event.listen;
var dialog = window.__TAURI__.dialog;

/* Deliveries arriving before start_session resolves park here:
   the session id they must be filtered against is its return
   value, but a pre-wire refusal can outrun it. */
var sessionId = null;
var pending = [];
var faulted = false;
var opened = false;

/* The Display menu's words, spelled as CSS: the faces are stacks,
   the measures are column widths. */
var FACES = {
  serif: 'Palatino, Georgia, "Times New Roman", Times, serif',
  sans: '"Segoe UI", Helvetica, Arial, sans-serif',
  mono: 'Consolas, "Courier New", monospace'
};
var MEASURES = {
  narrow: "700px",
  standard: "900px",
  wide: "1200px",
  full: "100%"
};

/* The picker's story shapes; All files rides behind them so a
   renamed story is never unreachable. */
var FILTERS = [
  { name: "Stories", extensions: [
      "z1", "z2", "z3", "z4", "z5", "z6", "z7", "z8",
      "zblorb", "zlb", "ulx", "gblorb", "glb", "blorb", "blb"] },
  { name: "All files", extensions: ["*"] }
];

/* The file prompt's shapes, one per protocol filetype; All files
   rides behind each, since a player's old save may wear any name. */
var PROMPTED = {
  save: { name: "Saved games", extensions: ["glksave", "sav"] },
  transcript: { name: "Transcripts", extensions: ["txt", "log"] },
  command: { name: "Command records", extensions: ["txt", "rec"] },
  data: { name: "Data files", extensions: ["glkdata", "dat"] }
};

/* The working light, raised while the machine has the turn and
   lowered by whatever comes back. The delay is the whole point:
   an ordinary turn answers long before it expires, so the chip
   never flashes, and a story that really is thinking gets to say
   so rather than looking dead. */
var WORKING_DELAY = 600;
var workingTimer = null;
var workingTick = null;

function working(thinking) {
  var chip = document.getElementById("working");
  var counter = document.getElementById("working-for");
  var began = Date.now();

  function tell() {
    if (counter) {
      counter.textContent = " " + Math.round((Date.now() - began) / 1000) + "s";
    }
  }

  if (thinking) {
    if (workingTimer === null) {
      workingTimer = setTimeout(function() {
        if (chip) chip.setAttribute("data-shown", "");
        tell();
        workingTick = setInterval(tell, 1000);
      }, WORKING_DELAY);
    }

    return;
  }

  if (workingTimer !== null) {
    clearTimeout(workingTimer);
    workingTimer = null;
  }

  if (workingTick !== null) {
    clearInterval(workingTick);
    workingTick = null;
  }

  if (chip) chip.removeAttribute("data-shown");
  if (counter) counter.textContent = "";
}

var Game = {
  /* Every GlkOte event becomes one line down the pipe. Rejections
     are swallowed: glkote.js hardcodes timer support, and a timer
     or arrange can still fire after the child has ended. Pictures
     arrive inline as data: urls in the updates themselves, so the
     shell owes no Blorb interface and no picture road. */
  accept: function(event) {
    working(true);
    invoke("send_stanza", { line: JSON.stringify(event) }).catch(function() {});
  },
  Dialog: {
    /* glkote.js asks whether the Dialog needs initing; a native
       picker has nothing to init. */
    inited: function() { return true; },

    /* The protocol's file prompt answered with a real picker over
       the very filesystem the interpreter writes: the chosen path
       travels back verbatim as the specialresponse value -- the
       machine side takes a plain string, and anything else reads
       as the cancel it is. This is the desktop's own power; the
       browser face cannot reach the player's disk. */
    open: function(tosave, usage, gameid, callback) {
      var shaped = PROMPTED[usage];
      var filters = shaped
        ? [shaped, { name: "All files", extensions: ["*"] }]
        : [{ name: "All files", extensions: ["*"] }];
      var asked = tosave
        ? dialog.save({ filters: filters })
        : dialog.open({ filters: filters });

      asked.then(function(path) {
        callback(path || null);
      }).catch(function() {
        callback(null);
      });
    }
  }
};
window.Game = Game;

/* A finished play reports back down the same pipe every other
   event takes. */
VoxamAudio.start(function(event) { Game.accept(event); });

/* The picker starts at the stories' own home -- a pinned folder,
   or the last story's -- so a save to some other corner of the
   disk never drags the story picker after it. */
function chooseStory() {
  invoke("story_home").then(function(home) {
    var asked = { filters: FILTERS };

    if (home) asked.defaultPath = home;

    return dialog.open(asked);
  }).then(function(path) {
    if (!path) return;

    invoke("set_story", { path: path }).then(function() {
      location.reload();
    });
  });
}

/* Dress the page in the settings' word, then poke a resize so
   GlkOte re-measures its metrics -- the machines take the new
   arrangement live, no restart owed. Pre-init the poke is a
   harmless no-op; the dress still paints the landing. */
function dressed(display) {
  var root = document.documentElement.style;

  root.setProperty("--story-face", FACES[display.face] || FACES.serif);
  root.setProperty("--story-size", display.size + "px");
  root.setProperty("--grid-size", (display.size - 1) + "px");
  root.setProperty("--measure", MEASURES[display.measure] || MEASURES.standard);
  document.documentElement.dataset.theme = display.theme;

  window.dispatchEvent(new Event("resize"));
}

function stranded(message) {
  document.getElementById("loadingpane").style.display = "none";
  document.getElementById("note").textContent = message;
  document.getElementById("landing").style.display = "flex";
}

function deliver(kind, payload) {
  if (sessionId === null) {
    pending.push([kind, payload]);
    return;
  }

  /* A dead session's last words: the reload that replaced it
     attached fresh listeners before its pumps wound down. */
  if (payload.id !== sessionId) return;

  /* Whatever arrived, the machine has stopped thinking. */
  working(false);

  if (kind === "stanza") {
    /* Sounds ride the update in VOXAM's own dialect; the audio
       module reads them before GlkOte draws the rest. */
    VoxamAudio.update(payload.stanza);
    GlkOte.update(payload.stanza);
  } else if (kind === "fault") {
    /* Refusals and crashes both land in GlkOte's error pane,
       which is plain DOM and safe before init has ever run. */
    faulted = true;
    document.getElementById("loadingpane").style.display = "none";
    GlkOte.error(payload.text);
  } else if (kind === "ended" && !faulted) {
    /* The vendored glkote.js ignores the update's exit flag, so
       this bar is the only end-of-story signal the player gets. */
    document.getElementById("endedbar").style.display = "block";
  }
}

window.addEventListener("DOMContentLoaded", function() {
  document.getElementById("open").addEventListener("click", chooseStory);
  document.getElementById("reopen").addEventListener("click", chooseStory);

  listen("menu-open", chooseStory);
  listen("menu-restart", function() {
    if (opened) location.reload();
  });
  listen("menu-home", function() {
    dialog.open({ directory: true }).then(function(path) {
      if (path) invoke("set_home", { path: path });
    });
  });
  listen("menu-follow", function() {
    invoke("set_home", { path: null });
  });
  listen("display", function(event) {
    dressed(event.payload);
  });

  /* The dress arrives before the story: GlkOte's init measures
     the page, so the page must already wear its type and ink. */
  invoke("display_settings").then(function(display) {
    dressed(display);

    return invoke("current_story");
  }).then(function(story) {
    if (!story) return;

    opened = true;
    document.getElementById("landing").style.display = "none";

    /* listen() registers over IPC and resolves later; awaiting all
       three before the spawn is what keeps an instant refusal line
       from being emitted into the void. */
    Promise.all([
      listen("stanza", function(event) { deliver("stanza", event.payload); }),
      listen("fault", function(event) { deliver("fault", event.payload); }),
      listen("ended", function(event) { deliver("ended", event.payload); })
    ]).then(function() {
      return invoke("start_session");
    }).then(function(id) {
      sessionId = id;

      var parked = pending;
      pending = [];
      parked.forEach(function(entry) { deliver(entry[0], entry[1]); });

      /* A fault that beat the id here means the story never stood
         up; init would only send its stanza into a dead pipe. */
      if (!faulted) GlkOte.init();
    }).catch(function(message) {
      stranded(String(message));
    });
  });
});
