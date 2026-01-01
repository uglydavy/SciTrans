# SciTrans CLI Reference

## Commands Overview

```
scitrans [OPTIONS] COMMAND [ARGS]...
```

### Available Commands

- `translate` - Translate a PDF document
- `repair` - Repair failed blocks from previous run
- `backends` - List available translation backends
- `info` - Show system info or analyze PDF
- `status` - Check system status
- `gui` - Launch web GUI

---

## translate

Translate a PDF from source to target language.

### Basic Usage

```bash
scitrans translate --in document.pdf --out document_fr.pdf
```

### Options

| Option | Default | Description |
|--------|---------|-------------|
| `--in` | *required* | Input PDF path |
| `--out` | *required* | Output PDF path |
| `--source` | `en` | Source language code |
| `--target` | `fr` | Target language code |
| `--backend` | `cascade_free` | Translation backend |
| `--model` | `cascade_free` | Model name |
| `--artifacts` | `outputs` | Artifacts directory |
| `--n-candidates` | `3` | Number of candidates |
| `--context` | `2` | Context window size |
| `--no-cache` | `False` | Disable caching |
| `--no-rerank` | `False` | Disable reranking |
| `--no-retry` | `False` | Disable retry |
| `--render-mode` | `perfect` | Render mode |
| `--translate-tables` | `False` | Translate tables |
| `--verbose`, `-v` | `False` | Verbose output |
| `--debug` | `False` | Debug output |
| `--log-file` | `None` | Log file path |

### Render Modes

- `perfect` - Exact font sizes, bullets, styling (default)
- `enhanced` - Preserve major styling
- `auto` - Auto-detect math
- `math-aware` - Always preserve equations
- `math-safe` - Legacy mode

### Examples

```bash
# Basic translation
scitrans translate --in doc.pdf --out doc_fr.pdf

# High quality
scitrans translate \
  --in doc.pdf \
  --out doc_fr.pdf \
  --backend anthropic \
  --render-mode perfect \
  --n-candidates 5 \
  --context 3

# Fast translation
scitrans translate \
  --in doc.pdf \
  --out doc_fr.pdf \
  --n-candidates 1 \
  --no-rerank \
  --no-cache

# With verbose logging
scitrans translate \
  --in doc.pdf \
  --out doc_fr.pdf \
  --verbose \
  --log-file translation.log
```

---

## repair

Repair failed blocks from a previous translation.

### Usage

```bash
scitrans repair \
  --in document.pdf \
  --out document_fixed.pdf \
  --artifacts outputs/document
```

### Options

| Option | Default | Description |
|--------|---------|-------------|
| `--in` | *required* | Input PDF path |
| `--out` | *required* | Output PDF path |
| `--artifacts` | *required* | Artifacts directory |
| `--backend` | `cascade_free` | Backend for repair |
| `--model` | `cascade_free` | Model name |
| `--blocks` | `None` | Comma-separated block IDs |
| `--verbose`, `-v` | `False` | Verbose output |

### Examples

```bash
# Repair all failed blocks
scitrans repair \
  --in doc.pdf \
  --out doc_fixed.pdf \
  --artifacts outputs/doc

# Repair specific blocks
scitrans repair \
  --in doc.pdf \
  --out doc_fixed.pdf \
  --artifacts outputs/doc \
  --blocks b_0_abc,b_1_def
```

---

## backends

List all available translation backends.

### Usage

```bash
scitrans backends
```

### Output

Shows table with:
- Backend name
- Description
- Cost (Free/Paid)
- Status (✅ Available / ❌ Missing deps / ⚠️ Need API key)

---

## info

Show system information or analyze a PDF.

### Usage

```bash
# System info
scitrans info

# Analyze PDF
scitrans info document.pdf
```

### PDF Analysis Output

- Pages count
- Total blocks
- Text blocks
- Math blocks
- Tables
- Images
- File size

---

## status

Check system status: backends, dependencies, configuration.

### Usage

```bash
scitrans status
```

### Output

- Healthy backends count
- Missing dependencies
- Missing API keys
- Errors
- Overall system readiness

---

## gui

Launch the SciTrans web GUI.

### Usage

```bash
scitrans gui

# With options
scitrans gui --share --port 7860
```

### Options

| Option | Default | Description |
|--------|---------|-------------|
| `--share` | `False` | Create public share link |
| `--port` | `7860` | Server port |

---

## Language Codes

Common language codes:

- `en` - English
- `fr` - French
- `es` - Spanish
- `de` - German
- `zh` - Chinese
- `ja` - Japanese
- `ko` - Korean
- `pt` - Portuguese
- `it` - Italian
- `ru` - Russian
- `ar` - Arabic
- `nl` - Dutch

---

## Exit Codes

- `0` - Success
- `1` - Error (invalid input, backend unavailable, etc.)

---

## Examples

### Complete Workflow

```bash
# 1. Check system
scitrans status

# 2. Analyze PDF
scitrans info document.pdf

# 3. Translate
scitrans translate --in document.pdf --out document_fr.pdf

# 4. If needed, repair
scitrans repair \
  --in document.pdf \
  --out document_fr_fixed.pdf \
  --artifacts outputs/document
```

### Batch Processing

```bash
# Translate all PDFs in directory
for pdf in *.pdf; do
  scitrans translate \
    --in "$pdf" \
    --out "${pdf%.pdf}_fr.pdf" \
    --backend cascade_free
done
```

### Quality Comparison

```bash
# Test different backends
for backend in cascade_free anthropic openai; do
  scitrans translate \
    --in doc.pdf \
    --out "doc_${backend}_fr.pdf" \
    --backend "$backend" \
    --render-mode perfect
done
```

