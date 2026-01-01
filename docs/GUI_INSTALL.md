# Installing the Enhanced SciTrans GUI

## Quick Install (Recommended)

```bash
# Install SciTrans with all GUI dependencies
pip install -e ".[gui]"
```

This installs:
- ✅ Gradio (web interface)
- ✅ Requests (URL fetching)
- ✅ PyMuPDF (PDF preview)
- ✅ Matplotlib (visualizations)
- ✅ Pillow (image handling)
- ✅ NumPy (data processing)

---

## Manual Installation

If you prefer to install dependencies individually:

```bash
# Core requirement
pip install gradio

# Optional but recommended
pip install requests      # For URL fetching
pip install PyMuPDF       # For PDF preview
pip install matplotlib    # For ablation visualizations
pip install Pillow        # For image handling
pip install numpy         # For data processing
```

---

## Verifying Installation

```bash
# Test if GUI dependencies are installed
python3 -c "import gradio; print(f'✅ Gradio {gradio.__version__} installed')"
python3 -c "import requests; print('✅ Requests installed')"
python3 -c "import fitz; print('✅ PyMuPDF installed')"
python3 -c "import matplotlib; print('✅ Matplotlib installed')"
python3 -c "from PIL import Image; print('✅ Pillow installed')"
```

---

## Launching the GUI

### Method 1: Using scitrans command
```bash
scitrans gui
```

### Method 2: Using Python module
```bash
python3 -m scitrans.cli.main gui
```

### Method 3: Direct execution
```bash
python3 -m scitrans.gui.app
```

### With Options
```bash
# Share publicly (creates temporary public URL)
scitrans gui --share

# Custom port
scitrans gui --port 8080

# Both
scitrans gui --share --port 8080
```

---

## Feature Availability by Dependency

| Feature | Requires | What Happens Without It |
|---------|----------|------------------------|
| Basic GUI | gradio | ❌ GUI won't start |
| URL Fetching | requests | ⚠️ URL input disabled |
| PDF Preview | PyMuPDF | ⚠️ No preview shown |
| Ablation Charts | matplotlib | ⚠️ No visualizations |
| Image Display | Pillow | ⚠️ Preview may fail |
| Data Processing | numpy | ⚠️ Charts may fail |

**Recommendation:** Install all dependencies for full functionality:
```bash
pip install -e ".[gui]"
```

---

## Troubleshooting

### Issue: `ModuleNotFoundError: No module named 'gradio'`

**Solution:**
```bash
pip install gradio
# Or: pip install -e ".[gui]"
```

### Issue: URL fetching doesn't work

**Solution:**
```bash
pip install requests
```

### Issue: PDF preview is blank

**Solution:**
```bash
pip install PyMuPDF
```

### Issue: Ablation charts don't appear

**Solution:**
```bash
pip install matplotlib numpy
```

### Issue: `scitrans` command not found

**Solution 1 - Reinstall:**
```bash
pip install -e ".[gui]"
```

**Solution 2 - Use Python module:**
```bash
python3 -m scitrans.cli.main gui
```

### Issue: GUI starts but crashes on translation

**Check:**
1. Backend API keys are set (Settings tab)
2. PDF is valid
3. Check System Logs tab for errors

---

## Platform-Specific Notes

### macOS
```bash
# If using Homebrew Python
/usr/local/bin/python3 -m pip install -e ".[gui]"

# If PyMuPDF fails to install
brew install mupdf
pip install PyMuPDF
```

### Linux (Ubuntu/Debian)
```bash
# Install system dependencies
sudo apt-get update
sudo apt-get install -y python3-pip python3-dev

# Install GUI dependencies
pip3 install -e ".[gui]"
```

### Windows
```bash
# Use PowerShell or Command Prompt
python -m pip install -e ".[gui]"

# If PyMuPDF fails
pip install --upgrade pip setuptools wheel
pip install PyMuPDF
```

---

## Virtual Environment (Recommended)

```bash
# Create virtual environment
python3 -m venv .venv

# Activate (macOS/Linux)
source .venv/bin/activate

# Activate (Windows)
.venv\Scripts\activate

# Install SciTrans with GUI
pip install -e ".[gui]"

# Launch GUI
scitrans gui
```

---

## Docker Installation (Coming Soon)

```bash
# Future feature
docker pull scitrans/gui:latest
docker run -p 7860:7860 scitrans/gui:latest
```

---

## Checking Versions

```bash
# Check all versions
python3 << EOF
import sys
print(f"Python: {sys.version}")

try:
    import gradio
    print(f"✅ Gradio: {gradio.__version__}")
except ImportError:
    print("❌ Gradio: Not installed")

try:
    import requests
    print(f"✅ Requests: {requests.__version__}")
except ImportError:
    print("⚠️ Requests: Not installed (optional)")

try:
    import fitz
    print(f"✅ PyMuPDF: {fitz.version[0]}")
except ImportError:
    print("⚠️ PyMuPDF: Not installed (optional)")

try:
    import matplotlib
    print(f"✅ Matplotlib: {matplotlib.__version__}")
except ImportError:
    print("⚠️ Matplotlib: Not installed (optional)")

try:
    from PIL import Image
    import PIL
    print(f"✅ Pillow: {PIL.__version__}")
except ImportError:
    print("⚠️ Pillow: Not installed (optional)")

try:
    import numpy
    print(f"✅ NumPy: {numpy.__version__}")
except ImportError:
    print("⚠️ NumPy: Not installed (optional)")
EOF
```

---

## Updating Dependencies

```bash
# Update all dependencies to latest versions
pip install --upgrade gradio requests PyMuPDF matplotlib Pillow numpy

# Or update SciTrans installation
pip install --upgrade -e ".[gui]"
```

---

## Uninstalling

```bash
# Uninstall SciTrans
pip uninstall scitrans

# Remove virtual environment (if used)
rm -rf .venv
```

---

## Development Installation

For development with additional tools:

```bash
# Install with development dependencies
pip install -e ".[dev,gui]"

# This includes:
# - GUI dependencies
# - pytest (testing)
# - ruff (linting)
# - mypy (type checking)
# - black (formatting)
```

---

## Performance Tips

### Faster Startup
```bash
# Pre-compile Python files
python3 -m compileall scitrans/

# Use faster backend for testing
export SCITRANS_DEFAULT_BACKEND=dummy
```

### Reduced Memory Usage
```bash
# Disable matplotlib GUI backend
export MPLBACKEND=Agg

# Run with limited memory (if needed)
python3 -Xdev -m scitrans.gui.app
```

---

## Network Configuration

### Local Network Access
```bash
# Allow access from other devices on your network
scitrans gui --share
# Creates temporary public URL (via Gradio)
```

### Custom Port
```bash
# If port 7860 is already in use
scitrans gui --port 8080
```

### Behind Proxy
```bash
# Set proxy environment variables
export HTTP_PROXY=http://proxy:8080
export HTTPS_PROXY=http://proxy:8080

scitrans gui
```

---

## Security Considerations

### Development Mode (Default)
- GUI runs locally on `localhost:7860`
- No authentication
- API keys stored in plain text

### Production Deployment
For production use, consider:
1. Setting up authentication
2. Using environment-specific key management
3. Running behind reverse proxy (nginx)
4. Enabling HTTPS
5. Implementing rate limiting

**See:** `docs/PRODUCTION_ROADMAP.md` for deployment guide

---

## Getting Help

### Check Installation
```bash
scitrans info
```

### Test GUI Loading
```bash
python3 -c "from scitrans.gui.app import create_gui; print('✅ GUI loads successfully')"
```

### View Logs
Check console output when launching GUI for error messages.

### Contact Support
- **Email:** aknk.v@pm.me
- **Documentation:** See `docs/` folder
- **Issues:** Include output of `scitrans info`

---

## Next Steps

After installation:

1. **First Launch**
   ```bash
   scitrans gui
   ```

2. **Read Quick Start**
   - See `docs/GUI_QUICK_REFERENCE.md`

3. **Configure API Keys**
   - Go to Settings tab
   - Add keys for desired backends
   - Restart GUI

4. **Try Translation**
   - Upload a test PDF
   - Select target language
   - Click "Start Translation"

5. **Explore Features**
   - Read `docs/GUI_ENHANCED_FEATURES.md`
   - Try different tabs
   - Experiment with settings

---

## Frequently Asked Questions

### Q: Which dependencies are required vs. optional?

**Required:**
- `gradio` — Core GUI framework

**Recommended:**
- `requests` — URL fetching
- `PyMuPDF` — PDF preview
- `matplotlib` — Visualizations
- `Pillow` — Image handling
- `numpy` — Data processing

### Q: Can I run the GUI without optional dependencies?

Yes, but some features will be disabled:
- No URL fetching without `requests`
- No PDF preview without `PyMuPDF`
- No ablation charts without `matplotlib`

### Q: How much disk space is needed?

- SciTrans: ~50 MB
- GUI dependencies: ~200 MB
- Total: ~250 MB

### Q: What are the system requirements?

**Minimum:**
- Python 3.9+
- 2 GB RAM
- 500 MB disk space

**Recommended:**
- Python 3.10+
- 4 GB RAM
- 1 GB disk space

### Q: Can I use the GUI on a server?

Yes, use `--share` for public access or configure port forwarding.

---

**Last Updated:** December 30, 2025  
**Version:** 2.0  
**Author:** Franck Davy, Wenzhou University

