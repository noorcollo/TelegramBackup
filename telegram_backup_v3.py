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

import os, sys, json, time, queue, asyncio, hashlib, threading, webbrowser, uuid
import tkinter as tk
from tkinter import filedialog, scrolledtext
from datetime import datetime
from pathlib import Path
from collections import deque
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from telegram import Bot
from telegram.error import TelegramError

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
MAX_SIZE     = 50 * 1024 * 1024
APP_NAME     = "TelegramBackup"
REG_KEY      = r"Software\Microsoft\Windows\CurrentVersion\Run"
VERSION      = "v3"
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
    (7,"System Options","⚙️"),(8,"Launch","🚀"),
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


class Uploader(threading.Thread):
    def __init__(self,token,chat_id,cbs):
        super().__init__(daemon=True)
        self.token,self.chat_id=token,chat_id
        self.on_log=cbs["log"]; self.on_stat=cbs["stat"]
        self.on_count=cbs["count"]; self.on_skip=cbs["skip"]; self.on_speed=cbs["speed"]
        self.q=queue.Queue(); self.uploaded=load_hist(); self.active=True
        self.DELAY = 1.5   # minimum seconds between uploads (polite rate)
        self.MAX_RETRIES = 5

    def enqueue(self,path): self.q.put(path)
    def stop(self): self.active=False

    def run(self):
        loop=asyncio.new_event_loop(); asyncio.set_event_loop(loop)
        loop.run_until_complete(self._loop())

    async def _loop(self):
        bot=Bot(token=self.token)
        while self.active:
            try: path=self.q.get(timeout=0.4)
            except queue.Empty: continue
            if not os.path.exists(path):
                self.on_log(f"⚠  Gone: {os.path.basename(path)}","warn"); self.on_skip("error"); continue
            key=f"{path}::{fhash(path)}"
            if key in self.uploaded:
                self.on_log(f"⏭  Duplicate: {os.path.basename(path)}","sub"); self.on_skip("dup"); continue
            sz=os.path.getsize(path)
            if sz>MAX_SIZE:
                self.on_log(f"⛔  >50MB: {os.path.basename(path)}","warn"); self.on_skip("size"); continue
            if sz==0:
                self.on_log(f"⚠  Empty: {os.path.basename(path)}","warn"); self.on_skip("error"); continue

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
                        await bot.send_document(
                            chat_id=self.chat_id, document=doc, caption=cap,
                            parse_mode="Markdown",
                            read_timeout=90, write_timeout=90, connect_timeout=30)
                    elapsed=max(time.time()-t0, 0.1)
                    self.on_speed(sz/elapsed)
                    self.uploaded.add(key); save_hist(self.uploaded)
                    self.on_log(f"✅  {os.path.basename(path)}  ({sz/1024:.0f} KB)","done")
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
                            await asyncio.sleep(backoff)
                        else:
                            self.on_skip("error")
                        continue

                except Exception as e:
                    self.on_log(f"❌  {e}","err")
                    if attempt < self.MAX_RETRIES:
                        await asyncio.sleep(2 ** attempt)
                    else:
                        self.on_skip("error")
                    continue

            if not success and self.active:
                self.on_log(f"💀  Gave up after {self.MAX_RETRIES} attempts: {os.path.basename(path)}","err")
                self.on_skip("error")

            self.on_stat("Watching…")


class FolderWatcher(FileSystemEventHandler):
    def __init__(self,uploader,exts,log_cb):
        self.uploader,self.exts,self.log=uploader,exts,log_cb
    def on_created(self,event):
        if event.is_directory: return
        p=event.src_path
        if self.exts and Path(p).suffix.lower() not in self.exts: return
        self.log(f"📄  New: {os.path.basename(p)}","accent2")
        time.sleep(1.2); self.uploader.enqueue(p)


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
        self.v_sub=tk.BooleanVar(value=cfg.get("subfolders",True))
        self.v_autostart=tk.BooleanVar(value=cfg.get("autostart",False))
        self.v_bg_mode=tk.BooleanVar(value=cfg.get("bg_mode",True))
        self.v_min_tray=tk.BooleanVar(value=cfg.get("min_tray",True))
        self.v_all_files=tk.BooleanVar(value=cfg.get("all_files",True))
        self.v_status=tk.StringVar(value="⏹  Stopped")
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
        self.uploader=None; self.observers=[]; self.running=False
        self.tray_icon=None; self._quitting=False
        self.cur_step=0; self.step_done=[False]*8
        self._active_tab="main"; self._log_lines=[]
        if cfg.get("token") and cfg.get("chat_id") and self.watch_folders:
            self.cur_step=8
            for i in range(8): self.step_done[i]=True
        self.configure(bg=self.C["bg"])
        self._build_layout()
        self.protocol("WM_DELETE_WINDOW",self._on_close)
        if self.cur_step==8: self.after(500,self._start_backup)
        self._refresh_fc()

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
            for lbl,cmd,icon in [
                ("Dashboard",lambda:self._switch_tab("main"),"📡"),
                ("Folders",lambda:self._switch_tab("folders"),"📁"),
                ("File Types",lambda:self._switch_tab("filetypes"),"🗂️"),
                ("Settings",lambda:self._switch_tab("settings"),"⚙️"),
                ("Log",lambda:self._switch_tab("log"),"📋"),
                ("Reconfigure",self._goto_wizard,"🔧"),
            ]:
                act=self._active_tab==lbl.lower().replace(" ","")
                bg=C["hover"] if act else C["sidebar"]; fg=C["accent"] if act else C["text"]
                f=tk.Frame(self.sidebar,bg=bg,cursor="hand2"); f.pack(fill="x",padx=6,pady=1)
                f.bind("<Button-1>",lambda e,c=cmd:c())
                f.bind("<Enter>",lambda e,fr=f:fr.configure(bg=C["hover"]))
                f.bind("<Leave>",lambda e,fr=f,ob=bg:fr.configure(bg=ob))
                tk.Label(f,text=f"{icon}  {lbl}",font=("Consolas",9),bg=bg,fg=fg).pack(side="left",padx=14,pady=9)
        self._sdiv()
        self._status_lbl=tk.Label(self.sidebar,textvariable=self.v_status,font=("Consolas",8),bg=C["sidebar"],fg=C["accent"],width=28,anchor="w"); self._status_lbl.pack(padx=10,pady=(4,2))
        rw=tk.Frame(self.sidebar,bg=C["sidebar"]); rw.pack(fill="x",padx=8,pady=2)
        for var,lbl,clr in [(self.v_uploaded,"✅ sent",C["done"]),(self.v_skipped,"⏭ skip",C["warn"])]:
            f=tk.Frame(rw,bg=C["tag"]); f.pack(side="left",expand=True,fill="x",padx=2)
            tk.Label(f,textvariable=var,font=("Consolas",11,"bold"),bg=C["tag"],fg=clr,width=6,anchor="center").pack()
            tk.Label(f,text=lbl,font=("Consolas",7),bg=C["tag"],fg=C["sub"]).pack(pady=(0,4))
        self._sdiv()
        is_dark=self.theme_name.get()=="dark"
        tk.Button(self.sidebar,text="☀️  Light Mode" if is_dark else "🌙  Dark Mode",
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
        self._wtip(b,"💡  Token looks like:  1234567890:ABCDefGhIjKlMnOpQrStUvWxYz",row=4)
        self._wnav(b,20,back=False,next_cmd=lambda:self._next(0),next_text="Got my token  →")

    def _p2(self):
        b=self._outer(); self._whdr(b)
        self._wbox(b,[("1️⃣","Open your Telegram group or channel."),
                      ("2️⃣","Tap group name → Add Members → search your bot username."),
                      ("3️⃣","For channels: make it Admin with Post Messages permission."),
                      ("4️⃣","Add @userinfobot to the group — it replies instantly with the group ID.")],row=2)
        self._wlink(b,"Open @userinfobot","https://t.me/userinfobot",row=3)
        self._wtip(b,"💡  Group IDs are negative: -1001234567890  |  Channel: @mychannel",row=4,color=self.C["accent"])
        self._wnav(b,20,next_cmd=lambda:self._next(1),next_text="Bot is in group  →")

    def _p3(self):
        C=self.C; b=self._outer(); b.grid_columnconfigure(0,weight=1); self._whdr(b)
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
        if not self.v_token.get().strip(): self.fb3.config(text="⚠  Token required."); return
        self._next(2)

    def _p4(self):
        C=self.C; b=self._outer(); b.grid_columnconfigure(0,weight=1); self._whdr(b)
        self._wentry(b,"CHAT / GROUP ID  (e.g. -1001234567890 or @channel)",self.v_chat,row=2)
        self.fb4=self._wfb(b,4)
        self._wtip(b,"💡  Add @userinfobot to your group — it posts the ID instantly.",row=5,color=self.C["accent2"])
        self._wnav(b,20,next_cmd=self._val4)

    def _val4(self):
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
        opts=[(self.v_autostart,"🚀  Start with Windows","Launches on every boot automatically."),
              (self.v_bg_mode,"🔄  Run in background","Keeps backing up after closing the window."),
              (self.v_min_tray,"🔔  Minimize to tray","X hides to system tray instead of quitting.")]
        for i,(var,lbl,desc) in enumerate(opts):
            f=tk.Frame(b,bg=C["card"],highlightbackground=C["border"],highlightthickness=1)
            f.grid(row=2+i,column=0,sticky="ew",pady=4); f.grid_columnconfigure(1,weight=1)
            tk.Checkbutton(f,variable=var,bg=C["card"],selectcolor=C["tag"],activebackground=C["card"],cursor="hand2").grid(row=0,column=0,padx=(12,6),pady=12)
            inf=tk.Frame(f,bg=C["card"]); inf.grid(row=0,column=1,sticky="ew",pady=12)
            tk.Label(inf,text=lbl,font=("Consolas",9,"bold"),bg=C["card"],fg=C["text"]).pack(anchor="w")
            tk.Label(inf,text=desc,font=("Consolas",8),bg=C["card"],fg=C["sub"]).pack(anchor="w")
        if not TRAY_OK: self._wtip(b,"⚠  Tray needs: pip install pystray pillow",row=6)
        self._wnav(b,20,next_cmd=lambda:self._next(6))

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
        rows=[("🖥️  Machine ID",get_machine_id()),
              ("🔑  Token",self.v_token.get()[:24]+"…" if len(self.v_token.get())>24 else self.v_token.get()),
              ("💬  Chat ID",self.v_chat.get()),("📁  Folders",fl),
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
    def _page_dashboard(self):
        C=self.C; tab=self._active_tab
        outer=tk.Frame(self.content,bg=C["bg"])
        outer.grid(row=0,column=0,sticky="nsew",padx=20,pady=14)
        outer.grid_rowconfigure(2,weight=1); outer.grid_columnconfigure(0,weight=1)
        tb=tk.Frame(outer,bg=C["bg"]); tb.grid(row=0,column=0,sticky="ew",pady=(0,10))
        for tid,tlbl in [("main","📡 Dashboard"),("folders","📁 Folders"),("filetypes","🗂️ Types"),("settings","⚙️ Settings"),("log","📋 Log")]:
            act=tab==tid
            tk.Button(tb,text=tlbl,command=lambda x=tid:self._switch_tab(x),
                      bg=C["accent"] if act else C["tag"],fg=C["sidebar"] if act else C["sub"],
                      font=("Consolas",9,"bold" if act else "normal"),relief="flat",cursor="hand2",padx=12,pady=5
                      ).pack(side="left",padx=(0,4))
        if tab=="main": self._tab_main(outer)
        elif tab=="folders": self._tab_folders(outer)
        elif tab=="filetypes": self._tab_filetypes(outer)
        elif tab=="settings": self._tab_settings(outer)
        elif tab=="log": self._tab_log(outer)

    def _tab_main(self,outer):
        C=self.C; outer.grid_rowconfigure(3,weight=1)
        # stat cards
        sc=tk.Frame(outer,bg=C["bg"]); sc.grid(row=1,column=0,sticky="ew",pady=(0,8))
        sc.grid_columnconfigure((0,1,2,3,4),weight=1)
        for col,(icon,lbl,var,clr) in enumerate([
            ("✅","UPLOADED",self.v_uploaded,C["done"]),
            ("⏭️","SKIPPED",self.v_skipped,C["warn"]),
            ("⛔","OVERSIZED",self.v_size_skip,C["err"]),
            ("❌","ERRORS",self.v_err_skip,C["err"]),
            ("🔁","DUPES",self.v_dup_skip,C["sub"]),
        ]):
            f=tk.Frame(sc,bg=C["card"],highlightbackground=C["border"],highlightthickness=1)
            f.grid(row=0,column=col,padx=3,sticky="ew"); f.grid_columnconfigure(0,weight=1)
            tk.Label(f,text=icon,font=("Segoe UI Emoji",18),bg=C["card"]).pack(pady=(8,0))
            tk.Label(f,textvariable=var,font=("Consolas",20,"bold"),bg=C["card"],fg=clr,width=5,anchor="center").pack()
            tk.Label(f,text=lbl,font=("Consolas",7),bg=C["card"],fg=C["sub"]).pack(pady=(0,8))
        # middle
        mid=tk.Frame(outer,bg=C["bg"]); mid.grid(row=2,column=0,sticky="ew",pady=(0,8))
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
        lf.grid(row=3,column=0,sticky="nsew"); lf.grid_rowconfigure(1,weight=1); lf.grid_columnconfigure(0,weight=1)
        lh=tk.Frame(lf,bg=C["card"]); lh.grid(row=0,column=0,sticky="ew",padx=12,pady=(8,4))
        tk.Label(lh,text="📋  Live Activity",font=("Consolas",9,"bold"),bg=C["card"],fg=C["sub"]).pack(side="left")
        tk.Button(lh,text="Clear",command=self._clear_log,bg=C["tag"],fg=C["sub"],font=("Consolas",8),relief="flat",cursor="hand2",padx=8,pady=2).pack(side="right")
        self.log_box=scrolledtext.ScrolledText(lf,bg=C["bg"],fg=C["text"],font=("Consolas",9),relief="flat",bd=0,state="disabled",wrap="word")
        self.log_box.grid(row=1,column=0,sticky="nsew",padx=8,pady=(0,8))
        for tg,cl in [("done",C["done"]),("accent2",C["accent2"]),("warn",C["warn"]),("err",C["err"]),("sub",C["sub"]),("accent",C["accent"])]:
            self.log_box.tag_configure(tg,foreground=cl)
        self._repopulate_log()
        # controls
        ctrl=tk.Frame(outer,bg=C["bg"]); ctrl.grid(row=4,column=0,sticky="ew",pady=(8,0))
        self.btn_start=tk.Button(ctrl,text="▶  Start",command=self._start_backup,bg=C["accent"],fg=C["sidebar"],font=("Consolas",10,"bold"),relief="flat",cursor="hand2",padx=16,pady=7)
        self.btn_start.pack(side="left",padx=(0,6))
        self.btn_stop=tk.Button(ctrl,text="⏹  Stop",command=self._stop_backup,bg=C["tag"],fg=C["sub"],font=("Consolas",10),relief="flat",cursor="hand2",padx=16,pady=7,state="disabled")
        self.btn_stop.pack(side="left",padx=(0,6))
        tk.Button(ctrl,text="📤  Upload Existing Files",command=self._upload_all,bg=C["accent2"],fg="white",font=("Consolas",9),relief="flat",cursor="hand2",padx=14,pady=7).pack(side="left")
        if self.running: self.btn_start.config(state="disabled"); self.btn_stop.config(state="normal",bg=C["err"],fg="white")

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
        opts=[(self.v_autostart,"🚀  Start with Windows","Adds to Windows startup registry."),
              (self.v_bg_mode,"🔄  Run in background","Backup continues when window is closed."),
              (self.v_min_tray,"🔔  Minimize to tray","X hides to system tray instead of quitting."),
              (self.v_sub,"📂  Include subfolders","Watch nested folders inside watched folders.")]
        for i,(var,lbl,desc) in enumerate(opts):
            f=tk.Frame(outer,bg=C["card"],highlightbackground=C["border"],highlightthickness=1); f.grid(row=2+i,column=0,sticky="ew",pady=4); f.grid_columnconfigure(1,weight=1)
            tk.Checkbutton(f,variable=var,command=self._apply_s,bg=C["card"],selectcolor=C["tag"],activebackground=C["card"],cursor="hand2").grid(row=0,column=0,padx=(12,6),pady=12)
            inf=tk.Frame(f,bg=C["card"]); inf.grid(row=0,column=1,sticky="ew",pady=12)
            tk.Label(inf,text=lbl,font=("Consolas",10,"bold"),bg=C["card"],fg=C["text"]).pack(anchor="w")
            tk.Label(inf,text=desc,font=("Consolas",8),bg=C["card"],fg=C["sub"]).pack(anchor="w")
        tk.Button(outer,text="💾  Save Settings",command=self._apply_s,bg=C["accent"],fg=C["sidebar"],font=("Consolas",10,"bold"),relief="flat",cursor="hand2",pady=8).grid(row=10,column=0,sticky="w",pady=(14,0))

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

    def _start_backup(self):
        if self.running: return
        token=self.v_token.get().strip(); chat=self.v_chat.get().strip()
        if not (token and chat and self.watch_folders): self._log("⚠  Missing config.","warn"); return
        cbs={"log":self._log,"stat":lambda s:self.v_status.set(("🟢  "+s)[:32]),
             "count":self._on_upload,"skip":self._on_skip,"speed":self._on_speed}
        self.uploader=Uploader(token,chat,cbs); self.uploader.start()
        exts=self._get_exts()
        for folder in self.watch_folders:
            if not os.path.isdir(folder): self._log(f"⚠  Missing: {folder}","warn"); continue
            h=FolderWatcher(self.uploader,exts,self._log)
            obs=Observer(); obs.schedule(h,folder,recursive=self.v_sub.get()); obs.start()
            self.observers.append(obs)
        self.running=True; self.v_status.set("🟢  Watching…")
        self._log(f"▶  {len(self.watch_folders)} folder(s) watched  •  {'all types' if not exts else str(len(exts))+' ext'}","done")
        if hasattr(self,"btn_start"): self.btn_start.config(state="disabled"); self.btn_stop.config(state="normal",bg=self.C["err"],fg="white")

    def _stop_backup(self):
        for obs in self.observers: obs.stop(); obs.join()
        self.observers=[]
        if self.uploader: self.uploader.stop(); self.uploader=None
        self.running=False; self.v_status.set("⏹  Stopped"); self._log("⏹  Stopped.","warn")
        if hasattr(self,"btn_start"): self.btn_start.config(state="normal"); self.btn_stop.config(state="disabled",bg=self.C["tag"],fg=self.C["sub"])

    def _restart_backup(self): self._stop_backup(); self.after(300,self._start_backup)

    def _upload_all(self):
        if not self.running: self._log("⚠  Start first.","warn"); return
        exts=self._get_exts(); count=0; pat="**/*" if self.v_sub.get() else "*"
        for folder in self.watch_folders:
            for p in Path(folder).glob(pat):
                if p.is_file():
                    if exts and p.suffix.lower() not in exts: continue
                    self.uploader.enqueue(str(p)); count+=1
        self._log(f"📤  Queued {count} file(s).","accent2")

    # ── Callbacks ─────────────────────────────────────────────────────────────
    def _on_upload(self,n=1):
        self.n_uploaded+=n; self.after(0,lambda:self.v_uploaded.set(str(self.n_uploaded)))

    def _on_skip(self,reason):
        self.n_skipped+=1; self.after(0,lambda:self.v_skipped.set(str(self.n_skipped)))
        if reason=="size": self.n_size+=1; self.after(0,lambda:self.v_size_skip.set(str(self.n_size)))
        elif reason=="error": self.n_err+=1; self.after(0,lambda:self.v_err_skip.set(str(self.n_err)))
        elif reason=="dup": self.n_dup+=1; self.after(0,lambda:self.v_dup_skip.set(str(self.n_dup)))

    def _on_speed(self,bps):
        self.speed_hist.append(bps)
        lbl=f"{bps/1024:.1f} KB/s" if bps<1048576 else f"{bps/1048576:.2f} MB/s"
        self.after(0,lambda:self.v_speed.set(lbl))
        if hasattr(self,"graph") and self.graph.winfo_exists(): self.after(0,lambda:self.graph.push(bps))

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
        ts=datetime.now().strftime("%H:%M:%S"); self._log_lines.append((ts,msg,tag))
        if len(self._log_lines)>500: self._log_lines=self._log_lines[-500:]
        def _do():
            if not hasattr(self,"log_box") or not self.log_box.winfo_exists(): return
            self.log_box.config(state="normal")
            self.log_box.insert("end",f"[{ts}] ","sub"); self.log_box.insert("end",f"{msg}\n",tag)
            self.log_box.see("end"); self.log_box.config(state="disabled")
        self.after(0,_do)

    def _repopulate_log(self):
        if not hasattr(self,"log_box") or not self.log_box.winfo_exists(): return
        self.log_box.config(state="normal"); self.log_box.delete("1.0","end")
        for ts,msg,tag in self._log_lines[-200:]:
            self.log_box.insert("end",f"[{ts}] ","sub"); self.log_box.insert("end",f"{msg}\n",tag)
        self.log_box.see("end"); self.log_box.config(state="disabled")

    def _clear_log(self):
        self._log_lines=[]
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
            "watch_folders":self.watch_folders,"subfolders":self.v_sub.get(),
            "all_files":self.v_all_files.get(),"categories":[c for c,v in self.v_cats.items() if v.get()],
            "autostart":self.v_autostart.get(),"bg_mode":self.v_bg_mode.get(),
            "min_tray":self.v_min_tray.get(),"theme":self.theme_name.get(),"machine_id":get_machine_id(),
        })


def main():
    """Entry point — used by setup.py console_scripts."""
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
