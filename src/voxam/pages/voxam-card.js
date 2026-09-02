/* The story's iFiction card, shared by both faces that wear this page.
 *
 * The bibliography a story carries about itself: its title, its
 * headline, its author, and the blurb from the back of the box.
 * The painted faces show this at the door, in the story's own
 * text, because a terminal has nowhere else to put it. A face
 * with windows can do better, and this is that better: a button
 * beside the preferences opener, and a little sheet over the
 * story when a reader asks for it.
 *
 * The card arrives on the wire, in the sidecar block an update
 * carries, rather than travelling with the page. That is the one
 * road for both faces: the browser tab fetches its updates over
 * HTTP and the desktop shell reads them off a pipe, but the
 * stanza is the same stanza, so the card is read in one place and
 * dressed by one file. It comes exactly once, on the first real
 * update of a session, because a story's bibliography cannot
 * change while it runs.
 *
 * A story that says nothing about itself sends no card, and no
 * button is ever built. The module carries its own stylesheet and
 * builds its own markup, so a face adds it with one script tag
 * and one update call.
 */

var VoxamCard = (function () {
  "use strict";

  var STYLE = [
    "#voxam-card[hidden] { display: none; }",
    "#voxam-card {",
    "  position: fixed;",
    "  inset: 0;",
    "  z-index: 40;",
    "  display: flex;",
    "  align-items: center;",
    "  justify-content: center;",
    "  background: rgba(0, 0, 0, 0.45);",
    "}",
    "#voxam-card-sheet {",
    "  background: var(--paper);",
    "  color: var(--ink);",
    "  border: 1px solid var(--bar);",
    "  border-radius: 6px;",
    "  box-shadow: 0 10px 40px rgba(0, 0, 0, 0.35);",
    "  padding: 1.4em 1.6em 1.5em;",
    "  max-width: 34em;",
    "  max-height: 80vh;",
    "  overflow-y: auto;",
    "}",
    "#voxam-card-sheet h2 { margin: 0; font-size: 1.5em; }",
    "#voxam-card-sheet .headline,",
    "#voxam-card-sheet .author {",
    "  margin: 0.2em 0 0;",
    "  font-style: italic;",
    "  opacity: 0.85;",
    "}",
    "#voxam-card-sheet p.blurb { margin: 1em 0 0; line-height: var(--leading); }",
    /* The button takes the page's own ink rather than the
       browser's: a default control is white-on-grey whatever the
       sheet behind it is wearing, which reads as a hole in a dark
       theme. */
    "#voxam-card-done {",
    "  font: inherit;",
    "  margin-top: 1.3em;",
    "  padding: 0.4em 1.4em;",
    "  border-radius: 4px;",
    "  cursor: pointer;",
    "  color: var(--band-ink);",
    "  background: var(--band);",
    "  border: 1px solid var(--bar);",
    "}",
    /* The opener sits beside the preferences opener, in the same
       dress, because they are the same kind of door. */
    "#voxam-card-open {",
    "  position: fixed;",
    "  bottom: 12px;",
    "  right: 84px;",
    "  z-index: 20;",
    "  font-family: system-ui, sans-serif;",
    "  font-size: 15px;",
    "  line-height: 1;",
    "  color: var(--band-ink);",
    "  background: var(--band);",
    "  border: 1px solid var(--paper);",
    "  border-radius: 7px;",
    "  padding: 11px 14px;",
    "  opacity: 0.82;",
    "  cursor: pointer;",
    "  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);",
    "  transition: opacity 0.15s ease;",
    "}",
    "#voxam-card-open:hover,",
    "#voxam-card-open:focus { opacity: 1; }"
  ].join("\n");

  /* Built once, on the card's arrival, and never again: a second
   * card would mean a second story, which is a reload. */
  var standing = false;

  function line(sheet, tag, className, words) {
    if (!words) return;

    var node = document.createElement(tag);

    if (className) node.className = className;

    node.textContent = words;
    sheet.appendChild(node);
  }

  function build(card) {
    var style = document.createElement("style");
    var opener = document.createElement("button");
    var shade = document.createElement("div");
    var sheet = document.createElement("div");
    var done = document.createElement("button");

    style.textContent = STYLE;
    document.head.appendChild(style);

    opener.id = "voxam-card-open";
    opener.type = "button";
    opener.textContent = "iFiction Card";
    opener.title = "What the story's record says about itself";

    shade.id = "voxam-card";
    shade.hidden = true;

    sheet.id = "voxam-card-sheet";
    sheet.setAttribute("role", "dialog");
    sheet.setAttribute("aria-modal", "true");
    sheet.setAttribute("aria-label", "iFiction card");

    line(sheet, "h2", "", card.title);
    line(sheet, "p", "headline", card.headline);
    line(sheet, "p", "author", card.author);

    /* The blurb's paragraphs are the record's own breaks. The
       wrapping inside one belonged to the box the copy was set
       on, and was left behind at the parser. */
    (card.description || "").split("\n").forEach(function (paragraph) {
      line(sheet, "p", "blurb", paragraph);
    });

    done.id = "voxam-card-done";
    done.type = "button";
    done.textContent = "Close";
    sheet.appendChild(done);

    function show() {
      shade.hidden = false;
      done.focus();
    }

    function hide() {
      shade.hidden = true;
    }

    opener.addEventListener("click", show);
    done.addEventListener("click", hide);
    shade.addEventListener("click", function (event) {
      if (event.target === shade) hide();
    });

    /* Escape closes the sheet and goes no further: the story
       below is listening for keys too, and a dismissed window is
       not a keystroke the game asked for. */
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && !shade.hidden) {
        event.stopPropagation();
        hide();
      }
    });

    shade.appendChild(sheet);
    document.body.appendChild(opener);
    document.body.appendChild(shade);
  }

  return {
    /* Every update passes through here on its way to GlkOte. Only
     * one of them will ever carry a card, and anything that is
     * not an update carries none. */
    update: function (stanza) {
      if (standing || !stanza || !stanza.voxam || !stanza.voxam.card) return;

      standing = true;
      build(stanza.voxam.card);
    }
  };
})();
