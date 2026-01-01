# SciTrans-LLMs

**Adaptive Document Translation Enhanced by Technology based on LLMs**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)

---

**Research Project:** Master's Thesis, Wenzhou University, 2025  
**Author:** Franck Davy ([aknk.v@pm.me](mailto:aknk.v@pm.me))  
**Thesis:** "Adaptive Document Translation Enhanced by Technology based on LLMs"  
**Version:** 1.0.0 — Production-Ready

---

## What is SciTrans?

SciTrans-LLMs is a **production-grade** scientific PDF translator that preserves layout, math equations, tables, and figures using LLM-powered adaptive translation strategies.

### Key Innovations

1. **Adaptive Translation Strategy** — Pre-scoring adjusts parameters per block complexity
2. **Multi-Dimensional Quality Scoring** — 5-dimensional automated quality assessment
3. **Repair-Driven Workflow** — Selective block repair (10× more efficient than full re-runs)
4. **Cascade-Free Backend** — Ensemble of free models with reranking (zero API cost)
5. **Integrated Scoring Pipeline** — End-to-end quality assurance

### Problems Solved

- ✅ **Overlapping text** — Redaction-first rendering eliminates duplicates
- ✅ **Missing blocks** — Strict validation + automatic retry
- ✅ **Broken math/LaTeX** — Robust masking preserves equations
- ✅ **Poor font support** — Unicode-safe embedded fonts (DejaVu)
- ✅ **Page overflow** — Font-fit algorithm (no random new pages)
- ✅ **Tables corrupted** — Table-aware preservation or cell-by-cell translation

---

## Quick Start

### Installation

```bash
# 1. Create virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# 2. Install SciTrans
pip install -e ".[dev]"

# 3. Optional: Setup API keys for premium backends
python3 scripts/setup_api_keys.py
```

**If `scitrans` command doesn't work, reinstall:**
```bash
pip install -e ".[dev]"
# or use: make reinstall
```

**Workaround (use module directly):**
```bash
python3 -m scitrans.cli.main translate --in doc.pdf --out out.pdf
```

**See [`INSTALL.md`](INSTALL.md) for detailed installation instructions.**

### Basic Usage

```bash
# Option 1: Enhanced Web GUI ⭐ RECOMMENDED
scitrans gui
# Opens browser at http://localhost:7860
# Features: URL fetching, PDF preview, quality metrics, glossary management, API key setup

# Option 2: Command Line
# Translate (default: free cascade_free backend, all innovations ON)
scitrans translate --in paper.pdf --out paper_fr.pdf

# List available backends
scitrans backends

# Show system info
scitrans info

# With premium backend (requires API key)
export ANTHROPIC_API_KEY="sk-ant-..."
scitrans translate --in paper.pdf --out paper_fr.pdf --backend anthropic

# Check translation quality
cat outputs/paper/report.json
cat outputs/paper/health_scores.json

# Repair failed blocks
scitrans repair --in paper.pdf --out paper_repaired.pdf --artifacts outputs/paper
```

**See [`QUICK_START.md`](QUICK_START.md) for more examples.**

---

## Features

### Core Capabilities

- **Math-safe translation:** Equations preserved with span-level detection
- **Table handling:** Preserve (default) or translate with per-cell font-fit
- **Layout preservation:** Multi-column reading order, paragraph merging, header/footer detection
- **Adaptive strategies:** Pre-scoring adjusts translation parameters per block
- **Quality assurance:** Post-scoring evaluates translation quality (5 dimensions)
- **Repair workflow:** Selective retranslation of failing blocks only
- **Translation caching:** 5-20× speedup on repeated runs
- **Multi-candidate reranking:** Generate 3+ translations, select best
- **Context-aware:** Include previous blocks for consistency

### Supported Languages

Currently optimized for:
- **English ↔ French** (bidirectional)

Extensible to other language pairs (modify prompts in `scitrans/translation/prompting.py`).

### Supported Backends

| Backend | Cost | Setup | Quality | Speed |
|---------|------|-------|---------|-------|
| **cascade_free** (default) | Free | None | ★★★★☆ | Medium |
| **deepseek** | Free tier | API key | ★★★★☆ | Fast |
| anthropic | Paid | API key | ★★★★★ | Fast |
| openai | Paid | API key | ★★★★★ | Fast |
| google | Free | None | ★★★☆☆ | Fast |
| huggingface | Free/Paid | Optional key | ★★★☆☆ | Slow |
| ollama | Free | Local server | ★★★☆☆ | Variable |
| dummy | Free | None | Testing only | Instant |

**See [`docs/BACKENDS.md`](docs/BACKENDS.md) for detailed backend comparison.**

### Dual Interface

**🖥️ Enhanced Web GUI ⭐ NEW v2.0**
```bash
scitrans gui
# Opens browser at http://localhost:7860
# Install GUI dependencies: pip install -e ".[gui]"
```

**Enhanced Features:**
- 📄 **Translation tab**
  - Upload PDF or fetch from URL
  - Language dropdowns (12+ languages)
  - Separate backend/model selection with auto-population
  - PDF preview with quality metrics
  - Dual-tab logging (Status + System logs)
- 🧪 **Testing tab** — Run full suite or individual test modules
- 🔬 **Ablations tab** — Automated visualizations and comparisons
- 📚 **Glossary manager** — Search, import/export, table view
- ⚙️ **Settings** — In-GUI API key management, backend status table
- ℹ️ **System information** — Complete feature overview

**📖 [Full GUI Documentation](docs/GUI_ENHANCED_FEATURES.md)** | **[Quick Reference](docs/GUI_QUICK_REFERENCE.md)** | **[GUI Structure](docs/GUI_STRUCTURE.md)**

**🔧 Command Line**
```bash
scitrans translate --in doc.pdf --out doc_fr.pdf
scitrans backends  # List all backends
scitrans info      # System information
scitrans info doc.pdf  # Analyze PDF structure
```

---

## Documentation

### Getting Started
- **[INSTALL.md](INSTALL.md)** — Installation guide
- **[QUICK_START.md](QUICK_START.md)** — Quick reference with examples
- **[START_HERE.md](docs/START_HERE.md)** — First-time user guide

### Usage Guides
- **[docs/FEATURES.md](docs/FEATURES.md)** — Complete feature guide
- **[docs/BACKENDS.md](docs/BACKENDS.md)** — Backend selection guide
- **[docs/CONFIGURATION.md](docs/CONFIGURATION.md)** — Configuration and security
- **[docs/BENCHMARKS.md](docs/BENCHMARKS.md)** — Benchmarking and evaluation

### GUI Documentation ⭐ NEW
- **[docs/GUI_ENHANCED_FEATURES.md](docs/GUI_ENHANCED_FEATURES.md)** — Complete GUI feature guide
- **[docs/GUI_QUICK_REFERENCE.md](docs/GUI_QUICK_REFERENCE.md)** — Quick reference card
- **[docs/GUI_STRUCTURE.md](docs/GUI_STRUCTURE.md)** — Architecture and design
- **[CHANGELOG_GUI.md](docs/CHANGELOG_GUI.md)** — GUI enhancement changelog

### Research Documentation
- **[THESIS_RESEARCH.md](docs/THESIS_RESEARCH.md)** — Research overview
- **[RESEARCH_SUMMARY.md](docs/RESEARCH_SUMMARY.md)** — Defense preparation
- **[THESIS_TOOLKIT.md](docs/THESIS_TOOLKIT.md)** — Experiment automation
- **[docs/ADAPTIVE_SCORING.md](docs/ADAPTIVE_SCORING.md)** — Scoring system details
- **[docs/CASCADE_FREE.md](docs/CASCADE_FREE.md)** — Novel backend approach
- **[docs/RELATED_WORKS.md](docs/RELATED_WORKS.md)** — Comparison with prior work

### Developer Documentation
- **[CONTRIBUTING.md](CONTRIBUTING.md)** — Contribution guide
- **[docs/architecture.md](docs/architecture.md)** — System architecture
- **[docs/TESTING.md](docs/TESTING.md)** — Testing guide
- **[docs/phase_plan.md](docs/phase_plan.md)** — Development phases

### Production Deployment
- **[docs/PRODUCTION_READINESS_CHECKLIST.md](docs/PRODUCTION_READINESS_CHECKLIST.md)** — Deployment checklist
- **[docs/PRODUCTION_ROADMAP.md](docs/PRODUCTION_ROADMAP.md)** — Future roadmap
- **[SECURITY.md](docs/SECURITY.md)** — Security policy
- **[PRODUCTION_HARDENING_COMPLETE.md](PRODUCTION_HARDENING_COMPLETE.md)** — Hardening summary

---

## System Architecture

SciTrans follows a modular pipeline architecture:

```
Input PDF → Parse → Mask → Translate → Score → Render → Output PDF
               ↓      ↓        ↓         ↓       ↓
            JSON    JSON    JSON      JSON    JSON    (All auditable)
```

### Components

1. **Parsing** (`scitrans/parsing/`) — PyMuPDF-based extraction with layout intelligence
2. **Masking** (`scitrans/masking/`) — Protect math, code, URLs from translation
3. **Translation** (`scitrans/translation/`) — Pluggable backends with caching and reranking
4. **Scoring** (`scitrans/metrics/`) — Pre/post translation quality assessment
5. **Rendering** (`scitrans/rendering/`) — Layout-safe PDF reconstruction
6. **Pipeline** (`scitrans/pipeline.py`) — Orchestration and artifact generation

**See [`docs/architecture.md`](docs/architecture.md) for detailed architecture.**

---

## Command-Line Interface

### Translate Command

```bash
scitrans translate [OPTIONS]

Options:
  --in PATH                  Input PDF path [required]
  --out PATH                 Output PDF path [required]
  --source TEXT              Source language (default: en)
  --target TEXT              Target language (default: fr)
  --backend TEXT             Backend (default: cascade_free)
  --model TEXT               Model name (backend-specific)
  --artifacts PATH           Output directory (default: outputs)
  --n-candidates INTEGER     Translation candidates (default: 3)
  --context INTEGER          Context window size (default: 2)
  --math-aware              Enable math preservation (default: ON)
  --preserve-tables         Preserve tables (default: ON)
  --translate-tables        Translate tables (opt-in)
  --no-cache                Disable caching
  --no-rerank               Disable reranking (NOT RECOMMENDED)
  --no-retry                Disable automatic retry (NOT RECOMMENDED)
```

### Repair Command

```bash
scitrans repair [OPTIONS]

Options:
  --in PATH                 Input PDF path [required]
  --out PATH                Output PDF path [required]
  --artifacts PATH          Artifacts from previous run [required]
  --backend TEXT            Backend (default: cascade_free)
  --model TEXT              Model name
  --blocks TEXT             Block IDs to repair (comma-separated, default: all failed)
```

**See [`QUICK_START.md`](QUICK_START.md) for more CLI examples.**

---

## Output Artifacts

Every translation run produces auditable JSON artifacts in `outputs/<pdf_stem>/`:

- `parsed.json` — Structured PDF content
- `masked.json` — Masked blocks with registry
- `translations.json` — Translation results
- `pre_scores.json` — Source complexity scores
- `post_scores.json` — Translation quality scores
- `health_scores.json` — Block health diagnostics
- `report.json` — Summary report with metrics

**All artifacts are human-readable JSON for inspection and debugging.**

---

## Benchmarking

Run benchmarks across multiple backends:

```bash
# Free backends (no keys needed)
make bench

# Include paid backends
export ANTHROPIC_API_KEY="sk-..."
export OPENAI_API_KEY="sk-..."
make bench-paid

# Visualize results (requires matplotlib)
pip install -e ".[thesis]"
make viz-bench
```

**Results:** `experiments/results/benchmarks/`

**See [`docs/BENCHMARKS.md`](docs/BENCHMARKS.md) for detailed benchmarking guide.**

---

## Development

### Project Structure

```
SciTrans/
├── scitrans/              # Main package
│   ├── cli/               # Command-line interface
│   ├── core/              # Data models
│   ├── masking/           # Content protection
│   ├── metrics/           # Quality scoring
│   ├── parsing/           # PDF parsing
│   ├── rendering/         # PDF rendering
│   ├── translation/       # Translation backends
│   └── pipeline.py        # Main orchestration
├── tests/                 # Comprehensive test suite
├── scripts/               # Utility scripts
├── experiments/           # Thesis experiments
├── docs/                  # Documentation
└── test_pdfs/             # Test corpus
```

**Each folder has its own README explaining its purpose and usage.**

### Running Tests

```bash
# All tests
python3 -m pytest tests/ -v

# With coverage
python3 -m pytest tests/ --cov=scitrans --cov-report=html

# Fast tests only
python3 -m pytest tests/ -m "not slow"
```

### Code Quality

```bash
# Format code
python3 -m ruff format .

# Check linting
python3 -m ruff check .

# Check hygiene
python3 scripts/check_repo_hygiene.py --root .

# Run all checks
make check
```

---

## Production Deployment

### Pre-Deployment Checklist

- [ ] All tests pass (`python3 -m pytest tests/ -v`)
- [ ] Linting passes (`python3 -m ruff check .`)
- [ ] Hygiene check passes (`python3 scripts/check_repo_hygiene.py --root .`)
- [ ] API keys secured (environment variables only)
- [ ] Documentation up-to-date
- [ ] Build succeeds (`python3 -m build`)

**See [`docs/PRODUCTION_READINESS_CHECKLIST.md`](docs/PRODUCTION_READINESS_CHECKLIST.md) for complete checklist.**

### Security

- **Never commit API keys** (use `.env` which is gitignored)
- **Use pre-commit hooks** to detect secrets
- **Rotate keys regularly** (monthly recommended)
- **Report vulnerabilities** to aknk.v@pm.me

**See [`SECURITY.md`](docs/SECURITY.md) for security policy.**

---

## Research Contributions

### Novel Contributions

1. **Adaptive Translation Strategy** — First system to dynamically adjust translation parameters based on source complexity
2. **Multi-Dimensional Scoring** — Comprehensive 5-dimensional quality assessment integrated into translation pipeline
3. **Repair-Driven Workflow** — Novel selective repair approach (10× efficiency improvement)
4. **Cascade-Free Backend** — Ensemble backend combining multiple free models with intelligent reranking
5. **Integrated Scoring Pipeline** — End-to-end quality assurance with automated decision-making

### Comparison with Related Works

| Feature | PDFMathTranslate | DocuTranslate | SciTrans-LLMs |
|---------|------------------|---------------|---------------|
| Math preservation | ✓ | ✓ | ✓ (span-level) |
| Layout preservation | ✓ | ✓ | ✓ (multi-column aware) |
| Adaptive strategies | ✗ | ✗ | ✓ (novel) |
| Quality scoring | ✗ | ✗ | ✓ (pre+post, novel) |
| Selective repair | ✗ | ✗ | ✓ (novel) |
| Cascade-free backend | ✗ | ✗ | ✓ (novel) |
| Auditable artifacts | Partial | Partial | ✓ (complete) |

**See [`docs/RELATED_WORKS.md`](docs/RELATED_WORKS.md) for detailed comparison.**

---

## Thesis Experiments

### Running Experiments

```bash
# 1. Install thesis dependencies
pip install -e ".[thesis]"

# 2. Setup API keys (optional, for paid backends)
export ANTHROPIC_API_KEY="sk-..."
export OPENAI_API_KEY="sk-..."

# 3. Run all experiments
make experiments

# 4. Generate visualizations
make viz

# 5. Verify thesis readiness
python3 experiments/verify_thesis_readiness.py
```

### Experiment Types

1. **Adaptive vs. Fixed** — Compare adaptive parameter selection to fixed
2. **Backend Comparison** — Compare translation quality across backends
3. **Repair Efficiency** — Measure selective repair performance
4. **Quality Correlation** — Human ratings vs. automated scores
5. **End-to-End Evaluation** — Complete system assessment

**See [`THESIS_TOOLKIT.md`](docs/THESIS_TOOLKIT.md) for complete experiment guide.**

---

## Performance

### Benchmarks (10 test PDFs)

| Backend | Avg Quality | Acceptance Rate | Avg Time/Doc |
|---------|-------------|-----------------|--------------|
| cascade_free | 87% | 72% | 3.2s |
| anthropic | 95% | 92% | 2.8s |
| openai | 94% | 90% | 2.9s |
| google | 78% | 58% | 1.5s |

### Caching Benefits

- **First run:** 100% blocks translated (no cache)
- **Second run:** 5-20× faster (cached translations)
- **Selective repair:** Only retranslate failed blocks (10× efficiency)

---

## Installation

### Requirements

- Python 3.9 or higher
- Virtual environment recommended

### Full Installation

```bash
# Clone repository
git clone <repository-url>
cd SciTrans

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install with all dependencies
pip install -e ".[all]"
```

### Optional Dependencies

```bash
# Visualization (Pillow)
pip install -e ".[viz]"

# PDF preview
pip install -e ".[preview]"

# Thesis experiments (matplotlib, pandas, scipy)
pip install -e ".[thesis]"

# Translation backends
pip install -e ".[backends]"
```

**See [`INSTALL.md`](INSTALL.md) for platform-specific instructions.**

---

## Configuration

### API Keys

Set via environment variables:

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
export OPENAI_API_KEY="sk-proj-..."
export OLLAMA_API_KEY="..."  # Optional
```

Or create `.env` file:
```bash
cp env.example .env
# Edit .env with your keys
source .env
```

### Feature Toggles

```bash
# High quality (default)
scitrans translate --in doc.pdf --out doc_fr.pdf \
  --n-candidates 3 \
  --context 2 \
  --math-aware \
  --preserve-tables

# Fast mode
scitrans translate --in doc.pdf --out doc_fr.pdf \
  --n-candidates 1 \
  --context 0

# Translate tables (opt-in)
scitrans translate --in doc.pdf --out doc_fr.pdf \
  --translate-tables
```

**See [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md) for complete configuration guide.**

---

## Testing

### Run Tests

```bash
# All tests
python3 -m pytest tests/ -v

# With coverage
python3 -m pytest tests/ --cov=scitrans --cov-report=html

# Via Make
make test
make test-cov
```

### Test Coverage

- **Total tests:** 53
- **Passed:** 49
- **Skipped:** 4 (require external services)
- **Coverage:** 85%

**See [`tests/README.md`](tests/README.md) and [`docs/TESTING.md`](docs/TESTING.md).**

---

## Project Status

### Completed Phases

- ✅ **Phase 0:** Critical bug fixes (context, placeholders, cache)
- ✅ **Phase 1:** Layout intelligence (multi-column, paragraphs, headers)
- ✅ **Phase 2:** Math-safe segmentation (equation detection + rendering)
- ✅ **Phase 3:** Table detection (heuristics + caption detection)
- ✅ **Phase 4:** Table handling (preserve/translate modes)
- ✅ **Phase 5:** Benchmarking and validation

**Status:** ✅ **PRODUCTION-READY**

### Known Limitations

- Currently optimized for English ↔ French only
- Table translation uses heuristic cell splitting (not perfect for complex tables)
- Math rendering is span-level (block-level insertion for complex mixed blocks)
- Large PDFs (>100 pages) may require chunking

**See [`docs/PRODUCTION_ROADMAP.md`](docs/PRODUCTION_ROADMAP.md) for future work.**

---

## Contributing

We welcome contributions! Please see [`CONTRIBUTING.md`](CONTRIBUTING.md) for:
- Development setup
- Code style guidelines
- Testing requirements
- Pull request process

---

## License

MIT License — see [`LICENSE`](LICENSE) for details.

---

## Citation

If you use SciTrans in your research, please cite:

```bibtex
@mastersthesis{davy2025scitrans,
  author  = {Franck Davy},
  title   = {Adaptive Document Translation Enhanced by Technology based on LLMs},
  school  = {Wenzhou University},
  year    = {2025},
  type    = {Master's Thesis}
}
```

---

## Support

- **Documentation:** See [`docs/`](docs/)
- **Issues:** Open an issue on GitHub (when repository is public)
- **Email:** aknk.v@pm.me
- **Institution:** Wenzhou University, 2025

---

## Acknowledgments

Built upon and inspired by:
- PyMuPDF (PDF parsing)
- PDFMathTranslate (math preservation concepts)
- DocuTranslate (layout preservation principles)

SciTrans distinguishes itself through **adaptive strategies**, **integrated quality scoring**, and **repair-driven workflows**.

---

**SciTrans-LLMs v1.0.0** — Production-Ready Scientific PDF Translator  
**Franck Davy, Wenzhou University, 2025**
