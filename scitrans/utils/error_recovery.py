"""
Error Recovery and Retry Utilities

Provides robust error handling and automatic recovery strategies for translation backends.
"""

from __future__ import annotations

import logging
import time
from typing import Callable, TypeVar, Optional

logger = logging.getLogger(__name__)

T = TypeVar("T")


def retry_with_backoff(
    func: Callable[[], T],
    max_retries: int = 3,
    initial_delay: float = 1.0,
    backoff_factor: float = 2.0,
    max_delay: float = 60.0,
    exceptions: tuple[type[Exception], ...] = (Exception,),
    on_retry: Optional[Callable[[int, Exception], None]] = None,
) -> T:
    """
    Retry a function with exponential backoff.

    Args:
        func: Function to retry (no arguments)
        max_retries: Maximum number of retry attempts
        initial_delay: Initial delay in seconds
        backoff_factor: Multiplier for delay after each retry
        max_delay: Maximum delay between retries
        exceptions: Tuple of exceptions to catch and retry on
        on_retry: Optional callback called on each retry (attempt_num, exception)

    Returns:
        Result of func() if successful

    Raises:
        Last exception if all retries fail
    """
    delay = initial_delay
    last_exception = None

    for attempt in range(max_retries + 1):
        try:
            return func()
        except exceptions as e:
            last_exception = e
            if attempt < max_retries:
                if on_retry:
                    on_retry(attempt + 1, e)
                logger.warning(
                    f"Attempt {attempt + 1}/{max_retries + 1} failed: {e}. "
                    f"Retrying in {delay:.1f}s..."
                )
                time.sleep(delay)
                delay = min(delay * backoff_factor, max_delay)
            else:
                logger.error(f"All {max_retries + 1} attempts failed. Last error: {e}")

    if last_exception:
        raise last_exception
    raise RuntimeError("Retry failed but no exception was raised")


def retry_with_circuit_breaker(
    func: Callable[[], T],
    failure_threshold: int = 5,
    recovery_timeout: float = 60.0,
    exceptions: tuple[type[Exception], ...] = (Exception,),
) -> T:
    """
    Retry with circuit breaker pattern.

    Opens circuit after failure_threshold failures, then tries again after recovery_timeout.

    Args:
        func: Function to retry
        failure_threshold: Number of failures before opening circuit
        recovery_timeout: Seconds to wait before trying again after circuit opens
        exceptions: Exceptions to count as failures

    Returns:
        Result of func() if successful

    Raises:
        Last exception if circuit is open or all retries fail
    """
    # Simple in-memory circuit breaker (for production, use Redis or similar)
    if not hasattr(retry_with_circuit_breaker, "_circuit_state"):
        retry_with_circuit_breaker._circuit_state = {
            "failures": 0,
            "last_failure_time": 0.0,
            "circuit_open": False,
        }

    state = retry_with_circuit_breaker._circuit_state

    # Check if circuit is open
    if state["circuit_open"]:
        time_since_failure = time.time() - state["last_failure_time"]
        if time_since_failure < recovery_timeout:
            raise RuntimeError(
                f"Circuit breaker is OPEN. Too many failures. "
                f"Try again in {recovery_timeout - time_since_failure:.1f}s"
            )
        else:
            # Circuit can be closed, reset state
            logger.info("Circuit breaker: Attempting recovery...")
            state["circuit_open"] = False
            state["failures"] = 0

    try:
        result = func()
        # Success - reset failure count
        state["failures"] = 0
        return result
    except exceptions as e:
        state["failures"] += 1
        state["last_failure_time"] = time.time()

        if state["failures"] >= failure_threshold:
            state["circuit_open"] = True
            logger.error(
                f"Circuit breaker OPENED after {state['failures']} failures. "
                f"Will retry after {recovery_timeout}s"
            )

        raise


def safe_call(
    func: Callable[[], T],
    default: T,
    exceptions: tuple[type[Exception], ...] = (Exception,),
    log_error: bool = True,
) -> T:
    """
    Safely call a function, returning a default value on exception.

    Args:
        func: Function to call
        default: Value to return on exception
        exceptions: Exceptions to catch
        log_error: Whether to log errors

    Returns:
        Result of func() or default on exception
    """
    try:
        return func()
    except exceptions as e:
        if log_error:
            logger.error(f"Safe call failed: {e}", exc_info=True)
        return default

