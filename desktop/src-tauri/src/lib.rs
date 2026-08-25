//! The desktop shell's core: one child process speaking GlkOte.
//!
//! The webview wears the display; `voxam --glkote` owns the story.
//! This core spawns the child, pumps its stdout lines to the page
//! as events, and writes the page's events back down its stdin.
//! The contract with the child (voxam's cli.py): the child is
//! silent until sent the init stanza, flushes every line it
//! writes, prints pre-wire refusals as bare `voxam: ...` text,
//! and exits 0 on game over or EOF, 2 on a fault.

use std::io::{BufRead, BufReader, Read, Write};
use std::path::{Path, PathBuf};
use std::process::{Child, ChildStdin, Command, Stdio};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Mutex;

use serde_json::{json, Value};
use tauri::menu::{CheckMenuItem, IsMenuItem, Menu, MenuItem, PredefinedMenuItem, Submenu};
use tauri::{AppHandle, Emitter, Manager, RunEvent, State, Wry};

/// The friendly failure when voxam is not on PATH: the shell
/// finds voxam, it does not bundle it (yet -- a named road).
const NOT_FOUND: &str = "voxam is not on this machine's PATH.\n\n\
    Install it with:\n\n    uv tool install voxam\n\n\
    (or pipx install voxam, or pip install voxam). If it was\n\
    installed moments ago, sign out and back in so the PATH\n\
    refreshes for desktop apps.";

/// The screen's share the window opens at, as the pygame glass
/// takes it: 0.85 of the desktop, centered.
const SHARE: f64 = 0.85;

/// The §11.1.3 platforms the Story menu offers, shown by the
/// names Infocom used and passed by the names voxam's
/// `--interpreter` takes. Glulx stories ignore the claim, so the
/// spawn passes it unconditionally.
const PLATFORMS: [(&str, &str); 11] = [
    ("DECSystem-20", "dec-20"),
    ("Apple IIe", "apple-iie"),
    ("Macintosh", "macintosh"),
    ("Amiga", "amiga"),
    ("Atari ST", "atari-st"),
    ("IBM PC", "ibm-pc"),
    ("Commodore 128", "commodore-128"),
    ("Commodore 64", "commodore-64"),
    ("Apple IIc", "apple-iic"),
    ("Apple IIgs", "apple-iigs"),
    ("Tandy Color", "tandy-color"),
];

/// The identity the next machine boots with (§11.1.3-4): the
/// claimed platform and the legendary Tandy bit. IBM PC to begin,
/// since that is the number voxam claims on its own.
#[derive(Clone)]
struct Claim {
    interpreter: String,
    tandy: bool,
}

impl Default for Claim {
    fn default() -> Self {
        Self {
            interpreter: "ibm-pc".to_string(),
            tandy: false,
        }
    }
}

/// One Display menu group: its shown title, its settings word,
/// and its (label, value) options.
type DisplayGroup = (
    &'static str,
    &'static str,
    &'static [(&'static str, &'static str)],
);

/// The Display menu's roster: each group a radio row, each value
/// the word the page's own dresser understands.
const DISPLAY_GROUPS: [DisplayGroup; 4] = [
    (
        "Type",
        "face",
        &[("Serif", "serif"), ("Sans", "sans"), ("Typewriter", "mono")],
    ),
    (
        "Size",
        "size",
        &[
            ("12", "12"),
            ("15", "15"),
            ("18", "18"),
            ("21", "21"),
            ("24", "24"),
        ],
    ),
    (
        "Ink",
        "theme",
        &[("Paper", "paper"), ("Sepia", "sepia"), ("Dark", "dark")],
    ),
    (
        "Measure",
        "measure",
        &[
            ("Narrow", "narrow"),
            ("Standard", "standard"),
            ("Wide", "wide"),
            ("Full", "full"),
        ],
    ),
];

/// How the page dresses itself: the face and size of the story's
/// type, the ink it is set in, and the measure of its column.
/// Persisted as display.json in the app's own config dir, so the
/// menu's checkmarks tell the truth at every startup.
#[derive(Clone, serde::Serialize, serde::Deserialize)]
struct Display {
    face: String,
    size: u32,
    theme: String,
    measure: String,
}

impl Default for Display {
    fn default() -> Self {
        Self {
            face: "serif".to_string(),
            size: 15,
            theme: "paper".to_string(),
            measure: "standard".to_string(),
        }
    }
}

impl Display {
    /// The chosen value of one menu group, for the checkmarks.
    fn value(&self, group: &str) -> String {
        match group {
            "face" => self.face.clone(),
            "size" => self.size.to_string(),
            "theme" => self.theme.clone(),
            _ => self.measure.clone(),
        }
    }
}

fn display_path(app: &AppHandle) -> Option<PathBuf> {
    app.path()
        .app_config_dir()
        .ok()
        .map(|dir| dir.join("display.json"))
}

fn load_display(app: &AppHandle) -> Display {
    display_path(app)
        .and_then(|path| std::fs::read_to_string(path).ok())
        .and_then(|held| serde_json::from_str(&held).ok())
        .unwrap_or_default()
}

/// Best effort: a display preference that cannot be kept is not
/// worth refusing the change over.
fn save_display(app: &AppHandle, display: &Display) {
    let Some(path) = display_path(app) else {
        return;
    };

    if let Some(dir) = path.parent() {
        let _ = std::fs::create_dir_all(dir);
    }

    if let Ok(held) = serde_json::to_string_pretty(display) {
        let _ = std::fs::write(path, held);
    }
}

/// The menus' own check items, kept so a choice can dress its
/// whole radio row and the toggle from the state's word.
struct Chrome {
    interpreters: Vec<(String, CheckMenuItem<Wry>)>,
    tandy: CheckMenuItem<Wry>,
    displays: Vec<(String, CheckMenuItem<Wry>)>,
}

/// One running story: the child and the stdin we kept out of it.
///
/// The stdout and stderr pipes are taken by the pump threads at
/// spawn; only stdin stays here, so send_stanza can write without
/// ever contending with the readers.
struct Session {
    id: u64,
    child: Child,
    stdin: ChildStdin,
}

#[derive(Default)]
struct Shell {
    session: Mutex<Option<Session>>,
    story: Mutex<Option<PathBuf>>,
    claim: Mutex<Claim>,
    display: Mutex<Display>,
    minted: AtomicU64,
}

/// Remember the chosen story and wear its name on the title bar.
#[tauri::command]
async fn set_story(app: AppHandle, state: State<'_, Shell>, path: String) -> Result<(), String> {
    let chosen = PathBuf::from(&path);
    let name = titled(&chosen);

    if let Some(window) = app.get_webview_window("main") {
        let _ = window.set_title(&format!("{name} \u{2014} Voxam"));
    }

    *state.story.lock().unwrap() = Some(chosen);

    Ok(())
}

/// The story's name under the Treaty of Babel, asked of voxam
/// itself -- `--babel` reports a Title line for any story a record
/// names -- with the filename's stem standing in for the nameless.
fn titled(story: &Path) -> String {
    let stem = story
        .file_stem()
        .map(|stem| stem.to_string_lossy().into_owned())
        .unwrap_or_else(|| "Voxam".to_string());

    let mut command = Command::new("voxam");

    command
        .arg("--babel")
        .arg(story)
        .env("PYTHONUTF8", "1")
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::null());

    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;

        command.creation_flags(0x0800_0000);
    }

    let Ok(output) = command.output() else {
        return stem;
    };

    for line in String::from_utf8_lossy(&output.stdout).lines() {
        if let Some(title) = line.strip_prefix("Title: ") {
            if !title.trim().is_empty() {
                return title.trim().to_string();
            }
        }
    }

    stem
}

/// The story the shell holds, surviving the page's reloads.
#[tauri::command]
async fn current_story(state: State<'_, Shell>) -> Result<Option<String>, String> {
    Ok(state
        .story
        .lock()
        .unwrap()
        .as_ref()
        .map(|path| path.to_string_lossy().into_owned()))
}

/// Spawn `voxam --glkote` on the held story and start the pumps.
///
/// Returns the minted session id; every event this session emits
/// carries it, so a reloaded page can ignore a dead session's
/// last words (the stale-ended race).
#[tauri::command]
async fn start_session(app: AppHandle, state: State<'_, Shell>) -> Result<u64, String> {
    let story = state
        .story
        .lock()
        .unwrap()
        .clone()
        .ok_or("no story has been chosen")?;

    let mut held = state.session.lock().unwrap();

    if let Some(mut old) = held.take() {
        let _ = old.child.kill();
        let _ = old.child.wait();
    }

    let id = state.minted.fetch_add(1, Ordering::SeqCst) + 1;

    let mut command = Command::new("voxam");

    // PYTHONUTF8 matters: voxam reconfigures its stdout to UTF-8
    // but not its stdin, and a Windows pipe would otherwise hand
    // typed input to the locale codec.
    command
        .arg("--glkote")
        .arg(&story)
        .env("PYTHONUTF8", "1")
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());

    // The Story menu's claim joins the boot (§11.1.3-4); a Glulx
    // story ignores it, so no story needs sniffing here.
    let claim = state.claim.lock().unwrap().clone();

    command.arg("--interpreter").arg(claim.interpreter);

    if claim.tandy {
        command.arg("--tandy");
    }

    // The parent being a windowed app does not stop a console
    // child from flashing its own console; CREATE_NO_WINDOW does.
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;

        command.creation_flags(0x0800_0000);
    }

    let mut child = command.spawn().map_err(|fault| {
        if fault.kind() == std::io::ErrorKind::NotFound {
            NOT_FOUND.to_string()
        } else {
            format!("voxam could not start: {fault}")
        }
    })?;

    let stdin = child.stdin.take().expect("stdin was piped");
    let stdout = child.stdout.take().expect("stdout was piped");
    let stderr = child.stderr.take().expect("stderr was piped");

    *held = Some(Session { id, child, stdin });
    drop(held);

    let pump = app.clone();

    std::thread::spawn(move || {
        let mut lines = BufReader::new(stdout);
        let mut line = String::new();

        loop {
            line.clear();

            match lines.read_line(&mut line) {
                Ok(0) | Err(_) => break,
                Ok(_) => {}
            }

            // Windows newline translation leaves \r on the line;
            // trimmed before the JSON test and the passthrough.
            let text = line.trim_end();

            if text.is_empty() {
                continue;
            }

            // A line that is not JSON is a pre-wire refusal, spoken
            // in voxam's own words; it travels as a fault verbatim.
            match serde_json::from_str::<Value>(text) {
                Ok(stanza) => {
                    let _ = pump.emit("stanza", json!({"id": id, "stanza": stanza}));
                }
                Err(_) => {
                    let _ = pump.emit("fault", json!({"id": id, "kind": "refusal", "text": text}));
                }
            }
        }

        // EOF: if this session is still the current one, reclaim it
        // to reap the exit code; a replaced session dies silently.
        let state = pump.state::<Shell>();
        let mut held = state.session.lock().unwrap();

        if held.as_ref().map(|session| session.id) == Some(id) {
            let mut session = held.take().expect("the id just matched");
            drop(held);

            let code = session
                .child
                .wait()
                .ok()
                .and_then(|status| status.code())
                .unwrap_or(-1);

            let _ = pump.emit("ended", json!({"id": id, "code": code}));
        }
    });

    let drain = app.clone();

    std::thread::spawn(move || {
        let mut stderr = stderr;
        let mut text = String::new();

        // One fault for the whole stream: a Python traceback is one
        // crash, not twenty lines of separate ones.
        if stderr.read_to_string(&mut text).is_ok() && !text.trim().is_empty() {
            let _ = drain.emit(
                "fault",
                json!({"id": id, "kind": "crash", "text": text.trim()}),
            );
        }
    });

    Ok(id)
}

/// The settings the page dresses in, asked at every load.
#[tauri::command]
async fn display_settings(state: State<'_, Shell>) -> Result<Display, String> {
    Ok(state.display.lock().unwrap().clone())
}

/// One GlkOte event down the pipe, on its own line, flushed.
#[tauri::command]
async fn send_stanza(state: State<'_, Shell>, line: String) -> Result<(), String> {
    let mut held = state.session.lock().unwrap();

    let session = held.as_mut().ok_or("no session is running")?;

    writeln!(session.stdin, "{line}")
        .and_then(|()| session.stdin.flush())
        .map_err(|fault| format!("the pipe failed: {fault}"))
}

pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .manage(Shell::default())
        .setup(|app| {
            let handle = app.handle();

            let open = MenuItem::with_id(
                handle,
                "open",
                "Open Story\u{2026}",
                true,
                Some("CmdOrCtrl+O"),
            )?;
            let restart =
                MenuItem::with_id(handle, "restart", "Restart Story", true, None::<&str>)?;
            let quit = PredefinedMenuItem::quit(handle, Some("Exit"))?;
            let file = Submenu::with_items(handle, "File", true, &[&open, &restart, &quit])?;

            // The Story menu: the §11.1.3 platform claim as a
            // radio row -- IBM PC checked first, the number voxam
            // claims on its own -- and the Tandy bit as a toggle.
            let claimed = app.state::<Shell>().claim.lock().unwrap().clone();
            let mut interpreters = Vec::new();

            for (shown, named) in PLATFORMS {
                interpreters.push((
                    named.to_string(),
                    CheckMenuItem::with_id(
                        handle,
                        format!("claim:{named}"),
                        shown,
                        true,
                        named == claimed.interpreter,
                        None::<&str>,
                    )?,
                ));
            }

            let row: Vec<&dyn IsMenuItem<Wry>> = interpreters
                .iter()
                .map(|(_, item)| item as &dyn IsMenuItem<Wry>)
                .collect();
            let platforms = Submenu::with_items(handle, "Interpreter", true, &row)?;
            let tandy = CheckMenuItem::with_id(
                handle,
                "tandy",
                "Tandy Header Bit",
                true,
                false,
                None::<&str>,
            )?;
            let story = Submenu::with_items(handle, "Story", true, &[&platforms, &tandy])?;

            // The Display menu: the persisted dress read first, so
            // every checkmark tells the truth at startup.
            let dressed = load_display(handle);

            *app.state::<Shell>().display.lock().unwrap() = dressed.clone();

            let mut displays = Vec::new();
            let mut groups = Vec::new();

            for (shown, group, options) in DISPLAY_GROUPS {
                let chosen = dressed.value(group);
                let start = displays.len();

                for (label, value) in options {
                    displays.push((
                        format!("{group}:{value}"),
                        CheckMenuItem::with_id(
                            handle,
                            format!("{group}:{value}"),
                            *label,
                            true,
                            *value == chosen,
                            None::<&str>,
                        )?,
                    ));
                }

                let row: Vec<&dyn IsMenuItem<Wry>> = displays[start..]
                    .iter()
                    .map(|(_, item)| item as &dyn IsMenuItem<Wry>)
                    .collect();

                groups.push(Submenu::with_items(handle, shown, true, &row)?);
            }

            let rows: Vec<&dyn IsMenuItem<Wry>> = groups
                .iter()
                .map(|group| group as &dyn IsMenuItem<Wry>)
                .collect();
            let display = Submenu::with_items(handle, "Display", true, &rows)?;
            let menu = Menu::with_items(handle, &[&file, &story, &display])?;

            app.set_menu(menu)?;
            app.manage(Chrome {
                interpreters,
                tandy,
                displays,
            });

            // The menu only signals; the page owns the flow, since
            // choosing and restarting both end in its reload. A
            // changed claim restarts the open story on the spot:
            // the identity is the booting machine's (§11.1.3), so
            // the checkmark never outruns the header.
            app.on_menu_event(|app, event| match event.id().as_ref() {
                "open" => {
                    let _ = app.emit("menu-open", ());
                }
                "restart" => {
                    let _ = app.emit("menu-restart", ());
                }
                "tandy" => {
                    let shell = app.state::<Shell>();
                    let mut claim = shell.claim.lock().unwrap();

                    claim.tandy = !claim.tandy;

                    let _ = app.state::<Chrome>().tandy.set_checked(claim.tandy);
                    drop(claim);

                    let _ = app.emit("menu-restart", ());
                }
                chose if chose.starts_with("claim:") => {
                    let wanted = chose["claim:".len()..].to_string();

                    app.state::<Shell>().claim.lock().unwrap().interpreter = wanted.clone();

                    for (value, item) in &app.state::<Chrome>().interpreters {
                        let _ = item.set_checked(*value == wanted);
                    }

                    let _ = app.emit("menu-restart", ());
                }
                chose if chose.contains(':') => {
                    // A Display choice: dress the state, keep it,
                    // fix the group's checkmarks, and tell the
                    // page -- which re-dresses live, no restart.
                    let (group, value) = chose.split_once(':').expect("the arm found a colon");
                    let shell = app.state::<Shell>();
                    let mut display = shell.display.lock().unwrap();

                    match group {
                        "face" => display.face = value.to_string(),
                        "size" => display.size = value.parse().unwrap_or(15),
                        "theme" => display.theme = value.to_string(),
                        _ => display.measure = value.to_string(),
                    }

                    let settings = display.clone();

                    drop(display);
                    save_display(app, &settings);

                    let fellows = format!("{group}:");

                    for (id, item) in &app.state::<Chrome>().displays {
                        if id.starts_with(&fellows) {
                            let _ = item.set_checked(id == chose);
                        }
                    }

                    let _ = app.emit("display", settings);
                }
                _ => {}
            });

            // The window opens as the pygame glass does: a share
            // of the screen, centered -- placed while hidden, then
            // shown, so it never flashes at the fallback size. The
            // show is unconditional: a screen that cannot be asked
            // still gets the config's own size.
            if let Some(window) = app.get_webview_window("main") {
                if let Ok(Some(monitor)) = window.primary_monitor() {
                    let size = monitor.size();

                    let _ = window.set_size(tauri::PhysicalSize::new(
                        (f64::from(size.width) * SHARE) as u32,
                        (f64::from(size.height) * SHARE) as u32,
                    ));
                    let _ = window.center();
                }

                let _ = window.show();
            }

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            set_story,
            current_story,
            start_session,
            send_stanza,
            display_settings
        ])
        .build(tauri::generate_context!())
        .expect("the shell could not be built")
        .run(|app, event| {
            // Exit fires exactly once on every way out; the child
            // is killed and reaped rather than orphaned. And if the
            // shell dies hard instead, the closing pipe EOFs the
            // child's stdin and voxam ends itself cleanly.
            if let RunEvent::Exit = event {
                let held = app.state::<Shell>().session.lock().unwrap().take();

                if let Some(mut session) = held {
                    let _ = session.child.kill();
                    let _ = session.child.wait();
                }
            }
        });
}
