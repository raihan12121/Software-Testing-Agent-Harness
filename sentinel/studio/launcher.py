"""Desktop Application Window Launcher for Atrocious Studio."""

from __future__ import annotations

import io
import sys
import threading
import time
import webbrowser
from pathlib import Path

import uvicorn

from sentinel.core.logging import logger
from sentinel.daemon.server import create_daemon_app


class SafeStream:
    """Fallback stream for PyInstaller windowed/noconsole apps where stdout/stderr is None."""

    def write(self, data: str) -> int:
        return len(data) if data else 0

    def flush(self) -> None:
        pass

    def isatty(self) -> bool:
        return False


# Guard streams for GUI mode
if sys.stdout is None:
    sys.stdout = SafeStream()
if sys.stderr is None:
    sys.stderr = SafeStream()
if sys.stdin is None:
    sys.stdin = io.StringIO()


def find_available_port(host: str = "127.0.0.1", start_port: int = 8765) -> int:
    """Find first available TCP port starting from start_port."""
    import socket
    for p in range(start_port, start_port + 25):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind((host, p))
                return p
        except OSError:
            continue
    return start_port


def launch_studio(
    host: str = "127.0.0.1",
    port: int = 8765,
    force_browser: bool = False,
    app_name: str = "Atrocious",
) -> None:
    """Launch Atrocious desktop window and local control daemon."""
    port = find_available_port(host, start_port=port)
    if getattr(sys, "frozen", False):
        base_dir = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
        static_dir = base_dir / "sentinel" / "studio" / "static"
        if not static_dir.exists():
            static_dir = Path(__file__).parent / "static"
    else:
        static_dir = Path(__file__).parent / "static"

    app = create_daemon_app(static_dir=static_dir)

    # 1. Start daemon in background thread with safe logging configuration
    server_config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="warning",
        log_config=None,  # Disables ColourizedFormatter which calls sys.stdout.isatty()
    )
    server = uvicorn.Server(server_config)

    daemon_thread = threading.Thread(target=server.run, daemon=True)
    daemon_thread.start()

    studio_url = f"http://{host}:{port}/"
    logger.info(f"{app_name} Studio Daemon running at {studio_url}")

    # Give server 0.5s to bind port
    time.sleep(0.5)

    # 2. Launch Native Desktop Window (via pywebview) or fallback to Browser
    if not force_browser:
        try:
            import webview

            logger.info(f"Opening {app_name} Studio in native desktop window...")
            window = webview.create_window(
                title=f"{app_name} — Autonomous QA Desktop",
                url=studio_url,
                width=1440,
                height=920,
                min_size=(1024, 680),
                background_color="#090d16",
            )
            webview.start(debug=False)
            return
        except Exception as exc:
            logger.warning(f"Native desktop window unavailable ({exc}); opening in system browser...")

    # 3. Browser fallback
    webbrowser.open(studio_url)
    try:
        while daemon_thread.is_alive():
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info(f"Stopping {app_name} Studio...")
