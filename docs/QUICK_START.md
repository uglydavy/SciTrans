# SciTrans Quick Start Guide

## Installation

### 1. Create Virtual Environment

```bash
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

### 2. Install SciTrans

```bash
# Install with all dependencies
pip install -e ".[all]"

# Or install minimal version
pip install -e "."
```

### 3. Configure API Keys (Optional)

Edit `setup_env.sh` and add your API keys:

```bash
export DEEPSEEK_API_KEY="sk-..."
export ANTHROPIC_API_KEY="sk-..."
export OPENAI_API_KEY="sk-..."
```

Then load them:

```bash
source setup_env.sh
```

---

## Quick Examples

### CLI Translation

```bash
# Basic translation (English to French)
scitrans translate --in document.pdf --out document_fr.pdf

# Use specific backend
scitrans translate --in doc.pdf --out doc_fr.pdf --backend anthropic

# High quality with perfect rendering
scitrans translate --in doc.pdf --out doc_fr.pdf --render-mode perfect --n-candidates 5

# Fast translation
scitrans translate --in doc.pdf --out doc_fr.pdf --n-candidates 1 --no-rerank
```

### GUI

```bash
# Launch web interface
scitrans gui

# Open browser to: http://localhost:7860
```

### Check System Status

```bash
# Check backend availability
scitrans status

# List all backends
scitrans backends

# Analyze a PDF
scitrans info document.pdf
```

---

## Common Workflows

### Workflow 1: Quick Translation

```bash
# 1. Check system status
scitrans status

# 2. Translate
scitrans translate --in doc.pdf --out doc_fr.pdf

# 3. Check results
scitrans info doc_fr.pdf
```

### Workflow 2: High-Quality Translation

```bash
# 1. Use perfect renderer with multiple candidates
scitrans translate \
  --in document.pdf \
  --out document_fr.pdf \
  --backend anthropic \
  --render-mode perfect \
  --n-candidates 5 \
  --context 3

# 2. If some blocks fail, repair them
scitrans repair \
  --in document.pdf \
  --out document_fr_fixed.pdf \
  --artifacts outputs/document
```

### Workflow 3: Batch Translation

```bash
# Translate multiple PDFs
for pdf in *.pdf; do
  scitrans translate \
    --in "$pdf" \
    --out "${pdf%.pdf}_fr.pdf" \
    --backend cascade_free
done
```

---

## Backend Selection

### Free Backends (No API Key Required)

- **cascade_free** (default) - Ensemble of free models
- **google** - Google Translate (free tier)
- **huggingface** - HuggingFace models
- **ollama** - Local LLMs (requires Ollama running)
- **dummy** - Testing only

### Paid Backends (Require API Keys)

- **deepseek** - DeepSeek Chat (free tier available)
- **anthropic** - Claude 3.5 Sonnet
- **openai** - GPT-4 / GPT-4o

### Recommendation

- **For testing**: Use `cascade_free` or `dummy`
- **For quality**: Use `anthropic` or `openai`
- **For speed**: Use `google` or `cascade_free`

---

## Troubleshooting

### "Backend not available"

```bash
# Check backend status
scitrans status

# Install missing dependencies
pip install -e ".[backends]"
```

### "Translation failed"

```bash
# Run with verbose output
scitrans translate --in doc.pdf --out doc_fr.pdf --verbose

# Check artifacts
ls outputs/doc/
cat outputs/doc/report.json
```

### "GUI not available"

```bash
# Install GUI dependencies
pip install -e ".[gui]"
```

---

## Next Steps

- See [GUI User Guide](GUI_USER_GUIDE.md) for detailed GUI usage
- See [CLI Reference](CLI_REFERENCE.md) for all CLI options
- See [Backend Setup](BACKENDS.md) for backend configuration

