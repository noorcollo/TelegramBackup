# 🔧 Troubleshooting — TelegramBackup v3

---

## ❌ "Python not found" when running the .bat file

**Cause:** Python is not installed or not added to PATH.

**Fix:**
1. Download Python from https://python.org/downloads/
2. During install, **check "Add Python to PATH"** before clicking Install
3. After install, restart your PC
4. Try running the .bat again

---

## ❌ "Package installation failed"

**Cause:** Permission issue or corporate network blocking pip.

**Fix:**
1. Right-click `Launch_TelegramBackup.bat` → **Run as Administrator**
2. Or manually: open Command Prompt as Admin and run:
   ```
   pip install -r requirements.txt
   ```

---

## ❌ Token verification fails — "Unauthorized"

**Cause:** Token is wrong, has spaces, or was revoked.

**Fix:**
1. Go back to @BotFather → `/mybots` → select your bot → API Token
2. Copy the entire token with no spaces
3. Make sure you didn't accidentally copy extra characters

---

## ❌ Files not appearing in Telegram group

**Possible causes and fixes:**

| Problem | Fix |
|---|---|
| Bot not in group | Add your bot as a member of the group |
| Wrong Chat ID | Re-add @userinfobot to get the correct ID |
| File type filtered | Check Step 6 — make sure the file extension is selected or use "All types" |
| File over 50MB | Files larger than 50MB cannot be uploaded via Telegram Bot API |
| Backup not started | Click ▶ Start on the dashboard |

---

## ❌ "Flood control exceeded" errors

**Cause:** Uploading too many files too fast. Telegram rate-limits bots.

**This is now handled automatically.** The app:
1. Detects the flood error
2. Reads the exact wait time from Telegram
3. Shows a countdown: `⏳ Flood wait 21s…`
4. Retries automatically after the wait
5. Adds a 1.5s pause between uploads to prevent future floods

If you see this a lot, you're uploading many files at once — that's normal and will resolve itself.

---

## ❌ System tray not working (minimize to tray does nothing)

**Cause:** `pystray` and `Pillow` not installed.

**Fix:**
```bash
pip install pystray pillow
```

**Fallback:** If pystray isn't available, the app minimizes to the Windows taskbar instead. The backup still keeps running.

---

## ❌ App flickers or jumps when uploading

**Cause:** This was a bug in earlier versions where variable-length filenames caused layout recalculations.

**Fix:** Update to the latest version (v3 fixed). All dynamic labels now have fixed widths.

---

## ❌ "File gone" warnings in the log

**Cause:** A file was detected but deleted before the app could upload it.

**This is normal** for temporary files. The app skips them automatically.

---

## ❌ Same file uploaded twice

**This should not happen** — the app uses MD5 hashing to prevent duplicates. If it does:
1. Check if the file was genuinely modified (different content = different hash = re-uploaded intentionally)
2. The history file might have been deleted — at `~/.tgbackup_v3_history.json`

---

## ❌ Autostart not working

**Cause:** Registry write failed (permission issue) or Python path changed.

**Fix:**
1. Run the app as Administrator at least once after enabling autostart
2. Check: Open Run (`Win+R`) → type `regedit` → navigate to:
   `HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Run`
   You should see `TelegramBackup` listed there

---

## ❌ App won't open after first setup

**Fix:** Delete the config file and re-run the wizard:
1. Open File Explorer
2. Navigate to `%USERPROFILE%` (type it in the address bar)
3. Delete `.tgbackup_v3_config.json`
4. Re-launch the app

---

## 📋 Collecting Logs for Bug Reports

1. Open the app → click **📋 Log** tab
2. Copy all the log text
3. Open a GitHub Issue and paste the log

When reporting a bug, include:
- Windows version
- Python version (`python --version`)
- What you were doing when it happened
- The log output
