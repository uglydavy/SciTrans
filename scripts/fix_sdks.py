#!/usr/bin/env python3
"""
SDK Fix and Diagnostic Script for SciTrans.

This script:
1. Diagnoses all backend SDK issues
2. Provides installation instructions
3. Tests backend initialization
4. Reports comprehensive status
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from scitrans.utils.backend_checker import (  # noqa: E402
    get_all_backends_status,
)
from scitrans.utils.env_loader import load_environment_variables  # noqa: E402


def print_section(title: str):
    """Print a formatted section header."""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def print_status(backend: str, status: dict):
    """Print backend status in a readable format."""
    print(f"\n📦 {backend.upper()}")
    print(f"   Status: {status['health']}")

    if status["dependencies_ok"]:
        print("   ✅ Dependencies: OK")
    else:
        print("   ❌ Dependencies: MISSING")
        for dep in status["missing_dependencies"]:
            print(f"      - {dep}")

    if status["env_vars_ok"]:
        print("   ✅ Environment Variables: OK")
    else:
        print("   ⚠️  Environment Variables: MISSING")
        for var in status["missing_env_vars"]:
            print(f"      - {var}")

    if status["available"]:
        print("   ✅ Backend: Available and ready")
    elif status["error"]:
        print(f"   ❌ Error: {status['error']}")


def main():
    """Main diagnostic function."""
    print_section("SciTrans SDK Diagnostic & Fix Tool")

    # Load environment variables
    print("\n📋 Loading environment variables...")
    env_vars = load_environment_variables()
    if env_vars:
        print(f"   ✅ Loaded {len(env_vars)} environment variables")
    else:
        print("   ⚠️  No environment variables loaded (check setup_env.sh)")

    # Get status for all backends
    print_section("Backend Status Report")

    all_statuses = get_all_backends_status()

    # Categorize backends
    healthy = []
    missing_deps = []
    missing_env = []
    errors = []

    for backend, status in all_statuses.items():
        if status["available"] and status["health"] == "healthy":
            healthy.append(backend)
        elif not status["dependencies_ok"]:
            missing_deps.append(backend)
        elif not status["env_vars_ok"]:
            missing_env.append(backend)
        else:
            errors.append(backend)

        print_status(backend, status)

    # Summary
    print_section("Summary")

    print(f"\n✅ Healthy Backends ({len(healthy)}):")
    for backend in healthy:
        print(f"   - {backend}")

    if missing_deps:
        print(f"\n❌ Missing Dependencies ({len(missing_deps)}):")
        for backend in missing_deps:
            status = all_statuses[backend]
            print(f"   - {backend}: {', '.join(status['missing_dependencies'])}")

    if missing_env:
        print(f"\n⚠️  Missing API Keys ({len(missing_env)}):")
        for backend in missing_env:
            status = all_statuses[backend]
            print(f"   - {backend}: {', '.join(status['missing_env_vars'])}")

    if errors:
        print(f"\n❌ Errors ({len(errors)}):")
        for backend in errors:
            status = all_statuses[backend]
            print(f"   - {backend}: {status.get('error', 'Unknown error')}")

    # Installation instructions
    print_section("Installation Instructions")

    print("\nTo install all backend dependencies:")
    print("   pip install -e '.[backends]'")

    print("\nTo install specific backends:")
    print("   # OpenAI/DeepSeek (uses same SDK)")
    print("   pip install openai>=1.0.0")
    print("\n   # Anthropic")
    print("   pip install anthropic>=0.34.0")
    print("\n   # Google Translate (preferred)")
    print("   pip install deep-translator>=1.11.0")
    print("\n   # Ollama (local)")
    print("   pip install requests>=2.31.0")
    print("\n   # HuggingFace")
    print("   pip install huggingface-hub>=0.20.0")

    print("\n" + "=" * 70)

    # Return exit code
    if len(healthy) == 0:
        print("\n⚠️  WARNING: No backends are available!")
        return 1
    elif len(healthy) < len(all_statuses) / 2:
        print("\n⚠️  WARNING: Less than half of backends are available!")
        return 1
    else:
        print("\n✅ System is ready for translation!")
        return 0


if __name__ == "__main__":
    sys.exit(main())
