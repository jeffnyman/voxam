//! The desktop shell's core: one child process speaking GlkOte.
//!
//! The webview wears the display; `voxam --glkote` owns the story.
//! This core spawns the child, pumps its stdout lines to the page
//! as events, and writes the page's events back down its stdin.
//! The contract with the child (voxam's cli.py): the child is
//! silent until sent the init stanza, flushes every line it
//! writes, prints pre-wire refusals as bare `voxam: ...` text,
//! and exits 0 on game over or EOF, 2 on a fault.

use std::ffi::{OsStr, OsString};
use std::io::{BufRead, BufReader, Read, Write};
use std::path::{Path, PathBuf};
use std::process::{Child, ChildStdin, Command, Stdio};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Mutex, OnceLock};

use serde_json::{json, Value};
use tauri::menu::{CheckMenuItem, IsMenuItem, Menu, MenuItem, PredefinedMenuItem, Submenu};
use tauri::{AppHandle, Emitter, Manager, RunEvent, State, Wry};

/// The friendly failure when voxam cannot be found: the shell
/// finds voxam, it does not bundle it (yet -- a named road). By
/// the time this shows, `voxam_bin` has already tried the known
/// install dirs and the login shell's own PATH, so the honest
/// remaining advice is to install it or point straight at it.
const NOT_FOUND: &str = "Voxam can't find the voxam command.\n\n\
    Install it with one of:\n\n    \
    pipx install voxam\n    uv tool install voxam\n\n\
    If voxam is already installed and runs in a terminal, this\n\
    app was launched without your shell's PATH. Set VOXAM_BIN to\n\
    its full path -- what `which voxam` prints in a terminal --\n\
    or start the app from that terminal instead.";

/// The `voxam` executable the shell drives, resolved once.
///
/// A desktop app launched from Finder, the Dock, or a menu is
/// started by the OS session manager, not a shell, so it never
/// sees the PATH a shell's rc files build -- only the spare system
/// PATH. `uv tool install voxam` and `pipx install voxam` write to
/// `~/.local/bin`, which is not on that spare PATH, so a bare
/// `Command::new("voxam")` reports "not found" for nearly everyone
/// who installed it the documented way, while it runs fine in a
/// terminal. So the lookup goes wider: `VOXAM_BIN` wins outright,
/// then the bare name (a terminal launch, and Windows, where the
/// user PATH does reach GUI apps), then the bin dirs the Python
/// installers are known to use, then the user's login shell asked
/// to resolve it with its own full PATH.
fn voxam_bin() -> &'static OsString {
    static RESOLVED: OnceLock<OsString> = OnceLock::new();

    RESOLVED.get_or_init(|| {
        if let Some(pinned) = std::env::var_os("VOXAM_BIN") {
            if !pinned.is_empty() {
                return pinned;
            }
        }

        if runs(OsStr::new("voxam")) {
            return "voxam".into();
        }

        known_dirs()
            .into_iter()
            .map(|dir| dir.join(VOXAM_EXE))
            .find(|cand| runs(cand.as_os_str()))
            .map(PathBuf::into_os_string)
            .or_else(from_login_shell)
            .unwrap_or_else(|| "voxam".into())
    })
}

#[cfg(windows)]
const VOXAM_EXE: &str = "voxam.exe";
#[cfg(not(windows))]
const VOXAM_EXE: &str = "voxam";

/// Whether `<bin> --version` actually launches and exits clean --
/// the cheapest honest proof that a path is the runnable voxam.
fn runs(bin: &OsStr) -> bool {
    let mut probe = Command::new(bin);

    probe
        .arg("--version")
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());

    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;

        probe.creation_flags(0x0800_0000);
    }

    probe
        .status()
        .map(|status| status.success())
        .unwrap_or(false)
}

/// The bin directories `uv tool`, `pipx`, and `pip` install into,
/// honoring the env vars each reads to relocate its own, most
/// likely first. Absent dirs and duplicates are harmless: `runs`
/// is the real filter.
fn known_dirs() -> Vec<PathBuf> {
    let mut dirs: Vec<PathBuf> = Vec::new();
    let mut push = |dir: PathBuf| {
        if !dir.as_os_str().is_empty() && !dirs.contains(&dir) {
            dirs.push(dir);
        }
    };

    for key in [
        "VOXAM_BIN_DIR",
        "UV_TOOL_BIN_DIR",
        "PIPX_BIN_DIR",
        "XDG_BIN_HOME",
    ] {
        if let Some(dir) = std::env::var_os(key) {
            push(PathBuf::from(dir));
        }
    }

    if let Some(home) = home_dir() {
        push(home.join(".local").join("bin"));

        // pip's `--user` scheme on macOS: ~/Library/Python/3.x/bin.
        if let Ok(entries) = std::fs::read_dir(home.join("Library").join("Python")) {
            for entry in entries.flatten() {
                push(entry.path().join("bin"));
            }
        }
    }

    for fixed in ["/opt/homebrew/bin", "/usr/local/bin", "/usr/bin"] {
        push(PathBuf::from(fixed));
    }

    dirs
}

fn home_dir() -> Option<PathBuf> {
    std::env::var_os("HOME")
        .or_else(|| std::env::var_os("USERPROFILE"))
        .filter(|home| !home.is_empty())
        .map(PathBuf::from)
}

/// The user's login shell asked to resolve `voxam` with its own
/// full PATH -- the rc files sourced, the way a terminal sees it.
/// A last resort: it costs a shell spawn, and a login shell that
/// hangs on `-c` is already broken for the user everywhere else.
#[cfg(not(windows))]
fn from_login_shell() -> Option<OsString> {
    let shell = std::env::var_os("SHELL").unwrap_or_else(|| "/bin/sh".into());

    let output = Command::new(shell)
        .args(["-lic", "command -v voxam"])
        .stdin(Stdio::null())
        .stderr(Stdio::null())
        .output()
        .ok()?;

    // `command -v` prints an absolute path for an executable; any
    // other line is rc-file noise. Validate before trusting it.
    String::from_utf8_lossy(&output.stdout)
        .lines()
        .map(str::trim)
        .filter(|line| line.starts_with('/'))
        .map(PathBuf::from)
        .find(|cand| runs(cand.as_os_str()))
        .map(PathBuf::into_os_string)
}

#[cfg(windows)]
fn from_login_shell() -> Option<OsString> {
    None
}

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

/// How the page dresses itself, as the page's own JSON.
///
/// The shell keeps this and hands it back; it never reads a field.
/// That is deliberate. The page is the one place that knows what a
/// face, a measure, or a colour means, so holding the settings
/// shapelessly here means a new knob on the panel needs no
/// matching change on this side, and a settings file written by an
/// older version can never fail to parse and quietly reset the
/// lot. Persisted as display.json in the app's own config dir.
///
/// Null is the honest empty: the panel answers it with its own
/// defaults, which are the only defaults there are.
type Display = serde_json::Value;

/// Where the open-story dialog starts: a folder the player pinned
/// by hand, or -- with nothing pinned -- wherever the last story
/// was opened from, so a save to some other corner of the disk
/// never drags the story picker after it. Persisted as home.json
/// beside the display settings.
#[derive(Clone, Default, serde::Serialize, serde::Deserialize)]
struct Home {
    pinned: Option<PathBuf>,
    followed: Option<PathBuf>,
}

fn home_path(app: &AppHandle) -> Option<PathBuf> {
    app.path()
        .app_config_dir()
        .ok()
        .map(|dir| dir.join("home.json"))
}

fn load_home(app: &AppHandle) -> Home {
    home_path(app)
        .and_then(|path| std::fs::read_to_string(path).ok())
        .and_then(|held| serde_json::from_str(&held).ok())
        .unwrap_or_default()
}

fn save_home(app: &AppHandle, home: &Home) {
    let Some(path) = home_path(app) else {
        return;
    };

    if let Some(dir) = path.parent() {
        let _ = std::fs::create_dir_all(dir);
    }

    if let Ok(held) = serde_json::to_string_pretty(home) {
        let _ = std::fs::write(path, held);
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
    following: CheckMenuItem<Wry>,
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
    home: Mutex<Home>,
    minted: AtomicU64,
}

/// Remember the chosen story and wear its name on the title bar.
/// The story's own folder becomes the followed home, so the next
/// open starts among stories no matter where a save wandered.
#[tauri::command]
async fn set_story(app: AppHandle, state: State<'_, Shell>, path: String) -> Result<(), String> {
    let chosen = PathBuf::from(&path);
    let name = titled(&chosen);

    if let Some(window) = app.get_webview_window("main") {
        let _ = window.set_title(&format!("{name} \u{2014} Voxam"));
    }

    if let Some(parent) = chosen.parent() {
        let mut home = state.home.lock().unwrap();

        home.followed = Some(parent.to_path_buf());

        save_home(&app, &home);
    }

    *state.story.lock().unwrap() = Some(chosen);

    Ok(())
}

/// Where the story picker opens: the pinned folder if one was
/// chosen, else wherever the last story came from.
#[tauri::command]
async fn story_home(state: State<'_, Shell>) -> Result<Option<String>, String> {
    let home = state.home.lock().unwrap();

    Ok(home
        .pinned
        .as_ref()
        .or(home.followed.as_ref())
        .map(|path| path.to_string_lossy().into_owned()))
}

/// Pin the stories folder, or unpin it to follow the last story
/// again; the menu's checkmark tells whichever is true.
#[tauri::command]
async fn set_home(
    app: AppHandle,
    state: State<'_, Shell>,
    path: Option<String>,
) -> Result<(), String> {
    let mut home = state.home.lock().unwrap();

    home.pinned = path.map(PathBuf::from);

    save_home(&app, &home);

    let _ = app
        .state::<Chrome>()
        .following
        .set_checked(home.pinned.is_none());

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

    let mut command = Command::new(voxam_bin());

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

    let mut command = Command::new(voxam_bin());

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

/// The settings the page has just changed, kept beside the app's
/// own config so the next load opens in them. The page is the one
/// that knows what it is wearing; this only writes it down.
#[tauri::command]
async fn set_display(
    app: AppHandle,
    state: State<'_, Shell>,
    display: Display,
) -> Result<(), String> {
    *state.display.lock().unwrap() = display.clone();
    save_display(&app, &display);

    Ok(())
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

            // Where the story picker opens: pin a folder, or
            // follow the last story -- the persisted home read
            // first, so the checkmark tells the truth at startup.
            let settled = load_home(handle);

            *app.state::<Shell>().home.lock().unwrap() = settled.clone();

            let pin =
                MenuItem::with_id(handle, "home", "Choose Folder\u{2026}", true, None::<&str>)?;
            let following = CheckMenuItem::with_id(
                handle,
                "follow",
                "Follow the Last Story",
                true,
                settled.pinned.is_none(),
                None::<&str>,
            )?;
            let homes = Submenu::with_items(handle, "Stories Home", true, &[&pin, &following])?;

            let quit = PredefinedMenuItem::quit(handle, Some("Exit"))?;
            let file =
                Submenu::with_items(handle, "File", true, &[&open, &restart, &homes, &quit])?;

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

            // The dress is read once at startup and handed to the
            // page, which owns every knob from here: the panel it
            // opens is the browser face's own, so a choice means the
            // same thing in both.
            *app.state::<Shell>().display.lock().unwrap() = load_display(handle);

            let prefs = MenuItem::with_id(
                handle,
                "prefs",
                "Preferences...",
                true,
                Some("CmdOrCtrl+,"),
            )?;
            let display = Submenu::with_items(handle, "Display", true, &[&prefs])?;
            let menu = Menu::with_items(handle, &[&file, &story, &display])?;

            app.set_menu(menu)?;
            app.manage(Chrome {
                interpreters,
                tandy,
                following,
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
                "home" => {
                    let _ = app.emit("menu-home", ());
                }
                "follow" => {
                    // The page owns no flow here: unpin directly,
                    // and set_home rights the checkmark.
                    let _ = app.emit("menu-follow", ());
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
                "prefs" => {
                    // The panel lives in the page, so the menu item
                    // only knocks on it.
                    let _ = app.emit("menu-preferences", ());
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
            display_settings,
            set_display,
            story_home,
            set_home
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
