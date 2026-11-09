"""Sentinel Studio Daemon Server (FastAPI + WebSockets).

Provides live viewport streaming, agent chain-of-thought broadcasting,
interactive manual control, and API key management.
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from sentinel.computer_use.agent import ComputerUseQAAgent
from sentinel.computer_use.som import SetOfMarksAnnotator
from sentinel.core.config import TargetConfig
from sentinel.core.logging import logger
from sentinel.scanner import ProjectScanner
from sentinel.vault.manager import get_vault


class KeyUpdateRequest(BaseModel):
    provider: str
    key: str


class SessionStartRequest(BaseModel):
    target_type: str = "web"
    target_url: str = "http://localhost:3000"
    goal: str = "Explore application and uncover defects"
    max_steps: int = 15
    mode: str = "autonomous"  # "autonomous" or "copilot"


class CopilotDecisionRequest(BaseModel):
    decision: str = "approve"  # approve, edit, skip
    action: dict[str, Any] | None = None


class NavigateRequest(BaseModel):
    url: str


class ConnectionManager:
    """Manages active WebSocket clients for Sentinel Studio desktop."""

    def __init__(self) -> None:
        self.active_connections: list[WebSocket] = []
        self._loop: asyncio.AbstractEventLoop | None = None

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict[str, Any]) -> None:
        data_str = json.dumps(message)
        for conn in list(self.active_connections):
            try:
                await conn.send_text(data_str)
            except Exception:
                self.disconnect(conn)

    def threadsafe_broadcast(self, message: dict[str, Any]) -> None:
        """Publish event from worker thread to WebSocket clients."""
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(self.broadcast(message), self._loop)


def create_daemon_app(static_dir: Path | None = None) -> FastAPI:
    """Instantiate Sentinel Studio FastAPI and WebSocket daemon application."""
    app = FastAPI(title="Sentinel Studio Daemon", version="1.0.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    ws_manager = ConnectionManager()
    active_agent: dict[str, ComputerUseQAAgent | None] = {"agent": None}
    agent_thread: dict[str, threading.Thread | None] = {"thread": None}

    @app.get("/health")
    def health_check() -> dict[str, str]:
        return {"status": "ok", "service": "atrocious-studio-daemon"}

    # --- Target Discovery ---
    @app.get("/api/targets")
    def discover_workspace_targets() -> dict[str, Any]:
        """Automatically scan workspace for targets."""
        scanner = ProjectScanner(Path.cwd())
        targets = scanner.scan()
        return {
            "targets": [
                {
                    "name": t.name,
                    "target_type": t.target_type,
                    "target_path": t.target_path,
                    "description": t.description,
                }
                for t in targets
            ]
        }

    # --- API Key Vault Management ---
    @app.get("/api/vault/status")
    def get_vault_status() -> dict[str, Any]:
        vault = get_vault()
        return {"status": vault.get_all_status()}

    @app.post("/api/vault/set")
    def set_vault_key(req: KeyUpdateRequest) -> dict[str, Any]:
        vault = get_vault()
        vault.set_key(req.provider, req.key)
        return {"success": True, "message": f"Key saved for {req.provider}."}

    @app.post("/api/vault/test")
    def test_vault_key(req: KeyUpdateRequest) -> dict[str, Any]:
        vault = get_vault()
        if req.key:
            vault.set_key(req.provider, req.key)
        success, msg = vault.test_connection(req.provider)
        return {"success": success, "message": msg}

    def _get_or_create_agent(target_url: str = "") -> ComputerUseQAAgent:
        if not active_agent["agent"]:
            target_cfg = TargetConfig(
                target_type="web",
                name="studio-target",
                base_url=target_url or "about:blank",
                allowed_hosts=["localhost", "127.0.0.1", "0.0.0.0", "*"],
            )
            active_agent["agent"] = ComputerUseQAAgent(
                target_config=target_cfg,
                goal="Interactive QA Session",
                event_callback=ws_manager.threadsafe_broadcast,
            )
        return active_agent["agent"]

    # --- Session & Autonomous Control ---
    @app.post("/api/session/start")
    def start_session(req: SessionStartRequest) -> dict[str, Any]:
        if active_agent["agent"]:
            active_agent["agent"].stop()

        target_cfg = TargetConfig(
            target_type=req.target_type,
            name="studio-target",
            base_url=req.target_url,
            allowed_hosts=["localhost", "127.0.0.1", "0.0.0.0", "*"],
        )

        agent = ComputerUseQAAgent(
            target_config=target_cfg,
            goal=req.goal,
            event_callback=ws_manager.threadsafe_broadcast,
            mode=req.mode,
        )
        active_agent["agent"] = agent

        # Run autonomous loop in background thread
        def _run_worker():
            try:
                agent.run_autonomous(max_steps=req.max_steps)
            except Exception as exc:
                logger.error(f"Agent worker error: {exc}")

        th = threading.Thread(target=_run_worker, daemon=True)
        th.start()
        agent_thread["thread"] = th

        return {"status": "started", "goal": req.goal, "mode": req.mode}

    @app.post("/api/session/pause")
    def pause_session() -> dict[str, Any]:
        if active_agent["agent"]:
            active_agent["agent"].pause()
            return {"status": "paused"}
        raise HTTPException(status_code=400, detail="No active session.")

    @app.post("/api/session/resume")
    def resume_session() -> dict[str, Any]:
        if active_agent["agent"]:
            active_agent["agent"].resume()
            return {"status": "resumed"}
        raise HTTPException(status_code=400, detail="No active session.")

    @app.post("/api/session/stop")
    def stop_session() -> dict[str, Any]:
        if active_agent["agent"]:
            active_agent["agent"].stop()
            return {"status": "stopped"}
        return {"status": "idle"}

    @app.post("/api/session/navigate")
    def navigate_target(req: NavigateRequest) -> dict[str, Any]:
        agent = _get_or_create_agent(req.url)
        agent.execute_single_action({"action": "navigate", "value": req.url}, [])
        viewport_data = agent.capture_viewport()
        return {"status": "ok", "url": req.url, "viewport": viewport_data}

    @app.post("/api/session/copilot-decision")
    def submit_copilot_decision(req: CopilotDecisionRequest) -> dict[str, Any]:
        if active_agent["agent"]:
            active_agent["agent"].submit_copilot_decision(req.decision, req.action)
            return {"status": "ok", "decision": req.decision}
        raise HTTPException(status_code=400, detail="No active session.")

    @app.get("/api/session/export")
    def export_session_code(format: str = "yaml") -> dict[str, Any]:
        if not active_agent["agent"]:
            raise HTTPException(status_code=400, detail="No active session to export.")

        recorder = active_agent["agent"].recorder
        if format.lower() == "python":
            code = recorder.export_playwright_python()
            return {"format": "python", "code": code}
        else:
            code = recorder.export_yaml()
            return {"format": "yaml", "code": code}

    # --- WebSocket Real-Time Stream ---
    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        ws_manager.set_loop(asyncio.get_event_loop())
        await ws_manager.connect(websocket)

        # Send welcome and current vault status on connection
        vault = get_vault()
        await websocket.send_text(json.dumps({
            "type": "connected",
            "timestamp": time.time(),
            "data": {
                "message": "Connected to Atrocious Studio Daemon",
                "vault_status": vault.get_all_status(),
            }
        }))

        try:
            while True:
                msg_text = await websocket.receive_text()
                try:
                    payload = json.loads(msg_text)
                    msg_type = payload.get("type")

                    if msg_type == "manual_action":
                        # Interactive user action from canvas/toolbar (click, type, navigate, press)
                        action_data = payload.get("action", {})
                        agent = _get_or_create_agent()
                        page = agent.adapter._ensure_browser()
                        _, elements = SetOfMarksAnnotator.annotate_playwright_page(page, capture_screenshot=False)
                        agent.execute_single_action(action_data, elements)
                        agent.capture_viewport()

                    elif msg_type == "navigate":
                        url = payload.get("url")
                        if url:
                            agent = _get_or_create_agent(url)
                            agent.execute_single_action({"action": "navigate", "value": url}, [])
                            agent.capture_viewport()

                    elif msg_type == "refresh_viewport":
                        agent = _get_or_create_agent()
                        agent.capture_viewport()

                    elif msg_type == "copilot_decision":
                        decision = payload.get("decision", "approve")
                        action = payload.get("action")
                        if active_agent["agent"]:
                            active_agent["agent"].submit_copilot_decision(decision, action)

                    elif msg_type == "add_assertion":
                        assertion = payload.get("assertion")
                        agent = _get_or_create_agent()
                        if assertion:
                            agent.recorder.add_assertion(assertion)
                            await ws_manager.broadcast({
                                "type": "assertion_added",
                                "timestamp": time.time(),
                                "data": {"assertion": assertion},
                            })

                    elif msg_type == "ping":
                        await websocket.send_text(json.dumps({"type": "pong", "timestamp": time.time()}))

                except Exception as exc:
                    logger.warning(f"WebSocket incoming message processing error: {exc}")

        except WebSocketDisconnect:
            ws_manager.disconnect(websocket)

    # Optional static file serving for Desktop UI build
    if static_dir and static_dir.exists():
        assets_dir = static_dir / "assets"
        if assets_dir.exists():
            app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

        @app.get("/{full_path:path}")
        def serve_spa(full_path: str):
            index_file = static_dir / "index.html"
            if index_file.exists():
                return FileResponse(index_file)
            return {"message": "Sentinel Studio UI static build"}

    return app


def run_daemon(host: str = "127.0.0.1", port: int = 8765, static_dir: Path | None = None) -> None:
    """Run uvicorn server for Sentinel Studio daemon."""
    app = create_daemon_app(static_dir=static_dir)
    uvicorn.run(app, host=host, port=port, log_level="info")
