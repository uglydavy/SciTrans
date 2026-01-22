# Feature Tests

This directory contains comprehensive tests for individual features of the SciTrans translation pipeline.

## Test Categories

### Core Features
- `test_placeholder_preservation.py` - Test masking and restoration of LaTeX, code, URLs, etc.
- `test_identity_detection.py` - Test detection of identity translations
- `test_reranking_quality.py` - Test candidate reranking and selection
- `test_retry_logic.py` - Test automatic retry for failed translations
- `test_context_window.py` - Test context-aware translation

### Quality Features
- `test_scoring_metrics.py` - Test pre and post-translation scoring
- `test_hallucination_detection.py` - Test detection of added content
- `test_section_number_preservation.py` - Test preservation of numbering
- `test_glossary_compliance.py` - Test glossary term usage

### Rendering Features
- `test_font_fitting.py` - Test adaptive font sizing
- `test_text_overflow_handling.py` - Test overflow detection and handling
- `test_perfect_rendering.py` - Test layout-preserving rendering
- `test_math_rendering.py` - Test math equation preservation

### Backend Features
- `test_cascade_free.py` - Test free backend combination
- `test_backend_fallback.py` - Test fallback strategies
- `test_parallel_translation.py` - Test concurrent translation

## Running Feature Tests

```bash
# Run all feature tests
pytest tests/features/ -v

# Run specific feature test
pytest tests/features/test_placeholder_preservation.py -v

# Run with coverage
pytest tests/features/ --cov=scitrans --cov-report=html
```

## Adding New Feature Tests

1. Create a new file `test_<feature_name>.py`
2. Import necessary fixtures from `conftest.py`
3. Write tests following the pattern:
   ```python
   def test_feature_name():
       # Setup
       # Execute
       # Assert
       pass
   ```
4. Add documentation explaining what the test validates
5. Add to this README

