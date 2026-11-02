# TelegramBackup Rust port (v4 compatibility)

This separate `rust-port` branch adds an early native Windows GUI implementation using Rust, `egui`/`eframe`, and Cargo. It leaves the Python app untouched.

## Compatibility

The app reads and writes the same per-user files as TelegramBackup v4:

- `%USERPROFILE%\\.tgbackup_v3_config.json` (or `$HOME/.tgbackup_v3_config.json`): loads the existing JSON object and preserves unknown settings, including Drive-related values. It updates the familiar `token`, `chat_id`, and `watch_folders` keys.
- `%USERPROFILE%\\.tgbackup_v3_history.json` (or `$HOME/.tgbackup_v3_history.json`): reads and writes the legacy JSON array of MD5 strings, so already-uploaded items are recognized across versions.

The history array is shared with the existing app; avoid running both versions against the same profile simultaneously while either is writing it.

## Implemented in this initial port

- Native dark egui dashboard and bot connectivity check.
- Add/remove watched folders, manual recursive scans, and filesystem event watching.
- Telegram `sendDocument` uploads, 50 MiB size cap, MD5 duplicate suppression, saved legacy history, and retry/backoff with Telegram `retry_after` handling.
- Upload queue pause/resume between files.
- Settings persisted using the existing v4 config file and key names.
- GitHub Actions Windows build producing `TelegramBackup-Rust.exe` plus SHA-256 checksum.

## Not yet at v4 feature parity

Google Drive OAuth/upload, file-category filters, bandwidth throttling, offline detection, system-tray/autostart behavior, notifications, detailed statistics, and the full onboarding wizard have not yet been ported. Existing Drive settings are preserved, but this Rust version does not currently upload to Drive. Treat this as an initial port, not a replacement for the established Python release.

## Build

Install stable Rust and run from this directory:

```powershell
cargo test
cargo run
cargo build --release
```

The checked-in workflow builds on GitHub's hosted Windows runner when changes are pushed to `rust-port`, on pull requests targeting `main`, or by manual dispatch. The actual Windows `.exe` is available in the Actions artifact after that workflow succeeds; it is not built in this Linux sandbox.
