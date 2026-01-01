# Scripts

Utility scripts for SciTrans development, testing, and benchmarking.

## Available Scripts

### Setup and Configuration

#### `setup_api_keys.py`
Interactive script to configure API keys.

**Usage:**
```bash
python3 scripts/setup_api_keys.py
```

Or via Make:
```bash
make setup-keys
```

**What it does:**
- Prompts for API keys (Anthropic, OpenAI, Ollama)
- Creates/updates `.env` file
- Validates key format
- Never logs or commits keys

---

### Testing and Development

#### `create_test_pdfs.py`
Generate 10 test PDFs covering various scenarios.

**Usage:**
```bash
python3 scripts/create_test_pdfs.py
```

Or via Make:
```bash
make create-test-pdfs
```

**Generated PDFs:**
1. Simple text
2. Math equations
3. Bullet lists
4. Tables
5. Mixed fonts
6. Long paragraphs
7. Citations and URLs
8. Multi-column layout
9. Scientific paper structure
10. Complex real-world example

**Output:** `test_pdfs/*.pdf`

---

#### `check_repo_hygiene.py`
Automated repository hygiene checker.

**Usage:**
```bash
python3 scripts/check_repo_hygiene.py --root .
```

**Checks:**
- Git tracked files (no banned patterns)
- .gitignore completeness
- MANIFEST.in prune directives
- Local artifacts (informational)

**Strict mode (for CI):**
```bash
python3 scripts/check_repo_hygiene.py --root . --strict
```

---

#### `cleanup_repo_artifacts.sh`
Clean up development artifacts (caches, builds, compiled files).

**Usage:**
```bash
bash scripts/cleanup_repo_artifacts.sh
```

**Removes:**
- `.idea`, `.pytest_cache`, `.ruff_cache`, `.mypy_cache`
- `build/`, `dist/`, `*.egg-info`
- `__pycache__/`, `*.pyc`, `*.pyo`
- Test output PDFs
- Editor swap files

**Note:** Does NOT delete `.venv/` by default (add manually if needed).

---

### Benchmarking

#### `run_benchmarks.py`
Run translation benchmarks across multiple backends.

**Usage:**
```bash
# Free backends only (no API keys needed)
python3 scripts/run_benchmarks.py

# Include paid backends (requires keys)
python3 scripts/run_benchmarks.py --include-paid

# Custom PDFs and backends
python3 scripts/run_benchmarks.py --pdfs "my_pdfs/*.pdf" --backends "cascade_free,anthropic"
```

Or via Make:
```bash
make bench         # Free backends
make bench-paid    # Include paid
```

**Outputs:**
- Per-backend artifacts: `experiments/results/benchmarks/<backend>/<pdf>/`
- Summary: `experiments/results/benchmarks/summary.{json,csv}`

**Metrics captured:**
- Translation quality
- Health scores
- Processing time
- Cache hit rate
- Acceptance rate

---

#### `visualize_benchmarks.py`
Generate publication-quality visualizations from benchmark results.

**Usage:**
```bash
python3 scripts/visualize_benchmarks.py
```

Or via Make:
```bash
make viz-bench
```

**Requirements:**
```bash
pip install -e ".[thesis]"  # Installs matplotlib, pandas, scipy
```

**Generated figures (300 DPI PNG):**
1. `quality_by_document.png` — Quality per document per backend
2. `acceptance_rates.png` — Block acceptance rates
3. `health_scores.png` — Health ratios and failure rates
4. `performance_metrics.png` — Time and cache efficiency
5. `summary_comparison.png` — Overall comparison

**Output:** `experiments/results/benchmarks/figures/`

---

### Visualization

#### `preview_pdfs.py`
Generate side-by-side PDF previews for comparison.

**Usage:**
```bash
python3 scripts/preview_pdfs.py --source input.pdf --translated output.pdf

# Generate all pages
python3 scripts/preview_pdfs.py --source input.pdf --translated output.pdf --all
```

Or via Make:
```bash
make preview SOURCE=input.pdf TRANSLATED=output.pdf
```

**Requirements:**
```bash
pip install -e ".[preview]"  # Installs Pillow
```

**Output:** `previews/comparison_page_N.png`

---

## Make Commands

For convenience, most scripts have Make targets:

```bash
make setup-keys         # Setup API keys
make create-test-pdfs   # Generate test PDFs
make bench              # Run benchmarks (free)
make bench-paid         # Run benchmarks (paid)
make viz-bench          # Visualize benchmarks
make bench-all          # Bench + viz
make preview            # Preview PDFs (requires SOURCE and TRANSLATED)
```

## Script Development Guidelines

- Use `python3` explicitly (not `python`)
- Add shebang: `#!/usr/bin/env python3`
- Add docstring explaining purpose
- Use `argparse` or `typer` for CLI args
- Add `--help` support
- Handle errors gracefully
- Print clear success/failure messages
- Never log API keys or secrets

## Adding New Scripts

1. Create script in `scripts/<name>.py` or `.sh`
2. Add executable permissions: `chmod +x scripts/<name>.py`
3. Add docstring and usage examples
4. Add Make target in `Makefile` (optional)
5. Document in this README
6. Test in clean environment

## Troubleshooting

### Script can't find scitrans module
```bash
# Install in editable mode
pip install -e ".[dev]"
```

### Permission denied
```bash
chmod +x scripts/<script_name>
```

### Import errors
```bash
# Ensure virtual environment is activated
source .venv/bin/activate
```

## Contact

Questions about scripts? Contact: aknk.v@pm.me

