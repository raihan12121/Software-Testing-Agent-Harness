"""Sentinel Studio Desktop Control Daemon and WebSocket Protocol Server."""

from sentinel.daemon.server import create_daemon_app, run_daemon

__all__ = ["create_daemon_app", "run_daemon"]
