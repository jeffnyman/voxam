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

/* The picker's story shapes; All files rides behind them so a
   renamed story is never unreachable. */
var FILTERS = [
  { name: "Stories", extensions: [
      "z1", "z2", "z3", "z4", "z5", "z6", "z7", "z8",
      "zblorb", "zlb", "ulx", "gblorb", "glb", "blorb", "blb"] },
  { name: "All files", extensions: ["*"] }
];

var Game = {
  /* Every GlkOte event becomes one line down the pipe. Rejections
     are swallowed: glkote.js hardcodes timer support, and a timer
     or arrange can still fire after the child has ended. */
  accept: function(event) {
    invoke("send_stanza", { line: JSON.stringify(event) }).catch(function() {});
  },
  Blorb: {
    /* No pictures on the desktop yet -- a named road. Graphics
       windows still paint their color fills. */
    get_image_url: function(number) { return null; }
  }
};
window.Game = Game;

function chooseStory() {
  dialog.open({ filters: FILTERS }).then(function(path) {
    if (!path) return;

    invoke("set_story", { path: path }).then(function() {
      location.reload();
    });
  });
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

  if (kind === "stanza") {
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

  invoke("current_story").then(function(story) {
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
