# TelegramBackup v4 Upgrade Notes

## Scope

This upgrade modernizes the existing Tkinter desktop application incrementally. The existing Telegram and Google Drive backup engines, OAuth flow, JSON configuration paths, duplicate histories, watchdog folder monitoring, 50 MB Telegram limit, retry/backoff behavior, flood-wait handling, autostart, tray, background mode, and upload queue architecture remain in place.

## Changed files

| File | Modification |
|---|---|
| `telegram_backup_v3.py` | Added v4 dashboard status card, sidebar navigation, destination view, queue/activity view, statistics view, live queue state, safe pause/resume, offline waiting, file-stability checks, notification preference, bounded log tools, health indicators, and backward-compatible settings defaults. Worker callbacks now dispatch Tk updates safely through `after()`. |
| `drive_backup.py` | Preserved Google Drive OAuth and duplicate history while adding shared limiter integration, smaller resumable chunks for transfer control, progress/speed callbacks, queue state, cancellation, and offline waiting. |
| `bandwidth.py` | New dependency-free shared token-bucket limiter and throttled file reader used by Telegram and Drive. Unlimited mode has minimal overhead; limits can change while running. |
| `setup.py` | Bumped package version to `4.0.0` and included `bandwidth.py`. |
| `README.md` | Documented v4 controls and compatibility behavior. |
| `docs/CHANGELOG.md` | Added v4 release notes. |
| `tests/test_core.py` | Added offline tests for limit parsing, throttled reads, and file stability queueing. |
| `tests/test_gui.py` | Added a headless Tkinter construction/shutdown smoke test. |
| `backups/20260824_160706/` | Timestamped copies of important pre-change source and launcher files. |

## New dependencies

No new runtime dependency was added. The limiter uses only the Python standard library. The existing dependency list remains unchanged.

## Configuration compatibility

The existing files under `%USERPROFILE%` remain supported, including `.tgbackup_v3_config.json`, `.tgbackup_v3_history.json`, `.tgbackup_v3_drive_token.json`, and `.tgbackup_v3_drive_history.json`. New keys are optional and use safe defaults. Aggregate statistics are stored separately in `.tgbackup_v4_stats.json`.

## Build and run

```powershell
pip install -r requirements.txt
python telegram_backup_v3.py
```

The supported Windows launcher remains `Launch_TelegramBackup.bat`. To build an executable, use the existing PyInstaller command from the README; PyInstaller will include the imported `bandwidth` module, or it can be listed explicitly as an additional module if using a custom spec file.

## Validation

The following checks passed in the sandbox:

```text
python3 tests/test_core.py                    core tests passed
xvfb-run -a python3 tests/test_gui.py         GUI construction test passed
python3 -m py_compile ...                     final validation passed
python3 setup.py --name --version             telegrambackup / 4.0.0
```

Live Telegram API, Google OAuth, flood-wait, network interruption, and Windows tray/registry behavior were not exercised in the sandbox because they require user credentials and a Windows runtime. The implementation preserves the existing paths and APIs for those flows.
