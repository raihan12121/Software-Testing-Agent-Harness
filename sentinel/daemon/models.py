"""Pydantic schemas for Sentinel Studio WebSocket & REST Protocol."""

from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field


class DaemonClientMessage(BaseModel):
    """Message sent from Desktop UI to Daemon."""
    type: Literal[
        "start_session",
        "pause_session",
        "resume_session",
        "stop_session",
        "manual_action",
        "add_assertion",
        "ping",
    ]
    target_type: str = "web"
    target_url: str | None = None
    goal: str | None = None
    max_steps: int = 15
    action: dict[str, Any] = Field(default_factory=dict)
    assertion: str | None = None


class DaemonServerEvent(BaseModel):
    """Real-time event pushed from Daemon to Desktop UI."""
    type: str
    timestamp: float
    data: dict[str, Any] = Field(default_factory=dict)
