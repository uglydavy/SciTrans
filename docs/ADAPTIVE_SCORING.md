# Adaptive Scoring System — Pre & Post Translation

**Core Innovation:** SciTrans-LLMs uses comprehensive pre and post-translation scoring to drive adaptive translation strategies.

## Overview

The adaptive scoring system works in two stages:

```
                      ┌─────────────────┐
                      │  Source Block   │
                      └────────┬────────┘
                               │
                    ┌──────────▼──────────┐
                    │  PRE-SCORING        │
                    │  Assess complexity  │
                    └──────────┬──────────┘
                               │
                     ┌─────────▼─────────┐
                     │ Adapt Strategy:   │
                     │ • Temperature     │
                     │ • Candidates      │
                     │ • Constraints     │
                     └─────────┬─────────┘
                               │
                    ┌──────────▼──────────┐
                    │  TRANSLATION        │
                    │  (with adaptations) │
                    └──────────┬──────────┘
                               │
                    ┌──────────▼──────────┐
                    │  POST-SCORING       │
                    │  Assess quality     │
                    └──────────┬──────────┘
                               │
                     ┌─────────▼─────────┐
                     │ Decision:         │
                     │ • Accept          │
                     │ • Review          │
                     │ • Retry           │
                     └───────────────────┘
```

---

## Pre-Translation Scoring

**Purpose:** Assess source block complexity BEFORE translation to adapt strategy.

### Complexity Factors

1. **Special Content Detection**
   - Math expressions: `$...$`, `\(...\)`
   - Code blocks: ` ``` `, `` ` ``
   - URLs: `https://...`
   - Citations: `[1, 2]`
   - Tables: `|...|`
   - Bullets: `•`, `-`
   - Numbers: `42`, `3.14`

2. **Text Characteristics**
   - Sentence count
   - Word count
   - Average word length
   - Technical term density (words > 8 chars)

### Complexity Score (0.0-1.0)

- **0.0-0.3:** Simple text (news, general content)
- **0.4-0.6:** Moderate (technical writing)
- **0.7-1.0:** Complex (heavy math, code, technical)

### Adaptive Strategies

Based on complexity score:

| Complexity | Temperature | Candidates | Constraints |
|------------|-------------|------------|-------------|
| 0.0-0.4 | 0.2 | 3 | relaxed |
| 0.4-0.7 | 0.1 | 3 | normal |
| 0.7-1.0 | 0.0 | 5 | strict |

**Example:**
```python
# Simple block
complexity = 0.3
→ temperature = 0.2, candidates = 3, constraints = "relaxed"

# Complex block (math + technical)
complexity = 0.85
→ temperature = 0.0, candidates = 5, constraints = "strict"
```

### Implementation

```python
from scitrans.metrics.scoring import compute_pre_translation_score

pre_score = compute_pre_translation_score(block_id, source_text)

print(f"Complexity: {pre_score.complexity_score:.2f}")
print(f"Has math: {pre_score.has_math}")
print(f"Recommended candidates: {pre_score.recommended_candidates}")

if pre_score.is_complex():
    # Use stricter settings
    temperature = pre_score.recommended_temperature
    n_candidates = pre_score.recommended_candidates
```

---

## Post-Translation Scoring

**Purpose:** Assess translation quality AFTER translation to decide: accept, review, or retry.

### Quality Dimensions (5)

1. **Placeholder Preservation** (35% weight)
   - Are all math/code placeholders present?
   - Score: 0.0-1.0 (1.0 = all present)
   - **Critical:** Placeholder score < 1.0 → automatic retry

2. **Numeric Accuracy** (25% weight)
   - Are all numbers preserved correctly?
   - Score: 0.0-1.0
   - Issue if < 0.9

3. **Format Preservation** (20% weight)
   - Bullets preserved?
   - Line structure maintained?
   - Score: 0.0-1.0

4. **Fluency** (10% weight)
   - No excessive repetition?
   - Reasonable length?
   - Score: 0.0-1.0

5. **Fidelity** (10% weight)
   - Length ratio reasonable (0.8-1.5)?
   - Meaning likely preserved?
   - Score: 0.0-1.0

### Overall Score Calculation

```python
overall_score = (
    placeholder_score * 0.35 +
    numeric_score * 0.25 +
    format_score * 0.20 +
    fluency_score * 0.10 +
    fidelity_score * 0.10
)
```

### Decision Logic

```python
if overall_score >= 0.85 and no issues:
    → ACCEPT (high quality)
elif overall_score >= 0.70:
    → REVIEW (acceptable but needs check)
elif placeholder_score < 0.9 or numeric_score < 0.8:
    → RETRY (critical issues)
else:
    → REVIEW (quality concerns)
```

### Implementation

```python
from scitrans.metrics.scoring import compute_post_translation_score

post_score = compute_post_translation_score(
    block_id=block_id,
    source_text=source,
    translated_text=translation,
    registry=placeholder_registry,
    errors=validation_errors,
)

print(f"Overall quality: {post_score.overall_score:.2%}")
print(f"Placeholder preservation: {post_score.placeholder_score:.2%}")
print(f"Numeric accuracy: {post_score.numeric_score:.2%}")
print(f"Issues: {post_score.issues}")
print(f"Confidence: {post_score.confidence:.2%}")

if post_score.needs_retry:
    # Automatic retry with stronger constraints
    retry_translation(block_id)
elif post_score.needs_review:
    # Flag for human review
    flag_for_review(block_id)
else:
    # Accept
    accept_translation(block_id)
```

---

## Integration in Pipeline

### Workflow with Scoring

```python
for block in document:
    # 1. PRE-SCORING
    pre_score = compute_pre_translation_score(block.id, block.text)
    
    # 2. ADAPT STRATEGY
    if pre_score.is_complex():
        temperature = pre_score.recommended_temperature
        n_candidates = pre_score.recommended_candidates
    else:
        temperature = config.temperature
        n_candidates = config.n_candidates
    
    # 3. TRANSLATE (with adapted parameters)
    translation = backend.translate(
        block.text,
        temperature=temperature,
        n_candidates=n_candidates,
    )
    
    # 4. POST-SCORING
    post_score = compute_post_translation_score(
        block.id,
        block.text,
        translation.text,
        registry=block.registry,
        errors=translation.errors,
    )
    
    # 5. DECIDE
    if post_score.needs_retry:
        # Retry with stronger constraints
        translation = retry_translation(block, strict_mode=True)
        # Re-score
        post_score = compute_post_translation_score(...)
    
    if post_score.is_acceptable():
        accept(translation)
    else:
        flag_for_review(block.id, post_score.issues)
```

---

## Artifacts Generated

Each translation run produces:

```
outputs/<doc>/
├── pre_scores.json        # ← PRE: Complexity assessment
├── post_scores.json       # ← POST: Quality assessment
├── health_scores.json     # ← Combined health metrics
├── report.json            # ← Summary with scoring section
└── ...
```

### pre_scores.json Example

```json
[
  {
    "block_id": "b_0_abc123",
    "complexity_score": 0.75,
    "has_math": true,
    "has_code": false,
    "has_urls": true,
    "sentence_count": 3,
    "word_count": 45,
    "technical_term_density": 0.35,
    "recommended_temperature": 0.0,
    "recommended_candidates": 5,
    "recommended_constraints": "strict"
  }
]
```

### post_scores.json Example

```json
[
  {
    "block_id": "b_0_abc123",
    "overall_score": 0.92,
    "placeholder_score": 1.0,
    "numeric_score": 0.95,
    "format_score": 0.90,
    "fluency_score": 0.85,
    "fidelity_score": 0.95,
    "issues": [],
    "warnings": ["minor_numeric_variation:0.95"],
    "needs_review": false,
    "needs_retry": false,
    "confidence": 0.95
  }
]
```

### report.json Scoring Section

```json
{
  "scoring": {
    "document_quality": 0.91,
    "document_confidence": 0.93,
    "blocks_total": 50,
    "blocks_acceptable": 47,
    "blocks_need_review": 2,
    "blocks_need_retry": 1,
    "acceptance_rate": 0.94,
    "avg_source_complexity": 0.52,
    "complex_blocks": 12,
    "avg_placeholder_preservation": 0.98,
    "avg_numeric_accuracy": 0.95,
    "avg_format_preservation": 0.92,
    "avg_fluency": 0.88,
    "avg_fidelity": 0.90
  }
}
```

---

## Benefits

### 1. Adaptive Quality
- Simple blocks: faster, lower cost
- Complex blocks: more candidates, stricter validation
- **Result:** Optimal quality/cost tradeoff

### 2. Automated Decision Making
- No guessing: scores drive decisions
- Objective metrics: reproducible
- **Result:** Reliable automation

### 3. Targeted Improvements
- Know exactly which blocks are problematic
- Know exactly why (placeholder? numeric? format?)
- **Result:** Efficient repair

### 4. Research Insights
- Quantify translation difficulty
- Measure system performance
- Track quality over time
- **Result:** Publishable metrics

---

## Usage

### View Pre-Scores
```bash
cat outputs/doc/pre_scores.json | \
  jq '.[] | select(.complexity_score > 0.7)'
# Shows complex blocks that got special handling
```

### View Post-Scores
```bash
cat outputs/doc/post_scores.json | \
  jq '.[] | select(.needs_retry)'
# Shows blocks that need retry
```

### View Scoring Summary
```bash
cat outputs/doc/report.json | jq '.scoring'
# Document-level quality metrics
```

### Repair Based on Scores
```bash
# Get blocks that need retry
blocks=$(cat outputs/doc/post_scores.json | \
  jq -r '.[] | select(.needs_retry) | .block_id' | \
  paste -sd "," -)

# Repair them
scitrans repair \
  --in doc.pdf \
  --out doc_repaired.pdf \
  --artifacts outputs/doc \
  --blocks "$blocks"
```

---

## Research Applications

### Thesis Contribution: Adaptive Strategies

**Research Question:** Does adaptive translation strategy improve quality?

**Experiment:**
```python
# Control: Fixed strategy
config_fixed = PipelineConfig(
    temperature=0.1,
    n_candidates=3,
)

# Experimental: Adaptive strategy (uses pre-scoring)
config_adaptive = PipelineConfig(
    # Strategy adapts based on pre-scores
)

# Compare results using post-scores
```

**Metrics:**
- Document quality (adaptive vs. fixed)
- Complex block handling (adaptive vs. fixed)
- Cost efficiency (API calls saved)

### Thesis Contribution: Multi-Dimensional Scoring

**Research Question:** Which quality dimensions predict human judgment?

**Data from SciTrans:**
- Pre-scores: complexity assessment
- Post-scores: 5 quality dimensions
- Human ratings: collect for validation

**Analysis:**
- Correlation: post-scores vs human judgment
- Feature importance: which dimensions matter most?
- Threshold optimization: what score = acceptable?

---

## Comparison to Related Works

| Feature | Related Works | SciTrans-LLMs |
|---------|---------------|---------------|
| **Pre-Translation** |
| Complexity assessment | ❌ | ✅ Comprehensive |
| Adaptive strategy | ❌ | ✅ Yes |
| **Post-Translation** |
| Quality scoring | ⚠️ Basic | ✅ Multi-dimensional |
| Automated decisions | ❌ | ✅ Accept/review/retry |
| **Integration** |
| Scores drive workflow | ❌ | ✅ Yes |
| Artifacts for research | ⚠️ Limited | ✅ Complete |

---

## Implementation Details

### File: `scitrans/metrics/scoring.py`

**Functions:**
- `compute_pre_translation_score()` — Pre-scoring
- `compute_post_translation_score()` — Post-scoring
- `aggregate_scores()` — Document-level aggregation

### Integration Points

1. **Pipeline (scitrans/pipeline.py)**
   - Line ~76: Pre-scoring computation
   - Line ~95: Adaptive parameter selection
   - Line ~200: Post-scoring computation
   - Line ~250: Scoring summary in report

2. **CLI (scitrans/cli/main.py)**
   - Scoring runs automatically (no flags needed)

3. **Artifacts**
   - `pre_scores.json`: Per-block complexity
   - `post_scores.json`: Per-block quality
   - `report.json`: Aggregated metrics

---

## Advanced: Custom Scoring

### Customize Pre-Scoring Weights

```python
def custom_pre_score(text: str) -> float:
    complexity = 0.0
    
    # Your custom rules
    if "quantum" in text.lower():
        complexity += 0.3  # Quantum physics is complex
    if "theorem" in text.lower():
        complexity += 0.2  # Math theorem is complex
    
    # Use built-in detection
    if has_math(text):
        complexity += 0.25
    
    return min(complexity, 1.0)
```

### Customize Post-Scoring Weights

```python
# In scitrans/metrics/scoring.py
overall_score = (
    placeholder_score * 0.40 +  # Increase weight
    numeric_score * 0.30 +      # Increase weight
    format_score * 0.20 +
    fluency_score * 0.05 +      # Decrease weight
    fidelity_score * 0.05
)
```

---

## Testing

### Test Pre-Scoring
```python
from scitrans.metrics.scoring import compute_pre_translation_score

# Simple text
text1 = "This is simple text."
score1 = compute_pre_translation_score("b1", text1)
assert score1.complexity_score < 0.4

# Complex text (math + technical)
text2 = "The equation $E=mc^2$ shows mass-energy equivalence."
score2 = compute_pre_translation_score("b2", text2)
assert score2.complexity_score > 0.6
assert score2.has_math == True
```

### Test Post-Scoring
```python
from scitrans.metrics.scoring import compute_post_translation_score

source = "The value is 42 and $x^2$."
translation = "La valeur est 42 et ⟦MATH_0001⟧."
registry = {"⟦MATH_0001⟧": "$x^2$"}

score = compute_post_translation_score("b1", source, translation, registry, [])
assert score.placeholder_score == 1.0  # All placeholders present
assert score.numeric_score == 1.0  # Number preserved
assert score.is_acceptable()  # High quality
```

---

## Conclusion

**Pre and post-scoring make SciTrans-LLMs truly adaptive:**

✅ **Pre-scoring** adapts strategy to content complexity  
✅ **Post-scoring** validates quality comprehensively  
✅ **Integration** drives automated decisions  
✅ **Research-ready** artifacts for thesis

**This is a core innovation in your thesis:**
"Adaptive Document Translation Enhanced by Technology based on LLMs"

The scoring system is the "adaptive" part that sets SciTrans-LLMs apart from related works.

