"""Unit tests for Sentinel Studio Desktop UI and Launcher integration."""

from pathlib import Path
from fastapi.testclient import TestClient

from sentinel.daemon.server import create_daemon_app
from sentinel.studio.launcher import launch_studio


def test_studio_static_assets_exist():
    static_dir = Path(__file__).parent.parent / "sentinel" / "studio" / "static"
    assert static_dir.exists()
    index_file = static_dir / "index.html"
    assert index_file.exists()
    content = index_file.read_text(encoding="utf-8")
    assert "Atrocious Studio" in content
    assert "thought-stream" in content
    assert "viewport-canvas" in content
    assert "modal-vault" in content


def test_daemon_serves_studio_ui():
    static_dir = Path(__file__).parent.parent / "sentinel" / "studio" / "static"
    app = create_daemon_app(static_dir=static_dir)
    client = TestClient(app)

    resp = client.get("/")
    assert resp.status_code == 200
    assert "Atrocious Studio" in resp.text
