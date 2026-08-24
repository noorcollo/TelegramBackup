import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Keep the test isolated from any real user configuration.
os.environ["HOME"] = "/tmp/telegrambackup-test-home"
Path(os.environ["HOME"]).mkdir(parents=True, exist_ok=True)
config = Path(os.environ["HOME"]) / ".tgbackup_v3_config.json"
if config.exists():
    config.unlink()

from telegram_backup_v3 import App

app = App()
app.after(100, app.destroy)
app.mainloop()
print("GUI construction test passed")
