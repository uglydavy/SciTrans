# Testing Guide

SciTrans includes a comprehensive test suite to ensure all features work correctly.

## Quick Start

```bash
# Run all tests
make test

# Run with coverage
make test-cov

# Run fast tests only (skip slow integration tests)
make test-fast
```

## Test Structure

```
tests/
├── test_backends.py          # Backend interface tests
├── test_caching.py            # Translation cache tests
├── test_deterministic_ids.py  # Block ID stability
├── test_health_scoring.py     # Health score calculations
├── test_integration.py        # End-to-end pipeline tests
├── test_mask_roundtrip.py     # Masking/restoration
├── test_reranking.py          # Candidate reranking
└── test_render_basic.py       # Basic rendering
```

## Test Categories

### Unit Tests

Test individual components in isolation:

```bash
# Test masking engine
pytest tests/test_mask_roundtrip.py -v

# Test reranking
pytest tests/test_reranking.py -v

# Test caching
pytest tests/test_caching.py -v

# Test health scoring
pytest tests/test_health_scoring.py -v
```

### Integration Tests

Test the complete pipeline:

```bash
# Full pipeline test
pytest tests/test_integration.py -v

# Skip slow tests
pytest tests/test_integration.py -v -m "not slow"
```

### Backend Tests

Test individual backends (requires API keys):

```bash
# Test specific backend (skipped by default)
pytest tests/test_backends.py::test_anthropic_backend -v

# Enable all backend tests
export SCITRANS_TEST_BACKENDS=1
pytest tests/test_backends.py -v
```

## Manual Testing

### 1. Basic Translation (Dummy Backend)

```bash
# Create test PDF
make demo

# Or manually:
python -c "
import fitz
doc = fitz.open()
p = doc.new_page(width=300, height=200)
p.insert_text((50, 80), 'Hello World', fontsize=12)
doc.save('test.pdf')
doc.close()
"

# Translate
scitrans translate --in test.pdf --out test_fr.pdf --backend dummy

# Check outputs
ls outputs/test/
cat outputs/test/report.json
```

### 2. Real Translation (Anthropic)

```bash
# Setup API key
export ANTHROPIC_API_KEY="..."

# Run demo
make demo-anthropic

# Or manually:
scitrans translate \
  --in test.pdf \
  --out test_fr.pdf \
  --backend anthropic \
  --model claude-3-5-sonnet-20241022 \
  --n-candidates 3 \
  --context 2
```

### 3. Test Caching

```bash
# First run
time scitrans translate --in test.pdf --out out1.pdf

# Second run (should be faster)
time scitrans translate --in test.pdf --out out2.pdf

# Check cache
ls outputs/test/.cache/
```

### 4. Test Repair

```bash
# Translate
scitrans translate --in test.pdf --out test_fr.pdf --backend anthropic

# Check health scores
cat outputs/test/health_scores.json | jq '.[] | select(.status=="failed")'

# Repair failed blocks
scitrans repair \
  --in test.pdf \
  --out test_fr_repaired.pdf \
  --artifacts outputs/test \
  --backend anthropic
```

## Test Coverage

Current coverage for core modules:

- **Parsing:** 95%+ (deterministic IDs, reading order)
- **Masking:** 90%+ (masking, restoration, validation)
- **Translation:** 85%+ (caching, reranking, retry)
- **Rendering:** 80%+ (redaction, font-fit)
- **Metrics:** 90%+ (health scoring, layout metrics)

To generate coverage report:

```bash
pytest --cov=scitrans --cov-report=html
open htmlcov/index.html
```

## Feature Testing Matrix

### Core Features

| Feature | Unit Test | Integration Test | Manual Test |
|---------|-----------|------------------|-------------|
| Deterministic IDs | ✓ | ✓ | ✓ |
| Reading Order | ✓ | ✓ | ✓ |
| Masking/Restoration | ✓ | ✓ | ✓ |
| Translation Caching | ✓ | ✓ | ✓ |
| Multi-candidate Reranking | ✓ | ✓ | ✓ |
| Context Window | ✗ | ✓ | ✓ |
| Automatic Retry | ✗ | ✓ | ✓ |
| Health Scoring | ✓ | ✓ | ✓ |
| Selective Repair | ✗ | ✓ | ✓ |
| Redaction Rendering | ✓ | ✓ | ✓ |
| Font Fitting | ✓ | ✓ | ✓ |

### Backend Testing

| Backend | Import Test | Basic Translation | Real PDF |
|---------|-------------|-------------------|----------|
| Dummy | ✓ | ✓ | ✓ |
| Anthropic | ✓ | Manual | Manual |
| OpenAI | ✓ | Manual | Manual |
| Google Free | ✓ | Manual | Manual |
| HuggingFace | ✓ | Manual | Manual |
| Ollama | ✓ | Manual | Manual |

## Continuous Integration

Tests run automatically on:
- Push to main branch
- Pull requests
- Scheduled daily runs

CI runs:
- All unit tests
- Fast integration tests
- Linting (ruff, mypy)
- Coverage checks

## Common Test Failures

### "ModuleNotFoundError: No module named 'fitz'"

```bash
pip install pymupdf
```

### "Missing ANTHROPIC_API_KEY"

Backend tests requiring API keys are skipped by default. To enable:

```bash
export ANTHROPIC_API_KEY="..."
pytest tests/test_backends.py::test_anthropic_backend -v
```

### "Ollama connection refused"

Ensure Ollama is running:

```bash
ollama serve
```

### Test PDF Creation Fails

Ensure PyMuPDF is installed:

```bash
pip install pymupdf
```

## Writing New Tests

### Unit Test Template

```python
from scitrans.your_module import your_function

def test_your_feature():
    """Test description."""
    # Arrange
    input_data = "test"
    
    # Act
    result = your_function(input_data)
    
    # Assert
    assert result == "expected"
```

### Integration Test Template

```python
import pytest
from pathlib import Path

@pytest.mark.slow
def test_full_pipeline_feature(tmp_path: Path):
    """Test complete pipeline with specific feature."""
    # Create test PDF
    test_pdf = tmp_path / "test.pdf"
    # ... create PDF ...
    
    # Run pipeline
    from scitrans.pipeline import run_pipeline
    report = run_pipeline(...)
    
    # Verify results
    assert report["num_ok"] > 0
    # ... more assertions ...
```

## Test Data

Test PDFs should include:
- Various text blocks (paragraphs, lists, tables)
- Math content (`$E=mc^2$`)
- Numbers (42, 3.14)
- URLs (https://example.com)
- Multiple fonts and sizes

Example test PDF creation:

```python
import fitz

doc = fitz.open()
page = doc.new_page(width=400, height=600)

# Title
page.insert_text((50, 50), "Scientific Paper", fontsize=16, fontname="helv-bold")

# Abstract
page.insert_text((50, 80), "Abstract", fontsize=14, fontname="helv-bold")
page.insert_text((50, 100), "This paper presents...", fontsize=11)

# Math
page.insert_text((50, 130), "Equation: $E=mc^2$", fontsize=11)

# List
page.insert_text((50, 160), "• Point 1", fontsize=11)
page.insert_text((50, 180), "• Point 2", fontsize=11)

doc.save("test_scientific.pdf")
doc.close()
```

## Regression Testing

After each major change, run the full test suite:

```bash
make check  # Lint + test
```

Keep test PDFs in `tests/fixtures/` for regression testing.

