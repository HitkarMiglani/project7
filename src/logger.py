"""
src/logger.py
Centralized logging configuration for KnapResume.
Provides a console handler (with optional file output) so every module
logs through one consistent formatter and level.

Configuration:
  - KNAP_LOG_LEVEL: "DEBUG" | "INFO" | "WARNING" | "ERROR" (default: INFO)
  - KNAP_LOG_FILE:   path to append logs; if unset, logs go to console only.
"""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

_LOGGER_NAME = "knapresume"
_DEFAULT_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
_DEFAULT_DATE = "%Y-%m-%d %H:%M:%S"
_MAX_BYTES = 2 * 1024 * 1024  # 2MB per file
_BACKUP_COUNT = 3

_configured = False


def _level_from_env() -> int:
    level = os.environ.get("KNAP_LOG_LEVEL", "INFO").upper()
    return getattr(logging, level, logging.INFO)


def configure_logging() -> logging.Logger:
    """
    Idempotently configure the root KnapResume logger.

    Returns:
        The shared application logger.
    """
    global _configured
    logger = logging.getLogger(_LOGGER_NAME)

    if _configured:
        return logger

    logger.setLevel(_level_from_env())
    logger.propagate = False

    formatter = logging.Formatter(_DEFAULT_FORMAT, datefmt=_DEFAULT_DATE)

    console = logging.StreamHandler(stream=sys.stdout)
    console.setFormatter(formatter)
    logger.addHandler(console)

    log_file = os.environ.get("KNAP_LOG_FILE", "")
    if log_file:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=_MAX_BYTES,
            backupCount=_BACKUP_COUNT,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    _configured = True
    return logger


def get_logger(name: str = "") -> logging.Logger:
    """
    Return a child logger under the shared 'knapresume' namespace.

    Args:
        name: Sub-namespace, e.g. "app", "tailor", "database".

    Returns:
        A child logger that inherits the shared handlers/level.
    """
    configure_logging()
    if name:
        return logging.getLogger(f"{_LOGGER_NAME}.{name}")
    return logging.getLogger(_LOGGER_NAME)