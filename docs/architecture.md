# Architecture

## Core design principles

1. **Span-first representation**
   - We parse PDF into *blocks → lines → spans* with bounding boxes and style.
   - All later steps (masking, translation, rendering, scoring) operate on this structure.

2. **Strict invariants**
   - Every translatable unit gets either:
     - a translation, or
     - a logged error + deterministic fallback (never silent loss).
   - Rendering never produces duplicate source text (redaction is mandatory unless configured otherwise).

3. **Backend-agnostic**
   - Translation backends implement the same interface and are swappable.
   - Prompting, masking, validation and reranking are backend-independent.

4. **Separation of concerns**
   - Parsing != translation != rendering != scoring.
   - Each module writes intermediate artifacts (JSON) for debugging and regression tests.

## Data flow

```
PDF -> Parser -> Document(page/blocks/spans)
    -> Segmenter (merge/split)
    -> Masking (placeholders + registry)
    -> Translation (backend + candidates + rerank + validate)
    -> Unmask (restore placeholders)
    -> Renderer (redact + insert + fit)
    -> Metrics (layout + format + quality)
    -> Output PDF + report.json
```

## Module map

- `scitrans/core/models.py`
  - Document model (Pydantic dataclasses)
- `scitrans/parsing/pymupdf_parser.py`
  - PDF → Document using PyMuPDF
- `scitrans/segment/`
  - Block merging/splitting rules (paragraphs, hyphenation, bullet lists)
- `scitrans/masking/engine.py`
  - Placeholder generation + restoration + validation
- `scitrans/translation/`
  - Prompt templates, backend interface, reranker
- `scitrans/rendering/math_safe_renderer.py`
  - Redaction + font-fit insertion + Unicode font strategy
- `scitrans/metrics/`
  - Layout fidelity, format fidelity, translation quality hooks
- `scitrans/cli/main.py`
  - `scitrans translate ...`
- `scitrans/gui/`
  - GUI / review tooling (phase 6)

## Why this fixes your current failures

- **Overlaps**: caused by overlay without removal.
  - This renderer redacts the original text regions before inserting translation.
- **Missing blocks**: caused by silent fallback.
  - This pipeline treats missing translation as an error and retries; if still missing, it marks block “failed” and reports it.
- **Math corruption**: caused by LLM altering LaTeX.
  - Masking enforces preservation and restoration validation.
- **Bad fonts**: caused by glyph-missing fonts.
  - We embed Unicode-safe fonts (DejaVu/Noto) when necessary.
- **Tables**: treated as a separate content type.
  - Phase 4.3 introduces a dedicated table pathway (extract → translate cells → re-render).
