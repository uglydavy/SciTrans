# Benchmarks (Phase 5)

This runner executes translations across multiple backends on a small corpus of PDFs and aggregates quality/health/timing statistics. It defaults to free backends so it works without any API keys.

## Corpus
Uses the bundled test PDFs: `test_pdfs/*.pdf` (10 PDFs covering math, tables, multicolumn, bullets, references, long text, mixed fonts). You can point to your own corpus with `--pdfs`.

## Backends
- Free by default: `cascade_free`, `dummy`
- Optional paid (if keys set): `anthropic`, `openai`

Defaults are auto-detected; use `--include-paid` to add paid backends when keys are present.

## Running
```bash
# Free backends (no keys needed)
python scripts/run_benchmarks.py

# Include paid (if ANTHROPIC_API_KEY / OPENAI_API_KEY set)
python scripts/run_benchmarks.py --include-paid

# Custom PDFs and backends
python scripts/run_benchmarks.py --pdfs "my_pdfs/*.pdf" --backends "cascade_free,anthropic" --include-paid
```

## Outputs
- Per-backend artifacts under `experiments/results/benchmarks/<backend>/<pdf_stem>/...`
- Summary files under `experiments/results/benchmarks/`:
  - `summary.json`
  - `summary.csv`

Metrics captured per run: duration, num_blocks, num_ok, num_failed, document_quality, confidence, acceptance_rate (when available).

## Make targets
```bash
make bench        # free backends
make bench-paid   # include paid if keys set
make viz-bench    # visualize benchmark results
make bench-all    # run benchmarks + generate visualizations
```

## Visualization

After running benchmarks, generate publication-quality figures:

```bash
python scripts/visualize_benchmarks.py
# or
make viz-bench
```

**Generated figures** (saved to `experiments/results/benchmarks/figures/`):
1. `quality_by_document.png` — Quality scores per document per backend
2. `acceptance_rates.png` — Block acceptance rate comparison
3. `health_scores.png` — Health ratios and failure rates
4. `performance_metrics.png` — Processing time and cache efficiency
5. `summary_comparison.png` — Overall quality/health/acceptance/confidence

All figures are 300 DPI PNG suitable for thesis/papers.

