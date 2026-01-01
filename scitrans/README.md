# SciTrans Package

This is the core package for SciTrans-LLMs, containing all the translation logic, parsing, rendering, and backend implementations.

## Package Structure

```
scitrans/
├── __init__.py              # Package initialization, version
├── assets/                  # Static assets (fonts)
├── cli/                     # Command-line interface
├── core/                    # Core data models
├── masking/                 # Math/code/URL protection
├── metrics/                 # Quality and health scoring
├── parsing/                 # PDF parsing and layout intelligence
├── pipeline.py              # Main translation orchestration
├── rendering/               # PDF rendering engines
└── translation/             # Translation backends and utilities
```

## Core Modules

### `pipeline.py`
The central orchestrator that coordinates:
- PDF parsing
- Content masking
- Translation (with caching, reranking, context)
- Pre/post translation scoring
- Health scoring
- PDF rendering
- Artifact generation

**Key functions:**
- `run_pipeline()` — Full translation pipeline
- `repair_failed_blocks()` — Selective block repair

### `core/models.py`
Pydantic data models for the entire system:
- `Document`, `Page`, `Block`, `Line`, `Span` — PDF structure
- `MaskedBlock` — Masked content + registry
- `TranslatedBlock` — Translation results + metadata
- `SpanStyle`, `BBox` — Styling and geometry

### `cli/main.py`
Command-line interface using Typer:
- `scitrans translate` — Translate PDFs
- `scitrans repair` — Repair failed blocks

### `parsing/`
PDF parsing and layout intelligence:
- `pymupdf_parser.py` — PyMuPDF-based parser with deterministic block IDs
- `layout.py` — Multi-column, paragraph merging, header/footer/table detection
- `math_detection.py` — Math equation detection (fonts, Unicode, LaTeX)

### `masking/`
Content protection engine:
- `engine.py` — Mask/restore math, code, URLs, citations with robust placeholders

### `translation/`
Translation backends and utilities:
- `backends/` — Pluggable translation backends (Anthropic, OpenAI, HuggingFace, etc.)
- `cache.py` — Translation caching (5-20× speedup)
- `reranking.py` — Multi-candidate reranking
- `prompting.py` — System prompt generation

### `rendering/`
PDF rendering engines:
- `math_aware_renderer.py` — Preserves equation geometry (PHASE 2+)
- `math_safe_renderer.py` — Legacy renderer
- `font_manager.py` — Unicode-safe font selection

### `metrics/`
Quality assurance:
- `scoring.py` — Pre/post translation scoring (adaptive strategies)
- `health.py` — Block health diagnostics
- `layout.py` — Overlap detection, IoU metrics
- `quality.py` — Additional quality metrics

### `assets/`
Static resources:
- `fonts/` — Bundled Unicode-safe fonts (DejaVu)

## Usage

**As a library:**
```python
from scitrans.pipeline import PipelineConfig, run_pipeline
from scitrans.translation.backends.anthropic_backend import AnthropicBackend

cfg = PipelineConfig(
    source_lang="en",
    target_lang="fr",
    n_candidates=3,
    context_window=2,
)
backend = AnthropicBackend(model="claude-3-5-sonnet-20241022")

report = run_pipeline(
    input_pdf="paper.pdf",
    output_pdf="paper_fr.pdf",
    backend=backend,
    cfg=cfg,
)

print(report["num_ok"], "blocks translated successfully")
```

**As a CLI:**
```bash
scitrans translate --in paper.pdf --out paper_fr.pdf --backend anthropic
```

## Development

**Running tests:**
```bash
python3 -m pytest tests/ -v
```

**Linting:**
```bash
python3 -m ruff check scitrans/
python3 -m ruff format scitrans/
```

## Architecture Principles

1. **Modular:** Each component (parsing, masking, translation, rendering) is independent
2. **Deterministic:** Same PDF → same block IDs → cacheable
3. **Auditable:** Every run produces JSON artifacts for inspection
4. **Robust:** Strict validation, automatic retry, health scoring
5. **Production-ready:** No silent failures, clear error messages

## Key Innovations

1. **Adaptive Translation:** Pre-scoring adjusts parameters per block
2. **Multi-candidate Reranking:** Generate multiple translations, select best
3. **Repair-driven:** Only retranslate failing blocks (10× efficiency)
4. **Math-safe:** Preserve equation geometry (span-level preservation)
5. **Table-aware:** Preserve or translate with per-cell font-fit

## Contact

**Author:** Franck Davy (aknk.v@pm.me)  
**Institution:** Wenzhou University  
**Thesis:** "Adaptive Document Translation Enhanced by Technology based on LLMs"  
**Year:** 2025

