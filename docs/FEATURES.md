# Features Documentation

Comprehensive guide to all SciTrans features and how they work.

## Table of Contents

1. [Deterministic Parsing](#deterministic-parsing)
2. [Math-Safe Masking](#math-safe-masking)
3. [Multi-Candidate Reranking](#multi-candidate-reranking)
4. [Translation Caching](#translation-caching)
5. [Context Window](#context-window)
6. [Automatic Retry](#automatic-retry)
7. [Health Scoring](#health-scoring)
8. [Selective Repair](#selective-repair)
9. [Layout-Safe Rendering](#layout-safe-rendering)
10. [Glossary Enforcement](#glossary-enforcement)

---

## 1. Deterministic Parsing

### What It Does
Generates stable, deterministic block IDs that remain consistent across multiple parsing runs of the same PDF.

### How It Works
- Block IDs are computed as: `hash(page_index, bbox, text_content)`
- Reading order is enforced: top-to-bottom, then left-to-right
- Float values rounded to avoid floating-point instability

### Why It Matters
- **Caching:** Same block always gets same cache key
- **Repair:** Can target specific blocks reliably
- **Debugging:** Blocks have stable identifiers across runs

### Usage
Automatic. No configuration needed.

### Verification
```bash
# Parse twice and compare block IDs
scitrans translate --in doc.pdf --out v1.pdf
scitrans translate --in doc.pdf --out v2.pdf
# Check outputs/doc/parsed.json - block IDs should match
```

---

## 2. Math-Safe Masking

### What It Does
Protects mathematical expressions, code, URLs, and other sensitive content from translation by replacing them with robust placeholders.

### How It Works
1. **Pattern Detection:** Regex patterns detect:
   - LaTeX math: `$...$`, `\(...\)`, `\[...\]`
   - Code blocks: ` ```...``` `, `` `code` ``
   - URLs: `https://...`, `www....`
   - Email: `user@domain.com`
   - Citations: `[1]`, `[2,3]`

2. **Placeholder Generation:** Unique placeholders like `⟦MATH_INLINE_0001⟧`

3. **Registry:** Maps placeholders back to original content

4. **Validation:** Ensures all placeholders present after translation

5. **Tolerant Restoration:** Handles minor variations (extra spaces, etc.)

### Why It Matters
- **Prevents** math corruption: `$E=mc^2$` stays intact
- **Prevents** URL breaking: Links remain clickable
- **Prevents** code mangling: Code snippets preserved

### Configuration
```python
# Custom masking rules
from scitrans.masking.engine import MaskingEngine, MaskRule
import re

custom_rules = [
    MaskRule("EQUATION", re.compile(r"Eq\.\s*\(\d+\)"), priority=100),
    MaskRule("FIGURE_REF", re.compile(r"Fig\.\s*\d+"), priority=90),
]

masker = MaskingEngine(rules=custom_rules)
```

### Verification
Check `masked.json` artifact to see what was masked.

---

## 3. Multi-Candidate Reranking

### What It Does
Generates multiple translation candidates and automatically selects the best one based on quality metrics.

### How It Works
1. **Generate:** Request N candidates from backend (e.g., `--n-candidates 3`)

2. **Score:** Each candidate scored on:
   - **Placeholder Preservation** (weight: 10.0): All placeholders present?
   - **Glossary Compliance** (weight: 3.0): Terms translated correctly?
   - **Numeric Stability** (weight: 2.0): Numbers preserved?
   - **Format Stability** (weight: 1.0): Bullets/line breaks intact?

3. **Select:** Highest-scoring candidate wins

4. **Hard Gate:** Candidates with missing placeholders automatically rejected

### Why It Matters
- **Quality:** Best translation selected automatically
- **Reliability:** Invalid translations rejected
- **Flexibility:** Scoring weights can be customized

### Usage
```bash
scitrans translate \
  --in doc.pdf \
  --out doc_fr.pdf \
  --n-candidates 3 \  # Generate 3 candidates
  --backend anthropic
```

### Configuration
```python
# Custom reranking weights
from scitrans.translation.reranking import rerank_candidates

ranked = rerank_candidates(
    candidates=["Tr 1", "Tr 2", "Tr 3"],
    source_text="Source",
    registry={},
    glossary={"term": "terme"},
    weights={
        "placeholder_preservation": 15.0,  # Higher priority
        "glossary_compliance": 5.0,
        "numeric_stability": 2.0,
        "format_stability": 1.0,
    },
)
```

---

## 4. Translation Caching

### What It Does
Caches translations so re-running on the same document is 5-20× faster.

### How It Works
1. **Cache Key:** Deterministic hash of:
   - Backend name
   - Model name
   - Masked text
   - Source/target languages
   - Prompt version

2. **Cache Storage:** JSON files in `outputs/.cache/`

3. **Cache Hit:** Returns cached translation instantly

4. **Cache Miss:** Translates and stores result

### Why It Matters
- **Speed:** Re-runs are ~10× faster
- **Cost:** Saves API calls
- **Iteration:** Experiment with rendering/masking without re-translating

### Usage
```bash
# First run: ~60 seconds
scitrans translate --in doc.pdf --out doc_fr.pdf --backend anthropic

# Second run: ~6 seconds (cached)
scitrans translate --in doc.pdf --out doc_fr.pdf --backend anthropic

# Disable caching (if needed)
scitrans translate --in doc.pdf --out doc_fr.pdf --no-cache
```

### Cache Management
```bash
# Clear cache for specific document
rm -rf outputs/doc/.cache/

# Clear all caches
find outputs/ -name ".cache" -type d -exec rm -rf {} +
```

---

## 5. Context Window

### What It Does
Includes previous N translated blocks as context for the current translation, improving consistency.

### How It Works
1. **Buffer:** Maintains sliding window of last N translations

2. **Context Injection:** Prepends context to translation request:
   ```
   Previous context:
   [Block N-2 translation]
   [Block N-1 translation]
   
   ---
   
   [Current block to translate]
   ```

3. **Model Benefits:** Translation model sees previous context for:
   - Terminology consistency
   - Pronoun reference resolution
   - Style matching

### Why It Matters
- **Consistency:** Same terms translated consistently
- **Coherence:** Better flow between paragraphs
- **Quality:** Context helps with ambiguous terms

### Usage
```bash
scitrans translate \
  --in doc.pdf \
  --out doc_fr.pdf \
  --context 2 \  # Include previous 2 blocks
  --backend anthropic
```

### Recommended Settings
- **Short documents (<10 pages):** `--context 2`
- **Long documents (>50 pages):** `--context 1` or 0 (to avoid context length issues)
- **Technical docs:** `--context 3` (more terminology consistency needed)

---

## 6. Automatic Retry

### What It Does
Automatically retries failed translations with stronger constraints.

### How It Works
1. **Failure Detection:** Block fails if:
   - Translation empty
   - Placeholders missing
   - Backend error

2. **Retry Strategy:**
   - Lower temperature (more deterministic)
   - Stronger prompt: "CRITICAL: You MUST preserve ALL placeholders"
   - Single candidate (focus on quality)

3. **Success Check:** Validates retry result

4. **Fallback:** If still fails, marks block as failed (for manual repair)

### Why It Matters
- **Reliability:** Most failures recovered automatically
- **User Experience:** Fewer manual interventions
- **Quality:** Stricter constraints on retry

### Usage
Automatic. Enabled by default. Disable with:

```python
cfg = PipelineConfig(retry_failed=False)
```

### Monitoring
Check `translations.json` for blocks with `"retried": true` in metadata.

---

## 7. Health Scoring

### What It Does
Assigns a health score (0.0-1.0) to each translated block with detailed diagnostics.

### How It Works
**Scoring Components:**

1. **Placeholder Check** (critical): Missing placeholders → score = 0.0
2. **Numeric Stability**: Changed numbers → score penalty
3. **Format Preservation**: Lost bullets/line breaks → score penalty
4. **Overflow Detection**: Translation too long → score penalty

**Status Assignment:**
- `ok`: Score ≥ 0.9, no issues
- `warning`: Score 0.5-0.9, minor issues
- `failed`: Score < 0.5, critical issues

**Reason Codes:**
- `placeholder_missing`
- `numeric_drift`
- `format_drift`
- `potential_overflow`
- `translation_failed`

### Why It Matters
- **Quality Assurance:** Know which blocks are problematic
- **Selective Repair:** Fix only failed blocks
- **Metrics:** Track translation quality over time

### Usage
```bash
# Translate
scitrans translate --in doc.pdf --out doc_fr.pdf

# Check health scores
cat outputs/doc/health_scores.json | jq '.[] | select(.status!="ok")'

# Summary in report
cat outputs/doc/report.json | jq '.health'
```

### Example Health Score
```json
{
  "block_id": "b_0_abc123",
  "status": "warning",
  "score": 0.75,
  "reason_codes": ["numeric_drift"],
  "details": {
    "numeric_preservation": 0.75,
    "missing_numbers": ["42"]
  }
}
```

---

## 8. Selective Repair

### What It Does
Retranslate only failed/problematic blocks without re-running the entire pipeline.

### How It Works
1. **Load Artifacts:** Reads previous translation artifacts

2. **Identify Failed Blocks:** From `health_scores.json`

3. **Retranslate:** Only failed blocks, with repair mode prompt

4. **Update:** Merges repaired translations

5. **Re-render:** Generates new PDF with repaired blocks

### Why It Matters
- **Efficiency:** Fix 5 bad blocks instead of retranslating 500
- **Cost:** Only pay for failed block retranslations
- **Speed:** Repairs complete in seconds

### Usage
```bash
# Automatic (repair all failed blocks)
scitrans repair \
  --in doc.pdf \
  --out doc_repaired.pdf \
  --artifacts outputs/doc \
  --backend anthropic

# Manual (specific blocks)
scitrans repair \
  --in doc.pdf \
  --out doc_repaired.pdf \
  --artifacts outputs/doc \
  --blocks b_0_abc123,b_1_def456 \
  --backend anthropic
```

### Workflow
```bash
# 1. Initial translation
scitrans translate --in thesis.pdf --out thesis_fr.pdf

# 2. Check health
failed=$(cat outputs/thesis/health_scores.json | jq -r '.[] | select(.status=="failed") | .block_id' | wc -l)
echo "Failed blocks: $failed"

# 3. Repair if needed
if [ $failed -gt 0 ]; then
  scitrans repair --in thesis.pdf --out thesis_fr_repaired.pdf --artifacts outputs/thesis
fi
```

---

## 9. Layout-Safe Rendering

### What It Does
Renders translated text while preserving the original PDF layout perfectly.

### How It Works
**Redaction-First:**
1. Clear original text using redaction fill (white rectangle)
2. Apply redactions once per page
3. Insert translated text

**Font-Fit:**
1. Start with original font size
2. Binary search for largest size that fits
3. If still doesn't fit: reduce line height
4. Never create new pages

**Unicode-Safe Fonts:**
1. Detect original font style (bold, italic)
2. Map to bundled DejaVu font variant
3. Use fontfile parameter for guaranteed glyph coverage

### Why It Matters
- **No Overlap:** Redaction ensures clean replacement
- **No Overflow:** Font-fit keeps text in bounds
- **No ??? Characters:** Unicode fonts support all glyphs

### Configuration
```python
from scitrans.rendering.math_safe_renderer import RenderConfig

cfg = RenderConfig(
    min_font_size=5.0,           # Don't shrink below this
    max_shrink_ratio=0.55,       # Don't shrink below 55% of original
    line_height=1.2,             # Line spacing multiplier
    redact_padding=0.5,          # Padding around redacted area (pts)
    debug_draw_boxes=False,      # Draw red boxes around blocks (debug)
)
```

---

## 10. Glossary Enforcement

### What It Does
Ensures specific terms are translated consistently according to a glossary.

### How It Works
1. **Glossary Definition:** `{"source term": "target term"}`

2. **Prompt Injection:** Glossary added to system prompt

3. **Reranking:** Candidates scored on glossary compliance

4. **Hard Replacement** (optional): Force-replace terms after translation

### Why It Matters
- **Consistency:** "machine learning" always → "apprentissage automatique"
- **Domain Accuracy:** Technical terms translated correctly
- **Brand Names:** Company/product names preserved

### Usage
```python
glossary = {
    "machine learning": "apprentissage automatique",
    "neural network": "réseau de neurones",
    "deep learning": "apprentissage profond",
    "SciTrans": "SciTrans",  # Keep unchanged
}

from scitrans.pipeline import run_pipeline
report = run_pipeline(
    input_pdf="ml_paper.pdf",
    output_pdf="ml_paper_fr.pdf",
    backend=backend,
    cfg=cfg,
    glossary=glossary,
)
```

### Glossary File Format
```json
{
  "source_terms": {
    "machine learning": "apprentissage automatique",
    "neural network": "réseau de neurones"
  }
}
```

Load from file:
```python
import json
glossary = json.load(open("glossary_ml_en_fr.json"))["source_terms"]
```

---

## Feature Interaction Matrix

| Feature | Works With | Enhances | Conflicts |
|---------|------------|----------|-----------|
| Caching | All | Reranking, Retry | None |
| Reranking | Caching, Glossary | Health Scoring | None |
| Context Window | All | Translation Quality | Long docs (token limits) |
| Retry | All | Health Scoring | None |
| Glossary | Reranking, Masking | Terminology | None |
| Health Scoring | All | Selective Repair | None |
| Selective Repair | All features | Efficiency | None |

## Performance Tuning

**For Speed:**
- `--n-candidates 1` (no reranking)
- `--context 0` (no context)
- `--backend ollama` (local, no network)

**For Quality:**
- `--n-candidates 3` (reranking)
- `--context 2` (coherence)
- `--backend anthropic --model claude-3-5-sonnet`
- Use glossary for technical docs

**For Cost:**
- Enable caching (default)
- Use selective repair instead of re-translating
- `--backend google` or `ollama` (free)

**For Large Documents:**
- `--context 0` or `1` (avoid token limits)
- Split into smaller PDFs if > 100 pages
- Use caching to iterate on rendering without re-translating

