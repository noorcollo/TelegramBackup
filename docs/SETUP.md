# 🛠️ Setup Guide — TelegramBackup v3

This guide walks you through everything from zero to fully running backup.

---

## Step 1 — Install Python

1. Go to **https://python.org/downloads/**
2. Download Python **3.9 or higher** (3.11+ recommended)
3. Run the installer
4. ✅ **Check "Add Python to PATH"** — this is critical, don't skip it
5. Click **Install Now**
6. When done, open Command Prompt and run `python --version` to confirm

---

## Step 2 — Download TelegramBackup

**Option A — Git clone (recommended):**
```bash
git clone https://github.com/YOUR_USERNAME/TelegramBackup.git
cd TelegramBackup
```

**Option B — Download ZIP:**
- Click the green **Code** button on GitHub → **Download ZIP**
- Extract the folder anywhere on your PC

---

## Step 3 — Install Dependencies

Open Command Prompt in the TelegramBackup folder and run:
```bash
pip install -r requirements.txt
```

Or just double-click **`Launch_TelegramBackup.bat`** — it does this automatically.

---

## Step 4 — Create a Telegram Bot

1. Open Telegram
2. Search for **@BotFather** and open the chat
3. Send `/newbot`
4. When asked for a **name**, type anything (e.g. `My Backup Bot`)
5. When asked for a **username**, type something ending in `bot` (e.g. `mybackup_bot`)
6. BotFather will send you a message containing your **token**

The token looks like this:
```
1234567890:ABCDefGhIjKlMnOpQrStUvWxYz
```

**Keep this token private. Anyone with this token can control your bot.**

---

## Step 5 — Set Up Your Telegram Group

1. Create a Telegram group (or use an existing one)
2. Add your bot to the group:
   - Open the group
   - Tap the group name at the top
   - Click **Add Members**
   - Search your bot's username and add it
3. If using a **channel**, make your bot an Admin with "Post Messages" permission

---

## Step 6 — Get Your Chat ID

**Method 1 (easiest):**
1. Add **@userinfobot** to your group
2. It immediately replies with the group info including the ID
3. The ID is a **negative number** like `-1001234567890`
4. You can remove @userinfobot after

**Method 2 (channels):**
- Use the channel username with @ sign: `@mychannel`

**Method 3 (personal chat):**
- Message @userinfobot directly — it shows your personal user ID

---

## Step 7 — Launch and Configure

1. Double-click **`Launch_TelegramBackup.bat`**
2. The **8-step wizard** opens
3. Follow each step:
   - Steps 1-2: Confirm you've done the Telegram setup
   - Step 3: Paste your **Bot Token** → click Test Connection to verify
   - Step 4: Paste your **Chat/Group ID**
   - Step 5: Click ➕ Add Folder for each folder you want to back up
   - Step 6: Choose file types (or leave "All types" checked)
   - Step 7: Configure autostart, background mode, tray options
   - Step 8: Review everything → click **Launch**
4. Dashboard opens and backup starts automatically

---

## Step 8 — Optional System Options

| Option | What it does | Recommended |
|---|---|---|
| 🚀 Autostart with Windows | App launches silently on every boot | ✅ Yes |
| 🔄 Run in background | Window close keeps backup running | ✅ Yes |
| 🔔 Minimize to tray | X button → goes to clock area | ✅ Yes |
| 📂 Include subfolders | Watches folders inside folders | Depends |

---

## Testing Your Setup

1. Start watching
2. Copy any file into your watched folder
3. Within 2-3 seconds, the file should appear in your Telegram group
4. The caption shows: filename, date, size, and your machine ID

---

## Autostart Without the Wizard

After first setup, the app remembers everything. On next launch it skips the wizard and goes straight to the dashboard, then starts watching automatically.

To reset and re-run the wizard: delete `~/.tgbackup_v3_config.json`

---

## Need Help?

See [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for common issues.
