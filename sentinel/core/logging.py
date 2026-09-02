"""Structured logging with automated secrets redaction.

Adheres to:
- rules.md R-SEC-1 (No secrets in logs)
- rules.md R-SEC-3 (Redaction before storage)
"""

from __future__ import annotations

import logging
import sys

from rich.console import Console

from sentinel.core.redaction import RedactionFilter, default_redactor


class RedactingFormatter(logging.Formatter):
    """Logging formatter that automatically applies the redaction filter."""

    def __init__(self, fmt: str | None = None, datefmt: str | None = None, redactor: RedactionFilter | None = None) -> None:
        super().__init__(fmt=fmt, datefmt=datefmt)
        self.redactor = redactor or default_redactor

    def format(self, record: logging.LogRecord) -> str:
        formatted = super().format(record)
        return self.redactor.redact_text(formatted)


def setup_logger(
    name: str = "sentinel",
    level: int = logging.INFO,
    redactor: RedactionFilter | None = None,
) -> logging.Logger:
    """Configure and return a structured logger with redaction."""
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Avoid duplicate handlers if already configured
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(level)
        formatter = RedactingFormatter(
            fmt="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
            redactor=redactor,
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger


logger = setup_logger()
console = Console()
