"""
Environment variable loader for SciTrans.

Loads API keys and configuration from setup_env.sh file.
"""

import logging
import os
import re
from pathlib import Path
from typing import Union

logger = logging.getLogger(__name__)


def load_env_vars(env_file: Union[str, Path] = "setup_env.sh") -> dict[str, str]:
    """
    Load environment variables from setup_env.sh (alias for load_environment_variables).
    """
    return load_environment_variables(env_file)


def load_environment_variables(env_file: Union[str, Path] = "setup_env.sh") -> dict[str, str]:
    """
    Load environment variables from a shell script file.

    Parses lines like:
        export DEEPSEEK_API_KEY="sk-..."
        export ANTHROPIC_BASE_URL="https://..."

    Args:
        env_file: Path to the environment file (default: setup_env.sh)

    Returns:
        Dictionary of loaded environment variables
    """
    env_file = Path(env_file)
    loaded_vars = {}

    if not env_file.exists():
        logger.warning(f"Environment file not found: {env_file}")
        return loaded_vars

    try:
        content = env_file.read_text(encoding="utf-8")

        # Parse export statements
        # Matches: export KEY="value" or export KEY='value' or export KEY=value
        pattern = r'export\s+([A-Z_][A-Z0-9_]*)\s*=\s*["\']?([^"\']+)["\']?'

        for line in content.split("\n"):
            line = line.strip()

            # Skip comments and empty lines
            if not line or line.startswith("#"):
                continue

            # Match export statement
            match = re.match(pattern, line)
            if match:
                key = match.group(1)
                value = match.group(2).strip().strip('"').strip("'")

                # Set in environment
                os.environ[key] = value
                loaded_vars[key] = value
                logger.debug(f"Loaded {key} from {env_file}")

        if loaded_vars:
            logger.info(f"Loaded {len(loaded_vars)} environment variables from {env_file}")
        else:
            logger.warning(f"No environment variables found in {env_file}")

    except Exception as e:
        logger.error(f"Error loading environment file {env_file}: {e}")

    return loaded_vars


def check_required_env_vars(required_vars: list[str]) -> tuple[bool, list[str]]:
    """
    Check if required environment variables are set.

    Args:
        required_vars: List of required variable names

    Returns:
        Tuple of (all_set, missing_vars)
    """
    missing = []

    for var in required_vars:
        if not os.getenv(var):
            missing.append(var)

    return len(missing) == 0, missing


def get_backend_env_vars(backend: str) -> list[str]:
    """
    Get required environment variables for a backend.

    Args:
        backend: Backend name (deepseek, anthropic, openai, etc.)

    Returns:
        List of required environment variable names
    """
    backend_vars = {
        "deepseek": ["DEEPSEEK_API_KEY"],
        "anthropic": ["ANTHROPIC_API_KEY"],
        "openai": ["OPENAI_API_KEY"],
        "google": [],  # googletrans doesn't need API key
        "huggingface": [],  # Can work without key (rate-limited)
        "ollama": [],  # Local, no API key
        "cascade_free": [],  # Uses other backends
        "dummy": [],  # No requirements
    }

    return backend_vars.get(backend, [])


def validate_backend_env(backend: str) -> tuple[bool, str]:
    """
    Validate that environment is set up for a backend.

    Args:
        backend: Backend name

    Returns:
        Tuple of (is_valid, error_message)
    """
    required_vars = get_backend_env_vars(backend)

    if not required_vars:
        return True, ""  # No requirements

    all_set, missing = check_required_env_vars(required_vars)

    if not all_set:
        error_msg = f"Missing environment variables for {backend}: {', '.join(missing)}"
        return False, error_msg

    return True, ""
