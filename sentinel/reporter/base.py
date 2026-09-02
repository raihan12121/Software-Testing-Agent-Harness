"""Reporter Protocol and Registry."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from sentinel.core.schemas import Report


@runtime_checkable
class Reporter(Protocol):
    """Protocol for test report formatters and publishers."""

    def generate_report(self, report: Report, output_dir: Path) -> Path:
        """Format and write report to output directory, returning the created report path."""
        ...


_REPORTER_REGISTRY: dict[str, type[Reporter]] = {}


def register_reporter(format_name: str, reporter_cls: type[Reporter]) -> None:
    """Register a reporter class for a format name."""
    _REPORTER_REGISTRY[format_name.lower()] = reporter_cls


def get_reporter(format_name: str) -> Reporter:
    """Retrieve an instantiated reporter for the specified format."""
    key = format_name.lower()
    if key not in _REPORTER_REGISTRY:
        available = list(_REPORTER_REGISTRY.keys())
        raise ValueError(f"No reporter registered for format '{format_name}'. Available: {available}")
    return _REPORTER_REGISTRY[key]()
