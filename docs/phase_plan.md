# Phase plan (rewrite to finished product)

This is the professional, step-by-step roadmap to build SciTrans into a stable product.

Each phase includes:
- **Goal**
- **Implementation details**
- **Acceptance criteria**
- **Artifacts & tests**

---

## Phase 0 — Productization baseline

### Goal
Set up repo so future work is fast, safe and measurable.

### Implementation
- Add `pyproject.toml` + editable install
- Add `ruff`, `black`, `mypy`, `pytest`
- Start CI: lint + unit tests
- Define artifact directory structure:
  - `outputs/<doc_id>/parsed.json`
  - `outputs/<doc_id>/masked.json`
  - `outputs/<doc_id>/translations.json`
  - `outputs/<doc_id>/rendered.pdf`
  - `outputs/<doc_id>/report.json`

### Acceptance
- `pip install -e .` works
- `pytest` passes
- `scitrans --help` works

---

## Phase 1 — Parsing & layout extraction

### Goal
Produce a **high-quality, stable Document model** from PDFs.

### Implementation details
1. Use PyMuPDF to extract:
   - blocks / lines / spans
   - bbox per element
   - font name, size, flags
2. Normalize coordinates to a consistent origin (top-left vs bottom-left).
3. Tag each block:
   - `text`, `image`, `vector`, `table_candidate`, `header/footer_candidate`
4. Add *merge rules*:
   - merge adjacent blocks if vertical gap small and fonts match
   - detect bullet lists and keep them grouped
5. Persist `parsed.json` for debugging.

### Acceptance
- `parsed.json` can be reloaded into the same model (roundtrip)
- For a known PDF:
  - number of blocks is stable run-to-run
  - block order is reading order (top-to-bottom)

### Tests
- `tests/test_parse_roundtrip.py`
- `tests/test_reading_order.py`

---

## Phase 2 — Masking + validation

### Goal
Prevent the translator from breaking math/code/URLs/citations and make restoration **guaranteed**.

### Implementation details
1. Mask engine produces placeholders:
   - Use a token format that models rarely modify, e.g. `⟦MATH_0001⟧`.
2. Keep a registry:
   - `placeholder -> original_text`
3. Validate after translation:
   - every placeholder present exactly once
   - if missing, run auto-repair:
     - attempt tolerant matching (strip spaces)
     - if still missing, retranslate with stronger instruction
4. Provide knobs:
   - `mask.citations = on/off`
   - `mask.preserve_numbers = on/off`
   - `mask.custom_patterns = [...]`

### Acceptance
- Placeholder restoration passes on 100% of blocks in a test PDF.
- No “mask restoration failed” hard errors in normal runs.

### Tests
- `tests/test_mask_roundtrip.py`
- `tests/test_mask_repair.py`

---

## Phase 3 — Translation engine

### Goal
Backends become **reliable**, not just “it sometimes works”.

### Implementation details
1. Backend interface:
   - `translate(text, *, source, target, system_prompt, temperature, n_candidates)`
2. Candidate generation + reranking:
   - score candidates by:
     - placeholder preservation
     - glossary compliance
     - numeric stability (same numbers retained)
     - format stability (line breaks, bullet markers)
3. Context:
   - pass previous N translated blocks (configurable)
4. Caching:
   - deterministic cache key from (backend, model, prompt, masked_text)
5. Failure policy:
   - retry with backoff
   - if block fails, mark failed but do not crash whole doc

### Acceptance
- No silent fallbacks
- Cached runs are 5–20× faster on the same document

### Tests
- `tests/test_backend_contract.py`
- `tests/test_cache_key_stability.py`

---

## Phase 4 — Rendering (the critical phase)

### Goal
**No overlaps. No missing blocks. No “moved to end pages”.**
Produce a clean translated PDF that *looks like the original*.

### Implementation details

#### 4.1 Redaction-first replacement
- Before inserting translated text, redact original text rectangles:
  - `page.add_redact_annot(rect, fill=)`
  - `page.apply_redactions()`
- This guarantees the original text is not visible behind the translation.

#### 4.2 Font-fit algorithm (overflow-safe)
- Start with original font size.
- Use binary search down to a minimum size.
- At each step:
  - attempt `insert_textbox(...)`
  - if it doesn’t fit (PyMuPDF returns negative), shrink more
- If it still doesn’t fit:
  - reduce line height
  - fallback: minimal font + clip (never create new pages unless configured)

#### 4.3 Math-safe
- Masked math is restored after translation, so the renderer never re-writes the math in a different language.
- If your PDFs contain *typeset* math, treat it as non-translatable spans and avoid redacting them (span-level redaction comes later).

#### 4.4 Tables
Two modes:
- **Safe mode (default)**: do not translate detected tables, keep as-is (no corruption).
- **Table mode (opt-in)**:
  - detect table grid (Camelot, pdfplumber)
  - translate cell strings
  - re-render cell text with per-cell font-fit

### Acceptance
- IoU/layout overlap metric improves to > 0.85 on page 1
- Overlapping blocks: 0
- 0 blocks rendered on “new appended pages” unless explicitly allowed

### Tests
- `tests/test_render_no_overlap.py`
- `tests/test_render_font_fit.py`
- Golden PDF snapshot tests (optional)

---

## Phase 5 — Scoring & auto-debug

### Goal
Make quality measurable and guide automatic repair.

### Implementation details
- Layout fidelity:
  - overlap count, IoU vs source block bboxes
- Format fidelity:
  - missing bullets, broken newlines, dropped citations
- Translation quality:
  - heuristic + optional LLM judge
- Visual similarity (optional):
  - SSIM via `scikit-image`

### Acceptance
- `report.json` shows per-block and per-page metrics
- GUI can highlight “bad blocks” with reason codes

---

## Phase 6 — GUI & review workflow

### Goal
Turn it into a usable product.

### Implementation details
- Gradio or FastAPI UI:
  - upload PDF
  - choose backend/model/language
  - preview page images side-by-side
  - click block → see source/translation + metrics
  - export PDF + report
- “Repair mode”:
  - retranslate only failed/low-score blocks

### Acceptance
- You can fix a broken doc by repairing 5–10 blocks, not re-running everything.

---

## Phase 7 — Packaging & release

### Goal
Make it installable and maintainable.

### Implementation details
- Versioned releases
- Model/backends documented
- Add “troubleshooting” doc for typical failures
- Performance profiling

### Acceptance
- `pipx install scitrans` works (or similar)
- Docs reflect reality, no dead options
