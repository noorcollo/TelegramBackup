"""
TelegramBackup v3
=================
Auto-backup any folder on your Windows PC to a Telegram group or channel.
New files are detected instantly via filesystem watching and uploaded automatically.

Author  : 3ala
Version : 3.0
License : MIT
GitHub  : https://github.com/YOUR_USERNAME/TelegramBackup

Features:
  - Multi-folder watching (unlimited folders simultaneously)
  - All file types supported (8 categories or everything)
  - Live upload speed graph
  - Day / Night theme
  - Autostart with Windows, system tray, background mode
  - Flood control: auto-wait and retry on Telegram rate limits
  - Duplicate prevention via MD5 hashing
  - Per-machine ID tagging on every upload
  - 5 skip stat counters (uploaded / skipped / oversized / errors / duplicates)

Requirements:
  python-telegram-bot >= 21.0
  watchdog >= 4.0.0
  pystray >= 0.19.0     (optional — for system tray)
  Pillow >= 10.0.0      (optional — for system tray icon)

Usage:
  python telegram_backup_v3.py
  OR double-click Launch_TelegramBackup.bat
"""

import os, sys, json, time, queue, asyncio, hashlib, threading, webbrowser, uuid, socket
import tkinter as tk
from tkinter import filedialog, scrolledtext, messagebox, ttk
from datetime import datetime, date
from pathlib import Path
from collections import deque
from bandwidth import BandwidthLimiter, ThrottledReader
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from telegram import Bot, InputFile
from telegram.error import TelegramError

try:
    from drive_backup import GoogleDriveClient, DriveUploader, drive_available, drive_install_hint
    DRIVE_MODULE_OK = True
except ImportError:
    DRIVE_MODULE_OK = False
    GoogleDriveClient = DriveUploader = None
    def drive_available(): return False
    def drive_install_hint(): return "Google Drive support is not installed."

TRAY_OK = False
try:
    import pystray
    from PIL import Image, ImageDraw
    TRAY_OK = True
except ImportError:
    pass

WIN_OK = False
try:
    import winreg
    WIN_OK = True
except ImportError:
    pass

CONFIG_FILE  = os.path.join(os.path.expanduser("~"), ".tgbackup_v3_config.json")
HISTORY_FILE = os.path.join(os.path.expanduser("~"), ".tgbackup_v3_history.json")
STATS_FILE   = os.path.join(os.path.expanduser("~"), ".tgbackup_v4_stats.json")
MAX_SIZE     = 50 * 1024 * 1024
APP_NAME     = "TelegramBackup"
REG_KEY      = r"Software\Microsoft\Windows\CurrentVersion\Run"
VERSION      = "v4.0"
AUTHOR       = "Made by 3ala"

THEMES = {
    "dark": {
        "bg":"#07090f","sidebar":"#0c1018","card":"#101520","card2":"#141c28",
        "border":"#1c2a3a","accent":"#00e5b0","accent2":"#0d99ff","purple":"#a78bfa",
        "warn":"#fbbf24","err":"#f87171","text":"#e2edf8","sub":"#4d6d8a",
        "done":"#34d399","inp":"#0a1220","tag":"#0f1d2d","hover":"#182435",
        "graph_bg":"#060b12","graph_ln":"#00e5b0","graph_fi":"#0d3d28",
    },
    "light": {
        "bg":"#f0f4f8","sidebar":"#e2eaf2","card":"#ffffff","card2":"#f7fafd",
        "border":"#cbd5e1","accent":"#0891b2","accent2":"#2563eb","purple":"#7c3aed",
        "warn":"#d97706","err":"#dc2626","text":"#1e293b","sub":"#64748b",
        "done":"#059669","inp":"#f8fafc","tag":"#e8f0f8","hover":"#dbeafe",
        "graph_bg":"#f1f5f9","graph_ln":"#0891b2","graph_fi":"#bae6fd",
    },
}

FILE_CATS = {
    "📄 Documents":   [".pdf",".doc",".docx",".xls",".xlsx",".ppt",".pptx",".txt",".rtf",".odt",".csv"],
    "🖼️ Images":      [".jpg",".jpeg",".png",".gif",".bmp",".webp",".svg",".tiff",".ico",".heic",".raw"],
    "🎬 Videos":      [".mp4",".mkv",".avi",".mov",".wmv",".flv",".webm",".m4v",".3gp",".mpeg"],
    "🎵 Audio":       [".mp3",".wav",".flac",".aac",".ogg",".m4a",".wma",".opus"],
    "🗜️ Archives":    [".zip",".rar",".7z",".tar",".gz",".bz2",".xz",".iso"],
    "💻 Code":        [".py",".js",".ts",".html",".css",".java",".cpp",".c",".cs",".php",".go",".rs",".sh",".json",".xml",".sql"],
    "🗃️ Databases":   [".db",".sqlite",".sqlite3",".mdb",".bak"],
    "📦 Executables": [".exe",".msi",".apk",".dmg",".deb"],
}

WIZARD_STEPS = [
    (1,"Create Bot","🤖"),(2,"Add to Group","👥"),(3,"Bot Token","🔑"),
    (4,"Chat ID","💬"),(5,"Watch Folders","📁"),(6,"File Types","🗂️"),
    (7,"Backup Destinations","☁️"),(8,"Launch","🚀"),
]

def get_machine_id():
    return hashlib.md5(str(uuid.getnode()).encode()).hexdigest()[:12].upper()

def load_cfg():
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE) as f: return json.load(f)
    except: pass
    return {}

def save_cfg(d):
    with open(CONFIG_FILE,"w") as f: json.dump(d,f,indent=2)

def load_hist():
    try:
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE) as f: return set(json.load(f))
    except: pass
    return set()

def save_hist(s):
    with open(HISTORY_FILE,"w") as f: json.dump(list(s),f)

def fhash(p):
    h=hashlib.md5()
    with open(p,"rb") as f:
        for chunk in iter(lambda: f.read(8192),b""): h.update(chunk)
    return h.hexdigest()

def get_exe_path():
    return sys.executable if getattr(sys,"frozen",False) else os.path.abspath(__file__)

def set_autostart(on):
    if not WIN_OK: return
    try:
        k=winreg.OpenKey(winreg.HKEY_CURRENT_USER,REG_KEY,0,winreg.KEY_SET_VALUE)
        if on: winreg.SetValueEx(k,APP_NAME,0,winreg.REG_SZ,f'"{get_exe_path()}"')
        else:
            try: winreg.DeleteValue(k,APP_NAME)
            except: pass
        winreg.CloseKey(k)
    except: pass

def count_files(folder,recursive=True):
    try: return sum(1 for p in Path(folder).glob("**/*" if recursive else "*") if p.is_file())
    except: return 0


def format_bytes(value):
    value = float(value or 0)
    if value >= 1024 ** 3: return f"{value / 1024 ** 3:.2f} GB"
    if value >= 1024 ** 2: return f"{value / 1024 ** 2:.2f} MB"
    if value >= 1024: return f"{value / 1024:.1f} KB"
    return f"{int(value)} B"


def format_limit(value):
    value = int(value or 0)
    if not value: return "Unlimited"
    if value % (1024 * 1024) == 0: return f"{value // (1024 * 1024)} MB/s"
    return f"{value // 1024} KB/s"


def parse_limit(value):
    text = str(value or "").strip().lower().replace("/s", "")
    if not text or text in {"unlimited", "off", "none", "0"}: return 0
    try:
        if text.endswith("mb"): return max(0, int(float(text[:-2].strip()) * 1024 * 1024))
        if text.endswith("kb"): return max(0, int(float(text[:-2].strip()) * 1024))
        return max(0, int(float(text))) * 1024
    except (TypeError, ValueError): return 0


def safe_int(value, default, minimum=None):
    try: result=int(float(str(value).strip()))
    except (TypeError, ValueError): result=default
    return max(minimum,result) if minimum is not None else result


def safe_float(value, default, minimum=None, maximum=None):
    try: result=float(str(value).strip())
    except (TypeError, ValueError): result=default
    if minimum is not None: result=max(minimum,result)
    if maximum is not None: result=min(maximum,result)
    return result


def network_available():
    """Lightweight reachability check used only at the configured interval."""
    try:
        with socket.create_connection(("api.telegram.org", 443), timeout=3):
            return True
    except OSError:
        try:
            with socket.create_connection(("www.googleapis.com", 443), timeout=3):
                return True
        except OSError:
            return False


class StatsManager:
    """Small, rate-limited JSON store for daily, session, and all-time stats."""
    def __init__(self, path=STATS_FILE):
        self.path = path; self.lock = threading.Lock(); self.last_write = 0.0
        self.data = {"date": date.today().isoformat(), "today": {}, "all_time": {}}
        try:
            with open(path, encoding="utf-8") as handle: self.data.update(json.load(handle))
        except (OSError, ValueError, TypeError): pass
        if self.data.get("date") != date.today().isoformat():
            self.data["date"] = date.today().isoformat(); self.data["today"] = {}
        self.session = {"start_time": datetime.now().isoformat(), "uploaded": 0, "bytes": 0, "errors": 0, "skipped": 0}

    def record_upload(self, size=0):
        with self.lock:
            for bucket in (self.data.setdefault("today", {}), self.data.setdefault("all_time", {})):
                bucket["uploaded"] = bucket.get("uploaded", 0) + 1
                bucket["bytes"] = bucket.get("bytes", 0) + int(size or 0)
            self.session["uploaded"] += 1; self.session["bytes"] += int(size or 0); self._flush_locked()

    def record_error(self):
        with self.lock:
            for bucket in (self.data.setdefault("today", {}), self.data.setdefault("all_time", {})):
                bucket["errors"] = bucket.get("errors", 0) + 1
            self.session["errors"] += 1; self._flush_locked()

    def record_skip(self):
        with self.lock:
            for bucket in (self.data.setdefault("today", {}), self.data.setdefault("all_time", {})):
                bucket["skipped"] = bucket.get("skipped", 0) + 1
            self.session["skipped"] += 1; self._flush_locked()

    def _flush_locked(self):
        now = time.monotonic()
        if now - self.last_write < 5: return
        self.last_write = now
        try:
            with open(self.path, "w", encoding="utf-8") as handle: json.dump(self.data, handle, indent=2)
        except OSError: pass

    def snapshot(self):
        with self.lock: return json.loads(json.dumps({"data": self.data, "session": self.session}))


class Uploader(threading.Thread):
    def __init__(self,token,chat_id,cbs,limiter=None,cancel_event=None):
        super().__init__(daemon=True)
        self.token,self.chat_id=token,chat_id
        self.on_log=cbs["log"]; self.on_stat=cbs["stat"]
        self.on_count=cbs["count"]; self.on_skip=cbs["skip"]; self.on_speed=cbs["speed"]
        self.on_item=cbs.get("item",lambda *args,**kwargs: None)
        self.is_online=cbs.get("is_online",lambda: True)
        self.is_cancelled=cbs.get("is_cancelled",lambda path: False)
        self.limiter=limiter or BandwidthLimiter()
        self.cancel_event=cancel_event or threading.Event()
        self.q=queue.Queue(); self.uploaded=load_hist(); self.active=True
        self.DELAY = 1.5   # minimum seconds between uploads (polite rate)
        self.MAX_RETRIES = 5

    def enqueue(self,path):
        self.on_item(path,"Telegram","Waiting",0.0,0); self.q.put(path)
    def stop(self):
        self.active=False
        self.cancel_event.set()

    def run(self):
        loop=asyncio.new_event_loop(); asyncio.set_event_loop(loop)
        loop.run_until_complete(self._loop())

    async def _loop(self):
        bot=Bot(token=self.token)
        while self.active:
            try: path=self.q.get(timeout=0.4)
            except queue.Empty: continue
            if self.is_cancelled(path):
                self.on_item(path,"Telegram","Removed",0.0,0); continue
            if not os.path.exists(path):
                self.on_log(f"⚠  Gone: {os.path.basename(path)}","warn"); self.on_item(path,"Telegram","Error",0.0,0); self.on_skip("error"); continue
            key=f"{path}::{fhash(path)}"
            if key in self.uploaded:
                self.on_log(f"⏭  Duplicate: {os.path.basename(path)}","sub"); self.on_item(path,"Telegram","Duplicate",1.0,0); self.on_skip("dup"); continue
            sz=os.path.getsize(path)
            if sz>MAX_SIZE:
                self.on_log(f"⛔  >50MB: {os.path.basename(path)}","warn"); self.on_item(path,"Telegram","Skipped",0.0,0); self.on_skip("size"); continue
            if sz==0:
                self.on_log(f"⚠  Empty: {os.path.basename(path)}","warn"); self.on_item(path,"Telegram","Error",0.0,0); self.on_skip("error"); continue

            self.on_item(path,"Telegram","Waiting",0.0,0)
            while self.active and not self.is_online():
                self.on_item(path,"Telegram","Paused",0.0,0)
                self.on_stat("Offline — waiting for internet connection")
                time.sleep(5)
            if not self.active: break
            self.on_item(path,"Telegram","Uploading",0.0,0)
            self.on_stat(f"Uploading {os.path.basename(path)}…")
            cap=(f"📦 *TelegramBackup {VERSION}*\n`{os.path.basename(path)}`\n"
                 f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                 f"💾 {sz/1024:.1f} KB  •  🖥️ `{get_machine_id()}`\n_{AUTHOR}_")

            # ── Retry loop with flood-wait handling ──────────────────────────
            success = False
            for attempt in range(1, self.MAX_RETRIES + 1):
                if not self.active: break
                try:
                    t0=time.time()
                    with open(path,"rb") as doc:
                        throttled=ThrottledReader(doc,self.limiter,self.cancel_event)
                        upload_file=InputFile(throttled, filename=os.path.basename(path), read_file_handle=False)
                        self.on_item(path,"Telegram","Uploading",None,attempt-1)
                        await bot.send_document(
                            chat_id=self.chat_id, document=upload_file, caption=cap,
                            parse_mode="Markdown",
                            read_timeout=90, write_timeout=90, connect_timeout=30)
                    elapsed=max(time.time()-t0, 0.1)
                    self.on_speed(sz/elapsed)
                    self.uploaded.add(key); save_hist(self.uploaded)
                    self.on_log(f"✅  {os.path.basename(path)}  ({sz/1024:.0f} KB)","done")
                    self.on_item(path,"Telegram","Completed",1.0,attempt-1)
                    self.on_count(1)
                    success = True
                    # polite delay between sends to avoid hitting rate limits
                    await asyncio.sleep(self.DELAY)
                    break

                except TelegramError as e:
                    msg = str(e)
                    # Extract retry_after from FloodControl / RetryAfter errors
                    retry_after = None
                    if hasattr(e, "retry_after") and e.retry_after:
                        retry_after = int(e.retry_after) + 2   # +2 safety buffer
                    else:
                        # Parse "Retry in X seconds" from message text
                        import re
                        m = re.search(r"retry[^\d]*(\d+)", msg, re.IGNORECASE)
                        if m: retry_after = int(m.group(1)) + 2

                    if retry_after:
                        self.on_log(
                            f"⏳  Flood control — waiting {retry_after}s before retry "
                            f"(attempt {attempt}/{self.MAX_RETRIES})  [{os.path.basename(path)}]",
                            "warn")
                        self.on_item(path,"Telegram","Retrying",None,attempt)
                        self.on_stat(f"⏳ Flood wait {retry_after}s…")
                        # Count down visibly every 5 seconds
                        waited = 0
                        while waited < retry_after and self.active:
                            chunk = min(5, retry_after - waited)
                            await asyncio.sleep(chunk)
                            waited += chunk
                            remaining = retry_after - waited
                            if remaining > 0:
                                self.on_stat(f"⏳ Resuming in {remaining}s…")
                        # Put file back at front for retry (re-queue)
                        continue   # retry the same file

                    else:
                        self.on_log(f"❌  Telegram: {e}  (attempt {attempt}/{self.MAX_RETRIES})","err")
                        if attempt < self.MAX_RETRIES:
                            backoff = 2 ** attempt   # 2, 4, 8, 16 …
                            self.on_log(f"   Retrying in {backoff}s…","sub")
                            self.on_item(path,"Telegram","Retrying",None,attempt)
                            await asyncio.sleep(backoff)
                        continue

                except Exception as e:
                    self.on_log(f"❌  {e}","err")
                    self.on_item(path,"Telegram","Retrying" if attempt < self.MAX_RETRIES else "Error",None,attempt)
                    if attempt < self.MAX_RETRIES:
                        await asyncio.sleep(2 ** attempt)
                    continue

            if not success and self.active:
                self.on_log(f"💀  Gave up after {self.MAX_RETRIES} attempts: {os.path.basename(path)}","err")
                self.on_item(path,"Telegram","Error",0.0,self.MAX_RETRIES)
                self.on_skip("error")

            self.on_stat("Watching…")


class FolderWatcher(FileSystemEventHandler):
    def __init__(self,sinks,exts,log_cb,stability_enabled=True,stability_delay=2.0):
        self.sinks,self.exts,self.log=sinks,exts,log_cb
        self.stability_enabled=stability_enabled; self.stability_delay=max(0.2,float(stability_delay or 2))
        self._pending=set(); self._lock=threading.Lock()
    def on_created(self,event):
        if event.is_directory: return
        p=event.src_path
        if self.exts and Path(p).suffix.lower() not in self.exts: return
        with self._lock:
            if p in self._pending: return
            self._pending.add(p)
        self.log(f"📄  New: {os.path.basename(p)}","accent2")
        threading.Thread(target=self._wait_and_enqueue,args=(p,),daemon=True).start()
    def _wait_and_enqueue(self,p):
        try:
            if self.stability_enabled:
                last=None
                while os.path.exists(p):
                    try: state=(os.path.getsize(p),os.path.getmtime(p))
                    except OSError: state=None
                    if state and state==last: break
                    last=state; time.sleep(self.stability_delay)
            if os.path.exists(p):
                for sink in self.sinks: sink.enqueue(p)
        finally:
            with self._lock: self._pending.discard(p)


class SpeedGraph(tk.Canvas):
    N=60
    def __init__(self,parent,C,**kw):
        super().__init__(parent,bg=C["graph_bg"],bd=0,highlightthickness=0,**kw)
        self.C=C; self.pts=deque([0]*self.N,maxlen=self.N)
        self.bind("<Configure>",lambda e:self._draw())
    def push(self,v):
        self.pts.append(v); self._draw()
    def _draw(self):
        C=self.C; w,h=self.winfo_width(),self.winfo_height()
        if w<4 or h<4: return
        self.delete("all")
        for i in range(4):
            y=int(h*i/4)
            self.create_line(0,y,w,y,fill=C["border"],dash=(2,6))
        pts=list(self.pts); mx=max(max(pts),1)
        xs=[int(w*i/(self.N-1)) for i in range(self.N)]
        ys=[int(h-(v/mx)*(h-4)) for v in pts]
        poly=[0,h]+[x for pair in zip(xs,ys) for x in pair]+[w,h]
        self.create_polygon(poly,fill=C["graph_fi"],outline="")
        for i in range(len(xs)-1):
            self.create_line(xs[i],ys[i],xs[i+1],ys[i+1],fill=C["graph_ln"],width=2,smooth=True)
        pk=max(pts)
        lbl=f"{pk/1024:.1f} KB/s" if pk<1048576 else f"{pk/1048576:.2f} MB/s"
        self.create_text(w-6,6,text=lbl,anchor="ne",fill=C["graph_ln"],font=("Consolas",8))


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"TelegramBackup {VERSION}  •  {AUTHOR}")
        self.geometry("980x680"); self.minsize(860,560); self.resizable(True,True)
        cfg=load_cfg()
        self.theme_name=tk.StringVar(value=cfg.get("theme","dark"))
        self.C=THEMES[self.theme_name.get()]
        self.v_token=tk.StringVar(value=cfg.get("token",""))
        self.v_chat=tk.StringVar(value=cfg.get("chat_id",""))
        self.v_telegram_enabled=tk.BooleanVar(value=cfg.get("telegram_enabled",True))
        self.v_drive_enabled=tk.BooleanVar(value=cfg.get("drive_enabled",False))
        self.v_drive_credentials=tk.StringVar(value=cfg.get("drive_credentials",""))
        self.v_drive_folder_id=tk.StringVar(value=cfg.get("drive_folder_id",""))
        self.v_drive_folder_name=tk.StringVar(value=cfg.get("drive_folder_name","TelegramBackup"))
        self.v_drive_status=tk.StringVar(value="Not configured")
        self.v_sub=tk.BooleanVar(value=cfg.get("subfolders",True))
        self.v_autostart=tk.BooleanVar(value=cfg.get("autostart",False))
        self.v_bg_mode=tk.BooleanVar(value=cfg.get("bg_mode",True))
        self.v_min_tray=tk.BooleanVar(value=cfg.get("min_tray",True))
        self.v_all_files=tk.BooleanVar(value=cfg.get("all_files",True))
        self.v_start_minimized=tk.BooleanVar(value=cfg.get("start_minimized",False))
        self.v_notifications=tk.BooleanVar(value=cfg.get("notifications",True))
        self.v_stability_enabled=tk.BooleanVar(value=cfg.get("stability_enabled",True))
        self.v_stability_delay=tk.StringVar(value=str(cfg.get("stability_delay",2)))
        self.v_retry_count=tk.StringVar(value=str(cfg.get("retry_count",5)))
        self.v_retry_delay=tk.StringVar(value=str(cfg.get("retry_delay",2)))
        self.v_bandwidth=tk.StringVar(value=str(cfg.get("bandwidth_limit",0)))
        self.v_limit_label=tk.StringVar(value=format_limit(parse_limit(cfg.get("bandwidth_limit",0))))
        self.v_custom_bandwidth=tk.StringVar(value=str(cfg.get("custom_bandwidth", "")))
        self.v_pause_offline=tk.BooleanVar(value=cfg.get("pause_when_offline",True))
        self.v_network_interval=tk.StringVar(value=str(cfg.get("network_check_interval",30)))
        self.v_queue_warning=tk.StringVar(value=str(cfg.get("queue_warning",2500)))
        self.v_status=tk.StringVar(value="⏹  Stopped")
        self.v_current=tk.StringVar(value="No active upload")
        self.v_destination=tk.StringVar(value="—")
        self.v_queue=tk.StringVar(value="0")
        self.v_avg_speed=tk.StringVar(value="0 KB/s")
        self.v_peak_speed=tk.StringVar(value="0 KB/s")
        self.v_today_data=tk.StringVar(value="0 B")
        self.v_health=tk.StringVar(value="Healthy")
        self.v_summary=tk.StringVar(value="Destination: —    Queue: 0    Speed: 0 KB/s    Health: Healthy")
        self.v_uploaded=tk.StringVar(value="0"); self.v_skipped=tk.StringVar(value="0")
        self.v_size_skip=tk.StringVar(value="0"); self.v_err_skip=tk.StringVar(value="0")
        self.v_dup_skip=tk.StringVar(value="0")
        self.v_folders_n=tk.StringVar(value="0 folders"); self.v_files_n=tk.StringVar(value="0 files")
        self.v_speed=tk.StringVar(value="0 KB/s")
        saved_cats=set(cfg.get("categories",list(FILE_CATS.keys())))
        self.v_cats={c:tk.BooleanVar(value=(c in saved_cats)) for c in FILE_CATS}
        self.watch_folders=cfg.get("watch_folders",[])
        self.n_uploaded=self.n_skipped=self.n_size=self.n_err=self.n_dup=0
        self.speed_hist=deque([0.0]*60,maxlen=60)
        self.uploader=None; self.drive_uploader=None; self.drive_client=None; self.sinks=[]; self.observers=[]; self.running=False
        self.paused=False; self.pause_event=threading.Event(); self.pause_event.clear()
        self.limiter=BandwidthLimiter(parse_limit(self.v_bandwidth.get()))
        self.cancel_event=threading.Event(); self.network_last=None; self.network_last_check=0.0
        self.stats=StatsManager(); self.queue_items={}; self.queue_order=[]; self.cancelled_paths=set()
        self.tray_icon=None; self._quitting=False
        self.cur_step=0; self.step_done=[False]*8
        self._active_tab="main"; self._log_lines=[]; self._log_filter=tk.StringVar(value="All"); self._log_search=tk.StringVar()
        self.ui_events=queue.Queue(); self.log_lock=threading.Lock()
        has_telegram = self.v_telegram_enabled.get() and cfg.get("token") and cfg.get("chat_id")
        has_drive = self.v_drive_enabled.get() and cfg.get("drive_credentials")
        if (has_telegram or has_drive) and self.watch_folders:
            self.cur_step=8
            for i in range(8): self.step_done[i]=True
        self.configure(bg=self.C["bg"])
        self._build_layout()
        self.protocol("WM_DELETE_WINDOW",self._on_close)
        if self.cur_step==8: self.after(500,self._start_backup)
        self._refresh_fc(); self.after(100,self._poll_ui_events)

    def _apply_theme(self):
        self.C=THEMES[self.theme_name.get()]; self.configure(bg=self.C["bg"])

    def _toggle_theme(self):
        self.theme_name.set("light" if self.theme_name.get()=="dark" else "dark")
        self._apply_theme(); self._save(); self._rebuild()

    def _rebuild(self):
        for w in self.winfo_children(): w.destroy()
        self._build_layout()
        if self.cur_step==8 and hasattr(self,"log_box"): self._repopulate_log()

    def _build_layout(self):
        C=self.C
        self.grid_rowconfigure(0,weight=1); self.grid_columnconfigure(0,weight=0); self.grid_columnconfigure(1,weight=1)
        self.sidebar=tk.Frame(self,bg=C["sidebar"],width=244)
        self.sidebar.grid(row=0,column=0,sticky="nsew"); self.sidebar.grid_propagate(False)
        self.content=tk.Frame(self,bg=C["bg"])
        self.content.grid(row=0,column=1,sticky="nsew")
        self.content.grid_rowconfigure(0,weight=1); self.content.grid_columnconfigure(0,weight=1)
        self._build_sidebar(); self._render_page()

    def _build_sidebar(self):
        C=self.C
        for w in self.sidebar.winfo_children(): w.destroy()
        # accent stripe
        tk.Frame(self.sidebar,bg=C["accent"],height=3).pack(fill="x")
        # logo
        top=tk.Frame(self.sidebar,bg=C["sidebar"]); top.pack(fill="x",pady=(14,0))
        tk.Label(top,text="📡",font=("Segoe UI Emoji",26),bg=C["sidebar"],fg=C["accent"]).pack()
        tk.Label(top,text="TelegramBackup",font=("Consolas",12,"bold"),bg=C["sidebar"],fg=C["text"]).pack()
        tk.Label(top,text=f"{VERSION}  •  {AUTHOR}",font=("Consolas",8,"italic"),bg=C["sidebar"],fg=C["accent"]).pack()
        tk.Label(top,text=f"🖥️  {get_machine_id()}",font=("Consolas",8),bg=C["sidebar"],fg=C["sub"]).pack(pady=(2,10))
        self._sdiv()
        if self.cur_step<8:
            for i,(num,title,icon) in enumerate(WIZARD_STEPS):
                ic=i==self.cur_step; id_=self.step_done[i]; il=i>self.cur_step
                bg=C["hover"] if ic else C["sidebar"]
                fg=C["accent"] if ic else (C["done"] if id_ else (C["sub"] if il else C["text"]))
                dbg=C["accent"] if ic else (C["done"] if id_ else C["border"])
                dfg=C["sidebar"] if (ic or id_) else C["sub"]
                dt="✓" if (id_ and not ic) else str(num)
                row=tk.Frame(self.sidebar,bg=bg); row.pack(fill="x",padx=6,pady=1)
                if not il: row.configure(cursor="hand2"); row.bind("<Button-1>",lambda e,x=i:self._goto(x))
                tk.Label(row,text=dt,width=2,font=("Consolas",8,"bold"),bg=dbg,fg=dfg,pady=2).pack(side="left",padx=(8,6),pady=6)
                tk.Label(row,text=f"{icon}  {title}",font=("Consolas",8),bg=bg,fg=fg).pack(side="left",pady=6)
        else:
            for lbl,tab,icon in [
                ("Dashboard","main","📊"),
                ("Backup Sources","folders","📁"),
                ("Destinations","destinations","☁"),
                ("File Filters","filetypes","🗂"),
                ("Activity","activity","☷"),
                ("Statistics","stats","▥"),
                ("Settings","settings","⚙"),
            ]:
                cmd=lambda x=tab:self._switch_tab(x)
                act=self._active_tab==tab
                bg=C["hover"] if act else C["sidebar"]; fg=C["accent"] if act else C["text"]
                f=tk.Frame(self.sidebar,bg=bg,cursor="hand2"); f.pack(fill="x",padx=6,pady=1)
                f.bind("<Button-1>",lambda e,c=cmd:c())
                f.bind("<Enter>",lambda e,fr=f:fr.configure(bg=C["hover"]))
                f.bind("<Leave>",lambda e,fr=f,ob=bg:fr.configure(bg=ob))
                tk.Label(f,text=f"{icon}  {lbl}",font=("Segoe UI",9),bg=bg,fg=fg).pack(side="left",padx=14,pady=9)
        self._sdiv()
        self._status_lbl=tk.Label(self.sidebar,textvariable=self.v_status,font=("Consolas",8),bg=C["sidebar"],fg=C["accent"],width=28,anchor="w"); self._status_lbl.pack(padx=10,pady=(4,2))
        rw=tk.Frame(self.sidebar,bg=C["sidebar"]); rw.pack(fill="x",padx=8,pady=2)
        for var,lbl,clr in [(self.v_uploaded,"✅ sent",C["done"]),(self.v_skipped,"⏭ skip",C["warn"])]:
            f=tk.Frame(rw,bg=C["tag"]); f.pack(side="left",expand=True,fill="x",padx=2)
            tk.Label(f,textvariable=var,font=("Consolas",11,"bold"),bg=C["tag"],fg=clr,width=6,anchor="center").pack()
            tk.Label(f,text=lbl,font=("Consolas",7),bg=C["tag"],fg=C["sub"]).pack(pady=(0,4))
        self._sdiv()
        is_dark=self.theme_name.get()=="dark"
        tk.Label(self.sidebar,text="●  "+("Ready" if self.running else "Stopped"),font=("Segoe UI",9,"bold"),bg=C["sidebar"],fg=C["done"] if self.running else C["sub"]).pack(anchor="w",padx=14,pady=(8,2))
        tk.Button(self.sidebar,text="☀  Light Mode" if is_dark else "☾  Dark Mode",
                  command=self._toggle_theme,bg=C["tag"],fg=C["text"],font=("Consolas",9),
                  relief="flat",cursor="hand2",pady=6).pack(fill="x",padx=10,pady=(4,12))

    def _sdiv(self):
        tk.Frame(self.sidebar,bg=self.C["border"],height=1).pack(fill="x",padx=10,pady=4)

    def _render_page(self):
        for w in self.content.winfo_children(): w.destroy()
        if self.cur_step==8: self._page_dashboard()
        else: [self._p1,self._p2,self._p3,self._p4,self._p5,self._p6,self._p7,self._p8][self.cur_step]()

    def _goto(self,idx): self.cur_step=idx; self._build_sidebar(); self._render_page()
    def _goto_wizard(self): self.cur_step=0; self._build_sidebar(); self._render_page()
    def _switch_tab(self,tab):
        self._active_tab=tab; self._build_sidebar()
        for w in self.content.winfo_children(): w.destroy()
        self._page_dashboard()

    # ── Wizard helpers ────────────────────────────────────────────────────────
    def _outer(self):
        C=self.C; f=tk.Frame(self.content,bg=C["bg"])
        f.grid(row=0,column=0,sticky="nsew",padx=32,pady=24); f.grid_columnconfigure(0,weight=1)
        return f

    def _whdr(self,parent):
        C=self.C; num,title,icon=WIZARD_STEPS[self.cur_step]
        tk.Label(parent,text=f"STEP {num} OF 8",font=("Consolas",8),bg=C["bg"],fg=C["sub"]).grid(row=0,column=0,sticky="w")
        hf=tk.Frame(parent,bg=C["bg"]); hf.grid(row=1,column=0,sticky="w",pady=(2,16))
        tk.Label(hf,text=icon+" ",font=("Segoe UI Emoji",20),bg=C["bg"]).pack(side="left")
        tk.Label(hf,text=title,font=("Consolas",20,"bold"),bg=C["bg"],fg=C["text"]).pack(side="left")

    def _wbox(self,parent,lines,row=0):
        C=self.C; b=tk.Frame(parent,bg=C["card"],highlightbackground=C["border"],highlightthickness=1)
        b.grid(row=row,column=0,sticky="ew",pady=(0,10))
        for i,(icon,text) in enumerate(lines):
            r=tk.Frame(b,bg=C["card"]); r.pack(fill="x",padx=14,pady=(8 if i==0 else 2,2 if i<len(lines)-1 else 8))
            tk.Label(r,text=icon,font=("Segoe UI Emoji",12),bg=C["card"]).pack(side="left",padx=(0,8))
            tk.Label(r,text=text,font=("Consolas",9),bg=C["card"],fg=C["text"],wraplength=500,justify="left").pack(side="left",fill="x",expand=True)

    def _wtip(self,parent,text,row=0,color=None):
        C=self.C; color=color or C["warn"]
        f=tk.Frame(parent,bg=C["tag"],highlightbackground=color,highlightthickness=1)
        f.grid(row=row,column=0,sticky="ew",pady=(0,8))
        tk.Label(f,text=text,font=("Consolas",8),bg=C["tag"],fg=color,wraplength=560,justify="left",pady=8).pack(padx=12,anchor="w")

    def _wlink(self,parent,text,url,row=0):
        C=self.C
        tk.Button(parent,text=f"🌐  {text}",command=lambda:webbrowser.open(url),
                  bg=C["accent2"],fg="white",font=("Consolas",9),relief="flat",cursor="hand2",padx=12,pady=5
                  ).grid(row=row,column=0,sticky="w",pady=(0,10))

    def _wentry(self,parent,label,var,row=0,show=""):
        C=self.C
        tk.Label(parent,text=label,font=("Consolas",8,"bold"),bg=C["bg"],fg=C["sub"]).grid(row=row,column=0,sticky="w",pady=(10,2))
        e=tk.Entry(parent,textvariable=var,font=("Consolas",11),bg=C["inp"],fg=C["text"],relief="flat",
                   insertbackground=C["text"],bd=0,show=show,highlightbackground=C["border"],highlightthickness=1)
        e.grid(row=row+1,column=0,sticky="ew",ipady=8)
        return e

    def _wfb(self,parent,row):
        C=self.C; lbl=tk.Label(parent,text="",font=("Consolas",8),bg=C["bg"],fg=C["warn"])
        lbl.grid(row=row,column=0,sticky="w",pady=2); return lbl

    def _wnav(self,parent,row,back=True,next_cmd=None,next_text="Next  →"):
        C=self.C; f=tk.Frame(parent,bg=C["bg"]); f.grid(row=row,column=0,sticky="ew",pady=(16,0))
        if back and self.cur_step>0:
            tk.Button(f,text="← Back",command=lambda:self._goto(self.cur_step-1),
                      bg=C["tag"],fg=C["sub"],font=("Consolas",9),relief="flat",cursor="hand2",padx=14,pady=7).pack(side="left")
        if next_cmd:
            tk.Button(f,text=next_text,command=next_cmd,
                      bg=C["accent"],fg=C["sidebar"],font=("Consolas",10,"bold"),relief="flat",cursor="hand2",padx=22,pady=7).pack(side="right")

    # ── Wizard pages ──────────────────────────────────────────────────────────
    def _p1(self):
        b=self._outer(); self._whdr(b)
        self._wbox(b,[("1️⃣","Open Telegram and search for @BotFather."),
                      ("2️⃣","Send /newbot — pick a name and a username ending in 'bot'."),
                      ("3️⃣","BotFather sends a TOKEN — copy it, you need it in Step 3.")],row=2)
        self._wlink(b,"Open @BotFather","https://t.me/BotFather",row=3)
        self._wtip(b,"💡  Token looks like:  1234567890:REPLACE_WITH_BOT_TOKEN",row=4)
        tk.Checkbutton(b,text="  Enable Telegram Backup",variable=self.v_telegram_enabled,
                       bg=self.C["bg"],fg=self.C["text"],selectcolor=self.C["tag"],
                       activebackground=self.C["bg"],font=("Consolas",10,"bold"),cursor="hand2").grid(row=5,column=0,sticky="w",pady=(4,0))
        tk.Label(b,text="Uncheck this if you want Google Drive only.",font=("Consolas",8),bg=self.C["bg"],fg=self.C["sub"]).grid(row=6,column=0,sticky="w")
        self._wnav(b,20,back=False,next_cmd=lambda:self._next(0),next_text="Continue  →")

    def _p2(self):
        b=self._outer(); self._whdr(b)
        if not self.v_telegram_enabled.get():
            self._wbox(b,[("☁️","Telegram Backup is disabled."),("✅","Continue to the folder and Google Drive setup.")],row=2)
            self._wnav(b,20,next_cmd=lambda:self._next(1),next_text="Skip Telegram  →")
            return
        self._wbox(b,[("1️⃣","Open your Telegram group or channel."),
                      ("2️⃣","Tap group name → Add Members → search your bot username."),
                      ("3️⃣","For channels: make it Admin with Post Messages permission."),
                      ("4️⃣","Add @userinfobot to the group — it replies instantly with the group ID.")],row=2)
        self._wlink(b,"Open @userinfobot","https://t.me/userinfobot",row=3)
        self._wtip(b,"💡  Group IDs are negative: -1001234567890  |  Channel: @mychannel",row=4,color=self.C["accent"])
        self._wnav(b,20,next_cmd=lambda:self._next(1),next_text="Bot is in group  →")

    def _p3(self):
        C=self.C; b=self._outer(); b.grid_columnconfigure(0,weight=1); self._whdr(b)
        if not self.v_telegram_enabled.get():
            self._wbox(b,[("☁️","Telegram Backup is disabled."),("✅","No bot token is needed for Google Drive-only mode.")],row=2)
            self._wnav(b,20,next_cmd=lambda:self._next(2),next_text="Skip Telegram  →")
            return
        self._wentry(b,"BOT TOKEN",self.v_token,row=2)
        self.fb3=self._wfb(b,4)
        tk.Button(b,text="🔍  Test Connection",command=self._test_token,
                  bg=C["tag"],fg=C["text"],font=("Consolas",9),relief="flat",cursor="hand2",padx=12,pady=5
                  ).grid(row=5,column=0,sticky="w",pady=(6,0))
        self._wnav(b,20,next_cmd=self._val3)

    def _test_token(self):
        t=self.v_token.get().strip()
        if not t: self.fb3.config(text="⚠  Paste token first."); return
        self.fb3.config(text="⏳  Connecting…",fg=self.C["sub"]); self.update()
        async def _t():
            try: info=await Bot(token=t).get_me(); return f"✅  @{info.username}",True
            except Exception as e: return f"❌  {e}",False
        def run():
            loop=asyncio.new_event_loop(); msg,ok=loop.run_until_complete(_t()); loop.close()
            self.fb3.config(text=msg,fg=self.C["done"] if ok else self.C["err"])
        threading.Thread(target=run,daemon=True).start()

    def _val3(self):
        if not self.v_telegram_enabled.get(): self._next(2); return
        if not self.v_token.get().strip(): self.fb3.config(text="⚠  Token required."); return
        self._next(2)

    def _p4(self):
        C=self.C; b=self._outer(); b.grid_columnconfigure(0,weight=1); self._whdr(b)
        if not self.v_telegram_enabled.get():
            self._wbox(b,[("☁️","Telegram Backup is disabled."),("✅","No chat or group ID is needed for Google Drive-only mode.")],row=2)
            self._wnav(b,20,next_cmd=lambda:self._next(3),next_text="Skip Telegram  →")
            return
        self._wentry(b,"CHAT / GROUP ID  (e.g. -1001234567890 or @channel)",self.v_chat,row=2)
        self.fb4=self._wfb(b,4)
        self._wtip(b,"💡  Add @userinfobot to your group — it posts the ID instantly.",row=5,color=self.C["accent2"])
        self._wnav(b,20,next_cmd=self._val4)

    def _val4(self):
        if not self.v_telegram_enabled.get(): self._next(3); return
        if not self.v_chat.get().strip(): self.fb4.config(text="⚠  Chat ID required."); return
        self._next(3)

    def _p5(self):
        C=self.C; b=self._outer(); b.grid_columnconfigure(0,weight=1); self._whdr(b)
        tk.Label(b,text="Add one or more folders. Any new file dropped in them goes straight to Telegram.",
                 font=("Consolas",9),bg=C["bg"],fg=C["sub"],justify="left"
                 ).grid(row=2,column=0,sticky="w",pady=(0,10))
        lf=tk.Frame(b,bg=C["card"],highlightbackground=C["border"],highlightthickness=1)
        lf.grid(row=3,column=0,sticky="ew",pady=(0,8)); lf.grid_columnconfigure(0,weight=1)
        self._flf=lf; self._render_folder_list(lf)
        br=tk.Frame(b,bg=C["bg"]); br.grid(row=4,column=0,sticky="w")
        tk.Button(br,text="➕  Add Folder",command=lambda:self._add_folder_wiz(lf),
                  bg=C["accent"],fg=C["sidebar"],font=("Consolas",9,"bold"),relief="flat",cursor="hand2",padx=14,pady=7).pack(side="left",padx=(0,8))
        tk.Checkbutton(b,text="  Include subfolders (recursive)",variable=self.v_sub,
                       bg=C["bg"],fg=C["text"],selectcolor=C["tag"],activebackground=C["bg"],
                       font=("Consolas",9),cursor="hand2").grid(row=5,column=0,sticky="w",pady=(8,0))
        self.fb5=self._wfb(b,6); self._wnav(b,20,next_cmd=self._val5)

    def _render_folder_list(self,frame):
        C=self.C
        for w in frame.winfo_children(): w.destroy()
        if not self.watch_folders:
            tk.Label(frame,text="  No folders yet. Click ➕ Add Folder.",font=("Consolas",9),
                     bg=C["card"],fg=C["sub"],pady=14).pack(anchor="w",padx=14); return
        for i,folder in enumerate(self.watch_folders):
            r=tk.Frame(frame,bg=C["card"]); r.pack(fill="x",padx=10,pady=4); r.grid_columnconfigure(1,weight=1)
            tk.Label(r,text="📁",font=("Segoe UI Emoji",12),bg=C["card"]).grid(row=0,column=0,padx=(0,8))
            tk.Label(r,text=folder,font=("Consolas",8),bg=C["card"],fg=C["text"],anchor="w",wraplength=420).grid(row=0,column=1,sticky="w")
            idx=i
            tk.Button(r,text="✕",command=lambda x=idx:self._rm_folder(x,frame),
                      bg=C["err"],fg="white",font=("Consolas",8),relief="flat",cursor="hand2",padx=6,pady=2).grid(row=0,column=2,padx=(8,0))

    def _add_folder_wiz(self,frame):
        f=filedialog.askdirectory(title="Select folder to watch")
        if f and f not in self.watch_folders: self.watch_folders.append(f); self._render_folder_list(frame)

    def _rm_folder(self,idx,frame):
        if 0<=idx<len(self.watch_folders): self.watch_folders.pop(idx); self._render_folder_list(frame)

    def _val5(self):
        if not self.watch_folders: self.fb5.config(text="⚠  Add at least one folder."); return
        self._next(4)

    def _p6(self):
        C=self.C; b=self._outer(); b.grid_columnconfigure(0,weight=1); self._whdr(b)
        af=tk.Frame(b,bg=C["card"],highlightbackground=C["accent"],highlightthickness=1)
        af.grid(row=2,column=0,sticky="ew",pady=(0,10))
        tk.Checkbutton(af,text="  ✅  Back up ALL file types (recommended)",variable=self.v_all_files,
                       command=self._tog6,bg=C["card"],fg=C["accent"],selectcolor=C["tag"],
                       activebackground=C["card"],font=("Consolas",10,"bold"),cursor="hand2").pack(anchor="w",padx=12,pady=10)
        tk.Label(b,text="— OR — pick categories:",font=("Consolas",8),bg=C["bg"],fg=C["sub"]).grid(row=3,column=0,sticky="w",pady=(0,6))
        cf=tk.Frame(b,bg=C["bg"]); cf.grid(row=4,column=0,sticky="ew"); cf.grid_columnconfigure((0,1,2,3),weight=1)
        self.cat_chks6={}
        for idx,(cat,exts) in enumerate(FILE_CATS.items()):
            ri,ci=divmod(idx,4)
            ff=tk.Frame(cf,bg=C["card"],highlightbackground=C["border"],highlightthickness=1); ff.grid(row=ri,column=ci,padx=3,pady=3,sticky="ew")
            chk=tk.Checkbutton(ff,text=cat,variable=self.v_cats[cat],bg=C["card"],fg=C["text"],selectcolor=C["tag"],
                               activebackground=C["card"],font=("Consolas",8),cursor="hand2",command=self._unchk6)
            chk.pack(anchor="w",padx=8,pady=4)
            tk.Label(ff,text=f"{len(exts)} types",font=("Consolas",7),bg=C["card"],fg=C["sub"]).pack(anchor="w",padx=20,pady=(0,3))
            self.cat_chks6[cat]=chk
        self._tog6(); self._wnav(b,20,next_cmd=lambda:self._next(5))

    def _tog6(self):
        st="disabled" if self.v_all_files.get() else "normal"
        if hasattr(self,"cat_chks6"):
            for chk in self.cat_chks6.values(): chk.configure(state=st)

    def _unchk6(self): self.v_all_files.set(False); self._tog6()

    def _p7(self):
        C=self.C; b=self._outer(); b.grid_columnconfigure(0,weight=1); self._whdr(b)
        dest=tk.Frame(b,bg=C["card"],highlightbackground=C["accent"],highlightthickness=1)
        dest.grid(row=2,column=0,sticky="ew",pady=(0,8)); dest.grid_columnconfigure(1,weight=1)
        tk.Label(dest,text="BACKUP DESTINATIONS",font=("Consolas",8,"bold"),bg=C["card"],fg=C["sub"]).grid(row=0,column=0,columnspan=2,sticky="w",padx=12,pady=(10,4))
        tk.Checkbutton(dest,text="  Telegram Backup",variable=self.v_telegram_enabled,
                       bg=C["card"],fg=C["text"],selectcolor=C["tag"],activebackground=C["card"],
                       font=("Consolas",10,"bold"),cursor="hand2").grid(row=1,column=0,sticky="w",padx=12,pady=5)
        tk.Checkbutton(dest,text="  Google Drive Backup",variable=self.v_drive_enabled,
                       command=self._toggle_destination_controls,bg=C["card"],fg=C["text"],selectcolor=C["tag"],activebackground=C["card"],
                       font=("Consolas",10,"bold"),cursor="hand2").grid(row=2,column=0,sticky="w",padx=12,pady=5)
        tk.Label(dest,text="Choose either service or enable both. New files will be sent to every enabled destination.",
                 font=("Consolas",8),bg=C["card"],fg=C["sub"],wraplength=520,justify="left").grid(row=3,column=0,columnspan=2,sticky="w",padx=12,pady=(2,10))

        drive=tk.Frame(b,bg=C["card"],highlightbackground=C["border"],highlightthickness=1)
        drive.grid(row=3,column=0,sticky="ew",pady=(0,8)); drive.grid_columnconfigure(0,weight=1)
        tk.Label(drive,text="GOOGLE DRIVE SETUP",font=("Consolas",8,"bold"),bg=C["card"],fg=C["sub"]).grid(row=0,column=0,sticky="w",padx=12,pady=(10,2))
        tk.Label(drive,text="Select the OAuth desktop credentials JSON downloaded from Google Cloud Console. It stays on this PC.",font=("Consolas",8),bg=C["card"],fg=C["sub"],wraplength=560,justify="left").grid(row=1,column=0,sticky="w",padx=12,pady=(0,6))
        self._wentry(drive,"GOOGLE CREDENTIALS JSON",self.v_drive_credentials,row=2)
        br=tk.Frame(drive,bg=C["card"]); br.grid(row=4,column=0,sticky="w",padx=12,pady=(6,2))
        tk.Button(br,text="📂 Browse",command=self._browse_drive_credentials,bg=C["tag"],fg=C["text"],font=("Consolas",8),relief="flat",cursor="hand2",padx=10,pady=5).pack(side="left",padx=(0,6))
        tk.Button(br,text="🔗 Connect & Test",command=lambda:self._test_drive_connection(getattr(self,"fb_drive_wiz",None)),bg=C["accent2"],fg="white",font=("Consolas",8,"bold"),relief="flat",cursor="hand2",padx=10,pady=5).pack(side="left",padx=(0,6))
        tk.Button(br,text="➕ Create Drive Folder",command=self._create_drive_folder,bg=C["accent"],fg=C["sidebar"],font=("Consolas",8,"bold"),relief="flat",cursor="hand2",padx=10,pady=5).pack(side="left")
        self.fb_drive_wiz=self._wfb(drive,5); self.fb_drive_wiz.grid_configure(padx=12)
        self._wentry(drive,"DRIVE FOLDER ID  (optional; leave empty for My Drive root)",self.v_drive_folder_id,row=6)
        self._toggle_destination_controls()

        opts=[(self.v_autostart,"🚀  Start with Windows","Launches on every boot automatically."),
              (self.v_bg_mode,"🔄  Run in background","Keeps backing up after closing the window."),
              (self.v_min_tray,"🔔  Minimize to tray","X hides to system tray instead of quitting.")]
        for i,(var,lbl,desc) in enumerate(opts):
            f=tk.Frame(b,bg=C["card"],highlightbackground=C["border"],highlightthickness=1)
            f.grid(row=4+i,column=0,sticky="ew",pady=4); f.grid_columnconfigure(1,weight=1)
            tk.Checkbutton(f,variable=var,bg=C["card"],selectcolor=C["tag"],activebackground=C["card"],cursor="hand2").grid(row=0,column=0,padx=(12,6),pady=8)
            inf=tk.Frame(f,bg=C["card"]); inf.grid(row=0,column=1,sticky="ew",pady=8)
            tk.Label(inf,text=lbl,font=("Consolas",9,"bold"),bg=C["card"],fg=C["text"]).pack(anchor="w")
            tk.Label(inf,text=desc,font=("Consolas",8),bg=C["card"],fg=C["sub"]).pack(anchor="w")
        if not TRAY_OK: self._wtip(b,"⚠  Tray needs: pip install pystray pillow",row=8)
        self._wnav(b,20,next_cmd=self._val7)

    def _current_drive_feedback(self):
        for name in ("fb_drive_wiz", "fb_drive"):
            feedback=getattr(self,name,None)
            try:
                if feedback and feedback.winfo_exists(): return feedback
            except tk.TclError:
                pass
        return None

    def _toggle_destination_controls(self):
        feedback=self._current_drive_feedback()
        if feedback:
            enabled=self.v_drive_enabled.get()
            state="normal" if enabled else "disabled"
            try:
                for child in feedback.master.winfo_children():
                    if isinstance(child,(tk.Entry,tk.Button)):
                        child.configure(state=state)
            except tk.TclError:
                pass
        if hasattr(self,"_drive_toggle_btn"):
            self._drive_toggle_btn.configure(text="☁  Google Drive Backup: ON" if self.v_drive_enabled.get() else "☁  Google Drive Backup: OFF")

    def _browse_drive_credentials(self):
        path=filedialog.askopenfilename(title="Select Google OAuth desktop credentials JSON",filetypes=[("JSON files","*.json"),("All files","*.*")])
        if path: self.v_drive_credentials.set(path)

    def _set_drive_feedback(self,feedback,text,color=None):
        if feedback and feedback.winfo_exists(): feedback.config(text=text,fg=color or self.C["sub"])
        self.v_drive_status.set(text)

    def _test_drive_connection(self,feedback=None):
        if not self.v_drive_credentials.get().strip():
            self._set_drive_feedback(feedback,"⚠  Select credentials.json first.",self.C["warn"]); return
        if not drive_available():
            self._set_drive_feedback(feedback,"⚠  "+drive_install_hint(),self.C["warn"]); return
        self._set_drive_feedback(feedback,"⏳  Google authorization will open in your browser…",self.C["sub"])
        def run():
            try:
                client=GoogleDriveClient(self.v_drive_credentials.get().strip())
                client.test_connection(); self.drive_client=client
                self.after(0,lambda:self._set_drive_feedback(feedback,"✅  Google Drive connected.",self.C["done"]))
            except Exception as exc:
                self.after(0,lambda:self._set_drive_feedback(feedback,"❌  "+str(exc),self.C["err"]))
        threading.Thread(target=run,daemon=True).start()

    def _create_drive_folder(self):
        if not self.v_drive_enabled.get():
            self.v_drive_enabled.set(True); self._toggle_destination_controls()
        if not self.v_drive_credentials.get().strip():
            self._browse_drive_credentials()
        if not self.v_drive_credentials.get().strip(): return
        if not drive_available():
            self._set_drive_feedback(self._current_drive_feedback(),"⚠  "+drive_install_hint(),self.C["warn"]); return
        feedback=self._current_drive_feedback()
        self._set_drive_feedback(feedback,"⏳  Connecting to Google Drive…",self.C["sub"])
        def run():
            try:
                client=self.drive_client or GoogleDriveClient(self.v_drive_credentials.get().strip())
                client.ensure_service(); result=client.create_folder(self.v_drive_folder_name.get().strip() or "TelegramBackup")
                self.drive_client=client; self.after(0,lambda:(self.v_drive_folder_id.set(result.get("id","")),self._set_drive_feedback(feedback,"✅  Folder ready: "+result.get("name","TelegramBackup"),self.C["done"])))
            except Exception as exc:
                self.after(0,lambda:self._set_drive_feedback(feedback,"❌  "+str(exc),self.C["err"]))
        threading.Thread(target=run,daemon=True).start()

    def _val7(self):
        if not self.v_telegram_enabled.get() and not self.v_drive_enabled.get():
            self.fb_drive_wiz.config(text="⚠  Enable Telegram Backup, Google Drive Backup, or both.",fg=self.C["warn"]); return
        if self.v_telegram_enabled.get() and (not self.v_token.get().strip() or not self.v_chat.get().strip()):
            self.fb_drive_wiz.config(text="⚠  Telegram is enabled but its token or chat ID is missing.",fg=self.C["warn"]); return
        if self.v_drive_enabled.get() and not self.v_drive_credentials.get().strip():
            self.fb_drive_wiz.config(text="⚠  Google Drive is enabled but credentials.json is missing.",fg=self.C["warn"]); return
        self._next(6)

    def _p8(self):
        C=self.C; b=self._outer(); b.grid_columnconfigure(0,weight=1)
        tk.Label(b,text="STEP 8 OF 8",font=("Consolas",8),bg=C["bg"],fg=C["sub"]).grid(row=0,column=0,sticky="w")
        hf=tk.Frame(b,bg=C["bg"]); hf.grid(row=1,column=0,sticky="w",pady=(2,14))
        tk.Label(hf,text="🚀 ",font=("Segoe UI Emoji",20),bg=C["bg"]).pack(side="left")
        tk.Label(hf,text="Review & Launch",font=("Consolas",20,"bold"),bg=C["bg"],fg=C["text"]).pack(side="left")
        card=tk.Frame(b,bg=C["card"],highlightbackground=C["accent"],highlightthickness=1)
        card.grid(row=2,column=0,sticky="ew",pady=(0,14))
        fl="\n".join(f"  • {f}" for f in self.watch_folders) if self.watch_folders else "None"
        es="All types" if self.v_all_files.get() else ", ".join(c for c,v in self.v_cats.items() if v.get()) or "None"
        dests=[]
        if self.v_telegram_enabled.get(): dests.append("Telegram")
        if self.v_drive_enabled.get(): dests.append("Google Drive")
        rows=[("🖥️  Machine ID",get_machine_id()),
              ("🎯  Destinations",", ".join(dests) or "None"),
              ("🔑  Token",self.v_token.get()[:24]+"…" if len(self.v_token.get())>24 else self.v_token.get()) if self.v_telegram_enabled.get() else ("🔑  Token","Disabled"),
              ("💬  Chat ID",self.v_chat.get() if self.v_telegram_enabled.get() else "Disabled"),("📁  Folders",fl),
              ("📂  Subfolders","Yes" if self.v_sub.get() else "No"),
              ("🗂️  File Types",es),("🚀  Autostart","Yes" if self.v_autostart.get() else "No"),
              ("🔄  Background","Yes" if self.v_bg_mode.get() else "No"),
              ("🔔  Tray","Yes" if self.v_min_tray.get() else "No")]
        for i,(k,v) in enumerate(rows):
            r=tk.Frame(card,bg=C["card"]); r.pack(fill="x",padx=14,pady=(8 if i==0 else 2,2 if i<len(rows)-1 else 8))
            tk.Label(r,text=k,font=("Consolas",8),bg=C["card"],fg=C["sub"],width=18,anchor="w").pack(side="left")
            tk.Label(r,text=v,font=("Consolas",8,"bold"),bg=C["card"],fg=C["text"],wraplength=380,anchor="w",justify="left").pack(side="left",fill="x",expand=True)
        tk.Button(b,text="🚀  Launch TelegramBackup",command=self._launch,
                  bg=C["accent"],fg=C["sidebar"],font=("Consolas",13,"bold"),relief="flat",cursor="hand2",pady=14
                  ).grid(row=3,column=0,sticky="ew")
        self._wnav(b,20,back=True,next_cmd=None)

    # ── Dashboard ─────────────────────────────────────────────────────────────
    def _toggle_destination(self,which):
        if which=="telegram": self.v_telegram_enabled.set(not self.v_telegram_enabled.get())
        else: self.v_drive_enabled.set(not self.v_drive_enabled.get())
        if not self.v_telegram_enabled.get() and not self.v_drive_enabled.get():
            if which=="telegram": self.v_telegram_enabled.set(True)
            else: self.v_drive_enabled.set(True)
            messagebox.showwarning("Backup destination", "At least one backup destination must remain enabled.")
            return
        self._save()
        if self.running: self._restart_backup()
        self._build_sidebar(); self._render_page()

    # ── Dashboard ─────────────────────────────────────────────────────────────
    def _page_dashboard(self):
        C=self.C; tab=self._active_tab
        outer=tk.Frame(self.content,bg=C["bg"])
        outer.grid(row=0,column=0,sticky="nsew",padx=20,pady=14)
        outer.grid_rowconfigure(2,weight=1); outer.grid_columnconfigure(0,weight=1)
        tb=tk.Frame(outer,bg=C["bg"]); tb.grid(row=0,column=0,sticky="ew",pady=(0,10))
        for tid,tlbl in [("main","Dashboard"),("folders","Backup Sources"),("destinations","Destinations"),("filetypes","File Filters"),("activity","Activity"),("stats","Statistics"),("settings","Settings")]:
            act=tab==tid
            tk.Button(tb,text=tlbl,command=lambda x=tid:self._switch_tab(x),
                      bg=C["accent"] if act else C["tag"],fg=C["sidebar"] if act else C["sub"],
                      font=("Consolas",9,"bold" if act else "normal"),relief="flat",cursor="hand2",padx=12,pady=5
                      ).pack(side="left",padx=(0,4))
        if tab=="main": self._tab_main(outer)
        elif tab=="folders": self._tab_folders(outer)
        elif tab=="destinations": self._tab_destinations(outer)
        elif tab=="filetypes": self._tab_filetypes(outer)
        elif tab=="activity": self._tab_activity(outer)
        elif tab=="stats": self._tab_stats(outer)
        elif tab=="settings": self._tab_settings(outer)
        elif tab=="log": self._tab_activity(outer)

    def _tab_main(self,outer):
        C=self.C; outer.grid_rowconfigure(5,weight=1)
        status=tk.Frame(outer,bg=C["card"],highlightbackground=C["accent"],highlightthickness=1); status.grid(row=1,column=0,sticky="ew",pady=(0,8)); status.grid_columnconfigure(1,weight=1)
        tk.Label(status,textvariable=self.v_status,font=("Segoe UI",13,"bold"),bg=C["card"],fg=C["done"] if self.running else C["warn"]).grid(row=0,column=0,sticky="w",padx=14,pady=(10,2))
        tk.Label(status,textvariable=self.v_current,font=("Segoe UI",10),bg=C["card"],fg=C["text"]).grid(row=1,column=0,sticky="w",padx=14,pady=(0,10))
        tk.Label(status,textvariable=self.v_summary,font=("Segoe UI",9),bg=C["card"],fg=C["sub"]).grid(row=0,column=1,rowspan=2,sticky="e",padx=14)
        # backup destination controls
        dest=tk.Frame(outer,bg=C["bg"]); dest.grid(row=2,column=0,sticky="ew",pady=(0,8))
        dest.grid_columnconfigure((0,1),weight=1)
        telegram_on=self.v_telegram_enabled.get(); drive_on=self.v_drive_enabled.get()
        self._telegram_dest_btn=tk.Button(dest,text="📡  Telegram Backup  " + ("ON" if telegram_on else "OFF"),
                  command=lambda:self._toggle_destination("telegram"),bg=C["accent"] if telegram_on else C["tag"],
                  fg=C["sidebar"] if telegram_on else C["sub"],font=("Consolas",10,"bold"),relief="flat",cursor="hand2",pady=9)
        self._telegram_dest_btn.grid(row=0,column=0,sticky="ew",padx=(0,4))
        self._drive_dest_btn=tk.Button(dest,text="☁️  Google Drive Backup  " + ("ON" if drive_on else "OFF"),
                  command=lambda:self._toggle_destination("drive"),bg=C["accent2"] if drive_on else C["tag"],
                  fg="white" if drive_on else C["sub"],font=("Consolas",10,"bold"),relief="flat",cursor="hand2",pady=9)
        self._drive_dest_btn.grid(row=0,column=1,sticky="ew",padx=(4,0))
        status="Google Drive is ready." if self.v_drive_credentials.get() else "Google Drive is not configured yet."
        tk.Label(dest,text=status,font=("Consolas",8),bg=C["bg"],fg=C["done"] if self.v_drive_credentials.get() else C["sub"]).grid(row=1,column=1,sticky="w",padx=(8,0),pady=(3,0))
        tk.Button(dest,text="⚙ Configure Google Drive",command=lambda:self._switch_tab("settings"),bg=C["bg"],fg=C["accent2"],font=("Consolas",8,"underline"),relief="flat",cursor="hand2",bd=0).grid(row=1,column=0,sticky="w",padx=(8,0),pady=(3,0))
        # stat cards
        sc=tk.Frame(outer,bg=C["bg"]); sc.grid(row=3,column=0,sticky="ew",pady=(0,8))
        sc.grid_columnconfigure((0,1,2,3,4,5),weight=1)
        for col,(icon,lbl,var,clr) in enumerate([
            ("✓","UPLOADED",self.v_uploaded,C["done"]),
            ("↳","SKIPPED",self.v_skipped,C["warn"]),
            ("!","ERRORS",self.v_err_skip,C["err"]),
            ("↻","DUPES",self.v_dup_skip,C["sub"]),
            ("⇩","PENDING",self.v_queue,C["accent2"]),
            ("≈","TODAY",self.v_today_data,C["purple"]),
        ]):
            f=tk.Frame(sc,bg=C["card"],highlightbackground=C["border"],highlightthickness=1)
            f.grid(row=0,column=col,padx=3,sticky="ew"); f.grid_columnconfigure(0,weight=1)
            tk.Label(f,text=icon,font=("Segoe UI Emoji",18),bg=C["card"]).pack(pady=(8,0))
            tk.Label(f,textvariable=var,font=("Consolas",20,"bold"),bg=C["card"],fg=clr,width=5,anchor="center").pack()
            tk.Label(f,text=lbl,font=("Consolas",7),bg=C["card"],fg=C["sub"]).pack(pady=(0,8))
        # middle
        mid=tk.Frame(outer,bg=C["bg"]); mid.grid(row=4,column=0,sticky="ew",pady=(0,8))
        mid.grid_columnconfigure(0,weight=1); mid.grid_columnconfigure(1,weight=2)
        fi=tk.Frame(mid,bg=C["card"],highlightbackground=C["border"],highlightthickness=1); fi.grid(row=0,column=0,sticky="nsew",padx=(0,6))
        tk.Label(fi,text="📁  Watching",font=("Consolas",9,"bold"),bg=C["card"],fg=C["sub"]).pack(anchor="w",padx=12,pady=(10,2))
        tk.Label(fi,textvariable=self.v_folders_n,font=("Consolas",18,"bold"),bg=C["card"],fg=C["accent"],width=14,anchor="w").pack(anchor="w",padx=12)
        tk.Label(fi,textvariable=self.v_files_n,font=("Consolas",11),bg=C["card"],fg=C["text"],width=18,anchor="w").pack(anchor="w",padx=12,pady=(2,10))
        gc=tk.Frame(mid,bg=C["card"],highlightbackground=C["border"],highlightthickness=1); gc.grid(row=0,column=1,sticky="nsew")
        gh=tk.Frame(gc,bg=C["card"]); gh.pack(fill="x",padx=12,pady=(8,2))
        tk.Label(gh,text="📶  Upload Speed",font=("Consolas",9,"bold"),bg=C["card"],fg=C["sub"]).pack(side="left")
        tk.Label(gh,textvariable=self.v_speed,font=("Consolas",8),bg=C["card"],fg=C["accent"],width=14,anchor="e").pack(side="right")
        self.graph=SpeedGraph(gc,C,height=80); self.graph.pack(fill="x",padx=8,pady=(0,8))
        for v in self.speed_hist: self.graph.push(v)
        # log
        lf=tk.Frame(outer,bg=C["card"],highlightbackground=C["border"],highlightthickness=1)
        lf.grid(row=5,column=0,sticky="nsew"); lf.grid_rowconfigure(1,weight=1); lf.grid_columnconfigure(0,weight=1)
        lh=tk.Frame(lf,bg=C["card"]); lh.grid(row=0,column=0,sticky="ew",padx=12,pady=(8,4))
        tk.Label(lh,text="📋  Live Activity",font=("Consolas",9,"bold"),bg=C["card"],fg=C["sub"]).pack(side="left")
        tk.Button(lh,text="Clear",command=self._clear_log,bg=C["tag"],fg=C["sub"],font=("Consolas",8),relief="flat",cursor="hand2",padx=8,pady=2).pack(side="right")
        self.log_box=scrolledtext.ScrolledText(lf,bg=C["bg"],fg=C["text"],font=("Consolas",9),relief="flat",bd=0,state="disabled",wrap="word")
        self.log_box.grid(row=1,column=0,sticky="nsew",padx=8,pady=(0,8))
        for tg,cl in [("done",C["done"]),("accent2",C["accent2"]),("warn",C["warn"]),("err",C["err"]),("sub",C["sub"]),("accent",C["accent"])]:
            self.log_box.tag_configure(tg,foreground=cl)
        self._repopulate_log()
        # controls
        ctrl=tk.Frame(outer,bg=C["bg"]); ctrl.grid(row=6,column=0,sticky="ew",pady=(8,0))
        self.btn_start=tk.Button(ctrl,text="▶  Start",command=self._start_backup,bg=C["accent"],fg=C["sidebar"],font=("Consolas",10,"bold"),relief="flat",cursor="hand2",padx=16,pady=7)
        self.btn_start.pack(side="left",padx=(0,6))
        self.btn_stop=tk.Button(ctrl,text="⏹  Stop",command=self._stop_backup,bg=C["tag"],fg=C["sub"],font=("Consolas",10),relief="flat",cursor="hand2",padx=16,pady=7,state="disabled")
        self.btn_stop.pack(side="left",padx=(0,6))
        self.btn_pause=tk.Button(ctrl,text="⏸  Pause uploads",command=self._pause_resume,bg=C["tag"],fg=C["text"],font=("Segoe UI",9),relief="flat",cursor="hand2",padx=14,pady=7)
        self.btn_pause.pack(side="left",padx=(6,0))
        tk.Button(ctrl,text="📤  Upload Existing Files",command=self._upload_all,bg=C["accent2"],fg="white",font=("Segoe UI",9),relief="flat",cursor="hand2",padx=14,pady=7).pack(side="left",padx=(6,0))
        if self.running: self.btn_start.config(state="disabled"); self.btn_stop.config(state="normal",bg=C["err"],fg="white")

    def _tab_destinations(self,outer):
        C=self.C
        tk.Label(outer,text="Destinations",font=("Segoe UI",16,"bold"),bg=C["bg"],fg=C["text"]).grid(row=1,column=0,sticky="w",pady=(0,10))
        holder=tk.Frame(outer,bg=C["bg"]); holder.grid(row=2,column=0,sticky="ew"); holder.grid_columnconfigure((0,1),weight=1)
        cards=[("Telegram Backup", "telegram", self.v_telegram_enabled, C["accent"], "Bot API destination; existing token and chat configuration are preserved."),
               ("Google Drive Backup", "drive", self.v_drive_enabled, C["accent2"], "OAuth-protected resumable destination; credentials and tokens stay local.")]
        for col,(title,which,var,color,desc) in enumerate(cards):
            card=tk.Frame(holder,bg=C["card"],highlightbackground=C["border"],highlightthickness=1); card.grid(row=0,column=col,sticky="nsew",padx=(0 if col==0 else 6,6 if col==0 else 0)); card.grid_columnconfigure(0,weight=1)
            tk.Label(card,text=title,font=("Segoe UI",12,"bold"),bg=C["card"],fg=C["text"]).grid(row=0,column=0,sticky="w",padx=14,pady=(14,4))
            status="Connected" if var.get() and (which=="telegram" and self.v_token.get() or which=="drive" and self.v_drive_credentials.get()) else ("Disabled" if not var.get() else "Authentication required")
            tk.Label(card,text="●  "+status,font=("Segoe UI",10,"bold"),bg=C["card"],fg=C["done"] if status=="Connected" else C["warn"]).grid(row=1,column=0,sticky="w",padx=14)
            tk.Label(card,text=desc,font=("Segoe UI",9),wraplength=300,justify="left",bg=C["card"],fg=C["sub"]).grid(row=2,column=0,sticky="w",padx=14,pady=(6,10))
            tk.Label(card,text=f"Queue: {self._destination_queue(which)}    Uploaded: {self.n_uploaded}",font=("Segoe UI",9),bg=C["card"],fg=C["text"]).grid(row=3,column=0,sticky="w",padx=14,pady=(0,10))
            tk.Button(card,text="Disable" if var.get() else "Enable",command=lambda x=which:self._toggle_destination(x),bg=color if var.get() else C["tag"],fg=C["sidebar"] if var.get() else C["text"],font=("Segoe UI",9,"bold"),relief="flat",cursor="hand2",padx=12,pady=6).grid(row=4,column=0,sticky="w",padx=14,pady=(0,14))
        tk.Label(outer,text="At least one destination must remain enabled. Use Settings to test or reconfigure Google Drive.",font=("Segoe UI",9),bg=C["bg"],fg=C["sub"]).grid(row=3,column=0,sticky="w",pady=(12,0))

    def _destination_queue(self,which):
        return sum(1 for item in self.queue_items.values() if item.get("destination")==("Telegram" if which=="telegram" else "Google Drive") and item.get("status") in {"Waiting","Uploading","Retrying","Paused"})

    def _tab_activity(self,outer):
        C=self.C; outer.grid_rowconfigure(3,weight=2); outer.grid_rowconfigure(5,weight=1); outer.grid_columnconfigure(0,weight=1)
        tk.Label(outer,text="Activity & Queue",font=("Segoe UI",16,"bold"),bg=C["bg"],fg=C["text"]).grid(row=1,column=0,sticky="w",pady=(0,8))
        current=tk.Frame(outer,bg=C["card"],highlightbackground=C["accent"],highlightthickness=1); current.grid(row=2,column=0,sticky="ew",pady=(0,8)); current.grid_columnconfigure(1,weight=1)
        tk.Label(current,text="CURRENT UPLOAD",font=("Segoe UI",8,"bold"),bg=C["card"],fg=C["sub"]).grid(row=0,column=0,sticky="w",padx=12,pady=(9,2))
        tk.Label(current,textvariable=self.v_current,font=("Segoe UI",11,"bold"),bg=C["card"],fg=C["text"]).grid(row=1,column=0,sticky="w",padx=12,pady=(0,9))
        tk.Label(current,textvariable=self.v_destination,font=("Segoe UI",10),bg=C["card"],fg=C["accent"]).grid(row=1,column=1,sticky="e",padx=12)
        frame=tk.Frame(outer,bg=C["card"],highlightbackground=C["border"],highlightthickness=1); frame.grid(row=3,column=0,sticky="nsew"); frame.grid_rowconfigure(0,weight=1); frame.grid_columnconfigure(0,weight=1)
        cols=("file","size","source","destination","status","progress","retry")
        self.queue_tree=ttk.Treeview(frame,columns=cols,show="headings",selectmode="extended")
        heads={"file":"File","size":"Size","source":"Source","destination":"Destination","status":"Status","progress":"Progress","retry":"Retries"}
        for col in cols: self.queue_tree.heading(col,text=heads[col]); self.queue_tree.column(col,width=110,anchor="w")
        self.queue_tree.column("file",width=230); self.queue_tree.column("source",width=170)
        self.queue_tree.grid(row=0,column=0,sticky="nsew"); sb=ttk.Scrollbar(frame,orient="vertical",command=self.queue_tree.yview); sb.grid(row=0,column=1,sticky="ns"); self.queue_tree.configure(yscrollcommand=sb.set)
        controls=tk.Frame(outer,bg=C["bg"]); controls.grid(row=4,column=0,sticky="w",pady=(8,0))
        for text,cmd in [("Retry selected",self._retry_selected),("Remove from queue",self._remove_selected), ("Clear completed",lambda:self._clear_queue_by_status("Completed")),("Clear failed",lambda:self._clear_queue_by_status("Error")),("Clear all activity",self._clear_all_activity)]:
            tk.Button(controls,text=text,command=cmd,bg=C["tag"],fg=C["text"],font=("Segoe UI",9),relief="flat",cursor="hand2",padx=10,pady=6).pack(side="left",padx=(0,5))
        log_head=tk.Frame(outer,bg=C["bg"]); log_head.grid(row=5,column=0,sticky="ew",pady=(10,5))
        tk.Label(log_head,text="Activity log",font=("Segoe UI",11,"bold"),bg=C["bg"],fg=C["text"]).pack(side="left")
        tk.Entry(log_head,textvariable=self._log_search,font=("Segoe UI",9),bg=C["inp"],fg=C["text"],relief="flat",width=24).pack(side="left",padx=10)
        tk.OptionMenu(log_head,self._log_filter,"All","Info","Success","Warning","Error").pack(side="left")
        tk.Button(log_head,text="Copy",command=self._copy_log,bg=C["tag"],fg=C["text"],font=("Segoe UI",8),relief="flat",cursor="hand2").pack(side="right",padx=3)
        tk.Button(log_head,text="Export",command=self._export_log,bg=C["tag"],fg=C["text"],font=("Segoe UI",8),relief="flat",cursor="hand2").pack(side="right",padx=3)
        tk.Button(log_head,text="Clear visible",command=self._clear_log,bg=C["tag"],fg=C["text"],font=("Segoe UI",8),relief="flat",cursor="hand2").pack(side="right",padx=3)
        log_frame=tk.Frame(outer,bg=C["card"],highlightbackground=C["border"],highlightthickness=1); log_frame.grid(row=6,column=0,sticky="nsew"); log_frame.grid_rowconfigure(0,weight=1); log_frame.grid_columnconfigure(0,weight=1)
        self.log_box=scrolledtext.ScrolledText(log_frame,bg=C["bg"],fg=C["text"],font=("Consolas",8),relief="flat",bd=0,state="disabled",height=6,wrap="word"); self.log_box.grid(row=0,column=0,sticky="nsew",padx=8,pady=8)
        for tg,cl in [("done",C["done"]),("accent2",C["accent2"]),("warn",C["warn"]),("err",C["err"]),("sub",C["sub"]),("accent",C["accent"])]: self.log_box.tag_configure(tg,foreground=cl)
        self._log_search.trace_add("write",lambda *_:self._repopulate_log())
        self._repopulate_queue(); self._repopulate_log()

    def _tab_stats(self,outer):
        C=self.C
        tk.Label(outer,text="Statistics",font=("Segoe UI",16,"bold"),bg=C["bg"],fg=C["text"]).grid(row=1,column=0,sticky="w",pady=(0,10))
        snap=self.stats.snapshot(); today=snap["data"].get("today",{}); session=snap["session"]; all_time=snap["data"].get("all_time",{})
        sections=[("Today",today),("Current session",session),("All time",all_time)]
        for row,(title,bucket) in enumerate(sections,start=2):
            card=tk.Frame(outer,bg=C["card"],highlightbackground=C["border"],highlightthickness=1); card.grid(row=row,column=0,sticky="ew",pady=5); card.grid_columnconfigure(1,weight=1)
            tk.Label(card,text=title,font=("Segoe UI",11,"bold"),bg=C["card"],fg=C["text"]).grid(row=0,column=0,sticky="w",padx=14,pady=10)
            vals=f"Uploaded: {bucket.get('uploaded',0):,}    Data: {format_bytes(bucket.get('bytes',0))}    Errors: {bucket.get('errors',0):,}    Skipped: {bucket.get('skipped',0):,}"
            tk.Label(card,text=vals,font=("Segoe UI",9),bg=C["card"],fg=C["sub"]).grid(row=0,column=1,sticky="w",padx=14)
        tk.Label(outer,text=f"Session started: {session.get('start_time','—')}    Average: {self.v_avg_speed.get()}    Peak: {self.v_peak_speed.get()}",font=("Segoe UI",9),bg=C["bg"],fg=C["sub"]).grid(row=5,column=0,sticky="w",pady=(10,0))

    def _tab_folders(self,outer):
        C=self.C; outer.grid_rowconfigure(2,weight=1)
        tk.Label(outer,text="📁  Watched Folders",font=("Consolas",14,"bold"),bg=C["bg"],fg=C["text"]).grid(row=1,column=0,sticky="w",pady=(0,10))
        frame=tk.Frame(outer,bg=C["card"],highlightbackground=C["border"],highlightthickness=1)
        frame.grid(row=2,column=0,sticky="nsew"); frame.grid_columnconfigure(0,weight=1)
        self._render_folder_dash(frame)
        br=tk.Frame(outer,bg=C["bg"]); br.grid(row=3,column=0,sticky="w",pady=(10,0))
        tk.Button(br,text="➕  Add Folder",command=lambda:self._add_folder_dash(frame),bg=C["accent"],fg=C["sidebar"],font=("Consolas",9,"bold"),relief="flat",cursor="hand2",padx=14,pady=7).pack(side="left",padx=(0,8))
        if self.running:
            tk.Button(br,text="🔄  Restart Watching",command=self._restart_backup,bg=C["accent2"],fg="white",font=("Consolas",9),relief="flat",cursor="hand2",padx=14,pady=7).pack(side="left")

    def _render_folder_dash(self,frame):
        C=self.C
        for w in frame.winfo_children(): w.destroy()
        if not self.watch_folders:
            tk.Label(frame,text="  No folders yet.",font=("Consolas",10),bg=C["card"],fg=C["sub"],pady=20).pack(); return
        for i,folder in enumerate(self.watch_folders):
            r=tk.Frame(frame,bg=C["card2"] if i%2==0 else C["card"]); r.pack(fill="x")
            r.grid_columnconfigure(2,weight=1)
            tk.Label(r,text="📁",font=("Segoe UI Emoji",14),bg=r["bg"]).grid(row=0,column=0,padx=14,pady=10)
            inf=tk.Frame(r,bg=r["bg"]); inf.grid(row=0,column=1,sticky="w")
            tk.Label(inf,text=folder,font=("Consolas",9,"bold"),bg=r["bg"],fg=C["text"]).pack(anchor="w")
            fc=count_files(folder,self.v_sub.get())
            tk.Label(inf,text=f"{fc:,} files inside",font=("Consolas",8),bg=r["bg"],fg=C["sub"]).pack(anchor="w")
            idx=i
            tk.Button(r,text="✕  Remove",command=lambda x=idx:self._rm_folder_dash(x,frame),bg=C["tag"],fg=C["err"],font=("Consolas",8),relief="flat",cursor="hand2",padx=8,pady=4).grid(row=0,column=3,padx=12)

    def _add_folder_dash(self,frame):
        f=filedialog.askdirectory(title="Select folder to watch")
        if f and f not in self.watch_folders: self.watch_folders.append(f); self._save(); self._render_folder_dash(frame); self._update_fc()

    def _rm_folder_dash(self,idx,frame):
        if 0<=idx<len(self.watch_folders): self.watch_folders.pop(idx); self._save(); self._render_folder_dash(frame); self._update_fc()

    def _tab_filetypes(self,outer):
        C=self.C
        tk.Label(outer,text="🗂️  File Type Settings",font=("Consolas",14,"bold"),bg=C["bg"],fg=C["text"]).grid(row=1,column=0,sticky="w",pady=(0,10))
        af=tk.Frame(outer,bg=C["card"],highlightbackground=C["accent"],highlightthickness=1); af.grid(row=2,column=0,sticky="ew",pady=(0,8))
        tk.Checkbutton(af,text="  ✅  Back up ALL file types",variable=self.v_all_files,command=self._tog_dash,
                       bg=C["card"],fg=C["accent"],selectcolor=C["tag"],activebackground=C["card"],font=("Consolas",10,"bold"),cursor="hand2").pack(anchor="w",padx=12,pady=10)
        cf=tk.Frame(outer,bg=C["bg"]); cf.grid(row=3,column=0,sticky="ew"); cf.grid_columnconfigure((0,1,2,3),weight=1)
        self.cat_chks_d={}
        for idx,(cat,exts) in enumerate(FILE_CATS.items()):
            ri,ci=divmod(idx,4)
            ff=tk.Frame(cf,bg=C["card"],highlightbackground=C["border"],highlightthickness=1); ff.grid(row=ri,column=ci,padx=3,pady=3,sticky="ew")
            chk=tk.Checkbutton(ff,text=cat,variable=self.v_cats[cat],bg=C["card"],fg=C["text"],selectcolor=C["tag"],activebackground=C["card"],font=("Consolas",9),cursor="hand2",command=self._unchk_d)
            chk.pack(anchor="w",padx=10,pady=6)
            tk.Label(ff,text="  "+", ".join(exts[:4])+("…" if len(exts)>4 else ""),font=("Consolas",7),bg=C["card"],fg=C["sub"]).pack(anchor="w",padx=10,pady=(0,6))
            self.cat_chks_d[cat]=chk
        self._tog_dash()
        tk.Button(outer,text="💾  Save",command=self._save,bg=C["accent"],fg=C["sidebar"],font=("Consolas",10,"bold"),relief="flat",cursor="hand2",pady=8).grid(row=4,column=0,sticky="w",pady=(12,0))

    def _tog_dash(self):
        st="disabled" if self.v_all_files.get() else "normal"
        if hasattr(self,"cat_chks_d"):
            for chk in self.cat_chks_d.values(): chk.configure(state=st)

    def _unchk_d(self): self.v_all_files.set(False); self._tog_dash()

    def _tab_settings(self,outer):
        C=self.C
        tk.Label(outer,text="⚙️  System Settings",font=("Consolas",14,"bold"),bg=C["bg"],fg=C["text"]).grid(row=1,column=0,sticky="w",pady=(0,12))
        dest=tk.Frame(outer,bg=C["card"],highlightbackground=C["accent"],highlightthickness=1); dest.grid(row=2,column=0,sticky="ew",pady=(0,8)); dest.grid_columnconfigure(1,weight=1)
        tk.Label(dest,text="BACKUP DESTINATIONS",font=("Consolas",8,"bold"),bg=C["card"],fg=C["sub"]).grid(row=0,column=0,columnspan=2,sticky="w",padx=12,pady=(10,4))
        tk.Checkbutton(dest,text="  Telegram Backup",variable=self.v_telegram_enabled,command=self._apply_s,bg=C["card"],fg=C["text"],selectcolor=C["tag"],activebackground=C["card"],font=("Consolas",10,"bold"),cursor="hand2").grid(row=1,column=0,sticky="w",padx=12,pady=5)
        tk.Checkbutton(dest,text="  Google Drive Backup",variable=self.v_drive_enabled,command=self._toggle_destination_controls,bg=C["card"],fg=C["text"],selectcolor=C["tag"],activebackground=C["card"],font=("Consolas",10,"bold"),cursor="hand2").grid(row=2,column=0,sticky="w",padx=12,pady=5)
        tk.Label(dest,text="New files are sent to every enabled destination.",font=("Consolas",8),bg=C["card"],fg=C["sub"]).grid(row=3,column=0,columnspan=2,sticky="w",padx=12,pady=(2,10))

        drive=tk.Frame(outer,bg=C["card"],highlightbackground=C["border"],highlightthickness=1); drive.grid(row=3,column=0,sticky="ew",pady=(0,8)); drive.grid_columnconfigure(0,weight=1)
        tk.Label(drive,text="GOOGLE DRIVE CONNECTION",font=("Consolas",8,"bold"),bg=C["card"],fg=C["sub"]).grid(row=0,column=0,sticky="w",padx=12,pady=(10,2))
        tk.Label(drive,text="OAuth credentials stay on this computer. The browser opens only when you connect or re-authorize Google Drive.",font=("Consolas",8),bg=C["card"],fg=C["sub"],wraplength=560,justify="left").grid(row=1,column=0,sticky="w",padx=12,pady=(0,6))
        self._wentry(drive,"GOOGLE CREDENTIALS JSON",self.v_drive_credentials,row=2)
        br=tk.Frame(drive,bg=C["card"]); br.grid(row=4,column=0,sticky="w",padx=12,pady=(6,2))
        tk.Button(br,text="📂 Browse",command=self._browse_drive_credentials,bg=C["tag"],fg=C["text"],font=("Consolas",8),relief="flat",cursor="hand2",padx=10,pady=5).pack(side="left",padx=(0,6))
        tk.Button(br,text="🔗 Connect & Test",command=lambda:self._test_drive_connection(self.fb_drive),bg=C["accent2"],fg="white",font=("Consolas",8,"bold"),relief="flat",cursor="hand2",padx=10,pady=5).pack(side="left",padx=(0,6))
        tk.Button(br,text="➕ Create Drive Folder",command=self._create_drive_folder,bg=C["accent"],fg=C["sidebar"],font=("Consolas",8,"bold"),relief="flat",cursor="hand2",padx=10,pady=5).pack(side="left")
        self.fb_drive=self._wfb(drive,5); self.fb_drive.grid_configure(padx=12)
        self._wentry(drive,"DRIVE FOLDER ID  (optional; leave empty for My Drive root)",self.v_drive_folder_id,row=6)
        self._toggle_destination_controls()

        network=tk.Frame(outer,bg=C["card"],highlightbackground=C["border"],highlightthickness=1); network.grid(row=4,column=0,sticky="ew",pady=(0,8)); network.grid_columnconfigure(1,weight=1)
        tk.Label(network,text="NETWORK & BACKUP CONTROL",font=("Segoe UI",8,"bold"),bg=C["card"],fg=C["sub"]).grid(row=0,column=0,columnspan=3,sticky="w",padx=12,pady=(10,6))
        tk.Label(network,text="Upload speed limit",font=("Segoe UI",9),bg=C["card"],fg=C["text"]).grid(row=1,column=0,sticky="w",padx=12,pady=5)
        choices=["Unlimited","128 KB/s","256 KB/s","512 KB/s","1 MB/s","2 MB/s","5 MB/s","10 MB/s"]
        menu=tk.OptionMenu(network,self.v_limit_label,*choices,command=self._apply_limit_choice); menu.configure(bg=C["tag"],fg=C["text"],activebackground=C["hover"],relief="flat",highlightthickness=0); menu.grid(row=1,column=1,sticky="w",padx=6,pady=3)
        tk.Entry(network,textvariable=self.v_custom_bandwidth,font=("Segoe UI",9),bg=C["inp"],fg=C["text"],relief="flat",width=14).grid(row=1,column=2,sticky="w",padx=6,pady=3)
        tk.Label(network,text="Custom, e.g. 500 KB/s",font=("Segoe UI",8),bg=C["card"],fg=C["sub"]).grid(row=2,column=2,sticky="w",padx=6)
        tk.Checkbutton(network,text="Pause when offline",variable=self.v_pause_offline,bg=C["card"],fg=C["text"],selectcolor=C["tag"],activebackground=C["card"],font=("Segoe UI",9),cursor="hand2").grid(row=3,column=0,sticky="w",padx=12,pady=(6,10))
        tk.Label(network,text="Internet check interval (seconds)",font=("Segoe UI",9),bg=C["card"],fg=C["text"]).grid(row=3,column=1,sticky="e",padx=6)
        tk.Entry(network,textvariable=self.v_network_interval,font=("Segoe UI",9),bg=C["inp"],fg=C["text"],relief="flat",width=8).grid(row=3,column=2,sticky="w",padx=6)
        backup=tk.Frame(outer,bg=C["card"],highlightbackground=C["border"],highlightthickness=1); backup.grid(row=5,column=0,sticky="ew",pady=(0,8)); backup.grid_columnconfigure(1,weight=1)
        tk.Label(backup,text="RELIABILITY",font=("Segoe UI",8,"bold"),bg=C["card"],fg=C["sub"]).grid(row=0,column=0,columnspan=4,sticky="w",padx=12,pady=(10,6))
        for col,(label,var) in enumerate([("Stability delay (s)",self.v_stability_delay),("Retry count",self.v_retry_count),("Retry delay (s)",self.v_retry_delay),("Queue warning",self.v_queue_warning)]):
            tk.Label(backup,text=label,font=("Segoe UI",8),bg=C["card"],fg=C["sub"]).grid(row=1,column=col,sticky="w",padx=8)
            tk.Entry(backup,textvariable=var,font=("Segoe UI",9),bg=C["inp"],fg=C["text"],relief="flat",width=10).grid(row=2,column=col,sticky="w",padx=8,pady=(2,10))
        tk.Checkbutton(backup,text="Enable file stability check",variable=self.v_stability_enabled,bg=C["card"],fg=C["text"],selectcolor=C["tag"],activebackground=C["card"],font=("Segoe UI",9),cursor="hand2").grid(row=3,column=0,columnspan=2,sticky="w",padx=12,pady=(0,10))

        opts=[(self.v_autostart,"🚀  Start with Windows","Adds to Windows startup registry."),
              (self.v_bg_mode,"🔄  Run in background","Backup continues when window is closed."),
              (self.v_min_tray,"🔔  Minimize to tray","X hides to system tray instead of quitting."),
              (self.v_sub,"📂  Include subfolders","Watch nested folders inside watched folders."),
              (self.v_start_minimized,"▣  Start minimized","Open quietly at login when autostart is enabled."),
              (self.v_notifications,"◌  Windows notifications","Notify only for lifecycle and repeated failure events.")]
        for i,(var,lbl,desc) in enumerate(opts):
            f=tk.Frame(outer,bg=C["card"],highlightbackground=C["border"],highlightthickness=1); f.grid(row=6+i,column=0,sticky="ew",pady=4); f.grid_columnconfigure(1,weight=1)
            tk.Checkbutton(f,variable=var,command=self._apply_s,bg=C["card"],selectcolor=C["tag"],activebackground=C["card"],cursor="hand2").grid(row=0,column=0,padx=(12,6),pady=10)
            inf=tk.Frame(f,bg=C["card"]); inf.grid(row=0,column=1,sticky="ew",pady=10)
            tk.Label(inf,text=lbl,font=("Consolas",10,"bold"),bg=C["card"],fg=C["text"]).pack(anchor="w")
            tk.Label(inf,text=desc,font=("Consolas",8),bg=C["card"],fg=C["sub"]).pack(anchor="w")
        tk.Button(outer,text="💾  Save Settings",command=self._apply_s,bg=C["accent"],fg=C["sidebar"],font=("Segoe UI",10,"bold"),relief="flat",cursor="hand2",pady=8).grid(row=13,column=0,sticky="w",pady=(14,0))

    def _apply_s(self): set_autostart(self.v_autostart.get()); self._save(); self._log("⚙️  Settings saved.","sub")

    def _tab_log(self,outer):
        C=self.C; outer.grid_rowconfigure(2,weight=1)
        lh=tk.Frame(outer,bg=C["bg"]); lh.grid(row=1,column=0,sticky="ew",pady=(0,8))
        tk.Label(lh,text="📋  Activity Log",font=("Consolas",12,"bold"),bg=C["bg"],fg=C["text"]).pack(side="left")
        tk.Button(lh,text="Clear",command=self._clear_log,bg=C["tag"],fg=C["sub"],font=("Consolas",8),relief="flat",cursor="hand2",padx=8,pady=4).pack(side="right")
        lf=tk.Frame(outer,bg=C["card"],highlightbackground=C["border"],highlightthickness=1); lf.grid(row=2,column=0,sticky="nsew"); lf.grid_rowconfigure(0,weight=1); lf.grid_columnconfigure(0,weight=1)
        self.log_box=scrolledtext.ScrolledText(lf,bg=C["bg"],fg=C["text"],font=("Consolas",9),relief="flat",bd=0,state="disabled",wrap="word")
        self.log_box.grid(row=0,column=0,sticky="nsew",padx=8,pady=8)
        for tg,cl in [("done",C["done"]),("accent2",C["accent2"]),("warn",C["warn"]),("err",C["err"]),("sub",C["sub"]),("accent",C["accent"])]:
            self.log_box.tag_configure(tg,foreground=cl)
        self._repopulate_log()

    # ── Backup engine ─────────────────────────────────────────────────────────
    def _get_exts(self):
        if self.v_all_files.get(): return []
        exts=[]
        for cat,var in self.v_cats.items():
            if var.get(): exts.extend(FILE_CATS[cat])
        return list(set(exts))

    def _current_limit(self):
        custom=self.v_custom_bandwidth.get().strip()
        if custom: return parse_limit(custom)
        return parse_limit(self.v_bandwidth.get())

    def _stability_delay(self): return safe_float(self.v_stability_delay.get(),2.0,0.2,60.0)

    def _apply_limit_choice(self, value):
        self.v_bandwidth.set(str(parse_limit(value)))
        self.limiter.set_limit(self._current_limit())
        self._log(f"Network limit: {format_limit(self._current_limit())}","sub")

    def _pause_resume(self):
        if not self.running: return
        self.paused=not self.paused; self.limiter.set_paused(self.paused)
        self.v_status.set("⏸  Backup Paused" if self.paused else "🟢  Watching…")
        self._log("⏸  Uploads paused." if self.paused else "▶  Uploads resumed.","warn" if self.paused else "done")
        if hasattr(self,"btn_pause"):
            self.btn_pause.config(text="▶  Resume uploads" if self.paused else "⏸  Pause uploads")

    def _is_network_available(self):
        if not self.v_pause_offline.get(): return True
        now=time.monotonic()
        try: interval=max(10,int(self.v_network_interval.get()))
        except (TypeError,ValueError): interval=30
        if now-self.network_last_check < interval and self.network_last is not None: return self.network_last
        self.network_last_check=now; self.network_last=network_available()
        return self.network_last

    def _network_tick(self):
        if not self.running: return
        threading.Thread(target=self._network_probe,daemon=True).start()
        try: interval=max(10,int(self.v_network_interval.get()))*1000
        except (TypeError,ValueError): interval=30000
        self.after(interval,self._network_tick)

    def _network_probe(self):
        previous=self.network_last; current=self._is_network_available()
        if previous is False and current is True: self._notify("Internet restored","The upload queue will resume automatically.")
        if previous is True and current is False: self._log("Offline — waiting for internet connection","warn")
        if current != previous: self._post_ui(self.v_health.set,"Healthy" if current else "Warning")

    def _post_ui(self, callback, *args):
        self.ui_events.put((callback,args))

    def _poll_ui_events(self):
        try:
            for _ in range(100):
                callback,args=self.ui_events.get_nowait(); callback(*args)
        except queue.Empty:
            pass
        except tk.TclError:
            return
        try: self.after(100,self._poll_ui_events)
        except tk.TclError: pass

    def _set_status(self, text):
        self._post_ui(self._set_status_ui,text)

    def _set_status_ui(self,text):
        self.v_status.set(("🟢  "+str(text))[:64])

    def _notify(self,title,message):
        if not self.v_notifications.get(): return
        try:
            if self.tray_icon: self.tray_icon.notify(message,title)
        except Exception: pass

    def _queue_key(self,path,destination): return f"{destination}::{path}"

    def _on_queue_item(self,path,destination,status,progress=0.0,retries=0):
        self._post_ui(self._queue_item_ui,path,destination,status,progress,retries)

    def _queue_item_ui(self,path,destination,status,progress=0.0,retries=0):
        key=self._queue_key(path,destination); old=self.queue_items.get(key,{})
        item={"path":path,"destination":destination,"status":status,"progress":progress,"retries":retries,"size":os.path.getsize(path) if os.path.exists(path) else 0,"source":str(Path(path).parent)}
        self.queue_items[key]=item
        if key not in self.queue_order: self.queue_order.append(key)
        if len(self.queue_order)>1000:
            self.queue_order=self.queue_order[-1000:]
            for stale in list(self.queue_items):
                if stale not in self.queue_order: self.queue_items.pop(stale,None)
        if status=="Uploading": self.v_current.set(os.path.basename(path)); self.v_destination.set(destination)
        if status=="Completed" and old.get("status")!="Completed": self.stats.record_upload(item["size"])
        if status=="Error": self.v_health.set("Error")
        pending=sum(1 for x in self.queue_items.values() if x.get("status") in {"Waiting","Uploading","Retrying","Paused"})
        self.v_queue.set(str(pending)); snap=self.stats.snapshot(); self.v_today_data.set(format_bytes(snap["data"].get("today",{}).get("bytes",0)))
        self.v_summary.set(f"Destination: {self.v_destination.get()}    Queue: {pending}    Speed: {self.v_speed.get()}    Health: {self.v_health.get()}")
        self._repopulate_queue()

    def _repopulate_queue(self):
        tree=getattr(self,"queue_tree",None)
        try:
            if not tree or not tree.winfo_exists(): return
        except tk.TclError: return
        tree.delete(*tree.get_children())
        for key in self.queue_order[-1000:]:
            item=self.queue_items.get(key)
            if not item: continue
            pct="—" if item["progress"] is None else f"{item['progress']*100:.0f}%"
            tree.insert("","end",iid=key,values=(os.path.basename(item["path"]),format_bytes(item["size"]),item["source"],item["destination"],item["status"],pct,item["retries"]))

    def _retry_selected(self):
        tree=getattr(self,"queue_tree",None)
        if not tree: return
        for key in tree.selection():
            item=self.queue_items.get(key)
            if not item or item.get("status")!="Error": continue
            self.cancelled_paths.discard(item["path"])
            sink=self.uploader if item["destination"]=="Telegram" else self.drive_uploader
            if sink: sink.enqueue(item["path"])

    def _remove_selected(self):
        tree=getattr(self,"queue_tree",None)
        if not tree: return
        for key in tree.selection():
            item=self.queue_items.get(key)
            if item and item.get("status") in {"Waiting","Retrying","Paused","Error"}:
                self.cancelled_paths.add(item["path"]); self.queue_items.pop(key,None)
        self._repopulate_queue()

    def _clear_queue_by_status(self,status):
        for key,item in list(self.queue_items.items()):
            if item.get("status")==status:
                self.queue_items.pop(key,None)
        self._repopulate_queue()

    def _clear_all_activity(self):
        for item in self.queue_items.values():
            if item.get("status") in {"Waiting","Retrying","Paused"}: self.cancelled_paths.add(item["path"])
        self.queue_items.clear(); self.queue_order.clear(); self._repopulate_queue()

    def _start_backup(self):
        if self.running: return
        self.cancel_event.clear(); self.limiter.reset(); self.limiter.set_limit(self._current_limit()); self.limiter.set_paused(False); self.paused=False
        if not self.watch_folders:
            self._log("⚠  Add at least one folder first.","warn"); return
        if not self.v_telegram_enabled.get() and not self.v_drive_enabled.get():
            self._log("⚠  Enable Telegram Backup, Google Drive Backup, or both.","warn"); return
        if self.v_telegram_enabled.get() and not (self.v_token.get().strip() and self.v_chat.get().strip()):
            self._log("⚠  Telegram is enabled but token or chat ID is missing.","warn"); return
        if self.v_drive_enabled.get() and not self.v_drive_credentials.get().strip():
            self._log("⚠  Google Drive is enabled but credentials.json is missing.","warn"); return
        if self.v_drive_enabled.get() and not drive_available():
            self._log("⚠  "+drive_install_hint(),"warn"); return
        sinks=[]
        if self.v_telegram_enabled.get():
            token=self.v_token.get().strip(); chat=self.v_chat.get().strip()
            if not (token and chat):
                self._log("⚠  Telegram is enabled but token or chat ID is missing.","warn"); return
            cbs={"log":self._log,"stat":self._set_status,
                 "count":self._on_upload,"skip":self._on_skip,"speed":self._on_speed,
                 "item":self._on_queue_item,"is_online":self._is_network_available,"is_cancelled":lambda p:p in self.cancelled_paths}
            self.uploader=Uploader(token,chat,cbs,self.limiter,self.cancel_event)
            self.uploader.MAX_RETRIES=safe_int(self.v_retry_count.get(),5,1); self.uploader.DELAY=safe_float(self.v_retry_delay.get(),2.0,0.0)
            self.uploader.start(); sinks.append(self.uploader)
        else:
            self.uploader=None
        if self.v_drive_enabled.get():
            if not self.v_drive_credentials.get().strip():
                self._log("⚠  Google Drive is enabled but credentials.json is missing.","warn"); return
            if not drive_available():
                self._log("⚠  "+drive_install_hint(),"warn"); return
            try:
                self.drive_client=self.drive_client or GoogleDriveClient(self.v_drive_credentials.get().strip())
                drive_cbs={"log":self._log,"stat":self._set_status,
                           "success":self._on_upload,"skip":self._on_skip,"item":self._on_queue_item,
                           "speed":self._on_speed,"is_cancelled":lambda p:p in self.cancelled_paths,"is_online":self._is_network_available}
                self.drive_uploader=DriveUploader(self.drive_client,self.v_drive_folder_id.get(),drive_cbs,self.limiter,self.cancel_event)
                self.drive_uploader.max_retries=safe_int(self.v_retry_count.get(),4,1); self.drive_uploader.start(); sinks.append(self.drive_uploader)
            except Exception as exc:
                self._log(f"❌  Google Drive setup failed: {exc}","err"); return
        else:
            self.drive_uploader=None
        if not sinks:
            self._log("⚠  Enable Telegram Backup, Google Drive Backup, or both.","warn"); return
        self.sinks=sinks
        exts=self._get_exts()
        for folder in self.watch_folders:
            if not os.path.isdir(folder): self._log(f"⚠  Missing: {folder}","warn"); continue
            h=FolderWatcher(sinks,exts,self._log,self.v_stability_enabled.get(),self._stability_delay())
            obs=Observer(); obs.schedule(h,folder,recursive=self.v_sub.get()); obs.start()
            self.observers.append(obs)
        self.running=True; self.v_status.set("🟢  Watching…")
        self._notify("Backup started", "TelegramBackup is now watching your folders.")
        self._network_tick()
        enabled_names=[]
        if self.v_telegram_enabled.get(): enabled_names.append("Telegram")
        if self.v_drive_enabled.get(): enabled_names.append("Google Drive")
        self._log(f"▶  {len(self.watch_folders)} folder(s) watched  •  {', '.join(enabled_names)}  •  {'all types' if not exts else str(len(exts))+' ext'}","done")
        if hasattr(self,"btn_start"):
            self.btn_start.config(state="disabled"); self.btn_stop.config(state="normal",bg=self.C["err"],fg="white")
            self.btn_pause.config(state="normal",text="⏸  Pause uploads")

    def _stop_backup(self):
        self.cancel_event.set(); self.limiter.set_paused(False)
        for obs in self.observers: obs.stop(); obs.join(timeout=3)
        self.observers=[]
        if self.uploader: self.uploader.stop(); self.uploader.join(timeout=3); self.uploader=None
        if self.drive_uploader: self.drive_uploader.stop(); self.drive_uploader.join(timeout=3); self.drive_uploader=None
        self.sinks=[]
        self.running=False; self.paused=False; self.v_status.set("⏹  Stopped"); self.v_current.set("No active upload"); self.v_destination.set("—"); self._log("⏹  Stopped.","warn"); self._notify("Backup stopped", "TelegramBackup has stopped watching.")
        if hasattr(self,"btn_start"): self.btn_start.config(state="normal"); self.btn_stop.config(state="disabled",bg=self.C["tag"],fg=self.C["sub"])
        if hasattr(self,"btn_pause"): self.btn_pause.config(text="⏸  Pause uploads",state="disabled")

    def _restart_backup(self): self._stop_backup(); self.after(300,self._start_backup)

    def _upload_all(self):
        if not self.running: self._log("⚠  Start first.","warn"); return
        exts=self._get_exts(); count=0; pat="**/*" if self.v_sub.get() else "*"
        for folder in self.watch_folders:
            for p in Path(folder).glob(pat):
                if p.is_file():
                    if exts and p.suffix.lower() not in exts: continue
                    for sink in self.sinks: sink.enqueue(str(p))
                    count+=1
        self._log(f"📤  Queued {count} file(s) to {len(self.sinks)} destination(s).","accent2")

    # ── Callbacks ─────────────────────────────────────────────────────────────
    def _on_upload(self,n=1): self._post_ui(self._upload_ui,n)

    def _upload_ui(self,n=1):
        self.n_uploaded+=n; self.v_uploaded.set(str(self.n_uploaded))

    def _on_skip(self,reason): self._post_ui(self._skip_ui,reason)

    def _skip_ui(self,reason):
        self.n_skipped+=1; self.stats.record_skip(); self.v_skipped.set(str(self.n_skipped))
        if reason=="size": self.n_size+=1; self.v_size_skip.set(str(self.n_size))
        elif reason=="error": self.n_err+=1; self.stats.record_error(); self.v_err_skip.set(str(self.n_err))
        elif reason=="dup": self.n_dup+=1; self.v_dup_skip.set(str(self.n_dup))

    def _on_speed(self,bps): self._post_ui(self._speed_ui,float(bps or 0))

    def _speed_ui(self,bps):
        self.speed_hist.append(bps)
        avg=sum(self.speed_hist)/max(1,len(self.speed_hist)); peak=max(self.speed_hist or [0])
        lbl=f"{bps/1024:.1f} KB/s" if bps<1048576 else f"{bps/1048576:.2f} MB/s"
        albl=format_bytes(avg)+"/s"; plbl=format_bytes(peak)+"/s"
        self.v_speed.set(lbl); self.v_avg_speed.set(albl); self.v_peak_speed.set(plbl)
        self.v_summary.set(f"Destination: {self.v_destination.get()}    Queue: {self.v_queue.get()}    Speed: {lbl}    Health: {self.v_health.get()}")
        if hasattr(self,"graph") and self.graph.winfo_exists(): self.graph.push(bps)

    # ── File count ────────────────────────────────────────────────────────────
    def _update_fc(self):
        total=sum(count_files(f,self.v_sub.get()) for f in self.watch_folders)
        n=len(self.watch_folders)
        self.v_folders_n.set(f"{n} folder{'s' if n!=1 else ''}")
        self.v_files_n.set(f"{total:,} file{'s' if total!=1 else ''}")

    def _refresh_fc(self): self._update_fc(); self.after(10000,self._refresh_fc)

    # ── Tray ──────────────────────────────────────────────────────────────────
    def _start_tray(self):
        if not TRAY_OK or self.tray_icon: return
        try:
            img=Image.new("RGBA",(64,64),(0,0,0,0)); d=ImageDraw.Draw(img); d.ellipse([4,4,60,60],fill="#00e5b0")
            menu=pystray.Menu(
                pystray.MenuItem("📡 TelegramBackup",None,enabled=False),pystray.Menu.SEPARATOR,
                pystray.MenuItem("Open",self._tray_open,default=True),
                pystray.MenuItem("Stop",lambda i,it:self.after(0,self._stop_backup)),
                pystray.Menu.SEPARATOR,pystray.MenuItem("Quit",self._tray_quit))
            self.tray_icon=pystray.Icon(APP_NAME,img,APP_NAME,menu)
            threading.Thread(target=self.tray_icon.run,daemon=True).start()
        except Exception as e: print(f"Tray: {e}")

    def _tray_open(self,i=None,it=None): self.after(0,lambda:(self.deiconify(),self.lift(),self.focus_force()))
    def _tray_quit(self,i=None,it=None): self._quitting=True; self.after(0,self._full_quit)

    # ── Close ─────────────────────────────────────────────────────────────────
    def _on_close(self):
        if self._quitting:
            self._full_quit(); return

        # Minimize to tray (near clock)
        if self.v_min_tray.get():
            if TRAY_OK:
                self.withdraw()
                if not self.tray_icon: self._start_tray()
                self._log("🔔  Minimized to tray. Right-click tray icon to open.", "sub")
            else:
                # pystray not available - minimize to taskbar
                self.iconify()
                self._log("🔔  Minimized to taskbar. (pip install pystray for tray icon)", "sub")
            return

        # Keep running in background (hide window, keep backup alive)
        if self.v_bg_mode.get() and self.running:
            self.withdraw()
            if TRAY_OK and not self.tray_icon: self._start_tray()
            self._log("🔄  Running in background.", "sub")
            return

        # Normal close
        self._full_quit()

    def _full_quit(self):
        self._save()
        if self.running: self._stop_backup()
        if self.tray_icon:
            try: self.tray_icon.stop()
            except: pass
        self.destroy()

    # ── Log helpers ───────────────────────────────────────────────────────────
    def _log(self,msg,tag="text"):
        ts=datetime.now().strftime("%H:%M:%S")
        with self.log_lock:
            self._log_lines.append((ts,msg,tag))
            if len(self._log_lines)>500: self._log_lines=self._log_lines[-500:]
        self._post_ui(self._append_log_ui,ts,msg,tag)

    def _append_log_ui(self,ts,msg,tag):
        if not hasattr(self,"log_box") or not self.log_box.winfo_exists(): return
        # Re-render filtered activity only when a filter is active; otherwise
        # append one line to keep UI redraws cheap.
        if self._log_search.get().strip() or self._log_filter.get()!="All":
            self._repopulate_log(); return
        self.log_box.config(state="normal")
        self.log_box.insert("end",f"[{ts}] ","sub"); self.log_box.insert("end",f"{msg}\n",tag)
        self.log_box.see("end"); self.log_box.config(state="disabled")

    def _repopulate_log(self):
        if not hasattr(self,"log_box") or not self.log_box.winfo_exists(): return
        self.log_box.config(state="normal"); self.log_box.delete("1.0","end")
        query=self._log_search.get().strip().lower(); severity=self._log_filter.get()
        allowed={"Info":"sub","Success":"done","Warning":"warn","Error":"err"}
        with self.log_lock: lines=list(self._log_lines[-200:])
        for ts,msg,tag in lines:
            if query and query not in msg.lower(): continue
            if severity!="All" and tag!=allowed.get(severity): continue
            self.log_box.insert("end",f"[{ts}] ","sub"); self.log_box.insert("end",f"{msg}\n",tag)
        self.log_box.see("end"); self.log_box.config(state="disabled")

    def _copy_log(self):
        if not hasattr(self,"log_box") or not self.log_box.winfo_exists(): return
        text=self.log_box.get("1.0","end-1c"); self.clipboard_clear(); self.clipboard_append(text); self.update_idletasks()

    def _export_log(self):
        path=filedialog.asksaveasfilename(title="Export TelegramBackup activity log",defaultextension=".txt",filetypes=[("Text files","*.txt"),("All files","*.*")])
        if not path: return
        try:
            with open(path,"w",encoding="utf-8") as handle: handle.write(self.log_box.get("1.0","end-1c"))
            self._log(f"Exported activity log to {os.path.basename(path)}","sub")
        except OSError as exc: self._log(f"Could not export log: {exc}","err")

    def _clear_log(self):
        with self.log_lock: self._log_lines=[]
        if hasattr(self,"log_box") and self.log_box.winfo_exists():
            self.log_box.config(state="normal"); self.log_box.delete("1.0","end"); self.log_box.config(state="disabled")

    # ── Misc ──────────────────────────────────────────────────────────────────
    def _next(self,i): self.step_done[i]=True; self._save(); self._goto(i+1)

    def _launch(self):
        self._save()
        if self.v_autostart.get(): set_autostart(True)
        for i in range(8): self.step_done[i]=True
        self.cur_step=8; self._active_tab="main"
        self._build_sidebar(); self._render_page()
        self.after(300,self._start_backup)
        if self.v_bg_mode.get() and TRAY_OK: self.after(700,self._start_tray)

    def _save(self):
        save_cfg({
            "token":self.v_token.get().strip(),"chat_id":self.v_chat.get().strip(),
            "telegram_enabled":self.v_telegram_enabled.get(),"drive_enabled":self.v_drive_enabled.get(),
            "drive_credentials":self.v_drive_credentials.get().strip(),"drive_folder_id":self.v_drive_folder_id.get().strip(),
            "drive_folder_name":self.v_drive_folder_name.get().strip() or "TelegramBackup",
            "watch_folders":self.watch_folders,"subfolders":self.v_sub.get(),
            "all_files":self.v_all_files.get(),"categories":[c for c,v in self.v_cats.items() if v.get()],
            "autostart":self.v_autostart.get(),"bg_mode":self.v_bg_mode.get(),
            "min_tray":self.v_min_tray.get(),"theme":self.theme_name.get(),"machine_id":get_machine_id(),
            "start_minimized":self.v_start_minimized.get(),"notifications":self.v_notifications.get(),
            "stability_enabled":self.v_stability_enabled.get(),"stability_delay":self._stability_delay(),
            "retry_count":safe_int(self.v_retry_count.get(),5,1),"retry_delay":safe_int(self.v_retry_delay.get(),2,1),
            "bandwidth_limit":self._current_limit(),"custom_bandwidth":self.v_custom_bandwidth.get().strip(),
            "pause_when_offline":self.v_pause_offline.get(),"network_check_interval":safe_int(self.v_network_interval.get(),30,10),
            "queue_warning":safe_int(self.v_queue_warning.get(),2500,1),
        })


def main():
    """Entry point — used by setup.py console_scripts."""
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
