// Desktop-Hülle: startet den gebündelten Server, wartet auf seine Startmeldung und zeigt die
// Oberfläche in einem Fenster. Schliesst die Hülle, beendet sich der Server (Standardeingang).
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::io::{BufRead, BufReader};
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::thread;

use tauri::{AppHandle, Manager, RunEvent, WindowEvent};

const READY: &str = "PROCURATOR_READY ";

struct Server(Mutex<Option<Child>>);

/// Pfad des Servers: Umgebungsvariable (Entwicklung) oder die mitgelieferte Ressource.
fn server_path(app: &AppHandle) -> Result<PathBuf, String> {
    if let Ok(p) = std::env::var("PROCURATOR_SERVER") {
        return Ok(PathBuf::from(p));
    }
    let dir = app.path().resource_dir().map_err(|e| e.to_string())?;
    let exe = dir.join("pc-server").join("pc-server");
    if exe.is_file() {
        Ok(exe)
    } else {
        Err(format!("Server nicht gefunden: {}", exe.display()))
    }
}

/// Startet den Server und gibt seine Adresse zurück.
fn start_server(app: &AppHandle) -> Result<String, String> {
    let exe = server_path(app)?;
    let mut child = Command::new(&exe)
        .env("PROCURATOR_DESKTOP", "1")
        .stdin(Stdio::piped()) // bleibt offen, solange die Hülle lebt
        .stdout(Stdio::piped())
        .stderr(Stdio::inherit())
        .spawn()
        .map_err(|e| format!("{}: {}", exe.display(), e))?;
    let stdout = child.stdout.take().ok_or("Keine Ausgabe vom Server")?;
    let mut reader = BufReader::new(stdout);
    let mut line = String::new();
    reader.read_line(&mut line).map_err(|e| e.to_string())?;
    let url = line
        .trim()
        .strip_prefix(READY)
        .ok_or_else(|| format!("Unerwartete Startmeldung des Servers: {:?}", line.trim()))?
        .to_string();
    thread::spawn(move || {
        // weiterlesen, damit der Server nie an einer vollen Röhre hängen bleibt
        let mut sink = String::new();
        while reader.read_line(&mut sink).map(|n| n > 0).unwrap_or(false) {
            sink.clear();
        }
    });
    *app.state::<Server>().0.lock().unwrap() = Some(child);
    Ok(url)
}

fn main() {
    let app = tauri::Builder::default()
        .manage(Server(Mutex::new(None)))
        .on_page_load(|_webview, payload| {
            eprintln!("Seite {:?}: {}", payload.event(), payload.url());
        })
        .setup(|app| {
            let handle = app.handle().clone();
            thread::spawn(move || {
                let Some(window) = handle.get_webview_window("main") else { return };
                match start_server(&handle) {
                    Ok(url) => {
                        eprintln!("Server bereit: {url}");
                        match url.parse() {
                            Ok(parsed) => {
                                if let Err(e) = window.navigate(parsed) {
                                    eprintln!("navigate fehlgeschlagen: {e}, versuche es über die Seite");
                                    let _ = window.eval(format!("window.location.replace({})", js_string(&url)));
                                }
                            }
                            Err(e) => show_error(&window, &format!("Ungültige Adresse {url}: {e}")),
                        }
                    }
                    Err(msg) => show_error(&window, &msg),
                }
            });
            Ok(())
        })
        .on_window_event(|window, event| {
            if let WindowEvent::CloseRequested { .. } = event {
                window.app_handle().exit(0); // ein Fenster, danach ist Schluss (auch unter macOS)
            }
        })
        .build(tauri::generate_context!())
        .expect("Fehler beim Start der Desktop-App");

    app.run(|handle, event| {
        if let RunEvent::Exit = event {
            if let Some(mut child) = handle.state::<Server>().0.lock().unwrap().take() {
                let _ = child.kill();
                let _ = child.wait();
            }
        }
    });
}

fn show_error(window: &tauri::WebviewWindow, msg: &str) {
    let json = js_string(msg);
    let _ = window.eval(format!("window.showError({json})"));
}

/// Minimales Escapen eines Textes als JavaScript-Zeichenkette (ohne zusätzliche Abhängigkeit).
fn js_string(s: &str) -> String {
    let mut out = String::from("\"");
    for c in s.chars() {
        match c {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            c if (c as u32) < 0x20 => out.push_str(&format!("\\u{:04x}", c as u32)),
            c => out.push(c),
        }
    }
    out.push('"');
    out
}
