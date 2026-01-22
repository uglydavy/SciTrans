# Ablation Studies

This directory contains ablation studies to understand the impact of different features on translation quality.

## What are Ablation Studies?

Ablation studies systematically disable features to measure their individual contribution to overall performance. This helps us understand:
- Which features are most critical
- Which features can be optimized or removed
- How features interact with each other

## Ablation Categories

### Feature Ablations
- `ablation_reranking.py` - Impact of candidate reranking
- `ablation_context_window.py` - Impact of context-aware translation
- `ablation_retry_logic.py` - Impact of automatic retry
- `ablation_identity_detection.py` - Impact of identity translation detection
- `ablation_placeholder_masking.py` - Impact of placeholder protection

### Quality Ablations
- `ablation_scoring_metrics.py` - Impact of quality scoring
- `ablation_hallucination_detection.py` - Impact of hallucination detection
- `ablation_glossary.py` - Impact of glossary usage
- `ablation_temperature.py` - Impact of temperature settings

### Rendering Ablations
- `ablation_font_fitting.py` - Impact of adaptive font sizing
- `ablation_layout_preservation.py` - Impact of perfect rendering
- `ablation_math_detection.py` - Impact of math equation detection

## Running Ablation Studies

```bash
# Run all ablations
python -m pytest tests/ablations/ -v

# Run specific ablation
python tests/ablations/ablation_reranking.py

# Generate ablation report
python tests/ablations/generate_ablation_report.py
```

## Ablation Results Format

Each ablation study produces results in the following format:

```json
{
  "feature": "reranking",
  "enabled": {
    "quality": 0.92,
    "time": 45.2,
    "success_rate": 0.95
  },
  "disabled": {
    "quality": 0.85,
    "time": 38.1,
    "success_rate": 0.88
  },
  "impact": {
    "quality_delta": 0.07,
    "time_delta": 7.1,
    "success_rate_delta": 0.07
  },
  "conclusion": "Reranking improves quality by 7% at cost of 7s per document"
}
```

## Adding New Ablation Studies

1. Create a new file `ablation_<feature_name>.py`
2. Implement test with feature enabled and disabled
3. Measure relevant metrics (quality, time, success rate)
4. Calculate impact (delta between enabled/disabled)
5. Generate conclusions and recommendations
6. Add to this README

