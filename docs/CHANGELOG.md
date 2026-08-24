# 📋 Changelog — TelegramBackup

All notable changes to this project are documented here.

---

## [v4.0] — 2026-08-24

### Added
- Modern sidebar dashboard with destination cards, live health, current upload, queue, and speed summaries.
- Destination-aware Activity & Queue page with retry, queue-only removal, and clear actions.
- Shared token-bucket bandwidth limiter across Telegram and Google Drive, with unlimited, preset, and custom KB/s or MB/s values.
- Safe global pause/resume without destroying pending queues.
- Configurable file-stability checks and lightweight offline waiting with automatic resume.
- Daily, session, and all-time statistics with rate-limited persistence.
- General, reliability, and network settings with safe defaults and Windows notification preference.

### Compatibility
- Existing Telegram and Google Drive configuration, OAuth tokens, duplicate histories, watcher behavior, 50 MB Telegram limit, flood-wait handling, retry behavior, autostart, tray, and background mode remain in their original locations and formats.
- New settings are optional and loaded with defaults; source files are never deleted by queue actions.

---

## [v3.0] — 2026-03-14

### Added
- **Multi-folder watching** — add unlimited folders, each watched independently
- **Upload speed graph** — live animated canvas chart (KB/s / MB/s)
- **Day / Night theme** — one-click toggle, saved between sessions
- **5 skip stat counters** — Uploaded, Skipped, Oversized (>50MB), Errors, Duplicates
- **Flood control handling** — auto-waits exact Telegram retry time, counts down visibly
- **Exponential backoff** — automatic retry with increasing wait on network errors
- **Folder file counter** — shows how many folders and total files being watched
- **Polite rate limiting** — 1.5s delay between uploads to prevent flood errors
- **Folders tab** — add/remove folders from the dashboard without restarting
- **File Types tab** — change category filters from the dashboard
- **Log persistence** — log is kept in memory when switching tabs
- `Made by 3ala` credited in sidebar and every Telegram file caption

### Fixed
- Window flickering when filename changes in status bar (fixed-width labels)
- Minimize to tray now works even when backup is not running
- Background mode no longer requires pystray to hide the window
- Status text truncated to prevent sidebar layout shifts

### Changed
- Dashboard redesigned with tabbed navigation
- Stat cards enlarged with bigger numbers
- Sidebar accent stripe added

---

## [v2.0] — 2026-03-14

### Added
- **Machine ID** — unique hardware fingerprint per installation
- **Autostart with Windows** — registry-based startup
- **System tray** — minimize to clock area, right-click menu
- **Background mode** — keep backup alive after closing window
- **Multi-category file types** — 8 categories with individual toggles
- **Settings panel** — change options from dashboard without re-running wizard
- Duplicate prevention via MD5 hashing
- Config persisted between sessions

### Changed
- Wizard extended from 7 to 8 steps (added System Options step)
- File type selection redesigned with category grid

---

## [v1.0] — 2026-03-13

### Initial Release
- 7-step setup wizard
- Single folder watching via watchdog
- Auto-upload new files to Telegram
- Bot token + Chat ID configuration
- Upload existing files button
- Activity log
- Live connection test for bot token
- File type filter (extension list)
- Subfolder toggle
- Settings saved to JSON config
