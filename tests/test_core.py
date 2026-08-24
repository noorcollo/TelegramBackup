import os
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bandwidth import BandwidthLimiter, ThrottledReader
from telegram_backup_v3 import FolderWatcher, format_limit, parse_limit


class Sink:
    def __init__(self):
        self.items = []
        self.event = threading.Event()

    def enqueue(self, path):
        self.items.append(path)
        self.event.set()


def test_bandwidth_and_parsing():
    assert parse_limit("500 KB/s") == 500 * 1024
    assert parse_limit("2 MB/s") == 2 * 1024 * 1024
    assert format_limit(0) == "Unlimited"
    with tempfile.NamedTemporaryFile(delete=False) as handle:
        handle.write(b"x" * 128 * 1024)
        path = handle.name
    try:
        limiter = BandwidthLimiter(256 * 1024)
        with open(path, "rb") as raw:
            reader = ThrottledReader(raw, limiter, threading.Event())
            assert len(reader.read()) == 128 * 1024
    finally:
        os.unlink(path)


def test_file_stability_queueing():
    sink = Sink()
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "growing.bin"
        watcher = FolderWatcher([sink], [], lambda *_: None, True, 0.2)
        path.write_bytes(b"first")
        watcher.on_created(type("Event", (), {"is_directory": False, "src_path": str(path)})())
        time.sleep(0.1)
        with path.open("ab") as handle:
            handle.write(b"second")
        assert sink.event.wait(2.0)
        assert sink.items == [str(path)]


if __name__ == "__main__":
    test_bandwidth_and_parsing()
    test_file_stability_queueing()
    print("core tests passed")
