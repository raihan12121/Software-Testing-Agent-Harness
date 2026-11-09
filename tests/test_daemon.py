"""Unit tests for Sentinel Studio Daemon and REST endpoints."""

from fastapi.testclient import TestClient

from sentinel.daemon.server import create_daemon_app


def test_daemon_rest_endpoints():
    app = create_daemon_app()
    client = TestClient(app)

    # Health check
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

    # Targets discovery
    resp = client.get("/api/targets")
    assert resp.status_code == 200
    assert "targets" in resp.json()

    # Vault status
    resp = client.get("/api/vault/status")
    assert resp.status_code == 200
    assert "status" in resp.json()

    # Save key
    resp = client.post("/api/vault/set", json={"provider": "ollama_url", "key": "http://localhost:11434"})
    assert resp.status_code == 200
    assert resp.json()["success"] is True

    # Start session in copilot mode
    resp = client.post(
        "/api/session/start",
        json={
            "target_type": "web",
            "target_url": "http://localhost:8899",
            "goal": "Verify copilot mode",
            "max_steps": 1,
            "mode": "copilot",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "started"
    assert resp.json()["mode"] == "copilot"

    # Submit copilot decision
    resp = client.post("/api/session/copilot-decision", json={"decision": "approve"})
    assert resp.status_code == 200
    assert resp.json()["decision"] == "approve"

    # Stop session
    resp = client.post("/api/session/stop")
    assert resp.status_code == 200
    assert resp.json()["status"] == "stopped"

    # Export session code
    resp = client.get("/api/session/export?format=yaml")
    assert resp.status_code == 200
    assert "format" in resp.json()
    assert resp.json()["format"] == "yaml"

    resp = client.get("/api/session/export?format=python")
    assert resp.status_code == 200
    assert resp.json()["format"] == "python"
