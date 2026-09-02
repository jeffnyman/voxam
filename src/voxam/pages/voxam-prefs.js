/* The preferences panel, shared by both faces that wear this page.
 *
 * The browser tab and the desktop shell render the same GlkOte
 * display and dress it through the same custom properties, so the
 * panel that sets them is written once and copied to both. Only
 * the keeping differs: a tab keeps its choices in localStorage, the
 * shell hands them to its Rust side to write beside the app's own
 * config. That is the one seam install() asks a face to fill.
 *
 * The panel builds its own markup and carries its own stylesheet,
 * so a face adds it with one script tag and one install call, and
 * neither page holds a copy of the other's furniture.
 */

var VoxamPrefs = (function () {
  "use strict";

  /* The type a story is set in. Three families rather than a font
   * list, until the face can offer the real one. */
  var FACES = {
    serif: 'Palatino, Georgia, "Times New Roman", Times, serif',
    sans: '"Segoe UI", Helvetica, Arial, sans-serif',
    mono: 'Consolas, "Courier New", monospace'
  };

  /* The measure of the column, which is the setting that matters
   * most to a reader and the one no terminal can offer. */
  var MEASURES = {
    narrow: "700px",
    standard: "900px",
    wide: "1200px",
    full: "100%"
  };

  /* Every knob, in the order the panel shows them. The ink comes
   * first because it is the one people reach for. */
  var AXES = [
    {
      key: "theme",
      label: "Ink",
      values: [
        ["system", "System"],
        ["paper", "Paper"],
        ["sepia", "Sepia"],
        ["dark", "Dark"],
        ["frotz", "Frotz"]
      ]
    },
    {
      key: "face",
      label: "Type",
      values: [
        ["serif", "Serif"],
        ["sans", "Sans"],
        ["mono", "Typewriter"]
      ]
    },
    {
      key: "size",
      label: "Size",
      values: [
        ["12", "12"],
        ["15", "15"],
        ["18", "18"],
        ["21", "21"],
        ["24", "24"]
      ]
    },
    {
      key: "measure",
      label: "Measure",
      values: [
        ["narrow", "Narrow"],
        ["standard", "Standard"],
        ["wide", "Wide"],
        ["full", "Full"]
      ]
    }
  ];

  var DEFAULTS = {
    theme: "system",
    face: "serif",
    size: 15,
    measure: "standard"
  };

  /* The panel wears the story's own ink, so it never arrives as a
   * white card over a dark page. */
  var STYLE = [
    "#voxam-prefs[hidden] { display: none; }",
    "#voxam-prefs {",
    "  position: fixed;",
    "  inset: 0;",
    "  z-index: 40;",
    "  display: flex;",
    "  align-items: center;",
    "  justify-content: center;",
    "  background: rgba(0, 0, 0, 0.45);",
    "}",
    "#voxam-prefs-sheet {",
    "  background: var(--paper, #fff);",
    "  color: var(--ink, #000);",
    "  border: 1px solid var(--bar, #888);",
    "  border-radius: 6px;",
    "  padding: 1.1em 1.3em 1.2em;",
    "  min-width: 17em;",
    "  box-shadow: 0 10px 40px rgba(0, 0, 0, 0.35);",
    "  font-family: system-ui, sans-serif;",
    "  font-size: 14px;",
    "}",
    "#voxam-prefs-sheet h2 {",
    "  margin: 0 0 0.9em;",
    "  font-size: 1.05em;",
    "  letter-spacing: 0.06em;",
    "  text-transform: uppercase;",
    "  opacity: 0.75;",
    "}",
    "#voxam-prefs-sheet label {",
    "  display: flex;",
    "  align-items: center;",
    "  justify-content: space-between;",
    "  gap: 1.4em;",
    "  margin-bottom: 0.6em;",
    "}",
    "#voxam-prefs-sheet select {",
    "  font: inherit;",
    "  color: inherit;",
    "  background: transparent;",
    "  border: 1px solid var(--bar, #888);",
    "  border-radius: 4px;",
    "  padding: 0.2em 0.4em;",
    "  min-width: 8em;",
    "}",
    "#voxam-prefs-sheet select option {",
    "  color: initial;",
    "  background: initial;",
    "}",
    "#voxam-prefs-done {",
    "  font: inherit;",
    "  margin-top: 0.9em;",
    "  padding: 0.4em 1.4em;",
    "  border-radius: 4px;",
    "  cursor: pointer;",
    "}",
    "#voxam-prefs-open {",
    "  position: fixed;",
    "  bottom: 8px;",
    "  right: 10px;",
    "  z-index: 20;",
    "  font: inherit;",
    "  font-size: 12px;",
    "  letter-spacing: 0.06em;",
    "  color: var(--band-ink, #fff);",
    "  background: var(--band, #333);",
    "  border: 0;",
    "  border-radius: 4px;",
    "  padding: 5px 11px;",
    "  opacity: 0.7;",
    "  cursor: pointer;",
    "  transition: opacity 0.15s ease;",
    "}",
    "#voxam-prefs-open:hover,",
    "#voxam-prefs-open:focus {",
    "  opacity: 1;",
    "}"
  ].join("\n");

  var settings = null;
  var keeper = null;
  var panel = null;

  /* One stored object, with anything missing or unknown answered
   * by the default: a settings file from an older version, or a
   * hand-edited one, dresses the page rather than breaking it. */
  function sound(stored) {
    var chosen = {};

    AXES.forEach(function (axis) {
      var value = stored ? stored[axis.key] : undefined;
      var known = axis.values.some(function (pair) {
        return pair[0] === String(value);
      });

      chosen[axis.key] = known ? value : DEFAULTS[axis.key];
    });

    chosen.size = parseInt(chosen.size, 10) || DEFAULTS.size;

    return chosen;
  }

  /* Wear a settings object: the properties the page's own rules
   * read, and the ink stamped on the root where the CSS looks. */
  function apply(chosen) {
    var root = document.documentElement.style;

    root.setProperty("--story-face", FACES[chosen.face] || FACES.serif);
    root.setProperty("--story-size", chosen.size + "px");
    root.setProperty("--grid-size", chosen.size - 1 + "px");
    root.setProperty(
      "--measure",
      MEASURES[chosen.measure] || MEASURES.standard
    );
    document.documentElement.dataset.theme = chosen.theme;

    /* GlkOte measures the window in characters, so a change of type
     * or measure is a change of geometry and the display has to be
     * told to look again. */
    window.dispatchEvent(new Event("resize"));
  }

  function build() {
    var style = document.createElement("style");

    style.textContent = STYLE;
    document.head.appendChild(style);

    var opener = document.createElement("button");

    opener.id = "voxam-prefs-open";
    opener.type = "button";
    opener.textContent = "Aa";
    opener.title = "Preferences";
    opener.setAttribute("aria-label", "Preferences");
    opener.addEventListener("click", open);

    panel = document.createElement("div");
    panel.id = "voxam-prefs";
    panel.hidden = true;

    var sheet = document.createElement("div");

    sheet.id = "voxam-prefs-sheet";
    sheet.setAttribute("role", "dialog");
    sheet.setAttribute("aria-modal", "true");
    sheet.setAttribute("aria-label", "Preferences");

    var title = document.createElement("h2");

    title.textContent = "Preferences";
    sheet.appendChild(title);

    AXES.forEach(function (axis) {
      var row = document.createElement("label");
      var name = document.createElement("span");
      var pick = document.createElement("select");

      name.textContent = axis.label;

      axis.values.forEach(function (pair) {
        var option = document.createElement("option");

        option.value = pair[0];
        option.textContent = pair[1];
        pick.appendChild(option);
      });

      pick.value = String(settings[axis.key]);
      pick.addEventListener("change", function () {
        settings[axis.key] =
          axis.key === "size" ? parseInt(pick.value, 10) : pick.value;
        apply(settings);
        keeper.save(settings);
      });

      row.appendChild(name);
      row.appendChild(pick);
      sheet.appendChild(row);
    });

    var done = document.createElement("button");

    done.id = "voxam-prefs-done";
    done.type = "button";
    done.textContent = "Done";
    done.addEventListener("click", close);
    sheet.appendChild(done);

    panel.appendChild(sheet);

    /* A click on the ground behind the sheet closes it, the way a
     * dialog everywhere else does. */
    panel.addEventListener("click", function (event) {
      if (event.target === panel) close();
    });

    document.body.appendChild(opener);
    document.body.appendChild(panel);
  }

  function open() {
    if (!panel) return;

    panel.hidden = false;

    var first = panel.querySelector("select");

    if (first) first.focus();
  }

  function close() {
    if (panel) panel.hidden = true;
  }

  /* Escape closes it, which is the one keystroke every reader
   * tries. The game's own keyboard is GlkOte's while the panel is
   * shut, so the listener only acts when it is open. */
  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && panel && !panel.hidden) {
      event.stopPropagation();
      close();
    }
  });

  /* The seam: a face says how its choices are read and kept, and
   * gets the panel. Loading may take a round trip (the shell asks
   * its Rust side), so it answers a promise. */
  function install(face) {
    keeper = face;

    return Promise.resolve(face.load()).then(function (stored) {
      settings = sound(stored);
      apply(settings);

      /* A second install re-dresses the page and takes the new
         keeper, but never builds a second panel: two would share
         one set of ids, and the older one would answer for both. */
      if (!panel) build();

      return settings;
    });
  }

  return {
    install: install,
    open: open,
    close: close,
    apply: apply,
    sound: sound,
    defaults: DEFAULTS,
    faces: FACES,
    measures: MEASURES
  };
})();
