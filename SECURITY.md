# 🔒 Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| v3.x    | ✅ Yes     |
| v2.x    | ⚠️ Best effort |
| v1.x    | ❌ No      |

---

## 🚨 Reporting a Vulnerability

If you discover a security issue (e.g. token leakage, path traversal, code injection), **do NOT open a public GitHub issue.**

Instead:

1. Go to the **Security** tab of this repository
2. Click **Report a vulnerability**
3. Describe the issue clearly

Or email directly if a contact is listed in the profile.

I will respond within **48 hours** and release a patch as quickly as possible.

---

## ⚠️ Important Notes for Users

### Bot Token Safety
- **Never share your bot token** in issues, commits, or any public place
- If your token is exposed, revoke it immediately: open Telegram → @BotFather → `/revoke`
- TelegramBackup stores the token **locally only** in `~/.tgbackup_v3_config.json`
- This file is listed in `.gitignore` — it will never be committed to Git

### What TelegramBackup Does NOT Do
- It does not send your files anywhere except the Telegram chat you specify
- It does not collect analytics or phone home
- It does not store files — it reads them once to upload, then forgets
- It does not have any network communication other than the Telegram Bot API

### File Permissions
- The app reads files from folders you explicitly select
- It writes only to `~/.tgbackup_v3_config.json` and `~/.tgbackup_v3_history.json`
- On Windows, it optionally writes one registry key for autostart

---

## 🧪 Dependency Security

This project uses well-known, maintained libraries:

| Package | Purpose | Source |
|---|---|---|
| `python-telegram-bot` | Telegram API client | pypi.org |
| `watchdog` | Filesystem monitoring | pypi.org |
| `pystray` | System tray icon | pypi.org |
| `Pillow` | Tray icon image | pypi.org |

Keep dependencies updated:
```bash
pip install -r requirements.txt --upgrade
```
