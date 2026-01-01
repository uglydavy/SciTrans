# Production Roadmap — Honest Assessment & Phase Plan

**Author:** Franck Davy  
**System:** SciTrans-LLMs  
**Current Status:** Strong foundation, but needs critical fixes + features for true production readiness

---

## Honest Assessment

### ✅ What's Good (Foundation is Solid)

1. **Clean Architecture**
   - Modular: parsing → masking → translation → rendering → scoring
   - Clear separation of concerns
   - Swappable backends (6 implemented)
   - Auditable artifacts (JSON at every stage)

2. **Strong Starting Features**
   - Deterministic block IDs
   - Math-safe masking engine
   - Multi-candidate reranking
   - Translation caching
   - Health scoring system
   - Multiple backends

3. **Good Development Practices**
   - Tests (9 suites)
   - Documentation (13 files)
   - Type hints
   - CLI interface

### ❌ Critical Bugs (Must Fix)

**BUG A: Context Handling is Wrong** 🔴 **CRITICAL**

**Problem:**
```python
# Current (WRONG):
text_to_translate = context_text + mb.masked_text
# This makes the model translate context too!
# Results: longer output, overflow, wrong cache keys
```

**Fix:**
```python
# Correct:
req = TranslateRequest(
    text=mb.masked_text,
    context=context_text,  # Separate field
    # Backend sends context as "reference only, do not translate"
)
```

**Impact:** Major rendering and quality issues

---

**BUG B: Placeholder Validation After Restoration** 🔴 **CRITICAL**

**Problem:**
```python
# In compute_block_health():
if registry:
    all_present = masker.placeholders_present(translated_block.translated_text, registry)
    # After restoration, placeholders SHOULD NOT be present!
    # They should be replaced with original content!
```

**Fix:**
```python
# Check placeholder preservation BEFORE restoration
# In pipeline, check on the masked translation before calling restore()
```

**Impact:** False negatives in health scoring

---

**BUG C: Cache Test Uses Timing** 🟡 **MEDIUM**

**Problem:**
```python
# test_integration.py:
assert time2 <= time1 * 1.5  # Unreliable due to OS caching
```

**Fix:**
```python
# Check cache hits instead:
assert "cached" in report2["translations"][0]["meta"]
```

---

### ⚠️ Missing Features (Not Yet Better Than PDFMathTranslate)

**MISSING A: True Math-Safe Rendering**

Currently: Redacts ALL text, including math symbols  
Should: Detect equation spans, preserve them, redact only natural language

**MISSING B: Multi-Column Reading Order**

Currently: Simple (y0, x0) sort  
Should: Column detection + paragraph merging

**MISSING C: Table Structure Preservation**

Currently: Tables extracted as plain text  
Should: Cell-level translation with structure preservation

**MISSING D: Benchmarking & Validation**

Currently: Claims without evidence  
Should: Quantitative evaluation on standard corpus

---

## Phase-by-Phase Roadmap to Production

### 🔴 PHASE 0: Critical Bug Fixes (THIS WEEK)

**Priority:** CRITICAL — System broken without these

**Tasks:**
1. ✅ Add `.gitignore` (done above)
2. ⏳ Fix Bug A: Context as separate field
3. ⏳ Fix Bug B: Placeholder validation logic
4. ⏳ Fix Bug C: Cache test assertions
5. ⏳ Fix indentation errors
6. ⏳ Remove unused imports
7. ⏳ Run full test suite and ensure all pass

**Acceptance:**
- All tests green
- Context doesn't cause overflow
- Health scores accurate
- Cache tests reliable

**Deliverable:** `SciTrans-LLMs-v1.0-bugfixed.zip`

---

### 🟡 PHASE 1: Core Correctness (WEEK 2)

**Priority:** HIGH — Make existing features work correctly

**Tasks:**
1. Improve reading order (basic column detection)
2. Paragraph merging heuristics
3. Validate mask/restore roundtrip on all test PDFs
4. Ensure rendering never creates overlaps
5. Font-fit convergence guarantee

**Acceptance:**
- 10 test PDFs translate without overlap
- Math preservation 99%+
- No false health failures

**Deliverable:** Reliable core pipeline

---

### 🟢 PHASE 2: Math-Safe Segmentation (WEEK 3-4)

**Priority:** HIGH — This is what makes it "better than PMT"

**Tasks:**
1. Detect equation spans (font-based heuristics)
2. Exclude math spans from redaction
3. Redact only natural language spans
4. Preserve inline math geometry
5. Validate on math-heavy PDFs

**Acceptance:**
- Inline math never redacted
- Display equations preserved
- Natural language translated cleanly

**Deliverable:** True math-safe rendering

---

### 🟢 PHASE 3: Layout Intelligence (WEEK 5)

**Priority:** MEDIUM — Improves quality significantly

**Tasks:**
1. Multi-column detection (x-coordinate clustering)
2. Header/footer detection
3. Caption merging
4. Paragraph flow detection
5. Reading order validation

**Acceptance:**
- Two-column PDFs parse correctly
- Captions stay together
- Reading order matches human expectation

**Deliverable:** Smart layout extraction

---

### 🟢 PHASE 4: Table Handling (WEEK 6)

**Priority:** MEDIUM — Requested feature

**Tasks:**
1. Table detection (grid pattern recognition)
2. Cell extraction
3. Cell-level translation
4. Structure-preserving rendering
5. Border/alignment preservation

**Acceptance:**
- Tables translate without corruption
- Cell alignment maintained
- Numbers in tables preserved

**Deliverable:** Table-aware translation

---

### 🟢 PHASE 5: Benchmarking & Validation (WEEK 7-8)

**Priority:** HIGH — Needed for thesis

**Tasks:**
1. Create benchmark corpus (20 scientific PDFs)
2. Implement layout fidelity metrics (IoU, overlap count)
3. Implement translation quality metrics (BLEU, COMET, QE)
4. Run comparison vs PDFMathTranslate, Google, DeepL
5. Collect human evaluation (3+ raters)
6. Statistical analysis

**Acceptance:**
- Quantitative results for all metrics
- Comparison tables
- Statistical significance tests

**Deliverable:** Validated system with evidence

---

### 🔵 PHASE 6: Production Polish (WEEK 9)

**Priority:** MEDIUM — Makes it actually usable

**Tasks:**
1. Error handling (graceful failures)
2. Progress bars (rich progress)
3. Logging system
4. Config file support
5. Batch processing
6. Resume capability

**Acceptance:**
- Handles errors gracefully
- User-friendly output
- Can process 100+ PDFs

**Deliverable:** User-friendly system

---

### 🔵 PHASE 7: GUI & Distribution (WEEK 10+)

**Priority:** LOW — Nice to have

**Tasks:**
1. Gradio web UI
2. Docker container
3. PyPI package
4. Documentation website
5. Tutorial videos

**Acceptance:**
- Web UI works
- `pip install scitrans-llms` works
- Documentation online

**Deliverable:** Public release

---

## Current Status: Which Phase Are We In?

**Reality Check:**
- PHASE 0: 50% complete (bugs identified, some fixed, some remain)
- PHASE 1: 70% complete (core works but has issues)
- PHASE 2: 0% complete (math segmentation not implemented)
- PHASE 3: 30% complete (basic reading order, no column detection)
- PHASE 4: 0% complete (tables not handled)
- PHASE 5: 10% complete (test PDFs created, no benchmarking)
- PHASE 6: 40% complete (CLI exists, no error handling)
- PHASE 7: 0% complete (no GUI)

**Honest assessment: ~40% to true production readiness**

---

## Recommended Approach

### For Thesis (Minimum Viable)

**Focus on:**
1. Fix PHASE 0 bugs (critical)
2. Complete PHASE 5 benchmarking (evidence)
3. Run experiments with current system
4. Acknowledge limitations in thesis
5. Propose future work (PHASE 2-4)

**Timeline:** 2-3 weeks

**Result:** Defensible thesis with honest evaluation

### For Production System

**Complete all phases:**
1. PHASE 0-1: Critical fixes (2 weeks)
2. PHASE 2-3: Math + layout intelligence (4 weeks)
3. PHASE 4: Tables (2 weeks)
4. PHASE 5: Benchmarking (2 weeks)
5. PHASE 6-7: Polish + release (4 weeks)

**Timeline:** 3-4 months

**Result:** True production system

---

## Next Steps (Choose One)

### Option A: Thesis-Focused (Recommended for Defense)

**Priority:** Fix bugs, run experiments, write thesis

**Steps:**
1. Fix PHASE 0 bugs (this week)
2. Run all 5 experiments (next week)
3. Collect human ratings (week 3)
4. Analyze results (week 4)
5. Write thesis (weeks 5-8)
6. Defend (week 9-10)

**Deliverable:** Defensible thesis with working system

### Option B: Production-Focused (Post-Defense)

**Priority:** Build truly best-in-class system

**Steps:**
1. Complete all phases 0-6 systematically
2. Benchmark against PDFMathTranslate rigorously
3. Open-source release
4. Conference paper submission

**Deliverable:** Production system + publications

---

## Decision Point

**Franck, which approach do you want?**

**A:** Focus on thesis defense (fix bugs, run experiments, write)  
**B:** Build complete production system (all phases, takes 3-4 months)  
**C:** Hybrid (fix bugs now, complete phases post-defense)

I recommend **C**: Fix critical bugs now, run experiments for thesis, complete remaining phases after defense.

---

**Current deliverable:**
- Strong foundation (40% to production)
- Critical bugs identified
- Clear roadmap to completion
- Realistic timeline

**Next action:**
Tell me which option (A/B/C) and I'll execute phase by phase.

