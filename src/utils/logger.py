"""
utils/logger.py
===============
Project-wide structured logger factory for Quantum-Inspired Cyber Threat
Detection (SIH26141).

All modules obtain their logger via ``get_logger(__name__)`` rather than
calling ``logging.getLogger`` directly, so the root handler is configured
exactly once and consistently.

No AI/ML libraries are used in this project.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Optional

from config.settings import (
    LOG_DATE_FORMAT,
    LOG_FORMAT,
    LOG_LEVEL,
    LOG_TO_FILE,
    LOG_FILE,
    LOGS_DIR,
)

_HANDLER_CONFIGURED: bool = False


def _configure_root_handler(
    level: str = LOG_LEVEL,
    fmt: str = LOG_FORMAT,
    date_fmt: str = LOG_DATE_FORMAT,
    log_to_file: bool = LOG_TO_FILE,
    log_file: Path = LOG_FILE,
) -> None:
    """Configure the root logger's handlers once.

    Subsequent calls are no-ops (guarded by ``_HANDLER_CONFIGURED``).

    Parameters
    ----------
    level:
        Logging level string, e.g. ``'INFO'``.
    fmt:
        ``logging.Formatter`` format string.
    date_fmt:
        Datetime format string for log records.
    log_to_file:
        When ``True``, also write logs to *log_file*.
    log_file:
        Destination path for file-based logging.
    """
    global _HANDLER_CONFIGURED
    if _HANDLER_CONFIGURED:
        return

    root = logging.getLogger()
    root.setLevel(getattr(logging, level, logging.INFO))

    formatter = logging.Formatter(fmt=fmt, datefmt=date_fmt)

    # Console handler — always enabled
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root.addHandler(console_handler)

    # File handler — optional
    if log_to_file:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)

    _HANDLER_CONFIGURED = True


def get_logger(
    name: str,
    level: Optional[str] = None,
) -> logging.Logger:
    """Return a named logger, initialising root handlers on first call.

    Parameters
    ----------
    name:
        Logger name — pass ``__name__`` from the calling module.
    level:
        Override the logger's level (defaults to root level from config).

    Returns
    -------
    logging.Logger
        Configured logger instance.

    Examples
    --------
    >>> log = get_logger(__name__)
    >>> log.info("Phase 0 initialised")
    """
    _configure_root_handler()
    log = logging.getLogger(name)
    if level is not None:
        log.setLevel(getattr(logging, level.upper(), logging.INFO))
    return log
