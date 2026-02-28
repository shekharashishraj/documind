"""Logging configuration helpers for demo UI and backend service wrappers."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def configure_demo_logging(log_path: str | Path = "logs/demo_web.log") -> logging.Logger:
    """Configure root logging for the demo app with rotating file + console handlers."""
    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # Prevent duplicate handlers on module reloads.
    existing_file = any(
        isinstance(handler, RotatingFileHandler) and getattr(handler, "baseFilename", "") == str(path.resolve())
        for handler in root_logger.handlers
    )
    existing_console = any(isinstance(handler, logging.StreamHandler) for handler in root_logger.handlers)

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    if not existing_file:
        file_handler = RotatingFileHandler(path, maxBytes=5_000_000, backupCount=3, encoding="utf-8")
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    if not existing_console:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

    logger = logging.getLogger("maldoc.demo")
    logger.info("Demo logging configured. log_path=%s", path)
    return logger
