# Files Responsible for Extraction, Translation, and Rendering

This document identifies the exact files responsible for each stage of the PDF translation pipeline.

## 📋 Pipeline Flow

```
PDF Input → EXTRACTION → MASKING → TRANSLATION → RENDERING → PDF Output
```

---

## 1️⃣ EXTRACTION (PDF Parsing)

**Primary File:** `scitrans/parsing/pymupdf_parser.py`

### Key Functions:
- `parse_pdf(path, use_layout_intelligence=True)` - Main entry point
- `_detect_and_tag_headers_titles(blocks)` - Detects headers/titles (line 35)
- `_sort_blocks_by_reading_order(blocks)` - Sorts blocks by reading order

### Supporting Files:
- `scitrans/parsing/layout.py` - Layout intelligence:
  - `detect_headers_footers()` - Detects page headers/footers
  - `detect_tables_and_captions()` - Detects tables
  - `merge_paragraph_blocks()` - Merges paragraphs
  - `sort_blocks_multicolumn()` - Multi-column reading order

### What It Does:
1. Extracts text blocks from PDF using PyMuPDF
2. Detects headers/titles based on font size, styling, and patterns
3. Tags blocks with metadata (`is_header`, `block_type`, etc.)
4. Organizes blocks by reading order

### Where Headers Might Be Lost:
- **Line 238**: `_detect_and_tag_headers_titles(blocks)` - If this doesn't detect a header, it won't be tagged
- **Line 216-217**: `detect_headers_footers()` - Headers in margins might be excluded
- **Line 134-139**: Empty blocks are skipped - if a header is empty, it's skipped

---

## 2️⃣ TRANSLATION (Backend Calls)

**Primary File:** `scitrans/pipeline.py`

### Key Functions:
- `run_pipeline()` - Main orchestration function (line 83)
- Translation loop: Lines 246-700 (approximately)
- Header detection: Lines 497-502
- Retry logic: Lines 504-650

### Key Sections:

#### Block Masking (Lines 116-161):
```python
# scitrans/pipeline.py, lines 124-150
for page in doc.pages:
    for block in page.blocks:
        if block.type != "text":
            continue
        # Skip tables and empty blocks
        # Mask and add to masked_blocks
```

#### Translation Loop (Lines 246-700):
```python
# scitrans/pipeline.py, lines 246-700
for idx, mb in enumerate(masked_blocks):
    # Check if header (lines 497-502)
    # Translate block
    # Retry if needed (lines 504-650)
    # Store in translations dict (line 661)
```

#### Header Special Handling (Lines 497-522):
- Detects if block is header/title
- Forces retry for headers with issues
- Enhanced retry prompt for headers

### Translation Backends:
- `scitrans/translation/backends/cascade_free.py` - Ensemble backend
- `scitrans/translation/backends/google_backend.py` - Google Translate
- `scitrans/translation/backends/ollama_backend.py` - Local Ollama
- `scitrans/translation/backends/deepseek_backend.py` - DeepSeek API
- `scitrans/translation/backends/openai_backend.py` - OpenAI API

### Prompt Building:
- `scitrans/translation/prompting.py` - `build_system_prompt()` - Creates translation instructions

### Where Headers Might Be Lost:
- **Line 136-139**: Empty blocks are skipped - if header text is empty after extraction
- **Line 661**: `translations[mb.block_id] = restored` - If translation fails, `restored` might be empty
- **Line 504-522**: Retry logic might not catch all header failures
- **Line 847-884**: Validation checks for missing headers but doesn't force retranslation

---

## 3️⃣ RENDERING (PDF Output)

**Primary File:** `scitrans/rendering/perfect_renderer.py` (default mode)

### Key Functions:
- `render_translated_pdf_perfect()` - Main renderer (line 296)
- `_should_replace_block()` - Decides if block should be replaced (line 263)
- `_get_block_base_style()` - Extracts font info (line 187)

### Supporting Renderers:
- `scitrans/rendering/enhanced_block_renderer.py` - Enhanced mode
- `scitrans/rendering/math_aware_renderer.py` - Math-aware mode
- `scitrans/rendering/math_safe_renderer.py` - Legacy math-safe mode

### Key Sections:

#### Block Replacement Decision (Lines 263-293):
```python
# scitrans/rendering/perfect_renderer.py, lines 263-293
def _should_replace_block(block, translations, translate_tables):
    # Returns (replace?, target_text, source_text)
    # Checks if translation exists and is valid
```

#### Redaction (Lines 324-346):
```python
# scitrans/rendering/perfect_renderer.py, lines 324-346
# Redacts original text blocks
for block in page_model.blocks:
    if block.type != "text":
        continue
    # Redact block
```

#### Text Insertion (Lines 348-421):
```python
# scitrans/rendering/perfect_renderer.py, lines 348-421
# Inserts translated text
for block in page_model.blocks:
    if block.type != "text":
        continue
    # Get translation
    # Insert text with font fitting
```

### Where Headers Might Be Lost:
- **Line 300-309**: If `_should_replace_block()` returns `False`, block is not replaced
- **Line 277-280**: Missing/empty translations cause block to be skipped
- **Line 327**: `if block.type != "text": continue` - Non-text blocks skipped (images OK)
- **Line 350**: `if block.type != "text": continue` - Same check in insertion loop

---

## 🔍 Debugging Missing Headers

### Step 1: Check Extraction
```python
# In scitrans/parsing/pymupdf_parser.py
# After line 239, add logging:
for block in blocks:
    if block.meta.get("is_header"):
        print(f"EXTRACTED HEADER: {block.id} - {_block_text(block)}")
```

### Step 2: Check Translation
```python
# In scitrans/pipeline.py
# After line 661, add logging:
if is_header_block:
    print(f"TRANSLATED HEADER: {mb.block_id} - {restored[:50]}")
```

### Step 3: Check Rendering
```python
# In scitrans/rendering/perfect_renderer.py
# After line 297, add logging:
if block.meta.get("is_header"):
    print(f"RENDERING HEADER: {block.id} - {target_text[:50] if target_text else 'MISSING'}")
```

---

## 📝 Summary

| Stage | Primary File | Key Function | Line Range |
|-------|-------------|--------------|------------|
| **Extraction** | `scitrans/parsing/pymupdf_parser.py` | `parse_pdf()` | 133-253 |
| **Header Detection** | `scitrans/parsing/pymupdf_parser.py` | `_detect_and_tag_headers_titles()` | 35-108 |
| **Masking** | `scitrans/pipeline.py` | Loop in `run_pipeline()` | 124-161 |
| **Translation** | `scitrans/pipeline.py` | Loop in `run_pipeline()` | 246-700 |
| **Header Retry** | `scitrans/pipeline.py` | Retry logic | 497-650 |
| **Rendering** | `scitrans/rendering/perfect_renderer.py` | `render_translated_pdf_perfect()` | 296-421 |
| **Block Replacement** | `scitrans/rendering/perfect_renderer.py` | `_should_replace_block()` | 263-293 |

---

## 🎯 Most Likely Causes of Missing Headers

1. **Extraction**: Header not detected (font size, pattern, or position)
   - Fix: Improve `_detect_and_tag_headers_titles()` in `pymupdf_parser.py`

2. **Translation**: Header translation failed (identity translation, empty result)
   - Fix: Improve retry logic in `pipeline.py` lines 497-650

3. **Rendering**: Header translation exists but not rendered
   - Fix: Check `_should_replace_block()` in `perfect_renderer.py` line 263

4. **Validation**: Header missing from translations dict
   - Fix: Improve validation and fallback in `pipeline.py` lines 847-884

