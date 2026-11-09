"""Atrocious Desktop Application Entry Point."""

from __future__ import annotations

import io
import os
import sys
import time
from pathlib import Path


class SafeStream:
    """Fallback stream for PyInstaller windowed/noconsole apps where stdout/stderr is None."""

    def __init__(self, log_path: Path | None = None) -> None:
        self.log_path = log_path
        self._log_file = None
        if log_path:
            try:
                log_path.parent.mkdir(parents=True, exist_ok=True)
                self._log_file = open(log_path, "a", encoding="utf-8")
            except Exception:
                pass

    def write(self, data: str) -> int:
        if self._log_file:
            try:
                self._log_file.write(data)
                self._log_file.flush()
            except Exception:
                pass
        return len(data) if data else 0

    def flush(self) -> None:
        if self._log_file:
            try:
                self._log_file.flush()
            except Exception:
                pass

    def isatty(self) -> bool:
        return False


# 1. Resolve safe streams before any logging or uvicorn imports
log_dir = Path(os.environ.get("LOCALAPPDATA", ".")) / "Atrocious" / "logs"
safe_out = SafeStream(log_dir / "atrocious_out.log")
safe_err = SafeStream(log_dir / "atrocious_err.log")

if sys.stdout is None:
    sys.stdout = safe_out
if sys.stderr is None:
    sys.stderr = safe_err
if sys.stdin is None:
    sys.stdin = io.StringIO()

# Ensure application root directory is in sys.path
root_dir = Path(__file__).resolve().parent.parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from sentinel.studio.launcher import launch_studio


def main() -> None:
    """Launch Atrocious Desktop Application."""
    try:
        launch_studio(host="127.0.0.1", port=8765, force_browser=False, app_name="Atrocious")
    except Exception as exc:
        import traceback
        log_dir.mkdir(parents=True, exist_ok=True)
        crash_log = log_dir / "crash.log"
        with open(crash_log, "a", encoding="utf-8") as f:
            f.write(f"\n--- CRASH AT {time.ctime()} ---\n")
            f.write(traceback.format_exc())
            f.write(f"Exception: {exc}\n")


if __name__ == "__main__":
    main()
