# Tests

Comprehensive test suite for SciTrans covering all phases and features.

## Test Organization

```
tests/
├── test_adaptive_scoring.py       # Pre/post translation scoring
├── test_backends.py               # Translation backend tests
├── test_caching.py                # Translation cache tests
├── test_deterministic_ids.py      # Block ID stability
├── test_health_scoring.py         # Health diagnostics
├── test_integration.py            # End-to-end pipeline tests
├── test_layout_intelligence.py    # Multi-column, paragraphs, headers
├── test_mask_roundtrip.py         # Masking engine tests
├── test_math_detection.py         # Math equation detection
├── test_math_rendering.py         # Math-aware rendering
├── test_render_basic.py           # Basic rendering tests
├── test_reranking.py              # Candidate reranking
├── test_table_detection.py        # Table detection heuristics
└── test_table_pipeline.py         # Table rendering pipeline
```

## Running Tests

### All tests:
```bash
python3 -m pytest tests/ -v
```

### Specific test file:
```bash
python3 -m pytest tests/test_math_detection.py -v
```

### Fast tests only (skip slow integration):
```bash
python3 -m pytest tests/ -v -m "not slow"
```

### With coverage:
```bash
python3 -m pytest tests/ -v --cov=scitrans --cov-report=html
open htmlcov/index.html
```

## Test Categories

### Unit Tests (Fast)
- `test_backends.py` — Backend interfaces
- `test_caching.py` — Cache operations
- `test_mask_roundtrip.py` — Masking logic
- `test_adaptive_scoring.py` — Scoring algorithms
- `test_health_scoring.py` — Health diagnostics
- `test_reranking.py` — Reranking logic
- `test_deterministic_ids.py` — ID stability
- `test_math_detection.py` — Math detection
- `test_table_detection.py` — Table detection

### Integration Tests (Slower)
- `test_integration.py` — Full pipeline end-to-end
- `test_layout_intelligence.py` — Layout processing
- `test_math_rendering.py` — Math rendering pipeline
- `test_render_basic.py` — Basic rendering
- `test_table_pipeline.py` — Table rendering pipeline

## Test Fixtures

Common fixtures are defined in test files:
- `tmp_path` — Pytest built-in temp directory
- `sample_pdf` — Generated test PDF
- Backend instances (DummyBackend, etc.)

## Writing New Tests

### Test structure:
```python
def test_feature_description():
    """Clear docstring explaining what's being tested."""
    # Arrange: setup test data
    test_input = ...
    
    # Act: execute the function
    result = function_under_test(test_input)
    
    # Assert: verify expected behavior
    assert result == expected_value
```

### Best practices:
- Use descriptive names: `test_<what>_<when>_<expected>`
- Keep tests focused (one concept per test)
- Use fixtures for common setup
- Add docstrings explaining the test purpose
- Mark slow tests: `@pytest.mark.slow`
- Test both success and failure cases

## Coverage Goals

- **Target:** ≥80% code coverage
- **Current:** ~85% (verified with `pytest --cov`)
- **Critical paths:** 100% coverage for core logic (masking, rendering, scoring)

## Skipped Tests

Some tests are skipped when dependencies aren't available:
- `test_anthropic_backend` — Requires `ANTHROPIC_API_KEY`
- `test_openai_backend` — Requires `OPENAI_API_KEY`
- `test_google_backend` — Rate-limited
- `test_ollama_backend` — Requires Ollama running locally

To run these tests, set the appropriate environment variables or start required services.

## Continuous Integration

Tests run automatically on every push via GitHub Actions (`.github/workflows/ci.yml`):
- Python versions: 3.9, 3.10, 3.11, 3.12, 3.13
- Coverage reporting to Codecov
- Integration test with dummy backend

## Troubleshooting

### Tests fail with "ModuleNotFoundError: No module named 'scitrans'"
```bash
# Install package in editable mode
pip install -e ".[dev]"
```

### Tests fail with font/rendering errors
```bash
# Ensure fonts are installed
ls scitrans/assets/fonts/*.ttf
```

### Cache-related test failures
```bash
# Clear cache
rm -rf outputs/.cache
```

## Test Metrics

**As of v1.0.0:**
- Total tests: 53
- Passed: 49
- Skipped: 4 (require external services)
- Coverage: 85%
- Duration: ~1 second

## Adding New Tests

When adding new features:
1. Create test file: `tests/test_<feature>.py`
2. Add unit tests for individual functions
3. Add integration test for end-to-end workflow
4. Update this README if new test category
5. Ensure `make test` still passes

## Contact

Questions about tests? Contact: aknk.v@pm.me

