"""Adapter layer for target systems."""

from sentinel.adapters.api_adapter import APIAdapter
from sentinel.adapters.base import TargetAdapter, get_adapter, register_adapter
from sentinel.adapters.cli_adapter import CLIAdapter
from sentinel.adapters.stub import StubAdapter
from sentinel.adapters.web_adapter import WebAdapter

__all__ = ["TargetAdapter", "register_adapter", "get_adapter", "StubAdapter", "APIAdapter", "CLIAdapter", "WebAdapter"]
