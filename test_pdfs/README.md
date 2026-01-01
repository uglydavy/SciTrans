# Test PDFs for SciTrans

This directory contains 10 test PDFs covering various scenarios to validate SciTrans functionality.

## Test PDFs

### 1. Simple Text (`01_simple_text.pdf`)
**Purpose:** Basic translation test  
**Content:** Simple English sentences, no special formatting  
**Tests:** Basic parsing, translation, rendering

### 2. Math Equations (`02_math_equations.pdf`)
**Purpose:** Math preservation test  
**Content:**
- Inline math: `$E=mc^2$`, `$\alpha + \beta = \gamma$`
- Display math: `$$...$$`, `\[...\]`
**Tests:** Masking engine, placeholder preservation

### 3. Bullet Lists (`03_bullet_lists.pdf`)
**Purpose:** Format preservation test  
**Content:**
- Bulleted lists (`•`)
- Numbered lists (1, 2, 3...)
**Tests:** Format stability scoring, bullet detection

### 4. Tables (`04_tables.pdf`)
**Purpose:** Table handling test  
**Content:** Simple text-based table with headers and data rows  
**Tests:** Table detection (future), layout preservation

### 5. Mixed Fonts (`05_mixed_fonts.pdf`)
**Purpose:** Font handling test  
**Content:** Normal, bold, italic text in various sizes  
**Tests:** Font manager, Unicode-safe rendering

### 6. Long Paragraphs (`06_long_paragraphs.pdf`)
**Purpose:** Overflow handling test  
**Content:** Long paragraphs that fill large text boxes  
**Tests:** Font-fit algorithm, word wrapping

### 7. Citations and URLs (`07_citations_urls.pdf`)
**Purpose:** Masking test for non-math content  
**Content:**
- Citations: `[1, 2, 3]`
- URLs: `https://example.com`
- Emails: `user@domain.com`
**Tests:** Multi-pattern masking, URL preservation

### 8. Multi-Column Layout (`08_multicolumn.pdf`)
**Purpose:** Reading order test  
**Content:** Two-column academic paper layout  
**Tests:** Reading order sorting (top-to-bottom, left column then right)

### 9. Scientific Paper (`09_scientific_paper.pdf`)
**Purpose:** Realistic document test  
**Content:**
- Title, authors, abstract
- Sections with math
- Keywords, references
**Tests:** Complete pipeline with realistic structure

### 10. Complex Real-World (`10_complex_realworld.pdf`)
**Purpose:** Stress test  
**Content:**
- Multi-page document
- Mixed content (text, math, tables, citations, URLs)
- Complex formatting
**Tests:** All features together, edge cases

## Running Tests

### Create Test PDFs
```bash
make create-test-pdfs
# Or:
python scripts/create_test_pdfs.py
```

### Test Individual PDF
```bash
scitrans translate \
  --in test_pdfs/02_math_equations.pdf \
  --out output.pdf \
  --backend dummy
```

### Test All PDFs
```bash
make test-all-pdfs
```

### With Real Translation (Anthropic)
```bash
export ANTHROPIC_API_KEY="..."
scitrans translate \
  --in test_pdfs/09_scientific_paper.pdf \
  --out output_fr.pdf \
  --backend anthropic \
  --n-candidates 3 \
  --context 2
```

## Expected Results

### All Test PDFs Should:
✅ Parse successfully (no crashes)  
✅ Generate health scores  
✅ Preserve layout (page count unchanged)  
✅ Pass placeholder validation (for PDFs with math)  
✅ Maintain format (bullets, numbers preserved)

### Specific Expectations

**02_math_equations.pdf:**
- All math placeholders preserved (100%)
- No math translated or mangled
- Health score: 1.0 (perfect)

**03_bullet_lists.pdf:**
- All bullets present in output
- Format stability score: 1.0
- No broken numbering

**06_long_paragraphs.pdf:**
- No overflow (text fits in bboxes)
- Font-fit applied as needed
- No new pages created

**08_multicolumn.pdf:**
- Reading order: left column → right column
- No mixed-up text between columns

**10_complex_realworld.pdf:**
- All features work together
- Multi-page support
- No catastrophic failures

## Validation

### Manual Validation
1. Open output PDF in viewer
2. Check for:
   - No overlapping text
   - Math preserved correctly
   - Layout matches original
   - No missing content

### Automated Validation
```bash
# Check health scores
cat outputs/test_pdfs/02_math_equations/health_scores.json | \
  jq '.[] | select(.status!="ok")'

# Should return nothing (all blocks OK)

# Check report
cat outputs/test_pdfs/02_math_equations/report.json | \
  jq '.health'
```

### Expected Health Metrics

**Good Translation:**
```json
{
  "mean_score": 0.95,
  "ok_blocks": 15,
  "warning_blocks": 1,
  "failed_blocks": 0,
  "health_ratio": 0.94
}
```

**Failed Translation:**
```json
{
  "mean_score": 0.65,
  "ok_blocks": 10,
  "warning_blocks": 3,
  "failed_blocks": 3,
  "health_ratio": 0.62
}
```

## Troubleshooting

**"ModuleNotFoundError: fitz":**
```bash
pip install pymupdf
```

**"Font error":**
Test PDFs use base fonts (no custom fonts required)

**"Translation failed":**
Try with dummy backend first to isolate issues:
```bash
scitrans translate --in test.pdf --out out.pdf --backend dummy
```

**"Health score low":**
Check `health_scores.json` for reason codes:
- `placeholder_missing` → Math masking failed
- `numeric_drift` → Numbers changed
- `format_drift` → Bullets/formatting lost

## Adding New Test PDFs

Edit `scripts/create_test_pdfs.py` and add a new function:

```python
def create_test_pdf_11_your_test(output_dir: Path):
    """11. Your test description."""
    doc = fitz.open()
    page = doc.new_page(width=500, height=400)
    
    # Add content
    page.insert_text((50, 50), "Test content", fontsize=12)
    
    doc.save(output_dir / "11_your_test.pdf")
    doc.close()
    print("✓ Created: 11_your_test.pdf")
```

Then call it in `main()`:
```python
create_test_pdf_11_your_test(output_dir)
```

## Test Coverage

These 10 PDFs cover:
- ✅ Simple text
- ✅ Math preservation
- ✅ Format preservation
- ✅ Font handling
- ✅ Overflow handling
- ✅ URL/citation masking
- ✅ Reading order
- ✅ Multi-page documents
- ✅ Complex real-world scenarios
- ✅ Stress testing

**Missing (future):**
- Tables with complex layouts (requires table-aware rendering)
- Images and figures (preserved automatically, not translated)
- Right-to-left languages (EN↔FR only currently)

