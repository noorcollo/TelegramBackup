# Automatic Windows EXE Builds

TelegramBackup now builds a real Windows executable on GitHub's hosted `windows-latest` runner.

## Automatic builds

Every push to the `main` branch runs the workflow:

- **Workflow:** `Build Windows EXE`
- **Output:** `TelegramBackup.exe`
- **Checksum:** `SHA256SUMS.txt`
- **Artifact retention:** 14 days

To download the result:

1. Open the repository's **Actions** tab.
2. Open the latest **Build Windows EXE** run.
3. Scroll to **Artifacts**.
4. Download `TelegramBackup-Windows-<commit-sha>`.
5. Extract the ZIP and run `TelegramBackup.exe` on Windows 10/11.

The build does not contain Telegram bot tokens or Google OAuth credentials. Users enter credentials locally on each Windows computer, and the application's local configuration files remain outside the repository.

## Manual build

The workflow can also be started manually:

1. Open **Actions → Build Windows EXE**.
2. Click **Run workflow**.
3. Select the `main` branch.
4. Click **Run workflow** again.

## Release builds

For a permanent public download, a future release workflow can attach the EXE to a version tag such as `v4.1.0`. Daily sprint builds intentionally remain temporary Actions artifacts until a version is reviewed and approved for sale or public release.
