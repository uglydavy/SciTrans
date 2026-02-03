"""Structured logging configuration for SciTrans."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

PRODUCTION_FORMAT = "%(asctime)s %(levelname)s %(name)s [%(block_id)s] %(message)s"
DEBUG_FORMAT = "%(asctime)s %(levelname)s %(name)s [%(filename)s:%(lineno)d] [%(block_id)s] %(message)s"


class ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "block_id"):
            record.block_id = "-"
        return True


def setup_logging(
    level: str = "INFO",
    debug: bool = False,
    log_file: Path | None = None,
    *,
    force: bool = False,
):
    """Configure logging for SciTrans.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR)
        debug: If True, use detailed debug format
        log_file: Optional file to write logs to
    """
    log_level = getattr(logging, level.upper(), logging.INFO)
    log_format = DEBUG_FORMAT if debug else PRODUCTION_FORMAT

    root_logger = logging.getLogger()
    if root_logger.handlers and not force:
        root_logger.setLevel(log_level)
        return
    if force:
        for handler in list(root_logger.handlers):
            root_logger.removeHandler(handler)

    # Console handler
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(logging.Formatter(log_format))
    console_handler.addFilter(ContextFilter())
    root_logger.addHandler(console_handler)

    # File handler (optional)
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(log_level)
        file_handler.setFormatter(logging.Formatter(log_format))
        file_handler.addFilter(ContextFilter())
        root_logger.addHandler(file_handler)

    # Set library loggers to WARNING to reduce noise
    for lib in ["urllib3", "httpx", "httpcore", "anthropic", "openai", "fitz"]:
        logging.getLogger(lib).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Get a logger for a module.

    Usage:
        logger = get_logger(__name__)
        logger.debug("Parsing PDF...")
        logger.info("Translation complete")
        logger.warning("Cache miss")
        logger.error("API call failed")
    """
    return logging.getLogger(name)
