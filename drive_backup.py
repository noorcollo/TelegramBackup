"""Optional Google Drive backup support for TelegramBackup.

The module keeps Google dependencies optional so Telegram-only users can run the
application without configuring Google Drive. OAuth credentials and tokens stay
on the local Windows machine and are never written to the repository.
"""

import mimetypes
import os
import queue
import threading
import time
from pathlib import Path

from bandwidth import BandwidthLimiter

DRIVE_SCOPE = "https://www.googleapis.com/auth/drive.file"
DRIVE_TOKEN_FILE = os.path.join(os.path.expanduser("~"), ".tgbackup_v3_drive_token.json")
DRIVE_HISTORY_FILE = os.path.join(os.path.expanduser("~"), ".tgbackup_v3_drive_history.json")

_IMPORT_ERROR = None
try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaFileUpload
except ImportError as exc:  # pragma: no cover - exercised on machines without extras
    _IMPORT_ERROR = exc


def drive_available():
    """Return whether the optional Google client libraries are installed."""
    return _IMPORT_ERROR is None


def drive_install_hint():
    return "Install Google Drive support with: pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib"


def _load_history():
    try:
        if os.path.exists(DRIVE_HISTORY_FILE):
            import json
            with open(DRIVE_HISTORY_FILE, encoding="utf-8") as handle:
                return set(json.load(handle))
    except Exception:
        pass
    return set()


def _save_history(values):
    import json
    with open(DRIVE_HISTORY_FILE, "w", encoding="utf-8") as handle:
        json.dump(sorted(values), handle, indent=2)


class GoogleDriveClient:
    """Small wrapper around Drive v3 using a local desktop OAuth flow."""

    def __init__(self, credentials_path, token_path=DRIVE_TOKEN_FILE):
        self.credentials_path = os.path.abspath(os.path.expanduser(credentials_path or ""))
        self.token_path = os.path.abspath(os.path.expanduser(token_path))
        self.service = None

    def authenticate(self):
        if not drive_available():
            raise RuntimeError(drive_install_hint())
        if not self.credentials_path or not os.path.isfile(self.credentials_path):
            raise FileNotFoundError("Select the Google OAuth desktop credentials JSON file first.")

        creds = None
        if os.path.isfile(self.token_path):
            try:
                creds = Credentials.from_authorized_user_file(self.token_path, [DRIVE_SCOPE])
            except Exception:
                creds = None

        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        elif not creds or not creds.valid:
            flow = InstalledAppFlow.from_client_secrets_file(self.credentials_path, [DRIVE_SCOPE])
            creds = flow.run_local_server(port=0, open_browser=True)

        token_dir = os.path.dirname(self.token_path)
        if token_dir:
            os.makedirs(token_dir, exist_ok=True)
        with open(self.token_path, "w", encoding="utf-8") as handle:
            handle.write(creds.to_json())

        self.service = build("drive", "v3", credentials=creds, cache_discovery=False)
        return self.service

    def ensure_service(self):
        return self.service or self.authenticate()

    def test_connection(self):
        service = self.ensure_service()
        # A minimal Drive v3 request that works with the drive.file scope.
        result = service.files().list(
            pageSize=1,
            spaces="drive",
            q="trashed = false",
            fields="files(id,name)",
        ).execute()
        return result.get("files", [])

    def create_folder(self, name="TelegramBackup", parent_id=""):
        service = self.ensure_service()
        metadata = {
            "name": name.strip() or "TelegramBackup",
            "mimeType": "application/vnd.google-apps.folder",
        }
        if parent_id.strip():
            metadata["parents"] = [parent_id.strip()]
        return service.files().create(body=metadata, fields="id,name").execute()

    def upload_file(self, file_path, folder_id="", progress_cb=None,
                    limiter=None, cancel_event=None, speed_cb=None):
        service = self.ensure_service()
        path = Path(file_path)
        metadata = {"name": path.name}
        if folder_id and folder_id.strip():
            metadata["parents"] = [folder_id.strip()]
        mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        media = MediaFileUpload(
            str(path),
            mimetype=mime_type,
            resumable=True,
            # Smaller resumable chunks let the shared limiter control the
            # actual transfer rate instead of delaying completed files.
            chunksize=256 * 1024,
        )
        request = service.files().create(
            body=metadata,
            media_body=media,
            fields="id,name,size",
        )
        response = None
        last_bytes = 0
        last_time = time.monotonic()
        total_size = max(1, path.stat().st_size)
        while response is None:
            # ``next_chunk`` sends the next resumable chunk. Charge the shared
            # budget before sending it so Telegram and Drive share one limit.
            sent_before = int(getattr(media, "_progress", 0) or 0)
            planned = min(256 * 1024, max(0, total_size - sent_before))
            if limiter and planned and not limiter.acquire(planned, cancel_event):
                raise RuntimeError("Upload paused or stopped")
            status, response = request.next_chunk()
            if status is not None:
                progress = status.progress()
                if progress_cb:
                    progress_cb(progress)
                now = time.monotonic()
                current_bytes = int(progress * total_size)
                if speed_cb and now > last_time:
                    speed_cb(max(0, current_bytes - last_bytes) / (now - last_time))
                last_bytes, last_time = current_bytes, now
        return response


class DriveUploader(threading.Thread):
    """Background queue that uploads new files to Google Drive."""

    def __init__(self, client, folder_id, callbacks, limiter=None, cancel_event=None):
        super().__init__(daemon=True)
        self.client = client
        self.folder_id = folder_id.strip()
        self.on_log = callbacks["log"]
        self.on_stat = callbacks["stat"]
        self.on_success = callbacks["success"]
        self.on_skip = callbacks["skip"]
        self.on_item = callbacks.get("item", lambda *args, **kwargs: None)
        self.is_cancelled = callbacks.get("is_cancelled", lambda path: False)
        self.is_online = callbacks.get("is_online", lambda: True)
        self.limiter = limiter or BandwidthLimiter()
        self.cancel_event = cancel_event or threading.Event()
        self.queue = queue.Queue()
        self.uploaded = _load_history()
        self.active = True
        self.max_retries = 4

    def enqueue(self, path):
        self.on_item(path, "Google Drive", "Waiting", 0.0, 0)
        self.queue.put(path)

    def stop(self):
        self.active = False
        self.cancel_event.set()
        self.limiter.set_paused(False)

    def run(self):
        try:
            self.client.ensure_service()
            self.on_log("☁  Google Drive connected.", "done")
        except Exception as exc:
            self.on_log(f"❌  Google Drive connection failed: {exc}", "err")
            self.active = False
            return

        while self.active:
            try:
                path = self.queue.get(timeout=0.4)
            except queue.Empty:
                continue
            if self.is_cancelled(path):
                self.on_item(path, "Google Drive", "Removed", 0.0, 0)
                continue
            if not os.path.exists(path):
                self.on_log(f"⚠  Drive source gone: {os.path.basename(path)}", "warn")
                self.on_skip("error")
                continue
            try:
                size = os.path.getsize(path)
                if size == 0:
                    self.on_log(f"⚠  Drive skipped empty file: {os.path.basename(path)}", "warn")
                    self.on_skip("error")
                    continue
                key = f"{path}::{os.path.getmtime(path)}::{size}"
                if key in self.uploaded:
                    self.on_log(f"⏭  Drive duplicate: {os.path.basename(path)}", "sub")
                    self.on_skip("dup")
                    continue

                self.on_item(path, "Google Drive", "Uploading", 0.0, 0)
                while self.active and not self.is_online():
                    self.on_item(path, "Google Drive", "Paused", 0.0, 0)
                    self.on_stat("Offline — waiting for internet connection")
                    time.sleep(5)
                if not self.active: break
                self.on_stat(f"Drive: {os.path.basename(path)}…")
                success = False
                for attempt in range(1, self.max_retries + 1):
                    if not self.active:
                        break
                    try:
                        self.on_item(path, "Google Drive", "Uploading", 0.0, attempt - 1)
                        self.client.upload_file(
                            path,
                            self.folder_id,
                            progress_cb=lambda pct: (
                                self.on_stat(f"Drive {pct * 100:.0f}%: {os.path.basename(path)}"),
                                self.on_item(path, "Google Drive", "Uploading", pct, attempt - 1),
                            ),
                            limiter=self.limiter,
                            cancel_event=self.cancel_event,
                            speed_cb=self.on_speed,
                        )
                        self.uploaded.add(key)
                        _save_history(self.uploaded)
                        self.on_log(f"☁  ✅  {os.path.basename(path)}", "done")
                        self.on_success(1)
                        self.on_item(path, "Google Drive", "Completed", 1.0, attempt - 1)
                        success = True
                        break
                    except Exception as exc:
                        if attempt >= self.max_retries:
                            self.on_log(
                                f"❌  Drive upload failed: {os.path.basename(path)} — {exc}",
                                "err",
                            )
                        else:
                            self.on_log(
                                f"⚠  Drive retry {attempt}/{self.max_retries}: {exc}",
                                "warn",
                            )
                            self.on_item(path, "Google Drive", "Retrying", 0.0, attempt)
                            import time
                            time.sleep(2 ** attempt)
                if not success and self.active:
                    self.on_item(path, "Google Drive", "Error", 0.0, self.max_retries)
                    self.on_skip("error")
                self.on_stat("Watching…")
            except Exception as exc:
                self.on_log(f"❌  Drive worker error: {exc}", "err")
                self.on_skip("error")


__all__ = [
    "DRIVE_TOKEN_FILE",
    "GoogleDriveClient",
    "DriveUploader",
    "drive_available",
    "drive_install_hint",
]
