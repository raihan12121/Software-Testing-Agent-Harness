"""Adapter layer for target systems."""

from sentinel.adapters.api_adapter import APIAdapter
from sentinel.adapters.base import TargetAdapter, get_adapter, register_adapter
from sentinel.adapters.stub import StubAdapter

__all__ = ["TargetAdapter", "register_adapter", "get_adapter", "StubAdapter", "APIAdapter"]
