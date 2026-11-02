use crossbeam_channel::{unbounded, Receiver, Sender};
use eframe::egui;
use notify::{Event, RecursiveMode, Watcher};
use reqwest::blocking::{multipart, Client};
use serde_json::{Map, Value};
use std::{
    collections::HashSet,
    fs,
    path::{Path, PathBuf},
    sync::{
        atomic::{AtomicBool, Ordering},
        Arc, Mutex,
    },
    thread,
    time::Duration,
};
use walkdir::WalkDir;

const CONFIG_NAME: &str = ".tgbackup_v3_config.json";
const HISTORY_NAME: &str = ".tgbackup_v3_history.json";
const MAX_FILE: u64 = 50 * 1024 * 1024;

fn user_file(name: &str) -> PathBuf {
    dirs_home().join(name)
}
fn dirs_home() -> PathBuf {
    std::env::var_os("HOME")
        .or_else(|| std::env::var_os("USERPROFILE"))
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("."))
}
fn load_config() -> Map<String, Value> {
    fs::read(user_file(CONFIG_NAME))
        .ok()
        .and_then(|b| serde_json::from_slice::<Value>(&b).ok())
        .and_then(|v| v.as_object().cloned())
        .unwrap_or_default()
}
fn save_config(config: &Map<String, Value>) -> Result<(), String> {
    let data = serde_json::to_vec_pretty(config).map_err(|e| e.to_string())?;
    atomic_write(&user_file(CONFIG_NAME), &data)
}
fn load_history() -> HashSet<String> {
    fs::read(user_file(HISTORY_NAME))
        .ok()
        .and_then(|b| serde_json::from_slice::<Value>(&b).ok())
        .and_then(|v| v.as_array().cloned())
        .unwrap_or_default()
        .into_iter()
        .filter_map(|v| v.as_str().map(str::to_owned))
        .collect()
}
fn save_history(history: &HashSet<String>) -> Result<(), String> {
    let mut entries: Vec<_> = history.iter().collect();
    entries.sort();
    atomic_write(
        &user_file(HISTORY_NAME),
        &serde_json::to_vec(&entries).map_err(|e| e.to_string())?,
    )
}
fn atomic_write(path: &Path, data: &[u8]) -> Result<(), String> {
    fs::write(path, data).map_err(|e| e.to_string())
}
fn get_str(cfg: &Map<String, Value>, key: &str) -> String {
    cfg.get(key)
        .and_then(Value::as_str)
        .unwrap_or_default()
        .to_owned()
}

#[derive(Clone)]
enum Job {
    Scan(Vec<PathBuf>),
    Watch(Vec<PathBuf>),
}
struct App {
    cfg: Map<String, Value>,
    token: String,
    chat: String,
    folders: Vec<String>,
    events: Receiver<String>,
    tx: Sender<String>,
    jobs: Sender<Job>,
    status: Arc<Mutex<String>>,
    watching: bool,
    paused: bool,
    history: Arc<Mutex<HashSet<String>>>,
    pause_state: Arc<AtomicBool>,
}
impl App {
    fn new() -> Self {
        let cfg = load_config();
        let folders = cfg
            .get("watch_folders")
            .and_then(Value::as_array)
            .map(|a| {
                a.iter()
                    .filter_map(Value::as_str)
                    .map(str::to_owned)
                    .collect()
            })
            .unwrap_or_default();
        let (tx, events) = unbounded();
        let (jobs, job_rx) = unbounded();
        let status = Arc::new(Mutex::new(
            "Ready — add a watched folder and configure your Telegram bot.".into(),
        ));
        let history = Arc::new(Mutex::new(load_history()));
        let pause_state = Arc::new(AtomicBool::new(false));
        let work_pause = pause_state.clone();
        let work_status = status.clone();
        let work_tx = tx.clone();
        let work_history = history.clone();
        thread::Builder::new()
            .name("telegram-backup-worker".into())
            .spawn(move || worker(job_rx, work_tx, work_status, work_history, work_pause))
            .expect("worker thread");
        Self {
            token: get_str(&cfg, "token"),
            chat: get_str(&cfg, "chat_id"),
            folders,
            cfg,
            events,
            tx,
            jobs,
            status,
            watching: false,
            paused: false,
            history,
            pause_state,
        }
    }
    fn persist(&mut self) {
        self.cfg
            .insert("token".into(), Value::String(self.token.clone()));
        self.cfg
            .insert("chat_id".into(), Value::String(self.chat.clone()));
        self.cfg
            .insert("watch_folders".into(), serde_json::json!(self.folders));
        self.cfg
            .entry("theme")
            .or_insert(Value::String("dark".into()));
        self.cfg
            .entry("telegram_enabled")
            .or_insert(Value::Bool(true));
        self.cfg
            .entry("drive_enabled")
            .or_insert(Value::Bool(false));
        self.cfg.entry("all_files").or_insert(Value::Bool(true));
        self.cfg.entry("subfolders").or_insert(Value::Bool(true));
        self.cfg.entry("bandwidth_limit").or_insert(Value::from(0));
        if let Err(e) = save_config(&self.cfg) {
            self.set_status(format!("Could not save settings: {e}"));
        }
    }
    fn set_status(&self, message: String) {
        if let Ok(mut s) = self.status.lock() {
            *s = message;
        }
    }
    fn start_watching(&mut self) {
        let paths: Vec<PathBuf> = self.folders.iter().map(PathBuf::from).collect();
        if paths.is_empty() {
            self.set_status("Add at least one folder first.".into());
            return;
        }
        let _ = self.jobs.send(Job::Watch(paths));
        self.watching = true;
        self.set_status("Watching folders for new and changed files…".into());
    }
    fn scan(&self) {
        let _ = self
            .jobs
            .send(Job::Scan(self.folders.iter().map(PathBuf::from).collect()));
    }
}
impl eframe::App for App {
    fn update(&mut self, ctx: &egui::Context, _frame: &mut eframe::Frame) {
        while let Ok(message) = self.events.try_recv() {
            self.set_status(message);
        }
        ctx.request_repaint_after(Duration::from_millis(300));
        egui::TopBottomPanel::top("header").show(ctx, |ui| {
            ui.horizontal(|ui| {
                ui.heading("TelegramBackup");
                ui.label(
                    egui::RichText::new("RUST PORT · v4 compatible")
                        .small()
                        .color(egui::Color32::from_rgb(90, 190, 210)),
                );
            });
        });
        egui::CentralPanel::default().show(ctx, |ui| {
            ui.add_space(8.0);
            ui.label(egui::RichText::new("Backup dashboard").size(22.0).strong());
            ui.label("Native Rust preview — settings and deduplication reuse the existing v4 profile files.");
            ui.add_space(12.0);
            egui::Grid::new("credentials").num_columns(2).spacing([10.0, 8.0]).show(ui, |ui| {
                ui.label("Bot token");
                ui.add(egui::TextEdit::singleline(&mut self.token).password(true).desired_width(410.0));
                ui.end_row();
                ui.label("Chat / channel ID");
                ui.add(egui::TextEdit::singleline(&mut self.chat).desired_width(410.0));
                ui.end_row();
            });
            ui.horizontal(|ui| {
                if ui.button("Save settings").clicked() {
                    self.persist();
                    self.set_status("Settings saved to ~/.tgbackup_v3_config.json".into());
                }
                if ui.button("Test Telegram").clicked() {
                    let token = self.token.clone();
                    let tx = self.tx.clone();
                    thread::spawn(move || {
                        let result = Client::new()
                            .get(format!("https://api.telegram.org/bot{token}/getMe"))
                            .send().and_then(|r| r.error_for_status()).and_then(|r| r.json::<Value>());
                        let text = match result {
                            Ok(v) if v["ok"] == true => format!("Telegram bot connected: {}", v["result"]["username"].as_str().unwrap_or("OK")),
                            Ok(v) => format!("Telegram test failed: {v}"),
                            Err(e) => format!("Telegram test failed: {e}"),
                        };
                        let _ = tx.send(text);
                    });
                }
            });
            ui.add_space(12.0);
            ui.separator();
            ui.horizontal(|ui| {
                ui.heading("Watched folders");
                if ui.button("＋ Add folder").clicked() {
                    if let Some(path) = rfd::FileDialog::new().pick_folder() {
                        let value = path.display().to_string();
                        if !self.folders.contains(&value) { self.folders.push(value); self.persist(); }
                    }
                }
            });
            egui::ScrollArea::vertical().max_height(150.0).show(ui, |ui| {
                let mut remove = None;
                for (i, path) in self.folders.iter().enumerate() {
                    ui.horizontal(|ui| { ui.label(path); if ui.small_button("Remove").clicked() { remove = Some(i); } });
                }
                if let Some(i) = remove { self.folders.remove(i); self.persist(); }
            });
            ui.horizontal(|ui| {
                if ui.button("Scan folders now").clicked() { self.persist(); self.scan(); }
                if ui.button(if self.watching { "Watching" } else { "Start watching" }).clicked() && !self.watching {
                    self.persist(); self.start_watching();
                }
                if ui.button(if self.paused { "Resume" } else { "Pause" }).clicked() {
                    self.paused = !self.paused;
                    self.pause_state.store(self.paused, Ordering::SeqCst);
                    self.cfg.insert("paused".into(), Value::Bool(self.paused));
                    let _ = save_config(&self.cfg);
                    self.set_status(if self.paused { "Queue paused" } else { "Queue resumed" }.into());
                }
            });
            ui.add_space(10.0);
            ui.separator();
            ui.heading("Queue and activity");
            if let Ok(s) = self.status.lock() { ui.label(s.as_str()); }
            let count = self.history.lock().map(|h| h.len()).unwrap_or(0);
            ui.label(format!("Previously uploaded unique files: {count} · Max Telegram file size: 50 MB"));
            ui.add_space(4.0);
            ui.label(egui::RichText::new("Config: ~/.tgbackup_v3_config.json   ·   History: ~/.tgbackup_v3_history.json").small().weak());
        });
    }
}
fn worker(
    rx: Receiver<Job>,
    tx: Sender<String>,
    status: Arc<Mutex<String>>,
    history: Arc<Mutex<HashSet<String>>>,
    pause_state: Arc<AtomicBool>,
) {
    let (file_tx, file_rx) = unbounded::<PathBuf>();
    let work_tx = tx.clone();
    let work_status = status.clone();
    let work_history = history.clone();
    thread::spawn(move || {
        while let Ok(path) = file_rx.recv() {
            while pause_state.load(Ordering::SeqCst) {
                thread::sleep(Duration::from_millis(250));
            }
            if let Err(e) = upload_file(&path, &work_history) {
                let _ = work_tx.send(format!("Upload failed — {}: {e}", path.display()));
            } else {
                let _ = work_tx.send(format!("Uploaded {}", path.display()));
            }
            if let Ok(mut s) = work_status.lock() {
                *s = "Idle".into();
            }
        }
    });
    let mut watcher: Option<notify::RecommendedWatcher> = None;
    loop {
        match rx.recv() {
            Ok(Job::Scan(paths)) => {
                let _ = tx.send("Scanning configured folders…".into());
                for root in paths {
                    for entry in WalkDir::new(root)
                        .follow_links(false)
                        .into_iter()
                        .filter_map(Result::ok)
                        .filter(|e| e.file_type().is_file())
                    {
                        let _ = file_tx.send(entry.path().to_path_buf());
                    }
                }
            }
            Ok(Job::Watch(paths)) => {
                let ft = file_tx.clone();
                let et = tx.clone();
                let result =
                    notify::recommended_watcher(move |res: Result<Event, notify::Error>| {
                        if let Ok(event) = res {
                            for p in event.paths {
                                if p.is_file() {
                                    let _ = ft.send(p);
                                }
                            }
                        }
                    });
                match result {
                    Ok(mut w) => {
                        let mut ok = true;
                        for path in paths {
                            if let Err(e) = w.watch(&path, RecursiveMode::Recursive) {
                                let _ = et.send(format!("Could not watch {}: {e}", path.display()));
                                ok = false;
                            }
                        }
                        if ok {
                            watcher = Some(w);
                            let _ = tx.send("Folder watcher is active.".into());
                        }
                    }
                    Err(e) => {
                        let _ = tx.send(format!("Watcher failed: {e}"));
                    }
                }
            }
            Err(_) => break,
        }
    }
    drop(watcher);
}
fn upload_file(path: &Path, history: &Arc<Mutex<HashSet<String>>>) -> Result<(), String> {
    let config = load_config();
    let token = get_str(&config, "token");
    let chat = get_str(&config, "chat_id");
    if token.is_empty() || chat.is_empty() {
        return Err("enter and save the Telegram bot token and chat ID first".into());
    }
    let meta = fs::metadata(path).map_err(|e| e.to_string())?;
    if meta.len() > MAX_FILE {
        return Err(format!("oversized file ({} bytes)", meta.len()));
    }
    if !meta.is_file() {
        return Ok(());
    }
    let bytes = fs::read(path).map_err(|e| e.to_string())?;
    let digest = format!("{:x}", md5::compute(&bytes));
    {
        let h = history.lock().map_err(|e| e.to_string())?;
        if h.contains(&digest) {
            return Ok(());
        }
    }
    let name = path
        .file_name()
        .and_then(|n| n.to_str())
        .unwrap_or("backup.bin")
        .to_owned();
    let url = format!("https://api.telegram.org/bot{token}/sendDocument");
    let mut last = String::new();
    for attempt in 0..4 {
        let part = multipart::Part::bytes(bytes.clone())
            .file_name(name.clone())
            .mime_str("application/octet-stream")
            .map_err(|e| e.to_string())?;
        let form = multipart::Form::new()
            .text("chat_id", chat.clone())
            .part("document", part);
        match Client::new().post(&url).multipart(form).send() {
            Ok(resp) => {
                let body: Value = resp.json().unwrap_or(Value::Null);
                if body["ok"] == true {
                    let mut h = history.lock().map_err(|e| e.to_string())?;
                    h.insert(digest);
                    save_history(&h)?;
                    return Ok(());
                }
                last = body["description"]
                    .as_str()
                    .unwrap_or("Telegram upload rejected")
                    .to_owned();
                let delay = body["parameters"]["retry_after"].as_u64().unwrap_or(0);
                if delay > 0 {
                    thread::sleep(Duration::from_secs(delay));
                }
            }
            Err(e) => last = e.to_string(),
        }
        if attempt < 3 {
            thread::sleep(Duration::from_secs(2u64.pow(attempt)));
        }
    }
    Err(last)
}
fn main() -> eframe::Result<()> {
    let viewport = egui::ViewportBuilder::default()
        .with_inner_size([780.0, 650.0])
        .with_min_inner_size([620.0, 500.0])
        .with_title("TelegramBackup Rust");
    eframe::run_native(
        "TelegramBackup Rust",
        eframe::NativeOptions {
            viewport,
            ..Default::default()
        },
        Box::new(|cc| {
            cc.egui_ctx.set_visuals(egui::Visuals::dark());
            Ok(Box::new(App::new()))
        }),
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn legacy_history_array_is_supported() {
        let v: Value = serde_json::from_str("[\"abc123\",\"def456\"]").unwrap();
        let values: HashSet<String> = v
            .as_array()
            .unwrap()
            .iter()
            .filter_map(Value::as_str)
            .map(str::to_owned)
            .collect();
        assert!(values.contains("abc123"));
    }
    #[test]
    fn settings_map_preserves_unknown_keys() {
        let mut map = Map::new();
        map.insert("token".into(), Value::String("secret".into()));
        map.insert("drive_folder_id".into(), Value::String("kept".into()));
        assert_eq!(map["drive_folder_id"], "kept");
    }
}
