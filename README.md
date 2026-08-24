# 📡 TelegramBackup

> **Auto-backup any folder on your PC to Telegram, Google Drive, or both.**
> New files are detected instantly and uploaded automatically, with optional Google Drive OAuth.

<div align="center">

![Version](https://img.shields.io/badge/version-v4.0-00e5b0?style=flat-square)
![Platform](https://img.shields.io/badge/platform-Windows%2010%2F11-0078d4?style=flat-square)
![Python](https://img.shields.io/badge/python-3.9%2B-3776ab?style=flat-square)
![License](https://img.shields.io/badge/license-MIT-green?style=flat-square)
![Made by](https://img.shields.io/badge/made%20by-3ala-ff6b6b?style=flat-square)

</div>

---

## ✨ Features

| Feature | Description |
|---|---|
| 📁 **Multi-folder watching** | Watch as many folders as you want simultaneously |
| 📤 **Auto upload** | New files are detected and uploaded instantly |
| 🎯 **Two backup destinations** | Choose Telegram only, Google Drive only, or both |
| ☁️ **Optional Google Drive** | OAuth-protected Drive uploads with a selectable destination folder |
| 🗂️ **All file types** | Documents, images, videos, audio, archives, code, databases, executables |
| 📶 **Speed graph** | Live animated upload speed chart (KB/s or MB/s) |
| 📊 **Skip stats** | Tracks uploaded, skipped, oversized, errors, and duplicates separately |
| 🌙 **Day / Night theme** | One-click toggle, remembered between sessions |
| 🚀 **Autostart with Windows** | Launches silently on every boot |
| 🔄 **Background mode** | Keeps backing up after you close the window |
| 🔔 **System tray** | Minimize to the clock area, right-click to open or quit |
| 🔁 **Duplicate prevention** | MD5 hash check — same file is never uploaded twice |
| ⏸ **Pause / resume** | Safely pause active transfers while retaining the queue |
| 📶 **Global bandwidth limiter** | Shared token-bucket limit across Telegram and Drive, including custom KB/s and MB/s values |
| 🧾 **Queue and statistics** | Live destination-aware activity table plus daily, session, and all-time summaries |
| 🛡️ **Reliability controls** | File stability checks, offline queue waiting, configurable retry settings, and health state |
| ⏳ **Flood control** | Auto-waits when Telegram rate-limits, retries automatically |
| 🖥️ **Machine ID** | Each installation is tagged — know which PC uploaded each file |
| 🔧 **8-step wizard** | Guided first-time setup, including destination selection and Drive connection testing |

---

## 🖥️ Screenshots

> _Dark Mode_

```
┌─────────────────────────────────────────────────────────────────┐
│ 📡 TelegramBackup          [Dashboard] [Folders] [Settings] ... │
│                            ╔══════╗╔══════╗╔══════╗╔══════╗    │
│  📡 TelegramBackup         ║  12  ║║  2   ║║  0   ║║  1   ║    │
│  v3 • Made by 3ala         ║UPLOAD║║ SKIP ║║OVERSIZE DUPE ║    │
│  🖥️ A3F2C1B09D4E           ╚══════╝╚══════╝╚══════╝╚══════╝    │
│  ────────────              ┌─────────────┐ ┌──────────────────┐ │
│  📡 Dashboard              │ 📁 Watching │ │ 📶 Upload Speed  │ │
│  📁 Folders                │ 3 folders   │ │ ▁▃▅▇▅▃▁▂▄▆▇▅▃   │ │
│  🗂️ File Types             │ 1,247 files │ │         2.4 MB/s │ │
│  ⚙️ Settings               └─────────────┘ └──────────────────┘ │
│  📋 Log                    [▶ Start] [⏹ Stop] [📤 Upload All]   │
│  ────────────              ────────────────────────────────────  │
│  🟢 Watching…              [20:14:32] ✅ report.pdf (240 KB)    │
│  12 ✅  2 ⏭               [20:14:34] ✅ backup.zip (1.2 MB)    │
│  ────────────              [20:14:36] ⏳ Flood wait 21s...      │
│  ☀️ Light Mode             [20:14:58] ✅ photo.jpg (540 KB)     │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🚀 Quick Start

### Option A — Run with Python (Recommended)

**1. Install Python 3.9+**  
Download from [python.org](https://www.python.org/downloads/) — check ✅ **"Add Python to PATH"** during install.

**2. Clone or download this repo**
```bash
git clone https://github.com/noorcollo/TelegramBackup.git
cd TelegramBackup
```

**3. Install dependencies**
```bash
pip install -r requirements.txt
```

**4. Run**
```bash
python telegram_backup_v3.py
```

The v4 interface keeps the original Tkinter desktop architecture and existing JSON files. New settings use safe defaults, so existing installations do not need to reconfigure Telegram or Google Drive.

Or on Windows, just double-click:

```text
Launch_TelegramBackup.bat
```
The `.bat` file handles Python detection and package installation automatically.

### v4 settings and compatibility

The application continues to read and write the existing `%USERPROFILE%\\.tgbackup_v3_config.json`, Telegram history, Google Drive token, and Google Drive history files. Added settings are optional and default to conservative values: unlimited bandwidth, uploads paused while offline, a two-second stability check, notifications enabled, and a 30-second connectivity check interval. The new statistics file is `%USERPROFILE%\\.tgbackup_v4_stats.json` and is written at a throttled interval rather than on every UI refresh.

The queue’s **Remove from queue** action removes only an application queue entry. It never deletes source files.

---

### Option B — Windows .exe (No Python needed)

Download the latest `.exe` from the [Releases](../../releases) page and run it directly.

---

## 📋 First-Time Setup (8-Step Wizard)

The app walks you through everything step by step:

```
Step 1 → Create a Telegram Bot via @BotFather
Step 2 → Add your bot to a group/channel
Step 3 → Paste your Bot Token (with live verification)
Step 4 → Paste your Chat / Group ID
Step 5 → Select folders to watch (add as many as you want)
Step 6 → Choose file types (or select ALL)
Step 7 → Choose Telegram, Google Drive, or both; connect Drive and choose a folder; configure system options
Step 8 → Review summary and launch
```

Settings are saved after the wizard — future launches go straight to the dashboard.

---

## ☁️ Setting Up Google Drive Backup

Google Drive is optional. You can use Telegram only, Google Drive only, or both destinations at the same time.

1. In the [Google Cloud Console](https://console.cloud.google.com/), enable the Google Drive API.
2. Configure the Google Auth platform and create a **Desktop app** OAuth client.
3. Download the JSON file and keep it on your computer; do not commit it to GitHub.
4. In TelegramBackup, open **Settings → Backup Destinations**, choose **Google Drive Backup**, and browse to the JSON file.
5. Click **Connect & Test**, complete the Google authorization in your browser, and optionally create a `TelegramBackup` folder.
6. Use the dashboard buttons to switch Telegram Backup and Google Drive Backup on or off. At least one destination must remain enabled.

The app stores the local Google refresh token in your user profile. It does not place credentials in the source code or repository.

## ⚙️ Getting Your Telegram Credentials

### Bot Token
1. Open Telegram → search **@BotFather**
2. Send `/newbot`
3. Follow the prompts (pick a name and username ending in `bot`)
4. Copy the token — looks like: `1234567890:REPLACE_WITH_BOT_TOKEN`

### Chat / Group ID
1. Add your bot to your group/channel as a member
2. Add **@userinfobot** to the group — it replies with the group ID instantly
3. Group IDs are negative numbers: `-1001234567890`
4. Channel usernames also work: `@mychannel`

> ⚠️ **Security:** Never share your bot token publicly. If exposed, revoke it immediately via @BotFather → `/revoke`.

---

## 📦 File Type Support

| Category | Extensions |
|---|---|
| 📄 Documents | `.pdf` `.doc` `.docx` `.xls` `.xlsx` `.ppt` `.pptx` `.txt` `.rtf` `.csv` |
| 🖼️ Images | `.jpg` `.jpeg` `.png` `.gif` `.bmp` `.webp` `.svg` `.tiff` `.heic` `.raw` |
| 🎬 Videos | `.mp4` `.mkv` `.avi` `.mov` `.wmv` `.flv` `.webm` `.m4v` `.3gp` |
| 🎵 Audio | `.mp3` `.wav` `.flac` `.aac` `.ogg` `.m4a` `.wma` `.opus` |
| 🗜️ Archives | `.zip` `.rar` `.7z` `.tar` `.gz` `.bz2` `.xz` `.iso` |
| 💻 Code | `.py` `.js` `.ts` `.html` `.css` `.java` `.cpp` `.go` `.rs` `.sql` |
| 🗃️ Databases | `.db` `.sqlite` `.sqlite3` `.mdb` `.bak` |
| 📦 Executables | `.exe` `.msi` `.apk` `.dmg` `.deb` |

Select individual categories or enable **"Back up ALL file types"** to upload everything.

---

## ⚠️ Limitations

| Limit | Details |
|---|---|
| Max file size | **50 MB** per file (Telegram Bot API limit) |
| Files > 50 MB | Skipped with a warning, counted in "Oversized" stat |
| Rate limiting | Handled automatically — app waits the exact time Telegram requests and retries |
| Duplicate files | Detected via MD5 hash — never uploaded twice |

---

## 🗂️ Project Structure

```
TelegramBackup/
│
├── telegram_backup_v3.py     # Main application and existing Tkinter UI/engine
├── drive_backup.py            # Existing optional Google Drive OAuth/uploader module
├── bandwidth.py               # Shared token-bucket limiter and throttled reader
├── tests/test_core.py         # Offline smoke tests for limiter and stability checks
├── Launch_TelegramBackup.bat # Windows launcher (auto-installs deps)
├── requirements.txt          # Python dependencies
├── .gitignore                # Excludes config/token files from git
├── LICENSE                   # MIT License
├── README.md                 # This file
│
└── docs/
    ├── SETUP.md              # Detailed setup guide
    ├── TROUBLESHOOTING.md    # Common issues and fixes
    └── CHANGELOG.md          # Version history
```

---

## 🔧 Configuration Files

These are created automatically on first run — **never commit them to Git**.

| File | Location | Contains |
|---|---|---|
| `.tgbackup_v3_config.json` | `%USERPROFILE%\` | Token, chat ID, folder list, settings |
| `.tgbackup_v3_history.json` | `%USERPROFILE%\` | MD5 hashes of Telegram uploads |
| `.tgbackup_v3_drive_token.json` | `%USERPROFILE%\` | Local Google OAuth token cache |
| `.tgbackup_v3_drive_history.json` | `%USERPROFILE%\` | Google Drive duplicate-prevention history |

---

## 🛠️ Building the .exe Yourself

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name TelegramBackup \
  --hidden-import=telegram \
  --hidden-import=watchdog.observers \
  --hidden-import=pystray._win32 \
  --collect-all telegram \
  --collect-all watchdog \
  --collect-all pystray \
  --collect-all PIL \
  --hidden-import=drive_backup \
  --collect-all googleapiclient \
  --collect-all google_auth_oauthlib \
  telegram_backup_v3.py
```

Output: `dist/TelegramBackup.exe`

The build includes both destinations. Google Drive credentials and OAuth token files remain external and are entered locally on each computer.

---

## 📜 Changelog

See [docs/CHANGELOG.md](docs/CHANGELOG.md) for full version history.

---

## 🤝 Contributing

Pull requests are welcome. For major changes, open an issue first.

1. Fork the repo
2. Create your branch: `git checkout -b feature/my-feature`
3. Commit: `git commit -m "Add my feature"`
4. Push: `git push origin feature/my-feature`
5. Open a Pull Request

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.

---

<div align="center">

Made with ❤️ by **3ala**

</div>
