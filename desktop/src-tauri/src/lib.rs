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
use std::path::PathBuf;
use std::process::{Child, ChildStdin, Command, Stdio};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Mutex;

use serde_json::{json, Value};
use tauri::menu::{Menu, MenuItem, PredefinedMenuItem, Submenu};
use tauri::{AppHandle, Emitter, Manager, RunEvent, State};

/// The friendly failure when voxam is not on PATH: the shell
/// finds voxam, it does not bundle it (yet -- a named road).
const NOT_FOUND: &str = "voxam is not on this machine's PATH.\n\n\
    Install it with:\n\n    uv tool install voxam\n\n\
    (or pipx install voxam, or pip install voxam). If it was\n\
    installed moments ago, sign out and back in so the PATH\n\
    refreshes for desktop apps.";

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
    minted: AtomicU64,
}

/// Remember the chosen story and wear its name on the title bar.
#[tauri::command]
async fn set_story(app: AppHandle, state: State<'_, Shell>, path: String) -> Result<(), String> {
    let chosen = PathBuf::from(&path);

    let name = chosen
        .file_stem()
        .map(|stem| stem.to_string_lossy().into_owned())
        .unwrap_or_else(|| "Voxam".to_string());

    if let Some(window) = app.get_webview_window("main") {
        let _ = window.set_title(&format!("{name} \u{2014} Voxam"));
    }

    *state.story.lock().unwrap() = Some(chosen);

    Ok(())
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
            let menu = Menu::with_items(handle, &[&file])?;

            app.set_menu(menu)?;

            // The menu only signals; the page owns the flow, since
            // choosing and restarting both end in its reload.
            app.on_menu_event(|app, event| match event.id().as_ref() {
                "open" => {
                    let _ = app.emit("menu-open", ());
                }
                "restart" => {
                    let _ = app.emit("menu-restart", ());
                }
                _ => {}
            });

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            set_story,
            current_story,
            start_session,
            send_stanza
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
