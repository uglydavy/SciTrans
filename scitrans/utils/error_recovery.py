"""
Error Recovery and Retry Utilities

Provides robust error handling and automatic recovery strategies.
"""

from __future__ import annotations

import logging
import time
from typing import Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


def retry_with_backoff(
    func: Callable[[], T],
    max_retries: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    retryable_exceptions: tuple[type[Exception], ...] = (Exception,),
) -> T | None:
    """
    Retry a function with exponential backoff.

    Args:
        func: Function to retry
        max_retries: Maximum number of retry attempts
        initial_delay: Initial delay in seconds
        max_delay: Maximum delay in seconds
        exponential_base: Base for exponential backoff
        retryable_exceptions: Tuple of exceptions that should trigger retry

    Returns:
        Function result or None if all retries failed
    """
    delay = initial_delay

    for attempt in range(max_retries + 1):
        try:
            return func()
        except retryable_exceptions as e:
            if attempt == max_retries:
                logger.error(f"Function failed after {max_retries} retries: {e}")
                return None

            logger.warning(
                f"Attempt {attempt + 1}/{max_retries + 1} failed: {e}. Retrying in {delay:.1f}s..."
            )
            time.sleep(delay)
            delay = min(delay * exponential_base, max_delay)

    return None


def graceful_degradation(
    primary_func: Callable[[], T],
    fallback_func: Callable[[], T],
    error_message: str = "Primary function failed, using fallback",
) -> T:
    """
    Try primary function, fall back to secondary if it fails.

    Args:
        primary_func: Primary function to try
        fallback_func: Fallback function if primary fails
        error_message: Message to log when falling back

    Returns:
        Result from primary or fallback function
    """
    try:
        return primary_func()
    except Exception as e:
        logger.warning(f"{error_message}: {e}")
        try:
            return fallback_func()
        except Exception as e2:
            logger.error(f"Fallback also failed: {e2}")
            raise


def safe_execute(
    func: Callable[[], T], default: T, error_message: str = "Function execution failed"
) -> T:
    """
    Execute function safely, returning default on error.

    Args:
        func: Function to execute
        default: Default value to return on error
        error_message: Message to log on error

    Returns:
        Function result or default value
    """
    try:
        return func()
    except Exception as e:
        logger.error(f"{error_message}: {e}")
        return default
