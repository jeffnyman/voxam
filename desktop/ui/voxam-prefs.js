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

  /* The type a story is set in. The two Voxam faces travel with
   * the package, so they read the same on every machine; the three
   * families after them are whatever this one happens to have. */
  var FACES = {
    "voxam-serif": '"Voxam Serif", Palatino, Georgia, serif',
    "voxam-mono": '"Voxam Mono", Consolas, "Courier New", monospace',
    serif: 'Palatino, Georgia, "Times New Roman", Times, serif',
    sans: '"Segoe UI", Helvetica, Arial, sans-serif',
    mono: 'Consolas, "Courier New", monospace'
  };

  /* The measure of the column, counted in characters rather than
   * pixels, which is what a measure has always meant. A fixed
   * pixel width means a different line length in every face, and
   * shortens the line each time a reader asks for larger type;
   * counting characters holds the line steady through both.
   *
   * The top of the range is the old "full": no cap at all, the
   * column taking the whole window. */
  var FULL = 141;
  var MEASURE_FLOOR = 45;

  /* What the four named widths measured, in the default serif, so
   * a reader who chose one before keeps the column they had. */
  var NAMED_MEASURES = { narrow: 76, standard: 98, wide: 130, full: FULL };

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
        ["frotz", "Frotz"],
        ["custom", "Custom"]
      ]
    },
    {
      key: "face",
      label: "Type",
      values: [
        ["voxam-serif", "Voxam Serif"],
        ["voxam-mono", "Voxam Mono"],
        ["serif", "Serif"],
        ["sans", "Sans"],
        ["mono", "Typewriter"],
        ["named", "Named..."]
      ]
    },
  ];

  /* The knobs that answer a number rather than a word. Each says
   * what property it writes, in what unit, and how to say its
   * value back to a reader who is looking at the words and not at
   * the CSS. */
  var RANGES = [
    {
      key: "size",
      label: "Size",
      property: "--story-size",
      min: 11,
      max: 32,
      step: 1,
      unit: "px",
      shown: function (value) {
        return value + " px";
      }
    },
    {
      key: "measure",
      label: "Measure",
      min: MEASURE_FLOOR,
      max: FULL,
      step: 1,
      shown: function (value) {
        return value >= FULL ? "Full" : value + " chars";
      }
    },
    {
      key: "leading",
      label: "Line spacing",
      property: "--leading",
      min: 1.1,
      max: 2.2,
      step: 0.05,
      unit: "",
      shown: function (value) {
        return Number(value).toFixed(2);
      }
    },
    {
      key: "letters",
      label: "Letter spacing",
      property: "--letters",
      min: -0.02,
      max: 0.16,
      step: 0.005,
      unit: "em",
      shown: function (value) {
        return Number(value).toFixed(3) + " em";
      }
    },
    {
      key: "words",
      label: "Word spacing",
      property: "--words",
      min: 0,
      max: 0.5,
      step: 0.02,
      unit: "em",
      shown: function (value) {
        return Number(value).toFixed(2) + " em";
      }
    }
  ];

  /* The colours a reader can name outright, in the order the
   * panel offers them: the story first, then the two bands that
   * carry §8.7's reverse video and §8.2's status line, then the
   * accents. --quote is not among them, because every ink sets it
   * as a translucent wash and a colour input speaks only in solid
   * #rrggbb. It follows whichever preset the custom ink was mixed
   * from. */
  var COLORS = [
    ["paper", "Story paper"],
    ["ink", "Story ink"],
    ["bar", "Status bar"],
    ["bar-ink", "Status text"],
    ["band", "Reverse paper"],
    ["band-ink", "Reverse ink"],
    ["link", "Links"],
    ["page", "Surround"]
  ];

  var DEFAULTS = {
    theme: "system",
    face: "voxam-serif",
    named: "",
    size: 15,
    measure: 98,
    leading: 1.4,
    letters: 0,
    words: 0,
    colors: {}
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
    "  max-height: 82vh;",
    "  overflow-y: auto;",
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
    "#voxam-prefs-named[hidden] { display: none; }",
    "#voxam-prefs-sheet input[type=text] {",
    "  font: inherit;",
    "  color: inherit;",
    "  background: transparent;",
    "  border: 1px solid var(--bar, #888);",
    "  border-radius: 4px;",
    "  padding: 0.2em 0.4em;",
    "  width: 9em;",
    "}",
    "#voxam-prefs-sheet input[type=range] {",
    "  width: 9em;",
    "  accent-color: var(--link, #1a5fb4);",
    "}",
    "#voxam-prefs-sheet .voxam-prefs-reading {",
    "  margin-left: auto;",
    "  margin-right: 0.7em;",
    "  font-style: normal;",
    "  font-variant-numeric: tabular-nums;",
    "  opacity: 0.6;",
    "}",
    "#voxam-prefs-colors[hidden] { display: none; }",
    "#voxam-prefs-colors {",
    "  margin-top: 0.9em;",
    "  padding-top: 0.8em;",
    "  border-top: 1px solid var(--bar, #888);",
    "}",
    "#voxam-prefs-sheet input[type=color] {",
    "  width: 8em;",
    "  height: 1.7em;",
    "  padding: 0;",
    "  border: 1px solid var(--bar, #888);",
    "  border-radius: 4px;",
    "  background: transparent;",
    "  cursor: pointer;",
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

    RANGES.forEach(function (range) {
      var value = Number(stored ? stored[range.key] : NaN);

      if (range.key === "measure" && stored && NAMED_MEASURES[stored.measure]) {
        /* The measure was a word before it was a number. */
        value = NAMED_MEASURES[stored.measure];
      }

      chosen[range.key] =
        isFinite(value) && value >= range.min && value <= range.max
          ? value
          : DEFAULTS[range.key];
    });

    chosen.named =
      stored && typeof stored.named === "string" ? stored.named.slice(0, 120) : "";
    chosen.colors = {};

    COLORS.forEach(function (pair) {
      var mixed = stored && stored.colors ? stored.colors[pair[0]] : null;

      if (/^#[0-9a-f]{6}$/i.test(mixed)) chosen.colors[pair[0]] = mixed;
    });

    return chosen;
  }

  /* Wear a settings object: the properties the page's own rules
   * read, and the ink stamped on the root where the CSS looks. */
  function apply(chosen) {
    var root = document.documentElement.style;

    root.setProperty("--story-face", stack(chosen));
    root.setProperty("--grid-size", chosen.size - 1 + "px");
    root.setProperty(
      "--measure",
      chosen.measure >= FULL ? "100%" : chosen.measure + "ch"
    );

    RANGES.forEach(function (range) {
      if (range.property) {
        root.setProperty(range.property, chosen[range.key] + range.unit);
      }
    });
    document.documentElement.dataset.theme = chosen.theme;

    COLORS.forEach(function (pair) {
      var mixed = chosen.theme === "custom" && chosen.colors[pair[0]];

      if (mixed) {
        root.setProperty("--" + pair[0], mixed);
      } else {
        root.removeProperty("--" + pair[0]);
      }
    });

    /* GlkOte measures the window in characters, so a change of type
     * or measure is a change of geometry and the display has to be
     * told to look again. */
    window.dispatchEvent(new Event("resize"));
  }

  /* The face, as a CSS stack. A named one keeps a generic behind
   * it, so a name this machine has never heard of leaves the story
   * readable rather than fontless. */
  function stack(chosen) {
    if (chosen.face === "named" && chosen.named) {
      return '"' + chosen.named.replace(/["\\]/g, "") + '", serif';
    }

    return FACES[chosen.face] || FACES.serif;
  }

  /* Whether this machine actually has a face by that name.
   *
   * A webview cannot be asked for the list of installed fonts --
   * the one API that does is in a single engine, and Voxam's two
   * faces meet three -- so the question is answered the way it has
   * always been answered: set a probe string in the candidate over
   * a known generic, and see whether the width moves. A name that
   * resolves to nothing falls back to the generic and measures
   * exactly like it.
   */
  function installed(name) {
    if (!name) return false;

    var probe = document.createElement("canvas").getContext("2d");
    var sample = "mmmmmmmmmmlliWWWQQ0123";
    var clean = '"' + name.replace(/["\\]/g, "") + '"';

    return ["monospace", "serif", "sans-serif"].some(function (generic) {
      probe.font = "72px " + generic;

      var bare = probe.measureText(sample).width;

      probe.font = "72px " + clean + ", " + generic;

      return probe.measureText(sample).width !== bare;
    });
  }

  function hexed(value) {
    var probe = document.createElement("span");

    probe.style.color = value;
    probe.style.display = "none";
    document.body.appendChild(probe);

    var resolved = getComputedStyle(probe).color.match(/\d+/g);

    document.body.removeChild(probe);

    if (!resolved) return "#000000";

    return (
      "#" +
      resolved
        .slice(0, 3)
        .map(function (part) {
          return ("0" + parseInt(part, 10).toString(16)).slice(-2);
        })
        .join("")
    );
  }

  /* The ink as it stands, so mixing your own begins from whatever
   * you were just reading rather than from black on white. */
  function sampled() {
    var worn = getComputedStyle(document.documentElement);
    var found = {};

    COLORS.forEach(function (pair) {
      found[pair[0]] = hexed(worn.getPropertyValue("--" + pair[0]).trim());
    });

    return found;
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

        /* Mixing your own begins from the ink you were reading, so
           Custom opens on the page as it stands rather than on a
           blank black-on-white. A ink already mixed is kept. */
        if (
          axis.key === "theme" &&
          pick.value === "custom" &&
          !Object.keys(settings.colors).length
        ) {
          settings.colors = sampled();
          swatches();
        }

        apply(settings);
        keeper.save(settings);

        revealed();
      });

      row.appendChild(name);
      row.appendChild(pick);
      sheet.appendChild(row);

      if (axis.key === "face") sheet.appendChild(naming());
    });

    RANGES.forEach(function (range) {
      var row = document.createElement("label");
      var name = document.createElement("span");
      var slide = document.createElement("input");
      var reading = document.createElement("em");

      name.textContent = range.label;
      slide.type = "range";
      slide.min = range.min;
      slide.max = range.max;
      slide.step = range.step;
      slide.value = settings[range.key];
      reading.className = "voxam-prefs-reading";
      reading.textContent = range.shown(settings[range.key]);

      slide.addEventListener("input", function () {
        settings[range.key] = Number(slide.value);
        reading.textContent = range.shown(settings[range.key]);
        apply(settings);
        keeper.save(settings);
      });

      row.appendChild(name);
      row.appendChild(reading);
      row.appendChild(slide);
      sheet.appendChild(row);
    });

    var mixer = document.createElement("div");

    mixer.id = "voxam-prefs-colors";

    COLORS.forEach(function (pair) {
      var row = document.createElement("label");
      var name = document.createElement("span");
      var well = document.createElement("input");

      name.textContent = pair[1];
      well.type = "color";
      well.dataset.colour = pair[0];
      well.addEventListener("input", function () {
        settings.colors[pair[0]] = well.value;
        apply(settings);
        keeper.save(settings);
      });

      row.appendChild(name);
      row.appendChild(well);
      mixer.appendChild(row);
    });

    sheet.appendChild(mixer);

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
    revealed();
  }

  /* The name of a face this machine already has. There is no list
   * to offer, so there is a field to type into and an honest word
   * back about whether the name found anything. */
  function naming() {
    var row = document.createElement("label");
    var name = document.createElement("span");
    var field = document.createElement("input");
    var verdict = document.createElement("em");

    row.id = "voxam-prefs-named";
    name.textContent = "Font name";
    field.type = "text";
    field.id = "voxam-prefs-name";
    field.placeholder = "Iosevka, Charter...";
    field.spellcheck = false;
    field.value = settings.named;
    verdict.className = "voxam-prefs-reading";

    function judged() {
      verdict.textContent = !settings.named
        ? ""
        : installed(settings.named)
          ? "found"
          : "not on this system";
    }

    field.addEventListener("input", function () {
      settings.named = field.value.slice(0, 120);
      judged();
      apply(settings);
      keeper.save(settings);
    });

    judged();
    row.appendChild(name);
    row.appendChild(verdict);
    row.appendChild(field);

    return row;
  }

  /* The wells show the ink they will change, which matters most
   * the moment Custom is chosen and they are filled from the
   * preset that was showing. */
  function swatches() {
    if (!panel) return;

    var mixed = settings.theme === "custom" ? settings.colors : sampled();

    panel.querySelectorAll("input[type=color]").forEach(function (well) {
      var value = mixed[well.dataset.colour];

      if (value) well.value = value;
    });
  }

  function revealed() {
    if (!panel) return;

    panel.querySelector("#voxam-prefs-colors").hidden =
      settings.theme !== "custom";
    panel.querySelector("#voxam-prefs-named").hidden = settings.face !== "named";
    swatches();
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
    faces: FACES
  };
})();
