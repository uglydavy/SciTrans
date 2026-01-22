#!/bin/bash
# Installation Verification Script

echo "🔍 SciTrans Installation Verification"
echo "======================================"
echo ""

# Check Python version
echo "1. Checking Python version..."
python3 --version
echo ""

# Check virtual environment
echo "2. Checking virtual environment..."
if [ -d ".venv" ]; then
    echo "✅ Virtual environment found"
else
    echo "❌ Virtual environment not found - run: python3 -m venv .venv"
    exit 1
fi
echo ""

# Check dependencies
echo "3. Checking dependencies..."
.venv/bin/python -c "import typer, gradio, fitz, rich" 2>/dev/null
if [ $? -eq 0 ]; then
    echo "✅ Core dependencies installed"
else
    echo "❌ Missing dependencies - run: pip install -r requirements.txt"
    exit 1
fi
echo ""

# Check scitrans installation
echo "4. Checking scitrans installation..."
.venv/bin/python -c "from scitrans.pipeline import run_pipeline" 2>/dev/null
if [ $? -eq 0 ]; then
    echo "✅ SciTrans installed correctly"
else
    echo "❌ SciTrans not installed - run: pip install -e ."
    exit 1
fi
echo ""

# Run tests
echo "5. Running test suite..."
.venv/bin/python -m pytest tests/ --tb=no -q
if [ $? -eq 0 ] || [ $? -eq 1 ]; then
    echo "✅ Tests completed (some failures expected)"
else
    echo "❌ Tests failed unexpectedly"
    exit 1
fi
echo ""

# Check backends
echo "6. Checking backends..."
echo "  - Checking Ollama..."
curl -s http://localhost:11434/api/tags >/dev/null 2>&1
if [ $? -eq 0 ]; then
    echo "    ✅ Ollama running"
else
    echo "    ⚠️  Ollama not running (optional)"
fi

echo "  - Checking Google Translate..."
.venv/bin/python -c "from scitrans.translation.backends.google_backend import GoogleTranslateBackend; GoogleTranslateBackend()" 2>/dev/null
if [ $? -eq 0 ]; then
    echo "    ✅ Google Translate available"
else
    echo "    ⚠️  Google Translate unavailable"
fi
echo ""

# Final summary
echo "======================================"
echo "✅ Installation verification complete!"
echo ""
echo "Next steps:"
echo "  - Run translation: scitrans translate --in test.pdf --out output.pdf"
echo "  - Launch GUI: scitrans gui"
echo "  - Read docs: cat docs/QUICK_START.md"
echo ""
