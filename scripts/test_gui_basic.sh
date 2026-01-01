#!/bin/bash
# Basic GUI Testing Script
# Tests what can be verified without launching full GUI

set -e

echo "🔍 Testing SciTrans Enhanced GUI"
echo "================================="
echo ""

cd "$(dirname "$0")/.."

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

passed=0
failed=0
warnings=0

# Test 1: Check dependencies
echo "1. Checking dependencies..."
if python3 -c "import gradio" 2>/dev/null; then
    echo -e "${GREEN}✅ Gradio installed${NC}"
    ((passed++))
else
    echo -e "${RED}❌ Gradio NOT installed${NC}"
    echo "   Install: pip install gradio"
    ((failed++))
fi

if python3 -c "import requests" 2>/dev/null; then
    echo -e "${GREEN}✅ Requests installed (URL fetching)${NC}"
    ((passed++))
else
    echo -e "${YELLOW}⚠️  Requests NOT installed (optional feature)${NC}"
    echo "   Install: pip install requests"
    ((warnings++))
fi

if python3 -c "import fitz" 2>/dev/null; then
    echo -e "${GREEN}✅ PyMuPDF installed (PDF preview)${NC}"
    ((passed++))
else
    echo -e "${YELLOW}⚠️  PyMuPDF NOT installed (optional feature)${NC}"
    echo "   Install: pip install PyMuPDF"
    ((warnings++))
fi

if python3 -c "import matplotlib" 2>/dev/null; then
    echo -e "${GREEN}✅ Matplotlib installed (visualizations)${NC}"
    ((passed++))
else
    echo -e "${YELLOW}⚠️  Matplotlib NOT installed (optional feature)${NC}"
    echo "   Install: pip install matplotlib"
    ((warnings++))
fi

if python3 -c "from PIL import Image" 2>/dev/null; then
    echo -e "${GREEN}✅ Pillow installed (image handling)${NC}"
    ((passed++))
else
    echo -e "${YELLOW}⚠️  Pillow NOT installed (optional feature)${NC}"
    echo "   Install: pip install Pillow"
    ((warnings++))
fi

if python3 -c "import numpy" 2>/dev/null; then
    echo -e "${GREEN}✅ NumPy installed (data processing)${NC}"
    ((passed++))
else
    echo -e "${YELLOW}⚠️  NumPy NOT installed (optional feature)${NC}"
    echo "   Install: pip install numpy"
    ((warnings++))
fi

echo ""

# Test 2: Code structure
echo "2. Checking code structure..."
if python3 -c "
import ast
with open('scitrans/gui/app.py') as f:
    ast.parse(f.read())
" 2>/dev/null; then
    echo -e "${GREEN}✅ Code parses correctly (no syntax errors)${NC}"
    ((passed++))
else
    echo -e "${RED}❌ Code has syntax errors${NC}"
    ((failed++))
fi

# Test 3: Function definitions
echo ""
echo "3. Checking function definitions..."
function_count=$(python3 -c "
import ast
with open('scitrans/gui/app.py') as f:
    tree = ast.parse(f.read())
functions = [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
print(len(functions))
")

if [ "$function_count" -ge 25 ]; then
    echo -e "${GREEN}✅ $function_count functions defined (expected 25+)${NC}"
    ((passed++))
else
    echo -e "${RED}❌ Only $function_count functions defined (expected 25+)${NC}"
    ((failed++))
fi

# Test 4: Required functions
echo ""
echo "4. Checking required functions..."
python3 << 'EOF'
import ast
import sys

required_functions = [
    'translate_pdf', 'fetch_pdf_from_url', 'render_pdf_page',
    'run_individual_test', 'generate_ablation_plot', 
    'search_glossary', 'save_api_key', 'get_backend_status',
    'create_gui', 'launch_gui', 'add_log', 'add_status',
    'get_models_for_backend', 'generate_quality_metrics'
]

with open('scitrans/gui/app.py') as f:
    tree = ast.parse(f.read())

functions = [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]

missing = [f for f in required_functions if f not in functions]

if missing:
    print(f"\033[0;31m❌ Missing functions: {', '.join(missing)}\033[0m")
    sys.exit(1)
else:
    print(f"\033[0;32m✅ All {len(required_functions)} required functions present\033[0m")
    sys.exit(0)
EOF

if [ $? -eq 0 ]; then
    ((passed++))
else
    ((failed++))
fi

# Test 5: Global constants
echo ""
echo "5. Checking global constants..."
if grep -q "BACKEND_MODELS" scitrans/gui/app.py && grep -q "COMMON_LANGUAGES" scitrans/gui/app.py; then
    echo -e "${GREEN}✅ Global constants defined (BACKEND_MODELS, COMMON_LANGUAGES)${NC}"
    ((passed++))
else
    echo -e "${RED}❌ Missing global constants${NC}"
    ((failed++))
fi

# Test 6: Try importing (only if gradio installed)
echo ""
echo "6. Testing imports..."
if python3 -c "import gradio" 2>/dev/null; then
    if python3 -c "from scitrans.gui.app import create_gui" 2>/dev/null; then
        echo -e "${GREEN}✅ Imports successful (module loads without errors)${NC}"
        ((passed++))
    else
        echo -e "${RED}❌ Import failed (module has runtime errors)${NC}"
        ((failed++))
    fi
else
    echo -e "${YELLOW}⚠️  Skipped (gradio not installed)${NC}"
    ((warnings++))
fi

# Test 7: Documentation files
echo ""
echo "7. Checking documentation..."
doc_files=(
    "docs/GUI_ENHANCED_FEATURES.md"
    "docs/GUI_QUICK_REFERENCE.md"
    "docs/GUI_STRUCTURE.md"
    "docs/GUI_INSTALL.md"
    "CHANGELOG_GUI.md"
    "GUI_ENHANCEMENT_SUMMARY.md"
)

missing_docs=()
for doc in "${doc_files[@]}"; do
    if [ -f "$doc" ]; then
        echo -e "${GREEN}  ✅ $doc${NC}"
    else
        echo -e "${RED}  ❌ $doc (missing)${NC}"
        missing_docs+=("$doc")
    fi
done

if [ ${#missing_docs[@]} -eq 0 ]; then
    echo -e "${GREEN}✅ All documentation files present${NC}"
    ((passed++))
else
    echo -e "${RED}❌ Missing ${#missing_docs[@]} documentation files${NC}"
    ((failed++))
fi

# Summary
echo ""
echo "================================="
echo "📊 Test Summary"
echo "================================="
echo -e "${GREEN}Passed:   $passed${NC}"
echo -e "${RED}Failed:   $failed${NC}"
echo -e "${YELLOW}Warnings: $warnings${NC}"
echo ""

if [ $failed -eq 0 ]; then
    echo -e "${GREEN}✅ Basic checks PASSED${NC}"
    echo ""
    echo "Next steps:"
    echo "1. Install optional dependencies if needed:"
    echo "   pip install -e '.[gui]'"
    echo ""
    echo "2. Launch GUI for manual testing:"
    echo "   scitrans gui"
    echo ""
    echo "3. Follow GUI_TESTING_PLAN.md for comprehensive testing"
    exit 0
else
    echo -e "${RED}❌ Basic checks FAILED${NC}"
    echo ""
    echo "Fix the failed checks before proceeding."
    echo "See output above for details."
    exit 1
fi

