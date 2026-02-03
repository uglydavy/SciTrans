"""
Backend dependency checker and health monitor.

Ported from SciTrans-LLMs_NEW with improvements.
Provides utilities to check backend availability, dependencies, and health status.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


# Backend dependency mapping
BACKEND_DEPENDENCIES: dict[str, list[tuple[str, str, str]]] = {
    "openai": [
        ("openai", "OpenAI API client", "pip install openai>=1.0.0"),
    ],
    "anthropic": [
        ("anthropic", "Anthropic API client", "pip install anthropic>=0.34.0"),
    ],
    "deepseek": [
        (
            "openai",
            "OpenAI-compatible API client (DeepSeek uses OpenAI SDK)",
            "pip install openai>=1.0.0",
        ),
    ],
    "ollama": [
        ("requests", "HTTP requests for Ollama", "pip install requests>=2.31.0"),
    ],
    "google": [
        (
            "deep_translator",
            "Google Translate library (preferred)",
            "pip install deep-translator>=1.11.0",
        ),
        # googletrans is optional fallback (has httpcore compatibility issues)
    ],
    "google_ai": [
        ("requests", "HTTP requests for Google AI", "pip install requests>=2.31.0"),
    ],
    "huggingface": [
        ("huggingface_hub", "HuggingFace Hub client", "pip install huggingface-hub>=0.20.0"),
    ],
    "cascade_free": [
        # Depends on at least one of the above
    ],
    "dummy": [
        # No dependencies
    ],
}


def check_dependency(module_name: str) -> tuple[bool, str | None]:
    """
    Check if a dependency is available.

    Args:
        module_name: Name of the module to check

    Returns:
        Tuple of (is_available, error_message)
    """
    try:
        # PHASE 5: Try importing and also check the module is functional
        mod = __import__(module_name)
        # Verify it's actually loaded
        if mod is None:
            return False, f"Module '{module_name}' import returned None"
        return True, None
    except ImportError as e:
        return False, f"Module '{module_name}' not found: {str(e)}"
    except Exception as e:
        # Catch other errors (e.g., module exists but has issues)
        return False, f"Module '{module_name}' error: {str(e)}"


def check_backend_dependencies(backend: str) -> tuple[bool, list[str]]:
    """
    Check if all dependencies for a backend are available.

    Args:
        backend: Backend name

    Returns:
        Tuple of (all_available, list_of_error_messages)
    """
    if backend not in BACKEND_DEPENDENCIES:
        logger.warning(f"Unknown backend: {backend}")
        return True, []  # Unknown backends assumed OK

    dependencies = BACKEND_DEPENDENCIES.get(backend, [])
    errors = []

    for dep_name, purpose, install_cmd in dependencies:
        available, error_msg = check_dependency(dep_name)
        if not available:
            error = f"{purpose}: {install_cmd}"
            errors.append(error)

    return len(errors) == 0, errors


def check_backend_env_vars(backend: str) -> tuple[bool, list[str]]:
    """
    Check if required environment variables are set for a backend.

    Args:
        backend: Backend name

    Returns:
        Tuple of (all_set, list_of_missing_vars)
    """
    from scitrans.translation.backends.config import get_backend_value

    backend_keys = {
        "deepseek": ("api_key", "DEEPSEEK_API_KEY"),
        "anthropic": ("api_key", "ANTHROPIC_API_KEY"),
        "openai": ("api_key", "OPENAI_API_KEY"),
        "google_ai": ("api_key", None),
    }

    if backend not in backend_keys:
        return True, []

    key_name, env_var = backend_keys[backend]
    value = get_backend_value(backend, key_name, env_var=env_var)
    if not value:
        return False, [f"{backend}.{key_name}"]
    return True, []


def get_backend_status(backend: str) -> dict[str, Any]:
    """
    Get comprehensive status for a backend.

    Args:
        backend: Backend name

    Returns:
        Status dictionary with availability, dependencies, env vars, health
    """
    status = {
        "backend": backend,
        "available": False,
        "dependencies_ok": False,
        "env_vars_ok": False,
        "missing_dependencies": [],
        "missing_env_vars": [],
        "health": "unknown",
        "error": None,
    }

    # Check dependencies
    deps_ok, dep_errors = check_backend_dependencies(backend)
    status["dependencies_ok"] = deps_ok
    status["missing_dependencies"] = dep_errors

    if not deps_ok:
        status["error"] = f"Missing dependencies: {dep_errors[0] if dep_errors else 'unknown'}"
        status["health"] = "missing_deps"
        return status

    # Check environment variables
    env_ok, missing_vars = check_backend_env_vars(backend)
    status["env_vars_ok"] = env_ok
    status["missing_env_vars"] = missing_vars

    if not env_ok:
        status["error"] = f"Missing environment variables: {', '.join(missing_vars)}"
        status["health"] = "missing_env"
        return status

    # Try to instantiate backend (health check)
    try:
        backend_instance = _try_create_backend(backend)
        if backend_instance:
            status["available"] = True
            status["health"] = "healthy"
        else:
            status["health"] = "unknown"
            status["error"] = "Could not instantiate backend"
    except Exception as e:
        status["error"] = str(e)
        status["health"] = "error"

    return status


def _try_create_backend(backend: str) -> Any | None:
    """Try to create a backend instance for health checking."""
    try:
        if backend == "openai":
            from scitrans.translation.backends.openai_backend import OpenAIBackend

            # Only try if API key is available
            from scitrans.translation.backends.config import get_backend_value
            if not get_backend_value("openai", "api_key", env_var="OPENAI_API_KEY"):
                return None
            return OpenAIBackend()
        elif backend == "anthropic":
            from scitrans.translation.backends.anthropic_backend import AnthropicBackend

            # Only try if API key is available
            from scitrans.translation.backends.config import get_backend_value
            if not get_backend_value("anthropic", "api_key", env_var="ANTHROPIC_API_KEY") and not get_backend_value(
                "anthropic", "auth_token", env_var="ANTHROPIC_AUTH_TOKEN"
            ):
                return None
            return AnthropicBackend()
        elif backend == "deepseek":
            from scitrans.translation.backends.deepseek_backend import DeepSeekBackend

            # Only try if API key is available
            from scitrans.translation.backends.config import get_backend_value
            if not get_backend_value("deepseek", "api_key", env_var="DEEPSEEK_API_KEY"):
                return None
            return DeepSeekBackend()
        elif backend == "google_ai":
            from scitrans.translation.backends.google_backend import GoogleAIBackend

            from scitrans.translation.backends.config import get_backend_value
            if not get_backend_value("google_ai", "api_key"):
                return None
            return GoogleAIBackend()
        elif backend == "ollama":
            from scitrans.translation.backends.ollama_backend import OllamaBackend

            return OllamaBackend()
        elif backend == "google":
            from scitrans.translation.backends.google_backend import GoogleTranslateBackend

            return GoogleTranslateBackend()
        elif backend == "huggingface":
            from scitrans.translation.backends.huggingface_backend import HuggingFaceBackend

            return HuggingFaceBackend()
        elif backend == "cascade_free":
            from scitrans.translation.backends.cascade_free import CascadeFreeBackend

            return CascadeFreeBackend()
        elif backend == "dummy":
            from scitrans.translation.backends.dummy import DummyBackend

            return DummyBackend()
    except ValueError as e:
        # ValueError usually means missing API key (already checked, but handle gracefully)
        logger.debug(f"Could not create {backend} instance (missing config): {e}")
        return None
    except ImportError as e:
        # ImportError means missing dependencies
        logger.debug(f"Could not create {backend} instance (missing dependencies): {e}")
        return None
    except Exception as e:
        # Other errors (network, invalid key, etc.) - backend exists but not working
        logger.debug(f"Could not create {backend} instance: {e}")
        return None

    return None


def get_all_backends_status() -> dict[str, dict[str, Any]]:
    """
    Get status for all backends.

    Returns:
        Dictionary mapping backend names to their status
    """
    all_backends = [
        "deepseek",
        "anthropic",
        "openai",
        "google",
        "google_ai",
        "huggingface",
        "ollama",
        "cascade_free",
        "dummy",
    ]
    statuses = {}

    for backend in all_backends:
        statuses[backend] = get_backend_status(backend)

    return statuses


def validate_backend_before_use(backend: str) -> tuple[bool, str]:
    """
    Validate that a backend is ready to use.

    Args:
        backend: Backend name

    Returns:
        Tuple of (is_valid, error_message)
    """
    status = get_backend_status(backend)

    if status["available"] and status["health"] == "healthy":
        return True, ""

    error_parts = []

    if status["missing_dependencies"]:
        error_parts.append(
            "Missing dependencies:\n  " + "\n  ".join(status["missing_dependencies"])
        )

    if status["missing_env_vars"]:
        error_parts.append(
            "Missing environment variables:\n  " + "\n  ".join(status["missing_env_vars"])
        )

    if status["error"]:
        error_parts.append(f"Error: {status['error']}")

    return False, "\n\n".join(error_parts)
