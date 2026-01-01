# Installation Guide

## Quick Install

SciTrans requires **Python 3.9 or higher**. 

### Option 1: Use Virtual Environment (Recommended)

```bash
# Create virtual environment with Python 3.9+
python3 -m venv .venv

# Activate virtual environment
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install package
pip install -U pip setuptools wheel
pip install -e ".[dev]"
```

**Important:** Always activate the virtual environment before using SciTrans:
```bash
source .venv/bin/activate
scitrans translate --help
```

### Option 2: Use System Python 3.9+

If your system Python is 3.9+, you can install directly:

```bash
pip install -e ".[dev]"
```

## Troubleshooting

### "Python: 3.9.15 not in '>=3.9'"

This error means you're using a Python version below 3.9. 

**Solution:** Use Python 3.9+:
```bash
# Check available Python versions
python3 --version
python3.9 --version
python3.10 --version
python3.11 --version
python3.12 --version
python3.13 --version

# Create venv with specific Python version
python3.13 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### "ModuleNotFoundError: No module named 'fitz'"

PyMuPDF needs to be installed:
```bash
pip install pymupdf
```

Or reinstall the package:
```bash
pip install -e ".[dev]"
```

### "pip install" uses wrong Python version

Your system may have multiple Python versions. Always use the venv:

```bash
# Activate venv first
source .venv/bin/activate

# Then install
pip install -e ".[dev]"

# Verify Python version
python --version  # Should show 3.9+
```

## Verify Installation

```bash
# Activate venv
source .venv/bin/activate

# Check CLI works
scitrans --help

# Check Python version
python --version
```

### "scitrans: command not found" or "ModuleNotFoundError: No module named 'scitrans'"

This means the package isn't installed or needs reinstallation after code changes.

**Solution 1: Reinstall the package**
```bash
source .venv/bin/activate
pip install -e ".[dev]"
# or use Make:
make reinstall
```

**Solution 2: Use the module directly (workaround)**
```bash
# Instead of: scitrans translate --in doc.pdf --out out.pdf
# Use:
python3 -m scitrans.cli.main translate --in doc.pdf --out out.pdf
```

**When to reinstall:**
- After pulling code changes
- After editing `pyproject.toml`
- After editing `scitrans/cli/main.py`
- When `scitrans` command stops working

