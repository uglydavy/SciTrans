"""Structured logging configuration for SciTrans."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# Default format for production
PRODUCTION_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

# Detailed format for debugging
DEBUG_FORMAT = "%(asctime)s - %(name)s - [%(filename)s:%(lineno)d] - %(levelname)s - %(message)s"


def setup_logging(level: str = "INFO", debug: bool = False, log_file: Path | None = None):
    """Configure logging for SciTrans.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR)
        debug: If True, use detailed debug format
        log_file: Optional file to write logs to
    """
    log_level = getattr(logging, level.upper(), logging.INFO)
    log_format = DEBUG_FORMAT if debug else PRODUCTION_FORMAT

    # Configure root logger
    logging.basicConfig(
        level=log_level,
        format=log_format,
        handlers=[],  # Clear default handlers
    )

    # Console handler
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(logging.Formatter(log_format))
    logging.getLogger().addHandler(console_handler)

    # File handler (optional)
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(log_level)
        file_handler.setFormatter(logging.Formatter(log_format))
        logging.getLogger().addHandler(file_handler)

    # Set library loggers to WARNING to reduce noise
    for lib in ["urllib3", "httpx", "httpcore", "anthropic", "openai"]:
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
