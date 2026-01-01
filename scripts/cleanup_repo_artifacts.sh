#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-.}"
cd "$ROOT"

echo "[cleanup] Removing IDE / cache / build artifacts from: $(pwd)"

rm -rf .idea .pytest_cache scitrans.egg-info build dist .ruff_cache .mypy_cache .coverage htmlcov || true

# Remove __pycache__ directories
find . -type d -name "__pycache__" -prune -exec rm -rf {} + || true

# Remove compiled Python files
find . -type f \( -name "*.pyc" -o -name "*.pyo" -o -name "*.pyd" \) -delete || true

# Remove editor swap files
find . -type f \( -name "*.swp" -o -name "*.swo" -o -name "*~" \) -delete || true

# Remove test outputs
rm -f test_input.pdf test_output*.pdf test.pdf test_out.pdf || true

echo "[cleanup] Done. Note: this script intentionally does NOT delete .venv/ by default."
echo "[cleanup] To also remove .venv/, run: rm -rf .venv"

