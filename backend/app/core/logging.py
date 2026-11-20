"""Structured logging setup with console and rotating file output."""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_logging(log_level: str = "INFO", log_dir: Path | None = None) -> logging.Logger:
    """Configure root and `jarvis` loggers with console and rotating file handlers."""
    level = getattr(logging, log_level.upper(), logging.INFO)
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    jarvis_logger = logging.getLogger("jarvis")
    jarvis_logger.setLevel(level)
    jarvis_logger.handlers.clear()
    jarvis_logger.propagate = False

    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    jarvis_logger.addHandler(console_handler)

    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            filename=log_dir / "jarvis.log",
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        jarvis_logger.addHandler(file_handler)

    return jarvis_logger


def get_logger(name: str) -> logging.Logger:
    """Return a child logger under the `jarvis` namespace."""
    return logging.getLogger(f"jarvis.{name}")
