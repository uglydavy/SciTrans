# SciTrans Quick Start Guide

## Installation

```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install package
pip install -U pip
pip install -e ".[dev]"
```

## Basic Usage

### Translate a PDF (Identity/Dummy Backend)
```bash
scitrans translate --in input.pdf --out output.fr.pdf --source en --target fr --backend dummy
```

### Translate with Anthropic Backend
```bash
# Set API key
export ANTHROPIC_API_KEY="your-key-here"

# Translate
scitrans translate \
  --in input.pdf \
  --out output.fr.pdf \
  --source en \
  --target fr \
  --backend anthropic \
  --model claude-3-5-sonnet-20241022
```

### Advanced Options

**Multiple Candidates with Reranking:**
```bash
scitrans translate \
  --in input.pdf \
  --out output.fr.pdf \
  --n-candidates 3 \
  --backend anthropic
```

**Context Window (for better consistency):**
```bash
scitrans translate \
  --in input.pdf \
  --out output.fr.pdf \
  --context 2  # Include previous 2 blocks as context
```

**Disable Caching (for testing):**
```bash
scitrans translate \
  --in input.pdf \
  --out output.fr.pdf \
  --no-cache
```

## Repair Failed Blocks

After a translation run, check the health scores:

```bash
cat outputs/input/health_scores.json
```

Repair all failed blocks:
```bash
scitrans repair \
  --in input.pdf \
  --out output.repaired.pdf \
  --artifacts outputs/input \
  --backend anthropic
```

Repair specific blocks:
```bash
scitrans repair \
  --in input.pdf \
  --out output.repaired.pdf \
  --artifacts outputs/input \
  --blocks b_0_abc123,b_0_def456 \
  --backend anthropic
```

## Understanding Outputs

Each translation creates an `outputs/<doc_name>/` directory with:

- **`parsed.json`**: Document structure (pages/blocks/lines/spans)
- **`masked.json`**: Masked text with placeholder registry
- **`translations.json`**: Translation results with validation status
- **`health_scores.json`**: Per-block health scores and diagnostics
- **`report.json`**: Summary with metrics
- **`.cache/`**: Translation cache (for fast re-runs)

## Health Score Interpretation

Each block gets a health score:

- **`ok`**: Score ≥ 0.9, no issues
- **`warning`**: Score 0.5-0.9, minor issues (numeric drift, format drift)
- **`failed`**: Score < 0.5, critical issues (missing placeholders, translation failed)

Reason codes:
- `placeholder_missing`: Math/code placeholders were lost
- `numeric_drift`: Numbers changed significantly
- `format_drift`: Bullets or line breaks lost
- `potential_overflow`: Translation might overflow bbox
- `translation_failed`: Backend error or empty response

## Tips

1. **First Run**: Use `--n-candidates 1` for speed, then repair failed blocks
2. **Quality Run**: Use `--n-candidates 3` with reranking for best quality
3. **Consistency**: Use `--context 2` for better cross-block consistency
4. **Re-runs**: Caching makes re-runs 5-20x faster (same document)
5. **Repair Workflow**: Fix a few failed blocks rather than re-running everything

## Troubleshooting

**"Missing ANTHROPIC_API_KEY":**
```bash
export ANTHROPIC_API_KEY="your-key"
```

**"ModuleNotFoundError: No module named 'fitz'":**
```bash
pip install pymupdf
```

**Blocks still failing after repair:**
- Check `health_scores.json` for specific reason codes
- Try manual repair with `--blocks <specific-ids>`
- Consider using a different model or adjusting temperature

**Overlapping text in output:**
- This should be fixed by redaction-first rendering
- If still happening, check `layout_metrics` in `report.json`
- File an issue with the PDF and report.json

## Example Workflow

```bash
# 1. Initial translation
scitrans translate --in thesis.pdf --out thesis.fr.pdf --backend anthropic

# 2. Check health
cat outputs/thesis/health_scores.json | grep -A 5 '"status": "failed"'

# 3. Repair failed blocks
scitrans repair --in thesis.pdf --out thesis.fr.repaired.pdf \
  --artifacts outputs/thesis --backend anthropic

# 4. Verify
cat outputs/thesis/health_scores.json | grep '"status": "failed"' | wc -l
# Should be 0 or very few
```

